"""ContextPackage: composition, deduplication, reproducibility,
provenance tracing, and the InquiryState seam."""

from evidence.pool import EvidencePool
from retrieval.context import build_context_package, observations, referents, relationships, sources
from retrieval.engine import DeterministicRetrievalEngine
from retrieval.query import make_retrieval_query
from retrieval.seam import open_inquiry_seam
from scout.adapters import FixtureSourceAdapter
from scout.extraction import DeterministicExtractor
from scout.fixtures import ALL_FIXTURE_DOCUMENTS
from scout.pipeline import run_scout


def _scouted_pool():
    pool = EvidencePool()
    run_scout(FixtureSourceAdapter(ALL_FIXTURE_DOCUMENTS), DeterministicExtractor(), pool)
    return pool


def test_context_package_reproducible_from_same_result():
    pool = _scouted_pool()
    engine = DeterministicRetrievalEngine()
    query = make_retrieval_query(entity_natural_keys=("FEP",), traversal_depth=2)
    result = engine.retrieve(pool, query)

    ctx1 = build_context_package((result,))
    ctx2 = build_context_package((result,))
    assert ctx1 == ctx2
    assert ctx1.id == ctx2.id


def test_context_package_reproducible_end_to_end_same_evidence_and_query():
    pool = _scouted_pool()
    engine = DeterministicRetrievalEngine()
    query = make_retrieval_query(entity_natural_keys=("FEP",), traversal_depth=2)

    ctx1 = build_context_package((engine.retrieve(pool, query),))
    ctx2 = build_context_package((engine.retrieve(pool, query),))
    assert ctx1.id == ctx2.id


def test_duplicate_free_composition_across_overlapping_retrievals():
    """Composing two retrievals that share a Referent (FEP appears in
    both) must not duplicate it in the resulting ContextPackage."""
    pool = _scouted_pool()
    engine = DeterministicRetrievalEngine()
    result_a = engine.retrieve(pool, make_retrieval_query(entity_natural_keys=("FEP",), traversal_depth=1))
    result_b = engine.retrieve(pool, make_retrieval_query(entity_natural_keys=("rheo-sim",), traversal_depth=1))

    ctx = build_context_package((result_a, result_b))
    assert len(ctx.referent_ids) == len(set(ctx.referent_ids))
    fep_id = next(r.id for r in referents(pool, ctx) if r.natural_key == "FEP")
    # FEP is referenced by both retrievals but appears exactly once.
    assert ctx.referent_ids.count(fep_id) == 1


def test_composition_is_order_independent():
    pool = _scouted_pool()
    engine = DeterministicRetrievalEngine()
    result_a = engine.retrieve(pool, make_retrieval_query(entity_natural_keys=("FEP",), traversal_depth=1))
    result_b = engine.retrieve(pool, make_retrieval_query(entity_natural_keys=("rheo-sim",), traversal_depth=1))

    ctx_ab = build_context_package((result_a, result_b))
    ctx_ba = build_context_package((result_b, result_a))
    assert ctx_ab.id == ctx_ba.id


def test_composition_across_different_evidence_versions_is_recorded_not_hidden():
    pool = _scouted_pool()
    engine = DeterministicRetrievalEngine()
    query = make_retrieval_query(entity_natural_keys=("FEP",), traversal_depth=1)

    result_before = engine.retrieve(pool, query)

    from evidence.types import make_source

    pool.put_source(make_source(kind="paper", name="Another Unrelated Paper"))
    result_after = engine.retrieve(pool, query)

    ctx = build_context_package((result_before, result_after))
    assert len(ctx.evidence_version_ids) == 2


def test_provenance_trace_from_context_to_source():
    """ContextPackage -> Referent -> ClaimedRelationship -> Observation
    -> Source/Document/Record, per docs/RETRIEVAL_ARCHITECTURE.md §8."""
    pool = _scouted_pool()
    engine = DeterministicRetrievalEngine()
    result = engine.retrieve(pool, make_retrieval_query(entity_natural_keys=("FEP",), traversal_depth=2))
    ctx = build_context_package((result,))

    fep = next(r for r in referents(pool, ctx) if r.natural_key == "FEP")
    rel = next(r for r in relationships(pool, ctx) if fep.id in (r.from_referent_id, r.to_referent_id))
    obs = next(o for o in observations(pool, ctx) if o.id == rel.observation_id)
    record = pool.get_record(obs.record_ids[0])
    document = pool.get_document(record.document_id)
    source = pool.get_source(document.source_id)

    assert source.id in ctx.source_ids
    assert document.source_id == source.id
    assert record.document_id == document.id
    assert obs.record_ids[0] == record.id
    # the context's own `sources()` dereference helper must agree with
    # the manual pool.get_source(...) trace above -- same object, same id
    assert source in sources(pool, ctx)


def test_context_package_holds_references_not_copies():
    """Dereferencing through the pool returns the exact same stored
    object instances -- ContextPackage never captured a snapshot copy."""
    pool = _scouted_pool()
    engine = DeterministicRetrievalEngine()
    result = engine.retrieve(pool, make_retrieval_query(entity_natural_keys=("FEP",), traversal_depth=1))
    ctx = build_context_package((result,))

    fep_via_context = next(r for r in referents(pool, ctx) if r.natural_key == "FEP")
    fep_via_pool = pool.get_referent(fep_via_context.id)
    assert fep_via_context is fep_via_pool


def test_build_context_package_requires_at_least_one_result():
    import pytest

    with pytest.raises(ValueError):
        build_context_package(())


def test_same_context_supports_multiple_independent_downstream_inquiries():
    pool = _scouted_pool()
    engine = DeterministicRetrievalEngine()
    ctx = build_context_package(
        (engine.retrieve(pool, make_retrieval_query(entity_natural_keys=("FEP",), traversal_depth=1)),)
    )

    seam1 = open_inquiry_seam(ctx, opened_at="2026-01-01T00:00:00Z")
    seam2 = open_inquiry_seam(ctx, opened_at="2026-01-02T00:00:00Z")

    assert seam1.context_id == seam2.context_id == ctx.id
    assert seam1 != seam2  # independent openings, same underlying context
