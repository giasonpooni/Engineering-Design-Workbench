"""Phase 19: DerivedGrounding -- what a DerivedValue is ABOUT, kept
strictly separate from what it was derived FROM (Phase 18's
`derived_from`/`ancestry_of`). Same fixture/testing style as
`tests/test_evidence_derived_value.py` and
`tests/test_evidence_provenance.py`: objects built directly via `make_*`
+ `pool.put_*` where admission isn't the thing under test.
"""

import ast
from pathlib import Path

import pytest

from evidence.admission import admit_derived_grounding
from evidence.pool import EvidencePool
from evidence.provenance import ancestry_of
from evidence.trust_graph import build_trust_graph
from evidence.types import (
    make_derived_grounding,
    make_derived_value,
    make_document,
    make_observation,
    make_record,
    make_referent,
    make_source,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _pool_with_observations_and_referents(n_observations, referent_natural_keys):
    pool = EvidencePool()
    source = make_source(kind="paper", name="X")
    pool.put_source(source)
    document = make_document(source_id=source.id, raw_content="body", retrieval_method="m", retrieved_at="t")
    pool.put_document(document)
    record = make_record(document_id=document.id, locator="p1", raw_content="body")
    pool.put_record(record)
    observations = []
    for i in range(n_observations):
        o = make_observation(
            record_ids=(record.id,),
            extraction_method="regex:kv_v1",
            content={"value": 1000 + i},
            confidence=1.0,
            extracted_at="t",
        )
        pool.put_observation(o)
        observations.append(o)
    referents = []
    for key in referent_natural_keys:
        r = make_referent(natural_key=key, kind="reactor")
        pool.put_referent(r)
        referents.append(r)
    return pool, observations, referents


def _derived_value(observation, value):
    d = make_derived_value(
        derived_from=[observation.id], method="accept_as_is", content={"v": value}, confidence=1.0, derived_at="t"
    )
    return d


# -- Identity -----------------------------------------------------------------


def test_identity_same_inputs_same_id():
    pool, (o1,), (r1,) = _pool_with_observations_and_referents(1, ["reactor-a"])
    d1 = _derived_value(o1, 82)
    pool.put_derived_value(d1)

    g1 = make_derived_grounding(derived_value_id=d1.id, referent_ids=[r1.id])
    g2 = make_derived_grounding(derived_value_id=d1.id, referent_ids=[r1.id])
    assert g1.id == g2.id


def test_identity_differs_by_derived_value_id():
    pool, (o1, o2), (r1,) = _pool_with_observations_and_referents(2, ["reactor-a"])
    d1 = _derived_value(o1, 82)
    d2 = _derived_value(o2, 82)
    pool.put_derived_value(d1)
    pool.put_derived_value(d2)

    g1 = make_derived_grounding(derived_value_id=d1.id, referent_ids=[r1.id])
    g2 = make_derived_grounding(derived_value_id=d2.id, referent_ids=[r1.id])
    assert g1.id != g2.id


def test_identity_differs_by_referent_ids():
    pool, (o1,), (r1, r2) = _pool_with_observations_and_referents(1, ["reactor-a", "reactor-b"])
    d1 = _derived_value(o1, 82)
    pool.put_derived_value(d1)

    g1 = make_derived_grounding(derived_value_id=d1.id, referent_ids=[r1.id])
    g2 = make_derived_grounding(derived_value_id=d1.id, referent_ids=[r2.id])
    assert g1.id != g2.id


def test_identity_does_not_change_derived_value_id():
    pool, (o1,), (r1,) = _pool_with_observations_and_referents(1, ["reactor-a"])
    d1 = _derived_value(o1, 82)
    id_before = d1.id
    pool.put_derived_value(d1)

    make_derived_grounding(derived_value_id=d1.id, referent_ids=[r1.id])
    assert d1.id == id_before


# -- Normalization --------------------------------------------------------------


def test_referent_ids_deduplicated():
    pool, (o1,), (r1,) = _pool_with_observations_and_referents(1, ["reactor-a"])
    d1 = _derived_value(o1, 82)
    pool.put_derived_value(d1)

    g = make_derived_grounding(derived_value_id=d1.id, referent_ids=[r1.id, r1.id, r1.id])
    assert g.referent_ids == (r1.id,)


def test_referent_ids_sorted_regardless_of_construction_order():
    pool, (o1,), (r1, r2) = _pool_with_observations_and_referents(1, ["reactor-a", "reactor-b"])
    d1 = _derived_value(o1, 82)
    pool.put_derived_value(d1)

    g_a = make_derived_grounding(derived_value_id=d1.id, referent_ids=[r1.id, r2.id])
    g_b = make_derived_grounding(derived_value_id=d1.id, referent_ids=[r2.id, r1.id])
    assert g_a.id == g_b.id
    assert g_a.referent_ids == tuple(sorted([r1.id, r2.id]))


def test_empty_referent_set_constructible_but_admission_rejects_it():
    pool, (o1,), _ = _pool_with_observations_and_referents(1, [])
    d1 = _derived_value(o1, 82)
    pool.put_derived_value(d1)

    g = make_derived_grounding(derived_value_id=d1.id, referent_ids=[])
    assert g.referent_ids == ()

    result = admit_derived_grounding(pool, g)
    assert isinstance(result, list)
    assert any(e.code == "NO_REFERENT_IDS" for e in result)


# -- Admission --------------------------------------------------------------------


def test_admit_rejects_unknown_derived_value_id():
    pool, _, (r1,) = _pool_with_observations_and_referents(0, ["reactor-a"])
    g = make_derived_grounding(derived_value_id="ghost-derived-value", referent_ids=[r1.id])

    result = admit_derived_grounding(pool, g)
    assert isinstance(result, list)
    assert any(e.code == "UNKNOWN_DERIVED_VALUE" for e in result)


def test_admit_rejects_unknown_referent_id():
    pool, (o1,), _ = _pool_with_observations_and_referents(1, [])
    d1 = _derived_value(o1, 82)
    pool.put_derived_value(d1)

    g = make_derived_grounding(derived_value_id=d1.id, referent_ids=["ghost-referent"])
    result = admit_derived_grounding(pool, g)
    assert isinstance(result, list)
    assert any(e.code == "UNKNOWN_REFERENT" for e in result)


def test_admit_aggregates_multiple_errors():
    pool = EvidencePool()
    g = make_derived_grounding(derived_value_id="ghost-derived-value", referent_ids=["ghost-1", "ghost-2"])

    result = admit_derived_grounding(pool, g)
    assert isinstance(result, list)
    codes = {e.code for e in result}
    assert "UNKNOWN_DERIVED_VALUE" in codes
    assert "UNKNOWN_REFERENT" in codes
    assert sum(1 for e in result if e.code == "UNKNOWN_REFERENT") == 2


def test_admit_accepts_valid_grounding():
    pool, (o1,), (r1,) = _pool_with_observations_and_referents(1, ["reactor-a"])
    d1 = _derived_value(o1, 82)
    pool.put_derived_value(d1)

    g = make_derived_grounding(derived_value_id=d1.id, referent_ids=[r1.id])
    result = admit_derived_grounding(pool, g)
    assert result is g


def test_rejected_admission_does_not_mutate_pool():
    pool, (o1,), (r1,) = _pool_with_observations_and_referents(1, ["reactor-a"])
    d1 = _derived_value(o1, 82)
    pool.put_derived_value(d1)

    fingerprint_before = pool.fingerprint()
    history_before = pool.fingerprint_history()

    bad = make_derived_grounding(derived_value_id="ghost", referent_ids=["ghost-2"])
    result = admit_derived_grounding(pool, bad)
    assert isinstance(result, list)

    assert pool.fingerprint() == fingerprint_before
    assert pool.fingerprint_history() == history_before
    assert pool.all_derived_groundings() == ()


# -- Immutability -----------------------------------------------------------------


def test_derived_grounding_is_frozen():
    pool, (o1,), (r1,) = _pool_with_observations_and_referents(1, ["reactor-a"])
    d1 = _derived_value(o1, 82)
    pool.put_derived_value(d1)
    g = make_derived_grounding(derived_value_id=d1.id, referent_ids=[r1.id])

    with pytest.raises(AttributeError):
        g.referent_ids = (r1.id,)  # type: ignore[misc]


# -- Pool integration ---------------------------------------------------------------


def test_pool_put_get_has_all():
    pool, (o1,), (r1,) = _pool_with_observations_and_referents(1, ["reactor-a"])
    d1 = _derived_value(o1, 82)
    pool.put_derived_value(d1)
    g = make_derived_grounding(derived_value_id=d1.id, referent_ids=[r1.id])

    assert not pool.has_derived_grounding(g.id)
    pool.put_derived_grounding(g)
    assert pool.has_derived_grounding(g.id)
    assert pool.get_derived_grounding(g.id) == g
    assert pool.all_derived_groundings() == (g,)


def test_fingerprint_includes_eighth_category():
    pool, (o1,), (r1,) = _pool_with_observations_and_referents(1, ["reactor-a"])
    d1 = _derived_value(o1, 82)
    pool.put_derived_value(d1)

    fingerprint_before = pool.fingerprint()
    g = make_derived_grounding(derived_value_id=d1.id, referent_ids=[r1.id])
    pool.put_derived_grounding(g)
    assert pool.fingerprint() != fingerprint_before


def test_fingerprint_history_observes_grounding_admission():
    pool, (o1,), (r1,) = _pool_with_observations_and_referents(1, ["reactor-a"])
    d1 = _derived_value(o1, 82)
    pool.put_derived_value(d1)

    history_before = pool.fingerprint_history()
    g = make_derived_grounding(derived_value_id=d1.id, referent_ids=[r1.id])
    pool.put_derived_grounding(g)
    history_after = pool.fingerprint_history()

    assert len(history_after) == len(history_before) + 1
    assert history_after[-1] == pool.fingerprint()


def test_duplicate_grounding_put_is_idempotent_and_does_not_grow_history():
    pool, (o1,), (r1,) = _pool_with_observations_and_referents(1, ["reactor-a"])
    d1 = _derived_value(o1, 82)
    pool.put_derived_value(d1)
    g = make_derived_grounding(derived_value_id=d1.id, referent_ids=[r1.id])
    pool.put_derived_grounding(g)

    fingerprint_before = pool.fingerprint()
    history_before = pool.fingerprint_history()
    pool.put_derived_grounding(g)

    assert pool.fingerprint() == fingerprint_before
    assert pool.fingerprint_history() == history_before
    assert pool.all_derived_groundings() == (g,)


# -- Coexistence ----------------------------------------------------------------------


def test_multiple_groundings_for_the_same_derived_value_coexist():
    """No uniqueness or conflict-resolution logic exists -- two
    independent groundings naming different referent sets for the same
    DerivedValue both persist, exactly like ClaimedRelationship's own
    conflict-coexistence discipline."""
    pool, (o1,), (r1, r2) = _pool_with_observations_and_referents(1, ["reactor-a", "reactor-b"])
    d1 = _derived_value(o1, 82)
    pool.put_derived_value(d1)

    g1 = make_derived_grounding(derived_value_id=d1.id, referent_ids=[r1.id])
    g2 = make_derived_grounding(derived_value_id=d1.id, referent_ids=[r2.id])
    pool.put_derived_grounding(g1)
    pool.put_derived_grounding(g2)

    assert g1.id != g2.id
    assert {g.id for g in pool.all_derived_groundings()} == {g1.id, g2.id}


# -- The central semantic scenario: Reactor A vs Reactor B ------------------------------


def test_identical_content_derivations_independently_grounded_to_different_referents():
    """D1 = '82% conversion' derived from Reactor-A observations;
    D2 = '82% conversion' derived from Reactor-B observations. Grounding
    answers the subject question -- D1 -> Reactor-A, D2 -> Reactor-B --
    without DerivedValue.id ever encoding it."""
    pool, (o_a, o_b), (reactor_a, reactor_b) = _pool_with_observations_and_referents(
        2, ["reactor-a", "reactor-b"]
    )
    d1 = make_derived_value(
        derived_from=[o_a.id], method="model:conversion_predictor", content={"conversion_pct": 82},
        confidence=0.9, derived_at="t",
    )
    d2 = make_derived_value(
        derived_from=[o_b.id], method="model:conversion_predictor", content={"conversion_pct": 82},
        confidence=0.9, derived_at="t",
    )
    pool.put_derived_value(d1)
    pool.put_derived_value(d2)

    # Same content, same method -- distinct ids only because derived_from differs.
    assert d1.content == d2.content
    assert d1.method == d2.method
    assert d1.id != d2.id

    g1 = make_derived_grounding(derived_value_id=d1.id, referent_ids=[reactor_a.id])
    g2 = make_derived_grounding(derived_value_id=d2.id, referent_ids=[reactor_b.id])
    pool.put_derived_grounding(g1)
    pool.put_derived_grounding(g2)

    assert admit_derived_grounding(pool, g1) is g1
    assert admit_derived_grounding(pool, g2) is g2

    groundings_by_derived_value = {g.derived_value_id: g.referent_ids for g in pool.all_derived_groundings()}
    assert groundings_by_derived_value[d1.id] == (reactor_a.id,)
    assert groundings_by_derived_value[d2.id] == (reactor_b.id,)

    # The distinction was never made by mutating or re-deriving D1/D2's identity.
    id_a_before, id_b_before = d1.id, d2.id
    assert d1.id == id_a_before
    assert d2.id == id_b_before


# -- Provenance non-interference ----------------------------------------------------------


def test_ancestry_of_unaffected_by_presence_of_grounding():
    pool, (o1,), (r1,) = _pool_with_observations_and_referents(1, ["reactor-a"])
    d1 = _derived_value(o1, 82)
    pool.put_derived_value(d1)

    ancestry_without_grounding = ancestry_of(pool, d1.id)

    g = make_derived_grounding(derived_value_id=d1.id, referent_ids=[r1.id])
    pool.put_derived_grounding(g)

    ancestry_with_grounding = ancestry_of(pool, d1.id)
    assert ancestry_without_grounding == ancestry_with_grounding


# -- Trust graph non-interference ----------------------------------------------------------


def test_trust_graph_unaffected_by_derived_grounding():
    pool, (o1,), (r1,) = _pool_with_observations_and_referents(1, ["reactor-a"])
    d1 = _derived_value(o1, 82)
    pool.put_derived_value(d1)

    graph_before = build_trust_graph(pool)

    g = make_derived_grounding(derived_value_id=d1.id, referent_ids=[r1.id])
    pool.put_derived_grounding(g)

    graph_after = build_trust_graph(pool)
    assert graph_before == graph_after
    assert graph_after.edges == ()


# -- PYTHONHASHSEED determinism --------------------------------------------------------------


def test_identity_deterministic_across_hash_seeds():
    import subprocess
    import sys

    script = (
        "from evidence.types import make_derived_grounding\n"
        "g = make_derived_grounding(derived_value_id='dv-1', referent_ids=['r-b', 'r-a', 'r-a'])\n"
        "print(g.id, g.referent_ids)\n"
    )
    outputs = set()
    for seed in ("0", "1", "12345"):
        proc = subprocess.run(
            [sys.executable, "-c", script],
            cwd=REPO_ROOT,
            env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode == 0, proc.stderr
        outputs.add(proc.stdout)
    assert len(outputs) == 1, f"DerivedGrounding identity differed across PYTHONHASHSEED values: {outputs}"


# -- Boundary ------------------------------------------------------------------------------


def _python_files(package_dir: Path):
    return [p for p in package_dir.rglob("*.py") if "test_" not in p.name]


def _imported_modules(path: Path):
    tree = ast.parse(path.read_text())
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def test_evidence_never_imports_retrieval_core_runtime_scout():
    forbidden_prefixes = ("retrieval", "core", "runtime", "scout")
    for path in _python_files(REPO_ROOT / "evidence"):
        for module in _imported_modules(path):
            assert not module.startswith(forbidden_prefixes), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} -- evidence/ must stay isolated"
            )


def test_retrieval_never_references_derived_grounding():
    for path in _python_files(REPO_ROOT / "retrieval"):
        text = path.read_text().lower()
        assert "derivedgrounding" not in text and "derived_grounding" not in text, (
            f"{path.relative_to(REPO_ROOT)} references DerivedGrounding -- "
            f"Phase 19 explicitly does not make DerivedGrounding retrievable"
        )


def test_epistemic_module_unaware_of_derived_grounding():
    text = (REPO_ROOT / "retrieval" / "epistemic.py").read_text().lower()
    assert "derivedgrounding" not in text and "derived_grounding" not in text


# -- Regression: existing golden identities unaffected --------------------------------------


def test_derived_value_id_unchanged_by_grounding_construction():
    pool, (o1,), (r1,) = _pool_with_observations_and_referents(1, ["reactor-a"])
    d1 = _derived_value(o1, 82)
    expected_id = d1.id
    pool.put_derived_value(d1)
    make_derived_grounding(derived_value_id=d1.id, referent_ids=[r1.id])
    pool.put_derived_grounding(make_derived_grounding(derived_value_id=d1.id, referent_ids=[r1.id]))
    assert d1.id == expected_id
    assert pool.get_derived_value(d1.id).id == expected_id


def test_retrieval_result_and_context_package_ids_unaffected_by_grounding():
    from retrieval.context import build_context_package
    from retrieval.engine import DeterministicRetrievalEngine
    from retrieval.query import make_retrieval_query
    from evidence.types import make_claimed_relationship

    pool, (o1,), (r1, r2) = _pool_with_observations_and_referents(1, ["reactor-a", "reactor-b"])
    rel = make_claimed_relationship(
        from_referent_id=r1.id, to_referent_id=r2.id, type="feeds", observation_id=o1.id, confidence=1.0
    )
    pool.put_claimed_relationship(rel)

    query = make_retrieval_query(entity_natural_keys=("reactor-a",), traversal_depth=1)
    engine = DeterministicRetrievalEngine()
    result_before = engine.retrieve(pool, query)
    context_before = build_context_package((result_before,))

    d1 = _derived_value(o1, 82)
    pool.put_derived_value(d1)
    g = make_derived_grounding(derived_value_id=d1.id, referent_ids=[r1.id])
    pool.put_derived_grounding(g)

    query_2 = make_retrieval_query(entity_natural_keys=("reactor-a",), traversal_depth=1)
    result_after = engine.retrieve(pool, query_2)
    context_after = build_context_package((result_after,))

    assert query.id == query_2.id
    assert result_before.referent_ids == result_after.referent_ids
    assert result_before.relationship_ids == result_after.relationship_ids
    assert result_before.observation_ids == result_after.observation_ids
    # evidence_version_id / RetrievalResult.id / ContextPackage.id legitimately
    # change here because the pool's fingerprint changed (new categories were
    # added, per fingerprint()'s own documented, non-breaking behavior) -- what
    # must NOT change is which referents/relationships/observations are found.
    assert result_after.evidence_version_id == pool.fingerprint()
    assert context_after.referent_ids == context_before.referent_ids
