"""Analytic/reference values, conservation and refusal coverage for hydro/cryo."""
from copy import deepcopy
from decimal import Decimal, localcontext
import math
import random

import pytest

from ciw import weather_hydro as hydro


def example(profile):
    return deepcopy(hydro.PROFILES[profile]["example"])


@pytest.mark.parametrize("profile", hydro.PROFILES)
def test_examples_satisfy_independent_checks_and_declared_units(profile):
    inputs = example(profile)
    before = deepcopy(inputs)
    result = hydro.compute(profile, inputs)
    assert inputs == before
    assert set(result) == set(hydro.PROFILES[profile]["units"])
    verified = hydro.checks(profile, inputs, result)
    assert verified and all(verified.values()), verified
    assert all(type(value) is bool for value in verified.values())


def test_fao56_published_daily_uccle_example_18():
    # FAO56 chapter 4, example 18: rounding in the printed meteorology gives
    # 3.88 mm/day, with 2.81 radiative + 1.07 aerodynamic contributions.
    result = hydro.compute("evapotranspiration", example("evapotranspiration"))
    assert result["saturation_vapour_pressure_kpa"] == pytest.approx(1.997, abs=0.001)
    assert result["slope_kpa_per_k"] == pytest.approx(0.122, abs=0.001)
    assert result["radiation_component_mm_day"] == pytest.approx(2.81, abs=0.01)
    assert result["aerodynamic_component_mm_day"] == pytest.approx(1.07, abs=0.01)
    assert result["reference_et0_mm_day"] == pytest.approx(3.88, abs=0.015)


def test_et_saturated_calm_air_zero_available_energy_and_signed_condensation():
    inputs = example("evapotranspiration")
    inputs.update(wind_2m_m_s=0.0, net_radiation_mj_m2_day=0.0)
    result = hydro.compute("evapotranspiration", inputs)
    assert result["reference_et0_mm_day"] == 0
    inputs["net_radiation_mj_m2_day"] = -2
    result = hydro.compute("evapotranspiration", inputs)
    assert result["raw_et0_mm_day"] < 0
    assert result["reference_et0_mm_day"] == 0
    assert all(hydro.checks("evapotranspiration", inputs, result).values())


def test_bucket_analytic_order_and_saturated_overflow():
    inputs = example("water_balance")
    inputs.update(initial_storage_mm=95.0, capacity_mm=100.0, infiltration_limit_mm_day=50.0,
                  drainage_fraction_per_day=0.25, precipitation_mm_day=[20.0, 0.0], potential_et_mm_day=[4.0, 100.0])
    result = hydro.compute("water_balance", inputs)
    assert result["infiltration_mm"] == [5.0, 0.0]
    assert result["runoff_mm"] == [15.0, 0.0]
    assert result["actual_et_mm"] == [4.0, 72.0]
    assert result["drainage_mm"] == [24.0, 0.0]
    assert result["storage_mm"] == [95.0, 72.0, 0.0]
    assert result["mass_residual_mm"] == 0


def test_bucket_full_year_conservation_and_bounded_check_record():
    rng = random.Random(4240)
    inputs = example("water_balance")
    inputs.update(precipitation_mm_day=[rng.uniform(0, 2000) for _ in range(366)],
                  potential_et_mm_day=[rng.uniform(0, 100) for _ in range(366)])
    result = hydro.compute("water_balance", inputs)
    verified = hydro.checks("water_balance", inputs, result)
    assert all(verified.values()), verified
    assert len(verified) < 30
    assert abs(result["mass_residual_mm"]) < 1e-7
    assert min(result["storage_mm"]) >= 0
    assert max(result["storage_mm"]) <= inputs["capacity_mm"]


def test_snow_partition_energy_and_exhaustion_are_mass_conservative():
    result = hydro.compute("snow_ice", example("snow_ice"))
    assert result["snowfall_mm"] == [10, 5, 0, 0]
    assert result["rainfall_mm"] == [0, 5, 5, 0]
    assert result["melt_mm"] == pytest.approx([0, 1, 10, 54])
    assert result["swe_mm"] == pytest.approx([50, 60, 64, 54, 0])
    assert result["liquid_outflow_mm"] == pytest.approx([0, 6, 15, 54])
    assert result["unused_melt_energy_mj_m2"][-1] == pytest.approx(33.4 - 54 * 0.334)
    assert result["mass_residual_mm"] == pytest.approx(0, abs=1e-12)


def test_zero_snow_does_not_create_melt_when_energy_is_available():
    inputs = example("snow_ice")
    inputs.update(initial_swe_mm=0, precipitation_mm=[0], air_temperature_c=[10], melt_energy_mj_m2=[33.4])
    result = hydro.compute("snow_ice", inputs)
    assert result["swe_mm"] == [0, 0]
    assert result["melt_mm"] == [0]
    assert result["unused_melt_energy_mj_m2"] == [33.4]
    assert all(hydro.checks("snow_ice", inputs, result).values())


def test_full_year_snow_mass_and_energy_budgets():
    rng = random.Random(4310)
    inputs = example("snow_ice")
    inputs.update(precipitation_mm=[rng.uniform(0, 100) for _ in range(366)],
                  air_temperature_c=[rng.uniform(-10, 10) for _ in range(366)],
                  melt_energy_mj_m2=[rng.uniform(0, 100) for _ in range(366)])
    result = hydro.compute("snow_ice", inputs)
    verified = hydro.checks("snow_ice", inputs, result)
    assert all(verified.values()), verified
    assert len(verified) < 30
    assert sum(result["used_melt_energy_mj_m2"]) + sum(result["unused_melt_energy_mj_m2"]) == pytest.approx(sum(inputs["melt_energy_mj_m2"]))


def test_fao56_published_extraterrestrial_radiation_and_daylength_examples_8_9():
    inputs = example("polar_radiation")
    inputs.update(latitude_deg=-20, day_of_year=246)
    result = hydro.compute("polar_radiation", inputs)
    assert result["toa_radiation_mj_m2_day"] == pytest.approx(32.2, abs=0.1)
    assert result["daylight_hours"] == pytest.approx(11.7, abs=0.05)


@pytest.mark.parametrize("latitude", [-90, -89.999999, -75, 75, 89.999999, 90])
@pytest.mark.parametrize("day", [172, 355])
def test_polar_day_and_night_no_domain_errors(latitude, day):
    inputs = example("polar_radiation")
    inputs.update(latitude_deg=latitude, day_of_year=day)
    result = hydro.compute("polar_radiation", inputs)
    summer = (latitude > 0 and day == 172) or (latitude < 0 and day == 355)
    assert result["daylight_hours"] == (24 if summer else 0)
    assert (result["toa_radiation_mj_m2_day"] > 0) is summer
    assert all(hydro.checks("polar_radiation", inputs, result).values())


@pytest.mark.parametrize("latitude,day", [(0, 81), (45, 172), (-55, 355), (75, 172), (90, 355)])
def test_daily_solar_integral_matches_independent_midpoint_quadrature(latitude, day):
    inputs = example("polar_radiation")
    inputs.update(latitude_deg=latitude, day_of_year=day)
    result = hydro.compute("polar_radiation", inputs)
    # Integrate positive instantaneous horizontal insolation across a full day,
    # independent of the analytic sunset branch used in the implementation.
    bins = 20000
    phi = math.radians(latitude)
    delta = 0.409 * math.sin(2 * math.pi * day / 365 - 1.39)
    solar = 0.0820 * (1 + 0.033 * math.cos(2 * math.pi * day / 365))
    integral = math.fsum(max(0, math.sin(phi) * math.sin(delta) +
                               math.cos(phi) * math.cos(delta) * math.cos(-math.pi + 2 * math.pi * (i + .5) / bins))
                         for i in range(bins)) * solar * 1440 / bins
    assert result["toa_radiation_mj_m2_day"] == pytest.approx(integral, rel=2e-7, abs=2e-7)


def test_black_surface_longwave_equilibrium_and_perfect_reflector():
    inputs = example("polar_radiation")
    inputs.update(albedo=1, emissivity=1, upward_sensible_w_m2=0, upward_latent_w_m2=0,
                  downward_ground_w_m2=0, downward_longwave_w_m2=hydro.SIGMA * 273.15 ** 4)
    result = hydro.compute("polar_radiation", inputs)
    assert result["absorbed_shortwave_w_m2"] == 0
    assert result["surface_energy_residual_w_m2"] == 0


def test_stefan_decimal_reference_and_square_root_time_scaling():
    inputs = example("ice_growth")
    inputs.update(initial_thickness_m=0, duration_days=1)
    result = hydro.compute("ice_growth", inputs)
    with localcontext() as ctx:
        ctx.prec = 40
        expected = (Decimal(2) * Decimal("2.2") * Decimal(10) * Decimal(86400) /
                    (Decimal(917) * Decimal(334000))).sqrt()
    assert result["final_thickness_m"] == pytest.approx(float(expected), rel=2e-15)
    inputs["duration_days"] = 4
    later = hydro.compute("ice_growth", inputs)
    assert later["final_thickness_m"] == pytest.approx(2 * result["final_thickness_m"], rel=2e-15)


@pytest.mark.parametrize("thickness,temperature,duration", [(0, 0, 0), (10, 0, 366), (10, -1e-8, 1e-8), (10, -10, 1e-10), (10, -60, 366)])
def test_stefan_zero_and_weak_forcing_preserve_valid_checks(thickness, temperature, duration):
    inputs = dict(initial_thickness_m=thickness, surface_temperature_c=temperature, duration_days=duration)
    result = hydro.compute("ice_growth", inputs)
    checked = hydro.checks("ice_growth", inputs, result)
    assert all(checked.values()), checked
    if temperature == 0:
        assert result["growth_m"] == 0


@pytest.mark.parametrize("profile", hydro.PROFILES)
def test_verifier_does_not_call_forward_solver(profile, monkeypatch):
    inputs = example(profile)
    result = hydro.compute(profile, inputs)
    monkeypatch.setattr(hydro, "compute", lambda *args: pytest.fail("Verifier called forward solver"))
    assert all(hydro.checks(profile, inputs, result).values())


@pytest.mark.parametrize("profile", hydro.PROFILES)
def test_every_output_and_every_history_element_detects_tampering(profile):
    inputs = example(profile)
    result = hydro.compute(profile, inputs)
    for field, value in result.items():
        indices = range(len(value)) if type(value) is list else [None]
        for index in indices:
            altered = deepcopy(result)
            if index is None:
                altered[field] += max(1.0, abs(value) * .01)
            else:
                altered[field][index] += max(1.0, abs(value[index]) * .01)
            checked = hydro.checks(profile, inputs, altered)
            assert not all(checked.values()), (profile, field, index, checked)


@pytest.mark.parametrize("profile", hydro.PROFILES)
@pytest.mark.parametrize("invalid", [True, None, "1", float("nan"), float("inf")])
def test_strict_scalar_and_sample_input_types(profile, invalid):
    for field, original in example(profile).items():
        inputs = example(profile)
        if type(original) is list:
            inputs[field][0] = invalid
        else:
            inputs[field] = invalid
        with pytest.raises(ValueError):
            hydro.compute(profile, inputs)


@pytest.mark.parametrize("profile", hydro.PROFILES)
def test_exact_input_output_keys_and_bad_numeric_outputs_refused(profile):
    inputs = example(profile)
    for changed in ({**inputs, "unrecognized": 1}, {k: v for i, (k, v) in enumerate(inputs.items()) if i}):
        with pytest.raises(ValueError):
            hydro.compute(profile, changed)
    result = hydro.compute(profile, inputs)
    for bad in ({}, {**result, "injected": 1}, None):
        assert hydro.checks(profile, inputs, bad) == {"output_contract": False}
    for name, value in result.items():
        for invalid in (True, None, "1", float("nan"), float("inf")):
            bad = deepcopy(result)
            if type(value) is list:
                bad[name][0] = invalid
            else:
                bad[name] = invalid
            assert hydro.checks(profile, inputs, bad) == {"output_contract": False}


@pytest.mark.parametrize("profile,field,value", [
    ("evapotranspiration", "minimum_temperature_c", 22),
    ("evapotranspiration", "actual_vapour_pressure_kpa", 100),
    ("evapotranspiration", "wind_2m_m_s", -1),
    ("evapotranspiration", "air_pressure_kpa", 0),
    ("water_balance", "initial_storage_mm", 101),
    ("water_balance", "capacity_mm", 0),
    ("water_balance", "drainage_fraction_per_day", 1.1),
    ("water_balance", "infiltration_limit_mm_day", -1),
    ("water_balance", "precipitation_mm_day", [-1]),
    ("snow_ice", "initial_swe_mm", -1),
    ("snow_ice", "rain_above_c", 0),
    ("snow_ice", "melt_energy_mj_m2", [-1]),
    ("polar_radiation", "day_of_year", 172.0),
    ("polar_radiation", "day_of_year", 367),
    ("polar_radiation", "latitude_deg", 90.1),
    ("polar_radiation", "albedo", 1.01),
    ("polar_radiation", "surface_temperature_k", 0),
    ("ice_growth", "initial_thickness_m", -1),
    ("ice_growth", "surface_temperature_c", 1),
    ("ice_growth", "duration_days", -1),
])
def test_physical_bounds(profile, field, value):
    inputs = example(profile)
    inputs[field] = value
    with pytest.raises(ValueError):
        hydro.compute(profile, inputs)


@pytest.mark.parametrize("profile,field", [("water_balance", "precipitation_mm_day"), ("snow_ice", "precipitation_mm")])
@pytest.mark.parametrize("values", [[], [0] * 367, [0], (0, 0, 0, 0)])
def test_series_sizes_container_types_and_matching_lengths(profile, field, values):
    inputs = example(profile)
    inputs[field] = values
    with pytest.raises(ValueError):
        hydro.compute(profile, inputs)


def test_unknown_profile_refused():
    for value in ("unknown", None, [], True):
        with pytest.raises(ValueError):
            hydro.compute(value, {})
