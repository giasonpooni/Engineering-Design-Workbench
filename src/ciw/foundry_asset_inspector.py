"""Fixed, separately executed Godot observer; no access to the Blender recipe.

The inspector measures imported mesh vertices and casts rays against triangle
collision created from those meshes. It returns observations, never acceptance.
"""
GODOT_SCRIPT = r'''extends SceneTree
var args: PackedStringArray
func _initialize() -> void:
    run.call_deferred()
func v(p: Vector3) -> Array:
    return [p.x,p.y,p.z]
func run() -> void:
    args=OS.get_cmdline_user_args()
    if args.size()!=3:
        push_error("expected candidate.glb, request.json and observations.json");quit(2);return
    var request: Variant=JSON.parse_string(FileAccess.get_file_as_string(args[1]))
    var doc:=GLTFDocument.new()
    var state:=GLTFState.new()
    var error:=doc.append_from_file(args[0],state)
    if error!=OK:
        push_error("glTF import failed");quit(2);return
    var world:=Node3D.new();root.add_child(world)
    var asset:=doc.generate_scene(state)
    if asset==null:
        push_error("glTF scene absent");quit(2);return
    world.add_child(asset)
    var parts: Dictionary={}
    var meshes: Array=asset.find_children("*","MeshInstance3D",true,false)
    if asset is MeshInstance3D: meshes.push_front(asset)
    for node: MeshInstance3D in meshes:
        if parts.has(str(node.name)):
            push_error("duplicate imported mesh name");quit(2);return
        var lo:=Vector3(INF,INF,INF);var hi:=Vector3(-INF,-INF,-INF)
        var vertex_count:=0;var triangle_count:=0
        for surface in range(node.mesh.get_surface_count()):
            var arrays:=node.mesh.surface_get_arrays(surface)
            var vertices: PackedVector3Array=arrays[Mesh.ARRAY_VERTEX]
            var indices: PackedInt32Array=arrays[Mesh.ARRAY_INDEX]
            for point in vertices:
                var p: Vector3=node.global_transform*point
                lo=lo.min(p);hi=hi.max(p)
            vertex_count+=vertices.size()
            triangle_count+=int(indices.size()/3) if not indices.is_empty() else int(vertices.size()/3)
        parts[str(node.name)]={"min":v(lo),"max":v(hi),"vertices":vertex_count,"triangles":triangle_count}
        var body:=StaticBody3D.new();body.name=node.name;world.add_child(body)
        body.global_transform=node.global_transform
        var hull:=CollisionShape3D.new();hull.shape=node.mesh.create_trimesh_shape();body.add_child(hull)
    await physics_frame
    await physics_frame
    var rays: Array=[]
    # These probes are authored independently of generator helpers. Top, four feet,
    # and a clear area outside the bench. Full character collision is NOT inferred.
    var probes: Array=[
        [Vector3(0,1.5,0),Vector3(0,0.5,0)],
        [Vector3(-0.76,0.1,-1),Vector3(-0.76,0.1,0)],
        [Vector3(0.76,0.1,-1),Vector3(0.76,0.1,0)],
        [Vector3(-0.76,0.1,1),Vector3(-0.76,0.1,0)],
        [Vector3(0.76,0.1,1),Vector3(0.76,0.1,0)],
        [Vector3(2,1.5,0),Vector3(2,-0.2,0)]]
    for endpoints in probes:
        var q:=PhysicsRayQueryParameters3D.create(endpoints[0],endpoints[1])
        var hit:=world.get_world_3d().direct_space_state.intersect_ray(q)
        rays.append({"from":v(endpoints[0]),"to":v(endpoints[1]),
            "hit":not hit.is_empty(),"position":null if hit.is_empty() else v(hit.position),
            "name":null if hit.is_empty() else str(hit.collider.name)})
    var report: Dictionary={"schema":"ciw.workbench-import.v1","request":request,
        "asset_sha256":"sha256:"+FileAccess.get_sha256(args[0]),
        "engine_version":Engine.get_version_info().string,"parts":parts,"rays":rays}
    var file:=FileAccess.open(args[2],FileAccess.WRITE)
    file.store_string(JSON.stringify(report,"",true,true));file.flush();file.close()
    world.queue_free();await process_frame
    print("WORKBENCH_OBSERVATIONS_WRITTEN");quit(0)
'''
PROJECT = b'config_version=5\n[application]\nconfig/name="NET workbench asset inspection"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n'
