"""Deterministic bounded affine processing, separate from physical authority."""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
import math

from .control_contracts import detached, keys, number
from .core.covariance import _validate_matrix
from .operations.runner import check_seal, digest, seal
from .temperature_contract import (
    AUTHORITY, BUDGET_CATEGORIES, NUMERICAL_CONTRACT, REPORT_SCHEMA,
    validate_request,
)


def _inside(value, interval):
    return interval[0] <= value <= interval[1]


def _identities(request):
    return {
        "request_ref": digest(request),
        "raw_observations_ref": digest(request["raw_observations"]),
        "raw_commitment_scope": "canonical_json_declared_observations_not_acquisition_file_bytes",
        "measurement_identity_ref": digest(request["identity"]),
        "calibration_ref": digest(request["calibration"]),
        "joint_covariance_ref": digest(request["joint_covariance"]),
        "contributions_ref": digest(request["contributions"]),
        "budget_ref": digest(request["budget"]),
        "installed_correction_ref": digest(request["installed_correction"]),
        "procedure_ref": digest(NUMERICAL_CONTRACT),
        "acceptance_policy_ref": digest(request["acceptance"]),
    }


def _applicability(request):
    calibration, correction = request["calibration"], request["installed_correction"]
    conditions, identity = request["conditions"], request["identity"]
    global_flags = []
    for key in ("sensor_id", "readout_id", "clock_id"):
        if calibration[key] != identity[key]:
            global_flags.append("calibration_" + key + "_mismatch")
    for condition, envelope, flag in (
        ("ambient_temperature_K", "ambient_range_K", "ambient_outside_calibration"),
        ("maximum_heating_rate_K_s", "heating_rate_range_K_s", "heating_rate_outside_calibration"),
    ):
        if not _inside(conditions[condition], calibration[envelope]):
            global_flags.append(flag)
    installed_flags = []
    if correction is not None:
        for key in ("installation_id", "location_id", "material_id", "specimen_id"):
            if correction[key] != identity[key]:
                installed_flags.append("installed_correction_" + key + "_mismatch")
        for condition, envelope, flag in (
            ("ambient_temperature_K", "ambient_range_K", "ambient_outside_installed_correction"),
            ("maximum_heating_rate_K_s", "heating_rate_range_K_s", "heating_rate_outside_installed_correction"),
        ):
            if not _inside(conditions[condition], correction[envelope]):
                installed_flags.append(flag)
    flags, polymer_flags = [], []
    for index, sample in enumerate(request["raw_observations"]["samples"]):
        row_flags = list(global_flags)
        if sample["status"] != "ok":
            row_flags.append("acquisition_" + sample["status"])
        if sample["received_time_s"] - sample["time_s"] > request["clock"]["max_latency_s"]:
            row_flags.append("stale_observation")
        if not _inside(sample["time_s"], calibration["valid_time_s"]):
            row_flags.append("time_outside_calibration")
        if sample["value"] is not None:
            if not _inside(sample["value"], calibration["input_range"]):
                row_flags.append("raw_outside_calibration")
            nominal = calibration["gain"] * sample["value"] + calibration["offset_K"]
            if not _inside(nominal, calibration["output_range_K"]):
                row_flags.append("temperature_outside_calibration")
        flags.append(row_flags)
        installed_row_flags = row_flags + installed_flags
        if correction is not None:
            if not _inside(sample["time_s"], correction["valid_time_s"]):
                installed_row_flags.append("time_outside_installed_correction")
            if not row_flags and nominal + correction["offsets_K"][index] <= 0:
                installed_row_flags.append("nonpositive_polymer_temperature")
        polymer_flags.append(installed_row_flags)
    return flags, polymer_flags


def _sensor_output(request, flags):
    raw = request["raw_observations"]["samples"]
    n, calibration = len(raw), request["calibration"]
    gain, offset = float(calibration["gain"]), float(calibration["offset_K"])
    joint = request["joint_covariance"]["matrix"]
    covariance = [[None] * n for _ in range(n)]
    for i in range(n):
        if flags[i]:
            continue
        ji = ((i, gain), (n, float(raw[i]["value"])), (n + 1, 1.0))
        for j in range(i, n):
            if flags[j]:
                continue
            jj = ((j, gain), (n, float(raw[j]["value"])), (n + 1, 1.0))
            value = math.fsum([a * joint[p][q] * b for p, a in ji for q, b in jj] +
                              [source["covariance_K2"][i][j] for source in request["contributions"]])
            if not math.isfinite(value) or i == j and value < 0:
                raise ValueError("Propagation produced invalid variance; covariance is never repaired")
            covariance[i][j] = covariance[j][i] = value
    samples = []
    for i, sample in enumerate(raw):
        valid = not flags[i]
        samples.append({"sample_id": sample["sample_id"], "time_s": sample["time_s"],
                        "value_K": gain * sample["value"] + offset if valid else None,
                        "standard_uncertainty_K": math.sqrt(covariance[i][i]) if valid else None,
                        "status": "computed_from_declarations" if valid else "invalid",
                        "flags": flags[i]})
    return {"status": "computed_from_declarations", "quantity": "calibrated_sensor_temperature", "unit": "K",
            "samples": samples, "covariance_K2": covariance}


def _polymer_output(request, sensor, flags):
    correction = request["installed_correction"]
    if correction is None:
        return {"status": "unavailable", "quantity": "polymer_temperature", "unit": "K",
                "reason": "No separately declared installed correction and uncertainty supplied",
                "samples": [], "covariance_K2": []}
    samples, n = [], len(sensor["samples"])
    covariance = [[None] * n for _ in range(n)]
    for i in range(n):
        if flags[i]:
            continue
        for j in range(i, n):
            if flags[j]:
                continue
            value = math.fsum((sensor["covariance_K2"][i][j], correction["covariance_K2"][i][j]))
            covariance[i][j] = covariance[j][i] = value
    for i, sample in enumerate(sensor["samples"]):
        valid = not flags[i]
        samples.append({"sample_id": sample["sample_id"], "time_s": sample["time_s"],
                        "value_K": sample["value_K"] + correction["offsets_K"][i] if valid else None,
                        "standard_uncertainty_K": math.sqrt(covariance[i][i]) if valid else None,
                        "status": "estimated_from_declared_installed_correction" if valid else "invalid",
                        "flags": flags[i]})
    return {"status": "estimated_from_declared_installed_correction", "quantity": "polymer_temperature", "unit": "K",
            "samples": samples, "covariance_K2": covariance}


def _uncertainty(request):
    budget = {item["category"]: item for item in request["budget"]}
    omissions = [category for category in BUDGET_CATEGORIES if category not in budget or budget[category]["status"] == "omitted"]
    return {"status": "incomplete_declared_budget" if omissions else "complete_declared_budget",
            "missing_or_omitted_categories": omissions, "budget": deepcopy(request["budget"]),
            "joint_order": deepcopy(request["joint_covariance"]["order"]),
            "coverage_note": "Multiplier k is declared; no distribution or coverage probability is established",
            "limitations": "First-order propagation; declared independence is not experimentally validated"}


def _applicability_record(request, sensor_flags, polymer_flags):
    return {
        "calibration_status": "outside_declared_applicability" if any(sensor_flags) else "within_declared_applicability",
        "installed_correction_status": "not_supplied" if request["installed_correction"] is None else
            ("outside_declared_applicability" if any(polymer_flags) else "within_declared_applicability"),
        "condition_basis": "Submitted ambient and maximum heating-rate declarations, not independently observed conditions",
    }


def _expanded_interval(value, uncertainty, factor):
    """Outward endpoint rounding for the reported binary64 value/u/k only."""
    center = Fraction(float(value))
    radius = Fraction(float(uncertainty)) * Fraction(float(factor))
    exact_low, exact_high = center - radius, center + radius
    low, high = float(exact_low), float(exact_high)
    if Fraction(low) > exact_low:
        low = math.nextafter(low, -math.inf)
    if Fraction(high) < exact_high:
        high = math.nextafter(high, math.inf)
    return [low, high]


def _acceptance(request, sensor, polymer, uncertainty):
    policy = request["acceptance"]
    scope = "Conditional numerical decision on declarations; no physical qualification or traceability claim"
    if policy is None:
        return {"status": "not_requested", "quantity": None, "sample_results": [], "reasons": [], "scope": scope}
    target = sensor if policy["quantity"] == "calibrated_sensor_temperature" else polymer
    reasons = []
    if uncertainty["status"] != "complete_declared_budget":
        reasons.append("incomplete_uncertainty_budget")
    if target["status"] == "unavailable":
        reasons.append("requested_quantity_unavailable")
    if any(sample["status"] == "invalid" for sample in target["samples"]):
        reasons.append("invalid_or_inapplicable_observations")
    rows = []
    for sample in target["samples"]:
        interval = None
        if reasons:
            status = "indeterminate"
        else:
            interval = _expanded_interval(sample["value_K"], sample["standard_uncertainty_K"], policy["coverage_factor"])
            if interval[0] >= policy["lower"] and interval[1] <= policy["upper"]:
                status = "conditional_pass"
            elif interval[1] < policy["lower"] or interval[0] > policy["upper"]:
                status = "conditional_fail"
            else:
                status = "indeterminate"
        rows.append({"sample_id": sample["sample_id"], "status": status, "expanded_interval_K": interval})
    if reasons or not rows:
        status = "indeterminate"
    elif any(row["status"] == "conditional_fail" for row in rows):
        status = "conditional_fail"
    elif all(row["status"] == "conditional_pass" for row in rows):
        status = "conditional_pass"
    else:
        status = "indeterminate"
        reasons.append("uncertainty_interval_overlaps_acceptance_boundary")
    return {"status": status, "quantity": policy["quantity"], "sample_results": rows, "reasons": reasons, "scope": scope}


def process_request(value: dict) -> dict:
    """Process a detached request without hardware, model, provider, or proof IO."""
    request = validate_request(value)
    sensor_flags, polymer_flags = _applicability(request)
    sensor = _sensor_output(request, sensor_flags)
    polymer = _polymer_output(request, sensor, polymer_flags)
    uncertainty = _uncertainty(request)
    result = {
        "schema": REPORT_SCHEMA, "source_kind": request["source_kind"],
        "measurement_identity": deepcopy(request["identity"]),
        "raw_observations": deepcopy(request["raw_observations"]),
        "calibrated_sensor_temperature": sensor, "polymer_temperature": polymer,
        "applicability": _applicability_record(request, sensor_flags, polymer_flags),
        "uncertainty": uncertainty,
        "acceptance": _acceptance(request, sensor, polymer, uncertainty),
        "identities": _identities(request), "numerical_contract": deepcopy(NUMERICAL_CONTRACT),
        "authority": deepcopy(AUTHORITY),
    }
    return seal(result)


def validate_report(value: dict, report: dict) -> None:
    """Check retained structure/seals/bindings, without replaying or verifying execution.

    A caller can reseal altered numeric outputs. This function is an integrity and
    structure check only; independent numerical replay or a future proof is a
    separate operation and must not be inferred from successful validation.
    """
    request = validate_request(value)
    detached(report)
    keys(report, {"schema", "source_kind", "measurement_identity", "raw_observations", "calibrated_sensor_temperature",
                  "polymer_temperature", "applicability", "uncertainty", "acceptance", "identities", "numerical_contract",
                  "authority", "record_digest"})
    check_seal(report)
    if report["schema"] != REPORT_SCHEMA or report["source_kind"] != request["source_kind"]:
        raise ValueError("Retained temperature report schema/source mismatch")
    for actual, expected in ((report["identities"], _identities(request)), (report["authority"], AUTHORITY),
                             (report["numerical_contract"], NUMERICAL_CONTRACT),
                             (report["measurement_identity"], request["identity"]),
                             (report["raw_observations"], request["raw_observations"]),
                             (report["uncertainty"], _uncertainty(request))):
        if actual != expected:
            raise ValueError("Temperature report differs from its committed request or authority boundary")
    raw = request["raw_observations"]["samples"]
    sensor_flags, polymer_flags = _applicability(request)
    if report["applicability"] != _applicability_record(request, sensor_flags, polymer_flags):
        raise ValueError("Retained applicability differs from declared input limits")
    for name in ("calibrated_sensor_temperature", "polymer_temperature"):
        output = report[name]
        fields = {"status", "quantity", "unit", "samples", "covariance_K2"}
        if name == "polymer_temperature" and request["installed_correction"] is None:
            keys(output, fields | {"reason"})
            if output != _polymer_output(request, report["calibrated_sensor_temperature"], polymer_flags):
                raise ValueError("Polymer temperature cannot be available without installed correction")
            continue
        keys(output, fields)
        expected_status = "computed_from_declarations" if name == "calibrated_sensor_temperature" else "estimated_from_declared_installed_correction"
        if output["quantity"] != name or output["unit"] != "K" or output["status"] != expected_status:
            raise ValueError("Retained temperature quantity or semantics mismatch")
        samples, covariance = output["samples"], output["covariance_K2"]
        expected_flags = sensor_flags if name == "calibrated_sensor_temperature" else polymer_flags
        if type(samples) is not list or len(samples) != len(raw) or type(covariance) is not list or len(covariance) != len(raw):
            raise ValueError("Report must retain complete sample and covariance axes")
        for i, (sample, source) in enumerate(zip(samples, raw)):
            keys(sample, {"sample_id", "time_s", "value_K", "standard_uncertainty_K", "status", "flags"})
            if sample["sample_id"] != source["sample_id"] or sample["time_s"] != source["time_s"]:
                raise ValueError("Temperature report sample identity/order mismatch")
            if type(sample["flags"]) is not list or any(type(flag) is not str for flag in sample["flags"]):
                raise ValueError("Temperature sample flags must be strings")
            if sample["flags"] != expected_flags[i]:
                raise ValueError("Retained sample flags differ from declared applicability")
            if type(covariance[i]) is not list or len(covariance[i]) != len(raw):
                raise ValueError("Temperature report covariance shape mismatch")
            if sample["status"] == "invalid":
                if not sample["flags"] or sample["value_K"] is not None or sample["standard_uncertainty_K"] is not None:
                    raise ValueError("Invalid samples cannot carry computed temperatures")
            elif sample["status"] != expected_status or sample["flags"] or number(sample["value_K"]) <= 0 or number(sample["standard_uncertainty_K"]) < 0:
                raise ValueError("Invalid retained temperature value/status")
            elif name == "calibrated_sensor_temperature" and not _inside(sample["value_K"], request["calibration"]["output_range_K"]):
                raise ValueError("Retained sensor temperature is outside declared output range")
        for i in range(len(raw)):
            for j in range(len(raw)):
                item = covariance[i][j]
                if samples[i]["status"] == "invalid" or samples[j]["status"] == "invalid":
                    if item is not None:
                        raise ValueError("Invalid sample covariance row/column must be unavailable")
                elif number(item) != covariance[j][i] or i == j and item < 0:
                    raise ValueError("Invalid retained temperature covariance")
        active = [i for i, sample in enumerate(samples) if sample["status"] != "invalid"]
        if active:
            _validate_matrix([[covariance[i][j] for j in active] for i in active], len(active))
            if any(samples[i]["standard_uncertainty_K"] != math.sqrt(covariance[i][i]) for i in active):
                raise ValueError("Standard uncertainty differs from retained covariance diagonal")
    expected_acceptance = _acceptance(request, report["calibrated_sensor_temperature"], report["polymer_temperature"], report["uncertainty"])
    if report["acceptance"] != expected_acceptance:
        raise ValueError("Retained acceptance differs from report intervals and declared rules")
