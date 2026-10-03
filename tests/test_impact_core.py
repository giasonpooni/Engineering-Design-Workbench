from copy import deepcopy
import math

import pytest

from ciw.impact_contract import (MAX_SAMPLES, example_request, validate_request,
                                 validate_result)
from ciw.impact_reference import reference, reference_values, sample
from ciw.impact_solver import simulate
from ciw.impact_verification import validate_report, verify
from ciw.operations.runner import seal


def test_analytic_contact_and_signed_free_flight_have_known_si_values():
    request = example_request()
    ref = reference(request)
    assert ref["contact_duration_s"] == pytest.approx(math.pi / 100)
    assert ref["maximum_compression_m"] == pytest.approx(0.02)
    assert ref["peak_force_n"] == pytest.approx(200)
    assert ref["support_impulse_n_s"] == pytest.approx(4)
    assert ref["initial_energy_j"] == pytest.approx(2)
    peak = sample(request, math.pi / 200)
    assert peak["compression_m"] == pytest.approx(0.02)
    assert peak["force_n"] == pytest.approx(200)
    assert peak["velocity_m_per_s"] == pytest.approx(0, abs=1e-14)
    flight = sample(request, math.pi / 100 + 0.01)
    assert flight == pytest.approx({"compression_m": -0.02, "velocity_m_per_s": -2, "force_n": 0})


def test_benchmark_independent_audit_is_local_and_refinement_improves_errors():
    request = example_request()
    result = simulate(request)
    report = verify(request, result)
    validate_result(request, result)
    validate_report(request, result, report)
    assert report["status"] == "PASS"
    assert report["qualification"]["action"] == "LOCAL"
    assert all(check["status"] == "PASS" for check in report["checks"])
    primary, refined = report["metrics"]["primary"], report["metrics"]["refined"]
    assert primary["integrated_support_impulse_n_s"] == pytest.approx(4, rel=1e-6)
    assert primary["maximum_momentum_balance_relative_error"] < 1e-12
    assert primary["maximum_energy_relative_drift"] < 4e-5
    for quantity, error in primary["analytic_maximum_normalized_errors"].items():
        assert refined["analytic_maximum_normalized_errors"][quantity] < error / 3
    # The numerical crossing is interpolated from its own bracket, never
    # clamped to the analytically expected contact duration.
    lower, upper = primary["separation_bracket_s"]
    assert lower < primary["separation_time_s"] < upper
    assert primary["separation_time_s"] != report["reference"]["contact_duration_s"]
    assert result["primary"]["compression_m"][-1] < 0
    assert result["primary"]["force_n"][-1] == 0


@pytest.mark.parametrize("mass,stiffness,speed,steps,duration", [
    (0.001, 2e6, 25, 257, 1.251),
    (1e5, 1e-3, 5, 255, 2.0),
    (1.0, 10000.0, 2.0, 4096, 4.0),
])
def test_dimensioned_profiles_and_bounded_maximum_grid(mass, stiffness, speed, steps, duration):
    request = example_request()
    request["model"].update(mass_kg=mass, stiffness_n_per_m=stiffness, initial_speed_m_per_s=speed)
    request["integration"].update(steps_per_contact=steps, duration_factor=duration)
    result = simulate(request)
    report = verify(request, result)
    assert report["status"] == "PASS"
    assert len(result["refined"]["time_s"]) <= MAX_SAMPLES
    assert len(result["refined"]["time_s"]) == 2 * (len(result["primary"]["time_s"]) - 1) + 1
    validate_report(request, result, report)


def test_coarse_grid_refuses_under_the_declared_numerical_tolerances():
    request = example_request()
    request["integration"]["steps_per_contact"] = 16
    report = verify(request, simulate(request))
    assert report["status"] == "FAIL"
    assert report["qualification"]["action"] == "REFUSE"
    assert any(check["name"] == "primary.maximum_energy_drift" and check["status"] == "FAIL"
               for check in report["checks"])


def test_unqualified_requested_observables_expand_only_after_numerical_pass():
    request = example_request()
    request["desired_observables"].extend(["damage", "molecular_response", "scale_preservation"])
    result = simulate(request)
    report = verify(request, result)
    assert report["status"] == "PASS"
    assert report["qualification"]["action"] == "EXPAND"
    assert report["qualification"]["unsupported_observables"] == ["damage", "molecular_response", "scale_preservation"]
    validate_report(request, result, report)
    request["integration"]["steps_per_contact"] = 16
    failed = verify(request, simulate(request))
    assert failed["qualification"]["action"] == "REFUSE"


@pytest.mark.parametrize("field,value", [
    ("mass_kg", True), ("mass_kg", 0), ("mass_kg", float("inf")),
    ("stiffness_n_per_m", -1), ("initial_speed_m_per_s", 0),
    ("damping_n_s_per_m", 1), ("gravity_during_contact_m_per_s2", 9.81),
    ("initial_compression_m", 0.001), ("contact_law", "hertz"), ("support", "moving"),
])
def test_unsupported_or_invalid_physics_never_silently_coerce(field, value):
    request = example_request()
    request["model"][field] = value
    with pytest.raises(ValueError):
        validate_request(request)
    assert verify(request, {})["qualification"]["action"] == "REFUSE"


@pytest.mark.parametrize("path,value", [
    (("integration", "steps_per_contact"), True),
    (("integration", "steps_per_contact"), 4097),
    (("integration", "duration_factor"), 1.0),
    (("integration", "duration_factor"), float("nan")),
    (("integration", "method"), "euler"),
    (("tolerances", "energy_relative"), True),
    (("tolerances", "analytic_normalized"), 1.0),
])
def test_grid_and_tolerance_validation_is_strict(path, value):
    request = example_request()
    request[path[0]][path[1]] = value
    with pytest.raises(ValueError):
        validate_request(request)


def test_unknown_fields_scope_observables_and_boolean_samples_refuse():
    for mutate in (
        lambda request: request.update(extra="unbounded"),
        lambda request: request.update(scope="polymer_plate"),
        lambda request: request["desired_observables"].append("unrecognized"),
        lambda request: request["desired_observables"].append("impulse"),
        lambda request: request["model"].update(drop_height_m=0.2),
    ):
        request = example_request()
        mutate(request)
        with pytest.raises(ValueError):
            validate_request(request)
    request = example_request()
    result = simulate(request)
    result["primary"]["force_n"][2] = True
    seal(result)
    assert verify(request, result)["qualification"]["action"] == "REFUSE"


@pytest.mark.parametrize("label", ["primary", "refined"])
def test_resealed_corrupt_force_history_fails_independent_numerical_checks(label):
    request = example_request()
    result = simulate(request)
    result[label]["force_n"][15] *= 0.75
    seal(result)
    # Structure and seal alone cannot establish valid physical computation.
    validate_result(request, result)
    report = verify(request, result)
    assert report["status"] == "FAIL"
    assert report["qualification"]["action"] == "REFUSE"
    assert any(check["name"] == label + ".force_law" and check["status"] == "FAIL"
               for check in report["checks"])
    validate_report(request, result, report)


def test_an_analytic_path_cannot_impersonate_a_verlet_execution():
    request = example_request()
    result = simulate(request)
    for label in ("primary", "refined"):
        result[label].update(reference_values(request, result[label]["time_s"]))
    seal(result)
    report = verify(request, result)
    assert report["status"] == "FAIL"
    assert any(check["name"].endswith("integrator_equations") and check["status"] == "FAIL"
               for check in report["checks"])


@pytest.mark.parametrize("mutate", [
    lambda result: result["primary"]["time_s"].pop(),
    lambda result: result["primary"]["time_s"].__setitem__(1, -1),
    lambda result: result["refined"]["force_n"].__setitem__(1, float("nan")),
    lambda result: result.update(summary={"verified": True}),
    lambda result: result["units"].update(force_n="kN"),
    lambda result: result["primary"].update(dt_s=1),
])
def test_corrupt_or_unbounded_schema_is_a_refusal_report(mutate):
    request = example_request()
    result = simulate(request)
    mutate(result)
    # Invalid NaN is rejected before digesting; all variants return retained
    # refusal reports without trusting the candidate's summary or existing seal.
    report = verify(request, result)
    assert report["status"] == "FAIL"
    assert report["qualification"]["action"] == "REFUSE"
    assert report["result_digest"] is None


@pytest.mark.parametrize("mutate", [
    lambda report: report.update(status="FAIL"),
    lambda report: report["qualification"].update(action="EXPAND"),
    lambda report: report["checks"].pop(),
    lambda report: report["checks"].append(deepcopy(report["checks"][0])),
    lambda report: report["checks"][1].update(status="FAIL"),
    lambda report: report["checks"][1].update(tolerance=0.1),
    lambda report: report["metrics"]["primary"].update(restitution=2),
    lambda report: report["metrics"]["primary"].update(initial_energy_j=-2),
    lambda report: report["metrics"]["primary"].update(final_energy_j=-2),
    lambda report: report["metrics"]["primary"].update(peak_force_n=-1),
    lambda report: report["metrics"]["primary"].update(maximum_compression_m=-1),
    lambda report: report["metrics"]["primary"].update(peak_force_n=1),
    lambda report: report["limitations"].pop(),
    lambda report: report.update(result_digest="sha256:" + "0" * 64),
])
def test_resealed_report_mutation_is_detected_without_reexecuting(mutate, monkeypatch):
    request = example_request()
    result = simulate(request)
    report = verify(request, result)
    mutate(report)
    seal(report)
    monkeypatch.setattr("ciw.impact_solver.simulate", lambda *args: pytest.fail("No solver during static validation"))
    monkeypatch.setattr("ciw.impact_verification.verify", lambda *args: pytest.fail("No verifier rerun during static validation"))
    with pytest.raises(ValueError):
        validate_report(request, result, report)


def test_numerical_fail_cannot_be_resealed_into_local_qualification():
    request = example_request()
    request["integration"]["steps_per_contact"] = 16
    result = simulate(request)
    report = verify(request, result)
    validate_report(request, result, report)
    report["qualification"]["action"] = "LOCAL"
    seal(report)
    with pytest.raises(ValueError, match="qualification"):
        validate_report(request, result, report)


def test_many_strict_numerical_failures_still_form_a_valid_retained_report():
    request = example_request()
    request["integration"]["steps_per_contact"] = 16
    request["integration"]["duration_factor"] = 4.0
    request["tolerances"] = {key: 1e-12 for key in request["tolerances"]}
    result = simulate(request)
    report = verify(request, result)
    assert report["status"] == "FAIL"
    assert sum(check["status"] == "FAIL" for check in report["checks"]) > 20
    validate_report(request, result, report)


def test_verifier_does_not_consult_solver_or_mutate_inputs(monkeypatch):
    request = example_request()
    result = simulate(request)
    before = deepcopy((request, result))
    monkeypatch.setattr("ciw.impact_solver.simulate", lambda *args: pytest.fail("Independent verifier must not call solver"))
    first = verify(request, result)
    second = verify(request, result)
    assert first == second
    assert (request, result) == before
    assert first["status"] == "PASS"
