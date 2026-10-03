"""Phase 39: materials.selection -- small focused test set over a single
compact fixture (build-more-test-less development mode). Covers exactly
the seven required cases, not an exhaustive matrix.
"""

from evidence.admission import (
    admit_claimed_relationship, admit_document, admit_observation, admit_record, admit_referent,
)
from evidence.pool import EvidencePool
from evidence.types import (
    make_claimed_relationship, make_document, make_observation, make_record, make_referent, make_source,
)
from materials.audit import audit_program
from materials.candidates import generate_candidates
from materials.decision import make_criterion, evaluate_program
from materials.evaluation import evaluate_candidates
from materials.experiment import analyze_experiment_gaps
from materials.program import make_material_program_query, analyze_program
from materials.selection import SelectionPolicy, select_candidates
from materials.specification import specify_experiment_requirements
from retrieval.engine import DeterministicRetrievalEngine

ENGINE = DeterministicRetrievalEngine()

TENSILE_CRITERION = make_criterion("tensile_strength", ">=", 80)
VISCOSITY_CRITERION = make_criterion("viscosity", "<=", 950, context={"unit": "mPa.s", "temperature": 25, "temperature_unit": "C"})
HARDNESS_CRITERION = make_criterion("hardness", ">=", 50)  # never measured

ALLOW_ALL = SelectionPolicy(
    allowed_action_classes=None, allow_already_represented_context=True,
    allow_redundant=True, allow_not_determinable_feasibility=True, max_selected=None,
)


def _fixture():
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

    def _obs(locator, content):
        rec = make_record(document_id=doc.id, locator=locator, raw_content=locator)
        admit_record(pool, rec)
        pool.put_record(rec)
        obs = make_observation(record_ids=(rec.id,), extraction_method="human_transcription", content=content, confidence=1.0, extracted_at="2026-08-23T00:00:00Z")
        admit_observation(pool, obs)
        pool.put_observation(obs)
        rel = make_claimed_relationship(from_referent_id=f1.id, to_referent_id=process.id, type="tested_during", observation_id=obs.id, confidence=1.0)
        admit_claimed_relationship(pool, rel)
        pool.put_claimed_relationship(rel)
        return obs

    _obs("ts-a", {"property": "tensile_strength", "value": 82, "unit": "MPa"})
    _obs("ts-b", {"property": "tensile_strength", "value": 79, "unit": "MPa"})
    _obs("visc-40", {"property": "viscosity", "value": 1120, "unit": "mPa.s", "temperature": 40, "temperature_unit": "C"})
    # hardness: never measured -> MISSING_EVIDENCE

    return pool


def _evaluations_for(pool, criteria, properties):
    query = make_material_program_query(["formulation-f1"], "process-std-190c", properties)
    program_answer = analyze_program(pool, ENGINE, query)
    decision = evaluate_program(program_answer, criteria)
    audit = audit_program(decision)
    gaps = analyze_experiment_gaps(audit)
    spec = specify_experiment_requirements(gaps)
    return evaluate_candidates(generate_candidates(spec))


def _full_evaluations():
    pool = _fixture()
    return _evaluations_for(
        pool, (TENSILE_CRITERION, VISCOSITY_CRITERION, HARDNESS_CRITERION),
        ("tensile_strength", "viscosity", "hardness"),
    )


def _find(selection_set, action_class):
    return next(s for s in selection_set.selections if s.evaluation.candidate.action_class == action_class)


# -- 1. eligible candidate selected -----------------------------------------------------------------


def test_1_eligible_candidate_selected():
    evaluations = _full_evaluations()
    result = select_candidates(evaluations, ALLOW_ALL)
    s = _find(result, "measurement:repeat")
    assert s.eligible is True
    assert s.selected is True


# -- 2. policy exclusion -------------------------------------------------------------------------------


def test_2_policy_exclusion_by_action_class():
    evaluations = _full_evaluations()
    policy = SelectionPolicy(
        allowed_action_classes=("measurement:context",), allow_already_represented_context=True,
        allow_redundant=True, allow_not_determinable_feasibility=True, max_selected=None,
    )
    result = select_candidates(evaluations, policy)
    s = _find(result, "measurement:repeat")
    assert s.eligible is False
    assert s.selected is False
    assert "action_class" in s.eligibility_reason
    s2 = _find(result, "measurement:context")
    assert s2.eligible is True


# -- 3. NOT_DETERMINABLE feasibility handling ----------------------------------------------------------


def test_3_not_determinable_feasibility_handling():
    evaluations = _full_evaluations()
    strict_policy = SelectionPolicy(
        allowed_action_classes=None, allow_already_represented_context=True,
        allow_redundant=True, allow_not_determinable_feasibility=False, max_selected=None,
    )
    result = select_candidates(evaluations, strict_policy)
    # every candidate's feasibility is NOT_DETERMINABLE today (Phase 38
    # finding) -- so a policy that refuses NOT_DETERMINABLE feasibility
    # must make every candidate ineligible, never silently promote one.
    assert all(s.eligible is False for s in result.selections)
    assert all("NOT_DETERMINABLE" in s.eligibility_reason for s in result.selections)

    permissive = select_candidates(evaluations, ALLOW_ALL)
    assert any(s.eligible is True for s in permissive.selections)


# -- 4. maximum-selection limit -------------------------------------------------------------------------


def test_4_maximum_selection_limit():
    evaluations = _full_evaluations()
    policy = SelectionPolicy(
        allowed_action_classes=None, allow_already_represented_context=True,
        allow_redundant=True, allow_not_determinable_feasibility=True, max_selected=1,
    )
    result = select_candidates(evaluations, policy)
    eligible = [s for s in result.selections if s.eligible]
    selected = [s for s in result.selections if s.selected]
    assert len(eligible) >= 2  # more than one eligible candidate exists
    assert len(selected) == 1
    assert selected[0].evaluation.candidate.id == min(s.evaluation.candidate.id for s in eligible)


# -- 5. deterministic ordering --------------------------------------------------------------------------


def test_5_deterministic_ordering():
    evaluations = _full_evaluations()
    a = select_candidates(evaluations, ALLOW_ALL)
    b = select_candidates(evaluations, ALLOW_ALL)
    ids_a = [s.evaluation.candidate.id for s in a.selections]
    ids_b = [s.evaluation.candidate.id for s in b.selections]
    assert ids_a == ids_b == sorted(ids_a)


# -- 6. complete evaluation/provenance preservation -----------------------------------------------------


def test_6_complete_evaluation_preserved():
    evaluations = _full_evaluations()
    result = select_candidates(evaluations, ALLOW_ALL)
    by_id = {e.candidate.id: e for e in evaluations.evaluations}
    for s in result.selections:
        assert s.evaluation is by_id[s.evaluation.candidate.id]
        assert s.evaluation.targeted_requirements  # full requirement provenance still reachable


# -- 7. input immutability -------------------------------------------------------------------------------


def test_7_input_immutability():
    pool = _fixture()
    evaluations = _evaluations_for(pool, (TENSILE_CRITERION,), ("tensile_strength",))
    before = repr(evaluations)
    fingerprint_before = pool.fingerprint()
    select_candidates(evaluations, ALLOW_ALL)
    assert repr(evaluations) == before
    assert pool.fingerprint() == fingerprint_before
