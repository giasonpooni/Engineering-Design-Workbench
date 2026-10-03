"""Preserve a declared noiseless observation through the harmonic report map."""
import numpy as np
import pytest

from set_lcm.schema import Observation
from set_lcm.testbed.estimators_water import TideConfig, TideKF, TideMonthKF


def observation(step, variance, *, present=True):
    return Observation(
        t=360.0 * step, arrival_t=360.0 * step,
        y=np.array([0.25 if present else np.nan]), R=np.array([[variance]]),
        mask=np.array([present]), source_ids=("synthetic-tide",),
    )


@pytest.mark.parametrize("kind", [TideKF, TideMonthKF])
@pytest.mark.parametrize("q", [1e-7, 0.1])
def test_noiseless_report_has_zero_variance_and_cross_covariance(kind, q):
    clock = np.arange(4) * 360.0
    est = kind((0.0,), 10.0, 360.0, np.zeros(4), TideConfig(q), clock=clock)
    est.ingest(observation(0, 1e-6), 0)
    est.ingest(observation(1, 0.0), 1)
    state_before, covariance_before = est._x.copy(), est._P.copy()
    x, P = est.report(1)
    assert x[0] == pytest.approx(0.25, abs=1e-12)
    np.testing.assert_array_equal(P[0], np.zeros(est.N + 1))
    np.testing.assert_array_equal(P[:, 0], np.zeros(est.N + 1))
    np.testing.assert_array_equal(P[1:, 1:], covariance_before)
    np.testing.assert_array_equal(est._x, state_before)
    np.testing.assert_array_equal(est._P, covariance_before)

    # A future report must recover uncertainty from both the changed H and Q.
    future_x, future_P = est.predict(state_before, covariance_before)
    T = np.vstack([est.H(2), np.eye(est.N)])
    reported_x, reported_P = est.report(2)
    np.testing.assert_allclose(reported_x, T @ future_x)
    np.testing.assert_allclose(reported_P, T @ future_P @ T.T)
    assert reported_P[0, 0] > 0.0


@pytest.mark.parametrize("kind", [TideKF, TideMonthKF])
@pytest.mark.parametrize("variance,present", [(1e-6, True), (0.0, False)])
def test_noisy_or_missing_reading_does_not_zero_the_report(kind, variance, present):
    clock = np.arange(3) * 360.0
    est = kind((0.0,), 10.0, 360.0, np.zeros(3), TideConfig(1e-4), clock=clock)
    est.ingest(observation(0, 0.0), 0)
    est.ingest(observation(1, variance, present=present), 1)
    T = np.vstack([est.H(1), np.eye(est.N)])
    x, P = est.report(1)
    np.testing.assert_allclose(x, T @ est._x)
    np.testing.assert_allclose(P, T @ est._P @ T.T)
    assert P[0, 0] > 0.0
