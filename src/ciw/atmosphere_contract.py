"""Data-only SI contracts for a prescribed dry hydrostatic atmosphere column.

The retained origin, frame and source context identify a declaration. They do
not turn a synthetic column into a measurement, weather forecast or material
conditioning model. Static reads do not replay the compiler or its verifier.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
import re

from .control_contracts import keys, number
from .operations.runner import check_seal, digest

REQUEST_SCHEMA = "ciw.atmosphere-request.v1"
RESULT_SCHEMA = "ciw.atmosphere-result.v1"
REPORT_SCHEMA = "ciw.atmosphere-verification.v1"
OPERATION_ID = "atmosphere.compile.v1"
CLAIM_SCOPE = "dry_hydrostatic_constant_gravity_column"
COMPILER_ID = "analytic_dry_hydrostatic_column_binary64"
FRAME = "atmosphere.local_enu.v1"
MAX_SAMPLES = 129
CONSTANTS = {
    "dry_air_gas_constant_j_per_kg_k": 287.05,
    "heat_capacity_ratio": 1.4,
    "specific_heat_cp_j_per_kg_k": 1.4 * 287.05 / (1.4 - 1.0),
    "gravity_m_per_s2": 9.80665,
    "potential_temperature_reference_pressure_pa": 100000.0,
    "sutherland_reference_viscosity_pa_s": 1.716e-5,
    "sutherland_reference_temperature_k": 273.15,
    "sutherland_temperature_k": 110.4,
}
STATE_FIELDS = (
    "height_m", "temperature_k", "pressure_pa", "density_kg_per_m3",
    "sound_speed_m_per_s", "dynamic_viscosity_pa_s",
    "kinematic_viscosity_m2_per_s", "potential_temperature_k",
    "wind_enu_m_per_s",
)
UNITS = {
    "height_m": "m", "temperature_k": "K", "pressure_pa": "Pa",
    "density_kg_per_m3": "kg/m^3", "sound_speed_m_per_s": "m/s",
    "dynamic_viscosity_pa_s": "Pa*s", "kinematic_viscosity_m2_per_s": "m^2/s",
    "potential_temperature_k": "K", "wind_enu_m_per_s": "m/s",
}
SUPPORTED_OBSERVABLES = {
    "temperature", "pressure", "density", "sound_speed", "viscosity",
    "wind", "potential_temperature", "hydrostatic_profile",
}
EXPANSION_OBSERVABLES = {
    "humidity", "precipitation", "clouds", "turbulence", "weather_forecast",
    "radiation", "chemical_reactions", "visual_scattering",
    "material_conditioning", "fluid_dynamics",
}
TOLERANCE_KEYS = {
    "constitutive_relative", "hydrostatic_relative", "quadrature_relative",
}


def _bounded(value, lower: float, upper: float, label: str) -> float:
    value = number(value)
    if not lower <= value <= upper:
        raise ValueError(f"{label} must be inside {lower}..{upper}")
    return value


def _context(value: dict) -> None:
    keys(value, {"source_kind", "source_ref", "valid_time_utc"})
    if type(value["source_kind"]) is not str or value["source_kind"] not in {
        "synthetic", "declared_environment"
    }:
        raise ValueError("Declare a synthetic or declared_environment source")
    source = value["source_ref"]
    if type(source) is not str or not source.strip() or len(source) > 160:
        raise ValueError("Require a nonempty source_ref of at most 160 characters")
    timestamp = value["valid_time_utc"]
    if timestamp is not None:
        if (type(timestamp) is not str or len(timestamp) > 40
                or re.fullmatch(
                    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)",
                    timestamp,
                ) is None):
            raise ValueError("valid_time_utc must be an ISO UTC timestamp or null")
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Invalid valid_time_utc timestamp") from exc
        if parsed.utcoffset() != timedelta(0):
            raise ValueError("valid_time_utc must be UTC")


def validate_request(request: dict) -> dict:
    """Return a detached bounded declaration; no units or laws are inferred."""
    keys(request, {"schema", "scope", "reference", "profile", "sampling",
                   "desired_observables", "tolerances"})
    if request["schema"] != REQUEST_SCHEMA or request["scope"] != CLAIM_SCOPE:
        raise ValueError("Unsupported atmosphere schema or physical scope")
    reference = request["reference"]
    keys(reference, {"temperature_k", "pressure_pa", "height_origin_m", "frame", "context"})
    temperature = _bounded(reference["temperature_k"], 250.0, 330.0, "temperature_k")
    _bounded(reference["pressure_pa"], 50000.0, 120000.0, "pressure_pa")
    _bounded(reference["height_origin_m"], -500.0, 10000.0, "height_origin_m")
    if reference["frame"] != FRAME:
        raise ValueError("Require the declared atmosphere local ENU frame")
    _context(reference["context"])
    profile = request["profile"]
    keys(profile, {"lapse_rate_k_per_m", "wind_enu_m_per_s", "composition", "gravity_m_per_s2"})
    lapse = _bounded(profile["lapse_rate_k_per_m"], 0.0, 0.009, "lapse_rate_k_per_m")
    if profile["composition"] != "dry_air":
        raise ValueError("This profile requires dry_air composition")
    if number(profile["gravity_m_per_s2"]) != CONSTANTS["gravity_m_per_s2"]:
        raise ValueError("This profile requires constant gravity 9.80665 m/s^2")
    wind = profile["wind_enu_m_per_s"]
    if type(wind) is not list or len(wind) != 3:
        raise ValueError("Require three declared east, north, up wind components")
    for component in wind:
        _bounded(component, -300.0, 300.0, "wind_enu_m_per_s")
    sampling = request["sampling"]
    keys(sampling, {"height_m", "interpretation"})
    if sampling["interpretation"] != "height_above_reference":
        raise ValueError("Require heights above the declared reference")
    heights = sampling["height_m"]
    if type(heights) is not list or not 2 <= len(heights) <= MAX_SAMPLES:
        raise ValueError("Require 2..129 ordered height samples")
    previous = -1.0
    for height in heights:
        height = _bounded(height, 0.0, 11000.0, "height_m")
        if height <= previous:
            raise ValueError("Atmosphere heights must be strictly increasing")
        previous = height
    if heights[0] != 0.0:
        raise ValueError("The sampled column must start at the reference height")
    if temperature - lapse * number(heights[-1]) < 180.0:
        raise ValueError("Sampled temperatures must remain at least 180 K")
    keys(request["tolerances"], TOLERANCE_KEYS)
    for name, value in request["tolerances"].items():
        _bounded(value, 1e-12, 0.01, "tolerances." + name)
    observables = request["desired_observables"]
    known = SUPPORTED_OBSERVABLES | EXPANSION_OBSERVABLES
    if type(observables) is not list or not 1 <= len(observables) <= len(known):
        raise ValueError("Require a bounded nonempty desired_observables list")
    if (any(type(value) is not str or value not in known for value in observables)
            or len(set(observables)) != len(observables)):
        raise ValueError("Unknown or repeated atmospheric observable")
    return deepcopy(request)


def request_digest(request: dict) -> str:
    return digest(validate_request(request))


def validate_result(request: dict, result: dict) -> dict:
    """Check sealed data, bounds and declaration bindings without physics replay."""
    request = validate_request(request)
    keys(result, {"schema", "request_digest", "claim_scope", "compiler", "constants",
                  "units", "profile", "record_digest"})
    if (result["schema"] != RESULT_SCHEMA or result["request_digest"] != digest(request)
            or result["claim_scope"] != CLAIM_SCOPE or result["compiler"] != COMPILER_ID):
        raise ValueError("Atmosphere result schema, declaration, scope or compiler binding differs")
    keys(result["constants"], set(CONSTANTS))
    for name, expected in CONSTANTS.items():
        if number(result["constants"][name]) != expected:
            raise ValueError("Atmosphere result changed a fixed physical constant")
    keys(result["units"], set(UNITS))
    if result["units"] != UNITS:
        raise ValueError("Atmosphere result must retain exact SI units")
    profile = result["profile"]
    keys(profile, set(STATE_FIELDS))
    heights = request["sampling"]["height_m"]
    count = len(heights)
    for field in STATE_FIELDS:
        values = profile[field]
        if type(values) is not list or len(values) != count:
            raise ValueError("Atmosphere arrays must cover the declared height grid")
        if field == "wind_enu_m_per_s":
            for row in values:
                if type(row) is not list or len(row) != 3:
                    raise ValueError("Atmospheric wind samples require three ENU components")
                for component in row:
                    _bounded(component, -300.0, 300.0, "wind sample")
        else:
            for value in values:
                if field == "height_m":
                    _bounded(value, 0.0, 11000.0, "height sample")
                else:
                    _bounded(value, 1e-20, 1e20, field + " sample")
    if profile["height_m"] != heights:
        raise ValueError("Atmosphere samples differ from the declared height grid")
    check_seal(result)
    return deepcopy(result)


def example_request() -> dict:
    return {
        "schema": REQUEST_SCHEMA,
        "scope": CLAIM_SCOPE,
        "reference": {
            "temperature_k": 288.15,
            "pressure_pa": 101325.0,
            "height_origin_m": 0.0,
            "frame": FRAME,
            "context": {"source_kind": "synthetic", "source_ref": "atmosphere.default-example",
                        "valid_time_utc": None},
        },
        "profile": {"lapse_rate_k_per_m": 0.0065, "wind_enu_m_per_s": [0.0, 0.0, 0.0],
                    "composition": "dry_air", "gravity_m_per_s2": 9.80665},
        "sampling": {"height_m": [float(index * 1000) for index in range(11)],
                     "interpretation": "height_above_reference"},
        "desired_observables": ["temperature", "pressure", "density", "sound_speed",
                                "viscosity", "wind", "potential_temperature", "hydrostatic_profile"],
        "tolerances": {"constitutive_relative": 1e-10, "hydrostatic_relative": 1e-8,
                       "quadrature_relative": 1e-8},
    }
