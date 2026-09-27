extends VBoxContainer
const Kit = preload("res://scripts/presentation_kit.gd")
## Fluid balance tab: local HOST FSRT render JSON only. No websocket. Presentation only.
const TEXT := Color("dce6f1")
const MUTED := Color("899cb2")
const TEAL := Color("60dfcd")
const AMBER := Color("ffcc80")
const STEEL := Color("537778")
const AXIS := Color("4e647e")
const LABEL_C := Color("a4b4c8")
const WASH := Color(0.24, 0.42, 0.66, 0.36)
const DEFAULT_RELATIVE := "../examples/fsrt-two-reservoir/results/fsrt_render.json"
const MATCH_NAME := "fsrt_render.json"

var _render_relative := ""
var _render_match := ""
var _missing_hint := ""
var _chrome_kicker := "FLUID BALANCE  /  FSRT"
var _chrome_title := "Two-reservoir HOST presentation"
var _chrome_sub := "Local file only · no websocket · no fluid-volume op"

var _viewport: SubViewport
var _world: Node3D
var _camera: Camera3D
var _bars: Array[MeshInstance3D] = []
var _originals: Array[MeshInstance3D] = []
var _link: MeshInstance3D
var _axes: MeshInstance3D
var _marker: MeshInstance3D
var _labels_3d: Array[Label3D] = []
var _status: Label
var _path_label: Label
var _caption: Label
var _case_label: Label
var _guard_value: Label
var _residual_value: Label
var _mass_value: Label
var _case_option: OptionButton
var _reload: Button
var _data: Dictionary = {}
var _loaded := false
var _loaded_path := ""
var _case_index := 0
var _stale := true
var _center := Vector3.ZERO
var _radius := 4.0
var _base_radius := 4.0
var _yaw := 0.55
var _pitch := 0.35


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

	var schematic_card := _panel()
	schematic_card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	schematic_card.size_flags_vertical = Control.SIZE_EXPAND_FILL
	panels.add_child(schematic_card)
	var schematic_column := VBoxContainer.new()
	schematic_card.add_child(schematic_column)
	schematic_column.add_child(_label("01   TWO-NODE SCHEMATIC", 12, TEAL))
	schematic_column.add_child(_label("Tank level bars · residual · guard", 18))
	var host := SubViewportContainer.new()
	host.stretch = true
	host.custom_minimum_size = Vector2(300, 270)
	host.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	host.size_flags_vertical = Control.SIZE_EXPAND_FILL
	host.gui_input.connect(_on_viewport_input)
	schematic_column.add_child(host)
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
	_link = MeshInstance3D.new()
	_axes = MeshInstance3D.new()
	_marker = MeshInstance3D.new()
	for item in [_link, _axes, _marker]:
		_world.add_child(item)
	_link.material_override = _material(AXIS)
	_axes.material_override = _material(AXIS)
	_marker.material_override = _material(Color("ffcc80"))
	_marker.visible = false
	schematic_column.add_child(_label("HOST schematic · drag to orbit / wheel to zoom", 11, MUTED))

	var detail_card := _panel()
	detail_card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	detail_card.size_flags_vertical = Control.SIZE_EXPAND_FILL
	panels.add_child(detail_card)
	var detail_column := VBoxContainer.new()
	detail_card.add_child(detail_column)
	detail_column.add_child(_label("02   CASE / GUARD", 12, TEAL))
	detail_column.add_child(_label("Reconcile vs hold", 18))
	_case_option = OptionButton.new()
	_case_option.item_selected.connect(_on_case_selected)
	detail_column.add_child(_case_option)
	_case_label = _label("case —", 12, MUTED)
	_case_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	detail_column.add_child(_case_label)
	var spacer := Control.new()
	spacer.size_flags_vertical = Control.SIZE_EXPAND_FILL
	detail_column.add_child(spacer)
	detail_column.add_child(_label(
		"Originals stay visible when reconciled. Held keeps the unprojected estimate.",
		11,
		MUTED
	))

	var cards := HBoxContainer.new()
	cards.add_theme_constant_override("separation", 12)
	add_child(cards)
	_guard_value = _add_card(cards, "GUARD STATUS")
	_residual_value = _add_card(cards, "RESIDUAL |balance|")
	_mass_value = _add_card(cards, "DISPLAY MASSES")

	_caption = _label(
		"disagreement is not unique fault attribution. Numbers from host FSRT JSON only; STALE if missing.",
		11,
		MUTED
	)
	_caption.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	add_child(_caption)

	var footer := HBoxContainer.new()
	add_child(footer)
	var authority := _label(
		"HOST FSRT JSON → CARDS     •     SCHEMATIC → PRESENTATION     •     " + Kit.CAPTION,
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
	## Call before add_child so _ready uses use-case path/chrome.
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
		_clear_schematic()
		var hint := _missing_hint if not _missing_hint.is_empty() else "fsrt_render.json missing — generate with examples/fsrt-two-reservoir/emit_render.py"
		_apply_stale("STALE", hint)
		return
	_data = parsed
	_loaded = true
	_case_index = int(_data.get("selected_case_index", 0))
	_rebuild_case_options()
	_status.text = "●  LOADED"
	_status.add_theme_color_override("font_color", Kit.status_color("LIVE"))
	_set_interaction(true)
	_set_stale(false)
	_refresh()


func _rebuild_case_options() -> void:
	_case_option.clear()
	var cases: Array = _data.get("cases", [])
	for index in range(cases.size()):
		var entry: Dictionary = cases[index]
		_case_option.add_item("%s  /  %s" % [str(entry.get("guard_status", "?")), str(entry.get("label", entry.get("id", index)))], index)
	if _case_index < 0 or _case_index >= cases.size():
		_case_index = 0
	if cases.size() > 0:
		_case_option.select(_case_index)


func _apply_stale(state: String, detail: String) -> void:
	_status.text = "●  " + Kit.format_status_label(state)
	_status.add_theme_color_override("font_color", Kit.status_color(state))
	_path_label.text = detail if _loaded_path.is_empty() else (_loaded_path + "  ·  " + detail)
	_guard_value.text = "STALE"
	_residual_value.text = "—"
	_mass_value.text = "—"
	_case_label.text = "case —"
	_set_interaction(false)
	_set_stale(true)


func _set_interaction(enabled: bool) -> void:
	_case_option.disabled = not enabled


func _set_stale(value: bool) -> void:
	_stale = value
	var color := STEEL if value else TEAL
	for bar in _bars:
		bar.material_override = _material(color)
	for bar in _originals:
		bar.material_override = _material(WASH if not value else STEEL, true)


func _on_case_selected(index: int) -> void:
	_case_index = index
	_refresh()


func _current_case() -> Dictionary:
	var cases: Array = _data.get("cases", [])
	if _case_index >= 0 and _case_index < cases.size():
		return cases[_case_index]
	return {}


func _refresh() -> void:
	if not _loaded:
		_apply_stale("STALE", "no render data")
		return
	var case_data := _current_case()
	if case_data.is_empty():
		_apply_stale("STALE", "no cases in render JSON")
		return
	_case_label.text = "%s\n%s · %s" % [
		str(case_data.get("label", case_data.get("id", ""))),
		str(case_data.get("physical_model_status", "")),
		str(case_data.get("reconciliation_status", "")),
	]
	_guard_value.text = str(case_data.get("guard_status", "—")).to_upper()
	var residuals: Dictionary = case_data.get("residuals", {})
	if residuals.has("residual_size_kg"):
		_residual_value.text = "%.3f kg" % float(residuals["residual_size_kg"])
	else:
		_residual_value.text = "—"
	var tanks: Array = case_data.get("tanks", [])
	var parts: PackedStringArray = []
	for tank in tanks:
		parts.append("%s=%.2f" % [str(tank.get("name", "?")), float(tank.get("display_kg", 0.0))])
	_mass_value.text = "  ".join(parts) if not parts.is_empty() else "—"
	var caption := str(_data.get("caption", ""))
	if not caption.is_empty():
		_caption.text = caption
	_draw_schematic(case_data)


func _clear_schematic() -> void:
	for bar in _bars:
		bar.queue_free()
	_bars.clear()
	for bar in _originals:
		bar.queue_free()
	_originals.clear()
	for label in _labels_3d:
		label.queue_free()
	_labels_3d.clear()
	_link.mesh = null
	_axes.mesh = null
	_marker.visible = false


func _draw_schematic(case_data: Dictionary) -> void:
	_clear_schematic()
	var tanks: Array = case_data.get("tanks", [])
	var schematic: Dictionary = _data.get("schematic", {})
	var positions: Array = schematic.get("node_positions", [[-1.2, 0.0, 0.0], [1.2, 0.0, 0.0]])
	var max_kg := float(schematic.get("max_bar_kg", 100.0))
	var low := Vector3(INF, INF, INF)
	var high := Vector3(-INF, -INF, -INF)
	var link_mesh := ImmediateMesh.new()
	if positions.size() >= 2:
		link_mesh.surface_begin(Mesh.PRIMITIVE_LINES)
		var a := _vec(positions[0])
		var b := _vec(positions[1])
		link_mesh.surface_add_vertex(a)
		link_mesh.surface_add_vertex(b)
		link_mesh.surface_end()
	_link.mesh = link_mesh

	for index in range(tanks.size()):
		var tank: Dictionary = tanks[index]
		var base := _vec(positions[index] if index < positions.size() else [float(index) * 2.0 - 1.0, 0.0, 0.0])
		var display := float(tank.get("display_kg", 0.0))
		var original := float(tank.get("original_kg", display))
		var height := clampf(display / max_kg, 0.02, 1.4) * 2.0
		var original_height := clampf(original / max_kg, 0.02, 1.4) * 2.0

		var original_box := BoxMesh.new()
		original_box.size = Vector3(0.55, original_height, 0.55)
		var original_mesh := MeshInstance3D.new()
		original_mesh.mesh = original_box
		original_mesh.position = base + Vector3(0.0, original_height * 0.5, 0.0)
		original_mesh.material_override = _material(WASH, true)
		_world.add_child(original_mesh)
		_originals.append(original_mesh)

		var box := BoxMesh.new()
		box.size = Vector3(0.35, height, 0.35)
		var mesh_i := MeshInstance3D.new()
		mesh_i.mesh = box
		mesh_i.position = base + Vector3(0.0, height * 0.5, 0.0)
		mesh_i.material_override = _material(TEAL if not _stale else STEEL)
		_world.add_child(mesh_i)
		_bars.append(mesh_i)

		var label := Label3D.new()
		label.text = str(tank.get("name", "tank"))
		label.font_size = 28
		label.pixel_size = 0.004
		label.modulate = LABEL_C
		label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		label.position = base + Vector3(0.0, maxf(height, original_height) + 0.25, 0.0)
		_world.add_child(label)
		_labels_3d.append(label)

		low = low.min(base + Vector3(-0.4, 0.0, -0.4))
		high = high.max(base + Vector3(0.4, maxf(height, original_height) + 0.4, 0.4))

	var residual := float(case_data.get("residuals", {}).get("residual_size_kg", 0.0))
	var sphere := SphereMesh.new()
	sphere.radius = 0.08 + minf(residual / 80.0, 0.25)
	sphere.height = sphere.radius * 2.0
	_marker.mesh = sphere
	_marker.position = Vector3(0.0, 0.15, 0.0)
	_marker.visible = true

	if low.x < high.x:
		_center = (low + high) * 0.5
		_base_radius = maxf((high - low).length() * 1.15, 2.5)
		_radius = _base_radius
		_build_axes(low, high, schematic.get("axis_labels", ["tank-1", "level", "tank-2"]))
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


func _vec(value: Array) -> Vector3:
	return Vector3(float(value[0]), float(value[1]), float(value[2]))


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
