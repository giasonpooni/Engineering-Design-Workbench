"""Phase 52/53: materials.model_state -- the first dynamic-state layer,
plus Phase 53's state-resolution semantics. Small focused test set:
initial construction, deterministic identity, prediction from state,
observation update producing a new state, historical-state immutability,
prediction's dependence on state, uncertainty changing only when
mathematically warranted, the InformationValueModel seam consuming the
model's own output correctly across two different states, and (Phase 53)
`resolve_model_state_key` semantics, context separation, and
update/predict consistency.
"""

from evidence.admission import (
    admit_claimed_relationship, admit_document, admit_observation, admit_record, admit_referent,
)
from evidence.pool import EvidencePool
from evidence.types import (
    make_claimed_relationship, make_document, make_observation, make_record, make_referent, make_source,
)
from materials.campaign import assemble_experimental_campaign
from materials.candidates import generate_candidates
from materials.counterfactual import project_update
from materials.decision import make_criterion
from materials.design import assemble_experimental_design
from materials.evaluation import evaluate_candidates
from materials.information import ESTIMATED, NOT_DETERMINABLE, estimate_information_value
from materials.iteration import reevaluate_program
from materials.model_state import (
    EMPTY_MODEL_STATE, ModelStateInformationValueModel, Sample, make_model_state, predict,
    resolve_model_state_key, update,
)
from materials.plan import assemble_experiment_plan
from materials.program import make_material_program_query
from materials.results import admit_experimental_result, make_experimental_result
from materials.selection import SelectionPolicy, select_candidates
from retrieval.engine import DeterministicRetrievalEngine

ENGINE = DeterministicRetrievalEngine()
TENSILE_CRITERION = make_criterion("tensile_strength", ">=", 80)
HARDNESS_CRITERION = make_criterion("hardness", ">=", 50)  # never measured

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

    for locator, value in (("ts-a", 78), ("ts-b", 84)):
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

    query = make_material_program_query(["formulation-f1"], "process-std-190c", ("tensile_strength", "hardness"))
    iteration = reevaluate_program(pool, ENGINE, query, (TENSILE_CRITERION, HARDNESS_CRITERION))
    candidates = generate_candidates(iteration.specification)
    conflict_candidate = next(c for c in candidates.candidates if c.action_class == "measurement:repeat")
    hardness_candidate = next(c for c in candidates.candidates if c.property == "hardness")

    evaluations = evaluate_candidates(candidates)
    selection = select_candidates(evaluations, ALLOW_ALL)
    plan = assemble_experiment_plan(selection)
    design = assemble_experimental_design(plan)
    campaign = assemble_experimental_campaign(design)
    entry = next(e for e in campaign.entries if e.candidate_id == conflict_candidate.id)
    hardness_entry = next(e for e in campaign.entries if e.candidate_id == hardness_candidate.id)

    return pool, doc, iteration, conflict_candidate, campaign, entry, hardness_entry, hardness_candidate


def _admit_result(pool, doc, campaign, entry, locator, value):
    rec = make_record(document_id=doc.id, locator=locator, raw_content=locator)
    admit_record(pool, rec)
    pool.put_record(rec)
    result = make_experimental_result(
        campaign, entry, content={"property": "tensile_strength", "value": value, "unit": "MPa"},
        record_id=rec.id, extracted_at="2026-08-23T02:00:00Z",
    extraction_method="measurement:campaign_execution")
    observation, _ = admit_experimental_result(pool, result, confidence=1.0)
    return result, observation


# -- 1/2. initial model state construction + deterministic identity -----------------------------------


def test_1_2_initial_state_construction_and_deterministic_identity():
    a = make_model_state({})
    b = make_model_state({})
    assert a.id == b.id == EMPTY_MODEL_STATE.id
    assert a.samples == {}

    key = "x"
    c = make_model_state({key: (Sample(1.0, "o1"), Sample(2.0, "o2"))})
    d = make_model_state({key: (Sample(2.0, "o2"), Sample(1.0, "o1"))})  # different insertion order
    assert c.id == d.id  # order-independent


# -- 3/6. prediction from state, and prediction depends on the state ------------------------------------


def test_3_6_prediction_from_state_and_depends_on_state():
    pool, doc, iteration, candidate, campaign, entry, hardness_entry, hardness_candidate = _setup()
    empty_prediction = predict(EMPTY_MODEL_STATE, candidate)
    assert empty_prediction.sample_count == 0
    assert empty_prediction.predicted_value is None
    assert empty_prediction.uncertainty is None
    assert empty_prediction.state_id == EMPTY_MODEL_STATE.id

    result1, obs1 = _admit_result(pool, doc, campaign, entry, "ts-80", 80)
    state1 = update(EMPTY_MODEL_STATE, candidate, result1, obs1)
    prediction1 = predict(state1, candidate)
    assert prediction1.sample_count == 1
    assert prediction1.predicted_value == 80.0
    assert prediction1.uncertainty is None  # a single sample has no defined variance
    assert prediction1.state_id == state1.id != EMPTY_MODEL_STATE.id


# -- 4/5. observation update produces a NEW state; historical state unchanged ---------------------------


def test_4_5_update_produces_new_state_historical_unchanged():
    pool, doc, iteration, candidate, campaign, entry, hardness_entry, hardness_candidate = _setup()
    result1, obs1 = _admit_result(pool, doc, campaign, entry, "ts-80", 80)
    state1 = update(EMPTY_MODEL_STATE, candidate, result1, obs1)
    before_state0_repr = repr(EMPTY_MODEL_STATE)

    result2, obs2 = _admit_result(pool, doc, campaign, entry, "ts-90", 90)
    state2 = update(state1, candidate, result2, obs2)

    assert state2.id != state1.id
    assert repr(EMPTY_MODEL_STATE) == before_state0_repr  # never mutated
    assert predict(state1, candidate).sample_count == 1  # state1 itself never changed by the later update
    assert predict(state2, candidate).sample_count == 2


# -- 7. uncertainty changes only when mathematically warranted --------------------------------------------


def test_7_uncertainty_changes_only_when_warranted():
    pool, doc, iteration, candidate, campaign, entry, hardness_entry, hardness_candidate = _setup()
    result1, obs1 = _admit_result(pool, doc, campaign, entry, "ts-80", 80)
    state1 = update(EMPTY_MODEL_STATE, candidate, result1, obs1)
    result2, obs2 = _admit_result(pool, doc, campaign, entry, "ts-90", 90)
    state2 = update(state1, candidate, result2, obs2)

    prediction2 = predict(state2, candidate)
    assert prediction2.predicted_value == 85.0
    assert prediction2.uncertainty == 50.0  # sample variance (n-1) of [80, 90]

    # An update to a DIFFERENT (formulation, property, context) cell must not
    # change this candidate's prediction at all -- same state content for the
    # tensile_strength/f1 cell, so the same uncertainty, not a guessed drift.
    rec = make_record(document_id=doc.id, locator="hard-a", raw_content="hard-a")
    admit_record(pool, rec)
    pool.put_record(rec)
    result3 = make_experimental_result(
        campaign, hardness_entry, content={"property": "hardness", "value": 55, "unit": "Shore D"},
        record_id=rec.id, extracted_at="2026-08-23T03:00:00Z",
    extraction_method="measurement:campaign_execution")
    obs3, _ = admit_experimental_result(pool, result3, confidence=1.0)
    state3 = update(state2, hardness_candidate, result3, obs3)

    prediction3 = predict(state3, candidate)
    assert prediction3.uncertainty == prediction2.uncertainty == 50.0  # sample variance (n-1) of [80, 90]
    assert prediction3.predicted_value == prediction2.predicted_value == 85.0
    assert prediction3.sample_count == prediction2.sample_count == 2
    assert state3.id != state2.id  # the state itself did change (a new cell was added)


# -- 8. information-value seam consumes the model output correctly, across two states -----------------------


def test_8_information_value_seam_before_and_after():
    pool, doc, iteration, candidate, campaign, entry, hardness_entry, hardness_candidate = _setup()
    result1, obs1 = _admit_result(pool, doc, campaign, entry, "ts-80", 80)
    state1 = update(EMPTY_MODEL_STATE, candidate, result1, obs1)

    estimate_before = estimate_information_value(candidate, iteration, ModelStateInformationValueModel(state1))
    assert estimate_before.estimate is None
    assert estimate_before.estimate_status == NOT_DETERMINABLE  # only 1 sample -- honestly undetermined

    result2, obs2 = _admit_result(pool, doc, campaign, entry, "ts-90", 90)
    state2 = update(state1, candidate, result2, obs2)
    estimate_after = estimate_information_value(candidate, iteration, ModelStateInformationValueModel(state2))
    assert estimate_after.estimate == 50.0  # sample variance (n-1) of [80, 90]
    assert estimate_after.estimate_status == ESTIMATED

    assert estimate_before.estimate != estimate_after.estimate
    # full provenance preserved through the embedded structural facts
    requirement = estimate_after.information_value.evaluation.targeted_requirements[0]
    assert requirement.formulation.natural_key == "formulation-f1"


# -- 9. deterministic behavior across PYTHONHASHSEED ---------------------------------------------------------


def test_9_pythonhashseed_determinism():
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    script = (
        "from materials.model_state import Sample, make_model_state, predict, update\n"
        "from materials.candidates import make_action_candidate\n"
        "from evidence.types import make_referent\n"
        "f1 = make_referent(natural_key='formulation-f1', kind='formulation')\n"
        "candidate = make_action_candidate(action_class='measurement:repeat', requirement_ids=('r1',), "
        "formulation=f1, property='tensile_strength', role='OBSERVED', target_context={})\n"
        "state = make_model_state({})\n"
        "key_samples = {}\n"
        "from materials.model_state import resolve_model_state_key\n"
        "key = resolve_model_state_key(f1.id, 'tensile_strength', {})\n"
        "state = make_model_state({key: (Sample(80.0, 'o1'), Sample(90.0, 'o2'))})\n"
        "prediction = predict(state, candidate)\n"
        "print(state.id, prediction.predicted_value, prediction.uncertainty, prediction.sample_count, "
        "prediction.model_state_key)\n"
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
    assert len(outputs) == 1, f"model_state differed across PYTHONHASHSEED values: {outputs}"


# -- Phase 53, item 1/3: resolve_model_state_key semantics + deterministic key generation ------------------


def test_10_resolve_model_state_key_semantics():
    # Different declared target_context -> different cell, even for the
    # same (formulation, property) -- cases A vs B from the phase spec
    # (25C vs 100C), whenever a caller actually declares that distinction.
    key_25 = resolve_model_state_key("f1", "tensile_strength", {"temperature": 25})
    key_100 = resolve_model_state_key("f1", "tensile_strength", {"temperature": 100})
    assert key_25 != key_100

    # Same declared context, regardless of dict insertion order -> same
    # cell -- deterministic key generation, independent of key order.
    key_a = resolve_model_state_key("f1", "tensile_strength", {"temperature": 25, "batch": "x"})
    key_b = resolve_model_state_key("f1", "tensile_strength", {"batch": "x", "temperature": 25})
    assert key_a == key_b

    # Different property (case C) or different formulation (case D) with
    # an IDENTICAL declared context still produce different cells.
    assert resolve_model_state_key("f1", "viscosity", {}) != resolve_model_state_key("f1", "tensile_strength", {})
    assert resolve_model_state_key("f2", "tensile_strength", {}) != resolve_model_state_key("f1", "tensile_strength", {})

    # No declared context at all (the common case in this codebase's
    # fixtures) -> one shared cell for the property/formulation pair,
    # deterministically reproduced across repeated calls.
    assert resolve_model_state_key("f1", "tensile_strength", {}) == resolve_model_state_key("f1", "tensile_strength", {})


# -- Phase 53, item 2/4: context separation is preserved end to end through predict/update -------------------


def _setup_two_contexts():
    """Two candidates for the SAME (formulation, property) with two
    DIFFERENT explicitly-declared criterion contexts (25C vs 100C) --
    the direct end-to-end test of Phase 53's resolution: `predict`/
    `update` must keep these in separate cells without this module
    reimplementing `materials.decision`'s subset-matching."""
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

    criterion_25c = make_criterion("tensile_strength", ">=", 80, context={"temperature": 25})
    criterion_100c = make_criterion("tensile_strength", ">=", 80, context={"temperature": 100})
    query = make_material_program_query(["formulation-f1"], "process-std-190c", ("tensile_strength",))
    iteration = reevaluate_program(pool, ENGINE, query, (criterion_25c, criterion_100c))
    candidates = generate_candidates(iteration.specification)
    candidate_25c = next(c for c in candidates.candidates if c.target_context.get("temperature") == 25)
    candidate_100c = next(c for c in candidates.candidates if c.target_context.get("temperature") == 100)
    assert candidate_25c.id != candidate_100c.id
    assert candidate_25c.target_context != candidate_100c.target_context

    evaluations = evaluate_candidates(candidates)
    selection = select_candidates(evaluations, ALLOW_ALL)
    plan = assemble_experiment_plan(selection)
    design = assemble_experimental_design(plan)
    campaign = assemble_experimental_campaign(design)
    entry_25c = next(e for e in campaign.entries if e.candidate_id == candidate_25c.id)
    entry_100c = next(e for e in campaign.entries if e.candidate_id == candidate_100c.id)

    return pool, doc, campaign, candidate_25c, candidate_100c, entry_25c, entry_100c


def test_11_context_separation_end_to_end():
    pool, doc, campaign, candidate_25c, candidate_100c, entry_25c, entry_100c = _setup_two_contexts()

    rec = make_record(document_id=doc.id, locator="ts-25c", raw_content="ts-25c")
    admit_record(pool, rec)
    pool.put_record(rec)
    result_25c = make_experimental_result(
        campaign, entry_25c, content={"property": "tensile_strength", "value": 82, "unit": "MPa"},
        record_id=rec.id, extracted_at="2026-08-23T02:00:00Z",
    extraction_method="measurement:campaign_execution")
    obs_25c, _ = admit_experimental_result(pool, result_25c, confidence=1.0)

    state1 = update(EMPTY_MODEL_STATE, candidate_25c, result_25c, obs_25c)

    # update/predict consistency: the same candidate that produced the
    # sample sees it immediately.
    prediction_25c = predict(state1, candidate_25c)
    assert prediction_25c.sample_count == 1
    assert prediction_25c.predicted_value == 82.0

    # context separation: the OTHER candidate (same formulation/property,
    # different declared context) sees nothing -- the 25C sample never
    # leaks into the 100C cell.
    prediction_100c = predict(state1, candidate_100c)
    assert prediction_100c.sample_count == 0
    assert prediction_100c.predicted_value is None


def test_12_update_rejects_mismatched_candidate():
    pool, doc, campaign, candidate_25c, candidate_100c, entry_25c, entry_100c = _setup_two_contexts()

    rec = make_record(document_id=doc.id, locator="ts-25c-b", raw_content="ts-25c-b")
    admit_record(pool, rec)
    pool.put_record(rec)
    result_25c = make_experimental_result(
        campaign, entry_25c, content={"property": "tensile_strength", "value": 82, "unit": "MPa"},
        record_id=rec.id, extracted_at="2026-08-23T02:00:00Z",
    extraction_method="measurement:campaign_execution")
    obs_25c, _ = admit_experimental_result(pool, result_25c, confidence=1.0)

    # result_25c.candidate_id names candidate_25c -- passing candidate_100c
    # instead is a caller error update() actively rejects.
    try:
        update(EMPTY_MODEL_STATE, candidate_100c, result_25c, obs_25c)
        assert False, "expected an AssertionError for a mismatched candidate/result pair"
    except AssertionError as e:
        assert "does not match" in str(e)


# -- Phase 55, items 1/3: predictive snapshot reproducibility + deterministic prediction ------------------


def test_13_prediction_reproducible_across_independently_built_states():
    """Same ModelState.id + same Candidate.id => identical Prediction --
    proven here with two SEPARATELY constructed ModelStates that merely
    share content (hence the same `.id`), not the same object, and a
    freshly re-fetched candidate rather than the same Python reference."""
    pool, doc, iteration, candidate, campaign, entry, hardness_entry, hardness_candidate = _setup()

    state_a = make_model_state({
        resolve_model_state_key(candidate.formulation.id, candidate.property, candidate.target_context): (
            Sample(80.0, "o1"), Sample(90.0, "o2"),
        )
    })
    # Independently rebuilt from scratch, different insertion order, same content.
    state_b = make_model_state({
        resolve_model_state_key(candidate.formulation.id, candidate.property, candidate.target_context): (
            Sample(90.0, "o2"), Sample(80.0, "o1"),
        )
    })
    assert state_a.id == state_b.id
    assert state_a is not state_b

    prediction_a = predict(state_a, candidate)
    prediction_b = predict(state_b, candidate)
    assert prediction_a == prediction_b  # every field equal, including model_state_key
    assert prediction_a.predicted_value == 85.0
    assert prediction_a.uncertainty == 50.0  # sample variance (n-1) of [80, 90]

    # Calling predict() again against the SAME state is likewise
    # side-effect-free and reproduces the identical Prediction.
    assert predict(state_a, candidate) == prediction_a


# -- Phase 55, item 4: deterministic update -----------------------------------------------------------


def test_14_deterministic_update():
    """Same (previous state, candidate, result, observation) => same
    resulting ModelState.id, regardless of how many times update() is
    called or what the internal sample-list insertion order happens to
    be -- no external state influences the transition."""
    pool, doc, iteration, candidate, campaign, entry, hardness_entry, hardness_candidate = _setup()
    result, observation = _admit_result(pool, doc, campaign, entry, "ts-80", 80)

    state_1 = update(EMPTY_MODEL_STATE, candidate, result, observation)
    state_2 = update(EMPTY_MODEL_STATE, candidate, result, observation)  # same inputs, called again
    assert state_1.id == state_2.id
    assert state_1 == state_2


# -- Phase 55, item 7: context-key correctness -- Prediction exposes the exact cell used --------------------


def test_15_prediction_exposes_correct_model_state_key():
    pool, doc, iteration, candidate, campaign, entry, hardness_entry, hardness_candidate = _setup()
    prediction = predict(EMPTY_MODEL_STATE, candidate)
    expected_key = resolve_model_state_key(candidate.formulation.id, candidate.property, candidate.target_context)
    assert prediction.model_state_key == expected_key


# -- Phase 61: update() must never fold a counterfactual sample into real history --------------------------


def test_16_update_rejects_a_state_containing_a_hypothetical_sample():
    pool, doc, iteration, candidate, campaign, entry, hardness_entry, hardness_candidate = _setup()
    result, observation = _admit_result(pool, doc, campaign, entry, "ts-80", 80)

    counterfactual_state = project_update(EMPTY_MODEL_STATE, candidate, 90.0)
    try:
        update(counterfactual_state, candidate, result, observation)
        assert False, "expected an AssertionError -- a counterfactual state must never become real history"
    except AssertionError as e:
        assert "hypothetical" in str(e)

    # Sanity: an ordinary, fully-real state is unaffected by the guard.
    real_state = update(EMPTY_MODEL_STATE, candidate, result, observation)
    assert predict(real_state, candidate).predicted_value == 80.0

    # The reverse direction remains fully legitimate: project_update MAY
    # take a state that already contains a hypothetical sample, to build
    # a deeper counterfactual lookahead tree.
    deeper = project_update(counterfactual_state, candidate, 95.0)
    assert predict(deeper, candidate).sample_count == 2
