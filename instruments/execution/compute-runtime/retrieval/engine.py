"""RetrievalEngine: the only place graph traversal + filtering over the
evidence pool happens.

Two concerns are kept deliberately separate, rather than one cascading
filter pipeline:

  GRAPH SHAPE  -- entity_natural_keys, relationship_types, traversal_depth
                  determine which Referents/ClaimedRelationships are
                  included (a pure graph-structure question).

  EVIDENCE CONTENT -- epistemic_statuses, source_kinds, text_terms
                  determine which Observations behind that graph shape
                  are included (a pure content question, independent of
                  which referents/relationships were structurally
                  selected).

This mirrors the architecture's own repeated split between structure
and content (Trust Graph as a derived view over the pool, never the
authority on content -- `docs/SCOUT_ARCHITECTURE.md` §4) rather than
inventing a single ranked/cascading filter model this phase has no
principled way to justify.

Nothing here calls `pool.put_*`, `evidence.admission.admit_*`, or
anything in `core.canonical` -- retrieval is read-only by construction:
every function takes a `pool` and returns new objects, never mutates the
one it was given (`tests/test_retrieval_boundaries.py`,
`tests/test_retrieval_engine.py::test_retrieval_never_mutates_pool`).
"""

from __future__ import annotations

from typing import Protocol, Set, Tuple

from evidence.pool import EvidencePool
from evidence.trust_graph import TrustGraph, build_trust_graph
from retrieval.epistemic import classify_epistemic_status
from retrieval.query import RetrievalQuery
from retrieval.result import RetrievalResult, make_retrieval_result


class RetrievalEngine(Protocol):
    """The extension seam (`docs/RETRIEVAL_ARCHITECTURE.md` §15): a
    future SemanticRetrieval / VectorRetrieval / GraphRetrieval /
    HybridRetrieval engine implements this same Protocol and must
    return the same `RetrievalResult` shape. Retrieval *quality* may
    improve; what a `RetrievalResult`/`ContextPackage` mean does not
    change underneath it."""

    def retrieve(self, pool: EvidencePool, query: RetrievalQuery) -> RetrievalResult: ...


def _bounded_neighborhood(
    graph: TrustGraph, seed_ids: Set[str], depth: int, relationship_types: Tuple[str, ...]
) -> Set[str]:
    visited = set(seed_ids)
    frontier = set(seed_ids)
    for _ in range(depth):
        next_frontier: Set[str] = set()
        for edge in graph.edges:
            if relationship_types and edge.type not in relationship_types:
                continue
            if edge.from_referent_id in frontier and edge.to_referent_id not in visited:
                next_frontier.add(edge.to_referent_id)
            if edge.to_referent_id in frontier and edge.from_referent_id not in visited:
                next_frontier.add(edge.from_referent_id)
        if not next_frontier:
            break
        visited |= next_frontier
        frontier = next_frontier
    return visited


class DeterministicRetrievalEngine:
    """The only `RetrievalEngine` implementation in this codebase:
    exact entity/relationship/source lookup, bounded graph-neighborhood
    traversal, and metadata/epistemic/text filtering -- no embeddings,
    no vector search, no external infrastructure
    (`docs/RETRIEVAL_ARCHITECTURE.md` §minimum-capabilities)."""

    method_name = "deterministic:bfs_v1"

    def retrieve(self, pool: EvidencePool, query: RetrievalQuery) -> RetrievalResult:
        evidence_version_id = pool.fingerprint()
        graph = build_trust_graph(pool)

        seed_ids = {r.id for r in graph.nodes if r.natural_key in query.entity_natural_keys}
        visited_referent_ids = _bounded_neighborhood(graph, seed_ids, query.traversal_depth, query.relationship_types)

        relationship_ids = {
            e.id
            for e in graph.edges
            if (not query.relationship_types or e.type in query.relationship_types)
            and e.from_referent_id in visited_referent_ids
            and e.to_referent_id in visited_referent_ids
        }
        relationships_by_id = {e.id: e for e in graph.edges}

        candidate_observation_ids = {relationships_by_id[rid].observation_id for rid in relationship_ids}

        observation_ids = set()
        source_ids = set()
        for obs_id in candidate_observation_ids:
            observation = pool.get_observation(obs_id)

            if query.epistemic_statuses and classify_epistemic_status(observation) not in query.epistemic_statuses:
                continue

            observation_source_ids = set()
            for record_id in observation.record_ids:
                record = pool.get_record(record_id)
                document = pool.get_document(record.document_id)
                observation_source_ids.add(document.source_id)

            if query.source_kinds:
                kinds = {pool.get_source(sid).kind for sid in observation_source_ids}
                if not kinds & set(query.source_kinds):
                    continue

            if query.text_terms:
                haystack = " ".join(str(v).lower() for v in observation.content.values())
                if not any(term.lower() in haystack for term in query.text_terms):
                    continue

            observation_ids.add(obs_id)
            source_ids |= observation_source_ids

        limited_referent_ids = sorted(visited_referent_ids)
        if query.limit is not None:
            limited_referent_ids = limited_referent_ids[: query.limit]
        final_referent_ids: Set[str] = set(limited_referent_ids)

        # Limiting referents also bounds which relationships/observations
        # remain relevant -- an edge only survives if both endpoints
        # survived the limit.
        relationship_ids = {
            rid
            for rid in relationship_ids
            if relationships_by_id[rid].from_referent_id in final_referent_ids
            and relationships_by_id[rid].to_referent_id in final_referent_ids
        }
        observation_ids &= {relationships_by_id[rid].observation_id for rid in relationship_ids}

        filters_applied = []
        if query.relationship_types:
            filters_applied.append(f"relationship_type in {sorted(query.relationship_types)}")
        if query.epistemic_statuses:
            filters_applied.append(f"epistemic_status in {sorted(query.epistemic_statuses)}")
        if query.source_kinds:
            filters_applied.append(f"source_kind in {sorted(query.source_kinds)}")
        if query.text_terms:
            filters_applied.append(f"text_terms in {sorted(query.text_terms)}")
        if query.limit is not None:
            filters_applied.append(f"limit={query.limit}")

        return make_retrieval_result(
            query_id=query.id,
            evidence_version_id=evidence_version_id,
            retrieval_method=self.method_name,
            referent_ids=tuple(final_referent_ids),
            relationship_ids=tuple(relationship_ids),
            observation_ids=tuple(observation_ids),
            source_ids=tuple(source_ids),
            traversal_depth=query.traversal_depth,
            filters_applied=tuple(filters_applied),
        )
