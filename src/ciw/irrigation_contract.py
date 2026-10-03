"""Data boundaries for bounded daily root-zone irrigation planning.

Reading a result checks declarations and its content seal. It never estimates a
soil state, executes the bucket model, verifies numerical equations or actuates.
The measurements and calibration references are declarations, not accreditation.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta
import math
import re

from .control_contracts import json_tree, keys, number
from .operations.runner import check_seal, digest

REQUEST_SCHEMA = "ciw.irrigation-request.v1"
RESULT_SCHEMA = "ciw.irrigation-result.v1"
REPORT_SCHEMA = "ciw.irrigation-numerical-verification.v1"
SCOPE = "daily_root_zone_bucket_fao56_v1"
CLAIM_SCOPE = SCOPE
OPERATION_ID = "irrigation.plan.v1"
PROVIDER_ID = "irrigation_daily_bucket_gls_binary64.v1"
METHOD_ID = "fao56_daily_et0_early_wetting_same_day_drainage_priority_budget"
MAX_ZONES = 16
MAX_DAYS = 7
MAX_OBSERVATIONS = 8
MAX_TELEMETRY = 64
PLANNING_STATUSES = {"READY", "REVIEW", "ABSTAIN", "UNMET"}
MEASURAND = "root_zone_mean_volumetric_water_content"
UNCERTAINTY_SCOPE = "initial_soil_only_conditional_fixed_parameters_and_weather"
SCREENING_TOLERANCE_MM = 1e-9
THETA_DOMAIN_TOLERANCE = 1e-12
UNITS = {
    "soil_water_content": "m^3/m^3", "soil_covariance": "(m^3/m^3)^2",
    "root_depth": "m", "area": "m^2", "water_depth": "mm",
    "water_volume": "m^3", "flow": "m^3/h", "pressure": "kPa",
    "temperature": "degC", "wind_speed_at_2m": "m/s",
    "net_radiation_and_soil_heat_flux": "MJ/m^2/day", "vapour_pressure": "kPa",
    "time_step": "86400 s", "pump_time": "h",
}
MODEL_CONVENTIONS = {
    "time_step": "daily_86400s", "wetting": "early_day",
    "drainage": "same_day_excess_after_et", "stress": "single_crop_coefficient",
    "allocation_policy": "zone_list_order",
    "screening_interval": "propagated_initial_k_u_endpoints_same_allocated_irrigation",
    "forecast_confidence": "not_assessed", "parameter_and_weather_uncertainty": "not_propagated",
    "screening_comparison_absolute_tolerance_mm": SCREENING_TOLERANCE_MM,
    "initial_theta_domain_absolute_tolerance": THETA_DOMAIN_TOLERANCE,
    "allocation_shortfall_absolute_tolerance_mm": 1e-9,
    "covariance_cholesky_minimum_pivot_relative": 1e-12,
    "soil_covariance_minimum_scale": 1e-16,
}
WEATHER_FIELDS = {
    "date", "weather_ref", "temp_min_c", "temp_max_c", "temp_mean_c",
    "pressure_kpa", "net_radiation_mj_m2_day", "soil_heat_flux_mj_m2_day",
    "wind_2m_m_s", "saturation_vapour_pressure_kpa", "actual_vapour_pressure_kpa",
    "rainfall_mm", "runoff_mm",
}
ZONE_FIELDS = {
    "zone_id", "parameter_ref", "area_m2", "theta_fc", "theta_wp", "root_depth_m",
    "crop_coefficient", "depletion_fraction", "target_depletion_mm", "max_daily_net_mm",
    "capillary_rise_mm_per_day", "soil_measurements",
}
OBSERVATION_FIELDS = {
    "observation_id", "calibrated_theta_m3_m3", "calibration_ref", "clock_ref",
    "observed_at", "calibrated_until",
}
TELEMETRY_FIELDS = {
    "telemetry_id", "zone_id", "observed_at", "calibrated_until", "calibration_ref", "clock_ref",
    "commanded_open", "expected_flow_m3_h", "observed_flow_m3_h", "flow_tolerance_m3_h",
    "expected_pressure_kpa", "observed_pressure_kpa", "pressure_tolerance_kpa",
}
INITIAL_FIELDS = {
    "zone_id", "priority_index", "planning_status", "reasons", "fused_theta_m3_m3",
    "fused_variance_m3_m3_squared", "fused_standard_uncertainty_m3_m3", "fusion_weights",
    "taw_mm", "raw_mm", "depletion_mm", "standard_uncertainty_mm",
    "screening_lower_mm", "screening_upper_mm", "projection_is_descriptive_only",
}
DAY_FIELDS = {
    "date", "et0_mm", "available_gross_m3", "allocated_gross_m3", "remaining_gross_m3",
    "pump_hours", "unmet_gross_m3", "zones",
}
DAY_ZONE_FIELDS = {
    "zone_id", "planning_status", "reasons", "depletion_start_mm", "screening_lower_start_mm",
    "screening_upper_start_mm", "requested_net_mm", "allocated_net_mm", "requested_gross_m3",
    "allocated_gross_m3", "unmet_net_mm", "rainfall_mm", "runoff_mm", "capillary_rise_mm",
    "wetting_net_mm", "stress_coefficient", "potential_crop_et_mm", "actual_crop_et_mm",
    "unmet_crop_et_mm", "deep_percolation_mm", "depletion_end_mm", "screening_lower_end_mm",
    "screening_upper_end_mm", "balance_residual_mm", "projection_is_descriptive_only",
}
TELEMETRY_RESULT_FIELDS = {
    "telemetry_id", "zone_id", "quality_status", "reasons", "flow_residual_m3_h",
    "pressure_residual_kpa", "indicators",
}
TELEMETRY_INDICATORS = {
    "unexpected_flow_while_closed", "flow_above_expectation", "flow_below_expectation",
    "pressure_above_expectation", "pressure_below_expectation",
}


def _bounded(value, lower, upper, label):
    value = number(value)
    if not lower <= value <= upper:
        raise ValueError(f"{label} must be inside {lower}..{upper}")
    return value


def _text(value, label="reference", maximum=160):
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise ValueError(f"Require a bounded nonempty {label}")
    return value


def _identifier(value, label="identifier"):
    if type(value) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}", value) is None:
        raise ValueError(f"Require a bounded ASCII {label}")
    return value


def _enum(value, choices, label):
    if type(value) is not str or value not in choices:
        raise ValueError("Unsupported " + label)


def utc_datetime(value):
    """Require an explicit canonical UTC timestamp, without wall-clock access."""
    if type(value) is not str or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", value) is None:
        raise ValueError("Require an ISO UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("Invalid ISO UTC timestamp") from exc
    if not 1900 <= parsed.year <= 2200:
        raise ValueError("Timestamp outside bounded 1900..2200 model domain")
    return parsed


def _date(value):
    if type(value) is not str or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None:
        raise ValueError("Require a calendar date YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Invalid calendar date") from exc


def covariance_cholesky(covariance, count):
    """Check a bounded SPD declaration using a small dependency-free Cholesky."""
    if type(covariance) is not list or len(covariance) != count:
        raise ValueError("Soil covariance must match the observation count")
    if any(type(row) is not list or len(row) != count for row in covariance):
        raise ValueError("Soil covariance must be square")
    for i in range(count):
        for j in range(count):
            _bounded(covariance[i][j], -1.0, 1.0, "soil covariance")
            if covariance[i][j] != covariance[j][i]:
                raise ValueError("Soil covariance must be exactly symmetric")
        if covariance[i][i] <= 0:
            raise ValueError("Soil covariance diagonal must be positive")
    scale = max(covariance[i][i] for i in range(count))
    if scale < 1e-16:
        raise ValueError("Soil covariance is below the declared numerical resolution")
    factor = [[0.0] * count for _ in range(count)]
    for i in range(count):
        for j in range(i + 1):
            residual = covariance[i][j] - math.fsum(factor[i][k] * factor[j][k] for k in range(j))
            if i == j:
                if residual <= 1e-12 * scale:
                    raise ValueError("Require positive-definite soil covariance within the conditioning budget")
                factor[i][j] = math.sqrt(residual)
            else:
                factor[i][j] = residual / factor[j][j]
    return factor


def validate_request(request: dict) -> dict:
    """Check finite declarations; stale evidence remains representable for abstention."""
    json_tree(request)
    keys(request, {"schema", "scope", "source", "as_of", "max_age_hours", "coverage_factor",
                   "weather", "zones", "pump", "telemetry"})
    if request["schema"] != REQUEST_SCHEMA or request["scope"] != SCOPE:
        raise ValueError("Unsupported irrigation schema or model scope")
    keys(request["source"], {"kind", "source_ref"})
    _enum(request["source"]["kind"], {"synthetic", "declared_measurements"}, "irrigation source kind")
    _text(request["source"]["source_ref"], "source reference")
    as_of = utc_datetime(request["as_of"])
    if any((as_of.hour, as_of.minute, as_of.second, as_of.microsecond)):
        raise ValueError("Daily planning requires as_of at UTC midnight")
    _bounded(request["max_age_hours"], 0.001, 168.0, "max_age_hours")
    if number(request["coverage_factor"]) != 2.0:
        raise ValueError("This model declares coverage_factor=2 without a coverage probability")
    weather = request["weather"]
    if type(weather) is not list or not 1 <= len(weather) <= MAX_DAYS:
        raise ValueError("Require 1..7 daily weather rows")
    for index, row in enumerate(weather):
        keys(row, WEATHER_FIELDS)
        expected_date = (as_of.date() + timedelta(days=index)).isoformat()
        if _date(row["date"]).isoformat() != expected_date:
            raise ValueError("Weather dates must be contiguous beginning on the as_of UTC date")
        _text(row["weather_ref"], "weather reference")
        low = _bounded(row["temp_min_c"], 0.0, 50.0, "temp_min_c")
        high = _bounded(row["temp_max_c"], 0.0, 50.0, "temp_max_c")
        mean = _bounded(row["temp_mean_c"], 0.0, 50.0, "temp_mean_c")
        if high < low or abs(mean - (low + high) / 2) > 1e-10:
            raise ValueError("Daily temperature mean must equal (Tmin+Tmax)/2 within the declared tolerance")
        _bounded(row["pressure_kpa"], 50.0, 110.0, "pressure_kpa")
        _bounded(row["net_radiation_mj_m2_day"], 0.0, 40.0, "net_radiation_mj_m2_day")
        _bounded(row["soil_heat_flux_mj_m2_day"], -10.0, 10.0, "soil_heat_flux_mj_m2_day")
        if row["net_radiation_mj_m2_day"] < row["soil_heat_flux_mj_m2_day"]:
            raise ValueError("Daily net available radiation must be nonnegative in this model")
        _bounded(row["wind_2m_m_s"], 0.0, 20.0, "wind_2m_m_s")
        es = _bounded(row["saturation_vapour_pressure_kpa"], 0.01, 15.0, "saturation_vapour_pressure_kpa")
        expected_es = math.fsum(0.6108 * math.exp(17.27 * t / (t + 237.3)) for t in (low, high)) / 2.0
        if not math.isclose(es, expected_es, rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError("Declared saturation vapour pressure must match the FAO56 extrema calculation")
        _bounded(row["actual_vapour_pressure_kpa"], 0.0, es, "actual_vapour_pressure_kpa")
        rain = _bounded(row["rainfall_mm"], 0.0, 500.0, "rainfall_mm")
        _bounded(row["runoff_mm"], 0.0, rain, "runoff_mm")
    zones = request["zones"]
    if type(zones) is not list or not 1 <= len(zones) <= MAX_ZONES:
        raise ValueError("Require 1..16 zones; list order declares allocation priority")
    zone_ids, observation_ids = set(), set()
    for zone in zones:
        keys(zone, ZONE_FIELDS)
        identifier = _identifier(zone["zone_id"], "zone identifier")
        if identifier in zone_ids:
            raise ValueError("Zone identifiers must be unique")
        zone_ids.add(identifier)
        _text(zone["parameter_ref"], "soil/crop/geometry parameter reference")
        _bounded(zone["area_m2"], 0.01, 1e8, "area_m2")
        fc = _bounded(zone["theta_fc"], 0.001, 0.8, "theta_fc")
        wp = _bounded(zone["theta_wp"], 0.0, 0.799, "theta_wp")
        if fc - wp < 0.001:
            raise ValueError("Require theta_fc-theta_wp >=0.001")
        root = _bounded(zone["root_depth_m"], 0.01, 3.0, "root_depth_m")
        _bounded(zone["crop_coefficient"], 0.0, 2.0, "crop_coefficient")
        p = _bounded(zone["depletion_fraction"], 0.1, 0.8, "depletion_fraction")
        taw = 1000.0 * (fc - wp) * root
        _bounded(zone["target_depletion_mm"], 0.0, p * taw, "target_depletion_mm")
        _bounded(zone["max_daily_net_mm"], 0.0, taw, "max_daily_net_mm")
        _bounded(zone["capillary_rise_mm_per_day"], 0.0, 50.0, "capillary_rise_mm_per_day")
        measured = zone["soil_measurements"]
        keys(measured, {"measurand", "unit", "covariance_unit", "observations", "covariance"})
        if (measured["measurand"] != MEASURAND or measured["unit"] != UNITS["soil_water_content"]
                or measured["covariance_unit"] != UNITS["soil_covariance"]):
            raise ValueError("Require calibrated replicates of the same declared root-zone mean and explicit covariance units")
        observations = measured["observations"]
        if type(observations) is not list or not 1 <= len(observations) <= MAX_OBSERVATIONS:
            raise ValueError("Require 1..8 calibrated root-zone mean observations per zone")
        for observation in observations:
            keys(observation, OBSERVATION_FIELDS)
            oid = _identifier(observation["observation_id"], "observation identifier")
            if oid in observation_ids:
                raise ValueError("Observation identifiers must be globally unique")
            observation_ids.add(oid)
            _bounded(observation["calibrated_theta_m3_m3"], 0.0, 1.0, "calibrated_theta_m3_m3")
            for field in ("calibration_ref", "clock_ref"):
                _text(observation[field], field)
            utc_datetime(observation["observed_at"])
            utc_datetime(observation["calibrated_until"])
        covariance_cholesky(measured["covariance"], len(observations))
    pump = request["pump"]
    keys(pump, {"rate_m3_h", "available_hours_per_day", "water_budget_m3_per_day", "efficiency", "parameter_ref"})
    _bounded(pump["rate_m3_h"], 0.001, 1e6, "pump.rate_m3_h")
    _bounded(pump["available_hours_per_day"], 0.0, 24.0, "pump.available_hours_per_day")
    _bounded(pump["water_budget_m3_per_day"], 0.0, 1e8, "pump.water_budget_m3_per_day")
    _bounded(pump["efficiency"], 1e-6, 1.0, "pump.efficiency")
    _text(pump["parameter_ref"], "pump parameter reference")
    telemetry = request["telemetry"]
    if type(telemetry) is not list or len(telemetry) > MAX_TELEMETRY:
        raise ValueError("Telemetry must be a bounded list of at most 64 declarations")
    tids = set()
    for row in telemetry:
        keys(row, TELEMETRY_FIELDS)
        tid = _identifier(row["telemetry_id"], "telemetry identifier")
        if tid in tids:
            raise ValueError("Telemetry identifiers must be unique")
        tids.add(tid)
        _identifier(row["zone_id"], "telemetry zone identifier")
        if row["zone_id"] not in zone_ids:
            raise ValueError("Telemetry must refer to a declared zone")
        if type(row["commanded_open"]) is not bool:
            raise ValueError("commanded_open must be a boolean")
        for field in ("observed_at", "calibrated_until"):
            utc_datetime(row[field])
        for field in ("calibration_ref", "clock_ref"):
            _text(row[field], field)
        for field in ("expected_flow_m3_h", "observed_flow_m3_h", "flow_tolerance_m3_h"):
            _bounded(row[field], 0.0, 1e6, field)
        for field in ("expected_pressure_kpa", "observed_pressure_kpa", "pressure_tolerance_kpa"):
            _bounded(row[field], 0.0, 2000.0, field)
        if not row["commanded_open"] and row["expected_flow_m3_h"] != 0.0:
            raise ValueError("A closed command requires declared expected flow=0")
    return deepcopy(request)


def _reasons(value):
    if type(value) is not list or len(value) > 16:
        raise ValueError("Reasons must be a bounded list")
    for item in value:
        _text(item, "reason", 128)
    if len(set(value)) != len(value):
        raise ValueError("Reasons must be nonrepeated")


def validate_result(request: dict, result: dict) -> dict:
    """STRUCTURAL ONLY: identities, bounds and seals; no fusion or equation replay."""
    request = validate_request(request)
    json_tree(result)
    keys(result, {"schema", "request_digest", "scope", "provider", "method", "source", "as_of", "units",
                  "model_conventions", "coverage_factor", "uncertainty_scope", "physical_validation",
                  "canonical_admission", "actuation", "planning_status", "initial_zones", "days", "telemetry", "record_digest"})
    fixed = {
        "schema": RESULT_SCHEMA, "request_digest": digest(request), "scope": SCOPE,
        "provider": PROVIDER_ID, "method": METHOD_ID, "source": request["source"],
        "as_of": request["as_of"], "units": UNITS, "model_conventions": MODEL_CONVENTIONS,
        "coverage_factor": request["coverage_factor"], "uncertainty_scope": UNCERTAINTY_SCOPE,
        "physical_validation": "not_assessed", "actuation": "none",
    }
    for field, expected in fixed.items():
        if result[field] != expected:
            raise ValueError("Stored irrigation declaration differs: " + field)
    if type(result["canonical_admission"]) is not bool or result["canonical_admission"]:
        raise ValueError("Irrigation planning cannot perform canonical admission")
    _enum(result["planning_status"], PLANNING_STATUSES, "aggregate planning status")
    number(result["coverage_factor"])
    keys(result["source"], {"kind", "source_ref"})
    keys(result["units"], set(UNITS))
    keys(result["model_conventions"], set(MODEL_CONVENTIONS))
    initials = result["initial_zones"]
    if type(initials) is not list or len(initials) != len(request["zones"]):
        raise ValueError("Stored initial zones must cover the declared zones")
    for index, (zone, row) in enumerate(zip(request["zones"], initials)):
        keys(row, INITIAL_FIELDS)
        if row["zone_id"] != zone["zone_id"] or type(row["priority_index"]) is not int or row["priority_index"] != index:
            raise ValueError("Stored initial zone identity/priority differs")
        _enum(row["planning_status"], PLANNING_STATUSES - {"UNMET"}, "initial planning status")
        _reasons(row["reasons"])
        if type(row["projection_is_descriptive_only"]) is not bool:
            raise ValueError("Require an explicit descriptive projection flag")
        for field in INITIAL_FIELDS - {"zone_id", "priority_index", "planning_status", "reasons", "fusion_weights", "projection_is_descriptive_only"}:
            _bounded(row[field], -1e12, 1e12, field)
        if row["fused_variance_m3_m3_squared"] <= 0 or row["fused_standard_uncertainty_m3_m3"] <= 0:
            raise ValueError("Stored fused uncertainty must be positive")
        for field in ("taw_mm", "raw_mm", "standard_uncertainty_mm"):
            if row[field] < 0:
                raise ValueError("Stored soil capacities and uncertainty must be nonnegative")
        if not 0 <= row["screening_lower_mm"] <= row["depletion_mm"] <= row["screening_upper_mm"] <= row["taw_mm"]:
            raise ValueError("Stored initial screening interval exceeds bucket bounds")
        weights = row["fusion_weights"]
        count = len(zone["soil_measurements"]["observations"])
        if type(weights) is not list or len(weights) != count:
            raise ValueError("Stored GLS weights must cover each declared observation")
        for weight in weights:
            _bounded(weight, -1e12, 1e12, "GLS weight")
    days = result["days"]
    if type(days) is not list or len(days) != len(request["weather"]):
        raise ValueError("Stored days must cover every declared weather row")
    for weather, day in zip(request["weather"], days):
        keys(day, DAY_FIELDS)
        if day["date"] != weather["date"]:
            raise ValueError("Stored day date differs")
        for field in DAY_FIELDS - {"date", "zones"}:
            _bounded(day[field], 0.0, 1e18, field)
        rows = day["zones"]
        if type(rows) is not list or len(rows) != len(request["zones"]):
            raise ValueError("Stored day must cover every declared zone in priority order")
        for initial, zone, row in zip(initials, request["zones"], rows):
            keys(row, DAY_ZONE_FIELDS)
            if row["zone_id"] != zone["zone_id"]:
                raise ValueError("Stored daily zone identity differs")
            _enum(row["planning_status"], PLANNING_STATUSES, "daily planning status")
            _reasons(row["reasons"])
            if type(row["projection_is_descriptive_only"]) is not bool:
                raise ValueError("Require an explicit descriptive projection flag")
            for field in DAY_ZONE_FIELDS - {"zone_id", "planning_status", "reasons", "projection_is_descriptive_only", "balance_residual_mm"}:
                _bounded(row[field], 0.0, 1e18, field)
            _bounded(row["balance_residual_mm"], -1e12, 1e12, "balance_residual_mm")
            _bounded(row["stress_coefficient"], 0.0, 1.0, "stress_coefficient")
            if not 0 <= row["screening_lower_start_mm"] <= row["depletion_start_mm"] <= row["screening_upper_start_mm"] <= initial["taw_mm"]:
                raise ValueError("Stored start screening interval exceeds bucket bounds")
            if not 0 <= row["screening_lower_end_mm"] <= row["depletion_end_mm"] <= row["screening_upper_end_mm"] <= initial["taw_mm"]:
                raise ValueError("Stored end screening interval exceeds bucket bounds")
    telemetry = result["telemetry"]
    if type(telemetry) is not list or len(telemetry) != len(request["telemetry"]):
        raise ValueError("Stored telemetry must cover every declared telemetry row")
    for declared, row in zip(request["telemetry"], telemetry):
        keys(row, TELEMETRY_RESULT_FIELDS)
        if row["telemetry_id"] != declared["telemetry_id"] or row["zone_id"] != declared["zone_id"]:
            raise ValueError("Stored telemetry identity differs")
        _enum(row["quality_status"], {"VALID", "ABSTAIN"}, "telemetry quality status")
        _reasons(row["reasons"])
        for field in ("flow_residual_m3_h", "pressure_residual_kpa"):
            _bounded(row[field], -1e12, 1e12, field)
        indicators = row["indicators"]
        if (type(indicators) is not list or len(indicators) > len(TELEMETRY_INDICATORS)
                or any(type(item) is not str or item not in TELEMETRY_INDICATORS for item in indicators)
                or len(set(indicators)) != len(indicators)):
            raise ValueError("Unsupported telemetry indicators")
    check_seal(result)
    return deepcopy(result)


def example_request() -> dict:
    """Synthetic two-zone example with declared FAO56 weather intermediates."""
    esat = lambda t: 0.6108 * math.exp(17.27 * t / (t + 237.3))
    weather = {
        "date": "2026-10-03", "weather_ref": "synthetic:fao56-example18-intermediates",
        "temp_min_c": 12.3, "temp_max_c": 21.5, "temp_mean_c": 16.9,
        "pressure_kpa": 101.3 * ((293.0 - 0.0065 * 100.0) / 293.0) ** 5.26,
        "net_radiation_mj_m2_day": 13.28, "soil_heat_flux_mj_m2_day": 0.0,
        "wind_2m_m_s": (10.0 / 3.6) * 4.87 / math.log(67.8 * 10.0 - 5.42),
        "saturation_vapour_pressure_kpa": (esat(12.3) + esat(21.5)) / 2.0,
        "actual_vapour_pressure_kpa": (esat(12.3) * 0.84 + esat(21.5) * 0.63) / 2.0,
        "rainfall_mm": 0.0, "runoff_mm": 0.0,
    }
    zones = []
    for identifier, reading in (("tomato-east", 0.22), ("tomato-west", 0.26)):
        zones.append({
            "zone_id": identifier, "parameter_ref": "synthetic:tomato-silty-soil-parameters",
            "area_m2": 1000.0, "theta_fc": 0.32, "theta_wp": 0.12, "root_depth_m": 0.8,
            "crop_coefficient": 1.2, "depletion_fraction": 0.4, "target_depletion_mm": 32.0,
            "max_daily_net_mm": 50.0, "capillary_rise_mm_per_day": 0.0,
            "soil_measurements": {
                "measurand": MEASURAND, "unit": UNITS["soil_water_content"],
                "covariance_unit": UNITS["soil_covariance"],
                "observations": [{
                    "observation_id": identifier + "-soil-1", "calibrated_theta_m3_m3": reading,
                    "calibration_ref": "synthetic:calibration-" + identifier,
                    "clock_ref": "synthetic:utc-model-clock", "observed_at": "2026-10-02T23:00:00Z",
                    "calibrated_until": "2026-11-01T00:00:00Z",
                }], "covariance": [[0.000004]],
            },
        })
    request = {
        "schema": REQUEST_SCHEMA, "scope": SCOPE,
        "source": {"kind": "synthetic", "source_ref": "synthetic:two-zone-irrigation-first-run"},
        "as_of": "2026-10-03T00:00:00Z", "max_age_hours": 6.0, "coverage_factor": 2.0,
        "weather": [dict(weather, date=(date(2026, 10, 3) + timedelta(days=i)).isoformat()) for i in range(3)],
        "zones": zones,
        "pump": {"rate_m3_h": 10.0, "available_hours_per_day": 6.0,
                 "water_budget_m3_per_day": 60.0, "efficiency": 0.8,
                 "parameter_ref": "synthetic:bounded-pump-and-application-efficiency"},
        "telemetry": [{
            "telemetry_id": "east-flow-closed", "zone_id": "tomato-east",
            "observed_at": "2026-10-02T23:30:00Z", "calibrated_until": "2026-11-01T00:00:00Z",
            "calibration_ref": "synthetic:flow-pressure-calibration", "clock_ref": "synthetic:utc-model-clock",
            "commanded_open": False, "expected_flow_m3_h": 0.0, "observed_flow_m3_h": 0.0,
            "flow_tolerance_m3_h": 0.1, "expected_pressure_kpa": 200.0,
            "observed_pressure_kpa": 180.0, "pressure_tolerance_kpa": 30.0,
        }],
    }
    return validate_request(request)
