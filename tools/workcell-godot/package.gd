extends SceneTree
func _initialize() -> void:
	var packer := PCKPacker.new()
	if packer.pck_start("res://slice.pck") != OK:
		quit(2); return
	for path in ["project.godot","main.scn","prop.res","motion.gd","driver.gd","smoke.gd"]:
		if packer.add_file("res://"+path, "res://"+path) != OK:
			quit(3); return
	if packer.flush() != OK:
		quit(4); return
	quit(0)
