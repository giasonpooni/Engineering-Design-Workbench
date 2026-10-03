"""Phase 54: materials.assessment -- the prediction/observation
correspondence and residual primitive. Small focused test set (build-
more-test-less mode): correspondence, signed residual, mismatch
rejection, immutable update, state-dependent prediction, historical
state_id retention, information-value change after a real update, and
determinism.
"""

from evidence.admission import admit_document, admit_record, admit_referent
from evidence.pool import EvidencePool
from evidence.types import make_document, make_record, make_referent, make_source
from materials.assessment import assess
from materials.campaign import assemble_experimental_campaign
from materials.candidates import generate_candidates
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
from retrieval.engine import DeterministicRetrievalEngine

ENGINE = DeterministicRetrievalEngine()
TENSILE_CRITERION = make_criterion("tensile_strength", ">=", 80)

ALLOW_ALL = SelectionPolicy(
    allowed_action_classes=None, allow_already_represented_context=True,
    allow_redundant=True, allow_not_determinable_feasibility=True, max_selected=None,
)


def _setup():
    """No pre-seeded evidence for tensile_strength -- exactly the Phase
    54 sec.7 closed-loop shape: the first admitted result IS the first
    sample this reference model ever sees for this cell."""
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


def _other_candidate(pool, doc):
    """A second, unrelated candidate (different formulation) for the
    mismatch-rejection test -- built via its own tiny fixture rather than
    reusing `candidate` from `_setup()`, so the two really are distinct
    ActionCandidates."""
    f2 = make_referent(natural_key="formulation-f2", kind="formulation")
    admit_referent(pool, f2)
    pool.put_referent(f2)
    query = make_material_program_query(["formulation-f2"], "process-std-190c", ("tensile_strength",))
    iteration = reevaluate_program(pool, ENGINE, query, (TENSILE_CRITERION,))
    candidates = generate_candidates(iteration.specification)
    candidate = next(c for c in candidates.candidates if c.property == "tensile_strength")

    evaluations = evaluate_candidates(candidates)
    selection = select_candidates(evaluations, ALLOW_ALL)
    plan = assemble_experiment_plan(selection)
    design = assemble_experimental_design(plan)
    campaign = assemble_experimental_campaign(design)
    entry = next(e for e in campaign.entries if e.candidate_id == candidate.id)
    return candidate, campaign, entry


# -- 1. prediction/observation correspondence -----------------------------------------------------------


def test_1_correspondence():
    pool, doc, iteration, candidate, campaign, entry = _setup()
    result, observation = _admit_result(pool, doc, campaign, entry, "ts-80", 80)
    prediction = predict(EMPTY_MODEL_STATE, candidate)

    assessment = assess(prediction, result, observation)
    assert assessment.candidate_id == prediction.candidate_id == result.candidate_id == candidate.id
    assert assessment.state_id == prediction.state_id == EMPTY_MODEL_STATE.id
    assert assessment.prediction is prediction
    assert assessment.result is result
    assert assessment.observation is observation


# -- 2. correct SIGNED residual (both directions, never absolute-only) ------------------------------------


def test_2_signed_residual():
    pool, doc, iteration, candidate, campaign, entry = _setup()
    result1, obs1 = _admit_result(pool, doc, campaign, entry, "ts-80", 80)
    state1 = update(EMPTY_MODEL_STATE, candidate, result1, obs1)
    prediction1 = predict(state1, candidate)  # mean = 80.0

    result_high, obs_high = _admit_result(pool, doc, campaign, entry, "ts-90", 90)
    assessment_high = assess(prediction1, result_high, obs_high)
    assert assessment_high.observed_value == 90.0
    assert assessment_high.predicted_value == 80.0
    assert assessment_high.residual == 10.0  # positive: observation exceeded prediction
    assert assessment_high.absolute_residual == 10.0

    result_low, obs_low = _admit_result(pool, doc, campaign, entry, "ts-70", 70)
    assessment_low = assess(prediction1, result_low, obs_low)
    assert assessment_low.residual == -10.0  # negative: observation fell short -- sign preserved
    assert assessment_low.absolute_residual == 10.0

    # An empty state's prediction has no predicted_value -- residual is
    # honestly undeterminable, never a guessed zero.
    empty_prediction = predict(EMPTY_MODEL_STATE, candidate)
    assessment_empty = assess(empty_prediction, result_high, obs_high)
    assert assessment_empty.predicted_value is None
    assert assessment_empty.residual is None
    assert assessment_empty.absolute_residual is None


# -- 3. mismatch rejection ------------------------------------------------------------------------------


def test_3_mismatch_rejection():
    pool, doc, iteration, candidate, campaign, entry = _setup()
    result, observation = _admit_result(pool, doc, campaign, entry, "ts-80", 80)
    prediction = predict(EMPTY_MODEL_STATE, candidate)

    other_candidate, other_campaign, other_entry = _other_candidate(pool, doc)
    other_result, other_observation = _admit_result(pool, doc, other_campaign, other_entry, "ts-other-80", 80)

    try:
        assess(prediction, other_result, other_observation)
        assert False, "expected an AssertionError for a mismatched prediction/result pair"
    except AssertionError as e:
        assert "does not match" in str(e)

    # Sanity: the correctly-paired call still succeeds.
    assess(prediction, result, observation)


# -- 4/5/6. closed-loop demonstration (Phase 54 sec.7): immutable update, --------------------------------
# state-dependent prediction, historical state_id retention -----------------------------------------------


def test_4_5_6_closed_loop_update_prediction_and_historical_state_id():
    pool, doc, iteration, candidate, campaign, entry = _setup()

    result1, obs1 = _admit_result(pool, doc, campaign, entry, "ts-80", 80)
    state1 = update(EMPTY_MODEL_STATE, candidate, result1, obs1)
    before_state1_repr = repr(state1)

    prediction1 = predict(state1, candidate)
    assert prediction1.predicted_value == 80.0
    assert prediction1.uncertainty is None  # NOT_DETERMINABLE: a single sample has no defined variance
    assert prediction1.state_id == state1.id

    result2, obs2 = _admit_result(pool, doc, campaign, entry, "ts-90", 90)
    assessment1 = assess(prediction1, result2, obs2)
    assert assessment1.residual == 10.0

    state2 = update(state1, candidate, result2, obs2)

    # 4. immutable update -- state1 is untouched by producing state2.
    assert repr(state1) == before_state1_repr
    assert state2.id != state1.id

    # 5. new state changes the prediction -- genuinely different, not
    # just a different id.
    prediction2 = predict(state2, candidate)
    assert prediction2.predicted_value == 85.0
    # sample variance, divisor n-1: ((80-85)^2 + (90-85)^2) / (2-1) = 50
    assert prediction2.uncertainty == 50.0  # now estimable
    assert prediction2.predicted_value != prediction1.predicted_value
    assert prediction2.uncertainty != prediction1.uncertainty

    # 6. the historical prediction (and its assessment) still names the
    # ORIGINAL state -- producing state2 never rewrites prediction1.
    assert prediction1.state_id == state1.id
    assert assessment1.state_id == state1.id != state2.id
    assert predict(state1, candidate).predicted_value == 80.0  # state1 itself never changed

    # Phase 55 sec.8's full chain identity correspondence, named exactly:
    # S0 -> predict -> P0 -> observe -> O1 -> assess(P0,O1) -> A0 ->
    # update(S0,O1) -> S1 -> predict -> P1.
    assert prediction1.state_id == state1.id  # P0.state_id == S0.id
    assert prediction2.state_id == state2.id  # P1.state_id == S1.id
    assert state1.id != state2.id  # S0.id != S1.id (the state genuinely changed)
    assert assessment1.state_id == state1.id  # A0.state_id == S0.id


# -- 7. information-value changes after a real update (Phase 54 sec.6/7) ----------------------------------


def test_7_information_value_before_and_after_real_update():
    pool, doc, iteration, candidate, campaign, entry = _setup()
    result1, obs1 = _admit_result(pool, doc, campaign, entry, "ts-80", 80)
    state1 = update(EMPTY_MODEL_STATE, candidate, result1, obs1)

    estimate_before = estimate_information_value(candidate, iteration, ModelStateInformationValueModel(state1))
    assert estimate_before.estimate is None
    assert estimate_before.estimate_status == NOT_DETERMINABLE  # only 1 sample

    result2, obs2 = _admit_result(pool, doc, campaign, entry, "ts-90", 90)
    prediction1 = predict(state1, candidate)
    assess(prediction1, result2, obs2)  # diagnostic only -- not required by update()
    state2 = update(state1, candidate, result2, obs2)

    estimate_after = estimate_information_value(candidate, iteration, ModelStateInformationValueModel(state2))
    # the cell's sample variance, divisor n-1: two samples 80 and 90
    # about a mean of 85 give ((80-85)^2 + (90-85)^2) / (2-1) = 50
    assert estimate_after.estimate == 50.0
    assert estimate_after.estimate_status == ESTIMATED
    assert estimate_before.estimate != estimate_after.estimate  # caused by the real, admitted observation


# -- 8. deterministic behavior; no pool mutation --------------------------------------------------------


def test_8_deterministic_and_no_mutation():
    pool, doc, iteration, candidate, campaign, entry = _setup()
    result, observation = _admit_result(pool, doc, campaign, entry, "ts-80", 80)
    prediction = predict(EMPTY_MODEL_STATE, candidate)

    fingerprint_before = pool.fingerprint()
    a = assess(prediction, result, observation)
    b = assess(prediction, result, observation)
    assert a == b  # equal dataclasses for equal inputs
    assert pool.fingerprint() == fingerprint_before  # read-only
