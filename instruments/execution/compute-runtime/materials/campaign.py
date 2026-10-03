"""assemble_experimental_campaign(design, campaign_id=None) ->
ExperimentalCampaign: the first execution-ORIENTED representation above
materials.design -- still not execution. It represents a concrete
campaign derived from an already-assembled ExperimentalDesign: which
entries exist, whether each currently has enough information to be
executed, and an honest initial lifecycle position. It never runs
anything, never talks to a laboratory, and never introduces cost,
scheduling, or optimization.

Everything this module can determine comes from exactly two places
already inspected before writing it: `ExperimentalDesignEntry` itself
(`method`/`method_status`, `inherited_parameters`/`specified_parameters`/
`unspecified_parameter_keys`) and, transitively through its embedded
`plan_entry` (`candidate_id`, `action_class`, `formulation`, `property`,
`role`, `target_context`). Nothing else is available at this boundary
without reaching into `EvidencePool` -- which, like every layer since
`materials.decision`, this module never does.

READINESS is derived from exactly one rule, using only fields already on
`ExperimentalDesignEntry`: an entry is `READY` iff its method is
`METHOD_SPECIFIED` AND it has no outstanding
`unspecified_parameter_keys`; otherwise it is `INCOMPLETE`. No
instrument availability, operator availability, laboratory capability,
cost, scheduling, or safety information exists anywhere upstream, so
none of those enters this rule -- an entry missing them is simply never
claimed `READY` on their account, because nothing here knows about them
at all.

EXECUTION_STATE is a separate, wider vocabulary
(PLANNED/READY/IN_PROGRESS/COMPLETED/FAILED/CANCELLED) for a lifecycle a
future execution-ingestion layer would advance as real events occur.
`assemble_experimental_campaign` only ever produces two of those six
values -- `READY` when `readiness == READY`, `PLANNED` otherwise -- and
this is not a redundant field: `readiness` is a static fact about design
completeness that can be recomputed at any time and never changes on its
own; `execution_state` is the mutable lifecycle position a later layer
would move forward (IN_PROGRESS, then COMPLETED/FAILED/CANCELLED) as
real events arrive. The two coincide only at this specific moment --
freshly assembled, nothing executed yet -- which is the only moment this
module ever produces. `assemble_experimental_campaign` never produces
IN_PROGRESS/COMPLETED/FAILED/CANCELLED itself; inventing an execution
event to justify one of those would be exactly the fabricated execution
evidence this phase forbids.

Provenance: `ExperimentalCampaignEntry.design_entry` embeds the complete,
unmodified `ExperimentalDesignEntry`, which itself already embeds the
complete `ExperimentPlanEntry` -> `CandidateSelection` ->
`CandidateEvaluation` -> `ActionCandidate` -> targeted
`EvidenceRequirement`s (Phase 37-41's own chain, untouched). The
requested chain continues past `EvidenceRequirement` to `EvidenceGap`
and `MaterialPropertyAnswer`/provenance -- these are not reachable
per-entry (`EvidenceRequirement` itself never embedded its originating
`EvidenceGap`, by Phase 35's own design), but ARE reachable at the
campaign level: `campaign.design.plan.selection.evaluations.candidates.
specification.gaps.audit.decision` walks down to each
`PropertyDecision.evidence: Optional[MaterialPropertyAnswer]`, and from
there to the underlying observation/prediction provenance already
carried by Phase 27-29's own objects. Nothing here duplicates any of
that chain; it is reused exactly as it already exists.

Identity: `campaign_id`, if the caller supplies one, is used verbatim --
an explicit, human-meaningful campaign label (e.g. "Q3-tensile-followup")
is exactly as legitimate an identity as a content-derived one, and this
module does not second-guess it. If omitted, a deterministic,
content-derived id is computed with the existing
`evidence.identity.content_hash` over the design's `process_natural_key`
and the sorted set of its entries' candidate ids -- no new hashing
system is introduced.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Optional, Tuple

from evidence.identity import content_hash
from evidence.types import Referent
from materials.design import METHOD_SPECIFIED, ExperimentalDesign, ExperimentalDesignEntry
from materials.method import ExperimentalMethod

READY = "READY"
INCOMPLETE = "INCOMPLETE"
ALL_READINESS_STATES = (READY, INCOMPLETE)

PLANNED = "PLANNED"
IN_PROGRESS = "IN_PROGRESS"
COMPLETED = "COMPLETED"
FAILED = "FAILED"
CANCELLED = "CANCELLED"
# READY (above) is deliberately shared between the readiness and
# execution_state vocabularies -- see module docstring.
ALL_EXECUTION_STATES = (PLANNED, READY, IN_PROGRESS, COMPLETED, FAILED, CANCELLED)


@dataclass(frozen=True)
class ExperimentalCampaignEntry:
    """One design entry's campaign representation. `candidate_id`
    through `unspecified_parameter_keys` are copied verbatim from the
    underlying `ExperimentalDesignEntry` (directly, or via its embedded
    `plan_entry`) for direct inspection; `design_entry` is the complete,
    unmodified Phase 41 object -- full provenance without duplication."""

    candidate_id: str
    action_class: str
    formulation: Referent
    property: str
    role: str
    target_context: Mapping[str, object]
    method: Optional[ExperimentalMethod]
    method_status: str
    inherited_parameters: Mapping[str, object]
    specified_parameters: Mapping[str, object]
    unspecified_parameter_keys: Tuple[str, ...]
    design_entry: ExperimentalDesignEntry
    readiness: str
    execution_state: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_context", MappingProxyType(dict(self.target_context)))
        object.__setattr__(self, "inherited_parameters", MappingProxyType(dict(self.inherited_parameters)))
        object.__setattr__(self, "specified_parameters", MappingProxyType(dict(self.specified_parameters)))
        object.__setattr__(self, "unspecified_parameter_keys", tuple(self.unspecified_parameter_keys))


@dataclass(frozen=True)
class ExperimentalCampaign:
    id: str
    process_natural_key: str
    design: ExperimentalDesign
    entries: Tuple[ExperimentalCampaignEntry, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", tuple(self.entries))


def _readiness_for(design_entry: ExperimentalDesignEntry) -> str:
    if design_entry.method_status == METHOD_SPECIFIED and not design_entry.unspecified_parameter_keys:
        return READY
    return INCOMPLETE


def _entry_for(design_entry: ExperimentalDesignEntry) -> ExperimentalCampaignEntry:
    plan_entry = design_entry.plan_entry
    readiness = _readiness_for(design_entry)
    return ExperimentalCampaignEntry(
        candidate_id=plan_entry.candidate_id, action_class=plan_entry.action_class,
        formulation=plan_entry.formulation, property=plan_entry.property, role=plan_entry.role,
        target_context=plan_entry.target_context,
        method=design_entry.method, method_status=design_entry.method_status,
        inherited_parameters=design_entry.inherited_parameters,
        specified_parameters=design_entry.specified_parameters,
        unspecified_parameter_keys=design_entry.unspecified_parameter_keys,
        design_entry=design_entry, readiness=readiness,
        execution_state=READY if readiness == READY else PLANNED,
    )


def _default_campaign_id(design: ExperimentalDesign) -> str:
    payload = {
        "process_natural_key": design.process_natural_key,
        "candidate_ids": sorted(e.plan_entry.candidate_id for e in design.entries),
    }
    return content_hash(payload)


def assemble_experimental_campaign(design: ExperimentalDesign, campaign_id: Optional[str] = None) -> ExperimentalCampaign:
    """Deterministic, side-effect-free, read-only -- takes an
    ExperimentalDesign plus an optional caller-supplied `campaign_id`;
    never calls EvidencePool/RetrievalEngine, never mutates `design` or
    anything it references, never executes anything.

    Ordering: entries are sorted by `candidate_id` (== the untouched
    `ActionCandidate.id` from Phase 37) -- independent of
    `design.entries`' own insertion order, dict/set iteration, or
    PYTHONHASHSEED."""
    ordered = tuple(sorted(design.entries, key=lambda e: e.plan_entry.candidate_id))
    entries = tuple(_entry_for(e) for e in ordered)
    resolved_id = campaign_id if campaign_id is not None else _default_campaign_id(design)
    return ExperimentalCampaign(
        id=resolved_id, process_natural_key=design.process_natural_key, design=design, entries=entries,
    )
