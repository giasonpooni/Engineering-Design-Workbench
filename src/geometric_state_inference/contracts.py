# SPDX-License-Identifier: MPL-2.0
"""Validated numerical contracts for a bounded state-estimation instrument."""

from dataclasses import dataclass
from typing import Any

import numpy as np


def _identifier(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonblank string")
    return value


def _time(value: float) -> float:
    value = float(value)
    if not np.isfinite(value):
        raise ValueError("time must be finite")
    return value


def _array(value: Any, name: str, ndim: int) -> np.ndarray:
    if np.iscomplexobj(value):
        raise ValueError(f"{name} must be real-valued")
    result = np.array(value, dtype=float, copy=True)
    if result.ndim != ndim or any(size == 0 for size in result.shape):
        raise ValueError(f"{name} must be a nonempty {ndim}-dimensional array")
    if not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must contain only finite values")
    result.setflags(write=False)
    return result


def _symmetric_average(value: np.ndarray) -> np.ndarray:
    # Halve before adding to avoid overflow, but preserve equal entries exactly
    # so minimum-subnormal component variances are not halved into zero.
    result = value * 0.5 + value.T * 0.5
    np.copyto(result, value, where=value == value.T)
    return result


def _covariance(value: Any, size: int, name: str = "covariance") -> np.ndarray:
    """Validate in correlation coordinates so mixed units cannot hide failure.

    Negative component variances and nonzero covariance with a zero-variance
    component are always rejected. Symmetry tolerance is 64 * eps * dimension
    in correlation coordinates; the PSD eigenvalue tolerance additionally
    scales with the correlation matrix spectral radius.
    """
    result = _array(value, name, 2)
    if result.shape != (size, size):
        raise ValueError(f"{name} must have shape {(size, size)}")
    diagonal = np.diag(result)
    if np.any(diagonal < 0):
        raise ValueError(f"{name} must have nonnegative component variances")
    zero_variance = diagonal == 0
    if np.any(result[zero_variance, :] != 0) or np.any(result[:, zero_variance] != 0):
        raise ValueError(f"{name} zero-variance components must have zero covariance rows and columns")
    positive = diagonal > 0
    if np.any(positive):
        standard_deviations = np.sqrt(diagonal[positive])
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            correlation = (result[np.ix_(positive, positive)] / standard_deviations[:, None]
                           / standard_deviations[None, :])
        if not np.all(np.isfinite(correlation)):
            raise ValueError(f"{name} must have finite normalized correlations")
        tolerance = 64 * np.finfo(float).eps * size
        if np.max(np.abs(correlation)) > 1 + tolerance:
            raise ValueError(f"{name} must be positive semidefinite")
        if np.max(np.abs(correlation - correlation.T)) > tolerance:
            raise ValueError(f"{name} must be symmetric")
        correlation = _symmetric_average(correlation)
        eigenvalues = np.linalg.eigvalsh(correlation)
        tolerance *= float(np.max(np.abs(eigenvalues)))
        if eigenvalues[0] < -tolerance:
            raise ValueError(f"{name} must be positive semidefinite")
    result = _symmetric_average(result)
    result.setflags(write=False)
    return result


def _units(value: tuple[str, ...], size: int) -> tuple[str, ...]:
    if isinstance(value, str):
        raise ValueError("units must be a sequence of unit labels, not one string")
    result = tuple(value)
    if len(result) != size:
        raise ValueError(f"units must contain {size} labels")
    for item in result:
        _identifier(item, "unit label")
    return result


def _references(value: tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(value, str):
        raise ValueError("evidence_refs must be a sequence of references")
    result = tuple(value)
    if not result:
        raise ValueError("at least one evidence reference is required")
    for item in result:
        _identifier(item, "evidence reference")
    return result


@dataclass(frozen=True)
class StatePrior:
    """State mean and covariance in an explicitly named coordinate frame."""

    time: float
    mean: np.ndarray
    covariance: np.ndarray
    frame_id: str
    units: tuple[str, ...]
    state_id: str
    dynamics_model_id: str | None = None

    def __post_init__(self) -> None:
        mean = _array(self.mean, "mean", 1)
        object.__setattr__(self, "time", _time(self.time))
        object.__setattr__(self, "mean", mean)
        object.__setattr__(self, "covariance", _covariance(self.covariance, mean.size))
        object.__setattr__(self, "frame_id", _identifier(self.frame_id, "frame_id"))
        object.__setattr__(self, "units", _units(self.units, mean.size))
        object.__setattr__(self, "state_id", _identifier(self.state_id, "state_id"))
        if self.dynamics_model_id is not None:
            _identifier(self.dynamics_model_id, "dynamics_model_id")


@dataclass(frozen=True)
class Observation:
    """One timestamped measurement vector with externally supplied evidence refs."""

    time: float
    values: np.ndarray
    covariance: np.ndarray
    frame_id: str
    units: tuple[str, ...]
    observation_id: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        values = _array(self.values, "values", 1)
        object.__setattr__(self, "time", _time(self.time))
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "covariance", _covariance(self.covariance, values.size))
        object.__setattr__(self, "frame_id", _identifier(self.frame_id, "frame_id"))
        object.__setattr__(self, "units", _units(self.units, values.size))
        object.__setattr__(self, "observation_id", _identifier(self.observation_id, "observation_id"))
        object.__setattr__(self, "evidence_refs", _references(self.evidence_refs))


@dataclass(frozen=True)
class LinearDynamics:
    """Caller supplies F and Q discretized for the requested propagation interval."""

    matrix: np.ndarray
    process_covariance: np.ndarray
    model_id: str

    def __post_init__(self) -> None:
        matrix = _array(self.matrix, "dynamics matrix", 2)
        if matrix.shape[0] != matrix.shape[1]:
            raise ValueError("dynamics matrix must be square")
        object.__setattr__(self, "matrix", matrix)
        object.__setattr__(self, "process_covariance", _covariance(
            self.process_covariance, matrix.shape[0], "process covariance"))
        _identifier(self.model_id, "model_id")


@dataclass(frozen=True)
class LinearObservation:
    """Known observation matrix H and optional scalar-angle residual geometry.

    Unit labels are exact metadata, not an automatic unit-conversion system.
    When measurement_units is omitted, the state unit tuple is used. A map
    changing the vector dimension therefore requires explicit measurement units.
    """

    matrix: np.ndarray
    model_id: str
    measurement_geometry: Any = None
    measurement_units: tuple[str, ...] | None = None
    measurement_frame_id: str | None = None

    def __post_init__(self) -> None:
        matrix = _array(self.matrix, "observation matrix", 2)
        object.__setattr__(self, "matrix", matrix)
        _identifier(self.model_id, "model_id")
        if self.measurement_units is not None:
            object.__setattr__(self, "measurement_units", _units(
                self.measurement_units, matrix.shape[0]))
        if self.measurement_frame_id is not None:
            _identifier(self.measurement_frame_id, "measurement_frame_id")


@dataclass(frozen=True)
class Estimate:
    """Numerical result; supplied identities are not verification or authority."""

    time: float
    mean: np.ndarray
    covariance: np.ndarray
    frame_id: str
    units: tuple[str, ...]
    innovation: np.ndarray
    innovation_covariance: np.ndarray
    residual: np.ndarray
    nis: float
    observation_id: str
    evidence_refs: tuple[str, ...]
    observation_model_id: str
    dynamics_model_id: str | None
    prior_state_id: str

    def __post_init__(self) -> None:
        state = StatePrior(self.time, self.mean, self.covariance, self.frame_id,
                           self.units, self.prior_state_id, self.dynamics_model_id)
        for name in ("time", "mean", "covariance", "frame_id", "units"):
            object.__setattr__(self, name, getattr(state, name))
        innovation = _array(self.innovation, "innovation", 1)
        residual = _array(self.residual, "residual", 1)
        if residual.shape != innovation.shape:
            raise ValueError("residual and innovation dimensions must match")
        object.__setattr__(self, "innovation", innovation)
        object.__setattr__(self, "residual", residual)
        object.__setattr__(self, "innovation_covariance", _covariance(
            self.innovation_covariance, innovation.size, "innovation covariance"))
        nis = float(self.nis)
        if not np.isfinite(nis) or nis < 0:
            raise ValueError("nis must be finite and nonnegative")
        object.__setattr__(self, "nis", nis)
        object.__setattr__(self, "evidence_refs", _references(self.evidence_refs))
        _identifier(self.observation_id, "observation_id")
        _identifier(self.observation_model_id, "observation_model_id")

    def as_prior(self, state_id: str) -> StatePrior:
        """Caller explicitly assigns the next state identity for sequential replay."""
        return StatePrior(self.time, self.mean, self.covariance, self.frame_id,
                          self.units, state_id, self.dynamics_model_id)
