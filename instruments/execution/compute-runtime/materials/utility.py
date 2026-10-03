"""evaluate_candidate_utility(information_value, utility_input) ->
CandidateUtility: a transparent, deterministic combination of what the
system already knows (Phase 46's structural information value) with
what an engineering caller explicitly supplies -- never a ranking,
never a score used to pick a winner, never an invented probability or
cost.

Three provenance states, never blurred:

  KNOWN            -- derivable from existing evidence. This is exactly
                       what `materials.value.CandidateInformationValue`
                       already is (Phase 46) -- embedded here whole,
                       never re-derived, never a status this module
                       tags a field with, because nothing in this module
                       computes a NEW known fact; it only consumes one.

  SUPPLIED         -- a quantity the caller explicitly provided
                       (`ExperimentUtilityInput.benefit`/`.cost`). `0.0`
                       is a fully valid supplied value, distinct from
                       "not supplied" -- every check in this module uses
                       `is not None`, never truthiness, so a caller who
                       supplies a zero benefit or zero cost is never
                       silently treated the same as a caller who
                       supplied nothing.

  NOT_DETERMINABLE -- neither known nor supplied. `utility` is
                       `NOT_DETERMINABLE` whenever `benefit` or `cost`
                       (or both) is `None` -- never defaulted to zero,
                       never estimated.

Inspected before writing this module: `materials.value.CandidateInformationValue`
already carries `expected_information_gain = NOT_DETERMINABLE`
(Phase 46, itself reusing `materials.evaluation.NOT_DETERMINABLE`) and
every structural fact (gap category, current status, contexts) a caller
would need to judge benefit/cost by hand. Nothing about `ExperimentSpecification`/
`CandidateSet`/`CandidateEvaluation`/`CandidateSelection` supplies a
number for benefit or cost -- those are engineering judgments, not
retrievable facts, so this module never tries to derive them and instead
defines the smallest input shape that lets a caller state them
explicitly: exactly two optional numbers, `benefit` and `cost`, in
whatever units the caller's own judgment uses. `experiment_duration`/
`material_cost`/`operational_value`/`scientific_value`/`decision_value`/
`failure_probability` (all suggested as possible fields) were considered
and deliberately NOT added as separate fields: none of them is
independently determinable from any existing structure either, and
turning "benefit" and "cost" into a fixed decomposition of named
sub-quantities would be inventing a business/scientific ontology this
architecture has no data to justify -- a caller who wants that
granularity can compute their own `benefit`/`cost` from whatever inputs
they have; this module does not need to know how they got there.

utility = benefit - cost, computed ONLY when both are supplied --
otherwise `utility` is `None` and `utility_status` is
`NOT_DETERMINABLE`, never a default of `0`. No ranking, score used to
pick a winner, probability, cost-optimization, or scheduling logic
exists anywhere in this module; `evaluate_utility_set` evaluates every
candidate independently and never compares one against another.

Reuses `ActionCandidate.id` (via `CandidateInformationValue.candidate_id`,
itself Phase 37's `ActionCandidate.id`, untouched) as the sole identity
-- no parallel identity system is introduced. This module never touches
`EvidencePool`/`RetrievalEngine`: its only inputs are Phase 46's own
output and a caller-supplied mapping.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

from materials.value import CandidateInformationValue, CandidateInformationValueSet

KNOWN = "KNOWN"
SUPPLIED = "SUPPLIED"
NOT_DETERMINABLE = "NOT_DETERMINABLE"


@dataclass(frozen=True)
class ExperimentUtilityInput:
    """Exactly what an engineering caller can state about one candidate
    -- nothing this module derives on its own. `None` means "not
    supplied"; a numeric value (including `0.0`) means "supplied,"
    always distinguishable from absence."""

    benefit: Optional[float] = None
    cost: Optional[float] = None


@dataclass(frozen=True)
class CandidateUtility:
    """One candidate's utility result. `information_value` is the
    complete, unmodified Phase 46 `CandidateInformationValue` -- full
    provenance (candidate -> targeted requirements -> evidence gap ->
    audit -> decision -> evidence/provenance, all already reachable
    through it) without duplicating any of it. `utility_input` is the
    caller-supplied input, embedded unmodified."""

    candidate_id: str
    information_value: CandidateInformationValue
    utility_input: ExperimentUtilityInput
    utility: Optional[float]
    utility_status: str


@dataclass(frozen=True)
class CandidateUtilitySet:
    process_natural_key: str
    candidate_information_values: CandidateInformationValueSet
    utilities: Tuple[CandidateUtility, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "utilities", tuple(self.utilities))


def evaluate_candidate_utility(
    information_value: CandidateInformationValue, utility_input: ExperimentUtilityInput
) -> CandidateUtility:
    """Deterministic, side-effect-free -- a pure function of its two
    arguments. `utility_input.benefit`/`.cost` are checked with
    `is not None`, never truthiness."""
    if utility_input.benefit is not None and utility_input.cost is not None:
        utility: Optional[float] = utility_input.benefit - utility_input.cost
        status = SUPPLIED
    else:
        utility = None
        status = NOT_DETERMINABLE
    return CandidateUtility(
        candidate_id=information_value.candidate_id, information_value=information_value,
        utility_input=utility_input, utility=utility, utility_status=status,
    )


def evaluate_utility_set(
    candidate_information_values: CandidateInformationValueSet,
    utility_inputs: Optional[Mapping[str, ExperimentUtilityInput]] = None,
) -> CandidateUtilitySet:
    """Evaluates every candidate in `candidate_information_values`
    independently -- never ranks, scores for selection, or compares one
    against another. `utility_inputs` is keyed by `candidate_id`
    (the same keyed-by-candidate_id convention `materials.design`
    already established for `design_parameters`/`methods`) -- a
    candidate not mentioned receives an empty `ExperimentUtilityInput()`
    (both fields `None`), an honest "the caller said nothing about this
    candidate," never a guessed value.

    Ordering: exactly `candidate_information_values.values` order, which
    Phase 46 already made deterministic (sorted by `candidate_id`, in
    turn Phase 37's `ActionCandidate.id`) -- re-sorted here defensively,
    not because the input could plausibly be unsorted."""
    utility_inputs = utility_inputs or {}
    ordered = tuple(sorted(candidate_information_values.values, key=lambda v: v.candidate_id))
    utilities = tuple(
        evaluate_candidate_utility(v, utility_inputs.get(v.candidate_id, ExperimentUtilityInput()))
        for v in ordered
    )
    return CandidateUtilitySet(
        process_natural_key=candidate_information_values.process_natural_key,
        candidate_information_values=candidate_information_values, utilities=utilities,
    )
