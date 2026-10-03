"""Phase 44: materials.results -- the first write path in this pipeline.
Small focused test set over a single compact fixture (build-more-
test-less development mode), centered on the one question that matters:
does newly admitted evidence actually flow back through the existing
retrieval/materials-analysis pipeline.
"""

from evidence.admission import (
    admit_claimed_relationship, admit_document, admit_observation, admit_record, admit_referent,
)
from evidence.pool import EvidencePool
from evidence.types import (
    make_claimed_relationship, make_document, make_observation, make_record, make_referent, make_source,
)
from materials.analysis import MaterialQuestion, analyze
from materials.audit import audit_program
from materials.campaign import assemble_experimental_campaign
from materials.candidates import generate_candidates
from materials.decision import make_criterion, evaluate_program
from materials.design import assemble_experimental_design
from materials.evaluation import evaluate_candidates
from materials.experiment import analyze_experiment_gaps
from materials.plan import assemble_experiment_plan
from materials.program import make_material_program_query, analyze_program
from materials.results import admit_experimental_result, make_experimental_result
from materials.selection import SelectionPolicy, select_candidates
from materials.specification import specify_experiment_requirements
from retrieval.engine import DeterministicRetrievalEngine

ENGINE = DeterministicRetrievalEngine()
TENSILE_CRITERION = make_criterion("tensile_strength", ">=", 80)

ALLOW_ALL = SelectionPolicy(
    allowed_action_classes=None, allow_already_represented_context=True,
    allow_redundant=True, allow_not_determinable_feasibility=True, max_selected=None,
)


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
    plan = assemble_experiment_plan(selection)
    design = assemble_experimental_design(plan)
    campaign = assemble_experimental_campaign(design)
    entry = next(e for e in campaign.entries if e.action_class == "measurement:repeat")
    return pool, doc, campaign, entry


def _new_record(pool, doc, locator, raw_content):
    rec = make_record(document_id=doc.id, locator=locator, raw_content=raw_content)
    admit_record(pool, rec)
    pool.put_record(rec)
    return rec


# -- 1/2. result construction is deterministic + identity is stable ----------------------------------


def test_1_2_result_construction_deterministic_and_identity_stable():
    pool, doc, campaign, entry = _setup()
    rec = _new_record(pool, doc, "ts-c", "ts-c")
    a = make_experimental_result(
        campaign, entry, content={"property": "tensile_strength", "value": 84, "unit": "MPa"},
        record_id=rec.id, extracted_at="2026-08-23T02:00:00Z",
    extraction_method="measurement:campaign_execution")
    b = make_experimental_result(
        campaign, entry, content={"unit": "MPa", "property": "tensile_strength", "value": 84},  # different key order
        record_id=rec.id, extracted_at="2026-08-23T02:00:00Z",
    extraction_method="measurement:campaign_execution")
    c = make_experimental_result(
        campaign, entry, content={"property": "tensile_strength", "value": 90, "unit": "MPa"},  # different value
        record_id=rec.id, extracted_at="2026-08-23T02:00:00Z",
    extraction_method="measurement:campaign_execution")
    assert a.id == b.id
    assert a.id != c.id


# -- 3. result -> Observation mapping is correct --------------------------------------------------------


def test_3_result_to_observation_mapping_is_correct():
    pool, doc, campaign, entry = _setup()
    rec = _new_record(pool, doc, "ts-c", "ts-c")
    result = make_experimental_result(
        campaign, entry, content={"property": "tensile_strength", "value": 84, "unit": "MPa"},
        record_id=rec.id, extracted_at="2026-08-23T02:00:00Z",
    extraction_method="measurement:campaign_execution")
    outcome = admit_experimental_result(pool, result, confidence=1.0)
    assert not isinstance(outcome, list)
    observation, relationship = outcome
    assert dict(observation.content) == {"property": "tensile_strength", "value": 84, "unit": "MPa"}
    assert observation.record_ids == (rec.id,)
    assert relationship.from_referent_id == entry.formulation.id
    assert relationship.observation_id == observation.id


# -- 4. admission uses the existing EvidencePool API -------------------------------------------------------


def test_4_admission_uses_existing_pool_api():
    pool, doc, campaign, entry = _setup()
    rec = _new_record(pool, doc, "ts-c", "ts-c")
    result = make_experimental_result(
        campaign, entry, content={"property": "tensile_strength", "value": 84, "unit": "MPa"},
        record_id=rec.id, extracted_at="2026-08-23T02:00:00Z",
    extraction_method="measurement:campaign_execution")
    fingerprint_before = pool.fingerprint()
    outcome = admit_experimental_result(pool, result, confidence=1.0)
    observation, relationship = outcome
    assert pool.fingerprint() != fingerprint_before  # the pool really did change
    assert pool.get_observation(observation.id) is observation  # reachable via the existing public getter
    assert relationship.id in {r.id for r in pool.all_claimed_relationships()}  # no get_claimed_relationship exists


# -- 5/6. newly admitted evidence is retrievable AND materials.analyze() sees it -----------------------------


def test_5_6_new_evidence_retrievable_and_seen_by_analyze():
    pool, doc, campaign, entry = _setup()
    before = analyze(pool, ENGINE, MaterialQuestion("formulation-f1", "tensile_strength"))
    assert len(before.observed) == 2

    rec = _new_record(pool, doc, "ts-c", "ts-c")
    result = make_experimental_result(
        campaign, entry, content={"property": "tensile_strength", "value": 84, "unit": "MPa"},
        record_id=rec.id, extracted_at="2026-08-23T02:00:00Z",
    extraction_method="measurement:campaign_execution")
    outcome = admit_experimental_result(pool, result, confidence=1.0)
    observation, _ = outcome

    after = analyze(pool, ENGINE, MaterialQuestion("formulation-f1", "tensile_strength"))
    assert len(after.observed) == 3
    assert observation.id in {o.id for o in after.observed}
    assert after.observed_comparison_groups[0].values == (79.0, 82.0, 84.0) or (
        sorted(v for g in after.observed_comparison_groups for v in g.values) == [79.0, 82.0, 84.0]
    )


# -- 7. original campaign/design objects are not mutated ------------------------------------------------------


def test_7_campaign_and_design_not_mutated():
    pool, doc, campaign, entry = _setup()
    rec = _new_record(pool, doc, "ts-c", "ts-c")
    result = make_experimental_result(
        campaign, entry, content={"property": "tensile_strength", "value": 84, "unit": "MPa"},
        record_id=rec.id, extracted_at="2026-08-23T02:00:00Z",
    extraction_method="measurement:campaign_execution")
    before_campaign = repr(campaign)
    admit_experimental_result(pool, result, confidence=1.0)
    assert repr(campaign) == before_campaign
