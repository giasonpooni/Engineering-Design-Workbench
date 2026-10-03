"""MaterialProgramQuery -> MaterialProgramAnswer: the second dimension
Phase 30 demonstrated a real materials program actually needs --
formulation x process x property -- built entirely on top of
`materials.analysis.analyze`, never duplicating its evidence traversal.

Phase 30's own scratch workflow discovered that a formulation's process
condition requires application-side composition SCOUT does not provide:
`Referent --ClaimedRelationship--> Referent`, read directly, with no
`pool.process_for(...)`-style convenience method. That composition
moves here, unchanged in mechanism, still entirely inside `materials/`.

This module is descriptive only, per its own hard scope: it answers
"what evidence exists for these formulations under this process," never
"which formulation should we choose." No ranking, scoring, threshold
assessment, or winner selection exists here -- that discipline was
already established for single-property analysis in
`materials/analysis.py` (Phase 27) and is preserved, not re-decided,
at this composed level.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Tuple

from evidence.pool import EvidencePool
from evidence.types import Referent
from materials.analysis import MaterialPropertyAnswer, MaterialQuestion, _resolve_referent, analyze
from retrieval.engine import RetrievalEngine


@dataclass(frozen=True)
class MaterialProgramQuery:
    """The smallest stable contract Phase 30's actual workload used:
    which formulations, which single process condition, which
    properties. Deduplicated and sorted (`make_material_program_query`)
    so two queries naming the same set in a different order produce an
    identical result -- the same discipline `RetrievalQuery`/
    `DerivedValue.derived_from` already establish. No ranking/scoring/
    optimization/confidence-threshold/epistemic field exists here on
    purpose -- those belong to a later, separate consumer, not this
    one."""

    formulation_natural_keys: Tuple[str, ...]
    process_natural_key: str
    properties: Tuple[str, ...]


def make_material_program_query(
    formulation_natural_keys: Iterable[str], process_natural_key: str, properties: Iterable[str]
) -> MaterialProgramQuery:
    return MaterialProgramQuery(
        formulation_natural_keys=tuple(sorted(set(formulation_natural_keys))),
        process_natural_key=process_natural_key,
        properties=tuple(sorted(set(properties))),
    )


@dataclass(frozen=True)
class FormulationProcessAssociation:
    """What a formulation is actually connected to via the
    `ClaimedRelationship` graph -- never fewer than zero relationships,
    never silently collapsed to one when more exist (Phase 31 §10:
    "preserve the relationships rather than silently selecting one").
    `processes` is every related referent with `kind == "process"` --
    an application-level convention every existing materials fixture
    (Phases 26/27/28/30) already follows, not a structural guarantee:
    `Referent.kind` has no controlled vocabulary anywhere in the
    substrate. `matches_queried_process` is True iff the query's own
    `process_natural_key` resolves to one of `processes`'s ids --
    regardless of how many OTHER processes the formulation is also
    connected to."""

    formulation: Referent
    processes: Tuple[Referent, ...]
    matches_queried_process: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "processes", tuple(self.processes))


@dataclass(frozen=True)
class PropertyEvidence:
    """One requested property's full `MaterialPropertyAnswer`,
    unmodified -- observed values, predictions, provenance, grounding,
    and comparability-aware disagreement all pass through exactly as
    `materials.analysis.analyze` produced them. Nothing here flattens,
    merges, or re-derives any of it."""

    property: str
    answer: MaterialPropertyAnswer


@dataclass(frozen=True)
class FormulationProgramEntry:
    formulation: Referent
    process_association: FormulationProcessAssociation
    properties: Tuple[PropertyEvidence, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "properties", tuple(self.properties))


@dataclass(frozen=True)
class MaterialProgramAnswer:
    """Every requested formulation, always present -- matching and
    non-matching alike (Phase 31 explicitly avoids silently dropping a
    requested formulation just because it isn't associated with the
    queried process; a caller who wants only the matching set filters
    on `entry.process_association.matches_queried_process` itself,
    which is a caller decision, not one this layer makes for them)."""

    process_natural_key: str
    formulations: Tuple[FormulationProgramEntry, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "formulations", tuple(self.formulations))


def _related_referent_ids(pool: EvidencePool, formulation_referent_id: str) -> Tuple[str, ...]:
    """Every referent this formulation's ClaimedRelationships point to,
    regardless of kind or relationship type -- the raw, un-interpreted
    membership graph, read directly (no SCOUT convenience method
    exists or is added for this)."""
    ids = {rel.to_referent_id for rel in pool.all_claimed_relationships() if rel.from_referent_id == formulation_referent_id}
    return tuple(sorted(ids))


def _processes_for(pool: EvidencePool, formulation_referent_id: str) -> Tuple[Referent, ...]:
    related_ids = set(_related_referent_ids(pool, formulation_referent_id))
    return tuple(sorted((r for r in pool.all_referents() if r.id in related_ids and r.kind == "process"), key=lambda r: r.id))


def _formulation_entry(
    pool: EvidencePool, engine: RetrievalEngine, natural_key: str, properties: Tuple[str, ...], queried_process: Referent
) -> FormulationProgramEntry:
    formulation = _resolve_referent(pool, natural_key)
    processes = _processes_for(pool, formulation.id)
    association = FormulationProcessAssociation(
        formulation=formulation,
        processes=processes,
        matches_queried_process=queried_process.id in {p.id for p in processes},
    )
    property_evidence = tuple(
        PropertyEvidence(property=prop, answer=analyze(pool, engine, MaterialQuestion(natural_key, prop)))
        for prop in properties
    )
    return FormulationProgramEntry(formulation=formulation, process_association=association, properties=property_evidence)


def analyze_program(pool: EvidencePool, engine: RetrievalEngine, query: MaterialProgramQuery) -> MaterialProgramAnswer:
    """Deterministic, side-effect-free, read-only -- composes
    `materials.analysis.analyze` once per (formulation, property) pair
    plus the process-association lookup above; calls no `put_*` or
    `admit_*` anywhere. Raises `KeyError` immediately if
    `query.process_natural_key` does not resolve (same behavior
    `_resolve_referent` already gives `analyze` for an unknown
    formulation)."""
    queried_process = _resolve_referent(pool, query.process_natural_key)
    formulations = tuple(
        _formulation_entry(pool, engine, natural_key, query.properties, queried_process)
        for natural_key in query.formulation_natural_keys
    )
    return MaterialProgramAnswer(process_natural_key=query.process_natural_key, formulations=formulations)
