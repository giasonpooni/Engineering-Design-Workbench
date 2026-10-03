"""analyze_experiment_gaps(audit) -> ExperimentGapAnalysis: describes
experimental GAPS -- missing, conflicting, or incomparable information
relative to an already-defined engineering criterion -- never an
experiment plan, a recommendation, or a proposed measurement.

Pure function over an already-computed `ProgramAudit` (Phase 33) only
-- no `EvidencePool`, `RetrievalEngine`, `MaterialProgramAnswer`, or
`ProgramDecision` argument, confirmed by boundary tests. This is the
fifth layer's one job: it never re-derives comparability
(`materials.decision`'s own `_matching_groups` is reused directly for
`matching_contexts`), never re-classifies conflicts
(`materials.audit`'s `PropertyAudit.predicted_conflict` is reused
directly, not recomputed), and adds exactly one new thing: naming which
of six descriptive gap categories applies, from data every layer below
already produced.

A gap category never carries priority, cost, expected information
gain, or a suggested next measurement -- `criterion_context` is always
copied verbatim from the existing `Criterion` an engineer already
supplied (Phase 32); it is never generated. See the module's own tests
for the explicit checks that no such field exists anywhere in the
result tree.

Phase 34 sec.19's empirical question -- can a `DerivedValue` exist with
zero `Observation`s anywhere in its transitive ancestry? -- was tested
directly against the public API (not inferred from type names) and
answered no: `admit_derived_value` rejects any `derived_from` reference
that is not already a known `Observation` or `DerivedValue`, so the
root of any derivation chain must always be admitted against real
evidence. `PREDICTION_WITHOUT_MEASUREMENT`, as named here, therefore
describes a *property-level* fact instead -- a prediction exists for
property P on formulation F, but no Observation of P was retrieved for
F (its ancestry may perfectly well terminate in an Observation of a
*different* property, e.g. a modulus reading grounding a tensile
prediction) -- never the raw-ancestry case, which is structurally
unreachable and is proven unreachable by a dedicated test rather than
merely asserted.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Optional, Tuple

from evidence.types import Referent
from materials.audit import MODEL_DISAGREEMENT as _AUDIT_MODEL_DISAGREEMENT
from materials.audit import PropertyAudit, ProgramAudit
from materials.decision import (
    CONFLICTING_EVIDENCE, FAIL, INCOMPARABLE, INSUFFICIENT_EVIDENCE, PASS,
    Criterion, _matching_groups,
)

MEASUREMENT_CONFLICT = "MEASUREMENT_CONFLICT"
MODEL_DISAGREEMENT = "MODEL_DISAGREEMENT"
MISSING_EVIDENCE = "MISSING_EVIDENCE"
INCOMPARABLE_EVIDENCE = "INCOMPARABLE_EVIDENCE"
PREDICTION_WITHOUT_MEASUREMENT = "PREDICTION_WITHOUT_MEASUREMENT"
MEASUREMENT_WITHOUT_PREDICTION = "MEASUREMENT_WITHOUT_PREDICTION"

ALL_GAP_CATEGORIES = (
    MEASUREMENT_CONFLICT, MODEL_DISAGREEMENT, MISSING_EVIDENCE,
    INCOMPARABLE_EVIDENCE, PREDICTION_WITHOUT_MEASUREMENT, MEASUREMENT_WITHOUT_PREDICTION,
)


@dataclass(frozen=True)
class SideGap:
    """One side's (observed or predicted) diagnostic -- deliberately
    never merged with the other side, per Phase 32/33's own established
    discipline. `categories` is empty for a clean PASS/FAIL. `reason`
    is populated only when there is something to explain; for
    CONFLICTING_EVIDENCE it names the disagreeing comparable values
    (from the single matched group `materials.decision` already
    identified); for INSUFFICIENT_EVIDENCE/INCOMPARABLE it is copied
    verbatim from `materials.audit`'s own already-computed reason."""

    status: str
    categories: Tuple[str, ...]
    reason: Optional[str]
    available_contexts: Tuple[Mapping[str, object], ...]
    matching_contexts: Tuple[Mapping[str, object], ...]
    supporting_ids: Tuple[str, ...]
    provenance_observation_id_sets: Tuple[Tuple[str, ...], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "categories", tuple(self.categories))
        object.__setattr__(self, "available_contexts", tuple(self.available_contexts))
        object.__setattr__(self, "matching_contexts", tuple(self.matching_contexts))
        object.__setattr__(self, "supporting_ids", tuple(self.supporting_ids))
        object.__setattr__(self, "provenance_observation_id_sets", tuple(self.provenance_observation_id_sets))


@dataclass(frozen=True)
class EvidenceGap:
    """One (formulation, property, criterion)'s complete gap
    description. `categories` here holds only the CROSS-side
    categories (MISSING_EVIDENCE / MEASUREMENT_WITHOUT_PREDICTION /
    PREDICTION_WITHOUT_MEASUREMENT) -- facts about the *relationship*
    between the observed and predicted sides; per-side categories
    (MEASUREMENT_CONFLICT, MODEL_DISAGREEMENT, INCOMPARABLE_EVIDENCE)
    live on `observed.categories`/`predicted.categories`. This is an
    application-level DESCRIPTION, not evidence, not a prediction, and
    not a recommendation -- it is never put into EvidencePool and
    carries no priority/cost/expected-information-gain field."""

    formulation: Referent
    property: str
    criterion: Criterion
    criterion_context: Mapping[str, object]
    observed: SideGap
    predicted: SideGap
    categories: Tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "criterion_context", MappingProxyType(dict(self.criterion_context)))
        object.__setattr__(self, "categories", tuple(self.categories))


@dataclass(frozen=True)
class ExperimentGapAnalysis:
    process_natural_key: str
    audit: ProgramAudit
    gaps: Tuple[EvidenceGap, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "gaps", tuple(self.gaps))


def _reason_for_status(status: str, group, audit_reason: Optional[str]) -> Optional[str]:
    if status in (PASS, FAIL):
        return None
    if status == CONFLICTING_EVIDENCE:
        return f"comparable values disagree: {sorted(group.values)}"
    return audit_reason  # INSUFFICIENT_EVIDENCE / INCOMPARABLE -- already-computed text from materials.audit


def _build_side_gap(
    status: str, group, groups, criterion: Criterion,
    audit_reason: Optional[str], available_contexts: Tuple[Mapping[str, object], ...],
    supporting_ids: Tuple[str, ...], provenance_sets: Tuple[Tuple[str, ...], ...],
    conflict_category: str,
) -> SideGap:
    categories: Tuple[str, ...] = ()
    if status == CONFLICTING_EVIDENCE:
        categories = (conflict_category,)
    elif status == INCOMPARABLE:
        categories = (INCOMPARABLE_EVIDENCE,)
    matching = _matching_groups(groups, criterion) if groups else ()
    return SideGap(
        status=status, categories=categories,
        reason=_reason_for_status(status, group, audit_reason),
        available_contexts=available_contexts,
        matching_contexts=tuple(g.context for g in matching),
        supporting_ids=supporting_ids,
        provenance_observation_id_sets=provenance_sets,
    )


def _build_gap(pa: PropertyAudit) -> EvidenceGap:
    pd = pa.decision
    evidence = pd.evidence
    observed_groups = evidence.observed_comparison_groups if evidence is not None else ()
    predicted_groups = evidence.predicted_comparison_groups if evidence is not None else ()

    observed_supporting = tuple(o.id for o in evidence.observed) if evidence is not None else ()
    predicted_supporting = tuple(gp.derived_value.id for gp in evidence.predictions) if evidence is not None else ()
    predicted_provenance = tuple(gp.provenance.observation_ids for gp in evidence.predictions) if evidence is not None else ()

    predicted_conflict_category = MEASUREMENT_CONFLICT
    if pa.predicted_conflict is not None:
        predicted_conflict_category = MODEL_DISAGREEMENT if pa.predicted_conflict.kind == _AUDIT_MODEL_DISAGREEMENT else MEASUREMENT_CONFLICT

    observed_side = _build_side_gap(
        pd.observed_status, pd.observed_group, observed_groups, pd.criterion,
        pa.observed_reason, pa.observed_available_contexts, observed_supporting, (), MEASUREMENT_CONFLICT,
    )
    predicted_side = _build_side_gap(
        pd.predicted_status, pd.predicted_group, predicted_groups, pd.criterion,
        pa.predicted_reason, pa.predicted_available_contexts, predicted_supporting, predicted_provenance,
        predicted_conflict_category,
    )

    cross_categories: Tuple[str, ...] = ()
    observed_insufficient = pd.observed_status == INSUFFICIENT_EVIDENCE
    predicted_insufficient = pd.predicted_status == INSUFFICIENT_EVIDENCE
    if observed_insufficient and predicted_insufficient:
        cross_categories = (MISSING_EVIDENCE,)
    elif not observed_insufficient and predicted_insufficient:
        cross_categories = (MEASUREMENT_WITHOUT_PREDICTION,)
    elif observed_insufficient and not predicted_insufficient:
        cross_categories = (PREDICTION_WITHOUT_MEASUREMENT,)

    return EvidenceGap(
        formulation=pa.formulation, property=pd.criterion.property, criterion=pd.criterion,
        criterion_context=pd.criterion.context, observed=observed_side, predicted=predicted_side,
        categories=cross_categories,
    )


def analyze_experiment_gaps(audit: ProgramAudit) -> ExperimentGapAnalysis:
    """Deterministic, side-effect-free, read-only -- takes only a
    ProgramAudit; never calls EvidencePool/RetrievalEngine, never
    mutates `audit` or anything it references."""
    gaps = tuple(_build_gap(pa) for fa in audit.formulations for pa in fa.properties)
    return ExperimentGapAnalysis(process_natural_key=audit.decision.process_natural_key, audit=audit, gaps=gaps)
