"""Three.js backend (Section 14): Morpho IR -> declarative scene
descriptor.

This module never constructs a THREE.Object3D, THREE.Mesh,
THREE.Material, or any WebGL handle -- it returns plain, JSON-serializable
data. `renderer/index.html` is the only place real THREE.* objects are
built (I8). `compile_threejs` is pure and deterministic: the same
(ir, config) always produces the same descriptor.

Value-to-geometry encoding (Phase 12 -- upgraded from a fixed 1x1x1 box
for every entity): for an entity whose canonical `value` is numeric
(int/float, not bool), the emitted box geometry's size is a
min-max-normalized function of that value against every OTHER numeric
value present in the SAME compiled scene, mapped linearly onto
[_MIN_SCALE, _MAX_SCALE]. This is the entire mapping -- explicit,
documented here, and nowhere else: no domain semantics are buried in
`renderer/index.html`, which still only ever receives an
already-compiled `size` number and draws a box of that size. An entity
with a non-numeric value (string/bool), or a scene where every numeric
value is identical (an empty or degenerate range), falls back to the
previous fixed 1.0 scale -- there is no meaningful "relative magnitude"
to encode in either case.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Tuple

from core.canonical.schema import FieldValue
from morpho.ir import MorphoDocument

DEFAULT_MATERIAL_ID = "default_material"
_LAYOUT_SPACING = 2.0

# The explicit, deterministic value -> geometry-size mapping (see module
# docstring). Entities with no meaningful numeric value, or a scene with
# no numeric spread to normalize against, get _MIN_SCALE's midpoint (the
# pre-Phase-12 fixed size).
_MIN_SCALE = 0.5
_MAX_SCALE = 2.0
_DEFAULT_SCALE = 1.0


@dataclass(frozen=True)
class ThreeJSRenderConfig:
    # Extrinsic, non-canonical (§12): camera/viewport defaults, never
    # sourced from CanonicalState or Morpho IR.
    camera: Mapping[str, FieldValue] = field(default_factory=dict)
    viewport: Mapping[str, FieldValue] = field(default_factory=dict)


@dataclass(frozen=True)
class ThreeJSSceneDescriptor:
    geometries: Tuple[Dict, ...]
    materials: Tuple[Dict, ...]
    meshes: Tuple[Dict, ...]
    hierarchy: Tuple[Dict, ...]


def _layout_position(entity_id: str, index: int, ir: MorphoDocument) -> Tuple[float, float, float]:
    """Deterministic pure function of the IR: entities carrying an
    intrinsic CoordinateFrame (§12) are placed at that frame's position;
    everything else gets a fixed deterministic grid slot derived only
    from sorted entity-id order (never from wall-clock time, randomness,
    or renderer state)."""
    for frame in ir.frames:
        if frame.id == entity_id:
            p = frame.transform.position
            return (p.x, p.y, p.z)
    return (index * _LAYOUT_SPACING, 0.0, 0.0)


def _numeric_value(entity) -> Optional[float]:
    """The entity's canonical `value`, as a float, IF it is numeric --
    bool is deliberately excluded even though `isinstance(True, int)` is
    true in Python, since a boolean has no magnitude to encode."""
    value = entity.attributes.get("value")
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _normalized_scale(value: Optional[float], all_numeric_values: List[float]) -> float:
    """Deterministic min-max normalization onto [_MIN_SCALE, _MAX_SCALE].
    Pure function of `value` and the full set of numeric values in the
    scene being compiled -- never wall-clock time, randomness, or
    anything outside the IR."""
    if value is None:
        return _DEFAULT_SCALE
    lo, hi = min(all_numeric_values), max(all_numeric_values)
    if lo == hi:
        return _DEFAULT_SCALE  # degenerate range: nothing to normalize against
    fraction = (value - lo) / (hi - lo)
    return _MIN_SCALE + fraction * (_MAX_SCALE - _MIN_SCALE)


def compile_threejs(ir: MorphoDocument, config: ThreeJSRenderConfig) -> ThreeJSSceneDescriptor:
    from morpho.identity import geometry_id, visual_id

    geometries = []
    materials = [{"id": DEFAULT_MATERIAL_ID, "kind": "standard", "color": "#3366cc"}]
    meshes = []
    hierarchy = []

    sorted_entities = sorted(ir.entities, key=lambda e: e.id)
    all_numeric_values = [v for v in (_numeric_value(e) for e in sorted_entities) if v is not None]

    for index, entity in enumerate(sorted_entities):
        gid = geometry_id(entity.id)
        vid = visual_id(entity.id)
        scale = _normalized_scale(_numeric_value(entity), all_numeric_values)
        geometries.append({"id": gid, "kind": "box", "params": {"size": [scale, scale, scale]}})
        position = _layout_position(entity.id, index, ir)
        meshes.append(
            {
                "id": vid,
                "geometry": gid,
                "material": DEFAULT_MATERIAL_ID,
                "position": list(position),
                "orientation": [0.0, 0.0, 0.0, 1.0],
                "scale": [1.0, 1.0, 1.0],
            }
        )

    frames_by_id = {f.id: f for f in ir.frames}
    for frame in ir.frames:
        if frame.parent is not None and frame.parent in frames_by_id:
            hierarchy.append({"child": visual_id(frame.id), "parent": visual_id(frame.parent)})

    return ThreeJSSceneDescriptor(
        geometries=tuple(geometries),
        materials=tuple(materials),
        meshes=tuple(meshes),
        hierarchy=tuple(hierarchy),
    )
