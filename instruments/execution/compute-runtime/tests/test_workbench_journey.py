"""Phase 82/83: the complete interactive journey, driven end to end
through the real CLI dispatch layer, plus terminal-width hardening.

One test walks the whole loop the workbench exists to support --
scenario, candidates, predict, explore, decide, select, observe,
residual, predict, decide, history, diagnostics, repeat -- across
multiple formulations and contexts, and asserts BOTH that the interface
stays coherent at every step and that every semantic invariant the
engine guarantees survives the journey:

    candidate identity · observation identity · state identity
    prediction provenance · signed residuals · counterfactual isolation
    EvidencePool boundaries · historical immutability
    decision recomputation
"""

import json
import shutil
from pathlib import Path

import pytest

from materials.model_state import HYPOTHETICAL_SAMPLE_PREFIX, resolve_model_state_key, update
from workbench import theme
from workbench.cli import dispatch, format_scenario_banner
from workbench.interaction import WorkbenchState, bootstrap_research_scenario

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_SCENARIO_PATH = REPO_ROOT / "examples" / "polymer_tensile_strength.json"


def _fixed_clock():
    counter = {"n": 0}

    def clock() -> str:
        n = counter["n"]
        counter["n"] += 1
        return f"2026-08-24T08:{n:02d}:00Z"

    return clock


@pytest.fixture(autouse=True)
def _plain():
    theme.set_color(False)
    yield
    theme.set_color(None)


@pytest.fixture()
def state() -> WorkbenchState:
    with open(EXAMPLE_SCENARIO_PATH, encoding="utf-8") as f:
        config = json.load(f)
    return bootstrap_research_scenario(config, clock=_fixed_clock())


def _index_of(state: WorkbenchState, candidate) -> str:
    return f"{state.list_candidates().index(candidate) + 1:02d}"


def _samples(state: WorkbenchState, candidate) -> int:
    key = resolve_model_state_key(candidate.formulation.id, candidate.property, candidate.target_context)
    return len(state.session.state.samples.get(key, ()))


def _recommended_id(state: WorkbenchState) -> str:
    return [o.candidate_id for o in state.decide().optimizations if o.status == "SELECTED"][0]


def _assert_coherent(name: str, text: str) -> None:
    """Whatever the state, the view is still a closed, correctly-sized
    frame -- the interface must remain understandable throughout."""
    lines = text.splitlines()
    assert lines, f"{name}: rendered nothing"
    for line in lines:
        if line.startswith(("┌", "│", "└", "╔", "║", "╚")):
            assert theme.visible_len(line) == theme.width(), f"{name}: ragged frame"
    assert lines[0].startswith(("┌", "╔")), f"{name}: no opening rule"
    assert lines[-1].startswith(("└", "╚")), f"{name}: no closing rule"


def test_complete_interactive_journey(state: WorkbenchState):
    candidates = state.list_candidates()
    assert len(candidates) == 9  # 3 formulations x 3 contexts

    # ---- START: nothing is known, and the interface says so ----------------------------------------
    for view in ("scenario", "status", "candidates"):
        text = dispatch(state, view, [])
        _assert_coherent(view, text)
    assert "0 of 9" in dispatch(state, "scenario", [])
    assert dispatch(state, "candidates", []).count("UNMEASURED") == 9

    # ---- DECIDE: a recommendation that selects nothing ----------------------------------------------
    decide_1 = dispatch(state, "decide", [])
    _assert_coherent("decide", decide_1)
    assert "ADVISORY ONLY" in decide_1
    assert state.selected_candidate is None  # recommendation != selection
    first_recommended = _recommended_id(state)
    subject = next(c for c in candidates if c.id == first_recommended)
    untouched = [c for c in candidates if c.id != subject.id]

    # ---- SELECT: an explicit human choice ------------------------------------------------------------
    _assert_coherent("select", dispatch(state, "select", [_index_of(state, subject)]))
    assert state.selected_candidate is not None
    assert state.selected_candidate.id == subject.id

    # ---- PREDICT: genuinely undetermined, never fabricated -------------------------------------------
    predict_0 = dispatch(state, "predict", [])
    _assert_coherent("predict", predict_0)
    assert theme.UNDETERMINED in predict_0
    assert state.session.predict(subject).predicted_value is None

    # ---- EXPLORE: a hypothetical branch, fully isolated -----------------------------------------------
    state_before_explore = state.session.state.id
    fingerprint_before_explore = state.pool.fingerprint()
    history_len_before = len(state.session.state_history)

    explore_text = dispatch(state, "explore", ["90"])
    _assert_coherent("explore", explore_text)
    assert "HYPOTHETICAL" in explore_text and "NOT been admitted as evidence" in explore_text
    outcome = state.last_counterfactual
    assert outcome is not None

    assert state.session.state.id == state_before_explore          # source session untouched
    assert state.pool.fingerprint() == fingerprint_before_explore  # EvidencePool untouched
    assert len(state.session.state_history) == history_len_before  # no real trajectory transition
    key = resolve_model_state_key(subject.formulation.id, subject.property, subject.target_context)
    hypothetical = next(
        s for s in outcome.projected_state.samples[key]
        if s.observation_id.startswith(HYPOTHETICAL_SAMPLE_PREFIX)
    )
    assert hypothetical.value == 90.0  # hypothetical marker preserved

    # ---- OBSERVE 1: first real evidence; residual honestly undetermined --------------------------------
    observe_1 = dispatch(state, "observe", ["80"])
    _assert_coherent("observe", observe_1)
    assert "externally supplied experimental observation" in observe_1
    assert theme.UNDETERMINED in observe_1  # no prior prediction to form a residual against
    assert state.pool.fingerprint() != fingerprint_before_explore  # real admission moved the pool
    assert _samples(state, subject) == 1
    session_after_first = state.session
    prediction_after_first = session_after_first.predict(subject).predicted_value
    assert prediction_after_first == 80.0

    # the counterfactual never entered real history
    for samples in state.session.state.samples.values():
        for sample in samples:
            assert not sample.observation_id.startswith(HYPOTHETICAL_SAMPLE_PREFIX)

    # ---- DECIDE AGAIN: the recommendation changed because the state changed -----------------------------
    assert _recommended_id(state) != first_recommended

    # ---- OBSERVE 2: a POSITIVE residual ------------------------------------------------------------------
    dispatch(state, "select", [_index_of(state, subject)])
    observe_2 = dispatch(state, "observe", ["100"])
    _assert_coherent("observe", observe_2)
    assert "+20.0" in observe_2  # 100 - 80, sign preserved
    assert state.assessments[-1].residual == 20.0
    assert state.session.predict(subject).predicted_value == 90.0

    # ---- OBSERVE 3: a NEGATIVE residual -------------------------------------------------------------------
    observe_3 = dispatch(state, "observe", ["60"])
    _assert_coherent("observe", observe_3)
    assert "-30.0" in observe_3  # 60 - mean(80, 100), never absolute-valued
    assert state.assessments[-1].residual == -30.0

    # ---- DECIDE AGAIN: recomputed once more, now that real uncertainty exists ------------------------------
    assert _recommended_id(state) == subject.id  # its own measured variance now dominates

    # ---- A SECOND CANDIDATE: another formulation, another context -------------------------------------------
    other = next(
        c for c in untouched
        if c.formulation.natural_key != subject.formulation.natural_key
        and dict(c.target_context) != dict(subject.target_context)
    )
    dispatch(state, "select", [_index_of(state, other)])
    _assert_coherent("observe", dispatch(state, "observe", ["71"]))
    assert _samples(state, other) == 1
    assert _samples(state, subject) == 3  # unaffected by the other candidate's evidence

    # ---- UNTOUCHED CANDIDATES stayed untouched ---------------------------------------------------------------
    for candidate in untouched:
        if candidate.id != other.id:
            assert _samples(state, candidate) == 0
            assert state.session.predict(candidate).predicted_value is None

    # ---- HISTORY / DIAGNOSTICS: two views over one trajectory --------------------------------------------------
    dispatch(state, "select", [_index_of(state, subject)])
    history = dispatch(state, "history", [])
    diagnostics = dispatch(state, "diagnostics", [])
    _assert_coherent("history", history)
    _assert_coherent("diagnostics", diagnostics)
    for text in (history, diagnostics):
        assert "+20.0" in text and "-30.0" in text  # both residual directions survive to review

    diagnostic_set = state.history()
    assert diagnostic_set.candidate_id == subject.id  # correspondence by id, never list position
    assert len(diagnostic_set.diagnostics) == len(state.session.state_history) - 1

    # ---- HISTORICAL IMMUTABILITY: the earlier session is unchanged by everything since ---------------------------
    assert session_after_first.predict(subject).predicted_value == prediction_after_first == 80.0
    assert len(session_after_first.state_history) == 2

    # ---- the journey ends in a coherent, still-readable console --------------------------------------------------
    for view in ("scenario", "status", "candidates", "decide"):
        _assert_coherent(view, dispatch(state, view, []))
    assert "2 of 9" in dispatch(state, "scenario", [])


# -- Phase 83: terminal-width hardening -----------------------------------------------------------------------


@pytest.mark.parametrize("columns, expected", [(40, 64), (66, 64), (82, 80), (200, 96)])
def test_frame_width_clamps_to_a_legible_band(monkeypatch, columns, expected):
    """Narrow terminals get a readable floor, wide ones a ceiling, so
    lines never become unscannably long or crushed."""
    monkeypatch.setattr(shutil, "get_terminal_size", lambda fallback=(80, 24): shutil.os.terminal_size((columns, 24)))
    assert theme.width() == expected


@pytest.mark.parametrize("columns", [40, 66, 82, 120, 200])
def test_every_view_renders_correctly_at_any_terminal_width(monkeypatch, state: WorkbenchState, columns):
    """The full view set stays framed and correctly sized at every
    supported width -- including the narrow floor, where clipping does
    the most work."""
    monkeypatch.setattr(shutil, "get_terminal_size", lambda fallback=(80, 24): shutil.os.terminal_size((columns, 24)))
    dispatch(state, "select", ["1"])
    dispatch(state, "observe", ["80"])
    dispatch(state, "observe", ["100"])
    dispatch(state, "explore", ["90"])
    for view, args in (
        ("scenario", []), ("status", []), ("candidates", []), ("decide", []),
        ("predict", []), ("explore", ["90"]), ("history", []), ("diagnostics", []),
        ("help", []), ("bogus", []),
    ):
        _assert_coherent(f"{view}@{columns}", dispatch(state, view, args))
    _assert_coherent(f"banner@{columns}", format_scenario_banner(state))


def test_rendering_is_deterministic_for_identical_state():
    """The same scenario driven the same way renders byte-identically --
    there is no wall-clock, ordering, or hash-seed dependence in the
    presentation layer."""
    def run() -> str:
        with open(EXAMPLE_SCENARIO_PATH, encoding="utf-8") as f:
            config = json.load(f)
        s = bootstrap_research_scenario(config, clock=_fixed_clock())
        dispatch(s, "select", ["1"])
        dispatch(s, "observe", ["80"])
        dispatch(s, "observe", ["100"])
        return "\n".join(
            dispatch(s, view, []) for view in
            ("scenario", "status", "candidates", "decide", "history", "diagnostics")
        )

    assert run() == run()


def test_counterfactual_state_still_cannot_enter_real_history(state: WorkbenchState):
    """The Phase 61 guard survives the whole UI rebuild."""
    dispatch(state, "select", ["1"])
    dispatch(state, "observe", ["80"])
    outcome = state.explore(999.0)
    real = state.assessments[-1]
    with pytest.raises(AssertionError, match="hypothetical"):
        update(outcome.projected_state, state.selected_candidate, real.result, real.observation)
