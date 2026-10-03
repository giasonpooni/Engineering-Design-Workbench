from copy import deepcopy

import numpy as np
import pytest

from ciw.impact_plate_contract import example_request, validate_request, validate_result
from ciw.impact_plate_solver import simulate
from ciw.impact_plate_verification import validate_report, verify
from ciw.operations.runner import seal


@pytest.fixture(scope="module")
def qualified():
    request = example_request()
    result = simulate(request)
    report = verify(request, result)
    assert report["status"] == "PASS"
    return request, result, report


def _failed(report, name):
    return next(row for row in report["checks"] if row["name"] == name)["status"] == "FAIL"


def test_default_audit_retains_independent_reference_energy_and_two_refinements(qualified):
    request, result, report = qualified
    validate_report(request, result, report)
    assert report["qualification"]["action"] == "LOCAL"
    assert len(report["checks"]) == 105
    assert set(report["metrics"]) == {"primary", "refined", "spatial", "time_refinement", "spatial_refinement"}
    for label in ("primary", "refined", "spatial"):
        metrics = report["metrics"][label]
        assert metrics["maximum_energy_relative_drift"] < 1e-5
        assert metrics["maximum_striker_momentum_balance_relative_error"] < 1e-12
        assert metrics["max_deflection_over_thickness"] < 0.1
        assert metrics["slope_bound"] < 0.1
        assert metrics["terminal_plate_energy_j"] > 0
        assert metrics["terminal_spring_energy_j"] == 0
        assert metrics["terminal_striker_energy_j"] < metrics["initial_energy_j"]
        assert metrics["plate_peak_deflection_m"] >= metrics["plate_contact_peak_deflection_m"]
        assert metrics["deflection_interpretation"].startswith("maximum retained-time sum")
    primary = report["reference"]["state_normalizations"]["primary"]
    assert primary["plate_contact_velocity_m_per_s"] > request["model"]["initial_speed_m_per_s"]
    assert primary["modal_velocity_m_per_s"] > request["model"]["initial_speed_m_per_s"]
    assert result["spatial"]["modes_per_axis"] == result["refined"]["modes_per_axis"] + 2


def test_release_is_signed_patch_gap_event_with_adjacent_retained_bracket(qualified):
    _, result, report = qualified
    for label in ("primary", "refined", "spatial"):
        trace, metrics = result[label], report["metrics"][label]
        lower, upper = metrics["separation_bracket_s"]
        index = trace["time_s"].index(upper)
        assert trace["time_s"][index - 1] == lower
        assert trace["compression_m"][index - 1] > 0 >= trace["compression_m"][index]
        assert lower <= metrics["separation_time_s"] <= upper
        # The moving plate is a separate state; release does not mean zero
        # striker displacement or zero plate vibration.
        assert trace["striker_displacement_m"][index] != 0
        assert trace["plate_contact_displacement_m"][index] != 0
        assert trace["force_n"][index] == 0
        assert all(value <= 0 for value in trace["compression_m"][index:])


def test_retained_declaration_validation_never_propagates_a_reference_or_replays(qualified, monkeypatch):
    import ciw.impact_plate_reference as analytic
    import ciw.impact_plate_solver as solver
    import ciw.impact_plate_verification as auditor

    def forbidden(*args, **kwargs):
        raise AssertionError("Retained inspection replayed numerical physics")

    monkeypatch.setattr(auditor, "verify", forbidden)
    monkeypatch.setattr(auditor, "reference", forbidden)
    monkeypatch.setattr(auditor, "reference_values", forbidden)
    monkeypatch.setattr(analytic, "reference", forbidden)
    monkeypatch.setattr(analytic, "reference_values", forbidden)
    monkeypatch.setattr(analytic, "_prepare", forbidden)
    monkeypatch.setattr(analytic, "_bisect", forbidden)
    monkeypatch.setattr(solver, "simulate", forbidden)
    monkeypatch.setattr(np.linalg, "eigh", forbidden)
    validate_report(*qualified)


@pytest.mark.parametrize("label", ["primary", "refined", "spatial"])
@pytest.mark.parametrize("field", ["modal_displacement_m", "modal_velocity_m_per_s"])
def test_resealed_interior_modal_corruption_fails_full_history_equations(qualified, label, field):
    request, original, _ = qualified
    result = deepcopy(original)
    index = result[label]["steps_per_contact"] // 3
    result[label][field][0][index] += 0.001 if field == "modal_displacement_m" else 0.1
    seal(result)
    validate_result(request, result)
    report = verify(request, result)
    assert report["status"] == "FAIL" and report["qualification"]["action"] == "REFUSE"
    assert _failed(report, label + ".integrator_equations")
    assert _failed(report, label + ".analytic." + field)
    assert _failed(report, label + ".maximum_energy_drift")
    validate_report(request, result, report)


@pytest.mark.parametrize("field,check", [("force_n", "force_law"), ("compression_m", "gap_projection"),
    ("plate_contact_displacement_m", "patch_displacement_projection"),
    ("plate_contact_velocity_m_per_s", "patch_velocity_projection"),
    ("velocity_m_per_s", "integrator_equations"), ("striker_displacement_m", "integrator_equations")])
def test_resealed_scalar_errors_cannot_impersonate_a_valid_execution(qualified, field, check):
    request, original, _ = qualified
    result = deepcopy(original)
    index = result["primary"]["steps_per_contact"] // 3
    result["primary"][field][index] += 0.01 if "velocity" in field else 0.0001 if field != "force_n" else 1.0
    seal(result)
    validate_result(request, result)
    report = verify(request, result)
    assert report["status"] == "FAIL" and _failed(report, "primary." + check)
    validate_report(request, result, report)


def test_all_history_energy_detects_a_hidden_interior_velocity_spike_with_unchanged_terminal_energy(qualified):
    request, original, original_report = qualified
    result = deepcopy(original)
    result["primary"]["modal_velocity_m_per_s"][0][500] = 3.0
    seal(result)
    report = verify(request, result)
    assert report["metrics"]["primary"]["final_energy_j"] == original_report["metrics"]["primary"]["final_energy_j"]
    assert report["metrics"]["primary"]["maximum_energy_relative_drift"] > 1
    assert _failed(report, "primary.maximum_energy_drift")


def test_negative_counterfeit_contact_impulse_remains_retainable_as_failed_evidence(qualified):
    request, original, _ = qualified
    result = deepcopy(original)
    result["primary"]["force_n"][1:] = [-1.0] * (len(result["primary"]["force_n"]) - 1)
    seal(result)
    report = verify(request, result)
    assert report["metrics"]["primary"]["integrated_striker_impulse_n_s"] < 0
    assert report["qualification"]["action"] == "REFUSE"
    assert _failed(report, "primary.compression_only_force")
    validate_report(request, result, report)


def test_added_modes_cannot_hide_field_difference_by_canceling_the_patch_projection(qualified):
    request, original, original_report = qualified
    result = deepcopy(original)
    spatial = result["spatial"]
    first, second = spatial["modes"].index([1, 5]), spatial["modes"].index([5, 1])
    assert spatial["patch_coupling"][first] == spatial["patch_coupling"][second]
    # In the square plate these two added sine modes have equal patch weights.
    # Opposite coefficient changes therefore leave patch displacement, contact
    # force and every striker observation unchanged while changing the field.
    index = 1000
    spatial["modal_displacement_m"][first][index] += 0.0001
    spatial["modal_displacement_m"][second][index] -= 0.0001
    seal(result)
    report = verify(request, result)
    before = original_report["metrics"]["spatial_refinement"]["aligned_state_changes_normalized"]
    after = report["metrics"]["spatial_refinement"]["aligned_state_changes_normalized"]
    assert after["force_n"] == before["force_n"]
    assert after["plate_contact_displacement_m"] == before["plate_contact_displacement_m"]
    assert after["modal_displacement_m"] == before["modal_displacement_m"]
    assert after["displacement_field_bound"] > before["displacement_field_bound"]
    assert _failed(report, "spatial_refinement.displacement_field_bound")
    validate_report(request, result, report)


def test_small_amplitude_model_domain_cannot_be_relaxed_by_numerical_tolerances():
    request = example_request()
    request["model"]["initial_speed_m_per_s"] *= 2
    request["desired_observables"].append("fracture")
    request["tolerances"] = {name: 0.1 for name in request["tolerances"]}
    validate_request(request)
    result = simulate(request)
    report = verify(request, result)
    assert report["status"] == "FAIL" and report["qualification"]["action"] == "REFUSE"
    assert _failed(report, "primary.small_deflection_ratio")
    assert all(row["tolerance"] == 0.1 for row in report["checks"] if row["name"].endswith("small_deflection_ratio"))
    assert not _failed(report, "primary.maximum_energy_drift")
    validate_report(request, result, report)


def test_recontact_inside_retained_window_refuses_single_contact_scope(qualified):
    request, original, _ = qualified
    result = deepcopy(original)
    trace = result["primary"]
    gap = 0.00001
    trace["compression_m"][-1] = gap
    trace["striker_displacement_m"][-1] = trace["plate_contact_displacement_m"][-1] + gap
    trace["force_n"][-1] = request["model"]["stiffness_n_per_m"] * gap
    seal(result)
    report = verify(request, result)
    assert report["qualification"]["action"] == "REFUSE"
    assert _failed(report, "primary.single_contact")
    validate_report(request, result, report)


def test_genuine_recontact_is_retained_as_refused_even_when_integrator_energy_balances():
    request = example_request()
    request["model"]["mass_kg"] = 0.03
    request["integration"]["duration_factor"] = 2.0
    result = simulate(request)
    report = verify(request, result)
    spectral = report["reference"]["primary"]
    assert spectral["release_time_s"] < spectral["first_recontact_time_s"] < spectral["observation_duration_s"]
    assert spectral["single_contact_supported"] is False
    assert report["qualification"]["action"] == "REFUSE"
    assert _failed(report, "primary.single_contact")
    assert not _failed(report, "primary.maximum_energy_drift")
    assert not _failed(report, "primary.integrator_equations")
    validate_report(request, result, report)


def test_absent_first_release_does_not_invent_rebound_or_qualify_single_contact():
    request = example_request()
    request["model"].update(thickness_m=0.0025, initial_speed_m_per_s=0.01)
    result = simulate(request)
    report = verify(request, result)
    assert report["reference"]["primary"]["release_time_s"] is None
    assert report["reference"]["primary"]["restitution"] is None
    assert report["reference"]["primary"]["striker_impulse_n_s"] is None
    assert report["qualification"]["action"] == "REFUSE"
    assert _failed(report, "primary.separation_event")
    assert _failed(report, "primary.single_contact")
    validate_report(request, result, report)


@pytest.mark.parametrize("tolerance,name", [("refinement_normalized", "time_refinement"),
    ("spatial_refinement_normalized", "spatial_refinement")])
def test_declared_refinement_failure_is_retained_independently(tolerance, name):
    request = example_request()
    request["tolerances"][tolerance] = 1e-12
    result = simulate(request)
    report = verify(request, result)
    assert report["status"] == "FAIL"
    assert any(row["name"].startswith(name + ".") and row["status"] == "FAIL" for row in report["checks"])
    validate_report(request, result, report)


def test_higher_material_quantities_expand_only_after_numerical_acceptance():
    request = example_request()
    request["desired_observables"].extend(["strain", "thermal_response", "plastic_work"])
    result = simulate(request)
    report = verify(request, result)
    assert report["status"] == "PASS" and report["qualification"]["action"] == "EXPAND"
    assert report["qualification"]["unsupported_observables"] == ["plastic_work", "strain", "thermal_response"]
    validate_report(request, result, report)


@pytest.mark.parametrize("mutation", ["bool_metric", "bool_check", "bool_scale", "bool_basis", "bool_mode", "missing_check",
    "duplicate_check", "terminal_energy", "peak_force", "release_bracket", "scope", "normalization", "qualification"])
def test_resealed_report_declaration_corruption_is_rejected(qualified, mutation):
    request, result, original = qualified
    report = deepcopy(original)
    if mutation == "bool_metric":
        report["metrics"]["primary"]["maximum_energy_relative_drift"] = False
    elif mutation == "bool_check":
        report["checks"][0]["value"] = False
    elif mutation == "bool_scale":
        report["reference"]["scales"]["energy_j"] = True
    elif mutation == "bool_basis":
        report["reference"]["primary"]["modal_mass_kg"][0] = True
    elif mutation == "bool_mode":
        report["reference"]["primary"]["modes"][0][0] = True
    elif mutation == "missing_check":
        report["checks"].pop()
    elif mutation == "duplicate_check":
        report["checks"][-1] = deepcopy(report["checks"][0])
    elif mutation == "terminal_energy":
        report["metrics"]["primary"]["final_energy_j"] *= 2
    elif mutation == "peak_force":
        report["metrics"]["primary"]["peak_force_n"] *= 2
    elif mutation == "release_bracket":
        report["metrics"]["primary"]["separation_bracket_s"][0] *= 0.5
    elif mutation == "scope":
        report["claim_scope"] = "calibrated_polymer_plate"
    elif mutation == "normalization":
        report["reference"]["state_normalizations"]["spatial"]["plate_contact_velocity_m_per_s"] *= 2
    else:
        report["qualification"]["action"] = "EXPAND"
    seal(report)
    with pytest.raises(ValueError):
        validate_report(request, result, report)


def test_structurally_coherent_forged_history_error_requires_independent_verification(qualified):
    request, result, original = qualified
    report = deepcopy(original)
    report["metrics"]["primary"]["maximum_energy_relative_drift"] = 1e-4
    next(row for row in report["checks"] if row["name"] == "primary.maximum_energy_drift")["value"] = 1e-4
    seal(report)
    validate_report(request, result, report)
    assert report["status"] == "PASS"
    recomputed = verify(request, result)
    assert recomputed["record_digest"] != report["record_digest"]


def test_invalid_initial_state_produces_explicit_integrity_refusal(qualified):
    request, original, _ = qualified
    result = deepcopy(original)
    result["primary"]["modal_displacement_m"][0][0] = 1e-5
    seal(result)
    report = verify(request, result)
    assert report["status"] == "FAIL" and report["qualification"]["action"] == "REFUSE"
    assert report["checks"][0]["name"] == "schema_integrity"
