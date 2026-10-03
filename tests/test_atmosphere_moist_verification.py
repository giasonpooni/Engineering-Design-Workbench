from copy import deepcopy
import math

import pytest

from ciw.atmosphere_moist_contract import EXPANSION_OBSERVABLES, example_request, validate_result
from ciw.atmosphere_moist_compiler import compile_atmosphere
from ciw.atmosphere_moist_verification import (
    CHECK_TOLERANCES, COARSE_SUBINTERVALS, MAX_QUADRATURE_EVALUATIONS,
    MAX_RELATIVE_HUMIDITY, REFINED_SUBINTERVALS, _integrate_segment,
    validate_report, verify,
)
from ciw.operations.runner import digest, seal


@pytest.fixture(scope="module")
def qualified():
    request = example_request()
    result = compile_atmosphere(request)
    report = verify(request, result)
    assert report["status"] == "PASS"
    return request, result, report


def _failed(report, name):
    return next(row for row in report["checks"] if row["name"] == name)["status"] == "FAIL"


def _coherent_pressure_properties(result):
    """Rebuild pressure-dependent data for an adversarial candidate, not its audit."""
    mixture, profile = result["mixture"], result["profile"]
    ratio = mixture["water_mixing_ratio_kg_per_kg_dry_air"]
    for index, (temperature, pressure) in enumerate(zip(profile["temperature_k"], profile["pressure_pa"])):
        vapour = ratio * pressure / (287.05 / 461.5 + ratio)
        dry_pressure = pressure - vapour
        dry_density = dry_pressure / (287.05 * temperature)
        vapour_density = vapour / (461.5 * temperature)
        profile["water_vapour_pressure_pa"][index] = vapour
        profile["dry_air_partial_pressure_pa"][index] = dry_pressure
        profile["dry_air_density_kg_per_m3"][index] = dry_density
        profile["water_vapour_density_kg_per_m3"][index] = vapour_density
        profile["density_kg_per_m3"][index] = dry_density + vapour_density
        profile["relative_humidity"][index] = vapour / profile["liquid_water_saturation_pressure_pa"][index]
        if ratio:
            logarithm = math.log(vapour / 611.2)
            profile["liquid_equilibrium_dew_point_k"][index] = 273.15 + 243.12 * logarithm / (17.62 - logarithm)
        profile["frozen_potential_temperature_k"][index] = temperature * (1e5 / pressure) ** (
            mixture["gas_constant_j_per_kg_k"] / mixture["specific_heat_cp_j_per_kg_k"])
    seal(result)


def test_default_independent_audit_has_bounded_quadrature_and_continuous_domain(qualified):
    request, result, report = qualified
    validate_report(request, result, report)
    assert len(report["checks"]) == len(CHECK_TOLERANCES) == 30
    assert report["request_digest"] == digest(request)
    assert report["candidate_digest"] == result["record_digest"]
    assert report["qualification"]["action"] == "LOCAL"
    assert all(row["status"] == "PASS" for row in report["checks"])
    reference = report["reference"]
    assert reference["coarse_subintervals_per_segment"] == COARSE_SUBINTERVALS == 16
    assert reference["refined_subintervals_per_segment"] == REFINED_SUBINTERVALS == 32
    assert reference["segments"] == 4 and reference["quadrature_evaluations"] == 200
    assert reference["maximum_quadrature_evaluations"] == MAX_QUADRATURE_EVALUATIONS == 6400
    humidity = reference["continuous_humidity"]
    assert humidity["height_m"] == [0.0, 1000.0]
    assert humidity["maximum_allowed_relative_humidity"] == MAX_RELATIVE_HUMIDITY == 0.95
    assert math.isclose(humidity["maximum_relative_humidity"], 0.5396320764633862, rel_tol=1e-14)
    assert report["metrics"]["summary"]["sample_count"] == 5
    assert report["metrics"]["terminal"]["height_m"] == 1000.0
    assert any("pure-phase" in text for text in report["limitations"])
    assert any("conditioning or diffusion history" in text for text in report["limitations"])
    assert any("canonical state admission" in text for text in report["limitations"])


def test_retained_report_validation_does_not_replay_scientific_models(qualified, monkeypatch):
    import ciw.atmosphere_moist_compiler as compiler
    import ciw.atmosphere_moist_verification as auditor

    def forbidden(*args, **kwargs):
        raise AssertionError("Retained validation repeated moist-air physics")

    monkeypatch.setattr(compiler, "compile_atmosphere", forbidden)
    monkeypatch.setattr(compiler, "mixture_properties", forbidden)
    for name in ("verify", "_quadrature_reference", "_integrate_segment", "_mixture", "_saturation_pressure"):
        monkeypatch.setattr(auditor, name, forbidden)
    monkeypatch.setattr(auditor.math, "exp", forbidden)
    validate_report(*qualified)


def test_fresh_verifier_does_not_call_candidate_compiler_or_mixture_helper(qualified, monkeypatch):
    import ciw.atmosphere_moist_compiler as compiler

    def forbidden(*args, **kwargs):
        raise AssertionError("Independent verifier called the candidate compiler")

    monkeypatch.setattr(compiler, "compile_atmosphere", forbidden)
    monkeypatch.setattr(compiler, "mixture_properties", forbidden)
    assert verify(qualified[0], qualified[1])["status"] == "PASS"


@pytest.mark.parametrize("field,check", [
    ("temperature_k", "prescribed_temperature"), ("pressure_pa", "segment_hydrostatic_balance"),
    ("dry_air_partial_pressure_pa", "dry_partial_pressure"),
    ("water_vapour_pressure_pa", "vapour_partial_pressure"),
    ("dry_air_density_kg_per_m3", "dry_air_equation_of_state"),
    ("water_vapour_density_kg_per_m3", "water_vapour_equation_of_state"),
    ("density_kg_per_m3", "equation_of_state"), ("relative_humidity", "relative_humidity"),
    ("liquid_water_saturation_pressure_pa", "liquid_water_saturation_pressure"),
    ("liquid_equilibrium_dew_point_k", "dew_point_closure"),
    ("frozen_sound_speed_m_per_s", "frozen_sound_speed"),
    ("frozen_potential_temperature_k", "frozen_potential_temperature"),
])
def test_resealed_interior_physical_property_mutations_are_refused(qualified, field, check):
    request, original, _ = qualified
    result = deepcopy(original)
    result["profile"][field][2] *= 1.005
    seal(result)
    validate_result(request, result)
    report = verify(request, result)
    assert _failed(report, check)
    assert report["status"] == "FAIL" and report["qualification"]["action"] == "REFUSE"
    validate_report(request, result, report)


@pytest.mark.parametrize("field", ["water_mass_fraction", "gas_constant_j_per_kg_k",
    "specific_heat_cp_j_per_kg_k", "specific_heat_cv_j_per_kg_k", "heat_capacity_ratio"])
def test_resealed_mixture_metadata_is_independently_checked(qualified, field):
    request, original, _ = qualified
    result = deepcopy(original)
    result["mixture"][field] *= 1.01
    seal(result)
    validate_result(request, result)
    report = verify(request, result)
    assert _failed(report, "mixture_parameters") and report["qualification"]["action"] == "REFUSE"
    validate_report(request, result, report)


def test_coherent_constituent_errors_cannot_hide_behind_total_density(qualified):
    request, original, _ = qualified
    result = deepcopy(original)
    profile = result["profile"]
    shift = profile["water_vapour_pressure_pa"][2] * 0.01
    profile["water_vapour_pressure_pa"][2] += shift
    profile["dry_air_partial_pressure_pa"][2] -= shift
    profile["water_vapour_density_kg_per_m3"][2] = profile["water_vapour_pressure_pa"][2] / (461.5 * profile["temperature_k"][2])
    profile["dry_air_density_kg_per_m3"][2] = profile["dry_air_partial_pressure_pa"][2] / (287.05 * profile["temperature_k"][2])
    profile["density_kg_per_m3"][2] = profile["water_vapour_density_kg_per_m3"][2] + profile["dry_air_density_kg_per_m3"][2]
    seal(result)
    report = verify(request, result)
    assert not _failed(report, "partial_pressure_closure")
    assert not _failed(report, "dry_air_equation_of_state")
    assert not _failed(report, "water_vapour_equation_of_state")
    assert not _failed(report, "density_closure")
    assert _failed(report, "vapour_partial_pressure") and _failed(report, "dry_partial_pressure")
    assert _failed(report, "equation_of_state")


def test_coherent_interior_pressure_forgery_preserves_terminal_but_fails_hydrostatics(qualified):
    request, original, original_report = qualified
    result = deepcopy(original)
    result["profile"]["pressure_pa"][2] *= 1.001
    _coherent_pressure_properties(result)
    report = verify(request, result)
    assert report["metrics"]["terminal"] == original_report["metrics"]["terminal"]
    assert report["metrics"]["summary"] == original_report["metrics"]["summary"]
    assert _failed(report, "segment_hydrostatic_balance") and _failed(report, "cumulative_pressure_profile")
    for name in ("vapour_partial_pressure", "dry_partial_pressure", "equation_of_state", "density_closure", "relative_humidity", "dew_point_closure", "frozen_potential_temperature", "boundary_pressure"):
        assert not _failed(report, name)
    validate_report(request, result, report)


def test_coherently_forged_retained_report_requires_fresh_audit(qualified):
    request, original, original_report = qualified
    result = deepcopy(original)
    result["profile"]["pressure_pa"][2] *= 1.001
    _coherent_pressure_properties(result)
    forged = deepcopy(original_report)
    forged["candidate_digest"] = result["record_digest"]
    seal(forged)
    validate_report(request, result, forged)
    fresh = verify(request, result)
    assert fresh["status"] == "FAIL" and fresh["record_digest"] != forged["record_digest"]
    assert _failed(fresh, "segment_hydrostatic_balance")


def test_uniform_pressure_bias_fails_absolute_boundary_even_with_balanced_segments(qualified):
    request, original, _ = qualified
    result = deepcopy(original)
    result["profile"]["pressure_pa"] = [value * 1.01 for value in result["profile"]["pressure_pa"]]
    _coherent_pressure_properties(result)
    report = verify(request, result)
    assert not _failed(report, "segment_hydrostatic_balance")
    assert _failed(report, "boundary_pressure") and _failed(report, "cumulative_pressure_profile")
    validate_report(request, result, report)


def test_declared_wind_is_checked_at_every_sample(qualified):
    request, original, _ = qualified
    result = deepcopy(original)
    result["profile"]["wind_enu_m_per_s"][2] = [0.0, 0.25, 0.0]
    seal(result)
    report = verify(request, result)
    assert _failed(report, "prescribed_wind")
    assert report["metrics"]["summary"]["maximum_wind_speed_m_per_s"] == 0.25
    validate_report(request, result, report)


@pytest.mark.parametrize("observable", sorted(EXPANSION_OBSERVABLES))
def test_unsupported_physics_expands_only_after_numerical_and_domain_pass(observable):
    request = example_request()
    request["desired_observables"].append(observable)
    result = compile_atmosphere(request)
    report = verify(request, result)
    assert report["status"] == "PASS" and report["qualification"]["action"] == "EXPAND"
    assert report["qualification"]["unsupported_observables"] == [observable]
    validate_report(request, result, report)


@pytest.mark.parametrize("heights", [[0.0, 2000.0], [index * 2000.0 / 128 for index in range(129)]])
def test_saturated_declared_column_refuses_before_requested_cloud_or_transport_expansion(heights):
    request = example_request()
    request["reference"].update(temperature_k=293.15, pressure_pa=110000.0)
    request["profile"]["water_mixing_ratio_kg_per_kg_dry_air"] = 0.02
    request["sampling"]["height_m"] = heights
    request["desired_observables"].extend(["clouds", "viscosity"])
    result = compile_atmosphere(request)
    assert min(result["profile"]["relative_humidity"]) > 1.0
    report = verify(request, result)
    assert _failed(report, "sampled_unsaturation") and _failed(report, "continuous_unsaturation")
    assert report["status"] == "FAIL" and report["qualification"]["action"] == "REFUSE"
    assert report["qualification"]["unsupported_observables"] == ["clouds", "viscosity"]
    assert report["reference"]["continuous_humidity"]["maximum_relative_humidity"] > 2.7
    validate_report(request, result, report)


def test_continuous_unsaturation_uses_declaration_and_independent_pressure_not_candidate_rh():
    request = example_request()
    request["reference"].update(temperature_k=293.15, pressure_pa=110000.0)
    request["profile"]["water_mixing_ratio_kg_per_kg_dry_air"] = 0.02
    request["sampling"]["height_m"] = [0.0, 2000.0]
    result = compile_atmosphere(request)
    result["profile"]["relative_humidity"] = [0.2, 0.2]
    seal(result)
    report = verify(request, result)
    assert not _failed(report, "sampled_unsaturation")
    assert _failed(report, "continuous_unsaturation") and _failed(report, "relative_humidity")
    assert report["reference"]["continuous_humidity"]["relative_humidity"][0] > 1.46
    validate_report(request, result, report)


@pytest.mark.parametrize("field,value,check", [
    ("relative_humidity", math.nextafter(0.95, 1.0), "sampled_unsaturation"),
    ("temperature_k", 273.1499999, "declared_temperature_domain"),
    ("temperature_k", 308.1500001, "declared_temperature_domain"),
    ("liquid_equilibrium_dew_point_k", 253.1499999, "declared_dew_point_domain"),
    ("liquid_equilibrium_dew_point_k", 308.1500001, "declared_dew_point_domain"),
])
def test_fixed_domain_guards_cannot_be_relaxed_by_requested_tolerance(field, value, check):
    request = example_request()
    request["tolerances"] = {name: 0.01 for name in request["tolerances"]}
    result = compile_atmosphere(request)
    result["profile"][field][2] = value
    seal(result)
    report = verify(request, result)
    row = next(row for row in report["checks"] if row["name"] == check)
    assert row == {"name": check, "value": 1.0, "tolerance": 0.0, "status": "FAIL"}
    assert report["qualification"]["action"] == "REFUSE"
    validate_report(request, result, report)


@pytest.mark.parametrize("lapse", [0.0, 0.001901, 0.003, 0.0065])
def test_continuous_rh_maximum_matches_dense_endpoints_including_interior_minimum(lapse):
    request = example_request()
    request["profile"]["lapse_rate_k_per_m"] = lapse
    request["sampling"]["height_m"] = [index * 2000.0 / 128 for index in range(129)]
    result = compile_atmosphere(request)
    report = verify(request, result)
    humidity = result["profile"]["relative_humidity"]
    endpoints = [humidity[0], humidity[-1]]
    assert max(humidity) == max(endpoints)
    assert math.isclose(report["reference"]["continuous_humidity"]["maximum_relative_humidity"], max(humidity), rel_tol=1e-13)
    if lapse == 0.001901:
        assert min(humidity) < min(endpoints)
        assert 0 < humidity.index(min(humidity)) < len(humidity) - 1
    validate_report(request, result, report)


def test_zero_water_is_exact_dry_boundary_with_null_dewpoint_and_frozen_sound():
    from ciw.atmosphere_contract import example_request as dry_request
    from ciw.atmosphere_compiler import compile_atmosphere as compile_dry
    request = example_request()
    request["profile"]["water_mixing_ratio_kg_per_kg_dry_air"] = 0.0
    result = compile_atmosphere(request)
    report = verify(request, result)
    assert report["status"] == "PASS" and report["qualification"]["action"] == "LOCAL"
    assert result["mixture"]["heat_capacity_ratio"] == 1.4
    assert result["mixture"]["water_mass_fraction"] == 0.0
    assert report["metrics"]["summary"]["liquid_equilibrium_dew_point_k"] == {"minimum": None, "maximum": None}
    assert report["metrics"]["terminal"]["liquid_equilibrium_dew_point_k"] is None
    for field in ("water_vapour_pressure_pa", "water_vapour_density_kg_per_m3", "relative_humidity"):
        assert result["profile"][field] == [0.0] * 5
    assert result["profile"]["liquid_equilibrium_dew_point_k"] == [None] * 5
    old = dry_request()
    old["reference"].update(temperature_k=request["reference"]["temperature_k"], pressure_pa=request["reference"]["pressure_pa"])
    old["sampling"]["height_m"] = request["sampling"]["height_m"]
    dry = compile_dry(old)
    for moist_field, dry_field in [("temperature_k", "temperature_k"), ("pressure_pa", "pressure_pa"),
        ("density_kg_per_m3", "density_kg_per_m3"), ("frozen_sound_speed_m_per_s", "sound_speed_m_per_s"),
        ("frozen_potential_temperature_k", "potential_temperature_k")]:
        assert result["profile"][moist_field] == dry["profile"][dry_field]
    validate_report(request, result, report)


@pytest.mark.parametrize("field", ["water_vapour_pressure_pa", "water_vapour_density_kg_per_m3", "relative_humidity"])
def test_dry_limit_zero_water_state_is_exact_even_at_maximum_tolerance(field):
    request = example_request()
    request["profile"]["water_mixing_ratio_kg_per_kg_dry_air"] = 0.0
    request["tolerances"] = {name: 0.01 for name in request["tolerances"]}
    result = compile_atmosphere(request)
    result["profile"][field][2] = 1e-20
    seal(result)
    report = verify(request, result)
    assert _failed(report, "dry_limit_water_state")
    assert report["qualification"]["action"] == "REFUSE"
    validate_report(request, result, report)


@pytest.mark.parametrize("lapse", [0.0, 1e-320, 1e-16, 1e-12])
def test_isothermal_and_near_zero_lapse_pressure_are_continuous(lapse):
    request = example_request()
    request["profile"]["lapse_rate_k_per_m"] = lapse
    request["sampling"]["height_m"] = [0.0, 2000.0]
    result = compile_atmosphere(request)
    report = verify(request, result)
    assert report["status"] == "PASS"
    expected = request["reference"]["pressure_pa"] * math.exp(-9.80665 * 2000.0 / (
        result["mixture"]["gas_constant_j_per_kg_k"] * request["reference"]["temperature_k"]))
    assert math.isclose(result["profile"]["pressure_pa"][-1], expected, rel_tol=1e-10)
    validate_report(request, result, report)


@pytest.mark.parametrize("heights", [[0.0, math.nextafter(0.0, 1.0)],
    [0.0, 1.0, math.nextafter(1.0, 2.0)], [0.0, 1999.9999999999998, 2000.0]])
def test_close_height_spacing_is_bounded_and_preserves_zero_integral_limit(heights):
    request = example_request()
    request["sampling"]["height_m"] = heights
    result = compile_atmosphere(request)
    report = verify(request, result)
    assert report["status"] == "PASS"
    validate_report(request, result, report)


def test_tight_quadrature_tolerance_requires_resolution_without_silent_relaxation():
    request = example_request()
    request["reference"]["temperature_k"] = 293.15
    request["profile"]["water_mixing_ratio_kg_per_kg_dry_air"] = 0.002
    request["sampling"]["height_m"] = [0.0, 2000.0]
    request["tolerances"]["quadrature_relative"] = 1e-12
    result = compile_atmosphere(request)
    report = verify(request, result)
    assert _failed(report, "quadrature_refinement")
    assert report["qualification"]["action"] == "REFUSE"
    assert report["thresholds"]["quadrature_relative"] == 1e-12
    validate_report(request, result, report)
    request["sampling"]["height_m"] = [index * 2000.0 / 32 for index in range(33)]
    result = compile_atmosphere(request)
    report = verify(request, result)
    assert report["status"] == "PASS"
    validate_report(request, result, report)


def test_maximum_grid_consumes_exact_bounded_quadrature_budget():
    request = example_request()
    request["sampling"]["height_m"] = [index * 2000.0 / 128 for index in range(129)]
    result = compile_atmosphere(request)
    report = verify(request, result)
    assert report["status"] == "PASS" and report["reference"]["quadrature_evaluations"] == 6400
    validate_report(request, result, report)


@pytest.mark.parametrize("subintervals", [0, 1, 3, True, 16.0])
def test_simpson_rule_requires_positive_even_integer_count(subintervals):
    with pytest.raises(ValueError):
        _integrate_segment(example_request(), 0.0, 1000.0, subintervals)


def test_simpson_rule_rejects_outside_fixed_temperature_domain():
    with pytest.raises(ValueError, match="temperature"):
        _integrate_segment(example_request(), 0.0, 20000.0, 16)


@pytest.mark.parametrize("field,value", [
    ("temperature_k", 1e-20), ("temperature_k", 30.03), ("temperature_k", 1e20),
    ("pressure_pa", 1e-20), ("pressure_pa", 1e20),
    ("liquid_equilibrium_dew_point_k", 1e-20), ("liquid_equilibrium_dew_point_k", 1e20),
])
def test_extreme_finite_retained_candidates_generate_sealable_failed_reports(qualified, field, value):
    request, original, _ = qualified
    result = deepcopy(original)
    result["profile"][field][2] = value
    seal(result)
    report = verify(request, result)
    assert report["status"] == "FAIL" and report["qualification"]["action"] == "REFUSE"
    assert all(math.isfinite(value) for value in report["metrics"]["residuals"].values())
    validate_report(request, result, report)


@pytest.mark.parametrize("mutation", [
    lambda report: report["thresholds"].pop("quadrature_relative"),
    lambda report: report["thresholds"].update(hydrostatic_relative=0.01),
    lambda report: report["checks"].pop(),
    lambda report: report["checks"].__setitem__(0, deepcopy(report["checks"][1])),
    lambda report: report["checks"][0].update(status="FAIL"),
    lambda report: report["checks"][0].update(tolerance=0.01),
    lambda report: report["checks"][0].update(value=True),
    lambda report: report.update(status="FAIL"),
    lambda report: report["qualification"].update(action="EXPAND"),
    lambda report: report.update(candidate_digest="0" * 64),
    lambda report: report.update(request_digest="0" * 64),
    lambda report: report.update(claim_scope="moist_adiabatic_weather"),
    lambda report: report.update(verifier="candidate_compiler_replay"),
    lambda report: report["limitations"].pop(),
    lambda report: report["metrics"]["terminal"].update(pressure_pa=1.0),
    lambda report: report["metrics"]["summary"]["temperature_k"].update(minimum=1.0),
    lambda report: report["metrics"]["summary"].update(sample_count=True),
    lambda report: report["reference"].update(coarse_subintervals_per_segment=True),
    lambda report: report["reference"].update(quadrature_evaluations=199),
    lambda report: report["reference"]["coarse_segment_integrals"].__setitem__(0, -1.0),
    lambda report: report["reference"]["refined_pressure_pa"].__setitem__(2, 1.0),
    lambda report: report["reference"]["continuous_humidity"].update(maximum_allowed_relative_humidity=1.0),
    lambda report: report["reference"]["continuous_humidity"].update(proof="sampled_only"),
    lambda report: report["reference"]["continuous_humidity"].update(maximum_relative_humidity=0.1),
    lambda report: report["reference"]["continuous_humidity"]["height_m"].__setitem__(1, 2000.0),
    lambda report: report["reference"]["continuous_humidity"]["temperature_k"].__setitem__(1, 290.0),
    lambda report: report["reference"]["continuous_humidity"]["pressure_pa"].__setitem__(1, 1.0),
])
def test_resealed_report_declaration_corruption_is_rejected(qualified, mutation):
    request, result, original = qualified
    report = deepcopy(original)
    mutation(report)
    seal(report)
    with pytest.raises(ValueError):
        validate_report(request, result, report)


def test_signed_simpson_upper_guard_refuses_near_ceiling_even_when_candidate_rh_is_capped():
    request = example_request()
    request["profile"]["water_mixing_ratio_kg_per_kg_dry_air"] = 0.010478377852971083
    request["sampling"]["height_m"] = [0.0, 2000.0]
    request["tolerances"]["constitutive_relative"] = 0.01
    request["desired_observables"].append("clouds")
    result = compile_atmosphere(request)
    assert result["profile"]["relative_humidity"][-1] > MAX_RELATIVE_HUMIDITY
    result["profile"]["relative_humidity"][-1] = MAX_RELATIVE_HUMIDITY
    seal(result)
    report = verify(request, result)
    reference = report["reference"]
    humidity = reference["continuous_humidity"]
    assert humidity["maximum_relative_humidity"] < MAX_RELATIVE_HUMIDITY
    assert humidity["maximum_relative_humidity_upper_bound"] > MAX_RELATIVE_HUMIDITY
    assert not _failed(report, "sampled_unsaturation") and not _failed(report, "relative_humidity")
    assert _failed(report, "continuous_unsaturation")
    assert report["status"] == "FAIL" and report["qualification"]["action"] == "REFUSE"
    assert report["qualification"]["unsupported_observables"] == ["clouds"]
    assert reference["quadrature_evaluations"] == 50
    assert math.isclose(reference["refined_segment_error_bounds"][0], 1.3080071689526275e-13, rel_tol=1e-14)
    assert reference["segment_integral_roundoff_allowances"] == [1e-12]
    assert reference["segment_integral_lower_bounds"][0] < reference["refined_segment_integrals"][0]
    validate_report(request, result, report)


@pytest.mark.parametrize("lapse", [0.0, 0.001901, 0.0065])
def test_independent_pressure_upper_bound_encloses_analytic_column_without_extra_evaluations(lapse):
    request = example_request()
    request["profile"]["lapse_rate_k_per_m"] = lapse
    request["sampling"]["height_m"] = [index * 2000.0 / 128 for index in range(129)]
    result = compile_atmosphere(request)
    report = verify(request, result)
    reference = report["reference"]
    assert all(upper >= actual for upper, actual in zip(reference["pressure_upper_bound_pa"], result["profile"]["pressure_pa"]))
    assert reference["quadrature_evaluations"] == 6400
    assert reference["maximum_quadrature_evaluations"] == 6400
    assert all(error >= 0.0 for error in reference["refined_segment_error_bounds"])
    if lapse == 0.0:
        assert reference["refined_segment_error_bounds"] == [0.0] * 128
    humidity = reference["continuous_humidity"]
    assert humidity["maximum_relative_humidity_upper_bound"] >= max(result["profile"]["relative_humidity"])
    validate_report(request, result, report)


@pytest.mark.parametrize("mutation", [
    lambda report: report["reference"].update(integral_bound_method="uncertified_nominal_pressure"),
    lambda report: report["reference"].update(integral_roundoff_allowance=0.0),
    lambda report: report["reference"].update(pressure_roundoff_relative_allowance=0.0),
    lambda report: report["reference"]["refined_segment_error_bounds"].pop(),
    lambda report: report["reference"]["refined_segment_error_bounds"].__setitem__(0, -1.0),
    lambda report: report["reference"]["refined_segment_error_bounds"].__setitem__(0, True),
    lambda report: report["reference"]["segment_integral_roundoff_allowances"].__setitem__(0, 0.0),
    lambda report: report["reference"]["segment_integral_lower_bounds"].__setitem__(0, report["reference"]["refined_segment_integrals"][0]),
    lambda report: report["reference"]["pressure_upper_bound_pa"].__setitem__(0, 101325.0),
    lambda report: report["reference"]["pressure_upper_bound_pa"].__setitem__(1, 1.0),
    lambda report: report["reference"]["continuous_humidity"].update(humidity_roundoff_relative_allowance=0.0),
    lambda report: report["reference"]["continuous_humidity"].update(guard_interpretation="nominal endpoint check"),
    lambda report: report["reference"]["continuous_humidity"].update(maximum_relative_humidity_upper_bound=0.1),
    lambda report: report["reference"]["continuous_humidity"]["relative_humidity_upper_bound"].__setitem__(1, 0.1),
])
def test_resealed_guard_metadata_corruption_is_rejected_without_science_replay(qualified, mutation):
    request, result, original = qualified
    report = deepcopy(original)
    mutation(report)
    seal(report)
    with pytest.raises(ValueError):
        validate_report(request, result, report)


def test_static_reference_accepts_sealed_scientific_forgery_without_pressure_replay(qualified):
    request, result, original = qualified
    forged = deepcopy(original)
    forged["reference"]["coarse_segment_integrals"][0] = 1.0
    seal(forged)
    validate_report(request, result, forged)
    fresh = verify(request, result)
    assert fresh["status"] == "PASS"
    assert fresh["record_digest"] != forged["record_digest"]
    assert fresh["reference"]["coarse_segment_integrals"][0] != 1.0


def test_retained_reference_one_ulp_pressure_difference_does_not_require_libm_replay(qualified):
    request, result, original = qualified
    retained = deepcopy(original)
    retained["reference"]["refined_pressure_pa"][2] = math.nextafter(retained["reference"]["refined_pressure_pa"][2], 0.0)
    seal(retained)
    validate_report(request, result, retained)
    assert verify(request, result)["record_digest"] != retained["record_digest"]
