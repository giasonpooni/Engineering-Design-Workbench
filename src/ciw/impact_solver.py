"""Fixed-step velocity Verlet for the declared unilateral spring benchmark.

This provider does not consult the analytic reference or qualify a material.
"""
from __future__ import annotations

import math

from .impact_contract import CLAIM_SCOPE, RESULT_SCHEMA, UNITS, validate_request
from .operations.runner import digest, seal


def _trace(model: dict, steps_per_contact: int, step_count: int) -> dict:
    mass = float(model["mass_kg"])
    stiffness = float(model["stiffness_n_per_m"])
    speed = float(model["initial_speed_m_per_s"])
    dt = math.pi * math.sqrt(mass / stiffness) / steps_per_contact
    compression, velocity, force = 0.0, speed, 0.0
    times, compressions, velocities, forces = [0.0], [compression], [velocity], [force]
    for index in range(step_count):
        acceleration = -force / mass
        compression += velocity * dt + 0.5 * acceleration * dt * dt
        next_force = stiffness * max(compression, 0.0)
        velocity += 0.5 * (acceleration - next_force / mass) * dt
        force = next_force
        times.append((index + 1) * dt)
        compressions.append(compression)
        velocities.append(velocity)
        forces.append(force)
    return {"steps_per_contact": steps_per_contact, "dt_s": dt,
            "time_s": times, "compression_m": compressions,
            "velocity_m_per_s": velocities, "force_n": forces}


def simulate(request: dict) -> dict:
    request = validate_request(request)
    integration = request["integration"]
    steps = integration["steps_per_contact"]
    count = math.ceil(steps * integration["duration_factor"])
    return seal({"schema": RESULT_SCHEMA, "request_digest": digest(request),
                 "claim_scope": CLAIM_SCOPE, "solver": "fixed_step_velocity_verlet_binary64",
                 "units": dict(UNITS),
                 "primary": _trace(request["model"], steps, count),
                 "refined": _trace(request["model"], steps * 2, count * 2)})
