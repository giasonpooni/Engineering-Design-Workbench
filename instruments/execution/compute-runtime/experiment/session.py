"""ExperimentSession: the active state reference
`docs/EXPERIMENT_ARCHITECTURE.md` §3.1 specifies. Immutable, exactly
like every object beneath it -- "maintaining the active state
reference" means the caller holds the latest `ExperimentSession`
returned by `experiment.step.run_experiment_step`; nothing here is ever
mutated in place. Advancing one step produces a NEW `ExperimentSession`,
the same way `materials.model_state.update` produces a new `ModelState`
rather than mutating the old one -- a deliberate choice, not an
oversight: introducing the first mutable object in this codebase at the
exact layer meant to DRIVE the immutable algebra beneath it would
undermine every determinism guarantee Phases 52-61 already proved.

`state_history` is the raw, ordered tuple of every `ModelState` this
session has passed through (starting with `initial_state`, most
commonly `materials.model_state.EMPTY_MODEL_STATE`) -- a
`materials.trajectory.ModelStateTrajectory` is deliberately NOT stored
here (it would be a derived quantity duplicated alongside its own
source, exactly what Phase 55 already established `ModelState` itself
must never do with mean/variance); a caller who wants one calls
`materials.trajectory.make_model_state_trajectory(session.state_history)`
directly -- see `trajectory_of` below, a one-line convenience, not new
math.

Never touches `EvidencePool` beyond holding a reference to it -- this
module itself calls no `put_*`/`admit_*`; that boundary is enforced by
`tests/test_experiment_boundaries.py`.

PHASE 66 -- THE SESSION AS INTERACTION BOUNDARY: `experiment.step.
run_experiment_step` remains the fully-automated path (decide, dispatch,
admit, advance, in one call). This phase adds a SMALLER-grained surface
for a caller who wants to drive the loop manually -- inspect a
prediction, look at hypothetical outcomes, and only then decide what to
submit -- without reproducing any mathematics. Each method below is a
thin composition of an already-existing `materials/` primitive, bound to
`self.state`/`self.iteration`; none computes anything new. Every
candidate operation this phase considered was checked against six
questions (does an existing primitive already provide it; does the
session merely need to expose/combine it; does it introduce new state
ownership; new identity; new mathematics; does it cross the
`EvidencePool` write boundary) -- see this module's own tests and the
Phase 66 report for the operations that were considered and DECLINED
(candidate generation, information-value/utility inspection, "last
assessment" storage, and a `choose_action`/dispatch method) because
`materials/`'s own functions, or `run_experiment_step` itself, already
serve them with zero session involvement needed.

`ExperimentSession.observe` is the one place this phase's own
illustrative interaction sketch (`assessment = session.observe(...);
next_state = session.state`) could not be implemented completely
literally without breaking the "no mutation, ever" discipline this
module's own docstring already establishes as load-bearing (Phase
63/64). Introducing the first mutable object in this codebase at the
exact layer meant to drive the immutable algebra beneath it would
undermine every determinism guarantee Phases 52-61 proved -- not a
cosmetic preference, the one invariant Phase 65's audit specifically
re-verified holds. `observe` therefore returns `(assessment,
new_session)` rather than mutating `self` -- one extra rebind
(`assessment, session = session.observe(...)`) preserves the exact
ergonomics the sketch wants while keeping the object model honest."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from evidence.pool import EvidencePool
from evidence.types import Observation
from materials.assessment import PredictionAssessment, assess
from materials.candidates import ActionCandidate
from materials.ensemble import CounterfactualOutcome, project_outcome
from materials.iteration import MaterialsIteration
from materials.model_state import EMPTY_MODEL_STATE, ModelState, Prediction, predict, update
from materials.results import ExperimentalResult
from materials.trajectory import ModelStateTrajectory, make_model_state_trajectory
from retrieval.engine import RetrievalEngine


@dataclass(frozen=True)
class ExperimentSession:
    """S_t plus everything needed to compute the next step -- an
    `EvidencePool`/`RetrievalEngine` pair (read-only from this
    package's own perspective), the current `MaterialsIteration` (the
    engineering assessment this session's decisions are being made
    against), the current `ModelState`, `state_history` (every state
    this session has passed through, in order, starting with whatever
    `initial_state` `make_experiment_session` was given), and
    `document_id` -- an ALREADY-ADMITTED `evidence.types.Document` every
    measurement this session dispatches gets logged against as a new
    `Record` (one lab notebook, many entries -- the caller is
    responsible for having already admitted the Source/Document chain,
    exactly the same discipline `materials.results.ExperimentalResult`
    already established in Phase 44 for its own `record_id`).

    `ModelState` remains the mathematical state (samples, mean,
    variance); `ExperimentSession` is only ever the interaction/
    orchestration context wrapped around one -- it holds `state` by
    reference, computes nothing statistical of its own, and gains no
    field here that would make it a second, competing state
    representation."""

    pool: EvidencePool
    engine: RetrievalEngine
    iteration: MaterialsIteration
    state: ModelState
    state_history: Tuple[ModelState, ...]
    document_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "state_history", tuple(self.state_history))

    def predict(self, candidate: ActionCandidate) -> Prediction:
        """y_hat_t = G(S_t, x) -- `materials.model_state.predict` bound
        to this session's current state. No new mathematics; `inspect
        the current prediction for a candidate` needs nothing more than
        this one call, already proven across Phases 52-61."""
        return predict(self.state, candidate)

    def inspect_counterfactual(
        self, candidate: ActionCandidate, hypothetical_value: float, probability: Optional[float] = None,
    ) -> CounterfactualOutcome:
        """`materials.ensemble.project_outcome` bound to this session's
        current state -- "evaluate a hypothetical outcome" needs nothing
        beyond this one existing, already-complete primitive (Phase 59).
        Never advances the session or touches `EvidencePool`; the
        returned `CounterfactualOutcome.projected_state` is, and
        remains, distinguishable from real history exactly as
        `materials.counterfactual`/`materials.model_state`'s own Phase
        58/61 guarantees already establish."""
        return project_outcome(self.state, candidate, hypothetical_value, probability)

    def observe(
        self, candidate: ActionCandidate, prediction: Prediction, result: ExperimentalResult, observation: Observation,
    ) -> Tuple[PredictionAssessment, "ExperimentSession"]:
        """r_t = y_t - y_hat_t, then S_(t+1) = F(S_t, y_t) -- composes
        `materials.assessment.assess` and `materials.model_state.update`
        exactly as `experiment.step.run_experiment_step` already does
        for its own "receive result -> assess -> advance" portion,
        extracted here as an independently-callable step for a caller
        driving the loop manually.

        `result`/`observation` must already be admitted -- this method
        does NOT call `materials.results.admit_experimental_result`
        itself (the caller does, exactly the same "caller is
        responsible for having already admitted" discipline Phase 44
        established for `update`/`assess` themselves) -- so this method
        never touches `EvidencePool`, directly or indirectly.

        Never mutates `self`; returns `(assessment, new_session)`. See
        this module's own docstring for why returning a new session,
        rather than mutating `self.state` in place, is the one place
        this phase's illustrative sketch was deliberately not
        implemented literally."""
        assessment = assess(prediction, result, observation)
        new_state = update(self.state, candidate, result, observation)
        new_session = ExperimentSession(
            pool=self.pool, engine=self.engine, iteration=self.iteration, state=new_state,
            state_history=self.state_history + (new_state,), document_id=self.document_id,
        )
        return assessment, new_session


def make_experiment_session(
    pool: EvidencePool,
    engine: RetrievalEngine,
    iteration: MaterialsIteration,
    document_id: str,
    initial_state: ModelState = EMPTY_MODEL_STATE,
) -> ExperimentSession:
    """The only supported way to construct a starting `ExperimentSession`
    -- `state_history` always begins as exactly `(initial_state,)`.
    `document_id` must already be admitted in `pool` (this function does
    not check -- the same caller-responsibility discipline
    `materials.results.admit_experimental_result` already applies to
    `result.record_id`)."""
    return ExperimentSession(
        pool=pool, engine=engine, iteration=iteration, state=initial_state,
        state_history=(initial_state,), document_id=document_id,
    )


def trajectory_of(session: ExperimentSession) -> ModelStateTrajectory:
    """Convenience composition, not new math: `materials.trajectory.
    make_model_state_trajectory` applied to this session's own
    `state_history`. Reused rather than re-derived every time a caller
    wants trajectory-level analysis (`materials.trajectory.
    prediction_evolution`, `materials.diagnostics.diagnose_transitions`)
    over a session's history so far."""
    return make_model_state_trajectory(session.state_history)
