"""Conditional GLS fusion of declared calibrated root-zone mean replicas.

Covariance includes relevant calibration/common effects. This module does not
calibrate probes, reconstruct a layered profile or validate provenance.
"""
from __future__ import annotations

import math

from .irrigation_contract import THETA_DOMAIN_TOLERANCE, covariance_cholesky, utc_datetime


def evidence_reasons(observation, as_of, max_age_hours):
    """Evaluate declared timestamps against a declared planning instant."""
    now = utc_datetime(as_of)
    observed = utc_datetime(observation["observed_at"])
    until = utc_datetime(observation["calibrated_until"])
    reasons = []
    if observed > now:
        reasons.append("future_observation")
    if (now - observed).total_seconds() > max_age_hours * 3600.0:
        reasons.append("stale_observation")
    if until <= now:
        reasons.append("expired_calibration")
    return reasons


def _solve_cholesky(factor, rhs):
    count = len(rhs)
    forward = [0.0] * count
    for i in range(count):
        forward[i] = (rhs[i] - math.fsum(factor[i][j] * forward[j] for j in range(i))) / factor[i][i]
    solution = [0.0] * count
    for i in range(count - 1, -1, -1):
        solution[i] = (forward[i] - math.fsum(factor[j][i] * solution[j] for j in range(i + 1, count))) / factor[i][i]
    return solution


def gls_mean(values, covariance):
    """Return mean, variance and weights; correlated GLS weights may be negative."""
    factor = covariance_cholesky(covariance, len(values))
    precision_one = _solve_cholesky(factor, [1.0] * len(values))
    total = math.fsum(precision_one)
    if not math.isfinite(total) or total <= 0.0:
        raise ValueError("GLS covariance does not yield positive finite information")
    weights = [value / total for value in precision_one]
    anchor = values[0]
    mean = anchor + math.fsum(weight * (value - anchor) for weight, value in zip(weights, values))
    variance = 1.0 / total
    if not math.isfinite(mean) or not math.isfinite(variance) or variance <= 0.0:
        raise ValueError("GLS estimate exceeds the finite numerical domain")
    return {"mean": mean, "variance": variance, "weights": weights}


def fuse_zone(zone, *, as_of, max_age_hours, coverage_factor=2.0, priority_index=0):
    """Project a common measurand; invalid evidence gates recommendations."""
    measured = zone["soil_measurements"]
    values = [row["calibrated_theta_m3_m3"] for row in measured["observations"]]
    fused = gls_mean(values, measured["covariance"])
    reasons = []
    for observation in measured["observations"]:
        for reason in evidence_reasons(observation, as_of, max_age_hours):
            if reason not in reasons:
                reasons.append(reason)
    theta, variance = fused["mean"], fused["variance"]
    taw = 1000.0 * (zone["theta_fc"] - zone["theta_wp"]) * zone["root_depth_m"]
    raw = zone["depletion_fraction"] * taw
    original_depletion = 1000.0 * (zone["theta_fc"] - theta) * zone["root_depth_m"]
    standard_uncertainty = 1000.0 * zone["root_depth_m"] * math.sqrt(variance)
    if theta < zone["theta_wp"] - THETA_DOMAIN_TOLERANCE or theta > zone["theta_fc"] + THETA_DOMAIN_TOLERANCE:
        reasons.append("fused_mean_outside_bucket_domain")
    status = "ABSTAIN" if reasons else "READY"
    lower_unbounded = original_depletion - coverage_factor * standard_uncertainty
    upper_unbounded = original_depletion + coverage_factor * standard_uncertainty
    if not reasons and (lower_unbounded < 0.0 or upper_unbounded > taw):
        status = "REVIEW"
        reasons.append("initial_screening_outside_bucket_domain")
    # Held projections preserve the original fused mean and an explicit flag.
    depletion = min(taw, max(0.0, original_depletion))
    return {
        "zone_id": zone["zone_id"], "priority_index": priority_index,
        "planning_status": status, "reasons": reasons,
        "fused_theta_m3_m3": theta, "fused_variance_m3_m3_squared": variance,
        "fused_standard_uncertainty_m3_m3": math.sqrt(variance), "fusion_weights": fused["weights"],
        "taw_mm": taw, "raw_mm": raw, "depletion_mm": depletion,
        "standard_uncertainty_mm": standard_uncertainty,
        "screening_lower_mm": min(taw, max(0.0, lower_unbounded)),
        "screening_upper_mm": min(taw, max(0.0, upper_unbounded)),
        "projection_is_descriptive_only": status in {"ABSTAIN", "REVIEW"},
    }


def inspect_telemetry(row, *, as_of, max_age_hours):
    """Residual hints without a unique causal diagnosis or control authorization."""
    reasons = evidence_reasons(row, as_of, max_age_hours)
    flow = row["observed_flow_m3_h"] - row["expected_flow_m3_h"]
    pressure = row["observed_pressure_kpa"] - row["expected_pressure_kpa"]
    indicators = []
    if not reasons:
        if not row["commanded_open"] and row["observed_flow_m3_h"] > row["flow_tolerance_m3_h"]:
            indicators.append("unexpected_flow_while_closed")
        elif flow > row["flow_tolerance_m3_h"]:
            indicators.append("flow_above_expectation")
        elif flow < -row["flow_tolerance_m3_h"]:
            indicators.append("flow_below_expectation")
        if pressure > row["pressure_tolerance_kpa"]:
            indicators.append("pressure_above_expectation")
        elif pressure < -row["pressure_tolerance_kpa"]:
            indicators.append("pressure_below_expectation")
    return {
        "telemetry_id": row["telemetry_id"], "zone_id": row["zone_id"],
        "quality_status": "ABSTAIN" if reasons else "VALID", "reasons": reasons,
        "flow_residual_m3_h": flow, "pressure_residual_kpa": pressure, "indicators": indicators,
    }
