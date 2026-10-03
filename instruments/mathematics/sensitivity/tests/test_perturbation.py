from __future__ import annotations

import numpy as np

from sensitivity.perturbation import local_validity, perturbation_error, sweep_perturbation_scale
from sensitivity.reference_models import reference_catalogue


def test_affine_remainder_is_numerically_zero():
    model = reference_catalogue()["affine2"]
    sample = perturbation_error(model, [1.0, -2.0], [0.4, 0.7])
    assert sample.absolute_error < 1e-12


def test_quadratic_remainder_matches_exact_formula():
    model = reference_catalogue()["quadratic"]
    x = np.array([0.2, -0.1])
    dx = np.array([0.3, 0.4])
    sample = perturbation_error(model, x, dx)
    hess = np.array([[2.0, 0.4], [0.4, 1.2]])
    exact = 0.5 * float(dx @ hess @ dx)
    assert abs(sample.absolute_error - abs(exact)) < 1e-12


def test_local_validity_shrinks_for_exponential():
    model = reference_catalogue()["exp2"]
    sweep = sweep_perturbation_scale(
        model,
        [0.0, 0.0],
        [1.0, 0.2],
        scales=[1e-4, 1e-2, 1e-1, 1.0, 3.0],
    )
    validity = local_validity(sweep, absolute_tolerance=1e-3, relative_tolerance=5e-2)
    assert validity.valid_scale is not None
    assert validity.first_invalid_scale is not None
    assert validity.valid_scale < validity.first_invalid_scale
