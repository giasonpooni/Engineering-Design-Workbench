"""Compile one prescribed dry column; this engine does not infer the weather.

Temperature and wind are declarations. Pressure integrates the dry ideal-gas
hydrostatic equation at constant gravity; other properties use the declared
fixed thermodynamic and Sutherland coefficients. Wind is carried through as
external context and is not evolved by a fluid momentum equation.
"""
from __future__ import annotations

from copy import deepcopy
import math

from .atmosphere_contract import (
    CLAIM_SCOPE, COMPILER_ID, CONSTANTS, RESULT_SCHEMA, STATE_FIELDS, UNITS,
    validate_request,
)
from .operations.runner import digest, seal


def compile_atmosphere(request: dict) -> dict:
    request = validate_request(request)
    reference, declaration = request["reference"], request["profile"]
    initial_temperature = float(reference["temperature_k"])
    initial_pressure = float(reference["pressure_pa"])
    lapse = float(declaration["lapse_rate_k_per_m"])
    gas_constant = CONSTANTS["dry_air_gas_constant_j_per_kg_k"]
    gravity = CONSTANTS["gravity_m_per_s2"]
    gamma = CONSTANTS["heat_capacity_ratio"]
    cp = CONSTANTS["specific_heat_cp_j_per_kg_k"]
    sutherland_temperature = CONSTANTS["sutherland_temperature_k"]
    viscosity_reference_temperature = CONSTANTS["sutherland_reference_temperature_k"]
    viscosity_reference = CONSTANTS["sutherland_reference_viscosity_pa_s"]
    theta_pressure = CONSTANTS["potential_temperature_reference_pressure_pa"]
    profile = {field: [] for field in STATE_FIELDS}
    for declared_height in request["sampling"]["height_m"]:
        height = float(declared_height)
        temperature = initial_temperature - lapse * height
        # This dimensionless form is algebraically g/(R*L)*log(1-L*h/T0)
        # but also remains well conditioned as L tends to zero, including
        # binary64 subnormal declarations. No tolerance-based law switching.
        fraction = lapse * height / initial_temperature
        logarithm_ratio = 1.0 if fraction == 0.0 else -math.log1p(-fraction) / fraction
        log_pressure_ratio = -gravity * height / (gas_constant * initial_temperature) * logarithm_ratio
        pressure = initial_pressure * math.exp(log_pressure_ratio)
        density = pressure / (gas_constant * temperature)
        sound_speed = math.sqrt(gamma * gas_constant * temperature)
        viscosity = (viscosity_reference * (temperature / viscosity_reference_temperature) ** 1.5
                     * (viscosity_reference_temperature + sutherland_temperature)
                     / (temperature + sutherland_temperature))
        potential_temperature = temperature * (theta_pressure / pressure) ** (gas_constant / cp)
        profile["height_m"].append(height)
        profile["temperature_k"].append(temperature)
        profile["pressure_pa"].append(pressure)
        profile["density_kg_per_m3"].append(density)
        profile["sound_speed_m_per_s"].append(sound_speed)
        profile["dynamic_viscosity_pa_s"].append(viscosity)
        profile["kinematic_viscosity_m2_per_s"].append(viscosity / density)
        profile["potential_temperature_k"].append(potential_temperature)
        profile["wind_enu_m_per_s"].append(deepcopy(declaration["wind_enu_m_per_s"]))
    return seal({"schema": RESULT_SCHEMA, "request_digest": digest(request),
                 "claim_scope": CLAIM_SCOPE, "compiler": COMPILER_ID,
                 "constants": dict(CONSTANTS), "units": dict(UNITS), "profile": profile})
