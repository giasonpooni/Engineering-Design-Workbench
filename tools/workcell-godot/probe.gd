extends SceneTree
func _initialize() -> void:
	var mesh = load("res://prop.res")
	var script = load("res://motion.gd")
	var scene = load("res://main.scn")
	if mesh == null or script == null or scene == null:
		quit(2); return
	var rule = script.new()
	var challenges = [[0.0,2.0,0.25],[1.9,2.0,0.25],[2.0,0.0,0.4],[-1.0,1.0,0.1],[1.0,1.0,0.5]]
	var values := []
	for c in challenges:
		values.append(rule.integrate(c[0],c[1],c[2]))
	var trajectory := [0.0]
	for i in range(120):
		trajectory.append(rule.integrate(trajectory[-1],2.0,1.0/60.0))
	var node = scene.instantiate()
	var platform = node.get_node_or_null("Platform")
	var bounds = mesh.get_aabb()
	var array = mesh.surface_get_arrays(0)
	var vertices := []
	for p in array[Mesh.ARRAY_VERTEX]:
		vertices.append([p.x,p.y,p.z])
	var data = {"engine":Engine.get_version_info().string,"bounds":[bounds.size.x,bounds.size.y,bounds.size.z],
		"vertices":vertices,"challenges":challenges,"values":values,"trajectory":trajectory,
		"scene_has_platform":platform != null,"platform_matches":platform != null and platform.mesh.get_aabb() == bounds}
	var file = FileAccess.open("res://observations.json", FileAccess.WRITE)
	file.store_string(JSON.stringify(data)); file.close()
	node.free()
	quit(0)
