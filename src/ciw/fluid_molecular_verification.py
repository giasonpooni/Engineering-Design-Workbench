"""Independent finite-trajectory LJ audit with separately propagated references.

Fresh verify evaluates scalar derivatives, force/potential finite differences,
all-history diagnostics and the discrete Verlet equations. Static validation
only checks retained identities, declarations and report arithmetic. Numerical
agreement does not establish chemical fidelity or experimental validation.
"""
from __future__ import annotations

from copy import deepcopy
import math
import numpy as np

from .control_contracts import json_tree, keys, number
from .fluid_molecular_contract import (CLAIM_SCOPE, EXPANSION_OBSERVABLES, MIN_SEPARATION,
    REFUSED_OBSERVABLES, REPORT_SCHEMA, SCALAR_FIELDS, SUPPORTED_OBSERVABLES, TRACE_LABELS,
    validate_request, validate_result)
from .fluid_molecular_reference import REFERENCE_ID, independent_pair_state, reference
from .operations.runner import check_seal, digest, seal

VERIFIER_ID = "ciw.fluid-molecular-independent-verifier.v1"
LIMITATIONS = [
    "Particles are structureless classical atomistic interaction sites, not water molecules, polymer beads, SPH parcels or suspended grains.",
    "The fixed cubic periodic force-shifted 12-6 Lennard-Jones model is a synthetic short-range Hamiltonian; no chemical identity, bonds, electrostatics, thermostat or material calibration is established.",
    "Mass, sigma, epsilon and Boltzmann constant equal one in reduced units; optional SI scale declarations are unvalidated and confer no material fidelity.",
    "Positions are unwrapped three-dimensional coordinates; pair interactions use minimum images and a cutoff strictly below half the box.",
    "Hard trajectory guards require every pair separation >=0.85 sigma and bounded finite velocities/forces independently of user tolerances.",
    "Density is site count per box volume; kinetic temperature removes center-of-mass velocity and uses 3(N-1) degrees of freedom; virial pressure uses that same thermal kinetic energy.",
    "Instantaneous density, kinetic temperature and virial pressure are toy-model reductions; equilibrium, viscosity, conductivity, diffusivity and certified transport parameters are unestablished.",
    "Three Verlet resolutions and two independently propagated scalar-force RK4 resolutions provide finite numerical evidence, not a certified global error bound or a universal dynamics guarantee.",
    "Force-gradient checks sample initial, midpoint and final retained configurations; all-history scalar force and conservation checks are also performed.",
    "No molecular-to-continuum preservation witness, fluid-structure coupling, measured experimental validation or canonical state admission is performed.",
]


def _maximum(value):
    return float(np.max(np.abs(value)))


def _difference(left, right, stride):
    return max(_maximum(np.asarray(left[field]) - np.asarray(right[field])[::stride])
               for field in ("positions_reduced", "velocities_reduced"))


def _convergence(result):
    coarse = _difference(result["primary"], result["time_refined"], 2)
    fine = _difference(result["time_refined"], result["time_fine"], 2)
    resolved = coarse > 1e-10 and fine > 1e-11
    order = math.log2(coarse / fine) if resolved else None
    return {"coarse_difference_normalized": coarse, "fine_difference_normalized": fine,
            "resolved_above_roundoff": resolved, "observed_order": order,
            "order_deficit": max(0.0, 1.8 - order) if resolved else 0.0}


def _spec(request):
    tolerance = request["tolerances"]
    spec = {"reference.rk4_refinement": tolerance["reference_refinement_normalized"],
            "force_potential_gradient": tolerance["force_gradient_normalized"],
            "time_convergence.coarse_difference": tolerance["refinement_normalized"],
            "time_convergence.fine_difference": tolerance["refinement_normalized"],
            "time_convergence.order_deficit": 0.0}
    for label in TRACE_LABELS:
        spec.update({label + ".reference_position": tolerance["reference_normalized"],
                     label + ".reference_velocity": tolerance["reference_normalized"],
                     label + ".energy_relative_drift": tolerance["energy_relative"],
                     label + ".momentum_normalized_drift": tolerance["momentum_normalized"],
                     label + ".independent_force_residual": 1e-11,
                     label + ".independent_diagnostic_residual": 1e-11,
                     label + ".verlet_residual": 1e-11,
                     label + ".minimum_separation_deficit": 0.0})
    return spec


def _trace_values(request, trace, exact, stride):
    model = request["model"]
    positions, velocities, forces = (np.asarray(trace[field], dtype=float) for field in
                                    ("positions_reduced", "velocities_reduced", "forces_reduced"))
    observed = [independent_pair_state(model, p, v) for p, v in zip(positions, velocities)]
    exact_force = np.asarray([state["forces_reduced"] for state in observed])
    energy = np.asarray([state["total_energy_reduced"] for state in observed])
    momentum = np.asarray([state["momentum_reduced"] for state in observed])
    energy_scale = max(1.0, observed[0]["kinetic_energy_reduced"] + abs(observed[0]["potential_energy_reduced"]))
    force_scale = max(1.0, _maximum(exact_force))
    diagnostic_error = 0.0
    for field in (*SCALAR_FIELDS, "momentum_reduced"):
        independently_computed = np.asarray([state[field] for state in observed])
        scale = max(1.0, _maximum(independently_computed))
        diagnostic_error = max(diagnostic_error, _maximum(np.asarray(trace[field]) - independently_computed) / scale)
    dt = trace["dt_reduced"]
    position_residual = positions[1:] - positions[:-1] - dt * velocities[:-1] - 0.5 * dt * dt * exact_force[:-1]
    velocity_residual = velocities[1:] - velocities[:-1] - 0.5 * dt * (exact_force[:-1] + exact_force[1:])
    return {"reference_position": _maximum(positions - exact["positions_reduced"][::stride]),
            "reference_velocity": _maximum(velocities - exact["velocities_reduced"][::stride]),
            "energy_relative_drift": _maximum(energy - energy[0]) / energy_scale,
            "momentum_normalized_drift": _maximum(momentum - momentum[0]) / max(1.0, len(positions[0])),
            "independent_force_residual": _maximum(forces - exact_force) / force_scale,
            "independent_diagnostic_residual": diagnostic_error,
            "verlet_residual": max(_maximum(position_residual), _maximum(velocity_residual)),
            "minimum_separation_deficit": max(0.0, MIN_SEPARATION - min(state["minimum_separation_reduced"] for state in observed))}


def _gradient_error(request, result):
    model, trace = request["model"], result["time_fine"]
    error = 0.0
    increment = 1e-6
    for index in (0, trace["steps"] // 2, trace["steps"]):
        positions = np.asarray(trace["positions_reduced"][index])
        velocities = np.asarray(trace["velocities_reduced"][index])
        forces = np.asarray(trace["forces_reduced"][index])
        for site in range(len(positions)):
            for axis in range(3):
                above, below = positions.copy(), positions.copy()
                above[site, axis] += increment
                below[site, axis] -= increment
                derivative = (independent_pair_state(model, above, velocities)["potential_energy_reduced"] -
                              independent_pair_state(model, below, velocities)["potential_energy_reduced"]) / (2.0 * increment)
                error = max(error, abs(forces[site, axis] + derivative) / max(1.0, abs(forces[site, axis])))
    return float(error)


def _qualification(request, passed):
    desired = set(request["desired_observables"])
    refused, expansion = sorted(desired & REFUSED_OBSERVABLES), sorted(desired & EXPANSION_OBSERVABLES)
    action = "REFUSE" if not passed or refused else "EXPAND" if expansion else "LOCAL"
    return {"action": action, "recommended_admission": "verified_model" if action == "LOCAL" else "blocked",
            "requested_observables": list(request["desired_observables"]),
            "supported_observables": sorted(desired & SUPPORTED_OBSERVABLES),
            "expansion_observables": expansion, "refused_observables": refused,
            "reason": "The numerical candidate failed qualification checks." if not passed else
                      "Requested claims exceed the numerical instrument's authority." if refused else
                      "Additional qualified physical providers are required." if expansion else
                      "The candidate passed the bounded synthetic atomistic-site numerical scope."}


def verify(request, result):
    request, result = validate_request(request), validate_result(request, result)
    exact, reference_coarse = reference(request, substeps=4), reference(request, substeps=2)
    convergence = _convergence(result)
    values = {"reference.rk4_refinement": max(_maximum(exact[field] - reference_coarse[field]) for field in
                                            ("positions_reduced", "velocities_reduced")),
              "force_potential_gradient": _gradient_error(request, result),
              "time_convergence.coarse_difference": convergence["coarse_difference_normalized"],
              "time_convergence.fine_difference": convergence["fine_difference_normalized"],
              "time_convergence.order_deficit": convergence["order_deficit"]}
    for label, stride in zip(TRACE_LABELS, (4, 2, 1)):
        values.update({label + "." + name: value for name, value in _trace_values(request, result[label], exact, stride).items()})
    spec = _spec(request)
    checks = [{"name": name, "value": values[name], "tolerance": spec[name],
               "status": "PASS" if values[name] <= spec[name] else "FAIL"} for name in sorted(spec)]
    passed = all(row["status"] == "PASS" for row in checks)
    return seal({"schema": REPORT_SCHEMA, "request_digest": digest(request), "result_digest": result["record_digest"],
                 "claim_scope": CLAIM_SCOPE, "verification_method": VERIFIER_ID, "reference_method": REFERENCE_ID,
                 "status": "PASS" if passed else "FAIL", "checks": checks,
                 "metrics": {"check_values": values, "time_convergence": convergence},
                 "qualification": _qualification(request, passed), "limitations": list(LIMITATIONS)})


def validate_report(request, result, report):
    """Static structure/declaration/seal checking; no RK4, force or gradient work."""
    request, result = validate_request(request), validate_result(request, result)
    json_tree(report)
    keys(report, {"schema", "request_digest", "result_digest", "claim_scope", "verification_method", "reference_method",
                  "status", "checks", "metrics", "qualification", "limitations", "record_digest"})
    if (report["schema"] != REPORT_SCHEMA or report["request_digest"] != digest(request) or
            report["result_digest"] != result["record_digest"] or report["claim_scope"] != CLAIM_SCOPE or
            report["verification_method"] != VERIFIER_ID or report["reference_method"] != REFERENCE_ID or
            report["status"] not in ("PASS", "FAIL") or report["limitations"] != LIMITATIONS):
        raise ValueError("Molecular report identity, scope or limitations differ")
    spec = _spec(request)
    metrics = report["metrics"]
    keys(metrics, {"check_values", "time_convergence"})
    keys(metrics["check_values"], set(spec))
    for value in metrics["check_values"].values():
        if not 0.0 <= number(value) <= 1e100:
            raise ValueError("Molecular numerical errors must be finite and nonnegative")
    convergence = metrics["time_convergence"]
    keys(convergence, {"coarse_difference_normalized", "fine_difference_normalized", "resolved_above_roundoff", "observed_order", "order_deficit"})
    for field in ("coarse_difference_normalized", "fine_difference_normalized", "order_deficit"):
        if not 0.0 <= number(convergence[field]) <= 1e100:
            raise ValueError("Molecular convergence errors must be finite and nonnegative")
    coarse, fine = convergence["coarse_difference_normalized"], convergence["fine_difference_normalized"]
    resolved = coarse > 1e-10 and fine > 1e-11
    if type(convergence["resolved_above_roundoff"]) is not bool or convergence["resolved_above_roundoff"] != resolved:
        raise ValueError("Molecular convergence resolution claim differs")
    order = math.log2(coarse / fine) if resolved else None
    if order is None:
        if convergence["observed_order"] is not None:
            raise ValueError("Unresolved convergence must not invent an observed order")
    elif number(convergence["observed_order"]) != order:
        raise ValueError("Molecular observed convergence order differs from retained differences")
    deficit = max(0.0, 1.8 - order) if resolved else 0.0
    if number(convergence["order_deficit"]) != deficit:
        raise ValueError("Molecular convergence order deficit differs")
    for suffix, field in (("coarse_difference", "coarse_difference_normalized"), ("fine_difference", "fine_difference_normalized"), ("order_deficit", "order_deficit")):
        if metrics["check_values"]["time_convergence." + suffix] != convergence[field]:
            raise ValueError("Molecular convergence checks contradict retained metrics")
    if type(report["checks"]) is not list or len(report["checks"]) != len(spec):
        raise ValueError("Molecular report must retain exactly the declared checks")
    for row, name in zip(report["checks"], sorted(spec)):
        keys(row, {"name", "value", "tolerance", "status"})
        if row["name"] != name or number(row["tolerance"]) != spec[name] or number(row["value"]) != metrics["check_values"][name]:
            raise ValueError("Molecular check name, value or tolerance differs")
        if row["status"] != ("PASS" if row["value"] <= row["tolerance"] else "FAIL"):
            raise ValueError("Molecular check status contradicts its retained arithmetic")
    passed = all(row["status"] == "PASS" for row in report["checks"])
    if report["status"] != ("PASS" if passed else "FAIL") or report["qualification"] != _qualification(request, passed):
        raise ValueError("Molecular aggregate status or qualification differs")
    check_seal(report)
    return deepcopy(report)
