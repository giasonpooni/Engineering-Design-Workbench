"""Independent audit of retained atmospheric reference comparisons.

This verifier reconstructs alignment, arithmetic and decision gates from the
declared inputs. A disagreement with a reference may be a correctly computed
comparison. Neither its numerical verification nor its engineering acceptance
band establishes calibration, statistical confidence or physical validation.
Static report readers do not repeat the comparator or this arithmetic audit.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime

from .control_contracts import json_tree, keys, number
from .operations.runner import check_seal, digest, seal

REPORT_SCHEMA = "ciw.atmosphere-comparison-verification.v1"
SCHEMA = REPORT_SCHEMA
VERIFIER_ID = "independent_retained_reference_comparison_binary64.v1"
CHECK_NAMES = (
    "row_coverage", "field_alignment", "sample_alignment", "reference_alignment",
    "model_alignment", "signed_difference", "absolute_difference",
    "engineering_allowance", "reference_bound", "total_allowance",
    "normalized_acceptance_residual", "row_status", "diagnostics",
    "agreement_status", "qualification", "claims",
)
LIMITATIONS = [
    "Verifies bounded declared-input comparison arithmetic and alignment independently of the comparator; it does not verify the atmospheric governing equations.",
    "A numerical PASS includes correctly calculated scientific disagreement and correctly declared unsupported or refused alignment.",
    "Acceptance uses an engineering absolute-plus-relative band with an additive declared reference bound; it is not a statistical z-score or confidence interval.",
    "Reference provenance, uncertainty and context are retained declarations; their accuracy, calibration and independence require separate evidence.",
    "Only exact declared heights, frames, origins, times, units and humidity conventions are compared; no interpolation, conversion or geodetic transformation is performed.",
    "Pure liquid-water Magnus humidity is not interchangeable with pressure-enhanced humid-air conventions.",
    "No physical validation, material conditioning, provider activation or canonical state admission is performed.",
]


def _summary(comparison: dict) -> dict:
    rows = comparison["rows"]
    statuses = [row["status"] for row in rows]
    return {
        "row_count": len(rows),
        "evaluated_count": sum(status != "NOT_EVALUATED" for status in statuses),
        "passed_count": statuses.count("PASS"),
        "failed_count": statuses.count("FAIL"),
        "not_evaluated_count": statuses.count("NOT_EVALUATED"),
        "comparison_action": comparison["qualification"]["action"],
        "agreement_status": comparison["agreement_status"],
    }


def _qualification(comparison: dict, passed: bool) -> dict:
    return deepcopy(comparison["qualification"]) if passed else {
        "action": "REFUSE", "reasons": ["comparison_integrity_failed"]}


def _equal(left, right) -> bool:
    # Canonical content equality distinguishes booleans and integer/float data.
    return digest(left) == digest(right)


def _validated(request, result, reference, policy, comparison, bindings):
    # Data contracts are shared; the comparator and its reconstruction helpers
    # are deliberately not imported or invoked by this numerical provider.
    from .atmosphere_comparison_contract import validate_inputs
    from .atmosphere_comparison import validate_comparison
    request, result, reference, policy, bindings = validate_inputs(
        request, result, reference, policy, bindings)
    comparison = validate_comparison(request, result, reference, policy, comparison, bindings)
    return request, result, reference, policy, comparison, bindings


def _identity(comparison):
    from .atmosphere_comparison_contract import BINDING_KEYS
    fields = {"request_digest", "atmosphere_result_digest", "reference_digest", "policy_digest"} | set(BINDING_KEYS)
    return {field: deepcopy(comparison[field]) for field in fields}


_DIAGNOSTIC_MESSAGES = {
    "frame_mismatch": "Reference and model coordinate frames differ; no coordinate transformation is performed.",
    "height_origin_mismatch": "Reference and model height origins differ; no origin transfer is performed.",
    "time_mismatch": "Reference and model UTC context times differ.",
    "measurement_context_incompatible": "Declared measurements require a declared_environment model context with the same nonnull UTC time.",
    "sample_index_out_of_range": "Reference sample index is outside the retained model height grid.",
    "height_mismatch": "Reference height differs from the exact retained model sample height; no interpolation is performed.",
    "unsupported_field": "The retained atmospheric profile does not represent this reference quantity.",
    "humidity_convention_incompatible": "Pressure-enhanced relative humidity requires a separately qualified humidity law.",
}
_PURE_LIQUID_CONVENTION = "pure_liquid_magnus_17_62_243_12.v1"
_ARITHMETIC_FIELDS = (
    "signed_difference", "absolute_difference", "engineering_allowance",
    "total_allowance", "normalized_acceptance_residual",
)


def _reconstruct(request, result, reference, policy):
    """Independently derive the bounded comparison from its declarations.

    No compiler, comparator, comparator-domain helper or scientific inference
    participates. The mathematical provider remains separately qualified by
    the workflow that supplies the retained candidate.
    """
    diagnostics = []
    def diagnostic(code, sample=None, field=None):
        diagnostics.append({"code": code, "sample_index": sample, "field": field,
                            "message": _DIAGNOSTIC_MESSAGES[code]})

    model_context = request["reference"]
    reference_context = reference["context"]
    if model_context["frame"] != reference_context["frame"]:
        diagnostic("frame_mismatch")
    if number(model_context["height_origin_m"]) != number(reference_context["height_origin_m"]):
        diagnostic("height_origin_mismatch")
    model_time = model_context["context"]["valid_time_utc"]
    reference_time = reference_context["valid_time_utc"]
    parsed_model_time = None if model_time is None else datetime.fromisoformat(model_time.replace("Z", "+00:00"))
    parsed_reference_time = None if reference_time is None else datetime.fromisoformat(reference_time.replace("Z", "+00:00"))
    same_time = parsed_model_time == parsed_reference_time
    if not same_time:
        diagnostic("time_mismatch")
    if reference["provenance"]["kind"] == "declared_measurements" and (
            model_context["context"]["source_kind"] != "declared_environment"
            or parsed_model_time is None or not same_time):
        diagnostic("measurement_context_incompatible")
    profile = result["profile"]
    heights = profile["height_m"]
    for observation in reference["observations"]:
        index = observation["sample_index"]
        if not index < len(heights):
            diagnostic("sample_index_out_of_range", index)
        elif number(observation["height_m"]) != number(heights[index]):
            diagnostic("height_mismatch", index)
    action = "REFUSE" if diagnostics else "LOCAL"
    unsupported = set()
    if action == "LOCAL":
        for observation in reference["observations"]:
            for field in sorted(observation["quantities"]):
                index = observation["sample_index"]
                if field not in profile:
                    diagnostic("unsupported_field", index, field)
                    unsupported.add((index, field))
                elif field == "relative_humidity" and reference_context["humidity_convention"] != _PURE_LIQUID_CONVENTION:
                    diagnostic("humidity_convention_incompatible", index, field)
                    unsupported.add((index, field))
        if unsupported:
            action = "EXPAND"
    rows = []
    for observation in reference["observations"]:
        index = observation["sample_index"]
        for field in sorted(observation["quantities"]):
            datum = observation["quantities"][field]
            row = {
                "sample_index": index, "height_m": observation["height_m"], "field": field,
                "unit": datum["unit"], "model_value": None, "reference_value": datum["value"],
                "reference_bound": datum["uncertainty"]["absolute_bound"],
                **{name: None for name in _ARITHMETIC_FIELDS}, "status": "NOT_EVALUATED",
            }
            if action != "REFUSE" and (index, field) not in unsupported:
                model = number(profile[field][index])
                target = number(datum["value"])
                signed = model - target
                absolute = abs(signed)
                thresholds = policy["thresholds"][field]
                engineering = number(thresholds["absolute_tolerance"]) + number(thresholds["relative_tolerance"]) * abs(target)
                total = engineering + number(datum["uncertainty"]["absolute_bound"])
                row.update({
                    "model_value": deepcopy(profile[field][index]),
                    "signed_difference": signed, "absolute_difference": absolute,
                    "engineering_allowance": engineering, "total_allowance": total,
                    "normalized_acceptance_residual": None if total == 0.0 else absolute / total,
                    "status": "PASS" if absolute <= total else "FAIL",
                })
            rows.append(row)
    statuses = [row["status"] for row in rows]
    agreement = "FAIL" if "FAIL" in statuses else "NOT_EVALUATED" if "NOT_EVALUATED" in statuses else "PASS"
    reasons = []
    for item in diagnostics:
        if item["code"] not in reasons:
            reasons.append(item["code"])
    claims = {
        "exact_retained_samples": True, "interpolation_performed": False,
        "independence_declared": reference["provenance"]["independent_of_candidate"],
        "independence_established": False, "measurement_authenticity_established": False,
        "calibration_validation": False, "physical_validation": "not_established",
        "statistical_significance_established": False, "canonical_state_mutated": False,
        "state_admission_performed": False, "execution_authority": False,
    }
    return {"rows": rows, "diagnostics": diagnostics,
            "qualification": {"action": action, "reasons": reasons},
            "agreement_status": agreement, "claims": claims}


def _errors(comparison, expected):
    rows, expected_rows = comparison["rows"], expected["rows"]
    errors = {name: 0 for name in CHECK_NAMES}
    errors["row_coverage"] = abs(len(rows) - len(expected_rows))
    grouped = {
        "field_alignment": ("field", "unit"),
        "sample_alignment": ("sample_index", "height_m"),
        "reference_alignment": ("reference_value",),
        "model_alignment": ("model_value",),
    }
    for row, expected_row in zip(rows, expected_rows):
        for check, fields in grouped.items():
            errors[check] += int(any(not _equal(row[field], expected_row[field]) for field in fields))
        for field in (*_ARITHMETIC_FIELDS, "reference_bound"):
            errors[field] += int(not _equal(row[field], expected_row[field]))
        errors["row_status"] += int(row["status"] != expected_row["status"])
    for field in ("diagnostics", "agreement_status", "qualification", "claims"):
        errors[field] = int(not _equal(comparison[field], expected[field]))
    return errors


def verify(request: dict, result: dict, reference: dict, policy: dict,
           comparison: dict, bindings: dict) -> dict:
    """Freshly reconstruct a comparison without calling the comparator.

    Scientific disagreement does not imply arithmetic failure. A correct
    unsupported-field decision or a correct context refusal is also verifiable
    as such, while the export gate remains separate from this provider's PASS.
    """
    request, result, reference, policy, comparison, bindings = _validated(
        request, result, reference, policy, comparison, bindings)
    expected = _reconstruct(request, result, reference, policy)
    errors = _errors(comparison, expected)
    checks = [{"name": name, "value": errors[name], "tolerance": 0,
               "status": "PASS" if errors[name] == 0 else "FAIL"}
              for name in CHECK_NAMES]
    passed = all(check["status"] == "PASS" for check in checks)
    return seal({
        "schema": REPORT_SCHEMA, **_identity(comparison),
        "candidate_digest": comparison["record_digest"],
        "verifier": VERIFIER_ID, "status": "PASS" if passed else "FAIL",
        "checks": checks, "metrics": _summary(comparison),
        "qualification": _qualification(comparison, passed),
        "limitations": deepcopy(LIMITATIONS),
    })


def validate_report(request: dict, result: dict, reference: dict, policy: dict,
                    comparison: dict, report: dict, bindings: dict) -> dict:
    """Validate retained identity and structure without comparison replay."""
    request, result, reference, policy, comparison, bindings = _validated(
        request, result, reference, policy, comparison, bindings)
    identity = _identity(comparison)
    json_tree(report)
    keys(report, {"schema", *identity, "candidate_digest", "verifier", "status", "checks",
                  "metrics", "qualification", "limitations", "record_digest"})
    if (report["schema"] != REPORT_SCHEMA or report["verifier"] != VERIFIER_ID
            or report["candidate_digest"] != comparison["record_digest"]
            or report["status"] not in {"PASS", "FAIL"}
            or not _equal({field: report[field] for field in identity}, identity)
            or not _equal(report["limitations"], LIMITATIONS)):
        raise ValueError("Stored comparison audit identity or declaration differs")
    if not _equal(report["metrics"], _summary(comparison)):
        raise ValueError("Stored comparison audit summaries differ from retained row statuses")
    checks = report["checks"]
    if type(checks) is not list or len(checks) != len(CHECK_NAMES):
        raise ValueError("Stored comparison audit must contain every named check exactly once")
    names = []
    for check in checks:
        keys(check, {"name", "value", "tolerance", "status"})
        name = check["name"]
        if (type(name) is not str or name not in CHECK_NAMES
                or type(check["value"]) is not int or not 0 <= check["value"] <= 774
                or type(check["tolerance"]) is not int or check["tolerance"] != 0
                or check["status"] != ("PASS" if check["value"] == 0 else "FAIL")):
            raise ValueError("Stored comparison audit check contradicts its count or zero threshold")
        names.append(name)
    if len(set(names)) != len(names) or set(names) != set(CHECK_NAMES):
        raise ValueError("Stored comparison audit is missing or duplicates a check")
    passed = all(check["status"] == "PASS" for check in checks)
    if (report["status"] != ("PASS" if passed else "FAIL")
            or not _equal(report["qualification"], _qualification(comparison, passed))):
        raise ValueError("Stored comparison audit status or qualification contradicts retained checks")
    check_seal(report)
    return deepcopy(report)
