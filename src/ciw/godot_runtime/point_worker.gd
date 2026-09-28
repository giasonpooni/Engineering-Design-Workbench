extends SceneTree
## Bounded headless point model, not Godot's rigid-body/contact solver.
## State lives in this process. stdin is little-endian length + UTF-8 JSON.
const LIMIT := 65536
const MAX_TICKS := 128
var body := Node3D.new()
var velocity := Vector3.ZERO
var gravity := Vector3.ZERO
var tick := 0
var revision := 0
var queued: Array = []
var history: Array = []
var config_ref := ""
var owner := ""
var simulation := ""
var phase := "created"
var configured := false

func _initialize() -> void:
    root.add_child(body)
    call_deferred("serve")

func exact(n: int) -> PackedByteArray:
    var output := PackedByteArray()
    while output.size() < n:
        var part := OS.read_buffer_from_stdin(n - output.size())
        if part.is_empty():
            return PackedByteArray()
        output.append_array(part)
    return output

func xyz(v: Vector3) -> Array:
    return [v.x, v.y, v.z]

func vector(a: Array) -> Vector3:
    return Vector3(float(a[0]), float(a[1]), float(a[2]))

func finite_vector(v: Variant) -> bool:
    return typeof(v) == TYPE_VECTOR3 and v.is_finite()

func snapshot() -> PackedByteArray:
    # Native Variant bytes preserve float32 Vector3 values and integer revisions.
    # No owner, PID or wall-clock value is part of continuation state.
    return var_to_bytes([config_ref, tick, revision, body.position, velocity, queued, history])

func meta() -> Dictionary:
    return {"owner_id": owner, "simulation_id": simulation, "tick": tick,
            "state_revision": revision, "phase": phase}

func restore_state(raw: PackedByteArray) -> bool:
    if raw.size() > 32768:
        return false
    # bytes_to_var does NOT enable object deserialization.
    var s: Variant = bytes_to_var(raw)
    if typeof(s) != TYPE_ARRAY or s.size() != 7:
        return false
    if s[0] != config_ref or typeof(s[1]) != TYPE_INT or typeof(s[2]) != TYPE_INT:
        return false
    if s[1] < 0 or s[1] > MAX_TICKS or s[2] < s[1] or s[2] > 1024:
        return false
    if not finite_vector(s[3]) or not finite_vector(s[4]):
        return false
    if typeof(s[5]) != TYPE_ARRAY or s[5].size() > 16:
        return false
    for item in s[5]:
        if typeof(item) != TYPE_ARRAY or item.size() != 2:
            return false
        if typeof(item[0]) != TYPE_INT or item[0] <= s[1] or item[0] > MAX_TICKS or not finite_vector(item[1]):
            return false
    if typeof(s[6]) != TYPE_ARRAY or s[6].size() != s[1] + 1:
        return false
    for i in range(s[6].size()):
        var row: Variant = s[6][i]
        if typeof(row) != TYPE_ARRAY or row.size() != 3 or row[0] != i:
            return false
        if typeof(row[0]) != TYPE_INT or not finite_vector(row[1]) or not finite_vector(row[2]):
            return false
    if s[6][-1][1] != s[3] or s[6][-1][2] != s[4] or var_to_bytes(s) != raw:
        return false
    tick = s[1]
    revision = s[2]
    body.position = s[3]
    velocity = s[4]
    queued = s[5]
    history = s[6]
    phase = "paused"
    return true

func apply(action: String, args: Dictionary) -> Dictionary:
    if action == "configure" and not configured:
        var config: Dictionary = args["configuration"]
        if int(config["step_hz"]) != 64 or int(config["max_ticks"]) != MAX_TICKS:
            return {"error": "unsupported clock configuration"}
        body.position = vector(config["p0_m"])
        velocity = vector(config["v0_m_s"])
        gravity = vector(config["gravity_m_s2"])
        config_ref = args["configuration_ref"]
        owner = args["owner_id"]
        simulation = args["simulation_id"]
        history = [[0, body.position, velocity]]
        configured = true
        var version := Engine.get_version_info()
        return {"meta": meta(), "engine_version": version["string"],
                "version": [version["major"], version["minor"], version["patch"], version["status"]]}
    if not configured:
        return {"error": "not configured"}
    if action == "identity":
        return meta()
    if action == "snapshot":
        return {"snapshot_b64": Marshalls.raw_to_base64(snapshot())}
    if action == "restore":
        if phase != "created" or revision != 0:
            return {"error": "restore needs a fresh owner"}
        if not restore_state(Marshalls.base64_to_raw(args["snapshot_b64"])):
            return {"error": "invalid native checkpoint"}
        return meta()
    if action == "lifecycle":
        var verb: String = args["action"]
        var allowed := {"start": ["created"], "pause": ["running"], "resume": ["paused"],
                        "stop": ["created", "running", "paused", "stopped"]}
        if not allowed.has(verb) or not phase in allowed[verb]:
            return {"error": "invalid native lifecycle"}
        phase = {"start": "running", "pause": "paused", "resume": "running", "stop": "stopped"}[verb]
        return meta()
    if action == "step":
        if phase != "running" or float(args["dt"]) != 1.0 / 64.0 or tick >= MAX_TICKS:
            return {"error": "step outside declared boundary"}
        tick += 1
        var remaining: Array = []
        for event in queued:
            if event[0] == tick:
                velocity += event[1]
            else:
                remaining.append(event)
        queued = remaining
        velocity += gravity / 64.0
        body.position += velocity / 64.0
        revision += 1
        history.append([tick, body.position, velocity])
        return meta()
    if action == "intervene":
        if not phase in ["paused", "running"] or args["operation"] != "projectile.queue-impulse.v1" or args["target"] != "projectile":
            return {"error": "unsupported native intervention"}
        var at := int(args["parameters"]["at_tick"])
        if at <= tick or at > MAX_TICKS or queued.size() >= 16:
            return {"error": "impulse outside queue budget"}
        queued.append([at, vector(args["parameters"]["delta_v_m_s"])])
        revision += 1
        return meta()
    if action == "observe":
        var selected: Dictionary = args["observer"]
        var debug: bool = selected["kind"] == "debugger"
        var delay := 0 if debug or selected["kind"] == "retrospective_narrator" else 2
        var samples: Array = []
        var last := tick - delay
        for i in range(maxi(0, last - 31), last + 1):
            var row: Array = history[i]
            for channel in selected["channels"]:
                var component: int = ["x", "y", "z"].find(channel.right(1))
                if component < 0 or (not debug and not channel.begins_with("position_")):
                    return {"error": "observer channel unavailable"}
                var v: Vector3 = row[1] if channel.begins_with("position_") else row[2]
                samples.append({"tick": i, "quantity": channel, "value": v[component]})
        return {"meta": meta(), "samples": samples}
    return {"error": "unknown native operation"}

func serve() -> void:
    while true:
        var header := exact(4)
        if header.is_empty():
            break
        var length := header.decode_u32(0)
        if length < 1 or length > LIMIT:
            break
        var data := exact(length)
        if data.is_empty():
            break
        var parser := JSON.new()
        if parser.parse(data.get_string_from_utf8()) != OK or typeof(parser.data) != TYPE_DICTIONARY:
            break
        var request: Dictionary = parser.data
        if request.get("schema") != "ciw.godot-rpc.v1":
            break
        var action: String = request["action"]
        var result := {"closed": true} if action == "shutdown" else apply(action, request["arguments"])
        var response := {"schema": "ciw.godot-rpc-result.v1", "request_id": request["request_id"],
                         "action": action, "pid": OS.get_process_id(), "data": result}
        print("NET_SIM " + JSON.stringify(response, "", true, true))
        if action == "shutdown":
            break
    quit(0)
