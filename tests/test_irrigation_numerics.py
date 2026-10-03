"""Irrigation checks against independent FAO and analytical balance fixtures."""
from __future__ import annotations

from copy import deepcopy
import math

import pytest

from ciw.irrigation_reference import fao56_daily_et0, gls_replicas
from ciw.irrigation_contract import example_request, validate_request, validate_result
from ciw.irrigation_solver import simulate
from ciw.irrigation_verification import CHECK_NAMES, THRESHOLDS, validate_report, verify
from ciw.operations.runner import digest, seal


def _single_day():
    request = example_request()
    request["weather"] = request["weather"][:1]
    return request


def _qualified(request):
    result = simulate(request)
    report = verify(request, result)
    validate_report(request, result, report)
    assert report["status"] == "PASS", report["checks"]
    assert report["qualification"]["action"] == "LOCAL"
    return result, report


def test_fao56_example18_daily_reference_with_explicit_unrounded_conversions():
    # FAO Irrigation and Drainage Paper 56, ch. 4, Example 18, reports 3.9 mm/d.
    # Rn=13.28 is retained as published; temperature/humidity/wind/pressure
    # use the source's equations rather than silently mixing table rounding.
    # https://www.fao.org/4/x0490e/x0490e08.htm
    saturation = lambda t: 0.6108 * math.exp(17.27 * t / (t + 237.3))
    pressure = 101.3 * ((293.0 - 0.0065 * 100.0) / 293.0) ** 5.26
    wind = (10.0 / 3.6) * 4.87 / math.log(67.8 * 10.0 - 5.42)
    actual_vapor = (saturation(12.3) * 0.84 + saturation(21.5) * 0.63) / 2.0
    value = fao56_daily_et0(12.3, 21.5, pressure, wind, 13.28, 0.0, actual_vapor)
    assert value == pytest.approx(3.879586250204349, abs=1e-12)
    assert round(value, 1) == 3.9


def test_full_covariance_gls_matches_exact_two_replica_solution():
    mean, variance, weights = gls_replicas([0.22, 0.24], [[0.0001, 0.0], [0.0, 0.0004]])
    assert weights == pytest.approx([0.8, 0.2], abs=1e-14)
    assert mean == pytest.approx(0.224, abs=1e-14)
    assert variance == pytest.approx(0.00008, abs=1e-16)


def test_shared_error_does_not_disappear_with_replication():
    covariance = [[0.0001, 0.00008], [0.00008, 0.0001]]
    mean, variance, weights = gls_replicas([0.22, 0.24], covariance)
    assert weights == pytest.approx([0.5, 0.5], abs=1e-14)
    assert mean == pytest.approx(0.23, abs=1e-14)
    assert variance == pytest.approx(0.00009, abs=1e-16)
    independent_variance = gls_replicas([0.22, 0.24], [[0.0001, 0.0], [0.0, 0.0001]])[1]
    assert variance > independent_variance


def test_reference_refuses_singular_replica_covariance():
    with pytest.raises(ValueError, match="singular covariance"):
        gls_replicas([0.22, 0.24], [[0.0001, 0.0001], [0.0001, 0.0001]])


def test_positive_definite_correlations_can_produce_negative_gls_weights():
    # Positive determinant 1.75e-8; high positive correlation and unequal
    # variances make a negative coefficient mathematically legitimate.
    mean, variance, weights = gls_replicas([0.22, 0.24], [[0.0001, 0.00015], [0.00015, 0.0004]])
    assert weights == pytest.approx([1.25, -0.25], abs=1e-14)
    assert mean == pytest.approx(0.215, abs=1e-14)
    assert variance == pytest.approx(0.0000875, abs=1e-16)


def test_fao_reference_preserves_signed_daily_dew_expression():
    saturation = 0.6108 * math.exp(17.27 * 20.0 / (20.0 + 237.3))
    assert fao56_daily_et0(20.0, 20.0, 100.0, 0.0, -2.0, 0.0, saturation) < 0.0


def test_default_model_matches_fao_golden_and_declared_gross_net_units():
    request = _single_day()
    result, report = _qualified(request)
    initial, day = result["initial_zones"][0], result["days"][0]
    east = day["zones"][0]
    assert day["et0_mm"] == pytest.approx(3.879586250204349, abs=1e-12)
    assert initial["taw_mm"] == pytest.approx(160.0)
    assert initial["raw_mm"] == pytest.approx(64.0)
    assert initial["depletion_mm"] == pytest.approx(80.0)
    assert initial["standard_uncertainty_mm"] == pytest.approx(1.6)
    assert east["requested_net_mm"] == pytest.approx(48.0)
    assert east["allocated_net_mm"] == pytest.approx(48.0)
    assert east["allocated_gross_m3"] == pytest.approx(60.0)
    assert day["pump_hours"] == pytest.approx(6.0)
    assert east["depletion_end_mm"] == pytest.approx(32.0 + 1.2 * day["et0_mm"])
    assert set(row["name"] for row in report["checks"]) == set(CHECK_NAMES)
    assert report["thresholds"] == THRESHOLDS == {"absolute": 1e-9, "relative": 1e-9}
    assert report["request_digest"] == digest(request)
    assert report["candidate_digest"] == result["record_digest"]


def test_rain_runoff_and_upward_capillary_supply_have_accounted_same_day_drainage():
    request = _single_day()
    request["weather"][0].update(rainfall_mm=100.0, runoff_mm=10.0)
    request["zones"][0]["capillary_rise_mm_per_day"] = 5.0
    result, _ = _qualified(request)
    day = result["days"][0]
    east = day["zones"][0]
    et = 1.2 * day["et0_mm"]
    assert east["allocated_net_mm"] == 0.0
    assert east["wetting_net_mm"] == 95.0
    assert east["actual_crop_et_mm"] == pytest.approx(et)
    assert east["deep_percolation_mm"] == pytest.approx(15.0 - et)
    assert east["depletion_end_mm"] == pytest.approx(0.0, abs=1e-14)
    area = request["zones"][0]["area_m2"]
    water_in_m3 = east["wetting_net_mm"] * area / 1000.0
    storage_gain_m3 = (east["depletion_start_mm"] - east["depletion_end_mm"]) * area / 1000.0
    water_out_m3 = (east["actual_crop_et_mm"] + east["deep_percolation_mm"]) * area / 1000.0
    assert water_in_m3 == pytest.approx(storage_gain_m3 + water_out_m3, abs=1e-12)


def test_stress_reduces_crop_et_when_declared_pump_has_no_available_water():
    request = _single_day()
    request["pump"]["water_budget_m3_per_day"] = 0.0
    request["zones"][0]["capillary_rise_mm_per_day"] = 5.0
    result, report = _qualified(request)
    east = result["days"][0]["zones"][0]
    assert result["planning_status"] == "UNMET"
    assert report["qualification"]["planning_status"] == "UNMET"
    assert east["allocated_net_mm"] == 0.0
    assert east["stress_coefficient"] == pytest.approx((160.0 - 75.0) / (160.0 - 64.0))
    assert east["actual_crop_et_mm"] == pytest.approx(east["potential_crop_et_mm"] * east["stress_coefficient"])
    assert east["depletion_end_mm"] == pytest.approx(75.0 + east["actual_crop_et_mm"])
    assert east["unmet_crop_et_mm"] > 0.0


def test_declared_zone_order_controls_short_budget_and_reversing_priority_changes_recipient():
    request = _single_day()
    request["zones"][1]["soil_measurements"]["observations"][0]["calibrated_theta_m3_m3"] = 0.22
    request["pump"]["water_budget_m3_per_day"] = 30.0
    first, _ = _qualified(request)
    rows = first["days"][0]["zones"]
    assert [row["allocated_net_mm"] for row in rows] == pytest.approx([24.0, 0.0])
    assert all(row["planning_status"] == "UNMET" for row in rows)
    assert first["days"][0]["allocated_gross_m3"] == pytest.approx(30.0)
    assert first["days"][0]["unmet_gross_m3"] == pytest.approx(90.0)
    assert first["days"][0]["pump_hours"] == pytest.approx(3.0)
    request["zones"].reverse()
    second, _ = _qualified(request)
    changed = second["days"][0]["zones"]
    assert changed[0]["zone_id"] == rows[1]["zone_id"]
    assert [row["allocated_net_mm"] for row in changed] == pytest.approx([24.0, 0.0])


def test_zone_daily_limit_preserves_uncapped_requested_need_and_explains_shortfall():
    request = _single_day()
    request["zones"][0]["max_daily_net_mm"] = 10.0
    result, _ = _qualified(request)
    east = result["days"][0]["zones"][0]
    assert east["requested_net_mm"] == pytest.approx(48.0)
    assert east["allocated_net_mm"] == pytest.approx(10.0)
    assert east["unmet_net_mm"] == pytest.approx(38.0)
    assert east["reasons"] == ["zone_daily_limit_shortfall"]


@pytest.mark.parametrize("field,value,reason", [
    ("observed_at", "2026-10-03T00:00:01Z", "future_observation"),
    ("observed_at", "2026-10-02T00:00:00Z", "stale_observation"),
    ("calibrated_until", "2026-10-03T00:00:00Z", "expired_calibration"),
])
def test_invalid_soil_time_evidence_abstains_persistently_but_correct_arithmetic_qualifies(field, value, reason):
    request = example_request()
    request["zones"][0]["soil_measurements"]["observations"][0][field] = value
    result, report = _qualified(request)
    assert result["planning_status"] == "ABSTAIN"
    assert result["initial_zones"][0]["reasons"] == [reason]
    assert report["qualification"]["planning_status"] == "ABSTAIN"
    assert all(day["zones"][0]["allocated_net_mm"] == 0.0 for day in result["days"])
    assert all(day["zones"][0]["projection_is_descriptive_only"] for day in result["days"])


def test_explicit_calibration_boundary_in_telemetry_holds_only_affected_zone():
    request = example_request()
    request["telemetry"][0]["calibrated_until"] = request["as_of"]
    request["zones"][1]["soil_measurements"]["observations"][0]["calibrated_theta_m3_m3"] = 0.22
    result, _ = _qualified(request)
    assert result["telemetry"][0]["quality_status"] == "ABSTAIN"
    assert result["telemetry"][0]["reasons"] == ["expired_calibration"]
    assert result["telemetry"][0]["indicators"] == []
    assert result["initial_zones"][0]["reasons"] == ["telemetry_quality_hold"]
    assert all(day["zones"][0]["allocated_net_mm"] == 0.0 for day in result["days"])
    assert result["days"][0]["zones"][1]["allocated_net_mm"] > 0.0


def test_fresh_closed_valve_flow_residual_requires_review_without_unique_diagnosis():
    request = example_request()
    request["telemetry"][0]["observed_flow_m3_h"] = 0.3
    result, report = _qualified(request)
    assert result["telemetry"][0]["indicators"] == ["unexpected_flow_while_closed"]
    assert result["initial_zones"][0]["reasons"] == ["telemetry_discrepancy"]
    assert result["planning_status"] == "REVIEW"
    assert all(day["zones"][0]["allocated_net_mm"] == 0.0 for day in result["days"])
    assert any("do not uniquely identify" in text for text in report["limitations"])


def test_threshold_overlap_and_initial_out_of_domain_uncertainty_remain_held():
    request = _single_day()
    request["zones"][0]["soil_measurements"]["observations"][0]["calibrated_theta_m3_m3"] = 0.24
    result, _ = _qualified(request)
    assert result["initial_zones"][0]["planning_status"] == "READY"
    assert result["days"][0]["zones"][0]["reasons"] == ["threshold_screening_overlap"]
    assert result["days"][0]["zones"][0]["allocated_net_mm"] == 0.0
    request["zones"][0]["soil_measurements"]["covariance"] = [[0.02]]
    result, _ = _qualified(request)
    assert result["initial_zones"][0]["reasons"] == ["initial_screening_outside_bucket_domain"]
    assert result["days"][0]["zones"][0]["allocated_net_mm"] == 0.0


@pytest.mark.parametrize("theta", [0.12, 0.32])
def test_correlated_identical_replicas_at_wilting_and_field_capacity_keep_exact_common_value(theta):
    request = _single_day()
    measured = request["zones"][0]["soil_measurements"]
    first = measured["observations"][0]
    first["calibrated_theta_m3_m3"] = theta
    second = deepcopy(first)
    second["observation_id"] += "-replica"
    measured["observations"].append(second)
    measured["covariance"] = [
        [1.720973169938514e-7, 4.028760908019794e-7],
        [4.028760908019794e-7, 2.4247845854023253e-6],
    ]
    result, _ = _qualified(request)
    initial = result["initial_zones"][0]
    assert initial["fused_theta_m3_m3"] == theta
    assert initial["planning_status"] == "REVIEW"
    assert initial["reasons"] == ["initial_screening_outside_bucket_domain"]
    assert result["days"][0]["zones"][0]["allocated_net_mm"] == 0.0


@pytest.mark.parametrize("theta,status", [
    (0.12 - 0.5e-12, "REVIEW"), (0.12 - 2e-12, "ABSTAIN"),
    (0.32 + 0.5e-12, "REVIEW"), (0.32 + 2e-12, "ABSTAIN"),
])
def test_declared_theta_roundoff_margin_has_explicit_review_and_abstention_boundaries(theta, status):
    request = _single_day()
    request["zones"][0]["soil_measurements"]["observations"][0]["calibrated_theta_m3_m3"] = theta
    result, _ = _qualified(request)
    assert result["initial_zones"][0]["planning_status"] == status
    assert result["initial_zones"][0]["projection_is_descriptive_only"]


@pytest.mark.parametrize("edge,offset,status", [
    ("lower", 0.0, "REVIEW"), ("lower", 0.5e-9, "REVIEW"), ("lower", 2e-9, "READY"),
    ("upper", 0.0, "REVIEW"), ("upper", -0.5e-9, "REVIEW"), ("upper", -2e-9, "READY"),
])
def test_raw_threshold_ties_and_declared_roundoff_margin_are_deterministic(edge, offset, status):
    request = _single_day()
    zone = request["zones"][0]
    root_mm = 1000.0 * zone["root_depth_m"]
    raw = zone["depletion_fraction"] * (zone["theta_fc"] - zone["theta_wp"]) * root_mm
    sigma = root_mm * math.sqrt(zone["soil_measurements"]["covariance"][0][0])
    depletion = raw + (2.0 * sigma if edge == "lower" else -2.0 * sigma) + offset
    zone["soil_measurements"]["observations"][0]["calibrated_theta_m3_m3"] = zone["theta_fc"] - depletion / root_mm
    result, _ = _qualified(request)
    row = result["days"][0]["zones"][0]
    assert row["planning_status"] == status
    if status == "REVIEW" or edge == "upper":
        assert row["allocated_net_mm"] == 0.0
    else:
        assert row["allocated_net_mm"] > 0.0


@pytest.mark.parametrize("field,value", [
    ("pressure_kpa", True), ("pressure_kpa", float("inf")), ("pressure_kpa", float("nan")),
    ("rainfall_mm", -1.0), ("runoff_mm", 1.0), ("saturation_vapour_pressure_kpa", 10.0),
    ("temp_mean_c", 20.0), ("soil_heat_flux_mj_m2_day", 20.0),
])
def test_request_rejects_invalid_scientific_weather_values(field, value):
    request = _single_day()
    request["weather"][0][field] = value
    with pytest.raises(ValueError):
        validate_request(request)


@pytest.mark.parametrize("covariance", [
    [[True]], [[0.0]], [[float("nan")]], [[1e-20]],
    [[0.0001, 0.0001], [0.0001, 0.0001]],
    [[0.0001, 0.00009999999999999999], [0.00009999999999999999, 0.0001]],
    [[0.0001, 0.0], [0.00001, 0.0001]],
])
def test_request_refuses_ambiguous_or_unresolved_covariance(covariance):
    request = _single_day()
    measured = request["zones"][0]["soil_measurements"]
    if len(covariance) == 2:
        other = deepcopy(measured["observations"][0])
        other["observation_id"] += "-replica"
        measured["observations"].append(other)
    measured["covariance"] = covariance
    with pytest.raises(ValueError):
        validate_request(request)


@pytest.mark.parametrize("path", [(), ("weather", 0), ("zones", 0), ("pump",), ("telemetry", 0)])
def test_request_unknown_fields_are_refused(path):
    request = _single_day()
    target = request
    for field in path:
        target = target[field]
    target["unsupported"] = "unsupported"
    with pytest.raises(ValueError, match="contract fields"):
        validate_request(request)


@pytest.mark.parametrize("path,check", [
    (("days", 0, "et0_mm"), "fao56_reference_et0"),
    (("initial_zones", 0, "fused_theta_m3_m3"), "replica_gls_fusion"),
    (("days", 0, "zones", 0, "allocated_net_mm"), "priority_pump_budget_allocation"),
    (("days", 0, "zones", 0, "stress_coefficient"), "stress_and_crop_et"),
    (("days", 0, "zones", 0, "depletion_end_mm"), "daily_root_zone_balance"),
    (("days", 0, "allocated_gross_m3"), "gross_net_units_and_pump_limits"),
])
def test_resealed_numeric_forgery_requires_fresh_numerical_refusal(path, check):
    request = _single_day()
    result, _ = _qualified(request)
    target = result
    for field in path[:-1]:
        target = target[field]
    target[path[-1]] *= 0.99
    seal(result)
    validate_result(request, result)
    report = verify(request, result)
    assert report["status"] == "FAIL"
    assert report["qualification"]["action"] == "REFUSE"
    assert next(row for row in report["checks"] if row["name"] == check)["status"] == "FAIL"
    validate_report(request, result, report)


def test_resealed_overbudget_assertion_fails_independent_volume_and_limits():
    request = _single_day()
    result, _ = _qualified(request)
    result["days"][0]["allocated_gross_m3"] = 61.0
    result["days"][0]["pump_hours"] = 6.1
    seal(result)
    validate_result(request, result)
    report = verify(request, result)
    assert report["status"] == "FAIL"
    assert report["metrics"]["residuals"]["gross_net_units_and_pump_limits"] > 1e-9


def test_fresh_verifier_never_calls_candidate_or_metrology_helpers(monkeypatch):
    request = _single_day()
    result, _ = _qualified(request)
    import ciw.irrigation_solver as solver
    import ciw.irrigation_metrology as metrology
    def forbidden(*args, **kwargs):
        raise AssertionError("Independent irrigation audit called a candidate provider")
    for module, names in ((solver, ("simulate", "reference_et0", "bucket_step", "_decision")),
                          (metrology, ("fuse_zone", "inspect_telemetry", "gls_mean", "evidence_reasons"))):
        for name in names:
            monkeypatch.setattr(module, name, forbidden)
    assert verify(request, result)["status"] == "PASS"


def test_static_report_inspection_never_replays_numerical_reference(monkeypatch):
    request = _single_day()
    result, report = _qualified(request)
    import ciw.irrigation_reference as reference_module
    import ciw.irrigation_verification as verification_module
    import ciw.irrigation_solver as solver
    def forbidden(*args, **kwargs):
        raise AssertionError("Retained inspection ran irrigation arithmetic")
    monkeypatch.setattr(reference_module, "reference", forbidden)
    monkeypatch.setattr(verification_module, "reference", forbidden)
    monkeypatch.setattr(verification_module, "verify", forbidden)
    monkeypatch.setattr(solver, "simulate", forbidden)
    validate_report(request, result, report)


def test_coherent_retained_forgery_can_be_read_but_fresh_audit_detects_it():
    request = _single_day()
    result, report = _qualified(request)
    result["days"][0]["et0_mm"] *= 1.01
    seal(result)
    report["candidate_digest"] = result["record_digest"]
    seal(report)
    validate_report(request, result, report)
    assert verify(request, result)["qualification"]["action"] == "REFUSE"


@pytest.mark.parametrize("mutation", ["duplicate_check", "missing_check", "boolean_count", "boolean_residual", "threshold_change", "status_change", "unknown_field", "binding_change"])
def test_static_report_refuses_malformed_or_incoherent_retained_claims(mutation):
    request = _single_day()
    result, report = _qualified(request)
    if mutation == "duplicate_check":
        report["checks"][-1] = deepcopy(report["checks"][0])
    elif mutation == "missing_check":
        report["checks"].pop()
    elif mutation == "boolean_count":
        report["reference"]["day_count"] = True
    elif mutation == "boolean_residual":
        report["metrics"]["residuals"][CHECK_NAMES[0]] = False
    elif mutation == "threshold_change":
        report["thresholds"]["absolute"] = 0.1
    elif mutation == "status_change":
        report["status"] = "FAIL"
    elif mutation == "unknown_field":
        report["unknown"] = "unknown"
    else:
        report["candidate_digest"] = "sha256:" + "0" * 64
    seal(report)
    with pytest.raises(ValueError):
        validate_report(request, result, report)
