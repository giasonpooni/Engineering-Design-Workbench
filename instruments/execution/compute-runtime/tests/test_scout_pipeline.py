"""End-to-end SCOUT pipeline tests: source acquisition -> extraction ->
Trust Graph attachment -> metrics -> FEP signal, over the fixture
sources. Covers this phase's required scenarios: entity attachment,
relation attachment, temporal updates / graph state changes, uncertain
observations, and duplicate-observation handling."""

from evidence.pool import EvidencePool
from evidence.trust_graph import build_trust_graph
from scout.adapters import FixtureSourceAdapter
from scout.extraction import DeterministicExtractor
from scout.fixtures import ALL_FIXTURE_DOCUMENTS, GITHUB_REPO_DOCUMENT, PAPER_DOCUMENT
from scout.interface import ExtractedEntity, ExtractedRelation, ExtractionCandidate
from scout.pipeline import run_scout


def test_run_scout_over_fixtures_produces_findings_and_no_failures():
    pool = EvidencePool()
    findings, failures = run_scout(FixtureSourceAdapter(ALL_FIXTURE_DOCUMENTS), DeterministicExtractor(), pool)
    assert len(findings) == 2
    assert failures == ()


def test_entity_attachment_creates_referents_in_pool():
    pool = EvidencePool()
    findings, _ = run_scout(FixtureSourceAdapter((PAPER_DOCUMENT,)), DeterministicExtractor(), pool)
    finding = findings[0]
    labels = {r.natural_key for r in finding.referents}
    assert labels == {"FEP", "extrusion"}
    for referent in finding.referents:
        assert pool.has_referent(referent.id)


def test_relation_attachment_creates_claimed_relationship_in_pool():
    pool = EvidencePool()
    findings, _ = run_scout(FixtureSourceAdapter((PAPER_DOCUMENT,)), DeterministicExtractor(), pool)
    finding = findings[0]
    assert len(finding.relationships) == 1
    rel = finding.relationships[0]
    assert rel.type == "used_in"
    assert rel in pool.all_claimed_relationships()


def test_graph_state_changes_between_documents():
    """Processing the second (github) document, which references the
    already-known Referent "FEP", must show lower novelty and nonzero
    redundancy for that shared node -- proof the Trust Graph actually
    accumulates across findings rather than resetting per document."""
    pool = EvidencePool()
    findings, _ = run_scout(FixtureSourceAdapter(ALL_FIXTURE_DOCUMENTS), DeterministicExtractor(), pool)
    paper_finding, repo_finding = findings
    assert paper_finding.novelty == 1.0  # first document: everything is new
    assert repo_finding.novelty < 1.0  # second document: FEP was already known
    fep_id = next(r.id for r in repo_finding.referents if r.natural_key == "FEP")
    assert redundancy_of(pool, fep_id) >= 1


def redundancy_of(pool, referent_id):
    from evidence.metrics import redundancy

    return redundancy(pool, referent_id)


def test_temporal_update_second_observation_of_same_referent_does_not_overwrite_first():
    """A later, different-content observation about a Referent already
    seen does not replace the earlier one -- both remain queryable
    (§E's conflict-coexistence model, exercised through the pipeline)."""
    pool = EvidencePool()
    findings, _ = run_scout(FixtureSourceAdapter(ALL_FIXTURE_DOCUMENTS), DeterministicExtractor(), pool)
    fep_id = next(r.id for f in findings for r in f.referents if r.natural_key == "FEP")
    observations = pool.observations_about(fep_id)
    assert len(observations) == 2
    assert len({o.id for o in observations}) == 2


def test_pipeline_is_deterministic_across_independent_runs():
    pool1, pool2 = EvidencePool(), EvidencePool()
    findings1, failures1 = run_scout(FixtureSourceAdapter(ALL_FIXTURE_DOCUMENTS), DeterministicExtractor(), pool1)
    findings2, failures2 = run_scout(FixtureSourceAdapter(ALL_FIXTURE_DOCUMENTS), DeterministicExtractor(), pool2)
    assert [f.observation.id for f in findings1] == [f.observation.id for f in findings2]
    assert failures1 == failures2 == ()


def test_running_scout_twice_over_the_same_source_is_idempotent():
    """Re-scouting an unchanged document must not duplicate pool state --
    content-addressed identity makes every put a no-op the second time."""
    pool = EvidencePool()
    run_scout(FixtureSourceAdapter((PAPER_DOCUMENT,)), DeterministicExtractor(), pool)
    size_after_first_run = len(pool)
    run_scout(FixtureSourceAdapter((PAPER_DOCUMENT,)), DeterministicExtractor(), pool)
    assert len(pool) == size_after_first_run


def test_uncertain_observation_carries_explicit_uncertainty_not_fabricated_confidence():
    """A candidate with confidence < 1.0 must produce a Observation whose
    stored confidence -- and downstream FEPSignal.uncertainty -- reflect
    that, not silently round up to certainty."""

    class LowConfidenceExtractor:
        def extract(self, record):
            return (
                ExtractionCandidate(
                    content={"claim": "tentative"},
                    entities=(ExtractedEntity(label="X", kind="concept"),),
                    relations=(),
                    extraction_method="model:mistral-v1",
                    confidence=0.3,
                ),
            )

    pool = EvidencePool()
    findings, failures = run_scout(FixtureSourceAdapter((PAPER_DOCUMENT,)), LowConfidenceExtractor(), pool)
    assert failures == ()
    finding = findings[0]
    assert finding.observation.confidence == 0.3
    assert finding.fep_signal.uncertainty == 0.7


def test_model_sourced_candidate_without_confidence_is_rejected_not_defaulted():
    """docs/PHASE_14_DATA_POOL_ARCHITECTURE.md §K's rule, exercised
    end-to-end: a "model:" extraction_method with confidence=None must
    be rejected by the pipeline, never silently treated as confidence=1.0."""

    class BrokenModelExtractor:
        def extract(self, record):
            return (
                ExtractionCandidate(
                    content={"claim": "unattributed"},
                    entities=(),
                    relations=(),
                    extraction_method="model:mistral-v1",
                    confidence=None,
                ),
            )

    pool = EvidencePool()
    findings, failures = run_scout(FixtureSourceAdapter((PAPER_DOCUMENT,)), BrokenModelExtractor(), pool)
    assert findings == ()
    assert len(failures) == 1
    assert failures[0].stage == "extraction"
    assert failures[0].errors[0].code == "MISSING_MODEL_CONFIDENCE"


def test_relation_referencing_unextracted_label_is_rejected_not_silently_dropped():
    class BadRelationExtractor:
        def extract(self, record):
            return (
                ExtractionCandidate(
                    content={"claim": "x"},
                    entities=(ExtractedEntity(label="A", kind="concept"),),
                    relations=(ExtractedRelation(from_label="A", type="relates_to", to_label="B"),),
                    extraction_method="regex:kv_v1",
                    confidence=1.0,
                ),
            )

    pool = EvidencePool()
    findings, failures = run_scout(FixtureSourceAdapter((PAPER_DOCUMENT,)), BadRelationExtractor(), pool)
    assert len(findings) == 1
    assert findings[0].relationships == ()
    assert len(failures) == 1
    assert failures[0].stage == "relationship"
    assert failures[0].errors[0].code == "UNKNOWN_LABEL"
