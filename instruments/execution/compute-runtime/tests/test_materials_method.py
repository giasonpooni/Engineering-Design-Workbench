"""Phase 42: materials.method + its integration into materials.design --
small focused test set over a single compact fixture (build-more-
test-less development mode). Covers exactly the six required cases, not
an exhaustive matrix.
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
from materials.design import METHOD_SPECIFIED, METHOD_UNSPECIFIED, assemble_experimental_design
from materials.evaluation import evaluate_candidates
from materials.experiment import analyze_experiment_gaps
from materials.method import make_experimental_method
from materials.plan import assemble_experiment_plan
from materials.program import make_material_program_query, analyze_program
from materials.selection import SelectionPolicy, select_candidates
from materials.specification import specify_experiment_requirements
from retrieval.engine import DeterministicRetrievalEngine

ENGINE = DeterministicRetrievalEngine()
TENSILE_CRITERION = make_criterion("tensile_strength", ">=", 80)

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

    for locator, value in (("ts-a", 82), ("ts-b", 79)):
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

    query = make_material_program_query(["formulation-f1"], "process-std-190c", ("tensile_strength",))
    program_answer = analyze_program(pool, ENGINE, query)
    decision = evaluate_program(program_answer, (TENSILE_CRITERION,))
    audit = audit_program(decision)
    gaps = analyze_experiment_gaps(audit)
    spec = specify_experiment_requirements(gaps)
    candidates = generate_candidates(spec)
    evaluations = evaluate_candidates(candidates)
    selection = select_candidates(evaluations, ALLOW_ALL)
    return pool, assemble_experiment_plan(selection)


# -- 1. method can be represented ---------------------------------------------------------------------


def test_1_method_can_be_represented():
    method = make_experimental_method("tensile_test", parameters={"strain_rate": 5.0, "strain_rate_unit": "mm/min"})
    assert method.kind == "tensile_test"
    assert dict(method.parameters) == {"strain_rate": 5.0, "strain_rate_unit": "mm/min"}
    assert method.id


# -- 2. method identity is deterministic (content-addressed) ------------------------------------------


def test_2_method_identity_deterministic():
    a = make_experimental_method("DMA", parameters={"frequency": 1, "unit": "Hz"})
    b = make_experimental_method("DMA", parameters={"unit": "Hz", "frequency": 1})  # different key order
    c = make_experimental_method("DMA", parameters={"frequency": 5, "unit": "Hz"})  # different value
    assert a.id == b.id
    assert a.id != c.id


# -- 3. design can reference an explicit method --------------------------------------------------------


def test_3_design_references_explicit_method():
    pool, plan = _plan()
    entry = plan.entries[0]
    method = make_experimental_method("tensile_test", parameters={"strain_rate": 5.0})
    design = assemble_experimental_design(plan, methods={entry.candidate_id: method})
    e = next(e for e in design.entries if e.plan_entry.candidate_id == entry.candidate_id)
    assert e.method is method
    assert e.method_status == METHOD_SPECIFIED


# -- 4. unspecified method remains explicit -------------------------------------------------------------


def test_4_unspecified_method_remains_explicit():
    pool, plan = _plan()
    design = assemble_experimental_design(plan)  # no methods supplied at all
    for e in design.entries:
        assert e.method is None
        assert e.method_status == METHOD_UNSPECIFIED


# -- 5. method information survives design assembly ------------------------------------------------------


def test_5_method_survives_design_assembly():
    pool, plan = _plan()
    entry = plan.entries[0]
    method = make_experimental_method("tensile_test", parameters={"strain_rate": 5.0, "grip": "wedge"})
    design = assemble_experimental_design(plan, methods={entry.candidate_id: method})
    e = next(e for e in design.entries if e.plan_entry.candidate_id == entry.candidate_id)
    assert e.method.kind == "tensile_test"
    assert dict(e.method.parameters) == {"strain_rate": 5.0, "grip": "wedge"}
    assert e.method.id == method.id


# -- 6. input immutability --------------------------------------------------------------------------------


def test_6_input_immutability():
    pool, plan = _plan()
    entry = plan.entries[0]
    method = make_experimental_method("tensile_test")
    before_plan = repr(plan)
    fingerprint_before = pool.fingerprint()
    assemble_experimental_design(plan, methods={entry.candidate_id: method})
    assert repr(plan) == before_plan
    assert pool.fingerprint() == fingerprint_before
