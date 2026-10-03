"""Bounded cycle evidence for polymer processing; no device or provider loading."""
from __future__ import annotations

from copy import deepcopy

from .control_contracts import content_ref, detached, keys, number, text
from .operations.runner import digest

SCHEMA = "ciw.polymer-cycle-request.v1"
PROCESSES = {"injection_molding", "extrusion_blow_molding"}
UNITS = {"cavity_pressure": "Pa", "mold_temperature": "K",
         "cooling_water_temperature": "K", "part_temperature": "K",
         "part_dimension": "m", "wall_thickness": "m", "surface_defect_score": "1",
         "vibration_rms": "m/s2", "moisture": "kg/kg", "screw_position": "m",
         "tie_bar_strain": "1"}
MODALITIES = {"pressure", "temperature", "thermal", "vision_2d", "vision_3d",
              "thickness", "vibration", "moisture", "position", "strain"}
AUTHORITY = {"physical_validation": "not_established", "calibration_traceability": "not_established",
             "structural_acceptance": "not_established", "state_admission": "not_performed",
             "hardware_actuation": "not_performed", "llm_inference": "not_performed"}
MAX_BYTES = 2 * 1024 * 1024


def validate_request(value: dict) -> dict:
    from .polymer_models import validate_model, validate_control
    from .polymer_copilot import validate_knowledge
    keys(value, {"schema", "identity", "process", "source_kind", "frame", "clock",
                 "measurement_condition", "sensors", "tolerances", "model", "control", "knowledge"})
    detached(value)
    if value["schema"] != SCHEMA or value["process"] not in PROCESSES:
        raise ValueError("Require the polymer cycle schema and a supported process")
    if value["source_kind"] not in {"synthetic", "retained_observation"}:
        raise ValueError("Declare synthetic or retained observation evidence")
    if value["measurement_condition"] not in {"ejection", "conditioned"}:
        raise ValueError("Declare the part's measurement condition")
    keys(value["identity"], {"facility_id", "machine_id", "tool_id", "material_lot_id", "cycle_id", "part_id"})
    for item in value["identity"].values():
        text(item)
    frame = text(value["frame"])
    clock = value["clock"]
    keys(clock, {"id", "start_s", "end_s", "max_skew_s"})
    text(clock["id"])
    start, end, skew = (number(clock[k]) for k in ("start_s", "end_s", "max_skew_s"))
    if not 0 <= start < end or not 0 <= skew <= end - start:
        raise ValueError("Invalid bounded cycle clock")
    sensors = value["sensors"]
    if type(sensors) is not list or not 1 <= len(sensors) <= 32:
        raise ValueError("Require 1..32 retained sensor channels")
    ids = set()
    for sensor in sensors:
        keys(sensor, {"sensor_id", "quantity", "unit", "modality", "frame", "clock_id",
                      "calibration_ref", "clock_ref", "source_ref", "origin", "samples", "max_age_s"})
        sid = text(sensor["sensor_id"])
        if sid in ids:
            raise ValueError("Duplicate sensor ID")
        ids.add(sid)
        if sensor["quantity"] not in UNITS or sensor["unit"] != UNITS[sensor["quantity"]]:
            raise ValueError("Sensor quantity requires its exact declared SI unit; no implicit conversion")
        if sensor["modality"] not in MODALITIES:
            raise ValueError("Unsupported sensor modality")
        if sensor["frame"] != frame or sensor["clock_id"] != clock["id"]:
            raise ValueError("Explicit frame and clock alignment are required before cycle ingress")
        for field in ("calibration_ref", "clock_ref", "source_ref"):
            content_ref(sensor[field])
        if sensor["origin"] != ("synthetic" if value["source_kind"] == "synthetic" else "observed"):
            raise ValueError("Sensor semantics contradict source kind")
        age = number(sensor["max_age_s"])
        if not 0 <= age <= end - start:
            raise ValueError("Invalid freshness window")
        samples = sensor["samples"]
        if type(samples) is not list or len(samples) > 4096:
            raise ValueError("Bound retained sensor samples to 4096 per channel")
        previous = None
        for sample in samples:
            keys(sample, {"time_s", "value", "standard_uncertainty"})
            stamp, reading, uncertainty = (number(sample[k]) for k in ("time_s", "value", "standard_uncertainty"))
            if not start <= stamp <= end or previous is not None and stamp <= previous:
                raise ValueError("Require strictly ordered acquisition times within this cycle")
            if uncertainty < 0:
                raise ValueError("Unknown uncertainty cannot become zero uncertainty")
            if sensor["unit"] == "K" and reading <= 0:
                raise ValueError("Require positive absolute temperature")
            if sensor["quantity"] in {"part_dimension", "wall_thickness"} and reading <= 0:
                raise ValueError("Require positive dimensional measurements")
            if sensor["quantity"] in {"surface_defect_score", "moisture"} and not 0 <= reading <= 1:
                raise ValueError("Normalized score or mass fraction must lie in [0,1]")
            previous = stamp
    tolerances = value["tolerances"]
    if type(tolerances) is not list or not 1 <= len(tolerances) <= 16:
        raise ValueError("Require 1..16 declared acceptance intervals")
    quantities = set()
    for tolerance in tolerances:
        keys(tolerance, {"quantity", "unit", "lower", "upper", "coverage_factor", "condition", "specification_ref"})
        q = tolerance["quantity"]
        if q not in UNITS or tolerance["unit"] != UNITS[q] or q in quantities:
            raise ValueError("Tolerance requires a distinct supported quantity and exact unit")
        quantities.add(q)
        low, high, coverage = (number(tolerance[k]) for k in ("lower", "upper", "coverage_factor"))
        if low >= high or not 1 <= coverage <= 6 or tolerance["condition"] not in {"ejection", "conditioned"}:
            raise ValueError("Invalid tolerance or declared uncertainty multiplier")
        content_ref(tolerance["specification_ref"])
    validate_model(value["model"])
    validate_control(value["control"])
    validate_knowledge(value["knowledge"])
    if value["model"]["process"] != value["process"] or value["control"]["process"] != value["process"]:
        raise ValueError("Engineering and control configurations must match this process")
    # Canonical size check follows the existing NET content encoder.
    from .core.identities import canonical_json
    if len(canonical_json(value).encode()) > MAX_BYTES:
        raise ValueError("Polymer request exceeds the 2 MiB budget")
    return deepcopy(value)


def example_request(process: str = "injection_molding") -> dict:
    from .polymer_models import example_model, example_control
    from .polymer_copilot import example_knowledge
    if process not in PROCESSES:
        raise ValueError("Unsupported example process")
    identity = {"facility_id": "synthetic.factory", "machine_id": "synthetic.machine.4",
                "tool_id": "synthetic.tool.1", "material_lot_id": "synthetic.resin.lot.1",
                "cycle_id": "synthetic.cycle.10", "part_id": "synthetic.part.10"}

    def sensor(sid, quantity, modality, reading, uncertainty):
        samples = [{"time_s": 0.0, "value": reading, "standard_uncertainty": uncertainty},
                   {"time_s": 10.0, "value": reading, "standard_uncertainty": uncertainty}]
        if quantity == "cavity_pressure":
            samples = [{"time_s": 0.0, "value": 0.0, "standard_uncertainty": uncertainty},
                       {"time_s": 1.0, "value": reading, "standard_uncertainty": uncertainty},
                       {"time_s": 10.0, "value": reading, "standard_uncertainty": uncertainty}]
        return {"sensor_id": sid, "quantity": quantity, "unit": UNITS[quantity], "modality": modality,
                "frame": "polymer.machine.v1", "clock_id": "synthetic.aligned-clock",
                "calibration_ref": digest({"synthetic_calibration": sid}),
                "clock_ref": digest({"synthetic_clock": sid}), "source_ref": digest(samples),
                "origin": "synthetic", "samples": samples, "max_age_s": 1.0}

    model, control = example_model(), example_control()
    model["process"] = control["process"] = process
    if process == "extrusion_blow_molding":
        model["cavity_arrival"]["pressure_sensor_ids"] = []
    return {"schema": SCHEMA, "identity": identity, "process": process, "source_kind": "synthetic",
            "frame": "polymer.machine.v1", "clock": {"id": "synthetic.aligned-clock", "start_s": 0.0,
            "end_s": 10.0, "max_skew_s": 0.1}, "measurement_condition": "ejection",
            "sensors": [sensor("part-temperature", "part_temperature", "thermal", 350.0, 0.5),
                        sensor("cooling-water", "cooling_water_temperature", "temperature", 300.0, 0.2),
                        sensor("cavity-1", "cavity_pressure", "pressure", 5000000.0, 10000.0),
                        sensor("dimension-1", "part_dimension", "vision_3d", 0.0202, 0.00001),
                        sensor("wall-1", "wall_thickness", "thickness", 0.001, 0.00001)],
            "tolerances": [{"quantity": "part_dimension", "unit": "m", "lower": 0.0199,
                            "upper": 0.0201, "coverage_factor": 2.0, "condition": "ejection",
                            "specification_ref": digest({"synthetic_dimension_spec": 1})}],
            "model": model, "control": control, "knowledge": example_knowledge(identity)}
