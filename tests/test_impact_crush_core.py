from copy import deepcopy
import math

import pytest

from ciw.impact_crush_contract import MAX_SAMPLES, STATE_FIELDS, example_request, validate_request, validate_result
from ciw.impact_crush_reference import reference, reference_values, sample
from ciw.impact_crush_solver import simulate
from ciw.impact_crush_verification import validate_report, verify
from ciw.operations.runner import seal


def test_piecewise_plastic_reference_has_known_si_values_and_release_at_residual():
    request = example_request()
    ref = reference(request)
    assert ref["branch"] == "plastic"
    assert ref["yield_time_s"] == pytest.approx(math.pi / 600)
    assert ref["plateau_duration_s"] == pytest.approx(math.sqrt(3) / 100)
    assert ref["contact_duration_s"] == pytest.approx(math.pi / 600 + math.sqrt(3) / 100 + math.pi / 200)
    assert ref["maximum_compression_m"] == pytest.approx(0.025)
    assert ref["residual_compression_m"] == pytest.approx(0.015)
    assert ref["peak_force_n"] == 100
    assert ref["initial_energy_j"] == 2
    assert ref["plastic_work_j"] == 1.5
    assert ref["rebound_energy_j"] == 0.5
    assert ref["support_impulse_n_s"] == 3
    assert ref["restitution"] == 0.5
    peak = sample(request, ref["peak_time_s"])
    assert peak == pytest.approx({"compression_m": 0.025, "velocity_m_per_s": 0,
        "force_n": 100, "plastic_compression_m": 0.015, "plastic_work_j": 1.5})
    release = sample(request, ref["contact_duration_s"])
    assert release == pytest.approx({"compression_m": 0.015, "velocity_m_per_s": -1,
        "force_n": 0, "plastic_compression_m": 0.015, "plastic_work_j": 1.5})
    flight = sample(request, ref["contact_duration_s"] + 0.005)
    assert flight["compression_m"] == pytest.approx(0.01)
    assert flight["compression_m"] > 0 and flight["force_n"] == 0
    assert flight["plastic_compression_m"] == pytest.approx(0.015)


def test_reference_is_continuous_at_all_phase_boundaries_and_balances_energy():
    request = example_request()
    ref = reference(request)
    for boundary in (ref["yield_time_s"], ref["peak_time_s"], ref["contact_duration_s"]):
        left, right = sample(request, boundary - 1e-12), sample(request, boundary + 1e-12)
        assert left == pytest.approx(right, abs=2e-8)
    values = reference_values(request, [i * ref["contact_duration_s"] / 200 for i in range(301)])
    for q, velocity, plastic, work in zip(values["compression_m"], values["velocity_m_per_s"],
                                         values["plastic_compression_m"], values["plastic_work_j"]):
        assert 0.5 * velocity ** 2 + 5000 * max(q - plastic, 0) ** 2 + work == pytest.approx(2)


def test_independent_audit_passes_with_refinement_and_plastic_energy_accounting():
    request = example_request()
    result = simulate(request)
    report = verify(request, result)
    validate_result(request, result)
    validate_report(request, result, report)
    assert report["status"] == "PASS" and report["qualification"]["action"] == "LOCAL"
    primary, refined = report["metrics"]["primary"], report["metrics"]["refined"]
    assert primary["restitution"] == pytest.approx(0.5, abs=1e-6)
    assert primary["plastic_work_j"] == pytest.approx(1.5, abs=4e-6)
    assert primary["residual_compression_m"] == pytest.approx(0.015, abs=4e-8)
    assert primary["maximum_energy_relative_drift"] < 3e-6
    assert primary["maximum_momentum_balance_relative_error"] < 1e-12
    for field in STATE_FIELDS:
        assert refined["analytic_maximum_normalized_errors"][field] < primary["analytic_maximum_normalized_errors"][field]
    assert primary["separation_time_s"] != report["reference"]["contact_duration_s"]
    assert result["primary"]["compression_m"][-1] < result["primary"]["plastic_compression_m"][-1]
    assert result["primary"]["force_n"][-1] == 0


@pytest.mark.parametrize("ratio", [0.2, 0.5, 0.99, 1 - 1e-12, 1.0, 1 + 1e-12, 2.0, 5.0])
def test_yield_regime_and_continuous_boundary_are_numerically_qualified(ratio):
    request = example_request()
    request["model"]["yield_force_n"] = ratio * 200
    result = simulate(request)
    report = verify(request, result)
    assert report["status"] == "PASS"
    validate_report(request, result, report)
    assert report["reference"]["restitution"] == pytest.approx(min(1, ratio))
    assert all(0 <= force <= request["model"]["yield_force_n"] for force in result["primary"]["force_n"])
    if ratio >= 1:
        assert report["reference"]["plastic_work_j"] == 0
    else:
        assert report["reference"]["plastic_work_j"] >= 0


@pytest.mark.parametrize("mass,stiffness,speed", [(1.0, 10000.0, 2.0), (0.001, 2e6, 25), (1e5, 1e-3, 5)])
def test_unyielded_elastic_limit_reduces_exactly_to_existing_v1_grid_and_trajectory(mass, stiffness, speed):
    from ciw.impact_contract import example_request as elastic_request
    from ciw.impact_reference import reference as elastic_reference
    from ciw.impact_solver import simulate as elastic_simulate
    request = example_request()
    request["model"].update(mass_kg=mass, stiffness_n_per_m=stiffness,
        initial_speed_m_per_s=speed, yield_force_n=2 * speed * math.sqrt(mass * stiffness))
    elastic = elastic_request()
    elastic["model"].update(mass_kg=mass, stiffness_n_per_m=stiffness, initial_speed_m_per_s=speed)
    elastic["integration"] = deepcopy(request["integration"])
    result, expected = simulate(request), elastic_simulate(elastic)
    for label in ("primary", "refined"):
        for field in ("time_s", "compression_m", "velocity_m_per_s", "force_n", "dt_s"):
            assert result[label][field] == expected[label][field]
        assert set(result[label]["plastic_compression_m"]) == {0.0}
        assert set(result[label]["plastic_work_j"]) == {0.0}
    ref = reference(request)
    for field, value in elastic_reference(elastic).items():
        assert ref[field] == value


@pytest.mark.parametrize("mass,stiffness,speed,ratio,steps,duration", [
    (0.001, 2e6, 25, 0.2, 1023, 1.251),
    (1e5, 1e-3, 5, 0.9, 1025, 2.0),
    (1.0, 10000, 2, 0.5, 4096, 4.0),
])
def test_dimensioned_profiles_and_maximum_grid(mass, stiffness, speed, ratio, steps, duration):
    request = example_request()
    request["model"].update(mass_kg=mass, stiffness_n_per_m=stiffness,
        initial_speed_m_per_s=speed, yield_force_n=ratio * speed * math.sqrt(mass * stiffness))
    request["integration"].update(steps_per_contact=steps, duration_factor=duration)
    result = simulate(request)
    report = verify(request, result)
    assert report["status"] == "PASS"
    assert len(result["refined"]["time_s"]) <= MAX_SAMPLES
    assert len(result["refined"]["time_s"]) == 2 * (len(result["primary"]["time_s"]) - 1) + 1
    validate_report(request, result, report)


def test_coarse_grid_failure_is_retained_and_precedes_expansion():
    request = example_request()
    request["integration"]["steps_per_contact"] = 32
    request["desired_observables"].append("fracture")
    result = simulate(request)
    report = verify(request, result)
    assert report["status"] == "FAIL" and report["qualification"]["action"] == "REFUSE"
    assert any(check["status"] == "FAIL" and check["name"].startswith("primary.") for check in report["checks"])
    validate_report(request, result, report)


def test_unsupported_material_observables_expand_only_from_qualified_benchmark():
    request = example_request()
    request["desired_observables"].extend(["damage", "molecular_response", "rate_response", "thermal_response"])
    result = simulate(request)
    report = verify(request, result)
    assert report["status"] == "PASS" and report["qualification"]["action"] == "EXPAND"
    assert report["qualification"]["unsupported_observables"] == ["damage", "molecular_response", "rate_response", "thermal_response"]
    validate_report(request, result, report)


@pytest.mark.parametrize("field,value", [
    ("mass_kg", True), ("mass_kg", 0), ("stiffness_n_per_m", float("inf")),
    ("initial_speed_m_per_s", -1), ("yield_force_n", True), ("yield_force_n", 0),
    ("yield_force_n", 39), ("yield_force_n", 1001), ("initial_plastic_compression_m", 0.1),
    ("initial_compression_m", 0.1), ("damping_n_s_per_m", 1), ("gravity_during_contact_m_per_s2", 9.81),
    ("contact_law", "fracture"), ("support", "moving")])
def test_invalid_or_unsupported_material_laws_refuse_without_coercion(field, value):
    request = example_request()
    request["model"][field] = value
    with pytest.raises(ValueError):
        validate_request(request)
    assert verify(request, {})["qualification"]["action"] == "REFUSE"


@pytest.mark.parametrize("field,value", [("steps_per_contact", True), ("steps_per_contact", 31),
    ("steps_per_contact", 4097), ("duration_factor", 1), ("duration_factor", float("nan")), ("method", "euler")])
def test_grid_validation_rejects_silent_coercion(field, value):
    request = example_request()
    request["integration"][field] = value
    with pytest.raises(ValueError):
        validate_request(request)


@pytest.mark.parametrize("field,check", [("plastic_compression_m", "return_mapping"),
    ("plastic_work_j", "plastic_work_algebra"), ("force_n", "force_law"), ("velocity_m_per_s", "integrator_equations")])
@pytest.mark.parametrize("label", ["primary", "refined"])
def test_resealed_interior_state_corruption_cannot_impersonate_execution(field, check, label):
    request = example_request()
    result = simulate(request)
    index = result[label]["steps_per_contact"] // 3
    result[label][field][index] += 0.1 if field != "plastic_compression_m" else 0.001
    seal(result)
    validate_result(request, result)
    report = verify(request, result)
    assert report["status"] == "FAIL" and report["qualification"]["action"] == "REFUSE"
    assert any(item["name"] == label + "." + check and item["status"] == "FAIL" for item in report["checks"])
    validate_report(request, result, report)


def test_coherently_forged_plastic_state_and_work_still_fail_return_mapping():
    request = example_request()
    result = simulate(request)
    trace = result["primary"]
    for i in range(400, len(trace["time_s"])):
        trace["plastic_compression_m"][i] *= 1.01
        trace["plastic_work_j"][i] = request["model"]["yield_force_n"] * trace["plastic_compression_m"][i]
    seal(result)
    report = verify(request, result)
    indexed = {check["name"]: check for check in report["checks"]}
    assert indexed["primary.plastic_work_algebra"]["status"] == "PASS"
    assert indexed["primary.return_mapping"]["status"] == "FAIL"
    assert report["status"] == "FAIL"
    validate_report(request, result, report)


def test_exact_analytic_history_cannot_impersonate_a_discrete_execution():
    request = example_request()
    result = simulate(request)
    for label in ("primary", "refined"):
        result[label].update(reference_values(request, result[label]["time_s"]))
    seal(result)
    report = verify(request, result)
    assert report["status"] == "FAIL"
    assert any(check["name"].endswith("integrator_equations") and check["status"] == "FAIL" for check in report["checks"])


@pytest.mark.parametrize("mutation", [
    lambda result: result["primary"]["plastic_work_j"].pop(),
    lambda result: result["primary"]["plastic_compression_m"].__setitem__(5, True),
    lambda result: result["primary"]["force_n"].__setitem__(5, float("nan")),
    lambda result: result["primary"]["time_s"].__setitem__(5, -1),
    lambda result: result["primary"].update(dt_s=1),
    lambda result: result["units"].update(plastic_work_j="kJ"),
    lambda result: result.update(summary={"qualified": True}),
])
def test_malformed_trace_returns_refusal_without_trusting_content_seal(mutation):
    request = example_request()
    result = simulate(request)
    mutation(result)
    report = verify(request, result)
    assert report["status"] == "FAIL" and report["qualification"]["action"] == "REFUSE"
    assert report["result_digest"] is None


@pytest.mark.parametrize("mutation", [
    lambda report: report.update(status="FAIL"),
    lambda report: report.update(result_digest="sha256:" + "0" * 64),
    lambda report: report["checks"].pop(),
    lambda report: report["checks"].append(deepcopy(report["checks"][0])),
    lambda report: report["checks"][0].update(status="FAIL"),
    lambda report: report["checks"][0].update(tolerance=0.1),
    lambda report: report["metrics"]["primary"].update(plastic_work_j=0),
    lambda report: report["metrics"]["primary"].update(residual_compression_m=0),
    lambda report: report["metrics"]["primary"].update(restitution=1),
    lambda report: report["metrics"]["primary"]["numerical_residuals"].update(return_mapping=0.1),
    lambda report: report["metrics"]["refinement"]["aligned_state_changes_normalized"].update(plastic_work_j=-1),
    lambda report: report["reference"].update(plastic_work_j=0),
    lambda report: report["reference"].update(plateau_duration_s=True),
    lambda report: report["limitations"].pop(),
    lambda report: report["qualification"].update(action="EXPAND")])
def test_resealed_report_mutations_are_rejected_by_static_validation(mutation, monkeypatch):
    request = example_request()
    result = simulate(request)
    report = verify(request, result)
    mutation(report)
    seal(report)
    monkeypatch.setattr("ciw.impact_crush_solver.simulate", lambda *args: pytest.fail("No numerical replay"))
    monkeypatch.setattr("ciw.impact_crush_verification.verify", lambda *args: pytest.fail("No audit replay"))
    monkeypatch.setattr("ciw.impact_crush_verification.reference_values", lambda *args: pytest.fail("No analytic trajectory replay"))
    with pytest.raises(ValueError):
        validate_report(request, result, report)


def test_verifier_is_independent_deterministic_and_preserves_inputs(monkeypatch):
    request = example_request()
    result = simulate(request)
    before = deepcopy((request, result))
    monkeypatch.setattr("ciw.impact_crush_solver.simulate", lambda *args: pytest.fail("Independent verifier"))
    first, second = verify(request, result), verify(request, result)
    assert first == second and first["status"] == "PASS"
    assert (request, result) == before


def test_static_reference_numeric_fields_reject_equal_boolean_substitution():
    request = example_request()
    request["model"]["yield_force_n"] = 400
    result = simulate(request)
    report = verify(request, result)
    report["reference"]["plastic_work_j"] = False
    seal(report)
    with pytest.raises(ValueError, match="boolean"):
        validate_report(request, result, report)


def test_negative_counterfeit_terminal_plastic_work_remains_a_valid_failed_audit():
    request = example_request()
    result = simulate(request)
    result["primary"]["plastic_work_j"][-1] = -2
    seal(result)
    report = verify(request, result)
    assert report["status"] == "FAIL" and report["qualification"]["action"] == "REFUSE"
    validate_report(request, result, report)


def test_maximum_duration_with_strict_tolerances_retains_many_failed_checks():
    request = example_request()
    request["integration"].update(steps_per_contact=32, duration_factor=4)
    request["tolerances"] = {key: 1e-12 for key in request["tolerances"]}
    result = simulate(request)
    report = verify(request, result)
    assert report["status"] == "FAIL" and sum(check["status"] == "FAIL" for check in report["checks"]) > 20
    validate_report(request, result, report)
