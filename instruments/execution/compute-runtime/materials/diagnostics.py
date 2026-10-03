"""diagnose_transitions(trajectory, candidate, assessments) ->
StateTransitionDiagnosticSet: Phase 57's answer to "what changed in the
model state because of this new evidence?" -- the smallest pure
consolidation of quantities Phase 52-56 already compute separately, for
one consecutive state-transition pair at a time.

Before writing this module, `materials/model_state.py`, `materials/
trajectory.py`, `materials/assessment.py`, `materials/information.py`,
`materials/iteration.py`, and `materials/results.py` were re-read. The
finding: EVERY number this module reports already exists somewhere --
`materials.trajectory.prediction_evolution` already computes, per
trajectory state, the `Prediction` and (when a caller supplied a
matching `PredictionAssessment`) the observed value/residual;
`materials.trajectory.compare_predictions` already computes the signed
delta between any two `Prediction`s. This module invents NO new
mathematics. What did not exist: a single object that PAIRS two
consecutive `prediction_evolution` steps and their between-step delta,
so a caller asking "what changed at this one transition" does not have
to hand-assemble the pairing (and get it subtly wrong -- e.g. matching
the wrong assessment to the wrong step) every time. That pairing is a
real, recurring question this module consolidates -- nothing more.

WHY A NEW OBJECT IS JUSTIFIED, NOT JUST MORE CALLER CODE: comparing
consecutive `prediction_evolution` steps requires (a) knowing which
`PredictionAssessment` belongs to the CAUSE of a given transition
(specifically: the assessment attached to the PREDECESSOR step, since
`materials.assessment.assess(predict(S_t, x), result_t, observation_t)`
is exactly what production the observation that becomes `S_(t+1)` was
assessed against -- never the successor step's own, unrelated
assessment, if any), and (b) calling `compare_predictions` on the right
pair in the right order. Getting either wrong silently produces a
plausible-looking but incorrect diagnostic; consolidating both into one
function removes that entire class of caller error, which is exactly
the bar this project already applies elsewhere (`materials.model_state.
update`/`materials.assessment.assess`'s own one-cheap-check identity
assertions exist for the same reason -- catch a mismatch mechanically
rather than trust a caller to pair things correctly).

MULTI-CELL SCOPE (Phase 57 sec.3) -- deliberately (A), not (B):
`diagnose_transitions` reports the transition for exactly ONE
caller-supplied candidate, never a scan across every cell a `ModelState`
happens to contain. Two independent reasons, not just convenience: (1)
`ModelState.samples` is keyed by an opaque `resolve_model_state_key`
hash -- there is no registry anywhere of which `ActionCandidate`s exist
or which cell each one names, so "every cell whose predictions changed"
cannot even be enumerated without inventing a candidate registry this
architecture does not have; (2) mathematically, it would be uninteresting
even if it could: `materials.model_state.update` only ever appends a
`Sample` to the ONE cell its `result`/`candidate` name, copying every
other cell through UNCHANGED (proven directly by `materials.model_state`'s
own "uncertainty changes only when warranted" test) -- so every cell
other than the one the caller's candidate names is PROVABLY identical
between predecessor and successor, and a caller who cares about a
different cell simply calls `diagnose_transitions` again with a
candidate naming it. No hidden multi-candidate machinery is added.

NO INTERPRETATION: `StateTransitionDiagnostic` never labels a delta
"improved"/"degraded"/"better"/"worse", never assigns a "model quality"
or "causal effect", and never claims the residual CAUSED the state
update -- the reference model's `update` happens to work by accumulating
samples (unconditionally, regardless of the residual's sign or
magnitude); this module only reports the resulting mathematical
difference between two already-computed predictions, exactly as Phase
57 sec.6 requires.

INFORMATION VALUE (sec.7): no new function is added here.
`materials.information.estimate_information_value` combined with
`materials.model_state.ModelStateInformationValueModel` already computes
"information value at S_t" for any single state; calling it once per
side of a diagnostic's `predecessor_state_id`/`successor_state_id`
already expresses "information value before/after this transition" in
full, demonstrated in this module's own tests rather than wrapped in a
redundant function here.

OBSERVATION IDENTITY (sec.5): never copied or reconstructed. The
`PredictionAssessment` (and, through it, the `Observation`/
`ExperimentalResult` it embeds) that caused a transition is embedded
WHOLE on the diagnostic (`assessment`), exactly as `materials.trajectory.
TrajectoryPrediction` already does -- this module reads
`materials.assessment.PredictionAssessment.observation.id`/`.result`
through that embedding rather than adding an `Observation` reference to
`ModelState` itself (explicitly out of scope, sec.5).

BOUNDARY: no `EvidencePool`/`RetrievalEngine` access. No mutation of any
`ModelStateTrajectory`, `ActionCandidate`, or `PredictionAssessment`
passed in. `materials.results` remains the sole write boundary; this
module never touches it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from materials.assessment import PredictionAssessment
from materials.candidates import ActionCandidate
from materials.model_state import Prediction
from materials.trajectory import ModelStateTrajectory, compare_predictions, prediction_evolution


@dataclass(frozen=True)
class StateTransitionDiagnostic:
    """D(S_t, S_(t+1), x, y_t) -- what changed for ONE candidate across
    ONE consecutive pair of trajectory states. `previous_prediction`/
    `new_prediction` (== `G(S_t, x)`/`G(S_(t+1), x)`) and `assessment`
    (the `PredictionAssessment` -- if any -- of `previous_prediction`
    against the observation `y_t` that produced `S_(t+1)`) are embedded
    whole: full provenance (including the exact `Observation`/
    `ExperimentalResult` behind `y_t`, reachable via `assessment.
    observation`/`assessment.result`) without duplicating any of it.
    `observation_value`/`residual_against_previous_prediction`/
    `absolute_residual` are also surfaced directly, read verbatim off
    `assessment` when one exists, for the same ergonomic-access
    convenience `materials.trajectory.TrajectoryPrediction` already
    established -- never recomputed, never guessed when `assessment` is
    `None` (no observation was supplied for this transition)."""

    predecessor_state_id: str
    successor_state_id: str
    candidate_id: str
    model_state_key: str
    previous_prediction: Prediction
    new_prediction: Prediction
    delta_predicted_value: Optional[float]
    delta_uncertainty: Optional[float]
    assessment: Optional[PredictionAssessment]
    observation_value: Optional[float]
    residual_against_previous_prediction: Optional[float]
    absolute_residual: Optional[float]


@dataclass(frozen=True)
class StateTransitionDiagnosticSet:
    """One `diagnose_transitions` call's complete, ordered result --
    one `StateTransitionDiagnostic` per consecutive pair of entries in
    the supplied trajectory (`len(trajectory.entries) - 1` of them;
    empty for a single-state trajectory, which has no transition to
    diagnose)."""

    candidate_id: str
    diagnostics: Tuple[StateTransitionDiagnostic, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))


def diagnose_transitions(
    trajectory: ModelStateTrajectory,
    candidate: ActionCandidate,
    assessments: Tuple[PredictionAssessment, ...] = (),
) -> StateTransitionDiagnosticSet:
    """Deterministic, side-effect-free, read-only. Computes
    `materials.trajectory.prediction_evolution(trajectory, candidate,
    assessments)` once, then pairs each consecutive pair of steps via
    `materials.trajectory.compare_predictions` -- no new prediction math,
    no re-derivation of anything `prediction_evolution` already
    established. The residual reported for a given transition is always
    the PREDECESSOR step's own assessment (the observation that actually
    produced the successor state), never the successor's unrelated one.

    Never mutates `trajectory`, `candidate`, or `assessments`."""
    steps = prediction_evolution(trajectory, candidate, assessments)
    diagnostics = []
    for previous, current in zip(steps, steps[1:]):
        delta = compare_predictions(previous.prediction, current.prediction)
        diagnostics.append(StateTransitionDiagnostic(
            predecessor_state_id=previous.prediction.state_id,
            successor_state_id=current.prediction.state_id,
            candidate_id=candidate.id,
            model_state_key=previous.prediction.model_state_key,
            previous_prediction=previous.prediction, new_prediction=current.prediction,
            delta_predicted_value=delta.delta_predicted_value, delta_uncertainty=delta.delta_uncertainty,
            assessment=previous.assessment,
            observation_value=previous.observed_value,
            residual_against_previous_prediction=previous.residual,
            absolute_residual=(previous.assessment.absolute_residual if previous.assessment is not None else None),
        ))
    return StateTransitionDiagnosticSet(candidate_id=candidate.id, diagnostics=tuple(diagnostics))
