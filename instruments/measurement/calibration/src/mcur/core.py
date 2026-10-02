"""Affine calibration with explicit applicability and joint uncertainty."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from fractions import Fraction
from itertools import combinations
from math import isfinite, sqrt
from numbers import Real
from typing import Iterable

import numpy as np

Matrix2 = tuple[tuple[float, float], tuple[float, float]]
Matrix3 = tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]


class CalibrationError(ValueError):
    """An input, applicability condition, or numerical condition is invalid."""


def _identifier(value: str, name: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise CalibrationError(f"{name} must be a nonempty, unpadded string")


def _finite(value: Real, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise CalibrationError(f"{name} must be a real number")
    try:
        result = float(value)
    except (ValueError, OverflowError) as exc:
        raise CalibrationError(f"{name} cannot be represented as binary64") from exc
    if not isfinite(result):
        raise CalibrationError(f"{name} must be finite")
    return result


def _aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise CalibrationError(f"{name} must be a timezone-aware datetime")


def _utc(value: datetime) -> datetime:
    try:
        return value.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise CalibrationError("timestamp cannot be represented as a UTC instant") from exc


def _representable(value: Fraction, name: str) -> float:
    try:
        result = float(value)
    except OverflowError as exc:
        raise CalibrationError(f"{name} overflows binary64") from exc
    if not isfinite(result):
        raise CalibrationError(f"{name} overflows binary64")
    if result == 0.0 and value != 0:
        raise CalibrationError(f"{name} underflows binary64; rescale inputs")
    return result


def _determinant(matrix: list[list[Fraction]]) -> Fraction:
    if len(matrix) == 1:
        return matrix[0][0]
    if len(matrix) == 2:
        return matrix[0][0] * matrix[1][1] - matrix[0][1] * matrix[1][0]
    a, b, c = matrix[0]
    d, e, f = matrix[1]
    g, h, i = matrix[2]
    return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)


def _covariance(values: Iterable[Iterable[Real]], size: int, name: str) -> tuple:
    """Certify PSD for the supplied binary64 matrix, without scale tolerances."""
    try:
        array = np.asarray(values, dtype=object)
    except (ValueError, TypeError) as exc:
        raise CalibrationError(f"{name} must be a {size} by {size} matrix") from exc
    if array.shape != (size, size):
        raise CalibrationError(f"{name} must be a {size} by {size} matrix")
    result = tuple(tuple(_finite(value, name) for value in row) for row in array)
    if any(result[i][j] != result[j][i] for i in range(size) for j in range(size)):
        raise CalibrationError(f"{name} must be exactly symmetric")
    exact = [[Fraction(value) for value in row] for row in result]
    # A real symmetric matrix is PSD iff every principal minor is nonnegative.
    # Exact rational arithmetic avoids absolute tolerances and eigensolver noise.
    for order in range(1, size + 1):
        for indices in combinations(range(size), order):
            minor = [[exact[i][j] for j in indices] for i in indices]
            if _determinant(minor) < 0:
                raise CalibrationError(f"{name} must be positive semidefinite")
    return result


@dataclass(frozen=True, slots=True)
class Interval:
    minimum: float
    maximum: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "minimum", _finite(self.minimum, "minimum"))
        object.__setattr__(self, "maximum", _finite(self.maximum, "maximum"))
        if self.minimum > self.maximum:
            raise CalibrationError("interval minimum exceeds maximum")

    def contains(self, value: float) -> bool:
        return self.minimum <= value <= self.maximum


@dataclass(frozen=True, slots=True)
class EnvironmentReading:
    quantity_id: str
    unit: str
    value: float

    def __post_init__(self) -> None:
        _identifier(self.quantity_id, "environment quantity_id")
        _identifier(self.unit, "environment unit")
        object.__setattr__(self, "value", _finite(self.value, "environment value"))


@dataclass(frozen=True, slots=True)
class EnvironmentRequirement:
    quantity_id: str
    unit: str
    interval: Interval

    def __post_init__(self) -> None:
        _identifier(self.quantity_id, "environment quantity_id")
        _identifier(self.unit, "environment unit")
        if not isinstance(self.interval, Interval):
            raise CalibrationError("environment interval must be an Interval")


def _environment(items: Iterable, expected: type, name: str) -> tuple:
    result = tuple(items)
    if any(not isinstance(item, expected) for item in result):
        raise CalibrationError(f"{name} contains an invalid entry")
    keys = [item.quantity_id for item in result]
    if len(set(keys)) != len(keys):
        raise CalibrationError(f"{name} has duplicate quantity identities")
    return result


@dataclass(frozen=True, slots=True)
class Observation:
    observation_id: str
    artifact_id: str
    sensor_id: str
    quantity_id: str
    unit: str
    acquired_at: datetime
    indicated_value: float
    raw_value: float | None = None
    environment: tuple[EnvironmentReading, ...] = ()

    def __post_init__(self) -> None:
        for name in ("observation_id", "artifact_id", "sensor_id", "quantity_id", "unit"):
            _identifier(getattr(self, name), name)
        _aware(self.acquired_at, "acquired_at")
        object.__setattr__(self, "indicated_value", _finite(self.indicated_value, "indicated_value"))
        if self.raw_value is not None:
            object.__setattr__(self, "raw_value", _finite(self.raw_value, "raw_value"))
        object.__setattr__(self, "environment", _environment(self.environment, EnvironmentReading, "environment"))


@dataclass(frozen=True, slots=True)
class CalibrationProfile:
    profile_id: str
    artifact_id: str
    sensor_id: str
    quantity_id: str
    input_unit: str
    output_unit: str
    gain: float
    offset: float
    coefficient_covariance: Matrix2
    valid_from: datetime
    valid_until: datetime
    reference_ids: tuple[str, ...] = ()
    input_range: Interval | None = None
    environment_requirements: tuple[EnvironmentRequirement, ...] = ()

    def __post_init__(self) -> None:
        for name in ("profile_id", "artifact_id", "sensor_id", "quantity_id", "input_unit", "output_unit"):
            _identifier(getattr(self, name), name)
        object.__setattr__(self, "gain", _finite(self.gain, "gain"))
        object.__setattr__(self, "offset", _finite(self.offset, "offset"))
        object.__setattr__(self, "coefficient_covariance", _covariance(self.coefficient_covariance, 2, "coefficient covariance [g,b]"))
        _aware(self.valid_from, "valid_from")
        _aware(self.valid_until, "valid_until")
        if _utc(self.valid_from) >= _utc(self.valid_until):
            raise CalibrationError("valid_from must precede valid_until")
        references = tuple(self.reference_ids)
        for reference in references:
            _identifier(reference, "reference_id")
        if len(set(references)) != len(references):
            raise CalibrationError("reference_ids must be unique")
        object.__setattr__(self, "reference_ids", references)
        if self.input_range is not None and not isinstance(self.input_range, Interval):
            raise CalibrationError("input_range must be an Interval")
        object.__setattr__(self, "environment_requirements", _environment(self.environment_requirements, EnvironmentRequirement, "environment_requirements"))


class CrossCovariancePolicy(str, Enum):
    """Knowledge state for covariance between indication and coefficients."""

    DECLARED = "declared"
    DECLARED_ZERO = "declared_zero"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class JointCovariance:
    values: Matrix3
    order: tuple[str, str, str] = ("x", "g", "b")
    cross_covariance_policy: CrossCovariancePolicy = CrossCovariancePolicy.DECLARED
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if tuple(self.order) != ("x", "g", "b"):
            raise CalibrationError("joint covariance order must be ('x', 'g', 'b')")
        object.__setattr__(self, "order", ("x", "g", "b"))
        object.__setattr__(self, "values", _covariance(self.values, 3, "joint covariance [x,g,b]"))
        if not isinstance(self.cross_covariance_policy, CrossCovariancePolicy):
            raise CalibrationError("cross_covariance_policy must be a CrossCovariancePolicy")
        if isinstance(self.evidence_ids, (str, bytes)):
            raise CalibrationError("joint covariance evidence_ids must be a sequence of identities")
        try:
            evidence = tuple(self.evidence_ids)
        except TypeError as exc:
            raise CalibrationError("joint covariance evidence_ids must be a sequence of identities") from exc
        for identity in evidence:
            _identifier(identity, "joint covariance evidence_id")
        if len(set(evidence)) != len(evidence):
            raise CalibrationError("joint covariance evidence_ids must be unique")
        object.__setattr__(self, "evidence_ids", evidence)
        if self.cross_covariance_policy == CrossCovariancePolicy.DECLARED_ZERO:
            if any(self.values[0][index] != 0 or self.values[index][0] != 0 for index in (1, 2)):
                raise CalibrationError(
                    "declared_zero cross-covariance contradicts nonzero indication/coefficient terms"
                )


class ServingState(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    WITHDRAWN = "withdrawn"


@dataclass(frozen=True, slots=True)
class ServingStatus:
    """Caller-supplied status evidence; does not change acquisition-time validity."""

    record_id: str
    profile_id: str
    reported_at: datetime
    state: ServingState

    def __post_init__(self) -> None:
        _identifier(self.record_id, "serving record_id")
        _identifier(self.profile_id, "serving profile_id")
        _aware(self.reported_at, "serving reported_at")
        if not isinstance(self.state, ServingState):
            raise CalibrationError("serving state must be a ServingState")


@dataclass(frozen=True, slots=True)
class BudgetTerm:
    name: str
    variance_contribution: float


@dataclass(frozen=True, slots=True)
class CalibrationResult:
    observation_id: str
    source_artifact_id: str
    profile_id: str
    calibration_artifact_id: str
    reference_ids: tuple[str, ...]
    acquired_at: datetime
    raw_value: float | None
    indicated_value: float
    corrected_value: float
    input_unit: str
    output_unit: str
    correction_from_indication: float | None
    additive_correction: float
    jacobian: tuple[float, float, float]
    joint_covariance: JointCovariance
    variance: float
    standard_uncertainty: float
    uncertainty_budget: tuple[BudgetTerm, ...]
    serving_status: ServingStatus | None
    diagnostics: tuple[str, ...]
    operation_id: str = "mcur.affine-first-order.v1"


class FeatureCompatibilityState(str, Enum):
    COMPATIBLE = "compatible"
    VALUE_ONLY = "value_only"
    REFUSED = "refused"


@dataclass(frozen=True, slots=True)
class FeatureCompatibility:
    calibration_operation_id: str
    feature_operation_id: str
    status: FeatureCompatibilityState
    value_commutes: bool
    uncertainty_commutes: bool
    reason: str


def assess_feature_compatibility(
    profile: CalibrationProfile,
    feature_operation_id: str,
    *,
    same_profile_for_all_samples: bool,
    joint_temporal_covariance_declared: bool,
) -> FeatureCompatibility:
    """Assess the implemented affine-calibration/window-mean interchange.

    An affine map with one shared profile commutes with an arithmetic mean for
    the value. Uncertainty is only declared compatible when the full temporal
    covariance, including shared calibration-parameter effects, is supplied.
    Other feature operations remain refused rather than being guessed.
    """
    if not isinstance(profile, CalibrationProfile):
        raise CalibrationError("profile must be a CalibrationProfile")
    _identifier(feature_operation_id, "feature_operation_id")
    if not isinstance(same_profile_for_all_samples, bool):
        raise CalibrationError("same_profile_for_all_samples must be boolean")
    if not isinstance(joint_temporal_covariance_declared, bool):
        raise CalibrationError("joint_temporal_covariance_declared must be boolean")
    operation = "mcur.affine-first-order.v1"
    if feature_operation_id != "stfe.window-mean.v1":
        return FeatureCompatibility(
            operation, feature_operation_id, FeatureCompatibilityState.REFUSED,
            False, False, "feature/calibration commutation is not implemented",
        )
    if not same_profile_for_all_samples:
        return FeatureCompatibility(
            operation, feature_operation_id, FeatureCompatibilityState.REFUSED,
            False, False, "window samples do not share one affine calibration profile",
        )
    if not joint_temporal_covariance_declared:
        return FeatureCompatibility(
            operation, feature_operation_id, FeatureCompatibilityState.VALUE_ONLY,
            True, False,
            "affine values commute with a mean, but shared-parameter temporal covariance is absent",
        )
    return FeatureCompatibility(
        operation, feature_operation_id, FeatureCompatibilityState.COMPATIBLE,
        True, True,
        "one affine profile commutes with an arithmetic mean and full joint uncertainty is declared",
    )


def calibrate(
    observation: Observation,
    profile: CalibrationProfile,
    joint_covariance: JointCovariance,
    *,
    serving_status: ServingStatus | None = None,
) -> CalibrationResult:
    """Apply y=g*x+b and propagate the ordered joint covariance of [x,g,b].

    This operation provides a calibration candidate, not traceability certification,
    state admission, or authorization to use a withdrawn profile operationally.
    """
    if not isinstance(observation, Observation) or not isinstance(profile, CalibrationProfile):
        raise CalibrationError("observation and profile must be typed MCUR records")
    if not isinstance(joint_covariance, JointCovariance):
        raise CalibrationError("joint_covariance must be a JointCovariance")
    if joint_covariance.cross_covariance_policy == CrossCovariancePolicy.UNKNOWN:
        raise CalibrationError(
            "indication/coefficient cross-covariance is unknown; calibration refused"
        )
    for name in ("sensor_id", "quantity_id"):
        if getattr(observation, name) != getattr(profile, name):
            raise CalibrationError(f"{name} mismatch")
    if observation.unit != profile.input_unit:
        raise CalibrationError("input unit mismatch; no implicit unit conversion")
    if not _utc(profile.valid_from) <= _utc(observation.acquired_at) < _utc(profile.valid_until):
        raise CalibrationError("calibration is invalid at acquisition event time")
    if profile.input_range is not None and not profile.input_range.contains(observation.indicated_value):
        raise CalibrationError("indicated value is outside the calibration input range")
    readings = {item.quantity_id: item for item in observation.environment}
    for requirement in profile.environment_requirements:
        reading = readings.get(requirement.quantity_id)
        if reading is None:
            raise CalibrationError(f"missing environment reading: {requirement.quantity_id}")
        if reading.unit != requirement.unit:
            raise CalibrationError(f"environment unit mismatch: {requirement.quantity_id}")
        if not requirement.interval.contains(reading.value):
            raise CalibrationError(f"environment outside applicability: {requirement.quantity_id}")
    covariance = joint_covariance.values
    if tuple(tuple(covariance[i][j] for j in (1, 2)) for i in (1, 2)) != profile.coefficient_covariance:
        raise CalibrationError("joint covariance coefficient block differs from the calibration profile")
    if serving_status is not None:
        if not isinstance(serving_status, ServingStatus):
            raise CalibrationError("serving_status must be a ServingStatus")
        if serving_status.profile_id != profile.profile_id:
            raise CalibrationError("serving status profile_id mismatch")

    x, g, b = map(Fraction, (observation.indicated_value, profile.gain, profile.offset))
    jacobian_exact = (g, x, Fraction(1))
    exact = [[Fraction(value) for value in row] for row in covariance]
    budget_exact = (
        ("x", g * g * exact[0][0]),
        ("g", x * x * exact[1][1]),
        ("b", exact[2][2]),
        ("x:g", 2 * g * x * exact[0][1]),
        ("x:b", 2 * g * exact[0][2]),
        ("g:b", 2 * x * exact[1][2]),
    )
    variance_exact = sum((value for _, value in budget_exact), Fraction(0))
    if variance_exact < 0:  # Defensive invariant: impossible after exact PSD validation.
        raise CalibrationError("propagated variance is negative")
    variance = _representable(variance_exact, "propagated variance")
    corrected = _representable(g * x + b, "corrected value")
    same_units = profile.input_unit == profile.output_unit
    correction = _representable(g * x + b - x, "correction") if same_units else None
    diagnostics = [
        "first-order propagation in the joint uncertain inputs [x,g,b]; g*x is jointly nonlinear",
        "reference identities are supplied evidence pointers; traceability is not certified",
        "applicability checked at acquisition event time; serving status is separate",
        f"cross-covariance policy: {joint_covariance.cross_covariance_policy.value}",
    ]
    if not same_units:
        diagnostics.append("correction_from_indication is undefined for different input/output unit tokens")
    if serving_status is not None and serving_status.state != ServingState.ACTIVE:
        diagnostics.append(f"reported serving status: {serving_status.state.value}; no operational admission implied")
    return CalibrationResult(
        observation_id=observation.observation_id,
        source_artifact_id=observation.artifact_id,
        profile_id=profile.profile_id,
        calibration_artifact_id=profile.artifact_id,
        reference_ids=profile.reference_ids,
        acquired_at=observation.acquired_at,
        raw_value=observation.raw_value,
        indicated_value=observation.indicated_value,
        corrected_value=corrected,
        input_unit=profile.input_unit,
        output_unit=profile.output_unit,
        correction_from_indication=correction,
        additive_correction=profile.offset,
        jacobian=tuple(float(value) for value in jacobian_exact),
        joint_covariance=joint_covariance,
        variance=variance,
        standard_uncertainty=sqrt(variance),
        uncertainty_budget=tuple(BudgetTerm(name, _representable(value, f"budget term {name}")) for name, value in budget_exact),
        serving_status=serving_status,
        diagnostics=tuple(diagnostics),
    )
