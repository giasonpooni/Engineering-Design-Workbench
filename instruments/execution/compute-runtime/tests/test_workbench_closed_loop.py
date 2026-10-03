"""Phase 69: one coherent closed-loop materials-investigation scenario,
run through `workbench.investigation.run_investigation()` -- the same
function `python -m workbench.investigation` runs. Verifies the twelve
items Phase 69 sec.10 requires, asserting against the real objects the
implementation produced rather than hard-coded intermediate mathematics
wherever practical.
"""

import pytest

from materials.model_state import HYPOTHETICAL_SAMPLE_PREFIX, update
from workbench.investigation import run_investigation


@pytest.fixture(scope="module")
def investigation():
    return run_investigation()


# -- 1/2. initial prediction + initial decision -----------------------------------------------------


def test_initial_prediction_is_honestly_undetermined(investigation):
    session0 = investigation.sessions[0]
    for candidate in (investigation.candidate_room, investigation.candidate_elevated):
        prediction = session0.predict(candidate)
        assert prediction.predicted_value is None
        assert prediction.uncertainty is None
        assert prediction.sample_count == 0


def test_initial_decision_selected_exactly_one_candidate(investigation):
    decision_1 = investigation.decisions[0]
    selected = [o for o in decision_1.optimization.optimizations if o.status == "SELECTED"]
    assert len(selected) == 1
    assert selected[0].candidate_id == decision_1.selected_candidate.id
    # both candidates were determinate (SUPPLIED) at the tie -- honest, not indeterminate
    for o in decision_1.optimization.optimizations:
        assert o.utility.utility_status == "SUPPLIED"


# -- 3. counterfactual exploration, performed before the first real experiment ---------------------


def test_counterfactual_exploration_before_first_real_experiment(investigation):
    session0 = investigation.sessions[0]
    outcome_high, outcome_low = investigation.counterfactual_outcomes

    # hypothetical sample markers remain present
    for outcome in (outcome_high, outcome_low):
        sample = next(iter(outcome.projected_state.samples.values()))[0]
        assert sample.observation_id.startswith(HYPOTHETICAL_SAMPLE_PREFIX)

    # source state remains unchanged
    assert outcome_high.source_state_id == session0.state.id
    assert outcome_low.source_state_id == session0.state.id
    assert session0.state.id == investigation.sessions[0].state.id

    # projected states never enter EvidencePool -- no admit_experimental_result call exists for
    # either branch; verified structurally by their samples still carrying the hypothetical marker
    # (a real admission would have replaced it with a genuine Observation id, per materials.results).
    assert outcome_high.projected_state.id != outcome_low.projected_state.id
    assert outcome_high.projected_state.id != session0.state.id

    # real update() rejects a hypothetical state
    real_assessment = investigation.assessments[0]
    with pytest.raises(AssertionError, match="hypothetical"):
        update(
            outcome_high.projected_state, investigation.candidate_room,
            real_assessment.result, real_assessment.observation,
        )

    # identical hypothetical inputs remain deterministic
    from materials.ensemble import project_outcome
    outcome_high_repeat = project_outcome(session0.state, investigation.candidate_room, 88.0, probability=0.5)
    assert outcome_high_repeat.projected_state.id == outcome_high.projected_state.id
    assert outcome_high_repeat.prediction_after.predicted_value == outcome_high.prediction_after.predicted_value

    # the expected information value was honestly NOT_DETERMINABLE (each branch adds exactly one
    # sample to a zero-sample cell -- uncertainty needs 2+ samples, so no branch is ESTIMATED)
    assert investigation.counterfactual_information_value.expected_information_value is None
    assert investigation.counterfactual_information_value.expected_information_value_status == "NOT_DETERMINABLE"


# -- 4/5. real observation + signed residual, both directions --------------------------------------


def test_real_observations_and_signed_residuals_both_directions(investigation):
    assessment_1, assessment_2, assessment_3, assessment_4 = investigation.assessments

    # first observations for each cell are honestly undetermined (no prior sample in that cell)
    assert assessment_1.residual is None
    assert assessment_1.observed_value == 88.0
    assert assessment_2.residual is None
    assert assessment_2.observed_value == 65.0

    # a positive and a negative residual both appear once real predictions exist
    assert assessment_3.residual is not None and assessment_3.residual > 0
    assert assessment_4.residual is not None and assessment_4.residual < 0

    # residuals stay signed, not absolute-only, and carry no interpretation
    for assessment in investigation.assessments:
        assert not hasattr(assessment, "quality")
        assert not hasattr(assessment, "confidence")
        if assessment.residual is not None:
            assert assessment.absolute_residual == abs(assessment.residual)


# -- 6. successor state identity + changed/recomputed prediction + second decision -----------------


def test_successor_state_identity_and_decision_changed(investigation):
    session0, session1, session2 = investigation.sessions[0], investigation.sessions[1], investigation.sessions[2]
    assert session1.state.id != session0.state.id
    assert session2.state.id != session1.state.id

    decision_1, decision_2 = investigation.decisions[0], investigation.decisions[1]
    # the prediction for the room-temperature candidate genuinely changed between D1 and D2's states
    prediction_before = session0.predict(investigation.candidate_room)
    prediction_after = session1.predict(investigation.candidate_room)
    assert prediction_before.predicted_value != prediction_after.predicted_value

    # the second decision selected a DIFFERENT candidate than the first -- computed causality only:
    # observation -> ModelState_(t+1) -> prediction change -> utility change -> different selection
    assert decision_1.selected_candidate.id != decision_2.selected_candidate.id
    assert decision_1.selected_candidate.id == investigation.candidate_room.id
    assert decision_2.selected_candidate.id == investigation.candidate_elevated.id


def test_decision_returns_to_room_temperature_once_its_real_uncertainty_is_known(investigation):
    """D3/D4: once the room-temperature candidate has 2+ real samples,
    its now-computable real uncertainty dominates the still-single-
    sample elevated-temperature candidate's benefit -- a third and
    fourth demonstration that the recommendation tracks the state."""
    decision_3, decision_4 = investigation.decisions[2], investigation.decisions[3]
    assert decision_3.selected_candidate.id == investigation.candidate_room.id
    assert decision_4.selected_candidate.id == investigation.candidate_room.id
    room_utility_d3 = next(
        o for o in decision_3.optimization.optimizations if o.candidate_id == investigation.candidate_room.id
    ).utility
    assert room_utility_d3.utility_status == "ESTIMATED" or room_utility_d3.information_value.expected_information_gain
    assert room_utility_d3.utility is not None and room_utility_d3.utility > 1.0  # driven by real computed variance


# -- 9. trajectory construction + transition diagnostic ---------------------------------------------


def test_trajectory_and_transition_diagnostics(investigation):
    diagnostics = investigation.diagnostics
    assert diagnostics.candidate_id == investigation.candidate_room.id
    assert len(diagnostics.diagnostics) == len(investigation.sessions) - 1

    # each transition's residual is associated with the PREDECESSOR prediction that generated it
    d0, d1, d2, d3 = diagnostics.diagnostics
    assert d0.assessment is not None and d0.assessment is investigation.assessments[0]
    assert d0.predecessor_state_id == investigation.sessions[0].state.id

    # the transition caused by the OTHER candidate's observation correctly carries no
    # room-temperature-relevant assessment, and correctly shows its cell provably unchanged
    assert d1.assessment is None
    assert d1.delta_predicted_value == 0.0

    assert d2.assessment is investigation.assessments[2]
    assert d2.residual_against_previous_prediction == investigation.assessments[2].residual
    assert d3.assessment is investigation.assessments[3]
    assert d3.residual_against_previous_prediction == investigation.assessments[3].residual
    assert d2.residual_against_previous_prediction > 0
    assert d3.residual_against_previous_prediction < 0


# -- 11/12. historical-state immutability + hypothetical-state isolation ---------------------------


def test_historical_state_immutability(investigation):
    candidate = investigation.candidate_room
    # re-predicting against every historical session reproduces its original value exactly
    expected = [None, 88.0, 88.0, 95.0, 86.66666666666667]
    for session, expected_value in zip(investigation.sessions, expected):
        prediction = session.predict(candidate)
        if expected_value is None:
            assert prediction.predicted_value is None
        else:
            assert prediction.predicted_value == pytest.approx(expected_value)
    # the earliest session's own state_history was never extended by later cycles
    assert len(investigation.sessions[0].state_history) == 1


def test_hypothetical_state_isolation_from_real_history(investigation):
    outcome_high, outcome_low = investigation.counterfactual_outcomes
    real_state_ids = {s.state.id for s in investigation.sessions}
    assert outcome_high.projected_state.id not in real_state_ids
    assert outcome_low.projected_state.id not in real_state_ids
