from __future__ import annotations

import numpy as np
import pytest

from sensitivity.coordinates import AffineCoordinates, skeel_condition
from sensitivity.jacobian import JacobianEstimate


def test_skeel_is_one_on_positive_diagonal():
    chart = AffineCoordinates.scale([1e-3, 1.0, 1e-6], [1.0])
    assert skeel_condition(chart.T) == pytest.approx(1.0)
    assert chart.T_skeel == pytest.approx(1.0)
    assert chart.T_condition == pytest.approx(1e6)


def test_uniform_scale_has_unit_kappa2_and_skeel():
    chart = AffineCoordinates.scale([1000.0, 1000.0], [1000.0, 1000.0])
    assert chart.T_condition == pytest.approx(1.0)
    assert chart.T_skeel == pytest.approx(1.0)


def test_rectangular_jacobian_refuses_kappa2():
    estimate = JacobianEstimate(matrix=np.array([[1.0, 2.0, 3.0]]), source="analytical", point=np.zeros(3))
    assert estimate.structure().rank == 1
    with pytest.raises(ValueError, match="structure"):
        _ = estimate.condition_number
