"""Phase 45: materials.iteration -- the composable, repeatable feedback
loop. Small focused test set (build-more-test-less), doubling as the
phase's own required demonstration: evidence(t0) -> assessment(t0) ->
new evidence -> evidence(t1) -> assessment(t1), entirely on the existing
pipeline, with no SCOUT change.

New evidence between iterations is admitted with the raw, already-
established evidence API (admit_observation/admit_claimed_relationship)
-- the same sequence `materials.results.admit_experimental_result`
itself performs and Phase 44 already verified correct; re-proving that
bridge here would blur this phase's own focus, which is re-evaluation,
not ingestion.
"""

from evidence.admission import (
    admit_claimed_relationship, admit_document, admit_observation, admit_record, admit_referent,
)
from evidence.pool import EvidencePool
from evidence.types import (
    make_claimed_relationship, make_document, make_observation, make_record, make_referent, make_source,
)
from materials.decision import CONFLICTING_EVIDENCE, FAIL, INCOMPARABLE, PASS, make_criterion
from materials.iteration import reevaluate_program
from materials.program import make_material_program_query
from retrieval.engine import DeterministicRetrievalEngine

ENGINE = DeterministicRetrievalEngine()
TENSILE_CRITERION = make_criterion("tensile_strength", ">=", 80)
VISCOSITY_CRITERION = make_criterion("viscosity", "<=", 950, context={"unit": "mPa.s", "temperature": 25, "temperature_unit": "C"})
CRITERIA = (TENSILE_CRITERION, VISCOSITY_CRITERION)


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

    _add_obs(pool, doc, f1, process, "ts-78", {"property": "tensile_strength", "value": 78, "unit": "MPa"})
    _add_obs(pool, doc, f1, process, "visc-40", {"property": "viscosity", "value": 1120, "unit": "mPa.s", "temperature": 40, "temperature_unit": "C"})

    query = make_material_program_query(["formulation-f1"], "process-std-190c", ("tensile_strength", "viscosity"))
    return pool, doc, process, f1, query


def _add_obs(pool, doc, formulation, process, locator, content):
    rec = make_record(document_id=doc.id, locator=locator, raw_content=locator)
    admit_record(pool, rec)
    pool.put_record(rec)
    obs = make_observation(record_ids=(rec.id,), extraction_method="human_transcription", content=content, confidence=1.0, extracted_at="2026-08-23T01:00:00Z")
    admit_observation(pool, obs)
    pool.put_observation(obs)
    rel = make_claimed_relationship(from_referent_id=formulation.id, to_referent_id=process.id, type="tested_during", observation_id=obs.id, confidence=1.0)
    admit_claimed_relationship(pool, rel)
    pool.put_claimed_relationship(rel)
    return obs


def _property_decision(iteration, property_name):
    return next(pd for pd in iteration.decision.formulations[0].properties if pd.criterion.property == property_name)


# -- 1. initial analysis --------------------------------------------------------------------------


def test_1_initial_analysis():
    pool, doc, process, f1, query = _setup()
    iteration0 = reevaluate_program(pool, ENGINE, query, CRITERIA)
    assert _property_decision(iteration0, "tensile_strength").observed_status == FAIL
    assert _property_decision(iteration0, "viscosity").observed_status == INCOMPARABLE


# -- 2/3/4/5. new evidence admitted -> re-evaluated -> appears -> conflict preserved, not overwritten ---


def test_2_3_4_5_new_comparable_evidence_produces_conflict_not_overwrite():
    pool, doc, process, f1, query = _setup()
    iteration0 = reevaluate_program(pool, ENGINE, query, CRITERIA)
    assert _property_decision(iteration0, "tensile_strength").observed_status == FAIL

    new_obs = _add_obs(pool, doc, f1, process, "ts-84", {"property": "tensile_strength", "value": 84, "unit": "MPa"})
    iteration1 = reevaluate_program(pool, ENGINE, query, CRITERIA)

    tensile_pd = _property_decision(iteration1, "tensile_strength")
    assert tensile_pd.observed_status == CONFLICTING_EVIDENCE
    assert set(tensile_pd.observed_group.values) == {78.0, 84.0}  # both preserved, neither replaced

    tensile_answer = tensile_pd.evidence
    assert {o.id for o in tensile_answer.observed} == {
        o.id for o in tensile_answer.observed if o.content["value"] in (78, 84)
    }
    assert new_obs.id in {o.id for o in tensile_answer.observed}


def test_incomparable_resolved_by_distinct_context_not_by_overwriting():
    """A second, genuinely different case: viscosity starts INCOMPARABLE
    (only a 40C measurement exists, criterion requires 25C). Adding a
    NEW observation under the criterion's own 25C context resolves it to
    a determinate status -- while the original 40C group stays present,
    untouched, as its own separate comparison group."""
    pool, doc, process, f1, query = _setup()
    _add_obs(pool, doc, f1, process, "visc-25", {"property": "viscosity", "value": 900, "unit": "mPa.s", "temperature": 25, "temperature_unit": "C"})
    iteration1 = reevaluate_program(pool, ENGINE, query, CRITERIA)

    visc_pd = _property_decision(iteration1, "viscosity")
    assert visc_pd.observed_status == PASS
    groups = visc_pd.evidence.observed_comparison_groups
    assert len(groups) == 2  # 40C and 25C remain two separate groups
    assert {g.values[0] for g in groups} == {1120.0, 900.0}


# -- 6. historical decision remains unchanged -------------------------------------------------------


def test_6_historical_decision_unchanged():
    pool, doc, process, f1, query = _setup()
    iteration0 = reevaluate_program(pool, ENGINE, query, CRITERIA)
    before = repr(iteration0)

    _add_obs(pool, doc, f1, process, "ts-84", {"property": "tensile_strength", "value": 84, "unit": "MPa"})
    reevaluate_program(pool, ENGINE, query, CRITERIA)  # a new iteration -- must not touch iteration0

    assert repr(iteration0) == before
    assert _property_decision(iteration0, "tensile_strength").observed_status == FAIL


# -- 7. iteration does not mutate the pool -------------------------------------------------------------


def test_7_iteration_does_not_mutate_pool():
    pool, doc, process, f1, query = _setup()
    fingerprint_before = pool.fingerprint()
    reevaluate_program(pool, ENGINE, query, CRITERIA)
    assert pool.fingerprint() == fingerprint_before


# -- 8. deterministic output ------------------------------------------------------------------------------


def test_8_deterministic_output():
    pool, doc, process, f1, query = _setup()
    a = reevaluate_program(pool, ENGINE, query, CRITERIA)
    b = reevaluate_program(pool, ENGINE, query, CRITERIA)
    assert a.evidence_version_id == b.evidence_version_id == pool.fingerprint()
    assert _property_decision(a, "tensile_strength").observed_status == _property_decision(b, "tensile_strength").observed_status
    assert _property_decision(a, "viscosity").observed_status == _property_decision(b, "viscosity").observed_status
    # structural sharing, not duplication, all the way down
    assert a.audit.decision is a.decision
    assert a.gap_analysis.audit is a.audit
    assert a.specification.gaps is a.gap_analysis
