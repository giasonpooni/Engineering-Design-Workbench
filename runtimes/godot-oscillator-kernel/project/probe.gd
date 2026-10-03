extends SceneTree
# Qualification host, not a physics body or scientific-result inspector.
# Godot owns the RK4 state below; the extension evaluates derivatives only.
var kernel
var failed: bool = false

func fail(message: String) -> void:
	failed = true
	push_error(message)
	quit(2)

func _initialize() -> void:
	call_deferred("run_probe")

func refuse_tests(source: String) -> bool:
	var other = ClassDB.instantiate("CIWOscillatorKernel")
	if other.rhs(PackedFloat64Array([1.0, -2.0]), PackedFloat64Array([0.25, 2.0])).status != 7:
		return false
	if other.bind_source("0".repeat(64)) != 7 or other.bind_source(source) != 0:
		return false
	var known: Dictionary = other.rhs(PackedFloat64Array([1.0, -2.0]), PackedFloat64Array([0.25, 2.0]))
	if known.status != 0 or known.derivative != PackedFloat64Array([-2.0, -3.0]):
		return false
	var shape: Dictionary = other.rhs(PackedFloat64Array([1.0]), PackedFloat64Array([0.25, 2.0]))
	var nonfinite: Dictionary = other.rhs(PackedFloat64Array([NAN, 0.0]), PackedFloat64Array([0.0, 1.0]))
	var bounds: Dictionary = other.rhs(PackedFloat64Array([0.0, 0.0]), PackedFloat64Array([1.0, 1.0]))
	if shape.status != 2 or nonfinite.status != 3 or bounds.status != 4:
		return false
	if not shape.derivative.is_empty() or not nonfinite.derivative.is_empty() or not bounds.derivative.is_empty():
		return false
	if other.bind_source("0".repeat(64)) != 7:
		return false
	return other.rhs(PackedFloat64Array([1.0, -2.0]), PackedFloat64Array([0.25, 2.0])).status == 7

func rhs(state: PackedFloat64Array, parameters: PackedFloat64Array) -> PackedFloat64Array:
	var answer: Dictionary = kernel.rhs(state, parameters)
	if answer.status != 0:
		fail("Native derivative refused: " + str(answer.status))
		return PackedFloat64Array([NAN, NAN])
	return answer.derivative

func shifted(state: PackedFloat64Array, derivative: PackedFloat64Array, scale: float) -> PackedFloat64Array:
	return PackedFloat64Array([state[0] + scale * derivative[0], state[1] + scale * derivative[1]])

func trajectory(source: Dictionary) -> Dictionary:
	if not source.has_all(["model", "initial_state", "time_s"]):
		fail("Missing trajectory fields")
		return {}
	var model: Dictionary = source.model
	var initial: Dictionary = source.initial_state
	if not model.has_all(["gamma_s_inv", "omega_0_rad_s", "mass_kg"]) or not initial.has_all(["q0_m", "v0_m_s"]):
		fail("Missing model or initial-state fields")
		return {}
	var p := PackedFloat64Array([model.gamma_s_inv, model.omega_0_rad_s])
	var state := PackedFloat64Array([initial.q0_m, initial.v0_m_s])
	var mass: float = model.mass_kg
	var times: Array = source.time_s
	if times.size() < 2 or times.size() > 4096 or times[0] != 0.0 or not is_finite(mass) or mass <= 0.0 or mass > 100.0:
		fail("Trajectory outside bounded profile")
		return {}
	var previous: float = -1.0
	for raw_time in times:
		if typeof(raw_time) not in [TYPE_FLOAT, TYPE_INT]:
			fail("Invalid time type")
			return {}
		var time: float = raw_time
		if not is_finite(time) or time <= previous or time > 12.0:
			fail("Invalid time grid")
			return {}
		previous = time
	rhs(state, p) # Validate parameters and initial state before computing step counts.
	if failed:
		return {}
	var q: Array = [state[0]]
	var v: Array = [state[1]]
	var energy: Array = [0.5 * mass * (state[1] * state[1] + p[1] * p[1] * state[0] * state[0])]
	var steps: int = 0
	for index in range(1, times.size()):
		var count: int = maxi(1, ceili((times[index] - times[index - 1]) * maxf(1.0, p[1]) * 512.0))
		var dt: float = (times[index] - times[index - 1]) / count
		for _step in range(count):
			var a := rhs(state, p)
			var b := rhs(shifted(state, a, 0.5 * dt), p)
			var c := rhs(shifted(state, b, 0.5 * dt), p)
			var d := rhs(shifted(state, c, dt), p)
			if failed:
				return {}
			for component in range(2):
				state[component] += dt * (a[component] + 2.0 * b[component] + 2.0 * c[component] + d[component]) / 6.0
		steps += count
		q.append(state[0])
		v.append(state[1])
		energy.append(0.5 * mass * (state[1] * state[1] + p[1] * p[1] * state[0] * state[0]))
	return {"time_s": times, "q_m": q, "v_m_s": v, "energy_j": energy, "rk4_steps": steps, "owner": "godot-host-rk4"}

func run_probe() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() != 4 or args[0] not in ["probe", "trajectory"]:
		fail("Expected MODE SOURCE_SHA256 INPUT OUTPUT")
		return
	if not ClassDB.class_exists("CIWOscillatorKernel"):
		fail("Native extension unavailable")
		return
	kernel = ClassDB.instantiate("CIWOscillatorKernel")
	if kernel.bind_source(args[1]) != 0:
		fail("Native source/ABI mismatch")
		return
	if FileAccess.file_exists(args[3]):
		fail("Refusing to overwrite output")
		return
	var input := FileAccess.open(args[2], FileAccess.READ)
	if input == null or input.get_length() > 1048576:
		fail("Missing or oversized input")
		return
	var text := input.get_as_text()
	input.close()
	var output: Dictionary = {"schema": "oscillator-godot-probe.v1", "mode": args[0], "source_sha256": args[1]}
	if args[0] == "probe":
		if not refuse_tests(args[1]):
			fail("Godot refusal/binding tests failed")
			return
		var lines := text.strip_edges().split("\n", false)
		if lines.is_empty() or lines.size() > 4096:
			fail("Input row limit exceeded")
			return
		var rows: Array = []
		for line in lines:
			var fields: PackedStringArray = line.split("\t")
			if fields.size() != 4:
				fail("Expected four TSV fields")
				return
			var values := PackedFloat64Array()
			for field in fields:
				if not field.is_valid_float():
					fail("Invalid scalar")
					return
				values.append(field.to_float())
			var value := rhs(PackedFloat64Array([values[0], values[1]]), PackedFloat64Array([values[2], values[3]]))
			if failed:
				return
			rows.append(Array(value))
		output["rows"] = rows
		output["refusal_checks"] = "passed"
	else:
		var parser := JSON.new()
		if parser.parse(text) != OK or not parser.data is Dictionary:
			fail("Invalid trajectory source")
			return
		output["trajectory"] = trajectory(parser.data)
	if failed:
		return
	var destination := FileAccess.open(args[3], FileAccess.WRITE)
	if destination == null:
		fail("Cannot open output")
		return
	destination.store_string(JSON.stringify(output, "", true, true))
	destination.close()
	quit(0)
