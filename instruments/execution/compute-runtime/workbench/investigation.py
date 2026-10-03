"""Phase 69: `run_investigation()` -- one concrete, deterministic
materials-development investigation exercising the FULL closed loop
(state -> prediction -> decision -> observation -> residual -> updated
state -> next decision) through the existing algebra, end to end, with
no new primitive.

WHY A SEPARATE MODULE, NOT A NEW METHOD ON `WorkbenchState`: this
investigation's central question -- "does the closed loop change what
the system recommends doing next" -- requires comparing TWO candidates'
utility/optimization side by side at every decision point.
`WorkbenchState` (Phase 68) deliberately holds exactly ONE `selected_
candidate` at a time and deliberately declined to expose utility/
information-value/optimization inspection (see `workbench/interaction.py`'s
own Phase 66 "declined" list, inherited from `experiment/session.py`) --
retrofitting multi-candidate decision machinery into that single-
candidate interactive surface would be exactly "adding another
architectural layer merely to make the system look more complete,"
which this phase's own instructions forbid. Multi-candidate decision
composition already has a home: `experiment.step.run_experiment_step`
performs exactly this composition today, fully automated. This module
does the SAME composition -- predict, structural information value,
model-driven information estimate, utility, `optimize_candidates(...,
max_candidates=1)` -- but INLINE and NARRATED rather than behind one
opaque call, because the deliverable here is a human-readable
investigation transcript, not another automation entry point. No
decision primitive is added: every one of these calls is the same
unmodified `materials.*` function `experiment/step.py` itself already
calls internally.

ONE OBSERVED, NON-BLOCKING LIMITATION (documented rather than "fixed,"
since the underlying algebra remains fully sufficient by direct
composition -- see this module's own investigation report): `experiment.
policy.ExperimentPolicy.utility_input_source`'s signature is
`Callable[[InformationValueEstimate], ExperimentUtilityInput]` -- it
receives only the already-computed information-value ESTIMATE, not the
candidate's raw sample count. The utility policy this investigation
needs (`workbench.interaction._utility_input_for`) must distinguish
"zero real samples" (an unexplored candidate, worth an exploratory
bootstrap benefit) from "one real sample" (partially explored,
uncertainty not yet computable, but no longer a wholly fresh unknown) --
a distinction `InformationValueEstimate` alone cannot answer (its
`estimate`/`.basis` free-text string is not something a caller should
parse to recover a number; `materials.model_state.
ModelStateInformationValueModel.estimate` reports the same `None` for
zero samples and for one sample alike). This means a policy shaped like
this investigation's could not be plugged into `run_experiment_step` via
that one callback alone; it could still be expressed by composing the
same underlying primitives directly, exactly as this module does, and
exactly as `run_experiment_step` itself does internally. This is worth
recording, but it is NOT the "genuinely missing primitive" Phase 69
sec.12 asks about: it is a narrower callback shape on one particular
composition helper, not a gap in `predict`/`estimate_information_value`/
`evaluate_utility_set`/`optimize_candidates` themselves.

PHASE 70 UPDATE: the scenario-bootstrap and utility-policy logic this
module used to define locally (`_bootstrap_investigation_scenario`'s own
construction, `_utility_input_for`, `_sample_count`, `DECISION_POLICY`,
`MEASUREMENT_COST`, `BOOTSTRAP_BENEFIT`, `PARTIAL_EXPLORATION_BENEFIT`)
now live in `workbench/interaction.py` as `bootstrap_multi_candidate_
scenario`/`_utility_input_for`/`evaluate_decision` and friends -- the
same interactive workbench's own default decision policy, since Phase 70
needed exactly this policy for its `decide`/`candidates` commands to be
meaningful out of the box. This module imports them rather than keeping
a second copy; nothing about this module's own tested behavior changes
(same policy, same numbers, same scenario), only where the shared logic
is defined.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Tuple

from evidence.admission import admit_record
from evidence.types import make_record
from experiment.session import ExperimentSession
from materials.assessment import PredictionAssessment
from materials.candidates import ActionCandidate, CandidateSet
from materials.diagnostics import StateTransitionDiagnosticSet, diagnose_transitions
from materials.ensemble import (
    CounterfactualInformationValue, CounterfactualOutcome, CounterfactualSet,
    evaluate_counterfactual_information_value, make_counterfactual_set, project_outcome,
)
from materials.iteration import MaterialsIteration
from materials.optimization import OptimizationResult, optimize_candidates
from materials.results import admit_experimental_result, make_experimental_result
from materials.trajectory import make_model_state_trajectory
from materials.utility import evaluate_utility_set
from materials.value import evaluate_candidate_information_values
from workbench.interaction import DECISION_POLICY, _utility_input_for, bootstrap_multi_candidate_scenario

FORMULATION_KEY = "formulation-f1"
PROCESS_KEY = "process-std-190c"
PROPERTY = "tensile_strength"
UNIT = "MPa"
CRITERION_TARGET = 80.0


def _fixed_clock() -> Callable[[], str]:
    counter = {"n": 0}

    def clock() -> str:
        n = counter["n"]
        counter["n"] += 1
        return f"2026-08-24T02:{n:02d}:00Z"

    return clock


@dataclass(frozen=True)
class DecisionRecord:
    """One point in the investigation where a real decision was made --
    embeds the complete, unmodified `OptimizationResult` (full
    provenance: every candidate's utility/status, not just the chosen
    one) plus the `ActionCandidate` `optimize_candidates` actually
    selected. `label` is a human-readable tag for the transcript/report
    only; it carries no semantics of its own."""

    label: str
    optimization: OptimizationResult
    selected_candidate: ActionCandidate


@dataclass
class InvestigationResult:
    """Everything this investigation produced, embedded whole -- the
    test file asserts against these real objects directly rather than
    re-parsing printed narration text."""

    candidate_room: ActionCandidate
    candidate_elevated: ActionCandidate
    iteration: MaterialsIteration
    sessions: List[ExperimentSession] = field(default_factory=list)
    assessments: List[PredictionAssessment] = field(default_factory=list)
    decisions: List[DecisionRecord] = field(default_factory=list)
    counterfactual_outcomes: Tuple[CounterfactualOutcome, ...] = ()
    counterfactual_set: CounterfactualSet = None  # type: ignore[assignment]
    counterfactual_information_value: CounterfactualInformationValue = None  # type: ignore[assignment]
    diagnostics: StateTransitionDiagnosticSet = None  # type: ignore[assignment]


def _bootstrap_investigation_scenario(clock: Callable[[], str]) -> Tuple[ExperimentSession, CandidateSet, MaterialsIteration, object]:
    """Builds the pool/session for THIS investigation's own scenario --
    delegates entirely to `workbench.interaction.bootstrap_multi_
    candidate_scenario` (Phase 70), which now defines the exact two-
    experimental-context, zero-prior-evidence scenario this investigation
    already validated in Phase 69. Kept as a thin wrapper (rather than
    calling that function directly at each use site) purely so this
    module's own tuple-shaped return type -- `(session, candidates,
    iteration, campaign)`, matching how `run_investigation` already
    consumes it -- does not have to change."""
    workbench_state = bootstrap_multi_candidate_scenario(clock)
    return workbench_state.session, workbench_state.candidates, workbench_state.session.iteration, workbench_state.campaign


def _decide(candidates: CandidateSet, state, iteration: MaterialsIteration, label: str) -> DecisionRecord:
    """evaluate_utility_set() + optimize_candidates(max_candidates=1) --
    the existing decision primitives, unmodified, called directly
    (Phase 69 sec.3: 'do not create a new decision primitive')."""
    civs = evaluate_candidate_information_values(candidates, iteration)
    utility_inputs = {c.id: _utility_input_for(c, state, iteration)[0] for c in candidates.candidates}
    utility_set = evaluate_utility_set(civs, utility_inputs)
    optimization = optimize_candidates(utility_set, DECISION_POLICY)
    selected = [o for o in optimization.optimizations if o.status == "SELECTED"]
    if len(selected) != 1:
        raise ValueError(f"expected exactly one SELECTED candidate at decision {label!r}; got {len(selected)}")
    selected_candidate = next(c for c in candidates.candidates if c.id == selected[0].candidate_id)
    return DecisionRecord(label=label, optimization=optimization, selected_candidate=selected_candidate)


def _observe(
    session: ExperimentSession, campaign, candidate: ActionCandidate, value: float, locator: str, clock: Callable[[], str],
) -> Tuple[PredictionAssessment, ExperimentSession]:
    """The one place this investigation admits anything -- the same
    admit_record/admit_experimental_result sequence `experiment/step.py`
    and `workbench/interaction.py` already use. `value` is always an
    externally supplied experimental observation, never fabricated by
    this module's own computation."""
    entry = next(e for e in campaign.entries if e.candidate_id == candidate.id)
    prediction = session.predict(candidate)
    record = make_record(document_id=session.document_id, locator=locator, raw_content=f"{value} {UNIT}")
    admitted_record = admit_record(session.pool, record)
    if isinstance(admitted_record, list):
        raise ValueError(f"observation Record was rejected by admit_record: {admitted_record!r}")
    session.pool.put_record(record)
    result = make_experimental_result(
        campaign, entry, content={"property": candidate.property, "value": value, "unit": UNIT},
        record_id=record.id, extracted_at=clock(),
        extraction_method="measurement:campaign_execution",
    )
    admitted = admit_experimental_result(session.pool, result, confidence=1.0)
    if isinstance(admitted, list):
        raise ValueError(f"ExperimentalResult was rejected by admit_experimental_result: {admitted!r}")
    observation, _relationship = admitted
    return session.observe(candidate, prediction, result, observation)


def _print_decision(decision: DecisionRecord) -> None:
    print(f"  decision: {decision.label}")
    for o in decision.optimization.optimizations:
        candidate = next(
            c for c in decision.optimization.utility_set.candidate_information_values.candidate_set.candidates
            if c.id == o.candidate_id
        )
        print(
            f"    {dict(candidate.target_context)}: utility={o.utility.utility} "
            f"(benefit-cost, {o.utility.utility_status})  status={o.status}"
        )
    print(f"    -> selected: {dict(decision.selected_candidate.target_context)}")


def run_investigation() -> InvestigationResult:
    """The full closed-loop investigation, narrated. Deterministic
    (fixed clock); every printed number is read directly off a real
    domain object -- nothing here recomputes a mean/variance/residual
    by hand."""
    clock = _fixed_clock()
    session, candidates, iteration, campaign = _bootstrap_investigation_scenario(clock)
    candidate_room = next(c for c in candidates.candidates if c.target_context.get("temperature") == 25)
    candidate_elevated = next(c for c in candidates.candidates if c.target_context.get("temperature") == 100)
    result = InvestigationResult(
        candidate_room=candidate_room, candidate_elevated=candidate_elevated, iteration=iteration,
    )
    result.sessions.append(session)

    print("=" * 70)
    print("CLOSED-LOOP MATERIALS INVESTIGATION")
    print(f"formulation={FORMULATION_KEY!r} process={PROCESS_KEY!r} property={PROPERTY!r}")
    print(f"candidates: room-temperature (25C)={candidate_room.id[:12]}...  "
          f"elevated-temperature (100C)={candidate_elevated.id[:12]}...")
    print("=" * 70)

    print("\n--- INITIAL STATE ---")
    print(f"ModelState.id = {session.state.id[:12]}...")
    for c in (candidate_room, candidate_elevated):
        prediction = session.predict(c)
        print(
            f"  {dict(c.target_context)}: predicted_value={prediction.predicted_value} "
            f"uncertainty={prediction.uncertainty} sample_count={prediction.sample_count}"
        )

    print("\n--- COUNTERFACTUAL EXPLORATION (before the first real experiment) ---")
    outcome_high = project_outcome(session.state, candidate_room, 88.0, probability=0.5)
    outcome_low = project_outcome(session.state, candidate_room, 70.0, probability=0.5)
    cf_set = make_counterfactual_set((outcome_high, outcome_low))
    civ = evaluate_counterfactual_information_value(cf_set, candidate_room, iteration)
    outcome_high_repeat = project_outcome(session.state, candidate_room, 88.0, probability=0.5)
    print(f"  hypothetical branch (88.0): projected_state={outcome_high.projected_state_id[:12]}... "
          f"prediction_after={outcome_high.prediction_after.predicted_value}")
    print(f"  hypothetical branch (70.0): projected_state={outcome_low.projected_state_id[:12]}... "
          f"prediction_after={outcome_low.prediction_after.predicted_value}")
    print(f"  expected_information_value = {civ.expected_information_value} ({civ.expected_information_value_status})")
    print(f"  source state unchanged: {session.state.id == result.sessions[0].state.id}")
    print(f"  identical hypothetical input is deterministic: "
          f"{outcome_high.projected_state.id == outcome_high_repeat.projected_state.id}")
    result.counterfactual_outcomes = (outcome_high, outcome_low)
    result.counterfactual_set = cf_set
    result.counterfactual_information_value = civ

    decision_1 = _decide(candidates, session.state, iteration, "D1 (initial)")
    print("\n--- DECISION 1 ---")
    _print_decision(decision_1)
    result.decisions.append(decision_1)

    print("\n--- OBSERVATION 1 (externally supplied experimental observation) ---")
    value_1 = 88.0
    print(f"  measuring {dict(decision_1.selected_candidate.target_context)}: observed value = {value_1} {UNIT}")
    assessment_1, session = _observe(session, campaign, decision_1.selected_candidate, value_1, "obs-1", clock)
    result.sessions.append(session)
    result.assessments.append(assessment_1)
    print("\n--- RESIDUAL 1 ---")
    print(f"  prediction={assessment_1.predicted_value}  observed={assessment_1.observed_value}  "
          f"residual={assessment_1.residual}  absolute_residual={assessment_1.absolute_residual}")
    print(f"\n--- UPDATED STATE --- ModelState.id = {session.state.id[:12]}...")

    decision_2 = _decide(candidates, session.state, iteration, "D2 (after observation 1)")
    print("\n--- DECISION 2 ---")
    _print_decision(decision_2)
    changed_1_to_2 = decision_1.selected_candidate.id != decision_2.selected_candidate.id
    print(f"  decision changed from D1: {changed_1_to_2}")
    result.decisions.append(decision_2)

    print("\n--- OBSERVATION 2 (externally supplied experimental observation) ---")
    value_2 = 65.0
    print(f"  measuring {dict(decision_2.selected_candidate.target_context)}: observed value = {value_2} {UNIT}")
    assessment_2, session = _observe(session, campaign, decision_2.selected_candidate, value_2, "obs-2", clock)
    result.sessions.append(session)
    result.assessments.append(assessment_2)
    print(f"  residual={assessment_2.residual}")

    print("\n--- OBSERVATION 3 (second real sample, room-temperature candidate) ---")
    value_3 = 102.0
    print(f"  measuring {dict(candidate_room.target_context)}: observed value = {value_3} {UNIT}")
    assessment_3, session = _observe(session, campaign, candidate_room, value_3, "obs-3", clock)
    result.sessions.append(session)
    result.assessments.append(assessment_3)
    print("--- RESIDUAL 3 ---")
    print(f"  prediction={assessment_3.predicted_value}  observed={assessment_3.observed_value}  "
          f"residual={assessment_3.residual}  absolute_residual={assessment_3.absolute_residual}")

    decision_3 = _decide(candidates, session.state, iteration, "D3 (after observation 3)")
    print("\n--- DECISION 3 ---")
    _print_decision(decision_3)
    result.decisions.append(decision_3)

    print("\n--- OBSERVATION 4 (third real sample, room-temperature candidate) ---")
    value_4 = 70.0
    print(f"  measuring {dict(candidate_room.target_context)}: observed value = {value_4} {UNIT}")
    assessment_4, session = _observe(session, campaign, candidate_room, value_4, "obs-4", clock)
    result.sessions.append(session)
    result.assessments.append(assessment_4)
    print("--- RESIDUAL 4 ---")
    print(f"  prediction={assessment_4.predicted_value}  observed={assessment_4.observed_value}  "
          f"residual={assessment_4.residual}  absolute_residual={assessment_4.absolute_residual}")

    decision_4 = _decide(candidates, session.state, iteration, "D4 (final)")
    print("\n--- DECISION 4 (final) ---")
    _print_decision(decision_4)
    result.decisions.append(decision_4)

    print("\n--- TRAJECTORY DIAGNOSTICS (room-temperature candidate) ---")
    trajectory = make_model_state_trajectory(tuple(s.state for s in result.sessions))
    diagnostics = diagnose_transitions(trajectory, candidate_room, tuple(result.assessments))
    result.diagnostics = diagnostics
    for i, d in enumerate(diagnostics.diagnostics, start=1):
        observed = "no observation recorded for this transition" if d.assessment is None else d.observation_value
        residual = "n/a" if d.assessment is None else d.residual_against_previous_prediction
        print(
            f"  [{i}] {d.predecessor_state_id[:8]}... -> {d.successor_state_id[:8]}...  "
            f"prev_pred={d.previous_prediction.predicted_value}  new_pred={d.new_prediction.predicted_value}  "
            f"delta={d.delta_predicted_value}  observed={observed}  residual={residual}"
        )

    print("\n" + "=" * 70)
    print("INVESTIGATION COMPLETE")
    print("=" * 70)
    return result


if __name__ == "__main__":
    run_investigation()
