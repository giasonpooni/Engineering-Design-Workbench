"""Phase 47: materials.utility -- small focused test set over a single
compact fixture (build-more-test-less development mode).
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
from materials.iteration import reevaluate_program
from materials.program import make_material_program_query
from materials.utility import (
    NOT_DETERMINABLE, SUPPLIED, ExperimentUtilityInput, evaluate_candidate_utility, evaluate_utility_set,
)
from materials.value import evaluate_candidate_information_values
from retrieval.engine import DeterministicRetrievalEngine

ENGINE = DeterministicRetrievalEngine()
TENSILE_CRITERION = make_criterion("tensile_strength", ">=", 80)
HARDNESS_CRITERION = make_criterion("hardness", ">=", 50)  # never measured


def _values():
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
    return pool, evaluate_candidate_information_values(candidates, iteration)


def _find(values_set, action_class):
    return next(v for v in values_set.values if v.evaluation.candidate.action_class == action_class)


# -- 1. fully supplied utility calculation -----------------------------------------------------------


def test_1_fully_supplied_utility_calculation():
    pool, values = _values()
    conflict = _find(values, "measurement:repeat")
    cu = evaluate_candidate_utility(conflict, ExperimentUtilityInput(benefit=500.0, cost=120.0))
    assert cu.utility == 380.0
    assert cu.utility_status == SUPPLIED


# -- 2. missing utility inputs remain NOT_DETERMINABLE ------------------------------------------------


def test_2_missing_inputs_remain_not_determinable():
    pool, values = _values()
    conflict = _find(values, "measurement:repeat")
    cu_nothing = evaluate_candidate_utility(conflict, ExperimentUtilityInput())
    assert cu_nothing.utility is None
    assert cu_nothing.utility_status == NOT_DETERMINABLE

    cu_cost_only = evaluate_candidate_utility(conflict, ExperimentUtilityInput(cost=50.0))
    assert cu_cost_only.utility is None
    assert cu_cost_only.utility_status == NOT_DETERMINABLE


# -- 3. zero is distinguishable from missing ----------------------------------------------------------


def test_3_zero_distinguishable_from_missing():
    pool, values = _values()
    conflict = _find(values, "measurement:repeat")
    cu_zero = evaluate_candidate_utility(conflict, ExperimentUtilityInput(benefit=0.0, cost=0.0))
    assert cu_zero.utility == 0.0
    assert cu_zero.utility_status == SUPPLIED  # a real, supplied zero -- not the same as NOT_DETERMINABLE

    cu_missing = evaluate_candidate_utility(conflict, ExperimentUtilityInput())
    assert cu_missing.utility is None
    assert cu_missing.utility_status == NOT_DETERMINABLE
    assert cu_zero.utility_status != cu_missing.utility_status


# -- 4. candidate identity/provenance preservation ------------------------------------------------------


def test_4_candidate_identity_and_provenance_preserved():
    pool, values = _values()
    conflict = _find(values, "measurement:repeat")
    cu = evaluate_candidate_utility(conflict, ExperimentUtilityInput(benefit=10.0, cost=1.0))
    assert cu.candidate_id == conflict.candidate_id == conflict.evaluation.candidate.id
    # full chain reachable through the embedded information_value, unmodified
    assert cu.information_value is conflict
    requirement = cu.information_value.evaluation.targeted_requirements[0]
    assert requirement.formulation.natural_key == "formulation-f1"


# -- 5. deterministic output --------------------------------------------------------------------------------


def test_5_deterministic_output():
    pool, values = _values()
    inputs = {v.candidate_id: ExperimentUtilityInput(benefit=100.0, cost=25.0) for v in values.values}
    a = evaluate_utility_set(values, inputs)
    b = evaluate_utility_set(values, inputs)
    ids_a = [u.candidate_id for u in a.utilities]
    ids_b = [u.candidate_id for u in b.utilities]
    assert ids_a == ids_b == sorted(ids_a)
    assert [u.utility for u in a.utilities] == [u.utility for u in b.utilities]
    forbidden = ("score", "rank", "ranking", "winner", "best", "recommended", "optimal", "priority")
    for u in a.utilities:
        assert not any(hasattr(u, name) for name in forbidden)


# -- 6. input immutability -------------------------------------------------------------------------------------


def test_6_input_immutability():
    pool, values = _values()
    before = repr(values)
    evaluate_utility_set(values, {values.values[0].candidate_id: ExperimentUtilityInput(benefit=1.0, cost=1.0)})
    assert repr(values) == before
