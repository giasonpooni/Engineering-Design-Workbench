"""Phase 86/87: the inspection surface and the decision explanation.

Both commands are pure READ surfaces. Neither computes a scientific
quantity of its own: `inspect` reads `ExperimentSession.predict`,
`materials.diagnostics.diagnose_transitions` and the live
`OptimizationResult`; `explain` reads an ALREADY-COMPUTED
`OptimizationResult` and reports what the policy ranked. Every number
either of them shows must be byte-identical to the number the
corresponding `materials` call returns, and neither may advance the
session, admit evidence, or alter the pool.

PHASE 87 CONSTRAINT -- the explanation reports a COMPUTATION, never a
material. It may say the computed utility landscape changed. It may
never say an experiment proved a candidate better.
"""

import json
from pathlib import Path

import pytest

from experiment.session import trajectory_of
from materials.diagnostics import diagnose_transitions
from workbench import theme
from workbench.cli import dispatch
from workbench.interaction import WorkbenchState, bootstrap_research_scenario

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "polymer_tensile_strength.json"


def _clock():
    n = {"i": 0}

    def clock() -> str:
        n["i"] += 1
        return f"2026-08-24T11:{n['i']:02d}:00Z"

    return clock


@pytest.fixture(autouse=True)
def _plain():
    theme.set_color(False)
    yield
    theme.set_color(None)


@pytest.fixture()
def state() -> WorkbenchState:
    with open(EXAMPLE, encoding="utf-8") as f:
        return bootstrap_research_scenario(json.load(f), clock=_clock())


def _selected_id(optimization):
    chosen = [o for o in optimization.optimizations if o.status == "SELECTED"]
    return chosen[0].candidate_id if chosen else None


# -- Phase 86: inspection ----------------------------------------------------------------------------


def test_inspect_without_a_selection_names_what_was_expected(state: WorkbenchState):
    text = dispatch(state, "inspect", [])
    assert "EXPECTED" in text
    assert "UNDETERMINED" not in text  # a missing SELECTION is not a missing QUANTITY


def test_inspect_uses_the_selected_candidate(state: WorkbenchState):
    dispatch(state, "select", ["baseline", "80"])
    text = dispatch(state, "inspect", [])
    assert "baseline" in text and "80 C" in text


def test_inspect_accepts_an_index_and_semantic_terms_identically(state: WorkbenchState):
    dispatch(state, "select", ["baseline", "80"])
    by_selection = dispatch(state, "inspect", [])
    by_terms = dispatch(state, "inspect", ["baseline", "80"])
    candidate = state.selected_candidate
    index = next(
        i for i, c in enumerate(state.list_candidates(), start=1) if c.id == candidate.id
    )
    by_index = dispatch(state, "inspect", [str(index)])
    assert by_selection == by_terms == by_index


def test_inspect_reports_the_content_addressed_identity(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    candidate = state.selected_candidate
    text = dispatch(state, "inspect", [])
    # the rendered identity is a PREFIX of the real content hash -- never a
    # separate identifier minted by the workbench.
    assert candidate.id[:12] in text
    assert state.session.state.id[:12] in text
    assert "CANDIDATE_ID" in text and "MODEL STATE" in text


def test_inspect_at_bootstrap_is_honest_about_having_no_evidence(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    text = dispatch(state, "inspect", [])
    assert "No observation has been admitted for this candidate." in text
    assert "SAMPLES" in text
    prediction_rows = [ln for ln in text.splitlines() if "PREDICTION" in ln or "UNCERTAINTY" in ln]
    assert prediction_rows
    for row in prediction_rows:
        assert "UNDETERMINED" in row
        assert "0.0" not in row  # never substituted with zero


def test_inspect_discloses_policy_derived_utility(state: WorkbenchState):
    """Utility is a real number at zero samples ONLY because the workbench's
    exploration policy supplies its input. The view must say so, or the
    reader will take it for a measured quantity."""
    dispatch(state, "select", ["1"])
    text = dispatch(state, "inspect", [])
    assert "NOT_DETERMINABLE" in text
    assert "from exploration policy, not a measured quantity" in text


def test_inspect_after_observation_reports_the_real_transition(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    candidate = state.selected_candidate
    dispatch(state, "observe", ["80"])
    predecessor = state.session.state.id
    dispatch(state, "observe", ["90"])

    text = dispatch(state, "inspect", [])
    diagnostics = [
        d for d in diagnose_transitions(
            trajectory_of(state.session), candidate, tuple(state.assessments)
        ).diagnostics
        if d.assessment is not None
    ]
    last = diagnostics[-1]
    assert "TRANSITIONS" in text and str(len(diagnostics)) in text
    assert predecessor[:12] in text
    assert last.successor_state_id[:12] in text
    assert theme.TRANSITION in text


def test_inspect_residual_is_signed_and_matches_the_assessment(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    dispatch(state, "observe", ["80"])
    dispatch(state, "observe", ["90"])  # predicted 80, observed 90 -> +10.0
    assert state.assessments[-1].residual == 10.0
    text = dispatch(state, "inspect", [])
    assert "+10.0" in text

    dispatch(state, "observe", ["50"])  # predicted 85, observed 50 -> -35.0
    assert state.assessments[-1].residual == -35.0
    assert "-35.0" in dispatch(state, "inspect", [])


def test_inspect_prediction_equals_the_sessions_own_prediction(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    candidate = state.selected_candidate
    dispatch(state, "observe", ["80"])
    dispatch(state, "observe", ["100"])
    prediction = state.session.predict(candidate)
    assert prediction.predicted_value == 90.0
    text = dispatch(state, "inspect", [])
    assert "90.0" in text
    assert theme.num(prediction.uncertainty) in text


def test_inspect_never_advances_the_session_or_the_pool(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    dispatch(state, "observe", ["80"])
    state_id = state.session.state.id
    fingerprint = state.pool.fingerprint()
    observations = len(state.pool.all_observations())
    iteration = state.session.iteration
    assessments = len(state.assessments)

    for args in ([], ["1"], ["baseline", "80"], ["modified"]):
        dispatch(state, "inspect", args)

    assert state.session.state.id == state_id
    assert state.pool.fingerprint() == fingerprint
    assert len(state.pool.all_observations()) == observations
    assert state.session.iteration == iteration
    assert len(state.assessments) == assessments


def test_inspect_corresponds_by_candidate_id_not_position(state: WorkbenchState):
    """Two candidates share a formulation; inspecting one must report the
    other's context nowhere."""
    dispatch(state, "select", ["baseline", "25"])
    first = state.selected_candidate
    text = dispatch(state, "inspect", ["baseline", "120"])
    other = next(
        c for c in state.list_candidates()
        if c.formulation.natural_key == "baseline"
        and dict(c.target_context) == {"temperature_c": 120}
    )
    assert other.id != first.id
    assert other.id[:12] in text
    assert first.id[:12] not in text


def test_inspect_out_of_range_index_names_the_expected_form(state: WorkbenchState):
    text = dispatch(state, "inspect", ["99"])
    assert "EXPECTED" in text


# -- Phase 87: decision explanation ------------------------------------------------------------------


def test_explain_before_any_decision_names_what_was_expected(state: WorkbenchState):
    text = dispatch(state, "explain", [])
    assert "EXPECTED" in text and "decide" in text
    assert state.last_decision is None


def test_explain_reports_the_recommendation_the_optimizer_produced(state: WorkbenchState):
    dispatch(state, "decide", [])
    optimization = state.last_decision
    chosen_id = _selected_id(optimization)
    text = dispatch(state, "explain", [])
    chosen = next(c for c in state.list_candidates() if c.id == chosen_id)
    assert "RECOMMENDED" in text
    assert chosen.formulation.natural_key in text
    assert chosen.property in text
    # every candidate the optimizer considered appears, keyed by its own index
    for option in optimization.optimizations:
        candidate = next(c for c in state.list_candidates() if c.id == option.candidate_id)
        index = next(
            i for i, c in enumerate(state.list_candidates(), start=1) if c.id == candidate.id
        )
        assert f"{index:02d}" in text


def test_explain_utilities_are_not_recomputed(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    dispatch(state, "observe", ["85"])
    dispatch(state, "decide", [])
    text = dispatch(state, "explain", [])
    for option in state.last_decision.optimizations:
        assert theme.num(option.utility.utility) in text


def test_explain_first_decision_says_so(state: WorkbenchState):
    dispatch(state, "decide", [])
    text = dispatch(state, "explain", [])
    assert "This is the first decision in this session." in text
    assert "PREVIOUSLY" not in text


def test_explain_reports_an_unchanged_recommendation_as_unchanged(state: WorkbenchState):
    dispatch(state, "decide", [])
    first = _selected_id(state.last_decision)
    dispatch(state, "decide", [])  # nothing was observed in between
    assert _selected_id(state.last_decision) == first
    text = dispatch(state, "explain", [])
    assert "The recommendation is unchanged." in text


def test_explain_reports_a_changed_recommendation_in_computational_terms(state: WorkbenchState):
    dispatch(state, "decide", [])
    first = _selected_id(state.last_decision)
    index = next(
        i for i, c in enumerate(state.list_candidates(), start=1) if c.id == first
    )
    dispatch(state, "select", [str(index)])
    dispatch(state, "observe", ["85"])
    dispatch(state, "decide", [])
    assert _selected_id(state.last_decision) != first

    text = dispatch(state, "explain", [])
    assert "The recommendation changed because the computed" in text
    assert "utility landscape changed." in text
    assert "No claim is made about any material" in text
    assert "PREVIOUSLY" in text and "NOW" in text


def test_observation_demotes_rather_than_discards_the_prior_decision(state: WorkbenchState):
    """The comparison Phase 87 exists to report is precisely the one ACROSS
    an observation. A prior decision is stale as a recommendation but
    remains a true record of what the policy ranked beforehand."""
    dispatch(state, "decide", [])
    before = state.last_decision
    dispatch(state, "select", ["1"])
    dispatch(state, "observe", ["85"])
    assert state.last_decision is None  # stale: must be recomputed
    assert state.previous_decision is before  # held by reference, never recomputed


def test_explain_makes_no_causal_scientific_claim(state: WorkbenchState):
    dispatch(state, "decide", [])
    dispatch(state, "select", ["1"])
    dispatch(state, "observe", ["85"])
    dispatch(state, "decide", [])
    text = dispatch(state, "explain", []).lower()
    for phrase in (
        "proved", "proves", "shows that", "demonstrates", "because the material",
        "is better", "performs better", "outperform", "superior", "confirms",
        "the experiment proved",
    ):
        assert phrase not in text, f"causal scientific claim in explanation: {phrase!r}"


def test_explain_discloses_that_utility_rested_on_the_exploration_policy(state: WorkbenchState):
    dispatch(state, "decide", [])
    text = dispatch(state, "explain", [])
    assert "have no computable information value." in text
    assert "exploration policy, not from a measured quantity." in text
    assert "workbench.interaction._utility_input_for" in text


def test_explain_never_advances_the_session_or_the_pool(state: WorkbenchState):
    dispatch(state, "decide", [])
    state_id = state.session.state.id
    fingerprint = state.pool.fingerprint()
    decision = state.last_decision

    dispatch(state, "explain", [])
    dispatch(state, "explain", [])

    assert state.session.state.id == state_id
    assert state.pool.fingerprint() == fingerprint
    assert state.last_decision is decision  # the SAME object, not a recomputation
    assert state.previous_decision is None


def test_explain_undetermined_inputs_are_never_rendered_as_zero(state: WorkbenchState):
    dispatch(state, "decide", [])
    text = dispatch(state, "explain", [])
    for line in text.splitlines():
        for cell in line.split(theme.TRANSITION):
            if theme.UNDETERMINED in cell:
                after = cell.split(theme.UNDETERMINED, 1)[1]
                assert not any(ch.isdigit() for ch in after), line
