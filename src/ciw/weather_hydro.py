"""Bounded hydrometeorology and cryosphere teaching/reference calculations.

These are local, deterministic numerical models, not observations, forecasts,
state admission, or calibrated catchment/snow/ice models. Daily bucket ordering
is precipitation -> infiltration/overflow -> ET -> fractional drainage. Snow
energy is supplied *after* cold-content warming, at a melting point of 0 deg C.

Formula sources (retrieved 2026-10-03):
* FAO Irrigation and Drainage Paper 56, equations 6, 8, 11, 13, 21--25, 34:
  https://www.fao.org/4/x0490e/x0490e06.htm
  https://www.fao.org/4/x0490e/x0490e07.htm
  https://www.fao.org/4/x0490e/x0490e08.htm (worked example 18)
* USACE EM 1110-2-1406, snow energy and water budgets:
  https://www.publications.usace.army.mil/Portals/76/Publications/EngineerManuals/EM_1110-2-1406.pdf
* Zhaka et al., A review of level ice and brash ice growth models (2022),
  Journal of Glaciology, doi:10.1017/jog.2021.126 (Stefan approximation).

The bucket and precipitation partition are explicitly declared reduced models;
neither is claimed to implement HEC-HMS or a calibrated hydrologic method.
"""
from __future__ import annotations

import math

from .control_contracts import keys, number

MAX_DAYS = 366
LATENT_FUSION_MJ_KG = 0.334
SIGMA = 5.670374419e-8
ICE_CONDUCTIVITY = 2.2
ICE_DENSITY = 917.0

PROFILES = {
    "evapotranspiration": {
        "scope": "FAO56 daily grass reference evapotranspiration with prescribed net radiation and vapour pressure.",
        "limitations": [
            "Daily reference grass only; not actual crop ET, open-water evaporation, or frozen-surface sublimation.",
            "Wind is measured at 2 m; net radiation and soil heat flux are prescribed daily energy totals.",
            "Negative raw ET is retained as a condensation diagnostic; the nonnegative reference demand clips it to zero.",
            "No input uncertainty propagation or field calibration; vapour supersaturation is refused.",
        ],
        "example": {"minimum_temperature_c": 12.3, "maximum_temperature_c": 21.5,
                    "actual_vapour_pressure_kpa": 1.409, "air_pressure_kpa": 100.1,
                    "wind_2m_m_s": 2.078, "net_radiation_mj_m2_day": 13.28,
                    "soil_heat_mj_m2_day": 0.0},
        "units": {"saturation_vapour_pressure_kpa": "kPa", "vapour_pressure_deficit_kpa": "kPa",
                  "slope_kpa_per_k": "kPa/K", "psychrometric_kpa_per_k": "kPa/K",
                  "radiation_component_mm_day": "mm/day", "aerodynamic_component_mm_day": "mm/day",
                  "raw_et0_mm_day": "mm/day", "reference_et0_mm_day": "mm/day"},
    },
    "water_balance": {
        "scope": "Conservative daily single-store infiltration, runoff, ET and drainage bucket, 1..366 days.",
        "limitations": [
            "Conceptual bucket with prescribed capacity, infiltration limit and daily drainage fraction; no Richards equation or routing.",
            "Daily ordering is infiltration/overflow, then ET, then drainage; subdaily storm timing is unresolved.",
            "Inputs are liquid water; convert snowmelt externally. No groundwater exchange, frozen soil, or calibrated flood prediction.",
        ],
        "example": {"initial_storage_mm": 40.0, "capacity_mm": 100.0,
                    "infiltration_limit_mm_day": 25.0, "drainage_fraction_per_day": 0.1,
                    "precipitation_mm_day": [0.0, 50.0, 5.0, 0.0],
                    "potential_et_mm_day": [4.0, 3.0, 4.0, 5.0]},
        "units": {"storage_mm": "mm", "infiltration_mm": "mm", "runoff_mm": "mm",
                  "actual_et_mm": "mm", "drainage_mm": "mm", "total_runoff_mm": "mm",
                  "total_actual_et_mm": "mm", "total_drainage_mm": "mm", "mass_residual_mm": "mm"},
    },
    "snow_ice": {
        "scope": "Daily precipitation phase partition and energy-limited melt of a ripe 0 deg C snowpack, 1..366 days.",
        "limitations": [
            "Melt energy is prescribed nonnegative energy available after snowpack warming; no negative-energy cooling or cold-content state.",
            "Linear air-temperature rain/snow partition is a declared assumption; thresholds need local calibration.",
            "Snow water equivalent is mass per area expressed as liquid-water depth, not snow depth.",
            "No refreezing, sublimation, liquid retention, compaction, drifting, glacier dynamics or avalanche prediction.",
        ],
        "example": {"initial_swe_mm": 50.0, "snow_below_c": 0.0, "rain_above_c": 2.0,
                    "precipitation_mm": [10.0, 10.0, 5.0, 0.0],
                    "air_temperature_c": [-5.0, 1.0, 4.0, 3.0],
                    "melt_energy_mj_m2": [0.0, 0.334, 3.34, 33.4]},
        "units": {"swe_mm": "mm", "snowfall_mm": "mm", "rainfall_mm": "mm",
                  "melt_mm": "mm", "liquid_outflow_mm": "mm", "used_melt_energy_mj_m2": "MJ/m2",
                  "unused_melt_energy_mj_m2": "MJ/m2", "mass_residual_mm": "mm"},
    },
    "polar_radiation": {
        "scope": "Approximate daily TOA solar geometry, including polar day/night, and prescribed surface energy balance.",
        "limitations": [
            "FAO56 orbital approximation with geometric horizon; no refraction, terrain shading, spectral transfer or observed climatology.",
            "FAO notes reduced winter validity beyond 55 degrees latitude; exact polar branches prevent singularities but do not improve astronomical accuracy.",
            "Shortwave transmissivity, albedo, incoming longwave, temperature and turbulent/ground fluxes are prescribed.",
            "Surface energy residual is a diagnostic, not a prognostic temperature, climate feedback model, or melt estimate.",
        ],
        "example": {"latitude_deg": 75.0, "day_of_year": 172, "shortwave_transmissivity": 0.65,
                    "albedo": 0.75, "emissivity": 0.98, "surface_temperature_k": 273.15,
                    "downward_longwave_w_m2": 260.0, "upward_sensible_w_m2": 10.0,
                    "upward_latent_w_m2": 5.0, "downward_ground_w_m2": 2.0},
        "units": {"solar_declination_rad": "rad", "inverse_relative_distance": "1",
                  "sunset_hour_angle_rad": "rad", "daylight_hours": "h",
                  "toa_radiation_mj_m2_day": "MJ/m2/day", "downward_shortwave_w_m2": "W/m2",
                  "absorbed_shortwave_w_m2": "W/m2", "emitted_longwave_w_m2": "W/m2",
                  "net_longwave_w_m2": "W/m2", "net_radiation_w_m2": "W/m2",
                  "surface_energy_residual_w_m2": "W/m2"},
    },
    "ice_growth": {
        "scope": "Quasi-steady one-phase Stefan growth of freshwater ice under prescribed constant surface temperature.",
        "limitations": [
            "Fixed k=2.2 W/(m K), density=917 kg/m3 and latent heat=334000 J/kg; water stays at its 0 deg C freezing point.",
            "Neglects ice heat capacity, snow insulation, salinity, water heat flux, solar absorption and mechanical deformation.",
            "Surface temperature is prescribed, not inferred from air temperature. This is not ice load-bearing or travel-safety guidance.",
        ],
        "example": {"initial_thickness_m": 0.1, "surface_temperature_c": -10.0,
                    "duration_days": 10.0},
        "units": {"freezing_degree_days": "K day", "final_thickness_m": "m",
                  "growth_m": "m", "latent_heat_released_mj_m2": "MJ/m2"},
    },
}


def _bound(value: object, low: float, high: float, field: str) -> float:
    result = number(value)
    if not low <= result <= high:
        raise ValueError(f"{field} must lie in [{low}, {high}]")
    return result


def _series(value: object, low: float, high: float, field: str) -> None:
    if type(value) is not list or not 1 <= len(value) <= MAX_DAYS:
        raise ValueError(f"{field} requires 1..{MAX_DAYS} daily samples")
    for item in value:
        _bound(item, low, high, field)


def _saturation(temperature_c: float) -> float:
    return 0.6108 * math.exp(17.27 * temperature_c / (temperature_c + 237.3))


def validate(profile: str, inputs: dict) -> None:
    if type(profile) is not str or profile not in PROFILES:
        raise ValueError("Unknown hydrometeorology profile")
    keys(inputs, set(PROFILES[profile]["example"]))
    if profile == "evapotranspiration":
        lo = _bound(inputs["minimum_temperature_c"], -30.0, 50.0, "minimum_temperature_c")
        hi = _bound(inputs["maximum_temperature_c"], -30.0, 50.0, "maximum_temperature_c")
        if lo > hi:
            raise ValueError("Minimum temperature exceeds maximum")
        _bound(inputs["actual_vapour_pressure_kpa"], 0, (_saturation(lo) + _saturation(hi)) / 2,
               "actual_vapour_pressure_kpa")
        _bound(inputs["air_pressure_kpa"], 50, 110, "air_pressure_kpa")
        _bound(inputs["wind_2m_m_s"], 0, 30, "wind_2m_m_s")
        _bound(inputs["net_radiation_mj_m2_day"], -30, 50, "net_radiation_mj_m2_day")
        _bound(inputs["soil_heat_mj_m2_day"], -20, 20, "soil_heat_mj_m2_day")
    elif profile == "water_balance":
        capacity = _bound(inputs["capacity_mm"], 0.001, 10000, "capacity_mm")
        _bound(inputs["initial_storage_mm"], 0, capacity, "initial_storage_mm")
        _bound(inputs["infiltration_limit_mm_day"], 0, 2000, "infiltration_limit_mm_day")
        _bound(inputs["drainage_fraction_per_day"], 0, 1, "drainage_fraction_per_day")
        _series(inputs["precipitation_mm_day"], 0, 2000, "precipitation_mm_day")
        _series(inputs["potential_et_mm_day"], 0, 100, "potential_et_mm_day")
        if len(inputs["precipitation_mm_day"]) != len(inputs["potential_et_mm_day"]):
            raise ValueError("Daily input lengths differ")
    elif profile == "snow_ice":
        _bound(inputs["initial_swe_mm"], 0, 10000, "initial_swe_mm")
        snow = _bound(inputs["snow_below_c"], -10, 5, "snow_below_c")
        rain = _bound(inputs["rain_above_c"], -5, 10, "rain_above_c")
        if rain - snow < 0.1:
            raise ValueError("Rain threshold must exceed snow threshold by at least 0.1 C")
        _series(inputs["precipitation_mm"], 0, 2000, "precipitation_mm")
        _series(inputs["air_temperature_c"], -80, 50, "air_temperature_c")
        _series(inputs["melt_energy_mj_m2"], 0, 100, "melt_energy_mj_m2")
        if len({len(inputs[name]) for name in ("precipitation_mm", "air_temperature_c", "melt_energy_mj_m2")}) != 1:
            raise ValueError("Daily input lengths differ")
    elif profile == "polar_radiation":
        _bound(inputs["latitude_deg"], -90, 90, "latitude_deg")
        if type(inputs["day_of_year"]) is not int or not 1 <= inputs["day_of_year"] <= 366:
            raise ValueError("day_of_year requires an integer in 1..366")
        for name in ("shortwave_transmissivity", "albedo", "emissivity"):
            _bound(inputs[name], 0, 1, name)
        _bound(inputs["surface_temperature_k"], 180, 330, "surface_temperature_k")
        _bound(inputs["downward_longwave_w_m2"], 0, 700, "downward_longwave_w_m2")
        for name in ("upward_sensible_w_m2", "upward_latent_w_m2", "downward_ground_w_m2"):
            _bound(inputs[name], -500, 500, name)
    else:
        _bound(inputs["initial_thickness_m"], 0, 10, "initial_thickness_m")
        _bound(inputs["surface_temperature_c"], -60, 0, "surface_temperature_c")
        _bound(inputs["duration_days"], 0, 366, "duration_days")


def compute(profile: str, inputs: dict) -> dict:
    validate(profile, inputs)
    p = inputs
    if profile == "evapotranspiration":
        mean = (p["minimum_temperature_c"] + p["maximum_temperature_c"]) / 2
        es = (_saturation(p["minimum_temperature_c"]) + _saturation(p["maximum_temperature_c"])) / 2
        delta = 4098 * _saturation(mean) / (mean + 237.3) ** 2
        gamma = 0.000665 * p["air_pressure_kpa"]
        deficit = es - p["actual_vapour_pressure_kpa"]
        denom = delta + gamma * (1 + 0.34 * p["wind_2m_m_s"])
        radiative = 0.408 * delta * (p["net_radiation_mj_m2_day"] - p["soil_heat_mj_m2_day"]) / denom
        aerodynamic = gamma * 900 / (mean + 273) * p["wind_2m_m_s"] * deficit / denom
        return {"saturation_vapour_pressure_kpa": es, "vapour_pressure_deficit_kpa": deficit,
                "slope_kpa_per_k": delta, "psychrometric_kpa_per_k": gamma,
                "radiation_component_mm_day": radiative, "aerodynamic_component_mm_day": aerodynamic,
                "raw_et0_mm_day": radiative + aerodynamic, "reference_et0_mm_day": max(0.0, radiative + aerodynamic)}
    if profile == "water_balance":
        storage = [float(p["initial_storage_mm"])]
        infiltration, runoff, aet, drainage = [], [], [], []
        for rain, demand in zip(p["precipitation_mm_day"], p["potential_et_mm_day"]):
            inf = min(rain, p["infiltration_limit_mm_day"], max(0.0, p["capacity_mm"] - storage[-1]))
            available = storage[-1] + inf
            evaporated = min(demand, available)
            drained = p["drainage_fraction_per_day"] * (available - evaporated)
            infiltration.append(float(inf))
            runoff.append(float(rain - inf))
            aet.append(float(evaporated))
            drainage.append(float(drained))
            storage.append(available - evaporated - drained)
        return {"storage_mm": storage, "infiltration_mm": infiltration, "runoff_mm": runoff,
                "actual_et_mm": aet, "drainage_mm": drainage, "total_runoff_mm": math.fsum(runoff),
                "total_actual_et_mm": math.fsum(aet), "total_drainage_mm": math.fsum(drainage),
                "mass_residual_mm": math.fsum([storage[0], *p["precipitation_mm_day"], -storage[-1],
                                               *(-v for v in runoff), *(-v for v in aet), *(-v for v in drainage)])}
    if profile == "snow_ice":
        swe = [float(p["initial_swe_mm"])]
        snowfall, rainfall, melt, outflow, used, unused = [], [], [], [], [], []
        for precip, temp, energy in zip(p["precipitation_mm"], p["air_temperature_c"], p["melt_energy_mj_m2"]):
            fraction = min(1.0, max(0.0, (p["rain_above_c"] - temp) / (p["rain_above_c"] - p["snow_below_c"])))
            snow = precip * fraction
            rain = precip - snow
            melted = min(swe[-1] + snow, energy / LATENT_FUSION_MJ_KG)
            consumed = melted * LATENT_FUSION_MJ_KG
            snowfall.append(snow)
            rainfall.append(rain)
            melt.append(melted)
            outflow.append(rain + melted)
            used.append(consumed)
            unused.append(max(0.0, energy - consumed))
            swe.append(swe[-1] + snow - melted)
        return {"swe_mm": swe, "snowfall_mm": snowfall, "rainfall_mm": rainfall, "melt_mm": melt,
                "liquid_outflow_mm": outflow, "used_melt_energy_mj_m2": used,
                "unused_melt_energy_mj_m2": unused,
                "mass_residual_mm": math.fsum([swe[0], *p["precipitation_mm"], -swe[-1], *(-v for v in outflow)])}
    if profile == "polar_radiation":
        phi = math.radians(p["latitude_deg"])
        phase = 2 * math.pi * p["day_of_year"] / 365
        declination = 0.409 * math.sin(phase - 1.39)
        distance = 1 + 0.033 * math.cos(phase)
        a, b = math.sin(phi) * math.sin(declination), math.cos(phi) * math.cos(declination)
        if a >= b:
            angle = math.pi
        elif a <= -b:
            angle = 0.0
        else:
            angle = math.acos(-a / b)
        toa = max(0.0, 1440 / math.pi * 0.0820 * distance * (angle * a + b * math.sin(angle)))
        sw = toa / 0.0864 * p["shortwave_transmissivity"]
        absorbed = sw * (1 - p["albedo"])
        emitted = p["emissivity"] * SIGMA * p["surface_temperature_k"] ** 4
        net_lw = p["emissivity"] * p["downward_longwave_w_m2"] - emitted
        net_rad = absorbed + net_lw
        return {"solar_declination_rad": declination, "inverse_relative_distance": distance,
                "sunset_hour_angle_rad": angle, "daylight_hours": 24 * angle / math.pi,
                "toa_radiation_mj_m2_day": toa, "downward_shortwave_w_m2": sw,
                "absorbed_shortwave_w_m2": absorbed, "emitted_longwave_w_m2": emitted,
                "net_longwave_w_m2": net_lw, "net_radiation_w_m2": net_rad,
                "surface_energy_residual_w_m2": net_rad - p["upward_sensible_w_m2"] - p["upward_latent_w_m2"] - p["downward_ground_w_m2"]}
    exposure = -p["surface_temperature_c"] * p["duration_days"]
    addition = 2 * ICE_CONDUCTIVITY * exposure * 86400 / (ICE_DENSITY * LATENT_FUSION_MJ_KG * 1e6)
    thickness = math.sqrt(p["initial_thickness_m"] ** 2 + addition)
    # Rationalized increment avoids cancellation for weak forcing on thick ice.
    growth = addition / (thickness + p["initial_thickness_m"]) if addition else 0.0
    return {"freezing_degree_days": exposure, "final_thickness_m": thickness, "growth_m": growth,
            "latent_heat_released_mj_m2": growth * ICE_DENSITY * LATENT_FUSION_MJ_KG}


def _near(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=2e-10, abs_tol=2e-9)


def _output_contract(profile: str, values: dict, series_lengths: dict[str, int]) -> bool:
    try:
        keys(values, set(PROFILES[profile]["units"]))
        for key, value in values.items():
            if key in series_lengths:
                if type(value) is not list or len(value) != series_lengths[key]:
                    return False
                for item in value:
                    number(item)
            else:
                number(value)
    except (ValueError, TypeError, OverflowError):
        return False
    return True


def checks(profile: str, inputs: dict, values: dict) -> dict[str, bool]:
    """Check equations and conservation against retained inputs, never rerun compute.

    Checks establish numerical consistency within these explicit model equations;
    they do not validate atmospheric/catchment truth or observational provenance.
    """
    validate(profile, inputs)
    p, v = inputs, values
    lengths = {}
    if profile == "water_balance":
        n = len(p["precipitation_mm_day"])
        lengths = {name: n for name in ("infiltration_mm", "runoff_mm", "actual_et_mm", "drainage_mm")}
        lengths["storage_mm"] = n + 1
    elif profile == "snow_ice":
        n = len(p["precipitation_mm"])
        lengths = {name: n for name in PROFILES[profile]["units"] if name not in {"swe_mm", "mass_residual_mm"}}
        lengths["swe_mm"] = n + 1
    if not _output_contract(profile, v, lengths):
        return {"output_contract": False}
    result = {"output_contract": True}
    if profile == "evapotranspiration":
        mean = (p["minimum_temperature_c"] + p["maximum_temperature_c"]) * 0.5
        # Direct source equations, no forward-model helper dependency.
        expected_es = math.fsum(0.3054 * math.exp(17.27 * p[t] / (237.3 + p[t]))
                               for t in ("minimum_temperature_c", "maximum_temperature_c"))
        slope_numerator = 4098 * 0.6108 * math.exp(17.27 * mean / (237.3 + mean))
        delta, gamma = v["slope_kpa_per_k"], v["psychrometric_kpa_per_k"]
        den = delta + gamma + 0.34 * gamma * p["wind_2m_m_s"]
        result.update({
            "saturation_equation": _near(v["saturation_vapour_pressure_kpa"], expected_es),
            "vapour_deficit": _near(v["vapour_pressure_deficit_kpa"] + p["actual_vapour_pressure_kpa"], expected_es),
            "slope_equation": _near(delta * (237.3 + mean) ** 2, slope_numerator),
            "psychrometric_equation": _near(gamma, 0.000665 * p["air_pressure_kpa"]),
            "radiation_equation": _near(v["radiation_component_mm_day"] * den,
                                          0.408 * delta * (p["net_radiation_mj_m2_day"] - p["soil_heat_mj_m2_day"])),
            "aerodynamic_equation": _near(v["aerodynamic_component_mm_day"] * den * (mean + 273),
                                            900 * gamma * p["wind_2m_m_s"] * v["vapour_pressure_deficit_kpa"]),
            "et_sum": _near(v["raw_et0_mm_day"], v["radiation_component_mm_day"] + v["aerodynamic_component_mm_day"]),
            "nonnegative_demand": _near(v["reference_et0_mm_day"], max(0, v["raw_et0_mm_day"])),
        })
    elif profile == "water_balance":
        store, inf, runoff, et, drainage = (v[name] for name in ("storage_mm", "infiltration_mm", "runoff_mm", "actual_et_mm", "drainage_mm"))
        result["initial_storage"] = _near(store[0], p["initial_storage_mm"])
        result["storage_bounds"] = all(-2e-9 <= s <= p["capacity_mm"] + 2e-9 for s in store)
        for i, (rain, demand) in enumerate(zip(p["precipitation_mm_day"], p["potential_et_mm_day"])):
            available = store[i] + inf[i]
            # Complementarity verifies each limited flux without invoking the solver.
            result[f"day_{i}_infiltration"] = (inf[i] >= -2e-9 and inf[i] <= rain + 2e-9 and
                inf[i] <= p["infiltration_limit_mm_day"] + 2e-9 and inf[i] <= p["capacity_mm"] - store[i] + 2e-9 and
                any(_near(inf[i], limit) for limit in (rain, p["infiltration_limit_mm_day"], p["capacity_mm"] - store[i])))
            result[f"day_{i}_runoff"] = runoff[i] >= -2e-9 and _near(rain, runoff[i] + inf[i])
            result[f"day_{i}_et"] = (0 <= et[i] <= demand + 2e-9 and et[i] <= available + 2e-9 and
                                       (_near(et[i], demand) or _near(et[i], available)))
            result[f"day_{i}_drainage"] = _near(drainage[i], p["drainage_fraction_per_day"] * (available - et[i]))
            result[f"day_{i}_mass"] = _near(store[i] + rain, store[i + 1] + runoff[i] + et[i] + drainage[i])
        for total, series in (("total_runoff_mm", runoff), ("total_actual_et_mm", et), ("total_drainage_mm", drainage)):
            result[total] = _near(v[total], math.fsum(series))
        residual = math.fsum([p["initial_storage_mm"], *p["precipitation_mm_day"], -store[-1],
                              *(-x for x in runoff), *(-x for x in et), *(-x for x in drainage)])
        result["mass_residual_value"] = _near(v["mass_residual_mm"], residual)
        result["global_conservation"] = abs(residual) < 1e-7
    elif profile == "snow_ice":
        swe, snow, rain, melt, out, used, unused = (v[name] for name in (
            "swe_mm", "snowfall_mm", "rainfall_mm", "melt_mm", "liquid_outflow_mm", "used_melt_energy_mj_m2", "unused_melt_energy_mj_m2"))
        result["initial_swe"] = _near(swe[0], p["initial_swe_mm"])
        result["nonnegative_water_energy"] = all(x >= -2e-9 for name in lengths for x in v[name])
        for i, (precip, temp, energy) in enumerate(zip(p["precipitation_mm"], p["air_temperature_c"], p["melt_energy_mj_m2"])):
            if temp <= p["snow_below_c"]:
                partition = _near(snow[i], precip)
            elif temp >= p["rain_above_c"]:
                partition = _near(snow[i], 0)
            else:
                partition = _near(snow[i] * (p["rain_above_c"] - p["snow_below_c"]), precip * (p["rain_above_c"] - temp))
            result[f"day_{i}_phase"] = partition and _near(snow[i] + rain[i], precip)
            result[f"day_{i}_melt_energy"] = _near(used[i], melt[i] * LATENT_FUSION_MJ_KG)
            result[f"day_{i}_energy_closure"] = _near(used[i] + unused[i], energy)
            result[f"day_{i}_melt_limit"] = (melt[i] <= swe[i] + snow[i] + 2e-9 and used[i] <= energy + 2e-9 and
                (_near(melt[i], swe[i] + snow[i]) or _near(used[i], energy)))
            result[f"day_{i}_outflow"] = _near(out[i], rain[i] + melt[i])
            result[f"day_{i}_mass"] = _near(swe[i] + precip, swe[i + 1] + out[i])
        residual = math.fsum([p["initial_swe_mm"], *p["precipitation_mm"], -swe[-1], *(-x for x in out)])
        result["mass_residual_value"] = _near(v["mass_residual_mm"], residual)
        result["global_conservation"] = abs(residual) < 1e-7
    elif profile == "polar_radiation":
        phi, omega = math.radians(p["latitude_deg"]), v["sunset_hour_angle_rad"]
        declination, distance = v["solar_declination_rad"], v["inverse_relative_distance"]
        phase = 2 * math.pi * p["day_of_year"] / 365
        a, b = math.sin(phi) * math.sin(declination), math.cos(phi) * math.cos(declination)
        if a >= b:
            sunset_ok = _near(omega, math.pi)
        elif a <= -b:
            sunset_ok = _near(omega, 0)
        else:
            sunset_ok = 0 < omega < math.pi and _near(a + b * math.cos(omega), 0)
        result.update({
            "declination_equation": _near(declination, 0.409 * math.sin(phase - 1.39)),
            "distance_equation": _near(distance, 1 + 0.033 * math.cos(phase)),
            "sunset_geometry": sunset_ok,
            "daylength_equation": 0 <= v["daylight_hours"] <= 24 and _near(v["daylight_hours"] * math.pi, 24 * omega),
            "toa_integral": v["toa_radiation_mj_m2_day"] >= 0 and _near(v["toa_radiation_mj_m2_day"] * math.pi,
                                     max(0, 1440 * 0.0820 * distance * (omega * a + b * math.sin(omega)))),
            "shortwave_transmission": _near(v["downward_shortwave_w_m2"] * 0.0864,
                                              v["toa_radiation_mj_m2_day"] * p["shortwave_transmissivity"]),
            "shortwave_absorption": _near(v["absorbed_shortwave_w_m2"], v["downward_shortwave_w_m2"] * (1 - p["albedo"])),
            "thermal_emission": _near(v["emitted_longwave_w_m2"], SIGMA * p["emissivity"] * p["surface_temperature_k"] ** 4),
            "longwave_balance": _near(v["net_longwave_w_m2"] + v["emitted_longwave_w_m2"], p["emissivity"] * p["downward_longwave_w_m2"]),
            "net_radiation": _near(v["net_radiation_w_m2"], v["absorbed_shortwave_w_m2"] + v["net_longwave_w_m2"]),
            "surface_balance": _near(v["net_radiation_w_m2"], v["surface_energy_residual_w_m2"] +
                                         p["upward_sensible_w_m2"] + p["upward_latent_w_m2"] + p["downward_ground_w_m2"]),
        })
    else:
        result.update({
            "freezing_exposure": _near(v["freezing_degree_days"], -p["surface_temperature_c"] * p["duration_days"]),
            "stefan_integral": _near(v["growth_m"] * (v["final_thickness_m"] + p["initial_thickness_m"]) *
                                        ICE_DENSITY * LATENT_FUSION_MJ_KG * 1e6,
                                        2 * ICE_CONDUCTIVITY * v["freezing_degree_days"] * 86400),
            "growth_nonnegative": v["final_thickness_m"] >= 0 and v["growth_m"] >= 0,
            "growth_increment": _near(v["growth_m"] + p["initial_thickness_m"], v["final_thickness_m"]),
            "latent_energy": _near(v["latent_heat_released_mj_m2"], v["growth_m"] * ICE_DENSITY * LATENT_FUSION_MJ_KG),
        })
    # Retain compact per-mechanism checks even for a full year; every step is
    # inspected, without exceeding the shared record dictionary-size bound.
    daily_groups: dict[str, list[bool]] = {}
    for name in list(result):
        if name.startswith("day_"):
            mechanism = name.split("_", 2)[2]
            daily_groups.setdefault(mechanism, []).append(result.pop(name))
    result.update({f"daily_{name}": all(flags) for name, flags in daily_groups.items()})
    return result
