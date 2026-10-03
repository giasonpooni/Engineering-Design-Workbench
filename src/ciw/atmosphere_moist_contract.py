"""Data-only contracts for an unsaturated, frozen-composition moist column.

Water vapour is an ideal-gas constituent with prescribed constant mixing ratio.
The liquid-water Magnus expression supplies a diagnostic, not condensation or
ice physics. Static readers retain scientifically wrong sealed candidates for
independent verification; they never replay the compiler.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
import re

from .control_contracts import keys, number
from .operations.runner import check_seal, digest

REQUEST_SCHEMA = "ciw.atmosphere-moist-request.v1"
RESULT_SCHEMA = "ciw.atmosphere-moist-result.v1"
REPORT_SCHEMA = "ciw.atmosphere-moist-verification.v1"
OPERATION_ID = "atmosphere.moist-compile.v1"
CLAIM_SCOPE = "unsaturated_constant_mixing_ratio_hydrostatic_column"
COMPILER_ID = "analytic_frozen_composition_moist_column_binary64"
FRAME = "atmosphere.local_enu.v1"
MAX_SAMPLES = 129
CONSTANTS = {
    "dry_air_gas_constant_j_per_kg_k": 287.05,
    "water_vapour_gas_constant_j_per_kg_k": 461.5,
    "dry_air_heat_capacity_ratio": 1.4,
    "dry_air_specific_heat_cp_j_per_kg_k": 1.4 * 287.05 / (1.4 - 1.0),
    "water_vapour_specific_heat_cp_j_per_kg_k": 1864.53,
    "heat_capacity_reference_temperature_k": 298.15,
    "gravity_m_per_s2": 9.80665,
    "potential_temperature_reference_pressure_pa": 100000.0,
    "magnus_reference_pressure_pa": 611.2,
    "magnus_numerator_coefficient": 17.62,
    "magnus_temperature_offset_k": 243.12,
    "magnus_reference_temperature_k": 273.15,
}
MIXTURE_FIELDS = (
    "water_mixing_ratio_kg_per_kg_dry_air", "water_mass_fraction",
    "gas_constant_j_per_kg_k", "specific_heat_cp_j_per_kg_k",
    "specific_heat_cv_j_per_kg_k", "heat_capacity_ratio",
)
STATE_FIELDS = (
    "height_m", "temperature_k", "pressure_pa", "dry_air_partial_pressure_pa",
    "water_vapour_pressure_pa", "dry_air_density_kg_per_m3",
    "water_vapour_density_kg_per_m3", "density_kg_per_m3", "relative_humidity",
    "liquid_water_saturation_pressure_pa", "liquid_equilibrium_dew_point_k",
    "frozen_sound_speed_m_per_s", "frozen_potential_temperature_k",
    "wind_enu_m_per_s",
)
UNITS = {
    "height_m": "m", "temperature_k": "K", "pressure_pa": "Pa",
    "dry_air_partial_pressure_pa": "Pa", "water_vapour_pressure_pa": "Pa",
    "dry_air_density_kg_per_m3": "kg/m^3",
    "water_vapour_density_kg_per_m3": "kg/m^3", "density_kg_per_m3": "kg/m^3",
    "relative_humidity": "1", "liquid_water_saturation_pressure_pa": "Pa",
    "liquid_equilibrium_dew_point_k": "K", "frozen_sound_speed_m_per_s": "m/s",
    "frozen_potential_temperature_k": "K", "wind_enu_m_per_s": "m/s",
}
SUPPORTED_OBSERVABLES = {
    "temperature", "pressure", "density", "wind", "hydrostatic_profile",
    "humidity", "vapour_pressure", "dew_point", "mixing_ratio", "sound_speed",
    "frozen_potential_temperature",
}
EXPANSION_OBSERVABLES = {
    "viscosity", "phase_change", "precipitation", "clouds", "turbulence",
    "weather_forecast", "radiation", "chemical_reactions", "visual_scattering",
    "material_conditioning", "fluid_dynamics", "ice_response",
    "moist_adiabatic_response",
}
TOLERANCE_KEYS = {"constitutive_relative", "hydrostatic_relative", "quadrature_relative"}


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
    """Validate declarations without inferring saturation or phase transitions."""
    keys(request, {"schema", "scope", "reference", "profile", "sampling",
                   "desired_observables", "tolerances"})
    if request["schema"] != REQUEST_SCHEMA or request["scope"] != CLAIM_SCOPE:
        raise ValueError("Unsupported moist atmosphere schema or physical scope")
    reference = request["reference"]
    keys(reference, {"temperature_k", "pressure_pa", "height_origin_m", "frame", "context"})
    temperature = _bounded(reference["temperature_k"], 293.15, 308.15, "temperature_k")
    _bounded(reference["pressure_pa"], 80000.0, 110000.0, "pressure_pa")
    _bounded(reference["height_origin_m"], -500.0, 10000.0, "height_origin_m")
    if reference["frame"] != FRAME:
        raise ValueError("Require the declared atmosphere local ENU frame")
    _context(reference["context"])
    profile = request["profile"]
    keys(profile, {"lapse_rate_k_per_m", "wind_enu_m_per_s", "composition",
                   "gravity_m_per_s2", "water_mixing_ratio_kg_per_kg_dry_air"})
    lapse = _bounded(profile["lapse_rate_k_per_m"], 0.0, 0.0065, "lapse_rate_k_per_m")
    if profile["composition"] != "dry_air_water_vapour":
        raise ValueError("This profile requires dry_air_water_vapour composition")
    mixing_ratio = number(profile["water_mixing_ratio_kg_per_kg_dry_air"])
    if mixing_ratio != 0.0 and not 0.002 <= mixing_ratio <= 0.02:
        raise ValueError("Mixing ratio must be zero or inside 0.002..0.02 kg/kg dry air")
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
        height = _bounded(height, 0.0, 2000.0, "height_m")
        if height <= previous:
            raise ValueError("Atmosphere heights must be strictly increasing")
        previous = height
    if heights[0] != 0.0:
        raise ValueError("The sampled column must start at the reference height")
    if temperature - lapse * number(heights[-1]) < 273.15:
        raise ValueError("Sampled temperatures must remain at least 273.15 K")
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
    """Check sealed bounded data and declaration bindings without physics replay."""
    request = validate_request(request)
    keys(result, {"schema", "request_digest", "claim_scope", "compiler", "constants",
                  "units", "mixture", "profile", "record_digest"})
    if (result["schema"] != RESULT_SCHEMA or result["request_digest"] != digest(request)
            or result["claim_scope"] != CLAIM_SCOPE or result["compiler"] != COMPILER_ID):
        raise ValueError("Moist result schema, declaration, scope or compiler binding differs")
    keys(result["constants"], set(CONSTANTS))
    for name, expected in CONSTANTS.items():
        if number(result["constants"][name]) != expected:
            raise ValueError("Moist result changed a fixed physical constant")
    keys(result["units"], set(UNITS))
    if result["units"] != UNITS:
        raise ValueError("Moist result must retain exact SI units")
    mixture = result["mixture"]
    keys(mixture, set(MIXTURE_FIELDS))
    mixing_ratio = number(mixture["water_mixing_ratio_kg_per_kg_dry_air"])
    if mixing_ratio != number(request["profile"]["water_mixing_ratio_kg_per_kg_dry_air"]):
        raise ValueError("Mixture mixing ratio differs from its declaration")
    for field in MIXTURE_FIELDS[1:]:
        if field == "water_mass_fraction":
            _bounded(mixture[field], 0.0, 1.0, "mixture." + field)
        else:
            _bounded(mixture[field], 1e-20, 1e20, "mixture." + field)
    profile = result["profile"]
    keys(profile, set(STATE_FIELDS))
    heights = request["sampling"]["height_m"]
    for field in STATE_FIELDS:
        values = profile[field]
        if type(values) is not list or len(values) != len(heights):
            raise ValueError("Moist arrays must cover the declared height grid")
        for value in values:
            if field == "wind_enu_m_per_s":
                if type(value) is not list or len(value) != 3:
                    raise ValueError("Atmospheric wind samples require three ENU components")
                for component in value:
                    _bounded(component, -300.0, 300.0, "wind sample")
            elif field == "height_m":
                _bounded(value, 0.0, 2000.0, "height sample")
            elif field == "liquid_equilibrium_dew_point_k":
                if mixing_ratio == 0.0:
                    if value is not None:
                        raise ValueError("Dry-limit liquid-equilibrium dew point must be null")
                else:
                    _bounded(value, 1e-20, 1e20, field + " sample")
            elif field in {"water_vapour_pressure_pa", "water_vapour_density_kg_per_m3",
                           "relative_humidity"}:
                # RH may exceed one in a retained failed-assumption candidate.
                _bounded(value, 0.0, 1e20, field + " sample")
            else:
                _bounded(value, 1e-20, 1e20, field + " sample")
    if profile["height_m"] != heights:
        raise ValueError("Moist samples differ from the declared height grid")
    check_seal(result)
    return deepcopy(result)


def example_request() -> dict:
    return {
        "schema": REQUEST_SCHEMA,
        "scope": CLAIM_SCOPE,
        "reference": {
            "temperature_k": 298.15, "pressure_pa": 101325.0,
            "height_origin_m": 0.0, "frame": FRAME,
            "context": {"source_kind": "synthetic",
                        "source_ref": "atmosphere.moist-default-example", "valid_time_utc": None},
        },
        "profile": {
            "lapse_rate_k_per_m": 0.0065, "wind_enu_m_per_s": [0.0, 0.0, 0.0],
            "composition": "dry_air_water_vapour", "gravity_m_per_s2": 9.80665,
            "water_mixing_ratio_kg_per_kg_dry_air": 0.008,
        },
        "sampling": {"height_m": [0.0, 250.0, 500.0, 750.0, 1000.0],
                     "interpretation": "height_above_reference"},
        "desired_observables": ["temperature", "pressure", "density", "wind",
                                "hydrostatic_profile", "humidity", "vapour_pressure",
                                "dew_point", "mixing_ratio", "sound_speed",
                                "frozen_potential_temperature"],
        "tolerances": {"constitutive_relative": 1e-10, "hydrostatic_relative": 1e-8,
                       "quadrature_relative": 1e-8},
    }
