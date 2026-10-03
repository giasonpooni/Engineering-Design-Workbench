extends SceneTree
## Installed packaging step, not candidate-owned. Only explicitly scoped source/resources.
func _initialize() -> void:
	var config: Dictionary=JSON.parse_string(FileAccess.get_file_as_string("/recipe/smith_recipe.json"))
	var files: Array=config.sources.duplicate()
	files.append_array(["project.godot","smith.scn"])
	var packer:=PCKPacker.new()
	if packer.pck_start("/work/smith.pck")!=OK: quit(2);return
	for path in files:
		if packer.add_file("res://"+str(path),"/work/"+str(path))!=OK: quit(3);return
	if packer.flush()!=OK: quit(4);return
	quit(0)
