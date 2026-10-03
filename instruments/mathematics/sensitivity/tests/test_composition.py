from __future__ import annotations

import numpy as np

from sensitivity.checks import check_composition
from sensitivity.composition import compose
from sensitivity.reference_models import affine_map, componentwise_exp, scaled_rotation


def test_chain_rule_matches_composed_map():
    stages = [scaled_rotation(), componentwise_exp(dim=2), affine_map([[1.0, 0.2], [0.0, 0.7]])]
    result = check_composition(stages, np.array([0.3, -0.15]))
    assert result.passed, result.details


def test_compose_evaluates_in_application_order():
    first = affine_map([[2.0, 0.0], [0.0, 3.0]], name="scale")
    second = affine_map([[0.0, 1.0], [1.0, 0.0]], name="swap")
    composed = compose([first, second], name="scale-then-swap")
    value = composed.evaluate([1.0, 1.0])
    assert np.allclose(value, [3.0, 2.0])
