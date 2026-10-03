"""ModelStateTrajectory + prediction_evolution/compare_predictions:
Phase 56's answer to "can the system represent and inspect the
evolution of a predictive model across successive evidence states?"

Before writing this module, `materials/model_state.py`, `materials/
assessment.py`, `materials/iteration.py`, `materials/information.py`,
`materials/surrogate.py`, `materials/results.py`, and `materials/
candidates.py` were re-read. Finding: `predict`/`update`/`assess`
(Phase 52-54) already give a complete, deterministic single-step
transition (`S_t -> P_t -> O_(t+1) -> A_t -> S_(t+1)`), and Phase 55
already proved that step is fully self-contained (no hidden state, no
external dependency). What did NOT exist anywhere: a representation of
the ORDERED SEQUENCE of states a caller actually walked through, or a
way to read off how a candidate's prediction changed across that
sequence. That is the one genuinely missing thing this module adds.

--------------------------------------------------------------------
IDENTITY vs LINEAGE vs ORDERING vs CHRONOLOGY -- kept deliberately
distinct, per this phase's own instruction not to collapse them:

  IDENTITY (`ModelState.id`) -- content-derived, unchanged since Phase
  52: a hash of every cell's sorted sample list. Two states with
  identical content are the SAME id, regardless of how many different
  call sequences could have produced that content.

  LINEAGE (which state a given state was actually derived FROM by one
  real `update()` call) -- NOT part of `ModelState.id`, and NOT added to
  `ModelState` as a `parent_state_id` field. Investigated directly
  (Phase 56 sec.4) and rejected: the only place lineage genuinely exists
  is at the `update()` call site itself, where the caller already holds
  both `state` (the parent) and the returned `ModelState` (the child) in
  hand. A `ModelStateTrajectory` captures exactly that caller knowledge,
  at the moment it is still available, as an explicit `predecessor_
  state_id` per entry -- representing lineage as a COMPUTED VIEW over a
  caller-supplied, chronologically-ordered sequence rather than baking a
  new field into `ModelState` itself. This avoids two real costs a
  `parent_state_id` field would have introduced: (1) it would have to be
  excluded from `ModelState.id`'s own hash to keep identity purely
  content-derived (this phase's own instruction), which then raises the
  question of what participates in equality/deduplication at all --
  exactly the kind of ambiguity a computed, external view sidesteps
  entirely; and (2) `ModelState` would carry a field meaningful only to
  trajectory analysis, never read by `predict`/`update` themselves --
  scope creep this module does not need. If a future caller needs
  lineage recoverable from a BARE `ModelState` with no accompanying
  trajectory, that is the moment to revisit this decision -- not before.

  ORDERING (`TrajectoryEntry.position`) -- the index of a state WITHIN
  ONE PARTICULAR trajectory a caller constructed, `0, 1, 2, ...`. This is
  a LOCAL, relative position, not a claim about global chronology.
  `make_model_state_trajectory` does not accept states in arbitrary
  order and infer their history; it requires the caller's own order and
  verifies it is at least CONSISTENT with a real `update()` chain (see
  below) -- position is computed from that verified order, never
  guessed, never inferred from timestamps.

  CHRONOLOGY (wall-clock time) -- deliberately NOT modeled. Neither
  `ModelState` nor `Sample` carries a timestamp (by design, since Phase
  52); this module adds none either. `ExperimentalResult.extracted_at`/
  `Observation.extracted_at` DO carry real timestamps (Phase 44), but
  using them to order a trajectory would silently conflate "when a value
  was admitted to `EvidencePool`" with "which sequence of `update()`
  calls a caller chose to walk" -- these can legitimately differ (e.g. a
  caller replaying history out of admission order, or building a
  synthetic trajectory in tests), and Phase 56 sec.5 explicitly forbids
  adding timestamps not already meaningful state data. `position` is
  therefore a caller-verified sequence index, nothing more.
--------------------------------------------------------------------

STRUCTURAL VERIFICATION, not blind trust: `make_model_state_trajectory`
checks that each state in the supplied sequence is a valid successor of
its predecessor -- for every cell (`model_state_key`) present in the
predecessor, the successor's sample set for that cell must be a SUPERSET
(mirrors the one thing `update()` can ever do: append a `Sample`, never
remove one). A caller supplying unrelated or misordered states is
rejected with `ValueError`, exactly the same "one cheap, free check
available" discipline `materials.model_state.update`/`materials.
assessment.assess` already established for their own single-step
identity checks -- proportional here, not a full state-machine replay
audit.

TRAJECTORY IS A COMPUTED VIEW, NOT A DATABASE: `ModelStateTrajectory`
holds only the caller-supplied `ModelState` objects (embedded whole,
never copied/flattened) plus the position/predecessor bookkeeping
derived from their order. Nothing is looked up from a store; nothing is
cached beyond what one `make_model_state_trajectory` call computes;
every `ModelState` inside it remains exactly as immutable as it already
was. No mutable model registry, no version counter, no persistence.

PREDICTION EVOLUTION: `prediction_evolution(trajectory, candidate,
assessments)` computes `predict(entry.state, candidate)` for every entry
-- a pure, already-established Phase 52 operation, simply applied once
per state in the sequence rather than once in isolation. Where a
caller-supplied `materials.assessment.PredictionAssessment` exists for
the exact `(state_id, candidate_id)` pair a given step names, its
`observed_value`/`residual` are attached (matched by those two already-
stable ids -- `PredictionAssessment.state_id`/`.candidate_id` -- never
by re-querying `EvidencePool`, never by independently reconstructing
provenance, exactly Phase 56 sec.7's requirement). If more than one
supplied assessment happens to match the same `(state_id, candidate_id)`
pair (a caller assessed the same prediction against more than one
observation), the one with the lexicographically smallest
`observation.id` is used -- a deterministic, content-derived tie-break,
never insertion order.

`compare_predictions(prediction_a, prediction_b)` is the smaller, pure,
pairwise operation Phase 56 sec.6 asks for: `delta_predicted_value =
prediction_b.predicted_value - prediction_a.predicted_value`,
`delta_uncertainty = prediction_b.uncertainty - prediction_a.uncertainty`
-- signed, `None` whenever either side is `None` (never guessed as
zero, mirroring `materials.assessment`'s own residual convention).
NEITHER function interprets a delta as "improvement," "deterioration,"
"model quality," or "scientific progress" -- those are a caller's
semantic policy this module does not have a basis to assert, exactly
Phase 56 sec.6's own instruction.

INFORMATION-VALUE EVOLUTION (Phase 56 sec.8) is deliberately NOT a new
function in this module: `materials.information.estimate_information_value`
already accepts any `InformationValueModel`, and
`materials.model_state.ModelStateInformationValueModel` already binds to
one `ModelState` snapshot -- "information value at S_0, S_1, S_2" is
therefore already fully expressible today as
`estimate_information_value(candidate, iteration,
ModelStateInformationValueModel(entry.state))`, called once per
`trajectory.entries` entry. Wrapping that one-line composition in a new
function here would be exactly the "another thin descriptive wrapper"
this project has repeatedly declined to add; this module's own tests
demonstrate the composition directly instead.

BOUNDARY: no `EvidencePool`/`RetrievalEngine` access anywhere in this
module. No mutation of any `ModelState`, `Prediction`, or
`PredictionAssessment` passed in. `materials.results` remains the sole
write boundary; this module never touches it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from materials.assessment import PredictionAssessment
from materials.candidates import ActionCandidate
from materials.model_state import ModelState, Prediction, predict


@dataclass(frozen=True)
class TrajectoryEntry:
    """One state's position within one caller-constructed trajectory.
    `state` is embedded whole (the complete, unmodified `ModelState`) --
    `state_id` is also surfaced directly for ergonomic access, the same
    convenience every `materials/` layer since Phase 38 already offers
    alongside its embedded objects. `predecessor_state_id` is `None`
    exactly for `position == 0` (the trajectory's first state has no
    predecessor within this trajectory -- it may still have earlier
    real-world history this trajectory simply was not given)."""

    position: int
    state: ModelState
    state_id: str
    predecessor_state_id: Optional[str]


@dataclass(frozen=True)
class ModelStateTrajectory:
    """S_0 -> S_1 -> ... -> S_n as an explicit, computed, immutable
    view. Never mutates any entry's `ModelState`; never re-derives one
    from a store. See module docstring for why lineage lives here,
    rather than as a field on `ModelState` itself."""

    entries: Tuple[TrajectoryEntry, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", tuple(self.entries))


def make_model_state_trajectory(states: Tuple[ModelState, ...]) -> ModelStateTrajectory:
    """The only supported way to construct a `ModelStateTrajectory`.
    `states` must be given in the caller's own actual chronological
    `update()` order -- this function does not accept them in arbitrary
    order and infer history. It DOES verify that order is at least
    consistent with a real `update()` chain: for every cell present in
    a predecessor, the successor's sample set for that cell must be a
    superset (the one thing `update()` can ever do to a cell -- append a
    sample, never remove one). Raises `ValueError` otherwise -- a caller
    supplying unrelated or misordered states is an error this function
    actively rejects rather than silently accepting."""
    if not states:
        raise ValueError("ModelStateTrajectory requires at least one ModelState")

    for previous, current in zip(states, states[1:]):
        for key, previous_samples in previous.samples.items():
            current_samples = current.samples.get(key, ())
            if not set(previous_samples).issubset(set(current_samples)):
                raise ValueError(
                    f"state {current.id!r} is not a valid successor of {previous.id!r}: "
                    f"cell {key!r} lost sample(s) that update() can only ever append, never remove"
                )

    entries = tuple(
        TrajectoryEntry(
            position=position, state=state, state_id=state.id,
            predecessor_state_id=(states[position - 1].id if position > 0 else None),
        )
        for position, state in enumerate(states)
    )
    return ModelStateTrajectory(entries=entries)


@dataclass(frozen=True)
class TrajectoryPrediction:
    """One step of `prediction_evolution` -- how ONE candidate's
    prediction read at ONE trajectory state, plus (when available) what
    was actually observed at that state and the resulting residual.
    `prediction`/`assessment` are embedded whole -- full provenance
    without duplication; `observed_value`/`residual` are also surfaced
    directly (read off `assessment` when one exists) for the same
    ergonomic-access convenience every `materials/` layer already
    offers. `assessment`/`observed_value`/`residual` are all `None`
    together whenever no caller-supplied `PredictionAssessment` matched
    this step's `(state_id, candidate_id)` -- never guessed, never
    defaulted."""

    position: int
    predecessor_state_id: Optional[str]
    prediction: Prediction
    assessment: Optional[PredictionAssessment]
    observed_value: Optional[float]
    residual: Optional[float]


def prediction_evolution(
    trajectory: ModelStateTrajectory,
    candidate: ActionCandidate,
    assessments: Tuple[PredictionAssessment, ...] = (),
) -> Tuple[TrajectoryPrediction, ...]:
    """Deterministic, side-effect-free, read-only. For each entry in
    `trajectory` (already in caller-verified order), computes
    `predict(entry.state, candidate)` -- a pure, already-established
    Phase 52 operation -- and attaches the caller-supplied
    `PredictionAssessment` (if any) whose `(state_id, candidate_id)`
    matches this step's, matched by those already-stable ids alone.
    Never re-queries `EvidencePool`; never reconstructs provenance
    independently; never mutates `trajectory`, `candidate`, or
    `assessments`."""
    matching_by_state: Dict[str, PredictionAssessment] = {}
    for assessment in assessments:
        if assessment.candidate_id != candidate.id:
            continue
        existing = matching_by_state.get(assessment.state_id)
        if existing is None or assessment.observation.id < existing.observation.id:
            matching_by_state[assessment.state_id] = assessment

    steps = []
    for entry in trajectory.entries:
        prediction = predict(entry.state, candidate)
        matched_assessment = matching_by_state.get(entry.state_id)
        steps.append(TrajectoryPrediction(
            position=entry.position, predecessor_state_id=entry.predecessor_state_id,
            prediction=prediction, assessment=matched_assessment,
            observed_value=matched_assessment.observed_value if matched_assessment is not None else None,
            residual=matched_assessment.residual if matched_assessment is not None else None,
        ))
    return tuple(steps)


@dataclass(frozen=True)
class PredictionDelta:
    """The purely mathematical difference between two `Prediction`s for
    the SAME candidate -- `delta_predicted_value`/`delta_uncertainty` =
    (`prediction_b` - `prediction_a`), signed, `None` whenever either
    side is `None`. No interpretation ("improvement," "deterioration,"
    "model quality," "scientific progress") is attached -- that is a
    caller's semantic policy this dataclass does not assert."""

    candidate_id: str
    from_state_id: str
    to_state_id: str
    from_predicted_value: Optional[float]
    to_predicted_value: Optional[float]
    delta_predicted_value: Optional[float]
    from_uncertainty: Optional[float]
    to_uncertainty: Optional[float]
    delta_uncertainty: Optional[float]


def compare_predictions(prediction_a: Prediction, prediction_b: Prediction) -> PredictionDelta:
    """Deterministic, side-effect-free, read-only. Requires both
    predictions to concern the same candidate (`prediction_a.candidate_id
    == prediction_b.candidate_id`) -- the same identity check
    `materials.assessment.assess`/`materials.model_state.update` already
    establish is sufficient on its own (an `ActionCandidate.id` already
    encodes formulation/property/target_context, so two predictions
    agreeing on `candidate_id` are already guaranteed to concern the same
    model-state cell)."""
    assert prediction_a.candidate_id == prediction_b.candidate_id, (
        f"prediction_a.candidate_id {prediction_a.candidate_id!r} does not match "
        f"prediction_b.candidate_id {prediction_b.candidate_id!r} -- compare_predictions() "
        "requires two predictions for the same ActionCandidate"
    )
    a_value, b_value = prediction_a.predicted_value, prediction_b.predicted_value
    a_uncertainty, b_uncertainty = prediction_a.uncertainty, prediction_b.uncertainty
    delta_value = (b_value - a_value) if a_value is not None and b_value is not None else None
    delta_uncertainty = (
        (b_uncertainty - a_uncertainty) if a_uncertainty is not None and b_uncertainty is not None else None
    )
    return PredictionDelta(
        candidate_id=prediction_a.candidate_id,
        from_state_id=prediction_a.state_id, to_state_id=prediction_b.state_id,
        from_predicted_value=a_value, to_predicted_value=b_value, delta_predicted_value=delta_value,
        from_uncertainty=a_uncertainty, to_uncertainty=b_uncertainty, delta_uncertainty=delta_uncertainty,
    )
