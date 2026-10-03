"""Bounded moving computational parcels: periodic 1D barotropic WCSPH.

The parcels carry continuum mass, not molecule or suspended-grain identities.
One dimensional kernel density is divided by the declared cross-sectional
area to retain kg/m^3. Fixed h=2*dx has exact uniform-lattice normalization.
"""
from copy import deepcopy
import math

from .control_contracts import keys, number
from .operations.runner import check_seal, digest

REQUEST_SCHEMA = "ciw.fluid-sph-request.v1"
RESULT_SCHEMA = "ciw.fluid-sph-result.v1"
REPORT_SCHEMA = "ciw.fluid-sph-verification.v1"
CLAIM_SCOPE = "periodic_one_dimensional_low_mach_barotropic_computational_parcels"
PROVIDER_ID = "ciw.fluid-sph-provider.v1"
METHOD_ID = "fixed_h_conservative_density_sum_velocity_verlet_binary64"
OPERATION_ID = "fluid.sph.simulate.v1"
VERIFY_OPERATION_ID = "fluid.sph.verify.v1"
REPRESENTATION = {"scale": "mesoscopic_computational_parcel", "particle_semantics": "equal_mass_sph_continuum_parcel",
                  "wave_semantics": "barotropic_acoustic_pressure_wave", "dimensions": 1,
                  "kernel": "normalized_one_dimensional_cubic_bspline", "support_radius_over_h": 2,
                  "smoothing_length_over_lattice_spacing": 2, "boundary": "periodic",
                  "density_method": "mass_kernel_sum_divided_by_cross_section_area",
                  "equation_of_state": "p=c^2*(rho-rho0)", "molecular_identity": False}
SUPPORTED_OBSERVABLES = {"sph_computational_parcels", "acoustic_pressure_wave", "parcel_trajectory", "density_sum",
                         "pressure", "momentum_balance", "energy_accounting", "numerical_convergence"}
EXPANSION_OBSERVABLES = {"surface_gravity_wave", "free_surface", "breaking_waves", "shock", "turbulence",
                         "viscosity", "adaptive_smoothing_length", "three_dimensional_flow", "suspended_grains",
                         "molecular_response", "fluid_structure_interaction", "heat_transfer"}
REFUSED_OBSERVABLES = {"experimental_validation", "certified_design", "canonical_state_admission"}
FIELD_NAMES = ("unwrapped_position_m", "velocity_m_per_s", "density_kg_per_m3", "pressure_pa")
LABELS = ("primary", "time_refined", "time_fine", "spatial_refined", "spatial_fine")
UNITS = {"time_s": "s", "unwrapped_position_m": "m", "velocity_m_per_s": "m/s",
         "density_kg_per_m3": "kg/m^3", "pressure_pa": "Pa", "parcel_mass_kg": "kg",
         "smoothing_length_m": "m", "total_energy_j": "J", "total_momentum_kg_m_per_s": "kg*m/s"}
TOLERANCE_KEYS = {"reference_normalized", "analytic_normalized", "momentum_relative", "energy_relative",
                  "gradient_relative", "time_refinement_normalized", "spatial_refinement_normalized"}
CLOCK_OWNER = "fluid-sph-model-clock"


def _bound(v, a, b, name):
    v = number(v)
    if not a <= v <= b:
        raise ValueError(f"{name} must be inside {a}..{b}")
    return v


def validate_request(request):
    keys(request, {"schema", "scope", "model", "integration", "clock", "desired_observables", "tolerances"})
    if request["schema"] != REQUEST_SCHEMA or request["scope"] != CLAIM_SCOPE:
        raise ValueError("Unsupported SPH physical scope or schema")
    model = request["model"]
    keys(model, {"length_m", "area_m2", "reference_density_kg_per_m3", "sound_speed_m_per_s", "strain_amplitude",
                 "initial_profile", "particle_semantics", "kernel", "eos", "boundary"})
    length = _bound(model["length_m"], 0.1, 100.0, "length_m")
    _bound(model["area_m2"], 1e-4, 10.0, "area_m2")
    _bound(model["reference_density_kg_per_m3"], 500.0, 2000.0, "reference_density_kg_per_m3")
    c = _bound(model["sound_speed_m_per_s"], 1.0, 2000.0, "sound_speed_m_per_s")
    _bound(model["strain_amplitude"], 1e-5, 5e-4, "strain_amplitude")
    declarations = {"initial_profile": "small_right_travelling_material_sine",
                    "particle_semantics": "equal_mass_sph_continuum_parcel", "kernel": "cubic_bspline_1d_fixed_h_2dx",
                    "eos": "linear_barotropic_acoustic", "boundary": "periodic"}
    if any(model[key] != value for key, value in declarations.items()):
        raise ValueError("Require the fixed conservative computational parcel, kernel, EOS and periodic profile")
    integration = request["integration"]
    keys(integration, {"method", "particles", "steps", "duration_s"})
    if integration["method"] != "velocity_verlet":
        raise ValueError("Require the fixed velocity-Verlet SPH provider")
    n, steps = integration["particles"], integration["steps"]
    if type(n) is not int or n not in (32, 64):
        raise ValueError("particles must be the exact integer 32 or 64")
    if type(steps) is not int or not 32 <= steps <= 128 or n * steps > 4096:
        raise ValueError("Require integer 32..128 steps and base particle-time budget <=4096")
    horizon = _bound(integration["duration_s"], 0.05 * length / c, 0.125 * length / c, "duration_s")
    if c * horizon / steps / (2.0 * length / n) > 0.1:
        raise ValueError("Hard acoustic timestep requires sound_speed*dt/h <=0.1")
    clock = request["clock"]
    keys(clock, {"owner", "origin_s", "time_basis", "externally_synchronized"})
    if (clock["owner"] != CLOCK_OWNER or number(clock["origin_s"]) != 0.0
            or clock["time_basis"] != "elapsed_synthetic_model_time" or clock["externally_synchronized"] is not False):
        raise ValueError("SPH owns its zero-origin elapsed model clock")
    keys(request["tolerances"], TOLERANCE_KEYS)
    for key, value in request["tolerances"].items():
        _bound(value, 1e-12, 0.1, "tolerances." + key)
    observables = request["desired_observables"]
    known = SUPPORTED_OBSERVABLES | EXPANSION_OBSERVABLES | REFUSED_OBSERVABLES
    if (type(observables) is not list or not 1 <= len(observables) <= 24
            or any(type(v) is not str or v not in known for v in observables) or len(set(observables)) != len(observables)):
        raise ValueError("Require unique bounded known SPH observables")
    return deepcopy(request)


def grid_declarations(request):
    n, steps = request["integration"]["particles"], request["integration"]["steps"]
    return (("primary", n, steps), ("time_refined", n, 2 * steps), ("time_fine", n, 4 * steps),
            ("spatial_refined", 2 * n, 4 * steps), ("spatial_fine", 4 * n, 4 * steps))


def initial_state(request, n):
    model = request["model"]
    length, amplitude, c = model["length_m"], model["strain_amplitude"], model["sound_speed_m_per_s"]
    k = 2.0 * math.pi / length
    q = [(index + 0.5) * length / n for index in range(n)]
    return ([x - amplitude / k * math.sin(k * x) for x in q], [c * amplitude * math.cos(k * x) for x in q])


def _array(values, count):
    if type(values) is not list or len(values) != count:
        raise ValueError("SPH array differs from the declared parcel/time allocation")
    for value in values:
        if abs(number(value)) > 1e30:
            raise ValueError("SPH sample exceeds the finite data bound")


def validate_result(request, result):
    request = validate_request(request)
    keys(result, {"schema", "request_digest", "claim_scope", "provider", "method", "clock", "representation", "units",
                  "resolutions", "record_digest"})
    if (result["schema"] != RESULT_SCHEMA or result["request_digest"] != digest(request) or result["claim_scope"] != CLAIM_SCOPE
            or result["provider"] != PROVIDER_ID or result["method"] != METHOD_ID or result["clock"] != request["clock"]
            or result["representation"] != REPRESENTATION or result["units"] != UNITS):
        raise ValueError("SPH result identity, representation, units or clock differs")
    keys(result["clock"], set(request["clock"]))
    number(result["clock"]["origin_s"])
    if result["clock"]["externally_synchronized"] is not False:
        raise ValueError("SPH clock synchronization must be a strict boolean")
    keys(result["representation"], set(REPRESENTATION))
    for key in ("dimensions", "support_radius_over_h", "smoothing_length_over_lattice_spacing"):
        if type(result["representation"][key]) is not int:
            raise ValueError("SPH representation integers must retain strict types")
    if result["representation"]["molecular_identity"] is not False:
        raise ValueError("SPH computational parcels have no molecular identity")
    keys(result["resolutions"], set(LABELS))
    model = request["model"]
    for label, n, steps in grid_declarations(request):
        trace = result["resolutions"][label]
        keys(trace, {"particles", "steps", "dt_s", "smoothing_length_m", "parcel_mass_kg", "time_s",
                     "total_energy_j", "total_momentum_kg_m_per_s"} | set(FIELD_NAMES))
        if (type(trace["particles"]) is not int or trace["particles"] != n
                or type(trace["steps"]) is not int or trace["steps"] != steps):
            raise ValueError("SPH resolution differs from the declared refinement")
        dt, h = request["integration"]["duration_s"] / steps, 2.0 * model["length_m"] / n
        mass = model["reference_density_kg_per_m3"] * model["area_m2"] * model["length_m"] / n
        if number(trace["dt_s"]) != dt or number(trace["smoothing_length_m"]) != h or number(trace["parcel_mass_kg"]) != mass:
            raise ValueError("SPH mass, smoothing length or owned timestep differs")
        for field in ("time_s", "total_energy_j", "total_momentum_kg_m_per_s"):
            _array(trace[field], steps + 1)
        if trace["time_s"] != [index * dt for index in range(steps + 1)]:
            raise ValueError("SPH trace changed the ordered model clock")
        for field in FIELD_NAMES:
            if type(trace[field]) is not list or len(trace[field]) != steps + 1:
                raise ValueError("SPH fields must be time by parcel")
            for row in trace[field]:
                _array(row, n)
        initial_x, initial_v = initial_state(request, n)
        if trace["unwrapped_position_m"][0] != initial_x or trace["velocity_m_per_s"][0] != initial_v:
            raise ValueError("SPH result changed its declared moving-parcel initial state")
    check_seal(result)
    return deepcopy(result)


def preservation_scope(request):
    validate_request(request)
    return {"representation": "one-dimensional periodic barotropic smoothed computational continuum parcels",
            "particle_meaning": "equal-mass SPH computational parcel; neither molecule nor suspended grain",
            "spatial_detail": "moving material parcels; fixed compact cubic kernel; periodic minimum-image distances",
            "vertical_detail": "one-dimensional acoustic motion with declared cross-section; no vertical or free-surface structure",
            "clock": "provider-owned elapsed synthetic model time; explicit fixed Verlet steps",
            "receiver_coupling": "none; no deformable structure or general external boundary coupling",
            "physical_validity": "low-Mach small-density-perturbation short-time barotropic acoustic benchmark with ordered parcels",
            "molecular_scope": "not represented; no molecular reduction or preservation witness"}


def length_scale_m(request):
    return validate_request(request)["model"]["length_m"]


def time_scale_s(request):
    return validate_request(request)["integration"]["duration_s"]


def example_request():
    return {"schema": REQUEST_SCHEMA, "scope": CLAIM_SCOPE,
            "model": {"length_m": 1.0, "area_m2": 0.01, "reference_density_kg_per_m3": 1000.0,
                      "sound_speed_m_per_s": 10.0, "strain_amplitude": 1e-4,
                      "initial_profile": "small_right_travelling_material_sine", "particle_semantics": "equal_mass_sph_continuum_parcel",
                      "kernel": "cubic_bspline_1d_fixed_h_2dx", "eos": "linear_barotropic_acoustic", "boundary": "periodic"},
            "integration": {"method": "velocity_verlet", "particles": 32, "steps": 32, "duration_s": 0.0125},
            "clock": {"owner": CLOCK_OWNER, "origin_s": 0.0, "time_basis": "elapsed_synthetic_model_time", "externally_synchronized": False},
            "desired_observables": sorted(SUPPORTED_OBSERVABLES),
            "tolerances": {"reference_normalized": 0.001, "analytic_normalized": 0.05, "momentum_relative": 1e-10,
                           "energy_relative": 1e-5, "gradient_relative": 1e-5,
                           "time_refinement_normalized": 0.001, "spatial_refinement_normalized": 0.05}}
