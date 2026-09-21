# SPDX-License-Identifier: MPL-2.0
"""Numerical comparisons and contract failures for the public reference estimator."""

from dataclasses import replace

import numpy as np
import pytest

from geometric_state_inference import (
    LinearDynamics, LinearObservation, Observation, ObservabilityAssessment,
    SO2Geometry, StatePrior, predict, replay_estimate, update, update_observable,
)


def prior(**changes):
    values = dict(time=0.0, mean=[0.0, 1.0], covariance=[[2.0, 0.3], [0.3, 1.0]],
                  frame_id="local-enu", units=("m", "m/s"), state_id="prior:fixture")
    values.update(changes)
    return StatePrior(**values)


def observation(**changes):
    values = dict(time=0.0, values=[1.1], covariance=[[0.4]], frame_id="local-enu",
                  units=("m",), observation_id="observation:fixture",
                  evidence_refs=("artifact:fixture-raw-measurement",))
    values.update(changes)
    return Observation(**values)


def measurement_model():
    return LinearObservation([[1.0, 0.0]], "model:position", measurement_units=("m",))


def test_scalar_update_matches_analytic_posterior_and_diagnostics():
    state = prior(mean=[0.0], covariance=[[4.0]], units=("m",))
    obs = observation(values=[3.0], covariance=[[1.0]])
    result = update(state, obs, LinearObservation([[1.0]], "model:identity"))
    np.testing.assert_allclose(result.mean, [2.4], atol=1e-14)
    np.testing.assert_allclose(result.covariance, [[0.8]], atol=1e-14)
    np.testing.assert_allclose(result.innovation, [3.0], atol=1e-14)
    np.testing.assert_allclose(result.innovation_covariance, [[5.0]], atol=1e-14)
    np.testing.assert_allclose(result.residual, [0.6], atol=1e-14)
    assert result.nis == pytest.approx(1.8)
    assert result.observation_id == obs.observation_id
    assert result.evidence_refs == obs.evidence_refs
    assert result.prior_state_id == state.state_id
    assert result.observation_model_id == "model:identity"
    assert result.dynamics_model_id is None


def observability(status="observable", **changes):
    values = dict(
        assessment_id="assessment:oit:fixture", model_id="model:identity-2",
        status=status, rank=2, state_dimension=2, condition_number=1.0,
        condition_limit=1e8, evidence_refs=("result:oit:fixture",),
        observation_matrix=((1.0, 0.0), (0.0, 1.0)),
    )
    values.update(changes)
    return ObservabilityAssessment(**values)


def test_observable_update_binds_gate_and_replays():
    state = prior()
    obs = observation(values=[1.1, 0.8], covariance=np.eye(2), units=("m", "m/s"))
    model = LinearObservation(np.eye(2), "model:identity-2", measurement_units=("m", "m/s"))
    gate = observability()
    result = update_observable(state, obs, model, gate)
    assert result.observability_assessment_id == gate.assessment_id
    assert result.replay_snapshot["observability_gate"] == gate.to_dict()
    replayed = replay_estimate(result.replay_snapshot)
    assert replayed.state_id == result.state_id
    assert replayed.observability_assessment_id == gate.assessment_id


@pytest.mark.parametrize("gate", [
    observability("unobservable", rank=1, condition_number=None),
    observability("ill_conditioned", condition_number=1e9),
    observability("unresolved", condition_number=None, condition_limit=None),
])
def test_observability_gate_blocks_noninformative_classifications(gate):
    obs = observation(values=[1.1, 0.8], covariance=np.eye(2), units=("m", "m/s"))
    model = LinearObservation(np.eye(2), "model:identity-2", measurement_units=("m", "m/s"))
    with pytest.raises(ValueError, match=f"blocked update: {gate.status}"):
        update_observable(prior(), obs, model, gate)


def test_observability_gate_must_bind_model_and_state_dimension():
    obs = observation(values=[1.1, 0.8], covariance=np.eye(2), units=("m", "m/s"))
    model = LinearObservation(np.eye(2), "model:identity-2", measurement_units=("m", "m/s"))
    with pytest.raises(ValueError, match="model_id differs"):
        update_observable(prior(), obs, model, observability(model_id="other:model"))
    with pytest.raises(ValueError, match="state dimension differs"):
        update_observable(
            prior(), obs, model,
            observability(rank=1, state_dimension=1, condition_number=1.0,
                          observation_matrix=((1.0,),)),
        )
    changed_model = LinearObservation([[1.0, 0.0], [0.0, 0.0]], "model:identity-2",
                                      measurement_units=("m", "m/s"))
    with pytest.raises(ValueError, match="observation_matrix differs"):
        update_observable(prior(), obs, changed_model, observability())


def test_observability_matrix_is_copied_and_must_match_state_dimension():
    matrix = [[1.0, 0.0], [0.0, 1.0]]
    gate = observability(observation_matrix=matrix)
    matrix[1][1] = 0.0
    assert gate.observation_matrix == ((1.0, 0.0), (0.0, 1.0))
    with pytest.raises(ValueError, match="columns must equal state dimension"):
        observability(observation_matrix=[[1.0]])


def test_replayed_filter_matches_independent_batch_gaussian_qr_solution():
    """Compare final filtering marginal to all-at-once trajectory least squares.

    The reference solves whitened residuals using QR, independent of Kalman
    gains or Joseph propagation. No future measurements follow the final state.
    """
    initial = prior()
    transition = np.array([[1.0, 1.0], [0.0, 1.0]])
    process_noise = np.array([[0.12, 0.02], [0.02, 0.08]])
    dynamics = LinearDynamics(transition, process_noise, "model:constant-velocity-dt1")
    model = measurement_model()
    readings = [1.2, 1.9, 3.2]

    def replay():
        state = initial
        estimates = []
        for step, reading in enumerate(readings, start=1):
            state = predict(state, dynamics, float(step))
            obs = observation(time=float(step), values=[reading],
                              observation_id=f"observation:{step}",
                              evidence_refs=(f"artifact:measurement-{step}",))
            estimate = update(state, obs, model)
            estimates.append(estimate)
            state = estimate.as_prior(f"state:posterior-{step}")
        return estimates

    estimates = replay()
    repeated = replay()
    for one, two in zip(estimates, repeated):
        np.testing.assert_array_equal(one.mean, two.mean)
        np.testing.assert_array_equal(one.covariance, two.covariance)
        np.testing.assert_array_equal(one.innovation, two.innovation)
        assert one.nis == two.nis

    size = 2 * (len(readings) + 1)
    design_blocks, target_blocks = [], []

    def add_factor(matrix, target, covariance):
        chol = np.linalg.cholesky(covariance)
        design_blocks.append(np.linalg.solve(chol, matrix))
        target_blocks.append(np.linalg.solve(chol, target))

    initial_factor = np.zeros((2, size))
    initial_factor[:, :2] = np.eye(2)
    add_factor(initial_factor, initial.mean, initial.covariance)
    for step, reading in enumerate(readings, start=1):
        process_factor = np.zeros((2, size))
        process_factor[:, 2 * (step - 1):2 * step] = -transition
        process_factor[:, 2 * step:2 * (step + 1)] = np.eye(2)
        add_factor(process_factor, np.zeros(2), process_noise)
        measurement_factor = np.zeros((1, size))
        measurement_factor[:, 2 * step:2 * (step + 1)] = model.matrix
        add_factor(measurement_factor, np.array([reading]), np.array([[0.4]]))

    design = np.vstack(design_blocks)
    target = np.concatenate(target_blocks)
    orthogonal, triangular = np.linalg.qr(design, mode="reduced")
    batch_mean = np.linalg.solve(triangular, orthogonal.T @ target)
    triangular_inverse = np.linalg.solve(triangular, np.eye(size))
    batch_covariance = triangular_inverse @ triangular_inverse.T
    np.testing.assert_allclose(estimates[-1].mean, batch_mean[-2:], rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(estimates[-1].covariance, batch_covariance[-2:, -2:],
                               rtol=1e-12, atol=1e-12)
    assert estimates[-1].dynamics_model_id == dynamics.model_id
    # A propagation is a distinct transition, not its preceding posterior.
    assert estimates[-1].prior_state_id != "state:posterior-2"
    assert estimates[-1].replay_snapshot["prior"]["predecessor_state_id"] == "state:posterior-2"


def test_joseph_covariance_stays_psd_for_large_variance_scale_difference():
    state = prior(covariance=[[1e10, 0.0], [0.0, 1e-10]])
    obs = observation(covariance=[[1e-6]])
    estimate = update(state, obs, measurement_model())
    np.testing.assert_allclose(estimate.covariance, [[1e-6, 0.0], [0.0, 1e-10]],
                               rtol=1e-12, atol=1e-22)
    assert np.all(np.linalg.eigvalsh(estimate.covariance) >= 0)


def test_so2_update_crosses_branch_cut_by_short_arc():
    geometry = SO2Geometry()
    state = prior(mean=np.deg2rad([179.0]), covariance=[[0.01]], units=("rad",))
    obs = observation(values=np.deg2rad([-179.0]), covariance=[[0.01]], units=("rad",))
    model = LinearObservation([[1.0]], "model:heading", measurement_geometry=geometry)
    estimate = update(state, obs, model, state_geometry=geometry)
    np.testing.assert_allclose(estimate.innovation, np.deg2rad([2.0]), atol=1e-14)
    np.testing.assert_allclose(estimate.mean, [-np.pi], atol=1e-14)
    np.testing.assert_allclose(estimate.residual, np.deg2rad([1.0]), atol=1e-14)
    np.testing.assert_allclose(estimate.covariance, [[0.005]], atol=1e-14)
    assert estimate.nis == pytest.approx(np.deg2rad(2.0) ** 2 / 0.02)


def test_so2_prediction_normalizes_scalar_angle():
    state = prior(mean=[3 * np.pi], covariance=[[0.01]], units=("rad",))
    prediction = predict(state, LinearDynamics([[1.0]], [[0.02]], "model:angle-random-walk"),
                         1.0, state_geometry=SO2Geometry())
    np.testing.assert_allclose(prediction.mean, [-np.pi], atol=1e-14)
    np.testing.assert_allclose(prediction.covariance, [[0.03]], atol=1e-14)


@pytest.mark.parametrize("covariance", [
    [[1.0, 0.4], [0.1, 1.0]],  # asymmetry
    [[1.0, 2.0], [2.0, 1.0]],  # indefinite
    [[-1e-30, 0.0], [0.0, -1e-30]],  # negative at tiny absolute scale
    [[np.nan, 0.0], [0.0, 1.0]],
    [[np.inf, 0.0], [0.0, 1.0]],
    [[1.0]],
    [[1e30, 0.0], [0.0, -1.0]],
    [[0.0, 1e-30], [1e-30, 1e30]],
    [[1e30, 1e15], [0.0, 1.0]],
])
def test_invalid_prior_covariances_are_rejected(covariance):
    with pytest.raises(ValueError):
        prior(covariance=covariance)


@pytest.mark.parametrize("changes", [
    {"mean": [np.inf, 0.0]}, {"mean": []}, {"mean": [[0.0, 1.0]]},
    {"time": np.nan}, {"frame_id": " "}, {"state_id": ""},
    {"units": ("m",)}, {"units": ("m", "")},
])
def test_invalid_state_contracts_are_rejected(changes):
    with pytest.raises(ValueError):
        prior(**changes)


def test_covariance_psd_validation_scales_each_component_not_global_magnitude():
    covariance = [[1e30, 0.0, 0.0], [0.0, 1e-10, 2e-10], [0.0, 2e-10, 1e-10]]
    with pytest.raises(ValueError, match="positive semidefinite"):
        prior(mean=[0.0, 0.0, 0.0], units=("m", "rad", "rad"), covariance=covariance)


def test_large_finite_covariance_is_not_overflowed_by_symmetry_normalization():
    state = prior(mean=[0.0], covariance=[[1e308]], units=("m",))
    assert np.isfinite(state.covariance[0, 0])
    assert state.covariance[0, 0] == 1e308


def test_minimum_subnormal_variance_is_preserved_by_symmetry_normalization():
    variance = np.nextafter(0.0, 1.0)
    state = prior(mean=[0.0], covariance=[[variance]], units=("m",))
    assert state.covariance[0, 0] == variance


@pytest.mark.parametrize("changes", [
    {"mean": [1 + 2j, 0]}, {"covariance": [[1 + 0j, 0], [0, 1]]},
])
def test_complex_numerical_inputs_are_rejected(changes):
    with pytest.raises(ValueError, match="real-valued"):
        prior(**changes)


@pytest.mark.parametrize("changes", [
    {"evidence_refs": ()}, {"evidence_refs": ("",)}, {"evidence_refs": "artifact:a"},
    {"observation_id": ""}, {"covariance": [[-0.1]]}, {"values": [np.nan]},
])
def test_invalid_observation_contracts_are_rejected(changes):
    with pytest.raises(ValueError):
        observation(**changes)


@pytest.mark.parametrize("changes,match", [
    ({"time": 1.0}, "time"), ({"time": -1.0}, "time"),
    ({"frame_id": "body"}, "frame"), ({"units": ("ft",)}, "units"),
])
def test_update_rejects_time_frame_and_unit_mismatches(changes, match):
    with pytest.raises(ValueError, match=match):
        update(prior(), observation(**changes), measurement_model())


def test_dimension_change_requires_declared_output_units():
    with pytest.raises(ValueError, match="measurement_units"):
        update(prior(), observation(), LinearObservation([[1.0, 0.0]], "model:position"))


def test_model_can_explicitly_declare_measurement_coordinate_frame():
    # H and frame mapping are caller supplied; no transform is silently inferred.
    model = LinearObservation([[1.0, 0.0]], "model:known-projection",
                              measurement_units=("m",), measurement_frame_id="sensor-axis")
    result = update(prior(), observation(frame_id="sensor-axis"), model)
    assert result.frame_id == "local-enu"


def test_dimension_mismatch_rejected_before_numerical_update():
    with pytest.raises(ValueError, match="dimensions"):
        update(prior(), observation(), LinearObservation([[1.0]], "model:bad-shape"))
    with pytest.raises(ValueError, match="dimensions"):
        predict(prior(), LinearDynamics([[1.0]], [[0.1]], "model:bad-shape"), 1.0)


@pytest.mark.parametrize("time", [-1.0, 0.0, np.nan, np.inf])
def test_prediction_rejects_nonforward_or_nonfinite_time(time):
    with pytest.raises(ValueError, match="time"):
        predict(prior(), LinearDynamics(np.eye(2), np.eye(2), "model:identity"), time)


def test_singular_innovation_is_rejected_without_hidden_regularization():
    state = prior(mean=[1.0], covariance=[[0.0]], units=("m",))
    obs = observation(covariance=[[0.0]])
    with pytest.raises(ValueError, match="positive definite"):
        update(state, obs, LinearObservation([[1.0]], "model:identity"))


def test_deterministic_measurement_with_nonsingular_innovation_is_allowed():
    state = prior(mean=[1.0], covariance=[[2.0]], units=("m",))
    estimate = update(state, observation(values=[3.0], covariance=[[0.0]]),
                      LinearObservation([[1.0]], "model:identity"))
    np.testing.assert_allclose(estimate.mean, [3.0])
    np.testing.assert_allclose(estimate.covariance, [[0.0]])


def test_so2_rejects_vector_state_wrong_units_and_unsupported_mapping():
    geometry = SO2Geometry()
    with pytest.raises(ValueError, match="one angle"):
        update(prior(), observation(), measurement_model(), state_geometry=geometry)
    state = prior(mean=[0.0], covariance=[[1.0]], units=("rad",))
    obs = observation(values=[0.0], units=("rad",))
    with pytest.raises(ValueError, match="identity H"):
        update(state, obs, LinearObservation([[2.0]], "model:unsupported", geometry),
               state_geometry=geometry)
    with pytest.raises(ValueError, match="identity dynamics"):
        predict(state, LinearDynamics([[2.0]], [[0.0]], "model:unsupported"), 1.0,
                state_geometry=geometry)
    with pytest.raises(ValueError, match="SO2 measurement"):
        update(state, obs, LinearObservation([[1.0]], "model:unwrapped"), state_geometry=geometry)
    with pytest.raises(ValueError, match="SO2 state"):
        update(state, obs, LinearObservation([[1.0]], "model:wrapped", geometry))


def test_contracts_copy_arrays_and_results_do_not_mutate_inputs():
    mean = np.array([0.0, 1.0])
    covariance = np.eye(2)
    state = prior(mean=mean, covariance=covariance)
    mean[0] = 999.0
    covariance[0, 0] = 999.0
    estimate = update(state, observation(), measurement_model())
    np.testing.assert_array_equal(state.mean, [0.0, 1.0])
    np.testing.assert_array_equal(state.covariance, np.eye(2))
    assert not estimate.mean.flags.writeable
    assert not estimate.covariance.flags.writeable
    next_state = estimate.as_prior("state:explicit-next-id")
    assert next_state.state_id == "state:explicit-next-id"
    with pytest.raises(ValueError, match="state_id"):
        estimate.as_prior("")


def test_estimate_contract_rejects_invalid_diagnostics():
    estimate = update(prior(), observation(), measurement_model())
    with pytest.raises(ValueError, match="nis"):
        replace(estimate, nis=-1.0)
    with pytest.raises(ValueError, match="dimensions"):
        replace(estimate, residual=[1.0, 2.0])
