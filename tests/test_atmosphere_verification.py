from copy import deepcopy
import math

import pytest

from ciw.atmosphere_contract import EXPANSION_OBSERVABLES, example_request, validate_result
from ciw.atmosphere_compiler import compile_atmosphere
from ciw.atmosphere_verification import (
    COARSE_SUBINTERVALS, MAX_QUADRATURE_EVALUATIONS, REFINED_SUBINTERVALS,
    _integrate_segment, validate_report, verify,
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


def _reseal_properties(result):
    """Keep non-pressure constitutive laws coherent during a pressure forgery."""
    profile = result["profile"]
    for index, (temperature, pressure) in enumerate(zip(profile["temperature_k"], profile["pressure_pa"])):
        profile["density_kg_per_m3"][index] = pressure / (287.05 * temperature)
        profile["kinematic_viscosity_m2_per_s"][index] = profile["dynamic_viscosity_pa_s"][index] / profile["density_kg_per_m3"][index]
        profile["potential_temperature_k"][index] = temperature * (1e5 / pressure) ** (287.05 / (1.4 * 287.05 / (1.4 - 1.0)))
    seal(result)


def test_default_independent_audit_has_exact_coverage_units_and_identity(qualified):
    request, result, report = qualified
    validate_report(request, result, report)
    assert len(report["checks"]) == 17
    assert report["request_digest"] == digest(request)
    assert report["candidate_digest"] == result["record_digest"]
    assert report["thresholds"] == request["tolerances"]
    assert report["qualification"]["action"] == "LOCAL"
    reference = report["reference"]
    assert reference["coarse_subintervals_per_segment"] == COARSE_SUBINTERVALS == 16
    assert reference["refined_subintervals_per_segment"] == REFINED_SUBINTERVALS == 32
    assert reference["segments"] == 10 and reference["quadrature_evaluations"] == 500
    assert reference["maximum_quadrature_evaluations"] == MAX_QUADRATURE_EVALUATIONS == 6400
    assert reference["refined_pressure_pa"][0] == request["reference"]["pressure_pa"]
    assert report["metrics"]["residuals"]["cumulative_pressure_profile"] < 1e-10
    assert report["metrics"]["summary"]["sample_count"] == 11
    assert report["metrics"]["terminal"]["height_m"] == 10000.0
    assert all(row["status"] == "PASS" for row in report["checks"])
    assert any("weather observations" in text for text in report["limitations"])
    assert any("canonical state admission" in text for text in report["limitations"])


def test_retained_report_validation_does_not_compile_integrate_or_verify(qualified, monkeypatch):
    import ciw.atmosphere_compiler as compiler
    import ciw.atmosphere_verification as auditor

    def forbidden(*args, **kwargs):
        raise AssertionError("Retained inspection repeated atmospheric physics")

    monkeypatch.setattr(compiler, "compile_atmosphere", forbidden)
    monkeypatch.setattr(auditor, "verify", forbidden)
    monkeypatch.setattr(auditor, "_quadrature_reference", forbidden)
    monkeypatch.setattr(auditor, "_integrate_segment", forbidden)
    validate_report(*qualified)


def test_explicit_verification_never_imports_or_calls_compiler(qualified, monkeypatch):
    import ciw.atmosphere_compiler as compiler

    def forbidden(*args, **kwargs):
        raise AssertionError("Independent verifier called its candidate compiler")

    monkeypatch.setattr(compiler, "compile_atmosphere", forbidden)
    assert verify(qualified[0], qualified[1])["status"] == "PASS"


@pytest.mark.parametrize("field,check", [
    ("temperature_k", "prescribed_temperature"), ("pressure_pa", "segment_hydrostatic_balance"),
    ("density_kg_per_m3", "equation_of_state"), ("sound_speed_m_per_s", "sound_speed"),
    ("dynamic_viscosity_pa_s", "dynamic_viscosity"), ("kinematic_viscosity_m2_per_s", "kinematic_viscosity"),
    ("potential_temperature_k", "potential_temperature"),
])
def test_resealed_interior_scalar_mutation_is_numerically_refused(qualified, field, check):
    request, original, _ = qualified
    result = deepcopy(original)
    result["profile"][field][4] *= 1.01
    seal(result)
    validate_result(request, result)
    report = verify(request, result)
    assert report["status"] == "FAIL" and report["qualification"]["action"] == "REFUSE"
    assert _failed(report, check)
    validate_report(request, result, report)


def test_interior_pressure_error_is_detected_even_with_coherent_other_properties_and_terminal(qualified):
    request, original, original_report = qualified
    result = deepcopy(original)
    result["profile"]["pressure_pa"][4] *= 1.005
    _reseal_properties(result)
    report = verify(request, result)
    assert report["metrics"]["terminal"] == original_report["metrics"]["terminal"]
    assert _failed(report, "segment_hydrostatic_balance") and _failed(report, "cumulative_pressure_profile")
    for name in ("equation_of_state", "potential_temperature", "kinematic_viscosity", "boundary_pressure"):
        assert not _failed(report, name)
    validate_report(request, result, report)


def test_coherent_forged_retained_report_requires_fresh_verification(qualified):
    request, original, original_report = qualified
    result = deepcopy(original)
    result["profile"]["pressure_pa"][4] *= 1.005
    _reseal_properties(result)
    forged = deepcopy(original_report)
    forged["candidate_digest"] = result["record_digest"]
    # This interior perturbation preserves every retained extrema and terminal
    # value. A seal authenticates this content identity, not scientific claims.
    assert forged["metrics"]["terminal"] == {name: result["profile"][name][-1] for name in result["profile"]}
    seal(forged)
    validate_report(request, result, forged)
    fresh = verify(request, result)
    assert fresh["status"] == "FAIL" and fresh["record_digest"] != forged["record_digest"]
    assert _failed(fresh, "segment_hydrostatic_balance")


def test_uniform_pressure_bias_passes_local_balance_but_fails_absolute_boundary(qualified):
    request, original, _ = qualified
    result = deepcopy(original)
    result["profile"]["pressure_pa"] = [value * 1.01 for value in result["profile"]["pressure_pa"]]
    _reseal_properties(result)
    report = verify(request, result)
    assert not _failed(report, "segment_hydrostatic_balance")
    assert _failed(report, "boundary_pressure") and _failed(report, "cumulative_pressure_profile")
    validate_report(request, result, report)


def test_prescribed_wind_is_checked_at_every_height(qualified):
    request, original, _ = qualified
    result = deepcopy(original)
    result["profile"]["wind_enu_m_per_s"][4] = [0.0, 0.25, 0.0]
    seal(result)
    report = verify(request, result)
    assert _failed(report, "prescribed_wind")
    assert report["metrics"]["summary"]["maximum_wind_speed_m_per_s"] == 0.25
    validate_report(request, result, report)


def test_viscosity_error_cannot_hide_behind_consistent_kinematic_viscosity(qualified):
    request, original, _ = qualified
    result = deepcopy(original)
    result["profile"]["dynamic_viscosity_pa_s"][4] *= 1.01
    result["profile"]["kinematic_viscosity_m2_per_s"][4] = (
        result["profile"]["dynamic_viscosity_pa_s"][4] / result["profile"]["density_kg_per_m3"][4])
    seal(result)
    report = verify(request, result)
    assert _failed(report, "dynamic_viscosity") and not _failed(report, "kinematic_viscosity")


def test_fixed_temperature_domain_cannot_be_relaxed_by_tolerances(qualified):
    request = deepcopy(qualified[0])
    request["tolerances"] = {name: 0.01 for name in request["tolerances"]}
    result = compile_atmosphere(request)
    result["profile"]["temperature_k"][-1] = 179.999
    seal(result)
    report = verify(request, result)
    check = next(row for row in report["checks"] if row["name"] == "declared_temperature_domain")
    assert check["value"] == 1 and check["tolerance"] == 0 and check["status"] == "FAIL"
    validate_report(request, result, report)


def test_pressure_and_potential_temperature_monotonicity_are_explicit_audits(qualified):
    request, original, _ = qualified
    result = deepcopy(original)
    result["profile"]["pressure_pa"][4] = result["profile"]["pressure_pa"][3] * 1.01
    result["profile"]["potential_temperature_k"][5] = result["profile"]["potential_temperature_k"][4] * 0.99
    seal(result)
    report = verify(request, result)
    assert _failed(report, "pressure_monotonicity") and _failed(report, "potential_temperature_stability")


@pytest.mark.parametrize("observable", sorted(EXPANSION_OBSERVABLES))
def test_unsupported_physics_requires_expansion_after_numerical_pass(observable):
    request = example_request()
    request["desired_observables"].append(observable)
    report = verify(request, compile_atmosphere(request))
    assert report["status"] == "PASS" and report["qualification"]["action"] == "EXPAND"
    assert report["qualification"]["unsupported_observables"] == [observable]
    assert all(row["status"] == "PASS" for row in report["checks"])


def test_numerical_refusal_precedes_unsupported_weather_expansion():
    request = example_request()
    request["desired_observables"].extend(["weather_forecast", "material_conditioning"])
    result = compile_atmosphere(request)
    result["profile"]["pressure_pa"][4] *= 1.02
    seal(result)
    report = verify(request, result)
    assert report["status"] == "FAIL" and report["qualification"]["action"] == "REFUSE"
    assert report["qualification"]["unsupported_observables"] == ["material_conditioning", "weather_forecast"]
    validate_report(request, result, report)


@pytest.mark.parametrize("lapse", [0.0, 1e-320, 1e-16, 1e-12])
def test_isothermal_and_near_zero_lapse_are_numerically_continuous(lapse):
    request = example_request()
    request["profile"]["lapse_rate_k_per_m"] = lapse
    request["sampling"]["height_m"] = [0.0, 11000.0]
    result = compile_atmosphere(request)
    report = verify(request, result)
    assert report["status"] == "PASS"
    expected_top = request["reference"]["pressure_pa"] * math.exp(-9.80665 * 11000 / (287.05 * request["reference"]["temperature_k"]))
    assert math.isclose(result["profile"]["pressure_pa"][-1], expected_top, rel_tol=1e-9)
    validate_report(request, result, report)


@pytest.mark.parametrize("heights", [[0.0, math.nextafter(0.0, 1.0)], [0.0, 1.0, math.nextafter(1.0, 2.0)],
                                      [index * 1000.0 for index in range(11)] + [math.nextafter(10000.0, 11000.0)]])
def test_close_height_spacing_preserves_roundoff_and_zero_integral_limit(heights):
    request = example_request()
    request["sampling"]["height_m"] = heights
    result = compile_atmosphere(request)
    report = verify(request, result)
    assert report["status"] == "PASS"
    validate_report(request, result, report)


def test_worst_two_point_column_requires_quadrature_resolution_or_declared_tolerance():
    request = example_request()
    request["reference"]["temperature_k"] = 279.0
    request["profile"]["lapse_rate_k_per_m"] = 0.009
    request["sampling"]["height_m"] = [0.0, 11000.0]
    result = compile_atmosphere(request)
    report = verify(request, result)
    assert result["profile"]["temperature_k"][-1] == 180.0
    assert report["qualification"]["action"] == "REFUSE" and _failed(report, "quadrature_refinement")
    assert report["metrics"]["residuals"]["quadrature_refinement"] > 1e-7
    validate_report(request, result, report)
    request["sampling"]["height_m"] = [index * 11000.0 / 32 for index in range(33)]
    refined_result = compile_atmosphere(request)
    refined_report = verify(request, refined_result)
    assert refined_report["status"] == "PASS"
    validate_report(request, refined_result, refined_report)


def test_maximum_sample_grid_stays_within_fixed_quadrature_budget():
    request = example_request()
    request["sampling"]["height_m"] = [index * 11000.0 / 128 for index in range(129)]
    result = compile_atmosphere(request)
    report = verify(request, result)
    assert report["status"] == "PASS" and report["reference"]["quadrature_evaluations"] == 6400
    validate_report(request, result, report)


@pytest.mark.parametrize("subintervals", [0, 1, 3, True, 16.0])
def test_simpson_rule_rejects_non_even_or_non_integer_budget(subintervals):
    with pytest.raises(ValueError):
        _integrate_segment(example_request(), 0.0, 1000.0, subintervals)


def test_simpson_rule_rejects_temperature_outside_declared_domain():
    request = example_request()
    with pytest.raises(ValueError, match="temperature"):
        _integrate_segment(request, 0.0, 20000.0, 16)


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
    lambda report: report.update(claim_scope="moist_turbulent_weather"),
    lambda report: report.update(verifier="analytic_compiler_replay"),
    lambda report: report["limitations"].pop(),
    lambda report: report["metrics"]["terminal"].update(pressure_pa=1.0),
    lambda report: report["metrics"]["summary"]["temperature_k"].update(minimum=1.0),
    lambda report: report["metrics"]["summary"].update(sample_count=True),
    lambda report: report["reference"].update(coarse_subintervals_per_segment=True),
    lambda report: report["reference"].update(quadrature_evaluations=499),
    lambda report: report["reference"]["coarse_segment_integrals"].__setitem__(0, 1.0),
    lambda report: report["reference"]["refined_pressure_pa"].__setitem__(4, 1.0),
])
def test_resealed_report_declaration_corruption_is_rejected(qualified, mutation):
    request, result, original = qualified
    report = deepcopy(original)
    mutation(report)
    seal(report)
    with pytest.raises(ValueError):
        validate_report(request, result, report)


def test_unsealed_report_modification_is_rejected(qualified):
    request, result, original = qualified
    report = deepcopy(original)
    report["metrics"]["residuals"]["segment_hydrostatic_balance"] = 0.0
    row = next(row for row in report["checks"] if row["name"] == "segment_hydrostatic_balance")
    row["value"] = 0.0
    with pytest.raises(ValueError):
        validate_report(request, result, report)


def test_invalid_structural_candidate_is_not_represented_as_scientific_evidence(qualified):
    result = deepcopy(qualified[1])
    result["profile"]["pressure_pa"][4] = float("nan")
    with pytest.raises(ValueError):
        verify(qualified[0], result)
