"""FSRT chart law consumes JSPT. Skip if sensitivity is absent."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("sensitivity")
from set_lcm.bridge.jspt import map_covariance
from set_lcm.coordinates import AffineCoordinates
from set_lcm.invariant import GaussianState


def test_grams_chart_matches_jspt():
    t = np.diag([1000.0, 1000.0])
    p = np.array([[1.0, 0.2], [0.2, 1.5]])
    got = map_covariance(t, p)
    np.testing.assert_allclose(got, [[1e6, 2e5], [2e5, 1.5e6]], atol=1e-11)
    chart = AffineCoordinates(t, np.zeros(2))
    state = GaussianState(np.zeros(2), p)
    out = chart.transform_state(state)
    np.testing.assert_allclose(out.covariance, got, atol=1e-11)
