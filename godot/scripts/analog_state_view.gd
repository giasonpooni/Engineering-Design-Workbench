extends SubViewportContainer
## 3D analog state: host-supplied ellipsoid + trajectories. No A or P recomputed here.
var _viewport: SubViewport
var _world: Node3D
var _camera: Camera3D
var _surface: MeshInstance3D
var _renewal: MeshInstance3D
var _gap: MeshInstance3D
var _marker: MeshInstance3D
var _axes: MeshInstance3D
var _labels: Array[Label3D] = []
var _renewal_points: PackedVector3Array = []
var _gap_points: PackedVector3Array = []
var _center := Vector3.ZERO
var _radius := 4.0
var _base_radius := 4.0
var _yaw := 0.65
var _pitch := 0.42
var _stale := true


func _ready() -> void:
	stretch = true
	custom_minimum_size = Vector2(300, 270)
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	_viewport = SubViewport.new()
	_viewport.size = Vector2i(640, 400)
	_viewport.own_world_3d = true
	_viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	add_child(_viewport)
	_world = Node3D.new()
	_viewport.add_child(_world)
	var environment := WorldEnvironment.new()
	var settings := Environment.new()
	settings.background_mode = Environment.BG_COLOR
	settings.background_color = Color("0c1521")
	environment.environment = settings
	_world.add_child(environment)
	_camera = Camera3D.new()
	_camera.current = true
	_camera.near = 0.01
	_camera.far = 1000
	_camera.fov = 45
	_world.add_child(_camera)
	_surface = MeshInstance3D.new()
	_renewal = MeshInstance3D.new()
	_gap = MeshInstance3D.new()
	_axes = MeshInstance3D.new()
	_marker = MeshInstance3D.new()
	for item in [_surface, _renewal, _gap, _axes, _marker]:
		_world.add_child(item)
	_surface.material_override = _material(Color(0.24, 0.42, 0.66, 0.36), true)
	_renewal.material_override = _material(Color("60dfcd"))
	_gap.material_override = _material(Color("7f9bb8"))
	_axes.material_override = _material(Color("4e647e"))
	_marker.material_override = _material(Color("ffcc80"))
	_marker.visible = false
	_update_camera()


func _material(color: Color, transparent: bool = false) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.albedo_color = color
	if transparent:
		material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	return material


func _vector(value: Array) -> Vector3:
	return Vector3(float(value[0]), float(value[1]), float(value[2]))


func clear_view() -> void:
	_surface.mesh = null
	_renewal.mesh = null
	_gap.mesh = null
	_axes.mesh = null
	_marker.visible = false
	_renewal_points.clear()
	_gap_points.clear()
	for label in _labels:
		label.queue_free()
	_labels.clear()


func set_render(data: Dictionary) -> void:
	clear_view()
	var ellipsoid: Dictionary = data.get("ellipsoid", {})
	var vertices := PackedVector3Array()
	var low := Vector3(INF, INF, INF)
	var high := Vector3(-INF, -INF, -INF)
	for value in ellipsoid.get("vertices", []):
		var point := _vector(value)
		vertices.append(point)
		low = low.min(point)
		high = high.max(point)
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_INDEX] = PackedInt32Array(ellipsoid.get("indices", []))
	var mesh := ArrayMesh.new()
	if not vertices.is_empty() and not arrays[Mesh.ARRAY_INDEX].is_empty():
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	_surface.mesh = mesh

	var trajectories: Dictionary = data.get("trajectories", {})
	_renewal_points = _path_points(trajectories.get("renewal", {}).get("points", []))
	_gap_points = _path_points(trajectories.get("gap", {}).get("points", []))
	for point in _renewal_points:
		low = low.min(point)
		high = high.max(point)
	for point in _gap_points:
		low = low.min(point)
		high = high.max(point)
	_renewal.mesh = _line_strip(_renewal_points)
	_gap.mesh = _line_strip(_gap_points)

	var labels: Array = data.get("state_names", ["c", "m", "g"])
	if not _renewal_points.is_empty() or not _gap_points.is_empty() or not vertices.is_empty():
		_center = (low + high) * 0.5
		_base_radius = maxf((high - low).length() * 1.05, 1.0)
		_radius = _base_radius
		var sphere := SphereMesh.new()
		sphere.radius = _base_radius * 0.007
		sphere.height = sphere.radius * 2
		_marker.mesh = sphere
		_build_axes(low, high, labels)
		_update_camera()
	set_stale(_stale)


func _path_points(values: Array) -> PackedVector3Array:
	var points := PackedVector3Array()
	for value in values:
		points.append(_vector(value))
	return points


func _line_strip(points: PackedVector3Array) -> ImmediateMesh:
	var path := ImmediateMesh.new()
	if points.size() > 1:
		path.surface_begin(Mesh.PRIMITIVE_LINE_STRIP)
		for point in points:
			path.surface_add_vertex(point)
		path.surface_end()
	return path


func _build_axes(low: Vector3, high: Vector3, labels: Array) -> void:
	for label in _labels:
		label.queue_free()
	_labels.clear()
	var axis_mesh := ImmediateMesh.new()
	axis_mesh.surface_begin(Mesh.PRIMITIVE_LINES)
	var corners := [Vector3(high.x, low.y, low.z), Vector3(low.x, high.y, low.z), Vector3(low.x, low.y, high.z)]
	for index in range(3):
		axis_mesh.surface_add_vertex(low)
		axis_mesh.surface_add_vertex(corners[index])
		var label := Label3D.new()
		label.text = str(labels[index]) if index < labels.size() else ""
		label.font_size = 28
		label.pixel_size = _base_radius * 0.0013
		label.modulate = Color("a4b4c8")
		label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		label.position = corners[index]
		_world.add_child(label)
		_labels.append(label)
	for step in range(1, 6):
		var fraction := float(step) / 6.0
		var x := lerpf(low.x, high.x, fraction)
		var z := lerpf(low.z, high.z, fraction)
		axis_mesh.surface_add_vertex(Vector3(x, low.y, low.z))
		axis_mesh.surface_add_vertex(Vector3(x, low.y, high.z))
		axis_mesh.surface_add_vertex(Vector3(low.x, low.y, z))
		axis_mesh.surface_add_vertex(Vector3(high.x, low.y, z))
	axis_mesh.surface_end()
	_axes.mesh = axis_mesh


func set_sample(index: int) -> void:
	_marker.visible = index >= 0 and index < _renewal_points.size()
	if _marker.visible:
		_marker.position = _renewal_points[index]


func set_stale(value: bool) -> void:
	_stale = value
	if _renewal != null:
		_renewal.material_override = _material(Color("537778") if value else Color("60dfcd"))
	if _gap != null:
		_gap.material_override = _material(Color("537778") if value else Color("7f9bb8"))


func _update_camera() -> void:
	_camera.position = _center + Vector3(sin(_yaw) * cos(_pitch), sin(_pitch), cos(_yaw) * cos(_pitch)) * _radius
	_camera.look_at(_center, Vector3.UP)


func _gui_input(event: InputEvent) -> void:
	if _stale:
		return
	if event is InputEventMouseMotion and (event.button_mask & MOUSE_BUTTON_MASK_LEFT or event.button_mask & MOUSE_BUTTON_MASK_RIGHT):
		_yaw -= event.relative.x * 0.008
		_pitch = clampf(_pitch + event.relative.y * 0.006, -0.1, 1.45)
		_update_camera()
		accept_event()
	elif event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP:
			_radius = maxf(_radius * 0.9, _base_radius * 0.3)
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			_radius = minf(_radius * 1.1, _base_radius * 4.0)
		else:
			return
		_update_camera()
		accept_event()
