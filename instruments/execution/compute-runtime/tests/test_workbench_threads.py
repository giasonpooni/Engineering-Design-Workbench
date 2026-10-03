"""Phase 91: candidate evidence threads.

INVESTIGATION RESULT -- no CandidateHistory / EvidenceThread / second
provenance chain was built. A thread is a PROJECTION of the global
real-state trajectory, and the whole derivation rests on one fact that
already exists:

    the assessment that advanced the session out of a state carries its
    own `candidate_id`.

If it matches the thread's candidate, that transition is this
candidate's evidence. If it does not, the GLOBAL state advanced and this
candidate's evidence did not. Those are different statements, and the
view renders them differently rather than conflating them.

Everything else is read from objects that already exist:
`state_history` (the global chain), `prediction_at(candidate, state)`
(any candidate at any state), `PredictionAssessment` (observation,
signed residual), `decision_log` (retained OptimizationResults), and the
Phase 88 branch registry.

NO candidate-local state identity is invented. The ids in a thread are
the global `ModelState.id`s, which is why two threads over the same
session show the SAME ids and differ only in interpretation.
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
        return f"2026-08-24T19:{n['i']:02d}:00Z"

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


def _interleaved(state: WorkbenchState) -> WorkbenchState:
    """S0 -> baseline 80 -> S1 -> modified 70 -> S2 -> baseline 100 -> S3,
    with a decision at each state and one branch on baseline."""
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "decide", [])
    dispatch(state, "explore", ["70"])
    dispatch(state, "observe", ["80"])
    dispatch(state, "decide", [])
    dispatch(state, "select", ["modified", "25"])
    dispatch(state, "observe", ["70"])
    dispatch(state, "decide", [])
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["100"])
    return state


def _rows(section: str) -> list:
    """The substantive rows of a state block, free of frame characters and
    padding -- what the view SAYS, not how wide the terminal was."""
    out = []
    for line in section.splitlines():
        row = line.strip().strip("│").strip()
        if row and row not in ("│", "▼  REAL"):
            out.append(row)
    return out


def _candidate(state: WorkbenchState, formulation: str, temperature: int):
    return next(
        c for c in state.list_candidates()
        if c.formulation.natural_key == formulation
        and dict(c.target_context) == {"temperature_c": temperature}
    )


def _section(text: str, label: str) -> str:
    """The rows belonging to one state block of a rendered thread."""
    start = text.index(f"{label}  ·")
    following = [i for i in (text.find(f"S{n}  ·", start + 1) for n in range(10)) if i > start]
    return text[start:min(following)] if following else text[start:]


# -- no new abstraction ------------------------------------------------------------------------------


def test_a_thread_invents_no_candidate_local_state_identity(state: WorkbenchState):
    """Two threads over one session show the SAME global ids."""
    _interleaved(state)
    baseline = dispatch(state, "thread", ["baseline", "25"])
    modified = dispatch(state, "thread", ["modified", "25"])

    global_ids = [theme.ident(s.id) for s in state.session.state_history]
    assert len(global_ids) == 4
    for identity in global_ids:
        assert identity in baseline, identity
        assert identity in modified, identity

    known = set(global_ids)
    known |= {theme.ident(b.projected_state_id) for b in state.branches}
    known |= {theme.ident(c.id) for c in state.list_candidates()}
    for text in (baseline, modified):
        for token in re.findall(r"·[0-9a-f]{12}", text):
            assert token in known, f"thread invented an identity: {token}"


def test_a_thread_says_it_is_a_projection(state: WorkbenchState):
    _interleaved(state)
    text = dispatch(state, "thread", ["baseline", "25"])
    assert "A projection of the global real-state history." in text
    assert "The state identities below are the global ones." in text
    assert "A thread has no current" in text


# -- observation and residual attribution ------------------------------------------------------------


def test_every_global_state_is_represented_in_every_thread(state: WorkbenchState):
    """A thread is a projection of the chain, not a list of observations,
    so a state is never dropped for having no evidence for this candidate."""
    _interleaved(state)
    for selector in (["baseline", "25"], ["modified", "25"], ["high_filler", "25"]):
        text = dispatch(state, "thread", selector)
        for index in range(4):
            assert f"S{index}  ·" in text, f"{selector}: S{index} missing"


def test_an_unrelated_transition_is_marked_evidence_unchanged(state: WorkbenchState):
    _interleaved(state)
    baseline = dispatch(state, "thread", ["baseline", "25"])
    # S2 was reached by observing `modified`, so baseline's evidence did not move
    s2 = _section(baseline, "S2")
    # `tree` renders labels verbatim; the SEMANTICS are carried by the
    # uppercase values, which is what must not drift.
    assert "global state" in s2 and "ADVANCED" in s2
    assert "EVIDENCE UNCHANGED" in s2
    assert "modified · 25 C was observed" in s2
    # and no row on this state claims an observation or a residual
    for line in s2.splitlines():
        row = line.lstrip("│ ").lstrip("├└ ")
        assert not row.startswith(("observation", "residual")), row


def test_another_candidates_observation_never_appears_on_this_thread(state: WorkbenchState):
    _interleaved(state)
    baseline = dispatch(state, "thread", ["baseline", "25"])
    modified = dispatch(state, "thread", ["modified", "25"])

    # baseline admitted 80 and 100; modified admitted 70
    b_s1, b_s3 = _section(baseline, "S1"), _section(baseline, "S3")
    assert "80.0" in b_s1 and "100.0" in b_s3
    assert "70.0" not in _section(baseline, "S2")

    m_s2 = _section(modified, "S2")
    assert "70.0" in m_s2
    assert "80.0" not in _section(modified, "S1")
    assert "100.0" not in _section(modified, "S3")


def test_a_residual_attaches_only_to_the_candidate_that_earned_it(state: WorkbenchState):
    _interleaved(state)
    baseline_candidate = _candidate(state, "baseline", 25)
    modified_candidate = _candidate(state, "modified", 25)

    baseline_assessments = state.assessments_for(baseline_candidate)
    modified_assessments = state.assessments_for(modified_candidate)
    assert [a.observed_value for a in baseline_assessments] == [80.0, 100.0]
    assert [a.observed_value for a in modified_assessments] == [70.0]
    assert baseline_assessments[1].residual == 20.0  # predicted 80, observed 100
    assert modified_assessments[0].residual is None  # no prior prediction

    baseline = dispatch(state, "thread", ["baseline", "25"])
    modified = dispatch(state, "thread", ["modified", "25"])
    assert "+20.0" in baseline
    assert "+20.0" not in modified  # baseline's residual never leaks across


def test_samples_and_prediction_hold_steady_across_an_unrelated_transition(state: WorkbenchState):
    _interleaved(state)
    candidate = _candidate(state, "baseline", 25)
    history = state.session.state_history
    at_s1 = state.prediction_at(candidate, history[1])
    at_s2 = state.prediction_at(candidate, history[2])
    # the global chain moved from S1 to S2, but baseline gained nothing
    assert at_s1.sample_count == at_s2.sample_count == 1
    assert at_s1.predicted_value == at_s2.predicted_value == 80.0
    assert history[1].id != history[2].id


# -- decision attribution ----------------------------------------------------------------------------


def test_a_decision_is_shown_as_this_candidates_only_when_it_recommended_it(state: WorkbenchState):
    _interleaved(state)
    history = state.session.state_history
    decision = state.decision_at(history[0].id)
    assert decision is not None
    chosen = [o for o in decision.optimizations if o.status == "SELECTED"][0]
    recommended = next(c for c in state.list_candidates() if c.id == chosen.candidate_id)

    recommended_thread = dispatch(
        state, "thread", [recommended.formulation.natural_key,
                          str(dict(recommended.target_context)["temperature_c"])])
    assert "RECOMMENDED THIS CANDIDATE" in _section(recommended_thread, "S0")

    other = next(c for c in state.list_candidates() if c.id != recommended.id)
    other_thread = dispatch(
        state, "thread", [other.formulation.natural_key,
                          str(dict(other.target_context)["temperature_c"])])
    assert "OTHER CANDIDATE" in _section(other_thread, "S0")
    assert "RECOMMENDED THIS CANDIDATE" not in _section(other_thread, "S0")


def test_decisions_are_the_retained_objects_not_recomputations(state: WorkbenchState):
    _interleaved(state)
    log = list(state.decision_log)
    dispatch(state, "thread", ["baseline", "25"])
    dispatch(state, "thread", ["modified", "25"])
    assert state.decision_log == log
    assert all(a[1] is b[1] for a, b in zip(state.decision_log, log))


def test_a_recommendation_is_never_called_scientifically_superior(state: WorkbenchState):
    _interleaved(state)
    for selector in (["baseline", "25"], ["modified", "25"]):
        lowered = dispatch(state, "thread", selector).lower()
        for phrase in ("better", "worse", "superior", "proved", "confirms", "caused",
                       "validates", "probability", "confidence", "outperform"):
            assert phrase not in lowered, f"thread claims too much: {phrase!r}"


# -- branches ----------------------------------------------------------------------------------------


def test_branches_appear_as_side_projections_of_their_own_candidate_only(state: WorkbenchState):
    _interleaved(state)
    branch = state.branches[0]
    baseline = dispatch(state, "thread", ["baseline", "25"])
    modified = dispatch(state, "thread", ["modified", "25"])

    assert branch.candidate_id == _candidate(state, "baseline", 25).id
    row = next(ln for ln in baseline.splitlines() if theme.ident(branch.projected_state_id) in ln)
    assert "HYPOTHETICAL" in row
    assert "side projections · not in this chain" in baseline
    # and it never appears on a thread it does not belong to
    assert theme.ident(branch.projected_state_id) not in modified


def test_a_branch_stays_on_its_parent_state_after_the_session_advances(state: WorkbenchState):
    _interleaved(state)
    branch = state.branches[0]
    s0 = state.session.state_history[0].id
    assert branch.source_state_id == s0
    assert state.session.state.id != s0

    baseline = dispatch(state, "thread", ["baseline", "25"])
    assert theme.ident(branch.projected_state_id) in _section(baseline, "S0")
    for label in ("S1", "S2", "S3"):
        assert theme.ident(branch.projected_state_id) not in _section(baseline, label)


# -- navigation --------------------------------------------------------------------------------------


def test_thread_reuses_the_existing_semantic_selector(state: WorkbenchState):
    _interleaved(state)
    candidate = _candidate(state, "baseline", 25)
    index = next(i for i, c in enumerate(state.list_candidates(), start=1) if c.id == candidate.id)
    by_terms = dispatch(state, "thread", ["baseline", "25"])
    by_index = dispatch(state, "thread", [str(index)])
    by_pair = dispatch(state, "thread", ["formulation=baseline", "context=25"])
    assert by_terms == by_index == by_pair


def test_thread_with_no_argument_uses_the_current_selection(state: WorkbenchState):
    _interleaved(state)
    assert dispatch(state, "thread", []) == dispatch(state, "thread", ["baseline", "25"])
    dispatch(state, "select", ["clear"])
    assert "EXPECTED" in dispatch(state, "thread", [])


def test_inspect_thread_composes_with_the_existing_grammar(state: WorkbenchState):
    _interleaved(state)
    assert dispatch(state, "inspect", ["thread", "baseline", "25"]) == dispatch(
        state, "thread", ["baseline", "25"])
    # and the canonical candidate-inspection form is untouched
    assert "CANDIDATE INSPECTION" in dispatch(state, "inspect", ["baseline", "25"])


def test_an_ambiguous_or_unknown_selector_stays_that_way(state: WorkbenchState):
    _interleaved(state)
    assert "EXPECTED" in dispatch(state, "thread", ["nonexistent"])
    ambiguous = dispatch(state, "thread", ["baseline"])  # three contexts share it
    assert "EXPECTED" in ambiguous or "CANDIDATE THREAD" in ambiguous
    if "EXPECTED" in ambiguous:
        assert "25" in ambiguous  # the alternatives are named, not guessed between


# -- the current-state distinction -------------------------------------------------------------------


def test_the_current_marker_is_the_global_one(state: WorkbenchState):
    _interleaved(state)
    for selector in (["baseline", "25"], ["modified", "25"], ["high_filler", "120"]):
        text = dispatch(state, "thread", selector)
        assert text.count("▸ CURRENT") == 1
        row = next(ln for ln in text.splitlines() if "▸ CURRENT" in ln)
        assert theme.ident(state.session.state.id) in row


# -- isolation ---------------------------------------------------------------------------------------


def test_thread_rendering_mutates_nothing(state: WorkbenchState):
    _interleaved(state)
    session = state.session
    state_id = state.session.state.id
    history = [s.id for s in state.session.state_history]
    fingerprint = state.pool.fingerprint()
    observations = len(state.pool.all_observations())
    assessments = len(state.assessments)
    branches = list(state.branches)
    sources = [b.source_state_id for b in state.branches]
    decisions = list(state.decision_log)
    selected = state.selected_candidate

    for selector in ([], ["baseline", "25"], ["modified", "25"], ["high_filler", "80"],
                     ["nonexistent"], ["99"]):
        dispatch(state, "thread", selector)

    assert state.session is session
    assert state.session.state.id == state_id
    assert [s.id for s in state.session.state_history] == history
    assert state.pool.fingerprint() == fingerprint
    assert len(state.pool.all_observations()) == observations
    assert len(state.assessments) == assessments
    assert state.branches == branches
    assert [b.source_state_id for b in state.branches] == sources
    assert state.decision_log == decisions
    assert state.selected_candidate is selected


# -- historical immutability -------------------------------------------------------------------------


def test_a_rendered_thread_prefix_never_changes_as_the_session_advances(state: WorkbenchState):
    """The rows for S0..Sn are facts about frozen states. Advancing the
    session appends to a thread; it never rewrites it."""
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["80"])
    before = _section(dispatch(state, "thread", []), "S1")

    dispatch(state, "select", ["modified", "25"])
    dispatch(state, "observe", ["70"])
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["100"])

    after = _section(dispatch(state, "thread", []), "S1")
    # compare the substantive rows, free of frame padding: S1 loses only the
    # CURRENT marker it carried while it was the current state.
    def tree_rows(section: str) -> list:
        # tree rows only -- never the panel's own bottom rule, which also
        # begins with a box-drawing corner.
        return [
            r for r in _rows(section)
            if r.startswith(("├", "└")) and set(r) - set("─┘└├┌│ ")
        ]

    assert tree_rows(after) == tree_rows(before)
    assert "CURRENT" in before and "CURRENT" not in after.split("\n")[0]


# -- honesty -----------------------------------------------------------------------------------------


def test_thread_never_renders_an_unknown_as_zero(state: WorkbenchState):
    _interleaved(state)
    for selector in (["baseline", "25"], ["modified", "25"], ["high_filler", "80"]):
        text = dispatch(state, "thread", selector)
        for line in text.splitlines():
            for cell in line.split(theme.TRANSITION):
                if theme.UNDETERMINED in cell:
                    after = cell.split(theme.UNDETERMINED, 1)[1]
                    assert not any(ch.isdigit() for ch in after), f"{selector}: {line!r}"


def test_undetermined_is_never_a_section_heading(state: WorkbenchState):
    _interleaved(state)
    for selector in (["baseline", "25"], ["modified", "25"]):
        for line in dispatch(state, "thread", selector).splitlines():
            if line.lstrip("│║ ").startswith("─ "):
                assert theme.UNDETERMINED not in line


def test_evidence_unchanged_is_never_shown_as_an_observation(state: WorkbenchState):
    _interleaved(state)
    text = dispatch(state, "thread", ["baseline", "25"])
    s2 = _section(text, "S2")
    for line in s2.splitlines():
        if "EVIDENCE UNCHANGED" in line:
            assert "OBSERVATION" not in line
            assert "RESIDUAL" not in line


def test_a_thread_is_single_ruled_because_it_is_real(state: WorkbenchState):
    _interleaved(state)
    text = dispatch(state, "thread", ["baseline", "25"])
    assert "╔" not in text and "║" not in text
    # and every branch row inside it is marked on its own line
    for branch in state.branches:
        for line in text.splitlines():
            if theme.ident(branch.projected_state_id) in line:
                assert "HYPOTHETICAL" in line


# -- determinism -------------------------------------------------------------------------------------


def test_the_same_session_twice_produces_identical_threads():
    def run() -> tuple:
        state = _start()
        _interleaved(state)
        views = tuple(
            dispatch(state, "thread", selector)
            for selector in (["baseline", "25"], ["modified", "25"], ["high_filler", "80"])
        )
        identities = (
            tuple(s.id for s in state.session.state_history),
            tuple(b.projected_state_id for b in state.branches),
            tuple(b.source_state_id for b in state.branches),
            tuple(a.residual for a in state.assessments),
            tuple(a.candidate_id for a in state.assessments),
            tuple(sid for sid, _ in state.decision_log),
        )
        return identities, views

    assert run() == run()


# -- integration -------------------------------------------------------------------------------------


def test_full_interleaved_multi_candidate_session(state: WorkbenchState):
    dispatch(state, "select", ["baseline", "25"])
    baseline = state.selected_candidate
    s0 = state.session.state.id
    pool_0 = state.pool.fingerprint()

    dispatch(state, "decide", [])
    d0 = state.last_decision
    dispatch(state, "explore", ["70"])
    branch = state.branches[0]
    assert state.session.state.id == s0 and state.pool.fingerprint() == pool_0

    dispatch(state, "observe", ["80"])
    s1 = state.session.state.id
    dispatch(state, "decide", [])
    d1 = state.last_decision

    dispatch(state, "select", ["modified", "25"])
    modified = state.selected_candidate
    dispatch(state, "observe", ["70"])
    s2 = state.session.state.id
    dispatch(state, "decide", [])

    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["100"])
    s3 = state.session.state.id
    pool_3 = state.pool.fingerprint()

    # four distinct global states
    assert len({s0, s1, s2, s3}) == 4
    assert [s.id for s in state.session.state_history] == [s0, s1, s2, s3]

    baseline_view = dispatch(state, "thread", ["baseline", "25"])
    modified_view = dispatch(state, "thread", ["modified", "25"])
    timeline = dispatch(state, "timeline", [])
    inspections = [dispatch(state, "inspect", ["state", str(i)]) for i in range(4)]

    # both threads share the same global ids
    for identity in (theme.ident(i) for i in (s0, s1, s2, s3)):
        assert identity in baseline_view and identity in modified_view and identity in timeline

    # observations land on exactly one thread each
    assert [a.observed_value for a in state.assessments_for(baseline)] == [80.0, 100.0]
    assert [a.observed_value for a in state.assessments_for(modified)] == [70.0]
    assert "80.0" in _section(baseline_view, "S1")
    assert "70.0" in _section(modified_view, "S2")
    assert "EVIDENCE UNCHANGED" in _section(baseline_view, "S2")
    assert "EVIDENCE UNCHANGED" in _section(modified_view, "S1")
    assert "EVIDENCE UNCHANGED" in _section(modified_view, "S3")

    # residuals attach only where earned
    assert state.assessments_for(baseline)[1].residual == 20.0
    assert "+20.0" in _section(baseline_view, "S3")
    assert "+20.0" not in modified_view

    # decisions sit at the global states they were computed at
    assert state.decision_at(s0) is d0
    assert state.decision_at(s1) is d1
    assert state.decision_at(s3) is None

    # the current state is globally consistent across every view
    for view in [baseline_view, modified_view, timeline, *inspections[3:]]:
        assert theme.ident(s3) in view
    assert baseline_view.count("▸ CURRENT") == modified_view.count("▸ CURRENT") == 1

    # branches remain hypothetical, on their original parent, on their own thread
    assert branch.source_state_id == s0
    assert branch.candidate_id == baseline.id
    assert theme.ident(branch.projected_state_id) in _section(baseline_view, "S0")
    assert theme.ident(branch.projected_state_id) not in modified_view
    assert branch.projected_state_id not in {s0, s1, s2, s3}

    # historical states still reproduce themselves through the thread
    assert state.prediction_at(baseline, state.session.state_history[1]).predicted_value == 80.0
    assert state.prediction_at(baseline, state.session.state_history[2]).predicted_value == 80.0
    assert state.prediction_at(modified, state.session.state_history[1]).predicted_value is None

    # every command above was observational
    assert state.session.state.id == s3
    assert state.pool.fingerprint() == pool_3
    assert len(state.session.state_history) == 4
    assert len(state.branches) == 1
