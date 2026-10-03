from __future__ import annotations

import numpy as np

from sensitivity.affine import (
    AffinePlant,
    GaussianState,
    invariant_error,
    predict,
    restore_state,
    retract,
    transform_plant,
    transform_state,
    update,
)
from sensitivity.coordinates import AffineCoordinates, apply_output_map


def _plant():
    state = GaussianState([40.0, 60.0], [[1.0, 0.2], [0.2, 1.5]])
    plant = AffinePlant(
        F=[[0.96, 0.03], [0.04, 0.97]],
        drift=[0.2, -0.2],
        Q=0.01 * np.array([[1.0, -1.0], [-1.0, 1.0]]),
        H=np.eye(2),
        offset=[0.7, -0.4],
        R=[[0.25, 0.08], [0.08, 0.36]],
    )
    return state, plant, np.array([40.9, 59.6])


def test_translation_invariance_of_additive_error():
    ref = np.array([40.0, 60.0])
    val = np.array([41.0, 58.5])
    shift = np.array([100.0, -20.0])
    np.testing.assert_allclose(invariant_error(ref + shift, val + shift), invariant_error(ref, val))
    np.testing.assert_allclose(retract(ref, invariant_error(ref, val)), val)


def test_predict_is_exact_affine_pushforward():
    state, plant, _ = _plant()
    prior = predict(state, plant)
    np.testing.assert_allclose(prior.mean, plant.F @ state.mean + plant.drift)
    np.testing.assert_allclose(prior.covariance, plant.F @ state.covariance @ plant.F.T + plant.Q)


def test_chart_with_origin_preserves_posterior_and_nis():
    state, plant, measurement = _plant()
    chart = AffineCoordinates(
        T=np.diag([1000.0, 1000.0]),
        S=np.diag([1000.0, 1000.0]),
        name="grams-datum",
        input_offset=[0.0, 100.0],
        output_offset=[0.0, 100.0],
    )
    native = update(predict(state, plant), plant, measurement)
    primed_plant = transform_plant(plant, chart)
    primed = update(
        predict(transform_state(state, chart), primed_plant),
        primed_plant,
        apply_output_map(measurement, chart),
    )
    restored = restore_state(primed.posterior, chart)
    np.testing.assert_allclose(restored.mean, native.posterior.mean, atol=1e-12, rtol=1e-12)
    np.testing.assert_allclose(restored.covariance, native.posterior.covariance, atol=1e-12, rtol=1e-12)
    np.testing.assert_allclose(primed.statistic, native.statistic, atol=1e-12, rtol=1e-12)


def test_update_reduces_covariance_trace():
    state, plant, measurement = _plant()
    prior = predict(state, plant)
    posterior = update(prior, plant, measurement).posterior
    assert np.trace(posterior.covariance) < np.trace(prior.covariance)
