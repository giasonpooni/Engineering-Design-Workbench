extends SceneTree
## Headless authored reference, not historical gameplay or a physics benchmark.
## Godot owns these local actors and the logical tick loop. NET records results.

const Recorder = preload("res://recorder.gd")

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() != 2:
		push_error("Expected request and output paths")
		quit(1)
		return
	var parser := JSON.new()
	if parser.parse(FileAccess.get_file_as_string(args[0])) != OK or not parser.data is Dictionary:
		push_error("Invalid request JSON")
		quit(1)
		return
	var request: Dictionary = parser.data
	var scenario: Dictionary = request["scenario"]
	var delivery: int = int(scenario["parameters"]["delivery_tick"])
	var returned: int = int(scenario["parameters"]["return_tick"])
	var duration: int = int(scenario["clock"]["duration_ticks"])
	var fault: String = request["diagnostic_fault"]
	var recorder = Recorder.new()
	var actors := Node3D.new()
	root.add_child(actors)
	for actor_id in scenario["entities"]:
		var actor := Node3D.new()
		actor.name = actor_id
		actors.add_child(actor)
	var courier: Node3D = actors.get_node("courier")
	var recipient: Node3D = actors.get_node("recipient")
	recipient.set_meta("knows_order", false)
	var mission := 0
	var cargo := 0
	var reward := 0
	var issued := ""
	var acknowledged := ""
	for tick in range(duration + 1):
		if tick == 1:
			issued = recorder.event(tick, "order.issued", "commander", ["courier", "recipient"], [], {"order_id": "deliver-manifest"})
			mission = 1
			cargo = 1
			if fault == "early-knowledge":
				recipient.set_meta("knows_order", true)
		if tick == delivery:
			var received: String = recorder.event(tick, "order.received", "recipient", ["courier"], [issued])
			recipient.set_meta("knows_order", true)
			cargo = 0
			mission = 2
			acknowledged = recorder.event(tick, "order.acknowledged", "recipient", ["commander"], [received])
		if tick == returned:
			mission = 3
			reward += 1
			var completed: String = recorder.event(tick, "mission.completed", "courier", ["commander"], [acknowledged])
			recorder.event(tick, "report.received", "commander", ["courier"], [completed])
		if tick == returned + 1 and fault == "duplicate-reward":
			reward += 1
		# A real engine-local transform, not a physics trajectory or a reconstruction.
		courier.position.x = float(mini(tick, returned))
		var values := {"knowledge": 1 if recipient.get_meta("knows_order") else 0,
			"mission": mission, "reward": reward, "cargo": cargo}
		for channel in scenario["channels"]:
			if fault == "drop-sample" and tick == delivery and channel == "knowledge":
				recorder.dropped_samples += 1
			else:
				recorder.sample(tick, channel, values[channel])
	var file := FileAccess.open(args[1], FileAccess.WRITE)
	if file == null:
		push_error("Cannot create trace output")
		quit(1)
		return
	file.store_string(JSON.stringify(recorder.export_trace(request), "", true, true))
	file.flush()
	var result := file.get_error()
	file.close()
	actors.free()
	quit(0 if result == OK else 1)
