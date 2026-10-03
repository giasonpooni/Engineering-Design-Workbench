"""Moving conservative SPH parcels with fixed smoothing and Verlet integration."""
from copy import deepcopy
import numpy as np

from .fluid_sph_contract import (CLAIM_SCOPE, FIELD_NAMES, METHOD_ID, PROVIDER_ID, REPRESENTATION, RESULT_SCHEMA,
    UNITS, grid_declarations, initial_state, validate_request)
from .operations.runner import digest, seal


def kernel_and_gradient(distance, h):
    q = np.abs(distance) / h
    shape = np.where(q < 1.0, 1.0 - 1.5 * q * q + 0.75 * q ** 3,
                     np.where(q < 2.0, 0.25 * (2.0 - q) ** 3, 0.0))
    derivative = np.where(q < 1.0, -3.0 * q + 2.25 * q * q,
                          np.where(q < 2.0, -0.75 * (2.0 - q) ** 2, 0.0))
    return 2.0 / (3.0 * h) * shape, 2.0 / (3.0 * h * h) * derivative * np.sign(distance)


def evaluate(model, positions, velocity, mass, h):
    length, area, rho0, c = (model[name] for name in
        ("length_m", "area_m2", "reference_density_kg_per_m3", "sound_speed_m_per_s"))
    r = positions[:, None] - positions[None, :]
    r = (r + 0.5 * length) % length - 0.5 * length
    kernel, gradient = kernel_and_gradient(r, h)
    rho = (mass / area) * np.sum(kernel, axis=1)
    p = c * c * (rho - rho0)
    coefficient = p / (rho * rho)
    acceleration = -(mass / area) * np.sum((coefficient[:, None] + coefficient[None, :]) * gradient, axis=1)
    delta = (rho - rho0) / rho0
    # Stable near-uniform evaluation of log(1+d)-d/(1+d): its
    # linear terms cancel analytically, preventing spurious energy drift.
    e = c * c * sum(((-1.0) ** order) * (order - 1.0) / order * delta ** order for order in range(2, 13))
    energy = mass * float(np.sum(0.5 * velocity * velocity + e))
    momentum = mass * float(np.sum(velocity))
    return rho, p, acceleration, energy, momentum


def _trace(request, n, steps):
    model = request["model"]
    mass = model["reference_density_kg_per_m3"] * model["area_m2"] * model["length_m"] / n
    h, dt = 2.0 * model["length_m"] / n, request["integration"]["duration_s"] / steps
    initial_x, initial_v = initial_state(request, n)
    x, v = np.asarray(initial_x), np.asarray(initial_v)
    arrays = {field: [] for field in FIELD_NAMES}
    energies, momenta = [], []
    rho, pressure, acceleration, energy, momentum = evaluate(model, x, v, mass, h)
    for index in range(steps + 1):
        for field, values in zip(FIELD_NAMES, (x, v, rho, pressure)):
            arrays[field].append(values.tolist())
        energies.append(energy)
        momenta.append(momentum)
        if index == steps:
            break
        x = x + dt * v + 0.5 * dt * dt * acceleration
        next_rho, next_pressure, next_acceleration, _, _ = evaluate(model, x, v, mass, h)
        v = v + 0.5 * dt * (acceleration + next_acceleration)
        rho, pressure, acceleration = next_rho, next_pressure, next_acceleration
        _, _, _, energy, momentum = evaluate(model, x, v, mass, h)
    return {"particles": n, "steps": steps, "dt_s": dt, "smoothing_length_m": h,
            "parcel_mass_kg": mass, "time_s": [index * dt for index in range(steps + 1)],
            **arrays, "total_energy_j": energies, "total_momentum_kg_m_per_s": momenta}


def simulate(request):
    request = validate_request(request)
    return seal({"schema": RESULT_SCHEMA, "request_digest": digest(request), "claim_scope": CLAIM_SCOPE,
                 "provider": PROVIDER_ID, "method": METHOD_ID, "clock": deepcopy(request["clock"]),
                 "representation": deepcopy(REPRESENTATION), "units": dict(UNITS),
                 "resolutions": {label: _trace(request, n, steps) for label, n, steps in grid_declarations(request)}})


def csv_rows(result):
    trace = result["resolutions"]["primary"]
    header = ["time_s", "parcel_index", "parcel_mass_kg"] + list(FIELD_NAMES)
    rows = [[time, particle, trace["parcel_mass_kg"], *[trace[field][index][particle] for field in FIELD_NAMES]]
            for index, time in enumerate(trace["time_s"]) for particle in range(trace["particles"])]
    return header, rows
