"""workbench.cli: the workbench's user-facing surface -- command
parsing and presentation only. Every number rendered here is read
directly off a domain object `workbench.interaction.WorkbenchState` (or
a `materials.*`/`experiment.*` object it already produced); this module
computes nothing, and interprets nothing.

`dispatch()` returns text rather than printing, so the entire
interaction surface is callable from a test with no stdin/stdout
involved. `run_repl()` is the only function here that touches a
terminal.

No CLI framework, no third-party dependency: `parse_command`/`dispatch`/
`run_repl` are plain functions over `str`/`WorkbenchState`, using only
the standard library plus `workbench.theme` for layout.

PRESENTATION CONTRACT -- the rules every view below holds to, so the
interface reads as one instrument rather than a set of commands:

  ONE FRAME VOCABULARY. Every view is a `theme.panel`: a titled rule, a
  padded body, a closing rule. A single rule means established fact; a
  DOUBLE rule means hypothetical (used by, and only by, `explore`). An
  error is a panel too -- a state of the interface, not a break in it.

  LABELS LEFT, VALUES ALIGNED. Uppercase dim labels at a fixed width,
  values on a common column, units dim and trailing. A reader scans one
  column, not a paragraph.

  UNDETERMINED IS A WORD. A quantity the model cannot determine renders
  as the literal token UNDETERMINED in amber -- never a dash, never a
  blank, never zero. This is the interface's single most important
  honesty rule and `theme.num` enforces it centrally.

  SIGN IS NEVER DROPPED. Residuals and deltas render through
  `theme.num(signed=True)`, so `+20.0` and `-25.0` are visually
  distinct at a glance. No residual is ever coloured by magnitude or
  direction: the interface reports residuals, it does not grade them.

  RECOMMENDATION IS NOT ACTION. `decide` renders its choice as an
  advisory with the literal command needed to act on it; only `select`
  changes what `predict`/`explore`/`observe` operate on. The two are
  never rendered in the same voice.

  INDICES ARE 1-BASED AND ZERO-PADDED (`01`, `02`) -- a presentation
  choice this module owns end to end. `WorkbenchState.select_candidate`
  and `list_candidates` remain plain 0-indexed sequence operations
  underneath; `_display_index` and `_cmd_select` are the only places
  the translation happens.
"""

from __future__ import annotations

import json
import sys
from typing import List, NamedTuple, Optional, Sequence, Tuple, Union

from materials.assessment import PredictionAssessment
from materials.candidates import ActionCandidate
from materials.diagnostics import StateTransitionDiagnostic
from materials.ensemble import CounterfactualOutcome
from materials.decision import Criterion, ProgramDecision
from materials.trajectory import PredictionDelta
from materials.model_state import ModelState, Prediction
from materials.optimization import OptimizationResult
from experiment.session import trajectory_of
from materials.diagnostics import diagnose_transitions
from workbench import theme
from workbench.interaction import (
    WorkbenchState, bootstrap_multi_candidate_scenario, bootstrap_research_scenario, evaluate_decision,
)

PRODUCT = "S C O U T   R E T R I E V A L   A G E N T"
SUBTITLE = "EXPERIMENTAL WORKBENCH · DETERMINISTIC STATE ARCHITECTURE"

# Display-only abbreviations of `materials.optimization`'s own status
# vocabulary, so the decision table stays column-aligned. The full
# status is always available on the underlying `CandidateOptimization`.
_SHORT_STATUS = {
    "SELECTED": "selected",
    "ELIGIBLE_NOT_SELECTED": "eligible",
    "NOT_ELIGIBLE": "ineligible",
}

# Aliases, added only where they improve usability: `?` is the
# near-universal terminal request for help, `about` is the common
# word for a programme summary, and `q`/`exit` are what people type
# to leave. No abbreviation is invented for any other command.
ALIASES = {"?": "help", "about": "scenario", "q": "quit", "exit": "quit",
           "focus": "select", "why": "explain"}

COMMAND_GROUPS: Tuple[Tuple[str, Tuple[Tuple[str, str], ...]], ...] = (
    ("inspect", (
        ("scenario", "the research programme being investigated"),
        ("status", "session state, selection, recommendation, residual"),
        ("candidates", "registry with predictions and utility"),
        ("predict", "model prediction for the active candidate"),
        ("inspect [n|terms]", "everything computed about one candidate"),
        ("inspect state <n>", "one real state from the timeline"),
    )),
    ("decide", (
        ("decide", "utility landscape and recommendation"),
        ("explain", "why the last decision ranked as it did"),
        ("select <n|terms>", "activate a candidate by number or by name"),
        ("select clear", "deactivate the current candidate"),
        ("explore <value>", "project a hypothetical outcome"),
        ("branches", "every hypothetical branch projected this session"),
        ("branch <n>", "re-inspect one retained hypothetical branch"),
        ("compare [operands]", "place two states, branches or decisions side by side"),
    )),
    ("admit", (
        ("observe <value> [unit]", "admit an externally supplied result"),
    )),
    ("review", (
        ("timeline [n]", "the real state trajectory, and one state within it"),
        ("thread [n|terms]", "one candidate's projection through that trajectory"),
        ("state [n]", "every candidate cell of one real state"),
        ("criterion [n|terms]", "candidate cells against the declared criterion"),
        ("history", "transition narrative for this candidate"),
        ("diagnostics", "full detail for every transition"),
    )),
    ("session", (
        ("help", "this reference"),
        ("quit", "end the session"),
    )),
)


# -- shared rendering helpers -----------------------------------------------------------------------


def _display_index(state: WorkbenchState, candidate: ActionCandidate) -> int:
    return state.list_candidates().index(candidate) + 1


def _candidate_line(state: WorkbenchState, candidate: ActionCandidate) -> str:
    """`01  baseline · tensile_strength · 25 C` -- the canonical
    one-line identity of a candidate, used everywhere a candidate is
    named so it is recognisable across every view."""
    sep = theme.paint(f" {theme.DOT} ", theme.STRUCTURE)
    return (
        theme.paint(theme.index(_display_index(state, candidate)), theme.ACCENT)
        + "  "
        + theme.paint(candidate.formulation.natural_key, theme.VALUE)
        + sep
        + theme.paint(candidate.property, theme.VALUE)
        + sep
        + theme.paint(theme.context(candidate.target_context), theme.VALUE)
    )


def _short_candidate_line(state: WorkbenchState, candidate: ActionCandidate) -> str:
    """The compact form used inside dense tables: formulation + context,
    plus the PROPERTY when the scenario declares more than one. PHASE 103
    -- with several properties, formulation + context no longer names a
    cell uniquely, and two rows would read identically."""
    parts = [candidate.formulation.natural_key]
    if state.scenario is not None and len(state.scenario.properties) > 1:
        parts.append(candidate.property)
    parts.append(theme.context(candidate.target_context))
    return f" {theme.DOT} ".join(parts)


def _no_selection_notice() -> str:
    return theme.notice(
        "no active candidate",
        "no candidate selected — this command operates on the active candidate.",
        hint="candidates   then   select <n>",
    )


def _unit_for(state: WorkbenchState) -> str:
    """The unit last admitted for the active candidate, if any --
    display only, read off the real `ExperimentalResult.content`, never
    inferred."""
    for assessment in reversed(state.assessments):
        unit = assessment.result.content.get("unit")
        if isinstance(unit, str) and unit:
            return unit
    return ""


# -- format_* : deterministic renderers of already-existing domain objects ---------------------------


def format_masthead() -> str:
    return theme.masthead([PRODUCT, SUBTITLE])


def format_scenario_banner(state: WorkbenchState) -> str:
    """The session header: which study is loaded, its configured search
    space, the full candidate roster numbered to match `select <n>`, and
    the current real-observation count -- so the whole space is visible
    before anything is typed."""
    candidates = state.list_candidates()
    body: List[str] = [""]

    scenario = state.scenario
    if scenario is not None:
        body.append(theme.paint(scenario.name, theme.BOLD, theme.VALUE))
        body.append("")
        body.append(theme.kv("process", theme.paint(scenario.process, theme.VALUE)))
        body.append(theme.kv("properties", theme.paint(
            ", ".join(scenario.properties), theme.VALUE)))
        body.append(theme.kv("criteria", theme.paint(
            str(len(scenario.criteria)), theme.VALUE)
            + theme.paint("   see `scenario` for each", theme.MUTED)))
        body.append(theme.kv("search space", theme.paint(scenario.describe_candidate_space(), theme.VALUE)))
        body.append("")

    body.append(theme.divider("candidates"))
    body.append("")
    if not candidates:
        body.append(theme.paint("no candidates generated for this scenario", theme.WARN))
    for candidate in candidates:
        body.append(_candidate_line(state, candidate))
    body.append("")
    body.append(theme.divider())
    body.append("")
    body.append(theme.kv("observations", theme.paint(str(state.total_sample_count()), theme.VALUE)))
    body.append("")

    return theme.panel(
        "research scenario", body,
        right=f"{len(candidates)} candidate{'s' if len(candidates) != 1 else ''}",
    )


def _scenario_criteria_rows(scenario) -> List[str]:
    """Every declared criterion, one row each, numbered in the author's
    own order. PHASE 103 -- the scenario may declare several properties
    and several criteria per property, so a single `property`/`criterion`
    pair can no longer stand for the programme."""
    rows: List[str] = []
    for position, criterion in enumerate(scenario.criteria, start=1):
        rows.append(
            "  " + theme.paint(theme.index(position), theme.ACCENT) + "  "
            + theme.paint(criterion.property, theme.VALUE) + " "
            + theme.paint(f"{criterion.operator} {theme.num(criterion.target)}", theme.VALUE)
        )
        rows.append("     " + theme.paint(theme.context(criterion.context), theme.MUTED))
    return rows


def format_help() -> str:
    body: List[str] = [""]
    for group, commands in COMMAND_GROUPS:
        body.append(theme.divider(group))
        body.append("")
        for name, description in commands:
            body.append(
                "  " + theme.paint(theme.pad(name, 24), theme.ACCENT)
                + theme.paint(theme.truncate(description, theme.width() - 30), theme.LABEL)
            )
        body.append("")
    return theme.panel("command reference", body, right="workbench")


def _coverage(state: WorkbenchState) -> Tuple[int, int]:
    """How many candidate cells carry at least one real sample, out of
    how many exist. Plain counting over `predict(...).sample_count` --
    no new statistic, and never presented as progress toward a goal."""
    candidates = state.list_candidates()
    observed = sum(1 for c in candidates if state.session.predict(c).sample_count > 0)
    return observed, len(candidates)


def _recommended_candidate(state: WorkbenchState) -> Optional[ActionCandidate]:
    """The candidate the existing optimization currently recommends, or
    `None` if the policy selects nothing. Read-only: uses
    `evaluate_decision` rather than `state.decide()`, so inspecting
    status never overwrites what the user's own last `decide` reported."""
    decision = evaluate_decision(state.candidates, state.session.state, state.session.iteration)
    for option in decision.optimizations:
        if option.status == "SELECTED":
            return next(c for c in state.list_candidates() if c.id == option.candidate_id)
    return None


def format_scenario(state: WorkbenchState) -> str:
    """The research programme itself: what is being studied, under which
    conditions, against which criterion, and how much of the space has
    been measured. Answers "what am I operating?" without reading JSON
    or source."""
    scenario = state.scenario
    if scenario is None:
        return theme.notice(
            "no scenario loaded",
            "this session was constructed directly rather than from a research scenario.",
            hint="python -m workbench --scenario <file.json>", tone=theme.WARN,
        )

    observed, total = _coverage(state)
    body: List[str] = [""]
    body.append(theme.paint(scenario.name, theme.BOLD, theme.VALUE))
    body.append("")
    body.append(theme.kv("process", theme.paint(scenario.process, theme.VALUE)))
    body.append(theme.kv("properties", theme.paint(", ".join(scenario.properties), theme.VALUE)))
    body.append("")

    body.append(theme.divider("declared criteria"))
    body.append("")
    body.extend(_scenario_criteria_rows(scenario))
    body.append("")
    body.append(theme.paint(
        "  Each criterion is evaluated independently against its own", theme.MUTED))
    body.append(theme.paint(
        "  property and context. None is compared with another.", theme.MUTED))
    body.append("")

    body.append(theme.divider("formulations"))
    body.append("")
    for formulation in scenario.formulations:
        body.append("  " + theme.paint(formulation, theme.VALUE))
    body.append("")

    body.append(theme.divider("experimental contexts"))
    body.append("")
    for ctx in scenario.contexts:
        body.append("  " + theme.paint(theme.context(ctx), theme.VALUE))
    body.append("")

    body.append(theme.divider("search space"))
    body.append("")
    body.append(theme.kv("candidates", theme.paint(str(total), theme.VALUE)
                         + theme.paint(f"   {scenario.describe_candidate_space()}", theme.MUTED)))
    body.append(theme.kv("measured cells", theme.paint(f"{observed} of {total}", theme.VALUE)))
    body.append(theme.kv("observations", theme.paint(str(state.total_sample_count()), theme.VALUE)))
    body.append("")

    return theme.panel(
        "research programme", body,
        right=f"{total} candidate{'s' if total != 1 else ''}",
    )


def format_status(state: WorkbenchState) -> str:
    observed, total = _coverage(state)
    body: List[str] = [""]
    if state.scenario is not None:
        body.append(theme.kv("study", theme.paint(state.scenario.name, theme.VALUE)))
        body.append(theme.kv("properties", theme.paint(
            ", ".join(state.scenario.properties), theme.VALUE)))
    body.append(theme.kv("model state", theme.ident(state.session.state.id)))
    body.append(theme.kv("transitions", theme.paint(str(len(state.session.state_history) - 1), theme.VALUE)))
    body.append(theme.kv("observations", theme.paint(str(state.total_sample_count()), theme.VALUE)))
    body.append(theme.kv("candidates", theme.paint(str(total), theme.VALUE)
                         + theme.paint(f"   {observed} measured", theme.MUTED)))
    body.append("")

    body.append(theme.divider("active candidate"))
    body.append("")
    if state.selected_candidate is None:
        body.append(theme.kv("selection", theme.paint("none", theme.WARN)))
        body.append(theme.kv("", theme.paint("issue  select <n>  to choose one", theme.MUTED)))
    else:
        candidate = state.selected_candidate
        prediction = state.session.predict(candidate)
        body.append(theme.kv("selection", _candidate_line(state, candidate)))
        body.append(theme.kv("prediction", theme.quantity(prediction.predicted_value, _unit_for(state))))
        body.append(theme.kv("uncertainty", theme.quantity(prediction.uncertainty)))
        body.append(theme.kv("samples", theme.paint(str(prediction.sample_count), theme.VALUE)))
    body.append("")

    body.append(theme.divider("current recommendation"))
    body.append("")
    recommended = _recommended_candidate(state)
    if recommended is None:
        body.append(theme.kv("recommended", theme.paint("none selectable under policy", theme.WARN)))
    else:
        body.append(theme.kv("recommended", _candidate_line(state, recommended)))
        if state.selected_candidate is not None and state.selected_candidate.id == recommended.id:
            body.append(theme.kv("", theme.paint("this is the active candidate", theme.MUTED)))
        else:
            body.append(theme.kv("", theme.paint(
                f"advisory only — issue  select {theme.index(_display_index(state, recommended))}  to act on it",
                theme.MUTED,
            )))
    body.append("")

    body.append(theme.divider("latest observation"))
    body.append("")
    if state.assessments:
        latest = state.assessments[-1]
        body.append(theme.kv("observed", theme.quantity(latest.observed_value, _unit_for(state))))
        body.append(theme.kv("residual", theme.quantity(latest.residual, _unit_for(state), signed=True)))
        body.append(theme.kv("observation", theme.ident(latest.observation.id)))
    else:
        body.append(theme.kv("recorded", theme.paint("none", theme.MUTED)))
    body.append("")

    body.append(theme.divider("counterfactual"))
    body.append("")
    if state.last_counterfactual is not None:
        outcome = state.last_counterfactual
        body.append(theme.kv("inspected", theme.quantity(outcome.hypothetical_value, _unit_for(state))))
        body.append(theme.kv("projected state", theme.ident(outcome.projected_state_id)))
        body.append(theme.kv("", theme.badge("hypothetical · not evidence", theme.WARN)))
    else:
        body.append(theme.kv("inspected", theme.paint("none", theme.MUTED)))
    body.append("")

    right = state.scenario.name if state.scenario is not None else None
    return theme.panel("session status", body, right=right)


def format_candidate(state: WorkbenchState, candidate: ActionCandidate, optimization) -> List[str]:
    prediction = state.session.predict(candidate)
    estimate = state.information_value_estimate(candidate)
    selected = state.selected_candidate is not None and state.selected_candidate.id == candidate.id

    marks: List[str] = []
    if selected:
        marks.append(theme.badge("active", theme.ACCENT, filled=True))
    if optimization is not None and optimization.status == "SELECTED":
        marks.append(theme.paint(theme.ARROW + " ", theme.ACCENT) + theme.badge("recommended", theme.ACCENT))
    if prediction.sample_count == 0:
        marks.append(theme.badge("unmeasured", theme.WARN))

    header = _candidate_line(state, candidate)
    if marks:
        header = theme.pad(header, theme.width() - 6 - sum(theme.visible_len(m) + 2 for m in marks))
        header += "  ".join(marks)

    utility_value = theme.quantity(optimization.utility.utility) if optimization is not None else theme.paint(
        theme.UNDETERMINED, theme.WARN
    )
    rows: List[Tuple[str, str]] = [
        ("prediction", theme.quantity(prediction.predicted_value, _unit_for(state))),
        ("uncertainty", theme.quantity(prediction.uncertainty)),
        ("samples", theme.paint(str(prediction.sample_count), theme.VALUE)),
        ("information", theme.paint(
            estimate.estimate_status,
            theme.WARN if estimate.estimate is None else theme.VALUE,
        ) + (theme.paint(f"  {theme.num(estimate.estimate)}", theme.MUTED) if estimate.estimate is not None else "")),
        ("utility", utility_value),
        ("id", theme.ident(candidate.id)),
    ]
    return [header, *theme.tree(rows)]


def format_candidates(state: WorkbenchState) -> str:
    candidates = state.list_candidates()
    if not candidates:
        return theme.notice(
            "empty registry", "no candidates were generated for this scenario.", tone=theme.WARN,
        )
    decision = evaluate_decision(state.candidates, state.session.state, state.session.iteration)
    by_id = {o.candidate_id: o for o in decision.optimizations}

    observed, total = _coverage(state)
    body: List[str] = [""]
    body.append(
        theme.kv("measured", theme.paint(f"{observed} of {total}", theme.VALUE)
                 + theme.paint(f"   {total - observed} carry no observation yet", theme.MUTED))
    )
    body.append("")
    body.append(theme.divider())
    body.append("")
    for candidate in candidates:
        body.extend(format_candidate(state, candidate, by_id.get(candidate.id)))
        body.append("")
    return theme.panel(
        "candidate registry", body,
        right=f"{len(candidates)} candidate{'s' if len(candidates) != 1 else ''}",
    )


def _readout_rows(
    state: WorkbenchState, candidate: ActionCandidate, prediction: Prediction, unit: str,
    *, at_state=None, delta=None,
) -> List[str]:
    """The IDENTICAL readout vocabulary `predict` and `explore` both
    render -- prediction, uncertainty, samples, information -- so the
    two views are immediately recognisable as projections of the same
    research state. Every value is read off the `Prediction` it is
    given; `explore` passes the one `materials.ensemble.project_outcome`
    already computed, so nothing is calculated twice.

    `delta` (a `PredictionDelta`, when the caller has one) appends the
    signed change against the real state on the same rows."""
    estimate = state.information_value_estimate(candidate, at_state)
    rows = [
        theme.kv("prediction", theme.quantity(prediction.predicted_value, unit)),
        theme.kv("uncertainty", theme.quantity(prediction.uncertainty)),
        theme.kv("samples", theme.paint(str(prediction.sample_count), theme.VALUE)),
        theme.kv("information", theme.paint(
            estimate.estimate_status, theme.WARN if estimate.estimate is None else theme.VALUE,
        )),
    ]
    if delta is not None:
        rows[0] = theme.pad(rows[0], 40) + theme.paint("Δ  ", theme.STRUCTURE) + theme.quantity(
            delta.delta_predicted_value, signed=True)
        rows[1] = theme.pad(rows[1], 40) + theme.paint("Δ  ", theme.STRUCTURE) + theme.quantity(
            delta.delta_uncertainty, signed=True)
    return rows


def format_prediction(state: WorkbenchState, candidate: ActionCandidate, prediction: Prediction) -> str:
    """The REAL-state projection. Same frame vocabulary as `explore`,
    single-ruled and rooted at the real state -- the lineage tree stops
    at PREDICTION because nothing hypothetical is involved."""
    body = [
        "",
        *theme.lineage([
            ("real state", theme.ident(prediction.state_id)),
            ("prediction", theme.paint("from admitted evidence in this cell", theme.MUTED)),
        ]),
        "",
        theme.kv("candidate", _candidate_line(state, candidate)),
        "",
        theme.divider("readout"),
        "",
        *_readout_rows(state, candidate, prediction, _unit_for(state)),
        "",
    ]
    if prediction.predicted_value is None:
        body.append(theme.paint("No samples exist for this cell.", theme.MUTED))
        body.append(theme.paint("The model reports no value rather than assuming one.", theme.MUTED))
        body.append("")
    return theme.panel(
        "projection · real state", body,
        right=f"candidate {theme.index(_display_index(state, candidate))}",
    )


def _transitions_for(state: WorkbenchState, candidate: ActionCandidate):
    """Every real transition whose assessment belongs to this candidate,
    matched by `candidate_id` -- never by list position. Reads the
    `StateTransitionDiagnosticSet` `materials.diagnostics` already
    produced for the session's own trajectory."""
    trajectory = trajectory_of(state.session)
    diagnostics = diagnose_transitions(trajectory, candidate, tuple(state.assessments))
    return [d for d in diagnostics.diagnostics if d.assessment is not None]


def format_inspection(state: WorkbenchState, candidate: ActionCandidate) -> str:
    """The complete computational state relevant to one candidate. A
    projection over existing objects -- `ActionCandidate`, `Prediction`,
    `InformationValueEstimate`, `CandidateOptimization`,
    `StateTransitionDiagnostic` -- with no data model of its own."""
    prediction = state.session.predict(candidate)
    estimate = state.information_value_estimate(candidate)
    decision = evaluate_decision(state.candidates, state.session.state, state.session.iteration)
    optimization = next(o for o in decision.optimizations if o.candidate_id == candidate.id)
    transitions = _transitions_for(state, candidate)
    unit = _unit_for(state)
    measured = prediction.sample_count > 0

    body: List[str] = [
        "",
        theme.kv("candidate", _candidate_line(state, candidate)),
        theme.kv("formulation", theme.paint(candidate.formulation.natural_key, theme.VALUE)),
        theme.kv("property", theme.paint(candidate.property, theme.VALUE)),
        theme.kv("context", theme.paint(theme.context(candidate.target_context), theme.VALUE)),
        "",
        theme.divider("identity"),
        "",
        theme.kv("candidate_id", theme.ident(candidate.id, 24)),
        theme.kv("model_state_key", theme.ident(prediction.model_state_key, 24)),
        theme.kv("model state", theme.ident(prediction.state_id, 24)),
        "",
        theme.divider("computed state"),
        "",
        theme.kv("basis", theme.badge("real state", theme.ACCENT)
                 + theme.paint("   admitted evidence, not a projection", theme.MUTED)),
        theme.kv("measured", theme.badge("yes", theme.ACCENT) if measured else theme.badge("no", theme.WARN)),
        theme.kv("samples", theme.paint(str(prediction.sample_count), theme.VALUE)),
        theme.kv("prediction", theme.quantity(prediction.predicted_value, unit)),
        theme.kv("uncertainty", theme.quantity(prediction.uncertainty)),
        theme.kv("information", theme.paint(
            estimate.estimate_status, theme.WARN if estimate.estimate is None else theme.VALUE)),
        theme.kv("utility", theme.quantity(optimization.utility.utility)
                 + ("" if estimate.estimate is not None else theme.paint(
                     "   from exploration policy, not a measured quantity", theme.MUTED))),
        theme.kv("optimization", theme.paint(
            _SHORT_STATUS.get(optimization.status, optimization.status.lower()),
            theme.ACCENT if optimization.status == "SELECTED" else theme.MUTED)),
        "",
        theme.divider("observed history"),
        "",
    ]
    if not transitions:
        body.append(theme.paint("No observation has been admitted for this candidate.", theme.WARN))
        body.append(theme.paint("Its prediction rests on no evidence at all.", theme.MUTED))
    else:
        last = transitions[-1]
        body.append(theme.kv("transitions", theme.paint(str(len(transitions)), theme.VALUE)))
        body.append(theme.kv("last observed", theme.quantity(last.observation_value, unit)))
        body.append(theme.kv("last residual", theme.quantity(
            last.residual_against_previous_prediction, unit, signed=True)))
        body.append(theme.kv("last transition", theme.transition(
            theme.ident(last.predecessor_state_id), theme.ident(last.successor_state_id))))
    body.append("")
    return theme.panel(
        "candidate inspection", body,
        right=f"candidate {theme.index(_display_index(state, candidate))}",
    )


def format_explanation(state: WorkbenchState, optimization: OptimizationResult) -> str:
    """Explains an EXISTING computation -- which candidate the policy
    recommended, what each alternative received, which inputs were
    undetermined, and what changed since the last decision. Reports
    computational facts only: no causal or scientific claim is made
    about any material."""
    selected = [o for o in optimization.optimizations if o.status == "SELECTED"]
    body: List[str] = [""]

    if not selected:
        body.append(theme.paint("No candidate is selectable under the current policy.", theme.WARN))
        body.append(theme.paint("Every candidate's utility is undetermined, so none can rank.", theme.MUTED))
        body.append("")
        return theme.panel("decision explanation", body, right="no recommendation")

    chosen = next(c for c in state.list_candidates() if c.id == selected[0].candidate_id)
    body.append(theme.kv("recommended", _candidate_line(state, chosen)))
    body.append(theme.kv("utility", theme.quantity(selected[0].utility.utility)))
    body.append(theme.kv("policy", theme.paint(
        f"max_candidates={optimization.policy.max_candidates}", theme.VALUE)))
    body.append(theme.kv("reason", theme.paint(
        "highest determinate utility among eligible candidates", theme.VALUE)))
    body.append("")

    body.append(theme.divider("alternatives considered"))
    body.append("")
    for option in optimization.optimizations:
        candidate = next(c for c in state.list_candidates() if c.id == option.candidate_id)
        mark = theme.paint(theme.ARROW, theme.ACCENT) if option.status == "SELECTED" else " "
        body.append(
            f"  {mark} " + theme.paint(theme.index(_display_index(state, candidate)), theme.ACCENT) + "  "
            + theme.pad(theme.truncate(_short_candidate_line(state, candidate), 26), 28)
            + theme.pad(theme.quantity(option.utility.utility), 12)
            + theme.paint(_SHORT_STATUS.get(option.status, option.status.lower()), theme.MUTED)
        )
    body.append("")

    body.append(theme.divider("contributing inputs"))
    body.append("")
    body.append(
        "  " + theme.paint(theme.pad("  #", 6), theme.LABEL)
        + theme.paint(theme.pad("SAMPLES", 10), theme.LABEL)
        + theme.paint(theme.pad("UNCERTAINTY", 16), theme.LABEL)
        + theme.paint("INFORMATION", theme.LABEL)
    )
    undetermined: List[str] = []
    for option in optimization.optimizations:
        candidate = next(c for c in state.list_candidates() if c.id == option.candidate_id)
        prediction = state.session.predict(candidate)
        estimate = state.information_value_estimate(candidate)
        n = theme.index(_display_index(state, candidate))
        body.append(
            "    " + theme.pad(theme.paint(n, theme.ACCENT), 4)
            + theme.pad(theme.paint(str(prediction.sample_count), theme.VALUE), 10)
            + theme.pad(theme.quantity(prediction.uncertainty), 16)
            + theme.paint(
                estimate.estimate_status, theme.WARN if estimate.estimate is None else theme.VALUE)
        )
        if estimate.estimate is None:
            undetermined.append(n)
    body.append("")

    if undetermined:
        body.append(theme.paint(
            f"  Candidates {', '.join(undetermined)}", theme.WARN))
        body.append(theme.paint(
            "  have no computable information value.", theme.WARN))
        body.append(theme.paint(
            "  Their utility input came from the workbench's explicit", theme.MUTED))
        body.append(theme.paint(
            "  exploration policy, not from a measured quantity.", theme.MUTED))
        body.append(theme.paint(
            "  See workbench.interaction._utility_input_for.", theme.MUTED))
        body.append("")

    previous = state.previous_decision
    body.append(theme.divider("change since last decision"))
    body.append("")
    if previous is None:
        body.append(theme.paint("This is the first decision in this session.", theme.MUTED))
    else:
        previous_selected = [o for o in previous.optimizations if o.status == "SELECTED"]
        previous_id = previous_selected[0].candidate_id if previous_selected else None
        if previous_id is not None:
            was = next(c for c in state.list_candidates() if c.id == previous_id)
            body.append(theme.kv("previously", _candidate_line(state, was)))
        else:
            body.append(theme.kv("previously", theme.paint("no candidate was selectable", theme.WARN)))
        body.append(theme.kv("now", _candidate_line(state, chosen)))
        body.append("")
        if previous_id == chosen.id:
            body.append(theme.paint("  The recommendation is unchanged.", theme.VALUE))
        else:
            body.append(theme.paint(
                "  The recommendation changed because the computed", theme.VALUE))
            body.append(theme.paint(
                "  utility landscape changed.", theme.VALUE))
        body.append(theme.paint(
            "  No claim is made about any material — only about the computation.", theme.MUTED))
    body.append("")

    return theme.panel(
        "decision explanation", body,
        right=f"policy max_candidates={optimization.policy.max_candidates}",
    )


def format_decision(state: WorkbenchState, optimization: OptimizationResult) -> str:
    selected = [o for o in optimization.optimizations if o.status == "SELECTED"]

    body: List[str] = [""]
    body.append(
        theme.paint("  " + theme.pad("#", 4), theme.LABEL)
        + theme.paint(theme.pad("CANDIDATE", 30), theme.LABEL)
        + theme.paint(theme.pad("SAMPLES", 9), theme.LABEL)
        + theme.paint(theme.pad("UTILITY", 11), theme.LABEL)
        + theme.paint("STATUS", theme.LABEL)
    )
    body.append(theme.divider())
    for option in optimization.optimizations:
        candidate = next(c for c in state.list_candidates() if c.id == option.candidate_id)
        is_selected = option.status == "SELECTED"
        status = (
            theme.paint(theme.ARROW + " ", theme.ACCENT) + theme.badge("selected", theme.ACCENT)
            if is_selected else theme.paint(_SHORT_STATUS.get(option.status, option.status.lower()), theme.MUTED)
        )
        body.append(
            "  " + theme.paint(theme.pad(theme.index(_display_index(state, candidate)), 4), theme.ACCENT)
            + theme.pad(
                theme.paint(theme.truncate(_short_candidate_line(state, candidate), 28),
                            theme.VALUE if is_selected else theme.LABEL),
                30,
            )
            + theme.pad(theme.paint(str(state.session.predict(candidate).sample_count), theme.VALUE), 9)
            + theme.pad(theme.quantity(option.utility.utility), 11)
            + status
        )
    body.append("")

    body.append(theme.divider("recommendation"))
    body.append("")
    if selected:
        chosen = next(c for c in state.list_candidates() if c.id == selected[0].candidate_id)
        n = theme.index(_display_index(state, chosen))
        prediction = state.session.predict(chosen)
        estimate = state.information_value_estimate(chosen)
        body.append(theme.kv("candidate", _candidate_line(state, chosen)))
        body.append(theme.kv("prediction", theme.quantity(prediction.predicted_value, _unit_for(state))))
        body.append(theme.kv("uncertainty", theme.quantity(prediction.uncertainty)))
        body.append(theme.kv("samples", theme.paint(str(prediction.sample_count), theme.VALUE)))
        body.append(theme.kv("information", theme.paint(
            estimate.estimate_status, theme.WARN if estimate.estimate is None else theme.VALUE,
        )))
        body.append(theme.kv("utility", theme.quantity(selected[0].utility.utility)))
        body.append(theme.kv("basis", theme.paint("highest current utility under this policy", theme.VALUE)))
        # the next-highest determinate utility, shown for contrast -- both values are already
        # computed by materials.optimization; nothing is derived from them here.
        others = [
            o for o in optimization.optimizations
            if o.candidate_id != chosen.id and o.utility.utility is not None
        ]
        if others:
            runner_up = max(others, key=lambda o: o.utility.utility)  # type: ignore[arg-type,return-value]
            runner_candidate = next(c for c in state.list_candidates() if c.id == runner_up.candidate_id)
            body.append(theme.kv("next highest", theme.quantity(runner_up.utility.utility)
                                 + theme.paint(f"   candidate {theme.index(_display_index(state, runner_candidate))}",
                                               theme.MUTED)))
        body.append("")
        body.append(theme.paint("ADVISORY ONLY — no action has been taken.", theme.WARN))
        body.append(
            theme.paint("To act on this recommendation:  ", theme.MUTED)
            + theme.paint(f"select {n}", theme.ACCENT)
        )
    else:
        body.append(theme.paint("No candidate is selectable under the current policy.", theme.WARN))
        body.append(theme.paint("See `candidates` for each candidate's utility status.", theme.MUTED))
    body.append("")

    return theme.panel(
        "decision analysis", body, right=f"policy max_candidates={optimization.policy.max_candidates}",
    )


def format_selection(state: WorkbenchState, candidate: ActionCandidate) -> str:
    body = [
        "",
        theme.kv("active candidate", _candidate_line(state, candidate)),
        theme.kv("id", theme.ident(candidate.id)),
        "",
        theme.divider("status"),
        "",
        theme.paint("No experiment has been executed.", theme.VALUE),
        theme.paint("The next real observation must be supplied externally.", theme.MUTED),
        "",
        theme.paint("  observe <value>", theme.ACCENT)
        + theme.paint("     admit an externally obtained result", theme.MUTED),
        theme.paint("  explore <value>", theme.ACCENT)
        + theme.paint("     project a hypothetical one instead", theme.MUTED),
        "",
    ]
    return theme.panel("candidate selected", body, right=f"candidate {theme.index(_display_index(state, candidate))}")


def format_counterfactual(state: WorkbenchState, candidate: ActionCandidate, live_unchanged: bool) -> str:
    """The HYPOTHETICAL projection. Deliberately the same frame, the
    same lineage tree and the same readout rows as `format_prediction`
    -- but double-ruled, amber, and rooted one branch deeper, so the
    user reads it as the same instrument pointed at a branch that is
    not evidence."""
    outcome = state.last_counterfactual
    assert outcome is not None  # guaranteed: only rendered after a successful state.explore()
    unit = _unit_for(state)

    body = [
        "",
        *theme.lineage([
            ("real state", theme.ident(outcome.source_state_id)),
            ("hypothetical", theme.paint(f"y = {theme.num(outcome.hypothetical_value)}", theme.WARN)
             + (theme.paint(f" {unit}", theme.MUTED) if unit else "")),
            ("projected", theme.ident(outcome.projected_state_id)),
        ]),
        "",
        theme.kv("candidate", _candidate_line(state, candidate)),
        "",
        theme.divider("readout · projected"),
        "",
        *_readout_rows(
            state, candidate, outcome.prediction_after, unit,
            at_state=outcome.projected_state, delta=outcome.delta,
        ),
        "",
        theme.divider("isolation"),
        "",
        theme.kv("admitted", theme.badge("no", theme.WARN)
                 + theme.paint("   nothing was written to the evidence pool", theme.MUTED)),
        theme.kv("live session", theme.badge("unchanged" if live_unchanged else "CHANGED", theme.WARN)),
        theme.kv("real state", theme.ident(state.session.state.id)),
        "",
        theme.paint("NOT REAL EVIDENCE.", theme.WARN),
        theme.paint("This branch is hypothetical. It has NOT been admitted as evidence,", theme.MUTED),
        theme.paint("and the real session is unchanged.", theme.MUTED),
        "",
    ]
    return theme.panel(
        "projection · hypothetical branch", body,
        right="hypothetical · not evidence", tone=theme.WARN, double=True,
    )


def _branch_candidate(state: WorkbenchState, outcome: CounterfactualOutcome) -> Optional[ActionCandidate]:
    """Correspondence by `candidate_id` -- never by registry position and
    never by the candidate that happens to be selected right now."""
    return next((c for c in state.list_candidates() if c.id == outcome.candidate_id), None)


def _parent_note(state: WorkbenchState, outcome: CounterfactualOutcome) -> str:
    """PHASE 88 sec.7 -- a branch is never re-parented onto a newer real
    state. When the real session has advanced past the state a branch
    projected from, the view SAYS so rather than rewriting the branch."""
    if outcome.source_state_id == state.session.state.id:
        return theme.paint("   current real state", theme.MUTED)
    return theme.paint("   superseded · real session advanced", theme.MUTED)


def format_branches(state: WorkbenchState) -> str:
    """The registry. Same frame system, same identity formatting, same
    NOT ADMITTED language as the projection view -- double-ruled and
    amber, because every row in it is hypothetical."""
    if not state.branches:
        return theme.notice(
            "no counterfactual branches",
            "nothing has been projected in this session.",
            hint="select <n>   then   explore <value>",
        )

    unit = _unit_for(state)
    body: List[str] = [""]
    for position, outcome in enumerate(state.branches, start=1):
        candidate = _branch_candidate(state, outcome)
        label = _short_candidate_line(state, candidate) if candidate is not None else theme.paint(
            theme.ident(outcome.candidate_id), theme.MUTED)
        body.append(
            "  " + theme.paint(theme.index(position), theme.ACCENT) + "  " + label
        )
        body.extend(theme.tree([
            ("parent", theme.ident(outcome.source_state_id) + _parent_note(state, outcome)),
            ("hypothesis", theme.paint(
                f"y = {theme.num(outcome.hypothetical_value)}", theme.WARN)
                + (theme.paint(f" {unit}", theme.MUTED) if unit else "")),
            ("projected", theme.ident(outcome.projected_state_id)),
            ("evidence", theme.paint("NOT ADMITTED", theme.WARN)),
        ], label_width=12))
        body.append("")

    body.append(theme.paint("These are analyses, not alternative histories.", theme.WARN))
    body.append(theme.paint(
        "No branch has been admitted as evidence and none can be applied.", theme.MUTED))
    body.append("")
    return theme.panel(
        "counterfactual branches", body,
        right=f"{len(state.branches)} hypothetical · not evidence",
        tone=theme.WARN, double=True,
    )


def format_branch(state: WorkbenchState, outcome: CounterfactualOutcome, position: int) -> str:
    """One retained branch, re-inspected. Reads only what the branch
    already carries plus what `materials` computes AT the projected
    state -- `WorkbenchState.information_value_estimate` already accepts
    that state override, so nothing is recomputed here and no new
    mathematics is introduced."""
    candidate = _branch_candidate(state, outcome)
    unit = _unit_for(state)

    body: List[str] = [
        "",
        *theme.lineage([
            ("real state", theme.ident(outcome.source_state_id) + _parent_note(state, outcome)),
            ("hypothetical", theme.paint(f"y = {theme.num(outcome.hypothetical_value)}", theme.WARN)
             + (theme.paint(f" {unit}", theme.MUTED) if unit else "")),
            ("projected", theme.ident(outcome.projected_state_id)),
        ]),
        "",
    ]
    if candidate is not None:
        body.append(theme.kv("candidate", _candidate_line(state, candidate)))
    body.append(theme.kv("candidate_id", theme.ident(outcome.candidate_id)))
    body.append(theme.kv("model_state_key", theme.ident(outcome.model_state_key)))
    body.append("")

    body.append(theme.divider("readout · projected"))
    body.append("")
    if candidate is not None:
        body.extend(_readout_rows(
            state, candidate, outcome.prediction_after, unit,
            at_state=outcome.projected_state, delta=outcome.delta,
        ))
    else:
        body.append(theme.kv("prediction", theme.quantity(outcome.prediction_after.predicted_value, unit)))
        body.append(theme.kv("uncertainty", theme.quantity(outcome.prediction_after.uncertainty)))
    body.append("")

    body.append(theme.divider("provenance"))
    body.append("")
    body.append(theme.kv("basis", theme.badge("hypothetical", theme.WARN)
                         + theme.paint("   a projection, never an observation", theme.MUTED)))
    body.append(theme.kv("admitted", theme.badge("no", theme.WARN)
                         + theme.paint("   nothing was written to the evidence pool", theme.MUTED)))
    body.append(theme.kv("real state", theme.ident(state.session.state.id)))
    body.append("")
    body.append(theme.paint("HYPOTHETICAL", theme.WARN))
    body.append(theme.paint("NOT ADMITTED AS EVIDENCE", theme.WARN))
    body.append(theme.paint(
        "This state was projected from a hypothesis. It is not real history,", theme.MUTED))
    body.append(theme.paint(
        "it validates nothing, and the real session is unchanged.", theme.MUTED))
    body.append("")
    return theme.panel(
        "counterfactual branch", body,
        right=f"branch {theme.index(position)} · not evidence",
        tone=theme.WARN, double=True,
    )


# -- PHASE 90: the state-space timeline -------------------------------------------------------------
#
# Chronological order comes from `ExperimentSession.state_history`, which is
# the authoritative record: `experiment.session.trajectory_of` ->
# `materials.trajectory.make_model_state_trajectory` VERIFIES that order is
# consistent with a real `update()` chain (each successor's sample set for a
# cell is a superset of its predecessor's) and raises otherwise. So list
# order here is not an assumption -- it is a checked property of the chain.
# Everything else is read off objects that already exist: the admitted
# assessment (matched by `PredictionAssessment.state_id`), the decision
# computed at that state, and the branches whose `source_state_id` names it.


def _state_candidate(state: WorkbenchState, assessment: Optional[PredictionAssessment]) -> Optional[ActionCandidate]:
    """The candidate a state's own transition concerned, falling back to
    whatever is selected. Never guessed from position."""
    if assessment is not None:
        found = next((c for c in state.list_candidates() if c.id == assessment.candidate_id), None)
        if found is not None:
            return found
    return state.selected_candidate


def _decision_summary(state: WorkbenchState, model_state: ModelState) -> str:
    """What the policy recommended at this state, or an explicit absence.
    Reads the retained `OptimizationResult`; never recomputes one."""
    decision = state.decision_at(model_state.id)
    if decision is None:
        return theme.paint("NONE", theme.MUTED) + theme.paint(
            "   no decision was computed at this state", theme.MUTED)
    chosen = [o for o in decision.optimizations if o.status == "SELECTED"]
    if not chosen:
        return theme.paint("no candidate was selectable", theme.WARN)
    candidate = next((c for c in state.list_candidates() if c.id == chosen[0].candidate_id), None)
    if candidate is None:
        return theme.ident(chosen[0].candidate_id)
    return (theme.paint(theme.index(_display_index(state, candidate)), theme.ACCENT) + "  "
            + _short_candidate_line(state, candidate))


def format_timeline(state: WorkbenchState) -> str:
    """The real trajectory, in order, with hypothetical branches shown as
    explicit SIDE projections -- never as steps in the chain. A branch
    row always says HYPOTHETICAL and never occupies a state slot."""
    history = state.session.state_history
    unit = _unit_for(state)
    current_id = state.session.state.id

    body: List[str] = [""]
    for index, model_state in enumerate(history):
        assessment = state.assessment_for_transition(
            history[index - 1].id) if index > 0 else None
        candidate = _state_candidate(state, assessment)
        marker = (theme.paint("  " + theme.ARROW + " CURRENT", theme.ACCENT)
                  if model_state.id == current_id else "")
        body.append(
            theme.paint(f"S{index}", theme.TITLE) + "  "
            + theme.ident(model_state.id) + marker
        )

        rows: List[Tuple[str, str]] = []
        if assessment is not None:
            rows.append(("observation", theme.quantity(assessment.observed_value, unit)))
            rows.append(("residual", theme.quantity(assessment.residual, unit, signed=True)))
        if candidate is not None:
            prediction = state.prediction_at(candidate, model_state)
            rows.append(("samples", theme.paint(str(prediction.sample_count), theme.VALUE)))
            rows.append(("prediction", theme.quantity(prediction.predicted_value, unit)))
        rows.append(("decision", _decision_summary(state, model_state)))
        body.extend(theme.tree(rows, label_width=12))

        projections = state.branches_from(model_state.id)
        if projections:
            # a deliberate visual break: these are side shoots off this state,
            # not further children of the readout tree above and not steps in
            # the chain below, so they never reuse that tree's last-child glyph.
            body.append("")
            body.append("      " + theme.paint("side projections · not in this chain", theme.MUTED))
        for offset, branch in enumerate(projections):
            position = state.branches.index(branch) + 1
            stem = theme.TREE_END if offset == len(projections) - 1 else theme.TREE_MID
            body.append(
                "      " + theme.paint(stem + " HYPOTHETICAL", theme.WARN) + "  "
                + theme.paint(f"branch {theme.index(position)}", theme.WARN) + "  "
                + theme.ident(branch.projected_state_id)
            )
            body.append(
                "        " + theme.paint(
                    f"y = {theme.num(branch.hypothetical_value)}", theme.WARN)
                + (theme.paint(f" {unit}", theme.MUTED) if unit else "")
                + theme.paint("   NOT ADMITTED", theme.WARN)
            )

        if index < len(history) - 1:
            body.append("")
            body.append("    " + theme.paint("│", theme.STRUCTURE))
            body.append("    " + theme.paint("▼  REAL", theme.ACCENT))
        body.append("")

    body.append(theme.divider("legend"))
    body.append("")
    body.append(theme.paint("  S<n> is a display index. Identity is the state hash beside it.", theme.MUTED))
    body.append(theme.paint("  A branch is a side projection, never a step in this chain.", theme.MUTED))
    body.append("")
    return theme.panel(
        "state timeline", body,
        right=f"{len(history)} real state(s) · {len(state.branches)} branch(es)",
    )


def format_timeline_state(state: WorkbenchState, index: int) -> str:
    """One real state from the timeline, in the same vocabulary `inspect`
    uses. PHASE 90 sec.7 -- where a transition carries an assessment, the
    prediction -> observation -> residual -> successor chain is shown as
    a chain, because that is what the assessment already records."""
    history = state.session.state_history
    model_state = history[index]
    unit = _unit_for(state)
    incoming = state.assessment_for_transition(history[index - 1].id) if index > 0 else None
    outgoing = state.assessment_for_transition(model_state.id)
    candidate = _state_candidate(state, incoming if incoming is not None else outgoing)
    is_current = model_state.id == state.session.state.id

    body: List[str] = [
        "",
        theme.kv("state", theme.paint(f"S{index}", theme.TITLE)
                 + theme.paint("   display index only", theme.MUTED)),
        theme.kv("basis", theme.badge("real", theme.ACCENT)
                 + theme.paint("   admitted evidence, not a projection", theme.MUTED)),
        theme.kv("position", theme.paint(
            "CURRENT" if is_current else "HISTORICAL",
            theme.ACCENT if is_current else theme.MUTED)),
        "",
        theme.divider("identity"),
        "",
        theme.kv("state id", theme.ident(model_state.id, size=24)),
    ]
    if candidate is not None:
        body.append(theme.kv("candidate", _candidate_line(state, candidate)))
        body.append(theme.kv("candidate_id", theme.ident(candidate.id, size=24)))
    body.append("")

    body.append(theme.divider("computed state"))
    body.append("")
    if candidate is None:
        body.append(theme.paint("No candidate is associated with this state.", theme.WARN))
        body.append(theme.paint("Select one to read a prediction from it.", theme.MUTED))
    else:
        prediction = state.prediction_at(candidate, model_state)
        estimate = state.information_value_estimate(candidate, model_state)
        body.append(theme.kv("samples", theme.paint(str(prediction.sample_count), theme.VALUE)))
        body.append(theme.kv("prediction", theme.quantity(prediction.predicted_value, unit)))
        body.append(theme.kv("uncertainty", theme.quantity(prediction.uncertainty)))
        body.append(theme.kv("information", theme.paint(
            estimate.estimate_status, theme.WARN if estimate.estimate is None else theme.VALUE)))
    body.append("")

    body.append(theme.divider("incoming transition"))
    body.append("")
    if incoming is None:
        body.append(theme.kv("observation", theme.paint("NONE", theme.MUTED)))
        body.append(theme.kv("", theme.paint(
            "this state was not reached by an admitted observation", theme.MUTED)))
    else:
        body.extend(theme.lineage([
            ("prediction", theme.quantity(incoming.predicted_value, unit)),
            ("observation", theme.quantity(incoming.observed_value, unit)),
            ("residual", theme.quantity(incoming.residual, unit, signed=True)),
            ("this state", theme.ident(model_state.id)),
        ]))
        body.append(theme.kv("abs residual", theme.quantity(incoming.absolute_residual, unit)))
        body.append(theme.kv("from state", theme.ident(history[index - 1].id)))
    body.append("")

    body.append(theme.divider("decision at this state"))
    body.append("")
    body.append(theme.kv("recommended", _decision_summary(state, model_state)))
    body.append(theme.kv("", theme.paint("a computed recommendation, not a conclusion", theme.MUTED)))
    body.append("")

    branches = state.branches_from(model_state.id)
    body.append(theme.divider("branches from this state"))
    body.append("")
    if not branches:
        body.append(theme.paint("None. Nothing was projected from this state.", theme.MUTED))
    else:
        for branch in branches:
            position = state.branches.index(branch) + 1
            body.append(
                "  " + theme.paint(f"branch {theme.index(position)}".upper(), theme.WARN) + "  "
                + theme.paint(f"y = {theme.num(branch.hypothetical_value)}", theme.WARN)
                + (theme.paint(f" {unit}", theme.MUTED) if unit else "")
                + theme.paint("   NOT ADMITTED", theme.WARN)
            )
    body.append("")
    return theme.panel(
        "timeline state", body,
        right=f"S{index} · {'current' if is_current else 'historical'}",
    )


# -- PHASE 96: criterion evaluation -----------------------------------------------------------------
#
# The one comparison the materials layer defines: a candidate cell against
# a DECLARED Criterion -- (property, operator, target, context) supplied by
# the caller, never inferred from another cell. Phase 95 established this
# is the only legitimate reference relation the system has.
#
# Two substrate facts this view must state rather than blur:
#
#   * `evaluate_program` reads ADMITTED EVIDENCE in the EvidencePool. It
#     takes no ModelState anywhere in its signature. So these verdicts are
#     about admitted evidence, NOT about the ModelState predictions that
#     `predict`, `state` and `timeline` show.
#   * OBSERVED and PREDICTED are answered separately by the materials
#     layer and, in its own words, never combined. They are rendered as
#     two independent columns and never reduced to one verdict.
#
# The `predicted` column concerns DerivedValues in the pool -- a different
# thing again from `ExperimentSession.predict`. The view says so.

_CRITERION_TONE = {
    "PASS": theme.OK,
    "FAIL": theme.ERR,
    "CONFLICTING_EVIDENCE": theme.WARN,
    "INSUFFICIENT_EVIDENCE": theme.MUTED,
    "INCOMPARABLE": theme.WARN,
}


def _criterion_for(state: WorkbenchState, candidate: ActionCandidate) -> Optional[Criterion]:
    """The declared criterion whose property and context are this
    candidate's own. Matched on the candidate's declared fields -- the
    workbench never performs context resolution itself; that is
    `evaluate_program`'s job and this only finds which declared
    criterion the candidate corresponds to."""
    for criterion in state.declared_criteria():
        if (criterion.property == candidate.property
                and dict(criterion.context) == dict(candidate.target_context)):
            return criterion
    return None


def _verdict_for(
    decision: ProgramDecision, candidate: ActionCandidate, criterion: Criterion,
):
    """The PropertyDecision the materials layer produced for this
    (formulation, criterion) pair, or None. Matched by the formulation's
    own identity and the criterion's own declared fields."""
    for formulation_decision in decision.formulations:
        if formulation_decision.formulation.id != candidate.formulation.id:
            continue
        for property_decision in formulation_decision.properties:
            if (property_decision.criterion.property == criterion.property
                    and dict(property_decision.criterion.context) == dict(criterion.context)
                    and property_decision.criterion.operator == criterion.operator
                    and property_decision.criterion.target == criterion.target):
                return property_decision
    return None


def _criterion_header(state: WorkbenchState, criterion: Criterion, unit: str) -> List[str]:
    return [
        theme.kv("property", theme.paint(criterion.property, theme.VALUE)),
        theme.kv("operator", theme.paint(criterion.operator, theme.VALUE)),
        theme.kv("target", theme.quantity(criterion.target, unit)),
        theme.kv("context", theme.context(criterion.context)),
        theme.kv("reference", theme.badge("declared", theme.ACCENT)
                 + theme.paint("   engineering data, not another candidate", theme.MUTED)),
    ]


def format_criterion(state: WorkbenchState, candidates: Sequence[ActionCandidate]) -> str:
    """Candidate cells evaluated against their declared criteria. An
    evaluation table, never a leaderboard: registry order is preserved,
    nothing is ranked, no verdict is compared with another, and observed
    and predicted stay in separate columns."""
    declared = state.declared_criteria()
    if not declared:
        return theme.notice(
            "no criterion declared",
            "this scenario declares no criterion to evaluate against.",
            hint="a criterion is scenario configuration -- see examples/*.json",
        )
    decision, evidence_version = state.evaluate_criteria()
    unit = _unit_for(state)

    body: List[str] = ["", theme.divider("declared reference"), ""]
    first = declared[0]
    body.append(theme.kv("property", theme.paint(first.property, theme.VALUE)))
    body.append(theme.kv("operator", theme.paint(first.operator, theme.VALUE)))
    body.append(theme.kv("target", theme.quantity(first.target, unit)))
    body.append(theme.kv("contexts", theme.paint(str(len(declared)), theme.VALUE)
                         + theme.paint("   one criterion per declared context", theme.MUTED)))
    body.append(theme.kv("reference", theme.badge("declared", theme.ACCENT)
                         + theme.paint("   engineering data, not another candidate", theme.MUTED)))
    body.append("")
    body.append(theme.kv("evidence", theme.ident(evidence_version, size=24)))
    body.append(theme.kv("", theme.paint(
        "the admitted evidence these verdicts were computed from", theme.MUTED)))
    body.append("")
    body.append(theme.paint("  Verdicts concern ADMITTED EVIDENCE, not the model state that", theme.MUTED))
    body.append(theme.paint("  `predict` and `state` report. Observed and predicted are", theme.MUTED))
    body.append(theme.paint("  answered separately by the materials layer and never combined.", theme.MUTED))
    body.append("")

    body.append(theme.divider("evaluation"))
    body.append("")
    # a verdict is the ANSWER, not a descriptive label, so it is never
    # placed in a column narrow enough to clip it. Two rows per cell --
    # the same shape `state` uses -- keeps every status readable at 64.
    for candidate in candidates:
        position = _display_index(state, candidate)
        criterion = _criterion_for(state, candidate)
        body.append(
            theme.paint(theme.index(position), theme.ACCENT) + "  "
            + _short_candidate_line(state, candidate)
        )
        if criterion is None:
            body.extend(theme.tree(
                [("criterion", theme.paint("NONE DECLARED", theme.WARN))], label_width=12))
            body.append("")
            continue
        verdict = _verdict_for(decision, candidate, criterion)
        if verdict is None:
            body.extend(theme.tree(
                [("evaluated", theme.paint("NO", theme.WARN))], label_width=12))
            body.append("")
            continue
        body.extend(theme.tree([
            ("observed", theme.paint(
                verdict.observed_status,
                _CRITERION_TONE.get(verdict.observed_status, theme.VALUE))),
            ("predicted", theme.paint(
                verdict.predicted_status,
                _CRITERION_TONE.get(verdict.predicted_status, theme.VALUE))),
        ], label_width=12))
        body.append("")

    body.append(theme.paint("  Each row is one cell against the declared target.", theme.MUTED))
    body.append(theme.paint("  No row is compared with any other.", theme.MUTED))
    body.append("")
    return theme.panel(
        "criterion", body,
        right=f"{len(candidates)} cell(s) · declared reference",
    )


def format_criterion_detail(state: WorkbenchState, candidate: ActionCandidate) -> str:
    """One candidate against its declared criterion, with the two
    verdicts kept apart and the comparison group the materials layer
    actually matched, so an INCOMPARABLE result can be understood."""
    criterion = _criterion_for(state, candidate)
    if criterion is None:
        return theme.notice(
            "no declared criterion",
            "this scenario declares no criterion for this candidate's property and context.",
            hint="criterion   lists every declared criterion",
        )
    decision, evidence_version = state.evaluate_criteria()
    verdict = _verdict_for(decision, candidate, criterion)
    unit = _unit_for(state)

    body: List[str] = [
        "",
        theme.kv("candidate", _candidate_line(state, candidate)),
        theme.kv("candidate_id", theme.ident(candidate.id, size=24)),
        "",
        theme.divider("declared reference"),
        "",
        *_criterion_header(state, criterion, unit),
        "",
        theme.divider("verdict"),
        "",
    ]
    if verdict is None:
        body.append(theme.paint("This candidate was not evaluated.", theme.WARN))
        body.append(theme.paint(
            "Its formulation is not in the declared programme query.", theme.MUTED))
    else:
        body.append(theme.kv("observed", theme.paint(
            verdict.observed_status, _CRITERION_TONE.get(verdict.observed_status, theme.VALUE))))
        body.append(theme.kv("", theme.paint(_criterion_reason(verdict.observed_status), theme.MUTED)))
        body.append(theme.kv("predicted", theme.paint(
            verdict.predicted_status, _CRITERION_TONE.get(verdict.predicted_status, theme.VALUE))))
        body.append(theme.kv("", theme.paint(_criterion_reason(verdict.predicted_status), theme.MUTED)))
        body.append("")
        body.append(theme.paint(
            "  These two are answered independently and are never combined", theme.MUTED))
        body.append(theme.paint(
            "  into a single verdict.", theme.MUTED))
        body.append("")
        body.append(theme.divider("matched evidence"))
        body.append("")
        group = verdict.observed_group
        if group is None:
            body.append(theme.kv("observed group", theme.paint("NONE", theme.WARN)))
            body.append(theme.kv("", theme.paint(
                "no admitted evidence matched this criterion's context", theme.MUTED)))
            if verdict.observed_status == "INCOMPARABLE" and criterion.context:
                # PHASE 98 -- admitted evidence now carries the candidate's
                # declared context, so INCOMPARABLE no longer means the
                # context was simply never recorded. The materials layer
                # returns it for two distinct reasons and does not say which,
                # so neither does this.
                body.append("")
                body.append(theme.kv("cause", theme.paint(
                    "no comparison group selected uniquely", theme.WARN)))
                body.append(theme.kv("", theme.paint(
                    "either none matched this context, or more than one did", theme.MUTED)))
        else:
            body.append(theme.kv("context", theme.context(group.context)))
            body.append(theme.kv("values", theme.paint(
                ", ".join(theme.num(v) for v in group.values), theme.VALUE)))
    body.append("")
    body.append(theme.kv("evidence", theme.ident(evidence_version, size=24)))
    body.append("")
    return theme.panel(
        "criterion · candidate", body,
        right="declared reference",
    )


def _criterion_reason(status: str) -> str:
    """The materials layer's own meaning for each status. No status is
    reworded into a judgement about the material."""
    return {
        "PASS": "the matched evidence satisfies the target",
        "FAIL": "the matched evidence does not satisfy the target",
        "CONFLICTING_EVIDENCE": "the matched evidence disagrees with itself",
        "INSUFFICIENT_EVIDENCE": "no evidence on this side exists for this property",
        "INCOMPARABLE": "no single comparison group matched this context",
    }.get(status, "")


# -- PHASE 93: whole-state enumeration ------------------------------------------------------------
#
# The CELL projection, as opposed to `timeline`'s temporal one and
# `thread`'s single-candidate one. It answers exactly one question:
# what does this ModelState contain for every candidate cell?
#
# It is an ENUMERATION, never an interpretation. Phase 92 established
# that different candidate cells are independently predicted quantities
# with no defined scientific relation between them, so this view
# computes nothing spanning two rows: no difference, no ordering by
# value, no aggregate, no ranking. Each row is a self-contained reading
# of one cell, and rows appear in the candidate registry's own
# id-sorted order -- the same order `candidates`, `select <n>`,
# `decide`, `timeline` and `thread` already use.
#
# Utility is deliberately absent. Phase 92 classified it as a
# decision-policy quantity, not a material one; placing it beside a
# prediction here would invite exactly the reading this view exists to
# avoid. It stays in `decide` and `explain`, where its policy basis is
# disclosed.


def format_state(state: WorkbenchState, index: int) -> str:
    """Every candidate cell of one real state, side by side. Lossless
    with respect to the registry: every candidate appears exactly once,
    including those with no evidence at all, because a search space is
    not the same thing as the evidence gathered in it."""
    history = state.session.state_history
    model_state = history[index]
    unit = _unit_for(state)
    is_current = model_state.id == state.session.state.id
    candidates = state.list_candidates()
    occupied = sum(
        1 for c in candidates if state.prediction_at(c, model_state).sample_count > 0)

    body: List[str] = [
        "",
        theme.kv("state", theme.paint(f"S{index}", theme.TITLE)
                 + theme.paint("   display index only", theme.MUTED)),
        theme.kv("state id", theme.ident(model_state.id, size=24)),
        theme.kv("basis", theme.badge("real", theme.ACCENT)
                 + theme.paint("   admitted evidence, not a projection", theme.MUTED)),
        theme.kv("position", theme.paint(
            "CURRENT" if is_current else "HISTORICAL",
            theme.ACCENT if is_current else theme.MUTED)),
        "",
        theme.kv("candidate cells", theme.paint(str(len(candidates)), theme.VALUE)
                 + theme.paint("   the complete registry", theme.MUTED)),
        theme.kv("cells with evidence", theme.paint(str(occupied), theme.VALUE)
                 + theme.paint("   the rest hold no sample at this state", theme.MUTED)),
        "",
        theme.paint("  Each cell is read independently. This view states no relation", theme.MUTED),
        theme.paint("  between any two of them.", theme.MUTED),
        "",
        theme.divider("cells"),
        "",
    ]

    for position, candidate in enumerate(candidates, start=1):
        prediction = state.prediction_at(candidate, model_state)
        estimate = state.information_value_estimate(candidate, model_state)
        body.append(
            theme.paint(theme.index(position), theme.ACCENT) + "  "
            + _candidate_line(state, candidate).split("  ", 1)[-1]
        )
        body.extend(theme.tree([
            ("prediction", theme.quantity(prediction.predicted_value, unit)),
            ("uncertainty", theme.quantity(prediction.uncertainty)),
            ("samples", theme.paint(str(prediction.sample_count), theme.VALUE)),
            ("information", theme.paint(
                estimate.estimate_status,
                theme.WARN if estimate.estimate is None else theme.VALUE)),
        ], label_width=12))
        body.append("")

    return theme.panel(
        "state", body,
        right=f"S{index} · {len(candidates)} candidate cell(s)",
    )


# -- PHASE 91: candidate evidence threads -------------------------------------------------------------
#
# A thread is a PROJECTION of the global real-state trajectory, not a
# second history. The state ids are the global `ModelState.id`s; no
# candidate-local state identity is invented, because none exists.
#
# The whole derivation rests on one existing fact: the assessment that
# advanced the session out of a state carries its own `candidate_id`. If
# it matches the thread's candidate, that transition is this candidate's
# evidence; if it does not, the global state advanced and this
# candidate's evidence did not. Those are different statements and the
# view makes them differently.


def _thread_rows(
    state: WorkbenchState, candidate: ActionCandidate, index: int, unit: str,
) -> List[Tuple[str, str]]:
    """One global state, read through one candidate. An observation or a
    residual appears ONLY when the transition into this state belonged to
    this candidate."""
    history = state.session.state_history
    model_state = history[index]
    rows: List[Tuple[str, str]] = []

    if index > 0:
        assessment = state.assessment_for_transition(history[index - 1].id)
        if assessment is not None and assessment.candidate_id == candidate.id:
            rows.append(("observation", theme.quantity(assessment.observed_value, unit)))
            rows.append(("residual", theme.quantity(assessment.residual, unit, signed=True)))
        else:
            # the global chain moved; this candidate's evidence did not. Naming
            # the candidate that WAS observed keeps the two facts separate.
            other = None
            if assessment is not None:
                other = next(
                    (c for c in state.list_candidates() if c.id == assessment.candidate_id), None)
            rows.append(("global state", theme.paint("ADVANCED", theme.VALUE)))
            rows.append((
                "this candidate",
                theme.paint("EVIDENCE UNCHANGED", theme.WARN)
                + (theme.paint(f"   {_short_candidate_line(state, other)} was observed", theme.MUTED)
                   if other is not None else "")))

    prediction = state.prediction_at(candidate, model_state)
    rows.append(("samples", theme.paint(str(prediction.sample_count), theme.VALUE)))
    rows.append(("prediction", theme.quantity(prediction.predicted_value, unit)))

    decision = state.decision_at(model_state.id)
    if decision is not None:
        chosen = [o for o in decision.optimizations if o.status == "SELECTED"]
        recommended_id = chosen[0].candidate_id if chosen else None
        if recommended_id == candidate.id:
            rows.append(("decision", theme.paint("RECOMMENDED THIS CANDIDATE", theme.ACCENT)))
        elif recommended_id is None:
            rows.append(("decision", theme.paint("no candidate was selectable", theme.WARN)))
        else:
            other = next(
                (c for c in state.list_candidates() if c.id == recommended_id), None)
            rows.append((
                "decision",
                theme.paint("OTHER CANDIDATE", theme.MUTED)
                + (theme.paint(f"   {_short_candidate_line(state, other)}", theme.MUTED)
                   if other is not None else "")))
    return rows


def format_thread(state: WorkbenchState, candidate: ActionCandidate) -> str:
    """One candidate's projection through the global real trajectory.
    Every global state is represented -- a thread is a projection of that
    history, not a list of this candidate's observations -- but a state
    that did not change this candidate's evidence says so."""
    history = state.session.state_history
    unit = _unit_for(state)
    current_id = state.session.state.id
    observations = state.assessments_for(candidate)
    with_evidence = sum(
        1 for s in history if state.prediction_at(candidate, s).sample_count > 0)
    current = state.prediction_at(candidate, state.session.state)
    information = state.information_value_estimate(candidate, state.session.state)

    body: List[str] = [
        "",
        theme.kv("candidate", _candidate_line(state, candidate)),
        theme.kv("property", theme.paint(candidate.property, theme.VALUE)),
        theme.kv("context", theme.context(candidate.target_context)),
        theme.kv("candidate_id", theme.ident(candidate.id, size=24)),
        "",
        theme.paint("  A projection of the global real-state history.", theme.MUTED),
        theme.paint("  The state identities below are the global ones.", theme.MUTED),
        "",
        theme.divider("current"),
        "",
        theme.kv("samples", theme.paint(str(current.sample_count), theme.VALUE)),
        theme.kv("prediction", theme.quantity(current.predicted_value, unit)),
        theme.kv("uncertainty", theme.quantity(current.uncertainty)),
        theme.kv("information", theme.paint(
            information.estimate_status,
            theme.WARN if information.estimate is None else theme.VALUE)),
        theme.kv("observations", theme.paint(str(len(observations)), theme.VALUE)
                 + theme.paint("   admitted for this candidate", theme.MUTED)),
        theme.kv("global states", theme.paint(str(len(history)), theme.VALUE)),
        theme.kv("with evidence", theme.paint(str(with_evidence), theme.VALUE)
                 + theme.paint("   states where this candidate has any sample", theme.MUTED)),
        "",
        theme.divider("projection"),
        "",
    ]

    for index, model_state in enumerate(history):
        marker = (theme.paint("  " + theme.ARROW + " CURRENT", theme.ACCENT)
                  if model_state.id == current_id else "")
        body.append(
            theme.paint(f"S{index}", theme.TITLE) + "  "
            + theme.ident(model_state.id) + marker
        )
        body.extend(theme.tree(_thread_rows(state, candidate, index, unit), label_width=14))

        projections = [
            b for b in state.branches_from(model_state.id) if b.candidate_id == candidate.id
        ]
        if projections:
            body.append("")
            body.append("      " + theme.paint("side projections · not in this chain", theme.MUTED))
        for offset, branch in enumerate(projections):
            position = state.branches.index(branch) + 1
            stem = theme.TREE_END if offset == len(projections) - 1 else theme.TREE_MID
            body.append(
                "      " + theme.paint(stem + " HYPOTHETICAL", theme.WARN) + "  "
                + theme.paint(f"branch {theme.index(position)}", theme.WARN) + "  "
                + theme.ident(branch.projected_state_id)
            )
            body.append(
                "        " + theme.paint(
                    f"y = {theme.num(branch.hypothetical_value)}", theme.WARN)
                + (theme.paint(f" {unit}", theme.MUTED) if unit else "")
                + theme.paint("   NOT ADMITTED", theme.WARN)
            )

        if index < len(history) - 1:
            body.append("")
            body.append("    " + theme.paint("│", theme.STRUCTURE))
            body.append("    " + theme.paint("▼  REAL", theme.ACCENT))
        body.append("")

    body.append(theme.divider("legend"))
    body.append("")
    body.append(theme.paint(
        "  CURRENT marks the current GLOBAL state. A thread has no current", theme.MUTED))
    body.append(theme.paint(
        "  state of its own -- it is one reading of the chain above.", theme.MUTED))
    body.append("")
    return theme.panel(
        "candidate thread", body,
        right=f"{len(observations)} observation(s) · {len(history)} global state(s)",
    )


# -- PHASE 89: comparison operands ---------------------------------------------------------------------
#
# An operand is NEVER a new object. It is one of two things that already
# exist, each of which can yield a `Prediction` for a candidate:
#
#   a real `ModelState`        from `session.state_history`
#   a `CounterfactualOutcome`  from the Phase 88 branch registry
#
# `materials.trajectory.compare_predictions` then does the comparing, and
# `materials.diagnostics.StateTransitionDiagnostic` supplies the
# observation and signed residual for an adjacent real pair. No
# `Comparison` domain object is introduced, because none is missing.


class _Operand(NamedTuple):
    """A presentation-only handle on an EXISTING object. Carries no
    quantity of its own -- `state` is the real or projected `ModelState`
    that already existed, `branch` is the retained outcome when this
    operand is hypothetical, and `label`/`identity` are display strings
    derived from ids that already existed."""

    kind: str          # "real" | "hypothetical"
    label: str
    state: ModelState
    branch: Optional[CounterfactualOutcome]
    candidate: Optional[ActionCandidate]


def _real_operand(state: WorkbenchState, model_state: ModelState, position: int) -> _Operand:
    return _Operand(
        kind="real", label=f"state {theme.index(position)}",
        state=model_state, branch=None, candidate=state.selected_candidate,
    )


def _branch_operand(state: WorkbenchState, outcome: CounterfactualOutcome, position: int) -> _Operand:
    return _Operand(
        kind="hypothetical", label=f"branch {theme.index(position)}",
        state=outcome.projected_state, branch=outcome,
        candidate=_branch_candidate(state, outcome),
    )


def _operand_badge(operand: _Operand) -> str:
    if operand.kind == "real":
        return theme.badge("real", theme.ACCENT)
    return theme.badge("hypothetical", theme.WARN)


def _resolve_operand(state: WorkbenchState, tokens: List[str]) -> Union[_Operand, str]:
    """Consumes `state <n>` or `branch <n>` from the front of `tokens`.
    Returns the operand, or an already-rendered notice explaining exactly
    what was expected. Deliberately reuses the two selector words the
    workbench already uses -- no second selector grammar is introduced."""
    kind = tokens[0].lower()
    if len(tokens) < 2:
        return theme.notice(
            "incomplete operand", f"{kind} requires a number.",
            hint="compare state <n>   ·   compare branch <n>",
        )
    try:
        position = int(tokens[1])
    except ValueError:
        return theme.notice(
            "unreadable operand", f"{tokens[1]!r} is not a number.",
            hint="compare state <n>   ·   compare branch <n>",
        )
    if kind == "branch":
        outcome = state.branch_at(position)
        if outcome is None:
            return theme.notice(
                "no such branch", f"branch {position} is not in this session's registry.",
                hint=f"branch <1-{len(state.branches)}>" if state.branches else "explore <value>   first",
            )
        return _branch_operand(state, outcome, position)
    history = state.session.state_history
    if not 1 <= position <= len(history):
        return theme.notice(
            "no such state", f"state {position} is not in this session's real history.",
            hint=f"state <1-{len(history)}>",
        )
    return _real_operand(state, history[position - 1], position)


def _comparison_rows(
    state: WorkbenchState, left: _Operand, right: _Operand, candidate: ActionCandidate,
    delta: PredictionDelta, unit: str,
) -> List[str]:
    """The shared readout. Every row is a field that already exists on
    `Prediction`/`PredictionDelta`/`InformationValueEstimate`; nothing is
    synthesised to fill the table, and an undetermined side stays
    UNDETERMINED rather than becoming a number."""
    left_prediction = state.prediction_at(candidate, left.state)
    right_prediction = state.prediction_at(candidate, right.state)
    left_information = state.information_value_estimate(candidate, left.state)
    right_information = state.information_value_estimate(candidate, right.state)

    def row(label: str, a: str, b: str) -> str:
        """FROM and TO are two independent cells, separated by the same
        transition glyph every other before/after readout in this console
        uses. The separator is structural, not decorative: an
        UNDETERMINED on one side must never read as qualifying a numeral
        on the other."""
        return theme.kv(label, theme.transition(a, b, width_before=22))

    rows = [
        row("samples",
            theme.paint(str(left_prediction.sample_count), theme.VALUE),
            theme.paint(str(right_prediction.sample_count), theme.VALUE)),
        row("prediction",
            theme.quantity(left_prediction.predicted_value, unit),
            theme.quantity(right_prediction.predicted_value, unit)),
        row("uncertainty",
            theme.quantity(left_prediction.uncertainty),
            theme.quantity(right_prediction.uncertainty)),
        row("information",
            theme.paint(left_information.estimate_status,
                        theme.WARN if left_information.estimate is None else theme.VALUE),
            theme.paint(right_information.estimate_status,
                        theme.WARN if right_information.estimate is None else theme.VALUE)),
        "",
        theme.divider("change"),
        "",
        # a delta gets its own full-width row so an undetermined one can be
        # spelled out rather than clipped into a column.
        theme.kv("prediction", theme.quantity(
            delta.delta_predicted_value, unit, signed=True)),
        theme.kv("uncertainty", theme.quantity(
            delta.delta_uncertainty, signed=True)),
    ]
    return rows


def _operand_header(left: _Operand, right: _Operand) -> List[str]:
    return [
        theme.kv("from", theme.pad(_operand_badge(left), 20) + theme.paint(left.label.upper(), theme.MUTED)),
        theme.kv("to", theme.pad(_operand_badge(right), 20) + theme.paint(right.label.upper(), theme.MUTED)),
        theme.kv("state id", theme.pad(theme.ident(left.state.id), 24) + theme.ident(right.state.id)),
    ]


def format_comparison(state: WorkbenchState, left: _Operand, right: _Operand) -> str:
    """One comparison panel for any operand pair. Double-ruled whenever
    EITHER side is hypothetical -- the Phase 88 rule holds: a view that
    shows a projection is never single-ruled."""
    candidate = left.candidate if left.candidate is not None else right.candidate
    if candidate is None:
        return _no_selection_notice()
    if (left.branch is not None and right.branch is not None
            and left.branch.candidate_id != right.branch.candidate_id):
        return theme.notice(
            "incomparable branches",
            "these two branches project different candidates, so their predictions "
            "are not two readings of one quantity.",
            hint="compare branches that share a candidate   ·   branches   lists them",
        )

    unit = _unit_for(state)
    hypothetical = left.kind == "hypothetical" or right.kind == "hypothetical"
    delta = state.delta_between(
        state.prediction_at(candidate, left.state), state.prediction_at(candidate, right.state))

    body: List[str] = ["", *_operand_header(left, right), ""]
    body.append(theme.kv("candidate", _candidate_line(state, candidate)))
    body.append("")

    for side, operand in (("from", left), ("to", right)):
        if operand.branch is not None:
            body.append(theme.kv(f"{side} hypothesis", theme.paint(
                f"y = {theme.num(operand.branch.hypothetical_value)}", theme.WARN)
                + (theme.paint(f" {unit}", theme.MUTED) if unit else "")))
            body.append(theme.kv(f"{side} parent", theme.ident(operand.branch.source_state_id)))
    if hypothetical:
        body.append("")

    body.append(theme.divider("readout"))
    body.append("")
    # `transition` owns the column width; pre-padding to it as well double-counts
    # it and buys the header a stray space the data rows below do not have.
    body.append(theme.kv("", theme.paint(theme.transition(
        "FROM", "TO", width_before=22), theme.LABEL)))
    body.extend(_comparison_rows(state, left, right, candidate, delta, unit))
    body.append("")

    body.append(theme.divider("evidence"))
    body.append("")
    diagnostic = (
        state.transition_between(candidate, left.state.id, right.state.id)
        if not hypothetical else None
    )
    if hypothetical:
        body.append(theme.kv("admitted", theme.pad(
            theme.badge("no" if left.kind == "hypothetical" else "yes",
                        theme.WARN if left.kind == "hypothetical" else theme.ACCENT), 24)
            + theme.badge("no" if right.kind == "hypothetical" else "yes",
                          theme.WARN if right.kind == "hypothetical" else theme.ACCENT)))
        body.append(theme.kv("observation", theme.paint("NO OBSERVATION", theme.WARN)
                             + theme.paint("   a projection is never an observation", theme.MUTED)))
        body.append(theme.kv("residual", theme.paint(theme.UNDETERMINED, theme.WARN)
                             + theme.paint("   nothing admitted to compare against", theme.MUTED)))
    elif diagnostic is None:
        body.append(theme.kv("observation", theme.paint("NOT AVAILABLE", theme.WARN)))
        body.append(theme.kv("", theme.paint(
            "not one admitted transition apart", theme.MUTED)))
        body.append(theme.kv("residual", theme.paint(theme.UNDETERMINED, theme.WARN)))
    else:
        body.append(theme.kv("observation", theme.quantity(diagnostic.observation_value, unit)))
        body.append(theme.kv("residual", theme.quantity(
            diagnostic.residual_against_previous_prediction, unit, signed=True)))
        body.append(theme.kv("abs residual", theme.quantity(diagnostic.absolute_residual, unit)))
    body.append("")

    if hypothetical:
        body.append(theme.paint("HYPOTHETICAL", theme.WARN))
        body.append(theme.paint("NOT ADMITTED AS EVIDENCE", theme.WARN))
        body.append(theme.paint(
            "One side of this comparison was projected, not observed. Neither side", theme.MUTED))
        body.append(theme.paint(
            "is preferable to the other; this states a computed difference only.", theme.MUTED))
    else:
        body.append(theme.paint(
            "This states a computed difference between two real states.", theme.MUTED))
        body.append(theme.paint(
            "No claim is made about any material.", theme.MUTED))
    body.append("")

    title = "counterfactual comparison" if hypothetical else "state comparison"
    return theme.panel(
        title, body,
        right=("hypothetical · not evidence" if hypothetical else "real · admitted evidence"),
        tone=theme.WARN if hypothetical else theme.ACCENT, double=hypothetical,
    )


def format_decision_comparison(state: WorkbenchState) -> str:
    """Places the two decision objects the session ALREADY holds side by
    side. Neither is recomputed: `previous_decision` and `last_decision`
    are the exact `OptimizationResult`s `decide` produced."""
    previous, current = state.previous_decision, state.last_decision
    if current is None:
        return theme.notice(
            "no decision yet", "nothing has been decided in this session.",
            hint="decide   then   compare decisions", tone=theme.WARN,
        )
    if previous is None:
        return theme.notice(
            "only one decision", "this session has computed one decision, so there is "
            "nothing to compare it against.",
            hint="observe <value>   then   decide   then   compare decisions", tone=theme.WARN,
        )

    def recommended(optimization: OptimizationResult) -> Optional[ActionCandidate]:
        chosen = [o for o in optimization.optimizations if o.status == "SELECTED"]
        if not chosen:
            return None
        return next((c for c in state.list_candidates() if c.id == chosen[0].candidate_id), None)

    def utility_of(optimization: OptimizationResult) -> str:
        chosen = [o for o in optimization.optimizations if o.status == "SELECTED"]
        if not chosen:
            return theme.paint("NOT AVAILABLE", theme.WARN)
        return theme.quantity(chosen[0].utility.utility)

    before, after = recommended(previous), recommended(current)
    body: List[str] = ["", theme.divider("previous decision"), ""]
    body.append(theme.kv("recommended", _candidate_line(state, before) if before is not None
                         else theme.paint("no candidate was selectable", theme.WARN)))
    body.append(theme.kv("utility", utility_of(previous)))
    body.append(theme.kv("computed at", theme.ident(state.previous_decision_state_id)
                         if state.previous_decision_state_id is not None
                         else theme.paint("NOT AVAILABLE", theme.WARN)))
    body.append("")

    body.append(theme.divider("current decision"))
    body.append("")
    body.append(theme.kv("recommended", _candidate_line(state, after) if after is not None
                         else theme.paint("no candidate was selectable", theme.WARN)))
    body.append(theme.kv("utility", utility_of(current)))
    body.append(theme.kv("computed at", theme.ident(state.last_decision_state_id)
                         if state.last_decision_state_id is not None
                         else theme.paint("NOT AVAILABLE", theme.WARN)))
    body.append("")

    body.append(theme.divider("change"))
    body.append("")
    changed = (before.id if before else None) != (after.id if after else None)
    body.append(theme.kv("recommendation", theme.paint(
        "CHANGED" if changed else "UNCHANGED", theme.WARN if changed else theme.VALUE)))
    if changed and before is not None and after is not None:
        body.append(theme.transition(
            theme.truncate(_short_candidate_line(state, before), 22),
            _short_candidate_line(state, after), width_before=24))
    body.append("")

    body.append(theme.divider("basis"))
    body.append("")
    # the basis says what actually happened between the two decisions -- it is
    # never a stock sentence asserting a change that did not occur.
    advanced = (
        state.previous_decision_state_id is not None
        and state.last_decision_state_id is not None
        and state.previous_decision_state_id != state.last_decision_state_id
    )
    if advanced and changed:
        body.append(theme.paint("  The observed evidence changed the computed state, which", theme.VALUE))
        body.append(theme.paint("  changed the subsequent utility landscape and recommendation.", theme.VALUE))
    elif advanced:
        body.append(theme.paint("  The observed evidence changed the computed state. The", theme.VALUE))
        body.append(theme.paint("  recommendation the utility landscape yields is unchanged.", theme.VALUE))
    else:
        body.append(theme.paint("  Both decisions were computed at the same state, so nothing", theme.VALUE))
        body.append(theme.paint("  in the utility landscape could have changed between them.", theme.VALUE))
    body.append(theme.paint("  No scientific claim is made by this comparison.", theme.MUTED))
    body.append("")
    return theme.panel("decision comparison", body, right="computed recommendations")


def format_assessment(
    state: WorkbenchState, candidate: ActionCandidate, predecessor_state_id: str,
    prediction: Prediction, assessment: PredictionAssessment,
) -> str:
    """An observation rendered as a STATE TRANSITION, not a printed
    number. `prediction` is the projection that existed immediately
    before admission; `after` is the one the advanced session reports
    now. Both already exist -- the before/after columns pair them, they
    do not recompute anything."""
    unit = assessment.result.content.get("unit")
    unit = unit if isinstance(unit, str) else ""
    after = state.session.predict(candidate)

    body = [
        "",
        theme.kv("candidate", _candidate_line(state, candidate)),
        theme.kv("context", theme.paint(theme.context(candidate.target_context), theme.VALUE)),
        theme.kv("provenance", theme.paint("externally supplied experimental observation", theme.VALUE)),
        theme.kv("observation", theme.ident(assessment.observation.id)),
        "",
        theme.divider("measurement"),
        "",
        theme.kv("predicted", theme.quantity(prediction.predicted_value, unit)),
        theme.kv("observed", theme.quantity(assessment.observed_value, unit)),
        theme.kv("residual", theme.quantity(assessment.residual, unit, signed=True)),
        theme.kv("abs residual", theme.quantity(assessment.absolute_residual, unit)),
        "",
        theme.divider("state transition"),
        "",
        theme.kv("samples", theme.transition(
            theme.paint(str(prediction.sample_count), theme.VALUE),
            theme.paint(str(after.sample_count), theme.VALUE),
        )),
        theme.kv("prediction", theme.transition(
            theme.quantity(prediction.predicted_value, unit), theme.quantity(after.predicted_value, unit),
        )),
        theme.kv("uncertainty", theme.transition(
            theme.quantity(prediction.uncertainty), theme.quantity(after.uncertainty),
        )),
        theme.kv("state", theme.transition(
            theme.ident(predecessor_state_id), theme.ident(state.session.state.id),
        )),
        "",
        theme.paint("Prior session retained and immutable.", theme.MUTED),
        "",
    ]
    return theme.panel("observation accepted", body, right="external source", tone=theme.OK)


def format_transition(index: int, d: StateTransitionDiagnostic, unit: str = "") -> List[str]:
    """RESEARCH CHRONOLOGY: what was expected, what came back, how far
    off it was, and where the state moved. Same identifiers and the same
    `theme.transition` vocabulary diagnostics uses, so one transition is
    recognisable in both views."""
    header = theme.paint(theme.index(index), theme.ACCENT) + "   " + theme.paint(
        _short_candidate_line_from(d), theme.VALUE)
    observed = (
        theme.paint("no observation for this candidate", theme.MUTED) if d.assessment is None
        else theme.quantity(d.observation_value, unit)
    )
    rows = [
        ("prediction → observation", theme.transition(
            theme.quantity(d.previous_prediction.predicted_value, unit), observed, width_before=18)),
        ("residual", theme.paint("n/a", theme.MUTED) if d.assessment is None
         else theme.quantity(d.residual_against_previous_prediction, unit, signed=True)),
        ("state", theme.transition(
            theme.ident(d.predecessor_state_id), theme.ident(d.successor_state_id), width_before=18)),
    ]
    return [header, *theme.tree(rows, label_width=26)]


def _short_candidate_line_from(d: StateTransitionDiagnostic) -> str:
    """The candidate/context label for a transition, taken from the
    embedded `Prediction` -- which already carries the formulation and
    the target context, so nothing is looked up or re-derived."""
    prediction = d.previous_prediction
    return f"{prediction.formulation.natural_key} {theme.DOT} {theme.context(prediction.context)}"


def format_diagnostic(index: int, d: StateTransitionDiagnostic, unit: str = "") -> List[str]:
    """The full-detail view `diagnostics` uses: every field
    `materials.diagnostics.StateTransitionDiagnostic` carries."""
    header = (
        theme.paint(theme.index(index), theme.ACCENT) + "   "
        + theme.ident(d.predecessor_state_id)
        + theme.paint(f"  {theme.TRANSITION}  ", theme.STRUCTURE)
        + theme.ident(d.successor_state_id)
    )
    rows: List[Tuple[str, str]] = [
        ("candidate_id", theme.ident(d.candidate_id)),
        ("model_state_key", theme.ident(d.model_state_key)),
        ("state_t", theme.ident(d.predecessor_state_id)),
        ("state_t+1", theme.ident(d.successor_state_id)),
        ("samples t", theme.paint(str(d.previous_prediction.sample_count), theme.VALUE)),
        ("samples t+1", theme.paint(str(d.new_prediction.sample_count), theme.VALUE)),
        ("prediction t", theme.quantity(d.previous_prediction.predicted_value, unit)),
        ("uncertainty t", theme.quantity(d.previous_prediction.uncertainty)),
        ("prediction t+1", theme.quantity(d.new_prediction.predicted_value, unit)),
        ("uncertainty t+1", theme.quantity(d.new_prediction.uncertainty)),
        ("Δ prediction", theme.quantity(d.delta_predicted_value, signed=True)),
        ("Δ uncertainty", theme.quantity(d.delta_uncertainty, signed=True)),
    ]
    if d.assessment is None:
        rows.append(("observation", theme.paint("none for this candidate", theme.MUTED)))
    else:
        rows.append(("observation", theme.quantity(d.observation_value, unit)))
        rows.append(("residual", theme.quantity(d.residual_against_previous_prediction, unit, signed=True)))
        rows.append(("abs residual", theme.quantity(d.absolute_residual, unit)))
    return [header, *theme.tree(rows, label_width=16)]


def _format_transition_panel(
    state: WorkbenchState, title: str, renderer, diagnostics: Sequence[StateTransitionDiagnostic],
) -> str:
    candidate = state.selected_candidate
    assert candidate is not None  # guaranteed: only rendered after a successful state.history()
    unit = _unit_for(state)
    body: List[str] = [""]
    body.append(theme.kv("candidate", _candidate_line(state, candidate)))
    body.append("")
    body.append(theme.divider())
    body.append("")
    for i, d in enumerate(diagnostics, start=1):
        body.extend(renderer(i, d, unit))
        body.append("")
    return theme.panel(
        title, body,
        right=f"candidate {theme.index(_display_index(state, candidate))} · "
              f"{len(diagnostics)} transition{'s' if len(diagnostics) != 1 else ''}",
    )


# -- command handlers : thin parsing/dispatch around the renderers above ------------------------------


def parse_command(line: str) -> Tuple[str, List[str]]:
    """Tokenizes one line of input -- `str.split()`, nothing more."""
    tokens = line.strip().split()
    if not tokens:
        return "", []
    return tokens[0].lower(), tokens[1:]


def _context_tokens(candidate: ActionCandidate) -> set:
    """Every string a user could reasonably type to name this
    candidate's context, taken from the scenario's OWN representation --
    the raw values, the `key=value` form, and the rendered display form.
    Nothing is invented and nothing is fuzzy: each token is an exact
    string derived from the context mapping itself."""
    tokens = {theme.context(candidate.target_context).lower()}
    for key, value in dict(candidate.target_context).items():
        tokens.add(str(value).lower())
        tokens.add(f"{key}={value}".lower())
        if key.endswith("_c"):
            tokens.add(f"{value}c")
    return tokens


def _matches(candidate: ActionCandidate, constraints: List[Tuple[str, str]]) -> bool:
    for field, wanted in constraints:
        if field == "formulation":
            if candidate.formulation.natural_key.lower() != wanted:
                return False
        elif field == "property":
            if candidate.property.lower() != wanted:
                return False
        elif field == "context":
            if wanted not in _context_tokens(candidate):
                return False
        else:  # a bare token: it may name the formulation, the property, or the context
            if not (
                candidate.formulation.natural_key.lower() == wanted
                or candidate.property.lower() == wanted
                or wanted in _context_tokens(candidate)
            ):
                return False
    return True


def resolve_candidate(state: WorkbenchState, args: List[str]):
    """Resolve a human's words to EXACTLY ONE existing `ActionCandidate`,
    or return a `theme.notice` explaining why it could not.

    Accepts a display index (`select 1`, kept for compatibility) or
    semantic terms drawn from the scenario's own vocabulary:

        select baseline 80
        select formulation=baseline context=80
        select baseline @ 80

    Never fuzzy-matches, never creates a candidate, and never uses
    display position as identity: the returned object is the same
    `ActionCandidate` -- same `candidate.id` -- that prediction,
    decision, observation, history and diagnostics all use."""
    candidates = state.list_candidates()
    if not args:
        return theme.notice(
            "invalid command", "select needs a candidate.",
            hint="select <n>   or   select <formulation> <context>",
        )

    if len(args) == 1 and args[0].isdigit():
        n = int(args[0])
        if 1 <= n <= len(candidates):
            return candidates[n - 1]
        # out of registry range -- it may still be a context value, so keep resolving
        # semantically rather than dead-ending on a number the user did not mean as an index.
        if not any(args[0].lower() in _context_tokens(c) for c in candidates):
            return theme.notice(
                "candidate out of range", f"there is no candidate {theme.index(n)} in this scenario.",
                hint=f"candidates   then   select <n>   where n is 1..{len(candidates)}",
            )

    constraints: List[Tuple[str, str]] = []
    for token in args:
        if token == "@":  # a separator, not a term
            continue
        if "=" in token:
            field, _, value = token.partition("=")
            field = field.lower()
            if field in ("formulation", "property", "context"):
                constraints.append((field, value.lower()))
            elif any(field in {k.lower() for k in dict(c.target_context)} for c in candidates):
                # a real context key from the scenario, e.g. `temperature_c=80`
                constraints.append(("context", token.lower()))
            else:
                known = sorted({k for c in candidates for k in dict(c.target_context)})
                return theme.notice(
                    "unknown selector", f"{field!r} is not a selectable field.",
                    hint=f"formulation=  property=  context=  or a context key: {', '.join(known)}",
                )
        else:
            constraints.append(("", token.lower()))

    matches = [c for c in candidates if _matches(c, constraints)]
    if not matches:
        formulations = sorted({c.formulation.natural_key for c in candidates})
        contexts = sorted({theme.context(c.target_context) for c in candidates})
        properties = sorted({c.property for c in candidates})
        # PHASE 103 -- with several properties declared, a selector naming only
        # formulation and context is ambiguous, so the guidance must say that
        # a property is available to name. Terms are matched exactly, never
        # fuzzily, so the accepted words are listed in full.
        rows = [
            theme.paint(f"nothing in this scenario matches {' '.join(args)!r}.", theme.VALUE),
            "",
            theme.kv("expected", theme.paint(
                "select <formulation> <property> <context>" if len(properties) > 1
                else "select <formulation> <context>", theme.MUTED)),
            theme.kv("formulations", theme.paint(", ".join(formulations), theme.MUTED)),
        ]
        if len(properties) > 1:
            rows.append(theme.kv("properties", theme.paint(", ".join(properties), theme.MUTED)))
        rows.append(theme.kv("contexts", theme.paint(", ".join(contexts), theme.MUTED)))
        return theme.panel("no such candidate", rows, tone=theme.ERR)
    if len(matches) > 1:
        listing = "   ".join(
            f"{theme.index(_display_index(state, c))} {c.formulation.natural_key} "
            f"{theme.DOT} {theme.context(c.target_context)}"
            for c in matches[:6]
        )
        return theme.notice(
            "ambiguous candidate",
            f"{' '.join(args)!r} matches {len(matches)} candidates — say which.",
            hint=listing, tone=theme.WARN,
        )
    return matches[0]


def _cmd_select(state: WorkbenchState, args: List[str]) -> str:
    if len(args) == 1 and args[0].lower() == "clear":
        if state.selected_candidate is None:
            return theme.notice(
                "nothing selected", "no candidate is active, so there is nothing to clear.",
                hint="select <n>   or   select <formulation> <context>", tone=theme.WARN,
            )
        state.clear_selection()
        return theme.panel("selection cleared", [
            "", theme.paint("No candidate is active.", theme.VALUE),
            theme.paint("predict, explore and observe need one before they can run.", theme.MUTED), "",
            theme.paint("  select <n>", theme.ACCENT)
            + theme.paint("                  by registry number", theme.MUTED),
            theme.paint("  select <formulation> <context>", theme.ACCENT)
            + theme.paint("  by name", theme.MUTED), "",
        ])

    resolved = resolve_candidate(state, args)
    if isinstance(resolved, str):
        return resolved
    state.select_candidate(state.list_candidates().index(resolved))
    return format_selection(state, resolved)


def _cmd_thread(state: WorkbenchState, args: List[str]) -> str:
    """Observational only. Reuses Phase 84's semantic resolver, so
    `thread baseline 80`, `thread 03` and `thread formulation=baseline`
    all name a candidate the same way `select` and `inspect` do. No
    second selector grammar is introduced, and an ambiguous selector
    stays ambiguous."""
    if not args:
        if state.selected_candidate is None:
            return _no_selection_notice()
        return format_thread(state, state.selected_candidate)
    resolved = resolve_candidate(state, args)
    if isinstance(resolved, str):
        return resolved
    return format_thread(state, resolved)


def _resolve_state_index(state: WorkbenchState, token: str, command: str):
    """One display index -> one position in the real chain, or a notice.
    PHASE 93 factored this out of `_cmd_timeline` so `state <n>` reuses
    the SAME navigation rather than a parallel copy of it: there is one
    state-selector semantics in this instrument, not two."""
    history = state.session.state_history
    hint = f"{command} <0-{len(history) - 1}>   ·   timeline   lists them"
    try:
        index = int(token)
    except ValueError:
        return theme.notice("unreadable state number", f"{token!r} is not a number.", hint=hint)
    if not 0 <= index < len(history):
        return theme.notice(
            "no such state", f"S{index} is not in this session's real history.", hint=hint)
    return index


def _cmd_timeline(state: WorkbenchState, args: List[str]) -> str:
    """Observational only. With no argument, the whole real trajectory;
    with a number, one state by DISPLAY index (identity remains the
    state's own hash, which the view prints beside it)."""
    if not args:
        return format_timeline(state)
    resolved = _resolve_state_index(state, args[0], "timeline")
    if isinstance(resolved, str):
        return resolved
    return format_timeline_state(state, resolved)


def _cmd_criterion(state: WorkbenchState, args: List[str]) -> str:
    """Observational only. With no argument, every candidate cell against
    its declared criterion; with a candidate selector, that one cell in
    detail. Reuses Phase 84's resolver -- no second selector grammar, and
    no criterion-authoring grammar either: a declared reference is
    scenario configuration, which is where it stays."""
    if not args:
        return format_criterion(state, state.list_candidates())
    resolved = resolve_candidate(state, args)
    if isinstance(resolved, str):
        return resolved
    return format_criterion_detail(state, resolved)


def _cmd_state(state: WorkbenchState, args: List[str]) -> str:
    """Observational only. The whole candidate registry read at one real
    state. PHASE 93 sec.11 -- `state` is never silently filtered: a
    trailing candidate selector is REFUSED rather than quietly narrowing
    the enumeration, because a partial view under a whole-state name
    would misrepresent what the state contains. `thread` is the
    candidate-specific view."""
    if not args:
        return format_state(state, len(state.session.state_history) - 1)
    resolved = _resolve_state_index(state, args[0], "state")
    if isinstance(resolved, str):
        return theme.notice(
            "state is not filterable",
            f"{' '.join(args)!r} is not a state number, and `state` is always the "
            "complete candidate registry.",
            hint=f"state   ·   state <0-{len(state.session.state_history) - 1}>"
                 f"   ·   thread {' '.join(args)}   for one candidate",
        )
    return format_state(state, resolved)


def _cmd_compare(state: WorkbenchState, args: List[str]) -> str:
    """Observational only. Resolves operands from the vocabulary the
    workbench already uses (`state <n>`, `branch <n>`), or defaults to
    the last real transition. Never advances anything."""
    tokens = [a.lower() for a in args]
    if tokens[:1] == ["decisions"] or tokens[:1] == ["decision"]:
        return format_decision_comparison(state)

    if not tokens:
        history = state.session.state_history
        if len(history) < 2:
            return theme.notice(
                "no previous real state",
                "this session has one real state, so there is no earlier state to compare it with.",
                hint="select <n>   then   observe <value>   ·   compare branch <n>",
            )
        if state.selected_candidate is None:
            return _no_selection_notice()
        return format_comparison(
            state,
            _real_operand(state, history[-2], len(history) - 1),
            _real_operand(state, history[-1], len(history)),
        )

    if tokens[0] not in ("state", "branch"):
        return theme.notice(
            "unknown operand", f"{args[0]!r} is not a comparison operand.",
            hint="compare   ·   compare branch <n>   ·   compare state <n> state <m>   "
                 "·   compare decisions",
        )

    first = _resolve_operand(state, tokens)
    if isinstance(first, str):
        return first
    rest = tokens[2:]
    if not rest:
        # one operand named: compare it against the CURRENT real state.
        current = _real_operand(
            state, state.session.state, len(state.session.state_history))
        if first.kind == "hypothetical":
            return format_comparison(state, current, first)
        return format_comparison(state, first, current)

    if rest[0] not in ("state", "branch"):
        return theme.notice(
            "unknown operand", f"{rest[0]!r} is not a comparison operand.",
            hint="compare state <n> state <m>   ·   compare branch <n> branch <m>",
        )
    second = _resolve_operand(state, rest)
    if isinstance(second, str):
        return second
    return format_comparison(state, first, second)


def _cmd_branch(state: WorkbenchState, args: List[str]) -> str:
    """Inspection only. PHASE 88 sec.8 -- there is deliberately no
    commit/apply/merge/choose: a branch is an analysis, not an
    alternative reality, and no semantics for adopting one has been
    established."""
    if not state.branches:
        return theme.notice(
            "no counterfactual branches",
            "nothing has been projected in this session.",
            hint="select <n>   then   explore <value>",
        )
    if not args:
        return theme.notice(
            "no branch named", "branch requires the number of a retained branch.",
            hint=f"branch <1-{len(state.branches)}>   ·   branches   lists them",
        )
    raw = args[0]
    try:
        position = int(raw)
    except ValueError:
        return theme.notice(
            "unreadable branch number", f"{raw!r} is not a number.",
            hint=f"branch <1-{len(state.branches)}>   ·   branches   lists them",
        )
    outcome = state.branch_at(position)
    if outcome is None:
        return theme.notice(
            "no such branch", f"branch {raw} is not in this session's registry.",
            hint=f"branch <1-{len(state.branches)}>   ·   branches   lists them",
        )
    return format_branch(state, outcome, position)


def _cmd_inspect(state: WorkbenchState, args: List[str]) -> str:
    """PHASE 90 sec.4 -- `inspect state <n>` reaches the timeline's own
    state view rather than a second one. `state` is already an operand
    word in `compare`, so this extends one grammar instead of adding
    another. Anything else is a candidate inspection, unchanged."""
    if args and args[0].lower() == "state":
        return _cmd_timeline(state, args[1:] or ["__missing__"])
    if args and args[0].lower() == "thread":
        return _cmd_thread(state, args[1:])
    return _cmd_inspect_candidate(state, args)


def _cmd_inspect_candidate(state: WorkbenchState, args: List[str]) -> str:
    if not args:
        if state.selected_candidate is None:
            return _no_selection_notice()
        return format_inspection(state, state.selected_candidate)
    resolved = resolve_candidate(state, args)
    if isinstance(resolved, str):
        return resolved
    return format_inspection(state, resolved)


def _cmd_predict(state: WorkbenchState) -> str:
    try:
        prediction = state.predict()
    except ValueError:
        return _no_selection_notice()
    assert state.selected_candidate is not None  # guaranteed by the successful state.predict() above
    return format_prediction(state, state.selected_candidate, prediction)


def _cmd_explore(state: WorkbenchState, args: List[str]) -> str:
    if len(args) != 1:
        return theme.notice("invalid command", "explore takes exactly one value.", hint="explore <value>")
    try:
        hypothetical_value = float(args[0])
    except ValueError:
        return theme.notice(
            "invalid value", f"{args[0]!r} is not a numeric value.", hint="explore <value>",
        )
    before = state.session.state.id
    try:
        state.explore(hypothetical_value)
    except ValueError:
        return _no_selection_notice()
    candidate = state.selected_candidate
    assert candidate is not None  # guaranteed by the successful state.explore() above
    return format_counterfactual(state, candidate, live_unchanged=state.session.state.id == before)


def _cmd_observe(state: WorkbenchState, args: List[str]) -> str:
    if not (1 <= len(args) <= 2):
        return theme.notice(
            "invalid command", "observe takes a value and an optional unit.", hint="observe <value> [unit]",
        )
    try:
        value = float(args[0])
    except ValueError:
        return theme.notice(
            "invalid value", f"{args[0]!r} is not a numeric value.", hint="observe <value> [unit]",
        )
    unit = args[1] if len(args) == 2 else None
    if unit is not None:
        try:
            float(unit)
        except ValueError:
            pass
        else:
            return theme.notice(
                "invalid unit", f"{unit!r} is a number, not a unit of measurement.",
                hint="observe <value> [unit]   e.g.  observe 90 MPa",
            )
    predecessor_state_id = state.session.state.id
    try:
        assessment, prediction = state.observe(value, unit)
    except ValueError as e:
        if "no candidate selected" in str(e):
            return _no_selection_notice()
        return theme.notice("observation rejected", str(e))
    candidate = state.selected_candidate
    assert candidate is not None  # guaranteed by the successful state.observe() above
    return format_assessment(state, candidate, predecessor_state_id, prediction, assessment)


def _cmd_history(state: WorkbenchState) -> str:
    try:
        diagnostic_set = state.history()
    except ValueError:
        return _no_selection_notice()
    if not diagnostic_set.diagnostics:
        return theme.notice(
            "no transitions yet",
            "this session has admitted no observations.",
            hint="observe <value>", tone=theme.WARN,
        )
    return _format_transition_panel(state, "transition history", format_transition, diagnostic_set.diagnostics)


def _cmd_diagnostics(state: WorkbenchState) -> str:
    try:
        diagnostic_set = state.history()
    except ValueError:
        return _no_selection_notice()
    if not diagnostic_set.diagnostics:
        return theme.notice(
            "no transitions yet",
            "this session has admitted no observations.",
            hint="observe <value>", tone=theme.WARN,
        )
    return _format_transition_panel(state, "transition diagnostics", format_diagnostic, diagnostic_set.diagnostics)


def dispatch(state: WorkbenchState, command: str, args: List[str]) -> str:
    """The full command table. Returns text to display; never prints
    directly, so this function -- and therefore the entire interaction
    surface -- is callable from a test with no stdin/stdout involved."""
    command = ALIASES.get(command, command)
    if command in ("", "help"):
        return format_help()
    if command == "scenario":
        return format_scenario(state)
    if command == "status":
        return format_status(state)
    if command == "candidates":
        return format_candidates(state)
    if command == "decide":
        return format_decision(state, state.decide())
    if command == "inspect":
        return _cmd_inspect(state, args)
    if command == "explain":
        if state.last_decision is None:
            return theme.notice(
                "no decision yet", "nothing has been decided in this session.",
                hint="decide   then   explain", tone=theme.WARN,
            )
        return format_explanation(state, state.last_decision)
    if command == "select":
        return _cmd_select(state, args)
    if command == "predict":
        return _cmd_predict(state)
    if command == "explore":
        return _cmd_explore(state, args)
    if command == "criterion":
        return _cmd_criterion(state, args)
    if command == "state":
        return _cmd_state(state, args)
    if command == "thread":
        return _cmd_thread(state, args)
    if command == "timeline":
        return _cmd_timeline(state, args)
    if command == "compare":
        return _cmd_compare(state, args)
    if command == "branches":
        return format_branches(state)
    if command == "branch":
        return _cmd_branch(state, args)
    if command == "observe":
        return _cmd_observe(state, args)
    if command == "history":
        return _cmd_history(state)
    if command == "diagnostics":
        return _cmd_diagnostics(state)
    if command == "quit":
        return "__QUIT__"
    return theme.notice(
        "unknown command", f"{command!r} is not a command.", hint="help   for the command reference",
    )


def format_prompt(state: WorkbenchState) -> str:
    """The prompt carries the one piece of context every command depends
    on -- which candidate is active -- so it never has to be re-checked
    with `status`."""
    if state.selected_candidate is None:
        location = theme.paint("workbench", theme.LABEL)
    else:
        location = (
            theme.paint("workbench", theme.LABEL)
            + theme.paint(f" {theme.DOT} ", theme.STRUCTURE)
            + theme.paint(theme.index(_display_index(state, state.selected_candidate)), theme.ACCENT)
        )
    return location + theme.paint(f" {theme.ARROW} ", theme.ACCENT)


def run_repl(state: Optional[WorkbenchState] = None) -> None:
    """The only function in this package that touches a real terminal.
    `state` defaults to a fresh `bootstrap_multi_candidate_scenario()` --
    there is no persistence, so every invocation starts from nothing."""
    if state is None:
        state = bootstrap_multi_candidate_scenario()
    print(format_masthead())
    print()
    print(format_scenario_banner(state))
    print()
    print(theme.paint("  help", theme.ACCENT) + theme.paint("  for commands   ", theme.MUTED)
          + theme.paint("quit", theme.ACCENT) + theme.paint("  to end the session", theme.MUTED))
    print()
    while True:
        try:
            line = input(format_prompt(state))
        except EOFError:
            print()
            return
        command, args = parse_command(line)
        output = dispatch(state, command, args)
        if output == "__QUIT__":
            print(theme.paint("  session ended · no state persisted", theme.MUTED))
            return
        print(output)
        print()


def _load_scenario_state(path: str) -> WorkbenchState:
    """`--scenario <path>`: reads a plain JSON scenario DEFINITION
    (formulations/property/criterion/contexts, never observations) with
    only the standard library `json` module, and hands it to
    `workbench.interaction.bootstrap_research_scenario` unmodified."""
    with open(path, encoding="utf-8") as f:
        config = json.load(f)
    return bootstrap_research_scenario(config)


def main(argv: Optional[List[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) >= 2 and argv[0] == "--scenario":
        try:
            state = _load_scenario_state(argv[1])
        except (OSError, json.JSONDecodeError, KeyError, ValueError) as e:
            print(theme.notice("scenario not loaded", f"could not load {argv[1]!r}: {e}"), file=sys.stderr)
            return 1
        run_repl(state=state)
        return 0
    run_repl()
    return 0


if __name__ == "__main__":
    sys.exit(main())
