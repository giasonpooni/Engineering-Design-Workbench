"""Independent numerical audit, consuming samples rather than provider summaries.

This verifier never imports or calls the integrator. It recomputes physical
observables from bounded traces and closed-form values. PASS qualifies only the
declared numerical model; qualification is a recommendation, not admission.
"""
from __future__ import annotations

import math

from .control_contracts import keys, number, json_tree, text
from .impact_contract import (CLAIM_SCOPE, EXPANSION_OBSERVABLES,
                              REPORT_SCHEMA, validate_request, validate_result)
from .impact_reference import reference, reference_values
from .operations.runner import check_seal, digest, seal

LIMITATIONS = [
    "Numerical verification of one undamped point-mass and massless-spring model only.",
    "No plate, constitutive, damage, molecular, scale-preservation or experimental qualification.",
    "The effective spring stiffness is N/m and is not a material modulus or hardness.",
    "Qualification recommendations do not perform canonical state admission.",
]


def _check(checks, name, value, tolerance, **context):
    passed = math.isfinite(value) and value <= tolerance
    checks.append({"name": name, "status": "PASS" if passed else "FAIL",
                   "value": value, "tolerance": tolerance, **context})


def _metrics(request, trace, ref, label, checks):
    model = request["model"]
    mass, stiffness, speed = (model["mass_kg"], model["stiffness_n_per_m"],
                              model["initial_speed_m_per_s"])
    times, x, v, f = (trace[name] for name in
                      ("time_s", "compression_m", "velocity_m_per_s", "force_n"))
    dt = trace["dt_s"]
    xscale, fscale = ref["maximum_compression_m"], ref["peak_force_n"]
    jscale, escale = ref["support_impulse_n_s"], ref["initial_energy_j"]
    if times[0] != 0 or x[0] != 0 or v[0] != speed or f[0] != 0:
        raise ValueError("Trace changed the declared initial contact state")
    expected = reference_values(request, times)
    errors = {"compression_m": max(abs(a - b) for a, b in zip(x, expected["compression_m"])) / xscale,
              "velocity_m_per_s": max(abs(a - b) for a, b in zip(v, expected["velocity_m_per_s"])) / speed,
              "force_n": max(abs(a - b) for a, b in zip(f, expected["force_n"])) / fscale}
    law_error = max(abs(force - stiffness * max(compression, 0.0))
                    for compression, force in zip(x, f)) / fscale
    _check(checks, label + ".force_law", law_error, 1e-12,
           normalization="analytical_peak_force_n")
    # Independent per-step equations establish that a freshly resealed analytic
    # or otherwise fabricated path is not evidence of a Verlet execution.
    position_residual, velocity_residual = 0.0, 0.0
    impulse, momentum_error, energy_drift = 0.0, 0.0, 0.0
    energies = []
    for index, (compression, velocity) in enumerate(zip(x, v)):
        energy = 0.5 * mass * velocity * velocity + 0.5 * stiffness * max(compression, 0.0) ** 2
        energies.append(energy)
        energy_drift = max(energy_drift, abs(energy - escale) / escale)
        if index:
            impulse += 0.5 * (f[index - 1] + f[index]) * dt
            momentum_error = max(momentum_error, abs(mass * (speed - velocity) - impulse) / jscale)
            predicted_x = x[index - 1] + v[index - 1] * dt - 0.5 * f[index - 1] / mass * dt * dt
            predicted_v = v[index - 1] - 0.5 * (f[index - 1] + f[index]) / mass * dt
            position_residual = max(position_residual, abs(compression - predicted_x) / xscale)
            velocity_residual = max(velocity_residual, abs(velocity - predicted_v) / speed)
    _check(checks, label + ".integrator_equations", max(position_residual, velocity_residual), 1e-12,
           normalization="analytical_compression_amplitude_and_initial_speed")
    _check(checks, label + ".compression_only_force", max(0.0, -min(f)) / fscale, 0.0)
    tolerances = request["tolerances"]
    for quantity, error in errors.items():
        _check(checks, label + ".analytic." + quantity, error, tolerances["analytic_normalized"],
               normalization={"compression_m": "analytical_compression_amplitude_m",
                              "velocity_m_per_s": "initial_speed_m_per_s",
                              "force_n": "analytical_peak_force_n"}[quantity])
    _check(checks, label + ".support_impulse", abs(impulse - jscale) / jscale,
           tolerances["impulse_relative"], normalization="analytical_support_impulse_n_s")
    _check(checks, label + ".all_history_momentum_balance", momentum_error,
           tolerances["momentum_relative"], normalization="analytical_support_impulse_n_s")
    _check(checks, label + ".maximum_energy_drift", energy_drift,
           tolerances["energy_relative"], normalization="initial_energy_j")
    restitution = -v[-1] / speed
    _check(checks, label + ".restitution", abs(restitution - 1.0),
           tolerances["restitution_absolute"])
    crossings = [index for index in range(1, len(x)) if x[index - 1] > 0 and x[index] <= 0]
    separated = len(crossings) == 1
    crossing = crossings[0] if separated else None
    if separated:
        separated = all(x[index] <= 0 and f[index] == 0 and v[index] < 0
                        for index in range(crossing, len(x)))
    _check(checks, label + ".separation_event", 0.0 if separated else 1.0, 0.0,
           criterion="one positive-to-nonpositive compression crossing followed by separating free flight")
    separation_time = None
    if separated:
        separation_time = times[crossing - 1] + dt * x[crossing - 1] / (x[crossing - 1] - x[crossing])
        _check(checks, label + ".separation_time",
               abs(separation_time - ref["contact_duration_s"]) / ref["contact_duration_s"],
               tolerances["separation_relative"],
               normalization="analytical_contact_duration_s", interpolation="linear_crossing_bracket")
    return {"analytic_maximum_normalized_errors": errors,
            "integrated_support_impulse_n_s": impulse,
            "maximum_momentum_balance_relative_error": momentum_error,
            "maximum_energy_relative_drift": energy_drift,
            "initial_energy_j": energies[0], "final_energy_j": energies[-1],
            "restitution": restitution, "separation_time_s": separation_time,
            "separation_bracket_s": None if not separated else [times[crossing - 1], times[crossing]],
            "maximum_compression_m": max(x), "peak_force_n": max(f)}


def verify(request: dict, result: dict) -> dict:
    """Return a sealed PASS/FAIL audit and bounded qualification recommendation."""
    checks, metrics, ref = [], {}, {}
    request_ref, result_ref = None, None
    unsupported = []
    integrity_failure = None
    try:
        request = validate_request(request)
        request_ref = digest(request)
        unsupported = sorted(set(request["desired_observables"]) & EXPANSION_OBSERVABLES)
        validate_result(request, result)
        ref = reference(request)
        result_ref = result["record_digest"]
        _check(checks, "schema_integrity", 0.0, 0.0)
        metrics["primary"] = _metrics(request, result["primary"], ref, "primary", checks)
        metrics["refined"] = _metrics(request, result["refined"], ref, "refined", checks)
        scales = {"compression_m": ref["maximum_compression_m"],
                  "velocity_m_per_s": request["model"]["initial_speed_m_per_s"],
                  "force_n": ref["peak_force_n"]}
        changes = {name: max(abs(a - b) for a, b in
                             zip(result["primary"][name], result["refined"][name][::2])) / scale
                   for name, scale in scales.items()}
        primary, refined = metrics["primary"], metrics["refined"]
        observable_changes = {
            "support_impulse": abs(primary["integrated_support_impulse_n_s"] - refined["integrated_support_impulse_n_s"]) / ref["support_impulse_n_s"],
            "restitution": abs(primary["restitution"] - refined["restitution"]),
            "peak_force": abs(primary["peak_force_n"] - refined["peak_force_n"]) / ref["peak_force_n"],
            "maximum_compression": abs(primary["maximum_compression_m"] - refined["maximum_compression_m"]) / ref["maximum_compression_m"],
        }
        if primary["separation_time_s"] is not None and refined["separation_time_s"] is not None:
            observable_changes["separation_time"] = abs(primary["separation_time_s"] - refined["separation_time_s"]) / ref["contact_duration_s"]
        metrics["refinement"] = {"aligned_state_changes_normalized": changes,
                                  "observable_changes_normalized": observable_changes,
                                  "resolution_factor": 2,
                                  "interpretation": "one timestep refinement comparison; no convergence-order or continuum claim"}
        for name, change in {**changes, **observable_changes}.items():
            _check(checks, "refinement." + name, change,
                   request["tolerances"]["refinement_normalized"])
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        integrity_failure = str(exc) or type(exc).__name__
        checks.append({"name": "schema_integrity", "status": "FAIL", "reason": integrity_failure})
    passed = integrity_failure is None and all(check["status"] == "PASS" for check in checks)
    if not passed:
        action = "REFUSE"
        reasons = ([integrity_failure] if integrity_failure else
                   ["Numerical acceptance failed (" + str(sum(check["status"] == "FAIL" for check in checks))
                    + " checks); see the failed check records."])
    elif unsupported:
        action = "EXPAND"
        reasons = ["The numerical spring benchmark passed; requested observables need additional qualified models or evidence: " + ", ".join(unsupported)]
    else:
        action = "LOCAL"
        reasons = ["All declared numerical checks passed for the exact spring/contact scope."]
    return seal({"schema": REPORT_SCHEMA, "request_digest": request_ref,
                 "result_digest": result_ref, "claim_scope": CLAIM_SCOPE,
                 "status": "PASS" if passed else "FAIL",
                 "qualification": {"action": action, "reasons": reasons,
                                   "unsupported_observables": unsupported},
                 "checks": checks, "reference": ref, "metrics": metrics,
                 "limitations": list(LIMITATIONS)})


def validate_report(request: dict, result: dict, report: dict) -> None:
    """Validate a retained audit without calling the solver or verification run.

    A seal identifies content; it does not authenticate a producer. The caller
    must retain the separate verification occurrence and may explicitly rerun
    the independent audit to reproduce the scientific check values.
    """
    request = validate_request(request)
    validate_result(request, result)
    json_tree(report)
    keys(report, {"schema", "request_digest", "result_digest", "claim_scope", "status",
                  "qualification", "checks", "reference", "metrics", "limitations", "record_digest"})
    if (report["schema"] != REPORT_SCHEMA or report["request_digest"] != digest(request)
            or report["result_digest"] != result["record_digest"] or report["claim_scope"] != CLAIM_SCOPE
            or report["limitations"] != LIMITATIONS or report["status"] not in {"PASS", "FAIL"}):
        raise ValueError("Stored impact report identity, scope or limitations differ")
    # Algebraic scale binding is read-only declaration checking, not a replay.
    expected_reference = reference(request)
    keys(report["reference"], set(expected_reference))
    for value in report["reference"].values():
        number(value)
    if report["reference"] != expected_reference:
        raise ValueError("Stored report reference scales differ from the request")
    metrics = report["metrics"]
    keys(metrics, {"primary", "refined", "refinement"})
    metric_names = {"analytic_maximum_normalized_errors", "integrated_support_impulse_n_s",
                    "maximum_momentum_balance_relative_error", "maximum_energy_relative_drift",
                    "initial_energy_j", "final_energy_j", "restitution", "separation_time_s",
                    "separation_bracket_s", "maximum_compression_m", "peak_force_n"}
    for label in ("primary", "refined"):
        values = metrics[label]
        keys(values, metric_names)
        keys(values["analytic_maximum_normalized_errors"], {"compression_m", "velocity_m_per_s", "force_n"})
        for value in values["analytic_maximum_normalized_errors"].values():
            if number(value) < 0:
                raise ValueError("Numerical errors must be nonnegative")
        for name in metric_names - {"analytic_maximum_normalized_errors", "separation_time_s", "separation_bracket_s"}:
            number(values[name])
        for name in ("initial_energy_j", "final_energy_j", "maximum_compression_m", "peak_force_n"):
            if values[name] < 0:
                raise ValueError("Energy, maximum compression and peak force cannot be negative")
        if values["initial_energy_j"] != expected_reference["initial_energy_j"]:
            raise ValueError("Stored initial energy differs from the declared contact state")
        trace = result[label]
        if (values["maximum_compression_m"] != max(trace["compression_m"])
                or values["peak_force_n"] != max(trace["force_n"])):
            raise ValueError("Stored extrema differ from retained samples")
        crossing = values["separation_time_s"]
        bracket = values["separation_bracket_s"]
        if crossing is None:
            if bracket is not None:
                raise ValueError("Absent separation cannot retain a crossing bracket")
        else:
            crossing = number(crossing)
            if type(bracket) is not list or len(bracket) != 2:
                raise ValueError("Separation requires a two-time bracket")
            lower, upper = (number(value) for value in bracket)
            if not 0 <= lower <= crossing <= upper or lower >= upper:
                raise ValueError("Separation time is outside its retained bracket")
    refinement = metrics["refinement"]
    keys(refinement, {"aligned_state_changes_normalized", "observable_changes_normalized", "resolution_factor", "interpretation"})
    keys(refinement["aligned_state_changes_normalized"], {"compression_m", "velocity_m_per_s", "force_n"})
    observable_names = {"support_impulse", "restitution", "peak_force", "maximum_compression"}
    if all(metrics[label]["separation_time_s"] is not None for label in ("primary", "refined")):
        observable_names.add("separation_time")
    keys(refinement["observable_changes_normalized"], observable_names)
    if (type(refinement["resolution_factor"]) is not int or refinement["resolution_factor"] != 2
            or refinement["interpretation"] != "one timestep refinement comparison; no convergence-order or continuum claim"):
        raise ValueError("Stored refinement interpretation differs")
    for values in (refinement["aligned_state_changes_normalized"], refinement["observable_changes_normalized"]):
        if any(number(value) < 0 for value in values.values()):
            raise ValueError("Refinement changes must be nonnegative")
    checks = report["checks"]
    if type(checks) is not list or not 1 <= len(checks) <= 64:
        raise ValueError("Require a bounded nonempty audit check list")
    expected = {"schema_integrity": (0.0, {})}
    tolerances = request["tolerances"]
    for label in ("primary", "refined"):
        expected.update({
            label + ".force_law": (1e-12, {"normalization": "analytical_peak_force_n"}),
            label + ".integrator_equations": (1e-12, {"normalization": "analytical_compression_amplitude_and_initial_speed"}),
            label + ".compression_only_force": (0.0, {}),
            label + ".support_impulse": (tolerances["impulse_relative"], {"normalization": "analytical_support_impulse_n_s"}),
            label + ".all_history_momentum_balance": (tolerances["momentum_relative"], {"normalization": "analytical_support_impulse_n_s"}),
            label + ".maximum_energy_drift": (tolerances["energy_relative"], {"normalization": "initial_energy_j"}),
            label + ".restitution": (tolerances["restitution_absolute"], {}),
            label + ".separation_event": (0.0, {"criterion": "one positive-to-nonpositive compression crossing followed by separating free flight"}),
        })
        for quantity, scale in (("compression_m", "analytical_compression_amplitude_m"),
                                ("velocity_m_per_s", "initial_speed_m_per_s"),
                                ("force_n", "analytical_peak_force_n")):
            expected[label + ".analytic." + quantity] = (tolerances["analytic_normalized"], {"normalization": scale})
        if metrics[label]["separation_time_s"] is not None:
            expected[label + ".separation_time"] = (tolerances["separation_relative"],
                                                      {"normalization": "analytical_contact_duration_s", "interpolation": "linear_crossing_bracket"})
    for quantity in set(refinement["aligned_state_changes_normalized"]) | observable_names:
        expected["refinement." + quantity] = (tolerances["refinement_normalized"], {})
    names = []
    indexed = {}
    for check in checks:
        if type(check) is not dict or type(check.get("name")) is not str or check["name"] not in expected:
            raise ValueError("Unknown stored numerical check")
        name = check["name"]
        tolerance, context = expected[name]
        keys(check, {"name", "status", "value", "tolerance"} | set(context))
        value = number(check["value"])
        if value < 0 or number(check["tolerance"]) != tolerance or any(check[key] != wanted for key, wanted in context.items()):
            raise ValueError("Stored numerical check threshold or declaration differs")
        if check["status"] != ("PASS" if value <= tolerance else "FAIL"):
            raise ValueError("Stored numerical check status contradicts its metric")
        indexed[name] = check
        names.append(name)
    if len(set(names)) != len(names) or set(names) != set(expected):
        raise ValueError("Stored report is missing or duplicates declared checks")
    # Cross-bind reported measurements and check values, without recomputing a
    # trace, so changing a headline or metric alone cannot preserve validity.
    ref = report["reference"]
    for label in ("primary", "refined"):
        values = metrics[label]
        bindings = {label + ".analytic." + quantity: value
                    for quantity, value in values["analytic_maximum_normalized_errors"].items()}
        bindings.update({
            label + ".support_impulse": abs(values["integrated_support_impulse_n_s"] - ref["support_impulse_n_s"]) / ref["support_impulse_n_s"],
            label + ".all_history_momentum_balance": values["maximum_momentum_balance_relative_error"],
            label + ".maximum_energy_drift": values["maximum_energy_relative_drift"],
            label + ".restitution": abs(values["restitution"] - 1.0),
            label + ".separation_event": 1.0 if values["separation_time_s"] is None else 0.0,
        })
        if values["separation_time_s"] is not None:
            bindings[label + ".separation_time"] = abs(values["separation_time_s"] - ref["contact_duration_s"]) / ref["contact_duration_s"]
        for name, value in bindings.items():
            if indexed[name]["value"] != value:
                raise ValueError("Stored numerical checks differ from retained measurements")
    for values in (refinement["aligned_state_changes_normalized"], refinement["observable_changes_normalized"]):
        for name, value in values.items():
            if indexed["refinement." + name]["value"] != value:
                raise ValueError("Stored refinement checks differ from retained measurements")
    passed = all(check["status"] == "PASS" for check in checks)
    if report["status"] != ("PASS" if passed else "FAIL"):
        raise ValueError("Stored report status contradicts its checks")
    unsupported = sorted(set(request["desired_observables"]) & EXPANSION_OBSERVABLES)
    qualification = report["qualification"]
    keys(qualification, {"action", "reasons", "unsupported_observables"})
    action = "REFUSE" if not passed else "EXPAND" if unsupported else "LOCAL"
    if qualification["action"] != action or qualification["unsupported_observables"] != unsupported:
        raise ValueError("Stored qualification contradicts numerical checks or requested observables")
    if type(qualification["reasons"]) is not list or not 1 <= len(qualification["reasons"]) <= 16:
        raise ValueError("Stored qualification requires bounded reasons")
    for reason in qualification["reasons"]:
        text(reason)
    if not passed:
        expected_reasons = ["Numerical acceptance failed (" + str(sum(check["status"] == "FAIL" for check in checks))
                            + " checks); see the failed check records."]
    elif unsupported:
        expected_reasons = ["The numerical spring benchmark passed; requested observables need additional qualified models or evidence: " + ", ".join(unsupported)]
    else:
        expected_reasons = ["All declared numerical checks passed for the exact spring/contact scope."]
    if qualification["reasons"] != expected_reasons:
        raise ValueError("Stored qualification reasons differ from the checks and requested observables")
    check_seal(report)
