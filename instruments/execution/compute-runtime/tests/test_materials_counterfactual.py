"""Phase 58: materials.counterfactual -- pure counterfactual state
transition. Small focused test set (build-more-test-less mode):
prediction-level equivalence between an actual update and a matching
counterfactual projection, deterministic repetition, distinct
hypothetical values producing distinct states, source-state
immutability, EvidencePool isolation, projected-state prediction
reproducibility, correct model-state-key resolution, and PYTHONHASHSEED
determinism.
"""

from evidence.admission import admit_document, admit_record, admit_referent
from evidence.pool import EvidencePool
from evidence.types import make_document, make_record, make_referent, make_source
from materials.campaign import assemble_experimental_campaign
from materials.candidates import generate_candidates
from materials.counterfactual import project_update
from materials.decision import make_criterion
from materials.design import assemble_experimental_design
from materials.evaluation import evaluate_candidates
from materials.information import ESTIMATED, NOT_DETERMINABLE, estimate_information_value
from materials.iteration import reevaluate_program
from materials.model_state import EMPTY_MODEL_STATE, ModelStateInformationValueModel, predict, update
from materials.plan import assemble_experiment_plan
from materials.program import make_material_program_query
from materials.results import admit_experimental_result, make_experimental_result
from materials.selection import SelectionPolicy, select_candidates
from materials.trajectory import compare_predictions
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
    doc = make_document(source_id=source.id, raw_content="panel", retrieval_method="manual_entry", retrieved_at="2026-08-24T00:00:00Z")
    admit_document(pool, doc)
    pool.put_document(doc)
    process = make_referent(natural_key="process-std-190c", kind="process")
    admit_referent(pool, process)
    pool.put_referent(process)
    f1 = make_referent(natural_key="formulation-f1", kind="formulation")
    admit_referent(pool, f1)
    pool.put_referent(f1)

    query = make_material_program_query(["formulation-f1"], "process-std-190c", ("tensile_strength",))
    iteration = reevaluate_program(pool, ENGINE, query, (TENSILE_CRITERION,))
    candidates = generate_candidates(iteration.specification)
    candidate = next(c for c in candidates.candidates if c.property == "tensile_strength")

    evaluations = evaluate_candidates(candidates)
    selection = select_candidates(evaluations, ALLOW_ALL)
    plan = assemble_experiment_plan(selection)
    design = assemble_experimental_design(plan)
    campaign = assemble_experimental_campaign(design)
    entry = next(e for e in campaign.entries if e.candidate_id == candidate.id)

    return pool, doc, iteration, candidate, campaign, entry


def _admit_result(pool, doc, campaign, entry, locator, value):
    rec = make_record(document_id=doc.id, locator=locator, raw_content=locator)
    admit_record(pool, rec)
    pool.put_record(rec)
    result = make_experimental_result(
        campaign, entry, content={"property": "tensile_strength", "value": value, "unit": "MPa"},
        record_id=rec.id, extracted_at="2026-08-24T02:00:00Z",
    extraction_method="measurement:campaign_execution")
    observation, _ = admit_experimental_result(pool, result, confidence=1.0)
    return result, observation


# -- 1. actual update and counterfactual projection: identical PREDICTIONS for identical value ------------


def test_1_actual_and_counterfactual_prediction_equivalence():
    pool, doc, iteration, candidate, campaign, entry = _setup()
    result, observation = _admit_result(pool, doc, campaign, entry, "ts-80", 80)

    actual_state = update(EMPTY_MODEL_STATE, candidate, result, observation)
    counterfactual_state = project_update(EMPTY_MODEL_STATE, candidate, 80)

    # The two ModelStates are NOT the same object by content -- a real
    # observation and a hypothetical one must never be indistinguishable.
    assert actual_state.id != counterfactual_state.id

    # But predict() -- which reads only Sample.value, never
    # Sample.observation_id -- reports IDENTICAL numbers from both.
    actual_prediction = predict(actual_state, candidate)
    counterfactual_prediction = predict(counterfactual_state, candidate)
    assert actual_prediction.predicted_value == counterfactual_prediction.predicted_value == 80.0
    assert actual_prediction.uncertainty == counterfactual_prediction.uncertainty is None
    assert actual_prediction.sample_count == counterfactual_prediction.sample_count == 1

    # Each sample's identity remains honestly distinguishable.
    real_sample = next(iter(actual_state.samples.values()))[0]
    hypothetical_sample = next(iter(counterfactual_state.samples.values()))[0]
    assert real_sample.observation_id == observation.id
    assert hypothetical_sample.observation_id.startswith("hypothetical:")
    assert hypothetical_sample.observation_id != real_sample.observation_id


# -- 2. repeated projection is deterministic -----------------------------------------------------------


def test_2_repeated_projection_deterministic():
    pool, doc, iteration, candidate, campaign, entry = _setup()
    a = project_update(EMPTY_MODEL_STATE, candidate, 80)
    b = project_update(EMPTY_MODEL_STATE, candidate, 80)
    assert a.id == b.id
    assert a == b


# -- 3. distinct hypothetical values produce distinct states ----------------------------------------------


def test_3_distinct_hypothetical_values_distinct_states():
    pool, doc, iteration, candidate, campaign, entry = _setup()
    s80 = project_update(EMPTY_MODEL_STATE, candidate, 80)
    s85 = project_update(EMPTY_MODEL_STATE, candidate, 85)
    s90 = project_update(EMPTY_MODEL_STATE, candidate, 90)
    assert len({s80.id, s85.id, s90.id}) == 3

    p80, p85, p90 = predict(s80, candidate), predict(s85, candidate), predict(s90, candidate)
    assert p80.predicted_value == 80.0
    assert p85.predicted_value == 85.0
    assert p90.predicted_value == 90.0

    # Phase 56's existing compare_predictions works unmodified across
    # counterfactual predictions -- no new comparison math.
    delta = compare_predictions(p80, p90)
    assert delta.delta_predicted_value == 10.0


# -- 4. source state remains unchanged; EvidencePool isolation ---------------------------------------------


def test_4_source_state_and_pool_isolation():
    pool, doc, iteration, candidate, campaign, entry = _setup()
    before_repr = repr(EMPTY_MODEL_STATE)
    fingerprint_before = pool.fingerprint()

    projected = project_update(EMPTY_MODEL_STATE, candidate, 90)

    assert repr(EMPTY_MODEL_STATE) == before_repr
    assert predict(EMPTY_MODEL_STATE, candidate).sample_count == 0  # untouched
    assert pool.fingerprint() == fingerprint_before  # no admission, no fingerprint change
    assert projected.id != EMPTY_MODEL_STATE.id  # the state genuinely did change


# -- 5/6. projected-state prediction reproducibility; model-state-key correctness ---------------------------


def test_5_6_projected_prediction_reproducible_and_correct_key():
    pool, doc, iteration, candidate, campaign, entry = _setup()
    projected = project_update(EMPTY_MODEL_STATE, candidate, 90)

    p1 = predict(projected, candidate)
    p2 = predict(projected, candidate)
    assert p1 == p2  # reproducible

    from materials.model_state import resolve_model_state_key
    expected_key = resolve_model_state_key(candidate.formulation.id, candidate.property, candidate.target_context)
    assert p1.model_state_key == expected_key
    assert p1.state_id == projected.id
    assert p1.predicted_value == 90.0


# -- 7. information-value coexistence across a local neighborhood of projected states (sec.7/8/13) --------


def test_7_information_value_across_projected_neighborhood():
    pool, doc, iteration, candidate, campaign, entry = _setup()
    result1, obs1 = _admit_result(pool, doc, campaign, entry, "ts-80", 80)
    state1 = update(EMPTY_MODEL_STATE, candidate, result1, obs1)  # one real sample already present

    projected_80 = project_update(state1, candidate, 80)
    projected_90 = project_update(state1, candidate, 90)

    iv_actual = estimate_information_value(candidate, iteration, ModelStateInformationValueModel(state1))
    iv_cf_80 = estimate_information_value(candidate, iteration, ModelStateInformationValueModel(projected_80))
    iv_cf_90 = estimate_information_value(candidate, iteration, ModelStateInformationValueModel(projected_90))

    assert iv_actual.estimate_status == NOT_DETERMINABLE  # 1 sample -- no defined variance yet
    assert iv_cf_80.estimate_status == ESTIMATED
    assert iv_cf_90.estimate_status == ESTIMATED
    assert iv_cf_80.estimate == 0.0  # [80, 80] -- zero variance
    assert iv_cf_90.estimate == 50.0  # sample variance (n-1) of [80, 90]


# -- 8. deterministic behavior across PYTHONHASHSEED -----------------------------------------------------------


def test_8_pythonhashseed_determinism():
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    script = (
        "from evidence.types import make_referent\n"
        "from materials.candidates import make_action_candidate\n"
        "from materials.counterfactual import project_update\n"
        "from materials.model_state import EMPTY_MODEL_STATE, predict\n"
        "f1 = make_referent(natural_key='formulation-f1', kind='formulation')\n"
        "candidate = make_action_candidate(action_class='measurement:repeat', requirement_ids=('r1',), "
        "formulation=f1, property='tensile_strength', role='OBSERVED', target_context={})\n"
        "s1 = project_update(EMPTY_MODEL_STATE, candidate, 80)\n"
        "s2 = project_update(s1, candidate, 90)\n"
        "p2 = predict(s2, candidate)\n"
        "sample = next(iter(s1.samples.values()))[0]\n"
        "print(s1.id, s2.id, p2.predicted_value, p2.uncertainty, sample.observation_id)\n"
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
    assert len(outputs) == 1, f"counterfactual results differed across PYTHONHASHSEED values: {outputs}"
