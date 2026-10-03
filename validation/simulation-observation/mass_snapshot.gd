# Qualification fixture, not a general simulator or a fluid/PDE solver.
# Godot owns two node states and advances one declared transfer tick.
# Only the sensor projection enters NET; reference state is a separate file.
extends SceneTree

func _initialize() -> void:
    var args := OS.get_cmdline_user_args()
    if args.size() != 3:
        push_error("Expected template, new output, mode")
        quit(2)
        return
    var mode: String = args[2]
    if mode not in ["ordinary", "held", "missing", "both_missing", "singular"]:
        quit(2)
        return
    if FileAccess.file_exists(args[1]) or FileAccess.file_exists(args[1] + ".reference.json"):
        push_error("Fixture refuses existing output")
        quit(2)
        return
    var template: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
    var a := Node.new()
    var b := Node.new()
    a.name = "ReservoirA"
    b.name = "ReservoirB"
    root.add_child(a)
    root.add_child(b)
    a.set_meta("mass_kg", 50.0)
    b.set_meta("mass_kg", 50.0)
    # One exact transfer tick in this fixture; no rendered position is sampled.
    a.set_meta("mass_kg", float(a.get_meta("mass_kg")) - 1.0)
    b.set_meta("mass_kg", float(b.get_meta("mass_kg")) + 1.0)
    var reference: Array = [float(a.get_meta("mass_kg")), float(b.get_meta("mass_kg"))]
    var error: Array = [2.0, -4.0]
    if mode == "held":
        error = [30.0, 20.0]
    template["values"] = [reference[0] + error[0], reference[1] + error[1]]
    template["reference_values"] = template["values"].duplicate()
    template["mask"] = [true, true]
    template["clock"] = {"tick": 1, "ticks_per_second": 10, "phase": "post_step"}
    template["covariance"] = [[0.4, 0.1], [0.1, 0.9]]
    if mode == "missing" or mode == "both_missing":
        template["values"][1] = null
        template["mask"][1] = false
        template["reference_values"][1] = 0.0
    if mode == "both_missing":
        template["values"][0] = null
        template["mask"][0] = false
        template["reference_values"][0] = 0.0
    if mode == "singular":
        template["covariance"] = [[1.0, 1.0], [1.0, 1.0]]
    var output := FileAccess.open(args[1], FileAccess.WRITE)
    if output == null:
        quit(2)
        return
    output.store_string(JSON.stringify(template, "", true, true))
    output.close()
    var truth_output := FileAccess.open(args[1] + ".reference.json", FileAccess.WRITE)
    if truth_output == null:
        quit(2)
        return
    truth_output.store_string(JSON.stringify({
        "reference_class": "simulator_internal_test_state",
        "producer_execution_id": template["producer"]["execution_id"],
        "entity_ids": template["entity_ids"], "clock": template["clock"],
        "mass_kg": reference, "status": "synthetic_reference_not_physical_truth"
    }, "", true, true))
    truth_output.close()
    quit(0)
