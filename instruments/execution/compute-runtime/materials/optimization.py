"""optimize_candidates(utility_set, policy) -> OptimizationResult: which
SUBSET of candidates should be chosen under explicit constraints --
deliberately a different question from `materials.ranking`'s "how are
candidates ordered." The two modules are siblings, not a pipeline: both
consume `materials.utility.CandidateUtilitySet` directly, and this
module does not import `materials.ranking` at all -- a `CandidateRanking`
adds no information beyond what `CandidateUtility` already carries (it
only reorders the same utilities), so nothing here needs it.

The optimizer never claims its result is scientifically optimal. It is
optimal only with respect to the caller-supplied `utility` values and
`OptimizationPolicy` -- exactly as honest as `materials.utility`'s own
`utility = benefit - cost` was about being a caller judgment, not a
retrieved fact.

WHY SORTING IS THE OPTIMIZER, NOT AN APPROXIMATION OF ONE: the current
ontology (`CandidateUtility`) has no per-candidate resource consumption
dimension separate from `utility` itself -- there is no "cost" field
that competes against a shared budget the way, say, weight competes
against capacity in a knapsack problem. `OptimizationPolicy.max_candidates`
is a pure COUNT constraint. For "maximize the sum of utility subject to
at most K candidates," picking the K eligible, determinate-utility
candidates with the highest `utility` (ties broken by `ActionCandidate.id`)
is PROVABLY optimal, not a heuristic: swapping any selected candidate
for an unselected one of lower utility can only decrease or preserve the
sum. No linear programming, Bayesian optimization, active learning,
Monte Carlo, acquisition function, or neural model is needed for this
constraint shape, and none is added. If a future phase introduces a
genuine competing-resource constraint (e.g. a shared cost budget smaller
than the sum of individual costs), THAT is where real combinatorial
search would first become necessary -- not here.

Two explicit, caller-required policy fields (mirroring
`materials.selection.SelectionPolicy`'s "every field required" and
`materials.ranking.RankingPolicy`'s "two required fields" discipline):

  max_candidates            -- Optional[int]; None means unbounded.
  allowed_action_classes     -- Optional[Tuple[str, ...]]; None means no
                                 restriction (mirrors
                                 `SelectionPolicy.allowed_action_classes`).
  allow_indeterminate_utility -- bool; whether a candidate whose
                                 `utility` is `None` (Phase 47's
                                 NOT_DETERMINABLE) stays in the eligible
                                 set at all. Even when permitted, such a
                                 candidate can never become SELECTED --
                                 there is no way to include an unknown
                                 quantity in a sum-maximizing choice, so
                                 "permitted" only changes whether it is
                                 excluded outright (NOT_ELIGIBLE) or kept
                                 as ELIGIBLE_NOT_SELECTED.

No laboratory cost, duration, probability, feasibility, information
gain, scientific value, or resource-requirement field is added anywhere
-- none of those exists in `CandidateUtility`/`CandidateInformationValue`
either, and inventing one here to make the optimizer "more like a real
optimizer" would be exactly the fabricated ontology this phase forbids.

Three states per candidate, never collapsed to a boolean (the same
discipline `materials.selection.CandidateSelection` already established
for eligible/selected): SELECTED, ELIGIBLE_NOT_SELECTED, NOT_ELIGIBLE.
`eligibility_reason` explains only eligibility (mirroring
`SelectionPolicy`'s own single reason field) -- a caller distinguishes
"eligible but excluded by the count limit" from "eligible but has no
determinate utility" by reading `status` alongside `utility` directly,
not from a second free-text field.

`total_selected_utility` is the literal sum of `utility` over SELECTED
candidates -- always a determinate float (0.0 when nothing is selected,
the mathematically correct sum of an empty set, never `None`): this is a
newly-computed fact, not a caller-supplied or indeterminate one, so it
does not participate in the KNOWN/SUPPLIED/NOT_DETERMINABLE vocabulary
those other modules use for THEIR OWN fields.

Every `CandidateOptimization` embeds the complete, unmodified
`CandidateUtility` -- the full candidate -> requirement -> gap -> audit
-> decision -> evidence/provenance chain stays reachable without
duplicating any of it. No new identity system: `candidate_id` is exactly
`ActionCandidate.id`, untouched since Phase 37. Never touches
EvidencePool/RetrievalEngine; never mutates its inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from materials.utility import CandidateUtility, CandidateUtilitySet

SELECTED = "SELECTED"
ELIGIBLE_NOT_SELECTED = "ELIGIBLE_NOT_SELECTED"
NOT_ELIGIBLE = "NOT_ELIGIBLE"
ALL_OPTIMIZATION_STATUSES = (SELECTED, ELIGIBLE_NOT_SELECTED, NOT_ELIGIBLE)


@dataclass(frozen=True)
class OptimizationPolicy:
    """All three fields required, no defaults -- a caller must state the
    constraint explicitly."""

    max_candidates: Optional[int]
    allowed_action_classes: Optional[Tuple[str, ...]]
    allow_indeterminate_utility: bool

    def __post_init__(self) -> None:
        if self.allowed_action_classes is not None:
            object.__setattr__(self, "allowed_action_classes", tuple(self.allowed_action_classes))
        if self.max_candidates is not None and self.max_candidates < 0:
            raise ValueError("OptimizationPolicy.max_candidates must be >= 0 or None")


@dataclass(frozen=True)
class CandidateOptimization:
    """One candidate's optimization record. `utility` is the complete,
    unmodified Phase 47 `CandidateUtility` -- full provenance without
    duplicating any of it."""

    candidate_id: str
    utility: CandidateUtility
    status: str
    eligibility_reason: str


@dataclass(frozen=True)
class OptimizationResult:
    process_natural_key: str
    utility_set: CandidateUtilitySet
    policy: OptimizationPolicy
    total_selected_utility: float
    optimizations: Tuple[CandidateOptimization, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "optimizations", tuple(self.optimizations))


def _eligibility(u: CandidateUtility, policy: OptimizationPolicy) -> Tuple[bool, str]:
    action_class = u.information_value.evaluation.candidate.action_class
    if policy.allowed_action_classes is not None and action_class not in policy.allowed_action_classes:
        return False, f"action_class {action_class!r} is not in policy.allowed_action_classes"
    if u.utility is None and not policy.allow_indeterminate_utility:
        return False, "utility is NOT_DETERMINABLE, and policy.allow_indeterminate_utility is False"
    return True, "eligible under policy"


def optimize_candidates(utility_set: CandidateUtilitySet, policy: OptimizationPolicy) -> OptimizationResult:
    """Deterministic, side-effect-free, read-only -- takes only a
    CandidateUtilitySet and an explicit OptimizationPolicy; never
    mutates either argument.

    Eligibility is decided independently of `max_candidates` first.
    Among eligible candidates with a determinate `utility`, the
    `max_candidates` highest (ties broken by `candidate_id` ascending)
    are marked SELECTED -- see the module docstring for why this greedy
    sort is exactly optimal for this constraint shape, not a heuristic.
    Every other candidate is preserved as ELIGIBLE_NOT_SELECTED or
    NOT_ELIGIBLE; none is ever dropped from the output."""
    ordered = tuple(sorted(utility_set.utilities, key=lambda u: u.candidate_id))
    eligibility = [_eligibility(u, policy) for u in ordered]

    selectable = [u for u, (elig, _) in zip(ordered, eligibility) if elig and u.utility is not None]

    def _sort_key(u: CandidateUtility) -> Tuple[float, str]:
        assert u.utility is not None  # guaranteed by the `selectable` filter above
        return (-u.utility, u.candidate_id)

    selectable.sort(key=_sort_key)
    selected = selectable if policy.max_candidates is None else selectable[: policy.max_candidates]
    selected_ids = {u.candidate_id for u in selected}

    optimizations = []
    for u, (elig, reason) in zip(ordered, eligibility):
        if u.candidate_id in selected_ids:
            status = SELECTED
        elif elig:
            status = ELIGIBLE_NOT_SELECTED
        else:
            status = NOT_ELIGIBLE
        optimizations.append(CandidateOptimization(candidate_id=u.candidate_id, utility=u, status=status, eligibility_reason=reason))

    total_selected_utility = 0.0
    for u in selected:
        assert u.utility is not None  # guaranteed by the `selectable` filter above
        total_selected_utility += u.utility
    return OptimizationResult(
        process_natural_key=utility_set.process_natural_key, utility_set=utility_set, policy=policy,
        total_selected_utility=total_selected_utility, optimizations=tuple(optimizations),
    )
