"""Shared chart-law contract. FSRT should reproduce these numbers."""

from __future__ import annotations

import numpy as np

from sensitivity.affine import AffinePlant, GaussianState, predict, restore_state, transform_plant, transform_state, update
from sensitivity.coordinates import AffineCoordinates, apply_output_map

F = [[0.96, 0.03], [0.04, 0.97]]
DRIFT = [0.2, -0.2]
Q = 0.01 * __import__("numpy").array([[1.0, -1.0], [-1.0, 1.0]])
H = __import__("numpy").eye(2)
OFFSET = [0.7, -0.4]
R = [[0.25, 0.08], [0.08, 0.36]]
MEAN = [40.0, 60.0]
P = [[1.0, 0.2], [0.2, 1.5]]
Z = [40.9, 59.6]


def test_two_tank_chart_restores_posterior_and_nis():
    import numpy as np
    state = GaussianState(MEAN, P)
    plant = AffinePlant(F, DRIFT, Q, H, OFFSET, R)
    chart = AffineCoordinates(
        T=np.diag([1000.0, 1000.0]),
        S=np.diag([1000.0, 1000.0]),
        name="grams-datum",
        input_offset=[0.0, 100.0],
        output_offset=[0.0, 100.0],
    )
    native = update(predict(state, plant), plant, Z)
    primed_plant = transform_plant(plant, chart)
    primed = update(
        predict(transform_state(state, chart), primed_plant),
        primed_plant,
        apply_output_map(Z, chart),
    )
    restored = restore_state(primed.posterior, chart)
    np.testing.assert_allclose(restored.mean, native.posterior.mean, atol=1e-11, rtol=1e-11)
    np.testing.assert_allclose(restored.covariance, native.posterior.covariance, atol=1e-11, rtol=1e-11)
    np.testing.assert_allclose(primed.statistic, native.statistic, atol=1e-11, rtol=1e-11)
