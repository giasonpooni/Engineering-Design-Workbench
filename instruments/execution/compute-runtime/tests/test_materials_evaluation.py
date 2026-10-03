"""Phase 38: materials.evaluation -- small focused test set over a
single compact fixture (Phase 37's development-mode directive: build
more, test less). Covers exactly the six required cases, not an
exhaustive matrix.
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
from materials.evaluation import (
    CROSS_SIDE, NOT_DETERMINABLE, OBSERVED_SIDE, evaluate_candidates,
)
from materials.experiment import analyze_experiment_gaps
from materials.program import make_material_program_query, analyze_program
from materials.specification import specify_experiment_requirements
from retrieval.engine import DeterministicRetrievalEngine

ENGINE = DeterministicRetrievalEngine()

TENSILE_CRITERION = make_criterion("tensile_strength", ">=", 80)
VISCOSITY_CRITERION = make_criterion("viscosity", "<=", 950, context={"unit": "mPa.s", "temperature": 25, "temperature_unit": "C"})
HARDNESS_CRITERION = make_criterion("hardness", ">=", 50)  # never measured


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

    obs_a = _obs("ts-a", {"property": "tensile_strength", "value": 82, "unit": "MPa"})
    obs_b = _obs("ts-b", {"property": "tensile_strength", "value": 79, "unit": "MPa"})
    _obs("visc-40", {"property": "viscosity", "value": 1120, "unit": "mPa.s", "temperature": 40, "temperature_unit": "C"})
    # hardness: never measured at all -> MISSING_EVIDENCE

    return pool, f1, obs_a, obs_b


def _evaluate_for(pool, criteria, properties):
    query = make_material_program_query(["formulation-f1"], "process-std-190c", properties)
    program_answer = analyze_program(pool, ENGINE, query)
    decision = evaluate_program(program_answer, criteria)
    audit = audit_program(decision)
    gaps = analyze_experiment_gaps(audit)
    spec = specify_experiment_requirements(gaps)
    return evaluate_candidates(generate_candidates(spec))


def _find(eval_set, action_class):
    return next(e for e in eval_set.evaluations if e.candidate.action_class == action_class)


# -- 1. one candidate evaluates correctly (absence case) --------------------------------------------


def test_1_one_candidate_evaluates_correctly():
    pool, f1, obs_a, obs_b = _fixture()
    eval_set = _evaluate_for(pool, (HARDNESS_CRITERION,), ("hardness",))
    e = _find(eval_set, "acquisition:unspecified")
    assert e.gap_scope == CROSS_SIDE
    assert e.fully_specified is False
    assert e.redundant_with_existing_evidence is False
    assert e.target_context_represented is False
    assert e.feasibility_status == NOT_DETERMINABLE


# -- 2. existing evidence is correctly surfaced ---------------------------------------------------


def test_2_existing_evidence_correctly_surfaced():
    pool, f1, obs_a, obs_b = _fixture()
    eval_set = _evaluate_for(pool, (TENSILE_CRITERION,), ("tensile_strength",))
    e = _find(eval_set, "measurement:repeat")
    assert e.gap_scope == OBSERVED_SIDE
    assert set(e.candidate.existing_evidence_ids) == {obs_a.id, obs_b.id}
    assert set(e.targeted_requirements[0].existing_evidence_ids) == {obs_a.id, obs_b.id}
    assert e.redundant_with_existing_evidence is False  # conflicting, not redundant


# -- 3. unknown/non-determinable information is represented explicitly -----------------------------


def test_3_feasibility_always_explicitly_not_determinable():
    pool, f1, obs_a, obs_b = _fixture()
    eval_set = _evaluate_for(pool, (TENSILE_CRITERION, VISCOSITY_CRITERION), ("tensile_strength", "viscosity"))
    assert len(eval_set.evaluations) >= 2
    assert all(e.feasibility_status == NOT_DETERMINABLE for e in eval_set.evaluations)


# -- 4. multiple requirements remain associated with one candidate ----------------------------------


def test_4_multiple_requirements_remain_associated_with_one_candidate():
    pool, f1, obs_a, obs_b = _fixture()
    strict = make_criterion("tensile_strength", ">=", 81)  # 82/79 also straddles this -> also CONFLICTING
    eval_set = _evaluate_for(pool, (TENSILE_CRITERION, strict), ("tensile_strength",))
    e = _find(eval_set, "measurement:repeat")
    assert len(e.candidate.requirement_ids) == 2
    assert len(e.targeted_requirements) == 2
    assert {r.criterion.target for r in e.targeted_requirements} == {80.0, 81.0}


# -- 5. deterministic output --------------------------------------------------------------------------


def test_5_deterministic_output():
    pool, f1, obs_a, obs_b = _fixture()
    query = make_material_program_query(["formulation-f1"], "process-std-190c", ("tensile_strength", "viscosity", "hardness"))
    program_answer = analyze_program(pool, ENGINE, query)
    decision = evaluate_program(program_answer, (TENSILE_CRITERION, VISCOSITY_CRITERION, HARDNESS_CRITERION))
    audit = audit_program(decision)
    gaps = analyze_experiment_gaps(audit)
    spec = specify_experiment_requirements(gaps)
    candidates = generate_candidates(spec)
    a = evaluate_candidates(candidates)
    b = evaluate_candidates(candidates)
    summary_a = [(e.candidate.id, e.gap_scope, e.redundant_with_existing_evidence, e.fully_specified) for e in a.evaluations]
    summary_b = [(e.candidate.id, e.gap_scope, e.redundant_with_existing_evidence, e.fully_specified) for e in b.evaluations]
    assert summary_a == summary_b


# -- 6. input objects are not mutated -------------------------------------------------------------------


def test_6_input_objects_not_mutated():
    pool, f1, obs_a, obs_b = _fixture()
    query = make_material_program_query(["formulation-f1"], "process-std-190c", ("tensile_strength",))
    program_answer = analyze_program(pool, ENGINE, query)
    decision = evaluate_program(program_answer, (TENSILE_CRITERION,))
    audit = audit_program(decision)
    gaps = analyze_experiment_gaps(audit)
    spec = specify_experiment_requirements(gaps)
    candidates = generate_candidates(spec)
    before = repr(candidates)
    fingerprint_before = pool.fingerprint()
    evaluate_candidates(candidates)
    assert repr(candidates) == before
    assert pool.fingerprint() == fingerprint_before
