# SPDX-License-Identifier: MPL-2.0
from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from fdir import CusumState, cusum_step, evaluate_residual


def evaluate(residual, covariance, **overrides):
    kwargs = dict(threshold=4.0, variable_order=[f"axis-{i}" for i in range(len(residual))], source_ids=["innovation:fixture:1"])
    kwargs.update(overrides)
    return evaluate_residual(residual, covariance, **kwargs)


def step(value, state=None, **overrides):
    kwargs = dict(drift=0.5, threshold=3.0, direction="two_sided", source_ids=["sample:fixture:1"])
    kwargs.update(overrides)
    return cusum_step(value, state if state is not None else CusumState(), **kwargs)


def test_scalar_nis_analytical_and_equality_threshold():
    result = evaluate([6.0], [[9.0]], threshold=4.0)
    assert result.nis == 4.0
    assert result.marginal_normalized_residual == (2.0,)
    assert result.whitened_residual == (2.0,)
    assert result.status == "statistical_anomaly"
    assert evaluate([3.0], [[9.0]]).status == "nominal"


def test_correlated_covariance_requires_whitening():
    # S = L L^T for L = [[2, 0], [1, 2]], so L^-1 [2, 3] = [1, 1].
    result = evaluate([2.0, 3.0], [[4.0, 2.0], [2.0, 5.0]])
    assert result.whitened_residual == (1.0, 1.0)
    assert result.nis == 2.0
    assert result.marginal_normalized_residual == pytest.approx([1.0, 3 / np.sqrt(5)])
    assert sum(x*x for x in result.marginal_normalized_residual) != result.nis


def test_covariance_and_residual_consistent_scaling_preserves_nis():
    reference = evaluate([2.0, 3.0], [[4.0, 2.0], [2.0, 5.0]])
    tiny = evaluate([2e-100, 3e-100], [[4e-200, 2e-200], [2e-200, 5e-200]])
    assert tiny.nis == pytest.approx(reference.nis)


@pytest.mark.parametrize("covariance", [
    [[1, 2], [2, 1]],                       # indefinite
    [[1, 1], [1, 1]],                       # singular
    [[1e-200, 2e-200], [2e-200, 1e-200]],   # tiny indefinite
    [[1e-200, 1e-202], [0, 1e-200]],        # tiny asymmetric
    [[1, 1e-16], [0, 1]],                  # any asymmetry is explicit
    [[1, float("nan")], [float("nan"), 1]],
    [[1, 0], [0, float("inf")]],
    [[1, 0, 0], [0, 1, 0]],
])
def test_invalid_covariances_rejected(covariance):
    with pytest.raises(ValueError):
        evaluate([1, 1], covariance)


@pytest.mark.parametrize("residual,covariance", [
    ([], []),
    ([[1.0]], [[1.0]]),
    ([float("nan")], [[1.0]]),
    ([float("inf")], [[1.0]]),
    ([1j], [[1.0]]),
    ([True], [[1.0]]),
    (["1"], [[1.0]]),
    ([1.0], [[-1.0]]),
    ([1.0], [[0.0]]),
    ([1.0], [[True]]),
    ([1e300], [[1e-100]]),
])
def test_bad_inputs_or_unrepresentable_outputs_rejected(residual, covariance):
    with pytest.raises(ValueError):
        evaluate(residual, covariance)


@pytest.mark.parametrize("threshold", [0, -1, float("inf"), float("nan"), True, "4"])
def test_threshold_requires_finite_positive_real(threshold):
    with pytest.raises(ValueError):
        evaluate([1], [[1]], threshold=threshold)


@pytest.mark.parametrize("overrides", [
    {"variable_order": []}, {"variable_order": ["x", "y"]},
    {"variable_order": [""]}, {"source_ids": []},
    {"source_ids": ["same", "same"]}, {"source_ids": "source"},
])
def test_order_and_source_identity_validation(overrides):
    with pytest.raises(ValueError):
        evaluate([1], [[1]], **overrides)


def test_residual_inputs_are_not_mutated_or_aliased():
    residual = np.array([2., 3.])
    covariance = np.array([[4., 2.], [2., 5.]])
    sources = ["innovation:1"]
    order = ["x", "y"]
    result = evaluate(residual, covariance, source_ids=sources, variable_order=order)
    np.testing.assert_array_equal(residual, [2., 3.])
    np.testing.assert_array_equal(covariance, [[4., 2.], [2., 5.]])
    residual[:] = 0
    covariance[:] = 0
    sources[0] = "changed"
    order[0] = "changed"
    assert result.raw_residual == (2., 3.)
    assert result.innovation_covariance == ((4., 2.), (2., 5.))
    assert result.source_ids == ("innovation:1",)
    assert result.variable_order == ("x", "y")
    with pytest.raises(FrozenInstanceError):
        result.nis = 8


def test_cusum_detects_persistent_drift_and_reports_pre_reset_value():
    state = CusumState()
    results = []
    for index in range(3):
        result = step(1.5, state, source_ids=[f"innovation:{index}"], reset_on_alarm=True)
        results.append(result)
        state = result.next_state
    assert [result.status for result in results] == ["nominal", "nominal", "statistical_anomaly"]
    assert results[-1].observed_state == CusumState(3.0, 0.0, 3)
    assert state == CusumState(0.0, 0.0, 3)
    assert results[-1].alarm_sides == ("positive",)
    assert results[-1].prior_state == CusumState(2.0, 0.0, 2)
    assert step(1.5, state).status == "nominal"


def test_cusum_default_preserves_statistics_after_alarm():
    result = step(-2, CusumState(0, 2, 4))
    assert result.observed_state == CusumState(0, 3.5, 5)
    assert result.next_state == result.observed_state
    assert result.status == "statistical_anomaly"
    assert result.alarm_sides == ("negative",)


def test_cusum_one_sided_and_floor_at_zero():
    assert step(-100, direction="positive").next_state == CusumState(0, 0, 1)
    assert step(100, direction="negative").next_state == CusumState(0, 0, 1)
    assert step(-4, direction="negative").alarm_sides == ("negative",)
    assert step(0, CusumState(0.1, 0.2)).next_state == CusumState(0, 0, 1)


def test_cusum_is_deterministic_and_does_not_mutate_state():
    prior = CusumState(1, 0, 2)
    a = step(2, prior)
    b = step(2, prior)
    assert a == b
    assert prior == CusumState(1, 0, 2)
    assert a.raw_value == 2
    assert a.source_ids == ("sample:fixture:1",)
    with pytest.raises(FrozenInstanceError):
        prior.positive = 0


@pytest.mark.parametrize("overrides", [
    {"drift": -1}, {"drift": float("nan")}, {"drift": True},
    {"threshold": 0}, {"threshold": float("inf")},
    {"direction": "unknown"}, {"source_ids": []}, {"reset_on_alarm": 1},
])
def test_cusum_configuration_validation(overrides):
    with pytest.raises(ValueError):
        step(1, **overrides)


@pytest.mark.parametrize("state", [
    CusumState(-1, 0), CusumState(0, float("inf")),
    CusumState(0, 0, -1), CusumState(0, 0, 1.5), CusumState(0, 0, True),
    CusumState(float("nan"), 0),
])
def test_cusum_prior_state_validation(state):
    with pytest.raises(ValueError):
        step(1, state)


def test_cusum_direction_change_cannot_silently_discard_active_state():
    with pytest.raises(ValueError):
        step(1, CusumState(0, 1), direction="positive")
    with pytest.raises(ValueError):
        step(1, CusumState(1, 0), direction="negative")


def test_cusum_nonfinite_and_overflow_rejected():
    with pytest.raises(ValueError):
        step(float("nan"))
    with pytest.raises(ValueError):
        step(1e308, CusumState(1e308, 0))
