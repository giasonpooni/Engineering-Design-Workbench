"""Explicit unit-test kernel double; records are emitted by the real adapter."""
import sys
import types
from unittest.mock import patch

from schematics.adapters.jspt import call_jacobian_at
from schematics.ir import Status


def sampled_jacobian(schematic):
    fake = types.ModuleType("sensitivity")
    fake.DifferentiableModel = lambda **kwargs: types.SimpleNamespace(**kwargs)
    fake.jacobian_at = lambda model, x: types.SimpleNamespace(matrix=model.jacobian(x), source="unit-test-double")
    with patch.dict(sys.modules, {"sensitivity": fake}):
        assert call_jacobian_at(schematic, "f").result is Status.SAMPLED
    return schematic
