"""Phase 93: whole-state enumeration.

The CELL projection, as opposed to `timeline`'s temporal one and
`thread`'s single-candidate one:

    timeline  how did the global state evolve?      S0 -> S1 -> S2
    thread    how did ONE candidate's evidence      one row per state
              evolve through that chain?
    state     what does ONE state contain across    one row per candidate
              the complete candidate registry?

It is an ENUMERATION, never an interpretation. Phase 92 established that
different candidate cells are independently predicted quantities with no
defined scientific relation between them, so nothing here computes a
quantity spanning two rows: no difference, no ordering by value, no
aggregate, no ranking. Utility is deliberately absent -- Phase 92
classified it as a decision-policy quantity, and placing it beside a
prediction would invite exactly the reading this view exists to avoid.

NO new abstraction was required. The view composes `list_candidates()`
(registry order), `prediction_at(candidate, state)` and
`information_value_estimate(candidate, state)`, all of which already
existed. The one refactor is `_resolve_state_index`, lifted out of
`_cmd_timeline` so `state <n>` reuses the SAME state-selector semantics
rather than a parallel copy of it.
"""

import json
import re
from pathlib import Path

import pytest

from materials.model_state import resolve_model_state_key
from workbench import theme
from workbench.cli import dispatch
from workbench.interaction import WorkbenchState, bootstrap_research_scenario

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "polymer_tensile_strength.json"


def _clock():
    n = {"i": 0}

    def clock() -> str:
        n["i"] += 1
        return f"2026-08-24T23:{n['i']:02d}:00Z"

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


def _cand(state: WorkbenchState, formulation: str, temperature: int):
    return next(
        c for c in state.list_candidates()
        if c.formulation.natural_key == formulation
        and dict(c.target_context) == {"temperature_c": temperature}
    )


def _cells(text: str) -> list:
    """The (index, formulation-line) pairs the view enumerated."""
    return re.findall(r"(\d{2})  ([a-z_]+ · [a-z_]+ · [-\d.]+ C)", text)


def _rows_for(text: str, index: str) -> list:
    start = text.index(f"{index}  ")
    following = [
        text.find(f"{n:02d}  ", start + 1) for n in range(int(index) + 1, 40)
    ]
    ends = [i for i in following if i > start]
    block = text[start:min(ends)] if ends else text[start:]
    return [ln.strip().strip("│").strip() for ln in block.splitlines()]


# -- complete, lossless enumeration ------------------------------------------------------------------


def test_every_candidate_appears_exactly_once(state: WorkbenchState):
    text = dispatch(state, "state", [])
    cells = _cells(text)
    candidates = state.list_candidates()
    assert len(cells) == len(candidates) == 9
    assert len({index for index, _ in cells}) == len(cells)  # no duplicates


def test_zero_sample_candidates_remain_visible(state: WorkbenchState):
    """A search space is not the same thing as the evidence gathered in
    it. At bootstrap NOTHING has evidence, and all nine cells still show."""
    text = dispatch(state, "state", [])
    assert len(_cells(text)) == 9
    assert text.count("samples     0") == 9
    assert "CELLS WITH EVIDENCE" in text


def test_an_undetermined_prediction_stays_undetermined(state: WorkbenchState):
    text = dispatch(state, "state", [])
    for line in text.splitlines():
        row = line.strip().strip("│").strip()
        if row.startswith(("├ prediction", "└ prediction", "├ uncertainty", "└ uncertainty")):
            if theme.UNDETERMINED in row:
                after = row.split(theme.UNDETERMINED, 1)[1]
                assert not any(ch.isdigit() for ch in after), row


def test_the_enumeration_covers_every_occupied_cell(state: WorkbenchState):
    """The Phase 92 losslessness proof, re-asserted through the VIEW:
    no cell occupied in the ModelState can be missing from the render."""
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["80"])
    dispatch(state, "select", ["modified", "25"])
    dispatch(state, "observe", ["70"])
    dispatch(state, "select", ["high_filler", "120"])
    dispatch(state, "observe", ["55"])

    model_state = state.session.state
    text = dispatch(state, "state", [])
    rendered = {formulation for _, formulation in _cells(text)}

    for key in model_state.samples:
        owner = next(
            c for c in state.list_candidates()
            if resolve_model_state_key(c.formulation.id, c.property, c.target_context) == key
        )
        label = f"{owner.formulation.natural_key} · {owner.property} · "
        assert any(line.startswith(label) for line in rendered), key


def test_the_cell_count_matches_the_registry_not_the_evidence(state: WorkbenchState):
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["80"])
    text = dispatch(state, "state", [])
    assert "CANDIDATE CELLS   9" in text.replace("  ", "  ")
    assert len(_cells(text)) == 9


# -- ordering ----------------------------------------------------------------------------------------


def test_candidate_order_is_the_registry_order(state: WorkbenchState):
    """Registry order, never an ordering by any displayed value."""
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["80"])
    dispatch(state, "select", ["modified", "25"])
    dispatch(state, "observe", ["70"])

    text = dispatch(state, "state", [])
    cells = _cells(text)
    for position, (index, label) in enumerate(cells, start=1):
        candidate = state.list_candidates()[position - 1]
        assert int(index) == position
        assert label.startswith(candidate.formulation.natural_key)


def test_the_order_is_not_sorted_by_any_displayed_value(state: WorkbenchState):
    """After observing a LATER-indexed candidate a higher value, the
    order must not move: 01 stays 01."""
    dispatch(state, "select", ["modified", "25"])   # registry index 04
    dispatch(state, "observe", ["999"])
    text = dispatch(state, "state", [])
    cells = _cells(text)
    assert cells[0][1].startswith("baseline")       # still first
    assert any(index == "04" and "modified" in label for index, label in cells)
    # the big value did not float to the top
    assert "999" not in "\n".join(_rows_for(text, "01"))


def test_the_order_matches_every_other_view(state: WorkbenchState):
    listing = dispatch(state, "candidates", [])
    text = dispatch(state, "state", [])
    for position in range(1, 10):
        assert listing.index(f"{position:02d}  ") >= 0
    assert [int(i) for i, _ in _cells(text)] == list(range(1, 10))


# -- identity ----------------------------------------------------------------------------------------


def test_the_view_shows_the_real_model_state_id(state: WorkbenchState):
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["80"])
    text = dispatch(state, "state", [])
    assert theme.ident(state.session.state.id, size=24) in text
    assert "display index only" in text


def test_no_identity_comes_from_nowhere(state: WorkbenchState):
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["80"])
    known = {theme.ident(s.id) for s in state.session.state_history}
    known |= {theme.ident(c.id) for c in state.list_candidates()}
    for args in ([], ["0"], ["1"]):
        text = dispatch(state, "state", args)
        for token in re.findall(r"·[0-9a-f]{12}", text):
            assert token in known, f"state view invented an identity: {token}"


# -- historical navigation ---------------------------------------------------------------------------


def test_a_historical_state_can_be_rendered(state: WorkbenchState):
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["80"])
    at_s0 = dispatch(state, "state", ["0"])
    at_s1 = dispatch(state, "state", ["1"])
    assert theme.ident(state.session.state_history[0].id, size=24) in at_s0
    assert "HISTORICAL" in at_s0 and "CURRENT" in at_s1
    assert at_s0.count("samples     0") == 9   # nothing had evidence at S0


def test_state_navigation_reuses_the_timeline_selector(state: WorkbenchState):
    for args in (["99"], ["-1"]):
        assert "EXPECTED" in dispatch(state, "state", args)
        assert "EXPECTED" in dispatch(state, "timeline", args)


def test_state_is_never_silently_filtered(state: WorkbenchState):
    """PHASE 93 sec.11 -- a candidate selector is REFUSED, not honoured.
    A partial view under a whole-state name would misrepresent the state."""
    text = dispatch(state, "state", ["baseline"])
    assert "STATE IS NOT FILTERABLE" in text
    assert "thread baseline" in text     # points at the view that IS filtered
    assert len(_cells(text)) == 0        # and enumerates nothing


# -- candidate isolation -----------------------------------------------------------------------------


def test_an_observation_changes_only_its_own_cell(state: WorkbenchState):
    """The §14 assertion: global state advances, candidate-local evidence
    stays isolated."""
    before = dispatch(state, "state", [])
    baseline_before = _rows_for(before, "01")

    dispatch(state, "select", ["modified", "25"])       # registry index 04
    dispatch(state, "observe", ["70"])
    after = dispatch(state, "state", [])

    # the observed cell changed
    assert _rows_for(before, "04") != _rows_for(after, "04")
    assert "70.0" in "\n".join(_rows_for(after, "04"))
    # every other cell did not
    assert _rows_for(after, "01") == baseline_before
    for index in ("02", "03", "05", "06", "07", "08", "09"):
        assert _rows_for(after, index) == _rows_for(before, index), index
        assert "samples     0" in "\n".join(_rows_for(after, index))


def test_two_observations_touch_two_distinct_cells(state: WorkbenchState):
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["80"])
    dispatch(state, "select", ["modified", "25"])
    dispatch(state, "observe", ["70"])

    text = dispatch(state, "state", [])
    assert "80.0" in "\n".join(_rows_for(text, "01"))
    assert "70.0" in "\n".join(_rows_for(text, "04"))
    assert "70.0" not in "\n".join(_rows_for(text, "01"))
    assert "80.0" not in "\n".join(_rows_for(text, "04"))
    # exactly two cells hold evidence
    assert text.count("samples     0") == 7
    assert "CELLS WITH EVIDENCE 2" in text


def test_the_global_state_advanced_while_cells_stayed_isolated(state: WorkbenchState):
    ids = [state.session.state.id]
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["80"])
    ids.append(state.session.state.id)
    dispatch(state, "select", ["modified", "25"])
    dispatch(state, "observe", ["70"])
    ids.append(state.session.state.id)

    assert len(set(ids)) == 3
    assert [s.id for s in state.session.state_history] == ids
    for index, identity in enumerate(ids):
        assert theme.ident(identity, size=24) in dispatch(state, "state", [str(index)])


# -- immutability ------------------------------------------------------------------------------------


def test_a_historical_state_renders_identically_after_the_session_advances(state: WorkbenchState):
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["80"])
    before = dispatch(state, "state", ["1"])

    dispatch(state, "select", ["modified", "25"])
    dispatch(state, "observe", ["70"])
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["100"])
    after = dispatch(state, "state", ["1"])

    def substantive(view: str) -> list:
        return [
            ln for ln in view.splitlines()[1:]
            if "POSITION" not in ln and set(ln.strip()) - set("─┘└├┌│┐ ")
        ]

    assert substantive(after) == substantive(before)


def test_rendering_state_mutates_nothing(state: WorkbenchState):
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "decide", [])
    dispatch(state, "explore", ["90"])
    dispatch(state, "observe", ["80"])

    session = state.session
    state_id = state.session.state.id
    history = [s.id for s in state.session.state_history]
    fingerprint = state.pool.fingerprint()
    observations = len(state.pool.all_observations())
    assessments = len(state.assessments)
    branches = list(state.branches)
    decisions = list(state.decision_log)
    selected = state.selected_candidate

    for args in ([], ["0"], ["1"], ["99"], ["baseline"]):
        dispatch(state, "state", args)

    assert state.session is session
    assert state.session.state.id == state_id
    assert [s.id for s in state.session.state_history] == history
    assert state.pool.fingerprint() == fingerprint
    assert len(state.pool.all_observations()) == observations
    assert len(state.assessments) == assessments
    assert state.branches == branches
    assert state.decision_log == decisions
    assert state.selected_candidate is selected


# -- no interpretation -------------------------------------------------------------------------------


def test_the_view_states_no_relation_between_two_cells(state: WorkbenchState):
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["80"])
    dispatch(state, "select", ["modified", "25"])
    dispatch(state, "observe", ["70"])

    text = dispatch(state, "state", [])
    lowered = text.lower()
    for phrase in ("best", "worst", "better", "worse", "higher", "lower", "difference",
                   "delta", "spread", "ranking", "rank ", "dominates", "superior",
                   "inferior", "winner", "loser", "versus", "compared to", "outperform"):
        assert phrase not in lowered, f"state view interprets: {phrase!r}"
    assert "Δ" not in text
    assert "states no relation" in text


def test_the_view_computes_no_aggregate(state: WorkbenchState):
    """The only counts are cardinalities of the registry and of occupied
    cells -- never a statistic over predicted VALUES."""
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["80"])
    dispatch(state, "select", ["modified", "25"])
    dispatch(state, "observe", ["70"])

    text = dispatch(state, "state", [])
    lowered = text.lower()
    for phrase in ("mean", "average", "total", "sum", "min ", "max ", "range", "median",
                   "aggregate", "overall", "combined"):
        assert phrase not in lowered, f"state view aggregates: {phrase!r}"
    # neither observed value's mean (75.0) nor their sum (150.0) appears
    assert "75.0" not in text and "150.0" not in text


def test_utility_is_absent_from_the_enumeration(state: WorkbenchState):
    """Phase 92 classified utility as a decision-policy quantity. It
    stays in `decide`/`explain`, where its basis is disclosed."""
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "decide", [])
    text = dispatch(state, "state", [])
    assert "UTILITY" not in text.upper()
    # and it is still disclosed where it belongs
    assert "UTILITY" in dispatch(state, "explain", []).upper()


def test_the_state_view_is_real_and_single_ruled(state: WorkbenchState):
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "explore", ["90"])
    text = dispatch(state, "state", [])
    assert "╔" not in text and "║" not in text
    assert "REAL" in text
    # a hypothetical branch is not a cell of a real state
    assert theme.ident(state.branches[0].projected_state_id) not in text


# -- state vs timeline vs thread ---------------------------------------------------------------------


def test_the_three_projections_stay_distinct(state: WorkbenchState):
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["80"])
    dispatch(state, "select", ["modified", "25"])
    dispatch(state, "observe", ["70"])

    state_view = dispatch(state, "state", [])
    timeline = dispatch(state, "timeline", [])
    thread = dispatch(state, "thread", ["baseline", "25"])
    assert state_view != timeline != thread

    # state enumerates candidates; timeline and thread enumerate states
    assert len(_cells(state_view)) == 9
    assert state_view.count("S0") == 0          # one state only
    assert timeline.count("S0  ·") == 1 and timeline.count("S2  ·") == 1
    assert thread.count("S0  ·") == 1


# -- determinism -------------------------------------------------------------------------------------


def test_the_same_session_twice_renders_identically():
    def run() -> tuple:
        st = _start()
        dispatch(st, "select", ["baseline", "25"])
        dispatch(st, "observe", ["80"])
        dispatch(st, "select", ["modified", "25"])
        dispatch(st, "observe", ["70"])
        return tuple(dispatch(st, "state", args) for args in ([], ["0"], ["1"], ["2"]))

    assert run() == run()


def test_repeated_rendering_is_semantically_identical(state: WorkbenchState):
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["80"])
    assert dispatch(state, "state", []) == dispatch(state, "state", [])
    assert dispatch(state, "state", ["1"]) == dispatch(state, "state", [])
