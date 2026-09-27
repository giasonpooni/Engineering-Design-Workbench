extends VBoxContainer
## Proof tab: local HOST proved-heat render JSON only.
## Never draws proof bytes. Never paints VERIFIED unless fresh_verifier_occurrence.
## Godot must not reverify; HISTORICAL → retained_runtime_report_requires_fresh_verification.
const Kit = preload("res://scripts/presentation_kit.gd")

const DEFAULT_RELATIVE := "../examples/proved-heat/results/proved_heat_render.json"
const MATCH_NAME := "proved_heat_render.json"

var _render_relative := ""
var _render_match := ""
var _missing_hint := ""
var _chrome_kicker := "PROOF  /  PROVED HEAT"
var _chrome_title := "Retained runtime report presentation"
var _chrome_sub := "ciw.proved-heat.v1 · no reverify · no proof bytes drawn"

var _status: Label
var _path_label: Label
var _caption: Label
var _execution_value: Label
var _result_value: Label
var _verification_value: Label
var _scope_value: Label
var _pins_value: Label
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
	titles.add_child(Kit.make_label(_chrome_kicker, 12, Kit.TEAL))
	titles.add_child(Kit.make_label(_chrome_title, 20))
	titles.add_child(Kit.make_label(_chrome_sub, 12, Kit.MUTED))
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

	var id_card := Kit.panel()
	id_card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	id_card.size_flags_vertical = Control.SIZE_EXPAND_FILL
	panels.add_child(id_card)
	var id_column := VBoxContainer.new()
	id_card.add_child(id_column)
	id_column.add_child(Kit.make_label("01   IDENTITIES", 12, Kit.TEAL))
	id_column.add_child(Kit.make_label("execution · result · verification", 18))
	_case_option = OptionButton.new()
	_case_option.item_selected.connect(_on_case_selected)
	id_column.add_child(_case_option)
	_case_label = Kit.make_label("case —", 12, Kit.MUTED)
	_case_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	id_column.add_child(_case_label)
	var spacer := Control.new()
	spacer.size_flags_vertical = Control.SIZE_EXPAND_FILL
	id_column.add_child(spacer)
	id_column.add_child(Kit.make_label(
		"proof-before-result · unavailable ≠ passed · Godot does not reverify",
		11,
		Kit.MUTED
	))

	var pin_card := Kit.panel()
	pin_card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	pin_card.size_flags_vertical = Control.SIZE_EXPAND_FILL
	panels.add_child(pin_card)
	var pin_column := VBoxContainer.new()
	pin_card.add_child(pin_column)
	pin_column.add_child(Kit.make_label("02   PINS / SCOPE", 12, Kit.TEAL))
	pin_column.add_child(Kit.make_label("From docs/PROVED_HEAT.md — not proof bytes", 18))
	_pins_value = Kit.make_label("pins —", 12, Kit.MUTED)
	_pins_value.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	pin_column.add_child(_pins_value)

	var cards := HBoxContainer.new()
	cards.add_theme_constant_override("separation", 12)
	add_child(cards)
	var ex := Kit.make_card("EXECUTION")
	cards.add_child(ex["card"])
	_execution_value = ex["value"]
	var res := Kit.make_card("RESULT")
	cards.add_child(res["card"])
	_result_value = res["value"]
	var ver := Kit.make_card("VERIFICATION")
	cards.add_child(ver["card"])
	_verification_value = ver["value"]
	var scope := Kit.make_card("STATEMENT SCOPE")
	cards.add_child(scope["card"])
	_scope_value = scope["value"]

	_caption = Kit.make_label(Kit.CAPTION, 11, Kit.MUTED)
	_caption.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	add_child(_caption)

	var footer := HBoxContainer.new()
	add_child(footer)
	var authority := Kit.make_label(
		"HOST PROVED-HEAT JSON → CARDS     •     NO PROOF BYTES     •     " + Kit.CAPTION,
		10,
		Kit.MUTED
	)
	authority.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	footer.add_child(authority)
	_verify_label = Kit.make_label("VERIFICATION  /  NOT CLAIMED", 10, Kit.AMBER)
	footer.add_child(_verify_label)
	_set_interaction(false)


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
		var hint := _missing_hint if not _missing_hint.is_empty() else "proved_heat_render.json missing — generate with examples/proved-heat/emit_proof_render.py"
		_apply_stale("STALE", hint)
		return
	_data = parsed
	_loaded = true
	_case_index = int(_data.get("selected_case_index", 0))
	_rebuild_case_options()
	var top_status := str(_data.get("upstream_status", "LOADED")).to_upper()
	if top_status.find("ABSENT") >= 0 or top_status.find("UNAVAILABLE") >= 0:
		_status.text = "●  " + Kit.format_status_label("UNAVAILABLE")
		_status.add_theme_color_override("font_color", Kit.status_color("UNAVAILABLE"))
	else:
		_status.text = "●  LOADED"
		_status.add_theme_color_override("font_color", Kit.TEAL)
	_set_interaction(true)
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
			"%s  /  %s" % [str(entry.get("card_status", "?")), str(entry.get("label", entry.get("id", index)))],
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
	_execution_value.text = "—"
	_result_value.text = "—"
	_verification_value.text = "STALE"
	_scope_value.text = "—"
	_pins_value.text = "pins —"
	_case_label.text = "case —"
	_set_interaction(false)
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


func _id_text(value: Variant) -> String:
	if value == null:
		return "—"
	var text := str(value)
	return text if not text.is_empty() else "—"


func _refresh() -> void:
	if not _loaded:
		_apply_stale("STALE", "no render data")
		return
	var case_data := _current_case()
	if case_data.is_empty():
		_apply_stale("STALE", "no cases in render JSON")
		return
	var card_status := str(case_data.get("card_status", case_data.get("proof_status", "HISTORICAL")))
	# Never green for REFUSED / UNAVAILABLE / missing proof.
	var never_green := bool(case_data.get("never_green", false))
	_case_label.text = "%s\n%s · %s" % [
		str(case_data.get("label", case_data.get("id", ""))),
		Kit.format_status_label(card_status),
		str(case_data.get("reason", "")),
	]
	_status.text = "●  " + Kit.format_status_label(card_status)
	_status.add_theme_color_override("font_color", Kit.status_color(card_status))

	var identities: Dictionary = case_data.get("identities", {})
	_execution_value.text = _id_text(identities.get("execution", null))
	_result_value.text = _id_text(identities.get("result", null))
	# HISTORICAL maps to retained_runtime_report_requires_fresh_verification display.
	var verification_id = identities.get("verification", null)
	if verification_id == null or str(verification_id).is_empty():
		if card_status.to_upper() in ["HISTORICAL", "UNAVAILABLE", "REFUSED", "STALE"]:
			_verification_value.text = Kit.format_status_label(card_status if card_status.to_upper() != "STALE" else "HISTORICAL")
		else:
			_verification_value.text = Kit.format_status_label("HISTORICAL")
	else:
		# Still do not claim VERIFIED without fresh_verifier_occurrence on the payload.
		if bool(_data.get("fresh_verifier_occurrence", false)) and not never_green:
			_verification_value.text = _id_text(verification_id)
		else:
			_verification_value.text = Kit.format_status_label("HISTORICAL")
	_verification_value.add_theme_color_override("font_color", Kit.status_color(card_status))

	var statement: Dictionary = case_data.get("statement", _data.get("statement", {}))
	var initial = statement.get("initial_values", [])
	var final_v = statement.get("final_values", [])
	_scope_value.text = "%s\n%s → %s  steps=%s" % [
		str(statement.get("scope", "bounded_registered_guest_only")),
		str(initial),
		str(final_v),
		str(statement.get("steps", "?")),
	]

	var pins: Dictionary = case_data.get("pins", _data.get("pins", {}))
	var pin_lines: PackedStringArray = []
	for key in ["scr_revision", "sp1_revision", "guest_elf_sha256", "guest_recipe_identity", "backend_report"]:
		if pins.has(key):
			var val := str(pins[key])
			if val.length() > 24:
				val = val.substr(0, 12) + "…" + val.substr(val.length() - 8, 8)
			pin_lines.append("%s: %s" % [key, val])
	_pins_value.text = "\n".join(pin_lines) if not pin_lines.is_empty() else "pins —"

	var caption := str(_data.get("caption", ""))
	_caption.text = caption if not caption.is_empty() else Kit.CAPTION
