"""Declared input/output metrics for sensitivity scores.

Raw Jacobian norms and singular values change when units change. A
score is only comparable across representations when the quadratic
forms on ``dx`` and ``dy`` are declared and transformed with the model.

If ``x' = T x`` and ``y' = S y``, the pushed metrics are

    W_x' = T^{-T} W_x T^{-1},
    W_y' = S^{-T} W_y S^{-1}.

Then ``W_y^{1/2} J W_x^{-1/2}`` and ``W_y'^{1/2} J' W_x'^{-1/2}`` have
the same singular values. That scaled operator is the sensitivity
score this testbed will report.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

from .coordinates import AffineCoordinates
from .models import as_vector

Array = NDArray[np.floating]


def _spd(matrix: ArrayLike, name: str, size: int) -> Array:
    cov = np.asarray(matrix, dtype=float)
    if cov.ndim == 1:
        cov = np.diag(cov)
    if cov.shape != (size, size):
        raise ValueError(f"{name} must be {size}x{size} or a length-{size} diagonal")
    if not np.allclose(cov, cov.T, atol=1e-12):
        raise ValueError(f"{name} must be symmetric")
    eig = np.linalg.eigvalsh(cov)
    if np.any(eig <= 0.0):
        raise ValueError(f"{name} must be positive definite")
    return 0.5 * (cov + cov.T)


def _whitener(weight: Array) -> Array:
    evals, evecs = np.linalg.eigh(weight)
    return evecs @ np.diag(np.sqrt(evals)) @ evecs.T


def _unwhitener(weight: Array) -> Array:
    evals, evecs = np.linalg.eigh(weight)
    return evecs @ np.diag(1.0 / np.sqrt(evals)) @ evecs.T


@dataclass(frozen=True)
class DeclaredMetric:
    """Positive-definite weights on the input and output tangent spaces."""

    name: str
    input_weight: Array
    output_weight: Array

    @classmethod
    def identity(cls, input_dim: int, output_dim: int, name: str = "si") -> DeclaredMetric:
        return cls(name=name, input_weight=np.eye(input_dim), output_weight=np.eye(output_dim))

    @classmethod
    def diagonal(
        cls,
        input_scales: ArrayLike,
        output_scales: ArrayLike,
        name: str = "diagonal",
    ) -> DeclaredMetric:
        """Weights ``1/scale^2`` so a unit step in each declared unit has norm 1."""
        din = as_vector(input_scales, "input_scales")
        dout = as_vector(output_scales, "output_scales")
        if np.any(din == 0.0) or np.any(dout == 0.0):
            raise ValueError("metric scales must be nonzero")
        return cls(
            name=name,
            input_weight=np.diag(1.0 / (din * din)),
            output_weight=np.diag(1.0 / (dout * dout)),
        )

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_weight", _spd(self.input_weight, "input_weight", np.asarray(self.input_weight).shape[0]))
        object.__setattr__(self, "output_weight", _spd(self.output_weight, "output_weight", np.asarray(self.output_weight).shape[0]))

    @property
    def input_dim(self) -> int:
        return int(self.input_weight.shape[0])

    @property
    def output_dim(self) -> int:
        return int(self.output_weight.shape[0])

    def input_norm(self, dx: ArrayLike) -> float:
        vec = as_vector(dx, "dx")
        if vec.size != self.input_dim:
            raise ValueError("dx does not match the input metric")
        return float(np.sqrt(vec @ self.input_weight @ vec))

    def output_norm(self, dy: ArrayLike) -> float:
        vec = as_vector(dy, "dy")
        if vec.size != self.output_dim:
            raise ValueError("dy does not match the output metric")
        return float(np.sqrt(vec @ self.output_weight @ vec))

    def scale_jacobian(self, jacobian: ArrayLike) -> Array:
        """Return ``W_y^{1/2} J W_x^{-1/2}``."""
        jac = np.asarray(jacobian, dtype=float)
        if jac.shape != (self.output_dim, self.input_dim):
            raise ValueError(f"J shape {jac.shape} incompatible with metric {self.output_dim}x{self.input_dim}")
        return _whitener(self.output_weight) @ jac @ _unwhitener(self.input_weight)

    def operator_gain(self, jacobian: ArrayLike) -> float:
        """2-norm of the scaled Jacobian. Requires a declared metric."""
        scaled = self.scale_jacobian(jacobian)
        return float(np.linalg.norm(scaled, ord=2))

    def push(self, coordinates: AffineCoordinates) -> DeclaredMetric:
        """Metric in primed coordinates so physical lengths are unchanged."""
        if coordinates.T.shape[0] != self.input_dim or coordinates.S.shape[0] != self.output_dim:
            raise ValueError("coordinate dimensions do not match the metric")
        t_inv = coordinates.T_inv
        s_inv = coordinates.S_inv
        return DeclaredMetric(
            name=f"{self.name}[{coordinates.name}]",
            input_weight=t_inv.T @ self.input_weight @ t_inv,
            output_weight=s_inv.T @ self.output_weight @ s_inv,
        )
