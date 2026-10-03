"""Bounded structureless-site classical dynamics; reduced Lennard-Jones units.

This is a synthetic model, not a water force field or an SPH representation.
The force-shifted potential and unit convention follow the primary references:
https://docs.lammps.org/pair_lj_smooth_linear.html
https://docs.lammps.org/units.html
All optional SI scales are declarations, not calibrated material parameters.
Static validators never propagate particles or evaluate pair interactions.
"""
from __future__ import annotations

from copy import deepcopy
import math

from .control_contracts import json_tree, keys, number
from .operations.runner import check_seal, digest

REQUEST_SCHEMA = "ciw.fluid-molecular-request.v1"
RESULT_SCHEMA = "ciw.fluid-molecular-result.v1"
REPORT_SCHEMA = "ciw.fluid-molecular-verification.v1"
CLAIM_SCOPE = "periodic_classical_structureless_site_force_shifted_lennard_jones"
REPRESENTATION = "three-dimensional classical atomistic interaction sites in reduced Lennard-Jones units"
PARTICLE_SEMANTICS = "structureless_atomistic_interaction_site"
OPERATION_ID = "fluid.molecular.simulate.v1"
VERIFY_OPERATION_ID = "fluid.molecular.verify.v1"
PROVIDER_ID = "ciw.fluid-molecular-provider.v1"
SOLVER_ID = "pairwise_force_shifted_lj_velocity_verlet_binary64"
TRACE_LABELS = ("primary", "time_refined", "time_fine")
CLOCK = {"owner": PROVIDER_ID, "clock_id": "fluid-molecular-model-clock",
         "time_origin_reduced": 0.0, "time_basis": "elapsed_reduced_lj_model_time",
         "externally_synchronized": False}
UNITS = {"time_reduced": "tau=sigma*sqrt(m/epsilon)", "positions_reduced": "sigma",
         "velocities_reduced": "sqrt(epsilon/m)", "forces_reduced": "epsilon/sigma",
         "kinetic_energy_reduced": "epsilon", "potential_energy_reduced": "epsilon",
         "total_energy_reduced": "epsilon", "momentum_reduced": "sqrt(m*epsilon)",
         "number_density_reduced": "1/sigma^3", "kinetic_temperature_reduced": "epsilon/k_B",
         "virial_pressure_reduced": "epsilon/sigma^3", "minimum_separation_reduced": "sigma"}
VECTOR_FIELDS = ("positions_reduced", "velocities_reduced", "forces_reduced")
SCALAR_FIELDS = ("kinetic_energy_reduced", "potential_energy_reduced", "total_energy_reduced",
                 "number_density_reduced", "kinetic_temperature_reduced", "virial_pressure_reduced",
                 "minimum_separation_reduced")
SUPPORTED_OBSERVABLES = {"atomistic_site_trajectory", "pair_interactions", "energy_accounting",
                         "momentum_balance", "numerical_convergence", "toy_number_density",
                         "toy_kinetic_temperature", "toy_virial_pressure"}
EXPANSION_OBSERVABLES = {"water_molecules", "polymer_chains", "quantum_chemistry", "sph_particles",
                         "suspended_grains", "molecular_to_continuum_mapping", "viscosity",
                         "thermal_conductivity", "diffusivity", "equilibrium_statistics",
                         "certified_transport_parameters", "material_calibration",
                         "fluid_structure_interaction"}
REFUSED_OBSERVABLES = {"experimental_validation", "certified_design", "canonical_state_admission"}
TOLERANCE_KEYS = {"reference_normalized", "reference_refinement_normalized", "energy_relative",
                  "momentum_normalized", "refinement_normalized", "force_gradient_normalized"}
MIN_SEPARATION = 0.85
MAX_SITE_STEPS = 2048


def _bounded(value, lower, upper, label):
    value = number(value)
    if not lower <= value <= upper:
        raise ValueError(f"{label} must be inside {lower}..{upper}")
    return value


def _vectors(values, count, bound, label):
    if type(values) is not list or len(values) != count:
        raise ValueError(f"{label} must retain exactly {count} particle vectors")
    for row in values:
        if type(row) is not list or len(row) != 3:
            raise ValueError(f"{label} requires three components per site")
        for value in row:
            _bounded(value, -bound, bound, label)


def trace_declarations(request):
    steps = request["integration"]["steps"]
    return tuple((label, steps * factor) for label, factor in zip(TRACE_LABELS, (1, 2, 4)))


def validate_request(request):
    json_tree(request)
    keys(request, {"schema", "scope", "model", "integration", "clock", "si_scaling", "desired_observables", "tolerances"})
    if request["schema"] != REQUEST_SCHEMA or request["scope"] != CLAIM_SCOPE:
        raise ValueError("Unsupported molecular request schema or physical scope")
    keys(request["clock"], set(CLOCK))
    if request["clock"] != CLOCK or type(request["clock"]["externally_synchronized"]) is not bool:
        raise ValueError("Molecular provider must own its elapsed reduced-LJ clock")
    number(request["clock"]["time_origin_reduced"])
    model = request["model"]
    keys(model, {"particle_semantics", "boundary", "potential", "site_mass_reduced", "sigma_reduced",
                 "epsilon_reduced", "box_length_reduced", "cutoff_reduced", "positions_reduced", "velocities_reduced"})
    if (model["particle_semantics"] != PARTICLE_SEMANTICS or model["boundary"] != "periodic_cubic_minimum_image"
            or model["potential"] != "force_shifted_lennard_jones_12_6"):
        raise ValueError("Require structureless atomistic sites and the fixed periodic force-shifted LJ potential")
    for field in ("site_mass_reduced", "sigma_reduced", "epsilon_reduced"):
        if number(model[field]) != 1.0:
            raise ValueError("Reduced LJ mass, sigma and epsilon must each equal one")
    box = _bounded(model["box_length_reduced"], 5.1, 20.0, "box_length_reduced")
    cutoff = _bounded(model["cutoff_reduced"], 1.5, 2.5, "cutoff_reduced")
    if cutoff >= 0.5 * box:
        raise ValueError("Short-range cutoff must be strictly below half the periodic box")
    positions = model["positions_reduced"]
    if type(positions) is not list or not 2 <= len(positions) <= 32:
        raise ValueError("Require 2..32 structureless sites")
    count = len(positions)
    _vectors(positions, count, box, "initial positions")
    if any(value < 0.0 or value >= box for row in positions for value in row):
        raise ValueError("Initial positions must lie in the half-open periodic box")
    _vectors(model["velocities_reduced"], count, 2.0, "initial velocities")
    # Geometry-only hard overlap guard, independent of tolerances and propagation.
    for i in range(count):
        for j in range(i):
            distance_squared = sum((positions[i][d] - positions[j][d] - box *
                round((positions[i][d] - positions[j][d]) / box)) ** 2 for d in range(3))
            if distance_squared < 1.0:
                raise ValueError("Initial minimum-image separation must be at least one sigma")
    integration = request["integration"]
    keys(integration, {"method", "steps", "duration_reduced", "time_refinement_factor"})
    if integration["method"] != "velocity_verlet" or type(integration["time_refinement_factor"]) is not int or integration["time_refinement_factor"] != 2:
        raise ValueError("Require velocity Verlet and exact integer twofold refinements")
    steps = integration["steps"]
    if type(steps) is not int or not 32 <= steps <= 256 or count * steps > MAX_SITE_STEPS:
        raise ValueError("Require 32..256 steps inside the bounded site/time allocation")
    duration = _bounded(integration["duration_reduced"], 0.01, 0.5, "duration_reduced")
    if duration / steps > 0.004:
        raise ValueError("Hard primary reduced timestep must not exceed 0.004")
    scaling = request["si_scaling"]
    if scaling is not None:
        keys(scaling, {"sigma_m", "epsilon_j", "site_mass_kg", "parameter_status"})
        _bounded(scaling["sigma_m"], 1e-11, 1e-8, "sigma_m")
        _bounded(scaling["epsilon_j"], 1e-24, 1e-18, "epsilon_j")
        _bounded(scaling["site_mass_kg"], 1e-28, 1e-23, "site_mass_kg")
        if scaling["parameter_status"] != "declared_unvalidated_scales":
            raise ValueError("SI scales must retain their unvalidated declaration status")
    keys(request["tolerances"], TOLERANCE_KEYS)
    for field, value in request["tolerances"].items():
        _bounded(value, 1e-13, 0.1, "tolerances." + field)
    desired = request["desired_observables"]
    known = SUPPORTED_OBSERVABLES | EXPANSION_OBSERVABLES | REFUSED_OBSERVABLES
    if (type(desired) is not list or not 1 <= len(desired) <= 24 or
            any(type(item) is not str or item not in known for item in desired) or len(set(desired)) != len(desired)):
        raise ValueError("Require bounded unique known molecular observables")
    return deepcopy(request)


def validate_result(request, result):
    request = validate_request(request)
    json_tree(result)
    keys(result, {"schema", "request_digest", "claim_scope", "representation", "provider", "solver", "units", "clock",
                  "si_scaling", "record_digest"} | set(TRACE_LABELS))
    expected = {"schema": RESULT_SCHEMA, "request_digest": digest(request), "claim_scope": CLAIM_SCOPE,
                "representation": REPRESENTATION, "provider": PROVIDER_ID, "solver": SOLVER_ID,
                "units": UNITS, "clock": CLOCK, "si_scaling": request["si_scaling"]}
    if any(result[key] != value for key, value in expected.items()):
        raise ValueError("Molecular result identity, representation, units, clock or scaling differs")
    keys(result["clock"], set(CLOCK))
    number(result["clock"]["time_origin_reduced"])
    if type(result["clock"]["externally_synchronized"]) is not bool:
        raise ValueError("Clock synchronization flag requires a boolean")
    count, box = len(request["model"]["positions_reduced"]), request["model"]["box_length_reduced"]
    for label, steps in trace_declarations(request):
        trace = result[label]
        keys(trace, {"steps", "dt_reduced", "time_reduced", "momentum_reduced"} | set(VECTOR_FIELDS) | set(SCALAR_FIELDS))
        dt = request["integration"]["duration_reduced"] / steps
        if type(trace["steps"]) is not int or trace["steps"] != steps or number(trace["dt_reduced"]) != dt:
            raise ValueError("Molecular refinement clock declaration differs")
        if trace["time_reduced"] != [index * dt for index in range(steps + 1)]:
            raise ValueError("Molecular times must follow the exact owned finite grid")
        for value in trace["time_reduced"]:
            number(value)
        for field in VECTOR_FIELDS:
            values = trace[field]
            if type(values) is not list or len(values) != steps + 1:
                raise ValueError("Molecular vector histories must cover every declared time")
            bound = 2.0 * box if field == "positions_reduced" else 5.0 if field == "velocities_reduced" else 1e5
            for row in values:
                _vectors(row, count, bound, field)
        _vectors(trace["momentum_reduced"], steps + 1, 160.0, "momentum")
        for field in SCALAR_FIELDS:
            values = trace[field]
            if type(values) is not list or len(values) != steps + 1:
                raise ValueError("Molecular scalar histories must cover every declared time")
            for value in values:
                _bounded(value, -1e6, 1e6, field)
        if any(value < MIN_SEPARATION for value in trace["minimum_separation_reduced"]):
            raise ValueError("Retained molecular trajectory violates the hard overlap domain")
        if (trace["positions_reduced"][0] != request["model"]["positions_reduced"] or
                trace["velocities_reduced"][0] != request["model"]["velocities_reduced"]):
            raise ValueError("Molecular trajectory changed its declared initial state")
    check_seal(result)
    return deepcopy(result)


def length_scale_m(request):
    scaling = request["si_scaling"]
    return None if scaling is None else request["model"]["box_length_reduced"] * scaling["sigma_m"]


def time_scale_s(request):
    scaling = request["si_scaling"]
    return None if scaling is None else request["integration"]["duration_reduced"] * scaling["sigma_m"] * math.sqrt(scaling["site_mass_kg"] / scaling["epsilon_j"])


def preservation_scope(request):
    return {"representation": REPRESENTATION, "particle_meaning": PARTICLE_SEMANTICS,
            "spatial_detail": "finite three-dimensional site positions and velocities; periodic minimum-image pair interactions",
            "vertical_detail": "three Cartesian coordinates per site; no continuum vertical velocity field",
            "clock": "provider-owned elapsed reduced-LJ time; optional declared SI time scale",
            "receiver_coupling": "none; isolated periodic atomistic site system",
            "physical_validity": "classical short-range force-shifted LJ toy model; finite numerical and overlap domain only",
            "molecular_scope": "structureless interaction sites; no chemical identity, bonded structure, water model, validated material or continuum reduction"}


def example_request():
    positions = [[2.0 + 1.45 * i, 2.0 + 1.45 * j, 2.0 + 1.45 * k]
                 for i in range(2) for j in range(2) for k in range(2)]
    velocities = [[0.12 * (2 * i - 1), 0.08 * (2 * j - 1), 0.04 * (2 * k - 1)]
                  for i in range(2) for j in range(2) for k in range(2)]
    return {"schema": REQUEST_SCHEMA, "scope": CLAIM_SCOPE, "clock": deepcopy(CLOCK), "si_scaling": None,
            "model": {"particle_semantics": PARTICLE_SEMANTICS, "boundary": "periodic_cubic_minimum_image",
                      "potential": "force_shifted_lennard_jones_12_6", "site_mass_reduced": 1.0,
                      "sigma_reduced": 1.0, "epsilon_reduced": 1.0, "box_length_reduced": 6.0,
                      "cutoff_reduced": 2.5, "positions_reduced": positions, "velocities_reduced": velocities},
            "integration": {"method": "velocity_verlet", "steps": 64, "duration_reduced": 0.2, "time_refinement_factor": 2},
            "desired_observables": sorted(SUPPORTED_OBSERVABLES),
            "tolerances": {"reference_normalized": 2e-5, "reference_refinement_normalized": 1e-8,
                           "energy_relative": 1e-5, "momentum_normalized": 1e-12,
                           "refinement_normalized": 2e-5, "force_gradient_normalized": 1e-7}}
