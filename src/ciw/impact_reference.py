"""Closed-form contact solution independent of the numerical integration path."""
from __future__ import annotations

import math

from .impact_contract import validate_request


def reference(request: dict) -> dict:
    model = validate_request(request)["model"]
    mass, stiffness, speed = (model["mass_kg"], model["stiffness_n_per_m"],
                              model["initial_speed_m_per_s"])
    omega = math.sqrt(stiffness / mass)
    return {"angular_frequency_rad_per_s": omega,
            "contact_duration_s": math.pi / omega,
            "maximum_compression_m": speed / omega,
            "peak_force_n": speed * math.sqrt(mass * stiffness),
            "support_impulse_n_s": 2.0 * mass * speed,
            "initial_energy_j": 0.5 * mass * speed * speed,
            "restitution": 1.0}


def _sample(model: dict, time_s: float) -> dict:
    if type(time_s) not in (int, float) or not math.isfinite(time_s) or time_s < 0:
        raise ValueError("Analytical reference time must be finite and nonnegative")
    mass, stiffness, speed = (model["mass_kg"], model["stiffness_n_per_m"],
                              model["initial_speed_m_per_s"])
    omega = math.sqrt(stiffness / mass)
    duration = math.pi / omega
    if time_s < duration:
        compression = speed * math.sin(omega * time_s) / omega
        velocity = speed * math.cos(omega * time_s)
        force = stiffness * compression
    else:
        compression = -speed * (time_s - duration)
        velocity, force = -speed, 0.0
    return {"compression_m": compression, "velocity_m_per_s": velocity, "force_n": force}


def sample(request: dict, time_s: float) -> dict:
    """Compression is signed: after separation it is negative free-flight gap."""
    return _sample(validate_request(request)["model"], time_s)


def reference_values(request: dict, times: list) -> dict:
    """Bounded analytic array source suitable for separate reference evidence."""
    from .impact_contract import MAX_SAMPLES
    model = validate_request(request)["model"]
    if type(times) is not list or not 1 <= len(times) <= MAX_SAMPLES:
        raise ValueError("Require a bounded nonempty list of reference times")
    values = [_sample(model, time) for time in times]
    return {name: [value[name] for value in values]
            for name in ("compression_m", "velocity_m_per_s", "force_n")}
