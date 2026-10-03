"""Affine charts and the induced Jacobian and covariance laws."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

from .covariance import _require_psd
from .models import DifferentiableModel, as_vector

Array = NDArray[np.floating]

MAX_CONDITION_NUMBER = 1e12
ROUND_TRIP_TOLERANCE = 1e-8


def _require_chart(matrix: ArrayLike, name: str) -> Array:
    value = np.asarray(matrix, dtype=float)
    if value.ndim != 2 or value.shape[0] != value.shape[1] or value.shape[0] == 0:
        raise ValueError(f"{name} must be a nonempty square matrix")
    if not np.all(np.isfinite(value)):
        raise ValueError(f"{name} must contain finite numbers")
    try:
        condition = float(np.linalg.cond(value))
    except np.linalg.LinAlgError as exc:
        raise ValueError(f"{name} condition could not be resolved") from exc
    if not np.isfinite(condition) or condition > MAX_CONDITION_NUMBER:
        raise ValueError(f"{name} must be invertible with condition number <= 1e12")
    identity = np.eye(value.shape[0])
    recovered = np.linalg.solve(value, value @ identity)
    if float(np.max(np.abs(recovered - identity))) > ROUND_TRIP_TOLERANCE:
        raise ValueError(f"{name} loses precision in the coordinate round trip")
    return value


def skeel_condition(matrix: ArrayLike) -> float:
    """Componentwise Skeel condition || |A^{-1}| |A| ||_inf."""
    value = np.asarray(matrix, dtype=float)
    inverse = np.linalg.inv(value)
    return float(np.linalg.norm(np.abs(inverse) @ np.abs(value), ord=np.inf))


def check_mean_fidelity(reference, recovered, covariance, name: str) -> None:
    ref = as_vector(reference, name)
    rec = as_vector(recovered, f"round-trip {name}")
    if rec.shape != ref.shape:
        raise ValueError(f"{name} round-trip changed dimension")
    cov = np.asarray(covariance, dtype=float)
    scales = np.maximum(np.abs(ref), np.sqrt(np.maximum(np.diag(cov), 0.0)))
    positive = scales > 0
    if np.any(rec[~positive] != ref[~positive]):
        raise ValueError(f"{name} loses precision in the coordinate round trip (tolerance 1e-8)")
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        error = np.abs((rec[positive] - ref[positive]) / scales[positive])
    if not np.all(np.isfinite(error)) or np.any(error > ROUND_TRIP_TOLERANCE):
        raise ValueError(f"{name} loses precision in the coordinate round trip (tolerance 1e-8)")


def check_covariance_fidelity(reference, recovered, name: str) -> None:
    ref = np.asarray(reference, dtype=float)
    rec = np.asarray(recovered, dtype=float)
    if rec.shape != ref.shape:
        raise ValueError(f"{name} round-trip changed shape")
    positive = np.diag(ref) > 0.0
    if np.any(rec[~positive, :] != 0.0) or np.any(rec[:, ~positive] != 0.0):
        raise ValueError(f"{name} creates uncertainty in an exact zero direction during the coordinate round trip")
    if not np.any(positive):
        return
    scales = np.sqrt(np.diag(ref)[positive])
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        error = (rec[np.ix_(positive, positive)] - ref[np.ix_(positive, positive)]) / scales[:, None] / scales[None, :]
    if not np.all(np.isfinite(error)) or np.any(np.abs(error) > ROUND_TRIP_TOLERANCE):
        raise ValueError(f"{name} loses precision in the coordinate round trip (tolerance 1e-8)")


def push_covariance(chart, covariance, *, inverse: bool = False, name: str = "covariance"):
    t = _require_chart(chart, "chart")
    cov = _require_psd(np.asarray(covariance, dtype=float), name)
    if t.shape != cov.shape:
        raise ValueError(f"{name} does not match the chart")
    with np.errstate(over="ignore", invalid="ignore"):
        if inverse:
            left = np.linalg.solve(t, cov)
            mapped = np.linalg.solve(t, left.T).T
        else:
            mapped = t @ cov @ t.T
        mapped = 0.5 * mapped + 0.5 * mapped.T
        recovered = t @ mapped @ t.T if inverse else np.linalg.solve(t, np.linalg.solve(t, mapped).T).T
    check_covariance_fidelity(cov, recovered, name)
    return _require_psd(mapped, name)


@dataclass(frozen=True)
class AffineCoordinates:
    T: Array
    S: Array
    name: str = "coordinates"
    input_offset: Array | None = None
    output_offset: Array | None = None

    def __post_init__(self) -> None:
        t = _require_chart(self.T, "T")
        s = _require_chart(self.S, "S")
        object.__setattr__(self, "T", t)
        object.__setattr__(self, "S", s)
        cin = np.zeros(t.shape[0]) if self.input_offset is None else as_vector(self.input_offset, "input_offset")
        cout = np.zeros(s.shape[0]) if self.output_offset is None else as_vector(self.output_offset, "output_offset")
        if cin.size != t.shape[0] or cout.size != s.shape[0]:
            raise ValueError("offsets must match T and S")
        object.__setattr__(self, "input_offset", cin)
        object.__setattr__(self, "output_offset", cout)

    @property
    def T_inv(self) -> Array:
        return np.linalg.solve(self.T, np.eye(self.T.shape[0]))

    @property
    def S_inv(self) -> Array:
        return np.linalg.solve(self.S, np.eye(self.S.shape[0]))

    @property
    def T_condition(self) -> float:
        return float(np.linalg.cond(self.T))

    @property
    def S_condition(self) -> float:
        return float(np.linalg.cond(self.S))

    @property
    def T_skeel(self) -> float:
        return skeel_condition(self.T)

    @property
    def S_skeel(self) -> float:
        return skeel_condition(self.S)

    @classmethod
    def scale(cls, input_scales, output_scales, name: str = "units"):
        tin = np.asarray(input_scales, dtype=float)
        tout = np.asarray(output_scales, dtype=float)
        if np.any(tin == 0.0) or np.any(tout == 0.0):
            raise ValueError("scale factors must be nonzero")
        return cls(T=np.diag(tin), S=np.diag(tout), name=name)

    @classmethod
    def permutation(cls, input_order, output_order, name: str = "permutation"):
        inp = np.asarray(input_order, dtype=int)
        out = np.asarray(output_order, dtype=int)
        return cls(T=np.eye(inp.size)[inp], S=np.eye(out.size)[out], name=name)


def transform_jacobian(jacobian, coordinates: AffineCoordinates):
    jac = np.asarray(jacobian, dtype=float)
    if jac.shape != (coordinates.S.shape[0], coordinates.T.shape[0]):
        raise ValueError("J incompatible with S and T")
    return coordinates.S @ jac @ coordinates.T_inv


def apply_input_map(x, coordinates: AffineCoordinates):
    return coordinates.T @ as_vector(x, "x") + coordinates.input_offset


def apply_output_map(y, coordinates: AffineCoordinates):
    return coordinates.S @ as_vector(y, "y") + coordinates.output_offset


def invert_input_map(xp, coordinates: AffineCoordinates):
    return coordinates.T_inv @ (as_vector(xp, "x'") - coordinates.input_offset)


def invert_output_map(yp, coordinates: AffineCoordinates):
    return coordinates.S_inv @ (as_vector(yp, "y'") - coordinates.output_offset)


def transform_model(model: DifferentiableModel, coordinates: AffineCoordinates, *, name=None):
    if coordinates.T.shape[0] != model.input_dim or coordinates.S.shape[0] != model.output_dim:
        raise ValueError("chart does not match model dimensions")

    def forward(xp):
        return apply_output_map(model.evaluate(invert_input_map(xp, coordinates)), coordinates)

    jac_fn = None
    if model.jacobian is not None:

        def jac_fn(xp):
            return transform_jacobian(model.analytical_jacobian(invert_input_map(xp, coordinates)), coordinates)

    return DifferentiableModel(
        name=name or f"{model.name}[{coordinates.name}]",
        forward=forward,
        input_dim=model.input_dim,
        output_dim=model.output_dim,
        jacobian=jac_fn,
        notes=f"re-expressed under {coordinates.name}",
        tags=model.tags + ("transformed",),
    )
