"""Five bounded, steady analytical thermofluid references in explicit SI units.

Property values are declared inputs. Domain screening does not establish that
a real apparatus satisfies the model assumptions or an equation of state.
"""
from __future__ import annotations

from copy import deepcopy
import math

from .control_contracts import json_tree, keys, number

SCHEMA = "ciw.thermofluids-request.v1"
SIGMA = 5.670374419e-8  # W m^-2 K^-4, rounded SI Stefan–Boltzmann constant


def _profile(title, model, scope, sources, assumptions, limitations):
    return dict(title=title, model=model, scope=scope, sources=sources,
                assumptions=assumptions, limitations=limitations)


PROFILES = {
    "convection": _profile(
        "Convective Heat Transfer", "fully-developed-laminar-circular-tube",
        "Local heat-transfer coefficient and wall-to-bulk heat flux at a developed section",
        ["https://archive.nptel.ac.in/content/storage2/courses/103105052/AdvHeatMass_L_29.pdf",
         "https://web.mit.edu/10.302/www/Fall2001/final_rev.pdf"],
        ["Steady, incompressible Newtonian flow in a straight circular tube",
         "Constant properties evaluated at representative bulk temperature",
         "Hydrodynamically and thermally developed; negligible axial conduction and viscous heating",
         "Explicit uniform wall temperature or uniform wall heat flux boundary"],
        ["Local section only; no integrated duty or outlet temperature",
         "No developing, turbulent, natural/mixed or non-Newtonian convection",
         "No phase change or conjugate wall conduction; development distances are screening rules"]),
    "heat-exchanger": _profile(
        "Advanced Heat Transfer / Advanced Thermofluids Design", "effectiveness-ntu",
        "Counterflow or parallel-flow exchanger duty and outlet temperatures for declared UA",
        ["https://energyplus.readthedocs.io/en/latest/guides/engineering-reference/16.8-heat-exchangers.html"],
        ["Steady two-stream single-phase flow with positive constant heat capacities",
         "No external heat loss or axial conduction; declared constant UA"],
        ["No phase change, pressure loss, transient storage or geometry optimization",
         "UA and properties are inputs; material and mechanical suitability are not assessed"]),
    "pipe-flow": _profile(
        "Advanced Fluid Dynamics", "hagen-poiseuille",
        "Analytical fully developed laminar circular-pipe pressure and velocity reference",
        ["https://ocw.mit.edu/courses/2-25-advanced-fluid-mechanics-fall-2013/1a114d602956fa0dd328155f9b45f93d_MIT2_25F13_Couet_and_Pois.pdf"],
        ["Steady incompressible Newtonian flow, rigid straight circular tube, no slip",
         "Constant viscosity; measured segment starts downstream of the inlet development region"],
        ["Analytical benchmark, not a discretized Navier–Stokes solver",
         "No entrance/fitting losses, turbulence, non-Newtonian rheology or elevation head"]),
    "radiation": _profile(
        "Radiative Heat Transfer (energy and building systems)", "diffuse-gray-parallel-plates",
        "Signed net thermal radiative exchange between large facing opaque surfaces",
        ["https://web.mit.edu/16.unified/www/FALL/thermodynamics/notes/node136.html"],
        ["Two isothermal opaque diffuse-gray surfaces, equal exchange area, view factor one",
         "Nonparticipating intervening medium; absolute kelvin temperatures"],
        ["Ideal parallel-plate limit; no finite-edge view factors or enclosure solver",
         "No sunlight, transparent glazing, participating gases, conduction or convection",
         "Not a whole-building energy model"]),
    "two-phase": _profile(
        "Two-Phase Flow and Heat Transfer", "saturated-homogeneous-mixture",
        "Mixture properties and required latent duty from prescribed inlet/outlet vapor mass qualities",
        ["https://ocw.mit.edu/courses/22-06-engineering-of-nuclear-systems-fall-2010/2e8614e58cc569d96acff67df51d9aef_MIT22_06F10_lec13.pdf"],
        ["Saturated liquid/vapor at one declared constant pressure and temperature",
         "Homogeneous no-slip phases; negligible changes in kinetic and potential energy",
         "Caller supplies coexisting-phase properties at that saturation state"],
        ["No independent equation-of-state or saturation-property consistency validation",
         "No slip, flow regimes, boiling/condensation coefficients, dryout or critical heat flux",
         "No two-phase pressure drop or subcooled/superheated continuation"]),
}

OUTPUT_UNITS = {
    "convection": {"reynolds": "1", "prandtl": "1", "peclet": "1", "nusselt": "1",
                   "heat_transfer_coefficient": "W/(m^2 K)", "wall_to_bulk_heat_flux": "W/m^2",
                   "hydrodynamic_development_screen": "m", "thermal_development_screen": "m"},
    "heat-exchanger": {"hot_capacity_rate": "W/K", "cold_capacity_rate": "W/K", "capacity_ratio": "1",
                       "ntu": "1", "effectiveness": "1", "heat_duty": "W",
                       "hot_outlet_temperature": "K", "cold_outlet_temperature": "K"},
    "pipe-flow": {"reynolds": "1", "darcy_friction_factor": "1", "volume_flow_rate": "m^3/s",
                  "mass_flow_rate": "kg/s", "pressure_drop": "Pa", "wall_shear_stress": "Pa",
                  "hydraulic_pumping_power": "W", "centerline_velocity": "m/s",
                  "hydrodynamic_development_screen": "m"},
    "radiation": {"effective_emissivity": "1", "net_heat_flux": "W/m^2", "net_heat_rate": "W",
                  "radiative_heat_transfer_coefficient": "W/(m^2 K)"},
    "two-phase": {"latent_enthalpy": "J/kg", "inlet_void_fraction": "1", "outlet_void_fraction": "1",
                  "inlet_mixture_density": "kg/m^3", "outlet_mixture_density": "kg/m^3",
                  "inlet_specific_enthalpy": "J/kg", "outlet_specific_enthalpy": "J/kg", "heat_duty": "W"},
}

_EXAMPLES = {
    "convection": dict(density_kg_m3=1000.0, dynamic_viscosity_pa_s=0.001,
        heat_capacity_j_kg_k=4200.0, conductivity_w_m_k=0.6, diameter_m=0.01, mean_velocity_m_s=0.1,
        axial_distance_from_inlet_m=10.0, heated_distance_to_section_m=10.0,
        wall_temperature_k=320.0, bulk_temperature_k=310.0, boundary_condition="constant-wall-temperature"),
    "heat-exchanger": dict(hot_mass_flow_kg_s=1.0, cold_mass_flow_kg_s=1.0,
        hot_heat_capacity_j_kg_k=4000.0, cold_heat_capacity_j_kg_k=4000.0,
        ua_w_k=1000.0, hot_inlet_temperature_k=350.0, cold_inlet_temperature_k=300.0,
        arrangement="counterflow"),
    "pipe-flow": dict(density_kg_m3=1000.0, dynamic_viscosity_pa_s=0.001,
        diameter_m=0.01, mean_velocity_m_s=0.1, length_m=2.0, upstream_development_length_m=2.0),
    "radiation": dict(surface_1_temperature_k=330.0, surface_2_temperature_k=295.0,
        emissivity_1=0.9, emissivity_2=0.8, area_m2=10.0),
    "two-phase": dict(saturation_pressure_pa=101325.0, saturation_temperature_k=373.15,
        liquid_density_kg_m3=958.4, vapor_density_kg_m3=0.598,
        liquid_enthalpy_j_kg=419000.0, vapor_enthalpy_j_kg=2676000.0,
        quality_in=0.1, quality_out=0.3, mass_flow_kg_s=0.1),
}


def example_request(profile):
    if type(profile) is not str or profile not in PROFILES:
        raise ValueError("Unknown thermofluids profile")
    return {"schema": SCHEMA, "profile": profile, "input_semantics": "synthetic",
            "parameters": deepcopy(_EXAMPLES[profile])}


def _range(value, label, low=1e-12, high=1e12):
    parsed = number(value)
    if not low <= parsed <= high:
        raise ValueError(f"{label} outside supported interval [{low}, {high}]")
    return parsed


def _dimensionless(p):
    reynolds = p["density_kg_m3"] * p["mean_velocity_m_s"] * p["diameter_m"] / p["dynamic_viscosity_pa_s"]
    _range(reynolds, "laminar Reynolds number", 1.0, 2000.0)
    return reynolds


def validate_request(request):
    json_tree(request)
    keys(request, {"schema", "profile", "input_semantics", "parameters"})
    if request["schema"] != SCHEMA or type(request["profile"]) is not str or request["profile"] not in PROFILES:
        raise ValueError("Unsupported thermofluids schema or profile")
    if type(request["input_semantics"]) is not str or request["input_semantics"] not in {"synthetic", "declared"}:
        raise ValueError("Declare synthetic or declared input semantics")
    profile, p = request["profile"], request["parameters"]
    keys(p, set(_EXAMPLES[profile]))
    for name, value in p.items():
        if name in {"boundary_condition", "arrangement"}:
            continue
        if name.startswith("quality_"):
            _range(value, name, 0.0, 1.0)
        elif name.startswith("emissivity_"):
            _range(value, name, 1e-12, 1.0)
        elif name.endswith("temperature_k"):
            _range(value, name, 1.0, 3000.0)
        elif name.endswith("enthalpy_j_kg"):
            _range(value, name, -1e12, 1e12)
        elif name == "ua_w_k":
            _range(value, name, 0.0, 1e12)
        else:
            _range(value, name)
    if profile in {"convection", "pipe-flow"}:
        re = _dimensionless(p)
        development = max(10.0 * p["diameter_m"], 0.1 * re * p["diameter_m"])
        distance = p["axial_distance_from_inlet_m"] if profile == "convection" else p["upstream_development_length_m"]
        if distance < development:
            raise ValueError("Insufficient upstream hydrodynamic development distance")
    if profile == "convection":
        if type(p["boundary_condition"]) is not str or p["boundary_condition"] not in {"constant-wall-temperature", "constant-wall-heat-flux"}:
            raise ValueError("Unsupported thermal boundary condition")
        pr = p["dynamic_viscosity_pa_s"] * p["heat_capacity_j_kg_k"] / p["conductivity_w_m_k"]
        _range(pr, "Prandtl number", 0.1, 1000.0)
        _range(re * pr, "Peclet number", 100.0, 2e6)
        thermal = max(10.0 * p["diameter_m"], 0.1 * re * pr * p["diameter_m"])
        if p["heated_distance_to_section_m"] < thermal:
            raise ValueError("Insufficient upstream thermal development distance")
        if p["heated_distance_to_section_m"] > p["axial_distance_from_inlet_m"]:
            raise ValueError("Heated development distance exceeds distance from inlet")
    elif profile == "heat-exchanger":
        if type(p["arrangement"]) is not str or p["arrangement"] not in {"counterflow", "parallel-flow"}:
            raise ValueError("Unsupported heat-exchanger arrangement")
        if p["hot_inlet_temperature_k"] < p["cold_inlet_temperature_k"]:
            raise ValueError("Hot inlet temperature must be at least cold inlet temperature")
        minimum = min(p["hot_mass_flow_kg_s"] * p["hot_heat_capacity_j_kg_k"],
                      p["cold_mass_flow_kg_s"] * p["cold_heat_capacity_j_kg_k"])
        _range(p["ua_w_k"] / minimum, "NTU", 0.0, 1e6)
    elif profile == "two-phase":
        if p["liquid_density_kg_m3"] <= p["vapor_density_kg_m3"]:
            raise ValueError("Liquid density must exceed vapor density")
        if p["vapor_enthalpy_j_kg"] <= p["liquid_enthalpy_j_kg"]:
            raise ValueError("Vapor enthalpy must exceed liquid enthalpy")


def calculate(request):
    validate_request(request)
    profile, p = request["profile"], request["parameters"]
    if profile == "convection":
        re = _dimensionless(p)
        pr = p["dynamic_viscosity_pa_s"] * p["heat_capacity_j_kg_k"] / p["conductivity_w_m_k"]
        nu = 3.66 if p["boundary_condition"] == "constant-wall-temperature" else 48.0 / 11.0
        h = nu * p["conductivity_w_m_k"] / p["diameter_m"]
        values = dict(reynolds=re, prandtl=pr, peclet=re*pr, nusselt=nu,
            heat_transfer_coefficient=h, wall_to_bulk_heat_flux=h*(p["wall_temperature_k"]-p["bulk_temperature_k"]),
            hydrodynamic_development_screen=max(10*p["diameter_m"], 0.1*re*p["diameter_m"]),
            thermal_development_screen=max(10*p["diameter_m"], 0.1*re*pr*p["diameter_m"]))
    elif profile == "heat-exchanger":
        ch = p["hot_mass_flow_kg_s"] * p["hot_heat_capacity_j_kg_k"]
        cc = p["cold_mass_flow_kg_s"] * p["cold_heat_capacity_j_kg_k"]
        cmin, cmax = min(ch, cc), max(ch, cc)
        cr, ntu = cmin / cmax, p["ua_w_k"] / cmin
        if p["arrangement"] == "parallel-flow":
            effectiveness = -math.expm1(-ntu*(1+cr))/(1+cr)
        elif cr == 1.0:
            effectiveness = ntu/(1+ntu)
        else:
            numerator = -math.expm1(-ntu*(1-cr))
            effectiveness = numerator/((1-cr)+cr*numerator)
        duty = effectiveness*cmin*(p["hot_inlet_temperature_k"]-p["cold_inlet_temperature_k"])
        values = dict(hot_capacity_rate=ch, cold_capacity_rate=cc, capacity_ratio=cr, ntu=ntu,
            effectiveness=effectiveness, heat_duty=duty,
            hot_outlet_temperature=p["hot_inlet_temperature_k"]-duty/ch,
            cold_outlet_temperature=p["cold_inlet_temperature_k"]+duty/cc)
    elif profile == "pipe-flow":
        re = _dimensionless(p)
        d, u = p["diameter_m"], p["mean_velocity_m_s"]
        volume = math.pi*d*d*u/4
        pressure = 32*p["dynamic_viscosity_pa_s"]*p["length_m"]*u/(d*d)
        values = dict(reynolds=re, darcy_friction_factor=64/re, volume_flow_rate=volume,
            mass_flow_rate=p["density_kg_m3"]*volume, pressure_drop=pressure,
            wall_shear_stress=8*p["dynamic_viscosity_pa_s"]*u/d,
            hydraulic_pumping_power=pressure*volume, centerline_velocity=2*u,
            hydrodynamic_development_screen=max(10*d, 0.1*re*d))
    elif profile == "radiation":
        t1, t2 = p["surface_1_temperature_k"], p["surface_2_temperature_k"]
        emissivity = 1/(1/p["emissivity_1"]+1/p["emissivity_2"]-1)
        h = emissivity*SIGMA*(t1+t2)*(t1*t1+t2*t2)
        flux = h*(t1-t2)
        values = dict(effective_emissivity=emissivity, net_heat_flux=flux,
            net_heat_rate=p["area_m2"]*flux, radiative_heat_transfer_coefficient=h)
    else:
        liquid, vapor = p["liquid_density_kg_m3"], p["vapor_density_kg_m3"]
        hf, hg = p["liquid_enthalpy_j_kg"], p["vapor_enthalpy_j_kg"]
        latent = hg-hf
        values = {"latent_enthalpy": latent}
        for direction, quality_key in (("inlet", "quality_in"), ("outlet", "quality_out")):
            x = p[quality_key]
            specific_volume = x/vapor+(1-x)/liquid
            values[direction+"_void_fraction"] = (x/vapor)/specific_volume
            values[direction+"_mixture_density"] = 1/specific_volume
            values[direction+"_specific_enthalpy"] = (1-x)*hf+x*hg
        values["heat_duty"] = p["mass_flow_kg_s"]*latent*(p["quality_out"]-p["quality_in"])
    # Explicit output shape, units and finite range. No silent extrapolation/NaNs.
    keys(values, set(OUTPUT_UNITS[profile]))
    return {"quantities": {name: {"value": number(value), "unit": OUTPUT_UNITS[profile][name]}
                           for name, value in values.items()},
            "assumptions": deepcopy(PROFILES[profile]["assumptions"]),
            "limitations": deepcopy(PROFILES[profile]["limitations"])}
