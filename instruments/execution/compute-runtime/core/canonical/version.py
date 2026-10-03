"""Version and VersionStore (§4).

Version IDs are content-addressed SHA-256 digests of
`(schema_version, fields, edges)` ONLY -- id, parent, provenance, and
timestamp are excluded from the hash. Two CanonicalStates with identical
(schema_version, fields, edges) always produce the same VersionId,
regardless of when or by whom they were created.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol

from core.canonical.schema import StateSchema
from core.canonical.state import CanonicalState, EdgeRecord, Field

VersionId = str


@dataclass(frozen=True)
class ProvenanceInfo:
    author: str
    transaction_id: str
    source: str  # "manual_edit" | "simulation" | "estimator" | "genesis" | ...
    # Additive extension (documented before implementation -- see the
    # session report for Phase 12): when was the underlying FACT true or
    # measured, as opposed to Version.timestamp (when the version was
    # accepted). Optional and defaulted so every existing construction
    # site is unaffected. Mirrors morpho/provenance.py's ProvenanceRecord,
    # which already had this field -- this closes that asymmetry rather
    # than introducing a new concept. Not part of the Version.id content
    # hash (§4 already excludes all of ProvenanceInfo from that hash).
    timestamp: Optional[str] = None


def _field_to_jsonable(f: Field):
    return {"id": f.id, "type": f.type, "value": _value_to_jsonable(f.value), "unit": f.unit}


def _edge_to_jsonable(e: EdgeRecord):
    return {
        "id": e.id,
        "from": e.from_,
        "to": e.to,
        "type": e.type,
        "attributes": {k: _value_to_jsonable(v) for k, v in sorted(e.attributes.items())},
    }


def _value_to_jsonable(value):
    if isinstance(value, tuple):
        return [_value_to_jsonable(v) for v in value]
    return value


def canonical_content(state: CanonicalState) -> dict:
    """The exact `(schema_version, fields, edges)` payload the VersionId
    hash is computed over. Exposed separately from the hashing routine so
    tests can assert byte-for-byte determinism of the serialization step
    on its own (§4, §20)."""
    return {
        "schema_version": state.schema_version,
        "fields": {key: _field_to_jsonable(f) for key, f in sorted(state.fields.items())},
        "edges": [_edge_to_jsonable(e) for e in state.edges],
    }


def canonical_json_bytes(state: CanonicalState) -> bytes:
    payload = canonical_content(state)
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return text.encode("utf-8")


def compute_version_id(state: CanonicalState) -> VersionId:
    return hashlib.sha256(canonical_json_bytes(state)).hexdigest()


@dataclass(frozen=True)
class Version:
    id: VersionId
    parent: Optional[VersionId]
    state: CanonicalState
    schema_version: str
    provenance: ProvenanceInfo
    timestamp: str  # ISO-8601 UTC


def make_version(
    state: CanonicalState,
    parent: Optional[VersionId],
    provenance: ProvenanceInfo,
    timestamp: str,
) -> Version:
    """The only supported way to construct a Version: the id is always
    derived from `state`, never supplied by the caller, so a Version's id
    can never disagree with its own content."""
    return Version(
        id=compute_version_id(state),
        parent=parent,
        state=state,
        schema_version=state.schema_version,
        provenance=provenance,
        timestamp=timestamp,
    )


def create_genesis_version(schema: StateSchema, timestamp: str) -> Version:
    """Build the root Version (parent=None) directly from a schema's
    declared field defaults (§4). This is the ONLY Version ever
    constructed outside core.canonical.validation.validate_candidate --
    every later Version is minted by the validation pipeline."""
    fields = {}
    for key, field_schema in schema.fields.items():
        if field_schema.default is None and field_schema.required:
            raise ValueError(
                f"cannot build genesis version: field {key!r} is required "
                f"but has no declared default"
            )
        fields[key] = Field(
            id=key, type=field_schema.type, value=field_schema.default, unit=field_schema.unit
        )
    state = CanonicalState(schema_version=schema.schema_version, fields=fields, edges=())
    return make_version(
        state=state,
        parent=None,
        provenance=ProvenanceInfo(author="system", transaction_id="genesis", source="genesis"),
        timestamp=timestamp,
    )


class VersionStore(Protocol):
    def put(self, version: Version) -> None: ...
    def get(self, version_id: VersionId) -> Version: ...
    def parent_chain(self, version_id: VersionId) -> List[Version]: ...
    def head(self) -> Version: ...


class InMemoryVersionStore:
    """v1 VersionStore: single-writer, in-process, append-only. See §20 --
    multi-writer concurrency control is explicitly out of scope for v1."""

    def __init__(self) -> None:
        self._versions: Dict[VersionId, Version] = {}
        self._head: Optional[VersionId] = None

    def put(self, version: Version) -> None:
        self._versions[version.id] = version
        self._head = version.id

    def get(self, version_id: VersionId) -> Version:
        return self._versions[version_id]

    def parent_chain(self, version_id: VersionId) -> List[Version]:
        chain = []
        current: Optional[VersionId] = version_id
        while current is not None:
            v = self._versions[current]
            chain.append(v)
            current = v.parent
        return chain

    def head(self) -> Version:
        if self._head is None:
            raise LookupError("VersionStore is empty: no head version")
        return self._versions[self._head]

    def __contains__(self, version_id: VersionId) -> bool:
        return version_id in self._versions

    def __len__(self) -> int:
        return len(self._versions)
