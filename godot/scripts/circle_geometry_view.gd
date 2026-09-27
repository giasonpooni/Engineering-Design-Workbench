extends VBoxContainer
## Circle geometry tab: local HOST GTE circle eligibility render JSON only.
## Reuses ciw.geometric-circle.v1 presentation — no new CIW kind. No second solver.
const Kit = preload("res://scripts/presentation_kit.gd")
const Schematic = preload("res://scripts/presentation_schematic.gd")
const Strip = preload("res://scripts/presentation_strip.gd")

const DEFAULT_RELATIVE := "../examples/gte-circle-eligibility/results/gte_circle_render.json"
const MATCH_NAME := "gte_circle_render.json"
const CIRCLE_CAPTION := (
	"No surveyed frame / physical accuracy / BIM acceptance. "
	+ "Declared frame bench-plane only; presentation of retained teaching values."
)

var _schematic = Schematic.new()
var _strip = Strip.new()
var _canvas: Control
var _status: Label
var _path_label: Label
var _caption: Label
var _outcome_value: Label
var _residual_value: Label
var _policy_value: Label
var _reason_value: Label
var _case_label: Label
var _case_option: OptionButton
var _reload: Button
var _verify_label: Label
var _data: Dictionary = {}
var _loaded := false
var _loaded_path := ""
var _case_index := 0
var _draw_points: Array = []
var _draw_center: Vector2 = Vector2.ZERO
var _draw_radius := 1.0
var _draw_stale := true


func _ready() -> void:
	add_theme_constant_override("separation", 12)
	_build_ui()
	_try_load()


func _build_ui() -> void:
	var header := HBoxContainer.new()
	header.add_theme_constant_override("separation", 12)
	add_child(header)
	var titles := VBoxContainer.new()
	titles.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(titles)
	titles.add_child(Kit.make_label("CIRCLE GEOMETRY  /  GTE", 12, Kit.TEAL))
	titles.add_child(Kit.make_label("Eligibility teaching presentation", 20))
	titles.add_child(Kit.make_label("ciw.geometric-circle.v1 · local file · no second solver", 12, Kit.MUTED))
	var actions := HBoxContainer.new()
	header.add_child(actions)
	_status = Kit.make_label("●  WAITING", 13, Kit.AMBER)
	_status.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	actions.add_child(_status)
	_reload = Button.new()
	_reload.text = "Reload"
	_reload.pressed.connect(_try_load)
	actions.add_child(_reload)

	_path_label = Kit.make_label("render path —", 11, Kit.MUTED)
	_path_label.clip_text = true
	add_child(_path_label)

	var panels := HBoxContainer.new()
	panels.add_theme_constant_override("separation", 14)
	panels.size_flags_vertical = Control.SIZE_EXPAND_FILL
	add_child(panels)

	var plot_card := Kit.panel()
	plot_card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	plot_card.size_flags_vertical = Control.SIZE_EXPAND_FILL
	panels.add_child(plot_card)
	var plot_column := VBoxContainer.new()
	plot_card.add_child(plot_column)
	plot_column.add_child(Kit.make_label("01   PROJECTED POINTS", 12, Kit.TEAL))
	plot_column.add_child(Kit.make_label("Observed · projected · unit circle", 18))
	_canvas = Control.new()
	_canvas.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_canvas.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_canvas.custom_minimum_size = Vector2(280, 200)
	_canvas.draw.connect(_draw_circle_canvas)
	plot_column.add_child(_canvas)
	plot_column.add_child(Kit.make_label("HOST schematic · no surveyed frame", 11, Kit.MUTED))

	var strip_card := Kit.panel()
	strip_card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	strip_card.size_flags_vertical = Control.SIZE_EXPAND_FILL
	panels.add_child(strip_card)
	var strip_column := VBoxContainer.new()
	strip_card.add_child(strip_column)
	strip_column.add_child(Kit.make_label("02   RADIAL RESIDUAL STRIP", 12, Kit.TEAL))
	strip_column.add_child(Kit.make_label("Case residual magnitudes", 18))
	_strip.size_flags_vertical = Control.SIZE_EXPAND_FILL
	strip_column.add_child(_strip)
	_case_option = OptionButton.new()
	_case_option.item_selected.connect(_on_case_selected)
	strip_column.add_child(_case_option)
	_case_label = Kit.make_label("case —", 12, Kit.MUTED)
	_case_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	strip_column.add_child(_case_label)

	# Keep schematic available for residual bar wash (optional secondary cue).
	_schematic.visible = false
	add_child(_schematic)

	var cards := HBoxContainer.new()
	cards.add_theme_constant_override("separation", 12)
	add_child(cards)
	var outcome := Kit.make_card("OUTCOME")
	cards.add_child(outcome["card"])
	_outcome_value = outcome["value"]
	var residual := Kit.make_card("RADIAL |r|")
	cards.add_child(residual["card"])
	_residual_value = residual["value"]
	var policy := Kit.make_card("POLICY max_corr")
	cards.add_child(policy["card"])
	_policy_value = policy["value"]
	var reason := Kit.make_card("REASON")
	cards.add_child(reason["card"])
	_reason_value = reason["value"]

	_caption = Kit.make_label(CIRCLE_CAPTION, 11, Kit.MUTED)
	_caption.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	add_child(_caption)

	var footer := HBoxContainer.new()
	add_child(footer)
	var authority := Kit.make_label(
		"HOST GTE FIXTURES → CARDS     •     POINTS / STRIP → PRESENTATION     •     " + Kit.CAPTION,
		10,
		Kit.MUTED
	)
	authority.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	footer.add_child(authority)
	_verify_label = Kit.make_label("VERIFICATION  /  NOT CLAIMED", 10, Kit.AMBER)
	footer.add_child(_verify_label)
	_set_interaction(false)


func _try_load() -> void:
	var path := Kit.resolve_render_path(DEFAULT_RELATIVE, MATCH_NAME)
	_loaded_path = path
	_path_label.text = "render path  " + path
	_path_label.tooltip_text = path
	var parsed := Kit.load_json(path)
	if parsed.is_empty():
		_data.clear()
		_loaded = false
		_strip.clear_view()
		_draw_points.clear()
		_draw_stale = true
		_canvas.queue_redraw()
		_apply_stale("STALE", "gte_circle_render.json missing — generate with examples/gte-circle-eligibility/run_or_emit.py")
		return
	_data = parsed
	_loaded = true
	_case_index = int(_data.get("selected_case_index", 0))
	_rebuild_case_options()
	_status.text = "●  LOADED"
	_status.add_theme_color_override("font_color", Kit.TEAL)
	_set_interaction(true)
	_strip.set_stale(false)
	_draw_stale = false
	_verify_label.text = Kit.verification_label(_data)
	_verify_label.add_theme_color_override(
		"font_color", Kit.TEAL if bool(_data.get("fresh_verifier_occurrence", false)) else Kit.AMBER
	)
	_refresh()


func _rebuild_case_options() -> void:
	_case_option.clear()
	var cases: Array = _data.get("cases", [])
	for index in range(cases.size()):
		var entry: Dictionary = cases[index]
		_case_option.add_item(
			"%s  /  %s" % [str(entry.get("status", "?")), str(entry.get("label", entry.get("id", index)))],
			index
		)
	if _case_index < 0 or _case_index >= cases.size():
		_case_index = 0
	if cases.size() > 0:
		_case_option.select(_case_index)


func _apply_stale(state: String, detail: String) -> void:
	_status.text = "●  " + Kit.format_status_label(state)
	_status.add_theme_color_override("font_color", Kit.status_color(state))
	_path_label.text = detail if _loaded_path.is_empty() else (_loaded_path + "  ·  " + detail)
	_outcome_value.text = "STALE"
	_residual_value.text = "—"
	_policy_value.text = "—"
	_reason_value.text = "—"
	_case_label.text = "case —"
	_set_interaction(false)
	_strip.set_stale(true)
	_draw_stale = true
	_canvas.queue_redraw()
	Kit.apply_stale([_case_option], true)


func _set_interaction(enabled: bool) -> void:
	_case_option.disabled = not enabled
	Kit.apply_stale([_case_option], not enabled)


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
	var card_status := str(case_data.get("status", "STALE"))
	_case_label.text = "%s\n%s · %s" % [
		str(case_data.get("label", case_data.get("id", ""))),
		Kit.format_status_label(card_status),
		str(case_data.get("reason", "")),
	]
	_status.text = "●  " + Kit.format_status_label(card_status)
	_status.add_theme_color_override("font_color", Kit.status_color(card_status))
	_outcome_value.text = Kit.format_status_label(str(case_data.get("native_outcome", card_status)).to_upper())
	_outcome_value.add_theme_color_override("font_color", Kit.status_color(card_status))
	var residuals: Array = case_data.get("radial_residuals_m", [])
	var parts: PackedStringArray = []
	for item in residuals:
		if item is float or item is int:
			parts.append("%.4f" % absf(float(item)))
		else:
			parts.append(str(item))
	_residual_value.text = "  ".join(parts) if not parts.is_empty() else "—"
	var policy: Dictionary = case_data.get("policy", {})
	_policy_value.text = str(policy.get("max_correction_m", "—"))
	_reason_value.text = str(case_data.get("reason", "—"))
	var caption := str(_data.get("caption", ""))
	_caption.text = caption if not caption.is_empty() else CIRCLE_CAPTION

	# Strip: residual series across cases
	var series: Array = _data.get("residual_series", [])
	_strip.set_series(series, "index", PackedStringArray(["radial_abs_m"]))
	_strip.set_selected_x(float(_case_index))
	_strip.set_stale(false)

	# Circle canvas points
	var constraint: Dictionary = case_data.get("constraint", {})
	var center: Array = constraint.get("center_m", [0.0, 0.0])
	_draw_center = Vector2(float(center[0]), float(center[1]) if center.size() > 1 else 0.0)
	_draw_radius = float(constraint.get("radius_m", 1.0))
	_draw_points = case_data.get("points", [])
	_draw_stale = false
	_canvas.queue_redraw()


func _draw_circle_canvas() -> void:
	var margin := 24.0
	var area := Rect2(margin, margin, _canvas.size.x - margin * 2.0, _canvas.size.y - margin * 2.0)
	_canvas.draw_rect(Rect2(Vector2.ZERO, _canvas.size), Kit.BG, true)
	_canvas.draw_rect(area, Kit.PANEL, true)
	if _draw_stale or _draw_points.is_empty():
		_canvas.draw_string(ThemeDB.fallback_font, area.position + Vector2(8, 20), "NO CIRCLE DATA", HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Kit.MUTED)
		return
	var scale := minf(area.size.x, area.size.y) * 0.38 / maxf(_draw_radius, 1e-6)
	var origin := area.get_center()
	# Axes
	_canvas.draw_line(Vector2(area.position.x, origin.y), Vector2(area.position.x + area.size.x, origin.y), Kit.AXIS, 1.0)
	_canvas.draw_line(Vector2(origin.x, area.position.y), Vector2(origin.x, area.position.y + area.size.y), Kit.AXIS, 1.0)
	# Circle
	var circle_color := Kit.STEEL if _draw_stale else Kit.WASH
	_canvas.draw_arc(origin, _draw_radius * scale, 0.0, TAU, 64, circle_color, 2.0, true)
	for point in _draw_points:
		var obs: Array = point.get("observed_m", [0.0, 0.0])
		var obs_p := origin + Vector2(float(obs[0]) - _draw_center.x, -float(obs[1]) + _draw_center.y) * scale
		_canvas.draw_circle(obs_p, 5.0, Kit.AMBER if not _draw_stale else Kit.STEEL)
		var proj = point.get("projected_m", null)
		if proj != null and proj is Array and (proj as Array).size() >= 2:
			var proj_p := origin + Vector2(float(proj[0]) - _draw_center.x, -float(proj[1]) + _draw_center.y) * scale
			_canvas.draw_circle(proj_p, 4.0, Kit.TEAL if not _draw_stale else Kit.STEEL)
			_canvas.draw_line(obs_p, proj_p, Kit.LABEL if not _draw_stale else Kit.STEEL, 1.0)
		elif bool(point.get("singular", false)):
			_canvas.draw_circle(obs_p, 7.0, Color("e57373"))
	_canvas.draw_string(ThemeDB.fallback_font, area.position + Vector2(4, 14), "obs=amber  proj=teal", HORIZONTAL_ALIGNMENT_LEFT, -1, 10, Kit.MUTED)
