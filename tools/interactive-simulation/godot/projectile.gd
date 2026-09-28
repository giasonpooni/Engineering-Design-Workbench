extends SceneTree
## Independent Godot-owned point-projectile experiment, not rigid-body physics.
## Imports the actual GLB through GLTFDocument and records post-step Vector3 state.

func _initialize() -> void:
    call_deferred("run_experiment")

func fail(message: String) -> void:
    push_error(message)
    quit(2)

func coords(v: Vector3) -> Array:
    return [v.x, v.y, v.z]

func vec(values: Array) -> Vector3:
    return Vector3(float(values[0]), float(values[1]), float(values[2]))

func sample(tick: int, hz: int, p: Vector3, v: Vector3) -> Dictionary:
    return {"tick": tick, "time_s": float(tick) / hz, "entity": "projectile", "p_m": coords(p), "v_m_s": coords(v)}

func run_experiment() -> void:
    var args := OS.get_cmdline_user_args()
    if args.size() != 3:
        fail("expected request.json scene.glb trace.json")
        return
    var request_path: String = args[0]
    var asset_path: String = args[1]
    var output_path: String = args[2]
    if FileAccess.file_exists(output_path):
        fail("trace output already exists")
        return
    var parser := JSON.new()
    if parser.parse(FileAccess.get_file_as_string(request_path)) != OK:
        fail("invalid request JSON")
        return
    var request: Dictionary = parser.data
    var scenario: Dictionary = request["scenario"]
    var hz: int = int(scenario["step_hz"])
    var ticks: int = int(scenario["ticks"])
    if hz < 30 or hz > 1000 or ticks < 1 or ticks > 2000:
        fail("tick budget exceeded")
        return
    var asset_digest := "sha256:" + FileAccess.get_sha256(asset_path)
    if asset_digest != request["asset_sha256"]:
        fail("asset digest mismatch")
        return
    var document := GLTFDocument.new()
    var state := GLTFState.new()
    if document.append_from_file(asset_path, state) != OK:
        fail("GLB import failed")
        return
    var scene := document.generate_scene(state)
    if scene == null:
        fail("GLB scene generation failed")
        return
    root.add_child(scene)
    var landmarks := {}
    for name in ["origin", "axis_x", "axis_y", "axis_z"]:
        var marker := scene.find_child(name, true, false) as Node3D
        if marker == null:
            fail("missing imported marker " + name)
            return
        landmarks[name] = coords(marker.global_position)
    var sphere := scene.find_child("projectile", true, false) as MeshInstance3D
    if sphere == null or sphere.mesh == null:
        fail("missing imported projectile mesh")
        return
    var count := 0
    for surface in range(sphere.mesh.get_surface_count()):
        var arrays := sphere.mesh.surface_get_arrays(surface)
        count += arrays[Mesh.ARRAY_VERTEX].size()
    var bounds := sphere.mesh.get_aabb()
    var p := vec(scenario["p0_m"])
    var v := vec(scenario["v0_m_s"])
    var gravity := vec(scenario["gravity_m_s2"])
    if request["fault"] == "double-gravity":
        gravity *= 2.0 # Explicit diagnostic fixture, retained in implementation request.
    elif request["fault"] != "none":
        fail("unsupported diagnostic fault")
        return
    var observations: Array = [sample(0, hz, p, v)]
    var events: Array = []
    for tick in range(1, ticks + 1):
        for event in scenario["inputs"]:
            if int(event["tick"]) == tick:
                v += vec(event["delta_v_m_s"])
                events.append({"id": event["id"], "requested_tick": tick, "applied_tick": tick,
                               "delta_v_m_s": event["delta_v_m_s"]})
        # Semi-implicit Euler. Godot's RigidBody/contact solver is not involved.
        v += gravity / hz
        p += v / hz
        sphere.global_position = p
        observations.append(sample(tick, hz, p, v))
    var trace := {"engine": "godot", "engine_version": Engine.get_version_info()["string"],
                  "state_owner": "godot", "clock": "integer-ticks", "phase": "initial_then_post_step",
                  "precision": "Vector3-float32", "request_sha256": "sha256:" + FileAccess.get_sha256(request_path),
                  "asset_sha256": asset_digest, "import_report": {"landmarks_m": landmarks,
                  "vertex_count": count, "bounds_min_m": coords(bounds.position), "bounds_max_m": coords(bounds.end)},
                  "observations": observations, "events": events, "complete": true}
    var output := FileAccess.open(output_path, FileAccess.WRITE)
    if output == null:
        fail("cannot open trace output")
        return
    output.store_string(JSON.stringify(trace, "", true, true))
    output.flush()
    output.close()
    quit(0)
