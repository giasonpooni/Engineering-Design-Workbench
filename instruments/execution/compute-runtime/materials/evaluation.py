"""evaluate_candidates(candidates) -> CandidateEvaluationSet: the next
Phase-36-approved stage above materials.candidates -- answers descriptive
questions about each already-generated ActionCandidate using only
information already present in the CandidateSet it was built from
(which itself carries its originating ExperimentSpecification, per
Phase 37's own traceability convention -- no second argument is needed).

This is an EVALUATION layer, not selection: it never ranks, scores, or
recommends. No cost/feasibility/priority/utility/probability/expected-
value/optimization field exists anywhere in this module, and none is
added -- see the module's own tests for the explicit check that none of
those attributes exist.

Five descriptive facts are computed per candidate, each derived only
from fields `ActionCandidate`/`EvidenceRequirement` already expose:

  gap_scope -- OBSERVED_SIDE / PREDICTED_SIDE / CROSS_SIDE. Deliberately
  NOT the same thing as `candidate.role`: two of the six gap categories
  (MEASUREMENT_WITHOUT_PREDICTION, PREDICTION_WITHOUT_MEASUREMENT) carry
  a definite role (PREDICTED/OBSERVED respectively) despite being
  CROSS-side facts about the relationship between both sides, not a
  same-side disagreement -- exactly the distinction
  `materials.experiment`'s own SideGap-vs-EvidenceGap split already
  draws. `_gap_scope_for` reads the targeted requirement's `category`
  first, precisely to avoid collapsing that distinction into `role`
  alone.

  redundant_with_existing_evidence -- True only for the one case this
  is actually determinable without guessing: INCOMPARABLE_EVIDENCE where
  more than one comparison group already matches the criterion context
  (`matching_contexts` non-empty despite the INCOMPARABLE status --
  ambiguous, not absent). MEASUREMENT_CONFLICT/MODEL_DISAGREEMENT are
  never redundant by construction, even though they too always have a
  non-empty `matching_contexts` -- a conflicting group is not surplus
  information, it is exactly what still needs resolving. The absence
  categories are never redundant either, since nothing exists to be
  redundant with.

  target_context_represented -- whether ANY evidence already exists in
  the candidate's domain at all (`available_contexts` non-empty on any
  targeted requirement), regardless of whether it matches the target
  context.

  fully_specified -- whether the candidate's own `action_class` ends in
  ":unspecified". Phase 37 already encoded "nothing exists in this
  domain to anchor a more specific description" into that exact suffix;
  this field only ever reads it back, it does not recompute anything new.

  feasibility_status -- always `NOT_DETERMINABLE`. No feasibility,
  equipment, cost, or resource information exists ANYWHERE upstream of
  this module (Phase 36 sec.E/M concluded feasibility is a future,
  externally-supplied concern with no current data source) -- this is
  reported explicitly rather than defaulted to True/False, so a caller
  can never mistake "unknown" for "known feasible" or "known
  infeasible."

A candidate's targeted requirements are guaranteed to share exactly one
`category` and one `role`: `materials.candidates._action_group_key`
already includes `action_class` (itself a pure function of category and
role) in its grouping key, so no two requirements with different
category/role can ever land in the same candidate. This module relies on
that existing guarantee rather than re-deriving or re-checking it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from materials.candidates import ActionCandidate, CandidateSet, requirement_identity
from materials.experiment import (
    INCOMPARABLE_EVIDENCE, MEASUREMENT_WITHOUT_PREDICTION, MISSING_EVIDENCE,
    PREDICTION_WITHOUT_MEASUREMENT,
)
from materials.specification import EvidenceRequirement, OBSERVED, PREDICTED

OBSERVED_SIDE = "OBSERVED_SIDE"
PREDICTED_SIDE = "PREDICTED_SIDE"
CROSS_SIDE = "CROSS_SIDE"

NOT_DETERMINABLE = "NOT_DETERMINABLE"

_CROSS_SIDE_CATEGORIES = (MISSING_EVIDENCE, MEASUREMENT_WITHOUT_PREDICTION, PREDICTION_WITHOUT_MEASUREMENT)


def _gap_scope_for(category: str, role: str) -> str:
    if category in _CROSS_SIDE_CATEGORIES:
        return CROSS_SIDE
    if role == OBSERVED:
        return OBSERVED_SIDE
    if role == PREDICTED:
        return PREDICTED_SIDE
    return CROSS_SIDE


def _redundant_with_existing_evidence(category: str, requirements: Tuple[EvidenceRequirement, ...]) -> bool:
    if category != INCOMPARABLE_EVIDENCE:
        return False
    return any(len(r.matching_contexts) > 0 for r in requirements)


@dataclass(frozen=True)
class CandidateEvaluation:
    """One ActionCandidate's descriptive evaluation. `candidate` and
    `targeted_requirements` are embedded, not duplicated field-by-field
    -- the same "full evidence access without duplication" pattern
    `PropertyAudit.decision`/`ProgramAudit.decision` already establish."""

    candidate: ActionCandidate
    targeted_requirements: Tuple[EvidenceRequirement, ...]
    gap_scope: str
    redundant_with_existing_evidence: bool
    target_context_represented: bool
    fully_specified: bool
    feasibility_status: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "targeted_requirements", tuple(self.targeted_requirements))


@dataclass(frozen=True)
class CandidateEvaluationSet:
    process_natural_key: str
    candidates: CandidateSet
    evaluations: Tuple[CandidateEvaluation, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "evaluations", tuple(self.evaluations))


def _requirement_lookup(candidates: CandidateSet) -> Dict[str, EvidenceRequirement]:
    lookup: Dict[str, EvidenceRequirement] = {}
    for entry in candidates.specification.entries:
        for requirement in entry.requirements:
            lookup[requirement_identity(requirement)] = requirement
    return lookup


def _evaluate_one(candidate: ActionCandidate, lookup: Dict[str, EvidenceRequirement]) -> CandidateEvaluation:
    targeted = tuple(lookup[rid] for rid in candidate.requirement_ids)
    category = targeted[0].category
    role = targeted[0].role
    return CandidateEvaluation(
        candidate=candidate,
        targeted_requirements=targeted,
        gap_scope=_gap_scope_for(category, role),
        redundant_with_existing_evidence=_redundant_with_existing_evidence(category, targeted),
        target_context_represented=any(len(r.available_contexts) > 0 for r in targeted),
        fully_specified=not candidate.action_class.endswith(":unspecified"),
        feasibility_status=NOT_DETERMINABLE,
    )


def evaluate_candidates(candidates: CandidateSet) -> CandidateEvaluationSet:
    """Deterministic, side-effect-free, read-only -- takes only a
    CandidateSet (which already carries its originating
    ExperimentSpecification); never calls EvidencePool/RetrievalEngine,
    never mutates `candidates` or anything it references.

    Output ordering: evaluations are built in exactly
    `candidates.candidates` order, which Phase 37 already made
    deterministic (sorted by candidate id) -- no additional sort is
    needed here."""
    lookup = _requirement_lookup(candidates)
    evaluations = tuple(_evaluate_one(c, lookup) for c in candidates.candidates)
    return CandidateEvaluationSet(
        process_natural_key=candidates.process_natural_key, candidates=candidates, evaluations=evaluations,
    )
