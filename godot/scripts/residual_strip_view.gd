extends VBoxContainer
## Residual strip tab: local HOST residual-cusum teaching render JSON only.
## Attaches to residual-monitor / FDIR-OIT language — no new CIW kind.
const Kit = preload("res://scripts/presentation_kit.gd")
const Strip = preload("res://scripts/presentation_strip.gd")

const DEFAULT_RELATIVE := "../examples/residual-cusum-teach/results/residual_cusum_render.json"
const MATCH_NAME := "residual_cusum_render.json"
const RESIDUAL_CAPTION := (
	"Physical drift and alarm probability unestablished; "
	+ "no joint covariance / cross-window confidence bars. "
	+ "OIT-held windows do not advance the CUSUM state."
)

var _render_relative := ""
var _render_match := ""
var _missing_hint := ""
var _chrome_kicker := "RESIDUAL STRIP  /  CUSUM TEACH"
var _chrome_title := "HOST residual-monitor presentation"
var _chrome_sub := "FDIR-OIT language · local file · no stack-root"

var _strip = Strip.new()
var _status: Label
var _path_label: Label
var _caption: Label
var _crossed_value: Label
var _cusum_value: Label
var _threshold_value: Label
var _advance_value: Label
var _window_label: Label
var _window_option: OptionButton
var _reload: Button
var _verify_label: Label
var _data: Dictionary = {}
var _loaded := false
var _loaded_path := ""
var _window_index := 0


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

	var strip_card := Kit.panel()
	strip_card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	strip_card.size_flags_vertical = Control.SIZE_EXPAND_FILL
	panels.add_child(strip_card)
	var strip_column := VBoxContainer.new()
	strip_card.add_child(strip_column)
	strip_column.add_child(Kit.make_label("01   NORMALIZED RESIDUAL / CUSUM", 12, Kit.TEAL))
	strip_column.add_child(Kit.make_label("Ordered windows · threshold line in cards", 18))
	_strip.size_flags_vertical = Control.SIZE_EXPAND_FILL
	strip_column.add_child(_strip)
	strip_column.add_child(Kit.make_label("HOST series · click selects x along strip", 11, Kit.MUTED))

	var detail_card := Kit.panel()
	detail_card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	detail_card.size_flags_vertical = Control.SIZE_EXPAND_FILL
	panels.add_child(detail_card)
	var detail_column := VBoxContainer.new()
	detail_card.add_child(detail_column)
	detail_column.add_child(Kit.make_label("02   WINDOW / CUSUM", 12, Kit.TEAL))
	detail_column.add_child(Kit.make_label("Quiet · cross · OIT-held", 18))
	_window_option = OptionButton.new()
	_window_option.item_selected.connect(_on_window_selected)
	detail_column.add_child(_window_option)
	_window_label = Kit.make_label("window —", 12, Kit.MUTED)
	_window_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	detail_column.add_child(_window_label)

	var cards := HBoxContainer.new()
	cards.add_theme_constant_override("separation", 12)
	add_child(cards)
	var crossed := Kit.make_card("CROSSED")
	cards.add_child(crossed["card"])
	_crossed_value = crossed["value"]
	var cusum := Kit.make_card("CUSUM FINAL")
	cards.add_child(cusum["card"])
	_cusum_value = cusum["value"]
	var threshold := Kit.make_card("THRESHOLD")
	cards.add_child(threshold["card"])
	_threshold_value = threshold["value"]
	var advance := Kit.make_card("ADVANCES CUSUM")
	cards.add_child(advance["card"])
	_advance_value = advance["value"]

	_caption = Kit.make_label(RESIDUAL_CAPTION, 11, Kit.MUTED)
	_caption.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	add_child(_caption)

	var footer := HBoxContainer.new()
	add_child(footer)
	var authority := Kit.make_label(
		"HOST RESIDUAL JSON → CARDS     •     STRIP → PRESENTATION     •     " + Kit.CAPTION,
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
		_strip.clear_view()
		var hint := _missing_hint if not _missing_hint.is_empty() else "residual_cusum_render.json missing — generate with examples/residual-cusum-teach/emit_render.py"
		_apply_stale("STALE", hint)
		return
	_data = parsed
	_loaded = true
	_window_index = int(_data.get("selected_window_index", 0))
	_rebuild_window_options()
	_status.text = "●  LOADED"
	_status.add_theme_color_override("font_color", Kit.TEAL)
	_set_interaction(true)
	_strip.set_stale(false)
	_verify_label.text = Kit.verification_label(_data)
	_verify_label.add_theme_color_override(
		"font_color", Kit.TEAL if bool(_data.get("fresh_verifier_occurrence", false)) else Kit.AMBER
	)
	_refresh()


func _rebuild_window_options() -> void:
	_window_option.clear()
	var windows: Array = _data.get("windows", [])
	for index in range(windows.size()):
		var entry: Dictionary = windows[index]
		_window_option.add_item(
			"%s  /  %s" % [str(entry.get("status", "?")), str(entry.get("label", entry.get("id", index)))],
			index
		)
	if _window_index < 0 or _window_index >= windows.size():
		_window_index = 0
	if windows.size() > 0:
		_window_option.select(_window_index)


func _apply_stale(state: String, detail: String) -> void:
	_status.text = "●  " + Kit.format_status_label(state)
	_status.add_theme_color_override("font_color", Kit.status_color(state))
	_path_label.text = detail if _loaded_path.is_empty() else (_loaded_path + "  ·  " + detail)
	_crossed_value.text = "STALE"
	_cusum_value.text = "—"
	_threshold_value.text = "—"
	_advance_value.text = "—"
	_window_label.text = "window —"
	_set_interaction(false)
	_strip.set_stale(true)
	Kit.apply_stale([_window_option], true)


func _set_interaction(enabled: bool) -> void:
	_window_option.disabled = not enabled
	Kit.apply_stale([_window_option], not enabled)


func _on_window_selected(index: int) -> void:
	_window_index = index
	_refresh()


func _current_window() -> Dictionary:
	var windows: Array = _data.get("windows", [])
	if _window_index >= 0 and _window_index < windows.size():
		return windows[_window_index]
	return {}


func _refresh() -> void:
	if not _loaded:
		_apply_stale("STALE", "no render data")
		return
	var window := _current_window()
	if window.is_empty():
		_apply_stale("STALE", "no windows in render JSON")
		return
	var card_status := str(window.get("status", "STALE"))
	_window_label.text = "%s\n%s · advances=%s · crossed=%s" % [
		str(window.get("label", window.get("id", ""))),
		Kit.format_status_label(card_status),
		str(window.get("advances_cusum", false)),
		str(window.get("crossed", false)),
	]
	_status.text = "●  " + Kit.format_status_label(card_status)
	_status.add_theme_color_override("font_color", Kit.status_color(card_status))
	_crossed_value.text = "YES" if bool(window.get("crossed", false)) else "NO"
	_crossed_value.add_theme_color_override(
		"font_color", Kit.status_color("REQUEST_EVIDENCE" if bool(window.get("crossed", false)) else "LIVE")
	)
	var cusum: Array = window.get("cusum", [])
	_cusum_value.text = "%.3f" % float(cusum[-1]) if not cusum.is_empty() else "—"
	_threshold_value.text = "%.3f" % float(window.get("threshold", _data.get("threshold", 0.0)))
	_advance_value.text = "YES" if bool(window.get("advances_cusum", false)) else "NO (OIT-held)"
	var caption := str(_data.get("caption", ""))
	_caption.text = caption if not caption.is_empty() else RESIDUAL_CAPTION

	# Strip: show this window's residual + cusum series
	var samples: Array = []
	var residuals: Array = window.get("normalized_residuals", [])
	var cusum_path: Array = window.get("cusum", [])
	var threshold := float(window.get("threshold", _data.get("threshold", 5.0)))
	for i in range(residuals.size()):
		samples.append({
			"index": i,
			"normalized_residual": float(residuals[i]),
			"cusum": float(cusum_path[i]) if i < cusum_path.size() else 0.0,
			"threshold": threshold,
		})
	_strip.set_series(samples, "index", PackedStringArray(["normalized_residual", "cusum", "threshold"]))
	_strip.set_selected_x(0.0)
	_strip.set_stale(false)
