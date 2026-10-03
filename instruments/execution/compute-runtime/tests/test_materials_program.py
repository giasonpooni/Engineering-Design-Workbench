"""Phase 31: materials.program -- the formulation x process x property
composition layer built on top of materials.analysis (Phase 27/29),
exercised against the Formulation F1-F4 / process-std / process-hot
program Phase 30 validated by hand, plus the process-membership edge
cases (none / multiple) Phase 30 did not need but Phase 31 must handle
deterministically rather than by guessing.
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
from materials.program import analyze_program, make_material_program_query
from retrieval.engine import DeterministicRetrievalEngine

ENGINE = DeterministicRetrievalEngine()


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
    process_hot = make_referent(natural_key="process-hot-220c", kind="process")
    formulations = {k: make_referent(natural_key=f"formulation-{k}", kind="formulation") for k in ("f1", "f2", "f3", "f4", "f5", "f6")}
    all_refs = [process_std, process_hot] + list(formulations.values())
    for ref in (all_refs if order == "normal" else list(reversed(all_refs))):
        admit_referent(pool, ref)
        pool.put_referent(ref)

    return pool, doc, tp_doc, process_std, process_hot, formulations


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


def _full_program_pool(order="normal"):
    pool, doc, tp_doc, process_std, process_hot, f = _base(order)

    obs = {}
    obs["f1_ts_qc"] = _add_obs(pool, doc, f["f1"], process_std, "f1-ts-qc", {"property": "tensile_strength", "value": 82, "unit": "MPa"})
    obs["f1_ts_tp"] = _add_obs(pool, tp_doc, f["f1"], process_std, "f1-ts-tp", {"property": "tensile_strength", "value": 79, "unit": "MPa"}, extracted_at="2026-08-23T00:30:00Z")
    dv_f1_a = _add_pred(pool, f["f1"], obs["f1_ts_qc"], "model:tensile_predictor_A", {"property": "tensile_strength", "predicted_value": 80, "unit": "MPa"})
    dv_f1_b = _add_pred(pool, f["f1"], obs["f1_ts_tp"], "model:tensile_predictor_B", {"property": "tensile_strength", "predicted_value": 84, "unit": "MPa"})
    obs["f1_mod"] = _add_obs(pool, doc, f["f1"], process_std, "f1-mod", {"property": "modulus", "value": 2.8, "unit": "GPa"})

    obs["f2_ts"] = _add_obs(pool, doc, f["f2"], process_std, "f2-ts", {"property": "tensile_strength", "value": 79, "unit": "MPa"})
    obs["f2_mod"] = _add_obs(pool, doc, f["f2"], process_std, "f2-mod", {"property": "modulus", "value": 3.1, "unit": "GPa"})

    obs["f3_ts"] = _add_obs(pool, doc, f["f3"], process_hot, "f3-ts", {"property": "tensile_strength", "value": 86, "unit": "MPa"})
    dv_f3_a = _add_pred(pool, f["f3"], obs["f3_ts"], "model:tensile_predictor_A", {"property": "tensile_strength", "predicted_value": 84, "unit": "MPa"})
    dv_f3_b = _add_pred(pool, f["f3"], obs["f3_ts"], "model:tensile_predictor_B", {"property": "tensile_strength", "predicted_value": 89, "unit": "MPa"})

    obs["f4_ts"] = _add_obs(pool, doc, f["f4"], process_hot, "f4-ts", {"property": "tensile_strength", "value": 81, "unit": "MPa"})

    # F5: no process relationship at all.
    obs["f5_ts"] = _add_obs(pool, doc, f["f5"], None, "f5-ts", {"property": "tensile_strength", "value": 75, "unit": "MPa"})

    # F6: TWO process relationships (both std and hot).
    obs["f6_ts"] = _add_obs(pool, doc, f["f6"], process_std, "f6-ts", {"property": "tensile_strength", "value": 83, "unit": "MPa"})
    rel_f6_hot = make_claimed_relationship(from_referent_id=f["f6"].id, to_referent_id=process_hot.id, type="also_tested_during", observation_id=obs["f6_ts"].id, confidence=1.0)
    admit_claimed_relationship(pool, rel_f6_hot)
    pool.put_claimed_relationship(rel_f6_hot)

    return pool, f, process_std, process_hot, obs, dict(
        dv_f1_a=dv_f1_a, dv_f1_b=dv_f1_b, dv_f3_a=dv_f3_a, dv_f3_b=dv_f3_b,
    )


# -- 1. single formulation / single property -------------------------------------------


def test_single_formulation_single_property():
    pool, f, process_std, process_hot, obs, dv = _full_program_pool()
    query = make_material_program_query(["formulation-f2"], "process-std-190c", ["modulus"])
    answer = analyze_program(pool, ENGINE, query)

    assert len(answer.formulations) == 1
    entry = answer.formulations[0]
    assert entry.formulation.natural_key == "formulation-f2"
    assert len(entry.properties) == 1
    assert entry.properties[0].property == "modulus"
    assert entry.properties[0].answer.observed[0].content["value"] == 3.1


# -- 2. multiple formulations ------------------------------------------------------------


def test_multiple_formulations():
    pool, f, process_std, process_hot, obs, dv = _full_program_pool()
    query = make_material_program_query(["formulation-f1", "formulation-f2"], "process-std-190c", ["tensile_strength"])
    answer = analyze_program(pool, ENGINE, query)
    assert {e.formulation.natural_key for e in answer.formulations} == {"formulation-f1", "formulation-f2"}


# -- 3. multiple properties ---------------------------------------------------------------


def test_multiple_properties():
    pool, f, process_std, process_hot, obs, dv = _full_program_pool()
    query = make_material_program_query(["formulation-f1"], "process-std-190c", ["tensile_strength", "modulus"])
    answer = analyze_program(pool, ENGINE, query)
    entry = answer.formulations[0]
    assert {pe.property for pe in entry.properties} == {"tensile_strength", "modulus"}


# -- 4. process filtering -----------------------------------------------------------------


def test_process_filtering_std_matches_only_f1_f2():
    pool, f, process_std, process_hot, obs, dv = _full_program_pool()
    query = make_material_program_query(["formulation-f1", "formulation-f2", "formulation-f3", "formulation-f4"], "process-std-190c", ["tensile_strength"])
    answer = analyze_program(pool, ENGINE, query)
    matching = {e.formulation.natural_key for e in answer.formulations if e.process_association.matches_queried_process}
    assert matching == {"formulation-f1", "formulation-f2"}


def test_process_filtering_hot_matches_only_f3_f4():
    pool, f, process_std, process_hot, obs, dv = _full_program_pool()
    query = make_material_program_query(["formulation-f1", "formulation-f2", "formulation-f3", "formulation-f4"], "process-hot-220c", ["tensile_strength"])
    answer = analyze_program(pool, ENGINE, query)
    matching = {e.formulation.natural_key for e in answer.formulations if e.process_association.matches_queried_process}
    assert matching == {"formulation-f3", "formulation-f4"}


def test_non_matching_formulations_still_present_not_silently_dropped():
    pool, f, process_std, process_hot, obs, dv = _full_program_pool()
    query = make_material_program_query(["formulation-f1", "formulation-f3"], "process-std-190c", ["tensile_strength"])
    answer = analyze_program(pool, ENGINE, query)
    # F3 was requested but doesn't match process-std -- it must still appear, flagged False.
    by_key = {e.formulation.natural_key: e for e in answer.formulations}
    assert by_key["formulation-f1"].process_association.matches_queried_process is True
    assert by_key["formulation-f3"].process_association.matches_queried_process is False


# -- 5. formulation with no process relationship -------------------------------------------


def test_formulation_with_no_process_relationship():
    """F5 has an Observation but NO ClaimedRelationship at all --
    process_association correctly reports zero processes, but this
    also means `materials.analyze()`'s own retrieval (inherited
    unmodified, not something this layer controls) cannot reach F5's
    observation either: DeterministicRetrievalEngine only finds an
    Observation via a ClaimedRelationship between two visited
    referents, and F5 has none. Both facts stem from the same root
    cause -- no relationship exists -- and are reported honestly,
    not papered over."""
    pool, f, process_std, process_hot, obs, dv = _full_program_pool()
    query = make_material_program_query(["formulation-f5"], "process-std-190c", ["tensile_strength"])
    answer = analyze_program(pool, ENGINE, query)
    entry = answer.formulations[0]
    assert entry.process_association.processes == ()
    assert entry.process_association.matches_queried_process is False
    assert entry.properties[0].answer.observed == ()


# -- 6. formulation with multiple process relationships --------------------------------------


def test_formulation_with_multiple_process_relationships():
    pool, f, process_std, process_hot, obs, dv = _full_program_pool()
    query = make_material_program_query(["formulation-f6"], "process-hot-220c", ["tensile_strength"])
    answer = analyze_program(pool, ENGINE, query)
    entry = answer.formulations[0]
    # Both relationships preserved -- neither silently selected over the other.
    assert {p.natural_key for p in entry.process_association.processes} == {"process-std-190c", "process-hot-220c"}
    assert entry.process_association.matches_queried_process is True  # hot IS among its processes

    query_std = make_material_program_query(["formulation-f6"], "process-std-190c", ["tensile_strength"])
    answer_std = analyze_program(pool, ENGINE, query_std)
    assert answer_std.formulations[0].process_association.matches_queried_process is True  # std is ALSO among its processes


# -- 7/8. conflicting observations / conflicting predictions -----------------------------------


def test_conflicting_observations_preserved():
    pool, f, process_std, process_hot, obs, dv = _full_program_pool()
    query = make_material_program_query(["formulation-f1"], "process-std-190c", ["tensile_strength"])
    answer = analyze_program(pool, ENGINE, query)
    ts = answer.formulations[0].properties[0].answer
    assert {o.content["value"] for o in ts.observed} == {82, 79}
    assert ts.observed_disagreement is not None
    assert ts.observed_disagreement.spread == 3


def test_conflicting_predictions_preserved():
    pool, f, process_std, process_hot, obs, dv = _full_program_pool()
    query = make_material_program_query(["formulation-f3"], "process-hot-220c", ["tensile_strength"])
    answer = analyze_program(pool, ENGINE, query)
    ts = answer.formulations[0].properties[0].answer
    assert {gp.derived_value.content["predicted_value"] for gp in ts.predictions} == {84, 89}
    assert ts.predicted_disagreement is not None
    assert ts.predicted_disagreement.spread == 5


# -- 9/10. model disagreement over one observation vs different observations -------------------


def test_model_disagreement_over_one_observation_distinguishable_from_measurement_disagreement():
    """F1: two predictions trace to DIFFERENT observations (measurement
    disagreement propagated into predictions). F3: two predictions
    trace to the SAME observation (pure model disagreement). This
    distinction must survive program-level composition unchanged."""
    pool, f, process_std, process_hot, obs, dv = _full_program_pool()
    query = make_material_program_query(["formulation-f1", "formulation-f3"], "process-std-190c", ["tensile_strength"])
    answer = analyze_program(pool, ENGINE, query)
    by_key = {e.formulation.natural_key: e.properties[0].answer for e in answer.formulations}

    f1_ts = by_key["formulation-f1"]
    f1_provenance_sets = [gp.provenance.observation_ids for gp in f1_ts.predictions]
    assert len(f1_provenance_sets) == 2
    assert set(f1_provenance_sets[0]).isdisjoint(set(f1_provenance_sets[1])), (
        "F1's two predictions must trace to DIFFERENT observations"
    )

    f3_ts = by_key["formulation-f3"]
    f3_provenance_sets = [gp.provenance.observation_ids for gp in f3_ts.predictions]
    assert len(f3_provenance_sets) == 2
    assert f3_provenance_sets[0] == f3_provenance_sets[1] == (obs["f3_ts"].id,), (
        "F3's two predictions must trace to the SAME single observation"
    )


# -- 11. provenance preservation -----------------------------------------------------------------


def test_provenance_preserved_through_program_composition():
    pool, f, process_std, process_hot, obs, dv = _full_program_pool()
    query = make_material_program_query(["formulation-f1"], "process-std-190c", ["tensile_strength"])
    answer = analyze_program(pool, ENGINE, query)
    ts = answer.formulations[0].properties[0].answer
    by_value = {gp.derived_value.content["predicted_value"]: gp for gp in ts.predictions}
    assert by_value[80].provenance.observation_ids == (obs["f1_ts_qc"].id,)
    assert by_value[84].provenance.observation_ids == (obs["f1_ts_tp"].id,)


# -- 12. cross-formulation isolation -------------------------------------------------------------


def test_cross_formulation_isolation():
    pool, f, process_std, process_hot, obs, dv = _full_program_pool()
    query = make_material_program_query(["formulation-f1", "formulation-f2", "formulation-f3", "formulation-f4"], "process-std-190c", ["tensile_strength"])
    answer = analyze_program(pool, ENGINE, query)
    prediction_sets = {
        e.formulation.natural_key: {gp.derived_value.id for gp in e.properties[0].answer.predictions}
        for e in answer.formulations
    }
    keys = list(prediction_sets)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            assert prediction_sets[a].isdisjoint(prediction_sets[b])


# -- 13. cross-property isolation ----------------------------------------------------------------


def test_cross_property_isolation():
    pool, f, process_std, process_hot, obs, dv = _full_program_pool()
    query = make_material_program_query(["formulation-f1"], "process-std-190c", ["tensile_strength", "modulus"])
    answer = analyze_program(pool, ENGINE, query)
    entry = answer.formulations[0]
    ts = next(pe.answer for pe in entry.properties if pe.property == "tensile_strength")
    mod = next(pe.answer for pe in entry.properties if pe.property == "modulus")
    assert {o.content["value"] for o in ts.observed} == {82, 79}
    assert {o.content["value"] for o in mod.observed} == {2.8}


# -- 14. insertion-order determinism -------------------------------------------------------------


def test_insertion_order_determinism():
    pool_a, f_a, ps_a, ph_a, obs_a, dv_a = _full_program_pool("normal")
    pool_b, f_b, ps_b, ph_b, obs_b, dv_b = _full_program_pool("shuffled")

    query = make_material_program_query(["formulation-f1", "formulation-f2", "formulation-f3", "formulation-f6"], "process-std-190c", ["tensile_strength", "modulus"])
    answer_a = analyze_program(pool_a, ENGINE, query)
    answer_b = analyze_program(pool_b, ENGINE, query)

    keys_a = [e.formulation.natural_key for e in answer_a.formulations]
    keys_b = [e.formulation.natural_key for e in answer_b.formulations]
    assert keys_a == keys_b  # formulation ordering follows the (sorted) query, not insertion order

    for ea, eb in zip(answer_a.formulations, answer_b.formulations):
        assert ea.formulation.id == eb.formulation.id
        assert ea.process_association.matches_queried_process == eb.process_association.matches_queried_process
        assert {p.id for p in ea.process_association.processes} == {p.id for p in eb.process_association.processes}
        props_a = [pe.property for pe in ea.properties]
        props_b = [pe.property for pe in eb.properties]
        assert props_a == props_b  # property ordering follows the (sorted) query
        for pa, pb in zip(ea.properties, eb.properties):
            assert {o.id for o in pa.answer.observed} == {o.id for o in pb.answer.observed}
            assert {gp.derived_value.id for gp in pa.answer.predictions} == {gp.derived_value.id for gp in pb.answer.predictions}
            assert pa.answer.observed_disagreement == pb.answer.observed_disagreement


# -- 15. PYTHONHASHSEED determinism ---------------------------------------------------------------


def test_pythonhashseed_determinism():
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
        "f2 = make_referent(natural_key='formulation-f2', kind='formulation')\n"
        "pool.put_referent(f2)\n"
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
        "rel2 = make_claimed_relationship(from_referent_id=f2.id, to_referent_id=process.id, "
        "type='tested_during', observation_id=obs2.id, confidence=1.0)\n"
        "pool.put_claimed_relationship(rel2)\n"
        "dv = make_derived_value(derived_from=[obs1.id], method='model:tensile_predictor_A', "
        "content={'property': 'tensile_strength', 'predicted_value': 80, 'unit': 'MPa'}, confidence=0.85, derived_at='t')\n"
        "pool.put_derived_value(dv)\n"
        "g = make_derived_grounding(derived_value_id=dv.id, referent_ids=[f1.id])\n"
        "pool.put_derived_grounding(g)\n"
        "engine = DeterministicRetrievalEngine()\n"
        "query = make_material_program_query(['formulation-f2', 'formulation-f1'], 'process-std-190c', ['tensile_strength'])\n"
        "answer = analyze_program(pool, engine, query)\n"
        "print([e.formulation.natural_key for e in answer.formulations])\n"
        "print([(p.property, sorted(o.content['value'] for o in p.answer.observed)) for e in answer.formulations for p in e.properties])\n"
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
    assert len(outputs) == 1, f"analyze_program differed across PYTHONHASHSEED values: {outputs}"


# -- 17/18. unknown formulation / unknown process -------------------------------------------------


def test_unknown_formulation_raises_key_error():
    pool, f, process_std, process_hot, obs, dv = _full_program_pool()
    query = make_material_program_query(["formulation-does-not-exist"], "process-std-190c", ["tensile_strength"])
    with pytest.raises(KeyError):
        analyze_program(pool, ENGINE, query)


def test_unknown_process_raises_key_error():
    pool, f, process_std, process_hot, obs, dv = _full_program_pool()
    query = make_material_program_query(["formulation-f1"], "process-does-not-exist", ["tensile_strength"])
    with pytest.raises(KeyError):
        analyze_program(pool, ENGINE, query)


# -- query normalization ----------------------------------------------------------------------------


def test_query_normalization_dedup_and_sort():
    query = make_material_program_query(["formulation-f2", "formulation-f1", "formulation-f1"], "process-std-190c", ["modulus", "tensile_strength"])
    assert query.formulation_natural_keys == ("formulation-f1", "formulation-f2")
    assert query.properties == ("modulus", "tensile_strength")
