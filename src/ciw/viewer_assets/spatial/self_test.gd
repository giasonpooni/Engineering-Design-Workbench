extends SceneTree
## Actual engine checks; invoked only by explicit operator/CI request.
var checks := 0

func _initialize() -> void:
	call_deferred("run")

func require(condition: bool, message: String) -> bool:
	if not condition:
		printerr("CHECK FAILED: " + message)
		quit(2)
		return false
	checks += 1
	return true

func run() -> void:
	var args := OS.get_cmdline_user_args()
	var report_path := ""
	var capture_path := ""
	for i in range(0, args.size(), 2):
		if i + 1 >= args.size():
			quit(2)
			return
		if args[i] == "--report": report_path = args[i + 1]
		elif args[i] == "--capture": capture_path = args[i + 1]
		else:
			quit(2)
			return
	if not require(not report_path.is_empty() and not FileAccess.file_exists(report_path), "new explicit report path required"): return
	var before := FileAccess.get_sha256("res://display.json")
	var Script = load("res://view.gd")
	var view = Script.new()
	root.size = Vector2i(1280, 800)
	root.add_child(view)
	await process_frame
	if not require(view.load_error.is_empty(), "consumer load: " + view.load_error): return
	await process_frame
	if not require(view.status_label.get_global_rect().end.y <= root.size.y, "status footer stays inside viewport"): return
	var count := 0
	var bindings: Array = []
	for i in range(view.data.positions_xyz_m.size()):
		view.select_sample(i)
		if not require(view.selected == i, "sample selection"): return
		var enu: Variant = view.data.source.positions_enu_m[i]
		if enu == null:
			if not require(not view.cursor.visible and view.markers[i] == null, "missingness"): return
		else:
			var expected := Vector3(enu[0], enu[2], -enu[1])
			if not require(view.cursor.visible and view.cursor.position.distance_to(expected) < 0.00001, "ENU rotation"): return
			if not require(view.markers[i].get_meta("entity_id") == view.data.source.entity_id, "entity binding"): return
			bindings.append({"sample_index": int(view.data.source.sample_indices[i]), "node_path": str(view.markers[i].get_path()), "instance_id": str(view.markers[i].get_instance_id()), "position_xyz_m": [view.markers[i].position.x, view.markers[i].position.y, view.markers[i].position.z]})
			count += 1
	view.top_view = true
	view.update_camera()
	if not require(view.camera.position.y > view.centre.y and view.camera.projection == Camera3D.PROJECTION_ORTHOGONAL, "plan view"): return
	view.distance_scale = 2.0
	view.update_camera()
	if not require(is_equal_approx(view.camera.size, view.span * 2.9), "zoom"): return
	view.reset_camera()
	# Independent malformed-payload probes. No mutable source file is required.
	var bad: Array = []
	var copy: Dictionary = view.data.duplicate(true)
	copy.schema = "unknown"; bad.append(copy)
	copy = view.data.duplicate(true); copy.basis_enu_to_xyz[1] = [0, 1, 0]; bad.append(copy)
	copy = view.data.duplicate(true); copy.source.unit = "cm"; bad.append(copy)
	copy = view.data.duplicate(true); copy.source.authority.state_admission = "passed"; bad.append(copy)
	copy = view.data.duplicate(true); copy.positions_xyz_m = []; bad.append(copy)
	copy = view.data.duplicate(true); copy.marker_radius_m = true; bad.append(copy)
	copy = view.data.duplicate(true); copy.source.positions_enu_m[0] = null; copy.positions_xyz_m[0] = [0, 0, 0]; bad.append(copy)
	for candidate in bad:
		if not require(not Script.validate(candidate).is_empty(), "negative input check"): return
	view.select_sample(mini(2, view.data.positions_xyz_m.size() - 1))
	if not capture_path.is_empty():
		if not require(DisplayServer.get_name() != "headless" and not FileAccess.file_exists(capture_path), "capture requires rendering and new path"): return
		await process_frame
		await RenderingServer.frame_post_draw
		var image := root.get_texture().get_image()
		if not require(not image.is_empty() and image.save_png(capture_path) == OK, "render capture"): return
	var unchanged := FileAccess.get_sha256("res://display.json") == before
	if not require(unchanged, "source bytes changed"): return
	var report := {"status": "passed", "assertions": checks, "godot_version": Engine.get_version_info().string,
		"result_id": view.data.source.result_id, "available_count": count,
		"sample_count": view.data.positions_xyz_m.size(), "selection_checks": view.data.positions_xyz_m.size(),
		"negative_checks": bad.size(), "source_unchanged": unchanged, "display_sha256": "sha256:" + before,
		"rendered": not capture_path.is_empty(), "runtime_bindings": bindings,
		"runtime_identity_scope": "this process only", "scientific_verification": "not_performed"}
	var output := FileAccess.open(report_path, FileAccess.WRITE)
	if not require(output != null, "report open"): return
	output.store_string(JSON.stringify(report, "  "))
	output.close()
	view.queue_free()
	await process_frame
	print("PASS: retained spatial consumer; assertions=", checks)
	quit(0)
