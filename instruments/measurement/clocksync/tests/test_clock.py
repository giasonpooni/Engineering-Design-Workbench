from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from tbrt import (
    AffineClockModel,
    ClockFrame,
    TimePoint,
    TimestampObservation,
    replay_reconciliation,
    reconcile_time,
)


DEVICE = ClockFrame("sensor-17/oscillator", "device-monotonic")
REFERENCE = ClockFrame("reference-2/oscillator", "reference-monotonic")


def model(**changes):
    defaults = dict(
        model_id="synthetic-sync-model-1",
        source_frame=DEVICE,
        reference_frame=REFERENCE,
        device_origin=100.0,
        reference_origin=1_000.0,
        skew=2.0,
        offset=0.5,
        valid_device_interval=(100.0, 110.0),
        synchronization_evidence_ids=("sync-exchange:synthetic:1",),
    )
    return AffineClockModel(**(defaults | changes))


def observation(value=103.0, **changes):
    defaults = dict(device_time=value, frame=DEVICE, evidence_id="synthetic-observation-1")
    return TimestampObservation(**(defaults | changes))


def test_analytical_correlated_propagation():
    covariance = np.array([[4, 0.2, 0.1], [0.2, 0.25, -0.05], [0.1, -0.05, 1]])
    result = reconcile_time(observation(), model(), covariance)
    assert result.event_time_delta == 6.5
    assert result.event_time == 1006.5
    assert result.jacobian == (2.0, 3.0, 1.0)
    # 4*4 + 9*.25 + 1 + 2*(6*.2 + 2*.1 + 3*(-.05))
    assert result.variance == pytest.approx(21.75)
    assert result.standard_uncertainty == pytest.approx(np.sqrt(21.75))
    assert result.propagation == "first-order.v1"
    assert result.operation_id == "tbrt.affine-clock-reconcile.v1"
    assert replay_reconciliation(result) == result


def test_strict_mapping_requires_retained_synchronization_evidence():
    without_evidence = model(synchronization_evidence_ids=())
    with pytest.raises(ValueError, match="synchronization evidence.*refused"):
        reconcile_time(
            observation(), without_evidence, np.eye(3),
            require_synchronization_evidence=True,
        )
    result = reconcile_time(
        observation(), model(), np.eye(3), require_synchronization_evidence=True,
    )
    assert result.model.synchronization_evidence_ids == ("sync-exchange:synthetic:1",)


def test_synchronization_evidence_identities_are_typed_and_unique():
    with pytest.raises(ValueError, match="sequence"):
        model(synchronization_evidence_ids="not-a-sequence")
    with pytest.raises(ValueError, match="distinct"):
        model(synchronization_evidence_ids=("same", "same"))
    with pytest.raises(ValueError, match="nonempty"):
        model(synchronization_evidence_ids=("",))


def test_anchored_delta_survives_large_epoch_rounding():
    clock = model(
        device_origin=1e12,
        reference_origin=1e15,
        skew=1.0,
        offset=0.001,
        valid_device_interval=(1e12, 1e12 + 1),
    )
    result = reconcile_time(observation(1e12), clock, np.zeros((3, 3)))
    assert result.event_time_delta == 0.001
    assert result.event_time == 1e15  # scalar conversion demonstrably loses the delta
    assert result.variance == 0


def test_metadata_identity_is_preserved_and_not_used_as_event_time():
    received = TimePoint(202.0, REFERENCE)
    known = TimePoint(404.0, ClockFrame("database", "database-monotonic"))
    raw = observation(received_at=received, known_at=known)
    clock = model()
    covariance = np.eye(3)
    before = covariance.copy()
    result = reconcile_time(raw, clock, covariance)
    np.testing.assert_array_equal(covariance, before)
    assert result.observation is raw
    assert result.model is clock
    assert result.observation.device_time == 103.0
    assert result.observation.received_at is received
    assert result.observation.known_at is known
    assert result.reference_frame is REFERENCE
    covariance[:] = 0
    assert result.joint_covariance == ((1, 0, 0), (0, 1, 0), (0, 0, 1))
    with pytest.raises(FrozenInstanceError):
        result.event_time_delta = 0


@pytest.mark.parametrize("value", [100.0, 110.0])
def test_domain_endpoints_are_inclusive(value):
    assert reconcile_time(observation(value), model(), np.zeros((3, 3)))


@pytest.mark.parametrize("value", [99.999, 110.001])
def test_extrapolation_refused(value):
    with pytest.raises(ValueError, match="extrapolation refused"):
        reconcile_time(observation(value), model(), np.eye(3))


@pytest.mark.parametrize(
    "frame",
    [ClockFrame("other", "device-monotonic"), ClockFrame(DEVICE.clock_id, "TAI")],
)
def test_clock_and_time_scale_mismatches_are_rejected(frame):
    with pytest.raises(ValueError, match="differs from model source"):
        reconcile_time(observation(frame=frame), model(), np.eye(3))


def test_reference_mismatch_is_rejected():
    with pytest.raises(ValueError, match="expected reference"):
        reconcile_time(observation(), model(), np.eye(3), expected_reference=DEVICE)


@pytest.mark.parametrize(
    "covariance",
    [
        np.eye(2),
        np.diag([1, np.nan, 1]),
        np.diag([1, np.inf, 1]),
        np.diag([1, -1e-30, 1]),
        [[1, 0.1, 0], [0, 1, 0], [0, 0, 1]],
        [[1, 2, 0], [2, 1, 0], [0, 0, 1]],
        [[0, 1e-30, 0], [1e-30, 1, 0], [0, 0, 1]],
        [[1, 1.1e-15, 0], [1.1e-15, 1e-30, 0], [0, 0, 1]],
        [[1, 1, 1], [1, 1, -1], [1, -1, 1]],
        np.eye(3, dtype=complex) * (1 + 1j),
        np.eye(3, dtype=bool),
        [[1, True, 0], [True, 1, 0], [0, 0, 1]],
        [["1", 0, 0], [0, 1, 0], [0, 0, 1]],
        [[1, 1e-30, 0], [0, 1, 0], [0, 0, 1]],
    ],
)
def test_invalid_covariance_is_rejected(covariance):
    with pytest.raises(ValueError, match="joint_covariance"):
        reconcile_time(observation(), model(), covariance)


def test_singular_correlated_covariance_is_supported():
    # dt/skew variation anticorrelates to cancel at the nominal event.
    direction = np.array([3.0, -2.0, 0.0])
    result = reconcile_time(observation(), model(), np.outer(direction, direction))
    assert result.variance == 0


def test_zero_covariance_is_exact_deterministic_case():
    result = reconcile_time(observation(), model(), np.zeros((3, 3)))
    assert result.variance == 0


def test_dimension_scaling_does_not_hide_indefiniteness():
    scales = np.diag([1e100, 1e-100, 1.0])
    invalid = scales @ np.array([[1, 2, 0], [2, 1, 0], [0, 0, 1]]) @ scales
    with pytest.raises(ValueError, match="covariance"):
        reconcile_time(observation(), model(), invalid)


@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf, True, "10", np.complex128(1j)])
def test_invalid_timestamp(value):
    with pytest.raises(ValueError):
        observation(value)


@pytest.mark.parametrize("skew", [0, -1, np.nan, np.inf])
def test_invalid_skew(skew):
    with pytest.raises(ValueError):
        model(skew=skew)


def test_bad_domain_and_units():
    with pytest.raises(ValueError, match="ordered"):
        model(valid_device_interval=(2, 1))
    with pytest.raises(ValueError, match="seconds|unit"):
        ClockFrame("clock", "monotonic", "ms")
    with pytest.raises(ValueError, match="nonempty"):
        ClockFrame("", "monotonic")


def test_nonfinite_arithmetic_is_rejected():
    with pytest.raises(ValueError, match="nonfinite"):
        reconcile_time(observation(), model(skew=1e308), np.eye(3))
    with pytest.raises(ValueError, match="overflowed"):
        reconcile_time(observation(), model(), np.diag([1e308, 0, 0]))


def test_reconciliation_does_not_claim_exact_bilinear_moments():
    # The supplied joint covariance can correlate timestamp and skew. The
    # operation intentionally returns the nominal value, not E[a*t] corrected
    # by Cov(a,t); first-order.v1 makes that limitation explicit.
    covariance = np.array([[1.0, 0.2, 0], [0.2, 0.1, 0], [0, 0, 0]])
    result = reconcile_time(observation(), model(), covariance)
    assert result.event_time_delta == 6.5
    assert result.propagation == "first-order.v1"


def test_model_interval_is_copied_to_immutable_tuple():
    bounds = [100.0, 110.0]
    clock = model(valid_device_interval=bounds)
    bounds[0] = 1_000.0
    assert clock.valid_device_interval == (100.0, 110.0)


def test_smallest_positive_covariance_is_not_silently_erased():
    tiny = np.nextafter(0.0, 1.0)
    result = reconcile_time(observation(), model(), np.diag([0.0, 0.0, tiny]))
    assert result.variance == tiny


def test_valid_mixed_unit_rank_one_covariance_is_retained():
    covariance = np.array([[1e-14, 1e-7, 0], [1e-7, 1, 0], [0, 0, 0]])
    result = reconcile_time(observation(), model(), covariance)
    assert result.variance == pytest.approx((2e-7 + 3) ** 2)
    np.testing.assert_array_equal(result.joint_covariance, covariance)


def test_extreme_mixed_scale_covariance_normalization_is_finite():
    covariance = np.array([[1e-300, 1, 0], [1, 1e300, 0], [0, 0, 0]])
    result = reconcile_time(observation(100.0), model(), covariance)
    assert result.variance == 4e-300
    np.testing.assert_array_equal(result.joint_covariance, covariance)
