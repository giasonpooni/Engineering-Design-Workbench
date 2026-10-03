from __future__ import annotations

import numpy as np
import pytest

from sensitivity.jacobian import jacobian_at, jax_is_available
from sensitivity.reference_models import polar_from_cartesian, reference_catalogue


def test_jax_refused_without_traceable_sibling():
    model = polar_from_cartesian()
    with pytest.raises(RuntimeError, match="jax_forward"):
        jacobian_at(model, [1.2, 0.4], source="jax")


@pytest.mark.skipif(not jax_is_available(), reason="optional jax extra is not installed")
def test_jax_matches_analytical_on_traceable_exp():
    model = reference_catalogue()["exp2"]
    x = np.array([0.2, -0.15])
    analytical = jacobian_at(model, x, source="analytical").matrix
    ad = jacobian_at(model, x, source="jax").matrix
    assert np.allclose(analytical, ad, atol=1e-12)
