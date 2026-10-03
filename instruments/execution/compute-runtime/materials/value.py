"""evaluate_information_value(candidate, current_iteration) ->
CandidateInformationValue: STRUCTURAL information value only -- what an
ActionCandidate is structurally capable of addressing in the current
evidence state, never a numerical estimate of how much it would help.

There is no probabilistic model, uncertainty model, outcome distribution,
likelihood model, or utility function anywhere in this codebase.
`expected_information_gain` is therefore always the literal string
`NOT_DETERMINABLE` -- reusing `materials.evaluation.NOT_DETERMINABLE`,
the same constant Phase 38 already established for exactly this
"genuinely unknown, never guessed" situation, not a new one.

This module adds NO new derivation logic of its own for anything Phase
37/38 already computed -- it calls `materials.evaluation.evaluate_candidates`
internally (via a synthetic, single-candidate `CandidateSet` built from
`current_iteration.specification`) and reads `target_context_represented`/
`redundant_with_existing_evidence`/`gap_scope`/`targeted_requirements`
directly off the resulting `CandidateEvaluation`, embedding it whole for
full provenance rather than re-deriving any of it a second time.

STRUCTURAL VALUE KIND: exactly four, one per group of the six existing
gap categories (`materials.experiment`) that share the same underlying
"what would this candidate's evidence relate to" nature:

  RESOLVES_MISSING_EVIDENCE   <- MISSING_EVIDENCE, MEASUREMENT_WITHOUT_PREDICTION,
                                  PREDICTION_WITHOUT_MEASUREMENT (all three mean
                                  "nothing exists in this domain" -- `role`,
                                  already on the candidate, says which domain)
  TESTS_CONFLICT              <- MEASUREMENT_CONFLICT
  ADDRESSES_MODEL_DISAGREEMENT <- MODEL_DISAGREEMENT
  REDUCES_INCOMPARABILITY     <- INCOMPARABLE_EVIDENCE

No fifth or sixth kind is introduced for the phase's suggested
FILLS_MISSING_CONTEXT/VALIDATES_MODEL: both are exact synonyms of
REDUCES_INCOMPARABILITY/ADDRESSES_MODEL_DISAGREEMENT respectively, and
inventing two names for one already-existing category would itself be
adding ontology this phase does not justify.

`current_status` (PASS/FAIL/CONFLICTING_EVIDENCE/INCOMPARABLE/
INSUFFICIENT_EVIDENCE, from `materials.decision`) is derived from
`gap_category` via a proven, exhaustive mapping, not re-fetched from
`ProgramDecision`: `materials.experiment._build_side_gap`/`_build_gap`
only ever assigns MEASUREMENT_CONFLICT/MODEL_DISAGREEMENT when that
side's status is exactly CONFLICTING_EVIDENCE, INCOMPARABLE_EVIDENCE
only when it is exactly INCOMPARABLE, and the three absence categories
only from combinations of INSUFFICIENT_EVIDENCE -- a `EvidenceRequirement`
with a given category could not exist unless its targeted side already
had exactly that status, so reading it off the category is exact, not
approximate, and does not require a second lookup into
`iteration.decision`.

`existing_contexts` is read directly from `targeted_requirements[0].
available_contexts` rather than unioned across every targeted
requirement: `materials.candidates._action_group_key` already guarantees
every requirement merged into one candidate shares identical
formulation/property/role/action_class/criterion-context/evidence, so
`available_contexts` (itself derived only from those) is already
identical across all of them -- reading the first is exact, not a
simplification.

CASES A-D (this phase's own "most important investigation"), verified
directly against real fixtures in this module's own tests, not asserted
from reasoning alone:

  A. no measurement exists, a candidate proposes one
     -> MISSING_EVIDENCE/PREDICTION_WITHOUT_MEASUREMENT -> RESOLVES_MISSING_EVIDENCE.
  B. two conflicting measurements exist, a candidate proposes another
     -> MEASUREMENT_CONFLICT -> TESTS_CONFLICT.
  C. ONE observation and ONE prediction, "validating the model
     experimentally" by comparing them against each other -- genuinely
     NOT structurally derivable. `PropertyDecision` never compares an
     observed value against a predicted value; each is checked against
     the criterion independently (`materials.decision._status_for_groups`,
     called once per side). A single observation and a single prediction
     that each independently pass or fail their own criterion produce
     NO gap category, NO EvidenceRequirement, and NO ActionCandidate at
     all under the existing pipeline -- there is nothing for this module
     to evaluate, and it invents nothing to fill that absence. What IS
     structurally real and genuinely close in spirit is
     MODEL_DISAGREEMENT (multiple predictions disagreeing with each
     other) -> ADDRESSES_MODEL_DISAGREEMENT -- a different, real case,
     not a stand-in for C.
  D. a measurement exists under one context, the criterion requires a
     different one -> INCOMPARABLE_EVIDENCE -> REDUCES_INCOMPARABILITY.

Language throughout `explanation` is deliberately non-committal --
"structurally targets"/"potentially addresses"/"could reduce" -- never
"resolves"/"will improve"/"will prove"/"will select": a candidate that
targets a conflict does not mean the conflict will be resolved, only
that evidence relevant to it would exist. No score, rank, probability,
confidence, utility, cost, priority, winner, or recommendation exists
anywhere in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Tuple

from evidence.types import Referent
from materials.candidates import ActionCandidate, CandidateSet
from materials.decision import CONFLICTING_EVIDENCE, INCOMPARABLE, INSUFFICIENT_EVIDENCE, Criterion
from materials.evaluation import CandidateEvaluation, NOT_DETERMINABLE, evaluate_candidates
from materials.experiment import (
    INCOMPARABLE_EVIDENCE, MEASUREMENT_CONFLICT, MEASUREMENT_WITHOUT_PREDICTION,
    MISSING_EVIDENCE, MODEL_DISAGREEMENT, PREDICTION_WITHOUT_MEASUREMENT,
)
from materials.iteration import MaterialsIteration

RESOLVES_MISSING_EVIDENCE = "RESOLVES_MISSING_EVIDENCE"
TESTS_CONFLICT = "TESTS_CONFLICT"
ADDRESSES_MODEL_DISAGREEMENT = "ADDRESSES_MODEL_DISAGREEMENT"
REDUCES_INCOMPARABILITY = "REDUCES_INCOMPARABILITY"

ALL_INFORMATION_VALUE_KINDS = (
    RESOLVES_MISSING_EVIDENCE, TESTS_CONFLICT, ADDRESSES_MODEL_DISAGREEMENT, REDUCES_INCOMPARABILITY,
)

_CATEGORY_TO_STATUS = {
    MEASUREMENT_CONFLICT: CONFLICTING_EVIDENCE,
    MODEL_DISAGREEMENT: CONFLICTING_EVIDENCE,
    INCOMPARABLE_EVIDENCE: INCOMPARABLE,
    MISSING_EVIDENCE: INSUFFICIENT_EVIDENCE,
    MEASUREMENT_WITHOUT_PREDICTION: INSUFFICIENT_EVIDENCE,
    PREDICTION_WITHOUT_MEASUREMENT: INSUFFICIENT_EVIDENCE,
}

_CATEGORY_TO_VALUE_KIND = {
    MEASUREMENT_CONFLICT: TESTS_CONFLICT,
    MODEL_DISAGREEMENT: ADDRESSES_MODEL_DISAGREEMENT,
    INCOMPARABLE_EVIDENCE: REDUCES_INCOMPARABILITY,
    MISSING_EVIDENCE: RESOLVES_MISSING_EVIDENCE,
    MEASUREMENT_WITHOUT_PREDICTION: RESOLVES_MISSING_EVIDENCE,
    PREDICTION_WITHOUT_MEASUREMENT: RESOLVES_MISSING_EVIDENCE,
}


@dataclass(frozen=True)
class CandidateInformationValue:
    """What a single ActionCandidate is structurally capable of
    addressing -- never what it will accomplish. `evaluation` is the
    complete, unmodified Phase 38 `CandidateEvaluation` -- full
    provenance (candidate -> targeted requirements -> ... ) without
    duplicating any of it."""

    candidate_id: str
    formulation: Referent
    property: str
    criterion: Criterion
    role: str
    gap_scope: str
    current_status: str
    target_context: Mapping[str, object]
    existing_contexts: Tuple[Mapping[str, object], ...]
    gap_category: str
    value_kind: str
    target_context_represented: bool
    redundant_with_existing_evidence: bool
    expected_information_gain: str
    explanation: str
    evaluation: CandidateEvaluation

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_context", MappingProxyType(dict(self.target_context)))
        object.__setattr__(self, "existing_contexts", tuple(self.existing_contexts))


@dataclass(frozen=True)
class CandidateInformationValueSet:
    process_natural_key: str
    candidate_set: CandidateSet
    values: Tuple[CandidateInformationValue, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", tuple(self.values))


def _explanation_for(value_kind: str, evaluation: CandidateEvaluation) -> str:
    formulation_key = evaluation.candidate.formulation.natural_key
    property_name = evaluation.candidate.property
    scope = evaluation.gap_scope.lower().replace("_", "-")

    if value_kind == RESOLVES_MISSING_EVIDENCE:
        return (
            f"structurally targets currently absent {scope} evidence for {property_name!r} "
            f"on {formulation_key!r}; could provide evidence where none currently exists, "
            f"but does not determine any particular resulting value"
        )
    if value_kind == TESTS_CONFLICT:
        return (
            f"potentially addresses an existing {scope} conflict for {property_name!r} "
            f"on {formulation_key!r} by proposing additional comparable evidence; "
            f"does not determine which existing value, if either, is correct"
        )
    if value_kind == ADDRESSES_MODEL_DISAGREEMENT:
        return (
            f"potentially addresses disagreement among predictions sharing the same underlying "
            f"evidence for {property_name!r} on {formulation_key!r}; "
            f"does not determine which prediction, if either, is correct"
        )
    return (  # REDUCES_INCOMPARABILITY
        f"structurally targets the criterion's own declared context for {property_name!r} "
        f"on {formulation_key!r}, which no existing comparable evidence currently matches; "
        f"could reduce incomparability but does not determine a particular resulting value"
    )


def evaluate_information_value(candidate: ActionCandidate, current_iteration: MaterialsIteration) -> CandidateInformationValue:
    """Deterministic, side-effect-free, read-only -- takes only a
    candidate and the current MaterialsIteration; never touches
    EvidencePool, never mutates either argument."""
    synthetic_set = CandidateSet(
        process_natural_key=current_iteration.specification.process_natural_key,
        specification=current_iteration.specification, candidates=(candidate,),
    )
    evaluation = evaluate_candidates(synthetic_set).evaluations[0]
    requirement = evaluation.targeted_requirements[0]
    category = requirement.category
    value_kind = _CATEGORY_TO_VALUE_KIND[category]

    return CandidateInformationValue(
        candidate_id=candidate.id, formulation=candidate.formulation, property=candidate.property,
        criterion=requirement.criterion, role=candidate.role, gap_scope=evaluation.gap_scope,
        current_status=_CATEGORY_TO_STATUS[category], target_context=candidate.target_context,
        existing_contexts=requirement.available_contexts, gap_category=category, value_kind=value_kind,
        target_context_represented=evaluation.target_context_represented,
        redundant_with_existing_evidence=evaluation.redundant_with_existing_evidence,
        expected_information_gain=NOT_DETERMINABLE,
        explanation=_explanation_for(value_kind, evaluation),
        evaluation=evaluation,
    )


def evaluate_candidate_information_values(
    candidate_set: CandidateSet, current_iteration: MaterialsIteration
) -> CandidateInformationValueSet:
    """Evaluates every candidate in `candidate_set` independently --
    never ranks, scores, or selects among them. Ordering: exactly
    `candidate_set.candidates` order, which Phase 37 already made
    deterministic (sorted by `ActionCandidate.id`)."""
    ordered = tuple(sorted(candidate_set.candidates, key=lambda c: c.id))
    values = tuple(evaluate_information_value(c, current_iteration) for c in ordered)
    return CandidateInformationValueSet(
        process_natural_key=candidate_set.process_natural_key, candidate_set=candidate_set, values=values,
    )
