"""assemble_experimental_design(plan, ...) -> ExperimentalDesign: the
first experimental-design representation layer above materials.plan.

An `ActionCandidate` says WHAT KIND of evidence-acquisition action was
selected (`action_class`, a generic domain+specificity tag like
"measurement:repeat"). An `ExperimentalDesign` says WHAT PARAMETERS have
been specified for carrying that action out. This module represents
those parameters; it never decides them, ranks them, or optimizes them.

Before writing this module, every upstream structure an
ExperimentalDesign could draw from was inspected
(`materials/plan.py::ExperimentPlanEntry`, `materials/candidates.py::
ActionCandidate`, `materials/specification.py::EvidenceRequirement`) to
determine exactly what design-relevant information already exists,
rather than assuming any of it. The answer: exactly ONE field anywhere
in the existing pipeline has the shape of an experimental-design
parameter set -- `ActionCandidate.target_context` (== the triggering
`EvidenceRequirement.criterion_context`, an open `Mapping[str, object]`
of condition keys a caller already declared, e.g. `{"temperature": 25,
"temperature_unit": "C"}`). Nothing else scientifically useful for a
design -- measurement method, model-validation method, instrument,
replicate count, composition, process condition -- exists anywhere
upstream: `action_class` names a DOMAIN, not a method; `EvidenceRequirement`
carries a formulation identity but no composition breakdown; process
identity exists only at the top-level `process_natural_key` a query was
run against (Phase 31 onward), never attached to an individual
requirement/candidate/plan entry. None of those is fabricated here.

Every design entry therefore distinguishes exactly three kinds of
information, never blurring them:

  inherited_parameters -- copied verbatim from `ActionCandidate.
  target_context` via the embedded `ExperimentPlanEntry`. The only
  parameter data the architecture can actually justify without a caller
  supplying anything.

  specified_parameters -- an open `Mapping[str, object]` the CALLER
  explicitly supplies at design-assembly time (e.g. replicate_count,
  instrument, method). This module places no schema or validation on
  the values -- exactly the same open-content discipline
  `Observation.content`/`Criterion.context`/`DerivedValue.content`
  already establish -- because inventing a schema here would be
  inventing the laboratory ontology this phase explicitly forbids.

  unspecified_parameter_keys -- parameter keys the CALLER explicitly
  flags as known-to-matter but not yet determined. This module never
  infers this set on its own (there is no way to enumerate "what a
  design should specify" without inventing domain knowledge) -- a
  parameter simply absent from both `specified_parameters` and
  `unspecified_parameter_keys` is neither claimed determined nor
  claimed pending; it was never mentioned at all, which is itself an
  honest, distinct state from either.

A key may not appear in both `specified_parameters` and
`unspecified_parameter_keys` at once -- that is a caller contradiction,
rejected rather than silently resolved.

Provenance: `ExperimentalDesignEntry.plan_entry` embeds the complete,
unmodified `ExperimentPlanEntry` -- which itself already embeds the
complete `CandidateSelection` -> `CandidateEvaluation` -> `ActionCandidate`
-> targeted `EvidenceRequirement`s (Phase 37-40's own chain). Nothing is
duplicated or recomputed here; the full
ExperimentPlanEntry->CandidateSelection->CandidateEvaluation->
ActionCandidate->EvidenceRequirement->EvidenceGap chain this phase asks
for is already reachable by walking that one embedded object.

No new identity is introduced for the parameter fields: ordering
reuses `plan_entry.candidate_id` (== the untouched `ActionCandidate.id`
from Phase 37) -- the same "reuse the existing canonical id rather than
minting a new one" choice every layer since Phase 38 has already made.

Phase 42 -- method integration: `materials.method.ExperimentalMethod`
(a structured, content-addressed representation of WHICH measurement or
validation technique a design entry is asking to perform, distinct from
`action_class`'s generic domain tag -- see that module's own docstring
for the full ontology reasoning) is referenced here via `method` and
`method_status`. Three states, never blurred, mirroring the parameter
distinction above: `METHOD_SPECIFIED` (the caller supplied an
`ExperimentalMethod`), `METHOD_UNSPECIFIED` (the caller supplied
nothing), and `METHOD_INHERITED` (reserved for a method derivable from
upstream data without the caller supplying one). `METHOD_INHERITED` is
never actually produced by `assemble_experimental_design` today: the
only place a hint of method might exist is the underlying
`Observation.extraction_method`/`DerivedValue.method` string on the
evidence a requirement references -- but `EvidenceRequirement` carries
only evidence IDs, not the Observation/DerivedValue objects themselves,
and resolving an id back to its object requires `EvidencePool` access
that this layer -- like every layer since `materials.decision` --
deliberately never has. The state is kept in the taxonomy rather than
omitted, so a future layer that legitimately has that access can
produce it without this module's contract changing.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Optional, Tuple

from materials.method import ExperimentalMethod
from materials.plan import ExperimentPlan, ExperimentPlanEntry

METHOD_SPECIFIED = "METHOD_SPECIFIED"
METHOD_INHERITED = "METHOD_INHERITED"
METHOD_UNSPECIFIED = "METHOD_UNSPECIFIED"


@dataclass(frozen=True)
class ExperimentalDesignEntry:
    """One plan entry's experimental-design representation. `plan_entry`
    is the complete, unmodified `ExperimentPlanEntry` -- full provenance
    without duplication (see module docstring)."""

    plan_entry: ExperimentPlanEntry
    inherited_parameters: Mapping[str, object]
    specified_parameters: Mapping[str, object]
    unspecified_parameter_keys: Tuple[str, ...]
    method: Optional[ExperimentalMethod]
    method_status: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "inherited_parameters", MappingProxyType(dict(self.inherited_parameters)))
        object.__setattr__(self, "specified_parameters", MappingProxyType(dict(self.specified_parameters)))
        object.__setattr__(self, "unspecified_parameter_keys", tuple(self.unspecified_parameter_keys))
        overlap = set(self.specified_parameters) & set(self.unspecified_parameter_keys)
        if overlap:
            raise ValueError(
                f"parameter key(s) {sorted(overlap)} cannot be both specified and unspecified for the same design entry"
            )
        if (self.method is not None) != (self.method_status != METHOD_UNSPECIFIED):
            raise ValueError("ExperimentalDesignEntry.method and method_status are inconsistent")


@dataclass(frozen=True)
class ExperimentalDesign:
    process_natural_key: str
    plan: ExperimentPlan
    entries: Tuple[ExperimentalDesignEntry, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", tuple(self.entries))


def make_experimental_design_entry(
    plan_entry: ExperimentPlanEntry,
    specified_parameters: Optional[Mapping[str, object]] = None,
    unspecified_parameter_keys: Tuple[str, ...] = (),
    method: Optional[ExperimentalMethod] = None,
) -> ExperimentalDesignEntry:
    """`inherited_parameters` is always exactly `plan_entry.target_context`
    -- never re-derived, never extended with a guess. `method_status` is
    derived only from whether a caller passed `method` -- never
    `METHOD_INHERITED` (see module docstring for why that state is
    unreachable from this function)."""
    return ExperimentalDesignEntry(
        plan_entry=plan_entry,
        inherited_parameters=plan_entry.target_context,
        specified_parameters=specified_parameters or {},
        unspecified_parameter_keys=unspecified_parameter_keys,
        method=method,
        method_status=METHOD_SPECIFIED if method is not None else METHOD_UNSPECIFIED,
    )


def assemble_experimental_design(
    plan: ExperimentPlan,
    design_parameters: Optional[Mapping[str, Mapping[str, object]]] = None,
    unspecified_parameter_keys: Optional[Mapping[str, Tuple[str, ...]]] = None,
    methods: Optional[Mapping[str, ExperimentalMethod]] = None,
) -> ExperimentalDesign:
    """Deterministic, side-effect-free, read-only -- takes an
    ExperimentPlan plus explicitly caller-supplied design information,
    never anything from EvidencePool/RetrievalEngine, and never mutates
    `plan` or anything it references.

    `design_parameters`/`unspecified_parameter_keys`/`methods` are all
    keyed by `ExperimentPlanEntry.candidate_id` -- a plan entry not
    mentioned in any of them simply receives no explicitly-specified and
    no explicitly-unspecified parameters, and `method_status=
    METHOD_UNSPECIFIED` (an honest "the caller said nothing about this
    entry," never a guessed value).

    Ordering: exactly `plan.entries` order, which Phase 40 already made
    deterministic (sorted by `ActionCandidate.id`) -- no additional sort
    is needed here."""
    design_parameters = design_parameters or {}
    unspecified_parameter_keys = unspecified_parameter_keys or {}
    methods = methods or {}
    entries = tuple(
        make_experimental_design_entry(
            plan_entry,
            specified_parameters=design_parameters.get(plan_entry.candidate_id),
            unspecified_parameter_keys=unspecified_parameter_keys.get(plan_entry.candidate_id, ()),
            method=methods.get(plan_entry.candidate_id),
        )
        for plan_entry in plan.entries
    )
    return ExperimentalDesign(process_natural_key=plan.process_natural_key, plan=plan, entries=entries)
