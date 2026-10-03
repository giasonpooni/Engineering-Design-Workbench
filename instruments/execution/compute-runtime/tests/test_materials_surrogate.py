"""Phase 51: materials.surrogate -- small focused test set over a single
compact fixture (build-more-test-less development mode). Verifies the
mathematical cases, deterministic behavior, provenance preservation, and
invalid-input handling.
"""

import math

from evidence.admission import (
    admit_claimed_relationship, admit_document, admit_observation, admit_record, admit_referent,
)
from evidence.pool import EvidencePool
from evidence.types import (
    make_claimed_relationship, make_document, make_observation, make_record, make_referent, make_source,
)
from materials.candidates import generate_candidates
from materials.decision import make_criterion
from materials.information import ESTIMATED, NOT_DETERMINABLE, estimate_information_value, estimate_information_values
from materials.iteration import reevaluate_program
from materials.program import make_material_program_query
from materials.surrogate import SurrogateInformationValueModel, SurrogateState
from retrieval.engine import DeterministicRetrievalEngine

ENGINE = DeterministicRetrievalEngine()
TENSILE_CRITERION = make_criterion("tensile_strength", ">=", 80)
HARDNESS_CRITERION = make_criterion("hardness", ">=", 50)  # never measured


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
    conflict = next(c for c in candidates.candidates if c.action_class == "measurement:repeat")
    other = next(c for c in candidates.candidates if c.id != conflict.id)
    return pool, iteration, candidates, conflict, other


# -- 1. valid variance-reduction computation -----------------------------------------------------------


def test_1_valid_variance_reduction():
    pool, iteration, candidates, conflict, other = _setup()
    model = SurrogateInformationValueModel({conflict.id: SurrogateState(current_variance=4.0, expected_variance_after=1.5)})
    result = estimate_information_value(conflict, iteration, model)
    assert result.estimate == 2.5
    assert result.estimate_status == ESTIMATED
    assert result.model_name == "surrogate:variance_reduction"
    assert "4.0" in result.basis and "1.5" in result.basis


# -- 2. negative reduction reported honestly, never clamped ---------------------------------------------


def test_2_negative_reduction_not_clamped():
    pool, iteration, candidates, conflict, other = _setup()
    model = SurrogateInformationValueModel({conflict.id: SurrogateState(current_variance=1.0, expected_variance_after=3.0)})
    result = estimate_information_value(conflict, iteration, model)
    assert result.estimate == -2.0
    assert result.estimate_status == ESTIMATED  # a real, if unusual, computed number -- not a rejection
    assert "negative" in result.basis


# -- 3. missing predictive uncertainty -> NOT_DETERMINABLE ------------------------------------------------


def test_3_missing_current_variance():
    pool, iteration, candidates, conflict, other = _setup()
    model = SurrogateInformationValueModel({conflict.id: SurrogateState(expected_variance_after=1.0)})
    result = estimate_information_value(conflict, iteration, model)
    assert result.estimate is None
    assert result.estimate_status == NOT_DETERMINABLE
    assert "current_variance" in result.basis


# -- 4. missing expected post-experiment uncertainty -> NOT_DETERMINABLE ----------------------------------


def test_4_missing_expected_variance_after():
    pool, iteration, candidates, conflict, other = _setup()
    model = SurrogateInformationValueModel({conflict.id: SurrogateState(current_variance=2.0)})
    result = estimate_information_value(conflict, iteration, model)
    assert result.estimate is None
    assert result.estimate_status == NOT_DETERMINABLE
    assert "expected_variance_after" in result.basis


# -- 5. non-finite values -> NOT_DETERMINABLE --------------------------------------------------------------


def test_5_non_finite_values():
    pool, iteration, candidates, conflict, other = _setup()
    model_nan = SurrogateInformationValueModel({conflict.id: SurrogateState(current_variance=math.nan, expected_variance_after=1.0)})
    result_nan = estimate_information_value(conflict, iteration, model_nan)
    assert result_nan.estimate is None
    assert result_nan.estimate_status == NOT_DETERMINABLE

    model_inf = SurrogateInformationValueModel({conflict.id: SurrogateState(current_variance=2.0, expected_variance_after=math.inf)})
    result_inf = estimate_information_value(conflict, iteration, model_inf)
    assert result_inf.estimate is None
    assert result_inf.estimate_status == NOT_DETERMINABLE


# -- 6. no state supplied for a candidate at all -> NOT_DETERMINABLE ---------------------------------------


def test_6_no_state_supplied():
    pool, iteration, candidates, conflict, other = _setup()
    model = SurrogateInformationValueModel({conflict.id: SurrogateState(current_variance=4.0, expected_variance_after=1.0)})
    result = estimate_information_value(other, iteration, model)  # other candidate has no entry
    assert result.estimate is None
    assert result.estimate_status == NOT_DETERMINABLE
    assert "no SurrogateState" in result.basis


# -- 7. provenance preserved through to the targeted requirement --------------------------------------------


def test_7_provenance_preserved():
    pool, iteration, candidates, conflict, other = _setup()
    model = SurrogateInformationValueModel({conflict.id: SurrogateState(current_variance=4.0, expected_variance_after=1.0)})
    result = estimate_information_value(conflict, iteration, model)
    requirement = result.information_value.evaluation.targeted_requirements[0]
    assert requirement.formulation.natural_key == "formulation-f1"
    assert result.candidate_id == conflict.id == result.information_value.candidate_id


# -- 8. deterministic multi-candidate ordering + no mutation ---------------------------------------------------


def test_8_deterministic_and_no_mutation():
    pool, iteration, candidates, conflict, other = _setup()
    states = {c.id: SurrogateState(current_variance=5.0, expected_variance_after=2.0) for c in candidates.candidates}
    model = SurrogateInformationValueModel(states)
    before_iteration = repr(iteration)
    fingerprint_before = pool.fingerprint()

    a = estimate_information_values(candidates, iteration, model)
    b = estimate_information_values(candidates, iteration, model)
    assert [e.candidate_id for e in a.estimates] == [e.candidate_id for e in b.estimates] == [c.id for c in candidates.candidates]
    assert [e.estimate for e in a.estimates] == [e.estimate for e in b.estimates] == [3.0] * len(candidates.candidates)

    assert repr(iteration) == before_iteration
    assert pool.fingerprint() == fingerprint_before
