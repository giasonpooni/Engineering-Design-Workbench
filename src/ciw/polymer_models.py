"""Small polymer reference models and simulated cycle recommendations.

The cooling law is a homogeneous lumped energy balance, not a mold-flow solver
or a trained engineering model. The pressure calculation locates a nominal
threshold crossing at an instrumented location; it does not infer a melt front.
All control outputs are data-only simulated trials with no machine authority.
"""
from __future__ import annotations

import math

from .control_contracts import content_ref, detached, keys, number, text
from .core.identities import content_identity

MODEL_SCHEMA = "ciw.polymer-engineering-model.v1"
CONTROL_SCHEMA = "ciw.polymer-control-plan.v1"
PROCESSES = {"injection_molding", "extrusion_blow_molding"}
AUTHORITY = {"hardware_control": False, "plc_write": False,
             "evidence_admission": False, "verification": False}
PROPERTY_BOUNDS = {
    "density_kg_m3": (1.0, 10000.0),
    "heat_capacity_j_kg_k": (1.0, 100000.0),
    "volume_m3": (1e-12, 1.0),
    "area_m2": (1e-10, 100.0),
    "heat_transfer_w_m2_k": (1e-4, 100000.0),
    "conductivity_w_m_k": (1e-5, 10000.0),
    "target_temperature_k": (1.0, 2000.0),
}


def _bound(value, lo, hi, label):
    value = number(value)
    if not lo <= value <= hi:
        raise ValueError(f"{label} outside supported numerical bounds")
    return value


def _interval(value, lo, hi, label):
    if type(value) is not list or len(value) != 2:
        raise ValueError(f"{label} requires two interval endpoints")
    low, high = [_bound(x, lo, hi, label) for x in value]
    if low >= high:
        raise ValueError(f"{label} requires increasing endpoints")
    return low, high


def validate_model(model: dict) -> dict:
    """Validate declarations; physical validity is assessed at execution."""
    keys(model, {"schema", "model_id", "process", "kind", "uncertainty_profile", "cooling", "validity", "cavity_arrival"})
    if model["schema"] != MODEL_SCHEMA or model["kind"] != "lumped_cooling_reference":
        raise ValueError("Unsupported polymer engineering model")
    text(model["model_id"])
    if model["uncertainty_profile"] != "independent_first_order_declared":
        raise ValueError("Cooling requires an explicit supported uncertainty profile")
    if type(model["process"]) is not str or model["process"] not in PROCESSES:
        raise ValueError("Unsupported molding process")
    cooling = model["cooling"]
    keys(cooling, set(PROPERTY_BOUNDS) | {"temperature_sensor_id", "ambient_sensor_id", "forecast_horizon_s"})
    text(cooling["temperature_sensor_id"])
    text(cooling["ambient_sensor_id"])
    if cooling["temperature_sensor_id"] == cooling["ambient_sensor_id"]:
        raise ValueError("Part and boundary temperature require distinct sensors")
    _bound(cooling["forecast_horizon_s"], 0.0, 86400.0, "forecast_horizon_s")
    for name, (low, high) in PROPERTY_BOUNDS.items():
        parameter = cooling[name]
        keys(parameter, {"value", "standard_uncertainty", "source_ref"})
        value = _bound(parameter["value"], low, high, name)
        _bound(parameter["standard_uncertainty"], 0.0, value * 0.2, name + " uncertainty")
        content_ref(parameter["source_ref"])
    validity = model["validity"]
    keys(validity, {"temperature_k", "elapsed_s", "maximum_biot", "biot_uncertainty_multiplier"})
    _interval(validity["temperature_k"], 1.0, 2000.0, "temperature_k")
    _interval(validity["elapsed_s"], 0.0, 86400.0, "elapsed_s")
    _bound(validity["maximum_biot"], 1e-8, 0.1, "maximum_biot")
    _bound(validity["biot_uncertainty_multiplier"], 1.0, 6.0, "biot_uncertainty_multiplier")
    arrival = model["cavity_arrival"]
    keys(arrival, {"pressure_sensor_ids", "threshold_pa"})
    sensor_ids = arrival["pressure_sensor_ids"]
    if type(sensor_ids) is not list or len(sensor_ids) > 64:
        raise ValueError("Require at most 64 pressure locations")
    for identifier in sensor_ids:
        text(identifier)
    if len(sensor_ids) != len(set(sensor_ids)):
        raise ValueError("Duplicate cavity-pressure sensor location")
    if model["process"] == "extrusion_blow_molding" and sensor_ids:
        raise ValueError("Cavity melt-pressure arrival is injection-molding only")
    _bound(arrival["threshold_pa"], 1.0, 1e9, "threshold_pa")
    return detached(model)


def validate_control(control: dict) -> dict:
    keys(control, {"schema", "controller_id", "process", "mode", "parameter", "response", "cycle_guard", "toy_plant"})
    if control["schema"] != CONTROL_SCHEMA or control["mode"] != "simulation_only":
        raise ValueError("Only data-only simulated control is supported")
    text(control["controller_id"])
    if type(control["process"]) is not str or control["process"] not in PROCESSES:
        raise ValueError("Unsupported molding process")
    parameter = control["parameter"]
    keys(parameter, {"name", "unit", "current", "minimum", "maximum", "maximum_step"})
    allowed = {"cooling_time_s": "s"}
    allowed["holding_pressure_pa" if control["process"] == "injection_molding" else "blow_pressure_pa"] = "Pa"
    if type(parameter["name"]) is not str or parameter["name"] not in allowed or parameter["unit"] != allowed[parameter["name"]]:
        raise ValueError("Parameter or SI unit incompatible with molding process")
    minimum = _bound(parameter["minimum"], 0.0, 1e9, "minimum")
    maximum = _bound(parameter["maximum"], 0.0, 1e9, "maximum")
    if minimum >= maximum:
        raise ValueError("Parameter interval is empty")
    _bound(parameter["current"], minimum, maximum, "current")
    _bound(parameter["maximum_step"], 1e-12, maximum - minimum, "maximum_step")
    response = control["response"]
    keys(response, {"quantity", "unit", "target", "tolerance", "local_gain_per_parameter", "gain_source_ref",
                    "validity_quantity", "validity_parameter", "maximum_standard_uncertainty", "relaxation"})
    text(response["quantity"])
    text(response["unit"])
    lo, hi = _interval(response["validity_quantity"], -1e12, 1e12, "validity_quantity")
    _bound(response["target"], lo, hi, "target")
    _bound(response["tolerance"], 1e-15, hi - lo, "tolerance")
    gain = _bound(response["local_gain_per_parameter"], -1e12, 1e12, "local_gain_per_parameter")
    if abs(gain) < 1e-15:
        raise ValueError("Local response gain is zero or ill-conditioned")
    content_ref(response["gain_source_ref"])
    vlo, vhi = _interval(response["validity_parameter"], 0.0, 1e9, "validity_parameter")
    if minimum < vlo or maximum > vhi:
        raise ValueError("Control limits extend beyond declared gain validity")
    _bound(response["maximum_standard_uncertainty"], 0.0, hi - lo, "maximum_standard_uncertainty")
    _bound(response["relaxation"], 1e-6, 1.0, "relaxation")
    guard = control["cycle_guard"]
    keys(guard, {"current_cycle_index", "measurement_cycle_index", "last_adjustment_cycle_index",
                 "minimum_dwell_cycles", "maximum_measurement_delay_cycles"})
    for name in ("current_cycle_index", "measurement_cycle_index", "minimum_dwell_cycles", "maximum_measurement_delay_cycles"):
        if type(guard[name]) is not int or not 0 <= guard[name] <= 10**9:
            raise ValueError("Cycle indices and limits require bounded integers, not booleans")
    if not 1 <= guard["minimum_dwell_cycles"] <= 1024 or guard["maximum_measurement_delay_cycles"] > 1024:
        raise ValueError("Cycle dwell/delay outside bounded reference profile")
    if guard["measurement_cycle_index"] > guard["current_cycle_index"]:
        raise ValueError("Measurement cannot originate in a future cycle")
    last = guard["last_adjustment_cycle_index"]
    if last is not None and (type(last) is not int or not 0 <= last <= guard["current_cycle_index"]):
        raise ValueError("Last adjustment cycle requires a prior/current index or null")
    plant = control["toy_plant"]
    keys(plant, {"initial_quantity", "actual_gain_per_parameter", "cycles", "interlock_ok"})
    _bound(plant["initial_quantity"], lo, hi, "initial_quantity")
    _bound(plant["actual_gain_per_parameter"], -1e12, 1e12, "actual_gain_per_parameter")
    cycles = plant["cycles"]
    if type(cycles) is not int or not 1 <= cycles <= 1024:
        raise ValueError("cycles requires an integer inside 1..1024")
    if type(plant["interlock_ok"]) is not list or len(plant["interlock_ok"]) != cycles:
        raise ValueError("One toy interlock state is required for each cycle")
    if any(type(x) is not bool for x in plant["interlock_ok"]):
        raise ValueError("Interlock states must be exact booleans")
    return detached(control)


def _report(schema, **fields):
    return detached({"schema": schema, "authority": AUTHORITY, **fields})


def _sensor(request, sensor_id, quantity, unit):
    rows = [row for row in request["sensors"] if row["sensor_id"] == sensor_id]
    if len(rows) != 1:
        return None, "MISSING_OR_AMBIGUOUS_SENSOR"
    row = rows[0]
    if row["quantity"] != quantity or row["unit"] != unit:
        return None, "INCOMPATIBLE_QUANTITY_OR_UNIT"
    if row.get("clock_id", request["clock"]["id"]) != request["clock"]["id"] or row["frame"] != request["frame"]:
        return None, "UNALIGNED_SENSOR"
    if not row["samples"]:
        return None, "MISSING_SAMPLES"
    last = row["samples"][-1]
    age = request["clock"]["end_s"] - last["time_s"]
    if age < 0 or age + request["clock"]["max_skew_s"] > row["max_age_s"]:
        return None, "STALE_OR_UNCERTAIN_AGE"
    return row, None


def _cooling(request, model):
    cooling = model["cooling"]
    inputs = []
    for name, quantity in (("temperature_sensor_id", "part_temperature"),
                           ("ambient_sensor_id", "cooling_water_temperature")):
        sensor, reason = _sensor(request, cooling[name], quantity, "K")
        if reason:
            return {"status": "ABSTAINED", "reason": reason, "sensor_id": cooling[name]}
        inputs.append(sensor)
    part, ambient = inputs
    t0 = part["samples"][-1]["value"]
    ta = ambient["samples"][-1]["value"]
    u0 = part["samples"][-1]["standard_uncertainty"]
    ua = ambient["samples"][-1]["standard_uncertainty"]
    values = {name: row["value"] for name, row in cooling.items() if name in PROPERTY_BOUNDS}
    rho, cp, volume, area, h, k = [values[x] for x in (
        "density_kg_m3", "heat_capacity_j_kg_k", "volume_m3", "area_m2", "heat_transfer_w_m2_k", "conductivity_w_m_k")]
    tau, biot = rho * cp * volume / (h * area), h * volume / (area * k)
    biot_uncertainty = biot * math.hypot(*[
        cooling[name]["standard_uncertainty"] / values[name] for name in (
            "heat_transfer_w_m2_k", "volume_m3", "area_m2", "conductivity_w_m_k")])
    age = request["clock"]["end_s"] - part["samples"][-1]["time_s"]
    elapsed = age + cooling["forecast_horizon_s"]
    validity = model["validity"]
    low_t, high_t = validity["temperature_k"]
    target = values["target_temperature_k"]
    if (not all(low_t <= t <= high_t for t in (t0, ta, target))
            or not validity["elapsed_s"][0] <= elapsed <= validity["elapsed_s"][1]
            or biot + validity["biot_uncertainty_multiplier"] * biot_uncertainty > validity["maximum_biot"] or t0 <= ta):
        return {"status": "ABSTAINED", "reason": "OUTSIDE_DECLARED_LUMPED_COOLING_DOMAIN",
                "biot_number": biot, "biot_standard_uncertainty": biot_uncertainty,
                "biot_uncertainty_multiplier": validity["biot_uncertainty_multiplier"], "elapsed_s": elapsed}
    if u0 > 0.2 * t0 or ua > 0.2 * ta:
        return {"status": "ABSTAINED", "reason": "TEMPERATURE_UNCERTAINTY_OUTSIDE_LINEAR_PROFILE"}
    relative_tau_uncertainty = math.hypot(*[
        cooling[name]["standard_uncertainty"] / values[name] for name in (
            "density_kg_m3", "heat_capacity_j_kg_k", "volume_m3", "area_m2", "heat_transfer_w_m2_k")])
    decay = math.exp(-elapsed / tau)
    delta = t0 - ta
    predicted = ta + delta * decay
    uncertainty = math.hypot(decay * u0, (1.0 - decay) * ua,
                             delta * decay * (elapsed / tau) * relative_tau_uncertainty)
    # Clock skew is a declared bound, not an invented statistical uncertainty.
    timing_bound = request["clock"]["max_skew_s"]
    timing_temperature_bound = delta * decay * math.expm1(min(timing_bound / tau, 700.0))
    if not math.isfinite(timing_temperature_bound) or timing_temperature_bound > high_t - low_t:
        return {"status": "ABSTAINED", "reason": "TIMING_BOUND_OUTSIDE_NUMERICAL_PROFILE"}
    target_report = {"status": "UNREACHABLE", "reason": "TARGET_AT_OR_BELOW_BOUNDARY_TEMPERATURE"}
    if target >= t0:
        target_report = {"status": "ALREADY_SATISFIED", "remaining_time_s": 0.0,
                         "standard_uncertainty_s": None}
    elif target > ta:
        log_ratio = math.log(delta / (target - ta))
        total = tau * log_ratio
        utarget = cooling["target_temperature_k"]["standard_uncertainty"]
        time_uncertainty = math.hypot(total * relative_tau_uncertainty, tau * u0 / delta,
            tau * ua * (1.0 / (target - ta) - 1.0 / delta), tau * utarget / (target - ta))
        if total > validity["elapsed_s"][1] or target - ta <= 5.0 * math.hypot(ua, utarget):
            target_report = {"status": "ABSTAINED", "reason": "TARGET_TIME_OUTSIDE_VALIDITY_OR_ILL_CONDITIONED"}
        else:
            target_report = {"status": "ESTIMATED", "remaining_time_s": max(0.0, total - age),
                             "standard_uncertainty_s": time_uncertainty,
                             "timing_bound_s": timing_bound}
    return {"status": "ESTIMATED", "method": "homogeneous_lumped_energy_balance",
            "temperature_k": predicted, "standard_uncertainty_k": uncertainty,
            "timing_temperature_bound_k": timing_temperature_bound, "elapsed_s": elapsed,
            "time_constant_s": tau, "biot_number": biot, "biot_standard_uncertainty": biot_uncertainty,
            "biot_uncertainty_multiplier": validity["biot_uncertainty_multiplier"],
            "target": target_report,
            "source_refs": sorted(set([sensor[field] for sensor in inputs
                for field in ("source_ref", "calibration_ref", "clock_ref")] +
                [cooling[name]["source_ref"] for name in PROPERTY_BOUNDS])),
            "input_origins": sorted(set(sensor["origin"] for sensor in inputs)),
            "uncertainty_assumptions": ["First-order sensitivity; independent supplied standard uncertainties",
                                       "Clock skew reported separately as a bound; model discrepancy excluded",
                                       "Biot guard uses a declared uncertainty multiplier, not a validated coverage probability"],
            "assumptions": ["Homogeneous effective material properties and uniform part temperature",
                            "Constant boundary temperature and heat-transfer coefficient",
                            "Negligible latent heat, radiation, viscous heating, and spatial gradients",
                            "Temperature sensors represent this part and its cooling boundary by declaration"]}


def _arrivals(request, model):
    threshold = model["cavity_arrival"]["threshold_pa"]
    reports = []
    for sensor_id in model["cavity_arrival"]["pressure_sensor_ids"]:
        sensor, reason = _sensor(request, sensor_id, "cavity_pressure", "Pa")
        if reason:
            reports.append({"sensor_id": sensor_id, "status": "ABSTAINED", "reason": reason})
            continue
        samples = sensor["samples"]
        result = {"sensor_id": sensor_id, "frame": sensor["frame"], "status": "NOT_OBSERVED",
                  "threshold_pa": threshold, "source_refs": [sensor[field]
                      for field in ("source_ref", "calibration_ref", "clock_ref")],
                  "origin": sensor["origin"], "claim": "nominal_pressure_threshold_at_measured_location",
                  "spatial_extrapolation": False}
        if samples[0]["value"] >= threshold:
            result.update(status="ABSTAINED", reason="LEFT_CENSORED_THRESHOLD_ALREADY_EXCEEDED")
        else:
            for before, after in zip(samples, samples[1:]):
                if before["value"] < threshold <= after["value"]:
                    low, high = before["time_s"], after["time_s"]
                    if high <= low:
                        result.update(status="ABSTAINED", reason="NO_POSITIVE_TIME_BRACKET")
                        break
                    result.update(status="BRACKETED", time_interval_s=[low, high],
                        cadence_s=high-low, timing_bound_s=request["clock"]["max_skew_s"],
                        endpoint_standard_uncertainties_pa=[before["standard_uncertainty"], after["standard_uncertainty"]],
                        uncertainty_statement="Nominal sampled crossing; no sub-sample timing, confidence guarantee, or melt-front identity")
                    break
        reports.append(result)
    return reports


def engineering_estimate(request: dict) -> dict:
    """Use a request already validated by the polymer workflow boundary."""
    model = validate_model(request["model"])
    if model["process"] != request["process"]:
        raise ValueError("Engineering model/request process mismatch")
    cooling = _cooling(request, model)
    return _report("ciw.polymer-engineering-estimate.v1", status=cooling["status"],
        identity=request["identity"], model_id=model["model_id"], semantics="reference_estimate",
        cooling=cooling, cavity_arrival=_arrivals(request, model),
        limitations=["No mold-flow, parison-thickness, structural integrity, or defect-cause reconstruction",
                     "No learned model, accuracy guarantee, or physical validation supplied"])


def _trial(control, value, current):
    response, parameter = control["response"], control["parameter"]
    error = value - response["target"]
    if abs(error) <= response["tolerance"]:
        return current, "NO_CHANGE"
    step = -response["relaxation"] * error / response["local_gain_per_parameter"]
    step = max(-parameter["maximum_step"], min(parameter["maximum_step"], step))
    proposed = max(parameter["minimum"], min(parameter["maximum"], current + step))
    if proposed == current:
        return current, "BOUND_LIMITED"
    return proposed, "PROPOSED"


def control_proposal(request: dict, metrology: dict) -> dict:
    control = validate_control(request["control"])
    if control["process"] != request["process"]:
        raise ValueError("Controller/request process mismatch")
    common = {"identity": request["identity"], "controller_id": control["controller_id"],
              "mode": "simulation_only", "parameter": control["parameter"]["name"],
              "unit": control["parameter"]["unit"],
              "cycle_guard": control["cycle_guard"],
              "measurement_cycle_index": control["cycle_guard"]["measurement_cycle_index"],
              "trial_cycle_index": control["cycle_guard"]["current_cycle_index"] + 1,
              "limitations": ["Declared local linear response only; no defect-to-action or LLM-derived direction",
                              "Declared cycle indices require independently established measurement attribution",
                              "Requires machine-specific identification and separate control qualification before execution"]}
    def refuse(reason):
        return _report("ciw.polymer-control-proposal.v1", **common, status="ABSTAINED", reason=reason)
    if metrology.get("status") not in {"CONFORMING", "NONCONFORMING"}:
        return refuse("INDETERMINATE_METROLOGY")
    response = control["response"]
    specifications = [spec for spec in request["tolerances"]
                      if spec["quantity"] == response["quantity"] and spec["unit"] == response["unit"]]
    if len(specifications) != 1:
        return refuse("MISSING_OR_AMBIGUOUS_RESPONSE_SPECIFICATION")
    specification = specifications[0]
    if (request["measurement_condition"] != specification["condition"]
            or metrology.get("measurement_condition") != request["measurement_condition"]):
        return refuse("RESPONSE_MEASUREMENT_CONDITION_MISMATCH")
    quality = [item for item in metrology.get("quantities", [])
               if item["quantity"] == response["quantity"] and item["unit"] == response["unit"]]
    if (len(quality) != 1 or quality[0]["status"] not in {"CONFORMING", "NONCONFORMING"}
            or quality[0].get("specification_ref") != specification["specification_ref"]):
        return refuse("UNQUALIFIED_RESPONSE_METROLOGY")
    guard = control["cycle_guard"]
    current_cycle, measured_cycle = guard["current_cycle_index"], guard["measurement_cycle_index"]
    last_cycle = guard["last_adjustment_cycle_index"]
    if current_cycle - measured_cycle > guard["maximum_measurement_delay_cycles"]:
        return refuse("MEASUREMENT_CYCLE_TOO_OLD")
    if last_cycle is not None:
        if current_cycle - last_cycle < guard["minimum_dwell_cycles"]:
            return refuse("MINIMUM_CYCLE_DWELL_NOT_ELAPSED")
        if measured_cycle <= last_cycle:
            return refuse("NO_MEASUREMENT_AFTER_PRIOR_ADJUSTMENT")
    rows = [row for row in metrology.get("measurements", [])
            if row["quantity"] == response["quantity"] and row["unit"] == response["unit"]]
    if len(rows) != 1 or rows[0].get("status") != "VALID":
        return refuse("MISSING_STALE_OR_AMBIGUOUS_QUALITY_MEASUREMENT")
    row = rows[0]
    value, uncertainty = number(row["value"]), number(row["standard_uncertainty"])
    lo, hi = response["validity_quantity"]
    if not lo <= value <= hi or not 0.0 <= uncertainty <= response["maximum_standard_uncertainty"]:
        return refuse("QUALITY_OUTSIDE_GAIN_DOMAIN_OR_UNCERTAINTY_BUDGET")
    current = control["parameter"]["current"]
    proposed, status = _trial(control, value, current)
    return _report("ciw.polymer-control-proposal.v1", **common, status=status,
        measured_quantity=response["quantity"], measured_value=value, measurement_standard_uncertainty=uncertainty,
        current=current, proposed=proposed, delta=proposed-current,
        target=response["target"], local_gain_per_parameter=response["local_gain_per_parameter"],
        source_refs=sorted(set(row["source_refs"] + [response["gain_source_ref"]])))


def simulate_control(control: dict) -> dict:
    """Deterministic toy plant; an interlock dropout permanently halts this run."""
    control = validate_control(control)
    plant = control["toy_plant"]
    value, current = plant["initial_quantity"], control["parameter"]["current"]
    guard = control["cycle_guard"]
    last_action = guard["last_adjustment_cycle_index"]
    rows, status = [], "COMPLETED"
    for index in range(plant["cycles"]):
        cycle_index = guard["current_cycle_index"] + index
        if not plant["interlock_ok"][index]:
            rows.append({"cycle": index, "cycle_index": cycle_index, "status": "HALTED", "reason": "SIMULATED_INTERLOCK_DROPOUT",
                         "parameter": current, "quantity": value})
            status = "HALTED"
            break
        lo, hi = control["response"]["validity_quantity"]
        if not lo <= value <= hi:
            rows.append({"cycle": index, "cycle_index": cycle_index, "status": "HALTED", "reason": "TOY_PLANT_OUTSIDE_RESPONSE_DOMAIN",
                         "parameter": current, "quantity": value})
            status = "HALTED"
            break
        if last_action is not None and cycle_index - last_action < guard["minimum_dwell_cycles"]:
            proposed, trial_status = current, "DWELLING"
        else:
            proposed, trial_status = _trial(control, value, current)
        next_value = value + plant["actual_gain_per_parameter"] * (proposed-current)
        rows.append({"cycle": index, "cycle_index": cycle_index, "status": trial_status, "parameter_before": current,
                     "parameter_after": proposed, "delta": proposed-current,
                     "quantity_before": value, "quantity_after": next_value})
        if proposed != current:
            last_action = cycle_index
        current, value = proposed, next_value
        if not lo <= value <= hi:
            rows[-1].update(status="HALTED", reason="TOY_PLANT_OUTSIDE_RESPONSE_DOMAIN")
            status = "HALTED"
            break
    return _report("ciw.polymer-control-simulation.v1", status=status,
        controller_id=control["controller_id"], semantics="synthetic_toy_cycle_response", cycles=rows,
        cycle_guard=guard,
        final_parameter=current, final_quantity=value, target=control["response"]["target"],
        source_refs=[control["response"]["gain_source_ref"]],
        limitations=["Instantaneous scalar linear toy plant; no physical latency, disturbances, or nonlinear dynamics",
                     "Each toy cycle supplies an immediate noiseless observation; physical measurement delays are not modeled",
                     "Convergence of this toy plant does not qualify a real molding controller"])


def example_model() -> dict:
    declarations = {"density_kg_m3": (950.0, 10.0), "heat_capacity_j_kg_k": (2000.0, 20.0),
        "volume_m3": (1e-6, 1e-8), "area_m2": (0.006, 0.00006),
        "heat_transfer_w_m2_k": (50.0, 1.0), "conductivity_w_m_k": (0.2, 0.01),
        "target_temperature_k": (330.0, 0.5)}
    cooling = {name: {"value": value, "standard_uncertainty": uncertainty,
        "source_ref": content_identity({"semantics": "synthetic_parameter_declaration", "quantity": name,
                                         "value": value, "standard_uncertainty": uncertainty})}
        for name, (value, uncertainty) in declarations.items()}
    cooling.update(temperature_sensor_id="part-temperature", ambient_sensor_id="cooling-water", forecast_horizon_s=5.0)
    return validate_model({"schema": MODEL_SCHEMA, "model_id": "synthetic-lumped-cooling.v1",
        "process": "injection_molding", "kind": "lumped_cooling_reference",
        "uncertainty_profile": "independent_first_order_declared", "cooling": cooling,
        "validity": {"temperature_k": [250.0, 550.0], "elapsed_s": [0.0, 120.0], "maximum_biot": 0.1,
                     "biot_uncertainty_multiplier": 2.0},
        "cavity_arrival": {"pressure_sensor_ids": ["cavity-1"], "threshold_pa": 1e6}})


def example_control() -> dict:
    gain = -0.0001
    return validate_control({"schema": CONTROL_SCHEMA, "controller_id": "synthetic-cycle-controller.v1",
        "process": "injection_molding", "mode": "simulation_only",
        "parameter": {"name": "cooling_time_s", "unit": "s", "current": 10.0,
                      "minimum": 2.0, "maximum": 30.0, "maximum_step": 1.0},
        "response": {"quantity": "part_dimension", "unit": "m", "target": 0.02, "tolerance": 0.00005,
            "local_gain_per_parameter": gain,
            "gain_source_ref": content_identity({"semantics": "synthetic_gain_declaration", "gain": gain}),
            "validity_quantity": [0.01, 0.03], "validity_parameter": [2.0, 30.0],
            "maximum_standard_uncertainty": 0.00002, "relaxation": 0.5},
        "cycle_guard": {"current_cycle_index": 10, "measurement_cycle_index": 10,
                        "last_adjustment_cycle_index": 0, "minimum_dwell_cycles": 3,
                        "maximum_measurement_delay_cycles": 3},
        "toy_plant": {"initial_quantity": 0.0204, "actual_gain_per_parameter": gain,
                      "cycles": 20, "interlock_ok": [True] * 20}})
