"""Phase 29: comparability correction regression tests. Demonstrated
defect (Phase 28): `materials.analyze()` computed a flat spread across
viscosity measurements taken at different temperatures (850 mPa.s@25C,
1120 mPa.s@40C), implying a same-state disagreement that does not
exist. These tests pin the corrected behavior -- grouping by
comparison context (`materials/analysis.py::_comparison_context`) --
without special-casing "viscosity" anywhere.
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


def _pool():
    pool = EvidencePool()
    source = make_source(kind="lab_notebook", name="QC")
    pool.put_source(source)
    doc = make_document(source_id=source.id, raw_content="panel", retrieval_method="manual_entry", retrieved_at="2026-08-23T00:00:00Z")
    admit_document(pool, doc)
    pool.put_document(doc)
    process = make_referent(natural_key="process-injection-run-12", kind="process")
    admit_referent(pool, process)
    pool.put_referent(process)
    f1 = make_referent(natural_key="formulation-f1", kind="formulation")
    admit_referent(pool, f1)
    pool.put_referent(f1)
    return pool, doc, process, f1


def _add_obs(pool, doc, referent, process, locator, content):
    rec = make_record(document_id=doc.id, locator=locator, raw_content=locator)
    admit_record(pool, rec)
    pool.put_record(rec)
    obs = make_observation(record_ids=(rec.id,), extraction_method="human_transcription", content=content, confidence=1.0, extracted_at="2026-08-23T00:00:00Z")
    admit_observation(pool, obs)
    pool.put_observation(obs)
    rel = make_claimed_relationship(from_referent_id=referent.id, to_referent_id=process.id, type="tested_during", observation_id=obs.id, confidence=1.0)
    admit_claimed_relationship(pool, rel)
    pool.put_claimed_relationship(rel)
    return obs


def _add_pred(pool, referent, obs, method, content):
    dv = make_derived_value(derived_from=[obs.id], method=method, content=content, confidence=0.85, derived_at="2026-08-23T01:00:00Z")
    admit_derived_value(pool, dv)
    pool.put_derived_value(dv)
    g = make_derived_grounding(derived_value_id=dv.id, referent_ids=[referent.id])
    admit_derived_grounding(pool, g)
    pool.put_derived_grounding(g)
    return dv


# -- 1. Tensile conflict: existing 6 MPa spread preserved ------------------------------


def test_tensile_conflict_spread_unchanged():
    pool, doc, process, f1 = _pool()
    _add_obs(pool, doc, f1, process, "t1", {"property": "tensile_strength", "value": 82, "unit": "MPa"})
    _add_obs(pool, doc, f1, process, "t2", {"property": "tensile_strength", "value": 76, "unit": "MPa"})

    answer = analyze(pool, ENGINE, MaterialQuestion("formulation-f1", "tensile_strength"))
    assert answer.observed_disagreement.spread == 6
    assert answer.observed_disagreement.minimum == 76
    assert answer.observed_disagreement.maximum == 82
    assert len(answer.observed_comparison_groups) == 1
    # "unit" is part of the comparison context too (consistently "MPa" on
    # both observations here), not an empty context -- see
    # test_different_units_treated_as_different_context for why.
    assert dict(answer.observed_comparison_groups[0].context) == {"unit": "MPa"}


# -- 2. Tg conflict: existing 5C spread preserved ---------------------------------------


def test_tg_conflict_spread_unchanged():
    pool, doc, process, f1 = _pool()
    _add_obs(pool, doc, f1, process, "g1", {"property": "Tg", "value": 118, "unit": "C"})
    _add_obs(pool, doc, f1, process, "g2", {"property": "Tg", "value": 123, "unit": "C"})

    answer = analyze(pool, ENGINE, MaterialQuestion("formulation-f1", "Tg"))
    assert answer.observed_disagreement.spread == 5
    assert len(answer.observed_comparison_groups) == 1


# -- 3/4. Viscosity 25C vs 40C: no false same-state disagreement, both retained ---------


def test_viscosity_different_conditions_not_reported_as_single_disagreement():
    pool, doc, process, f1 = _pool()
    _add_obs(pool, doc, f1, process, "v1", {"property": "viscosity", "value": 850, "unit": "mPa.s", "temperature": 25, "temperature_unit": "C"})
    _add_obs(pool, doc, f1, process, "v2", {"property": "viscosity", "value": 1120, "unit": "mPa.s", "temperature": 40, "temperature_unit": "C"})

    answer = analyze(pool, ENGINE, MaterialQuestion("formulation-f1", "viscosity"))

    # The defect from Phase 28: this must NOT be Disagreement(850, 1120, 270).
    assert answer.observed_disagreement is None

    # Both observations remain present -- nothing discarded or merged.
    assert {o.content["value"] for o in answer.observed} == {850, 1120}

    # The full picture is visible: two distinct, non-comparable groups.
    assert len(answer.observed_comparison_groups) == 2
    contexts = {tuple(sorted(g.context.items())) for g in answer.observed_comparison_groups}
    assert contexts == {
        (("temperature", 25), ("temperature_unit", "C"), ("unit", "mPa.s")),
        (("temperature", 40), ("temperature_unit", "C"), ("unit", "mPa.s")),
    }
    for g in answer.observed_comparison_groups:
        assert len(g.values) == 1
        assert g.disagreement is None  # not enough data WITHIN this context to disagree


# -- 5. Provenance unchanged -------------------------------------------------------------


def test_provenance_unchanged_by_comparability_correction():
    pool, doc, process, f1 = _pool()
    obs = _add_obs(pool, doc, f1, process, "v1", {"property": "viscosity", "value": 850, "unit": "mPa.s", "temperature": 25, "temperature_unit": "C"})
    dv = _add_pred(pool, f1, obs, "model:viscosity_predictor", {"property": "viscosity", "predicted_value": 900, "unit": "mPa.s", "temperature": 25, "temperature_unit": "C"})

    answer = analyze(pool, ENGINE, MaterialQuestion("formulation-f1", "viscosity"))
    assert len(answer.predictions) == 1
    assert answer.predictions[0].derived_value.id == dv.id
    assert answer.predictions[0].provenance.observation_ids == (obs.id,)


# -- 6. Grounding unchanged --------------------------------------------------------------


def test_grounding_unchanged_by_comparability_correction():
    pool, doc, process, f1 = _pool()
    f2 = make_referent(natural_key="formulation-f2", kind="formulation")
    admit_referent(pool, f2)
    pool.put_referent(f2)

    obs1 = _add_obs(pool, doc, f1, process, "v1", {"property": "viscosity", "value": 850, "unit": "mPa.s", "temperature": 25, "temperature_unit": "C"})
    obs2 = _add_obs(pool, doc, f2, process, "v2", {"property": "viscosity", "value": 900, "unit": "mPa.s", "temperature": 25, "temperature_unit": "C"})
    dv1 = _add_pred(pool, f1, obs1, "model:viscosity_predictor", {"property": "viscosity", "predicted_value": 870, "unit": "mPa.s", "temperature": 25, "temperature_unit": "C"})
    dv2 = _add_pred(pool, f2, obs2, "model:viscosity_predictor", {"property": "viscosity", "predicted_value": 920, "unit": "mPa.s", "temperature": 25, "temperature_unit": "C"})

    answer_f1 = analyze(pool, ENGINE, MaterialQuestion("formulation-f1", "viscosity"))
    answer_f2 = analyze(pool, ENGINE, MaterialQuestion("formulation-f2", "viscosity"))
    assert {gp.derived_value.id for gp in answer_f1.predictions} == {dv1.id}
    assert {gp.derived_value.id for gp in answer_f2.predictions} == {dv2.id}


# -- 7. Conflicting predictions under different conditions not silently collapsed --------


def test_conflicting_predictions_under_different_conditions_not_collapsed():
    pool, doc, process, f1 = _pool()
    obs_25 = _add_obs(pool, doc, f1, process, "v1", {"property": "viscosity", "value": 850, "unit": "mPa.s", "temperature": 25, "temperature_unit": "C"})
    obs_40 = _add_obs(pool, doc, f1, process, "v2", {"property": "viscosity", "value": 1120, "unit": "mPa.s", "temperature": 40, "temperature_unit": "C"})
    _add_pred(pool, f1, obs_25, "model:viscosity_predictor", {"property": "viscosity", "predicted_value": 900, "unit": "mPa.s", "temperature": 25, "temperature_unit": "C"})
    _add_pred(pool, f1, obs_40, "model:viscosity_predictor", {"property": "viscosity", "predicted_value": 1150, "unit": "mPa.s", "temperature": 40, "temperature_unit": "C"})

    answer = analyze(pool, ENGINE, MaterialQuestion("formulation-f1", "viscosity"))
    assert len(answer.predictions) == 2
    assert answer.predicted_disagreement is None  # NOT Disagreement(900, 1150, 250)
    assert len(answer.predicted_comparison_groups) == 2
    for g in answer.predicted_comparison_groups:
        assert len(g.values) == 1
        assert g.disagreement is None


# -- Edge cases from Phase 29 §11 ---------------------------------------------------------


def test_different_models_same_condition_still_compared():
    """Model identity (DerivedValue.method) is never part of content --
    two different models predicting the SAME condition remain in one
    comparison group, exactly as before Phase 29."""
    pool, doc, process, f1 = _pool()
    obs = _add_obs(pool, doc, f1, process, "v1", {"property": "viscosity", "value": 850, "unit": "mPa.s", "temperature": 25, "temperature_unit": "C"})
    _add_pred(pool, f1, obs, "model:predictor_A", {"property": "viscosity", "predicted_value": 900, "unit": "mPa.s", "temperature": 25, "temperature_unit": "C"})
    _add_pred(pool, f1, obs, "model:predictor_B", {"property": "viscosity", "predicted_value": 870, "unit": "mPa.s", "temperature": 25, "temperature_unit": "C"})

    answer = analyze(pool, ENGINE, MaterialQuestion("formulation-f1", "viscosity"))
    assert len(answer.predicted_comparison_groups) == 1
    assert answer.predicted_disagreement is not None
    assert answer.predicted_disagreement.spread == 30


def test_condition_key_present_on_one_observation_absent_on_other():
    """Conservative choice (Phase 29 §11): a missing condition key is
    NOT treated as matching a present one -- these must NOT be grouped
    together even though only one of the two carries 'temperature'."""
    pool, doc, process, f1 = _pool()
    _add_obs(pool, doc, f1, process, "v1", {"property": "viscosity", "value": 850, "unit": "mPa.s", "temperature": 25, "temperature_unit": "C"})
    _add_obs(pool, doc, f1, process, "v2", {"property": "viscosity", "value": 900, "unit": "mPa.s"})  # no temperature recorded

    answer = analyze(pool, ENGINE, MaterialQuestion("formulation-f1", "viscosity"))
    assert len(answer.observed_comparison_groups) == 2
    assert answer.observed_disagreement is None


def test_different_units_treated_as_different_context():
    """Different units are also part of the comparison context (§11) --
    comparing 82 MPa against 82 psi as if same-state would be wrong;
    no unit conversion is performed or assumed."""
    pool, doc, process, f1 = _pool()
    _add_obs(pool, doc, f1, process, "t1", {"property": "tensile_strength", "value": 82, "unit": "MPa"})
    _add_obs(pool, doc, f1, process, "t2", {"property": "tensile_strength", "value": 82, "unit": "psi"})

    answer = analyze(pool, ENGINE, MaterialQuestion("formulation-f1", "tensile_strength"))
    assert len(answer.observed_comparison_groups) == 2
    assert answer.observed_disagreement is None


# -- 8/9/10: existing Phase 27 tests, insertion-order, PYTHONHASHSEED -------------------
# Covered by tests/test_materials_consumer.py (unmodified, all still passing) and its
# existing test_deterministic_across_insertion_order / test_deterministic_across_hash_seeds.
