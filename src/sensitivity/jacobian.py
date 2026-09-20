"""Jacobian evaluation, finite differences, and first-order maps."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import ArrayLike, NDArray

from .models import DifferentiableModel, as_vector

Array = NDArray[np.floating]
JacobianSource = Literal["analytical", "central", "forward", "complex", "jax", "auto"]


@dataclass(frozen=True)
class JacobianEstimate:
    matrix: Array
    source: str
    point: Array
    step: Array | None = None

    @property
    def shape(self) -> tuple[int, int]:
        return tuple(self.matrix.shape)  # type: ignore[return-value]

    def structure(self, *, singular_atol: float = 1e-10):
        """Return the local visible/invisible structure of this estimate."""
        from .structure import local_structure

        return local_structure(self.matrix, singular_atol=singular_atol)

    @property
    def condition_number(self) -> float:
        if self.matrix.ndim != 2 or self.matrix.shape[0] != self.matrix.shape[1]:
            raise ValueError(
                "condition_number requires a square Jacobian; use structure() "
                "for rectangular maps"
            )
        return float(np.linalg.cond(self.matrix))


def jvp(jacobian: ArrayLike, dx: ArrayLike) -> Array:
    jac = np.asarray(jacobian, dtype=float)
    delta = as_vector(dx, "dx")
    if jac.ndim != 2:
        raise ValueError(f"Jacobian must be 2-D, got {jac.shape}")
    if jac.shape[1] != delta.size:
        raise ValueError(f"J is {jac.shape}, dx has length {delta.size}")
    return jac @ delta


def vjp(jacobian: ArrayLike, dy: ArrayLike) -> Array:
    jac = np.asarray(jacobian, dtype=float)
    cotan = as_vector(dy, "dy")
    if jac.ndim != 2:
        raise ValueError(f"Jacobian must be 2-D, got {jac.shape}")
    if jac.shape[0] != cotan.size:
        raise ValueError(f"J is {jac.shape}, dy has length {cotan.size}")
    return jac.T @ cotan


def _default_step(x: Array, rel: float) -> Array:
    return rel * np.maximum(1.0, np.abs(x))


def finite_difference_jacobian(
    model: DifferentiableModel,
    x: ArrayLike,
    *,
    method: Literal["central", "forward", "complex"] = "central",
    relative_step: float | None = None,
) -> JacobianEstimate:
    point = as_vector(x, "x")
    if point.size != model.input_dim:
        raise ValueError(f"expected input dim {model.input_dim}, got {point.size}")
    if method == "complex":
        step_scale = 1e-20 if relative_step is None else relative_step
        steps = _default_step(point, step_scale)
        jac = np.zeros((model.output_dim, model.input_dim), dtype=float)
        for i in range(model.input_dim):
            probe = point.astype(complex)
            probe[i] += 1j * steps[i]
            value = np.asarray(model.forward(probe), dtype=complex)
            if value.ndim == 0:
                value = value.reshape(1)
            jac[:, i] = np.imag(value) / steps[i]
        return JacobianEstimate(matrix=jac, source="complex", point=point, step=steps)
    if relative_step is None:
        relative_step = 1.5e-6 if method == "central" else 1.0e-6
    steps = _default_step(point, relative_step)
    y0 = model.evaluate(point)
    jac = np.zeros((model.output_dim, model.input_dim), dtype=float)
    for i in range(model.input_dim):
        plus = point.copy()
        plus[i] += steps[i]
        y_plus = model.evaluate(plus)
        if method == "forward":
            jac[:, i] = (y_plus - y0) / steps[i]
        else:
            minus = point.copy()
            minus[i] -= steps[i]
            y_minus = model.evaluate(minus)
            jac[:, i] = (y_plus - y_minus) / (2.0 * steps[i])
    return JacobianEstimate(matrix=jac, source=method, point=point, step=steps)


def jax_is_available() -> bool:
    try:
        import jax  # noqa: F401
    except ImportError:
        return False
    return True


def _jax_jacobian(model: DifferentiableModel, x: Array) -> JacobianEstimate:
    if model.jax_forward is None:
        raise RuntimeError(
            f"{model.name} has no jax_forward; source='jax' is only used "
            "on maps that declare a traceable sibling, not on NumPy closures"
        )
    try:
        import jax
        import jax.numpy as jnp
    except ImportError as exc:
        raise RuntimeError("jax is not installed; install the optional [ad] extra") from exc

    def wrapped(vec):
        return jnp.asarray(model.jax_forward(vec))

    jac = np.asarray(jax.jacfwd(wrapped)(jnp.asarray(x, dtype=float)), dtype=float)
    expected = (model.output_dim, model.input_dim)
    if jac.shape != expected:
        raise ValueError(f"{model.name}: JAX Jacobian shape {jac.shape} != {expected}")
    return JacobianEstimate(matrix=jac, source="jax", point=x)


def jacobian_at(
    model: DifferentiableModel,
    x: ArrayLike,
    *,
    source: JacobianSource = "auto",
) -> JacobianEstimate:
    point = as_vector(x, "x")
    if source == "analytical":
        return JacobianEstimate(matrix=model.analytical_jacobian(point), source="analytical", point=point)
    if source in {"central", "forward", "complex"}:
        return finite_difference_jacobian(model, point, method=source)
    if source == "jax":
        return _jax_jacobian(model, point)
    if source != "auto":
        raise ValueError(f"unknown Jacobian source {source!r}")
    if model.jacobian is not None:
        return JacobianEstimate(matrix=model.analytical_jacobian(point), source="analytical", point=point)
    return finite_difference_jacobian(model, point, method="central")
