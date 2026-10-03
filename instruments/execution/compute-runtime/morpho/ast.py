"""Morpho HDL abstract syntax tree, matching the EBNF grammar in
Frozen Specification v1.0.0 §7.B exactly. These are syntax nodes only --
no semantic resolution (ref lookup, provenance defaulting, inference
status derivation) happens here. That is `morpho/ir.py`'s job.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple, Union

Ref = str  # a STRING token used to reference another declaration's id


@dataclass(frozen=True)
class Vector3Literal:
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class QuaternionLiteral:
    x: float
    y: float
    z: float
    w: float


@dataclass(frozen=True)
class ProvenanceBlock:
    source: str
    origin_version: str
    confidence: Optional[float] = None


AttrValue = Union[str, float, bool, Vector3Literal, ProvenanceBlock]


@dataclass(frozen=True)
class AttrStmt:
    name: str
    value: AttrValue


@dataclass(frozen=True)
class EntityDecl:
    id: str
    attrs: Tuple[AttrStmt, ...]
    # See docs/CONTRADICTIONS.md#C1: entity_decl's grammar is extended
    # with the same optional trailing provenance_block relation_decl
    # already has, to match the frozen spec's own §7.C example.
    provenance: Optional[ProvenanceBlock] = None


@dataclass(frozen=True)
class RelationDecl:
    id: str
    from_ref: Ref
    to_ref: Ref
    type: str
    modifier: Optional[str] = None  # None | "derived" | "inferred"
    confidence: Optional[float] = None
    provenance: Optional[ProvenanceBlock] = None


@dataclass(frozen=True)
class FrameDecl:
    id: str
    position: Vector3Literal
    parent: Optional[Ref] = None
    orientation: Optional[QuaternionLiteral] = None
    scale: Optional[Vector3Literal] = None


@dataclass(frozen=True)
class GroupDecl:
    id: str
    members: Tuple[Ref, ...]


@dataclass(frozen=True)
class ConstraintDecl:
    id: str
    on: Ref
    rule: str


Declaration = Union[EntityDecl, RelationDecl, FrameDecl, GroupDecl, ConstraintDecl]


@dataclass(frozen=True)
class Document:
    morpho_version: str
    declarations: Tuple[Declaration, ...]
