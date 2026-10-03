"""Retrieval is address, type, typed path, and Markov blanket. Not embeddings."""

from __future__ import annotations

from .ir import EdgeKind, Node, NodeKind, Schematic


def by_id(schematic: Schematic, node_id: str) -> Node:
    return schematic.node(node_id)


def by_kind(schematic: Schematic, kind: NodeKind) -> list[Node]:
    return schematic.of_kind(kind)


def by_attr(schematic: Schematic, key: str, value: object) -> list[Node]:
    return [n for n in schematic.nodes.values() if n.get(key) == value]


def path(
    schematic: Schematic,
    start: str,
    kinds: tuple[EdgeKind, ...],
    *,
    directed: bool = True,
) -> list[str]:
    current = start
    visited = [current]
    schematic.node(start)
    for kind in kinds:
        nxt = None
        for edge in schematic.out_edges(current, kind):
            nxt = edge.dst
            break
        if nxt is None and not directed:
            for edge in schematic.in_edges(current, kind):
                nxt = edge.src
                break
        if nxt is None:
            break
        current = nxt
        visited.append(current)
    return visited


def blanket(schematic: Schematic, node_id: str) -> list[str]:
    schematic.node(node_id)
    keep = {node_id}
    for neigh in schematic.neighbors(node_id):
        keep.add(neigh)
        for second in schematic.neighbors(neigh):
            keep.add(second)
    return sorted(keep)
