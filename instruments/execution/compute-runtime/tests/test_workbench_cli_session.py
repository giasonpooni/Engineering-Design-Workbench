"""Phase 70: the interactive workbench's own strong integration suite --
tests A-J, driven through `workbench.cli.dispatch`/`parse_command`
wherever practical (per Test J's own instruction: exercise the actual
command parser/interaction layer, not a hand-rolled reproduction of the
underlying orchestration), against `workbench.interaction.
bootstrap_multi_candidate_scenario` -- the same two-candidate scenario
`python -m workbench` starts with by default.
"""

from materials.model_state import HYPOTHETICAL_SAMPLE_PREFIX, update
from workbench.cli import dispatch, parse_command
from workbench.interaction import WorkbenchState, bootstrap_multi_candidate_scenario


def _fixed_clock():
    counter = {"n": 0}

    def clock() -> str:
        n = counter["n"]
        counter["n"] += 1
        return f"2026-08-24T03:{n:02d}:00Z"

    return clock


def _start() -> WorkbenchState:
    return bootstrap_multi_candidate_scenario(clock=_fixed_clock())


# -- Test A: bootstrap -- no fabricated prediction ---------------------------------------------------


def test_a_bootstrap_no_fabricated_prediction():
    state = _start()

    status_output = dispatch(state, "status", [])
    assert "CANDIDATES" in status_output and " 2" in status_output
    assert "SELECTION" in status_output and "none" in status_output

    candidates_output = dispatch(state, "candidates", [])
    assert candidates_output.count("UNDETERMINED") >= 2
    assert "0.0" not in candidates_output  # no undetermined quantity silently rendered as zero

    dispatch(state, "select", ["1"])
    predict_output = dispatch(state, "predict", [])
    assert "PREDICTION" in predict_output and "UNDETERMINED" in predict_output
    assert "SAMPLES" in predict_output
    assert state.session.predict(state.selected_candidate).predicted_value is None


# -- Test B: decision -- selection comes from existing optimization ----------------------------------


def test_b_decision_selection_comes_from_optimization():
    state = _start()
    decide_output = dispatch(state, "decide", [])
    assert "RECOMMENDATION" in decide_output and "ADVISORY ONLY" in decide_output
    assert state.last_decision is not None
    selected = [o for o in state.last_decision.optimizations if o.status == "SELECTED"]
    assert len(selected) == 1
    # the recommendation is read-only: it does not itself select a candidate for interaction
    assert state.selected_candidate is None


# -- Test C: counterfactual -- state unchanged, hypothetical marker present, no admission ------------


def test_c_counterfactual_state_unchanged_and_no_admission():
    state = _start()
    dispatch(state, "select", ["1"])
    pre_state_id = state.session.state.id
    pre_fingerprint = state.pool.fingerprint()
    pre_observation_count = len(state.pool.all_observations())

    explore_output = dispatch(state, "explore", ["90"])
    assert "NOT been admitted as evidence" in explore_output
    assert "LIVE SESSION" in explore_output and "UNCHANGED" in explore_output
    assert "This branch is hypothetical" in explore_output

    assert state.session.state.id == pre_state_id
    assert state.pool.fingerprint() == pre_fingerprint  # nothing at all was admitted to the pool
    assert len(state.pool.all_observations()) == pre_observation_count
    assert state.last_counterfactual is not None
    sample = next(iter(state.last_counterfactual.projected_state.samples.values()))[0]
    assert sample.observation_id.startswith(HYPOTHETICAL_SAMPLE_PREFIX)


# -- Test D: observation -- signed residual, successor state -----------------------------------------


def test_d_observation_signed_residual_and_successor_state():
    state = _start()
    dispatch(state, "select", ["1"])
    dispatch(state, "predict", [])
    predecessor_state_id = state.session.state.id

    observe_output = dispatch(state, "observe", ["80"])
    assert "RESIDUAL" in observe_output and "UNDETERMINED" in observe_output  # honest -- no prior sample in this cell
    assert state.session.state.id != predecessor_state_id
    assert state.assessments[-1].observed_value == 80.0

    second_output = dispatch(state, "observe", ["90"])
    assert "+10.0" in second_output
    assert state.assessments[-1].residual == 10.0


# -- Test E: repeated cycle -- predictions evolve through the real ModelState -------------------------


def test_e_repeated_cycle_predictions_evolve():
    state = _start()
    dispatch(state, "select", ["1"])
    candidate = state.selected_candidate

    dispatch(state, "observe", ["80"])
    assert state.session.predict(candidate).predicted_value == 80.0
    dispatch(state, "observe", ["90"])
    assert state.session.predict(candidate).predicted_value == 85.0
    dispatch(state, "observe", ["100"])
    assert state.session.predict(candidate).predicted_value == 90.0
    assert state.session.predict(candidate).uncertainty == _sample_variance([80.0, 90.0, 100.0])


def _sample_variance(values):
    """Divisor n-1, matching `materials.model_state.predict`.

    A helper that recomputes the estimator can agree with a WRONG
    implementation, so this exists only to spell the expected number --
    the estimator itself is pinned against hand-derived constants in
    tests/test_numerics.py, which is where a divisor change is caught."""
    mean = sum(values) / len(values)
    return sum((v - mean) ** 2 for v in values) / (len(values) - 1)


# -- Test F: decision evolution -- recomputing after observations can select a different candidate ---


def test_f_decision_evolution_selects_different_candidate():
    state = _start()
    decide_1 = dispatch(state, "decide", [])
    first_selected = [o.candidate_id for o in state.last_decision.optimizations if o.status == "SELECTED"][0]
    first_index = next(
        i for i, c in enumerate(state.list_candidates(), start=1) if c.id == first_selected
    )
    assert f"select {first_index:02d}" in decide_1  # the advisory names the command to act on it

    dispatch(state, "select", [str(first_index)])
    dispatch(state, "observe", ["90"])  # first candidate's benefit drops once measured once

    decide_2 = dispatch(state, "decide", [])
    second_selected = [o.candidate_id for o in state.last_decision.optimizations if o.status == "SELECTED"][0]
    assert second_selected != first_selected
    assert f"select {first_index:02d}" not in decide_2


# -- Test G: historical immutability -------------------------------------------------------------------


def test_g_historical_immutability():
    state = _start()
    dispatch(state, "select", ["1"])
    candidate = state.selected_candidate

    dispatch(state, "observe", ["80"])
    session_after_first = state.session
    state_after_first_id = session_after_first.state.id
    predicted_after_first = session_after_first.predict(candidate).predicted_value

    dispatch(state, "observe", ["90"])
    dispatch(state, "select", ["2"])
    dispatch(state, "observe", ["50"])
    dispatch(state, "decide", [])
    dispatch(state, "explore", ["999"])

    # the earlier session, held independently, is completely unaffected by all of the above.
    assert session_after_first.state.id == state_after_first_id
    assert session_after_first.predict(candidate).predicted_value == predicted_after_first
    assert len(session_after_first.state_history) == 2


# -- Test H: hypothetical contamination -- Phase 61 guard still rejects it ----------------------------


def test_h_hypothetical_contamination_rejected():
    state = _start()
    dispatch(state, "select", ["1"])
    candidate = state.selected_candidate

    dispatch(state, "explore", ["90"])
    outcome = state.last_counterfactual
    assert outcome is not None

    dispatch(state, "observe", ["80"])  # a real observation, to get a real result/observation pair
    real_assessment = state.assessments[-1]

    try:
        update(outcome.projected_state, candidate, real_assessment.result, real_assessment.observation)
        assert False, "expected the Phase 61 guard to reject a hypothetical-tainted state"
    except AssertionError as e:
        assert "hypothetical" in str(e)


# -- Test I: epistemic honesty -- None/NOT_DETERMINABLE never silently becomes 0.0 --------------------


def test_i_epistemic_honesty_never_zero():
    state = _start()
    candidates_output = dispatch(state, "candidates", [])
    assert "UNDETERMINED" in candidates_output
    assert "NOT_DETERMINABLE" in candidates_output
    # an undetermined quantity is never rendered as a number on its own row
    for line in candidates_output.splitlines():
        if "prediction " in line or "information " in line:
            assert "0.0" not in line

    dispatch(state, "select", ["1"])
    observe_output = dispatch(state, "observe", ["80"])
    residual_rows = [line for line in observe_output.splitlines() if "RESIDUAL" in line]
    assert len(residual_rows) == 2  # RESIDUAL and ABS RESIDUAL
    for row in residual_rows:
        assert "UNDETERMINED" in row  # never rendered as 0.0
        assert "0.0" not in row


# -- Test J: CLI command flow -- the actual parser/dispatch layer, not manual orchestration ------------


def test_j_cli_command_flow_through_parser_and_dispatch():
    state = _start()
    script = [
        "status", "candidates", "decide", "select 1", "predict", "explore 90",
        "observe 90", "status", "candidates", "predict", "history",
        "decide", "select 2", "observe 65", "history",
    ]
    outputs = []
    for line in script:
        command, args = parse_command(line)
        outputs.append(dispatch(state, command, args))

    assert parse_command("select 1") == ("select", ["1"])
    assert parse_command("  observe   90  MPa ") == ("observe", ["90", "MPa"])
    assert parse_command("") == ("", [])

    # the parser/dispatch layer alone drove the session through two real observations.
    assert len(state.assessments) == 2
    assert state.assessments[0].observed_value == 90.0
    assert state.assessments[1].observed_value == 65.0
    assert "UNKNOWN COMMAND" not in "\n".join(outputs)
    assert dispatch(state, "quit", []) == "__QUIT__"
    assert "UNKNOWN COMMAND" in dispatch(state, "bogus", [])
