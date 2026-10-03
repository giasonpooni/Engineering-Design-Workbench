"""Canonical schematic: function graph + factor graph.

USD and mermaid are projections. This module is the store.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping


class NodeKind(str, Enum):
    VARIABLE = "variable"
    FUNCTION = "function"
    MEASUREMENT = "measurement"
    PRIOR = "prior"
    CONSTRAINT = "constraint"
    CERTIFICATE = "certificate"
    OBSERVER = "observer"
    EVIDENCE = "evidence"


class EdgeKind(str, Enum):
    INPUT = "input"
    OUTPUT = "output"
    MEASURES = "measures"
    ACTUATES = "actuates"
    BINDS = "binds"
    LINEARIZES = "linearizes"
    CERTIFIES = "certifies"
    OBSERVES = "observes"
    SENSES = "senses"
    COMPOSED_IN = "composed_in"


class PlantClass(str, Enum):
    LINEAR = "linear"
    LPV = "lpv"
    NONLINEAR = "nonlinear"
    UNKNOWN = "unknown"


class Status(str, Enum):
    UNRESOLVED = "UNRESOLVED"
    MAPPED = "MAPPED"
    ELIGIBLE = "ELIGIBLE"
    SAMPLED = "SAMPLED"
    REFUSED = "REFUSED"
    NOT_CHECKED = "NOT_CHECKED"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"


FUNCTION_KINDS = frozenset({NodeKind.FUNCTION})
FACTOR_KINDS = frozenset(
    {NodeKind.MEASUREMENT, NodeKind.PRIOR, NodeKind.CONSTRAINT}
)
VARIABLE_KINDS = frozenset({NodeKind.VARIABLE})


@dataclass(frozen=True)
class Node:
    id: str
    kind: NodeKind
    attrs: Mapping[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.attrs.get(key, default)


@dataclass(frozen=True)
class Edge:
    kind: EdgeKind
    src: str
    dst: str
    attrs: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class Schematic:
    """Port-level function graph plus factor graph."""

    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def add(self, node: Node) -> Node:
        if node.id in self.nodes:
            raise ValueError(f"duplicate node id: {node.id}")
        self.nodes[node.id] = node
        return node

    def connect(self, kind: EdgeKind, src: str, dst: str, **attrs: Any) -> Edge:
        if src not in self.nodes:
            raise ValueError(f"unknown src: {src}")
        if dst not in self.nodes:
            raise ValueError(f"unknown dst: {dst}")
        edge = Edge(kind=kind, src=src, dst=dst, attrs=attrs)
        self.edges.append(edge)
        return edge

    def node(self, node_id: str) -> Node:
        try:
            return self.nodes[node_id]
        except KeyError as exc:
            raise KeyError(f"unknown node: {node_id}") from exc

    def of_kind(self, kind: NodeKind) -> list[Node]:
        return [n for n in self.nodes.values() if n.kind is kind]

    def out_edges(self, node_id: str, kind: EdgeKind | None = None) -> list[Edge]:
        return [
            e
            for e in self.edges
            if e.src == node_id and (kind is None or e.kind is kind)
        ]

    def in_edges(self, node_id: str, kind: EdgeKind | None = None) -> list[Edge]:
        return [
            e
            for e in self.edges
            if e.dst == node_id and (kind is None or e.kind is kind)
        ]

    def neighbors(self, node_id: str, kind: EdgeKind | None = None) -> list[str]:
        ids: list[str] = []
        for e in self.out_edges(node_id, kind):
            ids.append(e.dst)
        for e in self.in_edges(node_id, kind):
            ids.append(e.src)
        return ids

    def replace(self, node: Node) -> None:
        if node.id not in self.nodes:
            raise KeyError(f"unknown node: {node.id}")
        self.nodes[node.id] = node

    def subgraph(self, ids: Iterable[str]) -> "Schematic":
        keep = set(ids)
        out = Schematic(meta=dict(self.meta))
        for i in keep:
            if i in self.nodes:
                out.nodes[i] = self.nodes[i]
        for e in self.edges:
            if e.src in keep and e.dst in keep:
                out.edges.append(e)
        return out
