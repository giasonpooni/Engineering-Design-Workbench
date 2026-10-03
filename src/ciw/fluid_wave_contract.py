"""Strict bounded SI profile for periodic linear surface gravity waves.

This is a one-dimensional, uniform-depth, small-amplitude shallow-water model.
No particle representation is involved. Structural validation is data-only:
it never runs the solver or the independent travelling-wave reference.
"""
from __future__ import annotations

from copy import deepcopy
import math

from .control_contracts import keys, number
from .operations.runner import check_seal, digest

REQUEST_SCHEMA = "ciw.fluid-wave-request.v1"
RESULT_SCHEMA = "ciw.fluid-wave-result.v1"
REPORT_SCHEMA = "ciw.fluid-wave-verification.v1"
OPERATION_ID = "fluid.wave.simulate.v1"
VERIFY_OPERATION_ID = "fluid.wave.verify.v1"
CLAIM_SCOPE = "periodic_uniform_depth_linear_shallow_water_surface_gravity_wave"
PROVIDER_ID = "ciw.fluid-wave-provider.v1"
SOLVER_ID = "staggered_finite_volume_implicit_midpoint_binary64"
INITIAL_PROFILE = "zero_mean_three_mode_right_travelling_pulse"
HARMONICS = ((1, 0.5), (2, 0.3), (3, 0.2))
CLOCK = {"owner": PROVIDER_ID, "clock_id": "fluid-wave-model-clock",
         "time_origin_s": 0.0, "time_basis": "elapsed_model_time",
         "externally_synchronized": False}
FIELD_NAMES = ("free_surface_elevation_m", "depth_averaged_velocity_m_per_s",
               "volume_flux_m3_per_s", "bottom_gauge_pressure_pa")
SCALAR_NAMES = ("liquid_volume_m3", "mechanical_energy_j")
TRACE_LABELS = ("primary", "time_refined", "time_fine", "spatial_refined", "spatial_fine")
UNITS = {"time_s": "s", "cell_x_m": "m", "face_x_m": "m", "dx_m": "m", "dt_s": "s",
         "free_surface_elevation_m": "m", "depth_averaged_velocity_m_per_s": "m/s",
         "volume_flux_m3_per_s": "m^3/s", "bottom_gauge_pressure_pa": "Pa",
         "liquid_volume_m3": "m^3", "mechanical_energy_j": "J"}
SUPPORTED_OBSERVABLES = {"surface_gravity_wave", "free_surface_elevation", "depth_averaged_velocity",
                         "volume_flux", "hydrostatic_bottom_pressure", "mass_balance",
                         "energy_accounting", "wave_speed", "numerical_convergence"}
EXPANSION_OBSERVABLES = {"resolved_vertical_velocity", "nonlinear_flow", "breaking_waves",
                         "wetting_drying", "turbulence", "viscous_dissipation", "acoustic_wave",
                         "molecular_response", "sph_particles", "suspended_grains",
                         "fluid_structure_interaction", "structural_deformation", "surface_tension"}
REFUSED_OBSERVABLES = {"experimental_validation", "certified_design", "canonical_state_admission"}
TOLERANCE_KEYS = {"analytic_normalized", "mass_relative", "energy_relative",
                  "wave_speed_relative", "time_refinement_normalized", "spatial_refinement_normalized"}
MAX_BASE_SPACE_TIME_POINTS = 8192


def _bounded(value, lower, upper, label):
    value = number(value)
    if not lower <= value <= upper:
        raise ValueError(f"{label} must be inside {lower}..{upper}")
    return value


def wave_speed_m_per_s(model: dict) -> float:
    return math.sqrt(model["gravity_m_per_s2"] * model["depth_m"])


def trace_declarations(request: dict):
    """Fixed independent temporal and spatial refinement grids."""
    cells, steps = request["integration"]["cells"], request["integration"]["steps"]
    return (("primary", cells, steps), ("time_refined", cells, 2 * steps),
            ("time_fine", cells, 4 * steps), ("spatial_refined", 2 * cells, 4 * steps),
            ("spatial_fine", 4 * cells, 4 * steps))


def initial_values(model: dict, x_m: float) -> float:
    """The fixed zero-mean band-limited initial elevation declaration."""
    return model["amplitude_m"] * sum(weight * math.cos(2 * math.pi * mode *
        (x_m - model["pulse_center_m"]) / model["length_m"]) for mode, weight in HARMONICS)


def validate_request(request: dict) -> dict:
    keys(request, {"schema", "scope", "model", "integration", "clock", "desired_observables", "tolerances"})
    if request["schema"] != REQUEST_SCHEMA or request["scope"] != CLAIM_SCOPE:
        raise ValueError("Unsupported surface-wave request schema or physical scope")
    if request["clock"] != CLOCK or type(request["clock"].get("externally_synchronized")) is not bool:
        raise ValueError("The wave provider must own its declared elapsed model clock")
    keys(request["clock"], set(CLOCK))
    for key in ("owner", "clock_id", "time_basis"):
        if type(request["clock"][key]) is not str:
            raise ValueError("Require strict clock identity strings")
    if type(request["clock"]["time_origin_s"]) not in (int, float):
        raise ValueError("Clock origin must be a number, not a boolean")
    model = request["model"]
    keys(model, {"length_m", "depth_m", "width_m", "density_kg_per_m3", "gravity_m_per_s2",
                 "amplitude_m", "pulse_center_m", "initial_profile", "boundary", "particle_semantics"})
    length = _bounded(model["length_m"], 0.1, 10000.0, "length_m")
    depth = _bounded(model["depth_m"], 0.01, 10.0, "depth_m")
    _bounded(model["width_m"], 0.01, 10000.0, "width_m")
    _bounded(model["density_kg_per_m3"], 500.0, 2000.0, "density_kg_per_m3")
    _bounded(model["gravity_m_per_s2"], 1.0, 20.0, "gravity_m_per_s2")
    amplitude = _bounded(model["amplitude_m"], 1e-8, 0.1, "amplitude_m")
    center = _bounded(model["pulse_center_m"], 0.0, length, "pulse_center_m")
    if center == length:
        raise ValueError("Pulse center must lie in the half-open periodic interval [0,length)")
    if amplitude / depth > 0.01:
        raise ValueError("Hard small-amplitude validity requires sum of modal amplitudes/depth <= 0.01")
    if 6.0 * math.pi * depth / length > 0.2:
        raise ValueError("Hard long-wavelength validity requires every retained k*depth <= 0.2")
    if (model["initial_profile"] != INITIAL_PROFILE or model["boundary"] != "periodic_uniform_depth"
            or model["particle_semantics"] != "none"):
        raise ValueError("Require the fixed right-travelling pulse, periodic uniform depth and no particle semantics")
    integration = request["integration"]
    keys(integration, {"method", "cells", "steps", "duration_s", "time_refinement_factor", "spatial_refinement_factor"})
    if integration["method"] != "implicit_midpoint":
        raise ValueError("Only the staggered finite-volume implicit midpoint provider is supported")
    cells, steps = integration["cells"], integration["steps"]
    if type(cells) is not int or cells not in (32, 64, 128):
        raise ValueError("cells must be 32, 64 or 128; all fixed modes remain below Nyquist")
    if type(steps) is not int or not 32 <= steps <= 256:
        raise ValueError("steps must be an integer inside 32..256")
    if cells * steps > MAX_BASE_SPACE_TIME_POINTS:
        raise ValueError("Wave refinement traces exceed the bounded space/time allocation")
    for field in ("time_refinement_factor", "spatial_refinement_factor"):
        if type(integration[field]) is not int or integration[field] != 2:
            raise ValueError("Wave refinement factors must be the exact integer 2")
    period = length / wave_speed_m_per_s(model)
    duration = _bounded(integration["duration_s"], 0.1 * period, 1.0 * period, "duration_s")
    dt = duration / steps
    if wave_speed_m_per_s(model) * dt / (length / cells) > 0.5:
        raise ValueError("Hard accuracy CFL requires c*dt/dx <= 0.5 despite implicit stability")
    if 6.0 * math.pi * wave_speed_m_per_s(model) * dt / length > 0.2:
        raise ValueError("Hard modal time-resolution requires highest continuum omega*dt <= 0.2")
    keys(request["tolerances"], TOLERANCE_KEYS)
    for field, value in request["tolerances"].items():
        _bounded(value, 1e-13, 0.1, "tolerances." + field)
    observables = request["desired_observables"]
    all_observables = SUPPORTED_OBSERVABLES | EXPANSION_OBSERVABLES | REFUSED_OBSERVABLES
    if (type(observables) is not list or not 1 <= len(observables) <= 24 or
            any(type(item) is not str or item not in all_observables for item in observables)
            or len(set(observables)) != len(observables)):
        raise ValueError("Require bounded unique known desired observables")
    return deepcopy(request)


def request_digest(request: dict) -> str:
    return digest(validate_request(request))


def _array(values, count):
    if type(values) is not list or len(values) != count:
        raise ValueError("Trace arrays must cover the declared ordered grid")
    for value in values:
        if abs(number(value)) > 1e30:
            raise ValueError("Trace arithmetic exceeds the bounded SI profile")


def validate_result(request: dict, result: dict) -> dict:
    request = validate_request(request)
    keys(result, {"schema", "request_digest", "claim_scope", "provider", "solver", "units", "clock",
                  "record_digest"} | set(TRACE_LABELS))
    if (result["schema"] != RESULT_SCHEMA or result["request_digest"] != digest(request)
            or result["claim_scope"] != CLAIM_SCOPE or result["provider"] != PROVIDER_ID
            or result["solver"] != SOLVER_ID or result["units"] != UNITS or result["clock"] != CLOCK):
        raise ValueError("Wave result identity, scope, SI units or clock differs from its declaration")
    keys(result["clock"], set(CLOCK))
    if type(result["clock"]["externally_synchronized"]) is not bool:
        raise ValueError("Wave external clock synchronization declaration must be a boolean")
    number(result["clock"]["time_origin_s"])
    model = request["model"]
    for label, cells, steps in trace_declarations(request):
        trace = result[label]
        keys(trace, {"cells", "steps", "dt_s", "dx_m", "time_s", "cell_x_m", "face_x_m"}
                    | set(FIELD_NAMES) | set(SCALAR_NAMES))
        if type(trace["cells"]) is not int or trace["cells"] != cells or type(trace["steps"]) is not int or trace["steps"] != steps:
            raise ValueError("Wave trace grid differs from its declared refinement")
        dt, dx = request["integration"]["duration_s"] / steps, model["length_m"] / cells
        if number(trace["dt_s"]) != dt or number(trace["dx_m"]) != dx:
            raise ValueError("Wave trace timestep or cell spacing differs")
        _array(trace["time_s"], steps + 1)
        _array(trace["cell_x_m"], cells)
        _array(trace["face_x_m"], cells)
        if trace["time_s"] != [index * dt for index in range(steps + 1)]:
            raise ValueError("Wave timestamps must follow the owned fixed elapsed model clock")
        if (trace["cell_x_m"] != [(index + 0.5) * dx for index in range(cells)]
                or trace["face_x_m"] != [index * dx for index in range(cells)]):
            raise ValueError("Wave coordinates must retain cell-center/face stagger and periodic endpoint exclusion")
        for field in FIELD_NAMES:
            matrix = trace[field]
            if type(matrix) is not list or len(matrix) != steps + 1:
                raise ValueError("Wave field matrices must be time by space")
            for row in matrix:
                _array(row, cells)
        for field in SCALAR_NAMES:
            _array(trace[field], steps + 1)
        # Declared initial samples are inexpensive data bindings, not propagation.
        initial_eta = [initial_values(model, x) for x in trace["cell_x_m"]]
        initial_u = [wave_speed_m_per_s(model) / model["depth_m"] * initial_values(model, x)
                     for x in trace["face_x_m"]]
        for observed, expected in zip(trace["free_surface_elevation_m"][0], initial_eta):
            if not math.isclose(observed, expected, rel_tol=0.0, abs_tol=1e-14 * model["amplitude_m"]):
                raise ValueError("Wave trace changed its declared initial elevation")
        for observed, expected in zip(trace["depth_averaged_velocity_m_per_s"][0], initial_u):
            if not math.isclose(observed, expected, rel_tol=0.0,
                                abs_tol=1e-14 * wave_speed_m_per_s(model) * model["amplitude_m"] / model["depth_m"]):
                raise ValueError("Wave trace changed its declared initial right-travelling velocity")
    check_seal(result)
    return deepcopy(result)


def example_request() -> dict:
    model = {"length_m": 20.0, "depth_m": 0.1, "width_m": 1.0, "density_kg_per_m3": 1000.0,
             "gravity_m_per_s2": 9.81, "amplitude_m": 0.0005, "pulse_center_m": 10.0,
             "initial_profile": INITIAL_PROFILE, "boundary": "periodic_uniform_depth", "particle_semantics": "none"}
    return {"schema": REQUEST_SCHEMA, "scope": CLAIM_SCOPE, "model": model, "clock": deepcopy(CLOCK),
            "integration": {"method": "implicit_midpoint", "cells": 64, "steps": 64,
                            "duration_s": 0.25 * model["length_m"] / wave_speed_m_per_s(model),
                            "time_refinement_factor": 2, "spatial_refinement_factor": 2},
            "desired_observables": sorted(SUPPORTED_OBSERVABLES),
            "tolerances": {"analytic_normalized": 0.01, "mass_relative": 1e-12,
                           "energy_relative": 1e-11, "wave_speed_relative": 0.01,
                           "time_refinement_normalized": 0.001, "spatial_refinement_normalized": 0.01}}
