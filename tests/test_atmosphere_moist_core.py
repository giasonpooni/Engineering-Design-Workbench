from copy import deepcopy
import math

import pytest

from ciw.atmosphere_compiler import compile_atmosphere as compile_dry_atmosphere
from ciw.atmosphere_contract import example_request as dry_example_request
from ciw.atmosphere_moist_compiler import compile_atmosphere, mixture_properties
from ciw.atmosphere_moist_contract import (
    CONSTANTS, MAX_SAMPLES, MIXTURE_FIELDS, STATE_FIELDS, UNITS, example_request,
    request_digest, validate_request, validate_result,
)
from ciw.operations.runner import seal


def _dry_declaration(moist_request):
    request = dry_example_request()
    request["reference"] = deepcopy(moist_request["reference"])
    request["sampling"] = deepcopy(moist_request["sampling"])
    request["profile"].update({field: deepcopy(moist_request["profile"][field])
                               for field in ("lapse_rate_k_per_m", "wind_enu_m_per_s",
                                             "gravity_m_per_s2")})
    return request


def test_default_ideal_mixture_matches_rounded_numerical_reference():
    request = example_request()
    result = compile_atmosphere(request)
    validate_result(request, result)
    assert result["constants"] == CONSTANTS
    assert result["units"] == UNITS
    assert set(result["mixture"]) == set(MIXTURE_FIELDS)
    mixture = result["mixture"]
    assert mixture["gas_constant_j_per_kg_k"] == pytest.approx(288.43452381, rel=1e-10)
    assert mixture["specific_heat_cp_j_per_kg_k"] == pytest.approx(1011.49924603, rel=1e-10)
    assert mixture["specific_heat_cv_j_per_kg_k"] == pytest.approx(723.06472222, rel=1e-10)
    assert mixture["heat_capacity_ratio"] == pytest.approx(1.3989055405, rel=1e-10)
    profile = result["profile"]
    assert profile["density_kg_per_m3"][0] == pytest.approx(1.1782421562, rel=1e-9)
    assert profile["water_vapour_pressure_pa"][0] == pytest.approx(1286.6799430, rel=1e-9)
    assert profile["liquid_water_saturation_pressure_pa"][0] == pytest.approx(3160.0569165, rel=1e-9)
    assert profile["relative_humidity"][0] == pytest.approx(0.4071698634, rel=1e-9)
    assert profile["liquid_equilibrium_dew_point_k"][0] == pytest.approx(283.87421586, rel=1e-10)
    assert profile["pressure_pa"][-1] == pytest.approx(90290.8964073, rel=1e-10)
    assert profile["relative_humidity"][-1] == pytest.approx(0.5396320765, rel=1e-9)
    assert profile["frozen_sound_speed_m_per_s"][0] == pytest.approx(346.84482787, rel=1e-10)


@pytest.mark.parametrize("lapse", [0.0, 0.0065, 1e-12, 1e-100, 1e-320])
def test_dry_limit_retains_exact_prior_binary64_scalar_fields(lapse):
    request = example_request()
    request["profile"]["water_mixing_ratio_kg_per_kg_dry_air"] = 0.0
    request["profile"]["lapse_rate_k_per_m"] = lapse
    request["sampling"]["height_m"] = [0.0, 0.001, 1.0, 377.0, 1999.0]
    request["profile"]["wind_enu_m_per_s"] = [12.0, -3.0, 1.0]
    result = compile_atmosphere(request)
    validate_result(request, result)
    moist = result["profile"]
    dry = compile_dry_atmosphere(_dry_declaration(request))["profile"]
    for moist_field, dry_field in (
        ("height_m", "height_m"), ("temperature_k", "temperature_k"),
        ("pressure_pa", "pressure_pa"), ("dry_air_partial_pressure_pa", "pressure_pa"),
        ("density_kg_per_m3", "density_kg_per_m3"),
        ("dry_air_density_kg_per_m3", "density_kg_per_m3"),
        ("frozen_sound_speed_m_per_s", "sound_speed_m_per_s"),
        ("frozen_potential_temperature_k", "potential_temperature_k"),
        ("wind_enu_m_per_s", "wind_enu_m_per_s"),
    ):
        assert moist[moist_field] == dry[dry_field]
    assert moist["water_vapour_pressure_pa"] == [0.0] * 5
    assert moist["water_vapour_density_kg_per_m3"] == [0.0] * 5
    assert moist["relative_humidity"] == [0.0] * 5
    assert moist["liquid_equilibrium_dew_point_k"] == [None] * 5
    assert result["mixture"]["heat_capacity_ratio"] == 1.4


@pytest.mark.parametrize("ratio", [0.002, 0.008, 0.02])
def test_partial_ideal_gases_preserve_declared_mass_ratio_and_total_state(ratio):
    request = example_request()
    request["profile"]["water_mixing_ratio_kg_per_kg_dry_air"] = ratio
    result = compile_atmosphere(request)
    profile, mixture = result["profile"], result["mixture"]
    for index in range(len(profile["height_m"])):
        dry_density = profile["dry_air_density_kg_per_m3"][index]
        vapour_density = profile["water_vapour_density_kg_per_m3"][index]
        density = profile["density_kg_per_m3"][index]
        assert vapour_density / dry_density == pytest.approx(ratio, rel=5e-16)
        assert vapour_density / density == pytest.approx(mixture["water_mass_fraction"], rel=5e-16)
        assert density == dry_density + vapour_density
        assert profile["dry_air_partial_pressure_pa"][index] + profile["water_vapour_pressure_pa"][index] == pytest.approx(
            profile["pressure_pa"][index], rel=5e-16)
        assert density == pytest.approx(profile["pressure_pa"][index] / (
            mixture["gas_constant_j_per_kg_k"] * profile["temperature_k"][index]), rel=5e-16)


def test_vapour_reduces_density_at_same_pressure_and_temperature():
    request = example_request()
    moist = compile_atmosphere(request)
    dry = compile_dry_atmosphere(_dry_declaration(request))
    assert moist["profile"]["density_kg_per_m3"][0] < dry["profile"]["density_kg_per_m3"][0]
    assert moist["mixture"]["gas_constant_j_per_kg_k"] > CONSTANTS["dry_air_gas_constant_j_per_kg_k"]
    assert moist["profile"]["pressure_pa"][-1] > dry["profile"]["pressure_pa"][-1]
    assert moist["mixture"]["heat_capacity_ratio"] < 1.4


def test_isothermal_scale_height_and_frozen_sound_speed():
    request = example_request()
    request["profile"]["lapse_rate_k_per_m"] = 0.0
    # At H*log(10/9), both total and partial pressures and densities fall 10%.
    gas_constant = 288.43452380952385
    height = gas_constant * 298.15 / 9.80665 * math.log(10.0 / 9.0)
    request["sampling"]["height_m"] = [0.0, height]
    profile = compile_atmosphere(request)["profile"]
    for field in ("pressure_pa", "dry_air_partial_pressure_pa", "water_vapour_pressure_pa",
                  "density_kg_per_m3", "dry_air_density_kg_per_m3", "water_vapour_density_kg_per_m3",
                  "relative_humidity"):
        assert profile[field][1] == pytest.approx(0.9 * profile[field][0], rel=1e-14)
    for field in ("temperature_k", "frozen_sound_speed_m_per_s", "liquid_water_saturation_pressure_pa"):
        assert profile[field][1] == profile[field][0]
    assert profile["liquid_equilibrium_dew_point_k"][1] < profile["liquid_equilibrium_dew_point_k"][0]


@pytest.mark.parametrize("lapse", [1e-12, 1e-100, 1e-320])
def test_near_zero_lapse_remains_continuous_for_binary64_subnormals(lapse):
    request = example_request()
    request["profile"]["lapse_rate_k_per_m"] = 0.0
    isothermal = compile_atmosphere(request)
    request["profile"]["lapse_rate_k_per_m"] = lapse
    result = compile_atmosphere(request)
    validate_result(request, result)
    for field in STATE_FIELDS:
        if field not in {"height_m", "wind_enu_m_per_s"}:
            assert result["profile"][field] == pytest.approx(isothermal["profile"][field], rel=1e-10)


def test_local_pressure_gradient_balances_total_mixture_weight():
    request = example_request()
    request["sampling"]["height_m"] = [0.0, 999.99, 1000.0, 1000.01]
    profile = compile_atmosphere(request)["profile"]
    derivative = (profile["pressure_pa"][3] - profile["pressure_pa"][1]) / 0.02
    assert derivative == pytest.approx(-9.80665 * profile["density_kg_per_m3"][2], rel=2e-10)


def test_magnus_dew_point_inverts_liquid_water_diagnostic():
    profile = compile_atmosphere(example_request())["profile"]
    for index, dew_point in enumerate(profile["liquid_equilibrium_dew_point_k"]):
        celsius_dew_point = dew_point - 273.15
        recovered_pressure = 611.2 * math.exp(17.62 * celsius_dew_point / (243.12 + celsius_dew_point))
        assert recovered_pressure == pytest.approx(profile["water_vapour_pressure_pa"][index], rel=2e-15)
        assert dew_point < profile["temperature_k"][index]


def test_supersaturated_candidate_is_retained_without_saturation_clamp_or_phase_model():
    request = example_request()
    request["reference"].update(temperature_k=293.15, pressure_pa=110000.0)
    request["profile"]["water_mixing_ratio_kg_per_kg_dry_air"] = 0.02
    request["sampling"]["height_m"] = [0.0, 1000.0, 2000.0]
    result = compile_atmosphere(request)
    validate_result(request, result)
    assert result["profile"]["relative_humidity"][0] > 1.0
    assert result["profile"]["relative_humidity"][-1] > 2.0
    assert result["profile"]["liquid_equilibrium_dew_point_k"][0] > result["profile"]["temperature_k"][0]
    assert result["mixture"]["water_mixing_ratio_kg_per_kg_dry_air"] == 0.02
    assert "condensate_density_kg_per_m3" not in result["profile"]


def test_maximum_grid_and_bounded_height_are_supported():
    request = example_request()
    request["reference"]["temperature_k"] = 293.15
    request["sampling"]["height_m"] = [2000.0 * index / 128 for index in range(129)]
    result = compile_atmosphere(request)
    validate_result(request, result)
    assert len(result["profile"]["height_m"]) == MAX_SAMPLES
    assert result["profile"]["temperature_k"][-1] == 280.15


def test_origin_context_and_wind_are_declarations_with_distinct_content_bindings():
    request = example_request()
    first = compile_atmosphere(request)
    request["reference"]["height_origin_m"] = 1200.0
    request["reference"]["context"] = {
        "source_kind": "declared_environment", "source_ref": "test.moist-column",
        "valid_time_utc": "2026-10-03T07:38:18Z",
    }
    second = compile_atmosphere(request)
    assert first["profile"] == second["profile"]
    assert first["request_digest"] != second["request_digest"]
    assert first["record_digest"] != second["record_digest"]
    assert second["request_digest"] == request_digest(request)
    request["profile"]["wind_enu_m_per_s"] = [10, -20, 1]
    request["sampling"]["height_m"] = [0, 0.1, 2, 399, 1999]
    wind_result = compile_atmosphere(request)
    assert wind_result["profile"]["wind_enu_m_per_s"] == [[10, -20, 1]] * 5
    request["profile"]["wind_enu_m_per_s"][0] = 99
    assert wind_result["profile"]["wind_enu_m_per_s"][0][0] == 10
    assert all(a is not b for a, b in zip(wind_result["profile"]["wind_enu_m_per_s"],
                                         wind_result["profile"]["wind_enu_m_per_s"][1:]))


@pytest.mark.parametrize("path,value", [
    (("reference", "temperature_k"), True), (("reference", "temperature_k"), 293.149),
    (("reference", "temperature_k"), 308.151), (("reference", "temperature_k"), float("nan")),
    (("reference", "pressure_pa"), 79999.0), (("reference", "pressure_pa"), 110001.0),
    (("reference", "height_origin_m"), -501.0), (("reference", "frame"), "world.enu.v1"),
    (("profile", "lapse_rate_k_per_m"), -0.001), (("profile", "lapse_rate_k_per_m"), 0.006501),
    (("profile", "lapse_rate_k_per_m"), True), (("profile", "gravity_m_per_s2"), 9.81),
    (("profile", "composition"), "dry_air"), (("profile", "wind_enu_m_per_s"), [0, 0]),
    (("profile", "wind_enu_m_per_s"), [0, True, 0]), (("profile", "wind_enu_m_per_s"), [0, 301, 0]),
    (("profile", "water_mixing_ratio_kg_per_kg_dry_air"), True),
    (("profile", "water_mixing_ratio_kg_per_kg_dry_air"), -0.002),
    (("profile", "water_mixing_ratio_kg_per_kg_dry_air"), 0.001999),
    (("profile", "water_mixing_ratio_kg_per_kg_dry_air"), 0.020001),
    (("profile", "water_mixing_ratio_kg_per_kg_dry_air"), float("inf")),
    (("sampling", "height_m"), [1, 2]), (("sampling", "height_m"), [0, 0, 1]),
    (("sampling", "height_m"), [0, 2, 1]), (("sampling", "height_m"), [0, 2001]),
    (("sampling", "height_m"), [0, True]), (("sampling", "height_m"), [0]),
    (("sampling", "height_m"), [float(index) for index in range(130)]),
    (("sampling", "interpretation"), "absolute_altitude"),
    (("tolerances", "constitutive_relative"), True), (("tolerances", "quadrature_relative"), 0.1),
])
def test_request_boundaries_reject_bool_aliases_unbounded_values_and_unknown_physics(path, value):
    request = example_request()
    request[path[0]][path[1]] = value
    with pytest.raises(ValueError):
        validate_request(request)
    with pytest.raises(ValueError):
        compile_atmosphere(request)


@pytest.mark.parametrize("timestamp", ["2026-10-03T07:38:18Z", "2026-10-03T07:38:18.123456+00:00"])
def test_explicit_utc_context_is_accepted(timestamp):
    request = example_request()
    request["reference"]["context"]["valid_time_utc"] = timestamp
    assert validate_request(request) == request


@pytest.mark.parametrize("field,value", [
    ("source_kind", "measured"), ("source_kind", []), ("source_ref", " "),
    ("source_ref", "x" * 161), ("valid_time_utc", True), ("valid_time_utc", "2026-10-03"),
    ("valid_time_utc", "2026-10-03T07:38:18"), ("valid_time_utc", "2026-10-03T03:38:18-04:00"),
    ("valid_time_utc", "2026-02-30T07:38:18Z"),
])
def test_context_is_bounded_and_requires_utc(field, value):
    request = example_request()
    request["reference"]["context"][field] = value
    with pytest.raises(ValueError):
        validate_request(request)


def test_request_schema_unknown_fields_and_observable_duplicates_are_rejected():
    for mutate in (
        lambda request: request.update(extra="forecast"),
        lambda request: request.update(schema="ciw.atmosphere-request.v1"),
        lambda request: request.update(scope="dry_hydrostatic_constant_gravity_column"),
        lambda request: request["profile"].update(relative_humidity=0.5),
        lambda request: request["reference"]["context"].update(calibrated=True),
        lambda request: request["desired_observables"].append("unrecognized"),
        lambda request: request["desired_observables"].append("temperature"),
        lambda request: request.update(desired_observables=[[]]),
    ):
        request = example_request()
        mutate(request)
        with pytest.raises(ValueError):
            validate_request(request)


def test_known_expansion_observables_do_not_modify_computed_physics():
    request = example_request()
    original = compile_atmosphere(request)
    request["desired_observables"].extend([
        "viscosity", "material_conditioning", "fluid_dynamics", "visual_scattering",
        "phase_change", "ice_response", "moist_adiabatic_response",
    ])
    result = compile_atmosphere(request)
    assert result["profile"] == original["profile"]
    assert result["request_digest"] != original["request_digest"]
    assert "dynamic_viscosity_pa_s" not in result["profile"]
    assert "liquid_water_density_kg_per_m3" not in result["profile"]


def test_static_validation_does_not_recompute_pressure_mixture_or_reference_physics(monkeypatch):
    request = example_request()
    result = compile_atmosphere(request)
    result["profile"]["pressure_pa"][2] *= 0.8
    result["mixture"]["specific_heat_cp_j_per_kg_k"] *= 1.1
    seal(result)
    monkeypatch.setattr("ciw.atmosphere_moist_compiler.compile_atmosphere",
                        lambda *args: pytest.fail("Static validation replayed the compiler"))
    monkeypatch.setattr("ciw.atmosphere_moist_compiler.mixture_properties",
                        lambda *args: pytest.fail("Static validation replayed mixture physics"))
    detached = validate_result(request, result)
    assert detached == result
    detached["profile"]["pressure_pa"][2] = 1.0
    assert result["profile"]["pressure_pa"][2] != 1.0


@pytest.mark.parametrize("mutate", [
    lambda result: result["profile"]["pressure_pa"].pop(),
    lambda result: result["profile"]["height_m"].__setitem__(2, 501),
    lambda result: result["profile"]["density_kg_per_m3"].__setitem__(1, True),
    lambda result: result["profile"]["pressure_pa"].__setitem__(1, -1),
    lambda result: result["profile"]["pressure_pa"].__setitem__(1, 1e21),
    lambda result: result["profile"]["water_vapour_pressure_pa"].__setitem__(1, -1),
    lambda result: result["profile"]["relative_humidity"].__setitem__(1, -1),
    lambda result: result["profile"]["liquid_equilibrium_dew_point_k"].__setitem__(1, None),
    lambda result: result["profile"]["wind_enu_m_per_s"].__setitem__(1, [1, 2]),
    lambda result: result["profile"]["wind_enu_m_per_s"].__setitem__(1, [1, 2, True]),
    lambda result: result["mixture"].update(water_mixing_ratio_kg_per_kg_dry_air=0.007),
    lambda result: result["mixture"].update(heat_capacity_ratio=True),
    lambda result: result["mixture"].update(water_mass_fraction=1.01),
    lambda result: result["mixture"].update(specific_heat_cp_j_per_kg_k=0),
    lambda result: result["mixture"].update(extra="model"),
    lambda result: result["units"].update(pressure_pa="hPa"),
    lambda result: result["units"].update(altitude="m"),
    lambda result: result["constants"].update(gravity_m_per_s2=9.81),
    lambda result: result["constants"].update(magnus_numerator_coefficient=True),
    lambda result: result.update(compiler="forecast"),
    lambda result: result.update(extra="unbounded"),
])
def test_resealed_unbounded_or_misbound_result_is_not_readable(mutate):
    request = example_request()
    result = compile_atmosphere(request)
    mutate(result)
    seal(result)
    with pytest.raises(ValueError):
        validate_result(request, result)


def test_dry_limit_requires_null_liquid_dewpoint_in_static_schema():
    request = example_request()
    request["profile"]["water_mixing_ratio_kg_per_kg_dry_air"] = 0
    result = compile_atmosphere(request)
    result["profile"]["liquid_equilibrium_dew_point_k"][1] = 273.15
    seal(result)
    with pytest.raises(ValueError, match="must be null"):
        validate_result(request, result)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_properties_are_rejected_before_seal_encoding(value):
    request = example_request()
    result = compile_atmosphere(request)
    result["profile"]["relative_humidity"][1] = value
    with pytest.raises(ValueError):
        validate_result(request, result)


def test_content_tamper_and_context_rebinding_cannot_retain_result_binding():
    request = example_request()
    result = compile_atmosphere(request)
    result["profile"]["pressure_pa"][2] *= 0.99
    with pytest.raises(ValueError):
        validate_result(request, result)
    result = compile_atmosphere(request)
    request["reference"]["context"]["source_ref"] = "different.declaration"
    with pytest.raises(ValueError):
        validate_result(request, result)


def test_request_validation_compilation_and_mixture_queries_are_detached():
    request = example_request()
    original = deepcopy(request)
    validated = validate_request(request)
    result = compile_atmosphere(request)
    mixture = mixture_properties(request)
    assert request == original
    validated["profile"]["wind_enu_m_per_s"][0] = 1
    assert request == original
    mixture["gas_constant_j_per_kg_k"] = 1
    assert result["mixture"]["gas_constant_j_per_kg_k"] != 1
