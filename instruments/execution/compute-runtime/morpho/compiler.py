"""compile_morpho: ProjectedState -> Morpho IR (§13).

Pure and deterministic: the same (projected, config) always produces a
byte-identical (structurally-equal) MorphoDocument. Never reads a
VersionStore for anything beyond the `origin_version` it already carries
as input data. This is the canonical compilation path -- distinct from
`morpho.ir.from_ast`, which builds a MorphoDocument from hand-authored
`.morpho` source text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from core.canonical.schema import FieldValue
from core.projection.project import ProjectedState
from morpho.ir import CoordinateFrame, Entity, MorphoDocument, MorphoRelation, Transform, Vec3
from morpho.provenance import canonical_provenance

MORPHO_COMPILER_VERSION = "1.0.0"


@dataclass(frozen=True)
class CompilerConfig:
    compiler_version: str = MORPHO_COMPILER_VERSION
    options: Mapping[str, FieldValue] = field(default_factory=dict)


def compile_morpho(projected: ProjectedState, config: CompilerConfig) -> MorphoDocument:
    entities = []
    frames = []

    for key in sorted(projected.fields.keys()):
        f = projected.fields[key]
        provenance = canonical_provenance(
            origin_version=projected.source_version, compiler_version=config.compiler_version
        )
        entities.append(
            Entity(
                id=f.id,
                attributes={"type": f.type, "value": f.value, "unit": f.unit},
                provenance=provenance,
            )
        )
        if f.type == "vector3":
            frames.append(
                CoordinateFrame(
                    id=f.id,
                    parent=None,
                    transform=Transform(position=Vec3(*f.value)),
                    provenance=provenance,
                )
            )

    relations = []
    for e in projected.edges:
        provenance = canonical_provenance(
            origin_version=projected.source_version, compiler_version=config.compiler_version
        )
        relations.append(
            MorphoRelation(
                id=e.id,
                from_id=e.from_,
                to_id=e.to,
                type=e.type,
                is_canonical=True,
                inference_status="explicit",
                provenance=provenance,
                confidence=None,
            )
        )

    return MorphoDocument(
        entities=tuple(entities),
        relations=tuple(relations),
        frames=tuple(frames),
        groups=(),
        constraints=(),
    )
