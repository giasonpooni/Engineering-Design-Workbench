"""Phase 40: materials.plan -- small focused test set over a single
compact fixture (build-more-test-less development mode). Covers exactly
the six required cases, not an exhaustive matrix.
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
from materials.plan import assemble_experiment_plan
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
DENY_ALL = SelectionPolicy(
    allowed_action_classes=(), allow_already_represented_context=True,
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

    obs_a = _obs("ts-a", {"property": "tensile_strength", "value": 82, "unit": "MPa"})
    obs_b = _obs("ts-b", {"property": "tensile_strength", "value": 79, "unit": "MPa"})
    _obs("visc-40", {"property": "viscosity", "value": 1120, "unit": "mPa.s", "temperature": 40, "temperature_unit": "C"})
    # hardness: never measured -> MISSING_EVIDENCE

    return pool, obs_a, obs_b


def _selection_for(pool, policy, criteria, properties):
    query = make_material_program_query(["formulation-f1"], "process-std-190c", properties)
    program_answer = analyze_program(pool, ENGINE, query)
    decision = evaluate_program(program_answer, criteria)
    audit = audit_program(decision)
    gaps = analyze_experiment_gaps(audit)
    spec = specify_experiment_requirements(gaps)
    candidates = generate_candidates(spec)
    evaluations = evaluate_candidates(candidates)
    return select_candidates(evaluations, policy)


def _full_selection(policy):
    pool, obs_a, obs_b = _fixture()
    return pool, obs_a, obs_b, _selection_for(
        pool, policy, (TENSILE_CRITERION, VISCOSITY_CRITERION, HARDNESS_CRITERION),
        ("tensile_strength", "viscosity", "hardness"),
    )


# -- 1. selected candidates become plan entries ---------------------------------------------------


def test_1_selected_candidates_become_plan_entries():
    pool, obs_a, obs_b, selection = _full_selection(ALLOW_ALL)
    plan = assemble_experiment_plan(selection)
    selected_ids = {s.evaluation.candidate.id for s in selection.selections if s.selected}
    plan_ids = {e.candidate_id for e in plan.entries}
    assert plan_ids == selected_ids
    assert len(plan.entries) > 0


# -- 2. unselected candidates are excluded ----------------------------------------------------------


def test_2_unselected_candidates_excluded():
    pool, obs_a, obs_b, selection = _full_selection(DENY_ALL)  # empty allow-list -> nothing eligible
    assert any(not s.selected for s in selection.selections)
    plan = assemble_experiment_plan(selection)
    assert plan.entries == ()


# -- 3. information preservation ----------------------------------------------------------------------


def test_3_information_preservation():
    pool, obs_a, obs_b, selection = _full_selection(ALLOW_ALL)
    plan = assemble_experiment_plan(selection)
    entry = next(e for e in plan.entries if e.action_class == "measurement:repeat")
    candidate = entry.selection.evaluation.candidate
    assert entry.candidate_id == candidate.id
    assert entry.action_class == candidate.action_class
    assert entry.formulation == candidate.formulation
    assert entry.property == candidate.property
    assert entry.role == candidate.role
    assert dict(entry.target_context) == dict(candidate.target_context)
    assert entry.requirement_ids == candidate.requirement_ids
    assert set(entry.existing_evidence_ids) == {obs_a.id, obs_b.id}
    assert entry.evaluation is next(s.evaluation for s in selection.selections if s.evaluation.candidate.id == candidate.id)


# -- 4. deterministic ordering -------------------------------------------------------------------------


def test_4_deterministic_ordering():
    pool, obs_a, obs_b, selection = _full_selection(ALLOW_ALL)
    plan_a = assemble_experiment_plan(selection)
    plan_b = assemble_experiment_plan(selection)
    ids_a = [e.candidate_id for e in plan_a.entries]
    ids_b = [e.candidate_id for e in plan_b.entries]
    assert ids_a == ids_b == sorted(ids_a)


# -- 5. empty selection produces a valid empty plan ------------------------------------------------------


def test_5_empty_selection_produces_empty_plan():
    pool, obs_a, obs_b, selection = _full_selection(DENY_ALL)
    plan = assemble_experiment_plan(selection)
    assert plan.entries == ()
    assert plan.process_natural_key == selection.process_natural_key
    assert plan.selection is selection


# -- 6. input immutability ---------------------------------------------------------------------------------


def test_6_input_immutability():
    pool, obs_a, obs_b, selection = _full_selection(ALLOW_ALL)
    before = repr(selection)
    fingerprint_before = pool.fingerprint()
    assemble_experiment_plan(selection)
    assert repr(selection) == before
    assert pool.fingerprint() == fingerprint_before
