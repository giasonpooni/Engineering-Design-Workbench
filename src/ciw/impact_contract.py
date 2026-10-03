"""Bounded SI declarations for one numerical spring/contact benchmark.

Stiffness is an effective N/m spring parameter, not a material modulus. These
declarations confer neither physical qualification nor canonical admission.
"""
from __future__ import annotations

from copy import deepcopy
import math

from .control_contracts import keys, number
from .operations.runner import check_seal, digest

REQUEST_SCHEMA = "ciw.impact-request.v1"
RESULT_SCHEMA = "ciw.impact-result.v1"
REPORT_SCHEMA = "ciw.impact-verification.v1"
OPERATION_ID = "impact.spring-contact.v1"
CLAIM_SCOPE = "undamped_point_mass_massless_spring_contact"
CONTACT_LAW = "compression_only_linear_spring"
MAX_SAMPLES = 32769
SUPPORTED_OBSERVABLES = {
    "force_time", "impulse", "restitution", "energy_accounting", "separation_time"
}
EXPANSION_OBSERVABLES = {
    "plate_deformation", "stress", "strain", "damage", "fracture", "hardness",
    "molecular_response", "morphology", "robustness", "scale_preservation"
}
UNITS = {"time_s": "s", "compression_m": "m", "velocity_m_per_s": "m/s",
         "force_n": "N", "impulse": "N*s", "energy": "J"}
TOLERANCE_KEYS = {"analytic_normalized", "impulse_relative", "momentum_relative",
                  "energy_relative", "restitution_absolute", "separation_relative",
                  "refinement_normalized"}


def _bounded(value, lower, upper, label):
    value = number(value)
    if not lower <= value <= upper:
        raise ValueError(f"{label} must be inside {lower}..{upper}")
    return value


def _zero(value, label):
    if number(value) != 0.0:
        raise ValueError(f"This benchmark requires {label}=0")


def validate_request(request: dict) -> dict:
    """Return a detached strict request; unsupported physical laws are refused."""
    keys(request, {"schema", "scope", "model", "integration", "desired_observables", "tolerances"})
    if request["schema"] != REQUEST_SCHEMA or request["scope"] != CLAIM_SCOPE:
        raise ValueError("Unsupported impact schema or physical scope")
    model = request["model"]
    keys(model, {"mass_kg", "stiffness_n_per_m", "initial_speed_m_per_s",
                 "initial_compression_m", "damping_n_s_per_m",
                 "gravity_during_contact_m_per_s2", "contact_law", "support"})
    mass = _bounded(model["mass_kg"], 1e-6, 1e6, "mass_kg")
    stiffness = _bounded(model["stiffness_n_per_m"], 1e-6, 1e12, "stiffness_n_per_m")
    speed = _bounded(model["initial_speed_m_per_s"], 1e-6, 1e4, "initial_speed_m_per_s")
    for field in ("initial_compression_m", "damping_n_s_per_m", "gravity_during_contact_m_per_s2"):
        _zero(model[field], field)
    if model["contact_law"] != CONTACT_LAW or model["support"] != "fixed":
        raise ValueError("Require compression-only linear spring contact and fixed support")
    integration = request["integration"]
    keys(integration, {"method", "steps_per_contact", "duration_factor"})
    if integration["method"] != "velocity_verlet":
        raise ValueError("Unsupported impact integrator")
    steps = integration["steps_per_contact"]
    if type(steps) is not int or not 16 <= steps <= 4096:
        raise ValueError("steps_per_contact must be an integer inside 16..4096")
    _bounded(integration["duration_factor"], 1.25, 4.0, "duration_factor")
    tolerances = request["tolerances"]
    keys(tolerances, TOLERANCE_KEYS)
    for name, value in tolerances.items():
        _bounded(value, 1e-12, 0.1, "tolerances." + name)
    observables = request["desired_observables"]
    if type(observables) is not list or not 1 <= len(observables) <= 16:
        raise ValueError("Require 1..16 desired observables")
    if any(type(value) is not str or value not in SUPPORTED_OBSERVABLES | EXPANSION_OBSERVABLES
           for value in observables) or len(set(observables)) != len(observables):
        raise ValueError("Unknown or repeated impact observable")
    # Bounds above guarantee finite derived binary64 values; explicitly retain
    # the representability profile instead of silently rescaling a request.
    omega = math.sqrt(stiffness / mass)
    derived = [math.pi / omega, speed / omega, stiffness * speed / omega,
               2 * mass * speed, 0.5 * mass * speed * speed]
    if any(not math.isfinite(value) or not 1e-18 <= value <= 1e18 for value in derived):
        raise ValueError("Impact scales exceed the binary64 benchmark profile")
    return deepcopy(request)


def request_digest(request: dict) -> str:
    return digest(validate_request(request))


def validate_result(request: dict, result: dict) -> dict:
    """Read-only bounded structure and content binding; no simulation/audit run."""
    request = validate_request(request)
    keys(result, {"schema", "request_digest", "claim_scope", "solver", "units",
                  "primary", "refined", "record_digest"})
    if (result["schema"] != RESULT_SCHEMA or result["request_digest"] != digest(request)
            or result["claim_scope"] != CLAIM_SCOPE
            or result["solver"] != "fixed_step_velocity_verlet_binary64"):
        raise ValueError("Result schema, request, numerical runtime or scope binding differs")
    keys(result["units"], set(UNITS))
    if result["units"] != UNITS:
        raise ValueError("Impact result must retain exact SI units")
    steps = request["integration"]["steps_per_contact"]
    count = math.ceil(steps * request["integration"]["duration_factor"])
    contact_duration = math.pi * math.sqrt(request["model"]["mass_kg"] / request["model"]["stiffness_n_per_m"])
    for name, resolution, step_count in (("primary", steps, count), ("refined", steps * 2, count * 2)):
        trace = result[name]
        keys(trace, {"steps_per_contact", "dt_s", "time_s", "compression_m",
                     "velocity_m_per_s", "force_n"})
        if type(trace["steps_per_contact"]) is not int or trace["steps_per_contact"] != resolution:
            raise ValueError("Trace resolution differs from declared integration")
        dt = number(trace["dt_s"])
        if dt <= 0 or not math.isclose(dt, contact_duration / resolution, rel_tol=2e-14, abs_tol=0.0):
            raise ValueError("Trace timestep differs from declared fixed grid")
        if not 1 < step_count + 1 <= MAX_SAMPLES:
            raise ValueError("Trace exceeds the sample budget")
        for field in ("time_s", "compression_m", "velocity_m_per_s", "force_n"):
            values = trace[field]
            if type(values) is not list or len(values) != step_count + 1:
                raise ValueError("Trace arrays must cover every declared grid point")
            for value in values:
                if abs(number(value)) > 1e20:
                    raise ValueError("Trace sample exceeds the finite arithmetic budget")
        for index, time in enumerate(trace["time_s"]):
            if time < 0 or not math.isclose(time, index * dt, rel_tol=2e-14, abs_tol=0.0):
                raise ValueError("Trace times differ from the fixed ordered grid")
        if (trace["compression_m"][0] != 0 or trace["velocity_m_per_s"][0] != request["model"]["initial_speed_m_per_s"]
                or trace["force_n"][0] != 0):
            raise ValueError("Trace changed the declared initial contact state")
    check_seal(result)
    return deepcopy(result)


def example_request() -> dict:
    return {"schema": REQUEST_SCHEMA, "scope": CLAIM_SCOPE,
            "model": {"mass_kg": 1.0, "stiffness_n_per_m": 10000.0,
                      "initial_speed_m_per_s": 2.0, "initial_compression_m": 0.0,
                      "damping_n_s_per_m": 0.0, "gravity_during_contact_m_per_s2": 0.0,
                      "contact_law": CONTACT_LAW, "support": "fixed"},
            "integration": {"method": "velocity_verlet", "steps_per_contact": 256,
                            "duration_factor": 1.5},
            "desired_observables": ["force_time", "impulse", "restitution",
                                    "energy_accounting", "separation_time"],
            "tolerances": {"analytic_normalized": 0.001, "impulse_relative": 0.001,
                           "momentum_relative": 1e-10, "energy_relative": 0.001,
                           "restitution_absolute": 0.001, "separation_relative": 0.001,
                           "refinement_normalized": 0.001}}
