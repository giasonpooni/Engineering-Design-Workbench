from __future__ import annotations

import numpy as np

from sensitivity.checks import check_derivative
from sensitivity.jacobian import finite_difference_jacobian, jacobian_at
from sensitivity.reference_models import reference_catalogue


def test_analytical_matches_central_on_catalogue():
    catalogue = reference_catalogue()
    points = {
        "affine2": np.array([0.4, -1.2]),
        "quadratic": np.array([0.7, 0.2]),
        "exp2": np.array([0.1, -0.3]),
        "polar": np.array([1.2, 0.4]),
        "scaled-rotation": np.array([0.5, -0.8]),
        "two-tank": np.array([12.0, 8.0, 1.1]),
        "storage": np.array([1.2, 0.8]),
        "balance": np.array([12.0, 8.0]),
        "gauge-totalizer": np.array([12.0, 8.0]),
        "fluid-balance": np.array([1.2, 0.8]),
        "fluid-observer": np.array([1.2, 0.8]),
        "beam-midspan": np.array([10.0, 4.0, 2.0e4]),
    }
    for name, model in catalogue.items():
        result = check_derivative(model, points[name], against="central")
        assert result.passed, result.details


def test_complex_step_on_holomorphic_exp():
    model = reference_catalogue()["exp2"]
    x = np.array([0.25, -0.4])
    analytical = jacobian_at(model, x, source="analytical").matrix
    complex_step = finite_difference_jacobian(model, x, method="complex").matrix
    assert np.allclose(analytical, complex_step, atol=1e-12)
