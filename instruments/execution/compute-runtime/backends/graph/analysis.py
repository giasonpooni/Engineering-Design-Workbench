"""Graph analysis backend (§1, §11): Morpho IR -> descriptive graph
metrics. Pure and deterministic. Purely descriptive in v1 -- it reports
on whatever relations already exist in the IR (canonical and/or
derived/inferred, each still tagged with its own is_canonical /
inference_status from §11); it does not itself invent new inferred
relations. No backend may promote anything it computes into canonical
state (I3) -- this module has no path to CanonicalState or Version at
all.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from morpho.ir import MorphoDocument


@dataclass(frozen=True)
class GraphAnalysisReport:
    node_count: int
    edge_count: int
    adjacency: Dict[str, Tuple[str, ...]]
    degree: Dict[str, int]


def analyze(ir: MorphoDocument) -> GraphAnalysisReport:
    node_ids = sorted(e.id for e in ir.entities)
    adjacency: Dict[str, list] = {node_id: [] for node_id in node_ids}

    for relation in sorted(ir.relations, key=lambda r: r.id):
        adjacency.setdefault(relation.from_id, [])
        adjacency.setdefault(relation.to_id, [])
        adjacency[relation.from_id].append(relation.to_id)

    frozen_adjacency = {node_id: tuple(sorted(targets)) for node_id, targets in adjacency.items()}
    degree = {node_id: len(targets) for node_id, targets in frozen_adjacency.items()}

    return GraphAnalysisReport(
        node_count=len(frozen_adjacency),
        edge_count=len(ir.relations),
        adjacency=frozen_adjacency,
        degree=degree,
    )
