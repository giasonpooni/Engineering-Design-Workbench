"""Phase 73 (interface): locks the workbench's visual system, so the
UI cannot silently regress.

These tests assert PRESENTATION invariants only -- frame integrity,
epistemic honesty of rendered values, colour degradation, and the
consistency rules `workbench/cli.py`'s presentation contract states.
Scientific behaviour is covered by the other workbench test files;
nothing here touches state, evidence, or the algebra.
"""

import json
from pathlib import Path

import pytest

from materials.model_state import HYPOTHETICAL_SAMPLE_PREFIX
from workbench import theme
from workbench.cli import (
    COMMAND_GROUPS, dispatch, format_masthead, format_prompt, format_scenario_banner,
)
from workbench.interaction import WorkbenchState, bootstrap_research_scenario

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_SCENARIO_PATH = REPO_ROOT / "examples" / "polymer_tensile_strength.json"

FRAME_STARTS = "┌│└╔║╚"

# every view, in the order a session actually exercises them, including
# each error state -- so a regression in any one of them fails here.
VIEW_SCRIPT = (
    ("help", []), ("scenario", []), ("status", []), ("candidates", []),
    ("inspect", []), ("explain", []),  # before anything: no selection, no decision
    ("decide", []),
    ("select", ["1"]), ("predict", []), ("inspect", []), ("explain", []),
    ("branches", []), ("branch", ["1"]),  # before anything: empty registry
    ("explore", ["70"]), ("explore", ["90"]), ("explore", ["110"]),
    ("branches", []), ("branch", ["1"]), ("branch", ["2"]), ("branch", ["3"]),
    ("compare", []), ("compare", ["branch", "1"]),                  # no history yet
    ("compare", ["branch", "1", "branch", "2"]), ("compare", ["decisions"]),
    ("observe", ["80"]), ("observe", ["100"]),
    ("compare", []), ("compare", ["branch", "1"]),                  # real -> hypothetical
    ("compare", ["state", "1", "state", "3"]),                      # non-adjacent real pair
    ("decide", []), ("compare", ["decisions"]),
    ("timeline", []), ("timeline", ["0"]), ("timeline", ["1"]), ("timeline", ["2"]),
    ("inspect", ["state", "0"]), ("inspect", ["state", "1"]),
    ("thread", []), ("thread", ["baseline", "25"]), ("thread", ["modified"]),
    ("state", []), ("state", ["0"]), ("state", ["1"]),
    ("criterion", []), ("criterion", ["baseline", "25"]), ("criterion", ["1"]),
    ("inspect", ["thread", "baseline", "25"]),
    ("branches", []), ("branch", ["1"]),  # branches survive a real observation
    ("history", []), ("diagnostics", []), ("status", []), ("inspect", []),
    ("candidates", []), ("decide", []), ("explain", []),
    ("select", ["99"]), ("select", ["x"]), ("select", []),
    ("observe", ["abc"]), ("observe", []), ("explore", ["abc"]), ("explore", []),
    ("inspect", ["99"]),
    ("branch", ["99"]), ("branch", ["x"]), ("branch", []),
    ("compare", ["state", "99"]), ("compare", ["branch", "x"]),
    ("compare", ["state"]), ("compare", ["nonsense"]),
    ("timeline", ["99"]), ("timeline", ["x"]), ("inspect", ["state"]),
    ("thread", ["nonexistent"]), ("thread", ["99"]),
    ("state", ["99"]), ("state", ["baseline"]),
    ("criterion", ["nonexistent"]),
    ("bogus", []),
)


def _fixed_clock():
    counter = {"n": 0}

    def clock() -> str:
        n = counter["n"]
        counter["n"] += 1
        return f"2026-08-24T07:{n:02d}:00Z"

    return clock


@pytest.fixture()
def state() -> WorkbenchState:
    with open(EXAMPLE_SCENARIO_PATH, encoding="utf-8") as f:
        config = json.load(f)
    return bootstrap_research_scenario(config, clock=_fixed_clock())


@pytest.fixture(autouse=True)
def _plain_by_default():
    theme.set_color(False)
    yield
    theme.set_color(None)


def _rendered_views(state: WorkbenchState):
    yield "banner", format_scenario_banner(state)
    for command, args in VIEW_SCRIPT:
        yield command, dispatch(state, command, args)


# -- frame integrity ---------------------------------------------------------------------------------


@pytest.mark.parametrize("colored", [False, True])
def test_every_framed_line_is_exactly_frame_width(state: WorkbenchState, colored: bool):
    """The single most visible failure mode of a terminal UI is a ragged
    frame. Every bordered line in every view must measure exactly
    `theme.width()` -- identically with and without colour, since
    padding is computed on visible length."""
    theme.set_color(colored)
    for name, text in _rendered_views(state):
        for line in text.splitlines():
            plain = theme._ANSI.sub("", line)
            if plain.startswith(tuple(FRAME_STARTS)):
                assert theme.visible_len(line) == theme.width(), f"{name}: ragged frame line {plain!r}"


def test_every_view_is_a_closed_frame(state: WorkbenchState):
    """Each view opens and closes its frame exactly once, and the two
    match style: a double rule opens only where a double rule closes."""
    for name, text in _rendered_views(state):
        plain = [theme._ANSI.sub("", line) for line in text.splitlines()]
        opens = [line for line in plain if line.startswith(("┌", "╔"))]
        closes = [line for line in plain if line.startswith(("└", "╚"))]
        assert len(opens) == 1, f"{name}: expected one opening rule"
        assert len(closes) == 1, f"{name}: expected one closing rule"
        assert (opens[0][0] == "╔") == (closes[0][0] == "╚"), f"{name}: mismatched frame style"


def test_long_content_is_clipped_rather_than_breaking_the_frame():
    """`panel` clips before padding, so no body line -- however long --
    can overflow. Verified directly, since a regression here would only
    show up in an unusual scenario."""
    text = theme.panel("test", ["x" * 500, "short"])
    for line in text.splitlines():
        assert theme.visible_len(line) == theme.width()
    assert "…" in text


# -- epistemic honesty in the rendering layer ---------------------------------------------------------


def test_none_always_renders_as_the_word_undetermined():
    assert theme.num(None) == "UNDETERMINED"
    assert theme.num(None, signed=True) == "UNDETERMINED"
    assert theme.quantity(None, "MPa") == "UNDETERMINED"  # no unit on a non-measurement
    assert "0" not in theme.num(None)


def test_zero_is_rendered_distinctly_from_undetermined():
    """A real zero is a determined value and must never be confusable
    with the absence of one."""
    assert theme.num(0.0) == "0.0"
    assert theme.num(0.0) != theme.num(None)


def test_signed_rendering_never_drops_direction():
    assert theme.num(20.0, signed=True) == "+20.0"
    assert theme.num(-20.0, signed=True) == "-20.0"
    assert theme.num(0.0, signed=True) == "0.0"
    # unsigned rendering still keeps a negative sign -- only `+` is optional
    assert theme.num(-20.0) == "-20.0"


def test_float_noise_is_rendered_readably_without_losing_the_value():
    assert theme.num(-0.09999999999999998) == "-0.1"
    assert theme.num(86.66666666666667) == "86.6667"
    assert theme.num(100.0) == "100.0"


def test_no_view_renders_an_undetermined_quantity_as_zero(state: WorkbenchState):
    """Across a full session, every row carrying UNDETERMINED carries no
    numeral -- the two are never mixed on one line."""
    for name, text in _rendered_views(state):
        for line in text.splitlines():
            # a `before → after` pair is two independent cells; UNDETERMINED on one
            # side says nothing about a numeral on the other.
            for cell in line.split(theme.TRANSITION):
                if theme.UNDETERMINED in cell:
                    after = cell.split(theme.UNDETERMINED, 1)[1]
                    assert not any(ch.isdigit() for ch in after), (
                        f"{name}: numeral beside UNDETERMINED in one cell: {line!r}"
                    )


# -- consistency rules from the presentation contract -------------------------------------------------


def test_the_double_frame_means_hypothetical_and_nothing_else(state: WorkbenchState):
    """A double rule means hypothetical -- BOTH ways. No view whose SUBJECT
    is a projection may be single-ruled (it could be read as admitted
    evidence), and no view whose subject is real may be double-ruled (it
    could be dismissed as a projection).

    PHASE 88 generalised this from an allowlist of one view name to the
    property the allowlist stood for. PHASE 90 sharpened WHERE the
    property is read from: scanning the whole body for the word
    "HYPOTHETICAL" conflated "this view IS a projection" with "this view
    MENTIONS one" -- and the timeline is a real view that legitimately
    names its side projections. The subject is what the panel's own top
    rule declares, so that is what the frame must agree with."""
    for name, text in _rendered_views(state):
        plain = [theme._ANSI.sub("", line) for line in text.splitlines()]
        uses_double = any(line.startswith(("╔", "╚", "║")) for line in plain)
        top_rule = plain[0] if plain else ""
        declares_hypothetical = "HYPOTHETICAL" in top_rule or "NOT EVIDENCE" in top_rule
        assert uses_double == declares_hypothetical, (
            f"{name}: frame style disagrees with the top rule -- "
            f"double={uses_double}, declared hypothetical={declares_hypothetical}"
        )


def test_a_real_view_never_names_a_projection_without_marking_it(state: WorkbenchState):
    """The coverage the body-wide scan used to give, made exact: inside a
    single-ruled (real) view, any row carrying a branch's projected-state
    identity must say on that row that it is not admitted evidence."""
    dispatch(state, "select", ["1"])
    dispatch(state, "explore", ["70"])
    dispatch(state, "explore", ["110"])
    dispatch(state, "observe", ["90"])
    branch_ids = [theme.ident(b.projected_state_id) for b in state.branches]
    assert branch_ids

    for command, args in (("timeline", []), ("timeline", ["0"]), ("inspect", ["state", "0"]),
                          ("status", []), ("history", [])):
        text = dispatch(state, command, args)
        plain = [theme._ANSI.sub("", line) for line in text.splitlines()]
        if any(line.startswith(("╔", "╚", "║")) for line in plain):
            continue  # a declared projection view; the frame already says so
        for line in plain:
            if any(identity in line for identity in branch_ids):
                assert "HYPOTHETICAL" in line or "NOT ADMITTED" in line, (
                    f"{command}: a real view names a projection unmarked: {line!r}"
                )


def test_counterfactual_view_states_its_isolation_explicitly(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    text = dispatch(state, "explore", ["90"])
    assert "HYPOTHETICAL" in text
    assert "NOT been admitted as evidence" in text
    assert "ADMITTED" in text and "NO" in text
    assert "LIVE SESSION" in text and "UNCHANGED" in text


def test_decision_view_separates_recommendation_from_action(state: WorkbenchState):
    """`decide` must never read as though it acted. It states the
    advisory and the literal command required to act on it."""
    text = dispatch(state, "decide", [])
    assert "ADVISORY ONLY" in text
    assert "no action has been taken" in text.lower()
    assert "select " in text
    assert state.selected_candidate is None


def test_selection_view_states_that_no_experiment_was_run(state: WorkbenchState):
    text = dispatch(state, "select", ["1"])
    assert "No experiment has been executed." in text
    assert "supplied externally" in text


def test_observation_view_names_its_external_provenance(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    text = dispatch(state, "observe", ["80"])
    assert "externally supplied experimental observation" in text
    assert "immutable" in text.lower()


def test_no_view_grades_a_result(state: WorkbenchState):
    """The interface reports; it does not judge. No view may describe a
    residual or a candidate in evaluative language."""
    forbidden = ("good", "bad", "better", "worse", "improved", "degraded",
                 "accurate", "inaccurate", "success", "failure", "poor", "excellent")
    for name, text in _rendered_views(state):
        lowered = text.lower()
        for word in forbidden:
            assert word not in lowered, f"{name}: evaluative language {word!r}"


def test_every_error_state_names_what_was_expected(state: WorkbenchState):
    """Every rejection tells the user the form that would have worked."""
    for command, args in (
        ("select", ["99"]), ("select", ["x"]), ("select", []),
        ("observe", ["abc"]), ("observe", []),
        ("explore", ["abc"]), ("explore", []),
        ("inspect", ["99"]),
        ("branch", ["99"]), ("branch", ["x"]), ("branch", []),
        ("compare", ["state", "99"]), ("compare", ["branch", "x"]),
        ("compare", ["state"]), ("compare", ["nonsense"]),
        ("timeline", ["99"]), ("timeline", ["x"]), ("inspect", ["state"]),
        ("thread", ["nonexistent"]), ("thread", ["99"]),
        ("state", ["99"]), ("state", ["baseline"]),
        ("criterion", ["nonexistent"]),
        ("bogus", []),
    ):
        text = dispatch(state, command, args)
        assert "EXPECTED" in text, f"{command} {args}: no expected-form guidance"


def test_help_documents_every_dispatchable_command(state: WorkbenchState):
    """The command reference and the dispatch table cannot drift apart."""
    documented = {name.split()[0] for _, commands in COMMAND_GROUPS for name, _ in commands}
    dispatchable = {
        "help", "scenario", "status", "candidates", "decide", "select",
        "predict", "explore", "observe", "inspect", "explain",
        "branches", "branch", "compare", "timeline", "thread", "state", "criterion",
        "history", "diagnostics", "quit",
    }
    assert documented == dispatchable
    text = dispatch(state, "help", [])
    for command in dispatchable:
        assert command in text


def test_empty_input_shows_the_command_reference(state: WorkbenchState):
    assert dispatch(state, "", []) == dispatch(state, "help", [])


# -- prompt and masthead ------------------------------------------------------------------------------


def test_prompt_carries_the_active_candidate(state: WorkbenchState):
    assert "01" not in format_prompt(state)
    dispatch(state, "select", ["1"])
    assert "01" in format_prompt(state)
    dispatch(state, "select", ["5"])
    assert "05" in format_prompt(state)


def test_masthead_is_rules_not_a_frame():
    """The masthead is deliberately not a panel -- the top of a session
    must be visually distinct from every view inside it."""
    lines = format_masthead().splitlines()
    assert lines[0].startswith(theme.HEAVY)
    assert lines[-1].startswith(theme.HEAVY)
    assert not any(theme._ANSI.sub("", line).startswith(tuple(FRAME_STARTS)) for line in lines)


# -- colour degradation --------------------------------------------------------------------------------


def test_colour_is_disabled_by_default_off_a_terminal(state: WorkbenchState):
    theme.set_color(None)
    text = dispatch(state, "status", [])
    assert "\x1b[" not in text  # captured output is never a TTY


def test_no_color_env_var_is_respected(monkeypatch, state: WorkbenchState):
    theme.set_color(None)
    monkeypatch.setenv("WORKBENCH_FORCE_COLOR", "1")
    monkeypatch.setenv("NO_COLOR", "1")
    assert theme.color_enabled() is False


def test_layout_is_identical_with_and_without_colour(state: WorkbenchState):
    """Colour is decoration, never structure: every view must occupy the
    same lines at the same widths in both modes.

    Text is compared by WIDTH rather than byte-for-byte, because a
    filled badge deliberately substitutes `[ACTIVE]` for inverse video
    when colour is unavailable -- colour is never the only carrier of a
    state, so the monochrome mode needs its own glyph. The substitution
    is width-preserving, which is exactly what this asserts."""
    theme.set_color(False)
    plain = {name: text for name, text in _rendered_views(state)}

    with open(EXAMPLE_SCENARIO_PATH, encoding="utf-8") as f:
        config = json.load(f)
    colored_state = bootstrap_research_scenario(config, clock=_fixed_clock())
    theme.set_color(True)
    colored = {name: theme._ANSI.sub("", text) for name, text in _rendered_views(colored_state)}

    assert set(plain) == set(colored)
    for name in plain:
        plain_lines = plain[name].splitlines()
        colored_lines = colored[name].splitlines()
        assert len(plain_lines) == len(colored_lines), f"{name}: line count differs between colour modes"
        for a, b in zip(plain_lines, colored_lines):
            assert len(a) == len(b), f"{name}: width differs between colour modes:\n  {a!r}\n  {b!r}"


def test_badge_fallback_preserves_width_without_colour():
    """The monochrome substitution for a filled badge must not shift
    anything on its row."""
    theme.set_color(True)
    colored = theme.visible_len(theme.badge("active", filled=True))
    theme.set_color(False)
    plain = theme.visible_len(theme.badge("active", filled=True))
    assert colored == plain
    assert theme.badge("active", filled=True) == "[ACTIVE]"


# -- Phase 74: the scenario workspace -------------------------------------------------------------------


def test_scenario_view_describes_the_research_programme(state: WorkbenchState):
    """`scenario` answers "what am I operating?" without reading JSON or
    source: study, property, process, criterion, every formulation and
    every context, and how much of the space has been measured."""
    text = dispatch(state, "scenario", [])
    assert "RESEARCH PROGRAMME" in text
    assert "polymer tensile strength study" in text
    assert "tensile_strength >= 80.0" in text
    for formulation in ("baseline", "modified", "high_filler"):
        assert formulation in text
    for temperature in ("25 C", "80 C", "120 C"):
        assert temperature in text
    assert "MEASURED CELLS" in text and "0 of 9" in text


def test_scenario_view_tracks_measured_coverage(state: WorkbenchState):
    """Coverage is plain counting over real sample counts, and is never
    presented as progress toward a goal."""
    assert "0 of 9" in dispatch(state, "scenario", [])
    dispatch(state, "select", ["1"])
    dispatch(state, "observe", ["82"])
    assert "1 of 9" in dispatch(state, "scenario", [])
    dispatch(state, "observe", ["85"])
    assert "1 of 9" in dispatch(state, "scenario", [])  # same cell, still one measured
    dispatch(state, "select", ["2"])
    dispatch(state, "observe", ["70"])
    assert "2 of 9" in dispatch(state, "scenario", [])


def test_scenario_view_reports_absence_rather_than_failing():
    """A session built directly, with no scenario, says so."""
    from workbench.interaction import bootstrap_multi_candidate_scenario
    built = bootstrap_multi_candidate_scenario(clock=_fixed_clock())
    object.__setattr__(built, "scenario", None)
    text = dispatch(built, "scenario", [])
    assert "NO SCENARIO LOADED" in text
    assert "EXPECTED" in text


def test_status_reports_the_current_recommendation_without_selecting(state: WorkbenchState):
    """`status` surfaces what the optimizer currently recommends, and is
    explicit that seeing it is not acting on it."""
    text = dispatch(state, "status", [])
    assert "CURRENT RECOMMENDATION" in text
    assert "advisory only" in text
    assert "select " in text
    assert state.selected_candidate is None  # inspecting status selects nothing


def test_status_recommendation_does_not_overwrite_the_users_last_decide(state: WorkbenchState):
    """`status` uses a read-only evaluation, so it never clobbers what
    the user's own `decide` recorded."""
    dispatch(state, "decide", [])
    recorded = state.last_decision
    assert recorded is not None
    dispatch(state, "status", [])
    assert state.last_decision is recorded


def test_status_notes_when_the_recommendation_is_already_active(state: WorkbenchState):
    recommended_line = dispatch(state, "status", []).split("RECOMMENDED")[1].split("\n")[0]
    number = recommended_line.strip().split()[0]
    dispatch(state, "select", [number])
    assert "this is the active candidate" in dispatch(state, "status", [])


# -- Phase 80: aliases ----------------------------------------------------------------------------------


@pytest.mark.parametrize("alias, canonical", [("?", "help"), ("about", "scenario"), ("q", "quit")])
def test_aliases_resolve_to_their_canonical_command(state: WorkbenchState, alias, canonical):
    assert dispatch(state, alias, []) == dispatch(state, canonical, [])


def test_exit_and_quit_both_end_the_session(state: WorkbenchState):
    assert dispatch(state, "exit", []) == "__QUIT__"
    assert dispatch(state, "quit", []) == "__QUIT__"


# -- Phases 75/76/79: console density -------------------------------------------------------------------


def test_registry_marks_what_is_unknown(state: WorkbenchState):
    """WHAT IS UNKNOWN must be scannable, not inferred from a zero."""
    text = dispatch(state, "candidates", [])
    assert text.count("UNMEASURED") == 9
    assert "MEASURED" in text and "0 of 9" in text

    dispatch(state, "select", ["1"])
    dispatch(state, "observe", ["82"])
    text = dispatch(state, "candidates", [])
    assert text.count("UNMEASURED") == 8  # the measured candidate lost its marker
    assert "1 of 9" in text
    assert "8 carry no observation yet" in text


def test_decision_table_reports_samples_per_candidate(state: WorkbenchState):
    text = dispatch(state, "decide", [])
    assert "SAMPLES" in text and "UTILITY" in text and "STATUS" in text
    header = next(line for line in text.splitlines() if "CANDIDATE" in line and "UTILITY" in line)
    assert header.index("SAMPLES") < header.index("UTILITY") < header.index("STATUS")


def test_decision_recommendation_shows_the_inputs_behind_it(state: WorkbenchState):
    """The basis block reports the computational facts that produced the
    ranking -- never an invented scientific explanation."""
    dispatch(state, "select", ["1"])
    dispatch(state, "observe", ["82"])
    dispatch(state, "observe", ["91"])
    text = dispatch(state, "decide", [])
    for field in ("PREDICTION", "UNCERTAINTY", "SAMPLES", "INFORMATION", "UTILITY", "BASIS"):
        assert field in text
    assert "highest current utility" in text
    assert "NEXT HIGHEST" in text  # contrast value, both already computed by materials.optimization


def test_diagnostics_report_sample_counts_and_candidate_identity(state: WorkbenchState):
    """Diagnostics is telemetry: it names the candidate by id and shows
    the sample count either side of every transition."""
    dispatch(state, "select", ["1"])
    dispatch(state, "observe", ["82"])
    dispatch(state, "observe", ["91"])
    text = dispatch(state, "diagnostics", [])
    assert "candidate_id" in text
    assert "model_state_key" in text
    assert "samples t" in text and "samples t+1" in text


def test_history_stays_narrative_while_diagnostics_stays_technical(state: WorkbenchState):
    """Two views over one trajectory: history reads as chronology,
    diagnostics as telemetry. Neither duplicates the other's role."""
    dispatch(state, "select", ["1"])
    dispatch(state, "observe", ["82"])
    dispatch(state, "observe", ["91"])
    history = dispatch(state, "history", [])
    diagnostics = dispatch(state, "diagnostics", [])

    for technical in ("model_state_key", "candidate_id", "samples t"):
        assert technical not in history
        assert technical in diagnostics
    for narrative in ("prediction → observation", "residual", "state"):
        assert narrative in history
    # both describe the same transitions and agree on the residual
    count = len(state.history().diagnostics)
    assert count == 2
    for view in (history, diagnostics):
        assert f"{count} TRANSITIONS" in view
    assert "+9.0" in history and "+9.0" in diagnostics  # 91 - 82


# -- Phase 77: predict and explore as one instrument -----------------------------------------------------


def test_predict_and_explore_share_candidate_and_state_context(state: WorkbenchState):
    """Both views are rooted at the SAME real state and name the SAME
    candidate -- that shared context is what makes them read as two
    projections of one research state."""
    dispatch(state, "select", ["1"])
    dispatch(state, "observe", ["80"])
    real_state_id = state.session.state.id

    predict_text = dispatch(state, "predict", [])
    explore_text = dispatch(state, "explore", ["120"])

    for text in (predict_text, explore_text):
        assert "REAL STATE" in text
        assert theme.ident(real_state_id) in text           # same root state
        assert "baseline · tensile_strength · 25 C" in text  # same candidate
        assert "PROJECTION" in text
        # the identical readout vocabulary
        for row in ("PREDICTION", "UNCERTAINTY", "SAMPLES", "INFORMATION"):
            assert row in text


def test_explore_renders_the_hypothetical_branch_one_level_deeper(state: WorkbenchState):
    """The lineage tree is the visual carrier of the distinction:
    predict stops at the real state, explore continues into a branch."""
    dispatch(state, "select", ["1"])
    predict_text = dispatch(state, "predict", [])
    explore_text = dispatch(state, "explore", ["120"])

    assert "HYPOTHETICAL" not in predict_text
    assert "PROJECTED" not in predict_text
    assert "HYPOTHETICAL" in explore_text
    assert "PROJECTED" in explore_text
    assert "NOT REAL EVIDENCE." in explore_text
    assert "real session is unchanged" in explore_text


def test_exploration_leaves_real_history_pool_and_prediction_untouched(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    dispatch(state, "observe", ["80"])
    before_state = state.session.state.id
    before_fingerprint = state.pool.fingerprint()
    before_history = len(state.session.state_history)
    before_predict = dispatch(state, "predict", [])

    dispatch(state, "explore", ["120"])

    assert state.session.state.id == before_state
    assert state.pool.fingerprint() == before_fingerprint
    assert len(state.session.state_history) == before_history
    assert dispatch(state, "predict", []) == before_predict  # the real projection is unchanged


def test_hypothetical_marker_survives_in_the_projected_state(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    dispatch(state, "observe", ["80"])
    outcome = state.explore(120.0)
    marked = [
        s for samples in outcome.projected_state.samples.values() for s in samples
        if s.observation_id.startswith(HYPOTHETICAL_SAMPLE_PREFIX)
    ]
    assert len(marked) == 1 and marked[0].value == 120.0
    for samples in state.session.state.samples.values():  # never in real history
        for sample in samples:
            assert not sample.observation_id.startswith(HYPOTHETICAL_SAMPLE_PREFIX)


def test_repeated_identical_exploration_is_deterministic(state: WorkbenchState):
    """The same hypothetical against the same real state renders
    identically -- including the content-derived projected-state id,
    which is a function of that content and nothing else."""
    dispatch(state, "select", ["1"])
    dispatch(state, "observe", ["80"])
    first = dispatch(state, "explore", ["120"])
    second = dispatch(state, "explore", ["120"])
    assert first == second


# -- Phase 78: observation as a state transition ----------------------------------------------------------


def test_observation_renders_every_before_and_after_pair(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    dispatch(state, "observe", ["80"])
    text = dispatch(state, "observe", ["100"])

    assert "STATE TRANSITION" in text
    transition_rows = {
        line.strip("│ ").split()[0]: line for line in text.splitlines()
        if theme.TRANSITION in line and line.startswith("│")
    }
    assert {"SAMPLES", "PREDICTION", "UNCERTAINTY", "STATE"} <= set(transition_rows)
    assert "1" in transition_rows["SAMPLES"] and "2" in transition_rows["SAMPLES"]
    assert "80.0" in transition_rows["PREDICTION"] and "90.0" in transition_rows["PREDICTION"]
    assert "CONTEXT" in text and "25 C" in text


def test_first_observation_shows_undetermined_on_both_sides_of_the_residual(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    text = dispatch(state, "observe", ["80"])
    measurement = text.split("MEASUREMENT")[1].split("STATE TRANSITION")[0]
    predicted = next(line for line in measurement.splitlines() if "PREDICTED" in line)
    residual = next(line for line in measurement.splitlines() if line.strip("│ ").startswith("RESIDUAL"))
    assert theme.UNDETERMINED in predicted and not any(ch.isdigit() for ch in predicted.split("PREDICTED")[1])
    assert theme.UNDETERMINED in residual


def test_negative_residual_is_never_shown_as_positive(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    dispatch(state, "observe", ["100"])
    dispatch(state, "observe", ["80"])
    text = dispatch(state, "observe", ["30"])  # 30 - mean(100, 80) = -60
    assert "-60.0" in text
    assert "+60.0" not in text
    assert state.assessments[-1].residual == -60.0


# -- Phase 79: one transition, recognisable in both views ---------------------------------------------------


def test_the_same_transition_is_recognisable_in_history_and_diagnostics(state: WorkbenchState):
    """Candidate identity, residual, state transition and sample counts
    must agree across the two views -- they are layers of one telemetry
    system, not two calculations."""
    dispatch(state, "select", ["1"])
    dispatch(state, "observe", ["80"])
    dispatch(state, "observe", ["100"])
    dispatch(state, "observe", ["60"])

    history = dispatch(state, "history", [])
    diagnostics = dispatch(state, "diagnostics", [])
    diagnostic_set = state.history()
    assert len(diagnostic_set.diagnostics) == 3

    for d in diagnostic_set.diagnostics:
        # the same state identities appear in both views
        for identity in (theme.ident(d.predecessor_state_id), theme.ident(d.successor_state_id)):
            assert identity in history
            assert identity in diagnostics
        if d.assessment is not None:
            residual = theme.num(d.residual_against_previous_prediction, signed=True)
            assert residual in history
            assert residual in diagnostics

    # diagnostics additionally carries the technical telemetry history omits
    for technical in ("candidate_id", "model_state_key", "state_t", "state_t+1", "samples t", "samples t+1"):
        assert technical in diagnostics
    assert "candidate_id" not in history
    # and both agree on the candidate
    assert "baseline · 25 C" in history


# -- Phase 80: interaction hardening -------------------------------------------------------------------------


def test_a_numeric_unit_is_rejected_as_a_likely_mistyped_value(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    text = dispatch(state, "observe", ["90", "100"])
    assert "INVALID UNIT" in text
    assert "EXPECTED" in text
    assert not state.assessments  # nothing was admitted


def test_a_real_unit_is_accepted_and_shown_on_the_measurement(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    text = dispatch(state, "observe", ["90", "GPa"])
    assert "GPa" in text
    assert state.assessments[-1].result.content["unit"] == "GPa"


def test_empty_history_and_diagnostics_explain_the_next_step(state: WorkbenchState):
    dispatch(state, "select", ["1"])
    for view in ("history", "diagnostics"):
        text = dispatch(state, view, [])
        assert "NO TRANSITIONS YET" in text
        assert "observe <value>" in text


def test_selection_survives_a_changed_recommendation(state: WorkbenchState):
    """Selecting is the user's choice; a later recommendation change
    never silently moves it."""
    dispatch(state, "select", ["1"])
    chosen = state.selected_candidate
    dispatch(state, "observe", ["80"])
    dispatch(state, "decide", [])  # the recommendation moves off candidate 1
    assert state.selected_candidate is not None
    assert state.selected_candidate.id == chosen.id
