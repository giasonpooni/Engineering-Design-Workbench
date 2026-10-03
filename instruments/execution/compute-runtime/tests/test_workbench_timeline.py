"""Phase 90: the state-space timeline and navigation.

INVESTIGATION RESULT -- no Timeline/StateRecord/HistoryEntry/
NavigationNode was built. The chain already exists and is already
authoritative:

  `ExperimentSession.state_history`   the ordered real states
  `PredictionAssessment`             prediction, observation, SIGNED
                                     residual, absolute residual, and
                                     `state_id` = the predecessor it was
                                     assessed against
  `CounterfactualOutcome`            branches, each frozen to its own
                                     `source_state_id`
  `OptimizationResult`               the decisions, retained not recomputed

ON ORDER (sec.10) -- list order is not an assumption here. `trajectory_of`
-> `materials.trajectory.make_model_state_trajectory` VERIFIES that the
sequence is consistent with a real `update()` chain (for every cell in a
predecessor, the successor's sample set is a superset) and raises
otherwise. So `state_history` order is a checked property, and the
current state is identified by `session.state.id` -- an identity, never
by being last in a list.

ONE thing was genuinely missing and is retained rather than derived:
`OptimizationResult` carries no state id, so a timeline spanning more
than two states could not say which decision belonged to which state.
`decision_log` keeps the SAME OptimizationResult objects against the
`ModelState.id` they were computed at. Nothing is minted or recomputed.
"""

import json
import re
from pathlib import Path

import pytest

from workbench import theme
from workbench.cli import dispatch
from workbench.interaction import WorkbenchState, bootstrap_research_scenario

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "polymer_tensile_strength.json"


def _clock():
    n = {"i": 0}

    def clock() -> str:
        n["i"] += 1
        return f"2026-08-24T17:{n['i']:02d}:00Z"

    return clock


@pytest.fixture(autouse=True)
def _plain():
    theme.set_color(False)
    yield
    theme.set_color(None)


def _start() -> WorkbenchState:
    with open(EXAMPLE, encoding="utf-8") as f:
        return bootstrap_research_scenario(json.load(f), clock=_clock())


@pytest.fixture()
def state() -> WorkbenchState:
    return _start()


def _substantive(view: str) -> list:
    """A rendered state view minus the two things that legitimately change
    as the session advances: the top rule (which carries current/historical)
    and the POSITION row. Everything else is a fact about a frozen state and
    must re-render byte-identically forever."""
    return [
        line for line in view.splitlines()[1:]
        if "POSITION" not in line
    ]


def _three_states(state: WorkbenchState) -> WorkbenchState:
    dispatch(state, "select", ["baseline", "80"])
    dispatch(state, "decide", [])
    dispatch(state, "explore", ["70"])
    dispatch(state, "explore", ["110"])
    dispatch(state, "observe", ["90"])
    dispatch(state, "decide", [])
    dispatch(state, "observe", ["100"])
    return state


# -- the chain ---------------------------------------------------------------------------------------


def test_timeline_at_bootstrap_shows_one_state(state: WorkbenchState):
    text = dispatch(state, "timeline", [])
    assert "STATE TIMELINE" in text
    assert "S0" in text and "S1" not in text
    assert theme.ident(state.session.state.id) in text


def test_timeline_shows_every_real_state_in_order(state: WorkbenchState):
    _three_states(state)
    history = state.session.state_history
    assert len(history) == 3

    text = dispatch(state, "timeline", [])
    positions = [text.index(f"S{i}  ") for i in range(3)]
    assert positions == sorted(positions), "timeline is not in chronological order"
    for model_state in history:
        assert theme.ident(model_state.id) in text


def test_the_current_state_is_marked_by_identity_not_position(state: WorkbenchState):
    """`session.state.id` is the authority. The marker must follow it."""
    _three_states(state)
    text = dispatch(state, "timeline", [])
    current_line = next(
        ln for ln in text.splitlines() if theme.ident(state.session.state.id) in ln)
    assert "CURRENT" in current_line
    assert text.count("CURRENT") == 1
    # and it is in fact the last entry of the verified chain
    assert state.session.state_history[-1].id == state.session.state.id


def test_timeline_observations_and_signed_residuals_come_from_the_assessments(state: WorkbenchState):
    _three_states(state)
    text = dispatch(state, "timeline", [])
    # S0 -> S1 admitted 90 with no prior prediction; S1 -> S2 admitted 100
    # against a prediction of 90, so the residual is +10.0.
    assert state.assessments[0].observed_value == 90.0
    assert state.assessments[0].residual is None
    assert state.assessments[1].observed_value == 100.0
    assert state.assessments[1].residual == 10.0
    assert "90.0" in text and "100.0" in text
    assert "+10.0" in text


def test_a_state_with_no_incoming_observation_says_none_not_zero(state: WorkbenchState):
    _three_states(state)
    text = dispatch(state, "timeline", ["0"])
    assert "NONE" in text
    assert "this state was not reached by an admitted observation" in text
    observation_rows = [ln for ln in text.splitlines() if "OBSERVATION" in ln]
    assert observation_rows
    for row in observation_rows:
        assert "0.0" not in row


# -- decision lineage --------------------------------------------------------------------------------


def test_each_decision_is_shown_at_the_state_it_was_computed_at(state: WorkbenchState):
    _three_states(state)
    history = state.session.state_history
    assert state.decision_at(history[0].id) is not None
    assert state.decision_at(history[1].id) is not None
    assert state.decision_at(history[2].id) is None  # none was computed at S2

    text = dispatch(state, "timeline", [])
    assert "no decision was computed at this state" in text


def test_the_decision_shown_is_the_retained_object_not_a_recomputation(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    dispatch(state, "decide", [])
    decision = state.last_decision
    s0 = state.session.state.id

    dispatch(state, "observe", ["90"])
    dispatch(state, "timeline", [])
    dispatch(state, "timeline", ["0"])
    assert state.decision_at(s0) is decision  # the SAME object


def test_deciding_twice_at_one_state_keeps_one_entry(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    dispatch(state, "decide", [])
    dispatch(state, "decide", [])
    assert len(state.decision_log) == 1


def test_a_recommendation_is_never_called_a_conclusion(state: WorkbenchState):
    _three_states(state)
    for args in ([], ["0"], ["1"], ["2"]):
        lowered = dispatch(state, "timeline", args).lower()
        for phrase in ("better", "worse", "superior", "proved", "confirms", "caused",
                       "validates", "probability", "confidence"):
            assert phrase not in lowered, f"timeline claims too much: {phrase!r}"


# -- residual lineage --------------------------------------------------------------------------------


def test_the_state_view_shows_prediction_observation_residual_successor(state: WorkbenchState):
    _three_states(state)
    text = dispatch(state, "timeline", ["2"])
    assessment = state.assessments[1]
    assert assessment.predicted_value == 90.0
    assert assessment.observed_value == 100.0
    assert assessment.residual == 10.0

    for token in ("PREDICTION", "OBSERVATION", "RESIDUAL", "THIS STATE"):
        assert token in text
    assert "+10.0" in text
    # the chain is ordered as a chain
    assert text.index("PREDICTION") < text.index("OBSERVATION") < text.index("RESIDUAL")
    assert theme.ident(state.session.state_history[1].id) in text  # FROM STATE


def test_an_undetermined_residual_stays_undetermined(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    dispatch(state, "observe", ["90"])  # no prior prediction -> residual is None
    assert state.assessments[0].residual is None

    text = dispatch(state, "timeline", ["1"])
    residual_rows = [ln for ln in text.splitlines() if "RESIDUAL" in ln]
    assert residual_rows
    for row in residual_rows:
        assert theme.UNDETERMINED in row
        assert "0.0" not in row


def test_a_negative_residual_is_never_shown_unsigned(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    dispatch(state, "observe", ["90"])
    dispatch(state, "observe", ["60"])  # predicted 90, observed 60 -> -30.0
    assert state.assessments[-1].residual == -30.0

    text = dispatch(state, "timeline", ["2"])
    signed = [ln for ln in text.splitlines() if "RESIDUAL" in ln and "ABS" not in ln]
    assert any("-30.0" in ln for ln in signed)
    absolute = [ln for ln in text.splitlines() if "ABS RESIDUAL" in ln]
    assert len(absolute) == 1 and "30.0" in absolute[0]


# -- branch provenance -------------------------------------------------------------------------------


def test_branches_appear_as_side_projections_never_as_states(state: WorkbenchState):
    _three_states(state)
    text = dispatch(state, "timeline", [])
    plain = text.splitlines()
    for branch in state.branches:
        row = next(ln for ln in plain if theme.ident(branch.projected_state_id) in ln)
        assert "HYPOTHETICAL" in row
        # a branch never occupies a state slot
        assert not row.strip().startswith(("S0", "S1", "S2"))
    assert "side projections · not in this chain" in text


def test_branches_stay_attached_to_their_parent_after_the_session_advances(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    s0 = state.session.state.id
    dispatch(state, "explore", ["70"])
    dispatch(state, "explore", ["110"])
    dispatch(state, "observe", ["90"])
    dispatch(state, "observe", ["100"])
    s2 = state.session.state.id
    assert s2 != s0

    for branch in state.branches:
        assert branch.source_state_id == s0
    assert len(state.branches_from(s0)) == 2
    assert state.branches_from(s2) == []

    # and the timeline hangs them off S0, not off the current state
    text = dispatch(state, "timeline", [])
    s0_section = text[text.index("S0  "):text.index("S1  ")]
    assert s0_section.count("HYPOTHETICAL") == 2
    s2_view = dispatch(state, "timeline", ["2"])
    assert "Nothing was projected from this state." in s2_view


# -- navigation --------------------------------------------------------------------------------------


def test_numeric_navigation_resolves_to_the_existing_immutable_state(state: WorkbenchState):
    _three_states(state)
    for index, model_state in enumerate(state.session.state_history):
        text = dispatch(state, "timeline", [str(index)])
        assert theme.ident(model_state.id, size=24) in text
        assert f"S{index}" in text


def test_inspect_state_reaches_the_same_view(state: WorkbenchState):
    _three_states(state)
    assert dispatch(state, "inspect", ["state", "1"]) == dispatch(state, "timeline", ["1"])


def test_inspect_without_state_still_inspects_a_candidate(state: WorkbenchState):
    """Extending the grammar must not break the existing one."""
    _three_states(state)
    text = dispatch(state, "inspect", ["baseline", "80"])
    assert "CANDIDATE INSPECTION" in text


def test_every_navigation_rejection_names_the_expected_form(state: WorkbenchState):
    _three_states(state)
    for args in (["99"], ["x"], ["-1"]):
        assert "EXPECTED" in dispatch(state, "timeline", args), args
    assert "EXPECTED" in dispatch(state, "inspect", ["state"])


def test_a_display_index_is_never_treated_as_identity(state: WorkbenchState):
    """S<n> is a label. The view must print the real hash beside it, and
    must never render an identity that came from nowhere."""
    _three_states(state)
    known = {theme.ident(s.id) for s in state.session.state_history}
    known |= {theme.ident(b.projected_state_id) for b in state.branches}
    known |= {theme.ident(c.id) for c in state.list_candidates()}
    for args in ([], ["0"], ["1"], ["2"]):
        text = dispatch(state, "timeline", args)
        for token in re.findall(r"·[0-9a-f]{12}", text):
            assert token in known, f"timeline rendered an identity from nowhere: {token}"
    assert "display index only" in dispatch(state, "timeline", ["0"])


# -- navigation safety -------------------------------------------------------------------------------


def test_timeline_navigation_mutates_nothing(state: WorkbenchState):
    _three_states(state)
    session = state.session
    state_id = state.session.state.id
    fingerprint = state.pool.fingerprint()
    observations = len(state.pool.all_observations())
    history = [s.id for s in state.session.state_history]
    assessments = len(state.assessments)
    branches = list(state.branches)
    branch_sources = [b.source_state_id for b in state.branches]
    decisions = list(state.decision_log)
    selected = state.selected_candidate

    for args in ([], ["0"], ["1"], ["2"], ["99"]):
        dispatch(state, "timeline", args)
    for args in (["state", "0"], ["state", "1"], ["state", "2"]):
        dispatch(state, "inspect", args)

    assert state.session is session
    assert state.session.state.id == state_id
    assert state.pool.fingerprint() == fingerprint
    assert len(state.pool.all_observations()) == observations
    assert [s.id for s in state.session.state_history] == history
    assert len(state.assessments) == assessments
    assert state.branches == branches
    assert [b.source_state_id for b in state.branches] == branch_sources
    assert state.decision_log == decisions
    assert state.selected_candidate is selected


# -- historical immutability -------------------------------------------------------------------------


def test_historical_states_reproduce_their_original_values_after_the_session_advances(state: WorkbenchState):
    """Build S0..S3, having recorded what S0..S2 reported BEFORE S3
    existed, then re-read them afterwards."""
    dispatch(state, "select", ["baseline", "80"])
    candidate = state.selected_candidate
    recorded = []

    for value in ("90", "100", "80"):
        history = state.session.state_history
        index = len(history) - 1
        model_state = history[index]
        prediction = state.prediction_at(candidate, model_state)
        recorded.append((
            index, model_state.id, prediction.sample_count,
            prediction.predicted_value, prediction.uncertainty,
            dispatch(state, "timeline", [str(index)]),
        ))
        dispatch(state, "observe", [value])

    assert len(state.session.state_history) == 4  # S0..S3

    for index, state_id, samples, value, uncertainty, view in recorded:
        model_state = state.session.state_history[index]
        assert model_state.id == state_id
        prediction = state.prediction_at(candidate, model_state)
        assert prediction.sample_count == samples
        assert prediction.predicted_value == value
        assert prediction.uncertainty == uncertainty
        assert prediction.candidate_id == candidate.id
        # every substantive row re-renders identically. Only the top rule and
        # the POSITION row legitimately differ: the CURRENT marker moved on.
        now = dispatch(state, "timeline", [str(index)])
        assert _substantive(now) == _substantive(view), f"S{index} re-rendered differently"


def test_the_pool_fingerprint_changes_only_at_observe(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    fingerprints = [state.pool.fingerprint()]

    dispatch(state, "decide", [])
    dispatch(state, "explore", ["70"])
    dispatch(state, "timeline", [])
    dispatch(state, "timeline", ["0"])
    assert state.pool.fingerprint() == fingerprints[0]

    dispatch(state, "observe", ["90"])
    assert state.pool.fingerprint() != fingerprints[0]
    after = state.pool.fingerprint()

    dispatch(state, "timeline", [])
    dispatch(state, "inspect", ["state", "1"])
    dispatch(state, "compare", ["state", "1", "state", "2"])
    assert state.pool.fingerprint() == after


# -- honesty -----------------------------------------------------------------------------------------


def test_timeline_never_renders_an_unknown_as_zero(state: WorkbenchState):
    _three_states(state)
    for args in ([], ["0"], ["1"], ["2"]):
        text = dispatch(state, "timeline", args)
        for line in text.splitlines():
            for cell in line.split(theme.TRANSITION):
                if theme.UNDETERMINED in cell:
                    after = cell.split(theme.UNDETERMINED, 1)[1]
                    assert not any(ch.isdigit() for ch in after), f"{args}: {line!r}"


def test_undetermined_is_never_a_section_heading(state: WorkbenchState):
    _three_states(state)
    for args in ([], ["0"], ["1"], ["2"]):
        for line in dispatch(state, "timeline", args).splitlines():
            if line.lstrip("│║ ").startswith("─ "):
                assert theme.UNDETERMINED not in line


def test_a_real_state_is_never_called_hypothetical(state: WorkbenchState):
    _three_states(state)
    for index in range(3):
        text = dispatch(state, "timeline", [str(index)])
        basis_row = next(ln for ln in text.splitlines() if "BASIS" in ln)
        assert "REAL" in basis_row and "HYPOTHETICAL" not in basis_row
        assert "admitted evidence, not a projection" in text


# -- determinism -------------------------------------------------------------------------------------


def test_the_same_scenario_twice_produces_identical_timelines():
    def run() -> tuple:
        state = _start()
        _three_states(state)
        views = tuple(dispatch(state, "timeline", args)
                      for args in ([], ["0"], ["1"], ["2"]))
        identities = (
            tuple(s.id for s in state.session.state_history),
            tuple(b.projected_state_id for b in state.branches),
            tuple(b.source_state_id for b in state.branches),
            tuple(a.residual for a in state.assessments),
            tuple(sid for sid, _ in state.decision_log),
        )
        return identities, views

    assert run() == run()


# -- integration -------------------------------------------------------------------------------------


def test_full_multi_cycle_timeline(state: WorkbenchState):
    dispatch(state, "select", ["baseline", "80"])
    candidate = state.selected_candidate
    s0 = state.session.state.id
    pool_0 = state.pool.fingerprint()

    dispatch(state, "decide", [])
    d0 = state.last_decision
    dispatch(state, "explore", ["70"])
    dispatch(state, "explore", ["110"])
    b1, b2 = state.branches
    assert state.session.state.id == s0 and state.pool.fingerprint() == pool_0

    dispatch(state, "observe", ["90"])
    s1 = state.session.state.id
    pool_1 = state.pool.fingerprint()
    assert pool_1 != pool_0
    dispatch(state, "decide", [])
    d1 = state.last_decision

    dispatch(state, "observe", ["100"])
    s2 = state.session.state.id
    pool_2 = state.pool.fingerprint()
    assert pool_2 != pool_1

    # three distinct real states, in order, verified as a real update chain
    assert len({s0, s1, s2}) == 3
    assert [s.id for s in state.session.state_history] == [s0, s1, s2]

    timeline = dispatch(state, "timeline", [])
    views = [dispatch(state, "timeline", [str(i)]) for i in range(3)]
    inspects = [dispatch(state, "inspect", ["state", str(i)]) for i in range(3)]
    assert views == inspects

    # chronological order and the current marker
    assert timeline.index("S0  ") < timeline.index("S1  ") < timeline.index("S2  ")
    assert timeline.count("CURRENT") == 1
    assert "CURRENT" in next(ln for ln in timeline.splitlines() if theme.ident(s2) in ln)

    # observations and residuals, derived from the model rather than assumed
    assert state.assessments[0].observed_value == 90.0
    assert state.assessments[0].residual is None            # no prediction existed at S0
    assert state.assessments[1].observed_value == 100.0
    assert state.assessments[1].predicted_value == 90.0
    assert state.assessments[1].residual == 10.0            # signed
    assert "+10.0" in timeline

    # decisions sit at the states they were computed at
    assert state.decision_at(s0) is d0
    assert state.decision_at(s1) is d1
    assert state.decision_at(s2) is None

    # branches remain hypothetical and attached to S0
    assert b1.source_state_id == b2.source_state_id == s0
    assert state.branches_from(s0) == [b1, b2]
    assert state.branches_from(s2) == []
    assert {b1.projected_state_id, b2.projected_state_id} & {s0, s1, s2} == set()
    assert "NOT ADMITTED" in dispatch(state, "branches", [])

    # historical states still reproduce themselves
    assert state.prediction_at(candidate, state.session.state_history[0]).sample_count == 0
    assert state.prediction_at(candidate, state.session.state_history[1]).predicted_value == 90.0
    assert state.prediction_at(candidate, state.session.state_history[2]).predicted_value == 95.0

    # the comparison surface still agrees with the timeline
    dispatch(state, "compare", ["state", "1", "state", "3"])
    dispatch(state, "compare", ["branch", "1", "branch", "2"])

    # and none of the inspection changed anything
    assert state.session.state.id == s2
    assert state.pool.fingerprint() == pool_2
    assert len(state.branches) == 2
    assert len(state.session.state_history) == 3
