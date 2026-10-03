"""Fresh independent irrigation audit and structural-only retained inspection."""
from __future__ import annotations

from copy import deepcopy
import math

from .control_contracts import content_ref, json_tree, keys, number
from .irrigation_contract import REPORT_SCHEMA, SCOPE, validate_request, validate_result
from .irrigation_reference import REFERENCE_ID, reference
from .operations.runner import check_seal, digest, seal

VERIFIER_ID = "independent_irrigation_fao56_gls_balance_budget_audit_binary64.v1"
THRESHOLDS = {"absolute": 1e-9, "relative": 1e-9}
MAX_RESIDUAL = 1e150
CHECK_NAMES = (
    "retained_request_result_binding", "fao56_reference_et0", "replica_gls_fusion",
    "initial_root_zone_capacity", "daily_root_zone_balance", "stress_and_crop_et",
    "priority_pump_budget_allocation", "conditional_initial_uncertainty_screening",
    "planning_eligibility_and_decisions", "flow_pressure_telemetry",
    "explicit_water_mass_closure", "gross_net_units_and_pump_limits",
)
LIMITATIONS = [
    "Finite binary64 numerical consistency of declared daily FAO56 reference-ET, early-wetting root-zone bucket and list-priority pump allocation only.",
    "Soil observations represent one common root-zone mean by declaration; calibration, covariance, clock references and spatial representativeness are not independently established.",
    "Initial-soil uncertainty alone is propagated conditionally with the same allocated irrigation; fixed weather, crop parameters, geometry, application efficiency and model discrepancy have no propagated uncertainty or demonstrated forecast coverage.",
    "Single-coefficient crop stress and same-day drainage are declared approximations; no Richards PDE, infiltration dynamics, canopy reconstruction, salinity or fertigation chemistry is qualified.",
    "Flow and pressure residual indicators do not uniquely identify a leak, clog, stuck valve or causal mechanism; no live sensor acquisition or hardware actuation is performed.",
    "Numerically correct abstention, review or unmet allocation can receive LOCAL arithmetic qualification; planning eligibility remains separately retained and does not establish field readiness.",
    "No physical validation, trained forecast, equipment qualification or canonical state admission is established.",
    "Content seals bind retained declarations, not authenticity. A coherently forged retained report can pass structural inspection; fresh numerical verification is required to reassess its calculations.",
]


def _error(observed, expected):
    if type(observed) in (int, float) and type(expected) in (int, float):
        value = abs(observed - expected) / (1.0 + abs(expected))
        return min(value, MAX_RESIDUAL) if math.isfinite(value) else MAX_RESIDUAL
    return 0.0 if type(observed) is type(expected) and observed == expected else 1.0


def _compare(observed, expected):
    if type(expected) is dict:
        if type(observed) is not dict or set(observed) != set(expected):
            return 1.0
        return max([0.0] + [_compare(observed[name], expected[name]) for name in expected])
    if type(expected) is list:
        if type(observed) is not list or len(observed) != len(expected):
            return 1.0
        return max([0.0] + [_compare(a, b) for a, b in zip(observed, expected)])
    return _error(observed, expected)


def _fields(observed, expected, fields):
    return max([0.0] + [_compare(observed[name], expected[name]) for name in fields])


def _reference_identity(request, projection_digest):
    return {"method": REFERENCE_ID, "request_digest": digest(request), "projection_digest": projection_digest,
            "day_count": len(request["weather"]), "zone_count": len(request["zones"]),
            "observation_count": sum(len(z["soil_measurements"]["observations"]) for z in request["zones"]),
            "telemetry_count": len(request["telemetry"])}


def _summary(result):
    return {"planning_status": result["planning_status"], "day_count": len(result["days"]),
            "zone_count": len(result["initial_zones"]), "telemetry_count": len(result["telemetry"]),
            "total_allocated_gross_m3": math.fsum(d["allocated_gross_m3"] for d in result["days"]),
            "total_unmet_gross_m3": math.fsum(d["unmet_gross_m3"] for d in result["days"]),
            "total_pump_hours": math.fsum(d["pump_hours"] for d in result["days"])}


def _qualification(result, passed):
    return {"action": "LOCAL" if passed else "REFUSE", "scope": SCOPE,
            "planning_status": result["planning_status"],
            "reason": "Declared irrigation arithmetic passed; planning eligibility is separately retained." if passed else
                      "Independent irrigation numerical checks failed."}


def _audit(request, result, expected):
    errors = {name: 0.0 for name in CHECK_NAMES}
    def add(name, value):
        errors[name] = max(errors[name], value)
    add("planning_eligibility_and_decisions", _compare(result["planning_status"], expected["planning_status"]))
    for actual, target in zip(result["initial_zones"], expected["initial_zones"]):
        add("replica_gls_fusion", _fields(actual, target, {
            "fused_theta_m3_m3", "fused_variance_m3_m3_squared", "fused_standard_uncertainty_m3_m3", "fusion_weights"}))
        add("initial_root_zone_capacity", _fields(actual, target, {"taw_mm", "raw_mm", "depletion_mm", "standard_uncertainty_mm"}))
        add("conditional_initial_uncertainty_screening", _fields(actual, target, {"screening_lower_mm", "screening_upper_mm"}))
        add("planning_eligibility_and_decisions", _fields(actual, target, {"planning_status", "reasons", "projection_is_descriptive_only", "priority_index"}))
    pump = request["pump"]
    for day, target_day in zip(result["days"], expected["days"]):
        add("fao56_reference_et0", _error(day["et0_mm"], target_day["et0_mm"]))
        add("priority_pump_budget_allocation", _fields(day, target_day, {"available_gross_m3", "allocated_gross_m3", "remaining_gross_m3", "pump_hours", "unmet_gross_m3"}))
        for zone, row, target in zip(request["zones"], day["zones"], target_day["zones"]):
            add("daily_root_zone_balance", _fields(row, target, {
                "depletion_start_mm", "rainfall_mm", "runoff_mm", "capillary_rise_mm", "wetting_net_mm",
                "actual_crop_et_mm", "deep_percolation_mm", "depletion_end_mm", "balance_residual_mm"}))
            add("stress_and_crop_et", _fields(row, target, {"stress_coefficient", "potential_crop_et_mm", "actual_crop_et_mm", "unmet_crop_et_mm"}))
            add("priority_pump_budget_allocation", _fields(row, target, {"requested_net_mm", "allocated_net_mm", "requested_gross_m3", "allocated_gross_m3", "unmet_net_mm"}))
            add("conditional_initial_uncertainty_screening", _fields(row, target, {
                "screening_lower_start_mm", "screening_upper_start_mm", "screening_lower_end_mm", "screening_upper_end_mm"}))
            add("planning_eligibility_and_decisions", _fields(row, target, {"planning_status", "reasons", "projection_is_descriptive_only"}))
            wet = row["rainfall_mm"] - row["runoff_mm"] + row["capillary_rise_mm"] + row["allocated_net_mm"]
            closure = row["depletion_start_mm"] - wet + row["actual_crop_et_mm"] + row["deep_percolation_mm"]
            add("explicit_water_mass_closure", max(_error(row["depletion_end_mm"], closure),
                _error(row["wetting_net_mm"], wet), _error(row["balance_residual_mm"], row["depletion_end_mm"] - closure)))
            conversion = zone["area_m2"] / (1000.0 * pump["efficiency"])
            add("gross_net_units_and_pump_limits", max(
                _error(row["allocated_gross_m3"], row["allocated_net_mm"] * conversion),
                _error(row["requested_gross_m3"], row["requested_net_mm"] * conversion),
                _error(row["requested_net_mm"], row["allocated_net_mm"] + row["unmet_net_mm"]),
                _error(row["potential_crop_et_mm"], row["actual_crop_et_mm"] + row["unmet_crop_et_mm"]),
                max(0.0, row["allocated_net_mm"] - zone["max_daily_net_mm"]) / (1.0 + zone["max_daily_net_mm"])))
        allocated = math.fsum(row["allocated_gross_m3"] for row in day["zones"])
        unmet = math.fsum(row["unmet_net_mm"] * zone["area_m2"] / (1000.0 * pump["efficiency"])
                           for zone, row in zip(request["zones"], day["zones"]))
        available = min(pump["water_budget_m3_per_day"], pump["rate_m3_h"] * pump["available_hours_per_day"])
        add("gross_net_units_and_pump_limits", max(
            _error(day["allocated_gross_m3"], allocated), _error(day["unmet_gross_m3"], unmet),
            _error(day["pump_hours"], allocated / pump["rate_m3_h"]), _error(day["available_gross_m3"], available),
            _error(day["remaining_gross_m3"], available - allocated),
            max(0.0, allocated - available) / (1.0 + available),
            max(0.0, day["pump_hours"] - pump["available_hours_per_day"]) / (1.0 + pump["available_hours_per_day"])))
    add("flow_pressure_telemetry", _compare(result["telemetry"], expected["telemetry"]))
    return errors


def verify(request: dict, result: dict) -> dict:
    request = validate_request(request)
    result = validate_result(request, result)
    expected = reference(request)
    errors = _audit(request, result, expected)
    checks = [{"name": name, "value": errors[name], "tolerance": THRESHOLDS["absolute"],
               "status": "PASS" if errors[name] <= THRESHOLDS["absolute"] else "FAIL"} for name in CHECK_NAMES]
    passed = all(row["status"] == "PASS" for row in checks)
    return seal({"schema": REPORT_SCHEMA, "request_digest": digest(request), "candidate_digest": result["record_digest"],
                 "scope": SCOPE, "verifier": VERIFIER_ID, "thresholds": deepcopy(THRESHOLDS),
                 "residual_definition": "abs(candidate-reference)/(1+abs(reference)); absolute1e-9_plus_relative1e-9",
                 "status": "PASS" if passed else "FAIL", "checks": checks,
                 "reference": _reference_identity(request, digest(expected)),
                 "metrics": {"residuals": errors, "summary": _summary(result)},
                 "qualification": _qualification(result, passed), "limitations": list(LIMITATIONS)})


def validate_report(request: dict, result: dict, report: dict) -> None:
    """STRUCTURAL ONLY: bind sealed bytes and retained check coherence."""
    request = validate_request(request)
    result = validate_result(request, result)
    json_tree(report)
    keys(report, {"schema", "request_digest", "candidate_digest", "scope", "verifier", "thresholds",
                  "residual_definition", "status", "checks", "reference", "metrics", "qualification", "limitations", "record_digest"})
    fixed = {"schema": REPORT_SCHEMA, "request_digest": digest(request), "candidate_digest": result["record_digest"],
             "scope": SCOPE, "verifier": VERIFIER_ID, "thresholds": THRESHOLDS,
             "residual_definition": "abs(candidate-reference)/(1+abs(reference)); absolute1e-9_plus_relative1e-9", "limitations": LIMITATIONS}
    for field, value in fixed.items():
        if report[field] != value:
            raise ValueError("Stored irrigation verification declaration differs: " + field)
    keys(report["thresholds"], set(THRESHOLDS))
    for value in report["thresholds"].values():
        number(value)
    ref = report["reference"]
    keys(ref, {"method", "request_digest", "projection_digest", "day_count", "zone_count", "observation_count", "telemetry_count"})
    content_ref(ref["projection_digest"])
    for field, value in _reference_identity(request, ref["projection_digest"]).items():
        if ref[field] != value or (field.endswith("_count") and type(ref[field]) is not int):
            raise ValueError("Stored irrigation reference declaration differs: " + field)
    metrics = report["metrics"]
    keys(metrics, {"residuals", "summary"})
    keys(metrics["residuals"], set(CHECK_NAMES))
    for value in metrics["residuals"].values():
        if not 0.0 <= number(value) <= MAX_RESIDUAL:
            raise ValueError("Stored irrigation residual must be finite and nonnegative")
    keys(metrics["summary"], set(_summary(result)))
    if metrics["summary"] != _summary(result):
        raise ValueError("Stored irrigation summary differs from retained candidate")
    for field, value in metrics["summary"].items():
        if field.endswith("_count"):
            if type(value) is not int:
                raise ValueError("Stored irrigation summary counts must be integers")
        elif field != "planning_status":
            number(value)
    if type(report["checks"]) is not list or len(report["checks"]) != len(CHECK_NAMES):
        raise ValueError("Stored irrigation check coverage differs")
    names = []
    for row in report["checks"]:
        keys(row, {"name", "value", "tolerance", "status"})
        name = row["name"]
        if type(name) is not str or name not in CHECK_NAMES:
            raise ValueError("Unsupported stored irrigation check")
        value, tolerance = number(row["value"]), number(row["tolerance"])
        if (value != metrics["residuals"][name] or tolerance != THRESHOLDS["absolute"]
                or row["status"] != ("PASS" if value <= tolerance else "FAIL")):
            raise ValueError("Stored irrigation check contradicts retained residual")
        names.append(name)
    if set(names) != set(CHECK_NAMES) or len(set(names)) != len(names):
        raise ValueError("Stored irrigation checks duplicate or omit a check")
    passed = all(row["status"] == "PASS" for row in report["checks"])
    keys(report["qualification"], {"action", "scope", "planning_status", "reason"})
    if report["status"] != ("PASS" if passed else "FAIL") or report["qualification"] != _qualification(result, passed):
        raise ValueError("Stored irrigation qualification contradicts retained checks")
    check_seal(report)
