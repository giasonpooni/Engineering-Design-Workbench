extends SceneTree
## Persistent engine-owned synthetic integer motion. No world tick in _process.
## Same declared model as ReferenceMotion, implemented by the Godot provider.

const LIMIT = 131072
var configured := false
var status := "unconfigured"
var config: Dictionary = {}
var config_ref := ""
var state: Dictionary = {}
var sequence := 0
var body: Node3D
var error := ""

func _initialize() -> void:
	body = Node3D.new()
	body.name = "Body_1"
	root.add_child(body)

func keys_match(value: Variant, expected: Array) -> bool:
	if not value is Dictionary or value.size() != expected.size(): return false
	for key in expected:
		if not value.has(key): return false
	return true

func integer(value: Variant, low: int, high: int) -> bool:
	return typeof(value) in [TYPE_INT, TYPE_FLOAT] and is_finite(float(value)) and float(value) == floor(float(value)) and value >= low and value <= high

func refuse(message: String) -> Dictionary:
	error = message
	return {}

func restore_state(raw: String) -> Dictionary:
	if raw.to_utf8_buffer().size() > 32768: return refuse("Snapshot exceeds budget")
	var parsed: Variant = JSON.parse_string(raw)
	if not keys_match(parsed, ["configuration_ref", "state"]) or parsed.configuration_ref != config_ref:
		return refuse("Snapshot configuration mismatch")
	var s: Variant = parsed.state
	if not keys_match(s, ["tick", "revision", "position", "velocity", "rng", "queued", "history"]):
		return refuse("Incomplete continuation state")
	if not integer(s.tick, 0, 128) or not integer(s.revision, int(s.tick), 1024) or not integer(s.rng, 0, 2147483647):
		return refuse("Snapshot clock or RNG out of range")
	if not integer(s.position, -10000000, 10000000) or not integer(s.velocity, -100000, 100000):
		return refuse("Snapshot motion out of range")
	if not s.history is Array or s.history.size() != int(s.tick) + 1 or not s.queued is Array or s.queued.size() > 16:
		return refuse("Incomplete history or event queue")
	var history: Array = []
	for tick in range(s.history.size()):
		var row: Variant = s.history[tick]
		if not row is Array or row.size() != 3 or not integer(row[0], tick, tick) or not integer(row[1], -10000000, 10000000) or not integer(row[2], -100000, 100000):
			return refuse("Invalid history row")
		history.append([int(row[0]), int(row[1]), int(row[2])])
	if history[0] != [0, 0, 1] or history[-1] != [int(s.tick), int(s.position), int(s.velocity)]:
		return refuse("History differs from current state")
	var queued: Array = []
	for item in s.queued:
		if not keys_match(item, ["at_tick", "delta_v"]) or not integer(item.at_tick, int(s.tick) + 1, 128) or not integer(item.delta_v, -20, 20):
			return refuse("Invalid queued impulse")
		queued.append({"at_tick": int(item.at_tick), "delta_v": int(item.delta_v)})
	return {"tick": int(s.tick), "revision": int(s.revision), "position": int(s.position), "velocity": int(s.velocity), "rng": int(s.rng), "queued": queued, "history": history}

func dispatch(operation: String, args: Dictionary) -> Dictionary:
	if operation == "init":
		if configured or not keys_match(args, ["seed", "configuration_ref"]) or not integer(args.seed, 0, 2147483647) or not args.configuration_ref is String:
			return refuse("Invalid initialization")
		config = {"seed": int(args.seed), "tick_s": 1, "max_ticks": 128}
		config_ref = args.configuration_ref
		state = {"tick": 0, "revision": 0, "position": 0, "velocity": 1, "rng": int(args.seed), "queued": [], "history": [[0, 0, 1]]}
		configured = true
		status = "created"
		return {"configuration": config.duplicate(true), "engine_version": Engine.get_version_info().string, "platform": OS.get_name(), "pid": OS.get_process_id()}
	if not configured: return refuse("Engine is not initialized")
	if operation == "identity":
		if not args.is_empty(): return refuse("Identity takes no arguments")
		if body.position != Vector3(state.position, 0, 0): return refuse("Scene node diverged from engine model")
		return {"tick": state.tick, "revision": state.revision, "node_x": int(body.position.x), "node_id": str(body.get_instance_id())}
	if operation == "snapshot":
		if not args.is_empty(): return refuse("Snapshot takes no arguments")
		return {"snapshot": JSON.stringify({"configuration_ref": config_ref, "state": state}, "", true, true)}
	if operation == "lifecycle":
		if not keys_match(args, ["action"]): return refuse("Invalid lifecycle envelope")
		var allowed := {"start": ["created"], "pause": ["running"], "resume": ["paused"], "stop": ["created", "running", "paused", "stopped"]}
		if not allowed.has(args.action) or not status in allowed[args.action]: return refuse("Illegal lifecycle transition")
		status = {"start": "running", "pause": "paused", "resume": "running", "stop": "stopped"}[args.action]
		return {}
	if operation == "restore":
		if status != "created" or state.revision != 0 or not keys_match(args, ["snapshot"]) or not args.snapshot is String:
			return refuse("Restore needs a fresh owner and explicit snapshot")
		var candidate := restore_state(args.snapshot)
		if not error.is_empty(): return {}
		state = candidate
		status = "paused"
		body.position = Vector3(state.position, 0, 0)
		return {}
	if operation == "step":
		if status != "running" or not keys_match(args, ["dt"]) or not integer(args.dt, 1, 1) or state.tick >= 128:
			return refuse("Only running one-second ticks up to 128 are supported")
		# All values remain below signed 64-bit bounds; explicit toy LCG, not a
		# cryptographic RNG or Godot global random stream.
		var s := state.duplicate(true)
		s.tick += 1
		s.rng = (1103515245 * int(s.rng) + 12345) % 2147483648
		s.velocity += int(s.rng) % 3 - 1
		var pending: Array = []
		for item in s.queued:
			if item.at_tick == s.tick: s.velocity += item.delta_v
			else: pending.append(item)
		s.queued = pending
		s.position += s.velocity
		s.revision += 1
		s.history.append([s.tick, s.position, s.velocity])
		state = s
		body.position = Vector3(state.position, 0, 0)
		return {}
	if operation == "intervene":
		if not status in ["running", "paused"] or not keys_match(args, ["actor_id", "operation", "target", "parameters"]) or args.operation != "motion.queue-impulse.v1" or args.target != "body-1":
			return refuse("Unsupported intervention")
		var p: Variant = args.parameters
		if not keys_match(p, ["at_tick", "delta_v"]) or not integer(p.at_tick, state.tick + 1, 128) or not integer(p.delta_v, -20, 20) or state.queued.size() >= 16:
			return refuse("Invalid impulse magnitude, timing or queue budget")
		state.queued.append({"at_tick": int(p.at_tick), "delta_v": int(p.delta_v)})
		state.revision += 1
		return {}
	if operation == "observe":
		if not keys_match(args, ["kind", "channels", "policy", "player_knowledge_transfer"]) or args.player_knowledge_transfer != false or typeof(args.player_knowledge_transfer) != TYPE_BOOL or not args.policy is Dictionary or not args.policy.is_empty():
			return refuse("Unsupported observer policy")
		if not args.kind in ["debugger", "sensor", "embodied_agent", "retrospective_narrator"] or not args.channels is Array or args.channels.is_empty():
			return refuse("Invalid observer")
		var permitted := ["position", "velocity"] if args.kind == "debugger" else ["position"]
		var unique: Array = []
		for channel in args.channels:
			if not channel in permitted or channel in unique: return refuse("Observer requested a hidden or duplicate channel")
			unique.append(channel)
		var delay := 0 if args.kind in ["debugger", "retrospective_narrator"] else 2
		var rows: Array = []
		for row in state.history:
			if row[0] <= state.tick - delay: rows.append(row)
		rows = rows.slice(maxi(0, rows.size() - 8))
		var samples: Array = []
		for row in rows:
			for channel in args.channels:
				samples.append({"tick": row[0], "quantity": channel, "value": row[1] if channel == "position" else row[2]})
		return {"available_at_tick": state.tick, "samples": samples}
	return refuse("Unknown operation")

func _process(_delta: float) -> bool:
	if not FileAccess.file_exists("res://request.json"): return false
	var request_file := FileAccess.open("res://request.json", FileAccess.READ)
	if request_file == null or request_file.get_length() > LIMIT:
		printerr("ERROR: Request file exceeds budget")
		quit(2)
		return false
	var raw := request_file.get_as_text()
	request_file.close()
	DirAccess.remove_absolute(ProjectSettings.globalize_path("res://request.json"))
	var request: Variant = JSON.parse_string(raw)
	if not keys_match(request, ["schema", "sequence", "nonce", "operation", "arguments"]) or request.schema != "ciw.godot-motion-request.v1" or not integer(request.sequence, sequence, sequence) or not request.nonce is String or not request.operation is String or not request.arguments is Dictionary:
		printerr("ERROR: Invalid request envelope")
		quit(2)
		return false
	error = ""
	var data := dispatch(request.operation, request.arguments)
	var response := {"schema": "ciw.godot-motion-response.v1", "sequence": sequence, "nonce": request.nonce, "status": "ok" if error.is_empty() else "refused", "data": data, "error": null if error.is_empty() else error}
	var encoded := JSON.stringify(response, "", true, true)
	if encoded.to_utf8_buffer().size() > LIMIT:
		printerr("ERROR: Response exceeds budget")
		quit(2)
		return false
	var output := FileAccess.open("res://response.pending", FileAccess.WRITE)
	output.store_string(encoded)
	output.close()
	if DirAccess.rename_absolute(ProjectSettings.globalize_path("res://response.pending"), ProjectSettings.globalize_path("res://response.json")) != OK:
		printerr("ERROR: Cannot publish response")
		quit(2)
	sequence += 1
	return false
