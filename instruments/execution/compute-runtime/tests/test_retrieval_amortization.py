"""Compute amortization: proves -- by an actual, measurable call count,
not a fabricated performance number -- that extraction runs once and
retrieval reuses its output across many different queries
(`docs/RETRIEVAL_ARCHITECTURE.md` §compute-amortization).
"""

from evidence.pool import EvidencePool
from retrieval.context import build_context_package
from retrieval.engine import DeterministicRetrievalEngine
from retrieval.query import make_retrieval_query
from scout.adapters import FixtureSourceAdapter
from scout.extraction import DeterministicExtractor
from scout.fixtures import ALL_FIXTURE_DOCUMENTS
from scout.pipeline import run_scout


class _CountingExtractor(DeterministicExtractor):
    def __init__(self):
        self.call_count = 0

    def extract(self, record):
        self.call_count += 1
        return super().extract(record)


def test_extraction_runs_once_regardless_of_later_retrieval_count():
    pool = EvidencePool()
    extractor = _CountingExtractor()
    run_scout(FixtureSourceAdapter(ALL_FIXTURE_DOCUMENTS), extractor, pool)
    extraction_calls_after_scout = extractor.call_count
    assert extraction_calls_after_scout == len(ALL_FIXTURE_DOCUMENTS)  # one call per Record

    engine = DeterministicRetrievalEngine()
    queries = [
        make_retrieval_query(entity_natural_keys=("FEP",), traversal_depth=0),
        make_retrieval_query(entity_natural_keys=("FEP",), traversal_depth=1),
        make_retrieval_query(entity_natural_keys=("FEP",), traversal_depth=2),
        make_retrieval_query(entity_natural_keys=("extrusion",), traversal_depth=1),
        make_retrieval_query(entity_natural_keys=("rheo-sim",), traversal_depth=1),
    ]
    results = [engine.retrieve(pool, q) for q in queries]
    build_context_package(tuple(results))

    # Five independent queries, five results, one composed context --
    # none of it re-invoked extraction.
    assert extractor.call_count == extraction_calls_after_scout


def test_context_construction_touches_no_source_content_extraction_already_normalized():
    """The ContextPackage/RetrievalResult layer only ever reads ids and
    already-stored Observation.content -- it never re-reads
    Document.raw_content or re-runs any extraction logic. Verified by
    confirming the composed context's observation ids are exactly the
    ones the (one-time) extraction produced, with no new Observation
    objects created."""
    pool = EvidencePool()
    extractor = _CountingExtractor()
    run_scout(FixtureSourceAdapter(ALL_FIXTURE_DOCUMENTS), extractor, pool)
    observation_ids_after_scout = {o.id for o in pool.all_observations()}

    engine = DeterministicRetrievalEngine()
    result = engine.retrieve(
        pool, make_retrieval_query(entity_natural_keys=("FEP",), traversal_depth=2)
    )
    ctx = build_context_package((result,))

    assert set(ctx.observation_ids) <= observation_ids_after_scout
    assert {o.id for o in pool.all_observations()} == observation_ids_after_scout  # no new observations
