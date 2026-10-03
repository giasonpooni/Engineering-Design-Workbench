"""Phase 27: the first real consumer above the frozen SCOUT substrate
(db44142) -- `materials/analysis.py`, exercised against the exact
Formulation F1/F2 tensile-strength scenario validated by hand in
Phase 26. Every fixture here is built with existing, unmodified
`evidence` public API only; nothing under `evidence/`, `retrieval/`, or
`core/` is touched.
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
from materials.analysis import MaterialQuestion, analyze
from retrieval.engine import DeterministicRetrievalEngine

ENGINE = DeterministicRetrievalEngine()


def _base_pool():
    pool = EvidencePool()
    source = make_source(kind="lab_notebook", name="Internal QC Lab")
    pool.put_source(source)
    doc = make_document(
        source_id=source.id, raw_content="QC log", retrieval_method="manual_entry", retrieved_at="2026-08-18T00:00:00Z"
    )
    admit_document(pool, doc)
    pool.put_document(doc)
    process = make_referent(natural_key="process-injection-run-12", kind="process")
    admit_referent(pool, process)
    pool.put_referent(process)
    return pool, source, doc, process


def _add_observation(pool, doc, referent, process, locator, raw, value, extracted_at="2026-08-18T00:00:00Z"):
    rec = make_record(document_id=doc.id, locator=locator, raw_content=raw)
    admit_record(pool, rec)
    pool.put_record(rec)
    obs = make_observation(
        record_ids=(rec.id,), extraction_method="human_transcription",
        content={"property": "tensile_strength", "value": value, "unit": "MPa"},
        confidence=1.0, extracted_at=extracted_at,
    )
    admit_observation(pool, obs)
    pool.put_observation(obs)
    rel = make_claimed_relationship(
        from_referent_id=referent.id, to_referent_id=process.id,
        type="tested_during", observation_id=obs.id, confidence=1.0,
    )
    admit_claimed_relationship(pool, rel)
    pool.put_claimed_relationship(rel)
    return obs


def _add_prediction(pool, referent, obs, method, predicted_value, confidence=0.85, derived_at="2026-08-18T02:00:00Z"):
    dv = make_derived_value(
        derived_from=[obs.id], method=method,
        content={"property": "tensile_strength", "predicted_value": predicted_value, "unit": "MPa"},
        confidence=confidence, derived_at=derived_at,
    )
    admit_derived_value(pool, dv)
    pool.put_derived_value(dv)
    g = make_derived_grounding(derived_value_id=dv.id, referent_ids=[referent.id])
    admit_derived_grounding(pool, g)
    pool.put_derived_grounding(g)
    return dv


# -- Test 1: single observed value --------------------------------------------------


def test_single_observed_value():
    pool, source, doc, process = _base_pool()
    f1 = make_referent(natural_key="formulation-f1", kind="formulation")
    admit_referent(pool, f1)
    pool.put_referent(f1)
    _add_observation(pool, doc, f1, process, "row1", "F1: 82 MPa", 82)

    answer = analyze(pool, ENGINE, MaterialQuestion("formulation-f1", "tensile_strength"))
    assert len(answer.observed) == 1
    assert answer.observed[0].content["value"] == 82
    assert answer.predictions == ()
    assert answer.observed_disagreement is None
    assert answer.predicted_disagreement is None


# -- Test 2: observed conflict --------------------------------------------------------


def test_observed_conflict_both_retained_no_ranking():
    pool, source, doc, process = _base_pool()
    f1 = make_referent(natural_key="formulation-f1", kind="formulation")
    admit_referent(pool, f1)
    pool.put_referent(f1)
    _add_observation(pool, doc, f1, process, "row1", "F1: 82 MPa", 82)
    _add_observation(pool, doc, f1, process, "row2", "F1: 76 MPa", 76)

    answer = analyze(pool, ENGINE, MaterialQuestion("formulation-f1", "tensile_strength"))
    assert {o.content["value"] for o in answer.observed} == {82, 76}
    assert answer.observed_disagreement.minimum == 76
    assert answer.observed_disagreement.maximum == 82
    assert answer.observed_disagreement.spread == 6


# -- Test 3: derived prediction with provenance ----------------------------------------


def test_derived_prediction_with_correct_provenance():
    pool, source, doc, process = _base_pool()
    f1 = make_referent(natural_key="formulation-f1", kind="formulation")
    admit_referent(pool, f1)
    pool.put_referent(f1)
    obs = _add_observation(pool, doc, f1, process, "row1", "F1: 82 MPa", 82)
    dv = _add_prediction(pool, f1, obs, "model:tensile_predictor_A", 80)

    answer = analyze(pool, ENGINE, MaterialQuestion("formulation-f1", "tensile_strength"))
    assert len(answer.predictions) == 1
    gp = answer.predictions[0]
    assert gp.derived_value.id == dv.id
    assert gp.provenance.observation_ids == (obs.id,)


# -- Test 4: conflicting predictions ----------------------------------------------------


def test_conflicting_predictions_both_retained_independently():
    pool, source, doc, process = _base_pool()
    f1 = make_referent(natural_key="formulation-f1", kind="formulation")
    admit_referent(pool, f1)
    pool.put_referent(f1)
    obs_a = _add_observation(pool, doc, f1, process, "row1", "F1: 82 MPa", 82)
    obs_b = _add_observation(pool, doc, f1, process, "row2", "F1: 76 MPa", 76, extracted_at="2026-08-21T00:00:00Z")
    dv_a = _add_prediction(pool, f1, obs_a, "model:tensile_predictor_A", 80)
    dv_b = _add_prediction(pool, f1, obs_b, "model:tensile_predictor_B", 87, derived_at="2026-08-21T02:00:00Z")

    answer = analyze(pool, ENGINE, MaterialQuestion("formulation-f1", "tensile_strength"))
    assert len(answer.predictions) == 2
    by_id = {gp.derived_value.id: gp for gp in answer.predictions}
    assert by_id[dv_a.id].provenance.observation_ids == (obs_a.id,)
    assert by_id[dv_b.id].provenance.observation_ids == (obs_b.id,)
    assert answer.predicted_disagreement.spread == 7
    # No prediction is marked authoritative -- the result carries no such field at all.
    assert not hasattr(answer, "winner")
    assert not hasattr(answer, "authoritative")


# -- Full F1/F2 dataset (Phase 26 workload, reused exactly) -----------------------------


def _full_f1_f2_pool(order="normal"):
    pool = EvidencePool()
    qc_lab = make_source(kind="lab_notebook", name="Internal QC Lab")
    third_party = make_source(kind="external_report", name="Third-Party Test Lab")
    for s in ((qc_lab, third_party) if order == "normal" else (third_party, qc_lab)):
        pool.put_source(s)

    qc_doc = make_document(source_id=qc_lab.id, raw_content="Batch QC", retrieval_method="manual_entry", retrieved_at="2026-08-18T00:00:00Z")
    tp_doc = make_document(source_id=third_party.id, raw_content="Independent verification", retrieval_method="pdf_ingest", retrieved_at="2026-08-21T00:00:00Z")
    for d in (qc_doc, tp_doc):
        admit_document(pool, d)
        pool.put_document(d)

    f1 = make_referent(natural_key="formulation-f1", kind="formulation")
    f2 = make_referent(natural_key="formulation-f2", kind="formulation")
    process = make_referent(natural_key="process-injection-run-12", kind="process")
    for ref in ((f1, f2, process) if order == "normal" else (process, f2, f1)):
        admit_referent(pool, ref)
        pool.put_referent(ref)

    obs_f1_qc = _add_observation(pool, qc_doc, f1, process, "row4", "F1 QC: 82 MPa", 82)
    obs_f1_tp = _add_observation(pool, tp_doc, f1, process, "p2", "F1 verification: 76 MPa", 76, extracted_at="2026-08-21T00:00:00Z")
    obs_f2_qc = _add_observation(pool, qc_doc, f2, process, "row9", "F2 QC: 68 MPa", 68)

    d_f1_a = _add_prediction(pool, f1, obs_f1_qc, "model:tensile_predictor_A", 80, confidence=0.88)
    d_f1_b = _add_prediction(pool, f1, obs_f1_tp, "model:tensile_predictor_B", 87, confidence=0.79, derived_at="2026-08-21T02:00:00Z")
    d_f2_a = _add_prediction(pool, f2, obs_f2_qc, "model:tensile_predictor_A", 70, confidence=0.86)

    return pool, dict(
        f1=f1, f2=f2, obs_f1_qc=obs_f1_qc, obs_f1_tp=obs_f1_tp, obs_f2_qc=obs_f2_qc,
        d_f1_a=d_f1_a, d_f1_b=d_f1_b, d_f2_a=d_f2_a,
    )


# -- Test 5: full F1 scenario -----------------------------------------------------------


def test_full_f1_scenario_matches_phase_26_workload():
    pool, obj = _full_f1_f2_pool()
    answer = analyze(pool, ENGINE, MaterialQuestion("formulation-f1", "tensile_strength"))

    assert {o.content["value"] for o in answer.observed} == {82, 76}
    predicted = {gp.derived_value.content["predicted_value"] for gp in answer.predictions}
    assert predicted == {80, 87}
    assert answer.observed_disagreement.spread == 6
    assert answer.predicted_disagreement.spread == 7


# -- Test 6: second formulation, no special-casing ----------------------------------------


def test_second_formulation_f2_no_special_case_logic():
    pool, obj = _full_f1_f2_pool()
    answer = analyze(pool, ENGINE, MaterialQuestion("formulation-f2", "tensile_strength"))

    assert {o.content["value"] for o in answer.observed} == {68}
    assert len(answer.predictions) == 1
    assert answer.predictions[0].derived_value.content["predicted_value"] == 70
    assert answer.observed_disagreement is None  # only one measurement
    assert answer.predicted_disagreement is None  # only one prediction


# -- Test 7: provenance isolation -----------------------------------------------------------


def test_provenance_isolation_no_cross_contamination():
    pool, obj = _full_f1_f2_pool()
    answer = analyze(pool, ENGINE, MaterialQuestion("formulation-f1", "tensile_strength"))
    by_value = {gp.derived_value.content["predicted_value"]: gp for gp in answer.predictions}

    assert by_value[80].provenance.observation_ids == (obj["obs_f1_qc"].id,)
    assert by_value[87].provenance.observation_ids == (obj["obs_f1_tp"].id,)
    assert obj["obs_f1_tp"].id not in by_value[80].provenance.observation_ids
    assert obj["obs_f1_qc"].id not in by_value[87].provenance.observation_ids


# -- Test 8: deterministic output across insertion order --------------------------------------


def test_deterministic_across_insertion_order():
    pool_a, _ = _full_f1_f2_pool("normal")
    pool_b, _ = _full_f1_f2_pool("shuffled")

    answer_a = analyze(pool_a, ENGINE, MaterialQuestion("formulation-f1", "tensile_strength"))
    answer_b = analyze(pool_b, ENGINE, MaterialQuestion("formulation-f1", "tensile_strength"))

    assert {o.id for o in answer_a.observed} == {o.id for o in answer_b.observed}
    assert {gp.derived_value.id for gp in answer_a.predictions} == {gp.derived_value.id for gp in answer_b.predictions}
    assert answer_a.observed_disagreement == answer_b.observed_disagreement
    assert answer_a.predicted_disagreement == answer_b.predicted_disagreement
    assert answer_a.material.id == answer_b.material.id


# -- Test 9: PYTHONHASHSEED determinism --------------------------------------------------------


def test_deterministic_across_hash_seeds():
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
        "from materials.analysis import MaterialQuestion, analyze\n"
        "from retrieval.engine import DeterministicRetrievalEngine\n"
        "pool = EvidencePool()\n"
        "source = make_source(kind='lab_notebook', name='QC')\n"
        "pool.put_source(source)\n"
        "doc = make_document(source_id=source.id, raw_content='log', retrieval_method='m', retrieved_at='t')\n"
        "pool.put_document(doc)\n"
        "process = make_referent(natural_key='process-injection-run-12', kind='process')\n"
        "pool.put_referent(process)\n"
        "f1 = make_referent(natural_key='formulation-f1', kind='formulation')\n"
        "pool.put_referent(f1)\n"
        "rec_a = make_record(document_id=doc.id, locator='r1', raw_content='82')\n"
        "pool.put_record(rec_a)\n"
        "rec_b = make_record(document_id=doc.id, locator='r2', raw_content='76')\n"
        "pool.put_record(rec_b)\n"
        "obs_a = make_observation(record_ids=(rec_a.id,), extraction_method='human_transcription', "
        "content={'property': 'tensile_strength', 'value': 82, 'unit': 'MPa'}, confidence=1.0, extracted_at='t')\n"
        "pool.put_observation(obs_a)\n"
        "obs_b = make_observation(record_ids=(rec_b.id,), extraction_method='human_transcription', "
        "content={'property': 'tensile_strength', 'value': 76, 'unit': 'MPa'}, confidence=1.0, extracted_at='t2')\n"
        "pool.put_observation(obs_b)\n"
        "rel_a = make_claimed_relationship(from_referent_id=f1.id, to_referent_id=process.id, "
        "type='tested_during', observation_id=obs_a.id, confidence=1.0)\n"
        "pool.put_claimed_relationship(rel_a)\n"
        "rel_b = make_claimed_relationship(from_referent_id=f1.id, to_referent_id=process.id, "
        "type='tested_during', observation_id=obs_b.id, confidence=1.0)\n"
        "pool.put_claimed_relationship(rel_b)\n"
        "dv_a = make_derived_value(derived_from=[obs_a.id], method='model:tensile_predictor_A', "
        "content={'property': 'tensile_strength', 'predicted_value': 80, 'unit': 'MPa'}, confidence=0.88, derived_at='t')\n"
        "pool.put_derived_value(dv_a)\n"
        "dv_b = make_derived_value(derived_from=[obs_b.id], method='model:tensile_predictor_B', "
        "content={'property': 'tensile_strength', 'predicted_value': 87, 'unit': 'MPa'}, confidence=0.79, derived_at='t2')\n"
        "pool.put_derived_value(dv_b)\n"
        "g_a = make_derived_grounding(derived_value_id=dv_a.id, referent_ids=[f1.id])\n"
        "pool.put_derived_grounding(g_a)\n"
        "g_b = make_derived_grounding(derived_value_id=dv_b.id, referent_ids=[f1.id])\n"
        "pool.put_derived_grounding(g_b)\n"
        "engine = DeterministicRetrievalEngine()\n"
        "answer = analyze(pool, engine, MaterialQuestion('formulation-f1', 'tensile_strength'))\n"
        "observed = sorted(o.content['value'] for o in answer.observed)\n"
        "predicted = sorted(gp.derived_value.content['predicted_value'] for gp in answer.predictions)\n"
        "print(observed, predicted, answer.observed_disagreement, answer.predicted_disagreement)\n"
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
    assert len(outputs) == 1, f"materials.analyze differed across PYTHONHASHSEED values: {outputs}"


# -- Unknown material ---------------------------------------------------------------------------


def test_unknown_material_raises_key_error():
    import pytest

    pool, _, _, _ = _base_pool()
    with pytest.raises(KeyError):
        analyze(pool, ENGINE, MaterialQuestion("formulation-does-not-exist", "tensile_strength"))
