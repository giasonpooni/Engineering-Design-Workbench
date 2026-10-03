"""Phase 84/85: semantic candidate selection.

Removes the last forced translation from human intent into an integer.
A candidate can be named by the scenario's own vocabulary -- its
formulation and its context -- and resolves to EXACTLY the same
`ActionCandidate` object, with the same `candidate.id`, that numeric
selection yields. Nothing is fuzzy-matched, nothing is created, and
display position is never used as identity.

PHASE 85 NOTE -- `focus` is an ALIAS for `select`, not a parallel
concept. `WorkbenchState.selected_candidate` is already exactly what
Phase 85 describes: interaction state that never touches `ModelState`,
`EvidencePool` or prediction mathematics. Introducing a second name for
the same slot would be the duplicated abstraction the ramp's own rules
forbid. What genuinely did not exist was the ability to DEACTIVATE a
candidate, so `select clear` / `focus clear` was added.
"""

import json
from pathlib import Path

import pytest

from workbench import theme
from workbench.cli import dispatch, resolve_candidate
from workbench.interaction import WorkbenchState, bootstrap_research_scenario

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "polymer_tensile_strength.json"


def _clock():
    n = {"i": 0}

    def clock() -> str:
        n["i"] += 1
        return f"2026-08-24T09:{n['i']:02d}:00Z"

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


def _find(state, formulation, temperature):
    return next(
        c for c in state.list_candidates()
        if c.formulation.natural_key == formulation
        and dict(c.target_context) == {"temperature_c": temperature}
    )


# -- numeric selection still works ---------------------------------------------------------------------


def test_numeric_selection_still_selects_by_registry_number(state: WorkbenchState):
    dispatch(state, "select", ["3"])
    assert state.selected_candidate is state.list_candidates()[2]


@pytest.mark.parametrize("bad", ["0", "10", "99"])
def test_out_of_range_numbers_are_rejected_with_the_valid_range(state: WorkbenchState, bad):
    text = dispatch(state, "select", [bad])
    assert "CANDIDATE OUT OF RANGE" in text
    assert "1..9" in text
    assert state.selected_candidate is None


# -- semantic selection ---------------------------------------------------------------------------------


@pytest.mark.parametrize("args", [
    ["baseline", "80"],
    ["formulation=baseline", "context=80"],
    ["baseline", "@", "80"],
    ["baseline", "80c"],
    ["baseline", "temperature_c=80"],
])
def test_semantic_forms_all_resolve_to_the_same_candidate(state: WorkbenchState, args):
    expected = _find(state, "baseline", 80)
    dispatch(state, "select", args)
    assert state.selected_candidate is expected


def test_semantic_and_numeric_selection_yield_identical_identity(state: WorkbenchState):
    """The whole point: the semantic route must land on the exact object
    prediction, decision, observation and diagnostics all use."""
    expected = _find(state, "modified", 120)
    dispatch(state, "select", ["modified", "120"])
    by_name = state.selected_candidate
    dispatch(state, "select", [str(state.list_candidates().index(expected) + 1)])
    by_number = state.selected_candidate

    assert by_name is by_number is expected
    assert by_name.id == by_number.id == expected.id


def test_selection_order_of_terms_does_not_matter(state: WorkbenchState):
    dispatch(state, "select", ["80", "baseline"])
    assert state.selected_candidate is _find(state, "baseline", 80)


def test_property_can_be_named_explicitly(state: WorkbenchState):
    dispatch(state, "select", ["baseline", "80", "property=tensile_strength"])
    assert state.selected_candidate is _find(state, "baseline", 80)


# -- rejection: zero matches, ambiguity, bad selectors ----------------------------------------------------


def test_an_underspecified_term_is_rejected_as_ambiguous_never_guessed(state: WorkbenchState):
    text = dispatch(state, "select", ["baseline"])
    assert "AMBIGUOUS CANDIDATE" in text
    assert "matches 3 candidates" in text
    assert state.selected_candidate is None  # nothing was guessed


def test_a_context_alone_is_ambiguous_across_formulations(state: WorkbenchState):
    text = dispatch(state, "select", ["25"])
    assert "AMBIGUOUS CANDIDATE" in text
    assert state.selected_candidate is None


def test_an_unknown_formulation_is_rejected_and_lists_what_exists(state: WorkbenchState):
    text = dispatch(state, "select", ["titanium", "80"])
    assert "NO SUCH CANDIDATE" in text
    assert "baseline" in text and "high_filler" in text and "modified" in text
    assert state.selected_candidate is None


def test_an_unknown_context_is_rejected_and_lists_what_exists(state: WorkbenchState):
    text = dispatch(state, "select", ["baseline", "500"])
    assert "NO SUCH CANDIDATE" in text
    assert "25 C" in text and "80 C" in text and "120 C" in text
    assert state.selected_candidate is None


def test_an_unknown_selector_field_is_rejected(state: WorkbenchState):
    text = dispatch(state, "select", ["colour=blue"])
    assert "UNKNOWN SELECTOR" in text
    assert state.selected_candidate is None


def test_nothing_is_ever_fuzzy_matched(state: WorkbenchState):
    """A near-miss is a rejection, not a guess."""
    for near_miss in (["baselin", "80"], ["Baseline!", "80"], ["baseline", "8"]):
        text = dispatch(state, "select", near_miss)
        assert "NO SUCH CANDIDATE" in text
        assert state.selected_candidate is None


def test_resolution_never_creates_a_candidate(state: WorkbenchState):
    before = list(state.list_candidates())
    dispatch(state, "select", ["baseline", "80"])
    dispatch(state, "select", ["titanium", "80"])
    assert list(state.list_candidates()) == before


# -- mixed candidate sets ---------------------------------------------------------------------------------


def test_resolution_works_across_a_mixed_multi_formulation_set(state: WorkbenchState):
    """Every one of the nine candidates is reachable by name, and each
    resolves uniquely."""
    seen = set()
    for candidate in state.list_candidates():
        temperature = dict(candidate.target_context)["temperature_c"]
        resolved = resolve_candidate(state, [candidate.formulation.natural_key, str(temperature)])
        assert not isinstance(resolved, str), f"could not resolve {candidate.formulation.natural_key}/{temperature}"
        assert resolved is candidate
        seen.add(resolved.id)
    assert len(seen) == 9


# -- Phase 85: focus is select; clearing is the genuinely new capability -----------------------------------


def test_focus_is_an_alias_for_select_not_a_second_concept(state: WorkbenchState):
    assert dispatch(state, "focus", ["baseline", "80"]) == dispatch(state, "select", ["baseline", "80"])
    assert state.selected_candidate is _find(state, "baseline", 80)


def test_clearing_deactivates_without_touching_any_scientific_state(state: WorkbenchState):
    dispatch(state, "select", ["baseline", "80"])
    dispatch(state, "observe", ["82"])
    state_id = state.session.state.id
    fingerprint = state.pool.fingerprint()
    history = len(state.session.state_history)

    text = dispatch(state, "select", ["clear"])
    assert "SELECTION CLEARED" in text
    assert state.selected_candidate is None
    # ModelState, EvidencePool and trajectory are all untouched
    assert state.session.state.id == state_id
    assert state.pool.fingerprint() == fingerprint
    assert len(state.session.state_history) == history
    # and the commands that need a candidate say so honestly
    assert "no candidate selected" in dispatch(state, "predict", [])


def test_clearing_when_nothing_is_selected_explains_itself(state: WorkbenchState):
    text = dispatch(state, "select", ["clear"])
    assert "NOTHING SELECTED" in text


def test_switching_selection_clears_a_stale_counterfactual(state: WorkbenchState):
    dispatch(state, "select", ["baseline", "80"])
    dispatch(state, "explore", ["90"])
    assert state.last_counterfactual is not None
    dispatch(state, "select", ["modified", "25"])
    assert state.last_counterfactual is None  # a hypothetical never carries across candidates


def test_decide_never_changes_the_selection(state: WorkbenchState):
    dispatch(state, "select", ["high_filler", "120"])
    chosen = state.selected_candidate
    dispatch(state, "decide", [])
    assert state.selected_candidate is chosen
