from __future__ import annotations

import numpy as np

from sensitivity.reference_models import affine_map, simply_supported_midspan
from sensitivity.structure import linearized_mean_gap, local_structure, propagate_belief


def test_affine_mean_equals_exact_and_linearized():
    model = affine_map([[2.0, 0.0], [0.0, 3.0]], offset=[1.0, -4.0])
    belief = propagate_belief(model, [1.0, 2.0], np.eye(2))
    np.testing.assert_allclose(belief.mean, [3.0, 2.0])
    np.testing.assert_allclose(belief.covariance, [[4.0, 0.0], [0.0, 9.0]])
    assert belief.rank == 2
    assert belief.invisible.shape == (2, 0)


def test_beam_mean_is_exact_reevaluation_not_j_times_x():
    model = simply_supported_midspan()
    x = np.array([10.0e3, 4.0, 8.0e6])
    belief = propagate_belief(model, x, np.diag([1.0, 1e-4, 1e8]))
    exact = model.evaluate(x)
    np.testing.assert_allclose(belief.mean, exact)
    gap = linearized_mean_gap(model, x)
    assert gap > 0.5 * float(np.linalg.norm(exact))


def test_beam_has_two_invisible_input_directions():
    model = simply_supported_midspan()
    x = np.array([10.0e3, 4.0, 8.0e6])
    structure = local_structure(model.analytical_jacobian(x))
    assert structure.rank == 1
    assert structure.invisible.shape == (3, 2)
    np.testing.assert_allclose(model.analytical_jacobian(x) @ structure.invisible, 0.0, atol=1e-8)
