"""Canonical state: the single source of truth (§3).

CanonicalState, Field, and EdgeRecord are immutable. Nothing outside this
module constructs or mutates them. "Update" always means "produce a new
CanonicalState" -- never in-place mutation.

Identity rule (I5 / §3): `fields[key].id == key` for every entry. This is
checked at construction time and is NEVER silently corrected -- a mismatch
is a ValueError, not an auto-fix.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping, Optional, Tuple

from core.canonical.schema import FieldType, FieldValue


@dataclass(frozen=True)
class Field:
    id: str
    type: FieldType
    value: FieldValue
    unit: Optional[str] = None


@dataclass(frozen=True)
class EdgeRecord:
    id: str
    from_: str
    to: str
    type: str
    attributes: Mapping[str, FieldValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Freeze attributes so an EdgeRecord is fully immutable, not just
        # its own top-level slots.
        object.__setattr__(self, "attributes", MappingProxyType(dict(self.attributes)))


@dataclass(frozen=True)
class CanonicalState:
    schema_version: str
    fields: Mapping[str, Field]
    edges: Tuple[EdgeRecord, ...] = ()

    def __post_init__(self) -> None:
        for key, f in self.fields.items():
            if f.id != key:
                raise ValueError(
                    f"CanonicalState.fields key {key!r} does not match "
                    f"Field.id {f.id!r}: canonical identity is never "
                    f"silently corrected"
                )
        # Freeze the fields mapping itself so no caller can mutate it
        # after construction (frozen=True only prevents rebinding the
        # `fields` attribute, not mutating the dict object it points to).
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))
        object.__setattr__(self, "edges", tuple(self.edges))
