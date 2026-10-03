"""A real adapter: arbitrary JSON records -> CandidateChange (Phase 12).

Implements the `Adapter` protocol from `adapters/interface.py`. Does NOT
hard-code any particular schema (no "temperature_C" field baked in
anywhere below) -- it normalizes whatever JSON structure it's given, and
the resulting CandidateChange set is only ever accepted or rejected by
the caller's own StateSchema through the unmodified validate_candidate
(§6). This module has no import of, and no path to, validate_candidate,
make_version, or CanonicalState construction.

Normalization rules (documented here because there is no single "right"
way to flatten JSON into a flat field-id space, and the choice matters
for correctness elsewhere in the pipeline):

1. Nested objects are flattened with a `__` (double underscore) joiner,
   e.g. {"material": {"polymer": {"molecular_weight": 85000}}} becomes
   one field id "material__polymer__molecular_weight". `__` is used
   instead of `.` deliberately: delta paths (core/canonical/delta.py)
   already use `.` and `[i]` as their OWN separators
   (`fields.<id>.value`), so a field id containing a literal `.` would
   be structurally ambiguous with a nested delta path. `__` cannot
   collide with that syntax.
2. Arrays are flattened the same way, using the index as the next path
   segment: "measurements": [{"time_s": 0, ...}, ...] becomes
   "measurements__0__time_s", "measurements__1__time_s", etc. This is
   how sequences/time-series (Phase 12 §2, §6) are represented in the
   current flat CanonicalState.fields model -- see
   docs/DATA_CAPABILITIES.md for the honest scope of what this does and
   does not preserve (ordering is recoverable from the index in the id;
   there is no first-class "this is a sequence" type).
3. A leaf value that is itself a dict shaped like {"value": ..., "unit":
   ...(optional), "timestamp": ...(optional)} is treated as a
   self-describing envelope: unit and timestamp are extracted (unit onto
   the Field itself, timestamp onto that change's ProvenanceInfo -- see
   core/canonical/version.py's additive `ProvenanceInfo.timestamp`
   field). This is the only case in which "units when supplied" and
   "timestamps when supplied" (Phase 12 §1) are honored -- they are
   read from an explicit, structured envelope, never guessed from a key
   name like "temperature_C" (that would be silent, unreliable
   inference, not "supplied").
4. A top-level "timestamp" key (not an envelope) sets the default
   per-change timestamp for every field in the record, overridable per
   field by that field's own envelope.
5. A top-level "relationships" key, if present, must be a list of
   {"from": ..., "to": ..., "type": ...} dicts; each becomes an
   `edges[i]` add CandidateChange using the existing EdgeRecord shape
   (§3) instead of a field. This is how "relationships when supplied"
   (Phase 12 §1) and graph-relationship data (§2) are represented --
   reusing CanonicalState.edges, not inventing a second mechanism.
6. Every other JSON leaf (including a literal "sample_id") becomes a
   real Field: bool -> "bool", int/float -> "scalar", str -> "string".
   All changes are emitted as whole-field `add` operations -- this
   adapter is for FIRST INGESTION into an empty/fresh CanonicalState
   (see `adapters/interface.py` for why `normalize()` doesn't have
   enough context to know whether a field already exists on some other
   target state, hence cannot correctly choose `add` vs `replace`
   itself; see docs/DATA_CAPABILITIES.md for this scope note).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from adapters.interface import ExternalRecord
from core.canonical.delta import CandidateChange
from core.canonical.schema import FieldConstraints, FieldSchema, FieldType, StateSchema
from core.canonical.version import ProvenanceInfo

_RESERVED_TOP_LEVEL_KEYS = {"relationships", "timestamp"}


def _is_value_envelope(value: Any) -> bool:
    return isinstance(value, dict) and "value" in value and set(value.keys()) <= {"value", "unit", "timestamp"}


def _infer_type(value: Any) -> FieldType:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "scalar"
    if isinstance(value, str):
        return "string"
    raise TypeError(f"JSON adapter cannot represent leaf value {value!r} of type {type(value)!r}")


def _flatten(prefix: str, value: Any, out: List[Tuple[str, Any]]) -> None:
    if _is_value_envelope(value):
        out.append((prefix, value))
        return
    if isinstance(value, dict):
        for key, sub_value in value.items():
            child_prefix = f"{prefix}__{key}" if prefix else key
            _flatten(child_prefix, sub_value, out)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _flatten(f"{prefix}__{index}", item, out)
    else:
        out.append((prefix, value))


class JSONAdapter:
    """Adapter protocol implementation for arbitrary JSON records."""

    def normalize(self, record: ExternalRecord) -> Tuple[CandidateChange, ...]:
        raw = json.loads(record.raw) if isinstance(record.raw, str) else record.raw
        if not isinstance(raw, dict):
            raise TypeError(f"JSONAdapter expects a JSON object at the top level, got {type(raw)!r}")

        default_timestamp: Optional[str] = raw.get("timestamp") if isinstance(raw.get("timestamp"), str) else None

        flattened: List[Tuple[str, Any]] = []
        for key, value in raw.items():
            if key in _RESERVED_TOP_LEVEL_KEYS:
                continue
            _flatten(key, value, flattened)

        changes = []
        for field_id, leaf in flattened:
            if _is_value_envelope(leaf):
                value = leaf["value"]
                unit = leaf.get("unit")
                timestamp = leaf.get("timestamp", default_timestamp)
            else:
                value = leaf
                unit = None
                timestamp = default_timestamp

            provenance = ProvenanceInfo(
                author="json_adapter",
                transaction_id=f"ingest:{record.source}",
                source=f"json_adapter:{record.source}",
                timestamp=timestamp,
            )
            changes.append(
                CandidateChange(
                    path=f"fields.{field_id}",
                    operation="add",
                    old_value=None,
                    new_value={"id": field_id, "type": _infer_type(value), "value": value, "unit": unit},
                    provenance=provenance,
                )
            )

        relationships = raw.get("relationships")
        if relationships is not None:
            if not isinstance(relationships, list):
                raise TypeError("JSONAdapter: 'relationships' must be a list of {from, to, type} objects")
            for index, rel in enumerate(relationships):
                provenance = ProvenanceInfo(
                    author="json_adapter",
                    transaction_id=f"ingest:{record.source}",
                    source=f"json_adapter:{record.source}",
                    timestamp=default_timestamp,
                )
                changes.append(
                    CandidateChange(
                        path=f"edges[{index}]",
                        operation="add",
                        old_value=None,
                        new_value={
                            "id": rel.get("id", f"{rel['from']}__{rel['type']}__{rel['to']}"),
                            "from": rel["from"],
                            "to": rel["to"],
                            "type": rel["type"],
                            "attributes": {},
                        },
                        provenance=provenance,
                    )
                )

        return tuple(changes)


def infer_schema_from_record(
    record: ExternalRecord, schema_version: str, edge_types: Tuple[str, ...] = ()
) -> StateSchema:
    """Pure utility: build a StateSchema that declares exactly the fields
    a given JSON record would normalize into, with an inferred type per
    field and no constraints. This does NOT relax validation -- it only
    AUTHORS a schema (the same StateSchema shape §6 already defines) for
    previously-unseen data; validate_candidate still enforces it exactly
    as strictly as any hand-written schema. `edge_types` must be supplied
    explicitly by the caller if the record includes relationships (schema
    authorship, like everything else about validation, is not left
    implicit -- see §6: "edges: () -- empty means no edges may ever be
    asserted under this schema version")."""
    adapter = JSONAdapter()
    changes = adapter.normalize(record)

    fields: Dict[str, FieldSchema] = {}
    for change in changes:
        if not change.path.startswith("fields."):
            continue
        new_value = change.new_value
        fields[new_value["id"]] = FieldSchema(
            id=new_value["id"],
            type=new_value["type"],
            unit=new_value["unit"],
            constraints=FieldConstraints(),
            required=False,
        )

    from core.canonical.schema import EdgeSchema

    edges = tuple(EdgeSchema(type=t) for t in edge_types)
    return StateSchema(schema_version=schema_version, fields=fields, edges=edges)
