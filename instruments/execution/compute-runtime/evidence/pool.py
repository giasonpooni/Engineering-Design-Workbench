"""EvidencePool: in-memory, append-only store for pool objects.

Same shape as `core/canonical/version.py::InMemoryVersionStore` --
single-writer, in-process, v1 only (§S: no real database is implied or
required yet). The one deliberate difference: `VersionStore` has one
head; `EvidencePool` has none, because unlike `CanonicalState` there is
no single "current" evidence state -- conflicting, coexisting
Observations are the point (§E), not a bug to resolve here.

Nothing is ever deleted. Because every id is content-addressed
(`evidence/identity.py`), re-putting an object that already exists is a
no-op by construction -- there is no way to construct two *different*
objects that collide on the same id, so unlike
`core.canonical.state.CanonicalState`'s `fields[key].id` check, there is
no possible mismatch to detect here.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from evidence.identity import content_hash
from evidence.types import (
    ClaimedRelationship,
    DerivedGrounding,
    DerivedValue,
    Document,
    Observation,
    Record,
    Referent,
    Source,
)


class EvidencePool:
    def __init__(self) -> None:
        self._sources: Dict[str, Source] = {}
        self._documents: Dict[str, Document] = {}
        self._records: Dict[str, Record] = {}
        self._observations: Dict[str, Observation] = {}
        self._referents: Dict[str, Referent] = {}
        self._claimed_relationships: Dict[str, ClaimedRelationship] = {}
        # Phase 17: DerivedValue -- a seventh evidence category, synthesized
        # from Observations and/or other DerivedValues (never raw Records
        # directly). Same storage/identity/write-observation discipline as
        # every category above.
        self._derived_values: Dict[str, DerivedValue] = {}
        # Phase 19: DerivedGrounding -- an eighth evidence category,
        # declaring which Referent(s) a DerivedValue is about. Strictly
        # additive: it does not touch DerivedValue's own storage or
        # identity, and is never consulted by provenance (evidence/
        # provenance.py) or the Trust Graph (evidence/trust_graph.py).
        self._derived_groundings: Dict[str, DerivedGrounding] = {}
        # Phase 16: append-only history of observed fingerprint() values.
        # See fingerprint_history() below -- populated only from inside the
        # six put_* methods, never from a read accessor (including
        # fingerprint() itself, which stays exactly as it was in Phase 15).
        self._fingerprint_history: List[str] = []

    # -- put: idempotent, append-only, never overwrites with different content (impossible by
    #    construction since ids are content hashes -- see module docstring) --

    def put_source(self, source: Source) -> None:
        self._sources[source.id] = source
        self._observe_fingerprint()

    def put_document(self, document: Document) -> None:
        self._documents[document.id] = document
        self._observe_fingerprint()

    def put_record(self, record: Record) -> None:
        self._records[record.id] = record
        self._observe_fingerprint()

    def put_observation(self, observation: Observation) -> None:
        self._observations[observation.id] = observation
        self._observe_fingerprint()

    def put_referent(self, referent: Referent) -> None:
        self._referents[referent.id] = referent
        self._observe_fingerprint()

    def put_claimed_relationship(self, relationship: ClaimedRelationship) -> None:
        self._claimed_relationships[relationship.id] = relationship
        self._observe_fingerprint()

    def put_derived_value(self, derived_value: DerivedValue) -> None:
        self._derived_values[derived_value.id] = derived_value
        self._observe_fingerprint()

    def put_derived_grounding(self, grounding: DerivedGrounding) -> None:
        self._derived_groundings[grounding.id] = grounding
        self._observe_fingerprint()

    def _observe_fingerprint(self) -> None:
        """The Phase 16 observation boundary (`docs/RETRIEVAL_ARCHITECTURE.md`
        §7): called after a put_* method has already stored its object, so
        `self.fingerprint()` here reflects the post-write state. Appends
        only when it differs from the last recorded entry -- the compare-
        and-append rule from the approved Phase 16 specification, kept as
        a plain private method (not a free-standing helper) since it is
        shared by all eight put_* call sites (put_source, put_document,
        put_record, put_observation, put_referent,
        put_claimed_relationship, put_derived_value -- added Phase 17,
        put_derived_grounding -- added Phase 19) and has no reason to
        exist independent of `EvidencePool`'s own state. `fingerprint()`
        itself is untouched: this method calls it, it never calls back
        into this method. Any future put_* method must call this too --
        nothing enforces that structurally, it is a convention, not a
        guarantee (see the Phase 17 post-implementation audit)."""
        current = self.fingerprint()
        if not self._fingerprint_history or self._fingerprint_history[-1] != current:
            self._fingerprint_history.append(current)

    # -- get --

    def get_source(self, source_id: str) -> Source:
        return self._sources[source_id]

    def get_document(self, document_id: str) -> Document:
        return self._documents[document_id]

    def get_record(self, record_id: str) -> Record:
        return self._records[record_id]

    def get_observation(self, observation_id: str) -> Observation:
        return self._observations[observation_id]

    def get_referent(self, referent_id: str) -> Referent:
        return self._referents[referent_id]

    def get_derived_value(self, derived_value_id: str) -> DerivedValue:
        return self._derived_values[derived_value_id]

    def get_derived_grounding(self, grounding_id: str) -> DerivedGrounding:
        return self._derived_groundings[grounding_id]

    def has_referent(self, referent_id: str) -> bool:
        return referent_id in self._referents

    def has_document(self, document_id: str) -> bool:
        return document_id in self._documents

    def has_record(self, record_id: str) -> bool:
        return record_id in self._records

    def has_source(self, source_id: str) -> bool:
        return source_id in self._sources

    def has_observation(self, observation_id: str) -> bool:
        return observation_id in self._observations

    def has_derived_value(self, derived_value_id: str) -> bool:
        return derived_value_id in self._derived_values

    def has_derived_grounding(self, grounding_id: str) -> bool:
        return grounding_id in self._derived_groundings

    # -- query: every Observation/ClaimedRelationship ever admitted, unfiltered and
    #    un-deduplicated -- §E requires conflicting evidence to coexist, so these
    #    intentionally never collapse to "the" value for anything --

    def observations_about(self, referent_id: str) -> Tuple[Observation, ...]:
        rel_obs_ids = {
            rel.observation_id
            for rel in self._claimed_relationships.values()
            if referent_id in (rel.from_referent_id, rel.to_referent_id)
        }
        return tuple(self._observations[oid] for oid in sorted(rel_obs_ids))

    def relationships_touching(self, referent_id: str) -> Tuple[ClaimedRelationship, ...]:
        return tuple(
            rel
            for rel in sorted(self._claimed_relationships.values(), key=lambda r: r.id)
            if referent_id in (rel.from_referent_id, rel.to_referent_id)
        )

    def all_referents(self) -> Tuple[Referent, ...]:
        return tuple(self._referents[k] for k in sorted(self._referents))

    def all_claimed_relationships(self) -> Tuple[ClaimedRelationship, ...]:
        return tuple(self._claimed_relationships[k] for k in sorted(self._claimed_relationships))

    def all_observations(self) -> Tuple[Observation, ...]:
        return tuple(self._observations[k] for k in sorted(self._observations))

    def all_derived_values(self) -> Tuple[DerivedValue, ...]:
        return tuple(self._derived_values[k] for k in sorted(self._derived_values))

    def all_derived_groundings(self) -> Tuple[DerivedGrounding, ...]:
        return tuple(self._derived_groundings[k] for k in sorted(self._derived_groundings))

    def fingerprint(self) -> str:
        """A deterministic content hash of exactly which object ids this
        pool currently holds (`docs/RETRIEVAL_ARCHITECTURE.md` §evidence
        versioning). Read-only, pure with respect to `self` -- calling it
        never mutates the pool. This is what lets a `RetrievalResult`
        distinguish "the same evidence version" from "evidence changed
        underneath the query" without needing a real version-store: two
        pools with identical object ids always fingerprint identically,
        regardless of insertion order (every id is content-addressed, and
        this hashes the *sorted* id sets, not any dict's iteration
        order).

        Phase 17 extended this with a seventh key, `"derived_values"`;
        Phase 19 adds an eighth, `"derived_groundings"` -- both always
        present (even when empty) for the same reason: omitting a real
        evidence category from this hash would leave it invisible to
        `fingerprint_history()` and to every `evidence_version_id` claim
        built on it, which would be the actual defect. Each addition
        intentionally changes `fingerprint()`'s *output value* relative to
        the prior phase for every pool, including ones that never
        construct the new category -- the hashing algorithm and every
        other key are unchanged; no committed test in this repository
        asserts a literal fingerprint string, so nothing here breaks any
        existing assertion, only the values a fresh run produces."""
        payload = {
            "sources": sorted(self._sources),
            "documents": sorted(self._documents),
            "records": sorted(self._records),
            "observations": sorted(self._observations),
            "referents": sorted(self._referents),
            "claimed_relationships": sorted(self._claimed_relationships),
            "derived_values": sorted(self._derived_values),
            "derived_groundings": sorted(self._derived_groundings),
        }
        return content_hash(payload)

    def fingerprint_history(self) -> Tuple[str, ...]:
        """Append-only history of `fingerprint()` values actually observed
        by this pool (Phase 16, `docs/RETRIEVAL_ARCHITECTURE.md` §7) --
        one entry per successful put_* call whose resulting fingerprint
        differed from the last recorded one; the empty pool's own
        fingerprint (before any put_* has ever succeeded) is never
        recorded, since observation only happens at write time.

        This establishes exactly one fact per entry: "this evidence state
        was observed by the system." It does NOT establish that the
        evidence contents behind a historical entry can still be
        recovered -- there is no method anywhere on this class, or
        elsewhere in this codebase, that maps a fingerprint back to the
        object ids that produced it. Historical evidence reconstruction
        is a deliberately separate, undecided, unimplemented capability.

        Pure read-only accessor: calling it never appends to the history
        (only put_* does that) and never mutates the pool. Returns a
        fresh tuple each call -- the caller can never obtain a reference
        to the internal, mutable list."""
        return tuple(self._fingerprint_history)

    def __len__(self) -> int:
        return (
            len(self._sources)
            + len(self._documents)
            + len(self._records)
            + len(self._observations)
            + len(self._referents)
            + len(self._claimed_relationships)
        )
