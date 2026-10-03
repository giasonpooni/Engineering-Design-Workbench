"""Phase 35: materials.specification -- converts an already-computed
ExperimentGapAnalysis (Phase 34) into structured descriptions of WHAT
INFORMATION would need to be obtained to close each gap, exercised
against the same Phase 30-34 workload: F1 (measurement conflict +
condition-dependent viscosity), F2 (clean FAIL), F3 (model disagreement
over one observation), F4 (clean PASS + measurement without prediction),
F5 (prediction without a matching measurement), F6 (no process
relationship).
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
from materials.audit import audit_program
from materials.decision import (
    make_criterion, evaluate_program,
)
from materials.experiment import (
    INCOMPARABLE_EVIDENCE, MEASUREMENT_CONFLICT, MEASUREMENT_WITHOUT_PREDICTION,
    MISSING_EVIDENCE, MODEL_DISAGREEMENT, PREDICTION_WITHOUT_MEASUREMENT,
    analyze_experiment_gaps,
)
from materials.program import make_material_program_query, analyze_program
from materials.specification import (
    EITHER, OBSERVED, PREDICTED, specify_experiment_requirements,
)
from retrieval.engine import DeterministicRetrievalEngine

ENGINE = DeterministicRetrievalEngine()

TENSILE_CRITERION = make_criterion("tensile_strength", ">=", 80)
MODULUS_CRITERION = make_criterion("modulus", ">=", 2.7)
VISCOSITY_CRITERION = make_criterion("viscosity", "<=", 950, context={"unit": "mPa.s", "temperature": 25, "temperature_unit": "C"})
HARDNESS_CRITERION = make_criterion("hardness", ">=", 50)  # never measured


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

    # F5: modulus observed, but its ONLY prediction is tensile_strength
    # (grounded via a modulus observation) -- tensile has a prediction
    # but no tensile OBSERVATION was ever retrieved for F5.
    obs["f5_mod"] = _add_obs(pool, doc, f["f5"], process_std, "f5-mod", {"property": "modulus", "value": 2.9, "unit": "GPa"})
    dv_f5 = _add_pred(pool, f["f5"], obs["f5_mod"], "model:A", {"property": "tensile_strength", "predicted_value": 82, "unit": "MPa"})

    obs["f6_ts"] = _add_obs(pool, doc, f["f6"], None, "f6-ts", {"property": "tensile_strength", "value": 90, "unit": "MPa"})

    return pool, f, process_std, obs, dict(dv_f1_a=dv_f1_a, dv_f1_b=dv_f1_b, dv_f3_a=dv_f3_a, dv_f3_b=dv_f3_b, dv_f5=dv_f5)


def _specify_for(pool, formulation_keys, criteria, properties=None):
    if properties is None:
        properties = tuple(sorted({c.property for c in criteria}))
    query = make_material_program_query([f"formulation-{k}" for k in formulation_keys], "process-std-190c", properties)
    program_answer = analyze_program(pool, ENGINE, query)
    decision = evaluate_program(program_answer, criteria)
    audit = audit_program(decision)
    gaps = analyze_experiment_gaps(audit)
    return specify_experiment_requirements(gaps)


def _find_entry(spec, formulation_key, property_name):
    return next(
        e for e in spec.entries
        if e.formulation.natural_key == f"formulation-{formulation_key}" and e.property == property_name
    )


def _req(entry, category, role=None):
    matches = [r for r in entry.requirements if r.category == category and (role is None or r.role == role)]
    assert len(matches) == 1, f"expected exactly one {category}/{role} requirement, got {len(matches)}"
    return matches[0]


# -- 1. MEASUREMENT_CONFLICT --------------------------------------------------------------


def test_1_measurement_conflict():
    pool, f, process_std, obs, dv = _workload()
    entry = _find_entry(_specify_for(pool, ["f1"], (TENSILE_CRITERION,)), "f1", "tensile_strength")
    req = _req(entry, MEASUREMENT_CONFLICT)
    assert req.role == OBSERVED
    assert set(req.existing_evidence_ids) == {obs["f1_ts_qc"].id, obs["f1_ts_tp"].id}
    assert req.criterion_context == {}
    assert req.formulation.natural_key == "formulation-f1"


# -- 2. MODEL_DISAGREEMENT -----------------------------------------------------------------


def test_2_model_disagreement():
    pool, f, process_std, obs, dv = _workload()
    strict = make_criterion("tensile_strength", ">=", 85)
    entry = _find_entry(_specify_for(pool, ["f3"], (strict,)), "f3", "tensile_strength")
    req = _req(entry, MODEL_DISAGREEMENT)
    assert req.role == PREDICTED
    assert set(req.existing_evidence_ids) == {dv["dv_f3_a"].id, dv["dv_f3_b"].id}
    assert req.provenance_observation_id_sets[0] == req.provenance_observation_id_sets[1] == (obs["f3_ts"].id,)


# -- 3. INCOMPARABLE_EVIDENCE ---------------------------------------------------------------


def test_3_incomparable_evidence():
    pool, f, process_std, obs, dv = _workload()
    entry = _find_entry(_specify_for(pool, ["f1"], (VISCOSITY_CRITERION,)), "f1", "viscosity")
    req = _req(entry, INCOMPARABLE_EVIDENCE)
    assert req.role == OBSERVED
    assert req.criterion_context == {"unit": "mPa.s", "temperature": 25, "temperature_unit": "C"}
    assert len(req.available_contexts) == 1
    assert req.available_contexts[0]["temperature"] == 40
    assert req.matching_contexts == ()
    # No fabricated "measure at 25C" context anywhere in what is available.
    assert all(ctx.get("temperature") != 25 for ctx in req.available_contexts)


# -- 4. MISSING_EVIDENCE --------------------------------------------------------------------


def test_4_missing_evidence():
    pool, f, process_std, obs, dv = _workload()
    entry = _find_entry(_specify_for(pool, ["f1"], (HARDNESS_CRITERION,)), "f1", "hardness")
    req = _req(entry, MISSING_EVIDENCE)
    assert req.role == EITHER
    assert req.existing_evidence_ids == ()
    assert req.provenance_observation_id_sets == ()
    assert req.available_contexts == ()


# -- 5. MEASUREMENT_WITHOUT_PREDICTION -------------------------------------------------------


def test_5_measurement_without_prediction():
    pool, f, process_std, obs, dv = _workload()
    entry = _find_entry(_specify_for(pool, ["f4"], (MODULUS_CRITERION,)), "f4", "modulus")
    req = _req(entry, MEASUREMENT_WITHOUT_PREDICTION)
    assert req.role == PREDICTED
    # The existing measurement information is preserved even though the
    # requirement names the PREDICTED side as what's missing.
    assert req.existing_evidence_ids == (obs["f4_mod"].id,)


# -- 6. PREDICTION_WITHOUT_MEASUREMENT -------------------------------------------------------


def test_6_prediction_without_measurement():
    pool, f, process_std, obs, dv = _workload()
    entry = _find_entry(_specify_for(pool, ["f5"], (TENSILE_CRITERION,)), "f5", "tensile_strength")
    req = _req(entry, PREDICTION_WITHOUT_MEASUREMENT)
    assert req.role == OBSERVED
    assert req.existing_evidence_ids == (dv["dv_f5"].id,)
    assert req.provenance_observation_id_sets == ((obs["f5_mod"].id,),)


# -- 7. criterion context preserved exactly ---------------------------------------------------


def test_7_criterion_context_preserved_exactly():
    pool, f, process_std, obs, dv = _workload()
    entry = _find_entry(_specify_for(pool, ["f1"], (VISCOSITY_CRITERION,)), "f1", "viscosity")
    assert entry.criterion_context == dict(VISCOSITY_CRITERION.context)
    for req in entry.requirements:
        assert req.criterion_context == dict(VISCOSITY_CRITERION.context)


# -- 8. formulation identity preserved ---------------------------------------------------------


def test_8_formulation_identity_preserved():
    pool, f, process_std, obs, dv = _workload()
    entry = _find_entry(_specify_for(pool, ["f1"], (TENSILE_CRITERION,)), "f1", "tensile_strength")
    assert entry.formulation == f["f1"]
    for req in entry.requirements:
        assert req.formulation == f["f1"]


# -- 9. property identity preserved ------------------------------------------------------------


def test_9_property_identity_preserved():
    pool, f, process_std, obs, dv = _workload()
    spec = _specify_for(pool, ["f4"], (TENSILE_CRITERION, MODULUS_CRITERION))
    assert {e.property for e in spec.entries} == {"tensile_strength", "modulus"}
    for e in spec.entries:
        for req in e.requirements:
            assert req.property == e.property


# -- 10. observation IDs preserved --------------------------------------------------------------


def test_10_observation_ids_preserved():
    pool, f, process_std, obs, dv = _workload()
    entry = _find_entry(_specify_for(pool, ["f1"], (TENSILE_CRITERION,)), "f1", "tensile_strength")
    req = _req(entry, MEASUREMENT_CONFLICT)
    assert obs["f1_ts_qc"].id in req.existing_evidence_ids
    assert obs["f1_ts_tp"].id in req.existing_evidence_ids


# -- 11. prediction IDs preserved -----------------------------------------------------------------


def test_11_prediction_ids_preserved():
    pool, f, process_std, obs, dv = _workload()
    entry = _find_entry(_specify_for(pool, ["f5"], (TENSILE_CRITERION,)), "f5", "tensile_strength")
    req = _req(entry, PREDICTION_WITHOUT_MEASUREMENT)
    assert dv["dv_f5"].id in req.existing_evidence_ids


# -- 12. provenance observation-ID sets preserved --------------------------------------------------


def test_12_provenance_observation_id_sets_preserved():
    pool2, doc2, tp2, process2, f2 = _base()
    obs_a = _add_obs(pool2, doc2, f2["f1"], process2, "a", {"property": "tensile_strength", "value": 82, "unit": "MPa"})
    obs_b = _add_obs(pool2, tp2, f2["f1"], process2, "b", {"property": "tensile_strength", "value": 79, "unit": "MPa"})
    _add_pred(pool2, f2["f1"], obs_a, "model:A", {"property": "tensile_strength", "predicted_value": 90, "unit": "MPa"})
    _add_pred(pool2, f2["f1"], obs_b, "model:B", {"property": "tensile_strength", "predicted_value": 70, "unit": "MPa"})
    entry = _find_entry(_specify_for(pool2, ["f1"], (TENSILE_CRITERION,)), "f1", "tensile_strength")
    req = _req(entry, MEASUREMENT_CONFLICT, role=PREDICTED)  # different provenance -- not MODEL_DISAGREEMENT
    sets = req.provenance_observation_id_sets
    assert set(sets[0]).isdisjoint(set(sets[1]))
    assert {obs_a.id, obs_b.id} == set(sets[0]) | set(sets[1])


# -- 13. available contexts preserved -----------------------------------------------------------------


def test_13_available_contexts_preserved():
    pool, f, process_std, obs, dv = _workload()
    entry = _find_entry(_specify_for(pool, ["f1"], (VISCOSITY_CRITERION,)), "f1", "viscosity")
    req = _req(entry, INCOMPARABLE_EVIDENCE)
    assert req.available_contexts[0] == {"unit": "mPa.s", "temperature": 40, "temperature_unit": "C"}


# -- 14. matching contexts preserved -----------------------------------------------------------------------


def test_14_matching_contexts_preserved():
    pool, f, process_std, obs, dv = _workload()
    entry = _find_entry(_specify_for(pool, ["f1"], (TENSILE_CRITERION,)), "f1", "tensile_strength")
    req = _req(entry, MEASUREMENT_CONFLICT)
    assert req.matching_contexts == ({"unit": "MPa"},)


# -- 15. no category is silently dropped -------------------------------------------------------------------


def test_15_no_category_silently_dropped():
    pool, f, process_std, obs, dv = _workload()
    strict = make_criterion("tensile_strength", ">=", 85)
    specs = (
        _specify_for(pool, ["f1"], (TENSILE_CRITERION, VISCOSITY_CRITERION)),
        _specify_for(pool, ["f3"], (strict,)),
        _specify_for(pool, ["f1"], (HARDNESS_CRITERION,)),
        _specify_for(pool, ["f4"], (MODULUS_CRITERION,)),
        _specify_for(pool, ["f5"], (TENSILE_CRITERION,)),
    )
    categories_seen = {
        req.category
        for spec in specs
        for entry in spec.entries
        for req in entry.requirements
    }
    assert categories_seen == {
        MEASUREMENT_CONFLICT, MODEL_DISAGREEMENT, INCOMPARABLE_EVIDENCE,
        MISSING_EVIDENCE, MEASUREMENT_WITHOUT_PREDICTION, PREDICTION_WITHOUT_MEASUREMENT,
    }


# -- 16. multiple gaps for one formulation remain separate ---------------------------------------------------


def test_16_multiple_gaps_for_one_formulation_remain_separate():
    pool, f, process_std, obs, dv = _workload()
    spec = _specify_for(pool, ["f1"], (TENSILE_CRITERION, VISCOSITY_CRITERION))
    assert {e.property for e in spec.entries if e.formulation.natural_key == "formulation-f1"} == {"tensile_strength", "viscosity"}
    ts_entry = _find_entry(spec, "f1", "tensile_strength")
    visc_entry = _find_entry(spec, "f1", "viscosity")
    assert all(r.category != INCOMPARABLE_EVIDENCE for r in ts_entry.requirements)
    assert any(r.category == INCOMPARABLE_EVIDENCE for r in visc_entry.requirements)


# -- 17. multiple properties remain separate -----------------------------------------------------------------


def test_17_multiple_properties_remain_separate():
    pool, f, process_std, obs, dv = _workload()
    spec = _specify_for(pool, ["f4"], (TENSILE_CRITERION, MODULUS_CRITERION))
    ts_entry = _find_entry(spec, "f4", "tensile_strength")
    mod_entry = _find_entry(spec, "f4", "modulus")
    # F4 has no tensile_strength prediction at all -- both properties
    # independently show MEASUREMENT_WITHOUT_PREDICTION, but each stays
    # attached to its own property, never merged.
    ts_req = _req(ts_entry, MEASUREMENT_WITHOUT_PREDICTION)
    mod_req = _req(mod_entry, MEASUREMENT_WITHOUT_PREDICTION)
    assert ts_req.property == "tensile_strength"
    assert mod_req.property == "modulus"
    assert ts_req.existing_evidence_ids != mod_req.existing_evidence_ids


# -- 18. observed and predicted requirements remain separate ----------------------------------------------------


def test_18_observed_and_predicted_requirements_remain_separate():
    pool2, doc2, tp2, process2, f2 = _base()
    obs_a = _add_obs(pool2, doc2, f2["f1"], process2, "a", {"property": "tensile_strength", "value": 82, "unit": "MPa"})
    obs_b = _add_obs(pool2, tp2, f2["f1"], process2, "b", {"property": "tensile_strength", "value": 79, "unit": "MPa"})
    _add_pred(pool2, f2["f1"], obs_a, "model:A", {"property": "tensile_strength", "predicted_value": 90, "unit": "MPa"})
    _add_pred(pool2, f2["f1"], obs_b, "model:B", {"property": "tensile_strength", "predicted_value": 70, "unit": "MPa"})
    entry = _find_entry(_specify_for(pool2, ["f1"], (TENSILE_CRITERION,)), "f1", "tensile_strength")
    observed_req = _req(entry, MEASUREMENT_CONFLICT, role=OBSERVED)
    predicted_req = _req(entry, MEASUREMENT_CONFLICT, role=PREDICTED)
    assert observed_req is not predicted_req
    assert set(observed_req.existing_evidence_ids) != set(predicted_req.existing_evidence_ids)


# -- 19. no ranking/score/recommendation fields ------------------------------------------------------------------


def test_19_no_ranking_score_or_recommendation_fields():
    pool, f, process_std, obs, dv = _workload()
    spec = _specify_for(pool, ["f1", "f2"], (TENSILE_CRITERION,))
    forbidden = (
        "score", "rank", "ranking", "winner", "best", "recommended", "optimal",
        "priority", "utility", "cost", "expected_information_gain", "confidence_rank",
        "suggested_temperature", "suggested_experiment", "suggested_measurement",
        "next_experiment", "experiment_priority", "selected_experiment", "chosen_experiment",
        "instrument", "operator", "sample_mass", "duration", "temperature_ramp", "geometry",
        "laboratory", "batch_size", "scheduling",
    )
    assert not any(hasattr(spec, name) for name in forbidden)
    for entry in spec.entries:
        assert not any(hasattr(entry, name) for name in forbidden)
        for req in entry.requirements:
            assert not any(hasattr(req, name) for name in forbidden)


# -- 20. input objects remain unchanged --------------------------------------------------------------------------


def test_20_input_objects_remain_unchanged():
    pool, f, process_std, obs, dv = _workload()
    query = make_material_program_query(["formulation-f1"], "process-std-190c", ("tensile_strength",))
    program_answer = analyze_program(pool, ENGINE, query)
    decision = evaluate_program(program_answer, (TENSILE_CRITERION,))
    audit = audit_program(decision)
    gaps = analyze_experiment_gaps(audit)
    before = repr(gaps)
    fingerprint_before = pool.fingerprint()
    specify_experiment_requirements(gaps)
    assert repr(gaps) == before
    assert pool.fingerprint() == fingerprint_before


# -- 21. deterministic insertion-order behavior ---------------------------------------------------------------------


def test_21_deterministic_insertion_order():
    pool_a, f_a, ps_a, obs_a, dv_a = _workload("normal")
    pool_b, f_b, ps_b, obs_b, dv_b = _workload("shuffled")
    spec_a = _specify_for(pool_a, ["f1", "f2", "f3"], (TENSILE_CRITERION,))
    spec_b = _specify_for(pool_b, ["f1", "f2", "f3"], (TENSILE_CRITERION,))

    keys_a = [(e.formulation.natural_key, e.property) for e in spec_a.entries]
    keys_b = [(e.formulation.natural_key, e.property) for e in spec_b.entries]
    assert keys_a == keys_b

    for ea, eb in zip(spec_a.entries, spec_b.entries):
        cats_a = [(r.role, r.category) for r in ea.requirements]
        cats_b = [(r.role, r.category) for r in eb.requirements]
        assert cats_a == cats_b


# -- 22. PYTHONHASHSEED determinism -----------------------------------------------------------------------------------


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
        "from materials.audit import audit_program\n"
        "from materials.decision import make_criterion, evaluate_program\n"
        "from materials.experiment import analyze_experiment_gaps\n"
        "from materials.program import make_material_program_query, analyze_program\n"
        "from materials.specification import specify_experiment_requirements\n"
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
        "audit = audit_program(decision)\n"
        "gaps = analyze_experiment_gaps(audit)\n"
        "spec = specify_experiment_requirements(gaps)\n"
        "entry = spec.entries[0]\n"
        "for req in entry.requirements:\n"
        "    print(req.role, req.category, sorted(req.existing_evidence_ids))\n"
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
    assert len(outputs) == 1, f"specify_experiment_requirements differed across PYTHONHASHSEED values: {outputs}"
