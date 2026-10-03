from __future__ import annotations

import numpy as np
import pytest

from sensitivity.affine import GaussianState, transform_state
from sensitivity.coordinates import AffineCoordinates, push_covariance


def test_round_trip_preserves_mean_in_sigma_units():
    chart = AffineCoordinates(T=np.diag([1000.0, 1000.0]), S=np.eye(2), input_offset=[0.0, 100.0])
    state = GaussianState([40.0, 60.0], [[1.0, 0.2], [0.2, 1.5]])
    primed = transform_state(state, chart)
    np.testing.assert_allclose(primed.mean, [40000.0, 60100.0])


def test_exact_zero_direction_survives_scale_chart():
    chart = AffineCoordinates(T=np.diag([1000.0, 1000.0]), S=np.eye(2))
    cov = np.array([[0.0, 0.0], [0.0, 2.0]])
    mapped = push_covariance(chart.T, cov, name="P")
    np.testing.assert_allclose(mapped, [[0.0, 0.0], [0.0, 2e6]])


def test_chart_that_corrupts_exact_zero_is_refused():
    t = np.array([[1.0, 1e-16], [0.0, 1e-16]])
    cov = np.array([[0.0, 0.0], [0.0, 1.0]])
    with pytest.raises(ValueError):
        push_covariance(t, cov, name="P")


def test_transform_state_refuses_origin_cancellation_on_exact_zero():
    chart = AffineCoordinates(
        T=np.array([[1.0, 0.3], [0.0, 1.0]]),
        S=np.eye(2),
        input_offset=[1e20, 0.0],
    )
    state = GaussianState([0.0, 1.0], np.zeros((2, 2)))
    with pytest.raises(ValueError, match="round trip"):
        transform_state(state, chart)
