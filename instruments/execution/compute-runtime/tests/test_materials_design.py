"""Phase 41: materials.design -- small focused test set over a single
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
from materials.design import assemble_experimental_design
from materials.evaluation import evaluate_candidates
from materials.experiment import analyze_experiment_gaps
from materials.plan import assemble_experiment_plan
from materials.program import make_material_program_query, analyze_program
from materials.selection import SelectionPolicy, select_candidates
from materials.specification import specify_experiment_requirements
from retrieval.engine import DeterministicRetrievalEngine

ENGINE = DeterministicRetrievalEngine()

VISCOSITY_CRITERION = make_criterion("viscosity", "<=", 950, context={"unit": "mPa.s", "temperature": 25, "temperature_unit": "C"})
HARDNESS_CRITERION = make_criterion("hardness", ">=", 50)  # never measured

ALLOW_ALL = SelectionPolicy(
    allowed_action_classes=None, allow_already_represented_context=True,
    allow_redundant=True, allow_not_determinable_feasibility=True, max_selected=None,
)


def _plan():
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

    rec = make_record(document_id=doc.id, locator="visc-40", raw_content="visc-40")
    admit_record(pool, rec)
    pool.put_record(rec)
    obs = make_observation(
        record_ids=(rec.id,), extraction_method="human_transcription",
        content={"property": "viscosity", "value": 1120, "unit": "mPa.s", "temperature": 40, "temperature_unit": "C"},
        confidence=1.0, extracted_at="2026-08-23T00:00:00Z",
    )
    admit_observation(pool, obs)
    pool.put_observation(obs)
    rel = make_claimed_relationship(from_referent_id=f1.id, to_referent_id=process.id, type="tested_during", observation_id=obs.id, confidence=1.0)
    admit_claimed_relationship(pool, rel)
    pool.put_claimed_relationship(rel)

    query = make_material_program_query(["formulation-f1"], "process-std-190c", ("viscosity", "hardness"))
    program_answer = analyze_program(pool, ENGINE, query)
    decision = evaluate_program(program_answer, (VISCOSITY_CRITERION, HARDNESS_CRITERION))
    audit = audit_program(decision)
    gaps = analyze_experiment_gaps(audit)
    spec = specify_experiment_requirements(gaps)
    candidates = generate_candidates(spec)
    evaluations = evaluate_candidates(candidates)
    selection = select_candidates(evaluations, ALLOW_ALL)
    return pool, assemble_experiment_plan(selection)


# -- 1. selected plan entry can become a design -----------------------------------------------------


def test_1_plan_entry_becomes_design_entry():
    pool, plan = _plan()
    design = assemble_experimental_design(plan)
    assert len(design.entries) == len(plan.entries) > 0
    assert {e.plan_entry.candidate_id for e in design.entries} == {pe.candidate_id for pe in plan.entries}


# -- 2. explicitly supplied parameters are preserved -------------------------------------------------


def test_2_explicitly_supplied_parameters_preserved():
    pool, plan = _plan()
    context_entry = next(pe for pe in plan.entries if pe.action_class == "measurement:context")
    design = assemble_experimental_design(
        plan, design_parameters={context_entry.candidate_id: {"replicate_count": 3, "instrument": "DMA Q800"}},
    )
    e = next(e for e in design.entries if e.plan_entry.candidate_id == context_entry.candidate_id)
    assert dict(e.specified_parameters) == {"replicate_count": 3, "instrument": "DMA Q800"}
    other = next(e for e in design.entries if e.plan_entry.candidate_id != context_entry.candidate_id)
    assert dict(other.specified_parameters) == {}


# -- 3. inherited candidate information is preserved --------------------------------------------------


def test_3_inherited_candidate_information_preserved():
    pool, plan = _plan()
    context_entry = next(pe for pe in plan.entries if pe.action_class == "measurement:context")
    design = assemble_experimental_design(plan)
    e = next(e for e in design.entries if e.plan_entry.candidate_id == context_entry.candidate_id)
    assert dict(e.inherited_parameters) == dict(context_entry.target_context)
    assert e.inherited_parameters["temperature"] == 25


# -- 4. unspecified parameters remain explicitly unspecified -------------------------------------------


def test_4_unspecified_parameters_remain_explicit():
    pool, plan = _plan()
    context_entry = next(pe for pe in plan.entries if pe.action_class == "measurement:context")
    design = assemble_experimental_design(
        plan, unspecified_parameter_keys={context_entry.candidate_id: ("replicate_count",)},
    )
    e = next(e for e in design.entries if e.plan_entry.candidate_id == context_entry.candidate_id)
    assert e.unspecified_parameter_keys == ("replicate_count",)
    assert "replicate_count" not in e.specified_parameters
    other = next(e for e in design.entries if e.plan_entry.candidate_id != context_entry.candidate_id)
    assert other.unspecified_parameter_keys == ()  # never mentioned, not guessed


# -- 5. deterministic order (design reuses ActionCandidate.id, no new identity) -------------------------


def test_5_deterministic_order_reuses_candidate_id():
    pool, plan = _plan()
    design_a = assemble_experimental_design(plan)
    design_b = assemble_experimental_design(plan)
    ids_a = [e.plan_entry.candidate_id for e in design_a.entries]
    ids_b = [e.plan_entry.candidate_id for e in design_b.entries]
    assert ids_a == ids_b == sorted(ids_a) == [pe.candidate_id for pe in plan.entries]


# -- 6. input immutability -------------------------------------------------------------------------------


def test_6_input_immutability():
    pool, plan = _plan()
    before = repr(plan)
    fingerprint_before = pool.fingerprint()
    assemble_experimental_design(plan, design_parameters={plan.entries[0].candidate_id: {"instrument": "x"}})
    assert repr(plan) == before
    assert pool.fingerprint() == fingerprint_before
