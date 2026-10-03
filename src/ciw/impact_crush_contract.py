"""Bounded SI declarations for one unilateral crush-contact benchmark.

An effective elastic spring and ideal plastic slider are a numerical model,
not an identified polymer, hardness measurement or fracture law.
"""
from __future__ import annotations

from copy import deepcopy
import math

from .control_contracts import keys, number
from .impact_contract import EXPANSION_OBSERVABLES as ELASTIC_EXPANSION_OBSERVABLES, TOLERANCE_KEYS
from .operations.runner import check_seal, digest

REQUEST_SCHEMA = "ciw.impact-crush-request.v1"
RESULT_SCHEMA = "ciw.impact-crush-result.v1"
REPORT_SCHEMA = "ciw.impact-crush-verification.v1"
OPERATION_ID = "impact.crush-contact.v1"
CLAIM_SCOPE = "unilateral_elastic_perfectly_plastic_crush"
CONTACT_LAW = "compression_only_elastic_perfectly_plastic"
MAX_SAMPLES = 32769
STATE_FIELDS = ("compression_m", "velocity_m_per_s", "force_n",
                "plastic_compression_m", "plastic_work_j")
SUPPORTED_OBSERVABLES = {"force_time", "impulse", "restitution", "energy_accounting",
                         "separation_time", "plastic_work", "residual_compression"}
EXPANSION_OBSERVABLES = ELASTIC_EXPANSION_OBSERVABLES | {"rate_response", "thermal_response"}
UNITS = {"time_s": "s", "compression_m": "m", "velocity_m_per_s": "m/s",
         "force_n": "N", "plastic_compression_m": "m", "plastic_work_j": "J",
         "impulse": "N*s", "energy": "J"}


def _bounded(value, lower, upper, label):
    value = number(value)
    if not lower <= value <= upper:
        raise ValueError(f"{label} must be inside {lower}..{upper}")
    return value


def contact_duration_s(model: dict) -> float:
    """Scalar grid declaration only; no analytic trajectory or event control."""
    mass, stiffness, speed, limit = (model[name] for name in
        ("mass_kg", "stiffness_n_per_m", "initial_speed_m_per_s", "yield_force_n"))
    omega = math.sqrt(stiffness / mass)
    ratio = limit / (speed * math.sqrt(mass * stiffness))
    if ratio >= 1.0:
        return math.pi * math.sqrt(mass / stiffness)
    yield_speed = speed * math.sqrt((1.0 - ratio) * (1.0 + ratio))
    return math.asin(ratio) / omega + mass * yield_speed / limit + math.pi / (2.0 * omega)


def validate_request(request: dict) -> dict:
    keys(request, {"schema", "scope", "model", "integration", "desired_observables", "tolerances"})
    if request["schema"] != REQUEST_SCHEMA or request["scope"] != CLAIM_SCOPE:
        raise ValueError("Unsupported crush schema or physical scope")
    model = request["model"]
    keys(model, {"mass_kg", "stiffness_n_per_m", "initial_speed_m_per_s",
                 "initial_compression_m", "initial_plastic_compression_m", "yield_force_n",
                 "damping_n_s_per_m", "gravity_during_contact_m_per_s2", "contact_law", "support"})
    mass = _bounded(model["mass_kg"], 1e-6, 1e6, "mass_kg")
    stiffness = _bounded(model["stiffness_n_per_m"], 1e-6, 1e12, "stiffness_n_per_m")
    speed = _bounded(model["initial_speed_m_per_s"], 1e-6, 1e4, "initial_speed_m_per_s")
    limit = _bounded(model["yield_force_n"], 1e-18, 1e18, "yield_force_n")
    for field in ("initial_compression_m", "initial_plastic_compression_m",
                  "damping_n_s_per_m", "gravity_during_contact_m_per_s2"):
        if number(model[field]) != 0.0:
            raise ValueError(f"This benchmark requires {field}=0")
    if model["contact_law"] != CONTACT_LAW or model["support"] != "fixed":
        raise ValueError("Require compression-only elastic-perfectly-plastic contact and fixed support")
    # One outward binary64 ULP covers the final derived-ratio division at an
    # inclusive declared endpoint. Preserve the actual value; never clamp it.
    ratio = limit / (speed * math.sqrt(mass * stiffness))
    if not math.nextafter(0.2, -math.inf) <= ratio <= math.nextafter(5.0, math.inf):
        raise ValueError("yield_ratio must be inside 0.2..5.0")
    integration = request["integration"]
    keys(integration, {"method", "steps_per_contact", "duration_factor"})
    if integration["method"] != "velocity_verlet":
        raise ValueError("Unsupported crush integrator")
    steps = integration["steps_per_contact"]
    if type(steps) is not int or not 32 <= steps <= 4096:
        raise ValueError("steps_per_contact must be an integer inside 32..4096")
    _bounded(integration["duration_factor"], 1.25, 4.0, "duration_factor")
    keys(request["tolerances"], TOLERANCE_KEYS)
    for name, value in request["tolerances"].items():
        _bounded(value, 1e-12, 0.1, "tolerances." + name)
    observables = request["desired_observables"]
    if type(observables) is not list or not 1 <= len(observables) <= 16:
        raise ValueError("Require 1..16 desired observables")
    if (any(type(value) is not str or value not in SUPPORTED_OBSERVABLES | EXPANSION_OBSERVABLES
            for value in observables) or len(set(observables)) != len(observables)):
        raise ValueError("Unknown or repeated crush observable")
    omega = math.sqrt(stiffness / mass)
    scales = [contact_duration_s(model), speed / omega, speed * math.sqrt(mass * stiffness),
              2.0 * mass * speed, 0.5 * mass * speed * speed, limit / stiffness]
    if any(not math.isfinite(value) or not 1e-18 <= value <= 1e18 for value in scales):
        raise ValueError("Crush scales exceed the binary64 benchmark profile")
    return deepcopy(request)


def request_digest(request: dict) -> str:
    return digest(validate_request(request))


def validate_result(request: dict, result: dict) -> dict:
    """Bound structure and content binding without running solver or audit."""
    request = validate_request(request)
    keys(result, {"schema", "request_digest", "claim_scope", "solver", "units", "primary", "refined", "record_digest"})
    if (result["schema"] != RESULT_SCHEMA or result["request_digest"] != digest(request)
            or result["claim_scope"] != CLAIM_SCOPE
            or result["solver"] != "fixed_step_velocity_verlet_return_mapping_binary64"):
        raise ValueError("Result schema, request, numerical runtime or scope binding differs")
    keys(result["units"], set(UNITS))
    if result["units"] != UNITS:
        raise ValueError("Crush result must retain exact SI units")
    steps = request["integration"]["steps_per_contact"]
    count = math.ceil(steps * request["integration"]["duration_factor"])
    duration = contact_duration_s(request["model"])
    for label, resolution, step_count in (("primary", steps, count), ("refined", steps * 2, count * 2)):
        trace = result[label]
        keys(trace, {"steps_per_contact", "dt_s", "time_s"} | set(STATE_FIELDS))
        if type(trace["steps_per_contact"]) is not int or trace["steps_per_contact"] != resolution:
            raise ValueError("Trace resolution differs from declared integration")
        dt = number(trace["dt_s"])
        if dt <= 0 or not math.isclose(dt, duration / resolution, rel_tol=2e-14, abs_tol=0.0):
            raise ValueError("Trace timestep differs from declared fixed grid")
        if not 1 < step_count + 1 <= MAX_SAMPLES:
            raise ValueError("Trace exceeds the sample budget")
        for field in ("time_s",) + STATE_FIELDS:
            values = trace[field]
            if type(values) is not list or len(values) != step_count + 1:
                raise ValueError("Trace arrays must cover every declared grid point")
            for value in values:
                if abs(number(value)) > 1e20:
                    raise ValueError("Trace sample exceeds the finite arithmetic budget")
        for index, time in enumerate(trace["time_s"]):
            if time < 0 or not math.isclose(time, index * dt, rel_tol=2e-14, abs_tol=0.0):
                raise ValueError("Trace times differ from the fixed ordered grid")
        initial = {"compression_m": 0.0, "velocity_m_per_s": request["model"]["initial_speed_m_per_s"],
                   "force_n": 0.0, "plastic_compression_m": 0.0, "plastic_work_j": 0.0}
        if any(trace[field][0] != value for field, value in initial.items()):
            raise ValueError("Trace changed the declared initial contact state")
    check_seal(result)
    return deepcopy(result)


def example_request() -> dict:
    return {"schema": REQUEST_SCHEMA, "scope": CLAIM_SCOPE,
            "model": {"mass_kg": 1.0, "stiffness_n_per_m": 10000.0,
                      "initial_speed_m_per_s": 2.0, "initial_compression_m": 0.0,
                      "initial_plastic_compression_m": 0.0, "yield_force_n": 100.0,
                      "damping_n_s_per_m": 0.0, "gravity_during_contact_m_per_s2": 0.0,
                      "contact_law": CONTACT_LAW, "support": "fixed"},
            "integration": {"method": "velocity_verlet", "steps_per_contact": 1024, "duration_factor": 1.5},
            "desired_observables": ["force_time", "impulse", "restitution", "energy_accounting",
                                    "separation_time", "plastic_work", "residual_compression"],
            "tolerances": {"analytic_normalized": 0.001, "impulse_relative": 0.001,
                           "momentum_relative": 1e-10, "energy_relative": 0.001,
                           "restitution_absolute": 0.001, "separation_relative": 0.001,
                           "refinement_normalized": 0.001}}
