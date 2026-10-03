"""Independent numerical qualification of the bounded linear wave provider.

Fresh verification evaluates a continuum reference and all-history discrete
balance residuals. Retained report validation checks identities/declarations
without propagating either solver or reference. A seal binds content; it is
neither producer authentication nor empirical material validation.
"""
from __future__ import annotations

from copy import deepcopy
import math
import numpy as np

from .control_contracts import json_tree, keys, number
from .fluid_wave_contract import (CLAIM_SCOPE, EXPANSION_OBSERVABLES, FIELD_NAMES, HARMONICS,
    REFUSED_OBSERVABLES, REPORT_SCHEMA, SUPPORTED_OBSERVABLES, TRACE_LABELS, validate_request,
    validate_result, wave_speed_m_per_s)
from .fluid_wave_reference import REFERENCE_ID, reference
from .operations.runner import check_seal, digest, seal

VERIFIER_ID = "ciw.fluid-wave-independent-verifier.v1"
LIMITATIONS = [
    "Numerically qualified only for a fixed band-limited zero-mean pulse in periodic one-dimensional uniform-depth linear shallow water.",
    "Hard bounds require total modal amplitude/depth <= 0.01 and every retained wavenumber*depth <= 0.2 independently of user tolerances.",
    "Velocity is depth averaged at faces; elevation and hydrostatic bottom gauge pressure are cell centered; discharge is width*mean_depth*velocity.",
    "The energy is linear perturbation mechanical energy relative to the resting liquid, with staggered equal-volume quadrature.",
    "Three-level time and spatial refinement measure second-order behavior for this declared smooth benchmark; they do not qualify arbitrary initial conditions or boundaries.",
    "Viscosity, turbulence, breaking, wetting/drying, acoustic waves, surface tension, molecular interactions and deformable structures require additional providers.",
    "Material parameters and geometry are declarations; no experimental validation, parameter identification or canonical state admission is performed.",
]
TRACE_METRIC_FIELDS = {"analytic_maximum_normalized_errors", "maximum_mass_relative_drift",
    "maximum_energy_relative_drift", "constitutive_maximum_normalized_residual",
    "integrator_maximum_normalized_residual", "initial_energy_j", "final_energy_j",
    "wave_speed_m_per_s", "wave_speed_relative_error", "maximum_elevation_over_depth",
    "maximum_velocity_over_wave_speed"}
CONVERGENCE_FIELDS = {"coarse_difference_normalized", "fine_difference_normalized", "observed_order", "order_deficit"}
CONVERGENCE_INTERPRETATION = "three levels; discrete Fourier coefficients at common physical coordinates; fixed other discretization"


def _scales(model):
    c, amplitude = wave_speed_m_per_s(model), model["amplitude_m"]
    return {"free_surface_elevation_m": amplitude,
            "depth_averaged_velocity_m_per_s": c * amplitude / model["depth_m"],
            "volume_flux_m3_per_s": model["width_m"] * c * amplitude,
            "bottom_gauge_pressure_pa": model["density_kg_per_m3"] * model["gravity_m_per_s2"] * amplitude}


def _observed_speed(model, trace):
    """Unwrap the retained first Fourier harmonic phase, independent of peak tracking."""
    eta = np.asarray(trace["free_surface_elevation_m"])
    cells = trace["cells"]
    coefficient = np.fft.rfft(eta, axis=1)[:, 1] / cells
    phase = np.unwrap(np.angle(coefficient))
    angular_frequency = -(phase[-1] - phase[0]) / trace["time_s"][-1]
    return float(angular_frequency * model["length_m"] / (2.0 * math.pi))


def _trace_metrics(request, trace):
    model, scales = request["model"], _scales(request["model"])
    c, depth, gravity, width, density = (wave_speed_m_per_s(model), model["depth_m"],
        model["gravity_m_per_s2"], model["width_m"], model["density_kg_per_m3"])
    eta = np.asarray(trace["free_surface_elevation_m"], dtype=float)
    u = np.asarray(trace["depth_averaged_velocity_m_per_s"], dtype=float)
    pressure = np.asarray(trace["bottom_gauge_pressure_pa"], dtype=float)
    flux = np.asarray(trace["volume_flux_m3_per_s"], dtype=float)
    exact = reference(request, trace["time_s"], cells=trace["cells"])
    analytic = {field: float(np.max(np.abs(np.asarray(trace[field]) - np.asarray(exact[field])))) / scales[field]
                for field in FIELD_NAMES}
    dx, dt = trace["dx_m"], trace["dt_s"]
    volumes = width * dx * np.sum(depth + eta, axis=1)
    energies = 0.5 * density * width * dx * np.sum(gravity * eta * eta + depth * u * u, axis=1)
    initial_energy = exact["mechanical_energy_j"]
    volume_scale = model["length_m"] * width * depth
    constitutive = max(
        float(np.max(np.abs(flux - width * depth * u))) / scales["volume_flux_m3_per_s"],
        float(np.max(np.abs(pressure - density * gravity * (depth + eta)))) / scales["bottom_gauge_pressure_pa"],
        float(np.max(np.abs(np.asarray(trace["liquid_volume_m3"]) - volumes))) / volume_scale,
        float(np.max(np.abs(np.asarray(trace["mechanical_energy_j"]) - energies))) / initial_energy)
    midpoint_eta, midpoint_u = 0.5 * (eta[1:] + eta[:-1]), 0.5 * (u[1:] + u[:-1])
    continuity = eta[1:] - eta[:-1] + dt * depth * (np.roll(midpoint_u, -1, axis=1) - midpoint_u) / dx
    momentum = u[1:] - u[:-1] + dt * gravity * (midpoint_eta - np.roll(midpoint_eta, 1, axis=1)) / dx
    observed_speed = _observed_speed(model, trace)
    return {"analytic_maximum_normalized_errors": analytic,
            "maximum_mass_relative_drift": float(np.max(np.abs(volumes - volume_scale))) / volume_scale,
            "maximum_energy_relative_drift": float(np.max(np.abs(energies - initial_energy))) / initial_energy,
            "constitutive_maximum_normalized_residual": constitutive,
            "integrator_maximum_normalized_residual": max(float(np.max(np.abs(continuity))) / scales["free_surface_elevation_m"],
                float(np.max(np.abs(momentum))) / scales["depth_averaged_velocity_m_per_s"]),
            "initial_energy_j": float(energies[0]), "final_energy_j": float(energies[-1]),
            "wave_speed_m_per_s": observed_speed, "wave_speed_relative_error": abs(observed_speed - c) / c,
            "maximum_elevation_over_depth": float(np.max(np.abs(eta))) / depth,
            "maximum_velocity_over_wave_speed": float(np.max(np.abs(u))) / c}


def _coefficients(trace, field):
    """Fourier coefficients dephased from the sampled stagger to physical x=0."""
    values = np.asarray(trace[field])
    cells = trace["cells"]
    coefficients = np.fft.rfft(values, axis=1)[:, :4] / cells
    if field == "free_surface_elevation_m":
        coefficients *= np.exp(-1j * np.pi * np.arange(4) / cells)[None, :]
    return coefficients


def _difference(request, left, right, stride):
    scales = _scales(request["model"])
    difference = 0.0
    for field in ("free_surface_elevation_m", "depth_averaged_velocity_m_per_s"):
        delta = _coefficients(left, field) - _coefficients(right, field)[::stride]
        # Absolute coefficient sum bounds differences of the reconstructed
        # physical fields everywhere, so no interpolation error enters order.
        bound = np.abs(delta[:, 0]) + 2.0 * np.sum(np.abs(delta[:, 1:]), axis=1)
        difference = max(difference, float(np.max(bound)) / scales[field])
    return difference


def _convergence(request, first, second, third, stride):
    coarse, fine = _difference(request, first, second, stride), _difference(request, second, third, stride)
    # Avoid an artificial order claim if changes are at floating-point noise.
    order = math.log2(coarse / fine) if coarse > 1e-11 and fine > 1e-12 else 0.0
    return {"coarse_difference_normalized": coarse, "fine_difference_normalized": fine,
            "observed_order": order, "order_deficit": max(0.0, 1.8 - order)}


def _check_spec(request):
    tolerance = request["tolerances"]
    spec = {}
    for label in TRACE_LABELS:
        spec.update({label + ".analytic." + field: tolerance["analytic_normalized"] for field in FIELD_NAMES})
        spec.update({label + ".mass_relative_drift": tolerance["mass_relative"],
                     label + ".energy_relative_drift": tolerance["energy_relative"],
                     label + ".wave_speed_relative_error": tolerance["wave_speed_relative"],
                     label + ".constitutive_residual": 1e-11, label + ".integrator_residual": 1e-11,
                     label + ".small_amplitude_ratio": 0.01, label + ".small_velocity_ratio": 0.01})
    for name, tolerance_key in (("time_convergence", "time_refinement_normalized"),
                                ("spatial_convergence", "spatial_refinement_normalized")):
        spec[name + ".coarse_difference"] = tolerance[tolerance_key]
        spec[name + ".fine_difference"] = tolerance[tolerance_key]
        spec[name + ".order_deficit"] = 0.0
    return spec


def _check_values(metrics):
    values = {}
    for label, metric in metrics["traces"].items():
        values.update({label + ".analytic." + field: value for field, value in metric["analytic_maximum_normalized_errors"].items()})
        for suffix, name in (("mass_relative_drift", "maximum_mass_relative_drift"),
                             ("energy_relative_drift", "maximum_energy_relative_drift"),
                             ("wave_speed_relative_error", "wave_speed_relative_error"),
                             ("constitutive_residual", "constitutive_maximum_normalized_residual"),
                             ("integrator_residual", "integrator_maximum_normalized_residual"),
                             ("small_amplitude_ratio", "maximum_elevation_over_depth"),
                             ("small_velocity_ratio", "maximum_velocity_over_wave_speed")):
            values[label + "." + suffix] = metric[name]
    for name in ("time_convergence", "spatial_convergence"):
        for suffix, field in (("coarse_difference", "coarse_difference_normalized"),
                              ("fine_difference", "fine_difference_normalized"), ("order_deficit", "order_deficit")):
            values[name + "." + suffix] = metrics[name][field]
    return values


def _qualification(request, passed):
    desired = set(request["desired_observables"])
    refused = sorted(desired & REFUSED_OBSERVABLES)
    expansion = sorted(desired & EXPANSION_OBSERVABLES)
    action = "REFUSE" if not passed or refused else "EXPAND" if expansion else "LOCAL"
    reason = ("The numerical candidate failed qualification checks." if not passed else
              "Requested claims exceed the numerical instrument's authority." if refused else
              "Additional qualified physical providers are required." if expansion else
              "The numerical candidate passed within the bounded linear surface-wave scope.")
    return {"action": action, "recommended_admission": "verified_model" if action == "LOCAL" else "blocked",
            "requested_observables": list(request["desired_observables"]),
            "supported_observables": sorted(desired & SUPPORTED_OBSERVABLES),
            "expansion_observables": expansion, "refused_observables": refused, "reason": reason}


def verify(request: dict, result: dict) -> dict:
    request = validate_request(request)
    result = validate_result(request, result)
    metrics = {"traces": {label: _trace_metrics(request, result[label]) for label in TRACE_LABELS},
               "time_convergence": _convergence(request, result["primary"], result["time_refined"], result["time_fine"], 2),
               "spatial_convergence": _convergence(request, result["time_fine"], result["spatial_refined"], result["spatial_fine"], 1),
               "refinement_interpretation": CONVERGENCE_INTERPRETATION}
    values, spec = _check_values(metrics), _check_spec(request)
    checks = [{"name": name, "value": values[name], "tolerance": spec[name],
               "status": "PASS" if values[name] <= spec[name] else "FAIL"} for name in sorted(spec)]
    passed = all(row["status"] == "PASS" for row in checks)
    return seal({"schema": REPORT_SCHEMA, "request_digest": digest(request), "result_digest": result["record_digest"],
                 "claim_scope": CLAIM_SCOPE, "verification_method": VERIFIER_ID,
                 "reference_method": REFERENCE_ID, "status": "PASS" if passed else "FAIL", "checks": checks,
                 "metrics": metrics, "qualification": _qualification(request, passed), "limitations": list(LIMITATIONS)})


def validate_report(request: dict, result: dict, report: dict) -> dict:
    """Static retained-record checking, deliberately independent of fresh physics.

    A coherently resealed forged report can pass declaration checks; use verify
    for fresh physics. This boundary never calls solver/reference or FFT.
    """
    request = validate_request(request)
    result = validate_result(request, result)
    json_tree(report)
    keys(report, {"schema", "request_digest", "result_digest", "claim_scope", "verification_method", "reference_method",
                  "status", "checks", "metrics", "qualification", "limitations", "record_digest"})
    if (report["schema"] != REPORT_SCHEMA or report["request_digest"] != digest(request)
            or report["result_digest"] != result["record_digest"] or report["claim_scope"] != CLAIM_SCOPE
            or report["verification_method"] != VERIFIER_ID or report["reference_method"] != REFERENCE_ID
            or report["status"] not in {"PASS", "FAIL"} or report["limitations"] != LIMITATIONS):
        raise ValueError("Wave report identity, claim scope or limitations differ")
    metrics = report["metrics"]
    keys(metrics, {"traces", "time_convergence", "spatial_convergence", "refinement_interpretation"})
    if metrics["refinement_interpretation"] != CONVERGENCE_INTERPRETATION:
        raise ValueError("Wave refinement interpretation differs")
    keys(metrics["traces"], set(TRACE_LABELS))
    for label in TRACE_LABELS:
        metric = metrics["traces"][label]
        keys(metric, TRACE_METRIC_FIELDS)
        keys(metric["analytic_maximum_normalized_errors"], set(FIELD_NAMES))
        for value in metric["analytic_maximum_normalized_errors"].values():
            if not 0.0 <= number(value) <= 1e150:
                raise ValueError("Wave report errors require bounded nonnegative numbers")
        for field in TRACE_METRIC_FIELDS - {"analytic_maximum_normalized_errors"}:
            value = number(metric[field])
            if abs(value) > 1e150 or field != "wave_speed_m_per_s" and value < 0:
                raise ValueError("Wave metrics require bounded finite numbers and nonnegative errors")
        # Fresh metrics recompute physical energy from the retained fields.
        # The candidate's reported energy can disagree in a valid FAIL record;
        # that discrepancy belongs to the constitutive residual, not schema.
        if report["status"] == "PASS":
            allowance = 1.01e-11 * metric["initial_energy_j"]
            if (abs(metric["initial_energy_j"] - result[label]["mechanical_energy_j"][0]) > allowance
                    or abs(metric["final_energy_j"] - result[label]["mechanical_energy_j"][-1]) > allowance):
                raise ValueError("Passing wave report contradicts its retained scalar energy declarations")
    for name in ("time_convergence", "spatial_convergence"):
        metric = metrics[name]
        keys(metric, CONVERGENCE_FIELDS)
        for field, value in metric.items():
            value = number(value)
            if abs(value) > 1e150 or field != "observed_order" and value < 0:
                raise ValueError("Wave convergence metrics require bounded finite numbers")
        coarse, fine = metric["coarse_difference_normalized"], metric["fine_difference_normalized"]
        expected_order = math.log2(coarse / fine) if coarse > 1e-11 and fine > 1e-12 else 0.0
        if metric["observed_order"] != expected_order or metric["order_deficit"] != max(0.0, 1.8 - expected_order):
            raise ValueError("Stored convergence order differs from declared retained changes")
    values, spec = _check_values(metrics), _check_spec(request)
    checks = report["checks"]
    if type(checks) is not list or len(checks) != len(spec):
        raise ValueError("Wave report requires exactly one row per check")
    names = []
    for row in checks:
        keys(row, {"name", "value", "tolerance", "status"})
        name = row["name"]
        if (type(name) is not str or name not in spec or number(row["value"]) != values[name]
                or number(row["tolerance"]) != spec[name]
                or row["status"] != ("PASS" if values[name] <= spec[name] else "FAIL")):
            raise ValueError("Wave check contradicts its retained metric or threshold")
        names.append(name)
    if len(set(names)) != len(names) or set(names) != set(spec):
        raise ValueError("Wave report has duplicate or missing checks")
    passed = all(row["status"] == "PASS" for row in checks)
    if report["status"] != ("PASS" if passed else "FAIL") or report["qualification"] != _qualification(request, passed):
        raise ValueError("Wave report status or qualification contradicts checks")
    check_seal(report)
    return deepcopy(report)
