extends VBoxContainer
## Stability verdict tab: local HOST identified-stability / PLSR render JSON only.
## Reuses ciw.identified-stability.v1 — no new CIW kind. Presentation only.
const Kit = preload("res://scripts/presentation_kit.gd")

const DEFAULT_RELATIVE := "../examples/plsr-stability-verdict/results/plsr_stability_render.json"
const MATCH_NAME := "plsr_stability_render.json"
const STABILITY_CAPTION := (
	"Does not certify the requested inequality; parameter covariance unknown; "
	+ "not physical equilibrium. Proof status NOT_CHECKED."
)

var _canvas: Control
var _status: Label
var _path_label: Label
var _caption: Label
var _verdict_value: Label
var _quadratic_value: Label
var _margin_value: Label
var _proof_value: Label
var _case_label: Label
var _case_option: OptionButton
var _reload: Button
var _verify_label: Label
var _data: Dictionary = {}
var _loaded := false
var _loaded_path := ""
var _case_index := 0
var _contour: Array = []
var _state_mean: Vector2 = Vector2.ZERO
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
	titles.add_child(Kit.make_label("STABILITY VERDICT  /  PLSR", 12, Kit.TEAL))
	titles.add_child(Kit.make_label("Identified-stability teaching presentation", 20))
	titles.add_child(Kit.make_label("ciw.identified-stability.v1 · local file · NOT_CHECKED proof", 12, Kit.MUTED))
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

	var contour_card := Kit.panel()
	contour_card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	contour_card.size_flags_vertical = Control.SIZE_EXPAND_FILL
	panels.add_child(contour_card)
	var contour_column := VBoxContainer.new()
	contour_card.add_child(contour_column)
	contour_column.add_child(Kit.make_label("01   QUADRATIC CONTOUR", 12, Kit.TEAL))
	contour_column.add_child(Kit.make_label("Identity V=x²+y² schematic · presentation only", 18))
	_canvas = Control.new()
	_canvas.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_canvas.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_canvas.custom_minimum_size = Vector2(280, 200)
	_canvas.draw.connect(_draw_contour)
	contour_column.add_child(_canvas)
	contour_column.add_child(Kit.make_label("HOST contour · not a solver mesh", 11, Kit.MUTED))

	var detail_card := Kit.panel()
	detail_card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	detail_card.size_flags_vertical = Control.SIZE_EXPAND_FILL
	panels.add_child(detail_card)
	var detail_column := VBoxContainer.new()
	detail_card.add_child(detail_column)
	detail_column.add_child(Kit.make_label("02   CASE / VERDICT", 12, Kit.TEAL))
	detail_column.add_child(Kit.make_label("Documented PLSR outcomes", 18))
	_case_option = OptionButton.new()
	_case_option.item_selected.connect(_on_case_selected)
	detail_column.add_child(_case_option)
	_case_label = Kit.make_label("case —", 12, Kit.MUTED)
	_case_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	detail_column.add_child(_case_label)

	var cards := HBoxContainer.new()
	cards.add_theme_constant_override("separation", 12)
	add_child(cards)
	var verdict := Kit.make_card("VERDICT")
	cards.add_child(verdict["card"])
	_verdict_value = verdict["value"]
	var quadratic := Kit.make_card("QUADRATIC V")
	cards.add_child(quadratic["card"])
	_quadratic_value = quadratic["value"]
	var margin := Kit.make_card("MARGIN")
	cards.add_child(margin["card"])
	_margin_value = margin["value"]
	var proof := Kit.make_card("PROOF")
	cards.add_child(proof["card"])
	_proof_value = proof["value"]

	_caption = Kit.make_label(STABILITY_CAPTION, 11, Kit.MUTED)
	_caption.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	add_child(_caption)

	var footer := HBoxContainer.new()
	add_child(footer)
	var authority := Kit.make_label(
		"HOST PLSR OUTCOMES → CARDS     •     CONTOUR → PRESENTATION     •     " + Kit.CAPTION,
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
		_contour.clear()
		_draw_stale = true
		_canvas.queue_redraw()
		_apply_stale("STALE", "plsr_stability_render.json missing — generate with examples/plsr-stability-verdict/emit_render.py")
		return
	_data = parsed
	_loaded = true
	_case_index = int(_data.get("selected_case_index", 0))
	_rebuild_case_options()
	_status.text = "●  LOADED"
	_status.add_theme_color_override("font_color", Kit.TEAL)
	_set_interaction(true)
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
			"%s  /  %s" % [str(entry.get("verdict", entry.get("status", "?"))), str(entry.get("label", entry.get("id", index)))],
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
	_verdict_value.text = "STALE"
	_quadratic_value.text = "—"
	_margin_value.text = "—"
	_proof_value.text = "—"
	_case_label.text = "case —"
	_set_interaction(false)
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
	var verdict := str(case_data.get("verdict", card_status))
	_case_label.text = "%s\n%s · %s · proof=%s" % [
		str(case_data.get("label", case_data.get("id", ""))),
		Kit.format_status_label(card_status),
		verdict,
		str(case_data.get("proof_status", "NOT_CHECKED")),
	]
	_status.text = "●  " + Kit.format_status_label(card_status)
	_status.add_theme_color_override("font_color", Kit.status_color(card_status))
	_verdict_value.text = verdict
	_verdict_value.add_theme_color_override("font_color", Kit.status_color(card_status))
	_quadratic_value.text = "%.4f" % float(case_data.get("quadratic_value", 0.0))
	var margin = case_data.get("margin", null)
	_margin_value.text = "%.4f" % float(margin) if margin != null else "—"
	_proof_value.text = str(case_data.get("proof_status", "NOT_CHECKED"))
	_proof_value.add_theme_color_override("font_color", Kit.AMBER)
	var caption := str(_data.get("caption", ""))
	_caption.text = caption if not caption.is_empty() else STABILITY_CAPTION

	var schematic: Dictionary = case_data.get("schematic", {})
	_contour = schematic.get("contour_xy", [])
	var state: Array = case_data.get("state_mean", [0.0, 0.0])
	_state_mean = Vector2(float(state[0]), float(state[1]) if state.size() > 1 else 0.0)
	_draw_stale = false
	_canvas.queue_redraw()


func _draw_contour() -> void:
	var margin := 24.0
	var area := Rect2(margin, margin, _canvas.size.x - margin * 2.0, _canvas.size.y - margin * 2.0)
	_canvas.draw_rect(Rect2(Vector2.ZERO, _canvas.size), Kit.BG, true)
	_canvas.draw_rect(area, Kit.PANEL, true)
	if _draw_stale or _contour.is_empty():
		_canvas.draw_string(ThemeDB.fallback_font, area.position + Vector2(8, 20), "NO CONTOUR DATA", HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Kit.MUTED)
		return
	var max_r := 1.0
	for pt in _contour:
		max_r = maxf(max_r, absf(float(pt[0])))
		max_r = maxf(max_r, absf(float(pt[1])))
	max_r = maxf(max_r, absf(_state_mean.x))
	max_r = maxf(max_r, absf(_state_mean.y))
	max_r = maxf(max_r, 1.0)
	var scale := minf(area.size.x, area.size.y) * 0.38 / max_r
	var origin := area.get_center()
	_canvas.draw_line(Vector2(area.position.x, origin.y), Vector2(area.position.x + area.size.x, origin.y), Kit.AXIS, 1.0)
	_canvas.draw_line(Vector2(origin.x, area.position.y), Vector2(origin.x, area.position.y + area.size.y), Kit.AXIS, 1.0)
	var points := PackedVector2Array()
	for pt in _contour:
		points.append(origin + Vector2(float(pt[0]), -float(pt[1])) * scale)
	if points.size() > 1:
		points.append(points[0])
		_canvas.draw_polyline(points, Kit.WASH if not _draw_stale else Kit.STEEL, 2.0, true)
	var state_p := origin + Vector2(_state_mean.x, -_state_mean.y) * scale
	_canvas.draw_circle(state_p, 6.0, Kit.AMBER if not _draw_stale else Kit.STEEL)
	_canvas.draw_string(ThemeDB.fallback_font, area.position + Vector2(4, 14), "V-level · state marker", HORIZONTAL_ALIGNMENT_LEFT, -1, 10, Kit.MUTED)
