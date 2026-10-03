"""Strict SI contract for a resolved 1-D gravity-wave/compliant-wall benchmark.

The qualified benchmark is an unforced single continuous coupled eigenmode.
A damper slot is explicit but its nonzero coefficient remains unqualified.
Structural reads bind finite declarations without executing the solver/reference.
"""
from copy import deepcopy
import math

from .control_contracts import keys, number
from .operations.runner import check_seal, digest

REQUEST_SCHEMA = "ciw.fluid-fsi-request.v1"
RESULT_SCHEMA = "ciw.fluid-fsi-result.v1"
REPORT_SCHEMA = "ciw.fluid-fsi-verification.v1"
OPERATION_ID = "fluid.fsi.simulate.v1"
VERIFY_OPERATION_ID = "fluid.fsi.verify.v1"
CLAIM_SCOPE = "linear_shallow_water_compliant_endwall_coupled_eigenmode"
PROVIDER_ID = "ciw.fluid-fsi-provider.v1"
SOLVER_ID = "monolithic_staggered_finite_volume_midpoint_modal_binary64"
INITIAL_PROFILE = "continuous_fundamental_coupled_eigenmode_at_maximum_displacement"
CLOCK = {"owner": PROVIDER_ID, "clock_id": "fluid-fsi-model-clock", "time_origin_s": 0.0,
         "time_basis": "elapsed_model_time", "externally_synchronized": False}
REPRESENTATION = {"kind": "resolved_1d_linear_shallow_water_with_compliant_endwall",
                  "particle_meaning": "none", "elevation_semantics": "cell_average_perturbation_from_equilibrium",
                  "velocity_semantics": "depth_averaged_horizontal_velocity_on_faces",
                  "boundary": "fixed_left_wall_and_preloaded_compliant_right_wall",
                  "interface": "work_conjugate_physical_traction_and_shared_wall_velocity",
                  "wall_fluid_inertia": "half_dual_cell_belongs_to_fluid_energy",
                  "clock_owner": PROVIDER_ID}
TRACE_LABELS = ("primary", "time_refined", "time_fine", "spatial_refined", "spatial_fine")
FIELD_NAMES = ("free_surface_elevation_m", "depth_averaged_velocity_m_per_s", "volume_flux_m3_per_s", "bottom_gauge_pressure_pa")
SCALAR_NAMES = ("wall_displacement_m", "wall_velocity_m_per_s", "wall_acceleration_m_per_s2",
                "boundary_elevation_m", "boundary_pressure_deviation_pa", "fluid_force_on_structure_n",
                "structure_force_on_fluid_n", "column_volume_m3", "wall_swept_volume_m3", "liquid_volume_m3",
                "liquid_mass_kg", "fluid_energy_j", "structure_energy_j", "total_energy_j",
                "fluid_interface_work_j", "structure_interface_work_j", "structure_dissipation_j", "external_work_j")
UNITS = {"time_s": "s", "cell_x_m": "m", "face_x_m": "m", "dx_m": "m", "dt_s": "s",
         "free_surface_elevation_m": "m", "depth_averaged_velocity_m_per_s": "m/s", "volume_flux_m3_per_s": "m^3/s",
         "bottom_gauge_pressure_pa": "Pa", "wall_displacement_m": "m", "wall_velocity_m_per_s": "m/s",
         "wall_acceleration_m_per_s2": "m/s^2", "boundary_elevation_m": "m", "boundary_pressure_deviation_pa": "Pa",
         "fluid_force_on_structure_n": "N", "structure_force_on_fluid_n": "N", "column_volume_m3": "m^3",
         "wall_swept_volume_m3": "m^3", "liquid_volume_m3": "m^3", "liquid_mass_kg": "kg",
         "fluid_energy_j": "J", "structure_energy_j": "J", "total_energy_j": "J",
         "fluid_interface_work_j": "J", "structure_interface_work_j": "J", "structure_dissipation_j": "J", "external_work_j": "J"}
SUPPORTED_OBSERVABLES = {"surface_gravity_wave", "free_surface_elevation", "depth_averaged_velocity", "volume_flux",
                         "hydrostatic_bottom_pressure", "fluid_structure_interaction", "structural_displacement",
                         "interface_force", "interface_work", "mass_balance", "energy_accounting", "numerical_convergence"}
EXPANSION_OBSERVABLES = {"structural_damping", "nonlinear_flow", "breaking_waves", "wetting_drying", "turbulence",
                         "viscous_dissipation", "resolved_vertical_velocity", "three_dimensional_cfd", "external_cfd_adapter",
                         "molecular_response", "sph_particles", "material_failure", "external_forcing"}
REFUSED_OBSERVABLES = {"experimental_validation", "certified_design", "canonical_state_admission"}
TOLERANCE_KEYS = {"equations_relative", "mass_relative", "energy_relative", "analytic_normalized",
                  "time_refinement_normalized", "spatial_refinement_normalized"}
MAX_BASE_SPACE_TIME_POINTS = 1024
MAX_ELEVATION_DEPTH_FRACTION = 0.01
MAX_WALL_LENGTH_FRACTION = 0.001


def _bounded(value,lo,hi,name):
    value=number(value)
    if not lo<=value<=hi:
        raise ValueError(f"{name} must be inside {lo}..{hi}")
    return value


def length_m(request):
    return request["model"]["length_m"]


def duration_s(request):
    return request["integration"]["duration_s"]


def length_scale_m(request):
    return length_m(request)


def time_scale_s(request):
    return duration_s(request)


def wave_speed_m_per_s(model):
    return math.sqrt(model["gravity_m_per_s2"]*model["depth_m"])


def mode_parameters(request):
    """Algebraic declared initial mode; no finite-volume propagation occurs."""
    model,wall=request["model"],request["structure"]
    length,depth,width,rho,g=(model[name] for name in ("length_m","depth_m","width_m","density_kg_per_m3","gravity_m_per_s2"))
    mu=wall["mass_kg"]/(rho*width*depth*length)
    kappa=wall["stiffness_n_per_m"]*length/(rho*g*width*depth*depth)
    lo,hi=1e-10,math.pi
    for _ in range(80):
        z=(lo+hi)/2
        value=(mu*z*z-kappa)*math.sin(z)-z*math.cos(z)
        if value>0: hi=z
        else: lo=z
    z=(lo+hi)/2
    k=z/length
    omega=wave_speed_m_per_s(model)*k
    return {"dimensionless_wavenumber":z,"wavenumber_per_m":k,"angular_frequency_per_s":omega,
            "wall_amplitude_m":abs(model["amplitude_m"]*math.sin(z)/(depth*k)),
            "mass_ratio":mu,"stiffness_ratio":kappa}


def trace_declarations(request):
    n,s=request["integration"]["cells"],request["integration"]["steps"]
    return (("primary",n,s),("time_refined",n,2*s),("time_fine",n,4*s),("spatial_refined",2*n,4*s),("spatial_fine",4*n,4*s))


def initial_displacement(request,position):
    mode=mode_parameters(request)
    return -request["model"]["amplitude_m"]*math.sin(mode["wavenumber_per_m"]*position)/(request["model"]["depth_m"]*mode["wavenumber_per_m"])


def preservation_scope(request):
    return {"representation":"one-dimensional linear shallow-water gravity-wave channel with a preloaded compliant endwall",
            "particle_meaning":"none", "spatial_detail":"finite staggered horizontal cells and faces; cell-average elevation and face velocity",
            "vertical_detail":"hydrostatic pressure and depth-averaged horizontal velocity; resolved vertical flow absent",
            "clock":"provider-owned elapsed synthetic model time; monolithic synchronous implicit midpoint coupling",
            "receiver_coupling":"one undamped preloaded spring-mass endwall; equal opposite traction and interface work; shared boundary velocity",
            "physical_validity":"unforced fundamental coupled eigenmode; hard small-amplitude, long-wave and bounded wall-travel limits",
            "molecular_scope":"not represented; no molecular reduction or cross-scale preservation witness"}


def validate_request(request):
    keys(request,{"schema","scope","model","structure","integration","clock","desired_observables","tolerances"})
    if request["schema"]!=REQUEST_SCHEMA or request["scope"]!=CLAIM_SCOPE:
        raise ValueError("Unsupported compliant-endwall request schema or scope")
    keys(request["clock"],set(CLOCK))
    if request["clock"]!=CLOCK or type(request["clock"]["externally_synchronized"]) is not bool:
        raise ValueError("The FSI provider must own its exact synthetic model clock")
    number(request["clock"]["time_origin_s"])
    model=request["model"]
    keys(model,{"length_m","depth_m","width_m","density_kg_per_m3","gravity_m_per_s2","amplitude_m","initial_profile","boundary","particle_semantics"})
    length=_bounded(model["length_m"],1.0,1000.0,"length_m")
    depth=_bounded(model["depth_m"],0.01,10.0,"depth_m")
    width=_bounded(model["width_m"],0.01,100.0,"width_m")
    rho=_bounded(model["density_kg_per_m3"],500.0,2000.0,"density")
    g=_bounded(model["gravity_m_per_s2"],1.0,20.0,"gravity")
    amplitude=_bounded(model["amplitude_m"],1e-8,0.01,"amplitude")
    if model["initial_profile"]!=INITIAL_PROFILE or model["boundary"]!="fixed_left_compliant_right" or model["particle_semantics"]!="none":
        raise ValueError("Require the fixed coupled continuum eigenmode, fixed/compliant walls and no particles")
    wall=request["structure"]
    keys(wall,{"mass_kg","stiffness_n_per_m","damping_n_s_per_m","maximum_displacement_m","equilibrium_preload"})
    _bounded(wall["mass_kg"],0.1,1e6,"wall mass")
    _bounded(wall["stiffness_n_per_m"],0.01,1e6,"wall stiffness")
    if number(wall["damping_n_s_per_m"])!=0.0:
        raise ValueError("Nonzero wall damping requires an additional qualified continuum reference")
    travel=_bounded(wall["maximum_displacement_m"],1e-4,0.1,"wall travel")
    if wall["equilibrium_preload"]!="balances_resting_hydrostatic_force":
        raise ValueError("Require resting hydrostatic force preload")
    mode=mode_parameters(request)
    if not 0.01<=mode["mass_ratio"]<=10.0 or not 0.01<=mode["stiffness_ratio"]<=100.0:
        raise ValueError("Coupled mode exceeds bounded mass/stiffness ratios")
    if amplitude/depth>MAX_ELEVATION_DEPTH_FRACTION or mode["wavenumber_per_m"]*depth>0.2:
        raise ValueError("Hard continuous small-amplitude or long-wave validity limit exceeded")
    if mode["wall_amplitude_m"]>travel or mode["wall_amplitude_m"]/length>MAX_WALL_LENGTH_FRACTION:
        raise ValueError("Continuous coupled mode exceeds the small wall-travel domain")
    integration=request["integration"]
    keys(integration,{"method","cells","steps","duration_s","time_refinement_factor","spatial_refinement_factor"})
    if integration["method"]!="implicit_midpoint":
        raise ValueError("Only monolithic implicit midpoint is qualified")
    n,s=integration["cells"],integration["steps"]
    if type(n) is not int or n not in (16,32,64) or type(s) is not int or not 16<=s<=64 or n*s>MAX_BASE_SPACE_TIME_POINTS:
        raise ValueError("Require cells16/32/64, steps16..64 and bounded space/time allocation <=1024")
    for name in ("time_refinement_factor","spatial_refinement_factor"):
        if type(integration[name]) is not int or integration[name]!=2:
            raise ValueError("Require exact integer refinement factors2")
    period=2*math.pi/mode["angular_frequency_per_s"]
    duration=_bounded(integration["duration_s"],0.05*period,0.2*period,"duration_s")
    dt=duration/s
    if wave_speed_m_per_s(model)*dt/(length/n)>0.5 or mode["angular_frequency_per_s"]*dt>0.1:
        raise ValueError("Hard accuracy CFL or modal time-resolution limit exceeded")
    keys(request["tolerances"],TOLERANCE_KEYS)
    for name,value in request["tolerances"].items():
        _bounded(value,1e-13,0.1,"tolerances."+name)
    obs=request["desired_observables"]
    known=SUPPORTED_OBSERVABLES|EXPANSION_OBSERVABLES|REFUSED_OBSERVABLES
    if type(obs) is not list or not 1<=len(obs)<=24 or any(type(v) is not str or v not in known for v in obs) or len(set(obs))!=len(obs):
        raise ValueError("Require known bounded unique observables")
    return deepcopy(request)


def _array(values,count):
    if type(values) is not list or len(values)!=count:
        raise ValueError("FSI arrays must cover the declared ordered grid")
    for value in values:
        if abs(number(value))>1e30:
            raise ValueError("FSI arithmetic exceeds finite SI bounds")


def validate_result(request,result):
    request=validate_request(request)
    keys(result,{"schema","request_digest","claim_scope","provider","solver","units","clock","representation","record_digest"}|set(TRACE_LABELS))
    declarations={"schema":RESULT_SCHEMA,"request_digest":digest(request),"claim_scope":CLAIM_SCOPE,"provider":PROVIDER_ID,
                  "solver":SOLVER_ID,"units":UNITS,"clock":CLOCK,"representation":REPRESENTATION}
    if any(result[name]!=value for name,value in declarations.items()):
        raise ValueError("FSI result schema/provider/model/clock/units binding differs")
    keys(result["clock"],set(CLOCK));number(result["clock"]["time_origin_s"])
    if type(result["clock"]["externally_synchronized"]) is not bool:
        raise ValueError("FSI external synchronization flag must be boolean")
    keys(result["units"],set(UNITS));keys(result["representation"],set(REPRESENTATION))
    length,depth=length_m(request),request["model"]["depth_m"]
    for label,n,s in trace_declarations(request):
        trace=result[label]
        keys(trace,{"cells","steps","dx_m","dt_s","time_s","cell_x_m","face_x_m"}|set(FIELD_NAMES)|set(SCALAR_NAMES))
        if type(trace["cells"]) is not int or trace["cells"]!=n or type(trace["steps"]) is not int or trace["steps"]!=s:
            raise ValueError("FSI grid differs from its fixed refinements")
        dx,dt=length/n,duration_s(request)/s
        if number(trace["dx_m"])!=dx or number(trace["dt_s"])!=dt:
            raise ValueError("FSI grid spacing differs")
        for name,count in (("time_s",s+1),("cell_x_m",n),("face_x_m",n+1)):
            _array(trace[name],count)
        if trace["time_s"]!=[j*dt for j in range(s+1)] or trace["cell_x_m"]!=[(j+.5)*dx for j in range(n)] or trace["face_x_m"]!=[j*dx for j in range(n+1)]:
            raise ValueError("FSI staggered coordinates or owned fixed clock differs")
        for name in FIELD_NAMES:
            matrix=trace[name]
            if type(matrix) is not list or len(matrix)!=s+1:
                raise ValueError("FSI field matrices must be time by space")
            width=n+1 if name in {"depth_averaged_velocity_m_per_s","volume_flux_m3_per_s"} else n
            for row in matrix: _array(row,width)
        for name in SCALAR_NAMES: _array(trace[name],s+1)
        for name in ("structure_dissipation_j","external_work_j"):
            if any(v!=0.0 for v in trace[name]):
                raise ValueError("Undamped unforced benchmark requires zero dissipation/external work")
        for name in ("liquid_volume_m3","liquid_mass_kg","fluid_energy_j","structure_energy_j","total_energy_j"):
            if any(v<0 for v in trace[name]):
                raise ValueError("Retained volume/mass/energies must be nonnegative")
    check_seal(result)
    return deepcopy(result)


def example_request():
    request={"schema":REQUEST_SCHEMA,"scope":CLAIM_SCOPE,
             "model":{"length_m":20.0,"depth_m":0.1,"width_m":1.0,"density_kg_per_m3":1000.0,"gravity_m_per_s2":9.81,
                      "amplitude_m":0.00005,"initial_profile":INITIAL_PROFILE,"boundary":"fixed_left_compliant_right","particle_semantics":"none"},
             "structure":{"mass_kg":1000.0,"stiffness_n_per_m":4.905,"damping_n_s_per_m":0.0,"maximum_displacement_m":0.02,
                          "equilibrium_preload":"balances_resting_hydrostatic_force"},
             "integration":{"method":"implicit_midpoint","cells":32,"steps":32,"duration_s":1.0,"time_refinement_factor":2,"spatial_refinement_factor":2},
             "clock":deepcopy(CLOCK),"desired_observables":sorted(SUPPORTED_OBSERVABLES),
             "tolerances":{"equations_relative":1e-9,"mass_relative":1e-12,"energy_relative":1e-10,
                           "analytic_normalized":0.002,"time_refinement_normalized":0.001,"spatial_refinement_normalized":0.002}}
    request["integration"]["duration_s"]=0.1*2*math.pi/mode_parameters(request)["angular_frequency_per_s"]
    return request
