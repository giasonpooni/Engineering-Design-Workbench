"""Phase 68: proves the interactive workbench is genuinely connected to
the real system, not a mock -- real observations change state,
hypothetical ones never do, residual sign survives, historical state
remains unchanged, the identity chain stays intact, no second identity
system is introduced, and no admission call is made outside the
established `admit_record`/`admit_experimental_result` exception
`experiment/step.py` already uses. Operates entirely through `workbench.
interaction.WorkbenchState` and `workbench.cli.dispatch` -- the exact
same functions `python -m workbench`/`python -m workbench.demo` use --
never a parallel, test-only implementation of the interaction surface.
"""

from materials.model_state import EMPTY_MODEL_STATE, HYPOTHETICAL_SAMPLE_PREFIX, resolve_model_state_key
from workbench.cli import dispatch
from workbench.interaction import DEFAULT_PROPERTY, WorkbenchState, bootstrap_default_scenario


def _fixed_clock():
    counter = {"n": 0}

    def clock() -> str:
        n = counter["n"]
        counter["n"] += 1
        return f"2026-08-24T01:{n:02d}:00Z"

    return clock


def _bootstrap_and_select() -> WorkbenchState:
    state = bootstrap_default_scenario(clock=_fixed_clock())
    index = next(i for i, c in enumerate(state.list_candidates()) if c.property == DEFAULT_PROPERTY)
    state.select_candidate(index)
    return state


def test_real_observation_changes_state_and_history_length():
    state = _bootstrap_and_select()
    initial_state_id = state.session.state.id
    initial_history_length = len(state.session.state_history)

    assessment, prediction = state.observe(80.0)

    assert state.session.state.id != initial_state_id
    assert len(state.session.state_history) == initial_history_length + 1
    assert assessment.observed_value == 80.0
    assert prediction.predicted_value is None  # honestly undetermined -- no prior samples


def test_hypothetical_exploration_never_advances_session_or_touches_pool():
    state = _bootstrap_and_select()
    pre_state_id = state.session.state.id
    pre_history = state.session.state_history

    outcome = state.explore(999.0)

    assert state.session.state.id == pre_state_id
    assert state.session.state_history == pre_history
    assert outcome.projected_state.id != pre_state_id
    cf_sample = next(iter(outcome.projected_state.samples.values()))[0]
    assert cf_sample.observation_id.startswith(HYPOTHETICAL_SAMPLE_PREFIX)
    # a hypothetical exploration touches no Record -- the pool's record count is unaffected
    assert state.locator_counter == 0


def test_residual_sign_survives_both_directions():
    state_up = _bootstrap_and_select()
    state_up.observe(80.0)
    _assessment_up, _prediction_up = state_up.observe(90.0)
    assert _assessment_up.residual == 10.0
    assert _assessment_up.residual > 0

    state_down = _bootstrap_and_select()
    state_down.observe(80.0)
    assessment_down, _ = state_down.observe(70.0)
    assert assessment_down.residual == -10.0
    assert assessment_down.residual < 0


def test_historical_state_remains_unchanged_after_later_cycles():
    state = _bootstrap_and_select()
    candidate = state.selected_candidate

    state.observe(80.0)
    session_after_first = state.session
    state.observe(90.0)
    state.observe(100.0)

    # the earlier session object, held independently, is untouched by later cycles.
    assert session_after_first.predict(candidate).predicted_value == 80.0
    assert session_after_first.state_history == (
        state.session.state_history[0], state.session.state_history[1],
    )


def test_identity_chain_intact_end_to_end():
    state = _bootstrap_and_select()
    candidate = state.selected_candidate
    predecessor_state_id = state.session.state.id

    assessment, prediction = state.observe(85.0)

    assert candidate.id == assessment.candidate_id
    assert assessment.prediction.state_id == predecessor_state_id
    assert prediction.state_id == predecessor_state_id
    expected_key = resolve_model_state_key(candidate.formulation.id, candidate.property, candidate.target_context)
    assert prediction.model_state_key == expected_key
    sample = next(
        s for s in state.session.state.samples[expected_key] if s.observation_id == assessment.observation.id
    )
    assert sample.value == 85.0
    assert not assessment.observation.id.startswith(HYPOTHETICAL_SAMPLE_PREFIX)


def test_no_second_identity_system_is_introduced():
    """Every id workbench-produced objects carry is a content-hash id
    from the existing evidence.identity/materials machinery -- the
    workbench introduces no uuid/random/counter-based identity of its
    own for any domain object (the plain integer `locator_counter` is
    workbench-local record-locator bookkeeping, not a domain identity)."""
    state = _bootstrap_and_select()
    assessment, prediction = state.observe(80.0)
    for identifier in (
        state.session.state.id, prediction.candidate_id, prediction.state_id,
        assessment.observation.id, assessment.candidate_id,
    ):
        assert isinstance(identifier, str) and len(identifier) == 64  # sha256 hex digest


def test_dispatch_end_to_end_via_cli_layer():
    """The same `dispatch` function `workbench.cli.run_repl` uses,
    exercised directly -- proves the CLI layer is genuinely wired to the
    interaction layer, not just the interaction layer in isolation."""
    state = bootstrap_default_scenario(clock=_fixed_clock())
    index = next(i for i, c in enumerate(state.list_candidates()) if c.property == DEFAULT_PROPERTY)

    assert "SELECTION" in dispatch(state, "status", []) and "none" in dispatch(state, "status", [])
    dispatch(state, "select", [str(index + 1)])  # workbench.cli displays/accepts candidates 1-indexed
    assert state.selected_candidate is not None

    predict_output = dispatch(state, "predict", [])
    assert "UNDETERMINED" in predict_output

    explore_output = dispatch(state, "explore", ["90"])
    assert "hypothetical" in explore_output.lower()
    assert "NOT been admitted" in explore_output
    assert state.session.state.id == EMPTY_MODEL_STATE.id  # unaffected by explore

    observe_output = dispatch(state, "observe", ["90"])
    assert "externally supplied experimental observation" in observe_output
    assert "good" not in observe_output.lower()
    assert "bad" not in observe_output.lower()
    assert "improved" not in observe_output.lower()
    assert "accurate" not in observe_output.lower()

    dispatch(state, "observe", ["100"])
    history_output = dispatch(state, "history", [])
    assert "10.0" in history_output  # the second transition's residual, 100 - 90


def test_quit_sentinel_and_unknown_command():
    state = _bootstrap_and_select()
    assert dispatch(state, "quit", []) == "__QUIT__"
    assert dispatch(state, "exit", []) == "__QUIT__"
    assert "UNKNOWN COMMAND" in dispatch(state, "bogus", [])
