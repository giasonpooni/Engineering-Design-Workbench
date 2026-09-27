extends VBoxContainer
## Measurement chain tab: local HOST measurement-chain teaching render JSON only.
## RCI/FSRT/JSPT language — no new CIW kind. No second FSRT solver.
const Kit = preload("res://scripts/presentation_kit.gd")
const Schematic = preload("res://scripts/presentation_schematic.gd")

const DEFAULT_RELATIVE := "../examples/measurement-chain-teach/results/measurement_chain_render.json"
const MATCH_NAME := "measurement_chain_render.json"
const CHAIN_CAPTION := (
	"HOST_SYNTHETIC measurement-chain-testbed. Distinct raw / calibrated / estimate / "
	+ "reconcile identities. No GSIE fusion or physical traceability. Viewport does not run RCI/FSRT/JSPT."
)

var _schematic = Schematic.new()
var _status: Label
var _path_label: Label
var _caption: Label
var _stage_value: Label
var _identity_value: Label
var _ops_value: Label
var _scope_value: Label
var _stage_label: Label
var _stage_option: OptionButton
var _reload: Button
var _verify_label: Label
var _data: Dictionary = {}
var _loaded := false
var _loaded_path := ""
var _stage_index := 0


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
	titles.add_child(Kit.make_label("MEASUREMENT CHAIN  /  RCI · FSRT · JSPT", 12, Kit.TEAL))
	titles.add_child(Kit.make_label("HOST measurement-chain teaching presentation", 20))
	titles.add_child(Kit.make_label("measurement-chain-testbed · local file · no second FSRT solver", 12, Kit.MUTED))
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
	schematic_column.add_child(Kit.make_label("01   TWO-NODE SCHEMATIC", 12, Kit.TEAL))
	schematic_column.add_child(Kit.make_label("HOST levels · not physical mass", 18))
	_schematic.size_flags_vertical = Control.SIZE_EXPAND_FILL
	schematic_column.add_child(_schematic)
	schematic_column.add_child(Kit.make_label("HOST_SYNTHETIC · presentation only", 11, Kit.MUTED))

	var detail_card := Kit.panel()
	detail_card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	detail_card.size_flags_vertical = Control.SIZE_EXPAND_FILL
	panels.add_child(detail_card)
	var detail_column := VBoxContainer.new()
	detail_card.add_child(detail_column)
	detail_column.add_child(Kit.make_label("02   STAGE / IDENTITY", 12, Kit.TEAL))
	detail_column.add_child(Kit.make_label("Raw → calibrated → estimate → reconcile", 18))
	_stage_option = OptionButton.new()
	_stage_option.item_selected.connect(_on_stage_selected)
	detail_column.add_child(_stage_option)
	_stage_label = Kit.make_label("stage —", 12, Kit.MUTED)
	_stage_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	detail_column.add_child(_stage_label)

	var cards := HBoxContainer.new()
	cards.add_theme_constant_override("separation", 12)
	add_child(cards)
	var stage := Kit.make_card("STAGE")
	cards.add_child(stage["card"])
	_stage_value = stage["value"]
	var identity := Kit.make_card("IDENTITY")
	cards.add_child(identity["card"])
	_identity_value = identity["value"]
	var ops := Kit.make_card("OPS LANGUAGE")
	cards.add_child(ops["card"])
	_ops_value = ops["value"]
	var scope := Kit.make_card("SCOPE")
	cards.add_child(scope["card"])
	_scope_value = scope["value"]

	_caption = Kit.make_label(CHAIN_CAPTION, 11, Kit.MUTED)
	_caption.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	add_child(_caption)

	var footer := HBoxContainer.new()
	add_child(footer)
	var authority := Kit.make_label(
		"HOST MEASUREMENT-CHAIN → CARDS     •     SCHEMATIC → PRESENTATION     •     " + Kit.CAPTION,
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
		_schematic.clear_view()
		_apply_stale("STALE", "measurement_chain_render.json missing — generate with examples/measurement-chain-teach/emit_render.py")
		return
	_data = parsed
	_loaded = true
	_stage_index = int(_data.get("selected_stage_index", 0))
	_rebuild_stage_options()
	_status.text = "●  LOADED"
	_status.add_theme_color_override("font_color", Kit.TEAL)
	_set_interaction(true)
	_schematic.set_stale(false)
	_verify_label.text = Kit.verification_label(_data)
	_verify_label.add_theme_color_override(
		"font_color", Kit.TEAL if bool(_data.get("fresh_verifier_occurrence", false)) else Kit.AMBER
	)
	_refresh()


func _rebuild_stage_options() -> void:
	_stage_option.clear()
	var stages: Array = _data.get("stages", [])
	for index in range(stages.size()):
		var entry: Dictionary = stages[index]
		_stage_option.add_item(
			"%s  /  %s" % [str(entry.get("status", "?")), str(entry.get("label", entry.get("id", index)))],
			index
		)
	if _stage_index < 0 or _stage_index >= stages.size():
		_stage_index = 0
	if stages.size() > 0:
		_stage_option.select(_stage_index)


func _apply_stale(state: String, detail: String) -> void:
	_status.text = "●  " + Kit.format_status_label(state)
	_status.add_theme_color_override("font_color", Kit.status_color(state))
	_path_label.text = detail if _loaded_path.is_empty() else (_loaded_path + "  ·  " + detail)
	_stage_value.text = "STALE"
	_identity_value.text = "—"
	_ops_value.text = "—"
	_scope_value.text = "—"
	_stage_label.text = "stage —"
	_set_interaction(false)
	_schematic.set_stale(true)
	Kit.apply_stale([_stage_option], true)


func _set_interaction(enabled: bool) -> void:
	_stage_option.disabled = not enabled
	Kit.apply_stale([_stage_option], not enabled)


func _on_stage_selected(index: int) -> void:
	_stage_index = index
	_refresh()


func _current_stage() -> Dictionary:
	var stages: Array = _data.get("stages", [])
	if _stage_index >= 0 and _stage_index < stages.size():
		return stages[_stage_index]
	return {}


func _refresh() -> void:
	if not _loaded:
		_apply_stale("STALE", "no render data")
		return
	var stage := _current_stage()
	if stage.is_empty():
		_apply_stale("STALE", "no stages in render JSON")
		return
	var card_status := str(stage.get("status", "STALE"))
	_stage_label.text = "%s\n%s · %s" % [
		str(stage.get("label", stage.get("id", ""))),
		Kit.format_status_label(card_status),
		str(stage.get("ops_language", "")),
	]
	_status.text = "●  " + Kit.format_status_label(card_status)
	_status.add_theme_color_override("font_color", Kit.status_color(card_status))
	_stage_value.text = str(stage.get("label", stage.get("id", "—")))
	_stage_value.add_theme_color_override("font_color", Kit.status_color(card_status))
	_identity_value.text = str(stage.get("identity", "—"))
	_ops_value.text = str(stage.get("ops_language", "—"))
	var configuration: Dictionary = _data.get("configuration", {})
	_scope_value.text = str(configuration.get("scope", "measurement-chain-testbed"))
	var caption := str(_data.get("caption", ""))
	_caption.text = caption if not caption.is_empty() else CHAIN_CAPTION

	var nodes: Array = _data.get("nodes", [])
	var schematic: Dictionary = _data.get("schematic", {})
	var residual := float(schematic.get("residual_norm", 0.22))
	_schematic.set_nodes(nodes, residual)
	_schematic.set_caption("two-node HOST schematic")
	_schematic.set_stale(false)
