"""Phase 34: materials.experiment -- experiment-gap analysis over an
already-computed ProgramAudit (Phase 33), exercised against the Phase
30-33 workload: F1 (measurement conflict + condition-dependent
viscosity), F2 (clean FAIL), F3 (model disagreement over one
observation), F4 (clean PASS), F5 (prediction without a matching
measurement), F6 (no process relationship).
"""

from evidence.admission import (
    admit_claimed_relationship, admit_derived_grounding, admit_derived_value,
    admit_document, admit_observation, admit_record, admit_referent,
)
from evidence.pool import EvidencePool
from evidence.provenance import ancestry_of
from evidence.types import (
    make_claimed_relationship, make_derived_grounding, make_derived_value,
    make_document, make_observation, make_record, make_referent, make_source,
)
from materials.audit import audit_program
from materials.decision import (
    CONFLICTING_EVIDENCE, FAIL, INSUFFICIENT_EVIDENCE, PASS,
    make_criterion, evaluate_program,
)
from materials.experiment import (
    ALL_GAP_CATEGORIES, INCOMPARABLE_EVIDENCE, MEASUREMENT_CONFLICT,
    MEASUREMENT_WITHOUT_PREDICTION, MISSING_EVIDENCE, MODEL_DISAGREEMENT,
    PREDICTION_WITHOUT_MEASUREMENT, analyze_experiment_gaps,
)
from materials.program import make_material_program_query, analyze_program
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


def _analysis_for(pool, formulation_keys, criteria, properties=None):
    if properties is None:
        properties = tuple(sorted({c.property for c in criteria}))
    query = make_material_program_query([f"formulation-{k}" for k in formulation_keys], "process-std-190c", properties)
    program_answer = analyze_program(pool, ENGINE, query)
    decision = evaluate_program(program_answer, criteria)
    audit = audit_program(decision)
    return analyze_experiment_gaps(audit)


def _find(analysis, formulation_key, property_name):
    return next(
        g for g in analysis.gaps
        if g.formulation.natural_key == f"formulation-{formulation_key}" and g.property == property_name
    )


# -- 1. measurement conflict --------------------------------------------------------------


def test_1_measurement_conflict():
    pool, f, process_std, obs, dv = _workload()
    gap = _find(_analysis_for(pool, ["f1"], (TENSILE_CRITERION,)), "f1", "tensile_strength")
    assert gap.observed.status == CONFLICTING_EVIDENCE
    assert MEASUREMENT_CONFLICT in gap.observed.categories
    assert set(gap.observed.supporting_ids) == {obs["f1_ts_qc"].id, obs["f1_ts_tp"].id}
    assert "disagree" in gap.observed.reason


# -- 2. model disagreement -----------------------------------------------------------------


def test_2_model_disagreement():
    pool, f, process_std, obs, dv = _workload()
    strict = make_criterion("tensile_strength", ">=", 85)
    gap = _find(_analysis_for(pool, ["f3"], (strict,)), "f3", "tensile_strength")
    assert gap.predicted.status == CONFLICTING_EVIDENCE
    assert MODEL_DISAGREEMENT in gap.predicted.categories
    assert gap.predicted.provenance_observation_id_sets[0] == gap.predicted.provenance_observation_id_sets[1] == (obs["f3_ts"].id,)


# -- 3. missing evidence --------------------------------------------------------------------


def test_3_missing_evidence():
    pool, f, process_std, obs, dv = _workload()
    gap = _find(_analysis_for(pool, ["f1"], (HARDNESS_CRITERION,)), "f1", "hardness")
    assert gap.observed.status == INSUFFICIENT_EVIDENCE
    assert gap.predicted.status == INSUFFICIENT_EVIDENCE
    assert MISSING_EVIDENCE in gap.categories


# -- 4. incomparable evidence -----------------------------------------------------------------


def test_4_incomparable_evidence():
    pool, f, process_std, obs, dv = _workload()
    gap = _find(_analysis_for(pool, ["f1"], (VISCOSITY_CRITERION,)), "f1", "viscosity")
    assert INCOMPARABLE_EVIDENCE in gap.observed.categories
    assert gap.criterion_context == {"unit": "mPa.s", "temperature": 25, "temperature_unit": "C"}
    assert len(gap.observed.available_contexts) == 1
    assert gap.observed.available_contexts[0]["temperature"] == 40
    assert gap.observed.matching_contexts == ()


# -- 5. measurement without prediction -----------------------------------------------------------


def test_5_measurement_without_prediction():
    pool, f, process_std, obs, dv = _workload()
    gap = _find(_analysis_for(pool, ["f4"], (MODULUS_CRITERION,)), "f4", "modulus")
    assert gap.observed.status == PASS
    assert gap.predicted.status == INSUFFICIENT_EVIDENCE
    assert MEASUREMENT_WITHOUT_PREDICTION in gap.categories


# -- 6. prediction without measurement, structurally tested separately -----------------------------


def test_6_prediction_without_measurement_property_level():
    """F5: a tensile prediction exists (grounded via a MODULUS
    observation) but no tensile Observation was retrieved for F5 --
    property-level PREDICTION_WITHOUT_MEASUREMENT."""
    pool, f, process_std, obs, dv = _workload()
    gap = _find(_analysis_for(pool, ["f5"], (TENSILE_CRITERION,)), "f5", "tensile_strength")
    assert gap.observed.status == INSUFFICIENT_EVIDENCE
    assert gap.predicted.status == PASS
    assert PREDICTION_WITHOUT_MEASUREMENT in gap.categories


def test_6b_ancestry_level_prediction_without_measurement_is_unreachable():
    """Phase 34 sec.19: empirically, NO admitted DerivedValue can have
    zero Observations anywhere in its transitive ancestry -- proven
    directly against the public API, not inferred from type names."""
    import pytest

    pool = EvidencePool()
    dv_fake = make_derived_value(
        derived_from=["not-a-real-observation-or-derived-value"],
        method="model:no_ancestry_attempt", content={"property": "x", "predicted_value": 1},
        confidence=0.5, derived_at="t",
    )
    result = admit_derived_value(pool, dv_fake)
    assert isinstance(result, list)  # rejected -- structurally cannot be admitted
    assert any(e.code == "UNKNOWN_INPUT" for e in result)

    # Even bypassing admission entirely (direct put_*), ancestry_of never
    # silently reports empty ancestry -- it raises instead.
    pool.put_derived_value(dv_fake)
    with pytest.raises(KeyError):
        ancestry_of(pool, dv_fake.id)


# -- 7/8. observed PASS / observed FAIL --------------------------------------------------------------


def test_7_observed_pass():
    pool, f, process_std, obs, dv = _workload()
    gap = _find(_analysis_for(pool, ["f4"], (TENSILE_CRITERION,)), "f4", "tensile_strength")
    assert gap.observed.status == PASS
    assert gap.observed.categories == ()
    assert gap.observed.reason is None


def test_8_observed_fail():
    pool, f, process_std, obs, dv = _workload()
    gap = _find(_analysis_for(pool, ["f2"], (TENSILE_CRITERION,)), "f2", "tensile_strength")
    assert gap.observed.status == FAIL
    assert gap.observed.categories == ()
    assert gap.observed.reason is None


# -- 9. observed conflict + predicted PASS -----------------------------------------------------------


def test_9_observed_conflict_predicted_pass():
    pool, f, process_std, obs, dv = _workload()
    gap = _find(_analysis_for(pool, ["f1"], (TENSILE_CRITERION,)), "f1", "tensile_strength")
    assert MEASUREMENT_CONFLICT in gap.observed.categories
    assert gap.predicted.status == PASS
    assert gap.predicted.categories == ()


# -- 10. provenance preservation ------------------------------------------------------------------------


def test_10_provenance_preservation():
    pool, f, process_std, obs, dv = _workload()
    gap = _find(_analysis_for(pool, ["f1"], (TENSILE_CRITERION,)), "f1", "tensile_strength")
    sets = gap.predicted.provenance_observation_id_sets
    assert set(sets[0]).isdisjoint(set(sets[1]))
    assert {obs["f1_ts_qc"].id, obs["f1_ts_tp"].id} == set(sets[0]) | set(sets[1])


# -- 11. condition/context preservation ------------------------------------------------------------------


def test_11_context_preservation():
    pool, f, process_std, obs, dv = _workload()
    gap = _find(_analysis_for(pool, ["f1"], (VISCOSITY_CRITERION,)), "f1", "viscosity")
    assert gap.criterion_context == dict(VISCOSITY_CRITERION.context)
    assert gap.criterion_context is not VISCOSITY_CRITERION.context  # copied, not aliased in a way that risks mutation
    assert gap.observed.available_contexts[0] != gap.criterion_context  # genuinely distinguishable


# -- 12/13. multiple formulations / properties -----------------------------------------------------------


def test_12_multiple_formulations():
    pool, f, process_std, obs, dv = _workload()
    analysis = _analysis_for(pool, ["f1", "f2", "f3", "f4"], (TENSILE_CRITERION,))
    assert {g.formulation.natural_key for g in analysis.gaps} == {
        "formulation-f1", "formulation-f2", "formulation-f3", "formulation-f4",
    }


def test_13_multiple_properties():
    pool, f, process_std, obs, dv = _workload()
    analysis = _analysis_for(pool, ["f1"], (TENSILE_CRITERION, MODULUS_CRITERION))
    assert {g.property for g in analysis.gaps} == {"tensile_strength", "modulus"}


# -- 14/15. deterministic ordering / insertion-order independence -------------------------------------------


def test_14_15_deterministic_ordering_and_insertion_order():
    pool_a, f_a, ps_a, obs_a, dv_a = _workload("normal")
    pool_b, f_b, ps_b, obs_b, dv_b = _workload("shuffled")

    a = _analysis_for(pool_a, ["f1", "f2", "f3"], (TENSILE_CRITERION,))
    b = _analysis_for(pool_b, ["f1", "f2", "f3"], (TENSILE_CRITERION,))

    keys_a = [g.formulation.natural_key for g in a.gaps]
    keys_b = [g.formulation.natural_key for g in b.gaps]
    assert keys_a == keys_b

    for ga, gb in zip(a.gaps, b.gaps):
        assert ga.observed.status == gb.observed.status
        assert ga.observed.categories == gb.observed.categories
        assert ga.predicted.categories == gb.predicted.categories
        assert ga.categories == gb.categories


# -- 16. PYTHONHASHSEED determinism ----------------------------------------------------------------------------


def test_16_pythonhashseed_determinism():
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
        "analysis = analyze_experiment_gaps(audit)\n"
        "gap = analysis.gaps[0]\n"
        "print(gap.observed.status, gap.observed.categories, sorted(gap.observed.supporting_ids))\n"
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
    assert len(outputs) == 1, f"analyze_experiment_gaps differed across PYTHONHASHSEED values: {outputs}"


# -- 17. input immutability -------------------------------------------------------------------------------------


def test_17_input_immutability():
    pool, f, process_std, obs, dv = _workload()
    query = make_material_program_query(["formulation-f1"], "process-std-190c", ("tensile_strength",))
    program_answer = analyze_program(pool, ENGINE, query)
    decision = evaluate_program(program_answer, (TENSILE_CRITERION,))
    audit = audit_program(decision)
    before = repr(audit)
    analyze_experiment_gaps(audit)
    assert repr(audit) == before


# -- 18. no retrieval ---------------------------------------------------------------------------------------------


def test_18_no_retrieval_fingerprint_unchanged():
    pool, f, process_std, obs, dv = _workload()
    query = make_material_program_query(["formulation-f1"], "process-std-190c", ("tensile_strength",))
    program_answer = analyze_program(pool, ENGINE, query)
    decision = evaluate_program(program_answer, (TENSILE_CRITERION,))
    audit = audit_program(decision)
    fingerprint_before = pool.fingerprint()
    analyze_experiment_gaps(audit)  # single argument -- no pool, no engine
    assert pool.fingerprint() == fingerprint_before


# -- 19. no mutation -----------------------------------------------------------------------------------------------


def test_19_no_mutation_of_analysis_on_repeated_calls():
    pool, f, process_std, obs, dv = _workload()
    query = make_material_program_query(["formulation-f1"], "process-std-190c", ("tensile_strength",))
    program_answer = analyze_program(pool, ENGINE, query)
    decision = evaluate_program(program_answer, (TENSILE_CRITERION,))
    audit = audit_program(decision)
    a1 = analyze_experiment_gaps(audit)
    a2 = analyze_experiment_gaps(audit)
    assert a1.gaps[0].observed.status == a2.gaps[0].observed.status
    assert a1.gaps[0].observed.categories == a2.gaps[0].observed.categories


# -- 20. no ranking/optimization fields ------------------------------------------------------------------------------


def test_20_no_ranking_or_optimization_fields():
    pool, f, process_std, obs, dv = _workload()
    analysis = _analysis_for(pool, ["f1", "f2"], (TENSILE_CRITERION,))
    forbidden = (
        "score", "rank", "ranking", "winner", "best", "recommended", "optimal",
        "priority", "utility", "cost", "expected_information_gain", "confidence_rank",
        "suggested_temperature", "suggested_experiment", "suggested_measurement",
        "next_experiment", "experiment_priority",
    )
    assert not any(hasattr(analysis, f) for f in forbidden)
    for gap in analysis.gaps:
        assert not any(hasattr(gap, f) for f in forbidden)
        assert not any(hasattr(gap.observed, f) for f in forbidden)
        assert not any(hasattr(gap.predicted, f) for f in forbidden)


# -- 21. criterion context preserved exactly ----------------------------------------------------------------------------


def test_21_criterion_context_preserved_exactly():
    pool, f, process_std, obs, dv = _workload()
    gap = _find(_analysis_for(pool, ["f1"], (VISCOSITY_CRITERION,)), "f1", "viscosity")
    assert gap.criterion_context == dict(VISCOSITY_CRITERION.context)
    assert gap.criterion is VISCOSITY_CRITERION


# -- 22. no experiment recommendation is generated ----------------------------------------------------------------------


def test_22_no_recommendation_text_anywhere():
    pool, f, process_std, obs, dv = _workload()
    analysis = _analysis_for(pool, ["f1"], (VISCOSITY_CRITERION,))
    for gap in analysis.gaps:
        for side in (gap.observed, gap.predicted):
            if side.reason:
                lowered = side.reason.lower()
                for banned_phrase in ("run another", "should measure", "recommend", "next experiment", "suggest"):
                    assert banned_phrase not in lowered


# -- 23. no experiment parameters are invented --------------------------------------------------------------------------


def test_23_available_contexts_are_only_ever_copied_from_existing_evidence():
    pool, f, process_std, obs, dv = _workload()
    gap = _find(_analysis_for(pool, ["f1"], (VISCOSITY_CRITERION,)), "f1", "viscosity")
    # Every available context must trace back to an actual observed value's content.
    observed_ids = gap.observed.supporting_ids
    assert observed_ids == (obs["f1_visc40"].id,)
    assert gap.observed.available_contexts[0]["temperature"] == 40  # copied from the real observation, not invented


# -- 24. available contexts distinguishable from criterion context ---------------------------------------------------------


def test_24_available_contexts_distinguishable_from_criterion_context():
    pool, f, process_std, obs, dv = _workload()
    gap = _find(_analysis_for(pool, ["f1"], (VISCOSITY_CRITERION,)), "f1", "viscosity")
    assert gap.criterion_context != gap.observed.available_contexts[0]
    assert gap.criterion_context["temperature"] == 25
    assert gap.observed.available_contexts[0]["temperature"] == 40


# -- taxonomy pin: exactly six descriptive categories, no more --------------------------------------------------------------


def test_taxonomy_is_exactly_six_descriptive_categories():
    assert ALL_GAP_CATEGORIES == (
        MEASUREMENT_CONFLICT, MODEL_DISAGREEMENT, MISSING_EVIDENCE,
        INCOMPARABLE_EVIDENCE, PREDICTION_WITHOUT_MEASUREMENT, MEASUREMENT_WITHOUT_PREDICTION,
    )
    assert len(ALL_GAP_CATEGORIES) == 6
    assert len(set(ALL_GAP_CATEGORIES)) == 6  # no duplicates
