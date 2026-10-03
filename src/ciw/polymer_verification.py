"""Offline contracts and an independent finite polymer numerical audit.

The audit derives interval decisions and a lumped energy balance directly from
retained declarations. It never calls the metrology, engineering, or controller
providers. Agreement qualifies these finite calculations, not equipment,
calibration traceability, material behavior, or structural quality.
"""
from __future__ import annotations

from copy import deepcopy
import math

from .control_contracts import content_ref, detached, keys, number, text
from .operations.runner import check_seal, digest, seal
from .polymer_contract import AUTHORITY, validate_request
from .polymer_models import AUTHORITY as MODEL_AUTHORITY, PROPERTY_BOUNDS, validate_control

REPORT_SCHEMA = "ciw.polymer-numerical-verification.v1"
SCOPE = "finite_numeric_consistency_not_physical_validation"
CHECK_NAMES = (
    "retained_contract_and_source_binding", "independent_metrology_intervals",
    "lumped_energy_balance", "cooling_uncertainty", "cooling_target_limits",
    "nominal_pressure_brackets", "bounded_control_proposal",
)
LIMITATIONS = [
    "Finite numerical consistency of caller-declared samples, intervals, a homogeneous cooling model, and a local linear trial only.",
    "Interval multipliers and supplied uncertainties do not establish empirical coverage, calibration traceability, or independent sensor errors.",
    "A nominal pressure crossing identifies an instrumented threshold bracket, not a melt front or an unobserved cavity field.",
    "No trained engineering model, LLM inference, causal diagnosis, structural acceptance, physical validation, or machine actuation is established.",
    "Correct abstention is a numerical audit success; it does not qualify an out-of-domain model or unavailable observation.",
]
COOLING_ASSUMPTIONS = [
    "Homogeneous effective material properties and uniform part temperature",
    "Constant boundary temperature and heat-transfer coefficient",
    "Negligible latent heat, radiation, viscous heating, and spatial gradients",
    "Temperature sensors represent this part and its cooling boundary by declaration",
]
UNCERTAINTY_ASSUMPTIONS = [
    "First-order sensitivity; independent supplied standard uncertainties",
    "Clock skew reported separately as a bound; model discrepancy excluded",
    "Biot guard uses a declared uncertainty multiplier, not a validated coverage probability",
]
CONTROL_LIMITATIONS = [
    "Declared local linear response only; no defect-to-action or LLM-derived direction",
    "Declared cycle indices require independently established measurement attribution",
    "Requires machine-specific identification and separate control qualification before execution",
]
ENGINEERING_LIMITATIONS = [
    "No mold-flow, parison-thickness, structural integrity, or defect-cause reconstruction",
    "No learned model, accuracy guarantee, or physical validation supplied",
]
SIMULATION_LIMITATIONS = [
    "Instantaneous scalar linear toy plant; no physical latency, disturbances, or nonlinear dynamics",
    "Each toy cycle supplies an immediate noiseless observation; physical measurement delays are not modeled",
    "Convergence of this toy plant does not qualify a real molding controller",
]
SENSOR_REASONS = {
    "MISSING_OR_AMBIGUOUS_SENSOR", "INCOMPATIBLE_QUANTITY_OR_UNIT",
    "UNALIGNED_SENSOR", "MISSING_SAMPLES", "STALE_OR_UNCERTAIN_AGE",
}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _nonnegative(value):
    _require(number(value) >= 0, "Require a nonnegative retained result")


def _refs(values, expected=None):
    _require(type(values) is list, "Require retained references")
    for value in values:
        content_ref(value)
    if expected is not None:
        _require(values == expected, "Retained result evidence references differ from source")


def _measurement_rows(request, metrology):
    """Check exact retained sample projection, without recalculating intervals."""
    rows = metrology["measurements"]
    _require(type(rows) is list and len(rows) == len(request["sensors"]), "Measurement row coverage differs")
    for sensor, row in zip(request["sensors"], rows):
        keys(row, {"sensor_id", "quantity", "unit", "value", "standard_uncertainty", "time_s", "status", "source_refs"})
        for field in ("sensor_id", "quantity", "unit"):
            _require(row[field] == sensor[field], "Retained measurement descriptor differs")
        _refs(row["source_refs"], [sensor["source_ref"], sensor["calibration_ref"], sensor["clock_ref"]])
        sample = sensor["samples"][-1] if sensor["samples"] else None
        for field in ("value", "standard_uncertainty", "time_s"):
            _require(row[field] == (None if sample is None else sample[field]), "Measurement must retain the exact selected source sample")
        if sample is None:
            _require(row["status"] == "MISSING", "Missing sample cannot become a valid measurement")
        elif request["clock"]["end_s"] - sample["time_s"] > sensor["max_age_s"]:
            _require(row["status"] == "STALE", "Stale sample cannot become a valid measurement")
        else:
            _require(row["status"] in {"VALID", "UNALIGNED"}, "Fresh sample has an invalid retained status")
    return rows


def _validate_metrology(request, value):
    keys(value, {"schema", "status", "quantities", "measurements", "fusion_method", "time_semantics", "uncertainty_semantics", "measurement_condition", "authority"})
    _require(value["schema"] == "ciw.polymer-metrology.v1" and value["authority"] == AUTHORITY, "Metrology schema or authority differs")
    _require(value["fusion_method"] == "conservative_interval_union_no_independence_assumption", "Unsupported fusion interpretation")
    _require(value["time_semantics"] == "cycle_associated_not_simultaneous_multimodal_state", "Unsupported time interpretation")
    _require(value["uncertainty_semantics"] == "caller_declared_standard_uncertainty_and_multiplier_not_coverage_validation", "Unsupported uncertainty interpretation")
    _require(value["measurement_condition"] == request["measurement_condition"], "Measurement condition differs")
    rows = _measurement_rows(request, value)
    quantities = value["quantities"]
    _require(type(quantities) is list and len(quantities) == len(request["tolerances"]), "Tolerance result coverage differs")
    for spec, item in zip(request["tolerances"], quantities):
        keys(item, {"quantity", "unit", "status", "interval", "evidence_refs", "reason", "specification_ref"})
        for field in ("quantity", "unit", "specification_ref"):
            _require(item[field] == spec[field], "Tolerance result binding differs")
        matching = [row for row in rows if row["quantity"] == spec["quantity"]]
        _refs(item["evidence_refs"], sorted({ref for row in matching for ref in row["source_refs"]}))
        status, interval = item["status"], item["interval"]
        _require(status in {"CONFORMING", "NONCONFORMING", "INDETERMINATE"}, "Invalid interval decision")
        if interval is None:
            _require(status == "INDETERMINATE" and item["reason"] in {
                "missing_or_stale_required_channel", "sensor_times_exceed_declared_skew",
                "measurement_condition_differs_from_specification"}, "Missing interval cannot confer acceptance")
        else:
            _require(type(interval) is list and len(interval) == 2, "Require two retained interval endpoints")
            low, high = [number(entry) for entry in interval]
            _require(low <= high and matching and all(row["status"] == "VALID" for row in matching), "Invalid interval or observation status")
            _require(request["measurement_condition"] == spec["condition"], "Unconditioned measurements cannot satisfy this specification")
            expected = ("CONFORMING" if spec["lower"] <= low and high <= spec["upper"] else
                        "NONCONFORMING" if high < spec["lower"] or low > spec["upper"] else "INDETERMINATE")
            reasons = {"CONFORMING": "entire_declared_uncertainty_interval_inside_tolerance",
                       "NONCONFORMING": "entire_declared_uncertainty_interval_outside_tolerance",
                       "INDETERMINATE": "declared_uncertainty_interval_overlaps_tolerance_boundary"}
            _require(status == expected and item["reason"] == reasons[expected], "Retained interval and decision disagree")
    expected = ("NONCONFORMING" if any(item["status"] == "NONCONFORMING" for item in quantities) else
                "INDETERMINATE" if any(item["status"] == "INDETERMINATE" for item in quantities) else "CONFORMING")
    _require(value["status"] == expected, "Metrology aggregate status differs from retained decisions")


def _validate_cooling(request, value):
    _require(type(value) is dict, "Cooling result must be an object")
    status = value.get("status")
    if status == "ABSTAINED":
        reason = value.get("reason")
        if reason in SENSOR_REASONS:
            keys(value, {"status", "reason", "sensor_id"})
            _require(value["sensor_id"] in {request["model"]["cooling"]["temperature_sensor_id"], request["model"]["cooling"]["ambient_sensor_id"]}, "Abstention sensor differs")
        elif reason == "OUTSIDE_DECLARED_LUMPED_COOLING_DOMAIN":
            keys(value, {"status", "reason", "biot_number", "biot_standard_uncertainty", "biot_uncertainty_multiplier", "elapsed_s"})
            _nonnegative(value["biot_number"])
            _nonnegative(value["biot_standard_uncertainty"])
            _require(value["biot_uncertainty_multiplier"] == request["model"]["validity"]["biot_uncertainty_multiplier"], "Biot uncertainty multiplier differs")
            _nonnegative(value["elapsed_s"])
        else:
            keys(value, {"status", "reason"})
            _require(reason in {"TEMPERATURE_UNCERTAINTY_OUTSIDE_LINEAR_PROFILE", "TIMING_BOUND_OUTSIDE_NUMERICAL_PROFILE"}, "Unknown cooling abstention")
        return
    keys(value, {"status", "method", "temperature_k", "standard_uncertainty_k", "timing_temperature_bound_k", "elapsed_s", "time_constant_s", "biot_number", "biot_standard_uncertainty", "biot_uncertainty_multiplier", "target", "source_refs", "input_origins", "uncertainty_assumptions", "assumptions"})
    _require(status == "ESTIMATED" and value["method"] == "homogeneous_lumped_energy_balance", "Unsupported cooling estimate")
    _require(number(value["temperature_k"]) > 0 and number(value["time_constant_s"]) > 0, "Cooling temperature and time constant must be positive")
    for field in ("standard_uncertainty_k", "timing_temperature_bound_k", "elapsed_s", "biot_number", "biot_standard_uncertainty"):
        _nonnegative(value[field])
    cooling = request["model"]["cooling"]
    sensor_ids = {cooling["temperature_sensor_id"], cooling["ambient_sensor_id"]}
    inputs = [sensor for sensor in request["sensors"] if sensor["sensor_id"] in sensor_ids]
    _require(len(inputs) == 2, "Estimated cooling requires both retained temperature channels")
    _refs(value["source_refs"], sorted({sensor[field] for sensor in inputs for field in ("source_ref", "calibration_ref", "clock_ref")} | {cooling[name]["source_ref"] for name in PROPERTY_BOUNDS}))
    _require(value["biot_uncertainty_multiplier"] == request["model"]["validity"]["biot_uncertainty_multiplier"], "Biot uncertainty multiplier differs")
    _require(value["input_origins"] == sorted({sensor["origin"] for sensor in inputs}), "Cooling origins differ from source")
    _require(value["uncertainty_assumptions"] == UNCERTAINTY_ASSUMPTIONS and value["assumptions"] == COOLING_ASSUMPTIONS, "Cooling assumption scope differs")
    target = value["target"]
    target_status = target.get("status")
    if target_status == "UNREACHABLE":
        keys(target, {"status", "reason"})
        _require(target["reason"] == "TARGET_AT_OR_BELOW_BOUNDARY_TEMPERATURE", "Unknown unreachable target")
    elif target_status == "ABSTAINED":
        keys(target, {"status", "reason"})
        _require(target["reason"] == "TARGET_TIME_OUTSIDE_VALIDITY_OR_ILL_CONDITIONED", "Unknown target abstention")
    elif target_status == "ALREADY_SATISFIED":
        keys(target, {"status", "remaining_time_s", "standard_uncertainty_s"})
        _require(target["remaining_time_s"] == 0.0 and target["standard_uncertainty_s"] is None, "Already-satisfied target has invalid remaining time")
    else:
        keys(target, {"status", "remaining_time_s", "standard_uncertainty_s", "timing_bound_s"})
        _require(target_status == "ESTIMATED", "Invalid target estimate status")
        _nonnegative(target["remaining_time_s"])
        _nonnegative(target["standard_uncertainty_s"])
        _require(target["timing_bound_s"] == request["clock"]["max_skew_s"], "Target timing bound differs")


def _validate_arrivals(request, values):
    arrival = request["model"]["cavity_arrival"]
    identifiers = arrival["pressure_sensor_ids"]
    _require(type(values) is list and len(values) == len(identifiers), "Pressure location coverage differs")
    sensors = {sensor["sensor_id"]: sensor for sensor in request["sensors"]}
    base = {"sensor_id", "frame", "status", "threshold_pa", "source_refs", "origin", "claim", "spatial_extrapolation"}
    for identifier, value in zip(identifiers, values):
        _require(value.get("sensor_id") == identifier, "Pressure location binding differs")
        if value.get("reason") in SENSOR_REASONS:
            keys(value, {"sensor_id", "status", "reason"})
            _require(value["status"] == "ABSTAINED", "Unavailable pressure location must abstain")
            continue
        status = value.get("status")
        extras = ({"time_interval_s", "cadence_s", "timing_bound_s", "endpoint_standard_uncertainties_pa", "uncertainty_statement"}
                  if status == "BRACKETED" else {"reason"} if status == "ABSTAINED" else set())
        keys(value, base | extras)
        _require(identifier in sensors, "Pressure result has no retained sensor")
        sensor = sensors[identifier]
        _require(value["frame"] == sensor["frame"] and value["origin"] == sensor["origin"], "Pressure frame or origin differs")
        _refs(value["source_refs"], [sensor[field] for field in ("source_ref", "calibration_ref", "clock_ref")])
        _require(value["threshold_pa"] == arrival["threshold_pa"] and value["spatial_extrapolation"] is False
                 and value["claim"] == "nominal_pressure_threshold_at_measured_location", "Pressure result exceeds its declared scope")
        if status == "BRACKETED":
            interval = value["time_interval_s"]
            _require(type(interval) is list and len(interval) == 2, "Require sampled crossing endpoints")
            low, high = [number(entry) for entry in interval]
            stamps = [sample["time_s"] for sample in sensor["samples"]]
            _require(low < high and low in stamps and high in stamps and value["cadence_s"] == high-low, "Pressure bracket must use retained acquisition times")
            _require(value["timing_bound_s"] == request["clock"]["max_skew_s"], "Pressure timing bound differs")
            uncertainties = value["endpoint_standard_uncertainties_pa"]
            _require(type(uncertainties) is list and len(uncertainties) == 2, "Require both endpoint uncertainties")
            for entry in uncertainties:
                _nonnegative(entry)
            _require(value["uncertainty_statement"] == "Nominal sampled crossing; no sub-sample timing, confidence guarantee, or melt-front identity", "Pressure uncertainty scope differs")
        elif status == "ABSTAINED":
            _require(value["reason"] in {"LEFT_CENSORED_THRESHOLD_ALREADY_EXCEEDED", "NO_POSITIVE_TIME_BRACKET"}, "Unknown nominal crossing abstention")
        else:
            _require(status == "NOT_OBSERVED", "Unknown nominal crossing status")


def _validate_engineering(request, value):
    keys(value, {"schema", "authority", "status", "identity", "model_id", "semantics", "cooling", "cavity_arrival", "limitations"})
    _require(value["schema"] == "ciw.polymer-engineering-estimate.v1", "Engineering schema differs")
    _assert_equal(value["authority"], MODEL_AUTHORITY, "Engineering authority")
    _require(value["identity"] == request["identity"] and value["model_id"] == request["model"]["model_id"], "Engineering identity differs")
    _require(value["semantics"] == "reference_estimate" and value["limitations"] == ENGINEERING_LIMITATIONS, "Engineering scope differs")
    _validate_cooling(request, value["cooling"])
    _require(value["status"] == value["cooling"]["status"], "Engineering status differs from cooling result")
    _validate_arrivals(request, value["cavity_arrival"])


def _validate_proposal(request, metrology, value):
    common = {"schema", "authority", "identity", "controller_id", "mode", "parameter", "unit", "cycle_guard", "measurement_cycle_index", "trial_cycle_index", "limitations", "status"}
    status = value.get("status")
    fields = {"reason"} if status == "ABSTAINED" else {"measured_quantity", "measured_value", "measurement_standard_uncertainty", "current", "proposed", "delta", "target", "local_gain_per_parameter", "source_refs"}
    keys(value, common | fields)
    control, parameter = request["control"], request["control"]["parameter"]
    response = control["response"]
    _require(value["schema"] == "ciw.polymer-control-proposal.v1", "Control proposal schema differs")
    _assert_equal(value["authority"], MODEL_AUTHORITY, "Control proposal authority")
    _require(value["identity"] == request["identity"] and value["controller_id"] == control["controller_id"], "Control proposal identity differs")
    _require(value["mode"] == "simulation_only" and value["parameter"] == parameter["name"] and value["unit"] == parameter["unit"], "Control scope differs")
    guard = control["cycle_guard"]
    _require(value["cycle_guard"] == guard and value["measurement_cycle_index"] == guard["measurement_cycle_index"]
             and value["trial_cycle_index"] == guard["current_cycle_index"]+1, "Control cycle attribution differs")
    _require(value["limitations"] == CONTROL_LIMITATIONS, "Control limitations differ")
    if status == "ABSTAINED":
        _require(value["reason"] in {"INDETERMINATE_METROLOGY", "MISSING_STALE_OR_AMBIGUOUS_QUALITY_MEASUREMENT", "QUALITY_OUTSIDE_GAIN_DOMAIN_OR_UNCERTAINTY_BUDGET",
                 "MISSING_OR_AMBIGUOUS_RESPONSE_SPECIFICATION", "RESPONSE_MEASUREMENT_CONDITION_MISMATCH", "UNQUALIFIED_RESPONSE_METROLOGY",
                 "MEASUREMENT_CYCLE_TOO_OLD", "MINIMUM_CYCLE_DWELL_NOT_ELAPSED", "NO_MEASUREMENT_AFTER_PRIOR_ADJUSTMENT"}, "Unknown control abstention")
        return
    _require(status in {"PROPOSED", "NO_CHANGE", "BOUND_LIMITED"}, "Unknown trial status")
    _require(metrology["status"] in {"CONFORMING", "NONCONFORMING"}, "Indeterminate metrology cannot support a trial")
    specs = [spec for spec in request["tolerances"]
             if spec["quantity"] == response["quantity"] and spec["unit"] == response["unit"]]
    _require(len(specs) == 1, "Trial requires one response-specific specification")
    _require(request["measurement_condition"] == specs[0]["condition"]
             and metrology["measurement_condition"] == request["measurement_condition"],
             "Trial response measurement condition differs from its specification")
    qualities = [item for item in metrology["quantities"]
                 if item["quantity"] == response["quantity"] and item["unit"] == response["unit"]]
    _require(len(qualities) == 1 and qualities[0]["status"] in {"CONFORMING", "NONCONFORMING"}
             and qualities[0]["specification_ref"] == specs[0]["specification_ref"],
             "Trial requires a determinate specification-bound response quantity")
    last = guard["last_adjustment_cycle_index"]
    _require(guard["current_cycle_index"]-guard["measurement_cycle_index"] <= guard["maximum_measurement_delay_cycles"], "Trial uses a delayed measurement")
    _require(last is None or (guard["current_cycle_index"]-last >= guard["minimum_dwell_cycles"] and guard["measurement_cycle_index"] > last), "Trial precedes dwell or post-adjustment observation")
    rows = [row for row in metrology["measurements"] if row["quantity"] == response["quantity"] and row["unit"] == response["unit"]]
    _require(len(rows) == 1 and rows[0]["status"] == "VALID", "Trial requires one available quality observation")
    row = rows[0]
    _require(value["measured_quantity"] == response["quantity"] and value["measured_value"] == row["value"]
             and value["measurement_standard_uncertainty"] == row["standard_uncertainty"], "Trial quality observation differs")
    _require(value["current"] == parameter["current"] and value["target"] == response["target"]
             and value["local_gain_per_parameter"] == response["local_gain_per_parameter"], "Trial configuration differs")
    current, proposed, delta = [number(value[field]) for field in ("current", "proposed", "delta")]
    _require(parameter["minimum"] <= proposed <= parameter["maximum"] and _close(delta, proposed-current)
             and abs(delta) <= parameter["maximum_step"] + 1e-12, "Trial exceeds parameter or rate bounds")
    low, high = response["validity_quantity"]
    _require(low <= row["value"] <= high and row["standard_uncertainty"] <= response["maximum_standard_uncertainty"], "Trial exceeds response or uncertainty domain")
    _require((status == "PROPOSED") == (proposed != current), "Trial status and parameter movement disagree")
    _refs(value["source_refs"], sorted(set(row["source_refs"] + [response["gain_source_ref"]])))


def validate_assessment(request: dict, data: dict) -> None:
    """Inspect retained shapes, exact sample bindings and non-actuation flags.

    This intentionally does not recompute cooling, interval endpoints, pressure
    crossings, or optimization. Use ``verify`` for a fresh numerical audit.
    """
    request = validate_request(request)
    detached(data)
    keys(data, {"schema", "source_ref", "identity", "process", "source_kind", "metrology", "engineering", "control", "authority"})
    _require(data["schema"] == "ciw.polymer-assessment.v1" and data["source_ref"] == digest(request), "Assessment source binding differs")
    _require(data["identity"] == request["identity"] and data["process"] == request["process"]
             and data["source_kind"] == request["source_kind"] and data["authority"] == AUTHORITY, "Assessment identity or authority differs")
    _validate_metrology(request, data["metrology"])
    _validate_engineering(request, data["engineering"])
    _validate_proposal(request, data["metrology"], data["control"])


def _close(actual, expected):
    return math.isclose(number(actual), number(expected), rel_tol=2e-12, abs_tol=1e-14)


def _assert_equal(actual, expected, label="result"):
    if type(expected) in (int, float):
        _require(type(actual) in (int, float) and _close(actual, expected), label + " numerical mismatch")
    elif type(expected) is dict:
        _require(type(actual) is dict and set(actual) == set(expected), label + " fields differ")
        for field in expected:
            _assert_equal(actual[field], expected[field], label + "." + field)
    elif type(expected) is list:
        _require(type(actual) is list and len(actual) == len(expected), label + " dimensions differ")
        for index, (left, right) in enumerate(zip(actual, expected)):
            _assert_equal(left, right, label + "." + str(index))
    else:
        _require(actual == expected and type(actual) is type(expected), label + " declaration differs")


def _metrology_oracle(request):
    """Source interval hull; no statistics or precision gain are inferred."""
    rows = []
    for sensor in request["sensors"]:
        sample = sensor["samples"][-1] if sensor["samples"] else None
        status = "MISSING" if sample is None else "STALE" if request["clock"]["end_s"]-sample["time_s"] > sensor["max_age_s"] else "VALID"
        rows.append({"sensor_id": sensor["sensor_id"], "quantity": sensor["quantity"], "unit": sensor["unit"],
                     "value": sample["value"] if sample else None, "standard_uncertainty": sample["standard_uncertainty"] if sample else None,
                     "time_s": sample["time_s"] if sample else None, "status": status,
                     "source_refs": [sensor["source_ref"], sensor["calibration_ref"], sensor["clock_ref"]]})
    results = []
    for spec in request["tolerances"]:
        matching = [row for row in rows if row["quantity"] == spec["quantity"]]
        available = [row for row in matching if row["status"] == "VALID"]
        interval, status, reason = None, "INDETERMINATE", "missing_or_stale_required_channel"
        if available and max(row["time_s"] for row in available)-min(row["time_s"] for row in available) > request["clock"]["max_skew_s"]:
            reason = "sensor_times_exceed_declared_skew"
            for row in available:
                row["status"] = "UNALIGNED"
        elif request["measurement_condition"] != spec["condition"]:
            reason = "measurement_condition_differs_from_specification"
        elif matching and len(matching) == len(available):
            endpoints = [(row["value"]-spec["coverage_factor"]*row["standard_uncertainty"],
                          row["value"]+spec["coverage_factor"]*row["standard_uncertainty"]) for row in available]
            interval = [min(pair[0] for pair in endpoints), max(pair[1] for pair in endpoints)]
            if interval[0] >= spec["lower"] and interval[1] <= spec["upper"]:
                status, reason = "CONFORMING", "entire_declared_uncertainty_interval_inside_tolerance"
            elif interval[0] > spec["upper"] or interval[1] < spec["lower"]:
                status, reason = "NONCONFORMING", "entire_declared_uncertainty_interval_outside_tolerance"
            else:
                reason = "declared_uncertainty_interval_overlaps_tolerance_boundary"
        results.append({"quantity": spec["quantity"], "unit": spec["unit"], "status": status, "interval": interval,
                        "evidence_refs": sorted({ref for row in matching for ref in row["source_refs"]}),
                        "reason": reason, "specification_ref": spec["specification_ref"]})
    overall = "NONCONFORMING" if any(row["status"] == "NONCONFORMING" for row in results) else "INDETERMINATE" if any(row["status"] == "INDETERMINATE" for row in results) else "CONFORMING"
    return {"status": overall, "quantities": results, "measurements": rows}


def _available_sensor(request, identifier, quantity, unit):
    matches = [sensor for sensor in request["sensors"] if sensor["sensor_id"] == identifier]
    if len(matches) != 1:
        return None, "MISSING_OR_AMBIGUOUS_SENSOR"
    sensor = matches[0]
    if sensor["quantity"] != quantity or sensor["unit"] != unit:
        return None, "INCOMPATIBLE_QUANTITY_OR_UNIT"
    if sensor["clock_id"] != request["clock"]["id"] or sensor["frame"] != request["frame"]:
        return None, "UNALIGNED_SENSOR"
    if not sensor["samples"]:
        return None, "MISSING_SAMPLES"
    age = request["clock"]["end_s"]-sensor["samples"][-1]["time_s"]
    if age < 0 or age+request["clock"]["max_skew_s"] > sensor["max_age_s"]:
        return None, "STALE_OR_UNCERTAIN_AGE"
    return sensor, None


def _cooling_oracle(request):
    """Closed-form energy balance and analytic first-order derivatives.

    Heat capacity C=rho*cp*V and conductance G=h*A give C*dT/dt=-G*(T-Ta).
    Derivatives of T and target time are formed explicitly for the independent
    supplied uncertainties; timing skew remains a separate deterministic bound.
    """
    model = request["model"]
    cooling = model["cooling"]
    channels = []
    for key, quantity in (("temperature_sensor_id", "part_temperature"), ("ambient_sensor_id", "cooling_water_temperature")):
        sensor, reason = _available_sensor(request, cooling[key], quantity, "K")
        if reason:
            return {"status": "ABSTAINED", "reason": reason, "sensor_id": cooling[key]}
        channels.append(sensor)
    part, boundary = [sensor["samples"][-1] for sensor in channels]
    initial, ambient = part["value"], boundary["value"]
    u_initial, u_ambient = part["standard_uncertainty"], boundary["standard_uncertainty"]
    p = {name: cooling[name]["value"] for name in PROPERTY_BOUNDS}
    u = {name: cooling[name]["standard_uncertainty"] for name in PROPERTY_BOUNDS}
    capacity = p["density_kg_m3"]*p["heat_capacity_j_kg_k"]*p["volume_m3"]
    conductance = p["heat_transfer_w_m2_k"]*p["area_m2"]
    tau = capacity/conductance
    biot = conductance*p["volume_m3"]/(p["area_m2"]**2*p["conductivity_w_m_k"])
    biot_variance = biot**2*sum((u[name]/p[name])**2 for name in (
        "heat_transfer_w_m2_k", "volume_m3", "area_m2", "conductivity_w_m_k"))
    biot_uncertainty = math.sqrt(biot_variance)
    age = request["clock"]["end_s"]-part["time_s"]
    elapsed = age+cooling["forecast_horizon_s"]
    validity = model["validity"]
    target = p["target_temperature_k"]
    tlo, thi = validity["temperature_k"]
    if (not all(tlo <= t <= thi for t in (initial, ambient, target)) or
            not validity["elapsed_s"][0] <= elapsed <= validity["elapsed_s"][1] or
            biot+validity["biot_uncertainty_multiplier"]*biot_uncertainty > validity["maximum_biot"] or initial <= ambient):
        return {"status": "ABSTAINED", "reason": "OUTSIDE_DECLARED_LUMPED_COOLING_DOMAIN", "biot_number": biot,
                "biot_standard_uncertainty": biot_uncertainty, "biot_uncertainty_multiplier": validity["biot_uncertainty_multiplier"], "elapsed_s": elapsed}
    if u_initial > 0.2*initial or u_ambient > 0.2*ambient:
        return {"status": "ABSTAINED", "reason": "TEMPERATURE_UNCERTAINTY_OUTSIDE_LINEAR_PROFILE"}
    rate = conductance/capacity
    decay = math.exp(-rate*elapsed)
    delta = initial-ambient
    prediction = ambient+delta*decay
    relative_tau_variance = sum((u[name]/p[name])**2 for name in (
        "density_kg_m3", "heat_capacity_j_kg_k", "volume_m3", "area_m2", "heat_transfer_w_m2_k"))
    prediction_variance = (decay*u_initial)**2+((1-decay)*u_ambient)**2+(delta*decay*elapsed*rate)**2*relative_tau_variance
    timing = request["clock"]["max_skew_s"]
    temperature_bound = delta*decay*math.expm1(min(timing/tau, 700.0))
    if not math.isfinite(temperature_bound) or temperature_bound > thi-tlo:
        return {"status": "ABSTAINED", "reason": "TIMING_BOUND_OUTSIDE_NUMERICAL_PROFILE"}
    if target >= initial:
        target_result = {"status": "ALREADY_SATISFIED", "remaining_time_s": 0.0, "standard_uncertainty_s": None}
    elif target <= ambient:
        target_result = {"status": "UNREACHABLE", "reason": "TARGET_AT_OR_BELOW_BOUNDARY_TEMPERATURE"}
    else:
        total = math.log(delta/(target-ambient))/rate
        if total > validity["elapsed_s"][1] or target-ambient <= 5*math.hypot(u_ambient, u["target_temperature_k"]):
            target_result = {"status": "ABSTAINED", "reason": "TARGET_TIME_OUTSIDE_VALIDITY_OR_ILL_CONDITIONED"}
        else:
            derivative_initial = 1/(rate*delta)
            derivative_ambient = (1/(target-ambient)-1/delta)/rate
            derivative_target = -1/(rate*(target-ambient))
            time_variance = total**2*relative_tau_variance+(derivative_initial*u_initial)**2+(derivative_ambient*u_ambient)**2+(derivative_target*u["target_temperature_k"])**2
            target_result = {"status": "ESTIMATED", "remaining_time_s": max(total-age, 0.0),
                             "standard_uncertainty_s": math.sqrt(time_variance), "timing_bound_s": timing}
    return {"status": "ESTIMATED", "temperature_k": prediction, "standard_uncertainty_k": math.sqrt(prediction_variance),
            "timing_temperature_bound_k": temperature_bound, "elapsed_s": elapsed, "time_constant_s": tau,
            "biot_number": biot, "biot_standard_uncertainty": biot_uncertainty,
            "biot_uncertainty_multiplier": validity["biot_uncertainty_multiplier"], "target": target_result}


def _arrival_oracle(request):
    reports = []
    arrival = request["model"]["cavity_arrival"]
    threshold = arrival["threshold_pa"]
    for identifier in arrival["pressure_sensor_ids"]:
        sensor, reason = _available_sensor(request, identifier, "cavity_pressure", "Pa")
        if reason:
            reports.append({"sensor_id": identifier, "status": "ABSTAINED", "reason": reason})
            continue
        row = {"sensor_id": identifier, "frame": sensor["frame"], "status": "NOT_OBSERVED",
               "threshold_pa": threshold, "source_refs": [sensor[field] for field in ("source_ref", "calibration_ref", "clock_ref")], "origin": sensor["origin"],
               "claim": "nominal_pressure_threshold_at_measured_location", "spatial_extrapolation": False}
        samples = sensor["samples"]
        if samples[0]["value"] >= threshold:
            row.update(status="ABSTAINED", reason="LEFT_CENSORED_THRESHOLD_ALREADY_EXCEEDED")
        else:
            crossing = next(((left, right) for left, right in zip(samples, samples[1:])
                             if left["value"] < threshold and right["value"] >= threshold), None)
            if crossing:
                left, right = crossing
                row.update(status="BRACKETED", time_interval_s=[left["time_s"], right["time_s"]],
                           cadence_s=right["time_s"]-left["time_s"], timing_bound_s=request["clock"]["max_skew_s"],
                           endpoint_standard_uncertainties_pa=[left["standard_uncertainty"], right["standard_uncertainty"]],
                           uncertainty_statement="Nominal sampled crossing; no sub-sample timing, confidence guarantee, or melt-front identity")
        reports.append(row)
    return reports


def _control_oracle(request, metrology):
    control, parameter = request["control"], request["control"]["parameter"]
    response = control["response"]
    if metrology["status"] == "INDETERMINATE":
        return {"status": "ABSTAINED", "reason": "INDETERMINATE_METROLOGY"}
    specs = [spec for spec in request["tolerances"]
             if (spec["quantity"], spec["unit"]) == (response["quantity"], response["unit"])]
    if len(specs) != 1:
        return {"status": "ABSTAINED", "reason": "MISSING_OR_AMBIGUOUS_RESPONSE_SPECIFICATION"}
    # The independent metrology oracle derives its condition from this request;
    # retained report condition binding is checked by the offline contract.
    if specs[0]["condition"] != request["measurement_condition"]:
        return {"status": "ABSTAINED", "reason": "RESPONSE_MEASUREMENT_CONDITION_MISMATCH"}
    quantities = [item for item in metrology["quantities"]
                  if (item["quantity"], item["unit"]) == (response["quantity"], response["unit"])]
    if (len(quantities) != 1 or quantities[0]["status"] not in {"CONFORMING", "NONCONFORMING"}
            or quantities[0]["specification_ref"] != specs[0]["specification_ref"]):
        return {"status": "ABSTAINED", "reason": "UNQUALIFIED_RESPONSE_METROLOGY"}
    guard = control["cycle_guard"]
    current_cycle, measured_cycle = guard["current_cycle_index"], guard["measurement_cycle_index"]
    last_cycle = guard["last_adjustment_cycle_index"]
    if current_cycle-measured_cycle > guard["maximum_measurement_delay_cycles"]:
        return {"status": "ABSTAINED", "reason": "MEASUREMENT_CYCLE_TOO_OLD"}
    if last_cycle is not None and current_cycle-last_cycle < guard["minimum_dwell_cycles"]:
        return {"status": "ABSTAINED", "reason": "MINIMUM_CYCLE_DWELL_NOT_ELAPSED"}
    if last_cycle is not None and measured_cycle <= last_cycle:
        return {"status": "ABSTAINED", "reason": "NO_MEASUREMENT_AFTER_PRIOR_ADJUSTMENT"}
    rows = [row for row in metrology["measurements"] if row["quantity"] == response["quantity"] and row["unit"] == response["unit"]]
    if len(rows) != 1 or rows[0]["status"] != "VALID":
        return {"status": "ABSTAINED", "reason": "MISSING_STALE_OR_AMBIGUOUS_QUALITY_MEASUREMENT"}
    row = rows[0]
    if not response["validity_quantity"][0] <= row["value"] <= response["validity_quantity"][1] or row["standard_uncertainty"] > response["maximum_standard_uncertainty"]:
        return {"status": "ABSTAINED", "reason": "QUALITY_OUTSIDE_GAIN_DOMAIN_OR_UNCERTAINTY_BUDGET"}
    current = parameter["current"]
    error = row["value"]-response["target"]
    if abs(error) <= response["tolerance"]:
        proposed, status = current, "NO_CHANGE"
    else:
        correction = response["relaxation"]*(response["target"]-row["value"])/response["local_gain_per_parameter"]
        limited = min(max(correction, -parameter["maximum_step"]), parameter["maximum_step"])
        proposed = min(max(current+limited, parameter["minimum"]), parameter["maximum"])
        status = "BOUND_LIMITED" if proposed == current else "PROPOSED"
    return {"status": status, "measured_quantity": response["quantity"], "measured_value": row["value"],
            "measurement_standard_uncertainty": row["standard_uncertainty"], "current": current,
            "proposed": proposed, "delta": proposed-current, "target": response["target"],
            "local_gain_per_parameter": response["local_gain_per_parameter"],
            "source_refs": sorted(set(row["source_refs"]+[response["gain_source_ref"]]))}


def validate_simulation(control: dict, simulation: dict) -> None:
    """Offline bounds, lineage and interlock audit; never execute a simulator."""
    control = validate_control(control)
    detached(simulation)
    keys(simulation, {"schema", "authority", "status", "controller_id", "semantics", "cycles", "cycle_guard", "final_parameter", "final_quantity", "target", "source_refs", "limitations"})
    _require(simulation["schema"] == "ciw.polymer-control-simulation.v1", "Simulation schema differs")
    _assert_equal(simulation["authority"], MODEL_AUTHORITY, "Simulation authority")
    _require(simulation["controller_id"] == control["controller_id"] and simulation["semantics"] == "synthetic_toy_cycle_response", "Simulation identity or semantics differ")
    _require(simulation["target"] == control["response"]["target"] and simulation["limitations"] == SIMULATION_LIMITATIONS, "Simulation scope differs")
    _refs(simulation["source_refs"], [control["response"]["gain_source_ref"]])
    plant, parameter, response = control["toy_plant"], control["parameter"], control["response"]
    guard = control["cycle_guard"]
    _require(simulation["cycle_guard"] == guard, "Simulation cycle guard differs")
    last_action = guard["last_adjustment_cycle_index"]
    rows = simulation["cycles"]
    _require(type(rows) is list and 1 <= len(rows) <= plant["cycles"], "Invalid simulation cycle count")
    current, quantity = parameter["current"], plant["initial_quantity"]
    halted = False
    low, high = response["validity_quantity"]
    for index, row in enumerate(rows):
        _require(row.get("cycle") == index and type(row["cycle"]) is int and not halted, "Simulation sequence differs or continues after halt")
        cycle_index = guard["current_cycle_index"]+index
        _require(row.get("cycle_index") == cycle_index and type(row["cycle_index"]) is int, "Simulation cycle attribution differs")
        if "parameter" in row:
            keys(row, {"cycle", "cycle_index", "status", "reason", "parameter", "quantity"})
            _require(row["status"] == "HALTED" and row["parameter"] == current and row["quantity"] == quantity, "Halt row differs from previous state")
            expected = "SIMULATED_INTERLOCK_DROPOUT" if not plant["interlock_ok"][index] else "TOY_PLANT_OUTSIDE_RESPONSE_DOMAIN" if not low <= quantity <= high else None
            _require(row["reason"] == expected and expected is not None, "Simulation halt has no retained interlock or domain cause")
            halted = True
            continue
        fields = {"cycle", "cycle_index", "status", "parameter_before", "parameter_after", "delta", "quantity_before", "quantity_after"}
        if row.get("status") == "HALTED":
            fields.add("reason")
        keys(row, fields)
        _require(plant["interlock_ok"][index] is True and low <= quantity <= high, "Simulation moves despite failed prerequisites")
        _require(row["parameter_before"] == current and row["quantity_before"] == quantity, "Simulation state continuity differs")
        after, delta, next_quantity = [number(row[field]) for field in ("parameter_after", "delta", "quantity_after")]
        _require(parameter["minimum"] <= after <= parameter["maximum"] and _close(delta, after-current)
                 and abs(delta) <= parameter["maximum_step"]+1e-12, "Simulated trial exceeds parameter or rate bounds")
        _require(_close(next_quantity, quantity+plant["actual_gain_per_parameter"]*delta), "Simulated plant transition differs from declared scalar response")
        status = row["status"]
        dwell_required = last_action is not None and cycle_index-last_action < guard["minimum_dwell_cycles"]
        _require(not dwell_required or status == "DWELLING" and after == current, "Simulation changes parameter before dwell completes")
        _require(status != "DWELLING" or dwell_required, "Dwell row has no active dwell guard")
        if not low <= next_quantity <= high:
            _require(status == "HALTED" and row["reason"] == "TOY_PLANT_OUTSIDE_RESPONSE_DOMAIN", "Out-of-domain simulated state must halt immediately")
            halted = True
        else:
            _require(status in {"PROPOSED", "NO_CHANGE", "BOUND_LIMITED", "DWELLING"}, "Unknown simulated trial status")
            _require((status == "PROPOSED") == (after != current), "Simulated status differs from movement")
            if status == "NO_CHANGE":
                _require(abs(quantity-response["target"]) <= response["tolerance"], "No-change result lies outside the deadband")
        if after != current:
            last_action = cycle_index
        current, quantity = after, next_quantity
    _require(simulation["status"] == ("HALTED" if halted else "COMPLETED"), "Simulation aggregate status differs")
    _require(halted or len(rows) == plant["cycles"], "Completed simulation omits declared cycles")
    _require(simulation["final_parameter"] == current and simulation["final_quantity"] == quantity, "Simulation final state differs from trace")


def _select(value, fields):
    return {field: value[field] for field in fields}


def verify(request: dict, assessment: dict) -> dict:
    """Fresh independent numeric checks, returning a sealed PASS/FAIL report."""
    checks = []
    try:
        validate_assessment(request, assessment)
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        checks.append({"name": CHECK_NAMES[0], "status": "FAIL", "detail": str(exc) or type(exc).__name__})
        checks.extend({"name": name, "status": "SKIP", "detail": "Retained contract or source binding rejected"} for name in CHECK_NAMES[1:])
    else:
        checks.append({"name": CHECK_NAMES[0], "status": "PASS", "detail": "Retained samples, source references and non-actuation authority match"})
        metrology = _metrology_oracle(request)
        cooling = _cooling_oracle(request)
        actual_cooling = assessment["engineering"]["cooling"]
        actual_control = assessment["control"]
        control = _control_oracle(request, metrology)
        if cooling["status"] == "ABSTAINED":
            energy_actual, energy_expected = actual_cooling, cooling
            uncertainty_actual, uncertainty_expected = actual_cooling, cooling
            target_actual, target_expected = actual_cooling, cooling
        else:
            energy_fields = ("status", "temperature_k", "elapsed_s", "time_constant_s", "biot_number")
            uncertainty_fields = ("standard_uncertainty_k", "timing_temperature_bound_k", "biot_standard_uncertainty", "biot_uncertainty_multiplier")
            energy_actual = _select(actual_cooling, energy_fields) if all(field in actual_cooling for field in energy_fields) else actual_cooling
            uncertainty_actual = _select(actual_cooling, uncertainty_fields) if all(field in actual_cooling for field in uncertainty_fields) else actual_cooling
            energy_expected, uncertainty_expected = _select(cooling, energy_fields), _select(cooling, uncertainty_fields)
            target_actual, target_expected = actual_cooling.get("target"), cooling["target"]
        comparisons = (
            (_select(assessment["metrology"], metrology), metrology),
            (energy_actual, energy_expected), (uncertainty_actual, uncertainty_expected),
            (target_actual, target_expected),
            (assessment["engineering"]["cavity_arrival"], _arrival_oracle(request)),
            (_select(actual_control, control) if all(field in actual_control for field in control) else actual_control, control),
        )
        for name, (actual, expected) in zip(CHECK_NAMES[1:], comparisons):
            try:
                _assert_equal(actual, expected, name)
            except (ValueError, TypeError, KeyError, OverflowError) as exc:
                checks.append({"name": name, "status": "FAIL", "detail": str(exc) or type(exc).__name__})
            else:
                checks.append({"name": name, "status": "PASS", "detail": "Independent finite reference agrees; physical validation remains unestablished"})
    report = seal({"schema": REPORT_SCHEMA, "request_ref": digest(request), "assessment_ref": digest(assessment),
                   "status": "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL",
                   "scope": SCOPE, "independent": True, "checks": checks, "authority": deepcopy(AUTHORITY),
                   "limitations": deepcopy(LIMITATIONS)})
    validate_report(report)
    return report


def validate_report(report: dict) -> None:
    """Read report structure and status without running a numerical oracle."""
    detached(report)
    keys(report, {"schema", "record_digest", "request_ref", "assessment_ref", "status", "scope", "independent", "checks", "authority", "limitations"})
    check_seal(report)
    _require(report["schema"] == REPORT_SCHEMA and report["scope"] == SCOPE and report["independent"] is True, "Verification report scope differs")
    _require(report["authority"] == AUTHORITY and report["limitations"] == LIMITATIONS, "Verification report exceeds numerical authority")
    content_ref(report["request_ref"])
    content_ref(report["assessment_ref"])
    checks = report["checks"]
    _require(type(checks) is list and len(checks) == len(CHECK_NAMES), "Verification check coverage differs")
    for name, check in zip(CHECK_NAMES, checks):
        keys(check, {"name", "status", "detail"})
        _require(check["name"] == name and check["status"] in {"PASS", "FAIL", "SKIP"}, "Invalid verification check")
        text(check["detail"])
    expected = "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL"
    _require(report["status"] == expected, "Verification status differs from retained checks")
    _require(not any(item["status"] == "SKIP" for item in checks) or checks[0]["status"] == "FAIL", "Skipped numeric checks require a rejected retained contract")
