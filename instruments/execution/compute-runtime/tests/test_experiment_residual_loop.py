"""Phase 66: the residual loop, solidified -- S_t -> y_hat_t -> y_t ->
r_t -> S_(t+1) -> y_hat_(t+1) -- proven with the actual production
APIs (materials.model_state.predict/update, materials.assessment.assess,
materials.counterfactual.project_update, materials.trajectory,
experiment.session.ExperimentSession), never a reimplementation of any
of their mathematics. Small, focused: identity relationships and signed
residuals in both directions, repeated real state evolution,
trajectory/assessment association, counterfactual separation, and one
asset-level acceptance test exercising ExperimentSession's new
predict/inspect_counterfactual/observe surface end to end.
"""

from evidence.admission import admit_document, admit_record, admit_referent
from evidence.pool import EvidencePool
from evidence.types import make_document, make_record, make_referent, make_source
from experiment.session import make_experiment_session, trajectory_of
from materials.assessment import assess
from materials.campaign import assemble_experimental_campaign
from materials.candidates import generate_candidates
from materials.counterfactual import project_update
from materials.decision import make_criterion
from materials.design import assemble_experimental_design
from materials.diagnostics import diagnose_transitions
from materials.evaluation import evaluate_candidates
from materials.iteration import reevaluate_program
from materials.model_state import EMPTY_MODEL_STATE, predict, update
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
    """No pre-seeded evidence -- the first admitted result IS the first
    sample this reference model ever sees, matching every prior
    dynamic-state phase's own fixture shape."""
    pool = EvidencePool()
    source = make_source(kind="lab_notebook", name="QC")
    pool.put_source(source)
    doc = make_document(source_id=source.id, raw_content="session log", retrieval_method="manual_entry", retrieved_at="2026-08-24T00:00:00Z")
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

    session = make_experiment_session(pool, ENGINE, iteration, document_id=doc.id)
    return session, candidate, campaign, entry


def _admit(session, campaign, entry, locator, value):
    """The one admission call this test file makes directly -- exactly
    the caller-responsibility `materials.results.admit_experimental_result`
    has always required (Phase 44)."""
    rec = make_record(document_id=session.document_id, locator=locator, raw_content=f"{value} MPa")
    admit_record(session.pool, rec)
    session.pool.put_record(rec)
    result = make_experimental_result(
        campaign, entry, content={"property": "tensile_strength", "value": value, "unit": "MPa"},
        record_id=rec.id, extracted_at="2026-08-24T02:00:00Z",
    extraction_method="measurement:campaign_execution")
    observation, _ = admit_experimental_result(session.pool, result, confidence=1.0)
    return result, observation


# -- 1/2. residual-loop identity relationships + signed residual, both directions -------------------------


def test_1_2_residual_loop_identity_and_signed_residual():
    session, candidate, campaign, entry = _setup()
    S0 = session.state
    P0 = predict(S0, candidate)
    assert P0.predicted_value is None  # no samples yet -- honestly undetermined

    # +10: observation exceeds prediction. Use a real prediction (from a
    # state with one sample already) so predicted_value is defined.
    result_seed, obs_seed = _admit(session, campaign, entry, "seed", 80)
    S_seed = update(S0, candidate, result_seed, obs_seed)
    P_seed = predict(S_seed, candidate)
    assert P_seed.predicted_value == 80.0

    result_high, obs_high = _admit(session, campaign, entry, "high", 90)
    assessment_high = assess(P_seed, result_high, obs_high)
    S_high = update(S_seed, candidate, result_high, obs_high)
    P_high = predict(S_high, candidate)

    assert assessment_high.residual == 10.0
    assert assessment_high.residual == obs_high.content["value"] - P_seed.predicted_value

    # -10: observation falls short. Same setup, different branch.
    result_low, obs_low = _admit(session, campaign, entry, "low", 70)
    assessment_low = assess(P_seed, result_low, obs_low)
    assert assessment_low.residual == -10.0
    assert assessment_low.residual == obs_low.content["value"] - P_seed.predicted_value

    # identity relationships, named exactly as the phase spec states them.
    assert P_seed.state_id == S_seed.id
    assert P_high.state_id == S_high.id
    assert P_seed.candidate_id == candidate.id
    assert P_high.candidate_id == candidate.id
    assert assessment_high.state_id == S_seed.id
    assert assessment_high.candidate_id == candidate.id
    sample = next(iter(S_seed.samples.values()))[0]
    assert sample.observation_id == obs_seed.id

    # S0 (and S_seed, once built) remain unchanged by any of this.
    assert session.state.id == S0.id
    assert predict(S_seed, candidate).predicted_value == 80.0


# -- 3/4. repeated real state evolution: S0 -> S1 -> S2, predictions change only because of accumulation ----


def test_3_4_repeated_state_evolution():
    session, candidate, campaign, entry = _setup()
    S0 = session.state
    P0 = predict(S0, candidate)

    result1, obs1 = _admit(session, campaign, entry, "y1", 90)
    S1 = update(S0, candidate, result1, obs1)
    P1 = predict(S1, candidate)

    result2, obs2 = _admit(session, campaign, entry, "y2", 100)
    S2 = update(S1, candidate, result2, obs2)
    P2 = predict(S2, candidate)

    assert P0.predicted_value is None
    assert P1.predicted_value == 90.0
    assert P2.predicted_value == 95.0  # mean([90, 100]) -- from the existing implementation, not asserted a priori
    assert P0 != P1
    assert P1 != P2
    assert S0.id != S1.id != S2.id

    # the change is caused by accumulated observations, not a new rule:
    # S2's cell literally contains both samples.
    key = next(iter(S2.samples))
    assert {s.value for s in S2.samples[key]} == {90.0, 100.0}


# -- 5. trajectory semantics: each transition's assessment is tied to the RIGHT observation ------------------


def test_5_trajectory_assessment_association():
    session, candidate, campaign, entry = _setup()
    S0 = session.state
    P0 = predict(S0, candidate)
    result1, obs1 = _admit(session, campaign, entry, "y1", 90)
    assessment_0_to_1 = assess(P0, result1, obs1)  # the observation that PRODUCED S1
    S1 = update(S0, candidate, result1, obs1)

    P1 = predict(S1, candidate)
    result2, obs2 = _admit(session, campaign, entry, "y2", 100)
    assessment_1_to_2 = assess(P1, result2, obs2)  # the observation that PRODUCED S2
    S2 = update(S1, candidate, result2, obs2)

    # never accidentally attach the successor's own assessment to the
    # transition that created it.
    assert assessment_0_to_1.state_id == S0.id
    assert assessment_1_to_2.state_id == S1.id
    assert assessment_0_to_1.state_id != S1.id
    assert assessment_1_to_2.state_id != S2.id

    # reuse the existing trajectory/diagnostic machinery -- no new math.
    updated_session = session
    for s in (S1, S2):
        updated_session = type(updated_session)(
            pool=updated_session.pool, engine=updated_session.engine, iteration=updated_session.iteration,
            state=s, state_history=updated_session.state_history + (s,), document_id=updated_session.document_id,
        )
    trajectory = trajectory_of(updated_session)
    diagnostics = diagnose_transitions(trajectory, candidate, (assessment_0_to_1, assessment_1_to_2))
    d0, d1 = diagnostics.diagnostics
    assert d0.predecessor_state_id == S0.id and d0.assessment is assessment_0_to_1
    assert d1.predecessor_state_id == S1.id and d1.assessment is assessment_1_to_2


# -- 6. counterfactual separation, even when a hypothetical value matches a real one -------------------------


def test_6_counterfactual_separation():
    session, candidate, campaign, entry = _setup()
    S0 = session.state
    result1, obs1 = _admit(session, campaign, entry, "y1", 90)
    S1 = update(S0, candidate, result1, obs1)  # the REAL successor, y=90

    S_cf90 = project_update(S0, candidate, 90)  # SAME numeric value as the real observation
    S_cf70 = project_update(S0, candidate, 70)

    assert S_cf90.id != S_cf70.id
    assert S_cf90.id != S1.id  # equal VALUE, but never equal identity
    assert S_cf70.id != S1.id

    cf90_sample = next(iter(S_cf90.samples.values()))[0]
    cf70_sample = next(iter(S_cf70.samples.values()))[0]
    assert cf90_sample.observation_id.startswith("hypothetical:")
    assert cf70_sample.observation_id.startswith("hypothetical:")

    try:
        update(S_cf90, candidate, result1, obs1)
        assert False, "expected the Phase 61 guard to reject a hypothetical-tainted state"
    except AssertionError as e:
        assert "hypothetical" in str(e)


# -- 7. asset-level acceptance test: a user interaction, through ExperimentSession's own surface -------------


def test_7_session_interaction_reads_like_a_user_interaction():
    session, candidate, campaign, entry = _setup()

    # inspect current state
    assert session.state.id == EMPTY_MODEL_STATE.id

    # select candidate; request prediction
    prediction = session.predict(candidate)
    assert prediction.predicted_value is None  # honestly undetermined -- no samples yet

    # evaluate a hypothetical outcome before committing to a real one
    outcome = session.inspect_counterfactual(candidate, 90.0)
    assert outcome.prediction_after.predicted_value == 90.0
    assert session.state.id == EMPTY_MODEL_STATE.id  # inspecting a hypothetical never advances the session

    # perform/represent the real experiment; submit the real observation
    result, observation = _admit(session, campaign, entry, "real-1", 90)
    assessment, session = session.observe(candidate, prediction, result, observation)

    # inspect residual
    assert assessment.residual is None  # prediction had no predicted_value -- honestly undetermined
    assert assessment.observed_value == 90.0

    # advance state; request new prediction
    assert session.state.id != EMPTY_MODEL_STATE.id
    new_prediction = session.predict(candidate)
    assert new_prediction.predicted_value == 90.0
    assert new_prediction != prediction  # verify the changed prediction

    # a second real cycle demonstrates the residual becomes defined once a real prediction exists.
    result2, observation2 = _admit(session, campaign, entry, "real-2", 100)
    assessment2, session = session.observe(candidate, new_prediction, result2, observation2)
    assert assessment2.residual == 10.0  # 100 - 90
    assert session.predict(candidate).predicted_value == 95.0
    assert len(session.state_history) == 3
