extends SceneTree
## Drives the real Godot scene. The harness selects a real or labelled fixture backend.
var client
var stage := 0
var before: Dictionary = {}
var after_impulse: Dictionary = {}
var deadline := 0

func _initialize() -> void:
    deadline = Time.get_ticks_msec() + 120000
    client = load("res://simulation.tscn").instantiate()
    root.add_child(client)
    client.response_received.connect(_response)

func _process(_delta: float) -> bool:
    if Time.get_ticks_msec() > deadline:
        push_error("Persistent simulation Godot smoke timed out at stage " + str(stage))
        quit(1)
    if stage == 0 and not client.view.is_empty() and client.pending.is_empty():
        before = client.view.duplicate(true)
        stage = 1
        client.send_mutation("advance", {"ticks": 12})
    elif stage == 4 and not client.view.is_empty() and client.pending.is_empty():
        if client.view.model_id != before.model_id or client.view.owner_id != before.owner_id or client.view.state != after_impulse.state:
            push_error("Reconnect changed model, owner or state")
            quit(1)
        stage = 5
        client.send_request("simulation.advance", {"command_id": "command-" + Crypto.new().generate_random_bytes(16).hex_encode(),
            "owner_id": before.owner_id, "expected_revision": int(before.revision), "at_tick": int(before.state.tick), "ticks": 12})
    return false

func _response(kind: String, message: Dictionary) -> void:
    if kind == "simulation.inspect":
        return
    if stage == 5:
        if message.get("type") != "error" or message.payload.get("code") != "stale_state":
            push_error("Stale client command was not refused")
            quit(1)
            return
        print("SIMULATION_GODOT_PASSED: same model/owner, advance, impulse, checkpoint, reconnect, stale-command refusal")
        quit(0)
        return
    if message.get("type") != "response":
        push_error("Godot simulation command failed: " + JSON.stringify(message))
        quit(1)
        return
    if stage == 1:
        if int(client.view.state.tick) != int(before.state.tick) + 12 or client.view.model_id != before.model_id:
            push_error("Advance did not preserve model or requested ticks")
            quit(1)
            return
        after_impulse = client.view.duplicate(true)
        stage = 2
        client.send_mutation("impulse", {"impulse_n_s": 0.25})
    elif stage == 2:
        if int(client.view.state.tick) != int(after_impulse.state.tick) or abs(float(client.view.state.v_m_s) - float(after_impulse.state.v_m_s) - 0.25) > 1e-8:
            push_error("Impulse changed time or failed mass-one velocity check")
            quit(1)
            return
        after_impulse = client.view.duplicate(true)
        stage = 3
        client.send_request("simulation.checkpoint", {})
    elif stage == 3:
        if not message.payload.has("checkpoint_id"):
            push_error("Checkpoint was not retained")
            quit(1)
            return
        stage = 4
        client.connect_session()
