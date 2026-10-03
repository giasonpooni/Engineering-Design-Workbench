"""Composition of declared maps and chain-rule Jacobians."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from numpy.typing import ArrayLike, NDArray

from .jacobian import jacobian_at
from .models import DifferentiableModel, require_models

Array = NDArray[np.floating]


def compose(
    models: Sequence[DifferentiableModel],
    *,
    name: str | None = None,
) -> DifferentiableModel:
    """Build F = f_n o ... o f_1 with a chain-rule Jacobian when possible.

    Stage order is application order: ``models[0]`` is applied first.
    Adjacent dimensions must match. If every stage declares an analytical
    Jacobian, the composition does too.
    """
    stages = require_models(models)
    for left, right in zip(stages, stages[1:]):
        if left.output_dim != right.input_dim:
            raise ValueError(
                f"cannot compose {left.name} (out={left.output_dim}) "
                f"with {right.name} (in={right.input_dim})"
            )

    first, last = stages[0], stages[-1]
    composed_name = name or " o ".join(stage.name for stage in stages)

    def forward(x: Array) -> Array:
        value = x
        for stage in stages:
            value = stage.evaluate(value)
        return value

    analytical = all(stage.jacobian is not None for stage in stages)
    traceable = all(stage.jax_forward is not None for stage in stages)

    def jacobian(x: Array) -> Array:
        return chain_rule_jacobian(stages, x, source="analytical" if analytical else "auto")

    def jax_forward(x: Array) -> Array:
        value = x
        for stage in stages:
            assert stage.jax_forward is not None
            value = stage.jax_forward(value)
        return value

    return DifferentiableModel(
        name=composed_name,
        forward=forward,
        input_dim=first.input_dim,
        output_dim=last.output_dim,
        jacobian=jacobian if analytical else None,
        jax_forward=jax_forward if traceable else None,
        input_names=first.input_names,
        output_names=last.output_names,
        notes="composed map; Jacobian uses the chain rule through declared stages",
        tags=("composed",),
    )


def chain_rule_jacobian(
    models: Sequence[DifferentiableModel],
    x: ArrayLike,
    *,
    source: str = "auto",
) -> Array:
    """J_F(x) = J_fn(x_{n-1}) ... J_f1(x)."""
    stages = require_models(models)
    value = np.asarray(x, dtype=float)
    pieces: list[Array] = []
    for stage in stages:
        pieces.append(jacobian_at(stage, value, source=source).matrix)  # type: ignore[arg-type]
        value = stage.evaluate(value)
    jac = pieces[0]
    for factor in pieces[1:]:
        jac = factor @ jac
    return jac
