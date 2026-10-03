"""Path-addressed structural deltas (§5).

Path syntax: dot-separated map keys, bracket integer index for sequence
elements. Always absolute from the root of CanonicalState, e.g.:

    fields.mass.value
    fields.mass.unit
    edges[0].type

Only `add`, `remove`, `replace` are implemented. `move` and `rename` are
reserved in the Operation type (forward-compatible) but `diff()` never
emits them in v1 -- see spec §5 and §23.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Literal, Optional, Tuple

from core.canonical.schema import FieldValue
from core.canonical.state import CanonicalState, EdgeRecord, Field
from core.canonical.version import ProvenanceInfo, VersionId

Operation = Literal["add", "remove", "replace", "move", "rename"]

_PATH_SEGMENT_RE = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def parse_path(path: str) -> Tuple[object, ...]:
    """Split a delta path into its segments, e.g. 'edges[0].type' ->
    ('edges', 0, 'type')."""
    segments: list = []
    for match in _PATH_SEGMENT_RE.finditer(path):
        key, index = match.group(1), match.group(2)
        if index is not None:
            segments.append(int(index))
        else:
            segments.append(key)
    if not segments:
        raise ValueError(f"empty or unparseable delta path: {path!r}")
    return tuple(segments)


@dataclass(frozen=True)
class Change:
    path: str
    operation: Operation
    old_value: Optional[object]
    new_value: Optional[object]
    provenance: ProvenanceInfo


@dataclass(frozen=True)
class StateDelta:
    version_from: Optional[VersionId]
    version_to: VersionId
    transaction_id: str
    timestamp: str
    changes: Tuple[Change, ...]


@dataclass(frozen=True)
class CandidateChange:
    path: str
    operation: Operation
    old_value: Optional[object]
    new_value: Optional[object]
    provenance: ProvenanceInfo
    confidence: Optional[float] = None


@dataclass(frozen=True)
class CandidateDelta:
    version_from: Optional[VersionId]
    transaction_id: str
    timestamp: str
    changes: Tuple[CandidateChange, ...]


@dataclass(frozen=True)
class CandidateNextState:
    """Shared shape for a simulation step's or a neural estimator's
    proposed next state (§16, §17). Defined here -- not in
    backends/simulation/interface.py -- so that
    backends/neural/interface.py can depend on it without importing
    another backend package (§2: "backends must not import each other").
    core/canonical is upstream of every backend, so both may import from
    it freely."""

    based_on_version: VersionId
    proposed_changes: Tuple[CandidateChange, ...]
    provenance: ProvenanceInfo


def _field_leaf_values(f: Field) -> Dict[str, FieldValue]:
    return {"type": f.type, "value": f.value, "unit": f.unit}


def _field_as_value(f: Field) -> Dict[str, FieldValue]:
    return {"id": f.id, "type": f.type, "value": f.value, "unit": f.unit}


def _edge_leaf_values(e: EdgeRecord) -> Dict[str, object]:
    return {"from": e.from_, "to": e.to, "type": e.type, "attributes": dict(e.attributes)}


def _edge_as_value(e: EdgeRecord) -> Dict[str, object]:
    return {"id": e.id, **_edge_leaf_values(e)}


def diff(
    old: CanonicalState, new: CanonicalState, provenance: ProvenanceInfo
) -> Tuple[Change, ...]:
    """Pure structural diff producing leaf-level Changes. Deterministically
    ordered: fields first (sorted by field id), then edges (by index),
    each in a fixed attribute order."""
    changes: list = []

    old_keys = set(old.fields.keys())
    new_keys = set(new.fields.keys())

    for key in sorted(old_keys - new_keys):
        changes.append(
            Change(
                path=f"fields.{key}",
                operation="remove",
                old_value=_field_as_value(old.fields[key]),
                new_value=None,
                provenance=provenance,
            )
        )

    for key in sorted(new_keys - old_keys):
        changes.append(
            Change(
                path=f"fields.{key}",
                operation="add",
                old_value=None,
                new_value=_field_as_value(new.fields[key]),
                provenance=provenance,
            )
        )

    for key in sorted(old_keys & new_keys):
        old_leaves = _field_leaf_values(old.fields[key])
        new_leaves = _field_leaf_values(new.fields[key])
        for attr in ("type", "value", "unit"):
            if old_leaves[attr] != new_leaves[attr]:
                changes.append(
                    Change(
                        path=f"fields.{key}.{attr}",
                        operation="replace",
                        old_value=old_leaves[attr],
                        new_value=new_leaves[attr],
                        provenance=provenance,
                    )
                )

    max_len = max(len(old.edges), len(new.edges))
    for i in range(max_len):
        if i >= len(old.edges):
            changes.append(
                Change(
                    path=f"edges[{i}]",
                    operation="add",
                    old_value=None,
                    new_value=_edge_as_value(new.edges[i]),
                    provenance=provenance,
                )
            )
        elif i >= len(new.edges):
            changes.append(
                Change(
                    path=f"edges[{i}]",
                    operation="remove",
                    old_value=_edge_as_value(old.edges[i]),
                    new_value=None,
                    provenance=provenance,
                )
            )
        else:
            old_leaves = _edge_leaf_values(old.edges[i])
            new_leaves = _edge_leaf_values(new.edges[i])
            for attr in ("from", "to", "type", "attributes"):
                if old_leaves[attr] != new_leaves[attr]:
                    changes.append(
                        Change(
                            path=f"edges[{i}].{attr}",
                            operation="replace",
                            old_value=old_leaves[attr],
                            new_value=new_leaves[attr],
                            provenance=provenance,
                        )
                    )

    return tuple(changes)


def apply_changes(base: CanonicalState, changes: Tuple[CandidateChange, ...]) -> CanonicalState:
    """Pure application of a sequence of leaf-level changes to `base`,
    producing a new CanonicalState. Used only by
    core.canonical.validation.validate_candidate as the last step before
    a candidate becomes a new Version (§6) -- never called directly by any
    backend, renderer, simulator, or neural component.

    Only the path shapes emitted by `diff()` are supported:
        fields.<id>            (add/remove a whole field)
        fields.<id>.<attr>      (replace a leaf: type/value/unit)
        edges[<i>]              (add/remove a whole edge)
        edges[<i>].<attr>        (replace a leaf: from/to/type/attributes)
    """
    fields: Dict[str, Field] = dict(base.fields)
    edges: list = list(base.edges)

    for change in changes:
        segments = parse_path(change.path)
        if segments[0] == "fields":
            _apply_field_change(fields, segments, change)
        elif segments[0] == "edges":
            edges = _apply_edge_change(edges, segments, change)
        else:
            raise ValueError(f"unsupported delta path root: {change.path!r}")

    return CanonicalState(schema_version=base.schema_version, fields=fields, edges=tuple(edges))


def _apply_field_change(fields: Dict[str, Field], segments: tuple, change: CandidateChange) -> None:
    key = segments[1]
    if len(segments) == 2:
        if change.operation == "add":
            new_value = change.new_value
            fields[key] = Field(
                id=key, type=new_value["type"], value=new_value["value"], unit=new_value["unit"]
            )
        elif change.operation == "remove":
            del fields[key]
        else:
            raise ValueError(f"unsupported whole-field operation: {change.operation!r}")
    elif len(segments) == 3:
        attr = segments[2]
        if change.operation != "replace":
            raise ValueError(f"unsupported leaf-field operation: {change.operation!r}")
        existing = fields[key]
        kwargs = {"id": existing.id, "type": existing.type, "value": existing.value, "unit": existing.unit}
        kwargs[attr] = change.new_value
        fields[key] = Field(**kwargs)
    else:
        raise ValueError(f"unsupported field delta path depth: {change.path!r}")


def _apply_edge_change(edges: list, segments: tuple, change: CandidateChange) -> list:
    index = segments[1]
    if len(segments) == 2:
        if change.operation == "add":
            if index != len(edges):
                raise ValueError(f"edge add index out of order: {change.path!r}")
            new_value = change.new_value
            edge = EdgeRecord(
                id=new_value["id"],
                from_=new_value["from"],
                to=new_value["to"],
                type=new_value["type"],
                attributes=new_value.get("attributes", {}),
            )
            edges = edges + [edge]
        elif change.operation == "remove":
            del edges[index]
        else:
            raise ValueError(f"unsupported whole-edge operation: {change.operation!r}")
    elif len(segments) == 3:
        attr = segments[2]
        if change.operation != "replace":
            raise ValueError(f"unsupported leaf-edge operation: {change.operation!r}")
        existing = edges[index]
        kwargs = {
            "id": existing.id,
            "from_": existing.from_,
            "to": existing.to,
            "type": existing.type,
            "attributes": dict(existing.attributes),
        }
        key_map = {"from": "from_", "to": "to", "type": "type", "attributes": "attributes"}
        kwargs[key_map[attr]] = change.new_value
        edges[index] = EdgeRecord(**kwargs)
    else:
        raise ValueError(f"unsupported edge delta path depth: {change.path!r}")
    return edges
