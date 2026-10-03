"""Phase 50: materials.information -- small focused test set over a
single compact fixture (build-more-test-less development mode). A tiny
test-only model class exercises the InformationValueModel Protocol --
it is deliberately NOT a real scientific model, just a stub proving the
seam actually plugs in.
"""

from evidence.admission import (
    admit_claimed_relationship, admit_document, admit_observation, admit_record, admit_referent,
)
from evidence.pool import EvidencePool
from evidence.types import (
    make_claimed_relationship, make_document, make_observation, make_record, make_referent, make_source,
)
from materials.candidates import generate_candidates
from materials.decision import make_criterion
from materials.information import (
    ESTIMATED, NOT_DETERMINABLE, NullInformationValueModel,
    estimate_information_value, estimate_information_values,
)
from materials.iteration import reevaluate_program
from materials.program import make_material_program_query
from retrieval.engine import DeterministicRetrievalEngine

ENGINE = DeterministicRetrievalEngine()
TENSILE_CRITERION = make_criterion("tensile_strength", ">=", 80)
HARDNESS_CRITERION = make_criterion("hardness", ">=", 50)  # never measured


class _StubModel:
    """Test-only stand-in for a real information-value model. Returns a
    fixed number for conflicts, None (NOT_DETERMINABLE) for everything
    else -- not a scientific claim, just enough behavior to prove the
    interface is exercised correctly in both directions."""

    name = "stub:fixed_for_conflicts"

    def estimate(self, information_value):
        if information_value.value_kind == "TESTS_CONFLICT":
            return 0.75, "stub model: fixed constant for conflict-testing candidates"
        return None, None


def _setup():
    pool = EvidencePool()
    source = make_source(kind="lab_notebook", name="QC")
    pool.put_source(source)
    doc = make_document(source_id=source.id, raw_content="panel", retrieval_method="manual_entry", retrieved_at="2026-08-23T00:00:00Z")
    admit_document(pool, doc)
    pool.put_document(doc)
    process = make_referent(natural_key="process-std-190c", kind="process")
    admit_referent(pool, process)
    pool.put_referent(process)
    f1 = make_referent(natural_key="formulation-f1", kind="formulation")
    admit_referent(pool, f1)
    pool.put_referent(f1)

    for locator, value in (("ts-a", 78), ("ts-b", 84)):
        rec = make_record(document_id=doc.id, locator=locator, raw_content=locator)
        admit_record(pool, rec)
        pool.put_record(rec)
        obs = make_observation(
            record_ids=(rec.id,), extraction_method="human_transcription",
            content={"property": "tensile_strength", "value": value, "unit": "MPa"},
            confidence=1.0, extracted_at="2026-08-23T00:00:00Z",
        )
        admit_observation(pool, obs)
        pool.put_observation(obs)
        rel = make_claimed_relationship(from_referent_id=f1.id, to_referent_id=process.id, type="tested_during", observation_id=obs.id, confidence=1.0)
        admit_claimed_relationship(pool, rel)
        pool.put_claimed_relationship(rel)

    query = make_material_program_query(["formulation-f1"], "process-std-190c", ("tensile_strength", "hardness"))
    iteration = reevaluate_program(pool, ENGINE, query, (TENSILE_CRITERION, HARDNESS_CRITERION))
    candidates = generate_candidates(iteration.specification)
    tensile_conflict = next(c for c in candidates.candidates if c.action_class == "measurement:repeat")
    return pool, iteration, candidates, tensile_conflict


# -- 1. estimate produced by a real (stub) model plugging into the interface -------------------------


def test_1_model_produces_estimate():
    pool, iteration, candidates, conflict_candidate = _setup()
    estimate = estimate_information_value(conflict_candidate, iteration, _StubModel())
    assert estimate.estimate == 0.75
    assert estimate.estimate_status == ESTIMATED
    assert estimate.model_name == "stub:fixed_for_conflicts"
    assert "conflict" in estimate.basis


# -- 2. NOT_DETERMINABLE when the model returns None ---------------------------------------------------


def test_2_not_determinable_when_model_declines():
    pool, iteration, candidates, conflict_candidate = _setup()
    other = next(c for c in candidates.candidates if c.id != conflict_candidate.id)
    estimate = estimate_information_value(other, iteration, _StubModel())
    assert estimate.estimate is None
    assert estimate.estimate_status == NOT_DETERMINABLE
    assert estimate.basis is None


# -- 3. structural facts preserved unmodified, embedded whole -------------------------------------------


def test_3_structural_facts_embedded_unmodified():
    pool, iteration, candidates, conflict_candidate = _setup()
    estimate = estimate_information_value(conflict_candidate, iteration, _StubModel())
    assert estimate.information_value.value_kind == "TESTS_CONFLICT"
    assert estimate.information_value.expected_information_gain == NOT_DETERMINABLE  # Phase 46 fact, untouched
    assert estimate.candidate_id == conflict_candidate.id == estimate.information_value.candidate_id


# -- 4. provenance preserved through to the targeted requirement -----------------------------------------


def test_4_provenance_preserved():
    pool, iteration, candidates, conflict_candidate = _setup()
    estimate = estimate_information_value(conflict_candidate, iteration, _StubModel())
    requirement = estimate.information_value.evaluation.targeted_requirements[0]
    assert requirement.formulation.natural_key == "formulation-f1"


# -- 5. the reference NullInformationValueModel always yields NOT_DETERMINABLE -----------------------------


def test_5_null_model_always_not_determinable():
    pool, iteration, candidates, conflict_candidate = _setup()
    result_set = estimate_information_values(candidates, iteration, NullInformationValueModel())
    assert all(e.estimate is None and e.estimate_status == NOT_DETERMINABLE for e in result_set.estimates)
    assert result_set.model_name == "null:not_determinable"


# -- 6. deterministic multi-candidate ordering ------------------------------------------------------------------


def test_6_deterministic_multi_candidate_ordering():
    pool, iteration, candidates, conflict_candidate = _setup()
    a = estimate_information_values(candidates, iteration, _StubModel())
    b = estimate_information_values(candidates, iteration, _StubModel())
    ids_a = [e.candidate_id for e in a.estimates]
    ids_b = [e.candidate_id for e in b.estimates]
    assert ids_a == ids_b == sorted(ids_a) == [c.id for c in candidates.candidates]
    assert [e.estimate for e in a.estimates] == [e.estimate for e in b.estimates]


# -- 7. no mutation --------------------------------------------------------------------------------------------


def test_7_no_mutation():
    pool, iteration, candidates, conflict_candidate = _setup()
    before_iteration = repr(iteration)
    before_candidates = repr(candidates)
    fingerprint_before = pool.fingerprint()
    estimate_information_values(candidates, iteration, _StubModel())
    assert repr(iteration) == before_iteration
    assert repr(candidates) == before_candidates
    assert pool.fingerprint() == fingerprint_before
