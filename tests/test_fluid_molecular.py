"""Physical/numerical boundary tests for the classical atomistic-site profile."""
from copy import deepcopy
import json
import math

import numpy as np
import pytest

from ciw import fluid_molecular_contract as contract
from ciw import fluid_molecular_reference as independent
from ciw import fluid_molecular_solver as solver
from ciw import fluid_molecular_verification as verification
from ciw.operations.runner import digest, seal


@pytest.fixture(scope="module")
def qualified():
    request = contract.example_request()
    result = solver.simulate(request)
    report = verification.verify(request, result)
    return request, result, report


def test_actual_motion_energy_momentum_and_independent_reference(qualified):
    request, result, report = qualified
    assert report["status"] == "PASS"
    assert report["qualification"]["action"] == "LOCAL"
    assert all(row["status"] == "PASS" for row in report["checks"])
    assert result["time_fine"]["positions_reduced"][-1] != result["time_fine"]["positions_reduced"][0]
    assert result["time_fine"]["velocities_reduced"][-1] != result["time_fine"]["velocities_reduced"][0]
    metrics = report["metrics"]["check_values"]
    assert metrics["primary.reference_velocity"] < 4e-6
    assert metrics["time_fine.reference_velocity"] < metrics["primary.reference_velocity"] / 10
    assert metrics["reference.rk4_refinement"] < 1e-9
    assert metrics["primary.energy_relative_drift"] < 5e-6
    assert metrics["time_fine.momentum_normalized_drift"] < 1e-15
    assert 1.9 < report["metrics"]["time_convergence"]["observed_order"] < 2.1
    assert len(json.dumps(result).encode()) < 4 * 1024 * 1024
    assert verification.validate_report(request, result, report) == report


def test_force_sign_coherent_shift_and_cutoff_continuity():
    model = contract.example_request()["model"]
    model["positions_reduced"] = [[0.0, 0.0, 0.0], [1.2, 0.0, 0.0]]
    velocity = np.zeros((2, 3))
    position = np.array(model["positions_reduced"])
    state = solver.pair_state(model, position, velocity)
    r, cutoff = 1.2, 2.5
    cutoff_force = 24 * (2 / cutoff ** 13 - 1 / cutoff ** 7)
    radial_force = 24 * (2 / r ** 13 - 1 / r ** 7) - cutoff_force
    expected_potential = 4 * (r ** -12 - r ** -6) - 4 * (cutoff ** -12 - cutoff ** -6) + (r - cutoff) * cutoff_force
    assert state["forces_reduced"][0, 0] == pytest.approx(-radial_force, abs=1e-14)
    assert state["forces_reduced"][0, 0] > 0  # Attractive left site moves toward right site.
    assert state["potential_energy_reduced"] == pytest.approx(expected_potential, abs=1e-14)
    assert np.sum(state["forces_reduced"], axis=0) == pytest.approx([0, 0, 0])
    assert state["virial_pressure_reduced"] == pytest.approx(r * radial_force / (3 * 6 ** 3))
    for distance in (cutoff - 1e-8, cutoff, cutoff + 1e-8):
        position[1, 0] = distance
        near = solver.pair_state(model, position, velocity)
        assert abs(near["potential_energy_reduced"]) < 1e-14
        assert np.max(np.abs(near["forces_reduced"])) < 2e-9


def test_periodic_image_and_galilean_diagnostic_invariance():
    request = contract.example_request()
    model = request["model"]
    positions = np.asarray(model["positions_reduced"])
    velocities = np.asarray(model["velocities_reduced"])
    first = solver.pair_state(model, positions, velocities)
    shifted_positions = positions.copy()
    shifted_positions[0] += [6.0, -6.0, 12.0]
    second = solver.pair_state(model, shifted_positions, velocities + [0.3, -0.2, 0.1])
    assert first["forces_reduced"] == pytest.approx(second["forces_reduced"], abs=1e-13)
    for field in ("potential_energy_reduced", "kinetic_temperature_reduced", "virial_pressure_reduced"):
        assert first[field] == pytest.approx(second[field], abs=1e-13)
    assert first["kinetic_energy_reduced"] != second["kinetic_energy_reduced"]


def test_independent_reference_has_no_solver_dependency(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Independent reference consulted numerical provider")
    monkeypatch.setattr(solver, "pair_state", forbidden)
    request = contract.example_request()
    reference = independent.reference(request, substeps=2)
    assert reference["positions_reduced"].shape == (257, 8, 3)


@pytest.mark.parametrize("mutation", [
    lambda r: r["model"].update(particle_semantics="sph_computational_parcel"),
    lambda r: r["model"].update(potential="lj_cut_energy_shift_only"),
    lambda r: r["model"].update(site_mass_reduced=True),
    lambda r: r["model"]["positions_reduced"].__setitem__(1, list(r["model"]["positions_reduced"][0])),
    lambda r: r["model"]["positions_reduced"][0].__setitem__(0, 6.0),
    lambda r: r["model"].update(cutoff_reduced=3.0),
    lambda r: r["integration"].update(steps=True),
    lambda r: r["integration"].update(steps=32, duration_reduced=0.5),
    lambda r: r["integration"].update(duration_reduced=1.0),
    lambda r: r["clock"].update(time_origin_reduced=True),
    lambda r: r["tolerances"].update(energy_relative=1.0),
])
def test_hard_schema_and_physical_domains(mutation):
    request = contract.example_request()
    mutation(request)
    with pytest.raises(ValueError):
        contract.validate_request(request)


def test_runtime_overlap_guard():
    model = contract.example_request()["model"]
    position = np.array([[0.0, 0.0, 0.0], [0.84, 0.0, 0.0]])
    with pytest.raises(ValueError, match="minimum-separation"):
        solver.pair_state(model, position, np.zeros((2, 3)))
    with pytest.raises(ValueError, match="overlap"):
        independent.independent_pair_state(model, position, np.zeros((2, 3)))


def test_resealed_trajectory_and_energy_tamper_freshly_fail(qualified):
    request, result, _ = qualified
    candidate = deepcopy(result)
    candidate["time_fine"]["velocities_reduced"][100][0][0] += 0.01
    candidate["primary"]["total_energy_reduced"][-1] += 0.1
    candidate = seal(candidate)
    contract.validate_result(request, candidate)
    report = verification.verify(request, candidate)
    assert report["status"] == "FAIL"
    assert report["qualification"]["action"] == "REFUSE"
    failed = {row["name"] for row in report["checks"] if row["status"] == "FAIL"}
    assert "time_fine.verlet_residual" in failed
    assert "primary.independent_diagnostic_residual" in failed
    verification.validate_report(request, candidate, report)


def test_static_checks_do_not_execute_provider_or_reference(monkeypatch, qualified):
    request, result, report = qualified
    def forbidden(*args, **kwargs):
        raise AssertionError("Static validation executed physics")
    monkeypatch.setattr(solver, "simulate", forbidden)
    monkeypatch.setattr(independent, "independent_pair_state", forbidden)
    monkeypatch.setattr(verification, "independent_pair_state", forbidden)
    monkeypatch.setattr(verification, "reference", forbidden)
    contract.validate_request(request)
    contract.validate_result(request, result)
    verification.validate_report(request, result, report)


@pytest.mark.parametrize("observable,action", [("viscosity", "EXPAND"), ("water_molecules", "EXPAND"),
                                               ("experimental_validation", "REFUSE")])
def test_scope_does_not_convert_toy_diagnostics_into_material_claims(observable, action, qualified):
    request, result, _ = qualified
    request = deepcopy(request)
    request["desired_observables"].append(observable)
    candidate = deepcopy(result)
    candidate["request_digest"] = digest(request)
    candidate = seal(candidate)
    report = verification.verify(request, candidate)
    assert report["status"] == "PASS"
    assert report["qualification"]["action"] == action


def test_declared_si_scale_and_explicit_reduced_csv(qualified):
    request, result, _ = qualified
    assert contract.length_scale_m(request) is None
    assert contract.time_scale_s(request) is None
    request = deepcopy(request)
    request["si_scaling"] = {"sigma_m": 3e-10, "epsilon_j": 1e-21, "site_mass_kg": 6e-26,
                             "parameter_status": "declared_unvalidated_scales"}
    contract.validate_request(request)
    assert contract.length_scale_m(request) == pytest.approx(1.8e-9)
    assert contract.time_scale_s(request) == pytest.approx(0.2 * 3e-10 * math.sqrt(6e-26 / 1e-21))
    header, rows = solver.csv_rows(result)
    assert len(rows) == 65 * 8
    assert all(len(row) == len(header) for row in rows)
    assert header[0] == "time_reduced"
    assert contract.preservation_scope(request)["particle_meaning"] == "structureless_atomistic_interaction_site"


def test_resealed_report_arithmetic_and_clock_tamper_refused(qualified):
    request, result, report = qualified
    altered = deepcopy(report)
    altered["checks"][0]["status"] = "FAIL"
    with pytest.raises(ValueError, match="status"):
        verification.validate_report(request, result, seal(altered))
    altered = deepcopy(result)
    altered["primary"]["time_reduced"][3] += 0.01
    with pytest.raises(ValueError, match="times"):
        contract.validate_result(request, seal(altered))
