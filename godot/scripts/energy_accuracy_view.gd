extends VBoxContainer
## Energy accuracy tab: local HOST energy-accuracy teaching render JSON only.
## Reuses ciw.energy-accuracy.v1 language — no new CIW kind. Presentation only.
const Kit = preload("res://scripts/presentation_kit.gd")
const Strip = preload("res://scripts/presentation_strip.gd")

const DEFAULT_RELATIVE := "../examples/energy-accuracy-teach/results/energy_accuracy_render.json"
const MATCH_NAME := "energy_accuracy_render.json"
const ENERGY_CAPTION := (
	"Synthetic fixtures; no calibrated uncertainty budget or whole-machine energy claim. "
	+ "Statistical free energy (nats), physical energy (joules), and elapsed time remain separate."
)

var _strip = Strip.new()
var _status: Label
var _path_label: Label
var _caption: Label
var _outcome_value: Label
var _kl_value: Label
var _energy_value: Label
var _amortized_value: Label
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
	titles.add_child(Kit.make_label("ENERGY ACCURACY  /  QUALIFICATION", 12, Kit.TEAL))
	titles.add_child(Kit.make_label("HOST energy-accuracy teaching presentation", 20))
	titles.add_child(Kit.make_label("ciw.energy-accuracy.v1 · local file · synthetic fixtures", 12, Kit.MUTED))
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
	strip_column.add_child(Kit.make_label("01   PHASE ENERGY / CASE STRIP", 12, Kit.TEAL))
	strip_column.add_child(Kit.make_label("Gross energy by phase · case KL strip", 18))
	_strip.size_flags_vertical = Control.SIZE_EXPAND_FILL
	strip_column.add_child(_strip)
	strip_column.add_child(Kit.make_label("HOST series · synthetic fixtures", 11, Kit.MUTED))

	var detail_card := Kit.panel()
	detail_card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	detail_card.size_flags_vertical = Control.SIZE_EXPAND_FILL
	panels.add_child(detail_card)
	var detail_column := VBoxContainer.new()
	detail_card.add_child(detail_column)
	detail_column.add_child(Kit.make_label("02   CASE / QUALIFICATION", 12, Kit.TEAL))
	detail_column.add_child(Kit.make_label("Baseline · under-target · missing", 18))
	_case_option = OptionButton.new()
	_case_option.item_selected.connect(_on_case_selected)
	detail_column.add_child(_case_option)
	_case_label = Kit.make_label("case —", 12, Kit.MUTED)
	_case_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	detail_column.add_child(_case_label)

	var cards := HBoxContainer.new()
	cards.add_theme_constant_override("separation", 12)
	add_child(cards)
	var outcome := Kit.make_card("OUTCOME")
	cards.add_child(outcome["card"])
	_outcome_value = outcome["value"]
	var kl := Kit.make_card("MAX KL nats")
	cards.add_child(kl["card"])
	_kl_value = kl["value"]
	var energy := Kit.make_card("GROSS ENERGY J")
	cards.add_child(energy["card"])
	_energy_value = energy["value"]
	var amortized := Kit.make_card("J / QUALIFIED")
	cards.add_child(amortized["card"])
	_amortized_value = amortized["value"]

	_caption = Kit.make_label(ENERGY_CAPTION, 11, Kit.MUTED)
	_caption.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	add_child(_caption)

	var footer := HBoxContainer.new()
	add_child(footer)
	var authority := Kit.make_label(
		"HOST ENERGY FIXTURES → CARDS     •     STRIP → PRESENTATION     •     " + Kit.CAPTION,
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
		_apply_stale("STALE", "energy_accuracy_render.json missing — generate with examples/energy-accuracy-teach/emit_render.py")
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
	_outcome_value.text = "STALE"
	_kl_value.text = "—"
	_energy_value.text = "—"
	_amortized_value.text = "—"
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
	_outcome_value.text = Kit.format_status_label(str(case_data.get("native_outcome", card_status)).to_upper())
	_outcome_value.add_theme_color_override("font_color", Kit.status_color(card_status))
	var measurement: Dictionary = case_data.get("measurement", {})
	_kl_value.text = "%.4g" % float(measurement.get("max_kl_nats", 0.0))
	var gross = measurement.get("gross_energy_j", null)
	_energy_value.text = "%.4g" % float(gross) if gross != null else "null"
	var amortized = measurement.get("amortized_j_per_qualified_solve", null)
	_amortized_value.text = "%.4g" % float(amortized) if amortized != null else "null"
	var caption := str(_data.get("caption", ""))
	_caption.text = caption if not caption.is_empty() else ENERGY_CAPTION

	# Prefer phase strip for selected case; fall back to residual_series across cases
	var phase_series: Array = case_data.get("phase_series", [])
	if not phase_series.is_empty():
		_strip.set_series(phase_series, "index", PackedStringArray(["gross_energy_j", "elapsed_s"]))
		_strip.set_selected_x(0.0)
	else:
		var series: Array = _data.get("residual_series", [])
		_strip.set_series(series, "index", PackedStringArray(["max_kl_nats", "amortized_j"]))
		_strip.set_selected_x(float(_case_index))
	_strip.set_stale(false)
