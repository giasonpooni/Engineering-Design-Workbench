extends VBoxContainer
## Free energy tab: local HOST VFE sensor-bias teaching render JSON only.
## Reuses ciw.variational-free-energy.v1 language — no new CIW kind.
const Kit = preload("res://scripts/presentation_kit.gd")
const Strip = preload("res://scripts/presentation_strip.gd")

const DEFAULT_RELATIVE := "../examples/vfe-sensor-bias-teach/results/vfe_sensor_bias_render.json"
const MATCH_NAME := "vfe_sensor_bias_render.json"
const VFE_CAPTION := (
	"Free-energy numerics are computational, not physical calibration. "
	+ "Sensor calibration, surveyed geometry, physical state admission and "
	+ "physical stability remain unestablished."
)

var _strip = Strip.new()
var _status: Label
var _path_label: Label
var _caption: Label
var _reason_value: Label
var _metric_value: Label
var _gen_value: Label
var _assumed_value: Label
var _case_label: Label
var _case_option: OptionButton
var _reload: Button
var _verify_label: Label
var _data: Dictionary = {}
var _loaded := false
var _loaded_path := ""
var _case_index := 0


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
	titles.add_child(Kit.make_label("FREE ENERGY  /  MODEL MISMATCH", 12, Kit.TEAL))
	titles.add_child(Kit.make_label("HOST variational-free-energy teaching presentation", 20))
	titles.add_child(Kit.make_label("ciw.variational-free-energy.v1 · local file · computational only", 12, Kit.MUTED))
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

	var strip_card := Kit.panel()
	strip_card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	strip_card.size_flags_vertical = Control.SIZE_EXPAND_FILL
	panels.add_child(strip_card)
	var strip_column := VBoxContainer.new()
	strip_card.add_child(strip_column)
	strip_column.add_child(Kit.make_label("01   MISMATCH METRIC STRIP", 12, Kit.TEAL))
	strip_column.add_child(Kit.make_label("Bias · correlation · curvature contrasts", 18))
	_strip.size_flags_vertical = Control.SIZE_EXPAND_FILL
	strip_column.add_child(_strip)
	strip_column.add_child(Kit.make_label("HOST contrast metrics · not a live solve", 11, Kit.MUTED))

	var detail_card := Kit.panel()
	detail_card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	detail_card.size_flags_vertical = Control.SIZE_EXPAND_FILL
	panels.add_child(detail_card)
	var detail_column := VBoxContainer.new()
	detail_card.add_child(detail_column)
	detail_column.add_child(Kit.make_label("02   CONTRAST / CASE", 12, Kit.TEAL))
	detail_column.add_child(Kit.make_label("Sensor-bias · ignored-correlation · wrong-curvature", 18))
	_case_option = OptionButton.new()
	_case_option.item_selected.connect(_on_case_selected)
	detail_column.add_child(_case_option)
	_case_label = Kit.make_label("case —", 12, Kit.MUTED)
	_case_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	detail_column.add_child(_case_label)

	var cards := HBoxContainer.new()
	cards.add_theme_constant_override("separation", 12)
	add_child(cards)
	var reason := Kit.make_card("REASON")
	cards.add_child(reason["card"])
	_reason_value = reason["value"]
	var metric := Kit.make_card("MISMATCH")
	cards.add_child(metric["card"])
	_metric_value = metric["value"]
	var gen := Kit.make_card("GENERATOR")
	cards.add_child(gen["card"])
	_gen_value = gen["value"]
	var assumed := Kit.make_card("ASSUMED / GEOMETRY")
	cards.add_child(assumed["card"])
	_assumed_value = assumed["value"]

	_caption = Kit.make_label(VFE_CAPTION, 11, Kit.MUTED)
	_caption.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	add_child(_caption)

	var footer := HBoxContainer.new()
	add_child(footer)
	var authority := Kit.make_label(
		"HOST VFE FIXTURES → CARDS     •     STRIP → PRESENTATION     •     " + Kit.CAPTION,
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
		_apply_stale("STALE", "vfe_sensor_bias_render.json missing — generate with examples/vfe-sensor-bias-teach/emit_render.py")
		return
	_data = parsed
	_loaded = true
	_case_index = int(_data.get("selected_case_index", 0))
	_rebuild_case_options()
	_status.text = "●  LOADED"
	_status.add_theme_color_override("font_color", Kit.TEAL)
	_set_interaction(true)
	_strip.set_stale(false)
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
	_reason_value.text = "STALE"
	_metric_value.text = "—"
	_gen_value.text = "—"
	_assumed_value.text = "—"
	_case_label.text = "case —"
	_set_interaction(false)
	_strip.set_stale(true)
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
	_reason_value.text = str(case_data.get("reason", "—"))
	_reason_value.add_theme_color_override("font_color", Kit.status_color(card_status))
	var contrast: Dictionary = case_data.get("contrast", {})
	var kind := str(contrast.get("kind", ""))
	if kind == "sensor_bias":
		_metric_value.text = "%.4g" % float(contrast.get("bias_mismatch_norm", 0.0))
		_gen_value.text = str(contrast.get("generator_heldout_bias", "—"))
		_assumed_value.text = str(contrast.get("assumed_heldout_bias", "—"))
	elif kind == "ignored_correlation":
		_metric_value.text = "%.4g" % float(contrast.get("offdiag_mismatch", 0.0))
		_gen_value.text = "offdiag %.4g" % float(contrast.get("generator_noise_offdiag", 0.0))
		_assumed_value.text = "offdiag %.4g" % float(contrast.get("assumed_noise_offdiag", 0.0))
	elif kind == "wrong_curvature":
		_metric_value.text = "%.4g" % float(contrast.get("curvature_delta", 0.0))
		_gen_value.text = "K=%.4g" % float(contrast.get("generator_curvature", 0.0))
		_assumed_value.text = "K=%.4g" % float(contrast.get("geometry_curvature", 0.0))
	else:
		_metric_value.text = "—"
		_gen_value.text = "—"
		_assumed_value.text = "—"
	var caption := str(_data.get("caption", ""))
	_caption.text = caption if not caption.is_empty() else VFE_CAPTION

	var series: Array = _data.get("residual_series", [])
	_strip.set_series(series, "index", PackedStringArray(["mismatch_metric"]))
	_strip.set_selected_x(float(_case_index))
	_strip.set_stale(false)
