"""Fresh conservative SPH audit, independent reference, and static receipt checks."""
from copy import deepcopy
import math
import numpy as np

from .control_contracts import json_tree, keys, number
from .fluid_sph_contract import (CLAIM_SCOPE, EXPANSION_OBSERVABLES, FIELD_NAMES, LABELS, REFUSED_OBSERVABLES,
    REPORT_SCHEMA, SUPPORTED_OBSERVABLES, validate_request, validate_result)
from .fluid_sph_reference import REFERENCE_ID, analytic_values, quantities, reference
from .operations.runner import check_seal, digest, seal

VERIFIER_ID = "ciw.fluid-sph-independent-verifier.v1"
LIMITATIONS = [
    "Moving equal-mass continuum computational parcels in one periodic dimension; parcels are neither molecules nor suspended grains.",
    "Fixed normalized compact cubic B-spline with h=2*lattice_spacing; density is kernel mass sum divided by the declared cross-sectional area.",
    "Barotropic acoustic EOS p=c^2*(rho-rho0) with conservative internal energy primitive and symmetric pair pressure forces; negative perturbation pressure is permitted.",
    "Hard limits are low Mach <=0.002, density deviation <=0.002, ordered parcels with gaps inside0.99..1.01 lattice spacing, and acoustic dt*c/h<=0.1.",
    "Temporal and spatial three-level trends qualify only the fixed smooth small-amplitude short-time benchmark, not arbitrary parcel disorders or continuum SPH convergence.",
    "Refinement differences compare the mean and first two material-coordinate Fourier harmonics; all field samples separately undergo density, EOS, conservation and integrator audits.",
    "The linear acoustic continuum benchmark has finite smoothing and nonlinear model errors; the independent RK4 reference verifies the declared discrete parcel model.",
    "No viscosity, shock, free surface, surface gravity, turbulence, adaptive smoothing, molecular identity or experimental parameter identification is claimed.",
    "Seals establish retained content identity, not producer authentication, experimental validation or canonical admission.",
]
TRACE_METRICS = {"density_sum_residual", "eos_residual", "scalar_energy_residual", "scalar_momentum_residual",
                 "momentum_drift", "energy_drift", "position_recurrence_residual", "velocity_recurrence_residual",
                 "analytic_error", "maximum_mach", "maximum_density_deviation", "maximum_gap_deviation"}
CONVERGENCE_METRICS = {"coarse_difference", "fine_difference", "order", "order_deficit"}


def _scales(request):
    model = request["model"]
    length, c, a, rho0, area = (model[name] for name in
        ("length_m", "sound_speed_m_per_s", "strain_amplitude", "reference_density_kg_per_m3", "area_m2"))
    return {"position": a * length / (2.0 * math.pi), "velocity": c * a, "density": rho0 * a,
            "pressure": rho0 * c * c * a, "momentum": rho0 * area * length * c * a,
            "energy": rho0 * area * length * c * c * a * a}


def _metrics(request, trace):
    model, scale = request["model"], _scales(request)
    n, mass, h = trace["particles"], trace["parcel_mass_kg"], trace["smoothing_length_m"]
    x, v, density, pressure = (np.asarray(trace[field], dtype=float) for field in FIELD_NAMES)
    dt = trace["dt_s"]
    metrics = {key: 0.0 for key in TRACE_METRICS}
    energy, momentum, accelerations = [], [], []
    rho0, c, length = model["reference_density_kg_per_m3"], model["sound_speed_m_per_s"], model["length_m"]
    for index in range(len(trace["time_s"])):
        rho, p, a, e = quantities(model, x[index], v[index], mass, h)
        accelerations.append(a)
        energy.append(e)
        momentum.append(mass * float(np.sum(v[index])))
        metrics["density_sum_residual"] = max(metrics["density_sum_residual"], float(np.max(np.abs(rho - density[index]))) / scale["density"])
        metrics["eos_residual"] = max(metrics["eos_residual"], float(np.max(np.abs(p - pressure[index]))) / scale["pressure"])
        gaps = np.diff(np.concatenate((x[index], [x[index, 0] + length])))
        metrics["maximum_gap_deviation"] = max(metrics["maximum_gap_deviation"], float(np.max(np.abs(gaps / (length / n) - 1.0))))
    accelerations = np.asarray(accelerations)
    energy, momentum = np.asarray(energy), np.asarray(momentum)
    metrics.update(scalar_energy_residual=float(np.max(np.abs(energy - trace["total_energy_j"]))) / scale["energy"],
                   scalar_momentum_residual=float(np.max(np.abs(momentum - trace["total_momentum_kg_m_per_s"]))) / scale["momentum"],
                   momentum_drift=float(np.max(np.abs(momentum - momentum[0]))) / scale["momentum"],
                   energy_drift=float(np.max(np.abs(energy - energy[0])) / energy[0]),
                   maximum_mach=float(np.max(np.abs(v))) / c,
                   maximum_density_deviation=float(np.max(np.abs(density / rho0 - 1.0))))
    predicted_x = x[:-1] + dt * v[:-1] + 0.5 * dt * dt * accelerations[:-1]
    predicted_v = v[:-1] + 0.5 * dt * (accelerations[:-1] + accelerations[1:])
    metrics["position_recurrence_residual"] = float(np.max(np.abs(x[1:] - predicted_x))) / scale["position"]
    metrics["velocity_recurrence_residual"] = float(np.max(np.abs(v[1:] - predicted_v))) / scale["velocity"]
    analytic = analytic_values(request, trace["time_s"], n)
    metrics["analytic_error"] = max(float(np.max(np.abs(x - analytic["unwrapped_position_m"]))) / scale["position"],
                                    float(np.max(np.abs(v - analytic["velocity_m_per_s"]))) / scale["velocity"],
                                    float(np.max(np.abs(density - analytic["density_kg_per_m3"]))) / scale["density"])
    return metrics


def _coefficient_difference(request, left, right, stride):
    scales, length = _scales(request), request["model"]["length_m"]
    difference = 0.0
    for field, scale in (("unwrapped_position_m", scales["position"]), ("velocity_m_per_s", scales["velocity"])):
        def coeff(trace):
            n = trace["particles"]
            array = np.asarray(trace[field])
            if field == "unwrapped_position_m":
                array = array - ((np.arange(n) + 0.5) * length / n)[None, :]
            return np.fft.rfft(array, axis=1)[:, :3] / n * np.exp(-1j * np.pi * np.arange(3) / n)[None, :]
        delta = coeff(left) - coeff(right)[::stride]
        bound = np.abs(delta[:, 0]) + 2.0 * np.sum(np.abs(delta[:, 1:]), axis=1)
        difference = max(difference, float(np.max(bound)) / scale)
    return difference


def _convergence(request, first, second, third, stride):
    coarse, fine = _coefficient_difference(request, first, second, stride), _coefficient_difference(request, second, third, stride)
    order = math.log2(coarse / fine) if coarse > 1e-9 and fine > 1e-10 else 0.0
    return {"coarse_difference": coarse, "fine_difference": fine, "order": order, "order_deficit": max(0.0, 1.8 - order)}


def _gradient_error(request, trace):
    """Five-point finite differences of independently evaluated Hamiltonian."""
    model, scale = request["model"], _scales(request)
    mass, h, n = trace["parcel_mass_kg"], trace["smoothing_length_m"], trace["particles"]
    step = model["length_m"] / n * 1e-3
    acceleration_scale = model["sound_speed_m_per_s"] ** 2 * model["strain_amplitude"] * 2 * math.pi / model["length_m"]
    error = 0.0
    for index in (0, trace["steps"] // 2, trace["steps"]):
        x, v = np.asarray(trace["unwrapped_position_m"][index]), np.asarray(trace["velocity_m_per_s"][index])
        expected = quantities(model, x, v, mass, h)[2]
        for particle in range(n):
            energies = []
            for offset in (-2.0, -1.0, 1.0, 2.0):
                perturbed = x.copy()
                perturbed[particle] += offset * step
                energies.append(quantities(model, perturbed, v, mass, h)[3])
            derivative = (energies[0] - 8 * energies[1] + 8 * energies[2] - energies[3]) / (12 * step)
            error = max(error, abs(expected[particle] + derivative / mass) / acceleration_scale)
    return float(error)


def _spec(request):
    tol = request["tolerances"]
    spec = {}
    for label in LABELS:
        for field in TRACE_METRICS:
            limit = {"momentum_drift": tol["momentum_relative"], "energy_drift": tol["energy_relative"],
                     "analytic_error": tol["analytic_normalized"], "maximum_mach": 0.002,
                     "maximum_density_deviation": 0.002, "maximum_gap_deviation": 0.01}.get(field, 1e-8)
            spec[label + "." + field] = limit
    spec.update(reference_error=request["tolerances"]["reference_normalized"], reference_refinement=1e-7,
                hamiltonian_gradient=request["tolerances"]["gradient_relative"])
    for name, key in (("time_convergence", "time_refinement_normalized"), ("spatial_convergence", "spatial_refinement_normalized")):
        spec[name + ".coarse_difference"] = tol[key]
        spec[name + ".fine_difference"] = tol[key]
        spec[name + ".order_deficit"] = 0.0
    return spec


def _values(metrics):
    return {**{label + "." + name: value for label, trace in metrics["traces"].items() for name, value in trace.items()},
            **{name: metrics[name] for name in ("reference_error", "reference_refinement", "hamiltonian_gradient")},
            **{name + "." + field: metrics[name][field] for name in ("time_convergence", "spatial_convergence")
               for field in ("coarse_difference", "fine_difference", "order_deficit")}}


def _qualification(request, passed):
    desired = set(request["desired_observables"])
    expansion, refused = sorted(desired & EXPANSION_OBSERVABLES), sorted(desired & REFUSED_OBSERVABLES)
    return {"action": "REFUSE" if not passed or refused else "EXPAND" if expansion else "LOCAL",
            "supported_observables": sorted(desired & SUPPORTED_OBSERVABLES),
            "unsupported_observables": expansion + refused,
            "reason": "Bounded synthetic SPH numerical qualification only; additional physics or empirical claims need separate qualified evidence."}


def verify(request, result):
    request, result = validate_request(request), validate_result(request, result)
    traces = result["resolutions"]
    primary = traces["primary"]
    oracle = reference(request, primary["time_s"], substeps=32)
    coarse_oracle = reference(request, primary["time_s"], substeps=16)
    scale = _scales(request)
    reference_error, reference_refinement = 0.0, 0.0
    for field, norm in (("unwrapped_position_m", scale["position"]), ("velocity_m_per_s", scale["velocity"])):
        expected = np.asarray(oracle[field])
        reference_error = max(reference_error, float(np.max(np.abs(np.asarray(primary[field]) - expected))) / norm)
        reference_refinement = max(reference_refinement, float(np.max(np.abs(np.asarray(coarse_oracle[field]) - expected))) / norm)
    metrics = {"traces": {label: _metrics(request, traces[label]) for label in LABELS},
               "time_convergence": _convergence(request, traces["primary"], traces["time_refined"], traces["time_fine"], 2),
               "spatial_convergence": _convergence(request, traces["time_fine"], traces["spatial_refined"], traces["spatial_fine"], 1),
               "reference_error": reference_error, "reference_refinement": reference_refinement,
               "hamiltonian_gradient": _gradient_error(request, primary)}
    values, spec = _values(metrics), _spec(request)
    checks = [{"name": name, "value": values[name], "tolerance": spec[name],
               "status": "PASS" if values[name] <= spec[name] else "FAIL"} for name in sorted(spec)]
    passed = all(row["status"] == "PASS" for row in checks)
    return seal({"schema": REPORT_SCHEMA, "request_digest": digest(request), "result_digest": result["record_digest"],
                 "claim_scope": CLAIM_SCOPE, "verifier": VERIFIER_ID, "reference_method": REFERENCE_ID,
                 "status": "PASS" if passed else "FAIL", "checks": checks, "metrics": metrics,
                 "qualification": _qualification(request, passed), "limitations": list(LIMITATIONS)})


def validate_report(request, result, report):
    """Data-only checks: never propagate reference, force, gradient or FFT."""
    request, result = validate_request(request), validate_result(request, result)
    json_tree(report)
    keys(report, {"schema", "request_digest", "result_digest", "claim_scope", "verifier", "reference_method", "status",
                  "checks", "metrics", "qualification", "limitations", "record_digest"})
    if (report["schema"] != REPORT_SCHEMA or report["request_digest"] != digest(request)
            or report["result_digest"] != result["record_digest"] or report["claim_scope"] != CLAIM_SCOPE
            or report["verifier"] != VERIFIER_ID or report["reference_method"] != REFERENCE_ID
            or report["status"] not in {"PASS", "FAIL"} or report["limitations"] != LIMITATIONS):
        raise ValueError("SPH report identity or physical declaration differs")
    metrics = report["metrics"]
    keys(metrics, {"traces", "time_convergence", "spatial_convergence", "reference_error", "reference_refinement", "hamiltonian_gradient"})
    keys(metrics["traces"], set(LABELS))
    for trace in metrics["traces"].values():
        keys(trace, TRACE_METRICS)
        if any(number(value) < 0.0 for value in trace.values()):
            raise ValueError("SPH metrics require bounded nonnegative finite errors")
    for name in ("reference_error", "reference_refinement", "hamiltonian_gradient"):
        if number(metrics[name]) < 0.0:
            raise ValueError("SPH reference errors must be nonnegative")
    for name in ("time_convergence", "spatial_convergence"):
        metric = metrics[name]
        keys(metric, CONVERGENCE_METRICS)
        for field, value in metric.items():
            if number(value) < 0.0 and field != "order":
                raise ValueError("SPH convergence errors must be nonnegative")
        coarse, fine = metric["coarse_difference"], metric["fine_difference"]
        order = math.log2(coarse / fine) if coarse > 1e-9 and fine > 1e-10 else 0.0
        if metric["order"] != order or metric["order_deficit"] != max(0.0, 1.8 - order):
            raise ValueError("SPH retained order differs from its retained refinement metrics")
    spec, values = _spec(request), _values(metrics)
    if type(report["checks"]) is not list or len(report["checks"]) != len(spec):
        raise ValueError("SPH report must retain each exact numerical check")
    names = []
    for row in report["checks"]:
        keys(row, {"name", "value", "tolerance", "status"})
        name = row["name"]
        if (type(name) is not str or name not in spec or number(row["value"]) != values[name]
                or number(row["tolerance"]) != spec[name]
                or row["status"] != ("PASS" if values[name] <= spec[name] else "FAIL")):
            raise ValueError("SPH check contradicts its retained metric or fixed threshold")
        names.append(name)
    if len(set(names)) != len(names) or set(names) != set(spec):
        raise ValueError("SPH numerical check duplicated or missing")
    passed = all(row["status"] == "PASS" for row in report["checks"])
    if report["status"] != ("PASS" if passed else "FAIL") or report["qualification"] != _qualification(request, passed):
        raise ValueError("SPH retained qualification contradicts numerical checks")
    check_seal(report)
    return deepcopy(report)
