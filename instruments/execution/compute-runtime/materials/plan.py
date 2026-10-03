"""assemble_experiment_plan(selection) -> ExperimentPlan: the final
Phase-36-approved stage -- converts an already-computed
CandidateSelectionSet (Phase 39) into an auditable ExperimentPlan.

This is PLAN ASSEMBLY ONLY: a straight, non-lossy projection of "which
candidates were selected" into a flat, directly-inspectable record. It
adds no new decision of its own -- no procedure, instrument, equipment,
schedule, duration, cost, resource, operator, execution state, expected
information gain, probability, utility, ranking, or optimization exists
anywhere in this module, and none is added. The plan states WHAT was
selected; it never states HOW or WHEN to carry it out.

Only `CandidateSelection`s with `selected=True` become
`ExperimentPlanEntry` objects -- an ineligible or eligible-but-
unselected candidate (Phase 39's own `eligible`/`selected` distinction)
never appears in the plan at all, so a caller reading `ExperimentPlan`
never has to re-filter it. Every entry both flattens the candidate's own
descriptive fields (for direct inspection without chasing through nested
objects) AND embeds the complete, unmodified `CandidateEvaluation` and
`CandidateSelection` it came from (for full provenance back through the
candidate's targeted requirements and the specification) -- the same
"flatten the immediately relevant fields, embed the rest" pattern
`materials.experiment`'s own `EvidenceGap` already established for
`criterion`/`criterion_context`.

Nothing is re-derived, re-queried, or re-evaluated: `assemble_experiment_plan`
reads only fields Phase 37/38/39 already computed, never touches
EvidencePool/RetrievalEngine, and never mutates its input.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Tuple

from evidence.types import Referent
from materials.evaluation import CandidateEvaluation
from materials.selection import CandidateSelection, CandidateSelectionSet


@dataclass(frozen=True)
class ExperimentPlanEntry:
    """One selected candidate's plan entry. `candidate_id` through
    `existing_evidence_ids` are copied verbatim from the underlying
    `ActionCandidate` (Phase 37) for direct inspection; `evaluation`
    and `selection` are the complete, unmodified Phase 38/39 objects --
    full provenance without re-deriving anything already computed."""

    candidate_id: str
    action_class: str
    formulation: Referent
    property: str
    role: str
    target_context: Mapping[str, object]
    requirement_ids: Tuple[str, ...]
    existing_evidence_ids: Tuple[str, ...]
    evaluation: CandidateEvaluation
    selection: CandidateSelection

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_context", MappingProxyType(dict(self.target_context)))
        object.__setattr__(self, "requirement_ids", tuple(self.requirement_ids))
        object.__setattr__(self, "existing_evidence_ids", tuple(self.existing_evidence_ids))


@dataclass(frozen=True)
class ExperimentPlan:
    process_natural_key: str
    selection: CandidateSelectionSet
    entries: Tuple[ExperimentPlanEntry, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", tuple(self.entries))


def _entry_for(selection: CandidateSelection) -> ExperimentPlanEntry:
    candidate = selection.evaluation.candidate
    return ExperimentPlanEntry(
        candidate_id=candidate.id, action_class=candidate.action_class,
        formulation=candidate.formulation, property=candidate.property, role=candidate.role,
        target_context=candidate.target_context, requirement_ids=candidate.requirement_ids,
        existing_evidence_ids=candidate.existing_evidence_ids,
        evaluation=selection.evaluation, selection=selection,
    )


def assemble_experiment_plan(selection: CandidateSelectionSet) -> ExperimentPlan:
    """Deterministic, side-effect-free, read-only -- takes only a
    CandidateSelectionSet; never calls EvidencePool/RetrievalEngine,
    never mutates `selection` or anything it references.

    Only `selected=True` entries are included; an empty selection (no
    candidate selected) produces a valid `ExperimentPlan` with
    `entries=()`. Ordering is by `ActionCandidate.id` -- Phase 37's own
    content-addressed identity, untouched here -- independent of
    insertion order, dict/set iteration, or PYTHONHASHSEED."""
    chosen = tuple(s for s in selection.selections if s.selected)
    ordered = tuple(sorted(chosen, key=lambda s: s.evaluation.candidate.id))
    entries = tuple(_entry_for(s) for s in ordered)
    return ExperimentPlan(process_natural_key=selection.process_natural_key, selection=selection, entries=entries)
