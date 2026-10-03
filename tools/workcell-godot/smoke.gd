extends SceneTree
func _initialize() -> void:
	var scene = load("res://main.scn")
	if scene == null:
		quit(2); return
	var node = scene.instantiate()
	root.add_child(node)
	for tick in range(120):
		node.target = 2.0
		node._physics_process(1.0/60.0)
	var result = {"pack_scene_loaded":true,"height":node.height,"platform_y":node.get_node("Platform").position.y}
	var file = FileAccess.open("/work/pack-observations.json", FileAccess.WRITE)
	file.store_string(JSON.stringify(result)); file.close()
	node.queue_free()
	quit(0)
