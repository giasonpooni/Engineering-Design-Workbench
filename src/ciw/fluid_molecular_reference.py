"""Independent scalar radial derivatives and finer classical RK4 integration.

No call to the Verlet provider or its vectorized force implementation occurs.
The reference independently differentiates the force-shifted scalar potential:
https://docs.lammps.org/pair_lj_smooth_linear.html
The returned finite RK4 refinement comparison is numerical evidence, not a
certified error bound. Temperature/pressure convention references:
https://docs.lammps.org/compute_temp.html
https://docs.lammps.org/compute_pressure.html
"""
from __future__ import annotations

import math
import numpy as np

from .fluid_molecular_contract import MIN_SEPARATION, validate_request

REFERENCE_ID = "independent_scalar_radial_derivative_force_shifted_lj_rk4_8x_16x.v1"


def independent_pair_state(model, positions, velocities):
    """Scalar pair loop and floor-based periodic reduction independent of solver."""
    count = len(positions)
    box, cutoff = model["box_length_reduced"], model["cutoff_reduced"]
    force = np.zeros((count, 3))
    potential, virial, minimum = 0.0, 0.0, math.inf
    phi_c = 4.0 / cutoff ** 12 - 4.0 / cutoff ** 6
    derivative_c = -48.0 / cutoff ** 13 + 24.0 / cutoff ** 7
    for i in range(count):
        for j in range(i):
            delta = [float(positions[i][d] - positions[j][d]) for d in range(3)]
            delta = [value - box * math.floor(value / box + 0.5) for value in delta]
            r = math.sqrt(sum(value * value for value in delta))
            minimum = min(minimum, r)
            if r < MIN_SEPARATION:
                raise ValueError("Independent molecular reference left the hard overlap domain")
            if r >= cutoff:
                continue
            phi = 4.0 / r ** 12 - 4.0 / r ** 6
            derivative = -48.0 / r ** 13 + 24.0 / r ** 7 - derivative_c
            potential += phi - phi_c - (r - cutoff) * derivative_c
            for d in range(3):
                component = -derivative * delta[d] / r
                force[i, d] += component
                force[j, d] -= component
                virial += delta[d] * component
    velocity = np.asarray(velocities, dtype=float)
    kinetic = 0.5 * sum(float(component) ** 2 for row in velocity for component in row)
    mean = [sum(float(row[d]) for row in velocity) / count for d in range(3)]
    thermal_kinetic = 0.5 * sum((float(row[d]) - mean[d]) ** 2 for row in velocity for d in range(3))
    return {"forces_reduced": force, "kinetic_energy_reduced": kinetic,
            "potential_energy_reduced": potential, "total_energy_reduced": kinetic + potential,
            "momentum_reduced": np.sum(velocity, axis=0), "number_density_reduced": count / box ** 3,
            "kinetic_temperature_reduced": 2.0 * thermal_kinetic / (3.0 * (count - 1)),
            "virial_pressure_reduced": (2.0 * thermal_kinetic + virial) / (3.0 * box ** 3),
            "minimum_separation_reduced": minimum}


def reference(request, *, substeps=4):
    """RK4 at 4*substeps times primary resolution, retained at the finest grid."""
    request = validate_request(request)
    if type(substeps) is not int or substeps not in (2, 4):
        raise ValueError("Independent reference supports exactly eightfold or sixteenfold primary steps")
    model = request["model"]
    retained_steps = request["integration"]["steps"] * 4
    dt = request["integration"]["duration_reduced"] / retained_steps / substeps
    state = np.array([model["positions_reduced"], model["velocities_reduced"]], dtype=float)
    positions, velocities = [state[0].copy()], [state[1].copy()]

    def derivative(y):
        force = independent_pair_state(model, y[0], y[1])["forces_reduced"]
        return np.array([y[1], force])

    for index in range(retained_steps * substeps):
        k1 = derivative(state)
        k2 = derivative(state + 0.5 * dt * k1)
        k3 = derivative(state + 0.5 * dt * k2)
        k4 = derivative(state + dt * k3)
        state = state + dt * (k1 + 2.0 * k2 + 2.0 * k3 + k4) / 6.0
        if np.max(np.abs(state[0])) > 2 * model["box_length_reduced"] or np.max(np.abs(state[1])) > 5:
            raise ValueError("Independent reference exceeds the hard finite trajectory domain")
        if (index + 1) % substeps == 0:
            positions.append(state[0].copy())
            velocities.append(state[1].copy())
    return {"positions_reduced": np.asarray(positions), "velocities_reduced": np.asarray(velocities),
            "integration_substeps_per_finest_step": substeps}
