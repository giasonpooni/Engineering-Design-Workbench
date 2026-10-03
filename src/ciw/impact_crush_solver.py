"""Fixed grid Verlet and local return mapping; no reference trajectory lookup."""
from __future__ import annotations

import math

from .impact_crush_contract import (CLAIM_SCOPE, RESULT_SCHEMA, STATE_FIELDS, UNITS,
                                    contact_duration_s, validate_request)
from .operations.runner import digest, seal


def _trace(model: dict, steps_per_contact: int, step_count: int) -> dict:
    mass, stiffness, speed, limit = (float(model[name]) for name in
        ("mass_kg", "stiffness_n_per_m", "initial_speed_m_per_s", "yield_force_n"))
    dt = contact_duration_s(model) / steps_per_contact
    q, velocity, force, plastic = 0.0, speed, 0.0, 0.0
    values = {"compression_m": [q], "velocity_m_per_s": [velocity], "force_n": [force],
              "plastic_compression_m": [plastic], "plastic_work_j": [0.0]}
    times = [0.0]
    for index in range(step_count):
        acceleration = -force / mass
        q += velocity * dt + 0.5 * acceleration * dt * dt
        plastic = max(plastic, q - limit / stiffness)
        next_force = min(limit, stiffness * max(q - plastic, 0.0))
        velocity += 0.5 * (acceleration - next_force / mass) * dt
        force = next_force
        state = (q, velocity, force, plastic, limit * plastic)
        for field, value in zip(STATE_FIELDS, state):
            values[field].append(value)
        times.append((index + 1) * dt)
    return {"steps_per_contact": steps_per_contact, "dt_s": dt, "time_s": times, **values}


def simulate(request: dict) -> dict:
    request = validate_request(request)
    integration = request["integration"]
    steps = integration["steps_per_contact"]
    count = math.ceil(steps * integration["duration_factor"])
    return seal({"schema": RESULT_SCHEMA, "request_digest": digest(request), "claim_scope": CLAIM_SCOPE,
                 "solver": "fixed_step_velocity_verlet_return_mapping_binary64", "units": dict(UNITS),
                 "primary": _trace(request["model"], steps, count),
                 "refined": _trace(request["model"], steps * 2, count * 2)})
