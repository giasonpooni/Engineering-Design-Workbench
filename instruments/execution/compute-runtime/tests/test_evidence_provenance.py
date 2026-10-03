"""Phase 18: provenance-ancestry traversal over DerivedValue.derived_from
chains -- the first thing in this codebase able to answer "what does
this DerivedValue ultimately rest on?" without walking `derived_from` by
hand. Same style as `tests/test_evidence_derived_value.py`: DerivedValue
fixtures built directly via `make_*` + `pool.put_*`, no admission gate
involved (ancestry_of is a read-only query, not an admission concern).
"""

import ast
from pathlib import Path

import pytest

from evidence.pool import EvidencePool
from evidence.provenance import ProvenanceAncestry, ancestry_of
from evidence.types import make_derived_value, make_document, make_observation, make_record, make_source

REPO_ROOT = Path(__file__).resolve().parent.parent


def _pool_with_observations(n):
    pool = EvidencePool()
    source = make_source(kind="paper", name="X")
    pool.put_source(source)
    document = make_document(source_id=source.id, raw_content="body", retrieval_method="m", retrieved_at="t")
    pool.put_document(document)
    record = make_record(document_id=document.id, locator="p1", raw_content="body")
    pool.put_record(record)
    observations = []
    for i in range(n):
        o = make_observation(
            record_ids=(record.id,),
            extraction_method="regex:kv_v1",
            content={"value": 1000 + i},
            confidence=1.0,
            extracted_at="t",
        )
        pool.put_observation(o)
        observations.append(o)
    return pool, observations


# -- A. Direct provenance ----------------------------------------------------


def test_direct_provenance():
    pool, (o1,) = _pool_with_observations(1)
    d1 = make_derived_value(derived_from=[o1.id], method="accept_as_is", content={"v": 1}, confidence=1.0, derived_at="t")
    pool.put_derived_value(d1)

    ancestry = ancestry_of(pool, d1.id)
    assert ancestry.root_derived_value_id == d1.id
    assert ancestry.observation_ids == (o1.id,)
    assert ancestry.derived_value_ids == ()


# -- B. Multi-parent provenance ----------------------------------------------


def test_multi_parent_provenance():
    pool, (o1, o2) = _pool_with_observations(2)
    d1 = make_derived_value(derived_from=[o1.id, o2.id], method="mean", content={"v": 1}, confidence=1.0, derived_at="t")
    pool.put_derived_value(d1)

    ancestry = ancestry_of(pool, d1.id)
    assert ancestry.observation_ids == tuple(sorted([o1.id, o2.id]))
    assert ancestry.derived_value_ids == ()


# -- C. Multi-level provenance -----------------------------------------------


def test_multi_level_provenance():
    pool, (o1, o2) = _pool_with_observations(2)
    d1 = make_derived_value(derived_from=[o1.id, o2.id], method="mean", content={"v": 1}, confidence=1.0, derived_at="t")
    pool.put_derived_value(d1)
    d2 = make_derived_value(derived_from=[d1.id], method="refine", content={"v": 2}, confidence=0.9, derived_at="t")
    pool.put_derived_value(d2)

    ancestry = ancestry_of(pool, d2.id)
    assert ancestry.observation_ids == tuple(sorted([o1.id, o2.id]))
    assert ancestry.derived_value_ids == (d1.id,)


# -- D. Shared ancestry / deduplication --------------------------------------


def test_shared_ancestry_is_deduplicated():
    """D1 = mean(O1, O2); D2 = accept_as_is(O2); D3 = combine(D1, D2).
    O2 is reachable via both D1 and D2 -- must appear exactly once."""
    pool, (o1, o2) = _pool_with_observations(2)
    d1 = make_derived_value(derived_from=[o1.id, o2.id], method="mean", content={"v": 1}, confidence=1.0, derived_at="t")
    pool.put_derived_value(d1)
    d2 = make_derived_value(derived_from=[o2.id], method="accept_as_is", content={"v": 2}, confidence=1.0, derived_at="t")
    pool.put_derived_value(d2)
    d3 = make_derived_value(derived_from=[d1.id, d2.id], method="combine", content={"v": 3}, confidence=0.9, derived_at="t")
    pool.put_derived_value(d3)

    ancestry = ancestry_of(pool, d3.id)
    assert ancestry.observation_ids == tuple(sorted([o1.id, o2.id]))
    assert ancestry.observation_ids.count(o2.id) == 1
    assert ancestry.derived_value_ids == tuple(sorted([d1.id, d2.id]))


# -- E. Root exclusion --------------------------------------------------------


def test_root_derived_value_never_appears_in_its_own_derived_value_ids():
    pool, (o1, o2) = _pool_with_observations(2)
    d1 = make_derived_value(derived_from=[o1.id, o2.id], method="mean", content={"v": 1}, confidence=1.0, derived_at="t")
    pool.put_derived_value(d1)
    d2 = make_derived_value(derived_from=[d1.id], method="refine", content={"v": 2}, confidence=0.9, derived_at="t")
    pool.put_derived_value(d2)

    ancestry = ancestry_of(pool, d2.id)
    assert d2.id not in ancestry.derived_value_ids
    assert d1.id in ancestry.derived_value_ids


# -- F. Unknown root ----------------------------------------------------------


def test_unknown_root_raises_key_error():
    pool, _ = _pool_with_observations(1)
    with pytest.raises(KeyError):
        ancestry_of(pool, "ghost-derived-value")


def test_dangling_derived_from_reference_raises_key_error():
    """A DerivedValue placed into the pool directly (bypassing admission,
    exactly like this file's other fixtures) whose derived_from names an
    id nothing in the pool knows about -- ancestry_of must not silently
    skip it."""
    pool, _ = _pool_with_observations(1)
    d1 = make_derived_value(derived_from=["ghost-observation"], method="mean", content={"v": 1}, confidence=1.0, derived_at="t")
    pool.put_derived_value(d1)

    with pytest.raises(KeyError):
        ancestry_of(pool, d1.id)


# -- G. Pool immutability -----------------------------------------------------


def test_ancestry_of_never_mutates_pool():
    pool, (o1, o2) = _pool_with_observations(2)
    d1 = make_derived_value(derived_from=[o1.id, o2.id], method="mean", content={"v": 1}, confidence=1.0, derived_at="t")
    pool.put_derived_value(d1)
    d2 = make_derived_value(derived_from=[d1.id], method="refine", content={"v": 2}, confidence=0.9, derived_at="t")
    pool.put_derived_value(d2)

    fingerprint_before = pool.fingerprint()
    history_before = pool.fingerprint_history()
    derived_values_before = {dv.id for dv in pool.all_derived_values()}

    ancestry_of(pool, d2.id)

    assert pool.fingerprint() == fingerprint_before
    assert pool.fingerprint_history() == history_before
    assert {dv.id for dv in pool.all_derived_values()} == derived_values_before


# -- H. Deterministic ordering -------------------------------------------------


def test_ancestry_independent_of_derived_from_construction_order():
    pool, (o1, o2) = _pool_with_observations(2)
    d1 = make_derived_value(derived_from=[o1.id, o2.id], method="mean", content={"v": 1}, confidence=1.0, derived_at="t")
    pool.put_derived_value(d1)
    d2 = make_derived_value(derived_from=[o2.id], method="accept_as_is", content={"v": 2}, confidence=1.0, derived_at="t")
    pool.put_derived_value(d2)

    d3_a = make_derived_value(derived_from=[d1.id, d2.id], method="combine", content={"v": 3}, confidence=0.9, derived_at="t")
    d3_b = make_derived_value(derived_from=[d2.id, d1.id], method="combine", content={"v": 3}, confidence=0.9, derived_at="t")
    assert d3_a.id == d3_b.id  # make_derived_value already normalizes order

    pool.put_derived_value(d3_a)
    ancestry_a = ancestry_of(pool, d3_a.id)
    ancestry_b = ancestry_of(pool, d3_b.id)
    assert ancestry_a == ancestry_b


def test_ancestry_result_is_a_plain_frozen_dataclass_not_a_pool_object():
    pool, (o1,) = _pool_with_observations(1)
    d1 = make_derived_value(derived_from=[o1.id], method="accept_as_is", content={"v": 1}, confidence=1.0, derived_at="t")
    pool.put_derived_value(d1)

    ancestry = ancestry_of(pool, d1.id)
    assert isinstance(ancestry, ProvenanceAncestry)
    with pytest.raises(AttributeError):
        ancestry.root_derived_value_id = "mutated"  # type: ignore[misc]


# -- I. PYTHONHASHSEED determinism --------------------------------------------


def test_ancestry_deterministic_across_hash_seeds():
    import subprocess
    import sys

    script = (
        "from evidence.pool import EvidencePool\n"
        "from evidence.provenance import ancestry_of\n"
        "from evidence.types import make_derived_value, make_document, make_observation, make_record, make_source\n"
        "pool = EvidencePool()\n"
        "s = make_source(kind='paper', name='X')\n"
        "pool.put_source(s)\n"
        "d = make_document(source_id=s.id, raw_content='body', retrieval_method='m', retrieved_at='t')\n"
        "pool.put_document(d)\n"
        "r = make_record(document_id=d.id, locator='p1', raw_content='body')\n"
        "pool.put_record(r)\n"
        "o1 = make_observation(record_ids=(r.id,), extraction_method='regex:kv_v1', content={'value': 1000}, confidence=1.0, extracted_at='t')\n"
        "o2 = make_observation(record_ids=(r.id,), extraction_method='regex:kv_v1', content={'value': 1001}, confidence=1.0, extracted_at='t')\n"
        "pool.put_observation(o1)\n"
        "pool.put_observation(o2)\n"
        "d1 = make_derived_value(derived_from=[o2.id, o1.id], method='mean', content={'v': 1}, confidence=1.0, derived_at='t')\n"
        "pool.put_derived_value(d1)\n"
        "d2 = make_derived_value(derived_from=[o2.id], method='accept_as_is', content={'v': 2}, confidence=1.0, derived_at='t')\n"
        "pool.put_derived_value(d2)\n"
        "d3 = make_derived_value(derived_from=[d2.id, d1.id], method='combine', content={'v': 3}, confidence=0.9, derived_at='t')\n"
        "pool.put_derived_value(d3)\n"
        "ancestry = ancestry_of(pool, d3.id)\n"
        "print(ancestry.root_derived_value_id, ancestry.observation_ids, ancestry.derived_value_ids)\n"
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
    assert len(outputs) == 1, f"ancestry_of differed across PYTHONHASHSEED values: {outputs}"


# -- J. Boundary --------------------------------------------------------------


def test_provenance_module_has_no_forbidden_dependencies():
    """evidence/provenance.py must not import retrieval/, core/, runtime/,
    or scout/ -- same AST-based convention as
    `tests/test_derived_value_boundaries.py`/`tests/test_scout_boundaries.py`,
    applied directly to this one new file rather than re-globbing a whole
    package directory."""
    path = REPO_ROOT / "evidence" / "provenance.py"
    tree = ast.parse(path.read_text())
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)

    forbidden_prefixes = ("retrieval", "core", "runtime", "scout")
    for module in modules:
        assert not module.startswith(forbidden_prefixes), (
            f"evidence/provenance.py imports {module!r} -- provenance must stay evidence-layer-only"
        )
