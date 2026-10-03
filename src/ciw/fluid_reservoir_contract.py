"""Bounded data contracts for a synthetic linear reservoir/piston instrument.

This is a lumped continuum perturbation model, not a spatial Navier--Stokes
solver. Stored readers check identities and finite declarations without running
its solver or numerical verifier. All accepted inputs/outputs are detached.
"""
from __future__ import annotations

from copy import deepcopy
import math

from .control_contracts import keys, number
from .operations.runner import check_seal, digest

REQUEST_SCHEMA = "ciw.fluid-reservoir-request.v1"
RESULT_SCHEMA = "ciw.fluid-reservoir-result.v1"
REPORT_SCHEMA = "ciw.fluid-reservoir-verification.v1"
OPERATION_ID = "fluid.reservoir.simulate.v1"
CLAIM_SCOPE = "linear_incompressible_two_reservoir_piston"
PROVIDER_ID = "fluid_reservoir_implicit_midpoint_binary64.v1"
METHOD_ID = "fixed_implicit_midpoint_with_work_conjugate_midpoint_quadrature"
CLOCK_ID = "fluid.reservoir.synthetic_model_clock.v1"
GRAVITY = 9.80665
MAX_COARSE_STEPS = 1024
RESOLUTION_FACTORS = {"coarse": 1, "fine": 2, "finer": 4}
REPRESENTATION = {
    "kind": "lumped_continuum_perturbation",
    "particle_meaning": "none",
    "coordinate_frame": "two_reservoir_vertical_head_and_outward_piston",
    "pressure_meaning": "hydrostatic_pressure_deviation_from_preloaded_equilibrium",
    "equilibrium_free_surface_datum": "common_horizontal_elevation",
    "boundary_condition": "closed_incompressible_liquid_with_optional_compliant_piston",
    "clock_owner": CLOCK_ID,
}
SUPPORTED_OBSERVABLES = {
    "volume_transfer", "flow_rate", "connector_velocity", "pressure_deviation",
    "free_surface_elevation", "mass_balance", "energy_balance", "interface_work",
    "structural_displacement",
}
EXPANSION_OBSERVABLES = {
    "turbulence", "wetting_drying", "molecular_transport", "sph_particles",
    "suspended_grains", "acoustic_waves", "surface_wave_breaking", "nonlinear_flow",
    "material_failure", "experimental_prediction", "external_forcing",
}
TOLERANCE_KEYS = {"equations_relative", "balance_relative", "reference_relative", "refinement_relative"}
UNITS = {
    "time_s": "s", "transfer_m3": "m^3", "flow_m3_per_s": "m^3/s",
    "connector_velocity_m_per_s": "m/s", "piston_displacement_m": "m",
    "piston_velocity_m_per_s": "m/s", "head1_m": "m", "head2_m": "m",
    "pressure1_deviation_pa": "Pa", "pressure2_deviation_pa": "Pa",
    "pressure_difference_pa": "Pa", "interface_force_n": "N",
    "reservoir1_volume_m3": "m^3", "reservoir2_column_volume_m3": "m^3",
    "piston_swept_volume_m3": "m^3", "total_liquid_volume_m3": "m^3",
    "total_liquid_mass_kg": "kg", "fluid_energy_j": "J", "structure_energy_j": "J",
    "total_energy_j": "J", "fluid_dissipation_j": "J", "structure_dissipation_j": "J",
    "external_work_j": "J", "fluid_interface_work_j": "J", "structure_interface_work_j": "J",
}
STATE_FIELDS = tuple(UNITS)


def _bounded(value, lower, upper, label):
    value = number(value)
    if not lower <= value <= upper:
        raise ValueError(f"{label} must be inside {lower}..{upper}")
    return value


def continuous_bounds(request):
    """Energy inequalities bounding the entire unforced passive trajectory."""
    f, rs, co, st, ini = (request[name] for name in ("fluid", "reservoirs", "connector", "structure", "initial"))
    rho_g = f["density_kg_per_m3"] * GRAVITY
    area = st["piston_area_m2"] if st["enabled"] else 0.0
    r, q, x, v = (ini[name] for name in ("transfer_m3", "flow_m3_per_s", "piston_displacement_m", "piston_velocity_m_per_s"))
    inertance = f["density_kg_per_m3"] * co["length_m"] / co["area_m2"]
    energy = 0.5 * (inertance * q*q + rho_g * (r*r / rs["area1_m2"] + (r-area*x)**2 / rs["area2_m2"]))
    if st["enabled"]:
        energy += 0.5 * (st["mass_kg"] * v*v + st["stiffness_n_per_m"] * x*x)
    return {
        "initial_energy_j": energy,
        "head1_m": math.sqrt(2*energy/(rho_g*rs["area1_m2"])),
        "head2_m": math.sqrt(2*energy/(rho_g*rs["area2_m2"])),
        "transfer_m3": math.sqrt(2*energy*rs["area1_m2"]/rho_g),
        "flow_m3_per_s": math.sqrt(2*energy/inertance),
        "piston_displacement_m": math.sqrt(2*energy/st["stiffness_n_per_m"]) if st["enabled"] else 0.0,
        "piston_velocity_m_per_s": math.sqrt(2*energy/st["mass_kg"]) if st["enabled"] else 0.0,
    }


def validate_request(request: dict) -> dict:
    keys(request, {"schema", "scope", "source", "fluid", "reservoirs", "connector", "structure",
                   "initial", "forcing", "clock", "desired_observables", "tolerances"})
    if request["schema"] != REQUEST_SCHEMA or request["scope"] != CLAIM_SCOPE:
        raise ValueError("Unsupported reservoir schema or physical scope")
    keys(request["source"], {"kind", "source_ref"})
    if request["source"]["kind"] != "synthetic":
        raise ValueError("Reservoir model requires a synthetic source; measurements are unqualified")
    source = request["source"]["source_ref"]
    if type(source) is not str or not source.strip() or len(source) > 160:
        raise ValueError("Require a bounded nonempty synthetic source_ref")
    f = request["fluid"]
    keys(f, {"density_kg_per_m3", "gravity_m_per_s2", "compressibility"})
    _bounded(f["density_kg_per_m3"], 500.0, 2000.0, "density")
    if number(f["gravity_m_per_s2"]) != GRAVITY or f["compressibility"] != "incompressible":
        raise ValueError("Require incompressibility and fixed gravity 9.80665 m/s^2")
    rs = request["reservoirs"]
    keys(rs, {"area1_m2", "area2_m2", "equilibrium_depth1_m", "equilibrium_depth2_m", "maximum_head_fraction"})
    for name in ("area1_m2", "area2_m2"):
        _bounded(rs[name], 0.01, 10.0, name)
    for name in ("equilibrium_depth1_m", "equilibrium_depth2_m"):
        _bounded(rs[name], 0.1, 10.0, name)
    if number(rs["maximum_head_fraction"]) != 0.1:
        raise ValueError("The small-deviation domain fixes maximum_head_fraction at 0.1")
    co = request["connector"]
    keys(co, {"length_m", "area_m2", "resistance_pa_s_per_m3"})
    _bounded(co["length_m"], 0.1, 100.0, "connector.length_m")
    _bounded(co["area_m2"], 1e-4, 0.1, "connector.area_m2")
    if co["area_m2"] > 0.1 * min(rs["area1_m2"], rs["area2_m2"]):
        raise ValueError("Connector must remain small compared with both reservoir areas")
    _bounded(co["resistance_pa_s_per_m3"], 0.0, 1e8, "hydraulic resistance")
    st = request["structure"]
    keys(st, {"enabled", "piston_area_m2", "mass_kg", "stiffness_n_per_m", "damping_n_s_per_m", "maximum_displacement_m", "equilibrium_preload"})
    if type(st["enabled"]) is not bool:
        raise ValueError("structure.enabled must be a boolean")
    _bounded(st["piston_area_m2"], 1e-4, 0.1, "piston area")
    _bounded(st["mass_kg"], 0.1, 1000.0, "structural mass")
    _bounded(st["stiffness_n_per_m"], 1.0, 1e6, "structural stiffness")
    _bounded(st["damping_n_s_per_m"], 0.0, 1e5, "structural damping")
    _bounded(st["maximum_displacement_m"], 1e-4, 0.1, "piston travel domain")
    if st["equilibrium_preload"] != "balances_equilibrium_hydrostatic_pressure":
        raise ValueError("Require an explicit equilibrium pressure preload declaration")
    ini = request["initial"]
    keys(ini, {"transfer_m3", "flow_m3_per_s", "piston_displacement_m", "piston_velocity_m_per_s"})
    for name in ini:
        _bounded(ini[name], -1.0, 1.0, "initial." + name)
    if not st["enabled"] and (ini["piston_displacement_m"] != 0 or ini["piston_velocity_m_per_s"] != 0):
        raise ValueError("Disabled structure requires zero piston displacement and velocity")
    keys(request["forcing"], {"kind", "external_force_n"})
    if request["forcing"]["kind"] != "none" or number(request["forcing"]["external_force_n"]) != 0.0:
        raise ValueError("Only the unforced passive initial-pulse model is qualified")
    clock = request["clock"]
    keys(clock, {"id", "kind", "start_s", "duration_s", "coarse_step_count"})
    if clock["id"] != CLOCK_ID or clock["kind"] != "synthetic_model_time" or number(clock["start_s"]) != 0.0:
        raise ValueError("Require the fixed synthetic model clock starting at zero")
    duration = _bounded(clock["duration_s"], 0.01, 100.0, "duration_s")
    count = clock["coarse_step_count"]
    if type(count) is not int or not 8 <= count <= MAX_COARSE_STEPS:
        raise ValueError("Require 8..1024 coarse time steps")
    rho_g = f["density_kg_per_m3"] * GRAVITY
    inertance = f["density_kg_per_m3"] * co["length_m"] / co["area_m2"]
    frequency_square_bound = rho_g*(1/rs["area1_m2"]+1/rs["area2_m2"])/inertance
    damping_bound = co["resistance_pa_s_per_m3"]/inertance
    if st["enabled"]:
        frequency_square_bound += (st["stiffness_n_per_m"]+rho_g*st["piston_area_m2"]**2/rs["area2_m2"])/st["mass_kg"]
        damping_bound += st["damping_n_s_per_m"]/st["mass_kg"]
    if duration/count * max(math.sqrt(frequency_square_bound), damping_bound) > 0.2:
        raise ValueError("Coarse time step exceeds the declared frequency/damping resolution budget")
    bounds = continuous_bounds(request)
    if bounds["initial_energy_j"] < 1e-12:
        raise ValueError("Require a nonzero pulse with at least 1e-12 J initial energy")
    for index in (1, 2):
        if bounds[f"head{index}_m"] > 0.1 * rs[f"equilibrium_depth{index}_m"]:
            raise ValueError("Initial energy cannot guarantee the continuous small-head domain")
    if bounds["piston_displacement_m"] > st["maximum_displacement_m"]:
        raise ValueError("Initial energy cannot guarantee the continuous piston travel domain")
    if bounds["flow_m3_per_s"]/co["area_m2"] > 10.0 or bounds["piston_velocity_m_per_s"] > 10.0:
        raise ValueError("Initial energy exceeds the declared continuous velocity domain")
    obs = request["desired_observables"]
    known = SUPPORTED_OBSERVABLES | EXPANSION_OBSERVABLES
    if (type(obs) is not list or not 1 <= len(obs) <= len(known)
            or any(type(name) is not str or name not in known for name in obs)
            or len(set(obs)) != len(obs)):
        raise ValueError("Require known nonrepeated bounded observables")
    keys(request["tolerances"], TOLERANCE_KEYS)
    for name, value in request["tolerances"].items():
        _bounded(value, 1e-12, 0.01, "tolerances." + name)
    return deepcopy(request)


def request_digest(request):
    return digest(validate_request(request))


def validate_result(request: dict, result: dict) -> dict:
    """Static structure/seal validation; this does not replay dynamics."""
    request = validate_request(request)
    keys(result, {"schema", "request_digest", "claim_scope", "provider", "method", "clock", "representation", "units", "resolutions", "record_digest"})
    declarations = {"schema": RESULT_SCHEMA, "request_digest": digest(request), "claim_scope": CLAIM_SCOPE,
                    "provider": PROVIDER_ID, "method": METHOD_ID, "clock": request["clock"],
                    "representation": REPRESENTATION, "units": UNITS}
    for name, expected in declarations.items():
        if result[name] != expected:
            raise ValueError("Reservoir result identity or fixed declaration differs: " + name)
    # Validate nested types even when Python treats True and 1 as equal.
    keys(result["clock"], set(request["clock"]))
    if type(result["clock"]["coarse_step_count"]) is not int:
        raise ValueError("Stored model clock step count must be an integer")
    for name in ("start_s", "duration_s"):
        number(result["clock"][name])
    keys(result["representation"], set(REPRESENTATION))
    keys(result["units"], set(UNITS))
    keys(result["resolutions"], set(RESOLUTION_FACTORS))
    for label, factor in RESOLUTION_FACTORS.items():
        row = result["resolutions"][label]
        keys(row, {"dt_s", "step_count", "trace"})
        count = request["clock"]["coarse_step_count"] * factor
        if type(row["step_count"]) is not int or row["step_count"] != count:
            raise ValueError("Stored refinement count differs from fixed 1/2/4 levels")
        dt = request["clock"]["duration_s"] / count
        if number(row["dt_s"]) != dt:
            raise ValueError("Stored refinement time step differs")
        trace = row["trace"]
        keys(trace, set(STATE_FIELDS))
        for field, values in trace.items():
            if type(values) is not list or len(values) != count + 1:
                raise ValueError("Reservoir arrays must cover every declared time node")
            for value in values:
                _bounded(value, -1e12, 1e12, field + " sample")
        if trace["time_s"] != [i*dt for i in range(count+1)]:
            raise ValueError("Stored reservoir time nodes differ from the model clock")
        for field in ("reservoir1_volume_m3", "reservoir2_column_volume_m3", "total_liquid_volume_m3", "total_liquid_mass_kg"):
            if any(value <= 0 for value in trace[field]):
                raise ValueError("Retained reservoir volumes and mass must be positive")
        for field in ("fluid_energy_j", "structure_energy_j", "total_energy_j", "fluid_dissipation_j", "structure_dissipation_j"):
            if any(value < 0 for value in trace[field]):
                raise ValueError("Retained energies and dissipations must be nonnegative")
        if any(value != 0.0 for value in trace["external_work_j"]):
            raise ValueError("Unforced profile requires identically zero external work")
        for field in ("fluid_dissipation_j", "structure_dissipation_j"):
            if trace[field][0] != 0.0 or any(b<a for a,b in zip(trace[field],trace[field][1:])):
                raise ValueError("Stored cumulative dissipation must start at zero and be monotone")
    check_seal(result)
    return deepcopy(result)


def example_request():
    return {
        "schema": REQUEST_SCHEMA, "scope": CLAIM_SCOPE,
        "source": {"kind": "synthetic", "source_ref": "fluid.reservoir.default_initial_head_pulse"},
        "fluid": {"density_kg_per_m3": 1000.0, "gravity_m_per_s2": GRAVITY, "compressibility": "incompressible"},
        "reservoirs": {"area1_m2": 0.1, "area2_m2": 0.12, "equilibrium_depth1_m": 0.5,
                       "equilibrium_depth2_m": 0.6, "maximum_head_fraction": 0.1},
        "connector": {"length_m": 1.0, "area_m2": 0.002, "resistance_pa_s_per_m3": 20000.0},
        "structure": {"enabled": True, "piston_area_m2": 0.01, "mass_kg": 5.0,
                      "stiffness_n_per_m": 200.0, "damping_n_s_per_m": 0.5,
                      "maximum_displacement_m": 0.1,
                      "equilibrium_preload": "balances_equilibrium_hydrostatic_pressure"},
        "initial": {"transfer_m3": -0.001, "flow_m3_per_s": 0.0,
                    "piston_displacement_m": 0.0, "piston_velocity_m_per_s": 0.0},
        "forcing": {"kind": "none", "external_force_n": 0.0},
        "clock": {"id": CLOCK_ID, "kind": "synthetic_model_time", "start_s": 0.0,
                  "duration_s": 4.0, "coarse_step_count": 400},
        "desired_observables": sorted(SUPPORTED_OBSERVABLES),
        "tolerances": {"equations_relative": 1e-9, "balance_relative": 1e-9,
                       "reference_relative": 1e-3, "refinement_relative": 1e-3},
    }
