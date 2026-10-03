"""Physics checks derived independently of the fluid compiler and verifier.

These tests construct analytical/generalized-coordinate references from the
declaration. They intentionally do not import a provider's evolution matrix,
derivative, exact solution, energy helper, or verification residual functions.
"""
from __future__ import annotations

from copy import deepcopy
import math

import numpy as np
import pytest

from ciw.operations.runner import seal


def _exponential(matrix: np.ndarray, time_s: float) -> np.ndarray:
    """Independent Taylor exponential with scaling/squaring; NumPy only.

    The provider uses an ODE stepping scheme. This reference instead evaluates
    the linear evolution operator directly, including nonzero damping.
    """
    scaled = np.asarray(matrix, dtype=float) * time_s
    norm = float(np.linalg.norm(scaled, ord=np.inf))
    halvings = max(0, math.ceil(math.log2(norm / 0.125))) if norm else 0
    scaled = scaled / 2.0**halvings
    result = np.eye(len(scaled))
    term = result.copy()
    for degree in range(1, 80):
        term = term @ scaled / degree
        result += term
        if float(np.linalg.norm(term, ord=np.inf)) < 1e-17:
            break
    else:
        raise AssertionError("Independent exponential failed to converge")
    for _ in range(halvings):
        result = result @ result
    return result


def _undamped_modes(mass: np.ndarray, stiffness: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Mass-normalized modes of a two-coordinate conservative system."""
    inverse_root = np.diag(1.0 / np.sqrt(np.diag(mass)))
    frequency_squared, normalized_modes = np.linalg.eigh(inverse_root @ stiffness @ inverse_root)
    assert np.all(frequency_squared > 0.0)
    return np.sqrt(frequency_squared), inverse_root @ normalized_modes


def _reservoir_mechanics(request: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Derive M*q'' + C*q' + K*q = 0 in coordinates (volume, wall)."""
    fluid, tanks, duct, wall = (request[name] for name in ("fluid", "reservoirs", "connector", "structure"))
    density = fluid["density_kg_per_m3"]
    rho_g = density * fluid["gravity_m_per_s2"]
    a1, a2, aw = tanks["area1_m2"], tanks["area2_m2"], wall["piston_area_m2"]
    mass = np.diag([density * duct["length_m"] / duct["area_m2"], wall["mass_kg"]])
    stiffness = np.array([
        [rho_g * (1.0 / a1 + 1.0 / a2), -rho_g * aw / a2],
        [-rho_g * aw / a2, wall["stiffness_n_per_m"] + rho_g * aw * aw / a2],
    ])
    damping = np.diag([duct["resistance_pa_s_per_m3"], wall["damping_n_s_per_m"]])
    return mass, stiffness, damping


def _reservoir_operator(request: dict) -> tuple[np.ndarray, np.ndarray]:
    mass, stiffness, damping = _reservoir_mechanics(request)
    operator = np.zeros((4, 4))
    operator[:2, 2:] = np.eye(2)
    operator[2:, :2] = -np.linalg.solve(mass, stiffness)
    operator[2:, 2:] = -np.linalg.solve(mass, damping)
    initial = request["initial"]
    state = np.array([initial[name] for name in (
        "transfer_m3", "piston_displacement_m", "flow_m3_per_s", "piston_velocity_m_per_s",
    )])
    return operator, state


def _reservoir_state(trace: dict) -> np.ndarray:
    return np.array([trace[name] for name in (
        "transfer_m3", "piston_displacement_m", "flow_m3_per_s", "piston_velocity_m_per_s",
    )])


@pytest.fixture(scope="module")
def reservoir():
    from ciw.fluid_reservoir_contract import example_request
    from ciw.fluid_reservoir_solver import simulate
    request = example_request()
    return request, simulate(request)


def test_reservoir_swept_volume_is_needed_for_actual_closed_liquid_mass(reservoir):
    request, result = reservoir
    tanks, wall = request["reservoirs"], request["structure"]
    density = request["fluid"]["density_kg_per_m3"]
    initial_volume = sum(tanks[f"area{i}_m2"] * tanks[f"equilibrium_depth{i}_m"] for i in (1, 2))
    for row in result["resolutions"].values():
        trace = row["trace"]
        transferred = np.array(trace["transfer_m3"])
        displacement = np.array(trace["piston_displacement_m"])
        head1, head2 = np.array(trace["head1_m"]), np.array(trace["head2_m"])
        np.testing.assert_allclose(head1, -transferred / tanks["area1_m2"], atol=1e-14)
        np.testing.assert_allclose(head2, (transferred - wall["piston_area_m2"] * displacement) / tanks["area2_m2"], atol=1e-14)
        column_volume = (tanks["area1_m2"] * (tanks["equilibrium_depth1_m"] + head1)
                         + tanks["area2_m2"] * (tanks["equilibrium_depth2_m"] + head2))
        actual_volume = column_volume + wall["piston_area_m2"] * displacement
        np.testing.assert_allclose(actual_volume, initial_volume, atol=2e-15, rtol=0)
        # The connecting duct retains a fixed liquid inventory as well.
        actual_mass = density * (actual_volume + request["connector"]["length_m"] * request["connector"]["area_m2"])
        np.testing.assert_allclose(trace["total_liquid_mass_kg"], actual_mass, atol=2e-11, rtol=0)
        # Ensure the test actually exercises compliance: omitting the moving
        # boundary term must create a measurable apparent mass change.
        assert np.ptp(density * column_volume) > 1e-3


def test_reservoir_work_conjugacy_and_passive_energy_from_request(reservoir):
    request, result = reservoir
    fluid, tanks, duct, wall = (request[name] for name in ("fluid", "reservoirs", "connector", "structure"))
    mass, stiffness, damping = _reservoir_mechanics(request)
    rho_g = fluid["density_kg_per_m3"] * fluid["gravity_m_per_s2"]
    for row in result["resolutions"].values():
        trace, dt = row["trace"], row["dt_s"]
        state = _reservoir_state(trace)
        coordinates, velocities = state[:2], state[2:]
        energy = 0.5 * (np.einsum("in,ij,jn->n", coordinates, stiffness, coordinates)
                        + np.einsum("in,ij,jn->n", velocities, mass, velocities))
        np.testing.assert_allclose(trace["total_energy_j"], energy, atol=2e-14, rtol=2e-13)
        midpoint_velocity = 0.5 * (velocities[:, 1:] + velocities[:, :-1])
        dissipated = dt * np.einsum("in,ij,jn->n", midpoint_velocity, damping, midpoint_velocity)
        cumulative_dissipation = np.r_[0.0, np.cumsum(dissipated)]
        np.testing.assert_allclose(energy + cumulative_dissipation, energy[0], atol=5e-13, rtol=0)
        assert np.all(np.diff(energy) <= 1e-13)
        # Fluid pressure and wall velocity form the work-conjugate pair. This
        # is derived from the wall's swept liquid volume, not trace forces.
        head2 = (coordinates[0] - wall["piston_area_m2"] * coordinates[1]) / tanks["area2_m2"]
        mid_force = rho_g * wall["piston_area_m2"] * 0.5 * (head2[1:] + head2[:-1])
        work_into_wall = np.r_[0.0, np.cumsum(dt * mid_force * midpoint_velocity[1])]
        np.testing.assert_allclose(trace["structure_interface_work_j"], work_into_wall, atol=1e-14, rtol=2e-12)
        np.testing.assert_allclose(trace["fluid_interface_work_j"], -work_into_wall, atol=1e-14, rtol=2e-12)
        np.testing.assert_allclose(np.array(trace["fluid_interface_work_j"]) + trace["structure_interface_work_j"], 0.0, atol=1e-15)
        for energy_name, dissipation_name, work_name in (
            ("fluid_energy_j", "fluid_dissipation_j", "fluid_interface_work_j"),
            ("structure_energy_j", "structure_dissipation_j", "structure_interface_work_j"),
        ):
            balance = np.array(trace[energy_name]) - trace[energy_name][0] + trace[dissipation_name] - np.array(trace[work_name])
            np.testing.assert_allclose(balance, 0.0, atol=6e-13, rtol=0)


def test_reservoir_damped_evolution_agrees_with_independent_matrix_exponential(reservoir):
    request, result = reservoir
    operator, initial = _reservoir_operator(request)
    mass, stiffness, _ = _reservoir_mechanics(request)
    # Scale mixed coordinate/velocity units using each state's initial-energy
    # bound. The reference is direct continuous-time evolution, never midpoint.
    energy0 = 0.5 * (initial[:2] @ stiffness @ initial[:2] + initial[2:] @ mass @ initial[2:])
    scales = np.sqrt(2 * energy0 / np.r_[np.diag(stiffness), np.diag(mass)])
    transform = np.diag(scales)
    scaled_operator = np.linalg.solve(transform, operator @ transform)
    errors = []
    for row in result["resolutions"].values():
        state, times = _reservoir_state(row["trace"]), row["trace"]["time_s"]
        error = 0.0
        for index in np.linspace(0, len(times) - 1, 17, dtype=int):
            expected = transform @ _exponential(scaled_operator, times[index]) @ np.linalg.solve(transform, initial)
            error = max(error, float(np.max(np.abs((state[:, index] - expected) / scales))))
        errors.append(error)
    assert errors[-1] < 1e-3
    # Independent convergence from actual states against the continuous
    # equation; claimed order/residual fields are deliberately not consulted.
    assert 3.8 < errors[0] / errors[1] < 4.2
    assert 3.8 < errors[1] / errors[2] < 4.2


def test_reservoir_undamped_coupled_modes_have_correct_frequency_and_direction():
    from ciw.fluid_reservoir_contract import example_request
    from ciw.fluid_reservoir_solver import simulate
    request = example_request()
    request["connector"]["resistance_pa_s_per_m3"] = 0.0
    request["structure"]["damping_n_s_per_m"] = 0.0
    request["clock"]["duration_s"] = 2.0
    mass, stiffness, _ = _reservoir_mechanics(request)
    frequencies, modes = _undamped_modes(mass, stiffness)
    # Explicit two-degree characteristic polynomial is a second independently
    # derived frequency expression, including hydrostatic coupling stiffness.
    a, d = stiffness[0, 0] / mass[0, 0], stiffness[1, 1] / mass[1, 1]
    coupling = stiffness[0, 1]**2 / (mass[0, 0] * mass[1, 1])
    discriminant = math.sqrt((a - d)**2 + 4.0 * coupling)
    np.testing.assert_allclose(frequencies**2, [(a + d - discriminant) / 2.0, (a + d + discriminant) / 2.0], rtol=1e-13)
    result = simulate(request)
    initial = np.array([request["initial"]["transfer_m3"], request["initial"]["piston_displacement_m"]])
    coefficients = modes.T @ mass @ initial
    fine = result["resolutions"]["finer"]["trace"]
    times = np.array(fine["time_s"])
    expected_coordinates = modes @ (coefficients[:, None] * np.cos(frequencies[:, None] * times))
    expected_velocities = modes @ (-frequencies[:, None] * coefficients[:, None] * np.sin(frequencies[:, None] * times))
    observed = _reservoir_state(fine)
    for row, expected in zip(observed, np.vstack([expected_coordinates, expected_velocities])):
        np.testing.assert_allclose(row, expected, atol=1e-4 * max(1e-5, np.max(np.abs(expected))), rtol=0)
    # A raised first tank initially sends flow to tank 2, whose negative
    # deviation pressure initially pulls the preloaded piston inward.
    assert fine["flow_m3_per_s"][1] > 0.0
    assert fine["piston_velocity_m_per_s"][1] < 0.0


@pytest.mark.parametrize("resistance", [0.0, 20000.0, 2000000.0])
def test_rigid_reservoir_closed_scalar_solution_spans_damping_regimes(resistance):
    from ciw.fluid_reservoir_contract import example_request
    from ciw.fluid_reservoir_solver import simulate
    request = example_request()
    request["structure"]["enabled"] = False
    request["connector"]["resistance_pa_s_per_m3"] = resistance
    trace = simulate(request)["resolutions"]["finer"]["trace"]
    times = np.array(trace["time_s"])
    fluid, tanks, connector = (request[name] for name in ("fluid", "reservoirs", "connector"))
    inertance = fluid["density_kg_per_m3"] * connector["length_m"] / connector["area_m2"]
    stiffness = fluid["density_kg_per_m3"] * fluid["gravity_m_per_s2"] * (1 / tanks["area1_m2"] + 1 / tanks["area2_m2"])
    alpha = resistance / inertance
    omega_squared = stiffness / inertance
    r0, q0 = request["initial"]["transfer_m3"], request["initial"]["flow_m3_per_s"]
    discriminant = alpha * alpha - 4 * omega_squared
    if discriminant < 0:
        beta = math.sqrt(-discriminant) / 2
        cosine_coefficient = r0
        sine_coefficient = (q0 + alpha * r0 / 2) / beta
        oscillation = cosine_coefficient * np.cos(beta * times) + sine_coefficient * np.sin(beta * times)
        expected_r = np.exp(-alpha * times / 2) * oscillation
        expected_q = np.exp(-alpha * times / 2) * (
            beta * (-cosine_coefficient * np.sin(beta * times) + sine_coefficient * np.cos(beta * times))
            - alpha / 2 * oscillation)
    else:
        first, second = (-alpha + math.sqrt(discriminant)) / 2, (-alpha - math.sqrt(discriminant)) / 2
        first_coefficient = (q0 - second * r0) / (first - second)
        second_coefficient = r0 - first_coefficient
        expected_r = first_coefficient * np.exp(first * times) + second_coefficient * np.exp(second * times)
        expected_q = first * first_coefficient * np.exp(first * times) + second * second_coefficient * np.exp(second * times)
    np.testing.assert_allclose(trace["transfer_m3"], expected_r, rtol=0, atol=2e-8)
    np.testing.assert_allclose(trace["flow_m3_per_s"], expected_q, rtol=0, atol=2e-8)
    assert set(trace["piston_displacement_m"]) == {0.0}
    assert set(trace["piston_velocity_m_per_s"]) == {0.0}
    assert set(trace["fluid_interface_work_j"]) == {0.0}
    assert set(trace["structure_interface_work_j"]) == {0.0}


def _travelling_pulse(request: dict, positions: list[float], times: list[float]) -> np.ndarray:
    """Independent characteristic solution of eta_t + sqrt(g*H)*eta_x=0."""
    model = request["model"]
    speed = math.sqrt(model["gravity_m_per_s2"] * model["depth_m"])
    phase_coordinate = (np.array(positions)[None, :] - model["pulse_center_m"]
                        - speed * np.array(times)[:, None])
    return model["amplitude_m"] * sum(
        weight * np.cos(2.0 * math.pi * harmonic * phase_coordinate / model["length_m"])
        for harmonic, weight in ((1, 0.5), (2, 0.3), (3, 0.2))
    )


@pytest.fixture(scope="module")
def wave():
    from ciw.fluid_wave_contract import example_request
    from ciw.fluid_wave_solver import simulate
    request = example_request()
    return request, simulate(request)


def test_wave_collocation_pressure_flux_and_conservation_from_physical_state(wave):
    request, result = wave
    model = request["model"]
    rho, gravity, depth, width = (model[key] for key in ("density_kg_per_m3", "gravity_m_per_s2", "depth_m", "width_m"))
    speed = math.sqrt(gravity * depth)
    for name in ("primary", "time_refined", "time_fine", "spatial_refined", "spatial_fine"):
        trace = result[name]
        eta = np.array(trace["free_surface_elevation_m"])
        velocity = np.array(trace["depth_averaged_velocity_m_per_s"])
        pressure = np.array(trace["bottom_gauge_pressure_pa"])
        flux = np.array(trace["volume_flux_m3_per_s"])
        np.testing.assert_allclose(pressure, rho * gravity * (depth + eta), rtol=0, atol=5e-12)
        np.testing.assert_allclose(flux, width * depth * velocity, rtol=0, atol=1e-16)
        np.testing.assert_allclose(eta[0], _travelling_pulse(request, trace["cell_x_m"], [0])[0], atol=1e-17, rtol=0)
        np.testing.assert_allclose(velocity[0], speed / depth * _travelling_pulse(request, trace["face_x_m"], [0])[0], atol=1e-16, rtol=0)
        assert trace["cell_x_m"][0] - trace["face_x_m"][0] == trace["dx_m"] / 2
        volume = width * trace["dx_m"] * np.sum(depth + eta, axis=1)
        energy = 0.5 * rho * width * trace["dx_m"] * np.sum(gravity * eta * eta + depth * velocity * velocity, axis=1)
        np.testing.assert_allclose(trace["liquid_volume_m3"], volume, rtol=0, atol=2e-14)
        np.testing.assert_allclose(volume, width * depth * model["length_m"], rtol=0, atol=2e-14)
        np.testing.assert_allclose(trace["mechanical_energy_j"], energy, rtol=0, atol=2e-13)
        np.testing.assert_allclose(energy, energy[0], rtol=1e-11, atol=1e-15)
        # Finite-volume continuity uses face discharge at each cell's left and
        # right boundaries. Shifted face collocation has the wrong local sign.
        midpoint_flux = 0.5 * (flux[1:] + flux[:-1])
        divergence = (np.roll(midpoint_flux, -1, axis=1) - midpoint_flux) / (width * trace["dx_m"])
        np.testing.assert_allclose((eta[1:] - eta[:-1]) / trace["dt_s"], -divergence, rtol=0, atol=2e-16)


def test_wave_speed_from_observed_fourier_phase_is_surface_gravity_speed(wave):
    request, result = wave
    model, trace = request["model"], result["spatial_fine"]
    eta = np.array(trace["free_surface_elevation_m"])
    # Estimate first-mode speed from the change of an observed coefficient;
    # never inspect the verifier's wave-speed or analytic-error metrics.
    coefficient = np.fft.rfft(eta, axis=1)[:, 1]
    phase = np.unwrap(np.angle(coefficient))
    angular_frequency = -(phase[-1] - phase[0]) / trace["time_s"][-1]
    observed_speed = angular_frequency * model["length_m"] / (2.0 * math.pi)
    expected_speed = math.sqrt(model["gravity_m_per_s2"] * model["depth_m"])
    assert abs(observed_speed / expected_speed - 1.0) < 5e-4
    assert observed_speed > 0.0


def test_wave_second_order_continuum_trend_and_independent_time_refinement(wave):
    request, result = wave
    spatial_errors = []
    for label in ("time_fine", "spatial_refined", "spatial_fine"):
        trace = result[label]
        expected = _travelling_pulse(request, trace["cell_x_m"], trace["time_s"])
        spatial_errors.append(float(np.max(np.abs(np.array(trace["free_surface_elevation_m"]) - expected))))
    assert spatial_errors[-1] / request["model"]["amplitude_m"] < 1e-3
    # A fixed fine dt leaves a small temporal error floor, hence ratios approach
    # four rather than being asserted to equal it exactly.
    assert 3.5 < spatial_errors[0] / spatial_errors[1] < 4.2
    assert 3.5 < spatial_errors[1] / spatial_errors[2] < 4.2
    primary = np.array(result["primary"]["free_surface_elevation_m"])
    refined = np.array(result["time_refined"]["free_surface_elevation_m"])[::2]
    fine = np.array(result["time_fine"]["free_surface_elevation_m"])[::4]
    coarse_difference = float(np.max(np.abs(primary - refined)))
    refined_difference = float(np.max(np.abs(refined - fine)))
    assert 3.8 < coarse_difference / refined_difference < 4.2


def test_wave_hard_model_domain_cannot_be_relaxed_by_loose_tolerances():
    from ciw.fluid_wave_contract import example_request, validate_request
    original = example_request()
    original["tolerances"] = {key: 0.1 for key in original["tolerances"]}
    request = deepcopy(original)
    request["model"]["amplitude_m"] = 0.010001 * request["model"]["depth_m"]
    with pytest.raises(ValueError, match="small-amplitude"):
        validate_request(request)
    request = deepcopy(original)
    request["model"]["length_m"] = 6 * math.pi * request["model"]["depth_m"] / 0.200001
    request["model"]["pulse_center_m"] = request["model"]["length_m"] / 2
    with pytest.raises(ValueError, match="long-wavelength"):
        validate_request(request)


def test_coherently_resealed_wave_snapshot_preserves_balances_but_fresh_audit_refuses(wave):
    from ciw.fluid_wave_contract import validate_result
    from ciw.fluid_wave_verification import validate_report, verify
    request, original = wave
    original_report = verify(request, original)
    assert original_report["status"] == "PASS"
    candidate = deepcopy(original)
    trace = candidate["primary"]
    index = trace["steps"] // 2
    # A common periodic shift at one interior time preserves every snapshot's
    # mass/energy and pressure/flux laws while breaking temporal propagation.
    for field in ("free_surface_elevation_m", "depth_averaged_velocity_m_per_s", "volume_flux_m3_per_s", "bottom_gauge_pressure_pa"):
        trace[field][index] = np.roll(trace[field][index], 1).tolist()
    seal(candidate)
    validate_result(request, candidate)
    forged_report = deepcopy(original_report)
    forged_report["result_digest"] = candidate["record_digest"]
    seal(forged_report)
    # The deliberately data-only retained reader cannot authenticate a
    # coherently forged claim. Qualification needs independent fresh physics.
    validate_report(request, candidate, forged_report)
    fresh = verify(request, candidate)
    assert fresh["status"] == "FAIL" and fresh["qualification"]["action"] == "REFUSE"
    checks = {row["name"]: row["status"] for row in fresh["checks"]}
    for name in ("primary.constitutive_residual", "primary.mass_relative_drift", "primary.energy_relative_drift"):
        assert checks[name] == "PASS"
    assert checks["primary.integrator_residual"] == "FAIL"


def test_resealed_reservoir_energy_preserving_state_reflection_fails_dynamics(reservoir):
    from ciw.fluid_reservoir_contract import validate_result
    from ciw.fluid_reservoir_verification import verify
    request, original = reservoir
    candidate = deepcopy(original)
    trace = candidate["resolutions"]["fine"]["trace"]
    index = len(trace["time_s"]) // 3
    # The passive model's total and subsystem energies are quadratic. A
    # simultaneous sign reflection preserves energies and mass exactly; a
    # verifier limited to balances would incorrectly accept this snapshot.
    signed_fields = (
        "transfer_m3", "flow_m3_per_s", "connector_velocity_m_per_s",
        "piston_displacement_m", "piston_velocity_m_per_s", "head1_m", "head2_m",
        "pressure1_deviation_pa", "pressure2_deviation_pa", "pressure_difference_pa",
        "interface_force_n", "piston_swept_volume_m3",
    )
    for field in signed_fields:
        trace[field][index] *= -1.0
    tanks, wall = request["reservoirs"], request["structure"]
    transferred, displaced = trace["transfer_m3"][index], trace["piston_displacement_m"][index]
    trace["reservoir1_volume_m3"][index] = tanks["area1_m2"] * tanks["equilibrium_depth1_m"] - transferred
    trace["reservoir2_column_volume_m3"][index] = tanks["area2_m2"] * tanks["equilibrium_depth2_m"] + transferred - wall["piston_area_m2"] * displaced
    seal(candidate)
    validate_result(request, candidate)
    report = verify(request, candidate)
    assert report["status"] == "FAIL" and report["qualification"]["action"] == "REFUSE"
    checks = {row["name"]: row["status"] for row in report["checks"]}
    for name in ("constitutive", "mass_balance", "total_energy_balance", "fluid_energy_balance", "structure_energy_balance"):
        assert checks[name] == "PASS"
    assert checks["kinematics"] == "FAIL"
    assert checks["hydraulic_momentum"] == "FAIL"
    assert checks["structural_momentum"] == "FAIL"


def test_extreme_bounded_wave_candidate_retains_a_valid_failed_report(wave):
    from ciw.fluid_wave_contract import validate_result
    from ciw.fluid_wave_verification import validate_report, verify
    request, original = wave
    candidate = deepcopy(original)
    candidate["primary"]["free_surface_elevation_m"][10][10] = 1e30
    seal(candidate)
    validate_result(request, candidate)
    report = verify(request, candidate)
    assert report["status"] == "FAIL"
    assert report["qualification"]["action"] == "REFUSE"
    # Failed numerical evidence must remain structurally readable at the
    # full permitted candidate bound; errors square primitive fields.
    validate_report(request, candidate, report)


@pytest.mark.parametrize("field", ["liquid_volume_m3", "mechanical_energy_j"])
def test_corrupted_final_wave_scalar_is_readable_failed_evidence(wave, field):
    from ciw.fluid_wave_contract import validate_result
    from ciw.fluid_wave_verification import validate_report, verify
    request, original = wave
    candidate = deepcopy(original)
    candidate["primary"][field][-1] = -1e30
    seal(candidate)
    validate_result(request, candidate)
    report = verify(request, candidate)
    assert report["status"] == "FAIL" and report["qualification"]["action"] == "REFUSE"
    validate_report(request, candidate, report)
