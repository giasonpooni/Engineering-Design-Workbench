"""An affine, explicitly anchored clock model with first-order uncertainty."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence
import numpy as np
from numpy.typing import ArrayLike


_EPS = np.finfo(float).eps


def _label(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")


def _labels(values: Sequence[str], name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{name} must be a sequence of distinct nonempty strings")
    try:
        result = tuple(values)
    except TypeError as exc:
        raise ValueError(f"{name} must be a sequence of distinct nonempty strings") from exc
    for value in result:
        _label(value, name)
    if len(set(result)) != len(result):
        raise ValueError(f"{name} must contain distinct values")
    return result


def _finite(value: float, name: str) -> float:
    if isinstance(value, (bool, np.bool_, str, bytes)) or np.iscomplexobj(value):
        raise ValueError(f"{name} must be a finite real number")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite real number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


@dataclass(frozen=True)
class ClockFrame:
    """Clock, time-scale and unit identity. This version accepts seconds only."""

    clock_id: str
    time_scale: str
    unit: str = "s"

    def __post_init__(self) -> None:
        _label(self.clock_id, "clock_id")
        _label(self.time_scale, "time_scale")
        if self.unit != "s":
            raise ValueError("only unit='s' is supported; convert upstream explicitly")


@dataclass(frozen=True)
class TimePoint:
    """A scalar instant with explicit frame, suitable for receipt/knowledge metadata."""

    value: float
    frame: ClockFrame

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _finite(self.value, "time value"))
        if not isinstance(self.frame, ClockFrame):
            raise ValueError("frame must be a ClockFrame")


@dataclass(frozen=True)
class TimestampObservation:
    """Source event timestamp; receipt and knowledge instants stay separate."""

    device_time: float
    frame: ClockFrame
    evidence_id: str
    received_at: TimePoint | None = None
    known_at: TimePoint | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "device_time", _finite(self.device_time, "device_time"))
        if not isinstance(self.frame, ClockFrame):
            raise ValueError("frame must be a ClockFrame")
        _label(self.evidence_id, "evidence_id")
        for name in ("received_at", "known_at"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, TimePoint):
                raise ValueError(f"{name} must be a TimePoint or None")


@dataclass(frozen=True)
class AffineClockModel:
    """Supplied clock map and inclusive applicability interval in source seconds."""

    model_id: str
    source_frame: ClockFrame
    reference_frame: ClockFrame
    device_origin: float
    reference_origin: float
    skew: float
    offset: float
    valid_device_interval: tuple[float, float]
    synchronization_evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _label(self.model_id, "model_id")
        if not isinstance(self.source_frame, ClockFrame) or not isinstance(
            self.reference_frame, ClockFrame
        ):
            raise ValueError("source_frame and reference_frame must be ClockFrames")
        for name in ("device_origin", "reference_origin", "skew", "offset"):
            object.__setattr__(self, name, _finite(getattr(self, name), name))
        if self.skew <= 0:
            raise ValueError("skew must be positive to preserve clock order")
        try:
            lower, upper = self.valid_device_interval
        except (TypeError, ValueError) as exc:
            raise ValueError("valid_device_interval must contain two bounds") from exc
        lower = _finite(lower, "lower applicability bound")
        upper = _finite(upper, "upper applicability bound")
        if lower > upper:
            raise ValueError("valid_device_interval bounds must be ordered")
        object.__setattr__(self, "valid_device_interval", (lower, upper))
        object.__setattr__(self, "synchronization_evidence_ids", _labels(
            self.synchronization_evidence_ids, "synchronization_evidence_ids",
        ))


@dataclass(frozen=True)
class ReconciledTimestamp:
    """Derived event coordinate with original observation and model retained."""

    observation: TimestampObservation
    model: AffineClockModel
    event_time_delta: float
    variance: float
    jacobian: tuple[float, float, float]
    joint_covariance: tuple[tuple[float, ...], ...]
    propagation: str = "first-order.v1"
    operation_id: str = "tbrt.affine-clock-reconcile.v1"

    @property
    def reference_origin(self) -> float:
        return self.model.reference_origin

    @property
    def reference_frame(self) -> ClockFrame:
        return self.model.reference_frame

    @property
    def event_time(self) -> float:
        """Rounded scalar convenience value; retain origin/delta for precision."""
        return self.reference_origin + self.event_time_delta

    @property
    def standard_uncertainty(self) -> float:
        return math.sqrt(self.variance)


def _covariance(value: ArrayLike) -> np.ndarray:
    """Copy and validate mixed-unit covariance using normalized correlation PSD."""
    if np.iscomplexobj(value):
        raise ValueError("joint_covariance must be real")
    try:
        supplied = np.asarray(value, dtype=object)
        if supplied.shape != (3, 3):
            raise ValueError("joint_covariance must be a real 3 by 3 matrix")
        covariance = np.array(
            [_finite(x, "joint_covariance entry") for x in supplied.flat]
        ).reshape(3, 3)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("joint_covariance must be a real 3 by 3 matrix") from exc
    if covariance.shape != (3, 3) or not np.isfinite(covariance).all():
        raise ValueError("joint_covariance must be a finite 3 by 3 matrix")
    if not np.array_equal(covariance, covariance.T):
        raise ValueError("joint_covariance must be exactly symmetric; no repair is applied")
    diagonal = np.diag(covariance)
    if np.any(diagonal < 0):
        raise ValueError("joint_covariance must have nonnegative diagonal")
    positive = diagonal > 0
    if np.any(covariance[~positive, :] != 0):
        raise ValueError("joint_covariance: zero variance requires zero associated covariance")
    if np.any(positive):
        deviations = np.sqrt(diagonal[positive])
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            larger = np.maximum(deviations[:, None], deviations[None, :])
            smaller = np.minimum(deviations[:, None], deviations[None, :])
            correlation = covariance[np.ix_(positive, positive)] / larger / smaller
        if not np.isfinite(correlation).all():
            raise ValueError("joint_covariance normalization overflowed")
        if np.any(np.abs(correlation) > 1 + 64 * _EPS):
            raise ValueError("joint_covariance violates covariance bounds")
        try:
            smallest = np.linalg.eigvalsh(correlation)[0]
        except np.linalg.LinAlgError as exc:
            raise ValueError("joint_covariance PSD check failed") from exc
        if smallest < -64 * _EPS * len(correlation):
            raise ValueError("joint_covariance must be positive semidefinite")
    return covariance


def reconcile_time(
    observation: TimestampObservation,
    model: AffineClockModel,
    joint_covariance: ArrayLike,
    *,
    expected_reference: ClockFrame | None = None,
    require_synchronization_evidence: bool = False,
) -> ReconciledTimestamp:
    """Map an event using covariance ordered [device_time, skew, offset].

    The origins are fixed constants. The returned variance is J C J.T with
    J = [skew, device_time-device_origin, 1]. All correlation terms survive.
    Receipt/knowledge instants are metadata and never enter the calculation.
    This does not convert UTC leap seconds or certify synchronization evidence.
    """
    if not isinstance(observation, TimestampObservation):
        raise ValueError("observation must be a TimestampObservation")
    if not isinstance(model, AffineClockModel):
        raise ValueError("model must be an AffineClockModel")
    if not isinstance(require_synchronization_evidence, bool):
        raise ValueError("require_synchronization_evidence must be boolean")
    if require_synchronization_evidence and not model.synchronization_evidence_ids:
        raise ValueError("synchronization evidence is required; clock mapping refused")
    if observation.frame != model.source_frame:
        raise ValueError("observation clock/time-scale/unit differs from model source")
    if expected_reference is not None and expected_reference != model.reference_frame:
        raise ValueError("model reference frame differs from expected reference")
    lower, upper = model.valid_device_interval
    if not lower <= observation.device_time <= upper:
        raise ValueError("timestamp falls outside model applicability; extrapolation refused")
    covariance = _covariance(joint_covariance)
    elapsed = observation.device_time - model.device_origin
    delta = model.skew * elapsed + model.offset
    if not math.isfinite(elapsed) or not math.isfinite(delta):
        raise ValueError("affine clock arithmetic produced a nonfinite value")
    if not math.isfinite(model.reference_origin + delta):
        raise ValueError("reference event time overflows binary64")
    jacobian = np.array([model.skew, elapsed, 1.0])
    # Sum explicitly: fsum reduces cancellation in correlated uncertainty terms.
    with np.errstate(over="ignore", invalid="ignore"):
        terms = jacobian[:, None] * covariance * jacobian[None, :]
    if not np.isfinite(terms).all():
        raise ValueError("uncertainty propagation overflowed")
    try:
        variance = math.fsum(terms.flat)
    except (OverflowError, ValueError) as exc:
        raise ValueError("uncertainty propagation overflowed") from exc
    if not math.isfinite(variance):
        raise ValueError("uncertainty propagation overflowed")
    if variance < 0:
        raise ValueError("uncertainty propagation produced a negative variance")
    return ReconciledTimestamp(
        observation=observation,
        model=model,
        event_time_delta=delta,
        variance=variance,
        jacobian=tuple(float(x) for x in jacobian),
        joint_covariance=tuple(tuple(float(x) for x in row) for row in covariance),
    )


def replay_reconciliation(result: ReconciledTimestamp) -> ReconciledTimestamp:
    """Recompute a retained typed reconciliation without reading wall-clock state.

    The result contains the untouched source observation, affine map, ordered
    covariance and applicability interval required for deterministic replay.
    A replay does not authenticate the retained synchronization evidence.
    """
    if not isinstance(result, ReconciledTimestamp):
        raise ValueError("result must be a ReconciledTimestamp")
    replayed = reconcile_time(
        result.observation,
        result.model,
        result.joint_covariance,
        expected_reference=result.reference_frame,
        require_synchronization_evidence=bool(result.model.synchronization_evidence_ids),
    )
    if replayed != result:
        raise ValueError("retained reconciliation does not match deterministic replay")
    return replayed
