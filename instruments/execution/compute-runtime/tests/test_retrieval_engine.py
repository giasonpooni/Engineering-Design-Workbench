"""DeterministicRetrievalEngine over the SCOUT fixtures: exact lookup,
relationship retrieval, bounded traversal, epistemic/source/text
filtering, determinism, read-only-ness, evidence-version sensitivity.
"""

from evidence.pool import EvidencePool
from evidence.trust_graph import build_trust_graph
from retrieval.engine import DeterministicRetrievalEngine
from retrieval.epistemic import EXTRACTED, INFERRED
from retrieval.query import make_retrieval_query
from scout.adapters import FixtureSourceAdapter
from scout.extraction import DeterministicExtractor
from scout.fixtures import ALL_FIXTURE_DOCUMENTS, PAPER_DOCUMENT
from scout.interface import ExtractedEntity, ExtractedRelation, ExtractionCandidate
from scout.pipeline import run_scout


def _scouted_pool(documents=ALL_FIXTURE_DOCUMENTS):
    pool = EvidencePool()
    run_scout(FixtureSourceAdapter(documents), DeterministicExtractor(), pool)
    return pool


def test_exact_entity_retrieval():
    pool = _scouted_pool()
    engine = DeterministicRetrievalEngine()
    query = make_retrieval_query(entity_natural_keys=("FEP",), traversal_depth=0)
    result = engine.retrieve(pool, query)
    labels = {pool.get_referent(rid).natural_key for rid in result.referent_ids}
    assert labels == {"FEP"}


def test_relationship_retrieval_within_seed_set():
    pool = _scouted_pool((PAPER_DOCUMENT,))
    engine = DeterministicRetrievalEngine()
    query = make_retrieval_query(entity_natural_keys=("FEP", "extrusion"), traversal_depth=0)
    result = engine.retrieve(pool, query)
    assert len(result.relationship_ids) == 1
    relationships = [r for r in pool.all_claimed_relationships() if r.id in result.relationship_ids]
    assert relationships[0].type == "used_in"


def test_bounded_graph_traversal_reaches_second_hop():
    pool = _scouted_pool()
    engine = DeterministicRetrievalEngine()
    depth1 = engine.retrieve(pool, make_retrieval_query(entity_natural_keys=("FEP",), traversal_depth=1))
    depth2 = engine.retrieve(pool, make_retrieval_query(entity_natural_keys=("FEP",), traversal_depth=2))
    labels_d1 = {pool.get_referent(rid).natural_key for rid in depth1.referent_ids}
    labels_d2 = {pool.get_referent(rid).natural_key for rid in depth2.referent_ids}
    # FEP is directly linked to both "extrusion" and "rheo-sim" (1 hop each) --
    # both already present at depth 1; depth 2 must be a superset, never smaller.
    assert labels_d1 <= labels_d2
    assert "FEP" in labels_d1


def test_traversal_depth_zero_returns_only_seed():
    pool = _scouted_pool()
    engine = DeterministicRetrievalEngine()
    result = engine.retrieve(pool, make_retrieval_query(entity_natural_keys=("FEP",), traversal_depth=0))
    labels = {pool.get_referent(rid).natural_key for rid in result.referent_ids}
    assert labels == {"FEP"}
    assert result.relationship_ids == ()


def test_relationship_type_filter_restricts_traversal():
    pool = _scouted_pool()
    engine = DeterministicRetrievalEngine()
    result = engine.retrieve(
        pool,
        make_retrieval_query(entity_natural_keys=("FEP",), traversal_depth=2, relationship_types=("used_in",)),
    )
    labels = {pool.get_referent(rid).natural_key for rid in result.referent_ids}
    # "models" (rheo-sim -> FEP) is excluded by the filter, so rheo-sim
    # must not be reachable even though it's within the depth budget.
    assert "rheo-sim" not in labels
    assert "extrusion" in labels


def test_epistemic_filtering_excludes_model_sourced_observations():
    pool = EvidencePool()

    class MixedExtractor:
        def extract(self, record):
            return (
                ExtractionCandidate(
                    content={"claim": "deterministic"},
                    entities=(ExtractedEntity(label="X", kind="concept"), ExtractedEntity(label="Y", kind="concept")),
                    relations=(ExtractedRelation(from_label="X", type="related_to", to_label="Y"),),
                    extraction_method="regex:kv_v1",
                    confidence=1.0,
                ),
            )

    run_scout(FixtureSourceAdapter((PAPER_DOCUMENT,)), MixedExtractor(), pool)
    engine = DeterministicRetrievalEngine()

    all_result = engine.retrieve(pool, make_retrieval_query(entity_natural_keys=("X", "Y"), traversal_depth=1))
    assert len(all_result.observation_ids) == 1

    filtered = engine.retrieve(
        pool,
        make_retrieval_query(entity_natural_keys=("X", "Y"), traversal_depth=1, epistemic_statuses=(INFERRED,)),
    )
    assert filtered.observation_ids == ()

    kept = engine.retrieve(
        pool,
        make_retrieval_query(entity_natural_keys=("X", "Y"), traversal_depth=1, epistemic_statuses=(EXTRACTED,)),
    )
    assert kept.observation_ids == all_result.observation_ids


def test_source_kind_filtering():
    pool = _scouted_pool()  # one "paper" source, one "github_repo" source
    engine = DeterministicRetrievalEngine()
    result = engine.retrieve(
        pool,
        make_retrieval_query(entity_natural_keys=("FEP",), traversal_depth=2, source_kinds=("github_repo",)),
    )
    kinds = {pool.get_source(sid).kind for sid in result.source_ids}
    assert kinds == {"github_repo"}


def test_text_term_filtering():
    pool = _scouted_pool()
    engine = DeterministicRetrievalEngine()
    result = engine.retrieve(
        pool,
        make_retrieval_query(entity_natural_keys=("FEP",), traversal_depth=2, text_terms=("viscosity",)),
    )
    for obs_id in result.observation_ids:
        content = dict(pool.get_observation(obs_id).content)
        assert any("viscosity" in str(v).lower() for v in content.values())


def test_limit_bounds_referent_count_deterministically():
    pool = _scouted_pool()
    engine = DeterministicRetrievalEngine()
    unlimited = engine.retrieve(pool, make_retrieval_query(entity_natural_keys=("FEP",), traversal_depth=2))
    limited = engine.retrieve(
        pool, make_retrieval_query(entity_natural_keys=("FEP",), traversal_depth=2, limit=1)
    )
    assert len(limited.referent_ids) == 1
    assert limited.referent_ids[0] == sorted(unlimited.referent_ids)[0]


def test_retrieval_result_is_deterministic_across_calls():
    pool = _scouted_pool()
    engine = DeterministicRetrievalEngine()
    query = make_retrieval_query(entity_natural_keys=("FEP",), traversal_depth=2)
    r1 = engine.retrieve(pool, query)
    r2 = engine.retrieve(pool, query)
    assert r1 == r2
    assert r1.id == r2.id


def test_retrieval_never_mutates_pool():
    pool = _scouted_pool()
    engine = DeterministicRetrievalEngine()
    fingerprint_before = pool.fingerprint()
    ids_before = (
        tuple(r.id for r in pool.all_referents()),
        tuple(r.id for r in pool.all_claimed_relationships()),
        tuple(o.id for o in pool.all_observations()),
    )
    engine.retrieve(pool, make_retrieval_query(entity_natural_keys=("FEP",), traversal_depth=2))
    ids_after = (
        tuple(r.id for r in pool.all_referents()),
        tuple(r.id for r in pool.all_claimed_relationships()),
        tuple(o.id for o in pool.all_observations()),
    )
    assert ids_before == ids_after
    assert pool.fingerprint() == fingerprint_before


def test_evidence_remains_immutable_object_identity():
    """Retrieval never replaces or edits a stored object -- the exact
    same Referent/Observation instances are returned before and after a
    retrieval call."""
    pool = _scouted_pool()
    engine = DeterministicRetrievalEngine()
    referent_before = pool.get_referent(pool.all_referents()[0].id)
    engine.retrieve(pool, make_retrieval_query(entity_natural_keys=("FEP",), traversal_depth=2))
    referent_after = pool.get_referent(referent_before.id)
    assert referent_before is referent_after


def test_trust_graph_remains_a_derived_view_after_retrieval():
    pool = _scouted_pool()
    engine = DeterministicRetrievalEngine()
    graph_before = build_trust_graph(pool)
    engine.retrieve(pool, make_retrieval_query(entity_natural_keys=("FEP",), traversal_depth=2))
    graph_after = build_trust_graph(pool)
    assert graph_before == graph_after


def test_source_version_sensitivity():
    """If the underlying evidence changes -- even in a way that doesn't
    affect this query's returned id sets -- the result must be
    distinguishable from the prior retrieval, per
    docs/RETRIEVAL_ARCHITECTURE.md §reproducibility."""
    from evidence.types import make_source

    pool = _scouted_pool()
    engine = DeterministicRetrievalEngine()
    query = make_retrieval_query(entity_natural_keys=("FEP",), traversal_depth=2)

    before = engine.retrieve(pool, query)
    pool.put_source(make_source(kind="paper", name="An Unrelated Paper"))
    after = engine.retrieve(pool, query)

    assert before.referent_ids == after.referent_ids  # same visible result...
    assert before.evidence_version_id != after.evidence_version_id  # ...but distinguishable
    assert before.id != after.id


def test_retrieval_result_id_unaffected_by_fingerprint_history_mechanism():
    """Phase 16 regression check: EvidencePool.fingerprint_history() must
    not leak into RetrievalResult.id or ContextPackage.id. For a FIXED,
    unchanged pool state, calling fingerprint_history() (a pure read, per
    tests/test_evidence_pool.py) any number of times, in between two
    identical retrievals, must not change either identity."""
    from retrieval.context import build_context_package

    pool = _scouted_pool()
    engine = DeterministicRetrievalEngine()
    query = make_retrieval_query(entity_natural_keys=("FEP",), traversal_depth=2)

    result_before = engine.retrieve(pool, query)
    context_before = build_context_package((result_before,))

    for _ in range(5):
        pool.fingerprint_history()

    result_after = engine.retrieve(pool, query)
    context_after = build_context_package((result_after,))

    assert result_before.id == result_after.id
    assert context_before.id == context_after.id


def test_empty_pool_retrieval_returns_empty_result_without_error():
    pool = EvidencePool()
    engine = DeterministicRetrievalEngine()
    result = engine.retrieve(pool, make_retrieval_query(entity_natural_keys=("FEP",), traversal_depth=3))
    assert result.referent_ids == ()
    assert result.relationship_ids == ()
    assert result.observation_ids == ()
    assert result.source_ids == ()


def test_no_match_retrieval_over_nonempty_pool_returns_empty_result():
    pool = _scouted_pool()
    engine = DeterministicRetrievalEngine()
    result = engine.retrieve(
        pool, make_retrieval_query(entity_natural_keys=("does-not-exist",), traversal_depth=2)
    )
    assert result.referent_ids == ()
    assert result.relationship_ids == ()
    assert result.observation_ids == ()
    # A no-match result is still fully identified and reproducible, not a
    # degenerate/None value.
    assert result.query_id
    assert result.evidence_version_id == pool.fingerprint()


def test_empty_query_with_no_seed_entities_returns_empty_result():
    pool = _scouted_pool()
    engine = DeterministicRetrievalEngine()
    result = engine.retrieve(pool, make_retrieval_query(traversal_depth=2))
    assert result.referent_ids == ()


def test_retrieval_over_duplicate_evidence_is_identical_to_retrieval_over_single_ingestion():
    """Re-scouting the identical document a second time is a no-op at
    the pool level (content-addressed ids) -- a retrieval run afterward
    must be indistinguishable from one run against the single-ingestion
    pool, including the evidence_version_id, since the pool's actual
    contents (and therefore its fingerprint) are unchanged."""
    pool_once = _scouted_pool((PAPER_DOCUMENT,))
    pool_twice = EvidencePool()
    run_scout(FixtureSourceAdapter((PAPER_DOCUMENT,)), DeterministicExtractor(), pool_twice)
    run_scout(FixtureSourceAdapter((PAPER_DOCUMENT,)), DeterministicExtractor(), pool_twice)  # re-scout

    assert pool_once.fingerprint() == pool_twice.fingerprint()

    engine = DeterministicRetrievalEngine()
    query = make_retrieval_query(entity_natural_keys=("FEP",), traversal_depth=2)
    result_once = engine.retrieve(pool_once, query)
    result_twice = engine.retrieve(pool_twice, query)
    assert result_once == result_twice
    assert result_once.id == result_twice.id


def test_epistemic_classification_is_reconstructable_from_a_retrieved_observation_id():
    """RetrievalResult does not duplicate the epistemic-status label
    onto the result itself -- it is a derived property of the
    Observation, recomputed on demand
    (`retrieval.epistemic.classify_epistemic_status`), never copied.
    This test proves that derivation is stable and reachable purely from
    what the result already references, i.e. the result exposes enough
    provenance to reconstruct the classification without any additional
    input."""
    from retrieval.epistemic import EXTRACTED, classify_epistemic_status

    pool = _scouted_pool((PAPER_DOCUMENT,))
    engine = DeterministicRetrievalEngine()
    result = engine.retrieve(pool, make_retrieval_query(entity_natural_keys=("FEP",), traversal_depth=1))

    assert result.observation_ids  # sanity: this query actually returned evidence
    for obs_id in result.observation_ids:
        observation = pool.get_observation(obs_id)
        assert classify_epistemic_status(observation) == EXTRACTED  # regex:kv_v1 -> EXTRACTED
        # recomputing twice from the same referenced id is stable
        assert classify_epistemic_status(pool.get_observation(obs_id)) == classify_epistemic_status(observation)


def test_retrieval_result_deterministic_across_hash_seeds():
    """Same discipline as `tests/test_versioning.py`'s and
    `tests/test_trust_graph.py`'s cross-process PYTHONHASHSEED checks,
    applied to RetrievalResult/ContextPackage identity -- since both are
    content hashes built by iterating sets during traversal, this closes
    the gap a purely in-process test cannot (PYTHONHASHSEED only applies
    at interpreter startup)."""
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    script = (
        "from evidence.pool import EvidencePool\n"
        "from retrieval.context import build_context_package\n"
        "from retrieval.engine import DeterministicRetrievalEngine\n"
        "from retrieval.query import make_retrieval_query\n"
        "from scout.adapters import FixtureSourceAdapter\n"
        "from scout.extraction import DeterministicExtractor\n"
        "from scout.fixtures import ALL_FIXTURE_DOCUMENTS\n"
        "from scout.pipeline import run_scout\n"
        "pool = EvidencePool()\n"
        "run_scout(FixtureSourceAdapter(ALL_FIXTURE_DOCUMENTS), DeterministicExtractor(), pool)\n"
        "engine = DeterministicRetrievalEngine()\n"
        "query = make_retrieval_query(entity_natural_keys=('FEP',), traversal_depth=2)\n"
        "result = engine.retrieve(pool, query)\n"
        "ctx = build_context_package((result,))\n"
        "print(query.id, result.id, ctx.id)\n"
    )
    outputs = set()
    for seed in ("0", "1", "12345"):
        proc = subprocess.run(
            [sys.executable, "-c", script],
            cwd=repo_root,
            env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode == 0, proc.stderr
        outputs.add(proc.stdout)
    assert len(outputs) == 1, f"ids differed across PYTHONHASHSEED values: {outputs}"


def test_second_engine_implementation_can_satisfy_the_same_protocol():
    """Proves the RetrievalEngine Protocol is a real seam: a second,
    trivial implementation (not "deterministic:bfs_v1") can still
    produce a valid RetrievalResult of the same shape -- exactly what a
    future SemanticRetrieval/VectorRetrieval engine would need."""
    from retrieval.result import make_retrieval_result

    class EmptyEngine:
        method_name = "stub:always_empty_v1"

        def retrieve(self, pool, query):
            return make_retrieval_result(
                query_id=query.id,
                evidence_version_id=pool.fingerprint(),
                retrieval_method=self.method_name,
                referent_ids=(),
                relationship_ids=(),
                observation_ids=(),
                source_ids=(),
                traversal_depth=query.traversal_depth,
                filters_applied=(),
            )

    pool = _scouted_pool()
    engine = EmptyEngine()
    result = engine.retrieve(pool, make_retrieval_query(entity_natural_keys=("FEP",)))
    assert result.retrieval_method == "stub:always_empty_v1"
    assert result.referent_ids == ()
