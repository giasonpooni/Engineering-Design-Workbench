"""Phase 46: materials.value -- structural information value over the
current MaterialsIteration + CandidateSet. Small focused test set,
doubling as the phase's own required investigation into cases A-D,
verified against real fixtures rather than asserted from reasoning.
"""

from evidence.admission import (
    admit_claimed_relationship, admit_derived_grounding, admit_derived_value,
    admit_document, admit_observation, admit_record, admit_referent,
)
from evidence.pool import EvidencePool
from evidence.types import (
    make_claimed_relationship, make_derived_grounding, make_derived_value,
    make_document, make_observation, make_record, make_referent, make_source,
)
from materials.candidates import generate_candidates
from materials.decision import CONFLICTING_EVIDENCE, INCOMPARABLE, INSUFFICIENT_EVIDENCE, make_criterion
from materials.iteration import reevaluate_program
from materials.program import make_material_program_query
from materials.value import (
    ADDRESSES_MODEL_DISAGREEMENT, REDUCES_INCOMPARABILITY, RESOLVES_MISSING_EVIDENCE,
    TESTS_CONFLICT, evaluate_candidate_information_values,
)
from retrieval.engine import DeterministicRetrievalEngine

ENGINE = DeterministicRetrievalEngine()

TENSILE_CRITERION = make_criterion("tensile_strength", ">=", 80)          # B: conflict
HARDNESS_CRITERION = make_criterion("hardness", ">=", 80)                 # C: investigated, no gap
ELONGATION_CRITERION = make_criterion("elongation_at_break", ">=", 5)     # A: missing evidence
VISCOSITY_CRITERION = make_criterion("viscosity", "<=", 950, context={"unit": "mPa.s", "temperature": 25, "temperature_unit": "C"})  # D
IMPACT_CRITERION = make_criterion("impact_strength", ">=", 85)            # model disagreement

CRITERIA = (TENSILE_CRITERION, HARDNESS_CRITERION, ELONGATION_CRITERION, VISCOSITY_CRITERION, IMPACT_CRITERION)
PROPERTIES = ("tensile_strength", "hardness", "elongation_at_break", "viscosity", "impact_strength")


def _add_obs(pool, doc, formulation, process, locator, content):
    rec = make_record(document_id=doc.id, locator=locator, raw_content=locator)
    admit_record(pool, rec)
    pool.put_record(rec)
    obs = make_observation(record_ids=(rec.id,), extraction_method="human_transcription", content=content, confidence=1.0, extracted_at="2026-08-23T00:00:00Z")
    admit_observation(pool, obs)
    pool.put_observation(obs)
    rel = make_claimed_relationship(from_referent_id=formulation.id, to_referent_id=process.id, type="tested_during", observation_id=obs.id, confidence=1.0)
    admit_claimed_relationship(pool, rel)
    pool.put_claimed_relationship(rel)
    return obs


def _add_pred(pool, formulation, obs, method, content):
    dv = make_derived_value(derived_from=[obs.id], method=method, content=content, confidence=0.85, derived_at="2026-08-23T01:00:00Z")
    admit_derived_value(pool, dv)
    pool.put_derived_value(dv)
    g = make_derived_grounding(derived_value_id=dv.id, referent_ids=[formulation.id])
    admit_derived_grounding(pool, g)
    pool.put_derived_grounding(g)
    return dv


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

    # B: tensile_strength conflict
    _add_obs(pool, doc, f1, process, "ts-a", {"property": "tensile_strength", "value": 78, "unit": "MPa"})
    _add_obs(pool, doc, f1, process, "ts-b", {"property": "tensile_strength", "value": 84, "unit": "MPa"})

    # C investigation: one observation, one (independently passing) prediction -- no gap expected
    hardness_obs = _add_obs(pool, doc, f1, process, "hard-a", {"property": "hardness", "value": 78, "unit": "Shore D"})
    _add_pred(pool, f1, hardness_obs, "model:A", {"property": "hardness", "predicted_value": 86, "unit": "Shore D"})

    # A: elongation_at_break never measured or predicted at all -- MISSING_EVIDENCE

    # D: viscosity only at 40C, criterion requires 25C
    _add_obs(pool, doc, f1, process, "visc-40", {"property": "viscosity", "value": 1120, "unit": "mPa.s", "temperature": 40, "temperature_unit": "C"})

    # MODEL_DISAGREEMENT: two predictions from the SAME observation, disagreeing against a strict criterion
    impact_obs = _add_obs(pool, doc, f1, process, "imp-a", {"property": "impact_strength", "value": 86, "unit": "J/m"})
    _add_pred(pool, f1, impact_obs, "model:A", {"property": "impact_strength", "predicted_value": 84, "unit": "J/m"})
    _add_pred(pool, f1, impact_obs, "model:B", {"property": "impact_strength", "predicted_value": 89, "unit": "J/m"})

    query = make_material_program_query(["formulation-f1"], "process-std-190c", PROPERTIES)
    return pool, query


def _iteration_and_candidates():
    pool, query = _setup()
    iteration = reevaluate_program(pool, ENGINE, query, CRITERIA)
    candidates = generate_candidates(iteration.specification)
    return iteration, candidates


def _value_for(values_set, property_name):
    return next(v for v in values_set.values if v.property == property_name)


# -- 1. missing evidence (A) -----------------------------------------------------------------------


def test_1_missing_evidence_case_a():
    iteration, candidates = _iteration_and_candidates()
    values = evaluate_candidate_information_values(candidates, iteration)
    v = _value_for(values, "elongation_at_break")
    assert v.value_kind == RESOLVES_MISSING_EVIDENCE
    assert v.current_status == INSUFFICIENT_EVIDENCE
    assert v.target_context_represented is False
    assert v.redundant_with_existing_evidence is False
    assert "resolves" not in v.explanation and "will" not in v.explanation


# -- 2. conflict (B) --------------------------------------------------------------------------------


def test_2_conflict_case_b():
    iteration, candidates = _iteration_and_candidates()
    values = evaluate_candidate_information_values(candidates, iteration)
    v = _value_for(values, "tensile_strength")
    assert v.value_kind == TESTS_CONFLICT
    assert v.current_status == CONFLICTING_EVIDENCE
    assert v.gap_category == "MEASUREMENT_CONFLICT"


# -- 3. model disagreement -----------------------------------------------------------------------------


def test_3_model_disagreement():
    iteration, candidates = _iteration_and_candidates()
    values = evaluate_candidate_information_values(candidates, iteration)
    v = _value_for(values, "impact_strength")
    assert v.value_kind == ADDRESSES_MODEL_DISAGREEMENT
    assert v.current_status == CONFLICTING_EVIDENCE
    assert v.role == "PREDICTED"


def test_3b_case_c_produces_no_gap_at_all():
    """The phase's own most important investigation: a single
    observation (78, FAIL) and a single independently-passing prediction
    (86, PASS) for the SAME property produce NO gap category, NO
    EvidenceRequirement, and NO ActionCandidate -- verified directly,
    not assumed. There is nothing for evaluate_information_value to be
    called on for 'hardness' at all."""
    iteration, candidates = _iteration_and_candidates()
    hardness_candidates = [c for c in candidates.candidates if c.property == "hardness"]
    assert hardness_candidates == []
    hardness_requirements = [
        r for entry in iteration.specification.entries for r in entry.requirements if r.property == "hardness"
    ]
    assert hardness_requirements == []


# -- 4. missing context (D) ------------------------------------------------------------------------------


def test_4_missing_context_case_d():
    iteration, candidates = _iteration_and_candidates()
    values = evaluate_candidate_information_values(candidates, iteration)
    v = _value_for(values, "viscosity")
    assert v.value_kind == REDUCES_INCOMPARABILITY
    assert v.current_status == INCOMPARABLE
    assert v.target_context == {"unit": "mPa.s", "temperature": 25, "temperature_unit": "C"}
    assert v.existing_contexts[0]["temperature"] == 40
    assert v.redundant_with_existing_evidence is False  # zero matches, not ambiguous multiple


# -- 5. deterministic multi-candidate evaluation ---------------------------------------------------------------


def test_5_deterministic_multi_candidate_evaluation():
    iteration, candidates = _iteration_and_candidates()
    a = evaluate_candidate_information_values(candidates, iteration)
    b = evaluate_candidate_information_values(candidates, iteration)
    ids_a = [v.candidate_id for v in a.values]
    ids_b = [v.candidate_id for v in b.values]
    assert ids_a == ids_b == sorted(ids_a) == [c.id for c in candidates.candidates]
    assert [v.value_kind for v in a.values] == [v.value_kind for v in b.values]
    # no ranking/scoring/selection field anywhere
    forbidden = ("score", "rank", "ranking", "winner", "best", "recommended", "optimal", "priority", "utility", "cost", "probability", "confidence")
    for v in a.values:
        assert not any(hasattr(v, name) for name in forbidden)


# -- 6. no mutation --------------------------------------------------------------------------------------------


def test_6_no_mutation():
    pool, query = _setup()
    iteration = reevaluate_program(pool, ENGINE, query, CRITERIA)
    candidates = generate_candidates(iteration.specification)
    before_iteration = repr(iteration)
    before_candidates = repr(candidates)
    fingerprint_before = pool.fingerprint()
    evaluate_candidate_information_values(candidates, iteration)
    assert repr(iteration) == before_iteration
    assert repr(candidates) == before_candidates
    assert pool.fingerprint() == fingerprint_before
