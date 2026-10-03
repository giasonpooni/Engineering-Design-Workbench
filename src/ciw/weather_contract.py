"""Bounded, data-only contracts for course-aligned weather science profiles.

The fixed dispatch table is trusted code. Saved declarations cannot load a
provider or claim acquired observations, experimental validation or admission.
"""
from __future__ import annotations

from copy import deepcopy

from .control_contracts import keys, number, text
from .operations.runner import check_seal, digest, seal

REQUEST = "ciw.weather-request.v1"
RESULT = "ciw.weather-result.v1"
REPORT = "ciw.weather-checks.v1"
COMPUTE = "weather.compute.v1"
VERIFY = "weather.verify.v1"
FRAME = "weather.declared_coordinate_context.v1"
AUTHORITY = {"physical_validation": "not_established", "operational_forecast": "not_established",
             "state_admission": "not_performed", "hardware_actuation": "not_performed"}


def providers() -> dict:
    from . import weather_thermo, weather_dynamics, weather_hydro, weather_storm
    result = {}
    for module in (weather_thermo, weather_dynamics, weather_hydro, weather_storm):
        for name in module.PROFILES:
            if name in result:
                raise ValueError("Duplicate trusted weather profile")
            result[name] = module
    return result


def profile(name: str):
    if type(name) is not str or name not in providers():
        raise ValueError("Unsupported weather profile; use net weather catalog")
    module = providers()[name]
    return module, module.PROFILES[name]


def catalog() -> dict:
    return {"schema": "ciw.weather-catalog.v1", "read_only": True,
            "qualification": "not_performed_by_catalog", "authority": deepcopy(AUTHORITY),
            "profiles": {name: deepcopy(module.PROFILES[name]) for name, module in providers().items()}}


def example_request(name: str) -> dict:
    _, spec = profile(name)
    return {"schema": REQUEST, "profile": name,
            "context": {"source_kind": "synthetic", "source_ref": "NET weather example: " + name},
            "inputs": deepcopy(spec["example"])}


def validate_request(request: dict) -> dict:
    keys(request, {"schema", "profile", "context", "inputs"})
    if request["schema"] != REQUEST:
        raise ValueError("Unsupported weather request schema")
    module, _ = profile(request["profile"])
    context = request["context"]
    keys(context, {"source_kind", "source_ref"})
    if type(context["source_kind"]) is not str or context["source_kind"] not in {"synthetic", "declared_inputs"}:
        raise ValueError("Weather inputs must be synthetic or declared_inputs; measurement qualification is separate")
    text(context["source_ref"])
    module.validate(request["profile"], request["inputs"])
    return deepcopy(request)


def _array_lengths(request: dict, fields: dict) -> dict:
    """Declared output topology, without evaluating any physical equations."""
    name, inputs = request["profile"], request["inputs"]
    if name == "nwp_transport":
        return {"final_scalar": len(inputs["initial_scalar"])}
    if name == "storm_sounding":
        return {"buoyancy_m_s2": len(inputs["height_m"])}
    if name == "water_balance":
        count = len(inputs["precipitation_mm_day"])
        return {"storage_mm": count + 1, **{field: count for field in (
            "infiltration_mm", "runoff_mm", "actual_et_mm", "drainage_mm")}}
    if name == "snow_ice":
        count = len(inputs["precipitation_mm"])
        return {"swe_mm": count + 1, **{field: count for field in fields
                                       if field not in {"swe_mm", "mass_residual_mm"}}}
    return {}


def validate_result(request: dict, result: dict) -> None:
    request = validate_request(request)
    _, spec = profile(request["profile"])
    keys(result, {"schema", "request_digest", "profile", "scope", "units", "values",
                  "limitations", "authority", "record_digest"})
    if (result["schema"] != RESULT or result["request_digest"] != digest(request)
            or result["profile"] != request["profile"] or result["scope"] != spec["scope"]
            or result["units"] != spec["units"] or result["limitations"] != spec["limitations"]
            or result["authority"] != AUTHORITY):
        raise ValueError("Weather result contract or request binding differs")
    keys(result["values"], set(spec["units"]))
    lengths = _array_lengths(request, spec["units"])
    for field, value in result["values"].items():
        if field in lengths:
            if type(value) is not list or len(value) != lengths[field]:
                raise ValueError("Weather result array differs from declared grid or time steps")
            for item in value:
                number(item)
        else:
            number(value)
    check_seal(result)


def calculate(request: dict) -> dict:
    request = validate_request(request)
    module, spec = profile(request["profile"])
    result = seal({"schema": RESULT, "request_digest": digest(request), "profile": request["profile"],
                   "scope": spec["scope"], "units": deepcopy(spec["units"]),
                   "values": module.compute(request["profile"], request["inputs"]),
                   "limitations": deepcopy(spec["limitations"]), "authority": deepcopy(AUTHORITY)})
    validate_result(request, result)
    return result


def validate_report(request: dict, result: dict, report: dict) -> None:
    """Structural inspection only; numerical checking is an explicit operation."""
    validate_result(request, result)
    keys(report, {"schema", "request_digest", "result_digest", "status", "checks", "claim", "record_digest"})
    if (report["schema"] != REPORT or report["request_digest"] != digest(request)
            or report["result_digest"] != result["record_digest"]
            or report["claim"] != "bounded_numerical_consistency_only"):
        raise ValueError("Weather numerical report binding differs")
    checks = report["checks"]
    if type(checks) is not dict or not 1 <= len(checks) <= 128:
        raise ValueError("Require bounded nonempty numerical checks")
    for name, value in checks.items():
        text(name)
        if type(value) is not bool:
            raise ValueError("Numerical check outcomes must be booleans")
    if report["status"] != ("PASS" if all(checks.values()) else "FAIL"):
        raise ValueError("Numerical report status contradicts checks")
    check_seal(report)


def check(request: dict, result: dict) -> dict:
    validate_result(request, result)
    module, _ = profile(request["profile"])
    outcomes = module.checks(request["profile"], request["inputs"], result["values"])
    report = seal({"schema": REPORT, "request_digest": digest(request),
                   "result_digest": result["record_digest"], "checks": outcomes,
                   "status": "PASS" if outcomes and all(outcomes.values()) else "FAIL",
                   "claim": "bounded_numerical_consistency_only"})
    validate_report(request, result, report)
    return report
