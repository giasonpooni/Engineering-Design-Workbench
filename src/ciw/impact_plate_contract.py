"""Strict SI declarations for a bounded simply supported plate impact model.

The sine basis describes a Kirchhoff--Love elastic plate. The finite patch
spring is an effective contact law; it does not identify a polymer or fracture
law. Structure validation never runs the numerical solver or eigen reference.
"""
from __future__ import annotations

from copy import deepcopy
import math

from .control_contracts import keys, number
from .impact_contract import TOLERANCE_KEYS as CONTACT_TOLERANCE_KEYS
from .operations.runner import check_seal, digest

REQUEST_SCHEMA = "ciw.impact-plate-request.v1"
RESULT_SCHEMA = "ciw.impact-plate-result.v1"
REPORT_SCHEMA = "ciw.impact-plate-verification.v1"
OPERATION_ID = "impact.plate-contact.v1"
CLAIM_SCOPE = "simply_supported_kirchhoff_love_plate_patch_contact"
CONTACT_LAW = "compression_only_linear_patch_spring"
SOLVER_ID = "fixed_step_modal_velocity_verlet_binary64"
MAX_SAMPLES = 8193
MAX_REFERENCE_PHASE_INTERVALS = 25000
STATE_FIELDS = ("striker_displacement_m", "compression_m", "velocity_m_per_s", "force_n",
                "plate_contact_displacement_m", "plate_contact_velocity_m_per_s")
MODAL_FIELDS = ("modal_displacement_m", "modal_velocity_m_per_s")
SUPPORTED_OBSERVABLES = {"force_time", "impulse", "restitution", "energy_accounting",
                         "separation_time", "plate_deformation", "plate_modes"}
EXPANSION_OBSERVABLES = {"stress", "strain", "damage", "fracture", "hardness",
                         "molecular_response", "morphology", "robustness", "scale_preservation",
                         "rate_response", "thermal_response", "plastic_work"}
TOLERANCE_KEYS = CONTACT_TOLERANCE_KEYS | {"spatial_refinement_normalized"}
UNITS = {"time_s": "s", "striker_displacement_m": "m", "compression_m": "m",
         "velocity_m_per_s": "m/s", "force_n": "N", "plate_contact_displacement_m": "m",
         "plate_contact_velocity_m_per_s": "m/s", "modal_displacement_m": "m",
         "modal_velocity_m_per_s": "m/s", "modal_mass_kg": "kg",
         "modal_stiffness_n_per_m": "N/m", "patch_coupling": "1", "impulse": "N*s", "energy": "J"}
MODEL_FIELDS = {"mass_kg", "stiffness_n_per_m", "initial_speed_m_per_s",
                "initial_compression_m", "damping_n_s_per_m", "gravity_during_contact_m_per_s2",
                "contact_law", "support", "length_x_m", "length_y_m", "thickness_m",
                "young_modulus_pa", "poissons_ratio", "density_kg_per_m3",
                "patch_center_x_m", "patch_center_y_m", "patch_width_x_m", "patch_width_y_m"}


def _bounded(value, lower, upper, label):
    value = number(value)
    if not lower <= value <= upper:
        raise ValueError(f"{label} must be inside {lower}..{upper}")
    return value


def nominal_contact_duration_s(model: dict) -> float:
    """Grid declaration from striker/spring scales, not the plate release event."""
    return math.pi * math.sqrt(model["mass_kg"] / model["stiffness_n_per_m"])


def nominal_scales(model: dict) -> dict:
    mass, stiffness, speed = (model[name] for name in
                              ("mass_kg", "stiffness_n_per_m", "initial_speed_m_per_s"))
    omega = math.sqrt(stiffness / mass)
    return {"nominal_contact_time_s": math.pi / omega,
            "nominal_compression_m": speed / omega,
            "nominal_force_n": speed * math.sqrt(mass * stiffness),
            "nominal_impulse_n_s": 2.0 * mass * speed,
            "initial_energy_j": 0.5 * mass * speed * speed,
            "nominal_speed_m_per_s": speed}


def modal_parameters(model: dict, modes_per_axis: int) -> dict:
    """Work-conjugate sine basis and uniform finite-patch average weights."""
    if type(modes_per_axis) is not int or modes_per_axis not in (1, 3, 5):
        raise ValueError("Require a declared plate sine basis of 1, 3 or 5 modes per axis")
    a, b, h = (float(model[name]) for name in ("length_x_m", "length_y_m", "thickness_m"))
    rigidity = model["young_modulus_pa"] * h ** 3 / (12.0 * (1.0 - model["poissons_ratio"] ** 2))
    mass = model["density_kg_per_m3"] * h * a * b / 4.0
    modes, stiffnesses, couplings, frequencies = [], [], [], []
    for m in range(1, modes_per_axis + 1):
        for n in range(1, modes_per_axis + 1):
            modes.append([m, n])
            wavenumber_squared = math.pi ** 2 * (m * m / (a * a) + n * n / (b * b))
            stiffness = rigidity * wavenumber_squared ** 2 * a * b / 4.0
            stiffnesses.append(stiffness)
            frequencies.append(math.sqrt(stiffness / mass))
            product = 1.0
            for order, length, center, width in (
                (m, a, model["patch_center_x_m"], model["patch_width_x_m"]),
                (n, b, model["patch_center_y_m"], model["patch_width_y_m"])):
                half_phase = order * math.pi * width / (2.0 * length)
                product *= math.sin(order * math.pi * center / length) * math.sin(half_phase) / half_phase
            couplings.append(product)
    return {"modes": modes, "modal_mass_kg": [mass] * len(modes),
            "modal_stiffness_n_per_m": stiffnesses, "patch_coupling": couplings,
            "angular_frequency_rad_per_s": frequencies, "flexural_rigidity_n_m": rigidity}


def validate_request(request: dict) -> dict:
    keys(request, {"schema", "scope", "model", "integration", "desired_observables", "tolerances"})
    if request["schema"] != REQUEST_SCHEMA or request["scope"] != CLAIM_SCOPE:
        raise ValueError("Unsupported plate-impact schema or physical scope")
    model = request["model"]
    keys(model, MODEL_FIELDS)
    _bounded(model["mass_kg"], 0.001, 1000.0, "mass_kg")
    _bounded(model["stiffness_n_per_m"], 10.0, 1e8, "stiffness_n_per_m")
    _bounded(model["initial_speed_m_per_s"], 1e-5, 10.0, "initial_speed_m_per_s")
    a = _bounded(model["length_x_m"], 0.02, 2.0, "length_x_m")
    b = _bounded(model["length_y_m"], 0.02, 2.0, "length_y_m")
    h = _bounded(model["thickness_m"], 1e-4, 0.05, "thickness_m")
    _bounded(model["young_modulus_pa"], 1e6, 1e12, "young_modulus_pa")
    _bounded(model["poissons_ratio"], 0.0, 0.49, "poissons_ratio")
    _bounded(model["density_kg_per_m3"], 100.0, 20000.0, "density_kg_per_m3")
    for field in ("initial_compression_m", "damping_n_s_per_m", "gravity_during_contact_m_per_s2"):
        if number(model[field]) != 0.0:
            raise ValueError(f"This plate benchmark requires {field}=0")
    if model["contact_law"] != CONTACT_LAW or model["support"] != "simply_supported_rectangular_plate":
        raise ValueError("Require a unilateral linear patch spring and simply supported rectangular plate")
    if h / min(a, b) > 0.05:
        raise ValueError("Kirchhoff--Love geometry requires thickness/minimum side <= 0.05")
    for axis, length in (("x", a), ("y", b)):
        width = _bounded(model[f"patch_width_{axis}_m"], 2.0 * h, 0.5 * length,
                         f"patch_width_{axis}_m")
        center = number(model[f"patch_center_{axis}_m"])
        if center - 0.5 * width < h or center + 0.5 * width > length - h:
            raise ValueError("Contact patch must remain inside the plate with one-thickness edge clearance")
    integration = request["integration"]
    keys(integration, {"method", "modes_per_axis", "spatial_refinement_increment",
                       "steps_per_contact", "duration_factor"})
    if integration["method"] != "velocity_verlet":
        raise ValueError("Unsupported plate integrator")
    modes = integration["modes_per_axis"]
    if type(modes) is not int or modes not in (1, 3):
        raise ValueError("modes_per_axis must be either 1 or 3")
    if type(integration["spatial_refinement_increment"]) is not int or integration["spatial_refinement_increment"] != 2:
        raise ValueError("spatial_refinement_increment must be 2")
    highest = modes + 2
    if h * math.pi * math.sqrt((highest / a) ** 2 + (highest / b) ** 2) > 0.35:
        raise ValueError("Highest retained plate wavenumber exceeds the thin-plate profile")
    steps = integration["steps_per_contact"]
    if type(steps) is not int or not 256 <= steps <= 2048:
        raise ValueError("steps_per_contact must be an integer inside 256..2048")
    _bounded(integration["duration_factor"], 1.25, 2.0, "duration_factor")
    dt = nominal_contact_duration_s(model) / steps
    horizon = math.ceil(steps * integration["duration_factor"]) * dt
    for order, local_dt in ((modes, dt), (highest, dt / 2.0)):
        basis = modal_parameters(model, order)
        omega_bound_squared = max(value * value for value in basis["angular_frequency_rad_per_s"])
        omega_bound_squared += model["stiffness_n_per_m"] * (1.0 / model["mass_kg"] + sum(
            coupling * coupling / mass for coupling, mass in zip(basis["patch_coupling"], basis["modal_mass_kg"])))
        if local_dt * math.sqrt(omega_bound_squared) > 0.5:
            raise ValueError("Fixed timestep exceeds the conservative dt*omega <= 0.5 profile; increase steps")
        if math.ceil(horizon * math.sqrt(omega_bound_squared) * 32.0 / math.pi) > MAX_REFERENCE_PHASE_INTERVALS:
            raise ValueError("Plate reference event scan exceeds the conservative phase budget")
    keys(request["tolerances"], TOLERANCE_KEYS)
    for name, value in request["tolerances"].items():
        _bounded(value, 1e-12, 0.1, "tolerances." + name)
    observables = request["desired_observables"]
    if type(observables) is not list or not 1 <= len(observables) <= 16:
        raise ValueError("Require 1..16 desired observables")
    if (any(type(value) is not str or value not in SUPPORTED_OBSERVABLES | EXPANSION_OBSERVABLES
            for value in observables) or len(set(observables)) != len(observables)):
        raise ValueError("Unknown or repeated plate observable")
    if any(not math.isfinite(value) or not 1e-18 <= value <= 1e18
           for value in nominal_scales(model).values()):
        raise ValueError("Plate impact scales exceed the binary64 benchmark profile")
    return deepcopy(request)


def request_digest(request: dict) -> str:
    return digest(validate_request(request))


def validate_result(request: dict, result: dict) -> dict:
    request = validate_request(request)
    keys(result, {"schema", "request_digest", "claim_scope", "solver", "units",
                  "primary", "refined", "spatial", "record_digest"})
    if (result["schema"] != RESULT_SCHEMA or result["request_digest"] != digest(request)
            or result["claim_scope"] != CLAIM_SCOPE or result["solver"] != SOLVER_ID):
        raise ValueError("Plate result schema, request, scope or runtime binding differs")
    if result["units"] != UNITS:
        raise ValueError("Plate result must retain exact SI units")
    integration = request["integration"]
    modes, steps = integration["modes_per_axis"], integration["steps_per_contact"]
    count = math.ceil(steps * integration["duration_factor"])
    for label, order, resolution, step_count in (
        ("primary", modes, steps, count), ("refined", modes, steps * 2, count * 2),
        ("spatial", modes + 2, steps * 2, count * 2)):
        trace = result[label]
        keys(trace, {"modes_per_axis", "steps_per_contact", "dt_s", "modes", "modal_mass_kg",
                     "modal_stiffness_n_per_m", "patch_coupling", "time_s"} | set(STATE_FIELDS) | set(MODAL_FIELDS))
        if (type(trace["modes_per_axis"]) is not int or trace["modes_per_axis"] != order
                or type(trace["steps_per_contact"]) is not int or trace["steps_per_contact"] != resolution):
            raise ValueError("Trace basis or temporal resolution differs from declaration")
        basis = modal_parameters(request["model"], order)
        if (type(trace["modes"]) is not list or len(trace["modes"]) != order * order
                or any(type(mode) is not list or len(mode) != 2
                       or any(type(index) is not int for index in mode) for mode in trace["modes"])):
            raise ValueError("Modal index pairs must be strict ordered integers")
        for field in ("modal_mass_kg", "modal_stiffness_n_per_m", "patch_coupling"):
            _validate_array(trace[field], order * order)
        for field in ("modes", "modal_mass_kg", "modal_stiffness_n_per_m", "patch_coupling"):
            if trace[field] != basis[field]:
                raise ValueError("Trace modal metadata differs from the geometry/material declaration")
        dt = number(trace["dt_s"])
        if dt <= 0 or not math.isclose(dt, nominal_contact_duration_s(request["model"]) / resolution,
                                      rel_tol=2e-14, abs_tol=0.0):
            raise ValueError("Trace timestep differs from declared fixed grid")
        if not 1 < step_count + 1 <= MAX_SAMPLES:
            raise ValueError("Trace exceeds the sample budget")
        for field in ("time_s",) + STATE_FIELDS:
            _validate_array(trace[field], step_count + 1)
        for field in MODAL_FIELDS:
            matrix = trace[field]
            if type(matrix) is not list or len(matrix) != order * order:
                raise ValueError("Modal arrays must be one time history per declared mode")
            for values in matrix:
                _validate_array(values, step_count + 1)
                if values[0] != 0.0:
                    raise ValueError("Plate modes must start at rest")
        for index, time in enumerate(trace["time_s"]):
            if time < 0 or not math.isclose(time, index * dt, rel_tol=2e-14, abs_tol=0.0):
                raise ValueError("Trace times differ from the fixed ordered grid")
        for field in STATE_FIELDS:
            expected = request["model"]["initial_speed_m_per_s"] if field == "velocity_m_per_s" else 0.0
            if trace[field][0] != expected:
                raise ValueError("Trace changed the declared initial plate contact state")
    check_seal(result)
    return deepcopy(result)


def _validate_array(values, count):
    if type(values) is not list or len(values) != count:
        raise ValueError("Trace arrays must cover every declared grid point")
    for value in values:
        if abs(number(value)) > 1e20:
            raise ValueError("Trace sample exceeds the finite arithmetic budget")


def example_request() -> dict:
    return {"schema": REQUEST_SCHEMA, "scope": CLAIM_SCOPE,
            "model": {"mass_kg": 1.0, "stiffness_n_per_m": 10000.0, "initial_speed_m_per_s": 0.03,
                      "initial_compression_m": 0.0, "damping_n_s_per_m": 0.0,
                      "gravity_during_contact_m_per_s2": 0.0, "contact_law": CONTACT_LAW,
                      "support": "simply_supported_rectangular_plate", "length_x_m": 0.2,
                      "length_y_m": 0.2, "thickness_m": 0.003, "young_modulus_pa": 2e9,
                      "poissons_ratio": 0.35, "density_kg_per_m3": 1200.0,
                      "patch_center_x_m": 0.1, "patch_center_y_m": 0.1,
                      "patch_width_x_m": 0.02, "patch_width_y_m": 0.02},
            "integration": {"method": "velocity_verlet", "modes_per_axis": 3,
                            "spatial_refinement_increment": 2, "steps_per_contact": 1024,
                            "duration_factor": 1.5},
            "desired_observables": ["force_time", "impulse", "restitution", "energy_accounting",
                                    "separation_time", "plate_deformation", "plate_modes"],
            "tolerances": {"analytic_normalized": 0.001, "impulse_relative": 0.001,
                           "momentum_relative": 1e-10, "energy_relative": 0.001,
                           "restitution_absolute": 0.001, "separation_relative": 0.001,
                           "refinement_normalized": 0.001, "spatial_refinement_normalized": 0.02}}
