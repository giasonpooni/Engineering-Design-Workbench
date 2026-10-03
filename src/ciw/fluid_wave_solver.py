"""Energy-preserving staggered finite-volume implicit midpoint wave provider.

The FFT only solves the constant periodic discrete Helmholtz system. Numerical
propagation never consults the independent continuum travelling-wave reference.
"""
from __future__ import annotations

from copy import deepcopy
import numpy as np

from .fluid_wave_contract import (CLAIM_SCOPE, CLOCK, FIELD_NAMES, PROVIDER_ID, RESULT_SCHEMA,
    SOLVER_ID, UNITS, initial_values, trace_declarations, validate_request, wave_speed_m_per_s)
from .operations.runner import digest, seal


def _trace(request: dict, cells: int, steps: int) -> dict:
    model = request["model"]
    depth, gravity, width, density = (model[field] for field in
        ("depth_m", "gravity_m_per_s2", "width_m", "density_kg_per_m3"))
    dx, dt = model["length_m"] / cells, request["integration"]["duration_s"] / steps
    cell_x = [(index + 0.5) * dx for index in range(cells)]
    face_x = [index * dx for index in range(cells)]
    eta = np.asarray([initial_values(model, x) for x in cell_x], dtype=float)
    velocity = np.asarray([wave_speed_m_per_s(model) / depth * initial_values(model, x) for x in face_x])
    fields = {field: np.empty((steps + 1, cells), dtype=float) for field in FIELD_NAMES}
    volumes, energies = np.empty(steps + 1), np.empty(steps + 1)
    kd_squared = (2.0 * np.sin(np.pi * np.arange(cells // 2 + 1) / cells) / dx) ** 2
    alpha = depth * gravity * dt * dt / 4.0

    def retain(index):
        fields["free_surface_elevation_m"][index] = eta
        fields["depth_averaged_velocity_m_per_s"][index] = velocity
        # Linearized depth-averaged discharge: the eta*u quadratic term is excluded.
        fields["volume_flux_m3_per_s"][index] = width * depth * velocity
        fields["bottom_gauge_pressure_pa"][index] = density * gravity * (depth + eta)
        volumes[index] = width * dx * float(np.sum(depth + eta))
        energies[index] = 0.5 * density * width * dx * float(np.sum(gravity * eta * eta + depth * velocity * velocity))

    retain(0)
    for index in range(steps):
        divergence = (np.roll(velocity, -1) - velocity) / dx
        rhs_hat = (1.0 - alpha * kd_squared) * np.fft.rfft(eta) - depth * dt * np.fft.rfft(divergence)
        next_eta = np.fft.irfft(rhs_hat / (1.0 + alpha * kd_squared), n=cells)
        midpoint_eta = 0.5 * (next_eta + eta)
        velocity = velocity - gravity * dt * (midpoint_eta - np.roll(midpoint_eta, 1)) / dx
        eta = next_eta
        retain(index + 1)
    return {"cells": cells, "steps": steps, "dt_s": dt, "dx_m": dx,
            "time_s": [index * dt for index in range(steps + 1)], "cell_x_m": cell_x, "face_x_m": face_x,
            **{field: values.tolist() for field, values in fields.items()},
            "liquid_volume_m3": volumes.tolist(), "mechanical_energy_j": energies.tolist()}


def simulate(request: dict) -> dict:
    request = validate_request(request)
    return seal({"schema": RESULT_SCHEMA, "request_digest": digest(request), "claim_scope": CLAIM_SCOPE,
                 "provider": PROVIDER_ID, "solver": SOLVER_ID, "units": dict(UNITS), "clock": deepcopy(CLOCK),
                 **{label: _trace(request, cells, steps) for label, cells, steps in trace_declarations(request)}})
