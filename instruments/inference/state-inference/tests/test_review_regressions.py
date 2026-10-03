# SPDX-License-Identifier: MPL-2.0
"""Regressions from independent adversarial numerical-contract review."""

from copy import deepcopy
from dataclasses import replace
from fractions import Fraction

import numpy as np
import pytest

from geometric_state_inference import (
    LinearDynamics, LinearObservation, Observation, StatePrior,
    predict, replay_estimate, update,
)


def test_covariance_normalization_does_not_create_nonfinite_values():
    # The input is finite and PSD; averaging A + A.T before dividing used to
    # overflow its diagonal and silently admit an infinite covariance.
    with np.errstate(over="raise", invalid="raise"):
        prior = StatePrior(0.0, [0.0], [[1e308]], "local", ("m",), "prior:large")
    assert np.all(np.isfinite(prior.covariance))
    np.testing.assert_array_equal(prior.covariance, [[1e308]])


def test_large_variance_in_another_coordinate_cannot_hide_negative_variance():
    with pytest.raises(ValueError):
        StatePrior(0.0, [0.0, 0.0], np.diag([1e30, -1.0]),
                   "local", ("m", "m"), "prior:indefinite")


def test_real_observation_contract_rejects_complex_data_without_projection():
    with pytest.raises(ValueError):
        Observation(0.0, np.array([3.0 + 4.0j]), [[1.0]], "local", ("m",),
                    "observation:complex", ("evidence:complex",))


def test_real_covariance_contract_rejects_complex_data_without_projection():
    covariance = np.array([[1.0, 2.0j], [-2.0j, 1.0]])
    with pytest.raises(ValueError):
        StatePrior(0.0, [0.0, 0.0], covariance, "local", ("m", "m"), "prior:complex")


@pytest.mark.parametrize("bad", [True, False, np.bool_(True), "1.25", 1 + 0j, None, np.nan, np.inf])
@pytest.mark.parametrize("field", ["time", "mean", "covariance"])
def test_declared_types_are_not_coerced(bad, field):
    arguments = dict(time=0, mean=[0], covariance=[[1]], frame_id="local",
                     units=("m",), state_id="prior:strict")
    arguments[field] = {"time": bad, "mean": [bad], "covariance": [[bad]]}[field]
    with pytest.raises(ValueError):
        StatePrior(**arguments)


@pytest.mark.parametrize("bad", [True, "1", 1 + 0j])
def test_observation_and_model_declared_types_are_strict(bad):
    with pytest.raises(ValueError):
        Observation(0, [bad], [[1]], "local", ("m",), "obs", ("evidence",))
    with pytest.raises(ValueError):
        LinearObservation([[bad]], "model")
    with pytest.raises(ValueError):
        LinearDynamics([[1]], [[bad]], "model")


@pytest.mark.parametrize("bad", [2**53 + 1, np.int64(2**53 + 1), np.uint64(2**64 - 1)])
@pytest.mark.parametrize("field", ["time", "mean", "covariance"])
def test_integer_precision_loss_cannot_change_declared_values(bad, field):
    arguments = dict(time=0, mean=[0], covariance=[[1]], frame_id="local",
                     units=("m",), state_id="prior:strict")
    arguments[field] = {"time": bad, "mean": [bad], "covariance": [[bad]]}[field]
    with pytest.raises(ValueError, match="exactly representable"):
        StatePrior(**arguments)


def test_representable_large_integer_is_not_rejected_just_for_magnitude():
    prior = StatePrior(0, [2**60], [[2**60]], "local", ("m",), "prior")
    assert int(prior.mean[0]) == 2**60


def test_nonrepresentable_integer_observation_cannot_become_zero_innovation():
    with pytest.raises(ValueError, match="exactly representable"):
        Observation(0, [2**53 + 1], [[1]], "local", ("m",), "obs", ("evidence",))


def test_tiny_declared_asymmetry_is_refused_without_repair():
    matrix = [[1.0, 0.2], [np.nextafter(0.2, 1.0), 1.0]]
    with pytest.raises(ValueError, match="asymmetry is not repaired"):
        StatePrior(0, [0, 0], matrix, "local", ("m", "m"), "prior")


def test_cancelled_prediction_covariance_matches_exact_binary64_oracle():
    matrix = [[9.7, -2.0], [0.0, 0.0]]
    covariance = [[4.0, 19.4], [19.4, 94.08999999999999]]
    prior = StatePrior(0, [0, 0], covariance, "local", ("m", "m"), "prior")
    prediction = predict(prior, LinearDynamics(matrix, np.zeros((2, 2)), "model"), 1)
    expected = sum(Fraction(matrix[0][i]) * Fraction(covariance[i][j]) * Fraction(matrix[0][j])
                   for i in range(2) for j in range(2))
    assert expected > 0
    assert prediction.covariance[0, 0] == float(expected)
    assert prediction.covariance[1, 1] == 0  # exact nullspace remains valid


def test_nonzero_prediction_covariance_below_float64_range_is_refused():
    prior = StatePrior(0, [0], [[1]], "local", ("m",), "prior")
    with pytest.raises(ValueError, match="underflow"):
        predict(prior, LinearDynamics([[1e-200]], [[0]], "model"), 1)


def test_nonzero_crosscovariance_cannot_disappear_with_healthy_variances():
    tiny = np.nextafter(0.0, 1.0)
    prior = StatePrior(0, [0, 0], [[1, tiny], [tiny, 1]], "local", ("m", "m"), "prior")
    model = LinearDynamics([[1, 0], [0, 0.25]], [[0, 0], [0, 0]], "model")
    with pytest.raises(ValueError, match="underflow"):
        predict(prior, model, 1)


def test_exact_cancelled_crosscovariance_remains_a_valid_zero():
    prior = StatePrior(0, [0, 0], [[1, 0], [0, 1]], "local", ("m", "m"), "prior")
    model = LinearDynamics([[1, 1], [1, -1]], [[0, 0], [0, 0]], "model")
    result = predict(prior, model, 1)
    np.testing.assert_array_equal(result.covariance, [[2, 0], [0, 2]])


def test_minimum_subnormal_prediction_covariance_is_preserved():
    tiny = np.nextafter(0.0, 1.0)
    prior = StatePrior(0, [0], [[tiny]], "local", ("m",), "prior")
    assert predict(prior, LinearDynamics([[1]], [[0]], "model"), 1).covariance[0, 0] == tiny


def test_cancelled_innovation_covariance_matches_exact_binary64_oracle():
    prior = StatePrior(0, [0, 0], [[4, 19.4], [19.4, 94.08999999999999]],
                       "local", ("m", "m"), "prior")
    obs = Observation(0, [0], [[0]], "local", ("m",), "obs", ("evidence",))
    estimate = update(prior, obs, LinearObservation([[9.7, -2]], "model", measurement_units=("m",)))
    assert estimate.innovation_covariance[0, 0] > 0


def test_joseph_covariance_cannot_underflow_to_false_certainty():
    tiny = np.nextafter(0.0, 1.0)
    prior = StatePrior(0, [0], [[tiny]], "local", ("m",), "prior")
    obs = Observation(0, [0], [[tiny]], "local", ("m",), "obs", ("evidence",))
    with pytest.raises(ValueError, match="underflow"):
        update(prior, obs, LinearObservation([[1]], "model"))


def test_nonzero_nis_underflow_is_not_reported_as_perfect_agreement():
    prior = StatePrior(0, [0], [[1]], "local", ("m",), "prior")
    obs = Observation(0, [1e-200], [[1]], "local", ("m",), "obs", ("evidence",))
    with pytest.raises(ValueError, match="NIS underflow"):
        update(prior, obs, LinearObservation([[1]], "model"))


def test_small_state_work_budget_is_bounded():
    with pytest.raises(ValueError, match="64-component"):
        StatePrior(0, np.zeros(65), np.eye(65), "local", ("m",) * 65, "prior")


def test_transitions_are_distinct_and_full_sequence_replays():
    original = StatePrior(0, [0], [[1]], "local", ("m",), "prior")
    dynamics = LinearDynamics([[1]], [[0.1]], "dynamics")
    predicted = predict(original, dynamics, 1)
    assert predicted.state_id != original.state_id
    assert predicted.predecessor_state_id == original.state_id
    assert predicted.state_id == predict(original, dynamics, 1).state_id
    obs = Observation(1, [0.5], [[0.3]], "local", ("m",), "obs", ("evidence",))
    estimate = update(predicted, obs, LinearObservation([[1]], "observation-model"))
    assert len({original.state_id, predicted.state_id, estimate.state_id}) == 3
    assert estimate.as_prior().state_id == estimate.state_id
    assert estimate.as_prior("state:explicit-alias").predecessor_state_id == predicted.state_id
    replayed = replay_estimate(estimate.replay_snapshot)
    assert replayed.state_id == estimate.state_id
    assert replayed.numerical_result_id == estimate.numerical_result_id
    with pytest.raises(ValueError, match="predecessor"):
        estimate.as_prior(predicted.state_id)
    second = predict(estimate.as_prior("state:explicit-alias"), dynamics, 2)
    final = update(second, replace(obs, time=2), LinearObservation([[1]], "observation-model"))
    assert replay_estimate(final.replay_snapshot).state_id == final.state_id


def test_replay_refuses_mutated_predecessor_values_and_unknown_geometry():
    prior = StatePrior(0, [0], [[1]], "local", ("m",), "prior")
    predicted = predict(prior, LinearDynamics([[1]], [[0.1]], "model"), 1)
    obs = Observation(1, [0], [[1]], "local", ("m",), "obs", ("evidence",))
    estimate = update(predicted, obs, LinearObservation([[1]], "model"))
    altered = deepcopy(estimate.replay_snapshot)
    altered["prior"]["mean"] = [100]
    with pytest.raises(ValueError, match="preceding transition"):
        replay_estimate(altered)
    altered = deepcopy(estimate.replay_snapshot)
    altered["state_geometry"] = "artifact:run-code"
    with pytest.raises(ValueError, match="geometry"):
        replay_estimate(altered)
