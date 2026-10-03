"""Qualified wave behavior and fail-closed public boundaries."""
from copy import deepcopy
import math

import numpy as np
import pytest

from ciw.fluid_wave_contract import (
    CLOCK, EXPANSION_OBSERVABLES, FIELD_NAMES, HARMONICS, REFUSED_OBSERVABLES, TRACE_LABELS,
    example_request, validate_request, validate_result, wave_speed_m_per_s,
)
from ciw.fluid_wave_reference import reference
from ciw.fluid_wave_solver import simulate
from ciw.fluid_wave_verification import validate_report, verify
from ciw.operations.runner import seal


@pytest.fixture(scope="module")
def wave():
    request = example_request()
    result = simulate(request)
    report = verify(request, result)
    return request, result, report


def test_default_wave_is_qualified_with_independent_second_order_trends(wave):
    request, result, report = wave
    assert report["status"] == "PASS"
    assert report["qualification"]["action"] == "LOCAL"
    assert validate_report(request, result, report) == report
    assert all(row["status"] == "PASS" for row in report["checks"])
    assert 1.95 < report["metrics"]["time_convergence"]["observed_order"] < 2.05
    assert 1.95 < report["metrics"]["spatial_convergence"]["observed_order"] < 2.05


def test_continuum_reference_has_analytic_translation_speed_and_correct_locations():
    request = example_request()
    c = wave_speed_m_per_s(request["model"])
    times = [0.0, request["integration"]["duration_s"]]
    exact = reference(request, times)
    model = request["model"]
    for t_index, t in enumerate(times):
        for field, x_name, scale in (("free_surface_elevation_m", "cell_x_m", 1.0),
                                     ("depth_averaged_velocity_m_per_s", "face_x_m", c / model["depth_m"])):
            for observed, x in zip(exact[field][t_index], exact[x_name]):
                expected = scale * model["amplitude_m"] * sum(weight * math.cos(
                    2.0 * math.pi * mode / model["length_m"] * (x - c * t - model["pulse_center_m"]))
                    for mode, weight in HARMONICS)
                assert observed == pytest.approx(expected, abs=1e-17)
    assert exact["wave_speed_m_per_s"] == c
    assert exact["face_x_m"][0] == 0.0
    assert exact["cell_x_m"][0] == model["length_m"] / (2.0 * request["integration"]["cells"])


def test_all_history_mass_energy_and_pressure_discharge_are_work_consistent(wave):
    request, result, report = wave
    model = request["model"]
    for label in TRACE_LABELS:
        trace, metric = result[label], report["metrics"]["traces"][label]
        assert metric["maximum_mass_relative_drift"] < 2e-14
        assert metric["maximum_energy_relative_drift"] < 2e-13
        assert metric["integrator_maximum_normalized_residual"] < 2e-13
        assert metric["wave_speed_relative_error"] < 0.001
        eta = np.asarray(trace["free_surface_elevation_m"])
        velocity = np.asarray(trace["depth_averaged_velocity_m_per_s"])
        assert np.allclose(trace["bottom_gauge_pressure_pa"], model["density_kg_per_m3"] *
                           model["gravity_m_per_s2"] * (model["depth_m"] + eta), rtol=0.0, atol=0.0)
        assert np.allclose(trace["volume_flux_m3_per_s"], model["width_m"] * model["depth_m"] * velocity,
                           rtol=0.0, atol=0.0)
        assert trace["time_s"][0] == 0.0
        assert trace["time_s"][-1] == pytest.approx(request["integration"]["duration_s"])
    assert result["clock"] == CLOCK


@pytest.mark.parametrize("field,value", [
    ("amplitude_m", 0.001000000001), ("depth_m", 0.3), ("particle_semantics", "molecule"),
    ("boundary", "open_reservoir"), ("initial_profile", "arbitrary_pulse"),
])
def test_physical_validity_cannot_be_relaxed_by_tolerances(field, value):
    request = example_request()
    request["model"][field] = value
    request["tolerances"] = {key: 0.1 for key in request["tolerances"]}
    with pytest.raises(ValueError):
        validate_request(request)


def test_hard_accuracy_cfl_and_period_resolution_and_resource_bounds():
    request = example_request()
    request["integration"]["steps"] = 32
    request["integration"]["duration_s"] *= 4.0
    with pytest.raises(ValueError, match="CFL"):
        validate_request(request)
    request = example_request()
    request["integration"]["cells"] = 32
    request["integration"]["steps"] = 32
    request["integration"]["duration_s"] *= 2.0
    with pytest.raises(ValueError, match="time-resolution"):
        validate_request(request)
    request = example_request()
    request["integration"]["cells"] = 128
    request["integration"]["steps"] = 256
    with pytest.raises(ValueError, match="allocation"):
        validate_request(request)


@pytest.mark.parametrize("path,value", [
    (("integration", "cells"), True), (("integration", "steps"), 64.0),
    (("integration", "spatial_refinement_factor"), 2.0), (("clock", "time_origin_s"), False),
    (("clock", "externally_synchronized"), 0), (("model", "depth_m"), float("nan")),
    (("model", "amplitude_m"), True), (("model", "width_m"), float("inf")),
])
def test_strict_si_request_rejects_boolean_float_integer_and_nonfinite_substitution(path, value):
    request = example_request()
    request[path[0]][path[1]] = value
    with pytest.raises(ValueError):
        validate_request(request)


def test_known_more_detailed_physics_routes_expand_and_authority_claims_refuse(wave):
    _, result, _ = wave
    for observable, expected in ((next(iter(EXPANSION_OBSERVABLES)), "EXPAND"),
                                  (next(iter(REFUSED_OBSERVABLES)), "REFUSE")):
        request = example_request()
        request["desired_observables"].append(observable)
        rebound_result = deepcopy(result)
        from ciw.operations.runner import digest
        rebound_result["request_digest"] = digest(request)
        rebound_result = seal(rebound_result)
        report = verify(request, rebound_result)
        assert report["status"] == "PASS"
        assert report["qualification"]["action"] == expected
        validate_report(request, rebound_result, report)
    request = example_request()
    request["desired_observables"].append("mystery")
    with pytest.raises(ValueError):
        validate_request(request)


@pytest.mark.parametrize("mutation", ["units", "clock", "matrix", "timestamp", "initial", "boolean", "seal"])
def test_result_boundary_detects_shape_clock_initial_and_identity_forgery(wave, mutation):
    request, result, _ = wave
    candidate = deepcopy(result)
    if mutation == "units":
        candidate["units"]["time_s"] = "ms"
    elif mutation == "clock":
        candidate["clock"]["owner"] = "external_snapshot_estimator"
    elif mutation == "matrix":
        candidate["primary"]["free_surface_elevation_m"][-1].pop()
    elif mutation == "timestamp":
        candidate["primary"]["time_s"][1] *= 2.0
    elif mutation == "initial":
        candidate["primary"]["depth_averaged_velocity_m_per_s"][0][1] *= -1.0
    elif mutation == "boolean":
        candidate["primary"]["depth_averaged_velocity_m_per_s"][1][1] = False
    else:
        candidate["primary"]["free_surface_elevation_m"][1][1] += 0.001
    if mutation != "seal":
        candidate = seal(candidate)
    with pytest.raises(ValueError):
        validate_result(request, candidate)


def test_resealed_numerical_corruption_is_detected_by_fresh_verifier(wave):
    request, result, _ = wave
    candidate = deepcopy(result)
    candidate["primary"]["free_surface_elevation_m"][10][3] += request["model"]["amplitude_m"]
    candidate = seal(candidate)
    validate_result(request, candidate)
    report = verify(request, candidate)
    assert report["status"] == "FAIL"
    assert report["qualification"]["action"] == "REFUSE"
    assert any(row["status"] == "FAIL" and "integrator" in row["name"] for row in report["checks"])
    validate_report(request, candidate, report)


@pytest.mark.parametrize("mutation", ["huge_interior_elevation", "huge_terminal_elevation", "negative_reported_energy"])
def test_fresh_failed_reports_remain_inspectable_for_structurally_valid_adversarial_traces(wave, mutation):
    request, result, _ = wave
    candidate = deepcopy(result)
    if mutation == "negative_reported_energy":
        candidate["primary"]["mechanical_energy_j"][-1] = -1.0
    else:
        index = 10 if mutation == "huge_interior_elevation" else -1
        candidate["primary"]["free_surface_elevation_m"][index][3] = 1e20
    candidate = seal(candidate)
    validate_result(request, candidate)
    report = verify(request, candidate)
    assert report["status"] == "FAIL"
    assert report["qualification"]["action"] == "REFUSE"
    validate_report(request, candidate, report)


def test_report_inspection_never_runs_solver_reference_or_fft(wave, monkeypatch):
    request, result, report = wave

    def forbidden(*args, **kwargs):
        raise AssertionError("retained inspection attempted fresh physics")

    monkeypatch.setattr("ciw.fluid_wave_solver.simulate", forbidden)
    monkeypatch.setattr("ciw.fluid_wave_verification.reference", forbidden)
    monkeypatch.setattr(np.fft, "rfft", forbidden)
    monkeypatch.setattr(np.fft, "irfft", forbidden)
    validate_report(request, result, report)


@pytest.mark.parametrize("mutation", ["threshold", "duplicate", "qualification", "order", "identity"])
def test_report_boundary_rejects_coherence_and_binding_tampering(wave, mutation):
    request, result, original = wave
    report = deepcopy(original)
    if mutation == "threshold":
        report["checks"][0]["tolerance"] = 0.1
    elif mutation == "duplicate":
        report["checks"][1] = deepcopy(report["checks"][0])
    elif mutation == "qualification":
        report["qualification"]["action"] = "EXPAND"
    elif mutation == "order":
        report["metrics"]["time_convergence"]["observed_order"] = 2.0
    else:
        report["result_digest"] = "sha256:" + "0" * 64
    report = seal(report)
    with pytest.raises(ValueError):
        validate_report(request, result, report)


def test_reference_boundary_enforces_declared_clock_and_grid():
    request = example_request()
    for times in ([0.0, -1.0], [0.0, 0.0], [0.0, 1000.0], [False]):
        with pytest.raises(ValueError):
            reference(request, times)
    with pytest.raises(ValueError):
        reference(request, [0.0], cells=True)
