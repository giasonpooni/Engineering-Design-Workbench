from __future__ import annotations

import numpy as np
import pytest

from sensitivity.checks import check_covariance_affine
from sensitivity.covariance import first_order_covariance, run_covariance_experiment
from sensitivity.reference_models import reference_catalogue


def test_affine_covariance_matches_monte_carlo():
    model = reference_catalogue()["affine2"]
    mean = np.array([0.2, -0.4])
    sigma = np.array([[0.04, 0.01], [0.01, 0.09]])
    result = check_covariance_affine(model, mean, sigma, samples=8000, seed=1)
    assert result.passed, result.details


def test_zero_variance_row_must_be_exactly_zero():
    jac = np.eye(2)
    with pytest.raises(ValueError, match="zero-variance"):
        first_order_covariance(jac, [[0.0, 0.1], [0.1, 1.0]])


def test_nonlinear_covariance_gap_grows_with_spread():
    model = reference_catalogue()["exp2"]
    mean = np.array([0.0, 0.0])
    tight = run_covariance_experiment(
        model, mean, np.diag([1e-4, 1e-4]), samples=3000, rng=np.random.default_rng(2)
    )
    wide = run_covariance_experiment(
        model, mean, np.diag([0.25, 0.25]), samples=3000, rng=np.random.default_rng(2)
    )
    assert tight.relative_gap < wide.relative_gap
