"""Fixed-step modal Verlet provider for one unilateral finite-patch impact.

The force acts on the striker and on every plate mode through the same patch
average. This provider does not consult the independent eigen reference.
"""
from __future__ import annotations

import math
import numpy as np

from .impact_plate_contract import (CLAIM_SCOPE, RESULT_SCHEMA, SOLVER_ID, UNITS,
                                    modal_parameters, nominal_contact_duration_s, validate_request)
from .operations.runner import digest, seal


def _trace(model: dict, modes_per_axis: int, steps_per_contact: int, step_count: int) -> dict:
    basis = modal_parameters(model, modes_per_axis)
    masses = np.asarray(basis["modal_mass_kg"], dtype=float)
    stiffnesses = np.asarray(basis["modal_stiffness_n_per_m"], dtype=float)
    coupling = np.asarray(basis["patch_coupling"], dtype=float)
    dt = nominal_contact_duration_s(model) / steps_per_contact
    dt_squared = dt * dt
    mass, spring = model["mass_kg"], model["stiffness_n_per_m"]
    q, velocity = np.zeros(len(masses)), np.zeros(len(masses))
    striker, striker_velocity, force = 0.0, model["initial_speed_m_per_s"], 0.0
    scalar_names = ("striker_displacement_m", "compression_m", "velocity_m_per_s", "force_n",
                    "plate_contact_displacement_m", "plate_contact_velocity_m_per_s")
    arrays = {name: np.empty(step_count + 1, dtype=float) for name in scalar_names}
    modal_q = np.empty((len(masses), step_count + 1), dtype=float)
    modal_v = np.empty_like(modal_q)

    def retain(index):
        plate_position, plate_speed = float(coupling @ q), float(coupling @ velocity)
        arrays["striker_displacement_m"][index] = striker
        arrays["compression_m"][index] = striker - plate_position
        arrays["velocity_m_per_s"][index] = striker_velocity
        arrays["force_n"][index] = force
        arrays["plate_contact_displacement_m"][index] = plate_position
        arrays["plate_contact_velocity_m_per_s"][index] = plate_speed
        modal_q[:, index], modal_v[:, index] = q, velocity

    retain(0)
    for index in range(step_count):
        striker_acceleration = -force / mass
        acceleration = (coupling * force - stiffnesses * q) / masses
        striker += striker_velocity * dt + 0.5 * striker_acceleration * dt_squared
        q = q + velocity * dt + 0.5 * acceleration * dt_squared
        next_force = spring * max(striker - float(coupling @ q), 0.0)
        next_acceleration = (coupling * next_force - stiffnesses * q) / masses
        striker_velocity += 0.5 * (striker_acceleration - next_force / mass) * dt
        velocity = velocity + 0.5 * (acceleration + next_acceleration) * dt
        force = next_force
        retain(index + 1)
    return {"modes_per_axis": modes_per_axis, "steps_per_contact": steps_per_contact, "dt_s": dt,
            **{field: basis[field] for field in ("modes", "modal_mass_kg", "modal_stiffness_n_per_m", "patch_coupling")},
            "time_s": [index * dt for index in range(step_count + 1)],
            **{field: values.tolist() for field, values in arrays.items()},
            "modal_displacement_m": modal_q.tolist(), "modal_velocity_m_per_s": modal_v.tolist()}


def simulate(request: dict) -> dict:
    request = validate_request(request)
    integration = request["integration"]
    modes, steps = integration["modes_per_axis"], integration["steps_per_contact"]
    count = math.ceil(steps * integration["duration_factor"])
    return seal({"schema": RESULT_SCHEMA, "request_digest": digest(request), "claim_scope": CLAIM_SCOPE,
                 "solver": SOLVER_ID, "units": dict(UNITS),
                 "primary": _trace(request["model"], modes, steps, count),
                 "refined": _trace(request["model"], modes, steps * 2, count * 2),
                 "spatial": _trace(request["model"], modes + 2, steps * 2, count * 2)})
