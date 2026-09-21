# SPDX-License-Identifier: MPL-2.0
"""Deterministic numerical primitives for residual anomaly diagnostics."""

from dataclasses import dataclass
from numbers import Real
from typing import Literal, Sequence

import numpy as np
from numpy.typing import ArrayLike

Status = Literal["nominal", "statistical_anomaly"]
Direction = Literal["positive", "negative", "two_sided"]


def _number(value: Real, name: str, *, positive: bool = False,
            nonnegative: bool = False) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a real number")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} is outside float64 range") from exc
    if not np.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if positive and result <= 0:
        raise ValueError(f"{name} must be positive")
    if nonnegative and result < 0:
        raise ValueError(f"{name} must be nonnegative")
    return result


def _labels(value: Sequence[str], name: str, length: int | None = None) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)):
        raise ValueError(f"{name} must be a sequence of distinct nonempty strings")
    try:
        result = tuple(value)
    except TypeError as exc:
        raise ValueError(f"{name} must be a sequence") from exc
    if not result or any(not isinstance(item, str) or not item.strip() for item in result):
        raise ValueError(f"{name} must contain nonempty strings")
    if len(set(result)) != len(result):
        raise ValueError(f"{name} must contain distinct strings")
    if length is not None and len(result) != length:
        raise ValueError(f"{name} length must match residual dimension")
    return result


def _array(value: ArrayLike, name: str) -> np.ndarray:
    try:
        raw = np.asarray(value)
        if raw.dtype.kind not in "iuf":
            raise ValueError(f"{name} must contain real numeric values")
        result = np.array(raw, dtype=np.float64, copy=True)
    except (TypeError, OverflowError, ValueError) as exc:
        raise ValueError(f"{name} must contain real numeric values") from exc
    if not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must be finite")
    return result


@dataclass(frozen=True)
class ResidualDiagnostics:
    raw_residual: tuple[float, ...]
    innovation_covariance: tuple[tuple[float, ...], ...]
    variable_order: tuple[str, ...]
    source_ids: tuple[str, ...]
    marginal_normalized_residual: tuple[float, ...]
    whitened_residual: tuple[float, ...]
    nis: float
    threshold: float
    status: Status


def evaluate_residual(
    residual: ArrayLike,
    innovation_covariance: ArrayLike,
    *,
    threshold: float,
    variable_order: Sequence[str],
    source_ids: Sequence[str],
) -> ResidualDiagnostics:
    """Evaluate NIS against an explicit caller threshold using a Cholesky solve.

    Residual coordinates and covariance rows/columns share ``variable_order``.
    Covariance must be exactly symmetric and strictly positive definite.
    A threshold equality is an anomaly. No probability is inferred.
    """
    limit = _number(threshold, "threshold", positive=True)
    raw = _array(residual, "residual")
    if raw.ndim != 1 or raw.size == 0:
        raise ValueError("residual must be a nonempty one-dimensional vector")
    labels = _labels(variable_order, "variable_order", raw.size)
    sources = _labels(source_ids, "source_ids")
    covariance = _array(innovation_covariance, "innovation_covariance")
    if covariance.shape != (raw.size, raw.size):
        raise ValueError("innovation_covariance must have shape (n, n)")
    # No absolute tolerance: tiny-scale asymmetric or indefinite matrices must
    # not be silently accepted. Any symmetrization is a separate caller action.
    if not np.array_equal(covariance, covariance.T):
        raise ValueError("innovation_covariance must be exactly symmetric")
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            lower = np.linalg.cholesky(covariance)
            whitened = np.linalg.solve(lower, raw)
            normalized = raw / np.sqrt(np.diag(covariance))
            nis = float(whitened @ whitened)
    except np.linalg.LinAlgError as exc:
        raise ValueError("innovation_covariance must be strictly positive definite") from exc
    except FloatingPointError as exc:
        raise ValueError("diagnostic calculation exceeds float64 range") from exc
    if not np.all(np.isfinite(whitened)) or not np.all(np.isfinite(normalized)) or not np.isfinite(nis):
        raise ValueError("diagnostic calculation exceeds float64 range")
    return ResidualDiagnostics(
        raw_residual=tuple(float(x) for x in raw),
        innovation_covariance=tuple(tuple(float(x) for x in row) for row in covariance),
        variable_order=labels,
        source_ids=sources,
        marginal_normalized_residual=tuple(float(x) for x in normalized),
        whitened_residual=tuple(float(x) for x in whitened),
        nis=nis,
        threshold=limit,
        status="statistical_anomaly" if nis >= limit else "nominal",
    )


@dataclass(frozen=True)
class CusumState:
    """Nonnegative accumulators; count is the number of processed samples."""

    positive: float = 0.0
    negative: float = 0.0
    sample_count: int = 0


@dataclass(frozen=True)
class CusumResult:
    raw_value: float
    source_ids: tuple[str, ...]
    drift: float
    threshold: float
    direction: Direction
    reset_on_alarm: bool
    prior_state: CusumState
    observed_state: CusumState
    next_state: CusumState
    alarm_sides: tuple[str, ...]
    status: Status


def cusum_step(
    value: float,
    prior_state: CusumState,
    *,
    drift: float,
    threshold: float,
    direction: Direction,
    source_ids: Sequence[str],
    reset_on_alarm: bool = False,
) -> CusumResult:
    """Pure one-sample CUSUM transition for an explicitly chosen scalar stream.

    Positive channel: max(0, positive + value - drift).
    Negative channel: max(0, negative - value - drift).
    Threshold equality emits an anomaly. Optional reset happens after reporting
    observed accumulators; it clears both accumulators but preserves count.
    """
    sample = _number(value, "value")
    allowance = _number(drift, "drift", nonnegative=True)
    limit = _number(threshold, "threshold", positive=True)
    sources = _labels(source_ids, "source_ids")
    if direction not in ("positive", "negative", "two_sided"):
        raise ValueError("direction must be positive, negative, or two_sided")
    if not isinstance(reset_on_alarm, bool):
        raise ValueError("reset_on_alarm must be boolean")
    if not isinstance(prior_state, CusumState):
        raise ValueError("prior_state must be CusumState")
    previous_positive = _number(prior_state.positive, "prior_state.positive", nonnegative=True)
    previous_negative = _number(prior_state.negative, "prior_state.negative", nonnegative=True)
    if isinstance(prior_state.sample_count, bool) or not isinstance(prior_state.sample_count, int) or prior_state.sample_count < 0:
        raise ValueError("prior_state.sample_count must be a nonnegative integer")
    if direction == "positive" and previous_negative != 0:
        raise ValueError("positive-only CUSUM requires zero negative accumulator")
    if direction == "negative" and previous_positive != 0:
        raise ValueError("negative-only CUSUM requires zero positive accumulator")
    positive = 0.0
    negative = 0.0
    if direction != "negative":
        intermediate = previous_positive + sample - allowance
        if not np.isfinite(intermediate):
            raise ValueError("positive CUSUM calculation exceeds float64 range")
        positive = max(0.0, intermediate)
    if direction != "positive":
        intermediate = previous_negative - sample - allowance
        if not np.isfinite(intermediate):
            raise ValueError("negative CUSUM calculation exceeds float64 range")
        negative = max(0.0, intermediate)
    observed = CusumState(positive, negative, prior_state.sample_count + 1)
    alarm_sides = tuple(name for name, accumulator in (("positive", positive), ("negative", negative)) if accumulator >= limit)
    next_state = CusumState(sample_count=observed.sample_count) if alarm_sides and reset_on_alarm else observed
    return CusumResult(
        raw_value=sample,
        source_ids=sources,
        drift=allowance,
        threshold=limit,
        direction=direction,
        reset_on_alarm=reset_on_alarm,
        prior_state=prior_state,
        observed_state=observed,
        next_state=next_state,
        alarm_sides=alarm_sides,
        status="statistical_anomaly" if alarm_sides else "nominal",
    )
