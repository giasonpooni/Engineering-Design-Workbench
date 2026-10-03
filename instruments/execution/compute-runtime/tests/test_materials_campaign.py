"""Phase 43: materials.campaign -- small focused test set over a single
compact fixture (build-more-test-less development mode). Covers exactly
the six required invariants, not an exhaustive matrix.
"""

from evidence.admission import (
    admit_claimed_relationship, admit_document, admit_observation, admit_record, admit_referent,
)
from evidence.pool import EvidencePool
from evidence.types import (
    make_claimed_relationship, make_document, make_observation, make_record, make_referent, make_source,
)
from materials.audit import audit_program
from materials.campaign import (
    INCOMPLETE, PLANNED, READY, assemble_experimental_campaign,
)
from materials.candidates import generate_candidates
from materials.decision import make_criterion, evaluate_program
from materials.design import assemble_experimental_design
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


# -- 1. design entries are preserved -------------------------------------------------------------------


def test_1_design_entries_preserved():
    pool, plan = _plan()
    design = assemble_experimental_design(plan)
    campaign = assemble_experimental_campaign(design)
    assert {e.candidate_id for e in campaign.entries} == {pe.candidate_id for pe in plan.entries}
    for e in campaign.entries:
        assert e.design_entry.plan_entry.candidate_id == e.candidate_id


# -- 2. incomplete designs remain explicitly incomplete -------------------------------------------------


def test_2_incomplete_designs_remain_explicitly_incomplete():
    pool, plan = _plan()
    design = assemble_experimental_design(plan)  # no method, no parameters supplied at all
    campaign = assemble_experimental_campaign(design)
    assert all(e.readiness == INCOMPLETE for e in campaign.entries)
    assert all(e.execution_state == PLANNED for e in campaign.entries)

    # even WITH a method, an outstanding unspecified parameter keeps it incomplete
    entry = plan.entries[0]
    method = make_experimental_method("tensile_test")
    design2 = assemble_experimental_design(
        plan, methods={entry.candidate_id: method},
        unspecified_parameter_keys={entry.candidate_id: ("replicate_count",)},
    )
    campaign2 = assemble_experimental_campaign(design2)
    e2 = next(e for e in campaign2.entries if e.candidate_id == entry.candidate_id)
    assert e2.readiness == INCOMPLETE
    assert e2.execution_state == PLANNED


# -- 3. ready/planned distinction is honest -----------------------------------------------------------


def test_3_ready_planned_distinction_is_honest():
    pool, plan = _plan()
    entry = plan.entries[0]
    method = make_experimental_method("tensile_test", parameters={"strain_rate": 5.0})
    design = assemble_experimental_design(plan, methods={entry.candidate_id: method})
    campaign = assemble_experimental_campaign(design)
    e = next(e for e in campaign.entries if e.candidate_id == entry.candidate_id)
    assert e.readiness == READY
    assert e.execution_state == READY
    # assembling a campaign never fabricates execution -- no entry is ever
    # anything other than PLANNED/READY from this constructor.
    assert all(c.execution_state in (PLANNED, READY) for c in campaign.entries)


# -- 4. provenance remains reachable --------------------------------------------------------------------


def test_4_provenance_remains_reachable():
    pool, plan = _plan()
    design = assemble_experimental_design(plan)
    campaign = assemble_experimental_campaign(design)
    entry = campaign.entries[0]
    # ExperimentalCampaignEntry -> ExperimentalDesignEntry -> ExperimentPlanEntry
    # -> CandidateSelection -> CandidateEvaluation -> EvidenceRequirement
    requirement = entry.design_entry.plan_entry.selection.evaluation.targeted_requirements[0]
    assert requirement.formulation.natural_key == "formulation-f1"
    # campaign -> design -> plan -> selection -> evaluations -> candidates
    # -> specification -> gaps -> audit -> decision -> MaterialPropertyAnswer
    property_decision = campaign.design.plan.selection.evaluations.candidates.specification.gaps.audit.decision.formulations[0].properties[0]
    assert property_decision.evidence is not None
    assert len(property_decision.evidence.observed) == 2


# -- 5. deterministic ordering ---------------------------------------------------------------------------


def test_5_deterministic_ordering():
    pool, plan = _plan()
    design = assemble_experimental_design(plan)
    a = assemble_experimental_campaign(design)
    b = assemble_experimental_campaign(design)
    ids_a = [e.candidate_id for e in a.entries]
    ids_b = [e.candidate_id for e in b.entries]
    assert ids_a == ids_b == sorted(ids_a)
    assert a.id == b.id  # deterministic content-derived id when campaign_id omitted


# -- 6. input immutability ----------------------------------------------------------------------------------


def test_6_input_immutability():
    pool, plan = _plan()
    design = assemble_experimental_design(plan)
    before = repr(design)
    fingerprint_before = pool.fingerprint()
    assemble_experimental_campaign(design, campaign_id="Q3-tensile-followup")
    assert repr(design) == before
    assert pool.fingerprint() == fingerprint_before
