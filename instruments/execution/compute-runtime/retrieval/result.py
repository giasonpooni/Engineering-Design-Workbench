"""RetrievalResult: what a RetrievalEngine returns.

Holds only references (ids) into `evidence/` -- never copies of
`Referent`/`Observation`/etc. content. `id` is a content hash over the
query, the evidence version the query ran against, and the returned id
sets, so `RetrievalResult.id` answers "can this be reproduced?" directly:
recomputing the same query against the same evidence version always
produces the same `id` (`docs/RETRIEVAL_ARCHITECTURE.md` §reproducibility).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from evidence.identity import content_hash


@dataclass(frozen=True)
class RetrievalResult:
    id: str
    query_id: str
    evidence_version_id: str  # EvidencePool.fingerprint() at query time
    retrieval_method: str  # "deterministic:bfs_v1" -- see retrieval/engine.py

    referent_ids: Tuple[str, ...]
    relationship_ids: Tuple[str, ...]
    observation_ids: Tuple[str, ...]
    source_ids: Tuple[str, ...]

    # Config actually applied -- echoes the query's own filters/depth so
    # a result is self-explaining without dereferencing the query object
    # ("why was it returned?").
    traversal_depth: int
    filters_applied: Tuple[str, ...]  # human-readable filter descriptions, e.g. "relationship_type in {...}"

    # Deterministic, not a relevance score -- see
    # docs/RETRIEVAL_ARCHITECTURE.md "ordering is not ranking".
    ordering: str


def make_retrieval_result(
    query_id: str,
    evidence_version_id: str,
    retrieval_method: str,
    referent_ids: Tuple[str, ...],
    relationship_ids: Tuple[str, ...],
    observation_ids: Tuple[str, ...],
    source_ids: Tuple[str, ...],
    traversal_depth: int,
    filters_applied: Tuple[str, ...],
    ordering: str = "sorted_by_id",
) -> RetrievalResult:
    referent_ids = tuple(sorted(set(referent_ids)))
    relationship_ids = tuple(sorted(set(relationship_ids)))
    observation_ids = tuple(sorted(set(observation_ids)))
    source_ids = tuple(sorted(set(source_ids)))
    filters_applied = tuple(sorted(set(filters_applied)))

    result_id = content_hash(
        {
            "query_id": query_id,
            "evidence_version_id": evidence_version_id,
            "retrieval_method": retrieval_method,
            "referent_ids": list(referent_ids),
            "relationship_ids": list(relationship_ids),
            "observation_ids": list(observation_ids),
            "source_ids": list(source_ids),
            "traversal_depth": traversal_depth,
            "filters_applied": list(filters_applied),
            "ordering": ordering,
        }
    )
    return RetrievalResult(
        id=result_id,
        query_id=query_id,
        evidence_version_id=evidence_version_id,
        retrieval_method=retrieval_method,
        referent_ids=referent_ids,
        relationship_ids=relationship_ids,
        observation_ids=observation_ids,
        source_ids=source_ids,
        traversal_depth=traversal_depth,
        filters_applied=filters_applied,
        ordering=ordering,
    )
