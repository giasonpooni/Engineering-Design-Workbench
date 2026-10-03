"""Pool object types (`docs/PHASE_14_DATA_POOL_ARCHITECTURE.md` §B/§D).

Naming deliberately follows that document's own collision warning:
`Referent` (not `Entity` -- `morpho/ir.py` already owns that name) and
`ClaimedRelationship` (not `Relationship` -- ditto for `MorphoRelation`).

Every type here is immutable once constructed, exactly like
`core/canonical/state.py`'s `Field`/`EdgeRecord`/`CanonicalState`: an
"update" is always a *new* object referencing its predecessor by id,
never an in-place edit. Nothing in this module is ever deleted by
anything in this repository -- see `evidence/pool.py`.

The ONLY supported way to construct one of these is its `make_*`
factory below -- exactly the discipline `core/canonical/version.py`'s
`make_version` already establishes ("the id is always derived from
content, never supplied by the caller, so an object's id can never
disagree with its own content"). Constructing a dataclass directly with
a hand-picked `id` bypasses that guarantee and is a caller error, not a
supported path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Iterable, Mapping, Optional, Tuple

from evidence.identity import content_hash


@dataclass(frozen=True)
class Source:
    """Origin of documents (§B). Identity is independent of any one
    document, so two documents from "the same place" naturally converge
    on one Source record rather than being silently duplicated."""

    id: str
    kind: str  # "paper" | "patent" | "github_repo" | "documentation" | ...
    name: str


def make_source(kind: str, name: str) -> Source:
    source_id = content_hash({"kind": kind, "name": name})
    return Source(id=source_id, kind=kind, name=name)


@dataclass(frozen=True)
class Document:
    """A retrieved artifact (§B). Immutable once ingested -- a changed
    source produces a *new* Document, exactly mirroring how a changed
    CanonicalState produces a new Version rather than mutating the old
    one. `raw_content` is kept on the object (not just its hash) because,
    unlike CanonicalState, nothing downstream reconstructs it from
    elsewhere -- this pool is its own store of record for raw evidence."""

    id: str
    source_id: str
    raw_content: str
    retrieval_method: str
    retrieved_at: str  # ISO-8601 UTC, caller-supplied -- never wall-clock


def make_document(source_id: str, raw_content: str, retrieval_method: str, retrieved_at: str) -> Document:
    content = content_hash(raw_content)
    doc_id = content_hash(
        {"source_id": source_id, "content_hash": content, "retrieval_method": retrieval_method}
    )
    return Document(
        id=doc_id,
        source_id=source_id,
        raw_content=raw_content,
        retrieval_method=retrieval_method,
        retrieved_at=retrieved_at,
    )


@dataclass(frozen=True)
class Record:
    """One raw structural unit within a Document (§B) -- still mechanical,
    not yet a semantic claim. `locator` is deliberately loosely typed
    (§D): a page/table/row description, a byte range, a section heading
    -- whatever is meaningful for the source format, validated only by
    convention, never forced into one universal locator schema."""

    id: str
    document_id: str
    locator: str
    raw_content: str


def make_record(document_id: str, locator: str, raw_content: str) -> Record:
    record_id = content_hash({"document_id": document_id, "locator": locator, "raw_content": raw_content})
    return Record(id=record_id, document_id=document_id, locator=locator, raw_content=raw_content)


@dataclass(frozen=True)
class Observation:
    """A semantic, extracted fact (§B), tied to the Record(s) it came
    from. Identity covers only what makes it *this* fact -- the source
    records, the extraction method, and the extracted content itself --
    never `confidence` or `extracted_at`, which are epistemic/temporal
    annotations that can differ between two otherwise-identical
    re-extractions without them being "different facts." This is what
    makes "same source, same extraction configuration -> same canonical
    observation" (this phase's determinism requirement) hold: re-running
    a deterministic extractor over the same Record always yields the
    same `Observation.id`, even if `extracted_at` differs.

    `content` is an open, extraction-defined mapping (e.g.
    {"property": "melt_viscosity", "value": 1250, "unit": "Pa.s"} or
    {"subject": "FEP", "predicate": "used_in", "object": "extrusion"})
    -- deliberately not forced into one schema, mirroring `Locator`'s own
    open-payload choice (§D) and this project's repeated conclusion
    (Phase 12, Phase 13 §L) that a universal ontology is not a
    prerequisite for representing heterogeneous evidence."""

    id: str
    record_ids: Tuple[str, ...]
    extraction_method: str  # "human_transcription" | "regex:<name>" | "model:<name>" | ...
    content: Mapping[str, object]
    confidence: float  # required, always a float -- see admit_observation for the model-source rule
    extracted_at: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "record_ids", tuple(self.record_ids))
        object.__setattr__(self, "content", MappingProxyType(dict(self.content)))
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"Observation.confidence must be in [0, 1], got {self.confidence!r}")


def make_observation(
    record_ids: Tuple[str, ...],
    extraction_method: str,
    content: Mapping[str, object],
    confidence: float,
    extracted_at: str,
) -> Observation:
    record_ids = tuple(sorted(record_ids))
    obs_id = content_hash(
        {"record_ids": list(record_ids), "extraction_method": extraction_method, "content": dict(sorted(content.items()))}
    )
    return Observation(
        id=obs_id,
        record_ids=record_ids,
        extraction_method=extraction_method,
        content=content,
        confidence=confidence,
        extracted_at=extracted_at,
    )


@dataclass(frozen=True)
class Referent:
    """The specific material/instrument/process/sample/concept a Claim is
    *about* (§B, called `Referent` rather than `Entity` to avoid
    colliding with `morpho.ir.Entity`). Identity is a deterministic
    function of an explicit `natural_key` the caller supplies (e.g. a
    normalized label) -- there is NO fuzzy entity resolution here.
    Two observations naming the identical natural_key converge on one
    Referent; two observations naming "FEP" and "Teflon FEP" do NOT
    automatically merge, because entity resolution is an explicitly
    unresolved research question (`docs/PHASE_14_DATA_POOL_ARCHITECTURE.md`
    §S) -- a proposed merge belongs in a `same_as`-typed
    ClaimedRelationship, itself just evidence, never an automatic
    collapse of two ids into one."""

    id: str
    natural_key: str
    kind: str  # "material" | "instrument" | "process" | "sample" | "concept" | ...


def make_referent(natural_key: str, kind: str) -> Referent:
    ref_id = content_hash({"natural_key": natural_key, "kind": kind})
    return Referent(id=ref_id, natural_key=natural_key, kind=kind)


@dataclass(frozen=True)
class ClaimedRelationship:
    """An asserted connection between two Referents (§B, `Relationship`
    renamed for the same collision-avoidance reason as `Referent`).
    Identity includes the source `observation_id` -- not just
    (from, to, type) -- because two sources can claim different, even
    contradictory, relationships between the same two Referents, and
    §E's conflict model requires both claims to coexist rather than one
    silently overwriting the other."""

    id: str
    from_referent_id: str
    to_referent_id: str
    type: str
    observation_id: str
    confidence: float

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"ClaimedRelationship.confidence must be in [0, 1], got {self.confidence!r}")


def make_claimed_relationship(
    from_referent_id: str, to_referent_id: str, type: str, observation_id: str, confidence: float
) -> ClaimedRelationship:
    rel_id = content_hash(
        {
            "from_referent_id": from_referent_id,
            "to_referent_id": to_referent_id,
            "type": type,
            "observation_id": observation_id,
        }
    )
    return ClaimedRelationship(
        id=rel_id,
        from_referent_id=from_referent_id,
        to_referent_id=to_referent_id,
        type=type,
        observation_id=observation_id,
        confidence=confidence,
    )


@dataclass(frozen=True)
class DerivedValue:
    """A value synthesized *from* other Observations and/or DerivedValues
    (`docs/COMPUTATIONAL_COMMONS.md` §B/§E) -- the first representation in
    this codebase for "using O1, O2, and O3, method M, I derive value V,"
    as opposed to `Observation`, which is always tied to exactly one
    extraction event over one Record. Identity covers only what makes it
    *this* derivation -- the inputs, the method, and the derived content
    -- never `confidence` or `derived_at`, the same discipline
    `Observation` already establishes and for the same reason: a
    re-derivation with the identical inputs/method/content is the same
    fact, even if its confidence or the moment it was recorded differs.

    `derived_from` may reference Observation ids, DerivedValue ids, or a
    mix of both -- a derivation may itself be re-derived (§E: "can itself
    be superseded by a better derivation"). Referential integrity (do the
    referenced ids actually exist in the pool) is checked at admission
    (`evidence/admission.py::admit_derived_value`), not here -- exactly
    the same split `make_claimed_relationship`/`admit_claimed_relationship`
    already establish.

    A derivation cycle (A referencing B, B referencing A) cannot exist at
    all, for a reason more fundamental than admission ordering: `id` is
    computed from `content_hash({derived_from, ...})`, so a `derived_from`
    containing the other object's id requires that id to already be a
    concrete value. Two objects whose `derived_from` each named the
    other's id could never have either id computed in the first place --
    the mutual dependency has no resolution, independent of whether
    admission is ever consulted. Admission's own, separate job is
    narrower: rejecting a *dangling* reference to an id that was never
    admitted at all (see `admit_derived_value`) -- see
    `tests/test_evidence_derived_value.py` for that proof."""

    id: str
    derived_from: Tuple[str, ...]
    method: str
    content: Mapping[str, object]
    confidence: float
    derived_at: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "derived_from", tuple(self.derived_from))
        object.__setattr__(self, "content", MappingProxyType(dict(self.content)))
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"DerivedValue.confidence must be in [0, 1], got {self.confidence!r}")


def make_derived_value(
    derived_from: Iterable[str],
    method: str,
    content: Mapping[str, object],
    confidence: float,
    derived_at: str,
) -> DerivedValue:
    # Deduplicated AND sorted before hashing -- unlike make_observation's
    # record_ids (sorted only), derived_from is explicitly deduplicated
    # per this phase's specification, so citing the same input twice
    # never changes identity.
    derived_from = tuple(sorted(set(derived_from)))
    derived_id = content_hash(
        {
            "derived_from": list(derived_from),
            "method": method,
            "content": dict(sorted(content.items())),
        }
    )
    return DerivedValue(
        id=derived_id,
        derived_from=derived_from,
        method=method,
        content=content,
        confidence=confidence,
        derived_at=derived_at,
    )


@dataclass(frozen=True)
class DerivedGrounding:
    """What a DerivedValue is ABOUT, kept strictly separate from what it
    was derived FROM (Phase 18's `derived_from`/`ancestry_of`) --
    `docs/PHASE_14_DATA_POOL_ARCHITECTURE.md` §M sketches an `--about-->`
    arrow from evidence to a Referent, but no code anywhere implemented
    it before this phase, for any type.

    Identity is `content_hash({derived_value_id, referent_ids})` --
    `DerivedValue.id` itself is deliberately untouched: folding
    `referent_ids` into DerivedValue's own identity would mean a
    derivation-fact (inputs + method + content) could never be shared or
    reused across two different asserted subjects, the same reason
    `ClaimedRelationship` is a separate object from `Observation` rather
    than a field on it. `referent_ids` is one-or-more, not a from/to
    pair -- most derived facts are unary ("82% conversion for Reactor
    A"), not a relationship between two Referents, and forcing a unary
    fact into a binary shape would require an unjustified second
    referent. What *kind* of connection this is stays in
    `DerivedValue.method`/`content`, exactly as `Observation.content`
    already carries semantic detail without a forced schema -- this
    object states only WHICH Referent(s), nothing about WHY.

    Multiple, even conflicting, groundings for the same DerivedValue can
    coexist -- content-addressed identity already makes this automatic,
    the same discipline `ClaimedRelationship` establishes for
    conflicting claims -- so no new conflict-resolution mechanism is
    introduced here."""

    id: str
    derived_value_id: str
    referent_ids: Tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "referent_ids", tuple(self.referent_ids))


def make_derived_grounding(derived_value_id: str, referent_ids: Iterable[str]) -> DerivedGrounding:
    referent_ids = tuple(sorted(set(referent_ids)))
    grounding_id = content_hash({"derived_value_id": derived_value_id, "referent_ids": list(referent_ids)})
    return DerivedGrounding(id=grounding_id, derived_value_id=derived_value_id, referent_ids=referent_ids)
