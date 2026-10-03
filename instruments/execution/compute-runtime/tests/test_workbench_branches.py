"""Phase 88: the counterfactual branch registry.

INVESTIGATION RESULT -- no new branch representation was built, because
`materials.ensemble.CounterfactualOutcome` already IS one. It is a
frozen dataclass carrying, for one projection:

    source_state_id     the real parent state's content hash
    candidate_id        the candidate's content hash
    model_state_key     the cell the hypothesis lands in
    hypothetical_value  y
    projected_state     a frozen, content-addressed ModelState
    projected_state_id  its content hash -- the branch's own identity
    prediction_after    read from the projected state
    delta               against the prediction at the parent

That is every field Phase 88 sec.2 lists as permitted. The registry is
therefore a plain ordered `List[CounterfactualOutcome]` on
`WorkbenchState` -- retention, not representation. Defining a parallel
`Branch` object would have duplicated an existing materials object and
introduced a second provenance system, both of which the phase forbids.

The six investigation questions, answered against the code:

1. The authoritative projected state is `materials.model_state.ModelState`;
   the authoritative BRANCH is `CounterfactualOutcome`.
2. Identity is `projected_state.id` -- a content hash that necessarily
   differs from its parent's, because the projected state contains a
   sample the parent does not.
3. Hypothetical provenance is established by
   `materials.model_state.HYPOTHETICAL_SAMPLE_PREFIX` on the projected
   sample's `observation_id`, minted by `_hypothetical_sample_id` as a
   content hash of `(model_state_key, hypothetical_value)`.
4. Yes -- `project_update` never mutates, so branches coexist freely.
5. Yes -- every object involved is frozen, so retention by reference
   cannot diverge from what was projected.
6. The minimum workbench representation is the outcome itself. Nothing
   was added to it.
"""

import json
from pathlib import Path

import pytest

from materials.ensemble import CounterfactualOutcome
from materials.model_state import HYPOTHETICAL_SAMPLE_PREFIX, update
from workbench import theme
from workbench.cli import dispatch
from workbench.interaction import WorkbenchState, bootstrap_research_scenario

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "polymer_tensile_strength.json"


def _clock():
    n = {"i": 0}

    def clock() -> str:
        n["i"] += 1
        return f"2026-08-24T13:{n['i']:02d}:00Z"

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


# -- no new domain model -----------------------------------------------------------------------------


def test_the_registry_holds_the_existing_materials_object(state: WorkbenchState):
    """If this ever stops being a CounterfactualOutcome, a parallel branch
    model has been introduced and Phase 88 sec.2 has been violated."""
    dispatch(state, "select", ["1"])
    dispatch(state, "explore", ["90"])
    assert len(state.branches) == 1
    assert type(state.branches[0]) is CounterfactualOutcome


def test_the_registry_retains_by_reference_never_by_copy(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    dispatch(state, "explore", ["90"])
    assert state.branches[0] is state.last_counterfactual


def test_branch_identity_is_the_existing_content_hash(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    dispatch(state, "explore", ["90"])
    branch = state.branches[0]
    assert branch.projected_state_id == branch.projected_state.id
    assert branch.projected_state_id != branch.source_state_id
    assert len(branch.projected_state_id) == 64  # a bare SHA-256 hex digest, not a UUID
    assert "-" not in branch.projected_state_id


def test_hypothetical_provenance_marker_is_the_existing_one(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    dispatch(state, "explore", ["90"])
    samples = state.branches[0].projected_state.samples
    hypothetical = [
        s for cell in samples.values() for s in cell
        if s.observation_id.startswith(HYPOTHETICAL_SAMPLE_PREFIX)
    ]
    assert len(hypothetical) == 1


# -- multiple coexisting branches --------------------------------------------------------------------


def test_three_branches_coexist_independently(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    for value in ("70", "90", "110"):
        dispatch(state, "explore", [value])

    assert len(state.branches) == 3
    a, b, c = state.branches
    assert a.hypothetical_value == 70.0
    assert b.hypothetical_value == 90.0
    assert c.hypothetical_value == 110.0
    # branch A != branch B != branch C, by identity
    assert len({a.projected_state_id, b.projected_state_id, c.projected_state_id}) == 3
    # all three branched from the SAME real parent
    assert a.source_state_id == b.source_state_id == c.source_state_id == state.session.state.id


def test_each_branch_retains_its_own_hypothetical_outcome(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    for value in ("70", "90", "110"):
        dispatch(state, "explore", [value])

    for position, expected in ((1, "70.0"), (2, "90.0"), (3, "110.0")):
        text = dispatch(state, "branch", [str(position)])
        assert f"y = {expected}" in text
        for other in ("70.0", "90.0", "110.0"):
            if other != expected:
                assert f"y = {other}" not in text


def test_exploring_the_same_value_twice_registers_one_branch(state: WorkbenchState):
    """Content-addressed identity means the second projection IS the first
    branch, not a second one."""
    dispatch(state, "select", ["1"])
    dispatch(state, "explore", ["90"])
    dispatch(state, "explore", ["90"])
    assert len(state.branches) == 1


def test_the_same_value_on_a_different_candidate_is_a_different_branch(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    dispatch(state, "explore", ["90"])
    dispatch(state, "select", ["2"])
    dispatch(state, "explore", ["90"])
    assert len(state.branches) == 2
    assert state.branches[0].candidate_id != state.branches[1].candidate_id
    assert state.branches[0].projected_state_id != state.branches[1].projected_state_id


# -- isolation ---------------------------------------------------------------------------------------


def test_projection_changes_nothing_real(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    candidate = state.selected_candidate
    state_id = state.session.state.id
    fingerprint = state.pool.fingerprint()
    observations = len(state.pool.all_observations())
    history_length = len(state.session.state_history)
    prediction = state.session.predict(candidate)
    samples = prediction.sample_count

    for value in ("70", "90", "110"):
        dispatch(state, "explore", [value])
    dispatch(state, "branches", [])
    for position in ("1", "2", "3"):
        dispatch(state, "branch", [position])

    assert state.session.state.id == state_id
    assert state.pool.fingerprint() == fingerprint
    assert len(state.pool.all_observations()) == observations
    assert len(state.session.state_history) == history_length
    after = state.session.predict(candidate)
    assert after.sample_count == samples
    assert after.predicted_value == prediction.predicted_value
    assert after.uncertainty == prediction.uncertainty


def test_no_projected_state_enters_real_history(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    for value in ("70", "90", "110"):
        dispatch(state, "explore", [value])
    dispatch(state, "observe", ["100"])

    real_ids = {s.id for s in state.session.state_history}
    for branch in state.branches:
        assert branch.projected_state_id not in real_ids


def test_observe_after_exploration_advances_only_the_real_session(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    for value in ("70", "90", "110"):
        dispatch(state, "explore", [value])
    before = state.session.state.id
    fingerprint_before = state.pool.fingerprint()

    dispatch(state, "observe", ["100"])

    assert state.session.state.id != before
    assert state.pool.fingerprint() != fingerprint_before
    assert state.session.predict(state.selected_candidate).predicted_value == 100.0
    # the hypotheses contributed nothing to the real prediction
    assert state.session.predict(state.selected_candidate).sample_count == 1


def test_an_earlier_session_remains_immutable_through_all_of_it(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    dispatch(state, "observe", ["80"])
    held = state.session
    held_id = held.state.id
    held_prediction = held.predict(state.selected_candidate).predicted_value

    for value in ("70", "90", "110"):
        dispatch(state, "explore", [value])
    dispatch(state, "branches", [])
    dispatch(state, "branch", ["2"])
    dispatch(state, "observe", ["100"])

    assert held.state.id == held_id
    assert held.predict(state.selected_candidate).predicted_value == held_prediction


def test_the_phase_61_guard_still_rejects_a_retained_branch(state: WorkbenchState):
    """Retaining a branch must not create a new route into real update()."""
    dispatch(state, "select", ["1"])
    candidate = state.selected_candidate
    dispatch(state, "explore", ["90"])
    dispatch(state, "observe", ["80"])
    assessment = state.assessments[-1]

    with pytest.raises(AssertionError, match="hypothetical"):
        update(state.branches[0].projected_state, candidate, assessment.result, assessment.observation)


# -- lifecycle: branches survive, parents are never rewritten -----------------------------------------


def test_branches_survive_a_real_observation(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    dispatch(state, "explore", ["90"])
    branch = state.branches[0]
    dispatch(state, "observe", ["100"])

    assert len(state.branches) == 1
    assert state.branches[0] is branch


def test_a_branch_is_never_reparented_onto_the_new_state(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    s0 = state.session.state.id
    dispatch(state, "explore", ["90"])
    dispatch(state, "observe", ["100"])
    s1 = state.session.state.id

    assert s1 != s0
    assert state.branches[0].source_state_id == s0
    assert state.branches[0].source_state_id != s1


def test_the_view_says_the_parent_is_superseded_rather_than_rewriting_it(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    s0 = state.session.state.id
    dispatch(state, "explore", ["90"])
    assert "current real state" in dispatch(state, "branches", [])

    dispatch(state, "observe", ["100"])
    for text in (dispatch(state, "branches", []), dispatch(state, "branch", ["1"])):
        assert "superseded" in text
        assert theme.ident(s0) in text  # still the OLD parent
        assert "current real state" not in text


# -- interaction surface -----------------------------------------------------------------------------


def test_branches_with_an_empty_registry_says_so(state: WorkbenchState):
    text = dispatch(state, "branches", [])
    assert "NO COUNTERFACTUAL BRANCHES" in text
    assert "UNDETERMINED" not in text  # an empty registry is not an unknown quantity


def test_branch_rejections_name_the_expected_form(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    dispatch(state, "explore", ["90"])
    for args in (["99"], ["x"], []):
        assert "EXPECTED" in dispatch(state, "branch", args)


def test_branch_corresponds_by_candidate_id_not_registry_position(state: WorkbenchState):
    dispatch(state, "select", ["baseline", "25"])
    first = state.selected_candidate
    dispatch(state, "explore", ["90"])
    dispatch(state, "select", ["baseline", "120"])
    second = state.selected_candidate
    dispatch(state, "explore", ["90"])

    assert theme.ident(first.id) in dispatch(state, "branch", ["1"])
    assert theme.ident(second.id) in dispatch(state, "branch", ["2"])
    assert theme.ident(second.id) not in dispatch(state, "branch", ["1"])


def test_no_branch_command_can_apply_or_adopt_a_branch(state: WorkbenchState):
    """PHASE 88 sec.8 -- a branch is an analysis, not an alternative
    reality. Inspection is the only permitted interaction."""
    dispatch(state, "select", ["1"])
    dispatch(state, "explore", ["90"])
    state_id = state.session.state.id
    fingerprint = state.pool.fingerprint()

    for command in ("commit", "apply", "merge", "choose", "adopt"):
        text = dispatch(state, command, ["1"])
        assert "UNKNOWN COMMAND" in text

    assert state.session.state.id == state_id
    assert state.pool.fingerprint() == fingerprint


# -- honesty -----------------------------------------------------------------------------------------


def test_branch_views_never_claim_validation_or_superiority(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    for value in ("70", "90", "110"):
        dispatch(state, "explore", [value])

    texts = [dispatch(state, "branches", [])]
    texts += [dispatch(state, "branch", [n]) for n in ("1", "2", "3")]
    for text in texts:
        lowered = text.lower()
        for phrase in (
            "better", "worse", "superior", "optimal branch", "proves", "proved",
            "validates the prediction", "confirms", "observed value", "measured",
            "admitted as evidence.", "actual result",
        ):
            assert phrase not in lowered, f"branch view claims too much: {phrase!r}"
        assert "validates nothing" in lowered or "NOT ADMITTED" in text


def test_branch_views_never_render_an_unknown_as_zero(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    dispatch(state, "explore", ["90"])
    for text in (dispatch(state, "branches", []), dispatch(state, "branch", ["1"])):
        for line in text.splitlines():
            for cell in line.split(theme.TRANSITION):
                if theme.UNDETERMINED in cell:
                    after = cell.split(theme.UNDETERMINED, 1)[1]
                    assert not any(ch.isdigit() for ch in after), line


def test_not_admitted_language_never_appears_on_a_real_observation(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    dispatch(state, "explore", ["90"])
    observation_view = dispatch(state, "observe", ["100"])
    assert "NOT ADMITTED" not in observation_view
    assert "HYPOTHETICAL" not in observation_view


# -- determinism -------------------------------------------------------------------------------------


def test_the_same_sequence_twice_produces_the_same_branches():
    def run() -> tuple:
        state = _start()
        dispatch(state, "select", ["baseline", "80"])
        for value in ("70", "90", "110"):
            dispatch(state, "explore", [value])
        views = tuple(dispatch(state, "branch", [n]) for n in ("1", "2", "3"))
        identities = tuple(
            (b.source_state_id, b.candidate_id, b.hypothetical_value, b.projected_state_id)
            for b in state.branches
        )
        return identities, views, dispatch(state, "branches", [])

    first = run()
    second = run()
    assert first[0] == second[0]  # identity is content-derived, not clock- or counter-derived
    assert first[1] == second[1]
    assert first[2] == second[2]


# -- integration -------------------------------------------------------------------------------------


def test_three_branches_from_one_state_then_one_real_advance(state: WorkbenchState):
    """S0 -> B1/B2/B3 (all from S0, none in real history), S0 unchanged
    throughout, then S0 -> S1 by a single real observation."""
    dispatch(state, "select", ["baseline", "80"])
    candidate = state.selected_candidate
    s0 = state.session.state.id
    pool_before = state.pool.fingerprint()
    history_before = len(state.session.state_history)

    dispatch(state, "explore", ["70"])
    dispatch(state, "explore", ["90"])
    dispatch(state, "explore", ["110"])
    b1, b2, b3 = state.branches

    # every branch hangs off S0
    assert b1.source_state_id == b2.source_state_id == b3.source_state_id == s0
    # and every branch is distinct from every other
    assert len({b1.projected_state_id, b2.projected_state_id, b3.projected_state_id}) == 3
    # S0 itself did not move, and the pool was untouched by all three
    assert state.session.state.id == s0
    assert state.pool.fingerprint() == pool_before
    assert len(state.session.state_history) == history_before
    assert state.session.predict(candidate).sample_count == 0

    # the pool changes ONLY at the real observation
    dispatch(state, "observe", ["100"])
    s1 = state.session.state.id
    assert s1 != s0
    assert state.pool.fingerprint() != pool_before
    assert len(state.session.state_history) == history_before + 1
    assert state.session.predict(candidate).sample_count == 1
    assert state.session.predict(candidate).predicted_value == 100.0

    # none of the three projected states is anywhere in real history
    real_ids = {s.id for s in state.session.state_history}
    assert not real_ids & {b1.projected_state_id, b2.projected_state_id, b3.projected_state_id}

    # and all three remain inspectable, still parented to S0
    assert len(state.branches) == 3
    for position, branch in enumerate([b1, b2, b3], start=1):
        text = dispatch(state, "branch", [str(position)])
        assert theme.ident(s0) in text
        assert theme.ident(branch.projected_state_id) in text
        assert "superseded" in text
        assert "NOT ADMITTED AS EVIDENCE" in text
