"""Morpho semantic IR model (§8), graph semantics (§11), and spatial
semantics (§12).

Constructs implemented for v1 (deliberately minimal, per §5/§8): Entity,
Relation, Frame (CoordinateFrame + Transform), Group, Constraint,
ProvenanceRecord, VersionReference. `DerivedNode` and `Collection` are
explicitly deferred (§8) -- Group already covers the v1 need for naming a
set of entities, and DerivedNode has no consumer yet.

This module also provides `from_ast`, which performs semantic analysis on
a parsed `morpho.ast.Document` (used for hand-authored `.morpho` fixtures,
e.g. in tests) -- distinct from `morpho.compiler.compile_morpho`, which
builds a MorphoDocument directly from a ProjectedState (the canonical
compilation path, §13).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Literal, Optional, Tuple

from morpho import ast
from morpho.provenance import ProvenanceRecord

InferenceStatus = Literal["explicit", "inferred"]

AttributeValue = object  # str | float | bool | Vec3 | ProvenanceRecord, per grammar §7.B `value`


class SemanticError(Exception):
    pass


@dataclass(frozen=True)
class Entity:
    id: str
    attributes: Dict[str, AttributeValue]
    provenance: ProvenanceRecord


@dataclass(frozen=True)
class MorphoRelation:
    id: str
    from_id: str
    to_id: str
    type: str
    is_canonical: bool
    inference_status: InferenceStatus
    provenance: ProvenanceRecord
    confidence: Optional[float] = None

    def __post_init__(self) -> None:
        if self.is_canonical and self.inference_status == "inferred":
            raise SemanticError(
                "illegal MorphoRelation: is_canonical=True with "
                "inference_status='inferred' (§11 -- inference never "
                "produces canonical truth)"
            )


@dataclass(frozen=True)
class Vec3:
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class Quaternion:
    x: float
    y: float
    z: float
    w: float


_IDENTITY_QUATERNION = Quaternion(0.0, 0.0, 0.0, 1.0)
_UNIT_SCALE = Vec3(1.0, 1.0, 1.0)


@dataclass(frozen=True)
class Transform:
    position: Vec3
    orientation: Quaternion = _IDENTITY_QUATERNION
    scale: Vec3 = _UNIT_SCALE


@dataclass(frozen=True)
class CoordinateFrame:
    id: str
    parent: Optional[str]
    transform: Transform
    provenance: Optional[ProvenanceRecord] = None


@dataclass(frozen=True)
class Group:
    id: str
    members: Tuple[str, ...]
    provenance: Optional[ProvenanceRecord] = None


@dataclass(frozen=True)
class Constraint:
    id: str
    on: str
    rule: str
    provenance: Optional[ProvenanceRecord] = None


@dataclass(frozen=True)
class MorphoDocument:
    entities: Tuple[Entity, ...] = ()
    relations: Tuple[MorphoRelation, ...] = ()
    frames: Tuple[CoordinateFrame, ...] = ()
    groups: Tuple[Group, ...] = ()
    constraints: Tuple[Constraint, ...] = ()

    def entity_by_id(self, entity_id: str) -> Optional[Entity]:
        for e in self.entities:
            if e.id == entity_id:
                return e
        return None


def check_frame_acyclicity(frames: Tuple[CoordinateFrame, ...]) -> None:
    by_id = {f.id: f for f in frames}
    for frame in frames:
        seen = {frame.id}
        current = frame.parent
        while current is not None:
            if current in seen:
                raise SemanticError(f"cyclic CoordinateFrame parent chain involving {frame.id!r}")
            seen.add(current)
            parent_frame = by_id.get(current)
            current = parent_frame.parent if parent_frame is not None else None


def _value_from_ast(value: ast.AttrValue) -> AttributeValue:
    if isinstance(value, ast.Vector3Literal):
        return Vec3(value.x, value.y, value.z)
    if isinstance(value, ast.ProvenanceBlock):
        return _provenance_record_from_ast(value, compiler_version=None)
    return value  # str | float | bool


def _provenance_record_from_ast(
    block: ast.ProvenanceBlock, compiler_version: Optional[str]
) -> ProvenanceRecord:
    return ProvenanceRecord(
        source=block.source,
        origin_version=block.origin_version,
        # compiler_version is not representable in provenance_block's
        # grammar (§7.B has no such field); it is supplied by whichever
        # tool is running semantic analysis, not read from source text.
        compiler_version=compiler_version or "unspecified",
        confidence=block.confidence,
    )


def _entity_from_ast(decl: ast.EntityDecl, compiler_version: Optional[str]) -> Entity:
    if decl.provenance is None:
        raise SemanticError(f"entity {decl.id!r} has no provenance block (required, §8)")
    attributes = {a.name: _value_from_ast(a.value) for a in decl.attrs}
    provenance = _provenance_record_from_ast(decl.provenance, compiler_version)
    return Entity(id=decl.id, attributes=attributes, provenance=provenance)


def _relation_from_ast(decl: ast.RelationDecl, compiler_version: Optional[str]) -> MorphoRelation:
    if decl.provenance is None:
        raise SemanticError(f"relation {decl.id!r} has no provenance block (required, §8)")
    provenance = _provenance_record_from_ast(decl.provenance, compiler_version)

    if decl.modifier == "inferred":
        is_canonical, inference_status = False, "inferred"
    elif decl.modifier == "derived":
        # "derived" = asserted by a non-canonical source, but not
        # computed by inference -- is_canonical=False, explicit.
        is_canonical, inference_status = False, "explicit"
    else:
        # Unmarked: representing a canonical fact (only legal reading
        # for a bare `relation` declaration, §8 "canonical if unmarked").
        is_canonical, inference_status = True, "explicit"

    return MorphoRelation(
        id=decl.id,
        from_id=decl.from_ref,
        to_id=decl.to_ref,
        type=decl.type,
        is_canonical=is_canonical,
        inference_status=inference_status,
        provenance=provenance,
        confidence=decl.confidence,
    )


def _frame_from_ast(decl: ast.FrameDecl) -> CoordinateFrame:
    position = Vec3(decl.position.x, decl.position.y, decl.position.z)
    orientation = (
        Quaternion(decl.orientation.x, decl.orientation.y, decl.orientation.z, decl.orientation.w)
        if decl.orientation is not None
        else _IDENTITY_QUATERNION
    )
    scale = Vec3(decl.scale.x, decl.scale.y, decl.scale.z) if decl.scale is not None else _UNIT_SCALE
    transform = Transform(position=position, orientation=orientation, scale=scale)
    return CoordinateFrame(id=decl.id, parent=decl.parent, transform=transform, provenance=None)


def from_ast(document: ast.Document, compiler_version: Optional[str] = None) -> MorphoDocument:
    """Semantic analysis: parsed AST -> MorphoDocument. `compiler_version`
    is supplied by the caller (it is not part of Morpho source text, see
    `_provenance_record_from_ast`)."""
    entities = []
    relations = []
    frames = []
    groups = []
    constraints = []

    for decl in document.declarations:
        if isinstance(decl, ast.EntityDecl):
            entities.append(_entity_from_ast(decl, compiler_version))
        elif isinstance(decl, ast.RelationDecl):
            relations.append(_relation_from_ast(decl, compiler_version))
        elif isinstance(decl, ast.FrameDecl):
            frames.append(_frame_from_ast(decl))
        elif isinstance(decl, ast.GroupDecl):
            groups.append(Group(id=decl.id, members=decl.members))
        elif isinstance(decl, ast.ConstraintDecl):
            constraints.append(Constraint(id=decl.id, on=decl.on, rule=decl.rule))
        else:
            raise SemanticError(f"unknown declaration node: {decl!r}")

    frames_tuple = tuple(frames)
    check_frame_acyclicity(frames_tuple)

    return MorphoDocument(
        entities=tuple(entities),
        relations=tuple(relations),
        frames=frames_tuple,
        groups=tuple(groups),
        constraints=tuple(constraints),
    )
