"""Phase 32: materials.decision -- the explicit engineering-decision
layer over materials.program (Phase 31), exercised against the Phase
30 workload's actual criteria: tensile_strength >= 80 MPa,
modulus >= 2.7 GPa, viscosity <= 950 mPa.s @ 25C.
"""

import pytest

from evidence.admission import (
    admit_claimed_relationship, admit_derived_grounding, admit_derived_value,
    admit_document, admit_observation, admit_record, admit_referent,
)
from evidence.pool import EvidencePool
from evidence.types import (
    make_claimed_relationship, make_derived_grounding, make_derived_value,
    make_document, make_observation, make_record, make_referent, make_source,
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


def _phase30_pool(order="normal"):
    """Exact Phase 30 scenario: F1 conflicting tensile observations AND
    conflicting predictions (from different observations); F2 clean;
    F3 conflicting predictions from the SAME observation (model
    disagreement); F4 clean; plus F1's viscosity condition-dependence."""
    pool, doc, tp_doc, process_std, f = _base(order)

    obs = {}
    obs["f1_ts_qc"] = _add_obs(pool, doc, f["f1"], process_std, "f1-ts-qc", {"property": "tensile_strength", "value": 82, "unit": "MPa"})
    obs["f1_ts_tp"] = _add_obs(pool, tp_doc, f["f1"], process_std, "f1-ts-tp", {"property": "tensile_strength", "value": 79, "unit": "MPa"}, extracted_at="2026-08-23T00:30:00Z")
    dv_f1_a = _add_pred(pool, f["f1"], obs["f1_ts_qc"], "model:tensile_predictor_A", {"property": "tensile_strength", "predicted_value": 80, "unit": "MPa"})
    dv_f1_b = _add_pred(pool, f["f1"], obs["f1_ts_tp"], "model:tensile_predictor_B", {"property": "tensile_strength", "predicted_value": 84, "unit": "MPa"})
    obs["f1_mod"] = _add_obs(pool, doc, f["f1"], process_std, "f1-mod", {"property": "modulus", "value": 2.8, "unit": "GPa"})
    obs["f1_visc25"] = _add_obs(pool, doc, f["f1"], process_std, "f1-visc25", {"property": "viscosity", "value": 850, "unit": "mPa.s", "temperature": 25, "temperature_unit": "C"})
    obs["f1_visc40"] = _add_obs(pool, doc, f["f1"], process_std, "f1-visc40", {"property": "viscosity", "value": 1120, "unit": "mPa.s", "temperature": 40, "temperature_unit": "C"})

    obs["f2_ts"] = _add_obs(pool, doc, f["f2"], process_std, "f2-ts", {"property": "tensile_strength", "value": 79, "unit": "MPa"})
    obs["f2_mod"] = _add_obs(pool, doc, f["f2"], process_std, "f2-mod", {"property": "modulus", "value": 3.1, "unit": "GPa"})
    obs["f2_visc25"] = _add_obs(pool, doc, f["f2"], process_std, "f2-visc25", {"property": "viscosity", "value": 910, "unit": "mPa.s", "temperature": 25, "temperature_unit": "C"})

    obs["f3_ts"] = _add_obs(pool, doc, f["f3"], process_std, "f3-ts", {"property": "tensile_strength", "value": 86, "unit": "MPa"})
    dv_f3_a = _add_pred(pool, f["f3"], obs["f3_ts"], "model:tensile_predictor_A", {"property": "tensile_strength", "predicted_value": 84, "unit": "MPa"})
    dv_f3_b = _add_pred(pool, f["f3"], obs["f3_ts"], "model:tensile_predictor_B", {"property": "tensile_strength", "predicted_value": 89, "unit": "MPa"})

    obs["f4_ts"] = _add_obs(pool, doc, f["f4"], process_std, "f4-ts", {"property": "tensile_strength", "value": 81, "unit": "MPa"})

    # F5: prediction only, no observation of its own retrieval path beyond a seed obs.
    obs["f5_ts_seed"] = _add_obs(pool, doc, f["f5"], process_std, "f5-ts-seed", {"property": "modulus", "value": 3.0, "unit": "GPa"})
    dv_f5 = _add_pred(pool, f["f5"], obs["f5_ts_seed"], "model:tensile_predictor_A", {"property": "tensile_strength", "predicted_value": 82, "unit": "MPa"})

    # F6: no process relationship at all.
    obs["f6_ts"] = _add_obs(pool, doc, f["f6"], None, "f6-ts", {"property": "tensile_strength", "value": 90, "unit": "MPa"})

    return pool, f, process_std, obs, dict(dv_f1_a=dv_f1_a, dv_f1_b=dv_f1_b, dv_f3_a=dv_f3_a, dv_f3_b=dv_f3_b, dv_f5=dv_f5)


def _decision_for(pool, formulation_keys, criteria, properties=None):
    if properties is None:
        properties = tuple(sorted({c.property for c in criteria}))
    query = make_material_program_query([f"formulation-{k}" for k in formulation_keys], "process-std-190c", properties)
    program_answer = analyze_program(pool, ENGINE, query)
    return evaluate_program(program_answer, criteria)


# -- 1-5: PASS / FAIL / conflicting -----------------------------------------------------


def test_1_single_observation_pass():
    pool, f, process_std, obs, dv = _phase30_pool()
    decision = _decision_for(pool, ["f4"], (TENSILE_CRITERION,))
    pd = decision.formulations[0].properties[0]
    assert pd.observed_status == PASS


def test_2_single_observation_fail():
    pool, f, process_std, obs, dv = _phase30_pool()
    decision = _decision_for(pool, ["f2"], (TENSILE_CRITERION,))
    pd = decision.formulations[0].properties[0]
    assert pd.observed_status == FAIL


def test_3_conflicting_observations():
    pool, f, process_std, obs, dv = _phase30_pool()
    decision = _decision_for(pool, ["f1"], (TENSILE_CRITERION,))
    pd = decision.formulations[0].properties[0]
    assert pd.observed_status == CONFLICTING_EVIDENCE


def test_4_all_observations_pass():
    pool, f, process_std, obs, dv = _phase30_pool()
    decision = _decision_for(pool, ["f3"], (TENSILE_CRITERION,))
    pd = decision.formulations[0].properties[0]
    assert pd.observed_status == PASS  # single 86 MPa observation, unambiguous


def test_5_all_observations_fail():
    pool, f, process_std, obs, dv = _phase30_pool()
    decision = _decision_for(pool, ["f2"], (TENSILE_CRITERION,))
    pd = decision.formulations[0].properties[0]
    assert pd.observed_status == FAIL


# -- 6-9: predictions -------------------------------------------------------------------


def test_6_prediction_only_evidence():
    pool, f, process_std, obs, dv = _phase30_pool()
    decision = _decision_for(pool, ["f5"], (TENSILE_CRITERION,))
    pd = decision.formulations[0].properties[0]
    assert pd.observed_status == INSUFFICIENT_EVIDENCE  # no tensile OBSERVATION for f5
    assert pd.predicted_status == PASS  # 82 MPa predicted


def test_7_observed_and_predictions_distinct():
    """F1's observations straddle the threshold (82 pass, 79 fail) while
    BOTH of its predictions independently satisfy it (80 and 84, each
    >= 80) -- the two statuses must be reported separately, not
    collapsed into one combined verdict."""
    pool, f, process_std, obs, dv = _phase30_pool()
    decision = _decision_for(pool, ["f1"], (TENSILE_CRITERION,))
    pd = decision.formulations[0].properties[0]
    assert pd.observed_status == CONFLICTING_EVIDENCE
    assert pd.predicted_status == PASS


def test_8_conflicting_predictions():
    pool, f, process_std, obs, dv = _phase30_pool()
    decision = _decision_for(pool, ["f3"], (TENSILE_CRITERION,))
    pd = decision.formulations[0].properties[0]
    assert pd.predicted_status == PASS  # 84 and 89 both >= 80


def test_9_predictions_straddling_threshold():
    pool, f, process_std, obs, dv = _phase30_pool()
    # F1's predictions are 80 (pass) and 84 (pass) from different obs -- not straddling.
    # Build a dedicated straddling case: 78 vs 85 against >=80.
    pool2, doc2, tp2, process2, f2 = _base()
    obs_seed = _add_obs(pool2, doc2, f2["f1"], process2, "seed", {"property": "tensile_strength", "value": 82, "unit": "MPa"})
    _add_pred(pool2, f2["f1"], obs_seed, "model:A", {"property": "tensile_strength", "predicted_value": 78, "unit": "MPa"})
    _add_pred(pool2, f2["f1"], obs_seed, "model:B", {"property": "tensile_strength", "predicted_value": 85, "unit": "MPa"})
    decision = _decision_for(pool2, ["f1"], (TENSILE_CRITERION,))
    pd = decision.formulations[0].properties[0]
    assert pd.predicted_status == CONFLICTING_EVIDENCE


# -- 10-11: comparability -----------------------------------------------------------------


def test_10_condition_matched_evidence_is_evaluable():
    pool, f, process_std, obs, dv = _phase30_pool()
    decision = _decision_for(pool, ["f1"], (VISCOSITY_CRITERION,))
    pd = decision.formulations[0].properties[0]
    assert pd.observed_status == PASS  # 850 mPa.s @ 25C <= 950
    assert pd.observed_group is not None
    assert pd.observed_group.values == (850.0,)


def test_11_condition_mismatched_evidence_is_incomparable():
    """F1 also has a 40C viscosity reading -- the @25C criterion must
    not be evaluated against it, and if ONLY the 40C reading existed,
    the criterion would be reported INCOMPARABLE, not silently passed
    or failed."""
    pool2, doc2, tp2, process2, f2 = _base()
    _add_obs(pool2, doc2, f2["f1"], process2, "v40", {"property": "viscosity", "value": 1120, "unit": "mPa.s", "temperature": 40, "temperature_unit": "C"})
    decision = _decision_for(pool2, ["f1"], (VISCOSITY_CRITERION,))
    pd = decision.formulations[0].properties[0]
    assert pd.observed_status == INCOMPARABLE
    assert pd.observed_group is None


# -- 12-14: missing / insufficient ---------------------------------------------------------


def test_12_missing_property():
    pool, f, process_std, obs, dv = _phase30_pool()
    # Request only tensile_strength in the program query -- modulus criterion has no evidence available.
    decision = _decision_for(pool, ["f1"], (MODULUS_CRITERION,), properties=("tensile_strength",))
    pd = decision.formulations[0].properties[0]
    assert pd.observed_status == INSUFFICIENT_EVIDENCE
    assert pd.predicted_status == INSUFFICIENT_EVIDENCE
    assert pd.evidence is None


def test_13_missing_formulation_raises_key_error():
    pool, f, process_std, obs, dv = _phase30_pool()
    with pytest.raises(KeyError):
        _decision_for(pool, ["does-not-exist"], (TENSILE_CRITERION,))


def test_14_no_comparable_evidence_at_all():
    pool, f, process_std, obs, dv = _phase30_pool()
    decision = _decision_for(pool, ["f1"], (make_criterion("hardness", ">=", 50),))
    pd = decision.formulations[0].properties[0]
    assert pd.observed_status == INSUFFICIENT_EVIDENCE  # property never measured for F1 at all


# -- 15-17: provenance / model vs measurement disagreement ------------------------------------


def test_15_provenance_preserved():
    pool, f, process_std, obs, dv = _phase30_pool()
    decision = _decision_for(pool, ["f1"], (TENSILE_CRITERION,))
    pd = decision.formulations[0].properties[0]
    by_value = {gp.derived_value.content["predicted_value"]: gp for gp in pd.evidence.predictions}
    assert by_value[80].provenance.observation_ids == (obs["f1_ts_qc"].id,)
    assert by_value[84].provenance.observation_ids == (obs["f1_ts_tp"].id,)


def test_16_model_disagreement_over_same_observation():
    pool, f, process_std, obs, dv = _phase30_pool()
    decision = _decision_for(pool, ["f3"], (TENSILE_CRITERION,))
    pd = decision.formulations[0].properties[0]
    provenance_sets = [gp.provenance.observation_ids for gp in pd.evidence.predictions]
    assert provenance_sets[0] == provenance_sets[1] == (obs["f3_ts"].id,)
    assert pd.predicted_status == PASS  # both 84 and 89 pass despite shared-observation disagreement


def test_17_predictions_from_different_observations():
    pool, f, process_std, obs, dv = _phase30_pool()
    decision = _decision_for(pool, ["f1"], (TENSILE_CRITERION,))
    pd = decision.formulations[0].properties[0]
    provenance_sets = [set(gp.provenance.observation_ids) for gp in pd.evidence.predictions]
    assert provenance_sets[0].isdisjoint(provenance_sets[1])


# -- 18-20: multiple formulations / properties / process filtering ---------------------------


def test_18_multiple_formulations():
    pool, f, process_std, obs, dv = _phase30_pool()
    decision = _decision_for(pool, ["f1", "f2", "f3", "f4"], (TENSILE_CRITERION,))
    assert {fd.formulation.natural_key for fd in decision.formulations} == {
        "formulation-f1", "formulation-f2", "formulation-f3", "formulation-f4",
    }
    by_key = {fd.formulation.natural_key: fd.properties[0].observed_status for fd in decision.formulations}
    assert by_key == {
        "formulation-f1": CONFLICTING_EVIDENCE,
        "formulation-f2": FAIL,
        "formulation-f3": PASS,
        "formulation-f4": PASS,
    }


def test_19_multiple_properties():
    pool, f, process_std, obs, dv = _phase30_pool()
    decision = _decision_for(pool, ["f1"], (TENSILE_CRITERION, MODULUS_CRITERION, VISCOSITY_CRITERION))
    statuses = {pd.criterion.property: pd.observed_status for pd in decision.formulations[0].properties}
    assert statuses == {"tensile_strength": CONFLICTING_EVIDENCE, "modulus": PASS, "viscosity": PASS}


def test_20_process_filtering_pass_through_unchanged():
    """F6 has no process relationship -- decision.py evaluates its
    properties normally (evidence-based), while process_association
    (unchanged, pass-through from materials.program) tells the caller
    it doesn't match the target process. decision.py does not invent a
    combined verdict from these two facts -- that composition is left
    to the caller."""
    pool, f, process_std, obs, dv = _phase30_pool()
    decision = _decision_for(pool, ["f6"], (TENSILE_CRITERION,))
    fd = decision.formulations[0]
    assert fd.process_association.matches_queried_process is False
    assert fd.properties[0].observed_status == INSUFFICIENT_EVIDENCE  # unreachable: no ClaimedRelationship at all


# -- 21-22: determinism --------------------------------------------------------------------------


def test_21_insertion_order_determinism():
    pool_a, f_a, ps_a, obs_a, dv_a = _phase30_pool("normal")
    pool_b, f_b, ps_b, obs_b, dv_b = _phase30_pool("shuffled")

    decision_a = _decision_for(pool_a, ["f1", "f2", "f3"], (TENSILE_CRITERION, MODULUS_CRITERION))
    decision_b = _decision_for(pool_b, ["f1", "f2", "f3"], (TENSILE_CRITERION, MODULUS_CRITERION))

    keys_a = [fd.formulation.natural_key for fd in decision_a.formulations]
    keys_b = [fd.formulation.natural_key for fd in decision_b.formulations]
    assert keys_a == keys_b

    for fda, fdb in zip(decision_a.formulations, decision_b.formulations):
        props_a = [(pd.criterion.property, pd.observed_status, pd.predicted_status) for pd in fda.properties]
        props_b = [(pd.criterion.property, pd.observed_status, pd.predicted_status) for pd in fdb.properties]
        assert props_a == props_b


def test_22_pythonhashseed_determinism():
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
        "engine = DeterministicRetrievalEngine()\n"
        "query = make_material_program_query(['formulation-f1'], 'process-std-190c', ['tensile_strength'])\n"
        "program_answer = analyze_program(pool, engine, query)\n"
        "criterion = make_criterion('tensile_strength', '>=', 80)\n"
        "decision = evaluate_program(program_answer, (criterion,))\n"
        "print([(fd.formulation.natural_key, pd.observed_status, pd.predicted_status) for fd in decision.formulations for pd in fd.properties])\n"
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
    assert len(outputs) == 1, f"evaluate_program differed across PYTHONHASHSEED values: {outputs}"


# -- 24: no ranking/score/winner field ------------------------------------------------------------


def test_24_no_ranking_score_or_winner_field_exists():
    pool, f, process_std, obs, dv = _phase30_pool()
    decision = _decision_for(pool, ["f1", "f2"], (TENSILE_CRITERION,))
    for forbidden in ("score", "rank", "ranking", "winner", "best", "recommended", "optimal"):
        assert not hasattr(decision, forbidden)
        for fd in decision.formulations:
            assert not hasattr(fd, forbidden)
            for pd in fd.properties:
                assert not hasattr(pd, forbidden)
