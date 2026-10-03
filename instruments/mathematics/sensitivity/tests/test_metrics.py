from __future__ import annotations

import numpy as np
import pytest

from sensitivity.checks import check_metric_consistency
from sensitivity.coordinates import AffineCoordinates
from sensitivity.jacobian import jacobian_at
from sensitivity.metrics import DeclaredMetric
from sensitivity.reference_models import reference_catalogue


def test_unscaled_gain_changes_with_units_scaled_gain_does_not():
    model = reference_catalogue()["fluid-observer"]
    x = np.array([1.2, 0.8])
    jac = jacobian_at(model, x).matrix
    coords = AffineCoordinates.scale([1000.0, 1000.0], [1.0, 1.0], name="level-mm")
    metric = DeclaredMetric.identity(2, 2, name="si")
    raw = float(np.linalg.norm(jac, ord=2))
    primed = float(np.linalg.norm(coords.S @ jac @ coords.T_inv, ord=2))
    assert not np.isclose(raw, primed)
    result = check_metric_consistency(model, x, coords, metric)
    assert result.passed, result.details
    assert np.isclose(result.extra["gain"], result.extra["primed_gain"], rtol=1e-10)


def test_diagonal_metric_rejects_zero_scale():
    with pytest.raises(ValueError):
        DeclaredMetric.diagonal([1.0, 0.0], [1.0, 1.0])
