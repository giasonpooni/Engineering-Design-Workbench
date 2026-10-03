"""Generate demo ThreeJSSceneDescriptor JSON files for renderer/index.html.

This script exercises the full pipeline described in Frozen Specification
v1.0.0 §1 end to end (CanonicalState -> Validation -> ProjectedState ->
Morpho IR -> Three.js backend) against a 10-field, 0-edge schema matching
the v1 prototype shape described in the spec (§0, §14, §22). It is a
demo/dev utility, not part of the architecture itself -- nothing in
core/, morpho/, or backends/ depends on it.

Usage: python3 scripts/generate_sample_scene.py
Writes: renderer/scene_v1.json, renderer/scene_v2.json
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.canonical.delta import CandidateChange, CandidateDelta
from core.canonical.schema import FieldSchema, StateSchema
from core.canonical.validation import validate_candidate
from core.canonical.version import ProvenanceInfo, create_genesis_version
from core.projection.project import project_state
from morpho.compiler import CompilerConfig, compile_morpho
from backends.threejs.compiler import ThreeJSRenderConfig, compile_threejs

SCHEMA = StateSchema(
    schema_version="1.0.0",
    fields={
        "mass": FieldSchema(id="mass", type="scalar", unit="kg", default=10),
        "temperature": FieldSchema(id="temperature", type="scalar", unit="K", default=293.15),
        "pressure": FieldSchema(id="pressure", type="scalar", unit="Pa", default=101325),
        "velocity": FieldSchema(id="velocity", type="scalar", unit="m/s", default=0),
        "energy": FieldSchema(id="energy", type="scalar", unit="J", default=0),
        "volume": FieldSchema(id="volume", type="scalar", unit="m^3", default=1.0),
        "density": FieldSchema(id="density", type="scalar", unit="kg/m^3", default=1.0),
        "charge": FieldSchema(id="charge", type="scalar", unit="C", default=0),
        "frequency": FieldSchema(id="frequency", type="scalar", unit="Hz", default=1),
        "luminosity": FieldSchema(id="luminosity", type="scalar", unit="cd", default=0),
    },
)


def _asdict(obj):
    if dataclasses.is_dataclass(obj):
        return {k: _asdict(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, (list, tuple)):
        return [_asdict(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _asdict(v) for k, v in obj.items()}
    return obj


def main() -> None:
    out_dir = Path(__file__).resolve().parent.parent / "renderer"

    v0 = create_genesis_version(SCHEMA, "2026-08-22T00:00:00Z")
    scene_v1 = compile_threejs(compile_morpho(project_state(v0), CompilerConfig()), ThreeJSRenderConfig())
    (out_dir / "scene_v1.json").write_text(json.dumps(_asdict(scene_v1), indent=2, sort_keys=True))

    provenance = ProvenanceInfo(author="demo_script", transaction_id="tx_demo_1", source="manual_edit")
    candidate = CandidateDelta(
        version_from=v0.id,
        transaction_id="tx_demo_1",
        timestamp="2026-08-22T00:05:00Z",
        changes=(
            CandidateChange(
                path="fields.mass.value", operation="replace", old_value=10, new_value=42, provenance=provenance
            ),
            CandidateChange(
                path="fields.temperature.value",
                operation="replace",
                old_value=293.15,
                new_value=310.0,
                provenance=provenance,
            ),
        ),
    )
    result = validate_candidate(SCHEMA, v0.state, candidate)
    if isinstance(result, list):
        raise SystemExit(f"validation failed: {result}")
    v1 = result

    scene_v2 = compile_threejs(compile_morpho(project_state(v1), CompilerConfig()), ThreeJSRenderConfig())
    (out_dir / "scene_v2.json").write_text(json.dumps(_asdict(scene_v2), indent=2, sort_keys=True))

    print(f"genesis version: {v0.id}")
    print(f"updated version: {v1.id}")
    print(f"wrote {out_dir / 'scene_v1.json'}")
    print(f"wrote {out_dir / 'scene_v2.json'}")


if __name__ == "__main__":
    main()
