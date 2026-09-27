extends VBoxContainer
## BIM quantity tab: local HOST CSE quantity render JSON only.
## No building/Revit mesh. Reuses ciw.bim-quantity.v1 presentation — no new CIW kind.
const Kit = preload("res://scripts/presentation_kit.gd")
const Schematic = preload("res://scripts/presentation_schematic.gd")

const DEFAULT_RELATIVE := "../examples/cse-bim-quantity/results/cse_bim_render.json"
const MATCH_NAME := "cse_bim_render.json"
const BIM_CAPTION := (
	"ACCEPT is recommendation not construction approval; "
	+ "demo IFC/--demo not field evidence; surveyed geometry separate. "
	+ "Quantity-only schematic — no building/Revit render."
)

var _render_relative := ""
var _render_match := ""
var _missing_hint := ""
var _chrome_kicker := "BIM QUANTITY  /  CSE"
var _chrome_title := "Quantity-only HOST presentation"
var _chrome_sub := "ciw.bim-quantity.v1 · local file · no building mesh"

var _schematic = Schematic.new()
var _status: Label
var _path_label: Label
var _caption: Label
var _prior_value: Label
var _posterior_value: Label
var _disposition_value: Label
var _ledger_value: Label
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

	var schematic_card := Kit.panel()
	schematic_card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	schematic_card.size_flags_vertical = Control.SIZE_EXPAND_FILL
	panels.add_child(schematic_card)
	var schematic_column := VBoxContainer.new()
	schematic_card.add_child(schematic_column)
	schematic_column.add_child(Kit.make_label("01   QUANTITY BARS", 12, Kit.TEAL))
	schematic_column.add_child(Kit.make_label("Prior / posterior means · no building", 18))
	_schematic.size_flags_vertical = Control.SIZE_EXPAND_FILL
	schematic_column.add_child(_schematic)
	schematic_column.add_child(Kit.make_label("HOST schematic · QUANTITY_ONLY authority", 11, Kit.MUTED))

	var detail_card := Kit.panel()
	detail_card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	detail_card.size_flags_vertical = Control.SIZE_EXPAND_FILL
	panels.add_child(detail_card)
	var detail_column := VBoxContainer.new()
	detail_card.add_child(detail_column)
	detail_column.add_child(Kit.make_label("02   CASE / DISPOSITION", 12, Kit.TEAL))
	detail_column.add_child(Kit.make_label("ACCEPT is recommendation only", 18))
	_case_option = OptionButton.new()
	_case_option.item_selected.connect(_on_case_selected)
	detail_column.add_child(_case_option)
	_case_label = Kit.make_label("case —", 12, Kit.MUTED)
	_case_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	detail_column.add_child(_case_label)

	var cards := HBoxContainer.new()
	cards.add_theme_constant_override("separation", 12)
	add_child(cards)
	var prior_card := Kit.make_card("PRIOR")
	cards.add_child(prior_card["card"])
	_prior_value = prior_card["value"]
	var post_card := Kit.make_card("POSTERIOR")
	cards.add_child(post_card["card"])
	_posterior_value = post_card["value"]
	var disp_card := Kit.make_card("DISPOSITION")
	cards.add_child(disp_card["card"])
	_disposition_value = disp_card["value"]
	var ledger_card := Kit.make_card("LEDGER REPLAY")
	cards.add_child(ledger_card["card"])
	_ledger_value = ledger_card["value"]

	_caption = Kit.make_label(BIM_CAPTION, 11, Kit.MUTED)
	_caption.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	add_child(_caption)

	var footer := HBoxContainer.new()
	add_child(footer)
	var authority := Kit.make_label(
		"HOST CSE JSON → CARDS     •     QUANTITY BARS → PRESENTATION     •     " + Kit.CAPTION,
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
		_schematic.clear_view()
		var hint := _missing_hint if not _missing_hint.is_empty() else "cse_bim_render.json missing — generate with examples/cse-bim-quantity/emit_render.py"
		_apply_stale("STALE", hint)
		return
	_data = parsed
	_loaded = true
	_case_index = int(_data.get("selected_case_index", 0))
	_rebuild_case_options()
	_status.text = "●  LOADED"
	_status.add_theme_color_override("font_color", Kit.TEAL)
	_set_interaction(true)
	_schematic.set_stale(false)
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
			"%s  /  %s" % [str(entry.get("disposition", entry.get("criterion_state", "?"))), str(entry.get("label", entry.get("id", index)))],
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
	_prior_value.text = "—"
	_posterior_value.text = "—"
	_disposition_value.text = "STALE"
	_ledger_value.text = "—"
	_case_label.text = "case —"
	_set_interaction(false)
	_schematic.set_stale(true)
	_schematic.clear_view()
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


func _fmt_quantities(block: Dictionary) -> String:
	var parts: PackedStringArray = []
	for qty in block.get("quantities", []):
		parts.append("%s=%.4g %s" % [str(qty.get("quantity", "?")), float(qty.get("mean", 0.0)), str(qty.get("unit", ""))])
	return "  ".join(parts) if not parts.is_empty() else "—"


func _refresh() -> void:
	if not _loaded:
		_apply_stale("STALE", "no render data")
		return
	var case_data := _current_case()
	if case_data.is_empty():
		_apply_stale("STALE", "no cases in render JSON")
		return
	_case_label.text = "%s\n%s · %s · %s" % [
		str(case_data.get("label", case_data.get("id", ""))),
		str(case_data.get("status", "")),
		str(case_data.get("criterion_state", "")),
		str(case_data.get("geometry_authority", "QUANTITY_ONLY")),
	]
	_prior_value.text = _fmt_quantities(case_data.get("prior", {}))
	_posterior_value.text = _fmt_quantities(case_data.get("posterior", {}))
	var disposition := str(case_data.get("disposition", case_data.get("criterion_state", "—")))
	_disposition_value.text = Kit.format_status_label(disposition)
	_disposition_value.add_theme_color_override("font_color", Kit.status_color(disposition))
	var ledger: Dictionary = case_data.get("ledger_replay", {})
	if ledger.get("present", false):
		_ledger_value.text = "acc=%s rej=%s non=%s" % [
			str(ledger.get("accepted", 0)),
			str(ledger.get("rejected", 0)),
			str(ledger.get("non_state", 0)),
		]
	else:
		_ledger_value.text = "—"
	var caption := str(_data.get("caption", ""))
	_caption.text = caption if not caption.is_empty() else BIM_CAPTION

	# Quantity bars from posterior vs prior means (normalized loosely for display).
	var nodes: Array = []
	var prior_q: Array = case_data.get("prior", {}).get("quantities", [])
	var post_q: Array = case_data.get("posterior", {}).get("quantities", [])
	for i in range(post_q.size()):
		var post: Dictionary = post_q[i]
		var prior: Dictionary = prior_q[i] if i < prior_q.size() else post
		var scale := maxf(absf(float(prior.get("mean", 1.0))), 1e-6)
		nodes.append({
			"name": str(post.get("quantity", "q")),
			"level": clampf(absf(float(post.get("mean", 0.0))) / scale, 0.05, 1.0),
			"original": clampf(absf(float(prior.get("mean", 0.0))) / scale, 0.05, 1.0),
		})
	_schematic.set_nodes(nodes, 0.15)
	_schematic.set_stale(false)
