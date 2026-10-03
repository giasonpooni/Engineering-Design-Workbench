"""Moving atomistic sites with coherent force-shifted LJ velocity Verlet.

The numerical provider does not consult the independent RK4 reference. Energies
are extensive. Density, temperature and pressure are instantaneous toy-model
reductions, not equilibrium statistics or calibrated transport parameters.
"""
from __future__ import annotations

from copy import deepcopy
import numpy as np

from .fluid_molecular_contract import (CLAIM_SCOPE, CLOCK, MIN_SEPARATION, PROVIDER_ID, REPRESENTATION,
    RESULT_SCHEMA, SCALAR_FIELDS, SOLVER_ID, UNITS, VECTOR_FIELDS, trace_declarations, validate_request)
from .operations.runner import digest, seal


def pair_state(model, positions, velocities):
    """Vectorized unordered pairs; equal/opposite force and one energy per pair."""
    count = len(positions)
    box, cutoff = model["box_length_reduced"], model["cutoff_reduced"]
    first, second = np.triu_indices(count, 1)
    displacement = positions[first] - positions[second]
    displacement -= box * np.rint(displacement / box)
    distance = np.sqrt(np.sum(displacement * displacement, axis=1))
    minimum = float(np.min(distance))
    if minimum < MIN_SEPARATION:
        raise ValueError("Molecular propagation left the hard minimum-separation domain")
    active = distance < cutoff
    r, d = distance[active], displacement[active]
    inv = 1.0 / r
    inv6 = inv ** 6
    cutoff_force = 24.0 * (2.0 * cutoff ** -13 - cutoff ** -7)
    cutoff_potential = 4.0 * (cutoff ** -12 - cutoff ** -6)
    radial_force = 24.0 * (2.0 * inv6 * inv6 - inv6) * inv - cutoff_force
    pair_force = (radial_force * inv)[:, None] * d
    forces = np.zeros_like(positions)
    np.add.at(forces, first[active], pair_force)
    np.add.at(forces, second[active], -pair_force)
    potential = float(np.sum(4.0 * (inv6 * inv6 - inv6) - cutoff_potential + (r - cutoff) * cutoff_force))
    kinetic = 0.5 * float(np.sum(velocities * velocities))
    thermal_velocity = velocities - np.mean(velocities, axis=0)
    thermal_kinetic = 0.5 * float(np.sum(thermal_velocity * thermal_velocity))
    virial = float(np.sum(d * pair_force))
    return {"forces_reduced": forces, "kinetic_energy_reduced": kinetic,
            "potential_energy_reduced": potential, "total_energy_reduced": kinetic + potential,
            "momentum_reduced": np.sum(velocities, axis=0), "number_density_reduced": count / box ** 3,
            "kinetic_temperature_reduced": 2.0 * thermal_kinetic / (3.0 * (count - 1)),
            "virial_pressure_reduced": (2.0 * thermal_kinetic + virial) / (3.0 * box ** 3),
            "minimum_separation_reduced": minimum}


def _trace(request, steps):
    model = request["model"]
    dt = request["integration"]["duration_reduced"] / steps
    positions = np.array(model["positions_reduced"], dtype=float)
    velocities = np.array(model["velocities_reduced"], dtype=float)
    history = {field: [] for field in (*VECTOR_FIELDS, *SCALAR_FIELDS, "momentum_reduced")}
    state = pair_state(model, positions, velocities)

    def retain():
        if (np.max(np.abs(positions)) > 2.0 * model["box_length_reduced"] or
                np.max(np.abs(velocities)) > 5.0 or np.max(np.abs(state["forces_reduced"])) > 1e5):
            raise ValueError("Molecular trajectory exceeds hard finite position/velocity/force bounds")
        history["positions_reduced"].append(positions.tolist())
        history["velocities_reduced"].append(velocities.tolist())
        for field in (*SCALAR_FIELDS, "momentum_reduced", "forces_reduced"):
            value = state[field]
            history[field].append(value.tolist() if isinstance(value, np.ndarray) else value)

    retain()
    for _ in range(steps):
        old_force = state["forces_reduced"]
        positions = positions + dt * velocities + 0.5 * dt * dt * old_force
        next_force = pair_state(model, positions, velocities)["forces_reduced"]
        velocities = velocities + 0.5 * dt * (old_force + next_force)
        state = pair_state(model, positions, velocities)
        retain()
    return {"steps": steps, "dt_reduced": dt, "time_reduced": [index * dt for index in range(steps + 1)], **history}


def simulate(request):
    request = validate_request(request)
    return seal({"schema": RESULT_SCHEMA, "request_digest": digest(request), "claim_scope": CLAIM_SCOPE,
                 "representation": REPRESENTATION, "provider": PROVIDER_ID, "solver": SOLVER_ID,
                 "units": dict(UNITS), "clock": deepcopy(CLOCK), "si_scaling": deepcopy(request["si_scaling"]),
                 **{label: _trace(request, steps) for label, steps in trace_declarations(request)}})


def csv_rows(result):
    """Finite primary trace in explicit reduced units; no implicit SI conversion."""
    header = ["time_reduced", "site_index", "x_reduced", "y_reduced", "z_reduced",
              "vx_reduced", "vy_reduced", "vz_reduced", "fx_reduced", "fy_reduced", "fz_reduced",
              *SCALAR_FIELDS, "px_reduced", "py_reduced", "pz_reduced"]
    trace = result["primary"]
    rows = []
    for index, time in enumerate(trace["time_reduced"]):
        for site in range(len(trace["positions_reduced"][index])):
            rows.append([time, site, *trace["positions_reduced"][index][site],
                         *trace["velocities_reduced"][index][site], *trace["forces_reduced"][index][site],
                         *(trace[field][index] for field in SCALAR_FIELDS), *trace["momentum_reduced"][index]])
    return header, rows
