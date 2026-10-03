"""audit_program(decision) -> ProgramAudit: diagnostics over an
already-computed `ProgramDecision` (Phase 32) -- exposes WHY each
non-PASS/FAIL status was reached, using nothing but the evidence
`materials.decision` already inspected.

Pure function over `ProgramDecision` only -- no `EvidencePool`,
`RetrievalEngine`, or `MaterialProgramAnswer` argument at all. This is
the fourth layer's one job: `materials.analysis` answers "what evidence
exists," `materials.program` answers "for which formulations, under
which process," `materials.decision` answers "does the comparable
evidence pass, fail, conflict, or fail to exist," and this module
answers "why" -- without re-querying, re-deriving, or duplicating
anything the layers below it already computed.

One genuinely new piece of logic exists here, not present in
`materials.decision`: classifying a `CONFLICTING_EVIDENCE` *predicted*
status as `MODEL_DISAGREEMENT` (all conflicting predictions trace to
the identical set of source observations -- the Phase 30/31/32 "F3
case") or `MEASUREMENT_DISAGREEMENT` (they do not all share the same
provenance -- the "F1 case"). This reuses `materials.decision`'s own
private context-matching helpers rather than re-implementing them, and
never resolves the disagreement -- only names its shape, from
provenance that already exists.

Every reason string below is built directly from counts/facts already
present in the evidence (how many comparison groups existed, whether
`evidence` was `None`, how many groups matched a criterion's context)
-- never an invented explanation. No ranking, scoring, or
recommendation exists anywhere in this module; `FormulationAuditSummary`
is a literal per-status tally, not a score.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Optional, Tuple

from evidence.types import Referent
from materials.analysis import MaterialPropertyAnswer, _comparison_context
from materials.decision import (
    CONFLICTING_EVIDENCE, FAIL, INCOMPARABLE, INSUFFICIENT_EVIDENCE, PASS,
    ALL_STATUSES, Criterion, FormulationDecision, ProgramDecision, PropertyDecision,
    _context_matches, _matching_groups,
)
from materials.program import FormulationProcessAssociation

MODEL_DISAGREEMENT = "MODEL_DISAGREEMENT"
MEASUREMENT_DISAGREEMENT = "MEASUREMENT_DISAGREEMENT"


@dataclass(frozen=True)
class ConflictDiagnosis:
    """Only produced when `predicted_status == CONFLICTING_EVIDENCE`.
    `kind` is `MODEL_DISAGREEMENT` iff every criterion-relevant
    prediction traces to the identical set of source observations;
    `MEASUREMENT_DISAGREEMENT` otherwise (any difference in provenance
    at all -- the conservative default per Phase 33's own instruction:
    do not claim shared provenance unless the evidence proves it)."""

    kind: str
    prediction_ids: Tuple[str, ...]
    provenance_observation_id_sets: Tuple[Tuple[str, ...], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "prediction_ids", tuple(self.prediction_ids))
        object.__setattr__(self, "provenance_observation_id_sets", tuple(self.provenance_observation_id_sets))


@dataclass(frozen=True)
class PropertyAudit:
    """One (formulation, criterion) pair's full diagnostic. `decision`
    is the unmodified `PropertyDecision` -- full evidence/provenance
    access without duplication. `*_reason` is populated only for
    non-PASS/FAIL statuses (PASS/FAIL are already fully explained by
    the matched `ComparisonGroup` already on `decision`).
    `*_available_contexts` lists every comparison context that existed
    for this property, whether or not it matched the criterion."""

    formulation: Referent
    criterion: Criterion
    decision: PropertyDecision
    observed_reason: Optional[str]
    observed_available_contexts: Tuple[Mapping[str, object], ...]
    predicted_reason: Optional[str]
    predicted_available_contexts: Tuple[Mapping[str, object], ...]
    predicted_conflict: Optional[ConflictDiagnosis]

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_available_contexts", tuple(self.observed_available_contexts))
        object.__setattr__(self, "predicted_available_contexts", tuple(self.predicted_available_contexts))


@dataclass(frozen=True)
class FormulationAuditSummary:
    """A literal per-status tally -- descriptive, not authoritative
    (Phase 33 §5). Never combined into one number; never used to imply
    one formulation is "better" than another."""

    observed_status_counts: Mapping[str, int]
    predicted_status_counts: Mapping[str, int]

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_status_counts", MappingProxyType(dict(self.observed_status_counts)))
        object.__setattr__(self, "predicted_status_counts", MappingProxyType(dict(self.predicted_status_counts)))


@dataclass(frozen=True)
class FormulationAudit:
    formulation: Referent
    process_association: FormulationProcessAssociation
    properties: Tuple[PropertyAudit, ...]
    summary: FormulationAuditSummary

    def __post_init__(self) -> None:
        object.__setattr__(self, "properties", tuple(self.properties))


@dataclass(frozen=True)
class ProgramAudit:
    decision: ProgramDecision
    formulations: Tuple[FormulationAudit, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "formulations", tuple(self.formulations))


def _reason_and_contexts(
    evidence: Optional[MaterialPropertyAnswer],
    groups,
    criterion: Criterion,
    status: str,
) -> Tuple[Optional[str], Tuple[Mapping[str, object], ...]]:
    if evidence is None:
        return f"property {criterion.property!r} was not included in the program query", ()
    contexts = tuple(g.context for g in groups)
    if status in (PASS, FAIL):
        return None, contexts
    if status == INSUFFICIENT_EVIDENCE:
        return f"no evidence exists for property {criterion.property!r}", contexts
    if status == INCOMPARABLE:
        matching = _matching_groups(groups, criterion)
        if not matching:
            return (
                f"{len(groups)} comparison group(s) exist for {criterion.property!r}, "
                f"none match criterion context {dict(criterion.context)}"
            ), contexts
        return (
            f"{len(matching)} comparison groups matched criterion context "
            f"{dict(criterion.context)} ambiguously (expected exactly 1)"
        ), contexts
    return None, contexts


def _classify_predicted_conflict(evidence: MaterialPropertyAnswer, criterion: Criterion) -> Optional[ConflictDiagnosis]:
    relevant = tuple(
        gp for gp in evidence.predictions
        if _context_matches(criterion.context, _comparison_context(gp.derived_value.content, "predicted_value"))
    )
    if len(relevant) < 2:
        return None
    provenance_sets = tuple(gp.provenance.observation_ids for gp in relevant)
    kind = MODEL_DISAGREEMENT if len(set(provenance_sets)) == 1 else MEASUREMENT_DISAGREEMENT
    return ConflictDiagnosis(
        kind=kind,
        prediction_ids=tuple(gp.derived_value.id for gp in relevant),
        provenance_observation_id_sets=provenance_sets,
    )


def _audit_property(formulation: Referent, pd: PropertyDecision) -> PropertyAudit:
    observed_groups = pd.evidence.observed_comparison_groups if pd.evidence is not None else ()
    predicted_groups = pd.evidence.predicted_comparison_groups if pd.evidence is not None else ()

    observed_reason, observed_contexts = _reason_and_contexts(pd.evidence, observed_groups, pd.criterion, pd.observed_status)
    predicted_reason, predicted_contexts = _reason_and_contexts(pd.evidence, predicted_groups, pd.criterion, pd.predicted_status)

    predicted_conflict = None
    if pd.predicted_status == CONFLICTING_EVIDENCE and pd.evidence is not None:
        predicted_conflict = _classify_predicted_conflict(pd.evidence, pd.criterion)

    return PropertyAudit(
        formulation=formulation, criterion=pd.criterion, decision=pd,
        observed_reason=observed_reason, observed_available_contexts=observed_contexts,
        predicted_reason=predicted_reason, predicted_available_contexts=predicted_contexts,
        predicted_conflict=predicted_conflict,
    )


def _summarize(properties: Tuple[PropertyAudit, ...]) -> FormulationAuditSummary:
    observed_counts = {status: 0 for status in ALL_STATUSES}
    predicted_counts = {status: 0 for status in ALL_STATUSES}
    for pa in properties:
        observed_counts[pa.decision.observed_status] += 1
        predicted_counts[pa.decision.predicted_status] += 1
    return FormulationAuditSummary(observed_status_counts=observed_counts, predicted_status_counts=predicted_counts)


def _audit_formulation(fd: FormulationDecision) -> FormulationAudit:
    properties = tuple(_audit_property(fd.formulation, pd) for pd in fd.properties)
    return FormulationAudit(
        formulation=fd.formulation, process_association=fd.process_association,
        properties=properties, summary=_summarize(properties),
    )


def audit_program(decision: ProgramDecision) -> ProgramAudit:
    """Deterministic, side-effect-free, read-only -- takes only a
    `ProgramDecision`; never calls `EvidencePool`/`RetrievalEngine`."""
    formulations = tuple(_audit_formulation(fd) for fd in decision.formulations)
    return ProgramAudit(decision=decision, formulations=formulations)
