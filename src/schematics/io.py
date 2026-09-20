"""JSON serialization of the canonical IR."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .ir import Edge, EdgeKind, Node, NodeKind, Schematic
from .validate import require, SchematicError, SCHEMA


def to_dict(schematic: Schematic) -> dict[str, Any]:
    return {
        "schema": schematic.meta.get("schema", "NsObservabilitySchematic@0.1"),
        "meta": schematic.meta,
        "nodes": [{"id": n.id, "kind": n.kind.value, "attrs": dict(n.attrs)} for n in schematic.nodes.values()],
        "edges": [{"kind": e.kind.value, "src": e.src, "dst": e.dst, "attrs": dict(e.attrs)} for e in schematic.edges],
    }


def from_dict(payload: dict[str, Any]) -> Schematic:
    if not isinstance(payload, dict):
        raise SchematicError("schematic payload must be an object")
    meta = payload.get("meta", {})
    if not isinstance(meta, dict):
        raise SchematicError("schematic meta must be an object")
    declared = [obj["schema"] for obj in (payload, meta) if "schema" in obj]
    if any(value != SCHEMA for value in declared):
        raise SchematicError("unknown or conflicting schematic schema")
    sch = Schematic(meta=dict(payload.get("meta") or {}))
    if "schema" in payload and "schema" not in sch.meta:
        sch.meta["schema"] = payload["schema"]
    for raw in payload.get("nodes", []):
        sch.add(Node(id=raw["id"], kind=NodeKind(raw["kind"]), attrs=dict(raw.get("attrs") or {})))
    for raw in payload.get("edges", []):
        sch.edges.append(Edge(kind=EdgeKind(raw["kind"]), src=raw["src"], dst=raw["dst"], attrs=dict(raw.get("attrs") or {})))
    return require(sch)


def dumps(schematic: Schematic) -> str:
    return json.dumps(to_dict(schematic), indent=2, sort_keys=False) + "\n"


def loads(text: str) -> Schematic:
    return from_dict(json.loads(text))


def write(schematic: Schematic, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(schematic), encoding="utf-8")
    return path


def read(path: str | Path) -> Schematic:
    return loads(Path(path).read_text(encoding="utf-8"))
