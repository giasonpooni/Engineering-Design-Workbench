extends VBoxContainer
## Analog / method-gap tab: local host-render JSON only. No websocket protocol.
const StateView = preload("res://scripts/analog_state_view.gd")
const StripView = preload("res://scripts/analog_strip.gd")
const Kit = preload("res://scripts/presentation_kit.gd")
const TEXT := Color("dce6f1")
const MUTED := Color("899cb2")
const TEAL := Color("60dfcd")
const AMBER := Color("ffcc80")
const DEFAULT_RELATIVE := "../examples/pyramid-method-gap/results/analog_render.json"

var _state = StateView.new()
var _strip = StripView.new()
var _status: Label
var _path_label: Label
var _caption: Label
var _v_value: Label
var _maxeig_value: Label
var _plsr_value: Label
var _sample_label: Label
var _slider: HSlider
var _play: Button
var _reload: Button
var _data: Dictionary = {}
var _sample_index := 0
var _selected_theta := 0.0
var _playing := false
var _play_accum := 0.0
var _loaded := false
var _loaded_path := ""


func _ready() -> void:
	add_theme_constant_override("separation", 12)
	_build_ui()
	_strip.theta_picked.connect(_on_theta_picked)
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


func _build_ui() -> void:
	var header := HBoxContainer.new()
	header.add_theme_constant_override("separation", 12)
	add_child(header)
	var titles := VBoxContainer.new()
	titles.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(titles)
	titles.add_child(_label("ANALOG  /  METHOD GAP", 12, TEAL))
	titles.add_child(_label("Host-rendered Lyapunov presentation", 20))
	titles.add_child(_label("Local file only · no websocket · may_authorize stays false", 12, MUTED))
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

	var state_card := _panel()
	state_card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	state_card.size_flags_vertical = Control.SIZE_EXPAND_FILL
	panels.add_child(state_card)
	var state_column := VBoxContainer.new()
	state_card.add_child(state_column)
	state_column.add_child(_label("01   ANALOG STATE", 12, TEAL))
	state_column.add_child(_label("V-level ellipsoid · A(0) / A(1) trajectories", 18))
	_state.size_flags_vertical = Control.SIZE_EXPAND_FILL
	state_column.add_child(_state)
	state_column.add_child(_label("Host mesh · drag to orbit / wheel to zoom", 11, MUTED))

	var strip_card := _panel()
	strip_card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	strip_card.size_flags_vertical = Control.SIZE_EXPAND_FILL
	panels.add_child(strip_card)
	var strip_column := VBoxContainer.new()
	strip_card.add_child(strip_column)
	strip_column.add_child(_label("02   PARAMETER STRIP", 12, TEAL))
	strip_column.add_child(_label("θ ∈ [0, 1]  ·  maxeig(M) and α(A)", 18))
	_strip.size_flags_vertical = Control.SIZE_EXPAND_FILL
	strip_column.add_child(_strip)
	strip_column.add_child(_label("Teaching vertices at 0, 0.5, 1 · click to select θ", 11, MUTED))

	var cards := HBoxContainer.new()
	cards.add_theme_constant_override("separation", 12)
	add_child(cards)
	_v_value = _add_card(cards, "V(x)")
	_maxeig_value = _add_card(cards, "maxeig(M)")
	_plsr_value = _add_card(cards, "RUNTIME / PLSR")

	var timeline := _panel()
	add_child(timeline)
	var timeline_column := VBoxContainer.new()
	timeline.add_child(timeline_column)
	var cursor_row := HBoxContainer.new()
	timeline_column.add_child(cursor_row)
	_sample_label = _label("PLAYBACK SAMPLE   —", 13, TEAL)
	_sample_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	cursor_row.add_child(_sample_label)
	cursor_row.add_child(_label("Retained host points only", 12, MUTED))
	_play = Button.new()
	_play.text = "Play"
	_play.pressed.connect(_toggle_play)
	cursor_row.add_child(_play)
	_slider = HSlider.new()
	_slider.custom_minimum_size.y = 26
	_slider.step = 1
	_slider.value_changed.connect(_slider_changed)
	timeline_column.add_child(_slider)

	_caption = _label(
		"Meshes are presentation only. Numeric cards come from host analog JSON, never reconstructed from displayed geometry.",
		11,
		MUTED
	)
	_caption.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	add_child(_caption)

	var footer := HBoxContainer.new()
	add_child(footer)
	var authority := _label(
		"HOST ANALOG JSON → CARDS     •     RENDER MESH → PRESENTATION     •     " + Kit.CAPTION,
		10,
		MUTED
	)
	authority.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	footer.add_child(authority)
	footer.add_child(_label("VERIFICATION  /  NOT CLAIMED", 10, AMBER))
	_set_interaction(false)


func _add_card(row: HBoxContainer, title: String) -> Label:
	var card := _panel()
	card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(card)
	var contents := VBoxContainer.new()
	card.add_child(contents)
	contents.add_child(_label(title, 11, MUTED))
	var value := _label("—", 22)
	contents.add_child(value)
	return value


func _resolve_path() -> String:
	return Kit.resolve_render_path(DEFAULT_RELATIVE, "analog_render.json")


func _try_load() -> void:
	_stop_playback()
	var path := _resolve_path()
	_loaded_path = path
	_path_label.text = "render path  " + path
	_path_label.tooltip_text = path
	var parsed := Kit.load_json(path)
	if parsed.is_empty():
		_data.clear()
		_loaded = false
		_state.clear_view()
		_strip.clear_view()
		_apply_stale("STALE", "analog_render.json missing — generate with run_analog.py --write-render")
		return
	_data = parsed
	_loaded = true
	_sample_index = int(_data.get("selected_sample_index", 0))
	_selected_theta = float(_data.get("selected_theta", 0.0))
	_state.set_render(_data)
	_strip.set_render(_data)
	_strip.set_selected_theta(_selected_theta)
	var playback: Array = _data.get("playback_samples", [])
	_slider.max_value = maxi(playback.size() - 1, 0)
	_slider.set_value_no_signal(_sample_index)
	_status.text = "●  LOADED"
	_status.add_theme_color_override("font_color", Kit.status_color("LIVE"))
	_set_interaction(true)
	_state.set_stale(false)
	_strip.set_stale(false)
	_refresh_cards()


func _apply_stale(state: String, detail: String) -> void:
	_status.text = "●  " + Kit.format_status_label(state)
	_status.add_theme_color_override("font_color", Kit.status_color(state))
	_path_label.text = detail if _loaded_path.is_empty() else (_loaded_path + "  ·  " + detail)
	_v_value.text = "—"
	_maxeig_value.text = "—"
	_plsr_value.text = "STALE"
	_sample_label.text = "PLAYBACK SAMPLE   —"
	_set_interaction(false)
	_state.set_stale(true)
	_strip.set_stale(true)


func _set_interaction(enabled: bool) -> void:
	_slider.editable = enabled
	_play.disabled = not enabled
	if not enabled:
		_stop_playback()


func _refresh_cards() -> void:
	if not _loaded:
		_apply_stale("STALE", "no render data")
		return
	var playback: Array = _data.get("playback_samples", [])
	var v_text := "—"
	if _sample_index >= 0 and _sample_index < playback.size():
		var sample: Dictionary = playback[_sample_index]
		v_text = "%.4f" % float(sample.get("V_renewal", sample.get("V", 0.0)))
	elif _data.has("V_at_sample"):
		v_text = "%.4f" % float(_data["V_at_sample"].get("V", _data["V_at_sample"].get("V_renewal", 0.0)))
	_v_value.text = v_text

	var maxeig := _lookup_maxeig(_selected_theta)
	_maxeig_value.text = "%.4f" % maxeig if not is_nan(maxeig) else "—"
	_plsr_value.text = str(_data.get("plsr_status", _data.get("runtime_status", "HOST_ANALOG_ONLY")))
	_sample_label.text = "PLAYBACK SAMPLE   %d / %d   ·   θ = %.3f" % [
		_sample_index,
		maxi(playback.size() - 1, 0),
		_selected_theta,
	]
	_state.set_sample(_sample_index)


func _lookup_maxeig(theta: float) -> float:
	var best := NAN
	var best_distance := INF
	for source in [_data.get("strip_samples", []), _data.get("vertex_table", [])]:
		for sample in source:
			var distance := absf(float(sample.get("theta", 0.0)) - theta)
			if distance < best_distance:
				best_distance = distance
				best = float(sample.get("maxeig_M", NAN))
	return best


func _on_theta_picked(theta: float) -> void:
	_selected_theta = theta
	_refresh_cards()


func _slider_changed(value: float) -> void:
	_sample_index = int(value)
	_refresh_cards()


func _toggle_play() -> void:
	if not _loaded:
		return
	_playing = not _playing
	_play.text = "Pause" if _playing else "Play"
	_play_accum = 0.0


func _stop_playback() -> void:
	_playing = false
	if _play != null:
		_play.text = "Play"


func _process(delta: float) -> void:
	if not _playing or not _loaded:
		return
	var playback: Array = _data.get("playback_samples", [])
	if playback.is_empty():
		_stop_playback()
		return
	_play_accum += delta
	# Slow optional playback along retained samples only.
	var step_s := 0.08
	while _play_accum >= step_s:
		_play_accum -= step_s
		_sample_index += 1
		if _sample_index >= playback.size():
			_sample_index = playback.size() - 1
			_slider.set_value_no_signal(_sample_index)
			_refresh_cards()
			_stop_playback()
			return
		_slider.set_value_no_signal(_sample_index)
		_refresh_cards()
