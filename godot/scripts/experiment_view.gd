extends VBoxContainer
## One selected bundle drives all panels. Selection is local presentation state.
const Plot = preload("res://scripts/experiment_plot.gd")
const SystemsView = preload("res://scripts/energy_view.gd")
var client
var selected_bundle := ""
var selected_result := ""
var view: Dictionary = {}
var _session_id := ""
var _revision := -1
var _bundle_ids: Array[String] = []
var _catalog: ItemList
var _follow: CheckBox
var _summary: Label
var _status: Label
var _panels: OptionButton
var _plot = Plot.new()
var _system_plot = Plot.new()
var _canvases: OptionButton
var _system = SystemsView.new()
var _numbers: TextEdit
var _graph: Tree
var _inspector: TextEdit
var _capabilities: TextEdit


func _ready() -> void:
	add_theme_constant_override("separation", 12)
	var heading := HBoxContainer.new()
	add_child(heading)
	var title := Label.new()
	title.text = "WORKBENCH  /  experiments, schematics and computation"
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	heading.add_child(title)
	_follow = CheckBox.new()
	_follow.text = "Follow new results"
	_follow.button_pressed = true
	heading.add_child(_follow)
	_status = Label.new()
	_status.text = "Waiting for the service"
	add_child(_status)
	_summary = Label.new()
	_summary.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_summary.text = "Run a shared workbench example to populate this view."
	add_child(_summary)
	var body := HSplitContainer.new()
	body.size_flags_vertical = Control.SIZE_EXPAND_FILL
	add_child(body)
	var sidebar := VBoxContainer.new()
	sidebar.custom_minimum_size.x = 250
	body.add_child(sidebar)
	sidebar.add_child(_label("RETAINED OCCURRENCES"))
	_catalog = ItemList.new()
	_catalog.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_catalog.custom_minimum_size.y = 180
	_catalog.item_selected.connect(func(index: int):
		_follow.button_pressed = false
		_select_bundle(_bundle_ids[index]))
	sidebar.add_child(_catalog)
	sidebar.add_child(_label("SOURCES & BOUND OPERATIONS"))
	_capabilities = _text_box()
	_capabilities.size_flags_vertical = Control.SIZE_EXPAND_FILL
	sidebar.add_child(_capabilities)
	var content := HSplitContainer.new()
	body.add_child(content)
	var scientific := VBoxContainer.new()
	scientific.custom_minimum_size.x = 410
	scientific.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	content.add_child(scientific)
	_panels = OptionButton.new()
	_panels.item_selected.connect(_select_panel)
	scientific.add_child(_panels)
	_plot.custom_minimum_size.y = 220
	_plot.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scientific.add_child(_plot)
	_canvases = OptionButton.new()
	_canvases.visible = false
	_canvases.item_selected.connect(func(_index: int):
		_draw_system_canvas())
	scientific.add_child(_canvases)
	_system_plot.custom_minimum_size.y = 180
	_system_plot.visible = false
	scientific.add_child(_system_plot)
	_system.custom_minimum_size.y = 220
	_system.visible = false
	scientific.add_child(_system)
	_numbers = _text_box()
	_numbers.custom_minimum_size.y = 88
	scientific.add_child(_numbers)
	scientific.add_child(_label("INSTRUMENT DEPENDENCIES  /  select a result"))
	_graph = Tree.new()
	_graph.hide_root = true
	_graph.custom_minimum_size.y = 110
	_graph.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_graph.item_selected.connect(_select_node)
	scientific.add_child(_graph)
	var evidence := VBoxContainer.new()
	evidence.custom_minimum_size.x = 310
	content.add_child(evidence)
	var actions := HBoxContainer.new()
	evidence.add_child(actions)
	for entry in [["Context", "fusion_context"], ["Raw", "raw_observations"], ["Verification", "verification"]]:
		var button := Button.new()
		button.text = entry[0]
		var field: String = entry[1]
		button.pressed.connect(func():
			selected_result = ""
			client.inspect_artifact("")
			if field == "fusion_context" and view.get("fusion_context") == null:
				_show_json(view.get("object_context", {}))
			elif field == "raw_observations" and view.has("raw_declaration"):
				_show_json(view.raw_declaration)
			else:
				_show_json(view.get(field, {})))
		actions.add_child(button)
	_inspector = _text_box()
	_inspector.size_flags_vertical = Control.SIZE_EXPAND_FILL
	evidence.add_child(_inspector)
	var footer := _label("Read-only retained values · plots preserve separate occurrences · inspection does not replay or admit state")
	footer.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	add_child(footer)


func _label(value: String) -> Label:
	var label := Label.new()
	label.text = value
	label.add_theme_font_size_override("font_size", 12)
	return label


func _text_box() -> TextEdit:
	var box := TextEdit.new()
	box.editable = false
	box.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	box.add_theme_font_size_override("font_size", 12)
	box.add_theme_color_override("font_readonly_color", Color("c4d0df"))
	return box


func attach(value) -> void:
	client = value
	client.snapshot_received.connect(apply_snapshot)
	client.experiment_received.connect(apply_view)
	client.artifact_received.connect(func(artifact: Dictionary):
		if not selected_result.is_empty():
			_show_json(artifact))
	client.status_changed.connect(func(state: String, _detail: String):
		_status.text = ("LIVE SESSION" if state == "ready" else "STALE / " + state.to_upper()) + " · catalog revision %s" % _revision)


func apply_snapshot(snapshot: Dictionary) -> void:
	var new_session := str(snapshot.get("session_id", ""))
	var catalog: Dictionary = snapshot.get("workbench", {})
	var revision := int(catalog.get("revision", 0))
	var changed_session := new_session != _session_id
	if not changed_session and revision <= _revision:
		if view.is_empty() and not selected_bundle.is_empty():
			client.inspect_experiment(selected_bundle)
		return
	if changed_session:
		selected_bundle = ""
		selected_result = ""
		view.clear()
		_plot.set_panel({})
		_system_plot.set_panel({})
		_system_plot.visible = false
		if _canvases != null:
			_canvases.clear()
			_canvases.visible = false
		if _system != null:
			_system.set_system({})
		_panels.clear()
		_graph.clear()
		_numbers.text = ""
		_inspector.text = ""
		_summary.text = "Select a retained occurrence."
		client.inspect_artifact("")
		client.inspect_experiment("")
	_session_id = new_session
	_revision = revision
	_catalog.clear()
	_bundle_ids.clear()
	for bundle in catalog.get("bundles", []):
		_bundle_ids.append(str(bundle.bundle_id))
		_catalog.add_item("%02d  %s" % [_bundle_ids.size(), bundle.kind])
		_catalog.set_item_tooltip(_bundle_ids.size() - 1, str(bundle.bundle_id))
	var lines: Array[String] = []
	for source in catalog.get("sources", []):
		lines.append("SOURCE · %s\n%s\n" % [source.kind, source.label])
	for operation in catalog.get("operations", []):
		lines.append("%s · %s" % ["BOUND" if operation.available else "UNAVAILABLE", operation.operation_id])
	_capabilities.text = "\n".join(lines)
	if not _bundle_ids.is_empty():
		if selected_bundle.is_empty() or _follow.button_pressed:
			_select_bundle(_bundle_ids[-1])
		else:
			_catalog.select(_bundle_ids.find(selected_bundle))
	_status.text = ("LIVE SESSION" if client.online else "STALE") + " · catalog revision %s" % _revision


func _select_bundle(bundle_id: String) -> void:
	if selected_bundle == bundle_id and not view.is_empty():
		_catalog.select(_bundle_ids.find(bundle_id))
		return
	selected_bundle = bundle_id
	selected_result = ""
	view.clear()
	_plot.set_panel({})
	_system_plot.set_panel({})
	_system_plot.visible = false
	if _canvases != null:
		_canvases.clear()
		_canvases.visible = false
	if _system != null:
		_system.set_system({})
	_numbers.text = ""
	_panels.clear()
	_graph.clear()
	_inspector.text = ""
	_summary.text = "Loading selected occurrence..."
	_catalog.select(_bundle_ids.find(bundle_id))
	client.inspect_artifact("")
	client.inspect_experiment(bundle_id)


func apply_view(value: Dictionary) -> void:
	if value.get("schema", "") != "ciw.experiment-view.v1" or value.get("bundle_id", "") != selected_bundle:
		return
	view = value
	var context: Dictionary = view.get("object_context", {}) if view.get("fusion_context") == null else view.fusion_context
	if view.get("fusion_context") == null:
		_summary.text = "%s\n%s · %s · fusion: not performed\n%s" % [view.label,
			context.object_kind, context.get("next_step", context.get("summary", "retained native result")), view.bundle_id]
	else:
		_summary.text = "%s\n%s · observability: %s · reconciliation: %s · detection: %s · declared isolability: %s\n%s" % [view.label,
			context.state_kind, context.get("observability", {}).get("status", "unresolved"),
			context.get("reconciliation", {}).get("status", "not_run"),
			context.get("fault_assessment", {}).get("detection", context.get("fault_assessment", {}).get("status", "not_run")),
			context.get("fault_assessment", {}).get("isolability", "not_run"), view.bundle_id]
	_plot.set_panel({})
	_numbers.text = ""
	_panels.clear()
	_fill_system_canvases()
	for panel in view.panels:
		_panels.add_item(panel.title)
	if not view.panels.is_empty():
		_select_panel(0)
	_graph.clear()
	var root := _graph.create_item()
	var roles: Dictionary = {view.evidence_id: "source evidence"}
	for node in view.graph.nodes:
		roles[node.result_id] = node.role.to_upper()
	for node in view.graph.nodes:
		var item := _graph.create_item(root)
		item.set_text(0, node.role.to_upper() + " · " + node.operation_id)
		item.set_metadata(0, node.result_id)
		item.set_tooltip_text(0, node.result_id + "\n" + node.execution_id)
		for reference in node.input_refs:
			var dependency := _graph.create_item(item)
			dependency.set_text(0, "← " + str(roles.get(reference, "external retained input")))
			dependency.set_tooltip_text(0, reference)
			dependency.set_selectable(0, false)
		item.collapsed = true
	if view.get("schematic") != null:
		for node in view.schematic.nodes:
			var item := _graph.create_item(root)
			item.set_text(0, node.id + " · " + node.kind)
			item.set_tooltip_text(0, JSON.stringify(node.attrs))
			item.set_selectable(0, false)
			for edge in view.schematic.edges:
				if edge.src == node.id:
					var link := _graph.create_item(item)
					link.set_text(0, edge.kind + " → " + edge.dst)
					link.set_selectable(0, false)
			item.collapsed = true
	_show_json(context)


func _overlay_phrase(render: Dictionary) -> String:
	var names: Array[String] = []
	for overlay in render.get("overlays", []):
		if typeof(overlay) != TYPE_DICTIONARY:
			continue
		if overlay.get("kind") != "declared_circle" or overlay.get("source") != "declared_constraint":
			continue
		var name := str(overlay.get("overlay_title", overlay.get("constraint_id", "")))
		if not name.is_empty() and names.find(name) < 0:
			names.append(name)
	return " · ".join(names)


func _endpoint_phrase(render: Dictionary) -> String:
	var start := str(render.get("start_label", render.get("source_label", "")))
	var end := str(render.get("end_label", render.get("target_label", "")))
	if start.is_empty() and end.is_empty():
		return ""
	if end.is_empty() or end == start:
		return start
	return start + " → " + end


func _mesh_extent_phrase(render: Dictionary) -> String:
	if str(render.get("kind", "")) != "mesh":
		return ""
	if render.get("declared_planar") == true:
		return "declared_planar"
	if render.get("declared_planar") == false:
		return "first two declared axes"
	return ""


func _declared_frame(render: Dictionary) -> String:
	var frame: Variant = render.get("frame", "")
	if typeof(frame) == TYPE_DICTIONARY:
		return str(frame.get("id", frame.get("frame_id", "")))
	return str(frame)


func _canvas_id_phrase(render: Dictionary) -> String:
	var identity := str(render.get("canvas_id", ""))
	if identity.is_empty() or identity == _declared_frame(render):
		return ""
	return "canvas " + identity


func _identity_extra(render: Dictionary) -> String:
	var bits: Array[String] = []
	var identity := _canvas_id_phrase(render)
	var frame := _frame_phrase(render)
	var declared := _declared_frame(render)
	if not declared.is_empty() and not frame.is_empty() and not frame.contains("frame " + declared):
		frame = frame.replace(declared, "frame " + declared)
	var extent := _mesh_extent_phrase(render)
	if not identity.is_empty():
		bits.append(identity)
	if not frame.is_empty() and bits.find(frame) < 0:
		bits.append(frame)
	if not extent.is_empty() and bits.find(extent) < 0:
		bits.append(extent)
	return " · ".join(bits)


func _frame_phrase(render: Dictionary) -> String:
	var kind := str(render.get("kind", ""))
	if kind == "strip":
		var bits: Array[String] = []
		for key in ["parameter_name", "frame", "parameter_unit"]:
			var value := str(render.get(key, ""))
			if key == "frame":
				value = _declared_frame(render)
			if not value.is_empty() and bits.find(value) < 0:
				bits.append(value)
		return " · ".join(bits)
	if kind == "plane2d":
		var bits: Array[String] = []
		var frame := _declared_frame(render)
		var unit := str(render.get("unit", ""))
		if not frame.is_empty():
			bits.append(frame)
		if not unit.is_empty() and bits.find(unit) < 0:
			bits.append(unit)
		return " · ".join(bits)
	var identity := str(render.get("canvas_id", ""))
	var frame := _declared_frame(render)
	if kind == "mesh":
		return frame
	if not identity.is_empty():
		return identity
	return frame


func _canvas_matches(item: Dictionary) -> bool:
	var identity := str(item.get("id", ""))
	if identity.is_empty():
		return false
	var render: Dictionary = item.get("render", {})
	var offered := str(render.get("canvas_id", ""))
	if not offered.is_empty() and offered != identity:
		return false
	var title := str(item.get("title", identity))
	var claimed := str(render.get("canvas_title", ""))
	if not claimed.is_empty() and claimed != title:
		return false
	return true


func _fill_system_canvases() -> void:
	if _canvases == null:
		return
	_canvases.clear()
	var items: Array = view.get("system_canvases", [])
	var selected := 0
	var default_id := str(view.get("system_canvas_id", ""))
	for i in items.size():
		var item: Dictionary = items[i]
		if not _canvas_matches(item):
			continue
		var title := str(item.get("title", item.get("id", "canvas")))
		var extra := _identity_extra(item.get("render", {}))
		if not extra.is_empty() and title.find(extra) < 0:
			title += " · " + extra
		var ends := _endpoint_phrase(item.get("render", {}))
		if not ends.is_empty():
			title += " · " + ends
		var overlays := _overlay_phrase(item.get("render", {}))
		if not overlays.is_empty():
			title += " · " + overlays
		_canvases.add_item(title)
		_canvases.set_item_metadata(_canvases.item_count - 1, str(item.get("id", "")))
		if str(item.get("id", "")) == default_id:
			selected = _canvases.item_count - 1
	if _canvases.item_count > 0:
		_canvases.select(selected)


func _canvas_render() -> Dictionary:
	var items: Array = view.get("system_canvases", [])
	var identity := ""
	if _canvases != null and _canvases.selected >= 0 and _canvases.selected < _canvases.item_count:
		identity = str(_canvases.get_item_metadata(_canvases.selected))
	for item in items:
		if typeof(item) != TYPE_DICTIONARY:
			continue
		if str(item.get("id", "")) != identity:
			continue
		if _canvas_matches(item):
			return item.get("render", {})
	var fallback: Dictionary = view.get("system_render", {})
	if not identity.is_empty() and str(fallback.get("canvas_id", "")) not in ["", identity]:
		return {}
	return fallback


func _companion_payload(system_render: Dictionary) -> Dictionary:
	if system_render.is_empty():
		return {}
	var payload := {"render": system_render}
	var panel_id := str(system_render.get("canvas_id", ""))
	var title := str(system_render.get("canvas_title", ""))
	if _canvases != null and _canvases.selected >= 0 and _canvases.selected < _canvases.item_count:
		panel_id = str(_canvases.get_item_metadata(_canvases.selected))
		if title.is_empty():
			title = str(_canvases.get_item_text(_canvases.selected))
	var offered := str(system_render.get("canvas_id", ""))
	if not offered.is_empty() and not panel_id.is_empty() and offered != panel_id:
		return {}
	if not panel_id.is_empty():
		payload["panel_id"] = panel_id
	if not title.is_empty():
		payload["title"] = title
	return payload

func _select_panel(index: int) -> void:
	var panel: Dictionary = view.panels[index]
	_plot.set_panel(panel)
	var panel_render: Dictionary = panel.get("render", {})
	var panel_kind := str(panel_render.get("kind", ""))
	var system_render: Dictionary = _canvas_render()
	if system_render.is_empty():
		system_render = view.get("system_render", {})
	var system_kind := str(system_render.get("kind", ""))
	var expected_id := str(view.get("system_canvas_id", ""))
	if panel_kind == "mesh":
		_system.set_system(panel_render, expected_id)
	else:
		_system.set_system(system_render if system_kind == "mesh" else {}, expected_id)
	var show_companion := system_kind in ["plane2d", "strip"] and panel_kind != system_kind
	_system_plot.visible = show_companion
	if _canvases != null:
		_canvases.visible = show_companion and _canvases.item_count > 1
	if show_companion:
		_system_plot.set_panel(_companion_payload(system_render))
	else:
		_system_plot.set_panel({})
	var rows: Array[String] = []
	for i in panel.values.size():
		rows.append("%s = %s %s" % [panel.labels[i], JSON.stringify(panel.values[i]), panel.units[i]])
	rows.append("Full covariance: " + JSON.stringify(panel.covariance))
	if panel.has("render"):
		rows.append("Presentation render: " + str(panel.render.get("kind", "")) + " · " + str(panel.render.get("note", panel.render.get("projection", "display only"))))
		var panel_ends := _endpoint_phrase(panel.render)
		if not panel_ends.is_empty():
			var panel_row := "Panel vertices" if str(panel.render.get("kind", "")) == "mesh" else "Panel endpoints"
			var panel_extra := _identity_extra(panel.render)
			rows.append(panel_row + ": " + panel_ends + (" · " + panel_extra if not panel_extra.is_empty() else "") + " · display only")
		var panel_overlays := _overlay_phrase(panel.render)
		if not panel_overlays.is_empty():
			rows.append("Panel constraint: " + panel_overlays + " · declared_constraint · display only")
	if view.get("system_render") != null:
		var canvas_id := str(system_render.get("canvas_id", view.get("system_canvas_id", "")))
		if _canvases != null and _canvases.visible and _canvases.selected >= 0 and _canvases.selected < _canvases.item_count:
			var selected_id := str(_canvases.get_item_metadata(_canvases.selected))
			if not selected_id.is_empty():
				canvas_id = selected_id
		rows.append("View system canvas: " + system_kind + (" · " + canvas_id if not canvas_id.is_empty() else "") + " · display only")
		var companion_ends := _endpoint_phrase(system_render)
		if not companion_ends.is_empty():
			var row_name := "Companion vertices" if system_kind == "mesh" else "Companion endpoints"
			var companion_extra := _identity_extra(system_render)
			rows.append(row_name + ": " + companion_ends + (" · " + companion_extra if not companion_extra.is_empty() else "") + " · display only")
		var companion_overlays := _overlay_phrase(system_render)
		if not companion_overlays.is_empty():
			rows.append("Companion constraint: " + companion_overlays + " · declared_constraint · display only")
	rows.append("Basis: " + JSON.stringify(panel.context))
	rows.append("Source: " + JSON.stringify(panel.provenance))
	_numbers.text = "\n".join(rows)


func _draw_system_canvas() -> void:
	if view.is_empty() or _panels == null or _panels.selected < 0:
		return
	_select_panel(_panels.selected)


func _select_node() -> void:
	var item := _graph.get_selected()
	if item == null or item.get_metadata(0) == null:
		return
	selected_result = str(item.get_metadata(0))
	_inspector.text = "Loading retained result..."
	client.inspect_artifact(selected_result)


func _show_json(value: Variant) -> void:
	_inspector.text = JSON.stringify(value, "  ")
