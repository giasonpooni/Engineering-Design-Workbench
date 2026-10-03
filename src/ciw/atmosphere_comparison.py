"""Acceptance comparisons against retained atmospheric reference declarations.

Agreement is distinct from numerical qualification and physical validation.
This provider neither runs an atmospheric compiler nor authenticates a source.
The workflow must freshly qualify its retained physical candidate separately.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime

from .atmosphere_comparison_contract import (
    BINDING_KEYS, CLAIMS, COMPARISON_SCHEMA, FIELD_UNITS, MAX_SCALARS,
    PURE_LIQUID_CONVENTION, validate_inputs,
)
from .control_contracts import keys, number
from .operations.runner import check_seal, digest, seal

ROW_KEYS = {
    "sample_index", "height_m", "field", "unit", "model_value", "reference_value",
    "signed_difference", "absolute_difference", "engineering_allowance", "reference_bound",
    "total_allowance", "normalized_acceptance_residual", "status",
}
ARITHMETIC_FIELDS = (
    "signed_difference", "absolute_difference", "engineering_allowance",
    "total_allowance", "normalized_acceptance_residual",
)
DIAGNOSTIC_MESSAGES = {
    "frame_mismatch": "Reference and model coordinate frames differ; no coordinate transformation is performed.",
    "height_origin_mismatch": "Reference and model height origins differ; no origin transfer is performed.",
    "time_mismatch": "Reference and model UTC context times differ.",
    "measurement_context_incompatible": "Declared measurements require a declared_environment model context with the same nonnull UTC time.",
    "sample_index_out_of_range": "Reference sample index is outside the retained model height grid.",
    "height_mismatch": "Reference height differs from the exact retained model sample height; no interpolation is performed.",
    "unsupported_field": "The retained atmospheric profile does not represent this reference quantity.",
    "humidity_convention_incompatible": "Pressure-enhanced relative humidity requires a separately qualified humidity law.",
}


def _diagnostic(code: str, sample_index=None, field=None) -> dict:
    return {"code": code, "sample_index": sample_index, "field": field,
            "message": DIAGNOSTIC_MESSAGES[code]}


def _same_time(first, second) -> bool:
    if first is None or second is None:
        return first is None and second is None
    return datetime.fromisoformat(first.replace("Z", "+00:00")) == datetime.fromisoformat(
        second.replace("Z", "+00:00"))


def _domain(request: dict, result: dict, reference: dict) -> tuple[str, list[dict], set[tuple[int, str]]]:
    origin = request["reference"]
    context = reference["context"]
    diagnostics = []
    if context["frame"] != origin["frame"]:
        diagnostics.append(_diagnostic("frame_mismatch"))
    if context["height_origin_m"] != origin["height_origin_m"]:
        diagnostics.append(_diagnostic("height_origin_mismatch"))
    reference_time = context["valid_time_utc"]
    model_time = origin["context"]["valid_time_utc"]
    if not _same_time(reference_time, model_time):
        diagnostics.append(_diagnostic("time_mismatch"))
    if reference["provenance"]["kind"] == "declared_measurements" and (
        origin["context"]["source_kind"] != "declared_environment" or model_time is None
        or not _same_time(reference_time, model_time)
    ):
        diagnostics.append(_diagnostic("measurement_context_incompatible"))
    heights = result["profile"]["height_m"]
    for observation in reference["observations"]:
        index = observation["sample_index"]
        if index >= len(heights):
            diagnostics.append(_diagnostic("sample_index_out_of_range", index))
        elif observation["height_m"] != heights[index]:
            diagnostics.append(_diagnostic("height_mismatch", index))
    if diagnostics:
        return "REFUSE", diagnostics, set()
    unsupported = set()
    for observation in reference["observations"]:
        index = observation["sample_index"]
        for field in sorted(observation["quantities"]):
            if field not in result["profile"]:
                diagnostics.append(_diagnostic("unsupported_field", index, field))
                unsupported.add((index, field))
            elif (field == "relative_humidity"
                  and context["humidity_convention"] != PURE_LIQUID_CONVENTION):
                diagnostics.append(_diagnostic("humidity_convention_incompatible", index, field))
                unsupported.add((index, field))
    return ("EXPAND" if unsupported else "LOCAL"), diagnostics, unsupported


def compare(request: dict, result: dict, reference: dict, policy: dict, bindings: dict) -> dict:
    """Compare exact retained values with separately declared acceptance allowances."""
    request, result, reference, policy, bindings = validate_inputs(
        request, result, reference, policy, bindings)
    action, diagnostics, unsupported = _domain(request, result, reference)
    rows = []
    for observation in reference["observations"]:
        index = observation["sample_index"]
        for field in sorted(observation["quantities"]):
            datum = observation["quantities"][field]
            row = {"sample_index": index, "height_m": observation["height_m"],
                   "field": field, "unit": datum["unit"], "model_value": None,
                   "reference_value": datum["value"],
                   "reference_bound": datum["uncertainty"]["absolute_bound"],
                   **{name: None for name in ARITHMETIC_FIELDS}, "status": "NOT_EVALUATED"}
            if action != "REFUSE" and (index, field) not in unsupported:
                value = result["profile"][field][index]
                target = number(datum["value"])
                limits = policy["thresholds"][field]
                signed = number(value) - target
                difference = abs(signed)
                engineering = number(limits["absolute_tolerance"]) + number(
                    limits["relative_tolerance"]) * abs(target)
                total = engineering + number(row["reference_bound"])
                row.update(model_value=value, signed_difference=signed,
                           absolute_difference=difference, engineering_allowance=engineering,
                           total_allowance=total,
                           normalized_acceptance_residual=(difference / total if total > 0.0 else None),
                           status=("PASS" if difference <= total else "FAIL"))
            rows.append(row)
    statuses = {row["status"] for row in rows}
    agreement = ("FAIL" if "FAIL" in statuses else
                 "NOT_EVALUATED" if "NOT_EVALUATED" in statuses else "PASS")
    claims = deepcopy(CLAIMS)
    claims["independence_declared"] = reference["provenance"]["independent_of_candidate"]
    report = seal({
        "schema": COMPARISON_SCHEMA, "request_digest": digest(request),
        "atmosphere_result_digest": result["record_digest"],
        "reference_digest": reference["record_digest"], "policy_digest": policy["record_digest"],
        **bindings, "rows": rows, "diagnostics": diagnostics,
        "qualification": {"action": action,
                          "reasons": list(dict.fromkeys(item["code"] for item in diagnostics))},
        "agreement_status": agreement, "claims": claims,
    })
    return validate_comparison(request, result, reference, policy, report, bindings)


def validate_comparison(request: dict, result: dict, reference: dict, policy: dict,
                        comparison: dict, bindings: dict) -> dict:
    """Inspect structure and retained data bindings without recomputing arithmetic.

Scientifically or arithmetically incorrect sealed candidates remain inspectable
for an explicitly executed independent verification. Content seals are not a
substitute for that execution.
"""
    request, result, reference, policy, bindings = validate_inputs(
        request, result, reference, policy, bindings)
    keys(comparison, {"schema", "request_digest", "atmosphere_result_digest", "reference_digest",
                      "policy_digest", *BINDING_KEYS, "rows", "diagnostics", "qualification",
                      "agreement_status", "claims", "record_digest"})
    if (comparison["schema"] != COMPARISON_SCHEMA or comparison["request_digest"] != digest(request)
            or comparison["atmosphere_result_digest"] != result["record_digest"]
            or comparison["reference_digest"] != reference["record_digest"]
            or comparison["policy_digest"] != policy["record_digest"]
            or any(comparison[name] != bindings[name] for name in BINDING_KEYS)):
        raise ValueError("Atmospheric comparison content or occurrence binding differs")
    expected_rows = [(observation, field) for observation in reference["observations"]
                     for field in sorted(observation["quantities"])]
    rows = comparison["rows"]
    if type(rows) is not list or len(rows) != len(expected_rows) or not 1 <= len(rows) <= MAX_SCALARS:
        raise ValueError("Comparison rows must cover every exact retained reference scalar")
    for row, (observation, field) in zip(rows, expected_rows):
        keys(row, ROW_KEYS)
        datum = observation["quantities"][field]
        fixed = {"sample_index": observation["sample_index"], "height_m": observation["height_m"],
                 "field": field, "unit": FIELD_UNITS[field], "reference_value": datum["value"],
                 "reference_bound": datum["uncertainty"]["absolute_bound"]}
        if digest({key: row[key] for key in fixed}) != digest(fixed):
            raise ValueError("Comparison row differs from its retained reference scalar")
        if type(row["status"]) is not str or row["status"] not in {"PASS", "FAIL", "NOT_EVALUATED"}:
            raise ValueError("Unsupported comparison row status")
        if row["status"] == "NOT_EVALUATED":
            if row["model_value"] is not None or any(row[name] is not None for name in ARITHMETIC_FIELDS):
                raise ValueError("Unevaluated comparisons must not make quantitative model claims")
            continue
        index = observation["sample_index"]
        if field not in result["profile"] or index >= len(result["profile"]["height_m"]):
            raise ValueError("Evaluated comparison field or sample is absent from the retained model")
        if digest(row["model_value"]) != digest(result["profile"][field][index]):
            raise ValueError("Comparison model value differs from its retained result scalar")
        for name in ARITHMETIC_FIELDS[:-1]:
            value = number(row[name])
            if name != "signed_difference" and value < 0.0:
                raise ValueError("Comparison allowance and absolute discrepancy must be nonnegative")
        normalized = row["normalized_acceptance_residual"]
        if normalized is not None and number(normalized) < 0.0:
            raise ValueError("Normalized acceptance residual must be nonnegative or null")
        if (row["total_allowance"] == 0.0) != (normalized is None):
            raise ValueError("Only a zero total allowance has a null normalized acceptance residual")
    diagnostics = comparison["diagnostics"]
    if type(diagnostics) is not list or len(diagnostics) > MAX_SCALARS + MAX_SCALARS + 4:
        raise ValueError("Require a bounded comparison diagnostic list")
    for item in diagnostics:
        keys(item, {"code", "sample_index", "field", "message"})
        if type(item["code"]) is not str or item["code"] not in DIAGNOSTIC_MESSAGES:
            raise ValueError("Unsupported comparison diagnostic code")
        if item["message"] != DIAGNOSTIC_MESSAGES[item["code"]]:
            raise ValueError("Comparison diagnostic message differs from its fixed interpretation")
        if item["sample_index"] is not None and (type(item["sample_index"]) is not int
                                                or not 0 <= item["sample_index"] <= 128):
            raise ValueError("Invalid comparison diagnostic sample index")
        if item["field"] is not None and (type(item["field"]) is not str
                                          or item["field"] not in FIELD_UNITS):
            raise ValueError("Invalid comparison diagnostic field")
    qualification = comparison["qualification"]
    keys(qualification, {"action", "reasons"})
    if type(qualification["action"]) is not str or qualification["action"] not in {"LOCAL", "EXPAND", "REFUSE"}:
        raise ValueError("Unsupported comparison domain qualification")
    reasons = qualification["reasons"]
    if (type(reasons) is not list or len(reasons) > len(DIAGNOSTIC_MESSAGES)
            or any(type(code) is not str or code not in DIAGNOSTIC_MESSAGES for code in reasons)
            or len(set(reasons)) != len(reasons)):
        raise ValueError("Invalid comparison qualification reasons")
    if (type(comparison["agreement_status"]) is not str
            or comparison["agreement_status"] not in {"PASS", "FAIL", "NOT_EVALUATED"}):
        raise ValueError("Unsupported comparison agreement status")
    expected_claims = deepcopy(CLAIMS)
    expected_claims["independence_declared"] = reference["provenance"]["independent_of_candidate"]
    keys(comparison["claims"], set(expected_claims))
    if digest(comparison["claims"]) != digest(expected_claims):
        raise ValueError("Comparison cannot establish independence, calibration, physical validity or authority")
    check_seal(comparison)
    return deepcopy(comparison)
