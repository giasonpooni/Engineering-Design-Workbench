"""Phase 94: semantic and boundary audit.

The presentation consolidation touched a primitive every view renders
through. This module re-asserts, from the outside, that none of the
semantic boundaries Phases 84-93 established moved as a result --
because a formatting change that quietly altered what a view CLAIMS
would be far worse than the defect it fixed.
"""

import json
from pathlib import Path

import pytest

from materials.trajectory import compare_predictions
from workbench import theme
from workbench.cli import dispatch
from workbench.interaction import WorkbenchState, bootstrap_research_scenario

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "polymer_tensile_strength.json"

ALL_VIEWS = (
    ("scenario", []), ("status", []), ("candidates", []), ("predict", []),
    ("history", []), ("diagnostics", []), ("inspect", []), ("explain", []),
    ("branches", []), ("branch", ["1"]), ("compare", []), ("compare", ["branch", "1"]),
    ("timeline", []), ("timeline", ["0"]), ("thread", []), ("state", []), ("state", ["0"]),
)


def _clock():
    n = {"i": 0}

    def clock() -> str:
        n["i"] += 1
        return f"2026-08-25T01:{n['i']:02d}:00Z"

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
    st = _start()
    dispatch(st, "select", ["baseline", "25"])
    dispatch(st, "decide", [])
    dispatch(st, "explore", ["70"])
    dispatch(st, "observe", ["80"])
    dispatch(st, "decide", [])
    dispatch(st, "select", ["modified", "25"])
    dispatch(st, "observe", ["70"])
    dispatch(st, "select", ["baseline", "25"])
    dispatch(st, "observe", ["100"])
    return st


# -- the semantic boundaries (sec.7) -------------------------------------------------------------------


def test_semantic_selection_still_resolves_through_scenario_vocabulary(state: WorkbenchState):
    candidate = state.selected_candidate
    index = next(i for i, c in enumerate(state.list_candidates(), start=1) if c.id == candidate.id)
    assert dispatch(state, "inspect", ["baseline", "25"]) == dispatch(state, "inspect", [str(index)])
    assert "EXPECTED" in dispatch(state, "select", ["nonexistent"])


def test_inspect_remains_a_projection_over_existing_state(state: WorkbenchState):
    candidate = state.selected_candidate
    prediction = state.session.predict(candidate)
    text = dispatch(state, "inspect", [])
    assert theme.num(prediction.predicted_value) in text
    assert candidate.id[:12] in text
    assert state.session.state.id[:12] in text


def test_explain_neither_recomputes_nor_manufactures_causality(state: WorkbenchState):
    decision, previous = state.last_decision, state.previous_decision
    lowered = dispatch(state, "explain", []).lower()
    assert state.last_decision is decision and state.previous_decision is previous
    for phrase in ("proved", "caused", "is better", "superior", "confirms", "validates"):
        assert phrase not in lowered


def test_branches_remain_the_existing_counterfactual_objects(state: WorkbenchState):
    from materials.ensemble import CounterfactualOutcome
    assert all(type(b) is CounterfactualOutcome for b in state.branches)
    assert state.branches[0].source_state_id == state.session.state_history[0].id
    assert "NOT ADMITTED" in dispatch(state, "branches", [])


def test_compare_still_refuses_cross_candidate_comparison(state: WorkbenchState):
    baseline = state.selected_candidate
    modified = next(
        c for c in state.list_candidates()
        if c.formulation.natural_key == "modified"
        and dict(c.target_context) == {"temperature_c": 25}
    )
    current = state.session.state
    with pytest.raises(AssertionError, match="same ActionCandidate"):
        compare_predictions(state.prediction_at(baseline, current),
                            state.prediction_at(modified, current))


def test_timeline_thread_and_state_keep_their_distinct_projections(state: WorkbenchState):
    timeline = dispatch(state, "timeline", [])
    thread = dispatch(state, "thread", ["baseline", "25"])
    state_view = dispatch(state, "state", [])

    global_ids = [theme.ident(s.id) for s in state.session.state_history]
    assert len(global_ids) == 4
    for identity in global_ids:                       # timeline: the chain
        assert identity in timeline
    for identity in global_ids:                       # thread: same chain, one candidate
        assert identity in thread
    assert "EVIDENCE UNCHANGED" in thread
    # state: one state, every candidate
    assert theme.ident(state.session.state.id, size=24) in state_view
    assert state_view.count("├ prediction") == 9


def test_state_still_makes_no_cross_candidate_claim(state: WorkbenchState):
    lowered = dispatch(state, "state", []).lower()
    for phrase in ("best", "worst", "better", "worse", "higher", "lower", "ranking",
                   "superior", "difference", "delta", "spread", "mean", "average"):
        assert phrase not in lowered, f"state view interprets: {phrase!r}"


# -- honesty invariants across every view (sec.5) -----------------------------------------------------


def test_every_view_preserves_real_versus_hypothetical_framing(state: WorkbenchState):
    for command, args in ALL_VIEWS:
        text = dispatch(state, command, args)
        plain = [theme._ANSI.sub("", ln) for ln in text.splitlines()]
        uses_double = any(ln.startswith(("╔", "╚", "║")) for ln in plain)
        top = plain[0] if plain else ""
        declares = "HYPOTHETICAL" in top or "NOT EVIDENCE" in top
        assert uses_double == declares, f"{command} {args}: framing drifted"


def test_no_view_renders_an_unknown_as_zero(state: WorkbenchState):
    for command, args in ALL_VIEWS:
        text = dispatch(state, command, args)
        for line in text.splitlines():
            for cell in line.split(theme.TRANSITION):
                if theme.UNDETERMINED in cell:
                    after = cell.split(theme.UNDETERMINED, 1)[1]
                    assert not any(ch.isdigit() for ch in after), f"{command}: {line!r}"


def test_no_view_is_mutated_by_rendering(state: WorkbenchState):
    session = state.session
    fingerprint = state.pool.fingerprint()
    history = [s.id for s in state.session.state_history]
    branches = list(state.branches)
    decisions = list(state.decision_log)
    assessments = len(state.assessments)
    selected = state.selected_candidate

    for command, args in ALL_VIEWS:
        dispatch(state, command, args)

    assert state.session is session
    assert state.pool.fingerprint() == fingerprint
    assert [s.id for s in state.session.state_history] == history
    assert state.branches == branches
    assert state.decision_log == decisions
    assert len(state.assessments) == assessments
    assert state.selected_candidate is selected


def test_every_identity_traces_to_an_existing_object(state: WorkbenchState):
    import re
    known = {theme.ident(s.id) for s in state.session.state_history}
    known |= {theme.ident(b.projected_state_id) for b in state.branches}
    known |= {theme.ident(b.model_state_key) for b in state.branches}
    known |= {theme.ident(c.id) for c in state.list_candidates()}
    # admitted evidence carries its own content-addressed identities, which
    # `status` and the transition views legitimately show.
    known |= {theme.ident(a.observation.id) for a in state.assessments}
    known |= {theme.ident(a.result.id) for a in state.assessments}
    known |= {theme.ident(state.pool.fingerprint()), theme.ident(state.document_id)}
    for command, args in ALL_VIEWS:
        text = dispatch(state, command, args)
        for token in re.findall(r"·[0-9a-f]{12}", text):
            assert token in known, f"{command}: identity from nowhere: {token}"


# -- scientific-value integrity (sec.6) ---------------------------------------------------------------


def test_a_scientific_value_is_never_merged_into_a_separator(state: WorkbenchState):
    """The Phase 94 defect, asserted through the real views: a value is
    always separated from whatever structural glyph follows it."""
    for command, args in ALL_VIEWS:
        text = dispatch(state, command, args)
        for line in text.splitlines():
            plain = theme._ANSI.sub("", line)
            if theme.TRANSITION in plain:
                before = plain.split(theme.TRANSITION)[0]
                assert before.endswith(" "), f"{command}: value fused to glyph: {plain!r}"


def test_a_long_unit_does_not_corrupt_the_transition_row():
    """The exact reproduction: the unit is caller-supplied, so a long one
    is reachable by ordinary use."""
    state = _start()
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["80", "kilonewtons_per_square_metre"])
    dispatch(state, "observe", ["100", "kilonewtons_per_square_metre"])

    text = dispatch(state, "compare", [])
    rows = [theme._ANSI.sub("", ln) for ln in text.splitlines() if theme.TRANSITION in ln]
    assert rows
    for row in rows:
        before = row.split(theme.TRANSITION)[0]
        assert before.endswith(" ")
        assert "metre" + theme.TRANSITION not in row


# -- boundary audit (sec.8) ---------------------------------------------------------------------------


def test_the_workbench_layer_boundary_is_unchanged():
    """The cleanup must not have bought convenience with a new lower-layer
    dependency, in either direction. Also re-asserts the standing rule
    that workbench/ takes no third-party dependency at all."""
    import ast
    import sys

    repo = Path(__file__).resolve().parent.parent
    allowed_roots = {"materials", "experiment", "evidence", "retrieval", "workbench"}
    for path in (repo / "workbench").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".")[0]
                if root in sys.stdlib_module_names or root == "__future__":
                    continue  # stdlib only -- no third-party dependency may appear
                assert root in allowed_roots, f"{path.name} imports {node.module}"

    # and nothing below workbench imports it
    for package in ("materials", "experiment", "core", "evidence", "retrieval"):
        for path in (repo / package).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                modules = []
                if isinstance(node, ast.ImportFrom) and node.module:
                    modules = [node.module]
                elif isinstance(node, ast.Import):
                    modules = [a.name for a in node.names]
                for module in modules:
                    assert not module.startswith("workbench"), f"{path} imports {module}"


def test_the_cli_reaches_materials_only_for_types_and_named_primitives():
    """`workbench.cli` may name materials TYPES for annotation and compose
    named primitives, but the interaction layer stays the place that
    calls scientific functions."""
    import ast

    source = (Path(__file__).resolve().parent.parent / "workbench" / "cli.py").read_text(
        encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("materials"):
            imported.update(a.name for a in node.names)
    # every materials name the CLI imports is a TYPE it renders, not a
    # computation it performs -- except the two diagnostics helpers Phase 86
    # composes, which the interaction layer also exposes.
    assert imported <= {
        "PredictionAssessment", "ActionCandidate", "StateTransitionDiagnostic",
        "CounterfactualOutcome", "ModelState", "Prediction", "OptimizationResult",
        "PredictionDelta", "diagnose_transitions",
        # PHASE 96: two more rendered TYPES. The criterion is CONSTRUCTED in
        # the interaction layer and EVALUATED there; the CLI only renders the
        # resulting objects, which is why make_criterion/evaluate_program/
        # reevaluate_program are asserted absent below.
        "Criterion", "ProgramDecision",
    }, imported
    assert "rank_candidates" not in imported
    assert "compare_predictions" not in imported
    for computation in ("make_criterion", "evaluate_program", "reevaluate_program",
                        "analyze_program", "predict", "update"):
        assert computation not in imported, f"cli performs {computation!r} itself"
