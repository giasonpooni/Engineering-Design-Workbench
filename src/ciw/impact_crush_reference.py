"""Independent closed-form elastic/loading/plateau/unloading/free-flight path."""
from __future__ import annotations

import math

from .impact_crush_contract import MAX_SAMPLES, STATE_FIELDS, validate_request


def _reference(model: dict) -> dict:
    mass, stiffness, speed, limit = (model[name] for name in
        ("mass_kg", "stiffness_n_per_m", "initial_speed_m_per_s", "yield_force_n"))
    omega = math.sqrt(stiffness / mass)
    ratio = limit / (speed * math.sqrt(mass * stiffness))
    energy = 0.5 * mass * speed * speed
    dy = limit / stiffness
    if ratio >= 1.0:
        return {"branch": "elastic", "angular_frequency_rad_per_s": omega,
                "contact_duration_s": math.pi / omega, "yield_time_s": None,
                "peak_time_s": math.pi / (2.0 * omega), "plateau_duration_s": 0.0,
                "elastic_yield_compression_m": dy, "maximum_compression_m": speed / omega,
                "peak_force_n": speed * math.sqrt(mass * stiffness),
                "support_impulse_n_s": 2.0 * mass * speed, "initial_energy_j": energy,
                "restitution": 1.0, "residual_compression_m": 0.0,
                "plastic_work_j": 0.0, "rebound_energy_j": energy}
    ty = math.asin(ratio) / omega
    vy = speed * math.sqrt((1.0 - ratio) * (1.0 + ratio))
    plateau = mass * vy / limit
    pmax = mass * vy * vy / (2.0 * limit)
    vr = limit / math.sqrt(mass * stiffness)
    rebound = 0.5 * mass * vr * vr
    return {"branch": "plastic", "angular_frequency_rad_per_s": omega,
            "contact_duration_s": ty + plateau + math.pi / (2.0 * omega),
            "yield_time_s": ty, "peak_time_s": ty + plateau, "plateau_duration_s": plateau,
            "elastic_yield_compression_m": dy, "maximum_compression_m": dy + pmax,
            "peak_force_n": limit, "support_impulse_n_s": mass * (speed + vr),
            "initial_energy_j": energy, "restitution": vr / speed,
            "residual_compression_m": pmax, "plastic_work_j": energy - rebound,
            "rebound_energy_j": rebound}


def reference(request: dict) -> dict:
    return _reference(validate_request(request)["model"])


def _sample(model: dict, time_s: float, ref: dict) -> dict:
    if type(time_s) not in (int, float) or not math.isfinite(time_s) or time_s < 0:
        raise ValueError("Analytical reference time must be finite and nonnegative")
    speed, stiffness, limit, mass = (model[name] for name in
        ("initial_speed_m_per_s", "stiffness_n_per_m", "yield_force_n", "mass_kg"))
    omega, duration = ref["angular_frequency_rad_per_s"], ref["contact_duration_s"]
    pmax, vr = ref["residual_compression_m"], speed * ref["restitution"]
    if time_s >= duration:
        q, velocity, force, plastic = pmax - vr * (time_s - duration), -vr, 0.0, pmax
    elif ref["branch"] == "elastic" or time_s < ref["yield_time_s"]:
        q, velocity = speed * math.sin(omega * time_s) / omega, speed * math.cos(omega * time_s)
        force, plastic = stiffness * q, 0.0
    elif time_s < ref["peak_time_s"]:
        tau = time_s - ref["yield_time_s"]
        ratio = limit / (speed * math.sqrt(mass * stiffness))
        vy = speed * math.sqrt((1.0 - ratio) * (1.0 + ratio))
        plastic = vy * tau - 0.5 * limit / mass * tau * tau
        q, velocity, force = ref["elastic_yield_compression_m"] + plastic, vy - limit / mass * tau, limit
    else:
        tau = time_s - ref["peak_time_s"]
        dy = ref["elastic_yield_compression_m"]
        q, velocity = pmax + dy * math.cos(omega * tau), -dy * omega * math.sin(omega * tau)
        force, plastic = limit * math.cos(omega * tau), pmax
    return {"compression_m": q, "velocity_m_per_s": velocity, "force_n": force,
            "plastic_compression_m": plastic, "plastic_work_j": limit * plastic}


def sample(request: dict, time_s: float) -> dict:
    """q is signed approach; release occurs at q-p=0, not generally at q=0."""
    model = validate_request(request)["model"]
    return _sample(model, time_s, _reference(model))


def reference_values(request: dict, times: list) -> dict:
    model = validate_request(request)["model"]
    if type(times) is not list or not 1 <= len(times) <= MAX_SAMPLES:
        raise ValueError("Require a bounded nonempty list of reference times")
    ref = _reference(model)
    values = [_sample(model, time, ref) for time in times]
    return {name: [value[name] for value in values] for name in STATE_FIELDS}
