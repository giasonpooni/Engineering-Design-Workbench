"""SurrogateInformationValueModel: the first genuine mathematical
implementation behind Phase 50's `InformationValueModel` seam --
variance-reduction, the simplest honest formulation of "how much would
this experiment be expected to reduce predictive uncertainty":

    information_value = current_variance - expected_variance_after

Before writing this module, `materials/information.py`, `materials/value.py`,
`materials/candidates.py`, `materials/iteration.py`, `materials/decision.py`,
and `evidence.types` were inspected. None of them contains, or pretends to
contain, a predictive/surrogate model -- there is no variance, posterior,
or uncertainty-over-a-future-observation anywhere in the SCOUT substrate
or in any `materials/` layer built so far (`Observation.confidence`/
`DerivedValue.confidence` are scalar annotations about an ALREADY-MADE
extraction or derivation, never a prediction about a value not yet
obtained). This module therefore does not invent that state out of the
existing evidence; it requires the caller to supply it explicitly, per
candidate, as a `SurrogateState`.

`SurrogateState` is keyed by `ActionCandidate.id` (via
`CandidateInformationValue.candidate_id`, itself untouched since
Phase 37) -- no second candidate identity system. The caller constructs
`SurrogateInformationValueModel(states={candidate_id: SurrogateState(...), ...})`
once, and it satisfies Phase 50's `InformationValueModel` Protocol
exactly like `NullInformationValueModel` already does.

FOUR explicit rejection cases, each returning `(None, reason)` -- never
an invented number, never a silent zero:

  1. `current_variance` not supplied           -> NOT_DETERMINABLE
  2. `expected_variance_after` not supplied     -> NOT_DETERMINABLE
  3. either value is non-finite (NaN/inf)       -> NOT_DETERMINABLE
  4. no SurrogateState was supplied for this
     candidate at all                          -> NOT_DETERMINABLE

A NEGATIVE result (`expected_variance_after > current_variance` --
the experiment's predicted effect is to INCREASE uncertainty) is
deliberately NOT case 5: it is a mathematically valid, if unusual,
output of `current - after`, and is returned exactly as computed, with
an honest note in `basis`. Clamping it to zero would silently discard
information the caller's own predictive state expressed; this module
never does that.

Variance values are taken at face value from the caller-supplied
`SurrogateState` -- this module does not independently validate that
they represent a physically meaningful variance (e.g. non-negative).
That is the responsibility of whatever produced the state, the same way
`materials.utility.ExperimentUtilityInput.benefit`/`.cost` are taken at
face value rather than second-guessed.

Boundary, verified by inspection and by this module's own imports: no
`EvidencePool`, no `RetrievalEngine`, no observation retrieval, no
evidence mutation, no inspection of raw SCOUT state. `estimate()`
receives only a `CandidateInformationValue` (Phase 46's structural
facts) and never reads `.property`, `.criterion`, `.current_status`,
`.role`, or `.value_kind` from it to COMPUTE the number -- only
`.candidate_id`, to look up the caller-supplied state. No observation
count, PASS/FAIL, candidate rank, or utility value is used anywhere in
this module. No experiment selection or optimization exists here either.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

from materials.value import CandidateInformationValue


@dataclass(frozen=True)
class SurrogateState:
    """A caller-supplied predictive state for one candidate -- current
    predictive variance and the variance expected after the candidate's
    experiment is performed, in whatever units the caller's own
    predictive model uses. Both default to `None` ("not supplied"),
    the same "caller supplies nothing is a valid, common case"
    discipline `materials.utility.ExperimentUtilityInput` already
    established."""

    current_variance: Optional[float] = None
    expected_variance_after: Optional[float] = None


def _compute(state: SurrogateState) -> Tuple[Optional[float], Optional[str]]:
    current = state.current_variance
    after = state.expected_variance_after

    if current is None:
        return None, "current_variance was not supplied"
    if after is None:
        return None, "expected_variance_after was not supplied"
    if not math.isfinite(current) or not math.isfinite(after):
        return None, "current_variance/expected_variance_after must be finite"

    value = current - after
    if value < 0:
        return value, (
            f"variance_reduction = current_variance({current!r}) - expected_variance_after({after!r}) "
            f"= {value!r} -- negative: the supplied predictive state expects variance to INCREASE, "
            f"reported honestly rather than clamped to zero"
        )
    return value, f"variance_reduction = current_variance({current!r}) - expected_variance_after({after!r}) = {value!r}"


class SurrogateInformationValueModel:
    """Implements `materials.information.InformationValueModel`. `states`
    is a plain `Mapping[str, SurrogateState]` keyed by `ActionCandidate.id`,
    supplied once at construction -- mirrors the keyed-by-candidate_id
    convention `materials.design`/`materials.utility` already established
    for `design_parameters`/`methods`/`utility_inputs`."""

    name = "surrogate:variance_reduction"

    def __init__(self, states: Mapping[str, SurrogateState]) -> None:
        self._states = dict(states)

    def estimate(self, information_value: CandidateInformationValue) -> Tuple[Optional[float], Optional[str]]:
        state = self._states.get(information_value.candidate_id)
        if state is None:
            return None, "no SurrogateState was supplied for this candidate"
        return _compute(state)
