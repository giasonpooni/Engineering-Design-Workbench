extends Control
## Generic 2D strip: draw series from JSON arrays (theta vs y). Presentation only.
signal point_picked(theta: float)

const Kit = preload("res://scripts/presentation_kit.gd")

var _series: Array = []  # [{x: float, y: float, ...}, ...] or raw arrays
var _x_key := "theta"
var _y_keys: PackedStringArray = PackedStringArray(["y"])
var _selected_x := 0.0
var _stale := true
var _colors: Array[Color] = [Kit.TEAL, Kit.LABEL]


func _ready() -> void:
	custom_minimum_size = Vector2(280, 180)
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	mouse_filter = Control.MOUSE_FILTER_STOP


func clear_view() -> void:
	_series.clear()
	queue_redraw()


func set_series(samples: Array, x_key: String = "theta", y_keys: PackedStringArray = PackedStringArray(["y"])) -> void:
	_series = samples
	_x_key = x_key
	_y_keys = y_keys
	queue_redraw()


func set_selected_x(value: float) -> void:
	_selected_x = value
	queue_redraw()


func set_stale(value: bool) -> void:
	_stale = value
	mouse_filter = Control.MOUSE_FILTER_IGNORE if value else Control.MOUSE_FILTER_STOP
	queue_redraw()


func _gui_input(event: InputEvent) -> void:
	if _stale or _series.is_empty():
		return
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		var margin := 28.0
		var plot := Rect2(margin, margin, size.x - margin * 2.0, size.y - margin * 2.0)
		if plot.has_point(event.position):
			var x := clampf((event.position.x - plot.position.x) / maxf(plot.size.x, 1.0), 0.0, 1.0)
			# Map click x in plot to data x range
			var x_min := _x_range().x
			var x_max := _x_range().y
			_selected_x = lerpf(x_min, x_max, x)
			point_picked.emit(_selected_x)
			queue_redraw()
			accept_event()


func _x_range() -> Vector2:
	var x_min := INF
	var x_max := -INF
	for sample in _series:
		var x := _sample_x(sample)
		x_min = minf(x_min, x)
		x_max = maxf(x_max, x)
	if x_min >= x_max:
		return Vector2(0.0, 1.0)
	return Vector2(x_min, x_max)


func _sample_x(sample: Variant) -> float:
	if sample is Dictionary:
		return float(sample.get(_x_key, 0.0))
	if sample is Array and (sample as Array).size() >= 1:
		return float(sample[0])
	return 0.0


func _sample_y(sample: Variant, key: String, index: int) -> float:
	if sample is Dictionary:
		return float(sample.get(key, 0.0))
	if sample is Array and (sample as Array).size() > index + 1:
		return float(sample[index + 1])
	return 0.0


func _draw() -> void:
	var margin := 28.0
	var plot := Rect2(margin, margin, size.x - margin * 2.0, size.y - margin * 2.0)
	draw_rect(Rect2(Vector2.ZERO, size), Kit.BG, true)
	draw_rect(plot, Kit.PANEL, true)
	if _series.is_empty():
		draw_string(ThemeDB.fallback_font, plot.position + Vector2(8, 20), "NO SERIES DATA", HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Kit.MUTED)
		return
	var y_min := INF
	var y_max := -INF
	for sample in _series:
		for i in range(_y_keys.size()):
			var value := _sample_y(sample, _y_keys[i], i)
			y_min = minf(y_min, value)
			y_max = maxf(y_max, value)
	if y_min >= y_max:
		y_min -= 1.0
		y_max += 1.0
	var pad := (y_max - y_min) * 0.08
	y_min -= pad
	y_max += pad
	var xr := _x_range()
	# Axes
	draw_line(plot.position + Vector2(0, plot.size.y), plot.position + Vector2(plot.size.x, plot.size.y), Kit.AXIS, 1.0)
	draw_line(plot.position, plot.position + Vector2(0, plot.size.y), Kit.AXIS, 1.0)
	for i in range(_y_keys.size()):
		var color: Color = _colors[i % _colors.size()]
		if _stale:
			color = Kit.STEEL
		var points := PackedVector2Array()
		for sample in _series:
			var tx := (_sample_x(sample) - xr.x) / maxf(xr.y - xr.x, 1e-9)
			var ty := (_sample_y(sample, _y_keys[i], i) - y_min) / maxf(y_max - y_min, 1e-9)
			points.append(plot.position + Vector2(tx * plot.size.x, (1.0 - ty) * plot.size.y))
		if points.size() > 1:
			draw_polyline(points, color, 2.0, true)
	# Selection marker
	var sx := (_selected_x - xr.x) / maxf(xr.y - xr.x, 1e-9)
	var mx := plot.position.x + clampf(sx, 0.0, 1.0) * plot.size.x
	draw_line(Vector2(mx, plot.position.y), Vector2(mx, plot.position.y + plot.size.y), Kit.AMBER if not _stale else Kit.STEEL, 1.0)
