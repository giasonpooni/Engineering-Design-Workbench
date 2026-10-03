"""Phase 33: materials.audit -- diagnostics over an already-computed
ProgramDecision (Phase 32), exercised against the Phase 30/32 workload:
F1 (measurement AND model-independent conflicts), F2 (clean FAIL), F3
(model disagreement over one observation), F4 (clean PASS), F5
(prediction-only), F6 (no process relationship -> insufficient
evidence), plus a dedicated incomparable-condition and missing-property
case.
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
from materials.audit import (
    MEASUREMENT_DISAGREEMENT, MODEL_DISAGREEMENT, audit_program,
)
from materials.decision import (
    CONFLICTING_EVIDENCE, FAIL, INCOMPARABLE, INSUFFICIENT_EVIDENCE, PASS,
    make_criterion, evaluate_program,
)
from materials.program import make_material_program_query, analyze_program
from retrieval.engine import DeterministicRetrievalEngine

ENGINE = DeterministicRetrievalEngine()

TENSILE_CRITERION = make_criterion("tensile_strength", ">=", 80)
MODULUS_CRITERION = make_criterion("modulus", ">=", 2.7)
VISCOSITY_CRITERION = make_criterion("viscosity", "<=", 950, context={"unit": "mPa.s", "temperature": 25, "temperature_unit": "C"})
HARDNESS_CRITERION = make_criterion("hardness", ">=", 50)  # never measured -- missing property


def _base(order="normal"):
    pool = EvidencePool()
    qc_lab = make_source(kind="lab_notebook", name="Internal QC Lab")
    third_party = make_source(kind="external_report", name="Third-Party Test Lab")
    for s in ((qc_lab, third_party) if order == "normal" else (third_party, qc_lab)):
        pool.put_source(s)

    doc = make_document(source_id=qc_lab.id, raw_content="QC panel", retrieval_method="manual_entry", retrieved_at="2026-08-23T00:00:00Z")
    tp_doc = make_document(source_id=third_party.id, raw_content="Third-party verification", retrieval_method="pdf_ingest", retrieved_at="2026-08-23T00:00:00Z")
    for d in (doc, tp_doc):
        admit_document(pool, d)
        pool.put_document(d)

    process_std = make_referent(natural_key="process-std-190c", kind="process")
    formulations = {k: make_referent(natural_key=f"formulation-{k}", kind="formulation") for k in ("f1", "f2", "f3", "f4", "f5", "f6")}
    all_refs = [process_std] + list(formulations.values())
    for ref in (all_refs if order == "normal" else list(reversed(all_refs))):
        admit_referent(pool, ref)
        pool.put_referent(ref)

    return pool, doc, tp_doc, process_std, formulations


def _add_obs(pool, document, formulation, process, locator, content, extracted_at="2026-08-23T00:00:00Z"):
    rec = make_record(document_id=document.id, locator=locator, raw_content=locator)
    admit_record(pool, rec)
    pool.put_record(rec)
    obs = make_observation(record_ids=(rec.id,), extraction_method="human_transcription", content=content, confidence=1.0, extracted_at=extracted_at)
    admit_observation(pool, obs)
    pool.put_observation(obs)
    if process is not None:
        rel = make_claimed_relationship(from_referent_id=formulation.id, to_referent_id=process.id, type="tested_during", observation_id=obs.id, confidence=1.0)
        admit_claimed_relationship(pool, rel)
        pool.put_claimed_relationship(rel)
    return obs


def _add_pred(pool, formulation, obs, method, content, confidence=0.85, derived_at="2026-08-23T01:00:00Z"):
    dv = make_derived_value(derived_from=[obs.id], method=method, content=content, confidence=confidence, derived_at=derived_at)
    admit_derived_value(pool, dv)
    pool.put_derived_value(dv)
    g = make_derived_grounding(derived_value_id=dv.id, referent_ids=[formulation.id])
    admit_derived_grounding(pool, g)
    pool.put_derived_grounding(g)
    return dv


def _workload(order="normal"):
    pool, doc, tp_doc, process_std, f = _base(order)
    obs = {}

    obs["f1_ts_qc"] = _add_obs(pool, doc, f["f1"], process_std, "f1-ts-qc", {"property": "tensile_strength", "value": 82, "unit": "MPa"})
    obs["f1_ts_tp"] = _add_obs(pool, tp_doc, f["f1"], process_std, "f1-ts-tp", {"property": "tensile_strength", "value": 79, "unit": "MPa"}, extracted_at="2026-08-23T00:30:00Z")
    dv_f1_a = _add_pred(pool, f["f1"], obs["f1_ts_qc"], "model:A", {"property": "tensile_strength", "predicted_value": 80, "unit": "MPa"})
    dv_f1_b = _add_pred(pool, f["f1"], obs["f1_ts_tp"], "model:B", {"property": "tensile_strength", "predicted_value": 84, "unit": "MPa"})
    obs["f1_visc40"] = _add_obs(pool, doc, f["f1"], process_std, "f1-visc40", {"property": "viscosity", "value": 1120, "unit": "mPa.s", "temperature": 40, "temperature_unit": "C"})

    obs["f2_ts"] = _add_obs(pool, doc, f["f2"], process_std, "f2-ts", {"property": "tensile_strength", "value": 79, "unit": "MPa"})

    obs["f3_ts"] = _add_obs(pool, doc, f["f3"], process_std, "f3-ts", {"property": "tensile_strength", "value": 86, "unit": "MPa"})
    dv_f3_a = _add_pred(pool, f["f3"], obs["f3_ts"], "model:A", {"property": "tensile_strength", "predicted_value": 84, "unit": "MPa"})
    dv_f3_b = _add_pred(pool, f["f3"], obs["f3_ts"], "model:B", {"property": "tensile_strength", "predicted_value": 89, "unit": "MPa"})

    obs["f4_ts"] = _add_obs(pool, doc, f["f4"], process_std, "f4-ts", {"property": "tensile_strength", "value": 81, "unit": "MPa"})
    obs["f4_mod"] = _add_obs(pool, doc, f["f4"], process_std, "f4-mod", {"property": "modulus", "value": 3.0, "unit": "GPa"})

    obs["f5_seed"] = _add_obs(pool, doc, f["f5"], process_std, "f5-seed", {"property": "modulus", "value": 2.9, "unit": "GPa"})
    dv_f5 = _add_pred(pool, f["f5"], obs["f5_seed"], "model:A", {"property": "tensile_strength", "predicted_value": 82, "unit": "MPa"})

    obs["f6_ts"] = _add_obs(pool, doc, f["f6"], None, "f6-ts", {"property": "tensile_strength", "value": 90, "unit": "MPa"})

    return pool, f, process_std, obs, dict(dv_f1_a=dv_f1_a, dv_f1_b=dv_f1_b, dv_f3_a=dv_f3_a, dv_f3_b=dv_f3_b, dv_f5=dv_f5)


def _audit_for(pool, formulation_keys, criteria, properties=None):
    if properties is None:
        properties = tuple(sorted({c.property for c in criteria}))
    query = make_material_program_query([f"formulation-{k}" for k in formulation_keys], "process-std-190c", properties)
    program_answer = analyze_program(pool, ENGINE, query)
    decision = evaluate_program(program_answer, criteria)
    return audit_program(decision)


def _find(audit, formulation_key, property_name):
    fd = next(fd for fd in audit.formulations if fd.formulation.natural_key == f"formulation-{formulation_key}")
    return next(pa for pa in fd.properties if pa.criterion.property == property_name)


# -- 1. all-PASS formulation --------------------------------------------------------------


def test_1_all_pass_formulation():
    pool, f, process_std, obs, dv = _workload()
    audit = _audit_for(pool, ["f4"], (TENSILE_CRITERION, MODULUS_CRITERION))
    fd = audit.formulations[0]
    assert fd.summary.observed_status_counts[PASS] == 2
    assert all(v == 0 for k, v in fd.summary.observed_status_counts.items() if k != PASS)


# -- 2. FAIL decision -----------------------------------------------------------------------


def test_2_fail_decision():
    pool, f, process_std, obs, dv = _workload()
    pa = _find(_audit_for(pool, ["f2"], (TENSILE_CRITERION,)), "f2", "tensile_strength")
    assert pa.decision.observed_status == FAIL
    assert pa.observed_reason is None  # PASS/FAIL are self-explaining via the matched group


# -- 3. observed conflict --------------------------------------------------------------------


def test_3_observed_conflict():
    pool, f, process_std, obs, dv = _workload()
    pa = _find(_audit_for(pool, ["f1"], (TENSILE_CRITERION,)), "f1", "tensile_strength")
    assert pa.decision.observed_status == CONFLICTING_EVIDENCE


# -- 4. predicted conflict -------------------------------------------------------------------


def test_4_predicted_conflict():
    pool2, doc2, tp2, process2, f2 = _base()
    seed = _add_obs(pool2, doc2, f2["f1"], process2, "seed", {"property": "tensile_strength", "value": 82, "unit": "MPa"})
    _add_pred(pool2, f2["f1"], seed, "model:A", {"property": "tensile_strength", "predicted_value": 78, "unit": "MPa"})
    _add_pred(pool2, f2["f1"], seed, "model:B", {"property": "tensile_strength", "predicted_value": 85, "unit": "MPa"})
    pa = _find(_audit_for(pool2, ["f1"], (TENSILE_CRITERION,)), "f1", "tensile_strength")
    assert pa.decision.predicted_status == CONFLICTING_EVIDENCE
    assert pa.predicted_conflict is not None
    assert pa.predicted_conflict.kind == MODEL_DISAGREEMENT  # both from the same seed observation


# -- 5. observed conflict + predicted PASS ----------------------------------------------------


def test_5_observed_conflict_predicted_pass_stay_separate():
    pool, f, process_std, obs, dv = _workload()
    pa = _find(_audit_for(pool, ["f1"], (TENSILE_CRITERION,)), "f1", "tensile_strength")
    assert pa.decision.observed_status == CONFLICTING_EVIDENCE
    assert pa.decision.predicted_status == PASS  # 80 and 84, both >= 80
    assert pa.predicted_conflict is None  # no conflict to diagnose


# -- 6. model disagreement over one observation ------------------------------------------------


def test_6_model_disagreement_over_one_observation():
    pool, f, process_std, obs, dv = _workload()
    pa = _find(_audit_for(pool, ["f3"], (TENSILE_CRITERION,)), "f3", "tensile_strength")
    assert pa.decision.predicted_status == PASS  # 84 and 89, both >= 80 -- no conflict here
    # Force a conflicting scenario reusing F3's shared-observation shape:
    query = make_material_program_query(["formulation-f3"], "process-std-190c", ("tensile_strength",))
    strict = make_criterion("tensile_strength", ">=", 85)
    program_answer = analyze_program(pool, ENGINE, query)
    decision = evaluate_program(program_answer, (strict,))
    audit = audit_program(decision)
    pa2 = audit.formulations[0].properties[0]
    assert pa2.decision.predicted_status == CONFLICTING_EVIDENCE  # 84 fails, 89 passes >=85
    assert pa2.predicted_conflict.kind == MODEL_DISAGREEMENT
    assert pa2.predicted_conflict.provenance_observation_id_sets[0] == pa2.predicted_conflict.provenance_observation_id_sets[1]
    assert pa2.predicted_conflict.provenance_observation_id_sets[0] == (obs["f3_ts"].id,)


# -- 7. measurement disagreement over multiple observations -----------------------------------


def test_7_measurement_disagreement_over_different_observations():
    pool2, doc2, tp2, process2, f2 = _base()
    obs_a = _add_obs(pool2, doc2, f2["f1"], process2, "a", {"property": "tensile_strength", "value": 82, "unit": "MPa"})
    obs_b = _add_obs(pool2, tp2, f2["f1"], process2, "b", {"property": "tensile_strength", "value": 79, "unit": "MPa"})
    _add_pred(pool2, f2["f1"], obs_a, "model:A", {"property": "tensile_strength", "predicted_value": 90, "unit": "MPa"})
    _add_pred(pool2, f2["f1"], obs_b, "model:B", {"property": "tensile_strength", "predicted_value": 70, "unit": "MPa"})
    pa = _find(_audit_for(pool2, ["f1"], (TENSILE_CRITERION,)), "f1", "tensile_strength")
    assert pa.decision.predicted_status == CONFLICTING_EVIDENCE
    assert pa.predicted_conflict.kind == MEASUREMENT_DISAGREEMENT
    sets = pa.predicted_conflict.provenance_observation_id_sets
    assert set(sets[0]).isdisjoint(set(sets[1]))


# -- 8. insufficient evidence -----------------------------------------------------------------


def test_8_insufficient_evidence():
    pool, f, process_std, obs, dv = _workload()
    pa = _find(_audit_for(pool, ["f5"], (TENSILE_CRITERION,)), "f5", "tensile_strength")
    assert pa.decision.observed_status == INSUFFICIENT_EVIDENCE
    assert pa.observed_reason == "no evidence exists for property 'tensile_strength'"
    assert pa.decision.predicted_status == PASS


# -- 9. incomparable evidence -------------------------------------------------------------------


def test_9_incomparable_evidence():
    pool, f, process_std, obs, dv = _workload()
    pa = _find(_audit_for(pool, ["f1"], (VISCOSITY_CRITERION,)), "f1", "viscosity")
    assert pa.decision.observed_status == INCOMPARABLE
    assert "none match criterion context" in pa.observed_reason
    assert len(pa.observed_available_contexts) == 1
    assert pa.observed_available_contexts[0]["temperature"] == 40  # available, but not @25C


# -- 10. missing property ------------------------------------------------------------------------


def test_10_missing_property():
    pool, f, process_std, obs, dv = _workload()
    audit = _audit_for(pool, ["f1"], (HARDNESS_CRITERION,), properties=("tensile_strength",))
    pa = audit.formulations[0].properties[0]
    assert pa.decision.observed_status == INSUFFICIENT_EVIDENCE
    assert pa.observed_reason == "property 'hardness' was not included in the program query"
    assert pa.decision.evidence is None


# -- 11. provenance preservation -------------------------------------------------------------------


def test_11_provenance_preserved_through_audit():
    pool, f, process_std, obs, dv = _workload()
    pa = _find(_audit_for(pool, ["f1"], (TENSILE_CRITERION,)), "f1", "tensile_strength")
    by_value = {gp.derived_value.content["predicted_value"]: gp for gp in pa.decision.evidence.predictions}
    assert by_value[80].provenance.observation_ids == (obs["f1_ts_qc"].id,)
    assert by_value[84].provenance.observation_ids == (obs["f1_ts_tp"].id,)


# -- 12-13. determinism -----------------------------------------------------------------------------


def test_12_13_deterministic_ordering_and_insertion_order_independence():
    pool_a, f_a, ps_a, obs_a, dv_a = _workload("normal")
    pool_b, f_b, ps_b, obs_b, dv_b = _workload("shuffled")

    audit_a = _audit_for(pool_a, ["f1", "f2", "f3", "f4"], (TENSILE_CRITERION,))
    audit_b = _audit_for(pool_b, ["f1", "f2", "f3", "f4"], (TENSILE_CRITERION,))

    keys_a = [fd.formulation.natural_key for fd in audit_a.formulations]
    keys_b = [fd.formulation.natural_key for fd in audit_b.formulations]
    assert keys_a == keys_b

    for fda, fdb in zip(audit_a.formulations, audit_b.formulations):
        assert fda.summary.observed_status_counts == fdb.summary.observed_status_counts
        for pa_a, pa_b in zip(fda.properties, fdb.properties):
            assert pa_a.decision.observed_status == pa_b.decision.observed_status
            assert pa_a.decision.predicted_status == pa_b.decision.predicted_status
            if pa_a.predicted_conflict is not None:
                assert pa_a.predicted_conflict.kind == pa_b.predicted_conflict.kind


# -- 14. PYTHONHASHSEED determinism -----------------------------------------------------------------


def test_14_pythonhashseed_determinism():
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    script = (
        "from evidence.admission import admit_claimed_relationship, admit_derived_grounding, "
        "admit_derived_value, admit_document, admit_observation, admit_record, admit_referent\n"
        "from evidence.pool import EvidencePool\n"
        "from evidence.types import make_claimed_relationship, make_derived_grounding, "
        "make_derived_value, make_document, make_observation, make_record, make_referent, make_source\n"
        "from materials.audit import audit_program\n"
        "from materials.decision import make_criterion, evaluate_program\n"
        "from materials.program import make_material_program_query, analyze_program\n"
        "from retrieval.engine import DeterministicRetrievalEngine\n"
        "pool = EvidencePool()\n"
        "source = make_source(kind='lab_notebook', name='QC')\n"
        "pool.put_source(source)\n"
        "doc = make_document(source_id=source.id, raw_content='panel', retrieval_method='m', retrieved_at='t')\n"
        "pool.put_document(doc)\n"
        "process = make_referent(natural_key='process-std-190c', kind='process')\n"
        "pool.put_referent(process)\n"
        "f1 = make_referent(natural_key='formulation-f1', kind='formulation')\n"
        "pool.put_referent(f1)\n"
        "rec1 = make_record(document_id=doc.id, locator='r1', raw_content='82')\n"
        "pool.put_record(rec1)\n"
        "rec2 = make_record(document_id=doc.id, locator='r2', raw_content='79')\n"
        "pool.put_record(rec2)\n"
        "obs1 = make_observation(record_ids=(rec1.id,), extraction_method='human_transcription', "
        "content={'property': 'tensile_strength', 'value': 82, 'unit': 'MPa'}, confidence=1.0, extracted_at='t')\n"
        "pool.put_observation(obs1)\n"
        "obs2 = make_observation(record_ids=(rec2.id,), extraction_method='human_transcription', "
        "content={'property': 'tensile_strength', 'value': 79, 'unit': 'MPa'}, confidence=1.0, extracted_at='t2')\n"
        "pool.put_observation(obs2)\n"
        "rel1 = make_claimed_relationship(from_referent_id=f1.id, to_referent_id=process.id, "
        "type='tested_during', observation_id=obs1.id, confidence=1.0)\n"
        "pool.put_claimed_relationship(rel1)\n"
        "rel2 = make_claimed_relationship(from_referent_id=f1.id, to_referent_id=process.id, "
        "type='tested_during', observation_id=obs2.id, confidence=1.0)\n"
        "pool.put_claimed_relationship(rel2)\n"
        "dv_a = make_derived_value(derived_from=[obs1.id], method='model:A', "
        "content={'property': 'tensile_strength', 'predicted_value': 90, 'unit': 'MPa'}, confidence=0.85, derived_at='t')\n"
        "pool.put_derived_value(dv_a)\n"
        "dv_b = make_derived_value(derived_from=[obs2.id], method='model:B', "
        "content={'property': 'tensile_strength', 'predicted_value': 70, 'unit': 'MPa'}, confidence=0.85, derived_at='t')\n"
        "pool.put_derived_value(dv_b)\n"
        "g_a = make_derived_grounding(derived_value_id=dv_a.id, referent_ids=[f1.id])\n"
        "pool.put_derived_grounding(g_a)\n"
        "g_b = make_derived_grounding(derived_value_id=dv_b.id, referent_ids=[f1.id])\n"
        "pool.put_derived_grounding(g_b)\n"
        "engine = DeterministicRetrievalEngine()\n"
        "query = make_material_program_query(['formulation-f1'], 'process-std-190c', ['tensile_strength'])\n"
        "program_answer = analyze_program(pool, engine, query)\n"
        "criterion = make_criterion('tensile_strength', '>=', 80)\n"
        "decision = evaluate_program(program_answer, (criterion,))\n"
        "audit = audit_program(decision)\n"
        "pa = audit.formulations[0].properties[0]\n"
        "print(pa.decision.predicted_status, pa.predicted_conflict.kind if pa.predicted_conflict else None)\n"
    )
    outputs = set()
    for seed in ("0", "1", "12345"):
        proc = subprocess.run(
            [sys.executable, "-c", script],
            cwd=repo_root,
            env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode == 0, proc.stderr
        outputs.add(proc.stdout)
    assert len(outputs) == 1, f"audit_program differed across PYTHONHASHSEED values: {outputs}"


# -- 15. no ranking/scoring/recommendation fields ------------------------------------------------


def test_15_no_ranking_score_or_winner_field():
    pool, f, process_std, obs, dv = _workload()
    audit = _audit_for(pool, ["f1", "f2"], (TENSILE_CRITERION,))
    for forbidden in ("score", "rank", "ranking", "winner", "best", "recommended", "optimal"):
        assert not hasattr(audit, forbidden)
        for fd in audit.formulations:
            assert not hasattr(fd, forbidden)
            assert not hasattr(fd.summary, forbidden)
            for pa in fd.properties:
                assert not hasattr(pa, forbidden)


# -- 16. audit does not mutate its input ------------------------------------------------------------


def test_16_audit_does_not_mutate_program_decision():
    pool, f, process_std, obs, dv = _workload()
    query = make_material_program_query(["formulation-f1"], "process-std-190c", ("tensile_strength",))
    program_answer = analyze_program(pool, ENGINE, query)
    decision = evaluate_program(program_answer, (TENSILE_CRITERION,))
    before = repr(decision)
    audit_program(decision)
    assert repr(decision) == before
    assert audit_program(decision).decision is decision  # same object, not copied/replaced


# -- 17/18. audit does not call retrieval / works on an already-created ProgramDecision -------------


def test_17_18_audit_never_touches_pool_or_engine():
    pool, f, process_std, obs, dv = _workload()
    query = make_material_program_query(["formulation-f1"], "process-std-190c", ("tensile_strength",))
    program_answer = analyze_program(pool, ENGINE, query)
    decision = evaluate_program(program_answer, (TENSILE_CRITERION,))
    fingerprint_before = pool.fingerprint()
    audit = audit_program(decision)  # single argument -- no pool, no engine
    assert pool.fingerprint() == fingerprint_before
    assert audit.formulations[0].formulation.natural_key == "formulation-f1"
