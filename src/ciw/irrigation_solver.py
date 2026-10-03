"""Bounded FAO56 daily planning; descriptive simulation, never hardware control.

Every allocation is a declared simulated net water supply. Screening endpoints
vary only the initial measured soil state; weather/parameters and subsequent
allocated irrigation stay fixed. They are not whole-forecast confidence bounds.
"""
from __future__ import annotations

from copy import deepcopy
import math

from .irrigation_contract import (
    METHOD_ID, MODEL_CONVENTIONS, PROVIDER_ID, RESULT_SCHEMA, SCOPE, SCREENING_TOLERANCE_MM,
    UNCERTAINTY_SCOPE, UNITS, validate_request, validate_result,
)
from .irrigation_metrology import fuse_zone, inspect_telemetry
from .operations.runner import digest, seal

ALLOCATION_ABSOLUTE_TOLERANCE_MM = 1e-9


def reference_et0(weather):
    """Daily Eq.6 using accepted declared intermediates and no calm-wind floor."""
    t = weather["temp_mean_c"]
    saturation_at_mean = 0.6108 * math.exp(17.27 * t / (t + 237.3))
    delta = 4098.0 * saturation_at_mean / (t + 237.3) ** 2
    gamma = 0.000665 * weather["pressure_kpa"]
    wind = weather["wind_2m_m_s"]
    deficit = weather["saturation_vapour_pressure_kpa"] - weather["actual_vapour_pressure_kpa"]
    available_radiation = weather["net_radiation_mj_m2_day"] - weather["soil_heat_flux_mj_m2_day"]
    numerator = 0.408 * delta * available_radiation + gamma * 900.0 / (t + 273.0) * wind * deficit
    return numerator / (delta + gamma * (1.0 + 0.34 * wind))


def bucket_step(depletion, *, taw, raw, potential_crop_et, wetting):
    """Early wetting, stressed ET, finite supply and explicitly accounted drainage."""
    wet_depletion = max(0.0, depletion - wetting)
    stress = 1.0 if wet_depletion <= raw else (taw - wet_depletion) / (taw - raw)
    stress = min(1.0, max(0.0, stress))
    demand = stress * potential_crop_et
    available = max(0.0, taw - depletion + wetting)
    actual_et = min(demand, available)
    drainage = max(0.0, wetting - actual_et - depletion)
    next_depletion = depletion - wetting + actual_et + drainage
    # Roundoff only: the algorithm accounts water before enforcing finite bounds.
    if -1e-9 <= next_depletion < 0.0:
        next_depletion = 0.0
    if taw < next_depletion <= taw + 1e-9:
        next_depletion = taw
    if not 0.0 <= next_depletion <= taw:
        raise ValueError("Daily bucket exceeds its accounted finite-water domain")
    balance = math.fsum((next_depletion, -depletion, wetting, -actual_et, -drainage))
    return {
        "stress_coefficient": stress, "actual_crop_et_mm": actual_et,
        "unmet_crop_et_mm": max(0.0, potential_crop_et - actual_et),
        "deep_percolation_mm": drainage, "depletion_end_mm": next_depletion,
        "balance_residual_mm": balance,
    }


def _decision(zone, initial, current, rain_net):
    nominal, lower, upper = current
    reasons = list(initial["reasons"])
    if initial["planning_status"] in {"ABSTAIN", "REVIEW"}:
        return initial["planning_status"], reasons, 0.0
    lower_wet, upper_wet = max(0.0, lower - rain_net), max(0.0, upper - rain_net)
    if lower_wet <= initial["raw_mm"] + SCREENING_TOLERANCE_MM and upper_wet >= initial["raw_mm"] - SCREENING_TOLERANCE_MM:
        return "REVIEW", ["threshold_screening_overlap"], 0.0
    request = max(0.0, max(0.0, nominal - rain_net) - zone["target_depletion_mm"]) if lower_wet > initial["raw_mm"] + SCREENING_TOLERANCE_MM else 0.0
    return "READY", reasons, request


def simulate(request: dict) -> dict:
    request = validate_request(request)
    telemetry = [inspect_telemetry(row, as_of=request["as_of"], max_age_hours=request["max_age_hours"])
                 for row in request["telemetry"]]
    initial_zones = [fuse_zone(zone, as_of=request["as_of"], max_age_hours=request["max_age_hours"],
                               coverage_factor=request["coverage_factor"], priority_index=index)
                     for index, zone in enumerate(request["zones"])]
    for initial in initial_zones:
        provided = [row for row in telemetry if row["zone_id"] == initial["zone_id"]]
        if any(row["quality_status"] == "ABSTAIN" for row in provided):
            initial["planning_status"] = "ABSTAIN"
            initial["reasons"].append("telemetry_quality_hold")
        if any(row["indicators"] for row in provided):
            if initial["planning_status"] != "ABSTAIN":
                initial["planning_status"] = "REVIEW"
            initial["reasons"].append("telemetry_discrepancy")
        initial["projection_is_descriptive_only"] = initial["planning_status"] in {"ABSTAIN", "REVIEW"}
    states = [(row["depletion_mm"], row["screening_lower_mm"], row["screening_upper_mm"])
              for row in initial_zones]
    pump = request["pump"]
    days = []
    for weather in request["weather"]:
        et0 = reference_et0(weather)
        capacity = min(pump["water_budget_m3_per_day"], pump["rate_m3_h"] * pump["available_hours_per_day"])
        remaining = capacity
        rows = []
        next_states = []
        for zone, initial, current in zip(request["zones"], initial_zones, states):
            nominal, lower, upper = current
            rain_net = weather["rainfall_mm"] - weather["runoff_mm"] + zone["capillary_rise_mm_per_day"]
            status, reasons, desired_net = _decision(zone, initial, current, rain_net)
            # Depth(mm)*area(m2)/1000 converts net water to m3; efficiency is net/gross.
            gross_per_mm = zone["area_m2"] / (1000.0 * pump["efficiency"])
            desired_gross = desired_net * gross_per_mm
            allowed_net = min(desired_net, zone["max_daily_net_mm"])
            allocated_gross = min(allowed_net * gross_per_mm, remaining)
            allocated_net = allocated_gross / gross_per_mm
            # Avoid an extra roundoff-generated mismatch when the full desired depth is met.
            if allocated_gross == desired_gross:
                allocated_net = desired_net
            remaining = max(0.0, remaining - allocated_gross)
            unmet_net = max(0.0, desired_net - allocated_net)
            if unmet_net > ALLOCATION_ABSOLUTE_TOLERANCE_MM:
                status = "UNMET"
                if desired_net - allowed_net > ALLOCATION_ABSOLUTE_TOLERANCE_MM:
                    reasons.append("zone_daily_limit_shortfall")
                if allowed_net - allocated_net > ALLOCATION_ABSOLUTE_TOLERANCE_MM:
                    reasons.append("budget_shortfall")
            wetting = rain_net + allocated_net
            potential_crop_et = zone["crop_coefficient"] * et0
            kwargs = {"taw": initial["taw_mm"], "raw": initial["raw_mm"],
                      "potential_crop_et": potential_crop_et, "wetting": wetting}
            step = bucket_step(nominal, **kwargs)
            lower_end = bucket_step(lower, **kwargs)["depletion_end_mm"]
            upper_end = bucket_step(upper, **kwargs)["depletion_end_mm"]
            if not lower_end <= step["depletion_end_mm"] <= upper_end:
                if (lower_end - step["depletion_end_mm"] > 1e-9
                        or step["depletion_end_mm"] - upper_end > 1e-9):
                    raise ValueError("Conditional screening endpoint ordering differs")
                lower_end = min(lower_end, step["depletion_end_mm"])
                upper_end = max(upper_end, step["depletion_end_mm"])
            rows.append({
                "zone_id": zone["zone_id"], "planning_status": status, "reasons": reasons,
                "depletion_start_mm": nominal, "screening_lower_start_mm": lower,
                "screening_upper_start_mm": upper, "requested_net_mm": desired_net,
                "allocated_net_mm": allocated_net, "requested_gross_m3": desired_gross,
                "allocated_gross_m3": allocated_gross, "unmet_net_mm": unmet_net,
                "rainfall_mm": weather["rainfall_mm"], "runoff_mm": weather["runoff_mm"],
                "capillary_rise_mm": zone["capillary_rise_mm_per_day"], "wetting_net_mm": wetting,
                "potential_crop_et_mm": potential_crop_et, **step,
                "screening_lower_end_mm": lower_end, "screening_upper_end_mm": upper_end,
                "projection_is_descriptive_only": status in {"ABSTAIN", "REVIEW"},
            })
            next_states.append((step["depletion_end_mm"], lower_end, upper_end))
        allocated = math.fsum(row["allocated_gross_m3"] for row in rows)
        days.append({
            "date": weather["date"], "et0_mm": et0, "available_gross_m3": capacity,
            "allocated_gross_m3": allocated, "remaining_gross_m3": remaining,
            "pump_hours": allocated / pump["rate_m3_h"],
            "unmet_gross_m3": math.fsum(row["unmet_net_mm"] * zone["area_m2"] / (1000.0 * pump["efficiency"])
                                        for row, zone in zip(rows, request["zones"])), "zones": rows,
        })
        states = next_states
    statuses = [row["planning_status"] for row in initial_zones]
    statuses.extend(row["planning_status"] for day in days for row in day["zones"])
    aggregate = next(status for status in ("ABSTAIN", "REVIEW", "UNMET", "READY") if status in statuses)
    result = seal({
        "schema": RESULT_SCHEMA, "request_digest": digest(request), "scope": SCOPE,
        "provider": PROVIDER_ID, "method": METHOD_ID, "source": deepcopy(request["source"]),
        "as_of": request["as_of"], "units": deepcopy(UNITS), "model_conventions": deepcopy(MODEL_CONVENTIONS),
        "coverage_factor": request["coverage_factor"], "uncertainty_scope": UNCERTAINTY_SCOPE,
        "physical_validation": "not_assessed", "canonical_admission": False, "actuation": "none",
        "planning_status": aggregate, "initial_zones": initial_zones, "days": days,
        "telemetry": telemetry,
    })
    return validate_result(request, result)
