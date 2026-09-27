extends VBoxContainer
const Kit = preload("res://scripts/presentation_kit.gd")
## Geodesic path tab: local HOST CSG render JSON only. No websocket. Presentation only.
## Conceptually attached to ciw.curved-path-transfer.v1 — no second op.
const TEXT := Color("dce6f1")
const MUTED := Color("899cb2")
const TEAL := Color("60dfcd")
const AMBER := Color("ffcc80")
const STEEL := Color("537778")
const AXIS := Color("4e647e")
const LABEL_C := Color("a4b4c8")
const WASH := Color(0.24, 0.42, 0.66, 0.36)
const DEFAULT_RELATIVE := "../examples/csg-path-sensitivity/results/csg_render.json"
const MATCH_NAME := "csg_render.json"

var _render_relative := ""
var _render_match := ""
var _missing_hint := ""
var _chrome_kicker := "GEODESIC PATH  /  CSG"
var _chrome_title := "Constant-curvature HOST presentation"
var _chrome_sub := "ciw.curved-path-transfer.v1 · local file · no second op"

var _viewport: SubViewport
var _world: Node3D
var _camera: Camera3D
var _path_mesh: MeshInstance3D
var _strip_mesh: MeshInstance3D
var _axes: MeshInstance3D
var _marker: MeshInstance3D
var _labels_3d: Array[Label3D] = []
var _path_points: PackedVector3Array = []
var _status: Label
var _path_label: Label
var _caption: Label
var _length_value: Label
var _residual_value: Label
var _sens_value: Label
var _native_value: Label
var _reload: Button
var _data: Dictionary = {}
var _loaded := false
var _loaded_path := ""
var _stale := true
var _center := Vector3.ZERO
var _radius := 4.0
var _base_radius := 4.0
var _yaw := 0.85
var _pitch := 0.4


func _ready() -> void:
	add_theme_constant_override("separation", 12)
	_build_ui()
	_try_load()


func _box(fill: Color, edge: Color, radius: int) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = fill
	style.border_color = edge
	style.set_border_width_all(1)
	style.set_corner_radius_all(radius)
	style.content_margin_left = 12
	style.content_margin_right = 12
	style.content_margin_top = 10
	style.content_margin_bottom = 10
	return style


func _label(text: String, font_size: int = 14, color: Color = TEXT) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", color)
	return label


func _panel() -> PanelContainer:
	var panel := PanelContainer.new()
	panel.add_theme_stylebox_override("panel", _box(Color("101a28"), Color("273549"), 9))
	return panel


func _material(color: Color, transparent: bool = false) -> StandardMaterial3D:
	return Kit.unshaded(color, transparent)


func _build_ui() -> void:
	var header := HBoxContainer.new()
	header.add_theme_constant_override("separation", 12)
	add_child(header)
	var titles := VBoxContainer.new()
	titles.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(titles)
	titles.add_child(_label(_chrome_kicker, 12, TEAL))
	titles.add_child(_label(_chrome_title, 20))
	titles.add_child(_label(_chrome_sub, 12, MUTED))
	var actions := HBoxContainer.new()
	header.add_child(actions)
	_status = _label("●  WAITING", 13, AMBER)
	_status.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	actions.add_child(_status)
	_reload = Button.new()
	_reload.text = "Reload"
	_reload.pressed.connect(_try_load)
	actions.add_child(_reload)

	_path_label = _label("render path —", 11, MUTED)
	_path_label.clip_text = true
	add_child(_path_label)

	var panels := HBoxContainer.new()
	panels.add_theme_constant_override("separation", 14)
	panels.size_flags_vertical = Control.SIZE_EXPAND_FILL
	add_child(panels)

	var path_card := _panel()
	path_card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	path_card.size_flags_vertical = Control.SIZE_EXPAND_FILL
	panels.add_child(path_card)
	var path_column := VBoxContainer.new()
	path_card.add_child(path_column)
	path_column.add_child(_label("01   PATH POLYLINE", 12, TEAL))
	path_column.add_child(_label("Declared constant curvature · host-sampled", 18))
	var host := SubViewportContainer.new()
	host.stretch = true
	host.custom_minimum_size = Vector2(300, 270)
	host.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	host.size_flags_vertical = Control.SIZE_EXPAND_FILL
	host.gui_input.connect(_on_viewport_input)
	path_column.add_child(host)
	_viewport = SubViewport.new()
	_viewport.size = Vector2i(640, 400)
	_viewport.own_world_3d = true
	_viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	host.add_child(_viewport)
	_world = Node3D.new()
	_viewport.add_child(_world)
	var environment := WorldEnvironment.new()
	var settings := Environment.new()
	settings.background_mode = Environment.BG_COLOR
	settings.background_color = Color("0c1521")
	environment.environment = settings
	_world.add_child(environment)
	_camera = Camera3D.new()
	_camera.current = true
	_camera.near = 0.01
	_camera.far = 1000
	_camera.fov = 45
	_world.add_child(_camera)
	_path_mesh = MeshInstance3D.new()
	_strip_mesh = MeshInstance3D.new()
	_axes = MeshInstance3D.new()
	_marker = MeshInstance3D.new()
	for item in [_path_mesh, _strip_mesh, _axes, _marker]:
		_world.add_child(item)
	_path_mesh.material_override = _material(TEAL)
	_strip_mesh.material_override = _material(WASH, true)
	_axes.material_override = _material(AXIS)
	_marker.material_override = _material(Color("ffcc80"))
	_marker.visible = false
	path_column.add_child(_label("HOST mesh · drag to orbit / wheel to zoom · not surveyed BIM", 11, MUTED))

	var sens_card := _panel()
	sens_card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	sens_card.size_flags_vertical = Control.SIZE_EXPAND_FILL
	panels.add_child(sens_card)
	var sens_column := VBoxContainer.new()
	sens_card.add_child(sens_column)
	sens_column.add_child(_label("02   SENSITIVITY STRIP", 12, TEAL))
	sens_column.add_child(_label("Jacobi norm along arclength", 18))
	var sens_note := _label(
		"Strip is a presentation offset of host-computed Jacobi norms. "
		+ "Endpoint residual compares curved Jacobi magnitude to a flat linear prediction.",
		12,
		MUTED
	)
	sens_note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	sens_column.add_child(sens_note)
	var spacer := Control.new()
	spacer.size_flags_vertical = Control.SIZE_EXPAND_FILL
	sens_column.add_child(spacer)
	sens_column.add_child(_label("Native CSG checkout unsupported-until-checkout", 11, AMBER))

	var cards := HBoxContainer.new()
	cards.add_theme_constant_override("separation", 12)
	add_child(cards)
	_length_value = _add_card(cards, "PATH LENGTH")
	_residual_value = _add_card(cards, "DECLARED RESIDUAL")
	_sens_value = _add_card(cards, "SENSITIVITY NORM")
	_native_value = _add_card(cards, "NATIVE STATUS")

	_caption = _label(
		"Not surveyed BIM or physical geodesic truth. Numbers from host CSG JSON only; STALE if missing.",
		11,
		MUTED
	)
	_caption.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	add_child(_caption)

	var footer := HBoxContainer.new()
	add_child(footer)
	var authority := _label(
		"HOST CSG JSON → CARDS     •     POLYLINE → PRESENTATION     •     " + Kit.CAPTION,
		10,
		MUTED
	)
	authority.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	footer.add_child(authority)
	footer.add_child(_label("VERIFICATION  /  NOT CLAIMED", 10, AMBER))
	_set_interaction(false)
	_update_camera()


func _add_card(row: HBoxContainer, title: String) -> Label:
	var card := _panel()
	card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(card)
	var contents := VBoxContainer.new()
	card.add_child(contents)
	contents.add_child(_label(title, 11, MUTED))
	var value := _label("—", 20)
	value.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	contents.add_child(value)
	return value


func configure_presentation(opts: Dictionary) -> void:
	if opts.has("relative"):
		_render_relative = str(opts["relative"])
	if opts.has("match"):
		_render_match = str(opts["match"])
	if opts.has("missing_hint"):
		_missing_hint = str(opts["missing_hint"])
	if opts.has("kicker"):
		_chrome_kicker = str(opts["kicker"])
	if opts.has("title"):
		_chrome_title = str(opts["title"])
	if opts.has("subtitle"):
		_chrome_sub = str(opts["subtitle"])


func _resolve_path() -> String:
	var relative := _render_relative if not _render_relative.is_empty() else DEFAULT_RELATIVE
	var match_name := _render_match if not _render_match.is_empty() else MATCH_NAME
	return Kit.resolve_render_path(relative, match_name)


func _try_load() -> void:
	var path := _resolve_path()
	_loaded_path = path
	_path_label.text = "render path  " + path
	_path_label.tooltip_text = path
	var parsed := Kit.load_json(path)
	if parsed.is_empty():
		_data.clear()
		_loaded = false
		_clear_view()
		var hint := _missing_hint if not _missing_hint.is_empty() else "csg_render.json missing — generate with examples/csg-path-sensitivity/emit_render.py"
		_apply_stale("STALE", hint)
		return
	_data = parsed
	_loaded = true
	_status.text = "●  LOADED"
	_status.add_theme_color_override("font_color", Kit.status_color("LIVE"))
	_set_interaction(true)
	_set_stale(false)
	_refresh()


func _apply_stale(state: String, detail: String) -> void:
	_status.text = "●  " + Kit.format_status_label(state)
	_status.add_theme_color_override("font_color", Kit.status_color(state))
	_path_label.text = detail if _loaded_path.is_empty() else (_loaded_path + "  ·  " + detail)
	_length_value.text = "—"
	_residual_value.text = "—"
	_sens_value.text = "—"
	_native_value.text = "STALE"
	_set_interaction(false)
	_set_stale(true)


func _set_interaction(_enabled: bool) -> void:
	pass


func _set_stale(value: bool) -> void:
	_stale = value
	if _path_mesh != null:
		_path_mesh.material_override = _material(STEEL if value else TEAL)
	if _strip_mesh != null:
		_strip_mesh.material_override = _material(STEEL if value else WASH, true)


func _refresh() -> void:
	if not _loaded:
		_apply_stale("STALE", "no render data")
		return
	var cards: Dictionary = _data.get("cards", {})
	if cards.has("path_length_m"):
		_length_value.text = "%.3f m" % float(cards["path_length_m"])
	else:
		_length_value.text = "—"
	if cards.has("declared_residual") and cards["declared_residual"] != null:
		_residual_value.text = "%.6g" % float(cards["declared_residual"])
	else:
		_residual_value.text = "—"
	var sens_parts: PackedStringArray = []
	if cards.get("sensitivity_norm_endpoint") != null:
		sens_parts.append("end %.6g" % float(cards["sensitivity_norm_endpoint"]))
	if cards.get("sensitivity_norm_peak") != null:
		sens_parts.append("peak %.6g" % float(cards["sensitivity_norm_peak"]))
	_sens_value.text = "  ·  ".join(sens_parts) if not sens_parts.is_empty() else "—"
	_native_value.text = str(cards.get("native_status", "—"))
	var caption := str(_data.get("caption", ""))
	if not caption.is_empty():
		_caption.text = caption
	_draw_path()


func _clear_view() -> void:
	_path_mesh.mesh = null
	_strip_mesh.mesh = null
	_axes.mesh = null
	_marker.visible = false
	_path_points.clear()
	for label in _labels_3d:
		label.queue_free()
	_labels_3d.clear()


func _line_strip(points: PackedVector3Array) -> ImmediateMesh:
	var path := ImmediateMesh.new()
	if points.size() > 1:
		path.surface_begin(Mesh.PRIMITIVE_LINE_STRIP)
		for point in points:
			path.surface_add_vertex(point)
		path.surface_end()
	return path


func _draw_path() -> void:
	_clear_view()
	var low := Vector3(INF, INF, INF)
	var high := Vector3(-INF, -INF, -INF)
	_path_points = PackedVector3Array()
	for value in _data.get("path_polyline", []):
		var point := Vector3(float(value[0]), float(value[1]), float(value[2]))
		_path_points.append(point)
		low = low.min(point)
		high = high.max(point)
	_path_mesh.mesh = _line_strip(_path_points)

	var strip_points := PackedVector3Array()
	for value in _data.get("sensitivity_strip", []):
		var point := Vector3(float(value[0]), float(value[1]), float(value[2]))
		strip_points.append(point)
		low = low.min(point)
		high = high.max(point)
	# Closed ribbon outline: path → strip reversed → close
	var ribbon := ImmediateMesh.new()
	if _path_points.size() > 1 and strip_points.size() == _path_points.size():
		ribbon.surface_begin(Mesh.PRIMITIVE_LINE_STRIP)
		for point in _path_points:
			ribbon.surface_add_vertex(point)
		for index in range(strip_points.size() - 1, -1, -1):
			ribbon.surface_add_vertex(strip_points[index])
		ribbon.surface_add_vertex(_path_points[0])
		ribbon.surface_end()
		# Also draw the strip midline
		ribbon.surface_begin(Mesh.PRIMITIVE_LINE_STRIP)
		for point in strip_points:
			ribbon.surface_add_vertex(point)
		ribbon.surface_end()
	_strip_mesh.mesh = ribbon

	if not _path_points.is_empty():
		_center = (low + high) * 0.5
		_base_radius = maxf((high - low).length() * 1.2, 2.0)
		_radius = _base_radius
		var sphere := SphereMesh.new()
		sphere.radius = _base_radius * 0.012
		sphere.height = sphere.radius * 2.0
		_marker.mesh = sphere
		_marker.position = _path_points[_path_points.size() - 1]
		_marker.visible = true
		_build_axes(low, high, ["x", "sens", "z"])
		_update_camera()
	_set_stale(_stale)


func _build_axes(low: Vector3, high: Vector3, labels: Array) -> void:
	var axis_mesh := ImmediateMesh.new()
	axis_mesh.surface_begin(Mesh.PRIMITIVE_LINES)
	var corners := [Vector3(high.x, low.y, low.z), Vector3(low.x, high.y, low.z), Vector3(low.x, low.y, high.z)]
	for index in range(3):
		axis_mesh.surface_add_vertex(low)
		axis_mesh.surface_add_vertex(corners[index])
		var label := Label3D.new()
		label.text = str(labels[index]) if index < labels.size() else ""
		label.font_size = 24
		label.pixel_size = _base_radius * 0.0012
		label.modulate = LABEL_C
		label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		label.position = corners[index]
		_world.add_child(label)
		_labels_3d.append(label)
	axis_mesh.surface_end()
	_axes.mesh = axis_mesh


func _update_camera() -> void:
	_camera.position = _center + Vector3(sin(_yaw) * cos(_pitch), sin(_pitch), cos(_yaw) * cos(_pitch)) * _radius
	_camera.look_at(_center, Vector3.UP)


func _on_viewport_input(event: InputEvent) -> void:
	if _stale:
		return
	if event is InputEventMouseMotion and (event.button_mask & MOUSE_BUTTON_MASK_LEFT or event.button_mask & MOUSE_BUTTON_MASK_RIGHT):
		_yaw -= event.relative.x * 0.008
		_pitch = clampf(_pitch + event.relative.y * 0.006, -0.1, 1.45)
		_update_camera()
		accept_event()
	elif event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP:
			_radius = maxf(_radius * 0.9, _base_radius * 0.3)
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			_radius = minf(_radius * 1.1, _base_radius * 4.0)
		else:
			return
		_update_camera()
		accept_event()
