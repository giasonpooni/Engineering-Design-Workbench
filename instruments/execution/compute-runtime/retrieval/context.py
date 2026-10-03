"""ContextPackage: a reproducible selection of persistent evidence,
assembled from one or more RetrievalResults.

ContextPackage is NOT CanonicalState and NOT a new authoritative store
-- it holds only id references into `evidence/`, exactly like
`RetrievalResult`. Composing several RetrievalResults into one
ContextPackage never copies a `Referent`/`Observation`/etc.; it unions
and deduplicates their id sets. See
`docs/RETRIEVAL_ARCHITECTURE.md` §ContextPackage.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from evidence.identity import content_hash
from evidence.pool import EvidencePool
from evidence.types import ClaimedRelationship, Observation, Referent, Source
from retrieval.result import RetrievalResult


@dataclass(frozen=True)
class ContextPackage:
    id: str
    retrieval_result_ids: Tuple[str, ...]

    # Composed, deduplicated references -- unioned across every
    # contributing RetrievalResult.
    referent_ids: Tuple[str, ...]
    relationship_ids: Tuple[str, ...]
    observation_ids: Tuple[str, ...]
    source_ids: Tuple[str, ...]

    # Every distinct evidence version any contributing result was
    # queried against. A single value means every contributing result
    # ran against the identical evidence snapshot; more than one means
    # this context spans evidence that changed between retrievals --
    # recorded explicitly rather than silently collapsed to "current."
    evidence_version_ids: Tuple[str, ...]


def build_context_package(retrieval_results: Tuple[RetrievalResult, ...]) -> ContextPackage:
    if not retrieval_results:
        raise ValueError("build_context_package requires at least one RetrievalResult")

    retrieval_result_ids = tuple(sorted({r.id for r in retrieval_results}))
    referent_ids = tuple(sorted({rid for r in retrieval_results for rid in r.referent_ids}))
    relationship_ids = tuple(sorted({rid for r in retrieval_results for rid in r.relationship_ids}))
    observation_ids = tuple(sorted({oid for r in retrieval_results for oid in r.observation_ids}))
    source_ids = tuple(sorted({sid for r in retrieval_results for sid in r.source_ids}))
    evidence_version_ids = tuple(sorted({r.evidence_version_id for r in retrieval_results}))

    context_id = content_hash(
        {
            "retrieval_result_ids": list(retrieval_result_ids),
            "referent_ids": list(referent_ids),
            "relationship_ids": list(relationship_ids),
            "observation_ids": list(observation_ids),
            "source_ids": list(source_ids),
            "evidence_version_ids": list(evidence_version_ids),
        }
    )
    return ContextPackage(
        id=context_id,
        retrieval_result_ids=retrieval_result_ids,
        referent_ids=referent_ids,
        relationship_ids=relationship_ids,
        observation_ids=observation_ids,
        source_ids=source_ids,
        evidence_version_ids=evidence_version_ids,
    )


# -- Dereferencing helpers: ContextPackage stores ids only; these read
#    the referenced, still-authoritative objects back out of the pool.
#    None of them mutate `pool` -- they are plain lookups. --


def referents(pool: EvidencePool, context: ContextPackage) -> Tuple[Referent, ...]:
    return tuple(pool.get_referent(rid) for rid in context.referent_ids)


def relationships(pool: EvidencePool, context: ContextPackage) -> Tuple[ClaimedRelationship, ...]:
    by_id = {rel.id: rel for rel in pool.all_claimed_relationships()}
    return tuple(by_id[rid] for rid in context.relationship_ids)


def observations(pool: EvidencePool, context: ContextPackage) -> Tuple[Observation, ...]:
    return tuple(pool.get_observation(oid) for oid in context.observation_ids)


def sources(pool: EvidencePool, context: ContextPackage) -> Tuple[Source, ...]:
    return tuple(pool.get_source(sid) for sid in context.source_ids)
