extends Control
## 2D strip: theta in [0,1] vs maxeig(M) and spectral abscissa from host JSON.
signal theta_picked(theta: float)

const TEAL := Color("60dfcd")
const MUTED := Color("899cb2")
const AXIS := Color("4e647e")
const ZERO := Color("4e647e")
const MARK := Color("ffcc80")
const ALPHA_LINE := Color("7f9bb8")

var _strip: Array = []
var _vertices: Array = []
var _selected_theta := 0.0
var _stale := true


func _ready() -> void:
	custom_minimum_size = Vector2(280, 180)
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	mouse_filter = Control.MOUSE_FILTER_STOP


func clear_view() -> void:
	_strip.clear()
	_vertices.clear()
	queue_redraw()


func set_render(data: Dictionary) -> void:
	_strip = data.get("strip_samples", [])
	_vertices = data.get("vertex_table", [])
	_selected_theta = float(data.get("selected_theta", 0.0))
	queue_redraw()


func set_selected_theta(theta: float) -> void:
	_selected_theta = clampf(theta, 0.0, 1.0)
	queue_redraw()


func set_stale(value: bool) -> void:
	_stale = value
	queue_redraw()


func _gui_input(event: InputEvent) -> void:
	if _stale or _strip.is_empty():
		return
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		var margin := _margin()
		var plot := Rect2(margin, margin, size.x - margin * 2.0, size.y - margin * 2.0)
		if plot.has_point(event.position):
			var theta := clampf((event.position.x - plot.position.x) / maxf(plot.size.x, 1.0), 0.0, 1.0)
			_selected_theta = theta
			theta_picked.emit(theta)
			queue_redraw()
			accept_event()


func _margin() -> float:
	return 28.0


func _draw() -> void:
	var margin := _margin()
	var plot := Rect2(margin, margin, size.x - margin * 2.0, size.y - margin * 2.0)
	draw_rect(Rect2(Vector2.ZERO, size), Color("0c1521"), true)
	draw_rect(plot, Color("101a28"), true)
	if _strip.is_empty():
		draw_string(ThemeDB.fallback_font, plot.position + Vector2(8, 20), "NO STRIP DATA", HORIZONTAL_ALIGNMENT_LEFT, -1, 12, MUTED)
		return

	var y_min := INF
	var y_max := -INF
	for sample in _strip:
		for key in ["maxeig_M", "alpha"]:
			var value := float(sample.get(key, 0.0))
			y_min = minf(y_min, value)
			y_max = maxf(y_max, value)
	y_min = minf(y_min, -0.2)
	y_max = maxf(y_max, 0.2)
	var span := maxf(y_max - y_min, 1e-6)

	# Zero line.
	var zero_y := plot.position.y + plot.size.y * (1.0 - (0.0 - y_min) / span)
	draw_line(Vector2(plot.position.x, zero_y), Vector2(plot.end.x, zero_y), ZERO, 1.0)

	# Axes frame.
	draw_rect(plot, AXIS, false, 1.0)

	var maxeig_pts := PackedVector2Array()
	var alpha_pts := PackedVector2Array()
	for sample in _strip:
		var theta := float(sample.get("theta", 0.0))
		var x := plot.position.x + plot.size.x * theta
		var ym := plot.position.y + plot.size.y * (1.0 - (float(sample.get("maxeig_M", 0.0)) - y_min) / span)
		var ya := plot.position.y + plot.size.y * (1.0 - (float(sample.get("alpha", 0.0)) - y_min) / span)
		maxeig_pts.append(Vector2(x, ym))
		alpha_pts.append(Vector2(x, ya))

	var line_color := Color("537778") if _stale else TEAL
	var alpha_color := Color("537778") if _stale else ALPHA_LINE
	if maxeig_pts.size() > 1:
		draw_polyline(maxeig_pts, line_color, 1.5, true)
	if alpha_pts.size() > 1:
		draw_polyline(alpha_pts, alpha_color, 1.2, true)

	# Teaching vertices 0, 0.5, 1.
	for vertex in _vertices:
		var theta := float(vertex.get("theta", 0.0))
		var x := plot.position.x + plot.size.x * theta
		var ym := plot.position.y + plot.size.y * (1.0 - (float(vertex.get("maxeig_M", 0.0)) - y_min) / span)
		draw_circle(Vector2(x, ym), 3.5, MARK if not _stale else MUTED)
		draw_line(Vector2(x, plot.position.y), Vector2(x, plot.end.y), Color(AXIS, 0.45), 1.0)

	# Selected theta marker.
	var sx := plot.position.x + plot.size.x * _selected_theta
	draw_line(Vector2(sx, plot.position.y), Vector2(sx, plot.end.y), Color(MARK, 0.55), 1.0)

	var font := ThemeDB.fallback_font
	draw_string(font, Vector2(plot.position.x, plot.end.y + 16), "θ = 0", HORIZONTAL_ALIGNMENT_LEFT, -1, 11, MUTED)
	draw_string(font, Vector2(plot.position.x + plot.size.x * 0.5 - 12, plot.end.y + 16), "0.5", HORIZONTAL_ALIGNMENT_LEFT, -1, 11, MUTED)
	draw_string(font, Vector2(plot.end.x - 28, plot.end.y + 16), "θ = 1", HORIZONTAL_ALIGNMENT_LEFT, -1, 11, MUTED)
	draw_string(font, Vector2(plot.position.x + 4, plot.position.y + 14), "maxeig(M)", HORIZONTAL_ALIGNMENT_LEFT, -1, 11, line_color)
	draw_string(font, Vector2(plot.position.x + 4, plot.position.y + 28), "α(A)", HORIZONTAL_ALIGNMENT_LEFT, -1, 11, alpha_color)
