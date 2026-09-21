from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import math
from zoneinfo import ZoneInfo

import pytest

from mcur import (
    CalibrationError, CalibrationProfile, EnvironmentReading,
    EnvironmentRequirement, Interval, JointCovariance, Observation,
    ServingState, ServingStatus, calibrate,
)


START = datetime(2025, 1, 1, tzinfo=timezone.utc)
END = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def observation():
    return Observation(
        observation_id="observation:synthetic:1", artifact_id="artifact:raw:1",
        sensor_id="sensor:1", quantity_id="pressure", unit="kPa",
        acquired_at=START + timedelta(days=1), indicated_value=3.0, raw_value=300.0,
        environment=(EnvironmentReading("temperature", "degC", 20.0),),
    )


@pytest.fixture
def profile():
    return CalibrationProfile(
        profile_id="profile:synthetic:1", artifact_id="artifact:calibration:1",
        sensor_id="sensor:1", quantity_id="pressure", input_unit="kPa", output_unit="kPa",
        gain=2.0, offset=1.0, coefficient_covariance=((0.25, 0.05), (0.05, 1.0)),
        valid_from=START, valid_until=END,
        reference_ids=("reference:synthetic:1",), input_range=Interval(0.0, 10.0),
        environment_requirements=(EnvironmentRequirement("temperature", "degC", Interval(18.0, 25.0)),),
    )


@pytest.fixture
def covariance():
    return JointCovariance(((4.0, 0.2, 0.1), (0.2, 0.25, 0.05), (0.1, 0.05, 1.0)))


def test_analytical_correlated_budget_and_provenance(observation, profile, covariance):
    result = calibrate(observation, profile, covariance)
    assert result.corrected_value == 7.0
    assert result.correction_from_indication == 4.0
    assert result.additive_correction == 1.0
    assert result.jacobian == (2.0, 3.0, 1.0)
    assert result.variance == pytest.approx(22.35)
    assert result.standard_uncertainty == pytest.approx(math.sqrt(22.35))
    budget = {term.name: term.variance_contribution for term in result.uncertainty_budget}
    assert budget == pytest.approx({"x": 16.0, "g": 2.25, "b": 1.0, "x:g": 2.4, "x:b": 0.4, "g:b": 0.3})
    assert sum(budget.values()) == pytest.approx(result.variance)
    assert result.raw_value == observation.raw_value == 300.0
    assert result.indicated_value == observation.indicated_value == 3.0
    assert result.source_artifact_id == observation.artifact_id
    assert result.calibration_artifact_id == profile.artifact_id
    assert result.reference_ids == profile.reference_ids
    assert any("first-order" in item for item in result.diagnostics)
    assert any("not certified" in item for item in result.diagnostics)
    with pytest.raises(FrozenInstanceError):
        observation.indicated_value = 7.0


def test_acquisition_validity_is_separate_from_later_withdrawal(observation, profile, covariance):
    status = ServingStatus("status:1", profile.profile_id, END + timedelta(days=300), ServingState.WITHDRAWN)
    result = calibrate(observation, profile, covariance, serving_status=status)
    assert result.corrected_value == 7.0
    assert result.serving_status is status
    assert any("withdrawn" in item for item in result.diagnostics)


def test_serving_status_cannot_make_expired_acquisition_valid(observation, profile, covariance):
    status = ServingStatus("status:1", profile.profile_id, END, ServingState.ACTIVE)
    with pytest.raises(CalibrationError, match="acquisition event time"):
        calibrate(replace(observation, acquired_at=END), profile, covariance, serving_status=status)


@pytest.mark.parametrize("event,accepted", [(START, True), (END-timedelta(microseconds=1), True), (END, False), (START-timedelta(microseconds=1), False)])
def test_half_open_validity_interval(observation, profile, covariance, event, accepted):
    if accepted:
        calibrate(replace(observation, acquired_at=event), profile, covariance)
    else:
        with pytest.raises(CalibrationError, match="acquisition event time"):
            calibrate(replace(observation, acquired_at=event), profile, covariance)


@pytest.mark.parametrize("field,value", [("sensor_id", "sensor:2"), ("quantity_id", "temperature"), ("unit", "Pa")])
def test_identity_and_input_unit_mismatch(observation, profile, covariance, field, value):
    with pytest.raises(CalibrationError, match="mismatch"):
        calibrate(replace(observation, **{field: value}), profile, covariance)


def test_explicit_output_unit_conversion_has_no_ill_typed_delta(observation, profile, covariance):
    result = calibrate(observation, replace(profile, output_unit="Pa"), covariance)
    assert result.output_unit == "Pa"
    assert result.correction_from_indication is None
    assert any("different input/output" in item for item in result.diagnostics)


@pytest.mark.parametrize("environment", [(), (EnvironmentReading("temperature", "K", 293.0),), (EnvironmentReading("temperature", "degC", 50.0),)])
def test_environment_applicability(observation, profile, covariance, environment):
    with pytest.raises(CalibrationError, match="environment"):
        calibrate(replace(observation, environment=environment), profile, covariance)


def test_input_range_and_boundary(observation, profile, covariance):
    calibrate(replace(observation, indicated_value=10.0), profile, covariance)
    with pytest.raises(CalibrationError, match="input range"):
        calibrate(replace(observation, indicated_value=10.1), profile, covariance)


def test_reject_covariance_profile_substitution(observation, profile, covariance):
    with pytest.raises(CalibrationError, match="coefficient block"):
        calibrate(observation, replace(profile, coefficient_covariance=((0.5, 0.05), (0.05, 1.0))), covariance)


@pytest.mark.parametrize("scale", [1.0, 1e-200, 1e-320])
def test_reject_indefinite_covariance_at_every_scale(scale):
    with pytest.raises(CalibrationError, match="positive semidefinite"):
        JointCovariance(((scale, 2*scale, 0.0), (2*scale, scale, 0.0), (0.0, 0.0, scale)))


def test_reject_indefinite_matrix_with_nonnegative_two_by_two_minors():
    with pytest.raises(CalibrationError, match="positive semidefinite"):
        JointCovariance(((1.0, -0.75, -0.75), (-0.75, 1.0, -0.75), (-0.75, -0.75, 1.0)))


def test_reject_tiny_asymmetry():
    with pytest.raises(CalibrationError, match="exactly symmetric"):
        JointCovariance(((1e-200, 1e-220, 0), (0, 1e-200, 0), (0, 0, 1e-200)))


def test_reject_zero_diagonal_with_nonzero_covariance():
    with pytest.raises(CalibrationError, match="positive semidefinite"):
        JointCovariance(((0, 1e-200, 0), (1e-200, 1e-200, 0), (0, 0, 1e-200)))


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_reject_nonfinite_values(observation, profile, bad):
    with pytest.raises(CalibrationError, match="finite"):
        replace(observation, indicated_value=bad)
    with pytest.raises(CalibrationError, match="finite"):
        replace(profile, gain=bad)
    with pytest.raises(CalibrationError, match="finite"):
        JointCovariance(((bad, 0, 0), (0, 1, 0), (0, 0, 1)))


def test_covariance_order_is_semantic():
    with pytest.raises(CalibrationError, match="order"):
        JointCovariance(((1, 0, 0), (0, 1, 0), (0, 0, 1)), order=("g", "x", "b"))


def test_lists_are_frozen_and_aliased_covariance_cannot_mutate_result():
    source = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    covariance = JointCovariance(source)
    source[0][0] = -10
    assert covariance.values[0][0] == 1.0


def test_exact_psd_singular_and_negative_cross_budget(observation, profile):
    profile = replace(profile, gain=1.0, coefficient_covariance=((0, 0), (0, 1)))
    covariance = JointCovariance(((1, 0, -1), (0, 0, 0), (-1, 0, 1)))
    result = calibrate(observation, profile, covariance)
    assert result.variance == 0.0
    assert result.standard_uncertainty == 0.0
    assert dict((term.name, term.variance_contribution) for term in result.uncertainty_budget)["x:b"] == -2.0


def test_valid_subnormal_covariance_is_not_rounded_away(observation, profile):
    profile = replace(profile, gain=1.0, coefficient_covariance=((0, 0), (0, 0)))
    covariance = JointCovariance(((1e-320, 0, 0), (0, 0, 0), (0, 0, 0)))
    result = calibrate(observation, profile, covariance)
    assert result.variance == 1e-320
    assert result.standard_uncertainty > 0.0


def test_output_overflow_rejected(observation, profile):
    profile = replace(profile, gain=1e308, coefficient_covariance=((0, 0), (0, 0)))
    with pytest.raises(CalibrationError, match="overflows"):
        calibrate(observation, profile, JointCovariance(((0, 0, 0), (0, 0, 0), (0, 0, 0))))


def test_nonzero_variance_underflow_rejected(observation, profile):
    profile = replace(profile, gain=1e-200, coefficient_covariance=((0, 0), (0, 0)))
    with pytest.raises(CalibrationError, match="underflows"):
        calibrate(observation, profile, JointCovariance(((1e-200, 0, 0), (0, 0, 0), (0, 0, 0))))


def test_naive_times_rejected(observation, profile):
    with pytest.raises(CalibrationError, match="timezone-aware"):
        replace(observation, acquired_at=datetime(2025, 1, 1))
    with pytest.raises(CalibrationError, match="timezone-aware"):
        replace(profile, valid_until=datetime(2026, 1, 1))


def test_acquisition_validity_compares_instants_across_dst_fold(observation, profile, covariance):
    eastern = ZoneInfo("America/New_York")
    # 01:50 fold=0 is 05:50Z, before the 01:30 fold=1 start at 06:30Z.
    profile = replace(profile,
        valid_from=datetime(2025, 11, 2, 1, 30, tzinfo=eastern, fold=1),
        valid_until=datetime(2025, 11, 2, 2, 0, tzinfo=eastern),
    )
    with pytest.raises(CalibrationError, match="acquisition event time"):
        calibrate(replace(observation, acquired_at=datetime(2025, 11, 2, 1, 50, tzinfo=eastern, fold=0)), profile, covariance)
    result = calibrate(replace(observation, acquired_at=datetime(2025, 11, 2, 1, 50, tzinfo=eastern, fold=1)), profile, covariance)
    assert result.acquired_at.fold == 1


def test_validity_interval_order_compares_instants_across_dst_fold(profile):
    eastern = ZoneInfo("America/New_York")
    with pytest.raises(CalibrationError, match="valid_from must precede"):
        replace(profile,
            valid_from=datetime(2025, 11, 2, 1, 30, tzinfo=eastern, fold=1),
            valid_until=datetime(2025, 11, 2, 1, 50, tzinfo=eastern, fold=0),
        )


def test_mixed_boolean_numeric_covariance_rejected():
    with pytest.raises(CalibrationError, match="real number"):
        JointCovariance(((True, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)))


def test_serving_record_profile_identity_is_checked(observation, profile, covariance):
    status = ServingStatus("status:1", "profile:another", END, ServingState.ACTIVE)
    with pytest.raises(CalibrationError, match="profile_id mismatch"):
        calibrate(observation, profile, covariance, serving_status=status)


def test_missing_reference_does_not_manufacture_traceability(observation, profile, covariance):
    result = calibrate(observation, replace(profile, reference_ids=()), covariance)
    assert result.reference_ids == ()
    assert any("not certified" in item for item in result.diagnostics)
