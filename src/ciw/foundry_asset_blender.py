"""Closed Blender workbench recipe. Executed only inside operator-bound Blender.

This producer receives bounded parameters, never NET acceptance code, game scripts
or credentials. It exports geometry, not a self-issued PASS. Original authored
blockout, not an archaeological reconstruction or structural engineering model.
"""
from pathlib import Path
import json
import sys


def main():
    import bpy
    args = sys.argv[sys.argv.index('--') + 1:]
    if len(args) != 3:
        raise ValueError('expected request.json, candidate.glb and author.json')
    request_path, output, report = map(Path, args)
    request = json.loads(request_path.read_text(encoding='utf-8'))
    if set(request) != {'schema', 'packet_id', 'nonce', 'legs'} or request['schema'] != 'ciw.workbench-request.v1':
        raise ValueError('unsupported author request')
    if type(request['legs']) is not int or request['legs'] not in (3, 4):
        raise ValueError('bounded three/four-leg candidate only')
    if output.exists() or report.exists():
        raise FileExistsError('outputs must be new')
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bpy.context.scene.unit_settings.system = 'METRIC'
    bpy.context.scene.unit_settings.scale_length = 1.0
    material = bpy.data.materials.new('plain_wood')
    material.use_nodes = True
    material.use_backface_culling = True
    bsdf = material.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (0.32, 0.17, 0.075, 1.0)
    bsdf.inputs['Metallic'].default_value = 0.0
    bsdf.inputs['Roughness'].default_value = 0.82

    def box(name, size, center):
        # Author in final glTF coordinates; explicitly convert to Blender Z-up.
        sx, sy, sz = size
        x, y, z = center
        bpy.ops.mesh.primitive_cube_add(size=1, location=(x, -z, y))
        obj = bpy.context.object
        obj.name = name
        obj.dimensions = (sx, sz, sy)
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        obj.data.materials.append(material)

    box('top', (1.8, 0.08, 0.7), (0, 0.86, 0))
    corners = [(-0.76, -0.24), (0.76, -0.24), (-0.76, 0.24), (0.76, 0.24)]
    for i, (x, z) in enumerate(corners[:request['legs']]):
        box('leg_' + str(i), (0.1, 0.82, 0.1), (x, 0.41, z))
    for name, z in [('rail_front', -0.24), ('rail_back', 0.24)]:
        box(name, (1.52, 0.08, 0.08), (0, 0.24, z))
    for name, x in [('rail_left', -0.76), ('rail_right', 0.76)]:
        box(name, (0.08, 0.08, 0.48), (x, 0.24, 0))
    bpy.ops.export_scene.gltf(filepath=str(output), export_format='GLB',
        export_yup=True, export_animations=False, export_extras=False,
        export_texcoords=False, export_normals=True, export_tangents=False,
        export_materials='EXPORT', export_cameras=False, export_lights=False)
    with report.open('x', encoding='utf-8') as stream:
        json.dump({'schema': 'ciw.workbench-author.v1', 'request': request,
                   'blender_version': bpy.app.version_string}, stream)


if __name__ == '__main__':
    main()
