"""Known values, limiting cases, rejected domains, and independent output checks."""
from copy import deepcopy
import math

import pytest

from ciw import weather_thermo as weather


def example(profile):
    return deepcopy(weather.PROFILES[profile]["example"])


@pytest.mark.parametrize("profile", weather.PROFILES)
def test_examples_have_finite_declared_outputs_and_pass_checks(profile):
    inputs = example(profile)
    before = deepcopy(inputs)
    outputs = weather.compute(profile, inputs)
    assert inputs == before
    assert set(outputs) == set(weather.PROFILES[profile]["units"])
    assert all(type(value) is float and math.isfinite(value) for value in outputs.values())
    assert all(weather.checks(profile, inputs, outputs).values())


@pytest.mark.parametrize("profile", weather.PROFILES)
def test_every_output_is_checked_independently_of_compute(profile, monkeypatch):
    inputs = example(profile)
    outputs = weather.compute(profile, inputs)
    monkeypatch.setattr(weather, "compute", lambda *_: pytest.fail("checks must not rerun compute"))
    assert all(weather.checks(profile, inputs, outputs).values())
    for field, value in outputs.items():
        changed = dict(outputs, **{field: value + max(abs(value) * 0.01, 0.01)})
        assert not all(weather.checks(profile, inputs, changed).values()), field


@pytest.mark.parametrize("profile", weather.PROFILES)
def test_exact_input_contract_and_no_nonfinite_or_boolean_numbers(profile):
    inputs = example(profile)
    with pytest.raises(ValueError):
        weather.validate(profile, dict(inputs, extra=1))
    for field, value in inputs.items():
        if type(value) in (float, int):
            for bad in (True, False, float("inf"), float("nan"), "1", None, 10**160):
                changed = dict(inputs, **{field: bad})
                with pytest.raises(ValueError):
                    weather.validate(profile, changed)
    del inputs[next(iter(inputs))]
    with pytest.raises(ValueError):
        weather.validate(profile, inputs)


@pytest.mark.parametrize("profile", weather.PROFILES)
def test_malformed_outputs_fail_closed(profile):
    inputs = example(profile)
    outputs = weather.compute(profile, inputs)
    assert not all(weather.checks(profile, inputs, {}).values())
    for value in (True, float("nan"), float("inf"), "0"):
        outputs[next(iter(outputs))] = value
        assert not all(weather.checks(profile, inputs, outputs).values())


def test_unknown_profiles_and_phase_are_rejected():
    for profile in ("unknown", True, [], None):
        with pytest.raises(ValueError):
            weather.compute(profile, {})
    for phase in ("auto", "liquid", True, [], None):
        inputs = example("thermodynamics")
        inputs["phase"] = phase
        with pytest.raises(ValueError):
            weather.compute("thermodynamics", inputs)


def test_thermodynamic_reference_at_freezing_and_dry_limit():
    inputs = dict(example("thermodynamics"), temperature_k=273.15, relative_humidity=0.0,
                  layer_top_pressure_pa=50000.0)
    v = weather.compute("thermodynamics", inputs)
    assert v["saturation_vapor_pressure_pa"] == pytest.approx(611.21)
    assert v["vapor_pressure_pa"] == v["mixing_ratio_kg_kg"] == v["specific_humidity_kg_kg"] == 0.0
    assert v["virtual_temperature_k"] == v["potential_temperature_k"] == 273.15
    # Independently evaluated with Decimal at 40-digit precision, using declared constants.
    assert v["density_kg_m3"] == pytest.approx(1.2753848210649444, rel=1e-12)
    assert v["layer_thickness_m"] == pytest.approx(5541.9619735377400, rel=1e-12)
    assert all(weather.checks("thermodynamics", inputs, v).values())


def test_buck_water_ice_phase_reference_and_humidity_mass_balance():
    inputs = dict(example("thermodynamics"), temperature_k=253.15, relative_humidity=1.0)
    water = weather.compute("thermodynamics", inputs)
    ice = weather.compute("thermodynamics", dict(inputs, phase="ice"))
    assert water["saturation_vapor_pressure_pa"] == pytest.approx(125.5841, rel=1e-6)
    assert ice["saturation_vapor_pressure_pa"] == pytest.approx(103.2859, rel=1e-6)
    assert ice["saturation_vapor_pressure_pa"] < water["saturation_vapor_pressure_pa"]
    assert water["vapor_pressure_pa"] == water["saturation_vapor_pressure_pa"]
    assert water["virtual_temperature_k"] > inputs["temperature_k"]
    for result in (water, ice):
        r, q = result["mixing_ratio_kg_kg"], result["specific_humidity_kg_kg"]
        assert q / (1 - q) == pytest.approx(r)


@pytest.mark.parametrize("phase,temperature", [("water", 233.15), ("water", 323.15), ("ice", 223.15), ("ice", 273.15)])
def test_temperature_domain_endpoints_and_zero_layer(phase, temperature):
    inputs = dict(example("thermodynamics"), phase=phase, temperature_k=temperature,
                  layer_top_pressure_pa=100000.0)
    output = weather.compute("thermodynamics", inputs)
    assert output["layer_thickness_m"] == 0.0
    assert all(weather.checks("thermodynamics", inputs, output).values())


@pytest.mark.parametrize("overrides", [
    {"temperature_k": 233.14}, {"temperature_k": 323.16},
    {"phase": "ice", "temperature_k": 273.16}, {"phase": "ice", "temperature_k": 223.14},
    {"pressure_pa": 0}, {"pressure_pa": 110001}, {"relative_humidity": -0.01},
    {"relative_humidity": 1.01}, {"layer_top_pressure_pa": 100001}, {"layer_top_pressure_pa": 9999},
    {"temperature_k": 323.15, "pressure_pa": 20000, "relative_humidity": 1.0, "layer_top_pressure_pa": 10000},
])
def test_thermodynamic_domain_rejects_invalid_combinations(overrides):
    with pytest.raises(ValueError):
        weather.compute("thermodynamics", dict(example("thermodynamics"), **overrides))


def test_gray_blackbody_radiative_equilibrium_and_transparent_column():
    inputs = dict(example("radiation"), toa_direct_normal_w_m2=1000.0,
                  solar_cosine=0.5, optical_depth=0.0, albedo=1.0, emissivity=1.0,
                  surface_temperature_k=300.0, downwelling_longwave_w_m2=459.300327939)
    result = weather.compute("radiation", inputs)
    assert result["beam_transmittance"] == 1.0
    assert result["direct_shortwave_w_m2"] == 500.0
    assert result["emitted_longwave_w_m2"] == pytest.approx(459.300327939)
    assert result["net_radiation_w_m2"] == pytest.approx(0.0, abs=1e-10)
    assert all(weather.checks("radiation", inputs, result).values())


def test_beer_attenuation_optical_depth_and_zero_emissivity():
    inputs = dict(example("radiation"), optical_depth=0.5, solar_cosine=0.5, emissivity=0.0)
    result = weather.compute("radiation", inputs)
    assert result["beam_transmittance"] == pytest.approx(1 / math.e)
    assert result["net_longwave_w_m2"] == result["emitted_longwave_w_m2"] == 0.0
    assert result["net_radiation_w_m2"] == result["net_shortwave_w_m2"]
    thick = weather.compute("radiation", dict(inputs, optical_depth=20.0, solar_cosine=0.05))
    assert 0 < thick["beam_transmittance"] < 1e-170
    assert all(weather.checks("radiation", dict(inputs, optical_depth=20.0, solar_cosine=0.05), thick).values())


@pytest.mark.parametrize("field,bad", [("solar_cosine", 0.0), ("solar_cosine", 1.01),
    ("optical_depth", -0.01), ("optical_depth", 20.1), ("albedo", -0.1), ("emissivity", 1.01),
    ("surface_temperature_k", 0), ("downwelling_longwave_w_m2", -1), ("toa_direct_normal_w_m2", 2001)])
def test_radiation_domain_rejections(field, bad):
    with pytest.raises(ValueError):
        weather.compute("radiation", dict(example("radiation"), **{field: bad}))


def test_single_drop_bin_moments_dbz_and_empirical_zr_reference():
    inputs = dict(example("radar_cloud"), drop_bins=[{"diameter_mm": 1.0, "concentration_m3": 200.0}])
    result = weather.compute("radar_cloud", inputs)
    assert result["number_concentration_m3"] == 200.0
    assert result["reflectivity_mm6_m3"] == 200.0
    assert result["reflectivity_dbz"] == pytest.approx(23.01029995664)
    assert result["liquid_water_content_kg_m3"] == pytest.approx(math.pi / 30000.0)
    assert result["empirical_rain_rate_mm_h"] == 1.0


def test_radar_diameter_sixth_power_vs_mass_cubic_scaling():
    inputs = dict(example("radar_cloud"), drop_bins=[{"diameter_mm": 1.0, "concentration_m3": 10.0}])
    one = weather.compute("radar_cloud", inputs)
    inputs["drop_bins"][0]["diameter_mm"] = 2.0
    two = weather.compute("radar_cloud", inputs)
    assert two["reflectivity_mm6_m3"] / one["reflectivity_mm6_m3"] == 64.0
    assert two["liquid_water_content_kg_m3"] / one["liquid_water_content_kg_m3"] == 8.0


def test_radar_tiny_positive_moments_are_not_hidden_by_absolute_tolerance():
    inputs = dict(example("radar_cloud"), drop_bins=[{"diameter_mm": 0.01, "concentration_m3": 1e-6}])
    result = weather.compute("radar_cloud", inputs)
    assert all(weather.checks("radar_cloud", inputs, result).values())
    for field in ("liquid_water_content_kg_m3", "reflectivity_mm6_m3", "number_concentration_m3"):
        changed = dict(result, **{field: result[field] * 1.01})
        assert not all(weather.checks("radar_cloud", inputs, changed).values())


@pytest.mark.parametrize("bins", [[], (), [{}], [{"diameter_mm": 1.0, "concentration_m3": 0.0}],
    [{"diameter_mm": 1.0, "concentration_m3": -1.0}],
    [{"diameter_mm": True, "concentration_m3": 1.0}],
    [{"diameter_mm": 1.0, "concentration_m3": float("nan")}],
    [{"diameter_mm": 8.0, "concentration_m3": 1e8}],
    [{"diameter_mm": 1.0, "concentration_m3": 1.0, "bin_width_mm": 1.0}],
    [{"diameter_mm": 1.0, "concentration_m3": 1.0}] * 129])
def test_radar_bin_rejections(bins):
    with pytest.raises(ValueError):
        weather.compute("radar_cloud", dict(example("radar_cloud"), drop_bins=bins))


def test_radar_rayleigh_guard_and_coefficient_bounds():
    with pytest.raises(ValueError, match="Rayleigh"):
        weather.compute("radar_cloud", dict(example("radar_cloud"), wavelength_m=0.01))
    for field, value in (("zr_a", 0.0), ("zr_b", 0.0), ("wavelength_m", 0.0)):
        with pytest.raises(ValueError):
            weather.compute("radar_cloud", dict(example("radar_cloud"), **{field: value}))
