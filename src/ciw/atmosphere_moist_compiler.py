"""Compile a prescribed ideal moist-gas column with constant mixing ratio.

The Magnus liquid-water diagnostic is evaluated without clipping or changing
water content. A separate verifier refuses supersaturation or proximity to it;
this compiler never invents condensate, moist convection or ice response.
"""
from __future__ import annotations

from copy import deepcopy
import math

from .atmosphere_moist_contract import (
    CLAIM_SCOPE, COMPILER_ID, CONSTANTS, RESULT_SCHEMA, STATE_FIELDS, UNITS,
    validate_request,
)
from .operations.runner import digest, seal


def mixture_properties(request: dict) -> dict:
    """Return frozen ideal-mixture properties for a validated declaration."""
    request = validate_request(request)
    ratio = float(request["profile"]["water_mixing_ratio_kg_per_kg_dry_air"])
    dry_constant = CONSTANTS["dry_air_gas_constant_j_per_kg_k"]
    vapour_constant = CONSTANTS["water_vapour_gas_constant_j_per_kg_k"]
    dry_cp = CONSTANTS["dry_air_specific_heat_cp_j_per_kg_k"]
    vapour_cp = CONSTANTS["water_vapour_specific_heat_cp_j_per_kg_k"]
    gas_constant = (dry_constant + ratio * vapour_constant) / (1.0 + ratio)
    cp = (dry_cp + ratio * vapour_cp) / (1.0 + ratio)
    cv = cp - gas_constant
    # Preserve exact prior dry-gas sound speed at the zero-water boundary.
    gamma = CONSTANTS["dry_air_heat_capacity_ratio"] if ratio == 0.0 else cp / cv
    return {
        "water_mixing_ratio_kg_per_kg_dry_air": ratio,
        "water_mass_fraction": ratio / (1.0 + ratio),
        "gas_constant_j_per_kg_k": gas_constant,
        "specific_heat_cp_j_per_kg_k": cp,
        "specific_heat_cv_j_per_kg_k": cv,
        "heat_capacity_ratio": gamma,
    }


def compile_atmosphere(request: dict) -> dict:
    request = validate_request(request)
    reference, declaration = request["reference"], request["profile"]
    initial_temperature = float(reference["temperature_k"])
    initial_pressure = float(reference["pressure_pa"])
    lapse = float(declaration["lapse_rate_k_per_m"])
    mixture = mixture_properties(request)
    ratio = mixture["water_mixing_ratio_kg_per_kg_dry_air"]
    gas_constant = mixture["gas_constant_j_per_kg_k"]
    cp = mixture["specific_heat_cp_j_per_kg_k"]
    gamma = mixture["heat_capacity_ratio"]
    dry_constant = CONSTANTS["dry_air_gas_constant_j_per_kg_k"]
    vapour_constant = CONSTANTS["water_vapour_gas_constant_j_per_kg_k"]
    epsilon = dry_constant / vapour_constant
    gravity = CONSTANTS["gravity_m_per_s2"]
    theta_pressure = CONSTANTS["potential_temperature_reference_pressure_pa"]
    magnus_pressure = CONSTANTS["magnus_reference_pressure_pa"]
    magnus_a = CONSTANTS["magnus_numerator_coefficient"]
    magnus_b = CONSTANTS["magnus_temperature_offset_k"]
    magnus_temperature = CONSTANTS["magnus_reference_temperature_k"]
    profile = {field: [] for field in STATE_FIELDS}
    for declared_height in request["sampling"]["height_m"]:
        height = float(declared_height)
        temperature = initial_temperature - lapse * height
        fraction = lapse * height / initial_temperature
        logarithm_ratio = 1.0 if fraction == 0.0 else -math.log1p(-fraction) / fraction
        log_pressure_ratio = -gravity * height / (gas_constant * initial_temperature) * logarithm_ratio
        pressure = initial_pressure * math.exp(log_pressure_ratio)
        vapour_pressure = ratio * pressure / (epsilon + ratio)
        dry_pressure = pressure - vapour_pressure
        dry_density = dry_pressure / (dry_constant * temperature)
        vapour_density = vapour_pressure / (vapour_constant * temperature)
        celsius_temperature = temperature - magnus_temperature
        saturation_pressure = magnus_pressure * math.exp(
            magnus_a * celsius_temperature / (magnus_b + celsius_temperature))
        if ratio == 0.0:
            dew_point = None
        else:
            logarithm_vapour_ratio = math.log(vapour_pressure / magnus_pressure)
            dew_point = (magnus_temperature + magnus_b * logarithm_vapour_ratio
                         / (magnus_a - logarithm_vapour_ratio))
        row = {
            "height_m": height, "temperature_k": temperature, "pressure_pa": pressure,
            "dry_air_partial_pressure_pa": dry_pressure,
            "water_vapour_pressure_pa": vapour_pressure,
            "dry_air_density_kg_per_m3": dry_density,
            "water_vapour_density_kg_per_m3": vapour_density,
            "density_kg_per_m3": dry_density + vapour_density,
            "relative_humidity": vapour_pressure / saturation_pressure,
            "liquid_water_saturation_pressure_pa": saturation_pressure,
            "liquid_equilibrium_dew_point_k": dew_point,
            "frozen_sound_speed_m_per_s": math.sqrt(gamma * gas_constant * temperature),
            "frozen_potential_temperature_k": temperature * (theta_pressure / pressure) ** (gas_constant / cp),
            "wind_enu_m_per_s": deepcopy(declaration["wind_enu_m_per_s"]),
        }
        for field in STATE_FIELDS:
            profile[field].append(row[field])
    return seal({"schema": RESULT_SCHEMA, "request_digest": digest(request),
                 "claim_scope": CLAIM_SCOPE, "compiler": COMPILER_ID,
                 "constants": dict(CONSTANTS), "units": dict(UNITS),
                 "mixture": mixture, "profile": profile})
