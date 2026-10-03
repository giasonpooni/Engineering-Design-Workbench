"""Independent binary64 reference for the declared daily irrigation profile.

The FAO-56 equation and generalized least-squares calculation are assembled
here independently.  This module never imports a candidate solver or a
metrology provider. Agreement checks arithmetic within caller declarations;
it does not validate field measurements, crop parameters or an actuator.
"""
from __future__ import annotations

import math
from datetime import datetime

from .irrigation_contract import validate_request

REFERENCE_ID = "independent_fao56_gls_daily_bucket_allocation_binary64.v1"
# Independently declared roundoff policy; the data contract retains these
# values in MODEL_CONVENTIONS. These are numerical classification margins,
# not additions to the supplied measurement uncertainty.
THETA_DOMAIN_ROUNDOFF = 1e-12
DEPLETION_DECISION_ROUNDOFF_MM = 1e-9


def fao56_daily_et0(tmin_c: float, tmax_c: float, pressure_kpa: float,
                   wind_2m_m_per_s: float, net_radiation_mj_per_m2_day: float,
                   soil_heat_flux_mj_per_m2_day: float,
                   actual_vapor_pressure_kpa: float) -> float:
    """Equation 6, with equations 8, 11, 12 and 13, in daily FAO units.

    The signed expression is returned. A profile choosing a nonnegative
    evapotranspiration sink must explicitly retain its treatment of dew.
    """
    temperature = (tmin_c + tmax_c) / 2.0
    saturated_min = 0.6108 * math.exp(17.27 * tmin_c / (tmin_c + 237.3))
    saturated_max = 0.6108 * math.exp(17.27 * tmax_c / (tmax_c + 237.3))
    saturated_mean_temperature = 0.6108 * math.exp(17.27 * temperature / (temperature + 237.3))
    slope = 4098.0 * saturated_mean_temperature / (temperature + 237.3) ** 2
    psychrometric = 0.000665 * pressure_kpa
    vapor_deficit = (saturated_min + saturated_max) / 2.0 - actual_vapor_pressure_kpa
    radiative = 0.408 * slope * (net_radiation_mj_per_m2_day - soil_heat_flux_mj_per_m2_day)
    aerodynamic = psychrometric * 900.0 * wind_2m_m_per_s * vapor_deficit / (temperature + 273.0)
    return (radiative + aerodynamic) / (slope + psychrometric * (1.0 + 0.34 * wind_2m_m_per_s))


def _linear_solve(matrix: list[list[float]], right: list[float]) -> list[float]:
    """Independent partial-pivot Gaussian elimination, bounded by the schema."""
    count = len(right)
    augmented = [list(row) + [value] for row, value in zip(matrix, right)]
    for column in range(count):
        pivot = max(range(column, count), key=lambda row: abs(augmented[row][column]))
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        if not math.isfinite(divisor) or divisor == 0.0:
            raise ValueError("Independent irrigation reference refuses singular covariance")
        for row in range(column + 1, count):
            factor = augmented[row][column] / divisor
            for index in range(column + 1, count + 1):
                augmented[row][index] -= factor * augmented[column][index]
            augmented[row][column] = 0.0
    solution = [0.0] * count
    for row in range(count - 1, -1, -1):
        solution[row] = (augmented[row][-1] - math.fsum(
            augmented[row][column] * solution[column] for column in range(row + 1, count)
        )) / augmented[row][row]
    return solution


def gls_replicas(values: list[float], covariance: list[list[float]]) -> tuple[float, float, list[float]]:
    """One common estimand, using the full caller-declared covariance matrix."""
    if not 1 <= len(values) <= 8 or len(covariance) != len(values) or any(len(row) != len(values) for row in covariance):
        raise ValueError("Independent irrigation reference requires a bounded square covariance")
    precision_sum = _linear_solve(covariance, [1.0] * len(values))
    normalization = math.fsum(precision_sum)
    if not math.isfinite(normalization) or normalization <= 0.0:
        raise ValueError("Independent irrigation reference requires positive common-mean precision")
    weights = [entry / normalization for entry in precision_sum]
    anchor = values[0]
    mean = anchor + math.fsum(weight * (value - anchor) for weight, value in zip(weights, values))
    return mean, 1.0 / normalization, weights


def _declared_et0(weather):
    # Accepted weather intermediates remain explicit inputs. The contract
    # separately checks their declared saturation-pressure consistency.
    temperature = weather["temp_mean_c"]
    slope = 4098.0 * 0.6108 * math.exp(17.27 * temperature / (temperature + 237.3)) / (temperature + 237.3) ** 2
    gamma = 0.000665 * weather["pressure_kpa"]
    wind = weather["wind_2m_m_s"]
    radiation = weather["net_radiation_mj_m2_day"] - weather["soil_heat_flux_mj_m2_day"]
    deficit = weather["saturation_vapour_pressure_kpa"] - weather["actual_vapour_pressure_kpa"]
    return (0.408 * slope * radiation + gamma * 900.0 * wind * deficit / (temperature + 273.0)) / (slope + gamma * (1.0 + 0.34 * wind))


def _quality_reasons(request, rows):
    as_of = datetime.fromisoformat(request["as_of"].replace("Z", "+00:00"))
    reasons = []
    for row in rows:
        observed = datetime.fromisoformat(row["observed_at"].replace("Z", "+00:00"))
        until = datetime.fromisoformat(row["calibrated_until"].replace("Z", "+00:00"))
        tests = [("future_observation", observed > as_of),
                 ("stale_observation", (as_of - observed).total_seconds() > 3600.0 * request["max_age_hours"]),
                 ("expired_calibration", until <= as_of)]
        for reason, failed in tests:
            if failed and reason not in reasons:
                reasons.append(reason)
    return reasons


def _bucket(depletion, wetting, potential_et, taw, raw):
    # Work in the unclipped depletion coordinate so excess wetting remains
    # available for ET before the explicitly declared same-day drainage.
    before_et = depletion - wetting
    stress = min(1.0, max(0.0, (taw - max(0.0, before_et)) / (taw - raw)))
    actual_et = min(stress * potential_et, max(0.0, taw - before_et))
    percolation = max(0.0, -(before_et + actual_et))
    end = before_et + actual_et + percolation
    if -1e-9 <= end < 0.0:
        end = 0.0
    if taw < end <= taw + 1e-9:
        end = taw
    return end, stress, actual_et, percolation


def _initial_zone(request, zone, priority, telemetry):
    measured = zone["soil_measurements"]
    values = [observation["calibrated_theta_m3_m3"] for observation in measured["observations"]]
    mean, variance, weights = gls_replicas(values, measured["covariance"])
    root_mm = 1000.0 * zone["root_depth_m"]
    taw = (zone["theta_fc"] - zone["theta_wp"]) * root_mm
    raw = zone["depletion_fraction"] * taw
    raw_depletion = (zone["theta_fc"] - mean) * root_mm
    uncertainty = root_mm * math.sqrt(variance)
    low = max(0.0, min(taw, raw_depletion - request["coverage_factor"] * uncertainty))
    high = max(0.0, min(taw, raw_depletion + request["coverage_factor"] * uncertainty))
    depletion = max(0.0, min(taw, raw_depletion))
    reasons = _quality_reasons(request, measured["observations"])
    if mean < zone["theta_wp"] - THETA_DOMAIN_ROUNDOFF or mean > zone["theta_fc"] + THETA_DOMAIN_ROUNDOFF:
        reasons.append("fused_mean_outside_bucket_domain")
    status = "ABSTAIN" if reasons else "READY"
    if not reasons and (raw_depletion - request["coverage_factor"] * uncertainty < 0.0 or
                        raw_depletion + request["coverage_factor"] * uncertainty > taw):
        status, reasons = "REVIEW", ["initial_screening_outside_bucket_domain"]
    matching = [row for row in telemetry if row["zone_id"] == zone["zone_id"]]
    if any(row["quality_status"] == "ABSTAIN" for row in matching):
        status = "ABSTAIN"
        reasons.append("telemetry_quality_hold")
    if any(row["quality_status"] == "VALID" and row["indicators"] for row in matching):
        if status != "ABSTAIN":
            status = "REVIEW"
        reasons.append("telemetry_discrepancy")
    return {"zone_id": zone["zone_id"], "priority_index": priority, "planning_status": status, "reasons": reasons,
            "fused_theta_m3_m3": mean, "fused_variance_m3_m3_squared": variance,
            "fused_standard_uncertainty_m3_m3": math.sqrt(variance), "fusion_weights": weights,
            "taw_mm": taw, "raw_mm": raw, "depletion_mm": depletion, "standard_uncertainty_mm": uncertainty,
            "screening_lower_mm": low, "screening_upper_mm": high,
            "projection_is_descriptive_only": status in {"ABSTAIN", "REVIEW"}}


def _telemetry(request):
    telemetry = []
    for declared in request["telemetry"]:
        reasons = _quality_reasons(request, [declared])
        flow = declared["observed_flow_m3_h"] - declared["expected_flow_m3_h"]
        pressure = declared["observed_pressure_kpa"] - declared["expected_pressure_kpa"]
        indicators = []
        if not reasons:
            if not declared["commanded_open"] and declared["observed_flow_m3_h"] > declared["flow_tolerance_m3_h"]:
                indicators.append("unexpected_flow_while_closed")
            elif flow > declared["flow_tolerance_m3_h"]:
                indicators.append("flow_above_expectation")
            elif flow < -declared["flow_tolerance_m3_h"]:
                indicators.append("flow_below_expectation")
            if pressure > declared["pressure_tolerance_kpa"]:
                indicators.append("pressure_above_expectation")
            elif pressure < -declared["pressure_tolerance_kpa"]:
                indicators.append("pressure_below_expectation")
        telemetry.append({"telemetry_id": declared["telemetry_id"], "zone_id": declared["zone_id"],
                          "quality_status": "ABSTAIN" if reasons else "VALID", "reasons": reasons,
                          "flow_residual_m3_h": flow, "pressure_residual_kpa": pressure, "indicators": indicators})
    return telemetry


def reference(request: dict) -> dict:
    """Independently recompute every scientific field in the bounded profile.

    Gaussian elimination supplies the common-mean estimate; a depletion
    coordinate supplies the water inventory. Neither candidate provider nor
    its metrology, evolution, policy or telemetry helpers are imported.
    """
    request = validate_request(request)
    telemetry = _telemetry(request)
    initials = [_initial_zone(request, zone, index, telemetry) for index, zone in enumerate(request["zones"])]
    state = [(row["depletion_mm"], row["screening_lower_mm"], row["screening_upper_mm"]) for row in initials]
    pump = request["pump"]
    capacity = min(pump["water_budget_m3_per_day"], pump["rate_m3_h"] * pump["available_hours_per_day"])
    days = []
    for weather in request["weather"]:
        et0 = _declared_et0(weather)
        remaining = capacity
        rows = []
        for index, (zone, initial) in enumerate(zip(request["zones"], initials)):
            depletion, lower, upper = state[index]
            natural_wet = weather["rainfall_mm"] - weather["runoff_mm"] + zone["capillary_rise_mm_per_day"]
            lower_wet, upper_wet = max(0.0, lower - natural_wet), max(0.0, upper - natural_wet)
            status, reasons = initial["planning_status"], list(initial["reasons"])
            ideal = 0.0
            if status == "READY":
                if (lower_wet <= initial["raw_mm"] + DEPLETION_DECISION_ROUNDOFF_MM and
                        upper_wet >= initial["raw_mm"] - DEPLETION_DECISION_ROUNDOFF_MM):
                    status, reasons = "REVIEW", ["threshold_screening_overlap"]
                elif lower_wet > initial["raw_mm"] + DEPLETION_DECISION_ROUNDOFF_MM:
                    ideal = max(0.0, max(0.0, depletion - natural_wet) - zone["target_depletion_mm"])
            net_per_gross = 1000.0 * pump["efficiency"] / zone["area_m2"]
            limited = min(ideal, zone["max_daily_net_mm"])
            allocated_net = min(limited, remaining * net_per_gross)
            allocated_gross = allocated_net / net_per_gross
            remaining = max(0.0, remaining - allocated_gross)
            unmet = max(0.0, ideal - allocated_net)
            if unmet > 1e-9:
                status = "UNMET"
                if ideal - limited > 1e-9:
                    reasons.append("zone_daily_limit_shortfall")
                if limited - allocated_net > 1e-9:
                    reasons.append("budget_shortfall")
            wet = natural_wet + allocated_net
            potential = zone["crop_coefficient"] * et0
            end, stress, actual_et, percolation = _bucket(depletion, wet, potential, initial["taw_mm"], initial["raw_mm"])
            lower_end = _bucket(lower, wet, potential, initial["taw_mm"], initial["raw_mm"])[0]
            upper_end = _bucket(upper, wet, potential, initial["taw_mm"], initial["raw_mm"])[0]
            if lower_end > end and lower_end - end <= 1e-9:
                lower_end = end
            if upper_end < end and end - upper_end <= 1e-9:
                upper_end = end
            state[index] = (end, lower_end, upper_end)
            rows.append({"zone_id": zone["zone_id"], "planning_status": status, "reasons": reasons,
                "depletion_start_mm": depletion, "screening_lower_start_mm": lower, "screening_upper_start_mm": upper,
                "requested_net_mm": ideal, "allocated_net_mm": allocated_net,
                "requested_gross_m3": ideal / net_per_gross, "allocated_gross_m3": allocated_gross,
                "unmet_net_mm": unmet, "rainfall_mm": weather["rainfall_mm"], "runoff_mm": weather["runoff_mm"],
                "capillary_rise_mm": zone["capillary_rise_mm_per_day"], "wetting_net_mm": wet,
                "stress_coefficient": stress, "potential_crop_et_mm": potential, "actual_crop_et_mm": actual_et,
                "unmet_crop_et_mm": max(0.0, potential - actual_et), "deep_percolation_mm": percolation,
                "depletion_end_mm": end, "screening_lower_end_mm": lower_end, "screening_upper_end_mm": upper_end,
                "balance_residual_mm": end - (depletion - wet + actual_et + percolation),
                "projection_is_descriptive_only": status in {"ABSTAIN", "REVIEW"}})
        allocated = math.fsum(row["allocated_gross_m3"] for row in rows)
        days.append({"date": weather["date"], "et0_mm": et0, "available_gross_m3": capacity,
                     "allocated_gross_m3": allocated, "remaining_gross_m3": remaining,
                     "pump_hours": allocated / pump["rate_m3_h"],
                     "unmet_gross_m3": math.fsum(row["requested_gross_m3"] - row["allocated_gross_m3"] for row in rows), "zones": rows})
    statuses = [row["planning_status"] for row in initials] + [row["planning_status"] for day in days for row in day["zones"]]
    aggregate = next(status for status in ("ABSTAIN", "REVIEW", "UNMET", "READY") if status in statuses)
    return {"planning_status": aggregate, "initial_zones": initials, "days": days, "telemetry": telemetry}
