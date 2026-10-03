"""Morpho identity model (§9).

v1 rule -- exact, no transformation:

    field_name == node_id == cell_id == visual_id == geometry_id

These four functions exist separately (rather than call sites just using
`entity.id` directly) so that a future schema evolution can change one of
them to a real derivation without touching every call site. Do not
"improve" this into hashing, namespacing, or UUID generation now -- see
§9 and §23.
"""

from __future__ import annotations


def node_id(entity_id: str) -> str:
    return entity_id


def cell_id(entity_id: str) -> str:
    return entity_id


def visual_id(entity_id: str) -> str:
    return entity_id


def geometry_id(entity_id: str) -> str:
    return entity_id
