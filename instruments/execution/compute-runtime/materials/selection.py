"""select_candidates(evaluations, policy) -> CandidateSelectionSet: the
first phase in this pipeline where the system is allowed to choose among
ActionCandidates -- and it does so ONLY by applying an explicit,
caller-supplied `SelectionPolicy`, never a hidden or scientific
heuristic. No ranking, score, utility, expected-information-gain,
probability, or cost-optimization concept exists anywhere in this
module, and none is added.

The decision rule is fully inspectable: every `CandidateSelection`
carries a plain-text `eligibility_reason` built only from the policy
field that decided it, plus the complete, unmodified `CandidateEvaluation`
(Phase 38) it was computed from -- nothing here re-evaluates or
re-derives what Phase 38 already determined.

`eligible` and `selected` are deliberately two separate booleans, never
collapsed into one: `eligible` is a pure function of
(CandidateEvaluation, SelectionPolicy) -- did this candidate pass every
policy rule; `selected` additionally accounts for `policy.max_selected`
-- an eligible candidate can still end up unselected purely because the
limit was already reached by higher-priority (lower id) eligible
candidates. `selected` implies `eligible` always; the converse does not
hold whenever `max_selected` truncates the eligible set.

Ordering is entirely by `ActionCandidate.id` -- Phase 37's own
content-addressed identity, untouched here. No other ordering rule is
introduced (this phase explicitly forbids ranking), so "which eligible
candidates get selected first, when the limit truncates" is answered by
the same canonical id ordering every prior layer already relies on for
determinism, not by any notion of one candidate being scientifically
"better" than another.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from materials.evaluation import CandidateEvaluation, CandidateEvaluationSet, NOT_DETERMINABLE


@dataclass(frozen=True)
class SelectionPolicy:
    """A caller-supplied, deterministic eligibility rule -- every field
    is required, with no default, so a policy can never silently apply
    a rule the caller did not state. `allowed_action_classes=None` means
    "no action_class restriction" -- an explicit, self-documenting
    choice, not a hidden one."""

    allowed_action_classes: Optional[Tuple[str, ...]]
    allow_already_represented_context: bool
    allow_redundant: bool
    allow_not_determinable_feasibility: bool
    max_selected: Optional[int]

    def __post_init__(self) -> None:
        if self.allowed_action_classes is not None:
            object.__setattr__(self, "allowed_action_classes", tuple(self.allowed_action_classes))
        if self.max_selected is not None and self.max_selected < 0:
            raise ValueError("SelectionPolicy.max_selected must be >= 0 or None")


def _is_eligible(evaluation: CandidateEvaluation, policy: SelectionPolicy) -> Tuple[bool, str]:
    """Every rule maps directly onto one policy field and one
    already-computed CandidateEvaluation field -- nothing here consults
    any information the policy or Phase 38 did not already supply. A
    candidate whose eligibility this function cannot determine from
    those two objects is never reached: every branch below either
    returns a definite False with its reason, or falls through to the
    definite True at the end -- there is no third, "unknown" outcome for
    eligibility itself (only `feasibility_status` -- a CandidateEvaluation
    field -- carries an explicit NOT_DETERMINABLE value, and the policy's
    own `allow_not_determinable_feasibility` is exactly the caller's
    explicit answer for what to do with it)."""
    candidate = evaluation.candidate

    if policy.allowed_action_classes is not None and candidate.action_class not in policy.allowed_action_classes:
        return False, f"action_class {candidate.action_class!r} is not in policy.allowed_action_classes"

    if evaluation.target_context_represented and not policy.allow_already_represented_context:
        return False, "target context is already represented by existing evidence, and policy.allow_already_represented_context is False"

    if evaluation.redundant_with_existing_evidence and not policy.allow_redundant:
        return False, "candidate is redundant with existing evidence, and policy.allow_redundant is False"

    if evaluation.feasibility_status == NOT_DETERMINABLE and not policy.allow_not_determinable_feasibility:
        return False, "feasibility is NOT_DETERMINABLE, and policy.allow_not_determinable_feasibility is False"

    return True, "eligible under policy"


@dataclass(frozen=True)
class CandidateSelection:
    """One candidate's complete selection record. `evaluation` is the
    unmodified Phase 38 CandidateEvaluation -- full provenance back
    through the candidate, its targeted requirements, and (via those)
    the specification, without duplicating any of those fields here."""

    evaluation: CandidateEvaluation
    eligible: bool
    eligibility_reason: str
    selected: bool


@dataclass(frozen=True)
class CandidateSelectionSet:
    process_natural_key: str
    evaluations: CandidateEvaluationSet
    policy: SelectionPolicy
    selections: Tuple[CandidateSelection, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "selections", tuple(self.selections))


def select_candidates(evaluations: CandidateEvaluationSet, policy: SelectionPolicy) -> CandidateSelectionSet:
    """Deterministic, side-effect-free, read-only -- takes only a
    CandidateEvaluationSet and an explicit SelectionPolicy; never calls
    EvidencePool/RetrievalEngine, never mutates either argument.

    Every candidate's eligibility is decided independently of
    `max_selected` first; candidates are then walked in canonical
    `ActionCandidate.id` order, marking each eligible candidate
    `selected` until `policy.max_selected` is reached (or marking all of
    them selected, if `max_selected` is None) -- an eligible candidate
    past the limit is recorded as eligible but not selected, never
    silently promoted and never silently dropped from the output."""
    ordered = tuple(sorted(evaluations.evaluations, key=lambda e: e.candidate.id))

    selections = []
    selected_count = 0
    for evaluation in ordered:
        eligible, reason = _is_eligible(evaluation, policy)
        selected = eligible and (policy.max_selected is None or selected_count < policy.max_selected)
        if selected:
            selected_count += 1
        selections.append(CandidateSelection(
            evaluation=evaluation, eligible=eligible, eligibility_reason=reason, selected=selected,
        ))

    return CandidateSelectionSet(
        process_natural_key=evaluations.process_natural_key, evaluations=evaluations,
        policy=policy, selections=tuple(selections),
    )
