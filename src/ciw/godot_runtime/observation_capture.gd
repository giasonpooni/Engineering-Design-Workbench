extends SceneTree
# Installed render-only worker. No simulation state, physics or checkpoint loader.
const W = 1280
const H = 800
var request: Dictionary
var source_bytes: PackedByteArray
var marker: MeshInstance3D
var point_available = false

func _initialize():
    call_deferred("_capture")

func _digest(raw: PackedByteArray) -> String:
    var hash = HashingContext.new()
    hash.start(HashingContext.HASH_SHA256)
    hash.update(raw)
    return "sha256:" + hash.finish().hex_encode()

func _label(parent: Node, value: String, at: Vector2, width: float, font_size: int, color: Color) -> Label:
    var label = Label.new()
    label.text = value
    label.position = at
    label.size = Vector2(width, 30)
    label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    label.add_theme_font_size_override("font_size", font_size)
    label.add_theme_color_override("font_color", color)
    parent.add_child(label)
    return label

func _material(color: Color) -> StandardMaterial3D:
    var material = StandardMaterial3D.new()
    material.albedo_color = color
    material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    return material

func _line(parent: Node3D, start: Vector3, finish: Vector3, color: Color):
    var mesh = ImmediateMesh.new()
    mesh.surface_begin(Mesh.PRIMITIVE_LINES, _material(color))
    mesh.surface_add_vertex(start)
    mesh.surface_add_vertex(finish)
    mesh.surface_end()
    var instance = MeshInstance3D.new()
    instance.mesh = mesh
    parent.add_child(instance)

func _axis_label(parent: Node3D, name: String, at: Vector3, color: Color):
    var label = Label3D.new()
    label.text = name
    label.font_size = 42
    label.pixel_size = 0.008
    label.modulate = color
    label.outline_size = 5
    label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
    label.position = at
    parent.add_child(label)

func _capture():
    source_bytes = FileAccess.get_file_as_bytes("res://request.json")
    var parsed = JSON.parse_string(source_bytes.get_string_from_utf8())
    if typeof(parsed) != TYPE_DICTIONARY or parsed.get("schema") != "ciw.godot-observation-image-request.v1":
        push_error("Invalid retained observation request")
        quit(2)
        return
    request = parsed
    var version = Engine.get_version_info()
    if [version.major, version.minor, version.patch, version.status] != [4, 5, 2, "stable"] or DisplayServer.get_name() == "headless":
        push_error("Capture requires the selected Godot 4.5.2 renderer, not headless dummy rendering")
        quit(2)
        return
    root.size = Vector2i(W, H)
    var view: Dictionary = request.view
    point_available = view.availability == "present"
    var p = Vector3.ZERO
    if point_available:
        p = Vector3(float(view.position_xyz_m[0]), float(view.position_xyz_m[1]), float(view.position_xyz_m[2]))
    var span = maxf(4.0, maxf(absf(p.x), maxf(absf(p.y), absf(p.z))) * 2.4 + 1.0)
    var control = Control.new()
    control.name = "CaptureLayout"
    control.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(control)
    var background = ColorRect.new()
    background.color = Color(0.035, 0.055, 0.085)
    background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    control.add_child(background)
    var side = ColorRect.new()
    side.position = Vector2(20, 114)
    side.size = Vector2(396, 622)
    side.color = Color(0.06, 0.09, 0.14)
    control.add_child(side)
    var ink = Color(0.88, 0.93, 0.97)
    var muted = Color(0.57, 0.67, 0.76)
    var accent = Color(0.38, 0.87, 0.78)
    _label(control, "NOTATIONS ENGINEERING TERMINAL  /  DERIVED IMAGE EVIDENCE", Vector2(30, 22), 1220, 17, accent)
    _label(control, "Selected observation, not world truth", Vector2(30, 52), 1220, 30, ink)
    _label(control, str(view.observer.observer_id), Vector2(40, 135), 356, 24, ink)
    _label(control, str(view.observer.kind).replace("_", " "), Vector2(40, 173), 356, 16, muted)
    _label(control, "AVAILABLE SAMPLE" if point_available else "POSITION UNAVAILABLE", Vector2(40, 220), 356, 18, accent)
    _label(control, "Sample time: " + str(view.sample_time_s) + " s\nDelivered at: " + str(view.available_at.time_s) + " s", Vector2(40, 256), 356, 19, ink)
    var values = "No XYZ marker is drawn.\nMissing axes are not filled."
    if point_available:
        values = "x   " + str(view.position_xyz_m[0]) + " m\ny   " + str(view.position_xyz_m[1]) + " m\nz   " + str(view.position_xyz_m[2]) + " m"
    _label(control, values, Vector2(40, 332), 356, 22, ink)
    _label(control, "FRAME  godot / Y-up / metres\nENTITY  " + str(view.source.entity_id), Vector2(40, 454), 356, 16, muted)
    _label(control, "SOURCE OBSERVATION EXECUTION", Vector2(40, 532), 356, 13, accent)
    _label(control, str(view.source.execution_id), Vector2(40, 559), 350, 14, muted)
    _label(control, "No simulation worker is executed.\nThe marker is visual, not a physical body.\nFloat32 display; retained values unchanged.", Vector2(40, 636), 350, 14, muted)
    var container = SubViewportContainer.new()
    container.position = Vector2(438, 114)
    container.size = Vector2(820, 622)
    container.stretch = true
    control.add_child(container)
    var viewport = SubViewport.new()
    viewport.size = Vector2i(820, 622)
    viewport.own_world_3d = true
    viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
    container.add_child(viewport)
    var world = Node3D.new()
    world.name = "ObservationGeometry"
    viewport.add_child(world)
    var environment = WorldEnvironment.new()
    var env = Environment.new()
    env.background_mode = Environment.BG_COLOR
    env.background_color = Color(0.045, 0.07, 0.105)
    environment.environment = env
    world.add_child(environment)
    for index in range(-4, 5):
        var coord = index * span / 8.0
        _line(world, Vector3(-span / 2, 0, coord), Vector3(span / 2, 0, coord), Color(0.14, 0.20, 0.26))
        _line(world, Vector3(coord, 0, -span / 2), Vector3(coord, 0, span / 2), Color(0.14, 0.20, 0.26))
    var end = span * 0.43
    var red = Color(0.96, 0.40, 0.35)
    var green = Color(0.47, 0.87, 0.55)
    var blue = Color(0.38, 0.65, 0.98)
    _line(world, Vector3.ZERO, Vector3(end, 0, 0), red)
    _line(world, Vector3.ZERO, Vector3(0, end, 0), green)
    _line(world, Vector3.ZERO, Vector3(0, 0, end), blue)
    _axis_label(world, "+X", Vector3(end, 0, 0), red)
    _axis_label(world, "+Y", Vector3(0, end, 0), green)
    _axis_label(world, "+Z", Vector3(0, 0, end), blue)
    if point_available:
        marker = MeshInstance3D.new()
        marker.name = "SelectedObservedPosition"
        var sphere = SphereMesh.new()
        sphere.radius = span / 60.0
        sphere.height = 2 * sphere.radius
        marker.mesh = sphere
        marker.material_override = _material(accent)
        marker.position = p
        world.add_child(marker)
        _line(world, Vector3.ZERO, p, accent)
        # A leader locates the marker, not a trajectory or interpolated path.
    else:
        _label(control, "No position was available to this observer.", Vector2(492, 381), 730, 24, ink)
    var camera = Camera3D.new()
    camera.projection = Camera3D.PROJECTION_ORTHOGONAL
    camera.size = span
    camera.far = maxf(100.0, span * 6)
    world.add_child(camera)
    var focus = p * 0.5 if point_available else Vector3.ZERO
    var direction = Vector3(0, 0, 1) if request.camera == "front" else Vector3(6, 4, 7).normalized()
    camera.position = focus + direction * span * 2
    camera.look_at(focus, Vector3.UP)
    camera.current = true
    _label(control, str(request.camera).to_upper() + " VIEW  /  leader line is not a trajectory  /  grid spacing " + str(span / 8) + " m", Vector2(451, 122), 790, 14, muted)
    _label(control, "Image from retained observations only. No physics, calibration, verification or state admission.", Vector2(30, 757), 1220, 16, muted)
    # Capture only after the real renderer has updated both viewports and layout.
    await RenderingServer.frame_post_draw
    await process_frame
    await RenderingServer.frame_post_draw
    var image = root.get_texture().get_image()
    image.convert(Image.FORMAT_RGB8)
    if image.get_width() != W or image.get_height() != H or image.save_png("res://image.png") != OK:
        push_error("Native viewport image did not meet output contract")
        quit(2)
        return
    var position_value = null
    if point_available:
        position_value = [marker.global_position.x, marker.global_position.y, marker.global_position.z]
    var report = {"schema": "ciw.godot-observation-image-native.v1", "request_id": request.request_id,
        "request_sha256": _digest(source_bytes), "pid": OS.get_process_id(), "engine_version": version.string,
        "version": [version.major, version.minor, version.patch, version.status],
        "display_server": DisplayServer.get_name(), "rendering_method": RenderingServer.get_current_rendering_method(),
        "video_adapter": RenderingServer.get_video_adapter_name(),
        "image_sha256": _digest(FileAccess.get_file_as_bytes("res://image.png")), "width": W, "height": H,
        "camera": request.camera, "marker_count": 1 if point_available else 0,
        "position_xyz_m": position_value, "input_unchanged": FileAccess.get_file_as_bytes("res://request.json") == source_bytes}
    var file = FileAccess.open("res://observed.json", FileAccess.WRITE)
    file.store_string(JSON.stringify(report, "", true, true))
    file.close()
    quit(0)
