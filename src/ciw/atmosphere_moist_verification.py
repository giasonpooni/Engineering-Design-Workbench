"""Independent audit of a bounded unsaturated frozen-composition moist column.

Hydrostatic pressure is integrated with two Simpson rules; mixture and humidity
laws are calculated independently of the compiler. Retained report validation
checks data, declarations and identities without repeating scientific models.
The endpoint humidity guard is continuous in the selected ideal-mixture Magnus
model; it does not certify quadrature error or measured environmental accuracy.
"""
from __future__ import annotations

from copy import deepcopy
import math

from .atmosphere_moist_contract import (
    CLAIM_SCOPE, EXPANSION_OBSERVABLES, MIXTURE_FIELDS, REPORT_SCHEMA, STATE_FIELDS,
    validate_request, validate_result,
)
from .control_contracts import json_tree, keys, number
from .operations.runner import check_seal, digest, seal

VERIFIER_ID = "independent_composite_simpson_frozen_moist_hydrostatic_binary64"
COARSE_SUBINTERVALS = 16
REFINED_SUBINTERVALS = 32
MAX_SEGMENTS = 128
MAX_QUADRATURE_EVALUATIONS = MAX_SEGMENTS * (COARSE_SUBINTERVALS + REFINED_SUBINTERVALS + 2)
MIN_TEMPERATURE_K = 273.15
MAX_TEMPERATURE_K = 308.15
MIN_DEW_POINT_K = 253.15
MAX_DEW_POINT_K = 308.15
MAX_RELATIVE_HUMIDITY = 0.95
DRY_GAS_CONSTANT = 287.05
VAPOUR_GAS_CONSTANT = 461.5
DRY_GAMMA = 1.4
DRY_SPECIFIC_HEAT_CP = DRY_GAMMA * DRY_GAS_CONSTANT / (DRY_GAMMA - 1.0)
VAPOUR_SPECIFIC_HEAT_CP = 1864.53
GRAVITY = 9.80665
REFERENCE_PRESSURE_PA = 100000.0
MAGNUS_REFERENCE_PRESSURE_PA = 611.2
MAGNUS_A = 17.62
MAGNUS_B_K = 243.12
MAGNUS_REFERENCE_TEMPERATURE_K = 273.15
MAX_RESIDUAL = 1e150
INTEGRAL_ROUNDOFF_ALLOWANCE = 1e-12
PRESSURE_ROUNDOFF_RELATIVE_ALLOWANCE = 1e-12
HUMIDITY_ROUNDOFF_RELATIVE_ALLOWANCE = 1e-12
INTEGRAL_BOUND_METHOD = "signed_composite_simpson_fourth_derivative_remainder.v1"
GUARD_INTERPRETATION = (
    "For f=g/(R_mix*T), f''''=24*g*L^4/(R_mix*T^5)>=0. Each refined Simpson integral "
    "has real-arithmetic lower bound S-Delta*(Delta/32)^4*max(f'''')/180. "
    "Subtract a fixed 1e-12*max(1,abs(S)) integral rounding allowance; use nonnegative lower bounds "
    "to obtain upper pressures with a fixed 1e-12 relative pressure allowance, then upper RH "
    "with a fixed 1e-12 relative humidity allowance. These binary64 margins do not implement directed interval arithmetic."
)

LIMITATIONS = [
    "Numerical verification of an unsaturated ideal dry-air/water-vapour hydrostatic column with constant mixing ratio, frozen heat capacities, linear temperature lapse and prescribed local ENU wind only.",
    "Liquid-water Magnus saturation and equilibrium dew point are pure-phase diagnostics; the pressure enhancement factor is omitted and complete WMO conformity is not claimed.",
    "The continuous humidity maximum occurs at an endpoint in this bounded constant-mixing-ratio Magnus model; its guard uses the signed Simpson real-arithmetic remainder bound and fixed binary64 rounding allowances, without directed interval arithmetic.",
    "Simpson refinement compares two finite rules, not a continuum-convergence proof; numerical agreement does not measure physical approximation error.",
    "Frozen sound speed and frozen potential temperature exclude latent heat, phase change and moist adiabatic response.",
    "Water-vapour heat capacity is held at 1864.53 J/(kg*K), a rounded 298.15 K reference approximation; measured caloric accuracy across the declared temperature interval is unqualified.",
    "Declared source context and time do not provide weather observations, calibration, a forecast or experimental validation of an environment.",
    "Moist-mixture viscosity, condensate, ice, clouds, precipitation, turbulence, radiation, visual scattering, fluid dynamics and material conditioning remain unqualified.",
    "Ambient humidity does not establish polymer moisture content; a separate conditioning or diffusion history and qualified material model are required.",
    "Height is above the declared reference; local ENU frame and height origin do not provide a geodetic or terrain transformation.",
    "Qualification recommendations do not perform canonical state admission.",
]
QUADRATURE_INTERPRETATION = "composite Simpson integration of g/(R_mix*T) on each declared height interval; two finite rules, no certified error bound"
HUMIDITY_PROOF = "constant_mixing_ratio_liquid_magnus_endpoint_maximum.v1"
HUMIDITY_INTERPRETATION = (
    "For T>=273.15 K and nonnegative lapse, d(log RH)/dz=-g/(R_mix*T)+L*a*b/(T-d)^2, "
    "where d=273.15-243.12; g*(T-d)^2/(R_mix*a*b*T) increases with T. "
    "Any interior stationary point is a minimum, so the maximum is at the reference or top endpoint. "
    "The hard ceiling uses an upper humidity guard from lower integral bounds and fixed binary64 allowances."
)
CHECK_TOLERANCES = {
    "prescribed_temperature": "constitutive_relative",
    "prescribed_wind": "constitutive_relative",
    "mixture_parameters": "constitutive_relative",
    "vapour_partial_pressure": "constitutive_relative",
    "dry_partial_pressure": "constitutive_relative",
    "partial_pressure_closure": "constitutive_relative",
    "dry_air_equation_of_state": "constitutive_relative",
    "water_vapour_equation_of_state": "constitutive_relative",
    "density_closure": "constitutive_relative",
    "equation_of_state": "constitutive_relative",
    "relative_humidity": "constitutive_relative",
    "liquid_water_saturation_pressure": "constitutive_relative",
    "dew_point_closure": "constitutive_relative",
    "frozen_sound_speed": "constitutive_relative",
    "frozen_potential_temperature": "constitutive_relative",
    "positive_properties": None,
    "boundary_temperature": "constitutive_relative",
    "boundary_pressure": "constitutive_relative",
    "pressure_monotonicity": "constitutive_relative",
    "frozen_potential_temperature_stability": "constitutive_relative",
    "segment_hydrostatic_balance": "hydrostatic_relative",
    "cumulative_pressure_profile": "hydrostatic_relative",
    "quadrature_refinement": "quadrature_relative",
    "quadrature_budget": None,
    "declared_temperature_domain": None,
    "declared_dew_point_domain": None,
    "sampled_unsaturation": None,
    "continuous_unsaturation": None,
    "dry_limit_water_state": None,
    "frozen_stability_domain": None,
}
REFERENCE_FIELDS = {
    "method", "integrand", "coarse_subintervals_per_segment", "refined_subintervals_per_segment",
    "segments", "quadrature_evaluations", "maximum_quadrature_evaluations", "interpretation",
    "coarse_segment_integrals", "refined_segment_integrals", "coarse_pressure_pa", "refined_pressure_pa",
    "integral_bound_method", "integral_roundoff_allowance", "pressure_roundoff_relative_allowance",
    "refined_segment_error_bounds", "segment_integral_roundoff_allowances", "segment_integral_lower_bounds", "pressure_upper_bound_pa",
    "continuous_humidity",
}
HUMIDITY_REFERENCE_FIELDS = {
    "proof", "interpretation", "height_m", "temperature_k", "pressure_pa",
    "relative_humidity", "maximum_relative_humidity", "maximum_allowed_relative_humidity",
    "minimum_temperature_k", "maximum_temperature_k",
    "relative_humidity_upper_bound", "maximum_relative_humidity_upper_bound",
    "humidity_roundoff_relative_allowance", "guard_interpretation",
}
WATER_ZERO_FIELDS = ("water_vapour_pressure_pa", "water_vapour_density_kg_per_m3", "relative_humidity")
SUMMARY_FIELDS = tuple(field for field in STATE_FIELDS if field not in {"height_m", "wind_enu_m_per_s"})
POSITIVE_FIELDS = tuple(field for field in SUMMARY_FIELDS
                        if field not in set(WATER_ZERO_FIELDS) | {"liquid_equilibrium_dew_point_k"})


def _finite_residual(value):
    return min(abs(value), MAX_RESIDUAL) if math.isfinite(value) else MAX_RESIDUAL


def _relative(observed, expected):
    # Exact zero-water semantics have their own nonrelaxable check.
    return _finite_residual((observed - expected) / (abs(expected) if expected else 1.0))


def _mixture(request):
    ratio = float(request["profile"]["water_mixing_ratio_kg_per_kg_dry_air"])
    gas_constant = (DRY_GAS_CONSTANT + ratio * VAPOUR_GAS_CONSTANT) / (1.0 + ratio)
    cp = (DRY_SPECIFIC_HEAT_CP + ratio * VAPOUR_SPECIFIC_HEAT_CP) / (1.0 + ratio)
    cv = cp - gas_constant
    return {"water_mixing_ratio_kg_per_kg_dry_air": ratio,
            "water_mass_fraction": ratio / (1.0 + ratio),
            "gas_constant_j_per_kg_k": gas_constant,
            "specific_heat_cp_j_per_kg_k": cp, "specific_heat_cv_j_per_kg_k": cv,
            "heat_capacity_ratio": DRY_GAMMA if ratio == 0.0 else cp / cv}


def _temperature(request, height):
    return request["reference"]["temperature_k"] - request["profile"]["lapse_rate_k_per_m"] * height


def _saturation_pressure(temperature):
    celsius = temperature - MAGNUS_REFERENCE_TEMPERATURE_K
    return MAGNUS_REFERENCE_PRESSURE_PA * math.exp(MAGNUS_A * celsius / (MAGNUS_B_K + celsius))


def _integrate_segment(request, lower, upper, subintervals):
    """Composite Simpson rule, independently using the declared mixture."""
    if type(subintervals) is not int or subintervals < 2 or subintervals % 2:
        raise ValueError("Simpson quadrature requires a positive even subdivision count")
    gas_constant = _mixture(request)["gas_constant_j_per_kg_k"]
    width = (upper - lower) / subintervals
    total = 0.0
    for index in range(subintervals + 1):
        temperature = _temperature(request, lower + index * width)
        if not MIN_TEMPERATURE_K <= temperature <= MAX_TEMPERATURE_K:
            raise ValueError("Quadrature temperature is outside the declared moist-column domain")
        weight = 1 if index in (0, subintervals) else 4 if index % 2 else 2
        total += weight * GRAVITY / (gas_constant * temperature)
    return width * total / 3.0


def _quadrature_reference(request):
    heights = request["sampling"]["height_m"]
    segments = len(heights) - 1
    evaluations = segments * (COARSE_SUBINTERVALS + REFINED_SUBINTERVALS + 2)
    if not 1 <= segments <= MAX_SEGMENTS or evaluations > MAX_QUADRATURE_EVALUATIONS:
        raise ValueError("Moist-column quadrature exceeds the bounded evaluation budget")
    integrals, pressures = {}, {}
    for label, intervals in (("coarse", COARSE_SUBINTERVALS), ("refined", REFINED_SUBINTERVALS)):
        integrals[label] = [_integrate_segment(request, lower, upper, intervals)
                            for lower, upper in zip(heights, heights[1:])]
        cumulative = 0.0
        pressures[label] = [float(request["reference"]["pressure_pa"])]
        for integral in integrals[label]:
            cumulative += integral
            pressures[label].append(request["reference"]["pressure_pa"] * math.exp(-cumulative))
    endpoint_heights = [heights[0], heights[-1]]
    endpoint_temperatures = [_temperature(request, value) for value in endpoint_heights]
    endpoint_pressures = [pressures["refined"][0], pressures["refined"][-1]]
    ratio = request["profile"]["water_mixing_ratio_kg_per_kg_dry_air"]
    mixture_constant = _mixture(request)["gas_constant_j_per_kg_k"]
    lapse = request["profile"]["lapse_rate_k_per_m"]
    error_bounds = []
    roundoff_allowances = []
    lower_integrals = []
    for lower, upper, integral in zip(heights, heights[1:], integrals["refined"]):
        width = upper - lower
        fourth_derivative_maximum = 24.0 * GRAVITY * lapse ** 4 / (mixture_constant * _temperature(request, upper) ** 5)
        error_bound = width / 180.0 * (width / REFINED_SUBINTERVALS) ** 4 * fourth_derivative_maximum
        allowance = INTEGRAL_ROUNDOFF_ALLOWANCE * max(1.0, abs(integral))
        error_bounds.append(error_bound)
        roundoff_allowances.append(allowance)
        lower_integrals.append(max(0.0, integral - error_bound - allowance))
    cumulative_lower = 0.0
    pressure_upper_bounds = [request["reference"]["pressure_pa"] * (1.0 + PRESSURE_ROUNDOFF_RELATIVE_ALLOWANCE)]
    for integral in lower_integrals:
        cumulative_lower += integral
        pressure_upper_bounds.append(request["reference"]["pressure_pa"] * math.exp(-cumulative_lower)
                                     * (1.0 + PRESSURE_ROUNDOFF_RELATIVE_ALLOWANCE))
    epsilon = DRY_GAS_CONSTANT / VAPOUR_GAS_CONSTANT
    humidity = [ratio * pressure / (epsilon + ratio) / _saturation_pressure(temperature)
                for pressure, temperature in zip(endpoint_pressures, endpoint_temperatures)]
    humidity_upper_bounds = [ratio * pressure / (epsilon + ratio) / _saturation_pressure(temperature)
                             * (1.0 + HUMIDITY_ROUNDOFF_RELATIVE_ALLOWANCE)
        for pressure, temperature in zip([pressure_upper_bounds[0], pressure_upper_bounds[-1]], endpoint_temperatures)]
    continuous = {"proof": HUMIDITY_PROOF, "interpretation": HUMIDITY_INTERPRETATION,
        "height_m": endpoint_heights, "temperature_k": endpoint_temperatures,
        "pressure_pa": endpoint_pressures, "relative_humidity": humidity,
        "maximum_relative_humidity": max(humidity),
        "maximum_allowed_relative_humidity": MAX_RELATIVE_HUMIDITY,
        "minimum_temperature_k": MIN_TEMPERATURE_K, "maximum_temperature_k": MAX_TEMPERATURE_K,
        "relative_humidity_upper_bound": humidity_upper_bounds,
        "maximum_relative_humidity_upper_bound": max(humidity_upper_bounds),
        "humidity_roundoff_relative_allowance": HUMIDITY_ROUNDOFF_RELATIVE_ALLOWANCE,
        "guard_interpretation": GUARD_INTERPRETATION}
    return {"method": "composite_simpson", "integrand": "g/(R_mix*T)",
        "coarse_subintervals_per_segment": COARSE_SUBINTERVALS,
        "refined_subintervals_per_segment": REFINED_SUBINTERVALS,
        "segments": segments, "quadrature_evaluations": evaluations,
        "maximum_quadrature_evaluations": MAX_QUADRATURE_EVALUATIONS,
        "interpretation": QUADRATURE_INTERPRETATION,
        "coarse_segment_integrals": integrals["coarse"], "refined_segment_integrals": integrals["refined"],
        "coarse_pressure_pa": pressures["coarse"], "refined_pressure_pa": pressures["refined"],
        "integral_bound_method": INTEGRAL_BOUND_METHOD, "integral_roundoff_allowance": INTEGRAL_ROUNDOFF_ALLOWANCE,
        "pressure_roundoff_relative_allowance": PRESSURE_ROUNDOFF_RELATIVE_ALLOWANCE,
        "refined_segment_error_bounds": error_bounds, "segment_integral_roundoff_allowances": roundoff_allowances,
        "segment_integral_lower_bounds": lower_integrals, "pressure_upper_bound_pa": pressure_upper_bounds,
        "continuous_humidity": continuous}


def _summary(profile):
    summary = {"sample_count": len(profile["height_m"]), "top_height_m": profile["height_m"][-1]}
    for field in SUMMARY_FIELDS:
        values = profile[field]
        summary[field] = ({"minimum": None, "maximum": None} if values[0] is None else
                          {"minimum": min(values), "maximum": max(values)})
    summary["maximum_wind_speed_m_per_s"] = max(math.hypot(*row) for row in profile["wind_enu_m_per_s"])
    return summary


def _terminal(profile):
    return {field: deepcopy(profile[field][-1]) for field in STATE_FIELDS}


def _dry_limit_residual(request, result):
    if request["profile"]["water_mixing_ratio_kg_per_kg_dry_air"] != 0.0:
        return 0.0
    profile = result["profile"]
    return float(result["mixture"]["water_mass_fraction"] != 0.0
                 or any(value != 0.0 for field in WATER_ZERO_FIELDS for value in profile[field])
                 or any(value is not None for value in profile["liquid_equilibrium_dew_point_k"]))


def _dew_point_domain_residual(profile):
    return float(any(value is not None and not MIN_DEW_POINT_K <= value <= MAX_DEW_POINT_K
                     for value in profile["liquid_equilibrium_dew_point_k"]))


def _residuals(request, result, reference):
    profile = result["profile"]
    mixture = _mixture(request)
    gas_constant, cp, gamma = (mixture[field] for field in
        ("gas_constant_j_per_kg_k", "specific_heat_cp_j_per_kg_k", "heat_capacity_ratio"))
    ratio = mixture["water_mixing_ratio_kg_per_kg_dry_air"]
    epsilon = DRY_GAS_CONSTANT / VAPOUR_GAS_CONSTANT
    wind = request["profile"]["wind_enu_m_per_s"]
    wind_scale = max(1.0, math.hypot(*wind))
    residuals = {name: 0.0 for name in CHECK_TOLERANCES}
    residuals["mixture_parameters"] = max(_relative(result["mixture"][field], mixture[field])
                                           for field in MIXTURE_FIELDS)
    heights, temperatures, pressures = (profile[field] for field in ("height_m", "temperature_k", "pressure_pa"))
    for index, (height, temperature, pressure) in enumerate(zip(heights, temperatures, pressures)):
        vapour = ratio * pressure / (epsilon + ratio)
        dry_pressure = pressure - vapour
        dry_density = profile["dry_air_density_kg_per_m3"][index]
        vapour_density = profile["water_vapour_density_kg_per_m3"][index]
        observed_vapour = profile["water_vapour_pressure_pa"][index]
        observed_dry_pressure = profile["dry_air_partial_pressure_pa"][index]
        density = profile["density_kg_per_m3"][index]
        within_temperature = MIN_TEMPERATURE_K <= temperature <= MAX_TEMPERATURE_K
        saturation = _saturation_pressure(temperature) if within_temperature else None
        dew_point = profile["liquid_equilibrium_dew_point_k"][index]
        dew_closure = (0.0 if dew_point is None else
            _relative(_saturation_pressure(dew_point), vapour) if MIN_DEW_POINT_K <= dew_point <= MAX_DEW_POINT_K
            else MAX_RESIDUAL)
        values = {
            "prescribed_temperature": _relative(temperature, _temperature(request, height)),
            "prescribed_wind": max(_finite_residual((value - expected) / wind_scale)
                for value, expected in zip(profile["wind_enu_m_per_s"][index], wind)),
            "vapour_partial_pressure": _relative(observed_vapour, vapour),
            "dry_partial_pressure": _relative(observed_dry_pressure, dry_pressure),
            "partial_pressure_closure": _relative(observed_dry_pressure + observed_vapour, pressure),
            "dry_air_equation_of_state": _relative(dry_density, observed_dry_pressure / DRY_GAS_CONSTANT / temperature),
            "water_vapour_equation_of_state": _relative(vapour_density, observed_vapour / VAPOUR_GAS_CONSTANT / temperature),
            "density_closure": _relative(density, dry_density + vapour_density),
            "equation_of_state": _relative(density, pressure / gas_constant / temperature),
            "relative_humidity": _relative(profile["relative_humidity"][index], vapour / saturation) if saturation else MAX_RESIDUAL,
            "liquid_water_saturation_pressure": _relative(profile["liquid_water_saturation_pressure_pa"][index], saturation) if saturation else MAX_RESIDUAL,
            "dew_point_closure": dew_closure,
            "frozen_sound_speed": _relative(profile["frozen_sound_speed_m_per_s"][index], math.sqrt(gamma * gas_constant * temperature)),
            "frozen_potential_temperature": _relative(profile["frozen_potential_temperature_k"][index],
                temperature * (REFERENCE_PRESSURE_PA / pressure) ** (gas_constant / cp)),
        }
        for name, value in values.items():
            residuals[name] = max(residuals[name], value)
    residuals["boundary_temperature"] = _relative(temperatures[0], request["reference"]["temperature_k"])
    residuals["boundary_pressure"] = _relative(pressures[0], request["reference"]["pressure_pa"])
    residuals["positive_properties"] = float(any(value <= 0 or not math.isfinite(value)
        for field in POSITIVE_FIELDS for value in profile[field]) or any(value < 0 or not math.isfinite(value)
        for field in WATER_ZERO_FIELDS for value in profile[field]))
    residuals["declared_temperature_domain"] = float(any(not MIN_TEMPERATURE_K <= value <= MAX_TEMPERATURE_K for value in temperatures))
    residuals["declared_dew_point_domain"] = _dew_point_domain_residual(profile)
    residuals["sampled_unsaturation"] = float(max(profile["relative_humidity"]) > MAX_RELATIVE_HUMIDITY)
    residuals["continuous_unsaturation"] = float(reference["continuous_humidity"]["maximum_relative_humidity_upper_bound"] > MAX_RELATIVE_HUMIDITY)
    residuals["dry_limit_water_state"] = _dry_limit_residual(request, result)
    residuals["frozen_stability_domain"] = float(GRAVITY / cp <= request["profile"]["lapse_rate_k_per_m"])
    residuals["pressure_monotonicity"] = max(0.0, max((upper - lower) / lower for lower, upper in zip(pressures, pressures[1:])))
    potential = profile["frozen_potential_temperature_k"]
    residuals["frozen_potential_temperature_stability"] = max(0.0, max((lower - upper) / lower for lower, upper in zip(potential, potential[1:])))
    residuals["segment_hydrostatic_balance"] = max(_finite_residual(math.expm1(math.log(upper) - math.log(lower) + integral))
        for lower, upper, integral in zip(pressures, pressures[1:], reference["refined_segment_integrals"]))
    residuals["cumulative_pressure_profile"] = max(_relative(observed, expected) for observed, expected in zip(pressures, reference["refined_pressure_pa"]))
    residuals["quadrature_refinement"] = max(
        max(_finite_residual(math.expm1(coarse - refined)) for coarse, refined in zip(reference["coarse_segment_integrals"], reference["refined_segment_integrals"])),
        max(_relative(coarse, refined) for coarse, refined in zip(reference["coarse_pressure_pa"], reference["refined_pressure_pa"])))
    residuals["quadrature_budget"] = float(reference["quadrature_evaluations"] > MAX_QUADRATURE_EVALUATIONS)
    return {name: _finite_residual(value) for name, value in residuals.items()}


def _check_spec(request):
    return {name: 0.0 if key is None else request["tolerances"][key] for name, key in CHECK_TOLERANCES.items()}


def _qualification(request, passed):
    unsupported = sorted(set(request["desired_observables"]) & EXPANSION_OBSERVABLES)
    supported = sorted(set(request["desired_observables"]) - set(unsupported))
    action = "REFUSE" if not passed else "EXPAND" if unsupported else "LOCAL"
    reason = ("Numerical or domain checks failed; the declared unsaturated moist-column candidate is not qualified." if not passed else
        "Numerical and domain checks passed; requested observables require an additional qualified provider." if unsupported else
        "Numerical and domain checks passed within the declared unsaturated frozen-composition hydrostatic scope.")
    return {"action": action, "supported_observables": supported, "unsupported_observables": unsupported, "reason": reason}


def verify(request: dict, result: dict) -> dict:
    request = validate_request(request)
    result = validate_result(request, result)
    reference = _quadrature_reference(request)
    residuals = _residuals(request, result, reference)
    spec = _check_spec(request)
    checks = [{"name": name, "value": residuals[name], "tolerance": spec[name],
               "status": "PASS" if residuals[name] <= spec[name] else "FAIL"} for name in sorted(spec)]
    passed = all(row["status"] == "PASS" for row in checks)
    return seal({"schema": REPORT_SCHEMA, "request_digest": digest(request), "candidate_digest": result["record_digest"],
        "claim_scope": CLAIM_SCOPE, "verifier": VERIFIER_ID, "thresholds": deepcopy(request["tolerances"]),
        "status": "PASS" if passed else "FAIL", "checks": checks, "reference": reference,
        "metrics": {"residuals": residuals, "summary": _summary(result["profile"]), "terminal": _terminal(result["profile"])},
        "qualification": _qualification(request, passed), "limitations": list(LIMITATIONS)})


def _validate_reference(request, reference):
    """Validate retained arrays and declarations without scientific evaluation."""
    keys(reference, REFERENCE_FIELDS)
    segments = len(request["sampling"]["height_m"]) - 1
    declarations = {"method": "composite_simpson", "integrand": "g/(R_mix*T)",
        "coarse_subintervals_per_segment": COARSE_SUBINTERVALS, "refined_subintervals_per_segment": REFINED_SUBINTERVALS,
        "segments": segments, "quadrature_evaluations": segments * (COARSE_SUBINTERVALS + REFINED_SUBINTERVALS + 2),
        "maximum_quadrature_evaluations": MAX_QUADRATURE_EVALUATIONS, "interpretation": QUADRATURE_INTERPRETATION}
    for name, expected in declarations.items():
        if (type(expected) is int and type(reference[name]) is not int) or reference[name] != expected:
            raise ValueError("Stored moist quadrature declaration differs from the bounded rule")
    for name in ("coarse_segment_integrals", "refined_segment_integrals", "coarse_pressure_pa", "refined_pressure_pa"):
        count = segments if name.endswith("integrals") else segments + 1
        values = reference[name]
        if type(values) is not list or len(values) != count or any(
                number(value) < 0 if name.endswith("integrals") else number(value) <= 0 for value in values):
            raise ValueError("Stored quadrature arrays require nonnegative integrals and positive pressure")
        if name.endswith("pressure_pa") and (values[0] != request["reference"]["pressure_pa"] or any(upper > lower for lower, upper in zip(values, values[1:]))):
            raise ValueError("Stored quadrature pressure contradicts its boundary or monotonicity")
    if (reference["integral_bound_method"] != INTEGRAL_BOUND_METHOD
            or number(reference["integral_roundoff_allowance"]) != INTEGRAL_ROUNDOFF_ALLOWANCE
            or number(reference["pressure_roundoff_relative_allowance"]) != PRESSURE_ROUNDOFF_RELATIVE_ALLOWANCE):
        raise ValueError("Stored humidity guard changed its integral method or fixed rounding allowances")
    for field in ("refined_segment_error_bounds", "segment_integral_roundoff_allowances", "segment_integral_lower_bounds"):
        values = reference[field]
        if type(values) is not list or len(values) != segments or any(number(value) < 0 for value in values):
            raise ValueError("Stored humidity guard integral bounds require finite nonnegative segment arrays")
    values = reference["pressure_upper_bound_pa"]
    if type(values) is not list or len(values) != segments + 1 or any(number(value) <= 0 for value in values):
        raise ValueError("Stored upper pressure bound requires positive finite grid values")
    expected_boundary = request["reference"]["pressure_pa"] * (1.0 + PRESSURE_ROUNDOFF_RELATIVE_ALLOWANCE)
    if values[0] != expected_boundary:
        raise ValueError("Stored upper pressure bound changed its declared boundary allowance")
    for index, (integral, error, allowance, lower_bound) in enumerate(zip(reference["refined_segment_integrals"],
            reference["refined_segment_error_bounds"], reference["segment_integral_roundoff_allowances"], reference["segment_integral_lower_bounds"])):
        if (allowance != INTEGRAL_ROUNDOFF_ALLOWANCE * max(1.0, abs(integral))
                or lower_bound != max(0.0, integral - error - allowance)):
            raise ValueError("Stored lower integral bound contradicts retained Simpson data or fixed rounding allowance")
        if (not reference["refined_pressure_pa"][index + 1] <= values[index + 1] <= expected_boundary
                or values[index + 1] > values[index]):
            raise ValueError("Stored upper pressure bound contradicts retained ordering or boundaries")
    humidity = reference["continuous_humidity"]
    keys(humidity, HUMIDITY_REFERENCE_FIELDS)
    declarations = {"proof": HUMIDITY_PROOF, "interpretation": HUMIDITY_INTERPRETATION,
        "maximum_allowed_relative_humidity": MAX_RELATIVE_HUMIDITY,
        "minimum_temperature_k": MIN_TEMPERATURE_K, "maximum_temperature_k": MAX_TEMPERATURE_K,
        "humidity_roundoff_relative_allowance": HUMIDITY_ROUNDOFF_RELATIVE_ALLOWANCE,
        "guard_interpretation": GUARD_INTERPRETATION}
    for name, expected in declarations.items():
        if type(expected) is str:
            if humidity[name] != expected:
                raise ValueError("Stored continuous humidity declaration differs")
        elif number(humidity[name]) != expected:
            raise ValueError("Stored continuous humidity domain differs")
    for field in ("height_m", "temperature_k", "pressure_pa", "relative_humidity", "relative_humidity_upper_bound"):
        values = humidity[field]
        if type(values) is not list or len(values) != 2 or any(number(value) < 0 for value in values):
            raise ValueError("Stored humidity reference requires two finite nonnegative endpoints")
    heights = request["sampling"]["height_m"]
    if (humidity["height_m"] != [heights[0], heights[-1]] or humidity["temperature_k"] != [_temperature(request, heights[0]), _temperature(request, heights[-1])]
            or humidity["pressure_pa"] != [reference["refined_pressure_pa"][0], reference["refined_pressure_pa"][-1]]
            or number(humidity["maximum_relative_humidity"]) != max(humidity["relative_humidity"])
            or number(humidity["maximum_relative_humidity_upper_bound"]) != max(humidity["relative_humidity_upper_bound"])
            or any(upper < nominal for upper, nominal in zip(humidity["relative_humidity_upper_bound"], humidity["relative_humidity"]))):
        raise ValueError("Stored continuous humidity endpoints or maximum contradict retained declarations")


def validate_report(request: dict, result: dict, report: dict) -> None:
    """Validate retained identities without integration or constitutive replay.

    A coherently forged sealed report can pass; a fresh numerical audit is
    required before exporting a handoff with retained verification bindings.
    """
    request = validate_request(request)
    result = validate_result(request, result)
    json_tree(report)
    keys(report, {"schema", "request_digest", "candidate_digest", "claim_scope", "verifier", "thresholds",
        "status", "checks", "reference", "metrics", "qualification", "limitations", "record_digest"})
    if (report["schema"] != REPORT_SCHEMA or report["request_digest"] != digest(request)
            or report["candidate_digest"] != result["record_digest"] or report["claim_scope"] != CLAIM_SCOPE
            or report["verifier"] != VERIFIER_ID or report["thresholds"] != request["tolerances"]
            or report["limitations"] != LIMITATIONS or report["status"] not in {"PASS", "FAIL"}):
        raise ValueError("Stored moist verification identity or declaration differs")
    keys(report["thresholds"], set(request["tolerances"]))
    for value in report["thresholds"].values():
        number(value)
    _validate_reference(request, report["reference"])
    metrics = report["metrics"]
    keys(metrics, {"residuals", "summary", "terminal"})
    keys(metrics["residuals"], set(CHECK_TOLERANCES))
    if any(number(value) < 0 or value > MAX_RESIDUAL for value in metrics["residuals"].values()):
        raise ValueError("Stored numerical errors must be bounded nonnegative finite values")
    if metrics["summary"] != _summary(result["profile"]) or metrics["terminal"] != _terminal(result["profile"]):
        raise ValueError("Stored moist summaries differ from retained extrema or terminal state")
    summary = metrics["summary"]
    keys(summary, {"sample_count", "top_height_m", "maximum_wind_speed_m_per_s"} | set(SUMMARY_FIELDS))
    if type(summary["sample_count"]) is not int:
        raise ValueError("Stored sample count must be an integer")
    number(summary["top_height_m"])
    number(summary["maximum_wind_speed_m_per_s"])
    dry = request["profile"]["water_mixing_ratio_kg_per_kg_dry_air"] == 0.0
    for field in SUMMARY_FIELDS:
        keys(summary[field], {"minimum", "maximum"})
        for value in summary[field].values():
            if field == "liquid_equilibrium_dew_point_k" and dry:
                if value is not None:
                    raise ValueError("Dry-limit dew-point extrema must be null")
            else:
                number(value)
    keys(metrics["terminal"], set(STATE_FIELDS))
    for field in STATE_FIELDS:
        values = metrics["terminal"][field] if field == "wind_enu_m_per_s" else [metrics["terminal"][field]]
        for value in values:
            if field == "liquid_equilibrium_dew_point_k" and dry:
                if value is not None:
                    raise ValueError("Dry-limit terminal dew point must be null")
            else:
                number(value)
    profile = result["profile"]
    basic = {"positive_properties": 0.0, "quadrature_budget": 0.0, "frozen_stability_domain": 0.0,
        "declared_temperature_domain": float(any(not MIN_TEMPERATURE_K <= value <= MAX_TEMPERATURE_K for value in profile["temperature_k"])),
        "declared_dew_point_domain": _dew_point_domain_residual(profile),
        "sampled_unsaturation": float(max(profile["relative_humidity"]) > MAX_RELATIVE_HUMIDITY),
        "continuous_unsaturation": float(report["reference"]["continuous_humidity"]["maximum_relative_humidity_upper_bound"] > MAX_RELATIVE_HUMIDITY),
        "dry_limit_water_state": _dry_limit_residual(request, result),
        "boundary_temperature": _relative(profile["temperature_k"][0], request["reference"]["temperature_k"]),
        "boundary_pressure": _relative(profile["pressure_pa"][0], request["reference"]["pressure_pa"])}
    if any(metrics["residuals"][name] != value for name, value in basic.items()):
        raise ValueError("Stored errors contradict retained boundary, domain or budget declarations")
    checks, spec = report["checks"], _check_spec(request)
    if type(checks) is not list or len(checks) != len(spec):
        raise ValueError("Stored moist report is missing or duplicates checks")
    names = []
    for row in checks:
        keys(row, {"name", "value", "tolerance", "status"})
        name = row["name"]
        if (type(name) is not str or name not in spec or number(row["value"]) != metrics["residuals"][name]
                or number(row["tolerance"]) != spec[name] or row["status"] != ("PASS" if row["value"] <= row["tolerance"] else "FAIL")):
            raise ValueError("Stored moist check contradicts its metric or threshold")
        names.append(name)
    if len(set(names)) != len(names) or set(names) != set(spec):
        raise ValueError("Stored moist report is missing or duplicates checks")
    passed = all(row["status"] == "PASS" for row in checks)
    if report["status"] != ("PASS" if passed else "FAIL") or report["qualification"] != _qualification(request, passed):
        raise ValueError("Stored moist qualification contradicts checks or requested observables")
    check_seal(report)
