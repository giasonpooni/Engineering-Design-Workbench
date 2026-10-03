extends SceneTree
func _initialize() -> void:
	var obj = JSON.parse_string(FileAccess.get_file_as_string("res://mesh.json"))
	if not obj is Dictionary or not obj.has_all(["vertices", "triangles"]):
		quit(2); return
	if obj.vertices.size() != 8 or obj.triangles.size() != 12:
		quit(3); return
	var surface := SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	for face in obj.triangles:
		if face.size() != 3:
			quit(4); return
		for index in face:
			if int(index) < 0 or int(index) >= obj.vertices.size():
				quit(5); return
			var p = obj.vertices[int(index)]
			surface.add_vertex(Vector3(p[0], p[1], p[2]))
	surface.generate_normals()
	var mesh := surface.commit()
	if ResourceSaver.save(mesh, "res://prop.res") != OK:
		quit(6); return
	var rule = load("res://motion.gd")
	if rule == null or not rule.can_instantiate():
		quit(7); return
	var scene := Node3D.new()
	scene.name = "WorkcellSlice"
	scene.set_script(load("res://driver.gd"))
	var platform := MeshInstance3D.new()
	platform.name = "Platform"
	platform.mesh = load("res://prop.res")
	var material := StandardMaterial3D.new()
	material.albedo_color = Color(0.2, 0.65, 0.8)
	platform.material_override = material
	scene.add_child(platform); platform.owner = scene
	var camera := Camera3D.new()
	camera.name = "Camera"
	camera.position = Vector3(4, 3, 5)
	camera.rotation_degrees = Vector3(-22, 38, 0)
	scene.add_child(camera); camera.owner = scene
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-50, -25, 0)
	scene.add_child(light); light.owner = scene
	var floor := MeshInstance3D.new()
	var plane := PlaneMesh.new(); plane.size = Vector2(12,12)
	floor.mesh = plane
	scene.add_child(floor); floor.owner = scene
	var caption := Label.new()
	caption.text = "NET workcell test slice — Space/Enter: move platform\nOriginal demo geometry. Not the 1792 world."
	caption.position = Vector2(20,20)
	scene.add_child(caption); caption.owner = scene
	var packed := PackedScene.new()
	if packed.pack(scene) != OK or ResourceSaver.save(packed, "res://main.scn") != OK:
		quit(8); return
	scene.free()
	quit(0)
