"""Network-state metrics over a Trust Graph.

Each metric below is implemented ONLY because it is directly computable
from data this architecture already has (`evidence/types.py`,
`evidence/pool.py`) -- per this phase's own instruction not to implement
a metric "simply because it sounds useful." A metric the prompt suggested
but that would require data this architecture does not yet capture
(temporal activity / acceleration, which needs a time-series index no
part of this repository builds -- `docs/PHASE_14_DATA_POOL_ARCHITECTURE.md`
§S explicitly defers exactly this kind of index) is documented as
DEFERRED in `docs/SCOUT_ARCHITECTURE.md` rather than faked here with a
placeholder implementation.

Every function here is a pure function of a `TrustGraph`/`EvidencePool`
snapshot -- no wall-clock reads, no randomness, no reliance on raw
dict/set iteration order (see `evidence/trust_graph.py`'s
`connected_components` for the same discipline applied to graph
traversal). See `docs/SCOUT_ARCHITECTURE.md` for each metric's
definition / math / required data / cost / interpretation / limitations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from evidence.pool import EvidencePool
from evidence.trust_graph import TrustGraph
from evidence.types import ClaimedRelationship, Observation


@dataclass(frozen=True)
class ConnectivityMetrics:
    node_count: int
    edge_count: int
    average_degree: float


def connectivity(graph: TrustGraph) -> ConnectivityMetrics:
    node_count = len(graph.nodes)
    edge_count = len(graph.edges)
    average_degree = (2.0 * edge_count / node_count) if node_count else 0.0
    return ConnectivityMetrics(node_count=node_count, edge_count=edge_count, average_degree=average_degree)


def novelty(before: TrustGraph, referent_ids: Tuple[str, ...], relationship_ids: Tuple[str, ...]) -> float:
    """Fraction of the entities/relationships a new finding references
    that did not already exist in the graph. 0.0 = entirely composed of
    already-known referents/relationships; 1.0 = entirely new."""
    before_node_ids = {n.id for n in before.nodes}
    before_edge_ids = {e.id for e in before.edges}
    total = len(referent_ids) + len(relationship_ids)
    if total == 0:
        return 0.0
    new_count = sum(1 for r in referent_ids if r not in before_node_ids)
    new_count += sum(1 for e in relationship_ids if e not in before_edge_ids)
    return new_count / total


def redundancy(pool: EvidencePool, referent_id: str) -> int:
    """Count of distinct Sources that have contributed an Observation
    about this Referent (via any ClaimedRelationship touching it).
    Requires walking Observation -> Record -> Document -> Source, all
    already-stored reference fields -- no new index needed."""
    source_ids = set()
    for rel in pool.relationships_touching(referent_id):
        obs = pool.get_observation(rel.observation_id)
        for record_id in obs.record_ids:
            record = pool.get_record(record_id)
            document = pool.get_document(record.document_id)
            source_ids.add(document.source_id)
    return len(source_ids)


def source_diversity(pool: EvidencePool, referent_id: str) -> float:
    """distinct_source_count / observation_count for a Referent. Does
    NOT weight by source quality -- confidence/source-quality scoring is
    explicitly unresolved research
    (`docs/PHASE_14_DATA_POOL_ARCHITECTURE.md` §S), so this metric
    deliberately stays a plain ratio rather than pretending to a
    weighting scheme that does not exist yet."""
    relationships = pool.relationships_touching(referent_id)
    if not relationships:
        return 0.0
    return redundancy(pool, referent_id) / len(relationships)


def observation_uncertainty(observation: Observation) -> float:
    return 1.0 - observation.confidence


def aggregate_uncertainty(observations: Tuple[Observation, ...]) -> float:
    if not observations:
        return 0.0
    return sum(1.0 - o.confidence for o in observations) / len(observations)


def evidence_density(pool: EvidencePool, referent_id: str) -> int:
    """Raw count of (relationships touching this Referent). Deliberately
    NOT normalized against a graph-wide average -- doing so would need a
    baseline this v1 pool has no principled way to compute yet (what is
    "typical" density depends on domain, and no domain-weighting model
    exists). Reported as a raw count with that limitation stated, rather
    than a fabricated normalized score."""
    return len(pool.relationships_touching(referent_id))


def bridge_potential(before: TrustGraph, new_edge: ClaimedRelationship) -> bool:
    """True if `new_edge` connects two Referents that were in different
    connected components of the graph BEFORE this edge was added (i.e.
    it is the first evidence linking two previously-separate clusters of
    knowledge) -- computed via union-find over `before`, O(V+E)."""
    components = before.connected_components()

    def component_of(node_id: str):
        for comp in components:
            if node_id in comp:
                return comp
        return frozenset({node_id})

    return component_of(new_edge.from_referent_id) != component_of(new_edge.to_referent_id)
