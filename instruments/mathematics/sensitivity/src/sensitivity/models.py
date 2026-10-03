"""Declared differentiable maps used by the testbed."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import ArrayLike, NDArray

Array = NDArray[np.floating]


def as_vector(value: ArrayLike, name: str = "x") -> Array:
    array = np.asarray(value, dtype=float)
    if array.ndim == 0:
        return array.reshape(1)
    if array.ndim != 1:
        raise ValueError(f"{name} must be a 1-D vector, got shape {array.shape}")
    return array


JacobianFn = Callable[[Array], Array]
ForwardFn = Callable[[Array], Array]


@dataclass(frozen=True)
class DifferentiableModel:
    """An explicit map ``y = f(x)`` with optional analytical Jacobian.

    Parameters
    ----------
    name:
        Short identifier used in reports.
    forward:
        Evaluates the model at a 1-D input.
    input_dim, output_dim:
        Declared dimensions. Evaluations are checked against these.
    jacobian:
        Optional analytical Jacobian ``df/dx`` at ``x``. When omitted the
        testbed falls back to finite differences.
    jax_forward:
        Optional JAX-traceable sibling of ``forward``. Required for
        ``source='jax'``. A NumPy closure is not treated as traceable.
    input_names, output_names:
        Optional coordinate labels. They do not change numerics; they make
        permutation and unit tests readable.
    notes:
        Domain restrictions or interpretation caveats.
    """

    name: str
    forward: ForwardFn
    input_dim: int
    output_dim: int
    jacobian: JacobianFn | None = None
    jax_forward: ForwardFn | None = None
    input_names: tuple[str, ...] = ()
    output_names: tuple[str, ...] = ()
    notes: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.input_dim < 1 or self.output_dim < 1:
            raise ValueError("input_dim and output_dim must be positive")
        if self.input_names and len(self.input_names) != self.input_dim:
            raise ValueError("input_names length must match input_dim")
        if self.output_names and len(self.output_names) != self.output_dim:
            raise ValueError("output_names length must match output_dim")

    def evaluate(self, x: ArrayLike) -> Array:
        vector = as_vector(x, "x")
        if vector.size != self.input_dim:
            raise ValueError(
                f"{self.name}: expected input dim {self.input_dim}, got {vector.size}"
            )
        y = np.asarray(self.forward(vector), dtype=float)
        if y.ndim == 0:
            y = y.reshape(1)
        if y.ndim != 1 or y.size != self.output_dim:
            raise ValueError(
                f"{self.name}: expected output dim {self.output_dim}, got shape {y.shape}"
            )
        return y

    def analytical_jacobian(self, x: ArrayLike) -> Array:
        if self.jacobian is None:
            raise ValueError(f"{self.name} does not declare an analytical Jacobian")
        vector = as_vector(x, "x")
        if vector.size != self.input_dim:
            raise ValueError(
                f"{self.name}: expected input dim {self.input_dim}, got {vector.size}"
            )
        jac = np.asarray(self.jacobian(vector), dtype=float)
        expected = (self.output_dim, self.input_dim)
        if jac.shape != expected:
            raise ValueError(
                f"{self.name}: Jacobian shape {jac.shape} != {expected}"
            )
        return jac

    def with_jacobian(self, jacobian: JacobianFn) -> DifferentiableModel:
        return DifferentiableModel(
            name=self.name,
            forward=self.forward,
            input_dim=self.input_dim,
            output_dim=self.output_dim,
            jacobian=jacobian,
            jax_forward=self.jax_forward,
            input_names=self.input_names,
            output_names=self.output_names,
            notes=self.notes,
            tags=self.tags,
        )


def named_axes(prefix: str, count: int) -> tuple[str, ...]:
    return tuple(f"{prefix}{i}" for i in range(count))


def require_models(models: Sequence[DifferentiableModel]) -> tuple[DifferentiableModel, ...]:
    if not models:
        raise ValueError("at least one model is required")
    return tuple(models)
