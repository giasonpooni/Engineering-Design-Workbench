extends Control
## NET owns q/v. This client only requests bounded commands and plays returned samples.
signal response_received(kind: String, message: Dictionary)

var socket := WebSocketPeer.new()
var view: Dictionary = {}
var pending: Dictionary = {}
var endpoint := "ws://127.0.0.1:8765"
var elapsed := 0.0
var poll_elapsed := 0.0
var status_label: Label
var state_label: Label
var impulse: SpinBox
var plot: Control
var checkpoint_label: Label
var buttons: Array[Button] = []
var sequence := 0
var session_nonce := Crypto.new().generate_random_bytes(16).hex_encode()

func _ready() -> void:
    for arg in OS.get_cmdline_user_args():
        if arg.begins_with("--simulation-url="):
            endpoint = arg.trim_prefix("--simulation-url=")
    var panel := VBoxContainer.new()
    panel.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    panel.add_theme_constant_override("separation", 12)
    panel.offset_left = 24
    panel.offset_top = 24
    panel.offset_right = -24
    panel.offset_bottom = -24
    add_child(panel)
    var title := Label.new()
    title.text = "NET • Persistent simulation"
    title.add_theme_font_size_override("font_size", 26)
    panel.add_child(title)
    var description := Label.new()
    description.text = "Julia integrates • SCR supervises • C++ evaluates force/energy • NET owns state"
    panel.add_child(description)
    status_label = Label.new()
    status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    panel.add_child(status_label)
    state_label = Label.new()
    state_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    panel.add_child(state_label)
    var controls := HBoxContainer.new()
    panel.add_child(controls)
    _button(controls, "Advance 0.1 s", func(): send_mutation("advance", {"ticks": 12}))
    _button(controls, "Advance 1 s", func(): send_mutation("advance", {"ticks": 120}))
    impulse = SpinBox.new()
    impulse.min_value = -1.0
    impulse.max_value = 1.0
    impulse.step = 0.1
    impulse.value = 0.2
    impulse.suffix = "N·s"
    controls.add_child(impulse)
    _button(controls, "Apply impulse", func(): send_mutation("impulse", {"impulse_n_s": impulse.value}))
    _button(controls, "Checkpoint", func(): send_request("simulation.checkpoint", {}))
    var reconnect := Button.new()
    reconnect.text = "Reconnect (does not restart simulation)"
    reconnect.pressed.connect(connect_session)
    panel.add_child(reconnect)
    checkpoint_label = Label.new()
    checkpoint_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    panel.add_child(checkpoint_label)
    plot = Control.new()
    plot.custom_minimum_size = Vector2(360, 240)
    plot.size_flags_vertical = Control.SIZE_EXPAND_FILL
    plot.draw.connect(_draw_plot)
    panel.add_child(plot)
    var note := Label.new()
    note.text = "Animation plays retained samples only. Render time never advances the scientific state.\nSynthetic oscillator; no material calibration, physical validation, covariance or actuation authority."
    note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    panel.add_child(note)
    connect_session()

func _button(parent: Control, caption: String, action: Callable) -> void:
    var button := Button.new()
    button.text = caption
    button.pressed.connect(action)
    buttons.append(button)
    parent.add_child(button)

func connect_session() -> void:
    socket.close()
    socket = WebSocketPeer.new()
    socket.inbound_buffer_size = 8 * 1024 * 1024
    socket.outbound_buffer_size = 65536
    socket.max_queued_packets = 8
    pending.clear()
    view.clear()
    var error := socket.connect_to_url(endpoint)
    status_label.text = "Connecting to the existing NET session…" if error == OK else "Connection refused: " + str(error)

func send_request(kind: String, payload: Dictionary) -> void:
    if socket.get_ready_state() != WebSocketPeer.STATE_OPEN or not pending.is_empty():
        return
    sequence += 1
    var request_id := session_nonce + "-" + str(sequence)
    pending = {"id": request_id, "kind": kind}
    socket.send_text(JSON.stringify({"protocol_version": 1, "request_id": request_id,
                                    "type": kind, "payload": payload}))

func send_mutation(action: String, extra: Dictionary) -> void:
    if view.is_empty():
        return
    var payload := {"command_id": "command-" + Crypto.new().generate_random_bytes(16).hex_encode(),
                   "owner_id": view.owner_id, "expected_revision": int(view.revision),
                   "at_tick": int(view.state.tick)}
    payload.merge(extra)
    send_request("simulation." + action, payload)

func _accept_snapshot(value: Dictionary) -> void:
    if not value.has_all(["simulation_id", "model_id", "owner_id", "revision", "state", "trajectory", "observables", "status"]):
        return
    if not view.is_empty() and value.simulation_id == view.simulation_id and int(value.revision) < int(view.revision):
        return
    if view.is_empty() or value.owner_id != view.owner_id or int(value.revision) != int(view.revision):
        elapsed = 0.0
    view = value.duplicate(true)
    state_label.text = "tick %d  •  t = %.3f s  •  q = %.8f m  •  v = %.8f m/s\nF = %.8f N  •  E = %.8f J\n%s\n%s" % [
        int(view.state.tick), float(view.state.tick) / 120.0, view.state.q_m, view.state.v_m_s,
        view.observables.net_force_n, view.observables.energy_j, view.model_id, view.owner_id]

func _process(delta: float) -> void:
    socket.poll()
    while socket.get_available_packet_count() > 0:
        var raw := socket.get_packet()
        if not socket.was_string_packet():
            continue
        var decoded: Variant = JSON.parse_string(raw.get_string_from_utf8())
        if not decoded is Dictionary:
            continue
        var message: Dictionary = decoded
        if message.get("type") == "session.snapshot" and message.get("payload", {}).has("simulation"):
            _accept_snapshot(message.payload.simulation)
        if not pending.is_empty() and message.get("request_id") == pending.id:
            var kind: String = pending.kind
            pending.clear()
            if message.get("type") == "response":
                if kind == "simulation.checkpoint":
                    checkpoint_label.text = "Checkpoint retained on NET:\n" + str(message.payload.filename) + "\n" + str(message.payload.checkpoint_id)
                else:
                    _accept_snapshot(message.get("payload", {}))
                status_label.text = "Connected • snapshot/checkpoint only; no client-side solver"
            else:
                status_label.text = str(message.get("payload", {}).get("code", "refused")) + ": " + str(message.get("payload", {}).get("message", "request refused"))
            response_received.emit(kind, message)
    elapsed += delta
    poll_elapsed += delta
    if socket.get_ready_state() == WebSocketPeer.STATE_CLOSED:
        pending.clear()
        status_label.text = "Disconnected. Reconnect to inspect the same NET-owned instance."
    elif poll_elapsed >= 0.5 and pending.is_empty():
        poll_elapsed = 0.0
        send_request("simulation.inspect", {})
    for button in buttons:
        button.disabled = view.is_empty() or not pending.is_empty() or view.get("status") != "ready"
    if plot != null:
        plot.queue_redraw()

func _draw_plot() -> void:
    if view.is_empty():
        return
    var trajectory: Dictionary = view.trajectory
    var values: Array = trajectory.q_m
    if values.is_empty():
        return
    # Presentation cursor over returned values, NOT a numerical integration step.
    var i := mini(int(elapsed * float(trajectory.sample_rate_hz)), values.size() - 1)
    var center := plot.size * 0.5
    var scale_m := minf(plot.size.x * 0.3, 150.0)
    var location := center + Vector2(float(values[i]) * scale_m, 0)
    plot.draw_line(Vector2(16, center.y), Vector2(plot.size.x - 16, center.y), Color(0.5, 0.5, 0.5), 1.0)
    plot.draw_line(center, location, Color(0.25, 0.7, 0.95), 3.0)
    plot.draw_circle(center, 5.0, Color(0.7, 0.7, 0.7))
    plot.draw_circle(location, 16.0, Color(0.25, 0.7, 0.95))
    plot.draw_string(ThemeDB.fallback_font, Vector2(16, 24), "Retained playback tick %d; authoritative tick %d" % [int(trajectory.start_tick) + i, int(view.state.tick)])
