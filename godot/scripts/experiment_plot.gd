extends Control
## Display native points, declared plane geometry, a declared mesh wireframe,
## or samples on a retained parameter axis.
## No fit, interpolation, or measurement is performed here.
var panel: Dictionary = {}


func set_panel(value: Dictionary) -> void:
	panel = value
	queue_redraw()


func _draw() -> void:
	var render: Dictionary = panel.get("render", {}) if not panel.is_empty() else {}
	var kind := str(render.get("kind", ""))
	if kind == "plane2d":
		# Retained sample identities. Never honor render.connect.
		_draw_plane(render)
		return
	if kind == "mesh":
		_draw_mesh(render)
		return
	if kind == "strip":
		# Declared parameter samples. Never honor render.connect.
		_draw_strip(render)
		return
	_draw_categorical()


func _draw_categorical() -> void:
	var font := ThemeDB.fallback_font
	var color := Color("60dfcd")
	if panel.is_empty():
		draw_string(font, Vector2(20, 40), "Select a retained experiment", HORIZONTAL_ALIGNMENT_LEFT, -1, 16)
		return
	var values: Array = panel.get("values", [])
	var units: Array = panel.get("units", [])
	if values.is_empty() or units.size() != values.size():
		return
	for unit in units:
		if unit != units[0]:
			draw_string(font, Vector2(20, 40), "Mixed units: inspect the numeric table", HORIZONTAL_ALIGNMENT_LEFT, -1, 16)
			return
	var deviations: Variant = panel.get("marginal_standard_deviation")
	var lower := INF
	var upper := -INF
	for i in values.size():
		var sigma := float(deviations[i]) if deviations is Array else 0.0
		lower = minf(lower, float(values[i]) - sigma)
		upper = maxf(upper, float(values[i]) + sigma)
	if not is_finite(upper - lower):
		draw_string(font, Vector2(20, 40), "Display range overflow: inspect the numeric table", HORIZONTAL_ALIGNMENT_LEFT, -1, 14)
		return
	var extent := maxf(upper - lower, maxf(absf(upper), 1.0) * 0.1)
	lower -= extent * 0.15
	upper += extent * 0.15
	if not is_finite(upper - lower):
		draw_string(font, Vector2(20, 40), "Display range overflow: inspect the numeric table", HORIZONTAL_ALIGNMENT_LEFT, -1, 14)
		return
	var plot := Rect2(72, 28, maxf(size.x - 92, 20), maxf(size.y - 95, 40))
	for j in 5:
		var fraction := float(j) / 4.0
		var y := plot.end.y - fraction * plot.size.y
		draw_line(Vector2(plot.position.x, y), Vector2(plot.end.x, y), Color("273549"))
		draw_string(font, Vector2(2, y + 4), String.num_scientific(lerpf(lower, upper, fraction)), HORIZONTAL_ALIGNMENT_RIGHT, 62, 12)
	for i in values.size():
		# Equally spaced categorical positions, explicitly labeled. Event times
		# remain labels/context; sample order never implies a temporal trajectory.
		var x := plot.position.x + plot.size.x * (float(i) + 0.5) / values.size()
		var y := plot.end.y - (float(values[i]) - lower) / (upper - lower) * plot.size.y
		if deviations is Array:
			var dy := float(deviations[i]) / (upper - lower) * plot.size.y
			draw_line(Vector2(x, y - dy), Vector2(x, y + dy), color, 2)
			for end in [y - dy, y + dy]:
				draw_line(Vector2(x - 5, end), Vector2(x + 5, end), color, 2)
		draw_circle(Vector2(x, y), 4, color)
		var label := str(panel.labels[i])
		if values.size() > 4:
			label = "row %s" % (i + 1)
		if label.length() > 20:
			label = label.left(17) + "..."
		draw_string(font, Vector2(x - 65, plot.end.y + 22), label, HORIZONTAL_ALIGNMENT_CENTER, 130, 11)
	draw_string(font, Vector2(8, 18), str(units[0]), HORIZONTAL_ALIGNMENT_LEFT, -1, 12)
	draw_string(font, Vector2(72, size.y - 15), "Declared order · points only · " + ("marginal ±1σ" if deviations is Array else "covariance not supplied"), HORIZONTAL_ALIGNMENT_LEFT, -1, 12)


func _plot_rect() -> Rect2:
	return Rect2(72, 28, maxf(size.x - 92, 20), maxf(size.y - 95, 40))


func _bounds(points: Array) -> Rect2:
	var low := Vector2(INF, INF)
	var high := Vector2(-INF, -INF)
	for point in points:
		low = low.min(point)
		high = high.max(point)
	var span := high - low
	span.x = maxf(span.x, 0.05)
	span.y = maxf(span.y, 0.05)
	# Keep the declared plane isotropic so a circle stays a circle.
	var extent := maxf(span.x, span.y)
	var center := (low + high) * 0.5
	return Rect2(center - Vector2(extent, extent) * 0.6, Vector2(extent, extent) * 1.2)


func _map(point: Vector2, world: Rect2, plot: Rect2) -> Vector2:
	var fraction := (point - world.position) / world.size
	return Vector2(plot.position.x + fraction.x * plot.size.x, plot.end.y - fraction.y * plot.size.y)


func _draw_axes(world: Rect2, plot: Rect2, unit: String, caption: String) -> void:
	var font := ThemeDB.fallback_font
	draw_rect(plot, Color("0c1521"))
	for step in 5:
		var fraction := float(step) / 4.0
		var x := plot.position.x + fraction * plot.size.x
		var y := plot.end.y - fraction * plot.size.y
		draw_line(Vector2(x, plot.position.y), Vector2(x, plot.end.y), Color("273549"))
		draw_line(Vector2(plot.position.x, y), Vector2(plot.end.x, y), Color("273549"))
		draw_string(font, Vector2(x - 24, plot.end.y + 18), String.num_scientific(world.position.x + world.size.x * fraction), HORIZONTAL_ALIGNMENT_CENTER, 48, 11)
		draw_string(font, Vector2(2, y + 4), String.num_scientific(world.position.y + world.size.y * fraction), HORIZONTAL_ALIGNMENT_RIGHT, 62, 11)
	draw_string(font, Vector2(8, 18), unit, HORIZONTAL_ALIGNMENT_LEFT, -1, 12)
	draw_string(font, Vector2(72, size.y - 15), caption, HORIZONTAL_ALIGNMENT_LEFT, -1, 12)


func _declared_frame(render: Dictionary) -> String:
	var frame: Variant = render.get("frame", "")
	if typeof(frame) == TYPE_DICTIONARY:
		return str(frame.get("id", frame.get("frame_id", "")))
	return str(frame)


func _axis_unit(render: Dictionary) -> String:
	var unit := str(render.get("unit", render.get("value_unit", "")))
	var frame := _declared_frame(render)
	if not unit.is_empty() and not frame.is_empty():
		return unit + " · " + frame
	return unit if not unit.is_empty() else frame


func _canvas_caption(render: Dictionary, fallback: String) -> String:
	var title := str(render.get("canvas_title", panel.get("title", "")))
	var frame := _declared_frame(render)
	if title.is_empty():
		return fallback if frame.is_empty() else fallback + " · " + frame
	if not frame.is_empty() and title.find(frame) < 0:
		return title + " · " + frame + " · points only · display only"
	return title + " · points only · display only"


func _declared_circle(overlay: Variant) -> bool:
	return overlay is Dictionary and overlay.get("kind") == "declared_circle" and overlay.get("source") == "declared_constraint"


func _draw_canvas_id(render: Dictionary, plot: Rect2) -> void:
	var identity := str(render.get("canvas_id", panel.get("panel_id", "")))
	if identity.is_empty():
		return
	draw_string(ThemeDB.fallback_font, Vector2(plot.end.x - 170, 18), identity, HORIZONTAL_ALIGNMENT_RIGHT, 160, 11)


func _draw_plane(render: Dictionary) -> void:
	var font := ThemeDB.fallback_font
	var points: Array = render.get("points", [])
	if points.is_empty():
		draw_string(font, Vector2(20, 40), "Plane render has no retained points", HORIZONTAL_ALIGNMENT_LEFT, -1, 14)
		return
	var samples: Array[Vector2] = []
	var kept: Array = []
	for item in points:
		if typeof(item) != TYPE_DICTIONARY:
			continue
		if not is_finite(float(item.get("x", NAN))) or not is_finite(float(item.get("y", NAN))):
			continue
		samples.append(Vector2(float(item.x), float(item.y)))
		kept.append(item)
	if samples.is_empty():
		draw_string(font, Vector2(20, 40), "Plane render has no finite declared points", HORIZONTAL_ALIGNMENT_LEFT, -1, 14)
		return
	var extras: Array[Vector2] = []
	for overlay in render.get("overlays", []):
		if not _declared_circle(overlay):
			continue
		var center := Vector2(float(overlay.center[0]), float(overlay.center[1]))
		var radius := float(overlay.radius)
		extras.append(center)
		extras.append(center + Vector2(radius, 0))
		extras.append(center - Vector2(radius, 0))
		extras.append(center + Vector2(0, radius))
		extras.append(center - Vector2(0, radius))
	var world := _bounds(samples + extras)
	var plot := _plot_rect()
	_draw_axes(world, plot, _axis_unit(render), _canvas_caption(render, "Declared plane · points only · no interpolation"))
	_draw_canvas_id(render, plot)
	for overlay in render.get("overlays", []):
		if not _declared_circle(overlay):
			continue
		var center := _map(Vector2(float(overlay.center[0]), float(overlay.center[1])), world, plot)
		var radius := float(overlay.radius) / world.size.x * plot.size.x
		draw_arc(center, radius, 0.0, TAU, 64, Color(0.38, 0.48, 0.62, 0.9), 1.5)
		var name := str(overlay.get("overlay_title", overlay.get("constraint_id", "")))
		if not name.is_empty():
			draw_string(font, center + Vector2(radius + 6, -6), name, HORIZONTAL_ALIGNMENT_LEFT, -1, 11)
	for i in samples.size():
		var point := _map(samples[i], world, plot)
		draw_circle(point, 4, Color("60dfcd"))
		var name := ""
		if i == 0:
			name = str(render.get("start_label", kept[i].get("label", "")))
		elif i == samples.size() - 1:
			name = str(render.get("end_label", kept[i].get("label", "")))
		elif samples.size() <= 8:
			name = str(kept[i].get("label", i + 1))
		if not name.is_empty():
			draw_string(font, point + Vector2(6, -6), name, HORIZONTAL_ALIGNMENT_LEFT, -1, 11)


func _draw_mesh(render: Dictionary) -> void:
	var font := ThemeDB.fallback_font
	var vertices: Array = render.get("vertices", [])
	var triangles: Array = render.get("triangles", [])
	if vertices.is_empty() or triangles.is_empty():
		draw_string(font, Vector2(20, 40), "Mesh render has no declared faces", HORIZONTAL_ALIGNMENT_LEFT, -1, 14)
		return
	var samples: Array[Vector2] = []
	for vertex in vertices:
		if typeof(vertex) != TYPE_ARRAY and typeof(vertex) != TYPE_PACKED_FLOAT32_ARRAY:
			if typeof(vertex) != TYPE_PACKED_FLOAT64_ARRAY:
				continue
		if vertex.size() < 2 or not is_finite(float(vertex[0])) or not is_finite(float(vertex[1])):
			continue
		samples.append(Vector2(float(vertex[0]), float(vertex[1])))
	if samples.is_empty():
		draw_string(font, Vector2(20, 40), "Mesh render has no finite declared vertices", HORIZONTAL_ALIGNMENT_LEFT, -1, 14)
		return
	var world := _bounds(samples)
	var plot := _plot_rect()
	var planar := bool(render.get("declared_planar", true))
	if not render.has("declared_planar"):
		planar = true
		for vertex in vertices:
			if typeof(vertex) in [TYPE_ARRAY, TYPE_PACKED_FLOAT32_ARRAY, TYPE_PACKED_FLOAT64_ARRAY] and vertex.size() > 2 and not is_zero_approx(float(vertex[2])):
				planar = false
				break
	var fallback := "Declared planar mesh · not a surveyed surface" if planar else "Declared mesh · first two axes · not a surveyed surface"
	_draw_axes(world, plot, _axis_unit(render), _canvas_caption(render, fallback))
	_draw_canvas_id(render, plot)
	for face in triangles:
		var a := _map(samples[int(face[0])], world, plot)
		var b := _map(samples[int(face[1])], world, plot)
		var c := _map(samples[int(face[2])], world, plot)
		draw_line(a, b, Color("4e647e"), 1.2)
		draw_line(b, c, Color("4e647e"), 1.2)
		draw_line(c, a, Color("4e647e"), 1.2)
	var path: Array = render.get("path", [])
	for i in range(path.size() - 1):
		var a := int(path[i])
		var b := int(path[i + 1])
		if a < 0 or b < 0 or a >= samples.size() or b >= samples.size():
			continue
		draw_line(_map(samples[a], world, plot), _map(samples[b], world, plot), Color("60dfcd"), 2.4)
	for i in samples.size():
		var mapped := _map(samples[i], world, plot)
		var color := Color("dce6f1")
		var name := ""
		if render.get("source_vertex") != null and int(render.source_vertex) == i:
			color = Color("ffcc80")
			name = str(render.get("source_label", "source %s" % i))
		elif render.get("target_vertex") != null and int(render.target_vertex) == i:
			color = Color("60dfcd")
			name = str(render.get("target_label", "target %s" % i))
		draw_circle(mapped, 4, color)
		if not name.is_empty():
			draw_string(font, mapped + Vector2(6, -6), name, HORIZONTAL_ALIGNMENT_LEFT, -1, 11)


func _draw_strip(render: Dictionary) -> void:
	var font := ThemeDB.fallback_font
	var samples: Array = render.get("samples", [])
	if samples.is_empty():
		draw_string(font, Vector2(20, 40), "Strip render has no retained samples", HORIZONTAL_ALIGNMENT_LEFT, -1, 14)
		return
	var low := Vector2(INF, INF)
	var high := Vector2(-INF, -INF)
	for item in samples:
		if typeof(item) != TYPE_DICTIONARY:
			continue
		if not is_finite(float(item.get("parameter", NAN))) or not is_finite(float(item.get("value", NAN))):
			continue
		var point := Vector2(float(item.parameter), float(item.value))
		low = low.min(point)
		high = high.max(point)
	if not is_finite(low.x) or not is_finite(high.x):
		draw_string(font, Vector2(20, 40), "Strip render has no finite declared samples", HORIZONTAL_ALIGNMENT_LEFT, -1, 14)
		return
	var span := high - low
	span.x = maxf(span.x, 0.05)
	span.y = maxf(span.y, maxf(absf(high.y), 1.0) * 0.1)
	# Independent axes: parameter and value may have different units.
	var world := Rect2(low - span * 0.1, span * 1.2)
	var plot := _plot_rect()
	var parameter := str(render.get("parameter_name", "parameter"))
	var frame := _declared_frame(render)
	var fallback := "Declared %s axis · points only · not event time" % parameter
	if not frame.is_empty():
		fallback = "Declared %s axis · %s · points only · not event time" % [parameter, frame]
	_draw_axes(world, plot, str(render.get("value_unit", "")), _canvas_caption(render, fallback))
	_draw_canvas_id(render, plot)
	var kept: Array = []
	for item in samples:
		if typeof(item) != TYPE_DICTIONARY:
			continue
		if not is_finite(float(item.get("parameter", NAN))) or not is_finite(float(item.get("value", NAN))):
			continue
		draw_circle(_map(Vector2(float(item.parameter), float(item.value)), world, plot), 4, Color("60dfcd"))
		kept.append(item)
	if not kept.is_empty():
		var first: Dictionary = kept[0]
		var last: Dictionary = kept[kept.size() - 1]
		var start_name := str(render.get("start_label", ""))
		var end_name := str(render.get("end_label", ""))
		draw_string(font, _map(Vector2(float(first.parameter), float(first.value)), world, plot) + Vector2(6, -6), start_name, HORIZONTAL_ALIGNMENT_LEFT, -1, 11)
		if kept.size() > 1 and not end_name.is_empty() and end_name != start_name:
			draw_string(font, _map(Vector2(float(last.parameter), float(last.value)), world, plot) + Vector2(6, -6), end_name, HORIZONTAL_ALIGNMENT_LEFT, -1, 11)
	var abscissa := str(render.get("parameter_name", ""))
	var parameter_unit := str(render.get("parameter_unit", ""))
	var right := parameter_unit
	if not abscissa.is_empty() and not parameter_unit.is_empty():
		right = abscissa + " / " + parameter_unit
	elif not abscissa.is_empty():
		right = abscissa
	draw_string(font, Vector2(plot.end.x - 140, size.y - 15), right, HORIZONTAL_ALIGNMENT_RIGHT, 130, 11)
