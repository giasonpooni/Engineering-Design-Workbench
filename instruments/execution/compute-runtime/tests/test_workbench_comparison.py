"""Phase 89: comparative analysis.

INVESTIGATION RESULT -- no `Comparison` domain object was built, because
the algebra already expresses every comparison this phase asks for:

  `materials.trajectory.compare_predictions` -> `PredictionDelta`
      the comparison primitive. Signed, and `None` on either side
      whenever a quantity is undetermined. Works on ANY two Predictions
      for one candidate, and `predict(state, candidate)` reads a
      Prediction from any ModelState -- real OR projected. That single
      fact is what makes real/real, real/hypothetical and
      hypothetical/hypothetical the same operation.

  `materials.diagnostics.StateTransitionDiagnostic`
      already carries both predictions, both deltas, the admitted
      observation, the signed residual and the absolute residual for one
      adjacent real pair. A real-to-real comparison needs nothing more.

  `materials.ensemble.CounterfactualOutcome`   the hypothetical operand
  `materials.optimization.OptimizationResult`  the decision operand

So `compare` is a RENDERER. `workbench.cli._Operand` is a presentation
handle holding an existing ModelState and (when hypothetical) the
existing retained outcome; it carries no quantity of its own.

ONE thing was genuinely missing and is recorded rather than derived:
`OptimizationResult` carries no state id, so which real state a decision
was computed against was unknowable after the fact. The workbench knows
it at `decide()` time, so it now stores that existing `ModelState.id`.
Nothing is minted; without it the D -> observation -> S' -> D' loop
cannot be shown at all.
"""

import json
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
        return f"2026-08-24T15:{n['i']:02d}:00Z"

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


# -- operand resolution ------------------------------------------------------------------------------


def test_bare_compare_with_no_previous_state_says_so(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    text = dispatch(state, "compare", [])
    assert "NO PREVIOUS REAL STATE" in text
    assert "EXPECTED" in text
    assert "0.0" not in text  # a missing state is not a zero quantity


def test_bare_compare_uses_the_last_real_transition(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    s0 = state.session.state.id
    dispatch(state, "observe", ["90"])
    s1 = state.session.state.id

    text = dispatch(state, "compare", [])
    assert "STATE COMPARISON" in text
    assert theme.ident(s0) in text and theme.ident(s1) in text


def test_compare_one_branch_is_against_the_current_real_state(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    dispatch(state, "explore", ["70"])
    text = dispatch(state, "compare", ["branch", "1"])
    assert theme.ident(state.session.state.id) in text
    assert theme.ident(state.branches[0].projected_state_id) in text
    assert "COUNTERFACTUAL COMPARISON" in text


def test_every_compare_rejection_names_the_expected_form(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    dispatch(state, "explore", ["70"])
    for args in (["state", "99"], ["branch", "99"], ["branch", "x"], ["state"],
                 ["nonsense"], ["branch", "1", "nonsense", "2"]):
        assert "EXPECTED" in dispatch(state, "compare", args), args


def test_compare_without_a_selection_says_what_is_missing(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    dispatch(state, "observe", ["90"])
    dispatch(state, "select", ["clear"])
    text = dispatch(state, "compare", [])
    assert "EXPECTED" in text


# -- the three state comparison modes ----------------------------------------------------------------


def test_real_to_real_is_single_ruled_and_carries_the_admitted_observation(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    dispatch(state, "observe", ["80"])
    dispatch(state, "observe", ["90"])  # predicted 80, observed 90 -> residual +10.0

    text = dispatch(state, "compare", [])
    assert "╔" not in text and "║" not in text  # real evidence is never double-ruled
    assert "OBSERVATION" in text and "90.0" in text
    assert "+10.0" in text                        # signed, from the existing diagnostic
    assert "ABS RESIDUAL" in text
    assert "HYPOTHETICAL" not in text


def test_real_to_hypothetical_is_double_ruled_and_admits_nothing(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    dispatch(state, "observe", ["90"])
    dispatch(state, "explore", ["70"])

    text = dispatch(state, "compare", ["branch", "1"])
    assert "╔" in text
    assert "HYPOTHETICAL" in text and "NOT ADMITTED AS EVIDENCE" in text
    assert "NO OBSERVATION" in text
    # projecting ADDS a hypothetical sample, it does not replace the real one:
    # the real prediction is 90.0, the projected one is mean(90, 70) = 80.0.
    assert state.session.predict(state.selected_candidate).predicted_value == 90.0
    assert state.branches[0].prediction_after.predicted_value == 80.0
    assert "-10.0" in text  # signed, and it is the delta -- not either value


def test_hypothetical_to_hypothetical_ranks_nothing(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    dispatch(state, "explore", ["70"])
    dispatch(state, "explore", ["110"])

    text = dispatch(state, "compare", ["branch", "1", "branch", "2"])
    assert "COUNTERFACTUAL COMPARISON" in text
    assert "y = 70.0" in text and "y = 110.0" in text
    assert "+40.0" in text
    # both branches hang off the same parent, and that parent is shown
    assert text.count(theme.ident(state.branches[0].source_state_id)) >= 2
    lowered = text.lower()
    for phrase in ("better", "worse", "superior", "preferred", "optimal", "more likely",
                   "probability", "confidence", "recommended branch"):
        assert phrase not in lowered, f"branch comparison claims too much: {phrase!r}"


def test_non_adjacent_real_states_report_no_available_observation(state: WorkbenchState):
    """S1 vs S3 is a real comparison, but it is not one admitted
    transition, so there is no single observation or residual to show."""
    dispatch(state, "select", ["1"])
    dispatch(state, "observe", ["80"])
    dispatch(state, "observe", ["90"])

    text = dispatch(state, "compare", ["state", "1", "state", "3"])
    assert "NOT AVAILABLE" in text
    assert "RESIDUAL" in text and "UNDETERMINED" in text
    assert "not one admitted transition apart" in text


def test_branches_of_different_candidates_are_refused_rather_than_forced(state: WorkbenchState):
    """`compare_predictions` requires one candidate. Two branches on
    different candidates are not two readings of one quantity, so the
    workbench says so instead of working around the requirement."""
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "explore", ["70"])
    dispatch(state, "select", ["baseline", "120"])
    dispatch(state, "explore", ["70"])

    text = dispatch(state, "compare", ["branch", "1", "branch", "2"])
    assert "INCOMPARABLE BRANCHES" in text
    assert "EXPECTED" in text


# -- decision comparison -----------------------------------------------------------------------------


def test_decision_comparison_before_any_decision_says_so(state: WorkbenchState):
    assert "NO DECISION YET" in dispatch(state, "compare", ["decisions"])


def test_decision_comparison_with_one_decision_says_so(state: WorkbenchState):
    dispatch(state, "decide", [])
    text = dispatch(state, "compare", ["decisions"])
    assert "ONLY ONE DECISION" in text
    assert "EXPECTED" in text


def test_decision_comparison_uses_the_stored_objects_not_a_recomputation(state: WorkbenchState):
    dispatch(state, "decide", [])
    previous = state.last_decision
    dispatch(state, "select", ["1"])
    dispatch(state, "observe", ["85"])
    dispatch(state, "decide", [])
    current = state.last_decision

    dispatch(state, "compare", ["decisions"])
    assert state.previous_decision is previous  # the SAME objects
    assert state.last_decision is current


def test_decision_comparison_shows_the_observation_loop(state: WorkbenchState):
    """D1 at S0 -> observation -> D2 at S1: the state each decision was
    computed against is shown, so the loop is legible."""
    dispatch(state, "decide", [])
    s0 = state.session.state.id
    dispatch(state, "select", ["1"])
    dispatch(state, "observe", ["85"])
    s1 = state.session.state.id
    dispatch(state, "decide", [])

    text = dispatch(state, "compare", ["decisions"])
    assert theme.ident(s0) in text
    assert theme.ident(s1) in text
    assert "COMPUTED AT" in text
    assert "RECOMMENDATION" in text


def test_decision_basis_never_asserts_a_change_that_did_not_happen(state: WorkbenchState):
    """Two decisions at the SAME state cannot differ, and the basis must
    not recite a stock sentence about evidence changing anything."""
    dispatch(state, "decide", [])
    dispatch(state, "decide", [])
    text = dispatch(state, "compare", ["decisions"])
    assert "UNCHANGED" in text
    assert "Both decisions were computed at the same state" in text
    assert "changed the subsequent utility landscape and recommendation" not in text


def test_decision_basis_makes_no_causal_material_claim(state: WorkbenchState):
    dispatch(state, "decide", [])
    dispatch(state, "select", ["1"])
    dispatch(state, "observe", ["85"])
    dispatch(state, "decide", [])
    lowered = dispatch(state, "compare", ["decisions"]).lower()
    for phrase in ("proved", "proves", "caused the material", "is better", "performs better",
                   "outperform", "superior", "confirms", "validates"):
        assert phrase not in lowered, f"causal claim in decision comparison: {phrase!r}"
    assert "no scientific claim is made" in lowered


# -- isolation: comparison is observational ----------------------------------------------------------


def test_comparison_mutates_nothing(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    dispatch(state, "decide", [])
    dispatch(state, "explore", ["70"])
    dispatch(state, "explore", ["110"])
    dispatch(state, "observe", ["90"])
    dispatch(state, "decide", [])

    session = state.session
    state_id = state.session.state.id
    fingerprint = state.pool.fingerprint()
    observations = len(state.pool.all_observations())
    history = len(state.session.state_history)
    assessments = len(state.assessments)
    branch_ids = [b.projected_state_id for b in state.branches]
    branch_objects = list(state.branches)
    decision, previous = state.last_decision, state.previous_decision
    selected = state.selected_candidate

    for args in ([], ["branch", "1"], ["branch", "1", "branch", "2"],
                 ["state", "1", "state", "2"], ["decisions"]):
        dispatch(state, "compare", args)

    assert state.session is session
    assert state.session.state.id == state_id
    assert state.pool.fingerprint() == fingerprint
    assert len(state.pool.all_observations()) == observations
    assert len(state.session.state_history) == history
    assert len(state.assessments) == assessments
    assert [b.projected_state_id for b in state.branches] == branch_ids
    assert state.branches == branch_objects  # no branch created, none re-identified
    assert state.last_decision is decision
    assert state.previous_decision is previous
    assert state.selected_candidate is selected


def test_comparison_leaves_an_earlier_session_immutable(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    dispatch(state, "observe", ["80"])
    held = state.session
    held_id = held.state.id
    held_prediction = held.predict(state.selected_candidate).predicted_value

    dispatch(state, "explore", ["70"])
    dispatch(state, "observe", ["90"])
    for args in ([], ["branch", "1"], ["state", "1", "state", "2"]):
        dispatch(state, "compare", args)

    assert held.state.id == held_id
    assert held.predict(state.selected_candidate).predicted_value == held_prediction


# -- identity ----------------------------------------------------------------------------------------


def test_comparison_shows_only_pre_existing_content_hashes(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    dispatch(state, "explore", ["70"])
    dispatch(state, "observe", ["90"])

    real_ids = {s.id for s in state.session.state_history}
    branch_ids = {b.projected_state_id for b in state.branches}
    known = {theme.ident(i) for i in real_ids | branch_ids}
    known |= {theme.ident(c.id) for c in state.list_candidates()}
    known |= {theme.ident(b.model_state_key) for b in state.branches}

    import re
    for args in ([], ["branch", "1"]):
        text = dispatch(state, "compare", args)
        for token in re.findall(r"·[0-9a-f]{12}", text):
            assert token in known, f"comparison rendered an identity from nowhere: {token}"


# -- honesty -----------------------------------------------------------------------------------------


def test_comparison_never_renders_an_unknown_as_zero(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    dispatch(state, "explore", ["70"])
    dispatch(state, "observe", ["90"])
    dispatch(state, "decide", [])

    for args in ([], ["branch", "1"], ["state", "1", "state", "2"], ["decisions"]):
        text = dispatch(state, "compare", args)
        for line in text.splitlines():
            for cell in line.split(theme.TRANSITION):
                if theme.UNDETERMINED in cell:
                    after = cell.split(theme.UNDETERMINED, 1)[1]
                    assert not any(ch.isdigit() for ch in after), f"{args}: {line!r}"


def test_undetermined_is_never_a_section_title(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    dispatch(state, "explore", ["70"])
    dispatch(state, "observe", ["90"])
    for args in ([], ["branch", "1"]):
        for line in dispatch(state, "compare", args).splitlines():
            if line.lstrip("│║ ").startswith("─ "):  # a divider row
                assert theme.UNDETERMINED not in line


def test_a_projection_is_never_called_an_observation(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    dispatch(state, "explore", ["70"])
    text = dispatch(state, "compare", ["branch", "1"])
    assert "NO OBSERVATION" in text
    assert "a projection is never an observation" in text
    # and the real observation view never borrows hypothetical language
    observation_view = dispatch(state, "observe", ["90"])
    assert "HYPOTHETICAL" not in observation_view
    assert "NOT ADMITTED" not in observation_view


def test_a_negative_residual_is_never_shown_unsigned(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    dispatch(state, "observe", ["90"])
    dispatch(state, "observe", ["60"])  # predicted 90, observed 60 -> -30.0
    assert state.assessments[-1].residual == -30.0

    text = dispatch(state, "compare", [])
    residual_rows = [ln for ln in text.splitlines() if "RESIDUAL" in ln and "ABS" not in ln]
    assert residual_rows
    assert any("-30.0" in ln for ln in residual_rows)
    # 30.0 unsigned appears ONLY on the row that names itself absolute
    absolute_rows = [ln for ln in text.splitlines() if "ABS RESIDUAL" in ln]
    assert len(absolute_rows) == 1 and "30.0" in absolute_rows[0]


# -- determinism -------------------------------------------------------------------------------------


def test_the_same_session_twice_produces_identical_comparisons():
    def run() -> tuple:
        state = _start()
        dispatch(state, "select", ["baseline", "80"])
        dispatch(state, "decide", [])
        dispatch(state, "explore", ["70"])
        dispatch(state, "explore", ["110"])
        dispatch(state, "observe", ["90"])
        dispatch(state, "decide", [])
        return tuple(
            dispatch(state, "compare", args)
            for args in ([], ["branch", "1"], ["branch", "1", "branch", "2"],
                         ["state", "1", "state", "2"], ["decisions"])
        )

    assert run() == run()


# -- integration -------------------------------------------------------------------------------------


def test_full_cycle_comparison(state: WorkbenchState):
    """S0 -> D0 -> B1/B2 -> observe -> S1 -> D1, then every comparison."""
    dispatch(state, "select", ["baseline", "80"])
    candidate = state.selected_candidate
    s0 = state.session.state.id
    pool_before = state.pool.fingerprint()

    dispatch(state, "decide", [])
    d0 = state.last_decision
    dispatch(state, "explore", ["70"])
    dispatch(state, "explore", ["110"])
    b1, b2 = state.branches

    # nothing real moved during projection
    assert state.session.state.id == s0
    assert state.pool.fingerprint() == pool_before

    dispatch(state, "observe", ["90"])
    s1 = state.session.state.id
    assert s1 != s0
    assert state.pool.fingerprint() != pool_before  # the pool changed ONLY here
    pool_after = state.pool.fingerprint()

    dispatch(state, "decide", [])
    d1 = state.last_decision

    real_real = dispatch(state, "compare", ["state", "1", "state", "2"])
    branch_branch = dispatch(state, "compare", ["branch", "1", "branch", "2"])
    real_branch = dispatch(state, "compare", ["branch", "1"])
    decisions = dispatch(state, "compare", ["decisions"])

    # S0 unchanged and still in history; S1 distinct
    assert state.session.state_history[0].id == s0
    assert state.session.state_history[-1].id == s1
    assert theme.ident(s0) in real_real and theme.ident(s1) in real_real

    # B1/B2 still hypothetical and still attached to S0
    assert b1.source_state_id == b2.source_state_id == s0
    assert "NOT ADMITTED AS EVIDENCE" in branch_branch
    assert "NOT ADMITTED AS EVIDENCE" in real_branch
    for branch in (b1, b2):
        assert branch.projected_state_id not in {s.id for s in state.session.state_history}

    # the decision objects compared are the stored ones
    assert state.previous_decision is d0 and state.last_decision is d1
    assert theme.ident(s0) in decisions and theme.ident(s1) in decisions

    # signed residual survives: predicted UNDETERMINED at S0 (no samples)
    assert state.assessments[-1].observed_value == 90.0
    assert state.assessments[-1].residual is None
    assert state.session.predict(candidate).predicted_value == 90.0

    # and comparing changed nothing at all
    assert state.session.state.id == s1
    assert state.pool.fingerprint() == pool_after
    assert len(state.branches) == 2
