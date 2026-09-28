extends Control
## Read-only, disconnected consumer of a NET-generated spatial bundle.

const SCHEMA = "ciw.godot-spatial-inspection.v1"
const AUTHORITY = {"representation": "detached_copy", "scientific_verification": "not_performed", "state_admission": "not_performed", "physical_validation": "not_performed"}
var data: Dictionary = {}
var load_error := ""
var markers: Array[Node3D] = []
var cursor: MeshInstance3D
var camera: Camera3D
var viewport: SubViewport
var details: Label
var picker: OptionButton
var status_label: Label
var selected := -1
var span := 10.0
var centre := Vector3.ZERO
var angle := 0.65
var distance_scale := 1.0
var top_view := false
var world: Node3D

static func number(v: Variant) -> bool:
	return typeof(v) in [TYPE_INT, TYPE_FLOAT] and is_finite(float(v))

static func triple(v: Variant) -> bool:
	return v is Array and v.size() == 3 and number(v[0]) and number(v[1]) and number(v[2])

static func validate(payload: Variant) -> String:
	if not payload is Dictionary or payload.get("schema") != SCHEMA:
		return "Unsupported display schema"
	# JSON numbers are floats; compare finite scalar values, not Array variants.
	var basis: Variant = payload.get("basis_enu_to_xyz")
	var expected_basis := [[1, 0, 0], [0, 0, 1], [0, -1, 0]]
	if not basis is Array or basis.size() != 3:
		return "Unsupported frame mapping"
	for row in range(3):
		if not triple(basis[row]):
			return "Unsupported frame mapping"
		for col in range(3):
			if float(basis[row][col]) != float(expected_basis[row][col]):
				return "Unsupported frame mapping"
	if payload.get("interpolation") != "none" or payload.get("physics") != "not_declared":
		return "Unsupported interpolation or physics"
	if not number(payload.get("marker_radius_m")) or payload.marker_radius_m < 0.001 or payload.marker_radius_m > 100:
		return "Invalid visual marker radius"
	var src: Variant = payload.get("source")
	if not src is Dictionary or src.get("schema") != "ciw.local-frame-scene.v1":
		return "Unsupported source binding"
	if src.get("authority") != AUTHORITY or src.get("axes") != ["east", "north", "up"] or src.get("unit") != "m" or src.get("up_axis") != "Z":
		return "Unsupported source authority or coordinate convention"
	if src.get("runtime_entity_id") != null or src.get("interpolation") != "none" or src.get("physics") != "not_declared":
		return "Source must be detached, without a live runtime or physics"
	for key in ["result_id", "execution_id", "entity_id", "source_evidence_id", "frame_id", "prim_path"]:
		if not src.get(key) is String or src[key].is_empty():
			return "Missing source identity"
	var enu: Variant = src.get("positions_enu_m")
	var xyz: Variant = payload.get("positions_xyz_m")
	var times: Variant = src.get("time_s")
	var indices: Variant = src.get("sample_indices")
	if not enu is Array or not xyz is Array or not times is Array or not indices is Array:
		return "Samples must be arrays"
	if enu.size() < 1 or enu.size() > 4096 or xyz.size() != enu.size() or times.size() != enu.size() or indices.size() != enu.size():
		return "Sample counts disagree"
	for i in range(enu.size()):
		if not number(times[i]) or not number(indices[i]) or indices[i] < 0 or indices[i] != floor(indices[i]):
			return "Invalid sample index/time"
		if i > 0 and (times[i] <= times[i - 1] or indices[i] <= indices[i - 1]):
			return "Sample order must be increasing"
		if enu[i] == null:
			if xyz[i] != null:
				return "Missing position must remain unavailable"
		elif not triple(enu[i]) or not triple(xyz[i]):
			return "Positions must be finite triples"
		elif xyz[i] != [enu[i][0], enu[i][2], -enu[i][1]]:
			return "Frame mapping disagrees with source"
	return ""

func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var receipt: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://manifest.json"))
	if not receipt is Dictionary or receipt.get("schema") != "ciw.godot-spatial-bundle.v1" or not receipt.get("artifacts") is Dictionary:
		refuse("Invalid manifest")
		return
	for name in ["project.godot", "main.tscn", "view.gd", "self_test.gd", "workspace.json", "display.json"]:
		if receipt.artifacts.get(name) != "sha256:" + FileAccess.get_sha256("res://" + name):
			refuse("Bundle mismatch: " + name)
			return
	var payload: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://display.json"))
	load_error = validate(payload)
	if not load_error.is_empty():
		refuse(load_error)
		return
	data = payload.duplicate(true)
	build_view()
	select_sample(0)

func refuse(message: String) -> void:
	load_error = message
	var label := Label.new()
	label.text = "REFUSED: " + message
	add_child(label)

func label(text: String, font_size: int = 16) -> Label:
	var item := Label.new()
	item.text = text
	item.add_theme_font_size_override("font_size", font_size)
	return item

func button(text: String, callback: Callable) -> Button:
	var item := Button.new()
	item.text = text
	item.pressed.connect(callback)
	return item

func material(colour: Color) -> StandardMaterial3D:
	var item := StandardMaterial3D.new()
	item.albedo_color = colour
	item.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	return item

func sphere(radius: float, colour: Color) -> MeshInstance3D:
	var node := MeshInstance3D.new()
	var mesh := SphereMesh.new()
	mesh.radius = radius
	mesh.height = radius * 2
	mesh.radial_segments = 12
	mesh.rings = 6
	node.mesh = mesh
	node.material_override = material(colour)
	return node

func build_view() -> void:
	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for side in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 20)
	add_child(margin)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 12)
	margin.add_child(column)
	column.add_child(label("NOTATIONS  /  SPATIAL RESULT", 26))
	column.add_child(label("Retained samples · Disconnected inspection · No simulation or state admission", 16))
	var toolbar := HBoxContainer.new()
	column.add_child(toolbar)
	toolbar.add_child(button("Oblique", func(): top_view = false; update_camera()))
	toolbar.add_child(button("Plan view", func(): top_view = true; update_camera()))
	toolbar.add_child(button("Rotate", func(): angle += PI / 6.0; update_camera()))
	toolbar.add_child(button("Zoom in", func(): distance_scale = maxf(0.25, distance_scale * 0.8); update_camera()))
	toolbar.add_child(button("Zoom out", func(): distance_scale = minf(4.0, distance_scale * 1.25); update_camera()))
	toolbar.add_child(button("Reset view", reset_camera))
	var row := HBoxContainer.new()
	row.size_flags_vertical = Control.SIZE_EXPAND_FILL
	row.add_theme_constant_override("separation", 20)
	column.add_child(row)
	var box := SubViewportContainer.new()
	box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	box.stretch = true
	row.add_child(box)
	viewport = SubViewport.new()
	viewport.size = Vector2i(800, 580)
	viewport.own_world_3d = true
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	box.add_child(viewport)
	world = Node3D.new()
	world.name = "RetainedSamples"
	viewport.add_child(world)
	var positions: Array = data.positions_xyz_m
	var low := Vector3(INF, INF, INF)
	var high := -low
	for i in range(positions.size()):
		if positions[i] == null:
			markers.append(null)
			continue
		var p: Array = positions[i]
		var node := sphere(data.marker_radius_m, Color(0.20, 0.82, 0.76))
		node.name = "Sample_" + str(int(data.source.sample_indices[i]))
		node.position = Vector3(p[0], p[1], p[2])
		node.set_meta("entity_id", data.source.entity_id)
		node.set_meta("source_result_id", data.source.result_id)
		node.set_meta("sample_index", int(data.source.sample_indices[i]))
		world.add_child(node)
		markers.append(node)
		low = low.min(node.position)
		high = high.max(node.position)
	if low.is_finite():
		centre = (low + high) * 0.5
		span = maxf((high - low).length(), maxf(1.0, data.marker_radius_m * 4))
	cursor = sphere(data.marker_radius_m * 1.4, Color(1.0, 0.73, 0.30))
	cursor.name = "SelectionMarker"
	world.add_child(cursor)
	var grid := ImmediateMesh.new()
	grid.surface_begin(Mesh.PRIMITIVE_LINES, material(Color(0.19, 0.25, 0.32)))
	for i in range(-5, 6):
		var offset := float(i) * span / 10.0
		grid.surface_add_vertex(centre + Vector3(-span/2, -span/8, offset))
		grid.surface_add_vertex(centre + Vector3(span/2, -span/8, offset))
		grid.surface_add_vertex(centre + Vector3(offset, -span/8, -span/2))
		grid.surface_add_vertex(centre + Vector3(offset, -span/8, span/2))
	grid.surface_end()
	var grid_node := MeshInstance3D.new()
	grid_node.mesh = grid
	world.add_child(grid_node)
	camera = Camera3D.new()
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.near = 0.001
	camera.far = maxf(1000, span * 30)
	viewport.add_child(camera)
	camera.current = true
	update_camera()
	var sidebar := ScrollContainer.new()
	sidebar.custom_minimum_size.x = 360
	sidebar.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	row.add_child(sidebar)
	var side := VBoxContainer.new()
	side.custom_minimum_size.x = 340
	side.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	sidebar.add_child(side)
	side.add_child(label("SAMPLE INSPECTOR", 20))
	picker = OptionButton.new()
	for i in range(positions.size()):
		picker.add_item("Sample %d  |  t = %.3f s%s" % [int(data.source.sample_indices[i]), data.source.time_s[i], "  [missing]" if positions[i] == null else ""])
	picker.item_selected.connect(select_sample)
	side.add_child(picker)
	details = label("", 17)
	details.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	side.add_child(details)
	var provenance := label("Entity\n%s\n\nResult\n%s\n\nSource execution\n%s\n\nFrame\nX = east · Y = up · Z = -north\n1 unit = 1 metre\n\nMarker radius: %.3f m (display only)\nGrid spacing: %.3f m (display only)\n\nCovariance: unavailable\nInterpolation: none\nPhysics: not declared" % [data.source.entity_id, data.source.result_id, data.source.execution_id, data.marker_radius_m, span / 10.0], 15)
	provenance.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	side.add_child(provenance)
	status_label = label("", 15)
	column.add_child(status_label)

func update_camera() -> void:
	camera.size = span * 1.45 * distance_scale
	camera.position = centre + (Vector3(0, span * 2, 0) if top_view else Vector3(cos(angle), 0.85, sin(angle)) * span * 2)
	camera.look_at(centre, Vector3.FORWARD if top_view else Vector3.UP)

func reset_camera() -> void:
	angle = 0.65
	distance_scale = 1.0
	top_view = false
	update_camera()

func select_sample(index: int) -> void:
	if index < 0 or index >= data.positions_xyz_m.size():
		return
	selected = index
	picker.select(index)
	var point: Variant = data.source.positions_enu_m[index]
	cursor.visible = point != null
	if point == null:
		details.text = "POSITION UNAVAILABLE\n\nA source coordinate is missing.\nNo point or interpolation is invented."
	else:
		cursor.position = markers[index].position
		details.text = "RETAINED ENU (metres)\n\nEast    %.9f\nNorth  %.9f\nUp       %.9f\n\nTime    %.6f s" % [point[0], point[1], point[2], data.source.time_s[index]]
	status_label.text = "Sample %d / %d  ·  %s  ·  Source records remain unchanged" % [index + 1, data.positions_xyz_m.size(), "unavailable" if point == null else "selected"]
