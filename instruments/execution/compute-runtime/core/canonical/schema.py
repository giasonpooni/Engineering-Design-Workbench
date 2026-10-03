"""Schema / validation contract for canonical state.

Implements Frozen Specification v1.0.0 §6.

A StateSchema describes what fields and edge types a CanonicalState of a
given schema_version is allowed to contain. It is the frontend of the
compiler pipeline (§1, §13): every candidate update is checked against a
StateSchema before it may become a new Version.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Mapping, Optional, Tuple, Union

FieldType = Literal["scalar", "string", "bool", "vector3", "quaternion"]

# A field's runtime value. vector3/quaternion values are represented as
# fixed-length float tuples (immutable) rather than a Vec3/Quaternion
# object, so CanonicalState never depends on morpho's spatial types (§12
# keeps Vec3/Quaternion as Morpho-layer constructs built *from* canonical
# vector3/quaternion fields, not the other way around).
FieldValue = Union[int, float, str, bool, Tuple[float, ...]]


@dataclass(frozen=True)
class FieldConstraints:
    min: Optional[float] = None
    max: Optional[float] = None
    enum: Optional[Tuple[FieldValue, ...]] = None
    pattern: Optional[str] = None  # regex, only meaningful for type="string"


@dataclass(frozen=True)
class FieldSchema:
    id: str
    type: FieldType
    unit: Optional[str] = None
    constraints: FieldConstraints = field(default_factory=FieldConstraints)
    required: bool = True
    # Not itemized in the frozen spec's FieldSchema table (§6), but §4
    # requires the genesis Version to be "created once at system bootstrap
    # from the schema's declared defaults" -- `default` is the minimal
    # addition needed to make that sentence implementable. It does not
    # change validation semantics or introduce a new architectural
    # concept; it is only consulted by genesis construction (version.py).
    default: Optional[FieldValue] = None


@dataclass(frozen=True)
class EdgeSchema:
    type: str
    from_type: Optional[str] = None
    to_type: Optional[str] = None


@dataclass(frozen=True)
class StateSchema:
    schema_version: str
    fields: Mapping[str, FieldSchema]
    edges: Tuple[EdgeSchema, ...] = ()

    def __post_init__(self) -> None:
        for key, field_schema in self.fields.items():
            if field_schema.id != key:
                raise ValueError(
                    f"StateSchema.fields key {key!r} does not match "
                    f"FieldSchema.id {field_schema.id!r}"
                )
