"""estimate_information_value(candidate, current_iteration, model) ->
InformationValueEstimate: a formal, caller-supplied model SEAM for
turning `materials.value`'s structural facts about a candidate into an
epistemic number -- expected information gain, posterior entropy
reduction, expected variance reduction, expected improvement, mutual
information, or whatever a future scientific model computes. This
module implements NONE of those algorithms; it only defines the
interface a future one would plug into, and ships exactly one reference
implementation (`NullInformationValueModel`) that always returns
NOT_DETERMINABLE, proving the plumbing without making any scientific
claim.

THE ARCHITECTURAL DISTINCTION THIS MODULE EXISTS TO PRESERVE: the
materials application already knows WHAT information is missing
(`materials.experiment`'s gap categories), WHAT would close it
(`materials.specification`'s requirements), and WHAT possible actions
could obtain it (`materials.candidates`) -- but nothing anywhere in
`materials/analysis.py` through `materials/candidates.py` (inspected
before writing this module, along with `materials/value.py`,
`materials/evaluation.py`, `materials/decision.py`) knows HOW VALUABLE
resolving a given gap is. `materials.value.CandidateInformationValue`
already draws this line correctly (`expected_information_gain` is
always `NOT_DETERMINABLE` there too) -- this module does not change
that; it adds the one thing Phase 46 deliberately left as a seam: a
place a real model can be plugged in.

`InformationValueModel` is a `Protocol` -- the exact same extension-seam
pattern `retrieval.engine.RetrievalEngine` already establishes for
retrieval quality: a future SurrogateModelInformationValue /
PosteriorEntropyInformationValue / ExpectedImprovementInformationValue
implements this same interface and this module never changes underneath
it. `estimate()` receives ONLY the already-computed
`CandidateInformationValue` (Phase 46's structural facts) -- never
`EvidencePool`, never `RetrievalEngine`, never raw `Observation`/
`DerivedValue` objects. This is the hard boundary: a model may use
whatever mathematics or external knowledge it has, but it may not reach
back into the substrate itself, and this module's own code never
computes a number from `information_value.property`, `.criterion`,
`.current_status` (PASS/FAIL/etc.), the number of observations, a
candidate's rank, its utility, or its `action_class` -- those are
structural facts a MODEL may choose to consume, but none of them is by
itself sufficient grounds for a value estimate, and this module never
treats them as if it were.

Two states, reusing `materials.utility.NOT_DETERMINABLE` directly (not
redefined): `ESTIMATED` (the model returned a number) and
`NOT_DETERMINABLE` (it returned `None` -- its own honest "I cannot
produce this," never defaulted to zero or inferred from anything else).

Each `InformationValueEstimate` embeds the complete, unmodified
`CandidateInformationValue` -- the full candidate -> requirement -> gap
-> audit -> decision -> evidence/provenance chain stays reachable
without duplicating any of it. No new identity system: `candidate_id`
is exactly `ActionCandidate.id`, untouched since Phase 37.

No ranking, optimization, utility, recommendation, experiment
selection, Bayesian optimization, active learning, LLM call, database
write, or `EvidencePool` access exists anywhere in this module.
`materials.results` remains the sole write boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Tuple

from materials.candidates import ActionCandidate, CandidateSet
from materials.iteration import MaterialsIteration
from materials.utility import NOT_DETERMINABLE
from materials.value import CandidateInformationValue, evaluate_information_value

ESTIMATED = "ESTIMATED"


class InformationValueModel(Protocol):
    """The extension seam. `name` identifies which model produced an
    estimate -- an open string, the same convention
    `evidence.types.DerivedValue.method` already establishes for
    "which technique produced this," never a closed enum. `estimate`
    is a pure function of the structural facts it is given; it must not
    reach into `EvidencePool`/`RetrievalEngine` (nothing in this
    module's own contract gives it the means to).

    Declared as a read-only `@property` (Phase 59 fix) rather than a
    plain `name: str` field: a plain field is INVARIANT under mypy's
    structural typing -- it requires an implementation with a settable
    attribute of the exact same type -- which rejects an otherwise
    perfectly valid implementation like `materials.model_state.
    ModelStateInformationValueModel.name` that computes its name from
    instance state (`f"model_state:{self._state.id}"`) via a read-only
    `@property`, since a class cannot honestly offer a SETTABLE `name`
    that also derives from immutable instance data. A property-typed
    protocol member accepts both a read-only property AND a plain class
    attribute (`NullInformationValueModel.name`/`SurrogateInformationValueModel.
    name`, both unchanged) as valid implementations -- this widens the
    contract to what every existing and intended implementation actually
    needs (read access only; nothing in this codebase ever assigns to
    `model.name`), without weakening it in any way that matters."""

    @property
    def name(self) -> str: ...

    def estimate(self, information_value: CandidateInformationValue) -> Tuple[Optional[float], Optional[str]]:
        """Returns (value, basis). `value=None` means the model itself
        cannot produce an estimate for this candidate -- its own
        NOT_DETERMINABLE, never a zero. `basis` is an optional
        free-text account of how the value was reached; it is never
        required and never interpreted by this module."""
        ...


class NullInformationValueModel:
    """The one reference implementation this module ships: always
    NOT_DETERMINABLE. Proves `InformationValueModel` actually plugs into
    `estimate_information_value` without asserting any scientific
    relationship this architecture has no mathematical state to
    support -- the honest default until a real model is supplied."""

    name = "null:not_determinable"

    def estimate(self, information_value: CandidateInformationValue) -> Tuple[Optional[float], Optional[str]]:
        return None, "no information value model has been supplied"


@dataclass(frozen=True)
class InformationValueEstimate:
    """One candidate's model-supplied estimate. `information_value` is
    the complete, unmodified Phase 46 `CandidateInformationValue` --
    full provenance without duplicating any of it."""

    candidate_id: str
    information_value: CandidateInformationValue
    model_name: str
    estimate: Optional[float]
    estimate_status: str
    basis: Optional[str]


@dataclass(frozen=True)
class InformationValueEstimateSet:
    process_natural_key: str
    candidate_set: CandidateSet
    model_name: str
    estimates: Tuple[InformationValueEstimate, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "estimates", tuple(self.estimates))


def estimate_information_value(
    candidate: ActionCandidate, current_iteration: MaterialsIteration, model: InformationValueModel
) -> InformationValueEstimate:
    """Deterministic, side-effect-free, read-only, PROVIDED `model.estimate`
    is itself deterministic and pure -- exactly the same documented
    contract `materials.candidates`'s injected objective would have
    needed under Phase 36's Alternative 3, now actually exercised here.
    This function itself never touches EvidencePool/RetrievalEngine and
    never mutates `candidate`, `current_iteration`, or `model`."""
    information_value = evaluate_information_value(candidate, current_iteration)
    value, basis = model.estimate(information_value)
    status = ESTIMATED if value is not None else NOT_DETERMINABLE
    return InformationValueEstimate(
        candidate_id=candidate.id, information_value=information_value, model_name=model.name,
        estimate=value, estimate_status=status, basis=basis,
    )


def estimate_information_values(
    candidate_set: CandidateSet, current_iteration: MaterialsIteration, model: InformationValueModel
) -> InformationValueEstimateSet:
    """Evaluates every candidate in `candidate_set` independently against
    the same `model` -- never ranks, scores for selection, or compares
    one against another. Ordering: canonical `ActionCandidate.id` order,
    independent of insertion order, dict/set iteration, or
    PYTHONHASHSEED."""
    ordered = tuple(sorted(candidate_set.candidates, key=lambda c: c.id))
    estimates = tuple(estimate_information_value(c, current_iteration, model) for c in ordered)
    return InformationValueEstimateSet(
        process_natural_key=candidate_set.process_natural_key, candidate_set=candidate_set,
        model_name=model.name, estimates=estimates,
    )
