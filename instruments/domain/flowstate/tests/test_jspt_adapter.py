"""Compare FSRT charts to the pinned JSPT law when the extra is installed."""
from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("sensitivity")

from sensitivity.coordinates import push_covariance
from set_lcm.coordinates import AffineCoordinates
from set_lcm.invariant import GaussianState


def test_fsrt_push_matches_jspt_on_two_tank_scale_chart():
    p = np.array([[1.0, 0.2], [0.2, 1.5]])
    t = np.diag([1000.0, 1000.0])
    chart = AffineCoordinates(t, [0.0, 100.0])
    primed = chart.transform_state(GaussianState([40.0, 60.0], p))
    jspt = push_covariance(t, p, name="P")
    np.testing.assert_allclose(primed.covariance, jspt, atol=0.0, rtol=1e-12)


def test_exact_zero_direction_agrees_with_jspt():
    p = np.array([[0.0, 0.0], [0.0, 2.0]])
    t = np.diag([1000.0, 1000.0])
    chart = AffineCoordinates(t, [0.0, 0.0])
    primed = chart.transform_state(GaussianState([0.0, 1.0], p))
    jspt = push_covariance(t, p, name="P")
    np.testing.assert_allclose(primed.covariance, jspt)
    np.testing.assert_array_equal(primed.covariance[0], [0.0, 0.0])
