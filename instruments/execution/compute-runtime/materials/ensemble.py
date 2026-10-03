"""CounterfactualOutcome + CounterfactualSet +
evaluate_counterfactual_information_value: Phase 59's smallest formal
representation of a BRANCHING set of possible successor states --

    S_t
      |
      +-- y_1 --> S'_1 --> IV_1
      +-- y_2 --> S'_2 --> IV_2
      +-- y_3 --> S'_3 --> IV_3

-- and, ONLY when a caller explicitly supplies a probability for every
branch, the mathematically honest aggregate:

    E[IV] = sum_i p_i * IV_i

Before writing this module, `materials/counterfactual.py`, `materials/
model_state.py`, `materials/information.py`, `materials/surrogate.py`,
`materials/trajectory.py`, `materials/diagnostics.py`, `materials/
value.py`, `materials/utility.py`, and `materials/optimization.py` were
re-read. Finding: `materials.counterfactual.project_update` (Phase 58)
already computes exactly one branch (`S_t + hypothetical y -> S'_y`);
`materials.trajectory.compare_predictions` (Phase 56) already computes
the delta between two `Prediction`s; `materials.information.
estimate_information_value` + `materials.model_state.
ModelStateInformationValueModel` (Phase 50/52) already compute
information value for any single `ModelState`. NONE of this is
duplicated here. What did not exist: (1) a representation naming SEVERAL
branches from the SAME source state/candidate together, so a caller can
reason about "the possible futures" as one object rather than several
independent, uncorrelated function calls; and (2) the Sigma p_i * IV_i
aggregate itself, which is new arithmetic (though trivial) that exists
nowhere else in this codebase. Both are genuinely new; nothing else in
this module is.

--------------------------------------------------------------------
BRANCH REPRESENTATION (Phase 59 sec.2/3): `CounterfactualOutcome` is
built by `project_outcome(state, candidate, hypothetical_value,
probability=None)`, which does nothing but call `project_update`
(one branch), `predict` (before AND after, so `compare_predictions` --
already-existing Phase 56 math -- can compute the delta), and package
the results together with the identities Phase 59 sec.3 requires
(`source_state_id`, `candidate_id`, `model_state_key`,
`hypothetical_value`, `projected_state_id`) plus the embedded whole
`projected_state`/`prediction_after`/`delta` objects for full
provenance without duplication.

`probability` defaults to `None` -- "not supplied," the same "caller
supplies nothing is a valid, common case" discipline `materials.
surrogate.SurrogateState`/`materials.utility.ExperimentUtilityInput`
already established. It is NEVER inferred by this module from sample
frequency, residuals, prediction value, utility, ranking, candidate
identity, or observation counts -- Phase 59 sec.4's own explicit
prohibition. A caller who supplies one takes it at face value (this
module does not validate that a set of supplied probabilities sums to
1, or that any single value lies in `[0, 1]` -- the same "taken at face
value, not second-guessed" discipline `materials.surrogate.
SurrogateState`'s own variance values already established; the
responsibility for producing a meaningful distribution belongs to
whatever supplied it).

`CounterfactualSet` names several `CounterfactualOutcome`s branching
from the SAME `source_state_id`/`candidate_id` -- `make_counterfactual_set`
verifies this (the one cheap, free consistency check available, same
discipline `materials.trajectory.make_model_state_trajectory` already
applies to its own sequence), rejecting a mixed-source/mixed-candidate
set with `ValueError` rather than silently accepting one. No branch
mutates another, or the source state: every `ModelState`/`Prediction`
involved is exactly as immutable as it already was (Phase 52/55/58,
unchanged).

--------------------------------------------------------------------
INFORMATION VALUE (Phase 59 sec.6/7): `branch_information_values` is
computed by calling the EXISTING `materials.information.
estimate_information_value(candidate, iteration,
ModelStateInformationValueModel(outcome.projected_state))` once per
outcome -- no new information-value mathematics. `expected_information_value`
is the one genuinely new number this module adds: `sum(p_i * IV_i)`,
computed ONLY when EVERY outcome in the set carries a non-`None`
`probability` AND every branch's information-value estimate is itself
`ESTIMATED` (not `NOT_DETERMINABLE`) -- if either is missing for even
ONE branch, `expected_information_value` is `None`/`NOT_DETERMINABLE`
for the WHOLE set, never a partial sum over the branches that happened
to have both: a sum over a strict subset of branches is a different,
smaller mathematical quantity than the true expectation over all of
them, and reporting it under the same name would misrepresent it.

This module never merges information value with utility, never ranks
branches, and never selects one: `materials.utility`/`materials.ranking`/
`materials.optimization` remain the ONLY layers that consume a
`CandidateUtility`/produce an ordering/make a selection, and none of
them is imported here. This module describes possible futures; it does
not choose one (Phase 59 sec.7).

--------------------------------------------------------------------
THE P(y | S_t, candidate) SEAM (Phase 59 sec.9): `probability` on
`CounterfactualOutcome` IS the seam a future outcome-distribution model
would fill (mirroring `materials.information.InformationValueModel`'s
own role as the seam a future scientific model fills, established
Phase 50) -- a plain `Optional[float]` field, not a `Protocol`. No
`OutcomeDistributionModel` interface is extracted here: with no second
implementation yet demanding a different shape (exactly the "structurally
ready, not yet necessary, defer" discipline this project has applied
repeatedly, e.g. Phase 52's deferred `SurrogateModel` Protocol), doing so
now would be premature abstraction. The correct state this module
establishes is exactly Phase 59 sec.9's own words: "possible branches
known + probabilities unknown," never "guessed probabilities" -- this
module has, and fabricates, no basis for the latter.

--------------------------------------------------------------------
EPISTEMIC BOUNDARY (Phase 59 sec.10): inherited structurally from
`materials.counterfactual.project_update`, not merely by convention --
`project_outcome`/`make_counterfactual_set`/
`evaluate_counterfactual_information_value` take no `EvidencePool`
parameter anywhere in this module, so none of them can read or write
one, admit an `Observation`, affect `pool.fingerprint()`/a fingerprint
history, add a provenance entry, or become reachable through
`retrieval.engine`/any `RetrievalResult`/`ContextPackage`. A
`CounterfactualOutcome`'s `projected_state` remains exactly what
`project_update` already guaranteed: a purely computational,
in-memory-only possibility, permanently distinguishable from real
evidence by its samples' `"hypothetical:"`-prefixed ids.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from materials.candidates import ActionCandidate
from materials.counterfactual import project_update
from materials.information import ESTIMATED, InformationValueEstimate, estimate_information_value
from materials.iteration import MaterialsIteration
from materials.model_state import (
    ModelState, ModelStateInformationValueModel, Prediction, predict, resolve_model_state_key,
)
from materials.trajectory import PredictionDelta, compare_predictions
from materials.utility import NOT_DETERMINABLE


@dataclass(frozen=True)
class CounterfactualOutcome:
    """One branch: `S_t + hypothetical y -> S'_y`, plus the prediction
    read from `S'_y` and its delta against the prediction read from
    `S_t` -- all computed via already-existing Phase 52/56/58 machinery,
    never re-derived. `probability` is `None` unless a caller explicitly
    supplies one (see module docstring for why it is never inferred)."""

    source_state_id: str
    candidate_id: str
    model_state_key: str
    hypothetical_value: float
    projected_state: ModelState
    projected_state_id: str
    prediction_after: Prediction
    delta: PredictionDelta
    probability: Optional[float] = None


def project_outcome(
    state: ModelState, candidate: ActionCandidate, hypothetical_value: float, probability: Optional[float] = None,
) -> CounterfactualOutcome:
    """Deterministic, side-effect-free, read-only. Builds exactly one
    `CounterfactualOutcome` by composing `materials.counterfactual.
    project_update`, `materials.model_state.predict`, and
    `materials.trajectory.compare_predictions` -- no new prediction or
    transition math. Never mutates `state` or `candidate`."""
    prediction_before = predict(state, candidate)
    projected_state = project_update(state, candidate, hypothetical_value)
    prediction_after = predict(projected_state, candidate)
    delta = compare_predictions(prediction_before, prediction_after)
    key = resolve_model_state_key(candidate.formulation.id, candidate.property, candidate.target_context)
    return CounterfactualOutcome(
        source_state_id=state.id, candidate_id=candidate.id, model_state_key=key,
        hypothetical_value=float(hypothetical_value), projected_state=projected_state,
        projected_state_id=projected_state.id, prediction_after=prediction_after, delta=delta,
        probability=probability,
    )


@dataclass(frozen=True)
class CounterfactualSet:
    """Several `CounterfactualOutcome`s branching from the SAME
    `source_state_id`/`candidate_id` -- an unweighted set of possible
    futures unless every outcome carries an explicit `probability`. This
    is a computed grouping, not a mutable registry: nothing here is ever
    looked up from a store, and no outcome is ever mutated by
    constructing this set."""

    source_state_id: str
    candidate_id: str
    outcomes: Tuple[CounterfactualOutcome, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "outcomes", tuple(self.outcomes))


def make_counterfactual_set(outcomes: Tuple[CounterfactualOutcome, ...]) -> CounterfactualSet:
    """The only supported way to construct a `CounterfactualSet`.
    Verifies every outcome shares the same `source_state_id`/
    `candidate_id` -- the one cheap, free consistency check available
    (an `ActionCandidate.id` already encodes formulation/property/
    target_context, so matching `candidate_id` alone is sufficient,
    exactly the argument `materials.assessment.assess`/`materials.
    trajectory.compare_predictions` already establish for their own
    single-identity checks). Raises `ValueError` for a mixed-source or
    mixed-candidate set rather than silently accepting one."""
    if not outcomes:
        raise ValueError("CounterfactualSet requires at least one CounterfactualOutcome")
    source_state_id = outcomes[0].source_state_id
    candidate_id = outcomes[0].candidate_id
    for outcome in outcomes:
        if outcome.source_state_id != source_state_id or outcome.candidate_id != candidate_id:
            raise ValueError(
                f"CounterfactualSet requires every outcome to share the same source_state_id "
                f"({source_state_id!r}) and candidate_id ({candidate_id!r}); got "
                f"source_state_id={outcome.source_state_id!r}, candidate_id={outcome.candidate_id!r}"
            )
    return CounterfactualSet(source_state_id=source_state_id, candidate_id=candidate_id, outcomes=tuple(outcomes))


@dataclass(frozen=True)
class CounterfactualInformationValue:
    """`branch_information_values` -- one `InformationValueEstimate` per
    outcome in `counterfactual_set.outcomes`, same order, computed via
    the EXISTING Phase 50/52 seam, never new mathematics.
    `expected_information_value` is `sum(p_i * IV_i)`, computed ONLY
    when every branch carries both a supplied `probability` and an
    `ESTIMATED` information-value -- `NOT_DETERMINABLE` (never a partial
    sum, never a guess) otherwise. See module docstring for why a
    partial sum is not offered under this name."""

    candidate_id: str
    source_state_id: str
    branch_information_values: Tuple[InformationValueEstimate, ...]
    expected_information_value: Optional[float]
    expected_information_value_status: str


def evaluate_counterfactual_information_value(
    counterfactual_set: CounterfactualSet, candidate: ActionCandidate, iteration: MaterialsIteration,
) -> CounterfactualInformationValue:
    """Deterministic, side-effect-free, read-only. Never touches
    `EvidencePool`/`RetrievalEngine`; never mutates `counterfactual_set`,
    `candidate`, or `iteration`. Never ranks or selects among branches --
    `materials.ranking`/`materials.optimization`/`materials.utility` are
    not imported here and remain the only layers that do that."""
    branch_values = tuple(
        estimate_information_value(candidate, iteration, ModelStateInformationValueModel(outcome.projected_state))
        for outcome in counterfactual_set.outcomes
    )
    probabilities = tuple(outcome.probability for outcome in counterfactual_set.outcomes)

    all_probabilities_supplied = all(p is not None for p in probabilities)
    all_estimates_determined = all(v.estimate is not None for v in branch_values)
    expected: Optional[float]
    if all_probabilities_supplied and all_estimates_determined:
        total = 0.0
        for p, v in zip(probabilities, branch_values):
            assert p is not None and v.estimate is not None  # guaranteed by the checks above
            total += p * v.estimate
        expected = total
        status = ESTIMATED
    else:
        expected = None
        status = NOT_DETERMINABLE

    return CounterfactualInformationValue(
        candidate_id=candidate.id, source_state_id=counterfactual_set.source_state_id,
        branch_information_values=branch_values,
        expected_information_value=expected, expected_information_value_status=status,
    )
