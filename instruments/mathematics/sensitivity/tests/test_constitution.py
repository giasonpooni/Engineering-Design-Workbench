from __future__ import annotations

import numpy as np
import pytest

from sensitivity.affine import AffinePlant, GaussianState, predict, restore_state, transform_plant, transform_state, update
from sensitivity.constitution import MAX_CONDITION_NUMBER, ROUND_TRIP_TOLERANCE
from sensitivity.coordinates import AffineCoordinates, apply_output_map, push_covariance
from sensitivity.covariance import _require_psd


def test_constitution_values_are_frozen():
    assert MAX_CONDITION_NUMBER == 1e12
    assert ROUND_TRIP_TOLERANCE == 1e-8


def test_condition_cap_refuses_beyond_1e12():
    with pytest.raises(ValueError, match="condition number"):
        AffineCoordinates(T=np.diag([1.0, 1e-13]), S=np.eye(2))


def test_axis_aligned_unit_chart_with_large_scale_ratio_is_allowed():
    chart = AffineCoordinates(T=np.diag([1e-3, 1.0, 1e-6]), S=np.eye(3))
    push_covariance(chart.T, np.diag([25.0, 1e-4, 1e10]), name="P")


def test_exact_zero_row_stays_exact_on_scale_round_trip():
    mapped = push_covariance(np.diag([1000.0, 1000.0]), [[0.0, 0.0], [0.0, 2.0]], name="P")
    np.testing.assert_allclose(mapped[0, :], 0.0)
    np.testing.assert_allclose(mapped[:, 0], 0.0)


def test_clipping_is_not_a_repair_path():
    with pytest.raises(ValueError):
        _require_psd(np.array([[1.0, 2.0], [2.0, 1.0]]), "P")


def test_filter_invariants_not_frobenius_p():
    state = GaussianState([40.0, 60.0], [[1.0, 0.2], [0.2, 1.5]])
    plant = AffinePlant(
        F=[[0.96, 0.03], [0.04, 0.97]],
        drift=[0.2, -0.2],
        Q=0.01 * np.array([[1.0, -1.0], [-1.0, 1.0]]),
        H=np.eye(2),
        offset=[0.7, -0.4],
        R=[[0.25, 0.08], [0.08, 0.36]],
    )
    z = [40.9, 59.6]
    chart = AffineCoordinates(
        T=np.diag([1000.0, 1000.0]),
        S=np.diag([1000.0, 1000.0]),
        input_offset=[0.0, 100.0],
        output_offset=[0.0, 100.0],
    )
    native = update(predict(state, plant), plant, z)
    primed_plant = transform_plant(plant, chart)
    primed = update(
        predict(transform_state(state, chart), primed_plant),
        primed_plant,
        apply_output_map(z, chart),
    )
    restored = restore_state(primed.posterior, chart)
    np.testing.assert_allclose(restored.mean, native.posterior.mean, atol=1e-11, rtol=1e-11)
    np.testing.assert_allclose(primed.statistic, native.statistic, atol=1e-11, rtol=1e-11)
    assert np.linalg.norm(primed.posterior.covariance, "fro") != np.linalg.norm(
        native.posterior.covariance, "fro"
    )
