"""Independent numerical audit of a declared dry hydrostatic atmosphere column.

Hydrostatic pressure is checked by numerical integration of g/(R*T), independently
of the compiler's analytic pressure expression. Retained declaration validation
does not integrate, rerun the compiler, or repeat this numerical verification.
Neither a content seal nor numerical agreement validates a physical environment.
"""
from __future__ import annotations

from copy import deepcopy
import math

from .atmosphere_contract import (
    CLAIM_SCOPE, EXPANSION_OBSERVABLES, REPORT_SCHEMA, STATE_FIELDS,
    validate_request, validate_result,
)
from .control_contracts import json_tree, keys, number
from .operations.runner import check_seal, digest, seal

VERIFIER_ID = "independent_composite_simpson_dry_hydrostatic_binary64"
COARSE_SUBINTERVALS = 16
REFINED_SUBINTERVALS = 32
MAX_SEGMENTS = 128
MAX_QUADRATURE_EVALUATIONS = MAX_SEGMENTS * (COARSE_SUBINTERVALS + REFINED_SUBINTERVALS + 2)
MIN_TEMPERATURE_K = 180.0
GAS_CONSTANT = 287.05
GRAVITY = 9.80665
GAMMA = 1.4
SPECIFIC_HEAT_CP = GAMMA * GAS_CONSTANT / (GAMMA - 1.0)
REFERENCE_PRESSURE_PA = 100000.0
SUTHERLAND_MU_PA_S = 1.716e-5
SUTHERLAND_TEMPERATURE_K = 273.15
SUTHERLAND_CONSTANT_K = 110.4
MAX_RESIDUAL = 1e150

LIMITATIONS = [
    "Numerical verification of a declared dry ideal-gas hydrostatic column with a linear temperature lapse, constant gravity and a prescribed uniform local ENU wind only.",
    "Simpson quadrature refinement compares two finite rules; it is not a certified integration-error bound or a continuum-convergence proof.",
    "Declared source context and time do not provide weather observations, calibration, a forecast or experimental validation of an environment.",
    "Prescribed wind is an input, not a solved velocity field; horizontal momentum, turbulence and fluid dynamics are unqualified.",
    "Humidity, precipitation, clouds, radiation, reactions, visual scattering and material conditioning remain unqualified.",
    "Height is above the declared reference; the reference origin and local ENU frame do not supply a geodetic or terrain transformation.",
    "Qualification recommendations do not perform canonical state admission.",
]
QUADRATURE_INTERPRETATION = "composite Simpson integration of g/(R*T) on each declared height interval; two finite rules, no certified error bound"
CHECK_TOLERANCES = {
    "prescribed_temperature": "constitutive_relative",
    "prescribed_wind": "constitutive_relative",
    "equation_of_state": "constitutive_relative",
    "sound_speed": "constitutive_relative",
    "dynamic_viscosity": "constitutive_relative",
    "kinematic_viscosity": "constitutive_relative",
    "potential_temperature": "constitutive_relative",
    "positive_properties": None,
    "boundary_temperature": "constitutive_relative",
    "boundary_pressure": "constitutive_relative",
    "pressure_monotonicity": "constitutive_relative",
    "potential_temperature_stability": "constitutive_relative",
    "segment_hydrostatic_balance": "hydrostatic_relative",
    "cumulative_pressure_profile": "hydrostatic_relative",
    "quadrature_refinement": "quadrature_relative",
    "quadrature_budget": None,
    "declared_temperature_domain": None,
}
REFERENCE_FIELDS = {
    "method", "integrand", "coarse_subintervals_per_segment", "refined_subintervals_per_segment",
    "segments", "quadrature_evaluations", "maximum_quadrature_evaluations", "interpretation",
    "coarse_segment_integrals", "refined_segment_integrals", "coarse_pressure_pa", "refined_pressure_pa",
}
POSITIVE_FIELDS = tuple(field for field in STATE_FIELDS if field not in {"height_m", "wind_enu_m_per_s"})


def _finite_residual(value):
    """Bound overflowed residuals so correctly failed evidence remains sealable."""
    return min(abs(value), MAX_RESIDUAL) if math.isfinite(value) else MAX_RESIDUAL


def _relative(observed, expected):
    return _finite_residual((observed - expected) / abs(expected))


def _temperature(request, height):
    return request["reference"]["temperature_k"] - request["profile"]["lapse_rate_k_per_m"] * height


def _integrate_segment(request, lower, upper, subintervals):
    """Composite Simpson rule; no analytic hydrostatic pressure formula."""
    if type(subintervals) is not int or subintervals < 2 or subintervals % 2:
        raise ValueError("Simpson quadrature requires a positive even subdivision count")
    width = (upper - lower) / subintervals
    total = 0.0
    for index in range(subintervals + 1):
        temperature = _temperature(request, lower + index * width)
        if temperature < MIN_TEMPERATURE_K:
            raise ValueError("Quadrature temperature is outside the declared dry-column profile")
        weight = 1 if index in (0, subintervals) else 4 if index % 2 else 2
        total += weight * GRAVITY / (GAS_CONSTANT * temperature)
    return width * total / 3.0


def _quadrature_reference(request):
    heights = request["sampling"]["height_m"]
    segments = len(heights) - 1
    evaluations = segments * (COARSE_SUBINTERVALS + REFINED_SUBINTERVALS + 2)
    if not 1 <= segments <= MAX_SEGMENTS or evaluations > MAX_QUADRATURE_EVALUATIONS:
        raise ValueError("Dry-column quadrature exceeds the bounded evaluation budget")
    integrals = {}
    pressures = {}
    for label, intervals in (("coarse", COARSE_SUBINTERVALS), ("refined", REFINED_SUBINTERVALS)):
        integrals[label] = [_integrate_segment(request, lower, upper, intervals)
                            for lower, upper in zip(heights, heights[1:])]
        cumulative = 0.0
        pressures[label] = [float(request["reference"]["pressure_pa"])]
        for integral in integrals[label]:
            cumulative += integral
            pressures[label].append(request["reference"]["pressure_pa"] * math.exp(-cumulative))
    return {"method": "composite_simpson", "integrand": "g/(R*T)",
            "coarse_subintervals_per_segment": COARSE_SUBINTERVALS,
            "refined_subintervals_per_segment": REFINED_SUBINTERVALS,
            "segments": segments, "quadrature_evaluations": evaluations,
            "maximum_quadrature_evaluations": MAX_QUADRATURE_EVALUATIONS,
            "interpretation": QUADRATURE_INTERPRETATION,
            "coarse_segment_integrals": integrals["coarse"], "refined_segment_integrals": integrals["refined"],
            "coarse_pressure_pa": pressures["coarse"], "refined_pressure_pa": pressures["refined"]}


def _summary(profile):
    summary = {"sample_count": len(profile["height_m"]),
               "top_height_m": profile["height_m"][-1]}
    for field in POSITIVE_FIELDS:
        summary[field] = {"minimum": min(profile[field]), "maximum": max(profile[field])}
    # hypot avoids overflow when a finite but extreme retained wind is audited.
    summary["maximum_wind_speed_m_per_s"] = max(math.hypot(*row) for row in profile["wind_enu_m_per_s"])
    return summary


def _terminal(profile):
    return {field: deepcopy(profile[field][-1]) for field in STATE_FIELDS}


def _residuals(request, result, reference):
    profile = result["profile"]
    heights, temperatures, pressures, densities = (profile[field] for field in
        ("height_m", "temperature_k", "pressure_pa", "density_kg_per_m3"))
    wind = request["profile"]["wind_enu_m_per_s"]
    wind_scale = max(1.0, math.hypot(*wind))
    residuals = {name: 0.0 for name in CHECK_TOLERANCES}
    for index, (height, temperature, pressure, density) in enumerate(zip(heights, temperatures, pressures, densities)):
        expected_temperature = _temperature(request, height)
        values = {
            "prescribed_temperature": _relative(temperature, expected_temperature),
            "prescribed_wind": max(_finite_residual((value - expected) / wind_scale)
                                    for value, expected in zip(profile["wind_enu_m_per_s"][index], wind)),
            "equation_of_state": _relative(density, pressure / GAS_CONSTANT / temperature),
            "sound_speed": _relative(profile["sound_speed_m_per_s"][index], math.sqrt(GAMMA * GAS_CONSTANT * temperature)),
            "dynamic_viscosity": _relative(profile["dynamic_viscosity_pa_s"][index],
                SUTHERLAND_MU_PA_S * (temperature / SUTHERLAND_TEMPERATURE_K) ** 1.5
                * (SUTHERLAND_TEMPERATURE_K + SUTHERLAND_CONSTANT_K) / (temperature + SUTHERLAND_CONSTANT_K)),
            "kinematic_viscosity": _relative(profile["kinematic_viscosity_m2_per_s"][index], profile["dynamic_viscosity_pa_s"][index] / density),
            "potential_temperature": _relative(profile["potential_temperature_k"][index],
                temperature * (REFERENCE_PRESSURE_PA / pressure) ** (GAS_CONSTANT / SPECIFIC_HEAT_CP)),
        }
        for name, value in values.items():
            residuals[name] = max(residuals[name], value)
    residuals["boundary_temperature"] = _relative(temperatures[0], request["reference"]["temperature_k"])
    residuals["boundary_pressure"] = _relative(pressures[0], request["reference"]["pressure_pa"])
    residuals["positive_properties"] = float(any(value <= 0 or not math.isfinite(value)
        for field in POSITIVE_FIELDS for value in profile[field]))
    residuals["declared_temperature_domain"] = float(min(temperatures) < MIN_TEMPERATURE_K)
    residuals["pressure_monotonicity"] = max(0.0, max(
        (upper - lower) / lower for lower, upper in zip(pressures, pressures[1:])))
    potential = profile["potential_temperature_k"]
    residuals["potential_temperature_stability"] = max(0.0, max(
        (lower - upper) / lower for lower, upper in zip(potential, potential[1:])))
    # Relative local pressure reconstruction uses expm1(log ratio + integral),
    # avoiding a weak normalization for very short height intervals.
    residuals["segment_hydrostatic_balance"] = max(_finite_residual(math.expm1(
        math.log(upper) - math.log(lower) + integral))
        for lower, upper, integral in zip(pressures, pressures[1:], reference["refined_segment_integrals"]))
    residuals["cumulative_pressure_profile"] = max(_relative(observed, expected)
        for observed, expected in zip(pressures, reference["refined_pressure_pa"]))
    residuals["quadrature_refinement"] = max(
        max(_finite_residual(math.expm1(coarse - refined)) for coarse, refined in
            zip(reference["coarse_segment_integrals"], reference["refined_segment_integrals"])),
        max(_relative(coarse, refined) for coarse, refined in
            zip(reference["coarse_pressure_pa"], reference["refined_pressure_pa"])))
    residuals["quadrature_budget"] = float(reference["quadrature_evaluations"] > MAX_QUADRATURE_EVALUATIONS)
    return {name: _finite_residual(value) for name, value in residuals.items()}


def _check_spec(request):
    return {name: 0.0 if key is None else request["tolerances"][key]
            for name, key in CHECK_TOLERANCES.items()}


def _qualification(request, passed):
    unsupported = sorted(set(request["desired_observables"]) & EXPANSION_OBSERVABLES)
    supported = sorted(set(request["desired_observables"]) - set(unsupported))
    action = "REFUSE" if not passed else "EXPAND" if unsupported else "LOCAL"
    reason = ("Numerical checks failed; the declared dry-column candidate is not qualified." if not passed else
              "Numerical checks passed; requested observables require an additional qualified provider." if unsupported else
              "Numerical checks passed within the declared dry hydrostatic column scope.")
    return {"action": action, "supported_observables": supported,
            "unsupported_observables": unsupported, "reason": reason}


def verify(request: dict, result: dict) -> dict:
    """Audit a structurally valid candidate without importing its compiler."""
    request = validate_request(request)
    result = validate_result(request, result)
    reference = _quadrature_reference(request)
    residuals = _residuals(request, result, reference)
    spec = _check_spec(request)
    checks = [{"name": name, "value": residuals[name], "tolerance": spec[name],
               "status": "PASS" if residuals[name] <= spec[name] else "FAIL"}
              for name in sorted(spec)]
    passed = all(row["status"] == "PASS" for row in checks)
    return seal({"schema": REPORT_SCHEMA, "request_digest": digest(request),
                 "candidate_digest": result["record_digest"], "claim_scope": CLAIM_SCOPE,
                 "verifier": VERIFIER_ID, "thresholds": deepcopy(request["tolerances"]),
                 "status": "PASS" if passed else "FAIL", "checks": checks,
                 "reference": reference, "metrics": {"residuals": residuals,
                     "summary": _summary(result["profile"]), "terminal": _terminal(result["profile"])},
                 "qualification": _qualification(request, passed), "limitations": list(LIMITATIONS)})


def _validate_reference(request, reference):
    """Validate retained quadrature declarations without evaluating its rule."""
    keys(reference, REFERENCE_FIELDS)
    segments = len(request["sampling"]["height_m"]) - 1
    declarations = {"method": "composite_simpson", "integrand": "g/(R*T)",
        "coarse_subintervals_per_segment": COARSE_SUBINTERVALS,
        "refined_subintervals_per_segment": REFINED_SUBINTERVALS, "segments": segments,
        "quadrature_evaluations": segments * (COARSE_SUBINTERVALS + REFINED_SUBINTERVALS + 2),
        "maximum_quadrature_evaluations": MAX_QUADRATURE_EVALUATIONS,
        "interpretation": QUADRATURE_INTERPRETATION}
    for name, expected in declarations.items():
        if (type(expected) is int and type(reference[name]) is not int) or reference[name] != expected:
            raise ValueError("Stored quadrature declaration differs from the bounded rule")
    for name in ("coarse_segment_integrals", "refined_segment_integrals", "coarse_pressure_pa", "refined_pressure_pa"):
        expected_count = segments if name.endswith("integrals") else segments + 1
        values = reference[name]
        if (type(values) is not list or len(values) != expected_count
                or any(number(value) < 0 if name.endswith("integrals") else number(value) <= 0 for value in values)):
            raise ValueError("Stored quadrature arrays require finite nonnegative integrals and positive pressure")
        if name.endswith("pressure_pa") and (values[0] != request["reference"]["pressure_pa"]
                or any(upper > lower for lower, upper in zip(values, values[1:]))):
            raise ValueError("Stored quadrature pressure contradicts its boundary or monotonicity")
    heights = request["sampling"]["height_m"]
    for label in ("coarse", "refined"):
        integrals = reference[label + "_segment_integrals"]
        cumulative = 0.0
        for index, (lower, upper, integral) in enumerate(zip(heights, heights[1:], integrals)):
            # The positive decreasing prescribed temperature bounds the
            # integral. These endpoint bounds do not evaluate quadrature.
            lower_bound = GRAVITY * (upper - lower) / (GAS_CONSTANT * _temperature(request, lower))
            upper_bound = GRAVITY * (upper - lower) / (GAS_CONSTANT * _temperature(request, upper))
            allowance = 2e-14 * max(upper_bound, 1e-300)
            if not max(0.0, lower_bound - allowance) <= integral <= upper_bound + allowance:
                raise ValueError("Stored quadrature integral exceeds its endpoint temperature bounds")
            cumulative += integral
            if reference[label + "_pressure_pa"][index + 1] != request["reference"]["pressure_pa"] * math.exp(-cumulative):
                raise ValueError("Stored reference pressure differs from its retained cumulative integrals")


def validate_report(request: dict, result: dict, report: dict) -> None:
    """Check retained identities and declarations; do not repeat numerical physics.

    A coherent forged numerical report can pass this check. Fresh verification
    recomputes constitutive and hydrostatic residuals and detects such forgeries.
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
        raise ValueError("Stored atmosphere verification identity or declaration differs")
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
        raise ValueError("Stored atmosphere summaries differ from retained extrema or terminal state")
    # Strict types matter even when Python would equate true and 1.
    keys(metrics["summary"], {"sample_count", "top_height_m", "maximum_wind_speed_m_per_s"} | set(POSITIVE_FIELDS))
    if type(metrics["summary"]["sample_count"]) is not int:
        raise ValueError("Stored sample count must be an integer")
    number(metrics["summary"]["top_height_m"])
    number(metrics["summary"]["maximum_wind_speed_m_per_s"])
    for field in POSITIVE_FIELDS:
        keys(metrics["summary"][field], {"minimum", "maximum"})
        for value in metrics["summary"][field].values():
            number(value)
    keys(metrics["terminal"], set(STATE_FIELDS))
    for field in STATE_FIELDS:
        values = metrics["terminal"][field] if field == "wind_enu_m_per_s" else [metrics["terminal"][field]]
        for value in values:
            number(value)
    basic_bindings = {"positive_properties": 0.0, "quadrature_budget": 0.0,
        "declared_temperature_domain": float(min(result["profile"]["temperature_k"]) < MIN_TEMPERATURE_K),
        "boundary_temperature": _relative(result["profile"]["temperature_k"][0], request["reference"]["temperature_k"]),
        "boundary_pressure": _relative(result["profile"]["pressure_pa"][0], request["reference"]["pressure_pa"])}
    if any(metrics["residuals"][name] != value for name, value in basic_bindings.items()):
        raise ValueError("Stored errors contradict retained boundary, domain or budget declarations")
    checks, spec = report["checks"], _check_spec(request)
    if type(checks) is not list or len(checks) != len(spec):
        raise ValueError("Stored atmosphere report is missing or duplicates checks")
    names = []
    for row in checks:
        keys(row, {"name", "value", "tolerance", "status"})
        name = row["name"]
        if (type(name) is not str or name not in spec or number(row["value"]) != metrics["residuals"][name]
                or number(row["tolerance"]) != spec[name]
                or row["status"] != ("PASS" if row["value"] <= row["tolerance"] else "FAIL")):
            raise ValueError("Stored atmosphere check contradicts its metric or threshold")
        names.append(name)
    if len(set(names)) != len(names) or set(names) != set(spec):
        raise ValueError("Stored atmosphere report is missing or duplicates checks")
    passed = all(row["status"] == "PASS" for row in checks)
    if report["status"] != ("PASS" if passed else "FAIL") or report["qualification"] != _qualification(request, passed):
        raise ValueError("Stored atmosphere qualification contradicts checks or requested observables")
    check_seal(report)
