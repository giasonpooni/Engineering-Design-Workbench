# SPDX-License-Identifier: MPL-2.0
"""Regressions from independent adversarial numerical-contract review."""

import numpy as np
import pytest

from geometric_state_inference import Observation, StatePrior


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
