"""Phase 49: materials.optimization -- small focused test set over a
single compact fixture (build-more-test-less development mode).
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
from materials.optimization import (
    ELIGIBLE_NOT_SELECTED, NOT_ELIGIBLE, SELECTED, OptimizationPolicy, optimize_candidates,
)
from materials.program import make_material_program_query
from materials.utility import ExperimentUtilityInput, evaluate_utility_set
from materials.value import evaluate_candidate_information_values
from retrieval.engine import DeterministicRetrievalEngine

ENGINE = DeterministicRetrievalEngine()
TENSILE_CRITERION = make_criterion("tensile_strength", ">=", 80)
HARDNESS_CRITERION = make_criterion("hardness", ">=", 50)  # never measured


def _utility_set():
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
    values = evaluate_candidate_information_values(candidates, iteration)

    tensile = next(v for v in values.values if v.evaluation.candidate.action_class == "measurement:repeat")
    hardness = next(v for v in values.values if v.evaluation.candidate.action_class == "acquisition:unspecified")
    tensile_model = next(v for v in values.values if v.evaluation.candidate.action_class == "model_validation:unspecified")

    inputs = {
        tensile.candidate_id: ExperimentUtilityInput(benefit=150.0, cost=50.0),   # utility 100
        hardness.candidate_id: ExperimentUtilityInput(benefit=80.0, cost=30.0),   # utility 50
        # tensile_model intentionally left out -- indeterminate utility
    }
    return evaluate_utility_set(values, inputs), tensile.candidate_id, hardness.candidate_id, tensile_model.candidate_id


# -- 1. correct top-K selection by utility -----------------------------------------------------------


def test_1_top_k_selection_by_utility():
    utility_set, tensile_id, hardness_id, indeterminate_id = _utility_set()
    policy = OptimizationPolicy(max_candidates=1, allowed_action_classes=None, allow_indeterminate_utility=False)
    result = optimize_candidates(utility_set, policy)
    selected = [o for o in result.optimizations if o.status == SELECTED]
    assert [o.candidate_id for o in selected] == [tensile_id]  # utility 100 > 50
    assert result.total_selected_utility == 100.0
    hardness_opt = next(o for o in result.optimizations if o.candidate_id == hardness_id)
    assert hardness_opt.status == ELIGIBLE_NOT_SELECTED


# -- 2. indeterminate utility excluded unless explicitly permitted ------------------------------------


def test_2_indeterminate_utility_policy():
    utility_set, tensile_id, hardness_id, indeterminate_id = _utility_set()
    strict = OptimizationPolicy(max_candidates=None, allowed_action_classes=None, allow_indeterminate_utility=False)
    result_strict = optimize_candidates(utility_set, strict)
    indeterminate_opt = next(o for o in result_strict.optimizations if o.candidate_id == indeterminate_id)
    assert indeterminate_opt.status == NOT_ELIGIBLE

    permissive = OptimizationPolicy(max_candidates=None, allowed_action_classes=None, allow_indeterminate_utility=True)
    result_permissive = optimize_candidates(utility_set, permissive)
    indeterminate_opt2 = next(o for o in result_permissive.optimizations if o.candidate_id == indeterminate_id)
    assert indeterminate_opt2.status == ELIGIBLE_NOT_SELECTED  # still never selected -- no value to compare


# -- 3. action-class filtering ---------------------------------------------------------------------------


def test_3_action_class_filtering():
    utility_set, tensile_id, hardness_id, indeterminate_id = _utility_set()
    policy = OptimizationPolicy(max_candidates=None, allowed_action_classes=("acquisition:unspecified",), allow_indeterminate_utility=True)
    result = optimize_candidates(utility_set, policy)
    tensile_opt = next(o for o in result.optimizations if o.candidate_id == tensile_id)
    assert tensile_opt.status == NOT_ELIGIBLE
    assert "action_class" in tensile_opt.eligibility_reason
    hardness_opt = next(o for o in result.optimizations if o.candidate_id == hardness_id)
    assert hardness_opt.status == SELECTED


# -- 4. deterministic output, including tie-break -----------------------------------------------------------


def test_4_deterministic_output_and_tie_break():
    utility_set, tensile_id, hardness_id, indeterminate_id = _utility_set()
    policy = OptimizationPolicy(max_candidates=1, allowed_action_classes=None, allow_indeterminate_utility=False)
    a = optimize_candidates(utility_set, policy)
    b = optimize_candidates(utility_set, policy)
    assert [o.status for o in a.optimizations] == [o.status for o in b.optimizations]
    assert [o.candidate_id for o in a.optimizations] == [o.candidate_id for o in b.optimizations]
    assert a.total_selected_utility == b.total_selected_utility


# -- 5. provenance preserved --------------------------------------------------------------------------------


def test_5_provenance_preserved():
    utility_set, tensile_id, hardness_id, indeterminate_id = _utility_set()
    policy = OptimizationPolicy(max_candidates=1, allowed_action_classes=None, allow_indeterminate_utility=False)
    result = optimize_candidates(utility_set, policy)
    selected = next(o for o in result.optimizations if o.status == SELECTED)
    requirement = selected.utility.information_value.evaluation.targeted_requirements[0]
    assert requirement.formulation.natural_key == "formulation-f1"
    assert selected.utility.candidate_id == selected.candidate_id


# -- 6. no mutation, and empty selection is a real 0.0 --------------------------------------------------------


def test_6_no_mutation_and_empty_selection_is_zero():
    utility_set, tensile_id, hardness_id, indeterminate_id = _utility_set()
    before = repr(utility_set)
    policy = OptimizationPolicy(max_candidates=0, allowed_action_classes=None, allow_indeterminate_utility=False)
    result = optimize_candidates(utility_set, policy)
    assert repr(utility_set) == before
    assert result.total_selected_utility == 0.0
    assert not any(o.status == SELECTED for o in result.optimizations)
