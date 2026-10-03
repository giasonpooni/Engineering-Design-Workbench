"""specify_experiment_requirements(gaps) -> ExperimentSpecification: convert
an already-computed `ExperimentGapAnalysis` (Phase 34) into explicit,
structured descriptions of WHAT INFORMATION would need to be obtained to
close each identified gap.

This is the boundary the whole `materials/` pipeline has been building
toward, and it is drawn deliberately narrow:

    GAP ANALYSIS         = what information is missing/conflicting/incomparable
    EXPERIMENT SPECIFICATION = what information is required to resolve that gap
    EXPERIMENT SELECTION  = which actual experiment should be performed

This module implements only the middle layer. It never ranks, scores,
selects, or recommends a particular measurement, instrument, laboratory,
model retraining procedure, or repeat count -- see each gap category's
handler below and the module's own tests for the explicit checks that no
such field exists anywhere in the result tree.

Pure function over an already-computed `ExperimentGapAnalysis` only -- no
`EvidencePool`, `RetrievalEngine`, `ProgramAudit`/`ProgramDecision`/
`MaterialProgramAnswer` argument, no configuration, optimizer, ranking
function, or LLM. `ExperimentGapAnalysis.audit` is still reachable through
`gaps.audit` (unmodified, the same object Phase 34 already carried), but
this module never reaches into it for anything beyond what a `SideGap`/
`EvidenceGap` already exposes -- it adds no new evidence inspection of its
own.

Six gap categories in, six gap categories out -- one `EvidenceRequirement`
per (gap, side-or-cross) category present, never merged, never dropped,
never re-derived from raw evidence:

    MEASUREMENT_CONFLICT / MODEL_DISAGREEMENT / INCOMPARABLE_EVIDENCE
        -- per-side (`EvidenceGap.observed`/`.predicted`), `role` names
           which side the unresolved information concerns.
    MISSING_EVIDENCE
        -- cross-side, `role=EITHER`: neither side has evidence, and
           preferring one side over the other would be inventing a
           preference the upstream evidence does not express.
    MEASUREMENT_WITHOUT_PREDICTION
        -- cross-side, `role=PREDICTED`: the observed side's existing
           evidence is preserved on the requirement (per Phase 35 sec.6E,
           "preserving the existing measurement information"), even
           though the missing side is what the requirement names.
    PREDICTION_WITHOUT_MEASUREMENT
        -- cross-side, `role=OBSERVED`: the predicted side's IDs and
           provenance are preserved for the same reason (Phase 35 sec.6F).

`description` is a convenience field only -- built verbatim from a
`SideGap.reason` (or, for the two cross-side categories that preserve one
side's evidence, that side's own already-computed reason) that
`materials.experiment` already computed; never invented prose, and never
the canonical representation. Every field a caller could need is a plain
structured field (Referent, `Criterion`, id tuples, context mappings) --
see the module's own tests for the "no reparsing a string" check.

INCOMPARABLE_EVIDENCE never invents a target context (Phase 35 sec.6C):
`available_contexts`/`matching_contexts` are copied verbatim from the
`SideGap` that already computed them against the caller-supplied
`Criterion.context`; nothing here guesses what context "should" have been
measured.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Optional, Tuple

from evidence.types import Referent
from materials.decision import Criterion
from materials.experiment import (
    MEASUREMENT_WITHOUT_PREDICTION, MISSING_EVIDENCE,
    EvidenceGap, ExperimentGapAnalysis, SideGap,
)

OBSERVED = "OBSERVED"
PREDICTED = "PREDICTED"
EITHER = "EITHER"

ALL_ROLES = (OBSERVED, PREDICTED, EITHER)


@dataclass(frozen=True)
class EvidenceRequirement:
    """One (gap, category)'s information requirement -- describes what is
    needed, never a procedure. Every field below is either copied
    verbatim from the `EvidenceGap`/`SideGap` Phase 34 already produced,
    or is one of the two identifying constants (`role`, `category`) this
    module adds. No instrument/operator/sample-mass/duration/temperature-
    ramp/geometry/laboratory/cost/priority/batch/scheduling/utility field
    exists here, and none is added unless that fact already existed
    explicitly upstream (none currently does)."""

    formulation: Referent
    property: str
    criterion: Criterion
    criterion_context: Mapping[str, object]
    role: str
    category: str
    existing_evidence_ids: Tuple[str, ...]
    provenance_observation_id_sets: Tuple[Tuple[str, ...], ...]
    available_contexts: Tuple[Mapping[str, object], ...]
    matching_contexts: Tuple[Mapping[str, object], ...]
    description: Optional[str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "criterion_context", MappingProxyType(dict(self.criterion_context)))
        object.__setattr__(self, "existing_evidence_ids", tuple(self.existing_evidence_ids))
        object.__setattr__(self, "provenance_observation_id_sets", tuple(self.provenance_observation_id_sets))
        object.__setattr__(self, "available_contexts", tuple(self.available_contexts))
        object.__setattr__(self, "matching_contexts", tuple(self.matching_contexts))


@dataclass(frozen=True)
class SpecificationEntry:
    """One `EvidenceGap`'s complete set of requirements -- 1:1 with
    `ExperimentGapAnalysis.gaps`, in the same order. `requirements` holds
    zero (a clean PASS/FAIL on both sides), one, or two entries (never
    more -- `materials.experiment`'s own category assignment guarantees
    at most one per-side category per side, plus at most one cross-side
    category, and a cross-side category can only appear when the side it
    replaces contributed none). Observed and predicted requirements are
    never merged into one -- the same discipline `materials.decision`
    established in Phase 32 and every layer since has preserved."""

    formulation: Referent
    property: str
    criterion: Criterion
    criterion_context: Mapping[str, object]
    requirements: Tuple[EvidenceRequirement, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "criterion_context", MappingProxyType(dict(self.criterion_context)))
        object.__setattr__(self, "requirements", tuple(self.requirements))


@dataclass(frozen=True)
class ExperimentSpecification:
    process_natural_key: str
    gaps: ExperimentGapAnalysis
    entries: Tuple[SpecificationEntry, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", tuple(self.entries))


def _description(formulation: Referent, property_name: str, category: str, reason: Optional[str]) -> Optional[str]:
    """Built only from fields already computed by `materials.experiment`
    -- never invented prose. A clean PASS/FAIL side never reaches here
    (callers only build a requirement when a category is present), so
    `reason` is only ever None for the MISSING_EVIDENCE case where both
    sides' own reasons happen to both be unset, which does not occur in
    practice (INSUFFICIENT_EVIDENCE always populates a reason) but is
    handled without raising rather than assumed impossible."""
    if reason is None:
        return f"{category} for {formulation.natural_key!r} property {property_name!r}"
    return f"{category} for {formulation.natural_key!r} property {property_name!r}: {reason}"


def _side_requirement(gap: EvidenceGap, side: SideGap, role: str) -> Optional[EvidenceRequirement]:
    if not side.categories:
        return None
    category = side.categories[0]
    return EvidenceRequirement(
        formulation=gap.formulation, property=gap.property, criterion=gap.criterion,
        criterion_context=gap.criterion_context, role=role, category=category,
        existing_evidence_ids=side.supporting_ids,
        provenance_observation_id_sets=side.provenance_observation_id_sets,
        available_contexts=side.available_contexts, matching_contexts=side.matching_contexts,
        description=_description(gap.formulation, gap.property, category, side.reason),
    )


def _cross_requirement(gap: EvidenceGap) -> Optional[EvidenceRequirement]:
    if not gap.categories:
        return None
    category = gap.categories[0]

    if category == MISSING_EVIDENCE:
        # Neither side has evidence -- preferring one side's shape over
        # the other would invent a preference the evidence does not
        # express (Phase 35 sec.6D: "represent the missing information
        # requirement neutrally").
        return EvidenceRequirement(
            formulation=gap.formulation, property=gap.property, criterion=gap.criterion,
            criterion_context=gap.criterion_context, role=EITHER, category=category,
            existing_evidence_ids=(), provenance_observation_id_sets=(),
            available_contexts=(), matching_contexts=(),
            description=_description(gap.formulation, gap.property, category, gap.observed.reason or gap.predicted.reason),
        )

    if category == MEASUREMENT_WITHOUT_PREDICTION:
        # Predicted side is what is missing (role); the observed side's
        # existing measurement information is preserved on the
        # requirement per Phase 35 sec.6E.
        return EvidenceRequirement(
            formulation=gap.formulation, property=gap.property, criterion=gap.criterion,
            criterion_context=gap.criterion_context, role=PREDICTED, category=category,
            existing_evidence_ids=gap.observed.supporting_ids,
            provenance_observation_id_sets=gap.observed.provenance_observation_id_sets,
            available_contexts=gap.observed.available_contexts, matching_contexts=gap.observed.matching_contexts,
            description=_description(gap.formulation, gap.property, category, gap.predicted.reason),
        )

    # PREDICTION_WITHOUT_MEASUREMENT: observed side is what is missing
    # (role); the predicted side's IDs and provenance are preserved per
    # Phase 35 sec.6F.
    return EvidenceRequirement(
        formulation=gap.formulation, property=gap.property, criterion=gap.criterion,
        criterion_context=gap.criterion_context, role=OBSERVED, category=category,
        existing_evidence_ids=gap.predicted.supporting_ids,
        provenance_observation_id_sets=gap.predicted.provenance_observation_id_sets,
        available_contexts=gap.predicted.available_contexts, matching_contexts=gap.predicted.matching_contexts,
        description=_description(gap.formulation, gap.property, category, gap.observed.reason),
    )


def _entry_for(gap: EvidenceGap) -> SpecificationEntry:
    requirements = tuple(
        r for r in (
            _side_requirement(gap, gap.observed, OBSERVED),
            _side_requirement(gap, gap.predicted, PREDICTED),
            _cross_requirement(gap),
        )
        if r is not None
    )
    return SpecificationEntry(
        formulation=gap.formulation, property=gap.property, criterion=gap.criterion,
        criterion_context=gap.criterion_context, requirements=requirements,
    )


def specify_experiment_requirements(gaps: ExperimentGapAnalysis) -> ExperimentSpecification:
    """Deterministic, side-effect-free, read-only -- takes only an
    `ExperimentGapAnalysis`; never calls `EvidencePool`/`RetrievalEngine`,
    never mutates `gaps` or anything it references. `entries` is built in
    exactly `gaps.gaps` order (already deterministic per Phase 34), so no
    additional sort is needed here."""
    entries = tuple(_entry_for(gap) for gap in gaps.gaps)
    return ExperimentSpecification(process_natural_key=gaps.process_natural_key, gaps=gaps, entries=entries)
