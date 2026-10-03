"""RetrievalQuery: the minimum, content-addressed representation of "what
was asked."

Every field is a tuple/scalar, never a mutable collection, and `id` is
always derived from the other fields (same `make_*` discipline as
`evidence/types.py` and `core/canonical/version.py::make_version`) --
two queries with identical fields always have the identical `id`,
regardless of which process or when they were constructed. This is what
makes "same query -> same result" (§7 of `docs/RETRIEVAL_ARCHITECTURE.md`)
checkable by comparing ids, not by comparing every field by hand.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from evidence.identity import content_hash


@dataclass(frozen=True)
class RetrievalQuery:
    id: str

    # Exact entity lookup / traversal seeds: matched against
    # Referent.natural_key (§3 "exact entity lookup").
    entity_natural_keys: Tuple[str, ...]

    # Restrict traversed/returned ClaimedRelationships to these types.
    # Empty = no restriction.
    relationship_types: Tuple[str, ...]

    # Restrict returned Observations to those whose Source.kind is in
    # this set. Empty = no restriction.
    source_kinds: Tuple[str, ...]

    # Restrict returned Observations to these epistemic statuses
    # (retrieval.epistemic's classification -- see that module; NOT a
    # new taxonomy). Empty = no restriction.
    epistemic_statuses: Tuple[str, ...]

    # Case-insensitive substring match against any string value in an
    # Observation's content. Empty = no text filter.
    text_terms: Tuple[str, ...]

    # Bounded BFS depth from entity_natural_keys over the Trust Graph.
    # 0 = only the seed entities themselves, no traversal.
    traversal_depth: int

    # Cap on the number of returned Referents (deterministic:
    # id-sorted, not ranked -- see docs/RETRIEVAL_ARCHITECTURE.md
    # "ordering is not ranking"). None = unbounded.
    limit: Optional[int]


def make_retrieval_query(
    entity_natural_keys: Tuple[str, ...] = (),
    relationship_types: Tuple[str, ...] = (),
    source_kinds: Tuple[str, ...] = (),
    epistemic_statuses: Tuple[str, ...] = (),
    text_terms: Tuple[str, ...] = (),
    traversal_depth: int = 0,
    limit: Optional[int] = None,
) -> RetrievalQuery:
    # Deduplicated and sorted so two queries expressing the same request
    # in a different order (or with accidental repeats) get the same id.
    entity_natural_keys = tuple(sorted(set(entity_natural_keys)))
    relationship_types = tuple(sorted(set(relationship_types)))
    source_kinds = tuple(sorted(set(source_kinds)))
    epistemic_statuses = tuple(sorted(set(epistemic_statuses)))
    text_terms = tuple(sorted(set(text_terms)))

    if traversal_depth < 0:
        raise ValueError(f"traversal_depth must be >= 0, got {traversal_depth!r}")
    if limit is not None and limit < 0:
        raise ValueError(f"limit must be >= 0 or None, got {limit!r}")

    query_id = content_hash(
        {
            "entity_natural_keys": list(entity_natural_keys),
            "relationship_types": list(relationship_types),
            "source_kinds": list(source_kinds),
            "epistemic_statuses": list(epistemic_statuses),
            "text_terms": list(text_terms),
            "traversal_depth": traversal_depth,
            "limit": limit,
        }
    )
    return RetrievalQuery(
        id=query_id,
        entity_natural_keys=entity_natural_keys,
        relationship_types=relationship_types,
        source_kinds=source_kinds,
        epistemic_statuses=epistemic_statuses,
        text_terms=text_terms,
        traversal_depth=traversal_depth,
        limit=limit,
    )
