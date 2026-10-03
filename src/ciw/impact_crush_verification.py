"""Independent all-history audit of ideal plastic crush-contact traces.

The verifier never imports the integrator. Qualification is bounded numerical
acceptance, not material identification, experimental validation or admission.
"""
from __future__ import annotations

import math

from .control_contracts import json_tree, keys, number
from .impact_crush_contract import (CLAIM_SCOPE, EXPANSION_OBSERVABLES, REPORT_SCHEMA,
                                    STATE_FIELDS, validate_request, validate_result)
from .impact_crush_reference import reference, reference_values
from .operations.runner import check_seal, digest, seal

LIMITATIONS = [
    "Numerical verification of one unilateral elastic-perfectly-plastic point-mass crush model only.",
    "Plastic work is ideal slider dissipation, not measured polymer absorption, fracture energy or thermal prediction.",
    "No plate, rate-dependent, thermal, damage, molecular, scale-preservation or experimental qualification.",
    "Effective spring stiffness and yield force are N/m and N, not material modulus, strength or hardness.",
    "Qualification recommendations do not perform canonical state admission.",
]
RESIDUAL_FIELDS = {"force_law", "force_cap", "compression_only_force", "plastic_nonnegative",
                   "plastic_monotonic", "return_mapping", "plastic_work_algebra", "integrator_equations"}
METRIC_FIELDS = {"analytic_maximum_normalized_errors", "numerical_residuals",
                 "integrated_support_impulse_n_s", "maximum_momentum_balance_relative_error",
                 "maximum_energy_relative_drift", "initial_energy_j", "final_energy_j",
                 "rebound_energy_j", "restitution", "separation_time_s", "separation_bracket_s",
                 "maximum_compression_m", "peak_force_n", "residual_compression_m", "plastic_work_j",
                 "yield_branch_error"}
REFINEMENT_INTERPRETATION = "one timestep refinement comparison; no convergence-order or continuum claim"


def _scales(request, ref):
    return {"compression_m": ref["maximum_compression_m"],
            "velocity_m_per_s": request["model"]["initial_speed_m_per_s"],
            "force_n": ref["peak_force_n"], "plastic_compression_m": ref["maximum_compression_m"],
            "plastic_work_j": ref["initial_energy_j"]}


def _check_spec(request, metrics):
    """Exact check vocabulary/thresholds shared with static declaration validation."""
    tol = request["tolerances"]
    spec = {"schema_integrity": 0.0}
    for label in ("primary", "refined"):
        for name in RESIDUAL_FIELDS:
            spec[label + "." + name] = (0.0 if name in {"force_cap", "compression_only_force",
                "plastic_nonnegative", "plastic_monotonic"} else 1e-12)
        spec.update({label + ".analytic." + field: tol["analytic_normalized"] for field in STATE_FIELDS})
        spec.update({label + ".support_impulse": tol["impulse_relative"],
                     label + ".all_history_momentum_balance": tol["momentum_relative"],
                     label + ".maximum_energy_drift": tol["energy_relative"],
                     label + ".restitution": tol["restitution_absolute"],
                     label + ".plastic_work": tol["analytic_normalized"],
                     label + ".residual_compression": tol["analytic_normalized"],
                     label + ".rebound_energy_loss": tol["energy_relative"],
                     label + ".yield_branch": tol["analytic_normalized"],
                     label + ".separation_event": 0.0})
        if metrics[label]["separation_time_s"] is not None:
            spec[label + ".separation_time"] = tol["separation_relative"]
    for field in set(metrics["refinement"]["aligned_state_changes_normalized"]) | set(metrics["refinement"]["observable_changes_normalized"]):
        spec["refinement." + field] = tol["refinement_normalized"]
    return spec


def _check_values(metrics, ref):
    values = {"schema_integrity": 0.0}
    for label in ("primary", "refined"):
        observed = metrics[label]
        values.update({label + "." + name: value for name, value in observed["numerical_residuals"].items()})
        values.update({label + ".analytic." + name: value for name, value in observed["analytic_maximum_normalized_errors"].items()})
        values.update({
            label + ".support_impulse": abs(observed["integrated_support_impulse_n_s"] - ref["support_impulse_n_s"]) / ref["support_impulse_n_s"],
            label + ".all_history_momentum_balance": observed["maximum_momentum_balance_relative_error"],
            label + ".maximum_energy_drift": observed["maximum_energy_relative_drift"],
            label + ".restitution": abs(observed["restitution"] - ref["restitution"]),
            label + ".plastic_work": abs(observed["plastic_work_j"] - ref["plastic_work_j"]) / ref["initial_energy_j"],
            label + ".residual_compression": abs(observed["residual_compression_m"] - ref["residual_compression_m"]) / ref["maximum_compression_m"],
            label + ".rebound_energy_loss": abs(ref["initial_energy_j"] - observed["rebound_energy_j"] - observed["plastic_work_j"]) / ref["initial_energy_j"],
            label + ".yield_branch": observed["yield_branch_error"],
            label + ".separation_event": 1.0 if observed["separation_time_s"] is None else 0.0})
        if observed["separation_time_s"] is not None:
            values[label + ".separation_time"] = abs(observed["separation_time_s"] - ref["contact_duration_s"]) / ref["contact_duration_s"]
    for changes in (metrics["refinement"]["aligned_state_changes_normalized"], metrics["refinement"]["observable_changes_normalized"]):
        values.update({"refinement." + name: value for name, value in changes.items()})
    return values


def _metrics(request, trace, ref):
    model = request["model"]
    mass, stiffness, speed, limit = (model[name] for name in
        ("mass_kg", "stiffness_n_per_m", "initial_speed_m_per_s", "yield_force_n"))
    times, q, v, f, p, work = (trace[name] for name in ("time_s",) + STATE_FIELDS)
    dt = trace["dt_s"]
    scales = _scales(request, ref)
    qscale, fscale, escale, jscale = (ref[name] for name in
        ("maximum_compression_m", "peak_force_n", "initial_energy_j", "support_impulse_n_s"))
    expected = reference_values(request, times)
    errors = {name: max(abs(a - b) for a, b in zip(trace[name], expected[name])) / scale
              for name, scale in scales.items()}
    law_error = max(abs(force - min(limit, stiffness * max(position - plastic, 0.0)))
                    for position, plastic, force in zip(q, p, f)) / fscale
    residuals = {"force_law": law_error,
                 "force_cap": max(0.0, max(f) - limit) / fscale,
                 "compression_only_force": max(0.0, -min(f)) / fscale,
                 "plastic_nonnegative": max(0.0, -min(p)) / qscale,
                 "plastic_monotonic": max(0.0, max(a - b for a, b in zip(p, p[1:]))) / qscale,
                 "return_mapping": 0.0,
                 "plastic_work_algebra": max(abs(d - limit * plastic) for d, plastic in zip(work, p)) / escale,
                 "integrator_equations": 0.0}
    impulse, momentum_error, energy_drift = 0.0, 0.0, 0.0
    energies = []
    for index, (position, velocity, plastic, dissipation) in enumerate(zip(q, v, p, work)):
        energy = 0.5 * mass * velocity * velocity + 0.5 * stiffness * max(position - plastic, 0.0) ** 2 + dissipation
        energies.append(energy)
        energy_drift = max(energy_drift, abs(energy - escale) / escale)
        if index:
            impulse += 0.5 * (f[index - 1] + f[index]) * dt
            momentum_error = max(momentum_error, abs(mass * (speed - velocity) - impulse) / jscale)
            predicted_q = q[index - 1] + v[index - 1] * dt - 0.5 * f[index - 1] / mass * dt * dt
            predicted_v = v[index - 1] - 0.5 * (f[index - 1] + f[index]) / mass * dt
            predicted_p = max(p[index - 1], position - limit / stiffness)
            residuals["integrator_equations"] = max(residuals["integrator_equations"],
                abs(position - predicted_q) / qscale, abs(velocity - predicted_v) / speed)
            residuals["return_mapping"] = max(residuals["return_mapping"], abs(plastic - predicted_p) / qscale)
    gaps = [position - plastic for position, plastic in zip(q, p)]
    crossings = [i for i in range(1, len(gaps)) if gaps[i - 1] > 0 and gaps[i] <= 0]
    crossing = crossings[0] if len(crossings) == 1 else None
    separated = crossing is not None and all(gaps[i] <= 0 and f[i] == 0 and v[i] < 0
        and p[i] == p[crossing] and work[i] == work[crossing] for i in range(crossing, len(gaps)))
    separation_time, bracket = None, None
    if separated:
        separation_time = times[crossing - 1] + dt * gaps[crossing - 1] / (gaps[crossing - 1] - gaps[crossing])
        bracket = [times[crossing - 1], times[crossing]]
    branch_error = max(p) / qscale if ref["branch"] == "elastic" else (0.0 if max(p) > 0.0 else 1.0)
    return {"analytic_maximum_normalized_errors": errors, "numerical_residuals": residuals,
            "integrated_support_impulse_n_s": impulse,
            "maximum_momentum_balance_relative_error": momentum_error,
            "maximum_energy_relative_drift": energy_drift,
            "initial_energy_j": energies[0], "final_energy_j": energies[-1],
            "rebound_energy_j": 0.5 * mass * v[-1] * v[-1], "restitution": -v[-1] / speed,
            "separation_time_s": separation_time, "separation_bracket_s": bracket,
            "maximum_compression_m": max(q), "peak_force_n": max(f),
            "residual_compression_m": p[-1], "plastic_work_j": work[-1], "yield_branch_error": branch_error}


def _observable_changes(metrics, ref):
    primary, refined = metrics["primary"], metrics["refined"]
    mapping = {"support_impulse": ("integrated_support_impulse_n_s", ref["support_impulse_n_s"]),
               "restitution": ("restitution", 1.0), "peak_force": ("peak_force_n", ref["peak_force_n"]),
               "maximum_compression": ("maximum_compression_m", ref["maximum_compression_m"]),
               "residual_compression": ("residual_compression_m", ref["maximum_compression_m"]),
               "plastic_work": ("plastic_work_j", ref["initial_energy_j"])}
    changes = {name: abs(primary[field] - refined[field]) / scale for name, (field, scale) in mapping.items()}
    if all(metrics[label]["separation_time_s"] is not None for label in ("primary", "refined")):
        changes["separation_time"] = abs(primary["separation_time_s"] - refined["separation_time_s"]) / ref["contact_duration_s"]
    return changes


def _qualification(passed, unsupported, checks, integrity_failure=None):
    if not passed:
        return {"action": "REFUSE", "reasons": [integrity_failure] if integrity_failure else
                ["Numerical acceptance failed (" + str(sum(check["status"] == "FAIL" for check in checks))
                 + " checks); see the failed check records."], "unsupported_observables": unsupported}
    if unsupported:
        return {"action": "EXPAND", "reasons": ["The numerical crush benchmark passed; requested observables need additional qualified models or evidence: "
                + ", ".join(unsupported)], "unsupported_observables": unsupported}
    return {"action": "LOCAL", "reasons": ["All declared numerical checks passed for the exact crush/contact scope."],
            "unsupported_observables": []}


def verify(request: dict, result: dict) -> dict:
    """Recompute complete trajectories, balances and model/grid checks independently."""
    checks, metrics, ref, unsupported = [], {}, {}, []
    request_ref, result_ref, integrity_failure = None, None, None
    try:
        request = validate_request(request)
        request_ref = digest(request)
        unsupported = sorted(set(request["desired_observables"]) & EXPANSION_OBSERVABLES)
        validate_result(request, result)
        ref, result_ref = reference(request), result["record_digest"]
        for label in ("primary", "refined"):
            metrics[label] = _metrics(request, result[label], ref)
        changes = {name: max(abs(a - b) for a, b in zip(result["primary"][name], result["refined"][name][::2])) / scale
                   for name, scale in _scales(request, ref).items()}
        metrics["refinement"] = {"aligned_state_changes_normalized": changes,
                                 "observable_changes_normalized": _observable_changes(metrics, ref),
                                 "resolution_factor": 2, "interpretation": REFINEMENT_INTERPRETATION}
        values, spec = _check_values(metrics, ref), _check_spec(request, metrics)
        checks = [{"name": name, "status": "PASS" if math.isfinite(values[name]) and values[name] <= tolerance else "FAIL",
                   "value": values[name], "tolerance": tolerance} for name, tolerance in sorted(spec.items())]
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        integrity_failure = str(exc) or type(exc).__name__
        checks = [{"name": "schema_integrity", "status": "FAIL", "reason": integrity_failure}]
    passed = integrity_failure is None and all(check["status"] == "PASS" for check in checks)
    return seal({"schema": REPORT_SCHEMA, "request_digest": request_ref, "result_digest": result_ref,
                 "claim_scope": CLAIM_SCOPE, "status": "PASS" if passed else "FAIL",
                 "qualification": _qualification(passed, unsupported, checks, integrity_failure),
                 "checks": checks, "reference": ref, "metrics": metrics, "limitations": list(LIMITATIONS)})


def validate_report(request: dict, result: dict, report: dict) -> None:
    """Validate retained declarations and bindings; never replay a solver or audit.

    Content seals are not producer authentication. Full scientific reproduction
    uses verify as a separate verification occurrence.
    """
    request = validate_request(request)
    validate_result(request, result)
    json_tree(report)
    keys(report, {"schema", "request_digest", "result_digest", "claim_scope", "status", "qualification",
                  "checks", "reference", "metrics", "limitations", "record_digest"})
    if (report["schema"] != REPORT_SCHEMA or report["request_digest"] != digest(request)
            or report["result_digest"] != result["record_digest"] or report["claim_scope"] != CLAIM_SCOPE
            or report["limitations"] != LIMITATIONS or report["status"] not in {"PASS", "FAIL"}):
        raise ValueError("Stored crush report identity, scope or limitations differ")
    ref = reference(request)
    keys(report["reference"], set(ref))
    for name, value in report["reference"].items():
        if name == "branch":
            if type(value) is not str:
                raise ValueError("Stored reference branch must be exact text")
        elif name == "yield_time_s" and value is None:
            continue
        else:
            number(value)
    if report["reference"] != ref:
        raise ValueError("Stored report reference scales differ from the request")
    metrics = report["metrics"]
    keys(metrics, {"primary", "refined", "refinement"})
    model = request["model"]
    for label in ("primary", "refined"):
        observed, trace = metrics[label], result[label]
        keys(observed, METRIC_FIELDS)
        keys(observed["analytic_maximum_normalized_errors"], set(STATE_FIELDS))
        keys(observed["numerical_residuals"], RESIDUAL_FIELDS)
        for values in (observed["analytic_maximum_normalized_errors"], observed["numerical_residuals"]):
            if any(number(value) < 0 for value in values.values()):
                raise ValueError("Stored numerical errors must be nonnegative")
        for name in METRIC_FIELDS - {"analytic_maximum_normalized_errors", "numerical_residuals", "separation_time_s", "separation_bracket_s"}:
            number(observed[name])
        # Signed counterfeit terminal work, residual compression or restitution
        # remain retainable as failed audits. Errors and quadratic energy cannot
        # legitimately be negative, even in a numerically rejected candidate.
        for name in ("maximum_momentum_balance_relative_error", "maximum_energy_relative_drift",
                     "initial_energy_j", "rebound_energy_j", "maximum_compression_m", "peak_force_n", "yield_branch_error"):
            if observed[name] < 0:
                raise ValueError("Stored energies, observables and errors must be nonnegative")
        q, velocity, plastic, work = (trace[field][-1] for field in
            ("compression_m", "velocity_m_per_s", "plastic_compression_m", "plastic_work_j"))
        terminal_bindings = {"initial_energy_j": ref["initial_energy_j"], "maximum_compression_m": max(trace["compression_m"]),
            "peak_force_n": max(trace["force_n"]), "residual_compression_m": plastic, "plastic_work_j": work,
            "restitution": -velocity / model["initial_speed_m_per_s"],
            "rebound_energy_j": 0.5 * model["mass_kg"] * velocity * velocity,
            "final_energy_j": 0.5 * model["mass_kg"] * velocity * velocity
                + 0.5 * model["stiffness_n_per_m"] * max(q - plastic, 0.0) ** 2 + work,
            "yield_branch_error": max(trace["plastic_compression_m"]) / ref["maximum_compression_m"]
                if ref["branch"] == "elastic" else (0.0 if max(trace["plastic_compression_m"]) > 0 else 1.0)}
        if any(observed[name] != value for name, value in terminal_bindings.items()):
            raise ValueError("Stored measurements differ from retained terminal state or extrema")
        crossing, bracket = observed["separation_time_s"], observed["separation_bracket_s"]
        if crossing is None:
            if bracket is not None:
                raise ValueError("Absent separation cannot retain a crossing bracket")
        else:
            if type(bracket) is not list or len(bracket) != 2:
                raise ValueError("Separation requires a two-time bracket")
            lower, upper = (number(value) for value in bracket)
            if not 0 <= lower <= number(crossing) <= upper or lower >= upper:
                raise ValueError("Separation time is outside its retained bracket")
            indices = [i for i in range(1, len(trace["time_s"])) if trace["time_s"][i - 1] == lower and trace["time_s"][i] == upper]
            if len(indices) != 1:
                raise ValueError("Separation bracket is not an adjacent retained grid pair")
            index = indices[0]
            left = trace["compression_m"][index - 1] - trace["plastic_compression_m"][index - 1]
            right = trace["compression_m"][index] - trace["plastic_compression_m"][index]
            if not left > 0 >= right or crossing != lower + trace["dt_s"] * left / (left - right):
                raise ValueError("Separation interpolation differs from retained elastic gap")
    refinement = metrics["refinement"]
    keys(refinement, {"aligned_state_changes_normalized", "observable_changes_normalized", "resolution_factor", "interpretation"})
    keys(refinement["aligned_state_changes_normalized"], set(STATE_FIELDS))
    expected_changes = _observable_changes(metrics, ref)
    keys(refinement["observable_changes_normalized"], set(expected_changes))
    if (refinement["observable_changes_normalized"] != expected_changes
            or type(refinement["resolution_factor"]) is not int or refinement["resolution_factor"] != 2
            or refinement["interpretation"] != REFINEMENT_INTERPRETATION):
        raise ValueError("Stored refinement declarations or measurements differ")
    for values in (refinement["aligned_state_changes_normalized"], refinement["observable_changes_normalized"]):
        if any(number(value) < 0 for value in values.values()):
            raise ValueError("Refinement changes must be nonnegative")
    checks = report["checks"]
    spec, values = _check_spec(request, metrics), _check_values(metrics, ref)
    if type(checks) is not list or len(checks) != len(spec):
        raise ValueError("Stored report is missing or duplicates declared checks")
    names = []
    for check in checks:
        keys(check, {"name", "status", "value", "tolerance"})
        name = check["name"]
        if type(name) is not str or name not in spec:
            raise ValueError("Unknown stored numerical check")
        if number(check["value"]) != values[name] or number(check["tolerance"]) != spec[name]:
            raise ValueError("Stored numerical checks differ from retained measurements or thresholds")
        if check["status"] != ("PASS" if values[name] <= spec[name] else "FAIL"):
            raise ValueError("Stored numerical check status contradicts its metric")
        names.append(name)
    if len(set(names)) != len(names) or set(names) != set(spec):
        raise ValueError("Stored report is missing or duplicates declared checks")
    passed = all(check["status"] == "PASS" for check in checks)
    unsupported = sorted(set(request["desired_observables"]) & EXPANSION_OBSERVABLES)
    if report["status"] != ("PASS" if passed else "FAIL"):
        raise ValueError("Stored report status contradicts its checks")
    if report["qualification"] != _qualification(passed, unsupported, checks):
        raise ValueError("Stored qualification contradicts numerical checks or requested observables")
    check_seal(report)
