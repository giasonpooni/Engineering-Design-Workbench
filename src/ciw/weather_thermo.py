"""Bounded atmospheric diagnostics; no forecast, observation admission, or state owner.

Equations and model choices are frozen here rather than delegated to an optional
package. Constants use SI; radar diameters are explicitly millimetres. References:
* Buck (1996), water/ice equations reproduced by NCAR EOL:
  https://www.eol.ucar.edu/data-software/conventions-and-standards/water-vapor-pressure-formulations
* Unidata MetPy, potential_temperature, virtual_temperature, thickness_hydrostatic:
  https://unidata.github.io/MetPy/latest/api/generated/metpy.calc.html
* NOAA/NWS, radar sixth moment and empirical Z-R relation:
  https://training.weather.gov/nwstc/NEXRAD/RADAR/3-1.htm
* Beer direct-beam law: https://doi.org/10.1175/JAS-D-19-0030.1

Checks use inverse equations and conservation identities independently of compute.
They establish numerical consistency, not empirical accuracy or weather skill.
"""
from __future__ import annotations

import math

from .control_contracts import keys, number

RD = 287.05
RV = 461.5
CP_D = 1004.0
EPSILON = RD / RV
G = 9.80665
SIGMA = 5.670374419e-8
WATER_DENSITY = 1000.0

PROFILES = {
    "thermodynamics": {
        "scope": "Buck1996 saturation and ideal moist-air parcel diagnostics; uniform virtual-temperature hydrostatic layer",
        "limitations": [
            "Relative humidity is a fraction relative to the explicitly selected water or ice phase; no automatic phase switch.",
            "Buck1996 pure-plane saturation approximation, no enhancement factor, solute or curvature correction; water 233.15–323.15 K, ice 223.15–273.15 K.",
            "No supersaturation, condensate loading, latent heating or moist parcel ascent; potential temperature uses dry-air constant heat capacity.",
            "Hypsometric thickness assumes the calculated parcel virtual temperature is constant throughout the layer; it is not a sounding integration.",
            "Numerical consistency is not experimental validation or a calibrated uncertainty estimate.",
        ],
        "example": {"temperature_k": 283.15, "pressure_pa": 100000.0,
                    "relative_humidity": 0.65, "phase": "water", "layer_top_pressure_pa": 85000.0},
        "units": {"saturation_vapor_pressure_pa": "Pa", "vapor_pressure_pa": "Pa",
                  "mixing_ratio_kg_kg": "kg/kg dry air", "specific_humidity_kg_kg": "kg/kg moist air",
                  "virtual_temperature_k": "K", "density_kg_m3": "kg/m^3",
                  "potential_temperature_k": "K", "layer_thickness_m": "m"},
    },
    "radiation": {
        "scope": "Plane-parallel direct-beam attenuation and opaque gray-surface radiative energy budget; positive flux into surface",
        "limitations": [
            "Effective broadband optical depth is prescribed, not derived from atmospheric composition; no spectral or multiple-scattering solver.",
            "Diffuse shortwave and downwelling longwave are independent prescribed boundary fluxes.",
            "Daylight solar cosine is restricted to 0.05–1; no night, twilight, refraction or spherical-path calculation.",
            "Opaque gray surface has longwave absorptivity equal to emissivity; no thermal conduction, turbulent flux, temperature evolution or weather forecast.",
        ],
        "example": {"toa_direct_normal_w_m2": 1361.0, "diffuse_shortwave_w_m2": 80.0,
                    "downwelling_longwave_w_m2": 300.0, "surface_temperature_k": 288.15,
                    "albedo": 0.25, "emissivity": 0.97, "optical_depth": 0.2, "solar_cosine": 0.6},
        "units": {"beam_transmittance": "1", "direct_shortwave_w_m2": "W/m^2",
                  "downwelling_shortwave_w_m2": "W/m^2", "net_shortwave_w_m2": "W/m^2",
                  "emitted_longwave_w_m2": "W/m^2", "net_longwave_w_m2": "W/m^2",
                  "net_radiation_w_m2": "W/m^2"},
    },
    "radar_cloud": {
        "scope": "Spherical liquid-drop number, mass and reflectivity moments with an explicitly empirical Z-R rainfall estimate",
        "limitations": [
            "Each concentration_m3 is the bin-integrated number per cubic metre, not a spectral density per millimetre; diameters are millimetres.",
            "Liquid spheres at fixed density 1000 kg/m^3; no ice, mixed phase, dielectric correction, attenuation, beam geometry or Doppler velocity.",
            "Requires positive total concentration; dBZ of zero reflectivity is undefined and is rejected, not assigned a floor.",
            "Rayleigh size guard pi*diameter/wavelength <= 0.3 is a conservative declared scope, not an error bound on scattering accuracy.",
            "Rain rate comes only from user-declared empirical Z=a*R^b, not drop fall speeds; coefficients do not calibrate arbitrary storms.",
            "No cloud nucleation, growth, collision, coalescence or operational radar-data ingestion.",
        ],
        "example": {"drop_bins": [{"diameter_mm": 0.5, "concentration_m3": 100.0},
                                  {"diameter_mm": 1.0, "concentration_m3": 50.0},
                                  {"diameter_mm": 2.0, "concentration_m3": 5.0}],
                    "wavelength_m": 0.1, "zr_a": 200.0, "zr_b": 1.6},
        "units": {"number_concentration_m3": "1/m^3", "liquid_water_content_kg_m3": "kg/m^3",
                  "reflectivity_mm6_m3": "mm^6/m^3", "reflectivity_dbz": "dBZ",
                  "empirical_rain_rate_mm_h": "mm/h"},
    },
}


def _bounded(value: object, low: float, high: float, name: str) -> float:
    result = number(value)
    if not low <= result <= high:
        raise ValueError(f"{name} must be within [{low}, {high}]")
    return result


def _saturation(temperature: float, phase: str) -> float:
    t = temperature - 273.15
    if phase == "water":
        return 611.21 * math.exp((18.678 - t / 234.5) * t / (257.14 + t))
    return 611.15 * math.exp((23.036 - t / 333.7) * t / (279.82 + t))


def validate(profile: str, inputs: dict) -> None:
    if type(profile) is not str or profile not in PROFILES:
        raise ValueError("Unknown atmospheric thermodynamics/radiation/radar profile")
    keys(inputs, set(PROFILES[profile]["example"]))
    if profile == "thermodynamics":
        phase = inputs["phase"]
        if type(phase) is not str or phase not in ("water", "ice"):
            raise ValueError("phase must explicitly be water or ice")
        low, high = (233.15, 323.15) if phase == "water" else (223.15, 273.15)
        t = _bounded(inputs["temperature_k"], low, high, "temperature_k")
        p = _bounded(inputs["pressure_pa"], 20000.0, 110000.0, "pressure_pa")
        rh = _bounded(inputs["relative_humidity"], 0.0, 1.0, "relative_humidity")
        _bounded(inputs["layer_top_pressure_pa"], 10000.0, p, "layer_top_pressure_pa")
        if rh * _saturation(t, phase) > 0.2 * p:
            raise ValueError("Vapor partial pressure must not exceed 20 percent of total pressure")
    elif profile == "radiation":
        for key in ("toa_direct_normal_w_m2", "diffuse_shortwave_w_m2"):
            _bounded(inputs[key], 0.0, 2000.0, key)
        _bounded(inputs["downwelling_longwave_w_m2"], 0.0, 1500.0, "downwelling_longwave_w_m2")
        _bounded(inputs["surface_temperature_k"], 150.0, 350.0, "surface_temperature_k")
        for key in ("albedo", "emissivity"):
            _bounded(inputs[key], 0.0, 1.0, key)
        _bounded(inputs["solar_cosine"], 0.05, 1.0, "solar_cosine")
        _bounded(inputs["optical_depth"], 0.0, 20.0, "optical_depth")
    else:
        wavelength = _bounded(inputs["wavelength_m"], 0.01, 0.3, "wavelength_m")
        _bounded(inputs["zr_a"], 1.0, 1000.0, "zr_a")
        _bounded(inputs["zr_b"], 0.5, 3.0, "zr_b")
        bins = inputs["drop_bins"]
        if type(bins) is not list or not 1 <= len(bins) <= 128:
            raise ValueError("drop_bins requires 1–128 bin records")
        total, mass = 0.0, 0.0
        for item in bins:
            keys(item, {"diameter_mm", "concentration_m3"})
            d = _bounded(item["diameter_mm"], 0.01, 8.0, "diameter_mm")
            n = _bounded(item["concentration_m3"], 0.0, 1e8, "concentration_m3")
            if math.pi * d * 1e-3 / wavelength > 0.3:
                raise ValueError("Drop exceeds the declared Rayleigh size guard")
            total += n
            mass += n * WATER_DENSITY * math.pi / 6.0 * (d * 1e-3) ** 3
        if not 1e-6 <= total <= 1e9:
            raise ValueError("Total number concentration must be within [1e-6, 1e9] m^-3; dBZ at zero reflectivity is undefined")
        if mass > 0.05:
            raise ValueError("Liquid water content exceeds the 0.05 kg/m^3 scope")


def compute(profile: str, inputs: dict) -> dict:
    validate(profile, inputs)
    if profile == "thermodynamics":
        t, p = inputs["temperature_k"], inputs["pressure_pa"]
        saturation = _saturation(t, inputs["phase"])
        vapor = inputs["relative_humidity"] * saturation
        mixing = EPSILON * vapor / (p - vapor)
        virtual = t * (1.0 + mixing / EPSILON) / (1.0 + mixing)
        return {
            "saturation_vapor_pressure_pa": saturation, "vapor_pressure_pa": vapor,
            "mixing_ratio_kg_kg": mixing, "specific_humidity_kg_kg": mixing / (1.0 + mixing),
            "virtual_temperature_k": virtual, "density_kg_m3": p / (RD * virtual),
            "potential_temperature_k": t * (100000.0 / p) ** (RD / CP_D),
            "layer_thickness_m": RD * virtual / G * math.log(p / inputs["layer_top_pressure_pa"]),
        }
    if profile == "radiation":
        transmission = math.exp(-inputs["optical_depth"] / inputs["solar_cosine"])
        direct = inputs["toa_direct_normal_w_m2"] * inputs["solar_cosine"] * transmission
        down = direct + inputs["diffuse_shortwave_w_m2"]
        shortwave = (1.0 - inputs["albedo"]) * down
        emitted = inputs["emissivity"] * SIGMA * inputs["surface_temperature_k"] ** 4
        longwave = inputs["emissivity"] * inputs["downwelling_longwave_w_m2"] - emitted
        return {"beam_transmittance": transmission, "direct_shortwave_w_m2": direct,
                "downwelling_shortwave_w_m2": down, "net_shortwave_w_m2": shortwave,
                "emitted_longwave_w_m2": emitted, "net_longwave_w_m2": longwave,
                "net_radiation_w_m2": shortwave + longwave}
    bins = inputs["drop_bins"]
    z = math.fsum(item["concentration_m3"] * item["diameter_mm"] ** 6 for item in bins)
    mass = WATER_DENSITY * math.pi / 6.0 * math.fsum(
        item["concentration_m3"] * (item["diameter_mm"] * 1e-3) ** 3 for item in bins)
    return {"number_concentration_m3": math.fsum(float(item["concentration_m3"]) for item in bins),
            "liquid_water_content_kg_m3": mass, "reflectivity_mm6_m3": z,
            "reflectivity_dbz": 10.0 * math.log10(z),
            "empirical_rain_rate_mm_h": (z / inputs["zr_a"]) ** (1.0 / inputs["zr_b"])}


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=2e-11, abs_tol=1e-12)


def checks(profile: str, inputs: dict, values: dict) -> dict[str, bool]:
    """Algebraic verification independent of execution; malformed results fail closed."""
    validate(profile, inputs)
    try:
        keys(values, set(PROFILES[profile]["units"]))
        for value in values.values():
            number(value)
        v = values
        if profile == "thermodynamics":
            t, p = inputs["temperature_k"], inputs["pressure_pa"]
            tc = t - 273.15
            base, a, b, c = (611.21, 18.678, 234.5, 257.14) if inputs["phase"] == "water" else (611.15, 23.036, 333.7, 279.82)
            es, e, r = v["saturation_vapor_pressure_pa"], v["vapor_pressure_pa"], v["mixing_ratio_kg_kg"]
            q, tv = v["specific_humidity_kg_kg"], v["virtual_temperature_k"]
            return {
                "finite_schema": True,
                "saturation_log_relation": es > 0 and _close(math.log(es / base), (a - tc / b) * tc / (c + tc)),
                "relative_humidity_relation": _close(e, inputs["relative_humidity"] * es),
                "mixing_ratio_mass_relation": _close(r * (p - e), EPSILON * e),
                "specific_humidity_mass_relation": _close(q * (1.0 + r), r),
                "virtual_temperature_relation": _close(tv * (1.0 + r), t * (1.0 + r / EPSILON)),
                "ideal_gas_relation": _close(v["density_kg_m3"] * RD * tv, p),
                "dry_potential_temperature_relation": _close(v["potential_temperature_k"] * (p / 100000.0) ** (RD / CP_D), t),
                "hydrostatic_layer_relation": _close(v["layer_thickness_m"] * G, RD * tv * math.log(p / inputs["layer_top_pressure_pa"])),
                "physical_bounds": 0 <= e < p and r >= 0 and 0 <= q < 1 and tv >= t and v["density_kg_m3"] > 0 and v["layer_thickness_m"] >= 0,
            }
        if profile == "radiation":
            trans = v["beam_transmittance"]
            return {
                "finite_schema": True,
                "optical_depth_inverse": trans > 0 and _close(-math.log(trans) * inputs["solar_cosine"], inputs["optical_depth"]),
                "beam_projection": _close(v["direct_shortwave_w_m2"], inputs["toa_direct_normal_w_m2"] * inputs["solar_cosine"] * trans),
                "shortwave_components": _close(v["downwelling_shortwave_w_m2"] - v["direct_shortwave_w_m2"], inputs["diffuse_shortwave_w_m2"]),
                "albedo_budget": _close(v["net_shortwave_w_m2"], (1.0 - inputs["albedo"]) * v["downwelling_shortwave_w_m2"]),
                "thermal_emission": _close(v["emitted_longwave_w_m2"], inputs["emissivity"] * SIGMA * inputs["surface_temperature_k"] ** 4),
                "longwave_budget": _close(v["net_longwave_w_m2"] + v["emitted_longwave_w_m2"], inputs["emissivity"] * inputs["downwelling_longwave_w_m2"]),
                "surface_energy_budget": _close(v["net_radiation_w_m2"], v["net_shortwave_w_m2"] + v["net_longwave_w_m2"]),
                "physical_bounds": 0 < trans <= 1 and v["direct_shortwave_w_m2"] >= 0 and v["net_shortwave_w_m2"] >= 0 and v["emitted_longwave_w_m2"] >= 0,
            }
        bins = inputs["drop_bins"]
        # Separate moment accumulation, using radius in metres for the mass check.
        count, sixth, volume = 0.0, 0.0, 0.0
        for item in bins:
            n, d = item["concentration_m3"], item["diameter_mm"]
            count += n
            sixth += n * d * d * d * d * d * d
            volume += n * 4.0 / 3.0 * math.pi * (d / 2000.0) ** 3
        z, rain = v["reflectivity_mm6_m3"], v["empirical_rain_rate_mm_h"]
        return {
            "finite_schema": True,
            "number_moment": math.isclose(v["number_concentration_m3"], count, rel_tol=2e-11, abs_tol=0.0),
            "sphere_mass_moment": math.isclose(v["liquid_water_content_kg_m3"], volume * WATER_DENSITY, rel_tol=2e-11, abs_tol=0.0),
            "reflectivity_sixth_moment": math.isclose(z, sixth, rel_tol=2e-11, abs_tol=0.0),
            "dbz_definition": z > 0 and _close(v["reflectivity_dbz"] / 10.0, math.log10(z)),
            "empirical_zr_inverse": z > 0 and rain > 0 and _close(math.log(z), math.log(inputs["zr_a"]) + inputs["zr_b"] * math.log(rain)),
            "physical_bounds": v["number_concentration_m3"] > 0 and v["liquid_water_content_kg_m3"] > 0 and z > 0 and rain > 0,
        }
    except (ValueError, TypeError, OverflowError, ZeroDivisionError):
        return {"finite_schema": False}
