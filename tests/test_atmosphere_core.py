from copy import deepcopy
import math

import pytest

from ciw.atmosphere_compiler import compile_atmosphere
from ciw.atmosphere_contract import (
    CONSTANTS, MAX_SAMPLES, STATE_FIELDS, UNITS, example_request, request_digest,
    validate_request, validate_result,
)
from ciw.operations.runner import seal


def test_default_column_matches_known_dry_standard_lapse_values():
    request = example_request()
    result = compile_atmosphere(request)
    profile = result["profile"]
    validate_result(request, result)
    # Independent rounded dry standard-lapse values, not an executable copy
    # of the compiler's expressions. This is a synthetic numerical check.
    assert profile["temperature_k"][0] == 288.15
    assert profile["pressure_pa"][0] == 101325.0
    assert profile["density_kg_per_m3"][0] == pytest.approx(1.2250123, rel=1e-7)
    assert profile["sound_speed_m_per_s"][0] == pytest.approx(340.29229, rel=1e-7)
    assert profile["dynamic_viscosity_pa_s"][0] == pytest.approx(1.7892976e-5, rel=1e-7)
    assert profile["temperature_k"][-1] == pytest.approx(223.15)
    assert profile["pressure_pa"][-1] == pytest.approx(26435.9, rel=5e-6)
    assert profile["density_kg_per_m3"][-1] == pytest.approx(0.412705, rel=5e-6)
    for field in ("temperature_k", "pressure_pa", "density_kg_per_m3", "sound_speed_m_per_s"):
        assert all(left > right for left, right in zip(profile[field], profile[field][1:]))
    assert all(left < right for left, right in zip(profile["potential_temperature_k"],
                                                   profile["potential_temperature_k"][1:]))
    assert result["constants"] == CONSTANTS
    assert result["units"] == UNITS


def test_isothermal_pressure_half_height_retains_thermodynamic_consistency():
    request = example_request()
    request["profile"]["lapse_rate_k_per_m"] = 0.0
    # Analytic scale-height consequence: after H*log(2), pressure and density
    # halve while temperature, sound speed and dynamic viscosity stay fixed.
    half_height = 287.05 * 288.15 / 9.80665 * math.log(2.0)
    request["sampling"]["height_m"] = [0.0, half_height]
    profile = compile_atmosphere(request)["profile"]
    assert profile["pressure_pa"][1] == pytest.approx(profile["pressure_pa"][0] / 2, rel=1e-14)
    assert profile["density_kg_per_m3"][1] == pytest.approx(profile["density_kg_per_m3"][0] / 2, rel=1e-14)
    for field in ("temperature_k", "sound_speed_m_per_s", "dynamic_viscosity_pa_s"):
        assert profile[field][0] == profile[field][1]
    assert profile["kinematic_viscosity_m2_per_s"][1] == pytest.approx(
        2 * profile["kinematic_viscosity_m2_per_s"][0], rel=1e-14)


@pytest.mark.parametrize("lapse", [1e-12, 1e-100, 1e-320])
def test_near_zero_lapse_is_continuous_even_for_subnormal_declarations(lapse):
    request = example_request()
    request["profile"]["lapse_rate_k_per_m"] = 0.0
    isothermal = compile_atmosphere(request)
    request["profile"]["lapse_rate_k_per_m"] = lapse
    result = compile_atmosphere(request)
    validate_result(request, result)
    for field in STATE_FIELDS:
        if field not in {"height_m", "wind_enu_m_per_s"}:
            assert result["profile"][field] == pytest.approx(isothermal["profile"][field], rel=1e-10)


def test_pressure_gradient_obeys_local_hydrostatic_force_balance():
    request = example_request()
    request["sampling"]["height_m"] = [0.0, 999.99, 1000.0, 1000.01]
    profile = compile_atmosphere(request)["profile"]
    derivative = (profile["pressure_pa"][3] - profile["pressure_pa"][1]) / 0.02
    force_density = -9.80665 * profile["density_kg_per_m3"][2]
    assert derivative == pytest.approx(force_density, rel=2e-10)


def test_origin_time_and_source_bind_declaration_without_changing_relative_column():
    request = example_request()
    first = compile_atmosphere(request)
    request["reference"].update(height_origin_m=1000.0)
    request["reference"]["context"] = {
        "source_kind": "declared_environment", "source_ref": "test.site.column-1",
        "valid_time_utc": "2026-10-03T06:15:40Z",
    }
    second = compile_atmosphere(request)
    assert first["profile"] == second["profile"]
    assert first["request_digest"] != second["request_digest"]
    assert first["record_digest"] != second["record_digest"]
    assert second["request_digest"] == request_digest(request)


def test_upper_height_and_temperature_bounds_and_maximum_grid_are_supported():
    request = example_request()
    request["reference"]["temperature_k"] = 279.0
    request["profile"]["lapse_rate_k_per_m"] = 0.009
    request["sampling"]["height_m"] = [11000.0 * index / 128 for index in range(129)]
    result = compile_atmosphere(request)
    validate_result(request, result)
    assert len(result["profile"]["height_m"]) == MAX_SAMPLES
    assert result["profile"]["temperature_k"][-1] == 180.0
    request["reference"]["temperature_k"] = 278.999
    with pytest.raises(ValueError, match="180 K"):
        compile_atmosphere(request)


def test_irregular_declared_heights_and_external_enu_wind_pass_through_detached():
    request = example_request()
    request["sampling"]["height_m"] = [0, 0.1, 2, 999, 10999]
    request["profile"]["wind_enu_m_per_s"] = [30, -20, 1]
    result = compile_atmosphere(request)
    assert result["profile"]["height_m"] == request["sampling"]["height_m"]
    assert result["profile"]["wind_enu_m_per_s"] == [[30, -20, 1]] * 5
    assert all(a is not b for a, b in zip(result["profile"]["wind_enu_m_per_s"],
                                         result["profile"]["wind_enu_m_per_s"][1:]))
    request["profile"]["wind_enu_m_per_s"][0] = 99
    assert result["profile"]["wind_enu_m_per_s"][0][0] == 30


@pytest.mark.parametrize("path,value", [
    (("reference", "temperature_k"), True),
    (("reference", "temperature_k"), 249.0),
    (("reference", "temperature_k"), float("nan")),
    (("reference", "pressure_pa"), 120001.0),
    (("reference", "height_origin_m"), -501.0),
    (("reference", "frame"), "world.enu.v1"),
    (("profile", "lapse_rate_k_per_m"), -0.001),
    (("profile", "lapse_rate_k_per_m"), 0.01),
    (("profile", "lapse_rate_k_per_m"), True),
    (("profile", "gravity_m_per_s2"), 9.81),
    (("profile", "composition"), "humid_air"),
    (("profile", "wind_enu_m_per_s"), [0, 0]),
    (("profile", "wind_enu_m_per_s"), [0, True, 0]),
    (("profile", "wind_enu_m_per_s"), [0, 301, 0]),
    (("sampling", "height_m"), [1, 2]),
    (("sampling", "height_m"), [0, 0, 1]),
    (("sampling", "height_m"), [0, 2, 1]),
    (("sampling", "height_m"), [0, 11001]),
    (("sampling", "height_m"), [0, True]),
    (("sampling", "height_m"), [0]),
    (("sampling", "height_m"), [float(index) for index in range(130)]),
    (("sampling", "interpretation"), "absolute_altitude"),
    (("tolerances", "constitutive_relative"), True),
    (("tolerances", "quadrature_relative"), 0.1),
])
def test_strict_bounds_physical_declarations_and_grid_types(path, value):
    request = example_request()
    request[path[0]][path[1]] = value
    with pytest.raises(ValueError):
        validate_request(request)
    with pytest.raises(ValueError):
        compile_atmosphere(request)


@pytest.mark.parametrize("timestamp", [
    "2026-10-03T06:15:40Z", "2026-10-03T06:15:40.123456+00:00",
])
def test_explicit_utc_context_is_accepted(timestamp):
    request = example_request()
    request["reference"]["context"]["valid_time_utc"] = timestamp
    assert validate_request(request) == request


@pytest.mark.parametrize("field,value", [
    ("source_kind", "measured"), ("source_kind", []),
    ("source_ref", " "), ("source_ref", "x" * 161),
    ("valid_time_utc", True), ("valid_time_utc", "2026-10-03"),
    ("valid_time_utc", "2026-10-03T06:15:40"),
    ("valid_time_utc", "2026-10-03T02:15:40-04:00"),
    ("valid_time_utc", "2026-02-30T06:15:40Z"),
])
def test_source_context_is_bounded_and_time_requires_utc(field, value):
    request = example_request()
    request["reference"]["context"][field] = value
    with pytest.raises(ValueError):
        validate_request(request)


def test_unknown_fields_scope_observables_and_duplicate_observables_are_rejected():
    for mutate in (
        lambda request: request.update(extra="weather"),
        lambda request: request.update(scope="forecast"),
        lambda request: request["profile"].update(humidity=0.5),
        lambda request: request["reference"]["context"].update(calibrated=True),
        lambda request: request["desired_observables"].append("unrecognized"),
        lambda request: request["desired_observables"].append("temperature"),
        lambda request: request.update(desired_observables=[[]]),
    ):
        request = example_request()
        mutate(request)
        with pytest.raises(ValueError):
            validate_request(request)


def test_known_expansion_requests_do_not_silently_extend_the_compiled_physics():
    request = example_request()
    original = compile_atmosphere(request)
    request["desired_observables"].extend(["material_conditioning", "fluid_dynamics", "visual_scattering"])
    result = compile_atmosphere(request)
    assert result["profile"] == original["profile"]
    assert result["request_digest"] != original["request_digest"]
    assert "humidity" not in result["profile"]


def test_read_only_validator_accepts_resealed_scientific_errors_for_independent_audit(monkeypatch):
    request = example_request()
    result = compile_atmosphere(request)
    result["profile"]["pressure_pa"][3] *= 0.8
    seal(result)
    monkeypatch.setattr("ciw.atmosphere_compiler.compile_atmosphere",
                        lambda *args: pytest.fail("Static validation called the compiler"))
    detached = validate_result(request, result)
    assert detached == result
    detached["profile"]["pressure_pa"][3] = 1
    assert result["profile"]["pressure_pa"][3] != 1


@pytest.mark.parametrize("mutate", [
    lambda result: result["profile"]["pressure_pa"].pop(),
    lambda result: result["profile"]["height_m"].__setitem__(2, 2001),
    lambda result: result["profile"]["density_kg_per_m3"].__setitem__(1, True),
    lambda result: result["profile"]["pressure_pa"].__setitem__(1, -1),
    lambda result: result["profile"]["pressure_pa"].__setitem__(1, 1e21),
    lambda result: result["profile"]["wind_enu_m_per_s"].__setitem__(1, [1, 2]),
    lambda result: result["profile"]["wind_enu_m_per_s"].__setitem__(1, [1, 2, True]),
    lambda result: result["units"].update(pressure_pa="hPa"),
    lambda result: result["units"].update(altitude="m"),
    lambda result: result["constants"].update(gravity_m_per_s2=9.81),
    lambda result: result["constants"].update(heat_capacity_ratio=True),
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


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_properties_are_rejected_before_content_encoding(value):
    request = example_request()
    result = compile_atmosphere(request)
    result["profile"]["temperature_k"][1] = value
    with pytest.raises(ValueError):
        validate_result(request, result)


def test_content_tamper_and_context_rebinding_cannot_preserve_a_valid_seal():
    request = example_request()
    result = compile_atmosphere(request)
    result["profile"]["pressure_pa"][3] *= 0.99
    with pytest.raises(ValueError):
        validate_result(request, result)
    result = compile_atmosphere(request)
    request["reference"]["context"]["source_ref"] = "different.declaration"
    with pytest.raises(ValueError):
        validate_result(request, result)


def test_request_validation_and_compilation_do_not_mutate_input():
    request = example_request()
    before = deepcopy(request)
    detached = validate_request(request)
    compile_atmosphere(request)
    assert request == before
    detached["reference"]["context"]["source_ref"] = "different"
    detached["sampling"]["height_m"].append(11000.0)
    assert request == before
