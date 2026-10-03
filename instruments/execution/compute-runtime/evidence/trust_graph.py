"""Trust Graph: a derived, read-only view over an EvidencePool.

Per `docs/PHASE_14_DATA_POOL_ARCHITECTURE.md` §G ("graph = a derived
index over structured records, not the primary store") -- the SAME
discipline `docs/PHASE_13_ARCHITECTURE_INVESTIGATION.md` §G already
established for Morpho relative to CanonicalState, reapplied one layer
upstream: the Trust Graph is never authoritative and never stored
independently of the pool it is built from. `build_trust_graph(pool)`
is a pure function -- call it again any time the pool changes to get an
up-to-date view; there is no `TrustGraph.add_edge()` or similar mutator.

Nodes are Referents; edges are ClaimedRelationships. Because a
ClaimedRelationship's identity includes its source `observation_id`
(§types.py), this is a multigraph by construction -- two sources
claiming different relationships between the same two Referents both
appear as distinct edges, never silently merged into one "the"
relationship.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Tuple

from evidence.pool import EvidencePool
from evidence.types import ClaimedRelationship, Referent


@dataclass(frozen=True)
class TrustGraph:
    nodes: Tuple[Referent, ...]
    edges: Tuple[ClaimedRelationship, ...]

    def neighbors(self, referent_id: str) -> Tuple[str, ...]:
        seen = set()
        result = []
        for e in self.edges:
            other = None
            if e.from_referent_id == referent_id:
                other = e.to_referent_id
            elif e.to_referent_id == referent_id:
                other = e.from_referent_id
            if other is not None and other not in seen:
                seen.add(other)
                result.append(other)
        return tuple(sorted(result))

    def connected_components(self) -> Tuple[FrozenSet[str], ...]:
        """Deterministic connected-component partition over node ids,
        via union-find, iterating in sorted order so the result never
        depends on dict/set iteration order (same discipline as
        `project_state`/`compile_morpho` -- see `docs/ARCHITECTURE.md`
        "Determinism, concretely")."""
        parent: Dict[str, str] = {n.id: n.id for n in self.nodes}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)

        for e in sorted(self.edges, key=lambda e: e.id):
            if e.from_referent_id in parent and e.to_referent_id in parent:
                union(e.from_referent_id, e.to_referent_id)

        groups: Dict[str, set] = {}
        for n in sorted(self.nodes, key=lambda n: n.id):
            root = find(n.id)
            groups.setdefault(root, set()).add(n.id)

        return tuple(frozenset(groups[k]) for k in sorted(groups))


def build_trust_graph(pool: EvidencePool) -> TrustGraph:
    return TrustGraph(nodes=pool.all_referents(), edges=pool.all_claimed_relationships())
