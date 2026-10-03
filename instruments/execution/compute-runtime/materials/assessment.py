"""assess(prediction, result, observation) -> PredictionAssessment: the
missing primitive between Phase 52-53's `predict`/`update` -- the
explicit relationship between a `Prediction` and the `Observation` that
follows it.

Before writing this module, `materials/model_state.py`, `materials/
results.py`, `materials/information.py`, `materials/surrogate.py`,
`materials/iteration.py`, and `materials/candidates.py` were re-read.
The finding: `predict`/`update` already give the pipeline a full
state-transition loop (`ModelState_t -> Prediction_t -> ... ->
ModelState_(t+1)`), but nothing anywhere COMPARES a `Prediction` against
the `Observation` that later arrives for the same cell -- there is no
representation of "how far off was this prediction" anywhere in
`materials/`. This module adds exactly that comparison, nothing more.

CORRESPONDENCE -- Phase 54's own investigation question: what ties a
`Prediction` to the `Observation` that follows it? NOT property name
(two different formulations/candidates can share a property string) and
NOT array/call-site position (this codebase has never used positional
correspondence for identity anywhere -- every join is by an explicit,
stable id). The one stable id available on both sides is
`ActionCandidate.id`: `Prediction.candidate_id` is set by `predict()`
directly from the candidate it was computed against; `ExperimentalResult.
candidate_id` is set by `make_experimental_result()` from the campaign
entry's own candidate (Phase 44). `Observation` itself carries neither a
candidate id nor a formulation link (Phase 44's own module docstring
already establishes this -- that link lives externally, in a
`ClaimedRelationship`) -- so `assess()` never tries to derive
correspondence FROM an `Observation` alone; it is always given the
`ExperimentalResult` that names which candidate `observation` fulfills,
exactly the same two-object handoff `materials.model_state.update`
already requires. Matching on `prediction.candidate_id == result.
candidate_id` is sufficient, not merely convenient: `ActionCandidate.id`
is content-addressed from `action_class` + the sorted requirement
identities that targeted requirement encodes formulation/property/role/
criterion_context into (`materials.candidates.requirement_identity`), so
two objects agreeing on `candidate_id` are already guaranteed -- by
construction, not by a second check this module would have to perform
itself -- to agree on formulation, property, and target_context too.
`assess()` asserts this one identity check (the same "one cheap, free
check available" discipline `materials.model_state.update` already
established for its own `candidate.id == result.candidate_id` check),
and trusts the rest, like every other layer in this pipeline trusts an
already-constructed object handed to it.

RESIDUAL: `observed_value - predicted_value`, SIGNED. A positive
residual means the observation exceeded the prediction; negative means
it fell short. This module never collapses that into an absolute value
only -- `absolute_residual` is offered ALONGSIDE the signed `residual`,
never as a replacement for it, mirroring `materials.analysis.Disagreement`
keeping `spread` (already unsigned) separate from `minimum`/`maximum`
(which retain the sign information a caller needs to know which
direction things differ). `residual`/`absolute_residual` are `None`
exactly when `prediction.predicted_value` is `None` (the state had zero
samples for this cell when the prediction was made) -- never defaulted
to zero, the same discipline every `Optional[float]` in this pipeline
already follows.

SCIENTIFIC BOUNDARY, deliberately enforced by what this module does NOT
compute: no significance test, no confidence interval, no likelihood, no
p-value, no "model quality" score, and no interpretation of what a
residual MEANS. A residual is not model failure, not experimental
failure, not truth, not bias, and not a causal explanation -- it is only
`observed_value - predicted_value`, a fact about one pair. This
reference model's own statistics (a sample mean and, for 2+ samples, a
population variance -- `materials.model_state`'s own documented scope)
support nothing stronger than that difference, and nothing stronger is
manufactured here. A `PredictionAssessment` also never overwrites or
supersedes the `Prediction` it evaluates: both remain independent,
embedded-whole historical artifacts (see `PredictionAssessment`'s own
fields) -- assessing a prediction is not the same act as the state
transition that follows it; `materials.model_state.update` remains the
only place `ModelState_(t+1)` is ever produced, and it does not require
a `PredictionAssessment` as input (an assessment is diagnostic, read
afterward -- not a precondition the update transition depends on).

BOUNDARY: this module reads only already-constructed `Prediction`/
`ExperimentalResult`/`Observation` objects. No `EvidencePool` access, no
`RetrievalEngine` access, no mutation of any argument, no import of
`evidence.admission`. `materials.results.admit_experimental_result`
remains the sole write boundary; this module does not touch it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from evidence.types import Observation
from materials.model_state import Prediction
from materials.results import ExperimentalResult


@dataclass(frozen=True)
class PredictionAssessment:
    """One evaluated (prediction, observation) pair. `prediction`,
    `result`, and `observation` are embedded whole and unmodified -- full
    provenance (which `ModelState`/candidate produced the prediction;
    which campaign/candidate/formulation/property the result concerns;
    which admitted SCOUT fact the observation actually is) without
    duplicating any of it. `candidate_id`/`state_id` are also surfaced
    directly (read off `prediction`) purely for ergonomic access, the
    same convenience every `materials/` layer since Phase 38 already
    offers alongside its embedded objects."""

    candidate_id: str
    state_id: str
    prediction: Prediction
    result: ExperimentalResult
    observation: Observation
    observed_value: float
    predicted_value: Optional[float]
    residual: Optional[float]
    absolute_residual: Optional[float]


def assess(prediction: Prediction, result: ExperimentalResult, observation: Observation) -> PredictionAssessment:
    """Deterministic, side-effect-free, read-only -- a pure function of
    its three arguments. Never touches `EvidencePool`/`RetrievalEngine`;
    never mutates `prediction`, `result`, or `observation`.

    Correspondence is established by `prediction.candidate_id ==
    result.candidate_id` (see module docstring for why this one check is
    sufficient); a caller that assesses a prediction against a result
    for a DIFFERENT candidate has made an error this function actively
    rejects rather than silently comparing unrelated numbers."""
    assert prediction.candidate_id == result.candidate_id, (
        f"prediction.candidate_id {prediction.candidate_id!r} does not match "
        f"result.candidate_id {result.candidate_id!r} -- assess() requires a "
        "Prediction and ExperimentalResult that concern the same ActionCandidate"
    )
    value = observation.content.get("value")
    assert isinstance(value, (int, float)), f"expected a numeric Observation.content['value'], got {value!r}"
    observed_value = float(value)

    predicted_value = prediction.predicted_value
    if predicted_value is None:
        residual: Optional[float] = None
        absolute_residual: Optional[float] = None
    else:
        residual = observed_value - predicted_value
        absolute_residual = abs(residual)

    return PredictionAssessment(
        candidate_id=prediction.candidate_id, state_id=prediction.state_id,
        prediction=prediction, result=result, observation=observation,
        observed_value=observed_value, predicted_value=predicted_value,
        residual=residual, absolute_residual=absolute_residual,
    )
