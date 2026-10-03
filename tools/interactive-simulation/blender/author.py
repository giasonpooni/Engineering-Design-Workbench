"""Blender background job: a quarter-metre sphere and asymmetric frame markers.

This generator is intentionally fixed. Physical parameters come from NET's
scenario, not from materials or an animation. Run with --factory-startup.
"""
import json
from pathlib import Path
import sys
import bpy

args = sys.argv[sys.argv.index("--") + 1:]
if len(args) != 2:
    raise ValueError("expected output.glb and author-report.json")
asset, report = map(Path, args)
if asset.exists() or report.exists():
    raise FileExistsError("authoring outputs are create-only")
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
bpy.context.scene.unit_settings.system = "METRIC"
bpy.context.scene.unit_settings.scale_length = 1.0
bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=0.25)
bpy.context.object.name = "projectile"
# Blender (x,y,z) -> glTF (x,z,-y). Unequal axes expose swaps and reflections.
for name, position in {"origin": (0, 0, 0), "axis_x": (1, 0, 0),
                       "axis_y": (0, 0, 2), "axis_z": (0, -3, 0)}.items():
    obj = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = position
bpy.ops.export_scene.gltf(filepath=str(asset), export_format="GLB", export_yup=True,
                          export_animations=False, export_materials="NONE", export_extras=False)
with report.open("x", encoding="utf-8") as stream:
    json.dump({"blender_version": bpy.app.version_string, "export_y_up": True, "radius_m": .25}, stream)
