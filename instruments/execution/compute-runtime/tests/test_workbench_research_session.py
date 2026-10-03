"""Phase 71: one strong integration test exercising the actual CLI
interaction layer (`workbench.cli.dispatch`/`parse_command`) through a
realistic human-driven research session -- the same loop `python -m
workbench` supports interactively: inspect -> predict -> explore ->
decide -> explicitly select -> externally supply an observation ->
observe -> inspect residual -> inspect history -> inspect diagnostics ->
repeat.

ONE DELIBERATE ADAPTATION from the phase's own illustrative command
list: that list (and the Goal section's workflow diagram) shows
`predict`/`explore <value>` appearing BEFORE `select <n>`. The CLI's own
already-established design (Phase 68 sec.9, reaffirmed Phase 70) makes
candidate selection an explicit, required human choice -- `predict`/
`explore`/`observe`/`history`/`diagnostics` all operate on "the selected
candidate" and correctly, honestly refuse (rather than guessing) when
none is selected yet. This test exercises BOTH: it first confirms that
calling `predict`/`explore` before any `select` produces an honest
refusal, never a fabricated number (itself a form of "no fabricated
prediction"), and then runs the full predict/explore/decide/select/
observe/history/diagnostics loop in the order that actually succeeds --
select once, immediately after `decide`, before any single-candidate
inspection.
"""

import pytest

from materials.model_state import HYPOTHETICAL_SAMPLE_PREFIX
from tests.test_workbench_boundaries import test_materials_never_imports_workbench
from workbench.cli import dispatch, parse_command
from workbench.interaction import WorkbenchState, bootstrap_multi_candidate_scenario


def _fixed_clock():
    counter = {"n": 0}

    def clock() -> str:
        n = counter["n"]
        counter["n"] += 1
        return f"2026-08-24T04:{n:02d}:00Z"

    return clock


@pytest.fixture()
def state() -> WorkbenchState:
    return bootstrap_multi_candidate_scenario(clock=_fixed_clock())


def test_full_research_session_through_cli_dispatch(state: WorkbenchState):
    # -- inspect, before any selection -- predict/explore honestly refuse, never fabricate ------------
    status_0 = dispatch(state, "status", [])
    assert "CANDIDATES" in status_0
    candidates_0 = dispatch(state, "candidates", [])
    assert candidates_0.count("UNDETERMINED") >= 2  # both candidates, prediction + uncertainty

    predict_before_select = dispatch(state, "predict", [])
    assert "no candidate selected" in predict_before_select
    explore_before_select = dispatch(state, "explore", ["90"])
    assert "no candidate selected" in explore_before_select

    # -- decide: a recommendation, never a selection ----------------------------------------------------
    decide_1 = dispatch(state, "decide", [])
    assert "RECOMMENDATION" in decide_1
    assert "ADVISORY ONLY" in decide_1
    assert state.selected_candidate is None  # (3) decide never selects

    # -- explicit select: interaction state only, no evidence transition ---------------------------------
    select_output = dispatch(state, "select", ["1"])
    assert "CANDIDATE SELECTED" in select_output
    assert "No experiment has been executed." in select_output
    candidate = state.selected_candidate
    assert candidate is not None  # (4) select changed interaction state

    initial_state = state.session.state
    initial_fingerprint = state.pool.fingerprint()

    # (1) the first prediction is genuinely undetermined -- read directly off the real ModelState
    assert state.session.predict(candidate).predicted_value is None
    predict_1 = dispatch(state, "predict", [])
    assert "UNDETERMINED" in predict_1

    # -- explore: hypothetical only, never touches the live session --------------------------------------
    explore_output = dispatch(state, "explore", ["90"])
    assert "This branch is hypothetical." in explore_output
    assert "NOT been admitted as evidence" in explore_output
    assert "LIVE SESSION" in explore_output and "UNCHANGED" in explore_output
    outcome = state.last_counterfactual
    assert outcome is not None
    sample = next(iter(outcome.projected_state.samples.values()))[0]
    assert sample.observation_id.startswith(HYPOTHETICAL_SAMPLE_PREFIX)
    # (2) exploration does not change the live state
    assert state.session.state.id == initial_state.id
    assert state.pool.fingerprint() == initial_fingerprint

    # -- observe: the real, externally supplied result -- a genuine successor state ----------------------
    observe_1 = dispatch(state, "observe", ["80"])
    assert "externally supplied experimental observation" in observe_1
    assert "RESIDUAL" in observe_1 and "UNDETERMINED" in observe_1  # honest -- no prior sample in this cell
    successor_state_1 = state.session.state
    assert successor_state_1.id != initial_state.id  # (5) a real successor state
    # (6) the prior session/state remains immutable
    assert initial_state.samples == {} or all(
        not any(s.observation_id.startswith("workbench:observation:") for s in samples)
        for samples in initial_state.samples.values()
    )
    assert len(initial_state.samples) == 0
    # (12) EvidencePool fingerprint changed only on this real admission
    assert state.pool.fingerprint() != initial_fingerprint

    # (7) subsequent prediction changes because real evidence accumulated
    predict_2 = dispatch(state, "predict", [])
    assert "80.0" in predict_2
    assert state.session.predict(candidate).predicted_value == 80.0

    decide_2 = dispatch(state, "decide", [])
    assert "DECISION ANALYSIS" in decide_2

    # -- a second real observation -- signed residual preserved ------------------------------------------
    fingerprint_before_second_observe = state.pool.fingerprint()
    observe_2 = dispatch(state, "observe", ["100"])
    assert "+20.0" in observe_2  # (8) signed, never absolute-only
    assert state.pool.fingerprint() != fingerprint_before_second_observe

    predict_3 = dispatch(state, "predict", [])
    assert "90.0" in predict_3
    assert state.session.predict(candidate).predicted_value == 90.0
    # sample variance (n-1) of two samples 20 apart: (10^2 + 10^2) / 1 = 200
    assert state.session.predict(candidate).uncertainty == 200.0

    # -- history / diagnostics -- the real trajectory, not a reimplementation ----------------------------
    history_output = dispatch(state, "history", [])
    assert "UNDETERMINED" in history_output  # transition 1 -- no prior sample
    assert "80.0" in history_output  # transition 2 -- real accumulated evidence
    assert "+20.0" in history_output

    diagnostics_output = dispatch(state, "diagnostics", [])
    assert "+10.0" in diagnostics_output
    assert "+20.0" in diagnostics_output

    # (9) history references the correct predecessor prediction, and (10) diagnostics agree with the
    # trajectory -- verified directly against the real StateTransitionDiagnosticSet both commands share.
    diagnostic_set = state.history()
    assert len(diagnostic_set.diagnostics) == 2
    first, second = diagnostic_set.diagnostics
    assert first.previous_prediction.predicted_value is None
    assert second.previous_prediction.predicted_value == 80.0
    assert second.residual_against_previous_prediction == 20.0
    assert first.successor_state_id == second.predecessor_state_id  # transitions chain correctly

    # (11) no hypothetical sample appears anywhere in the real trajectory
    for samples in state.session.state.samples.values():
        for real_sample in samples:
            assert not real_sample.observation_id.startswith(HYPOTHETICAL_SAMPLE_PREFIX)

    # (13) no new identity mechanism -- every id involved is a real sha256 content hash
    for identifier in (
        state.session.state.id, candidate.id, state.assessments[-1].observation.id,
        diagnostic_set.diagnostics[0].predecessor_state_id,
    ):
        assert isinstance(identifier, str) and len(identifier) == 64

    # (14) materials/experiment/core remain independent of workbench -- reuse the real boundary test
    test_materials_never_imports_workbench()


def test_parse_command_and_quit():
    assert parse_command("select 1") == ("select", ["1"])
    assert parse_command("  observe   90  MPa ") == ("observe", ["90", "MPa"])
    assert parse_command("DECIDE") == ("decide", [])


def test_diagnostics_command_matches_history_command_data(state: WorkbenchState):
    """`diagnostics` is a second FORMAT over the same `StateTransitionDiagnosticSet`
    `history` already renders -- no second computation, no new trajectory
    abstraction (Phase 71 sec.6)."""
    dispatch(state, "select", ["1"])
    dispatch(state, "observe", ["80"])
    dispatch(state, "observe", ["100"])

    history_output = dispatch(state, "history", [])
    diagnostics_output = dispatch(state, "diagnostics", [])
    assert "80.0" in history_output and "80.0" in diagnostics_output
    assert "+20.0" in history_output and "+20.0" in diagnostics_output
    # diagnostics carries strictly more raw detail than the narrative history view
    assert "model_state_key" in diagnostics_output
    assert "model_state_key" not in history_output
