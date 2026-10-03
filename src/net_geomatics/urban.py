"""Descriptive area indicators and declared-time accessibility references.

Areas must be disjoint and population/events must share a declared observational
frame upstream. These numerical summaries support policy analysis; they do not
establish causality, individual characteristics, or facility capacity sufficiency.
"""
import math

from .common import MAX_CELLS, keys, number, text, output_number

_INDICATOR_LIMITATIONS = [
    "Descriptive area aggregates only; no causal or individual-level inference.",
    "Inputs must represent disjoint areas with comparable population/event periods and definitions.",
    "Zero denominators return null, including zero divided by zero; totals use summed denominators.",
    "Area aggregation and boundary choices can change the indicators (modifiable areal unit problem).",
]
_ACCESSIBILITY_LIMITATIONS = [
    "Population-weighted potential accessibility from supplied travel times; cutoff is inclusive.",
    "Null times mean unreachable; the mean time denominator includes reachable population only.",
    "No routing, congestion, facility capacity, service quality, causal or individual-level inference.",
    "Each area's supplied travel times stand for its entire population; within-area differences are unresolved.",
]


def _nonnegative(value, name):
    value = number(value)
    if value < 0:
        raise ValueError(name + " must be nonnegative")
    return value


def _count(value, name):
    if type(value) in (int, float) and value > 2**53 - 1:
        raise ValueError(name + " exceeds exact numeric count range")
    value = _nonnegative(value, name)
    if not value.is_integer():
        raise ValueError(name + " must be an integer count")
    return int(value)


def _rows(value):
    if type(value) is not list or not value or len(value) > MAX_CELLS:
        raise ValueError("rows must be a nonempty list with at most 65536 entries")
    return value


def _identity(row, seen):
    area_id = text(row["area_id"])
    if area_id in seen:
        raise ValueError("Duplicate area_id; disjoint unique areas are required")
    seen.add(area_id)
    return area_id


def _ratio(numerator, denominator, scale=1.0):
    if denominator == 0:
        return None
    value = numerator / denominator * scale
    if not math.isfinite(value) or value > 1e150:
        raise ValueError("Indicator exceeds retained output numeric range")
    return value


def _indicator(population, area, events, rate_per):
    return {
        "population": population,
        "area_km2": area,
        "event_count": events,
        "population_density_per_km2": _ratio(population, area),
        "density_status": "undefined_zero_area" if area == 0 else "defined",
        "event_rate": _ratio(events, population, rate_per),
        "event_rate_status": "undefined_zero_population" if population == 0 else "defined",
    }


def indicators(params):
    keys(params, {"rows", "rate_per"})
    rate_per = _nonnegative(params["rate_per"], "rate_per")
    if rate_per == 0:
        raise ValueError("rate_per must be positive")
    rows = []
    seen = set()
    for row in _rows(params["rows"]):
        keys(row, {"area_id", "population", "area_km2", "event_count"})
        area_id = _identity(row, seen)
        population = _count(row["population"], "population")
        area = _nonnegative(row["area_km2"], "area_km2")
        events = _count(row["event_count"], "event_count")
        rows.append({"area_id": area_id, **_indicator(population, area, events, rate_per)})
    totals = _indicator(
        sum(row["population"] for row in rows),
        math.fsum(row["area_km2"] for row in rows),
        sum(row["event_count"] for row in rows), rate_per)
    return {
        "areas": rows,
        "totals": totals,
        "rate_per": rate_per,
        "limitations": list(_INDICATOR_LIMITATIONS),
    }


def accessibility(params):
    keys(params, {"rows", "cutoff_min"})
    cutoff = _nonnegative(params["cutoff_min"], "cutoff_min")
    rows = []
    seen = set()
    width = None
    source_rows = _rows(params["rows"])
    for row in source_rows:
        keys(row, {"area_id", "population", "travel_times_min"})
        area_id = _identity(row, seen)
        population = _count(row["population"], "population")
        times = row["travel_times_min"]
        if type(times) is not list or not times:
            raise ValueError("travel_times_min must be a nonempty list; null denotes unreachable")
        if width is None:
            width = len(times)
        if len(times) != width or width * len(source_rows) > MAX_CELLS:
            raise ValueError("Require rectangular travel-time matrix with at most 65536 cells")
        reachable = [_nonnegative(t, "travel time") for t in times if t is not None]
        nearest = min(reachable) if reachable else None
        rows.append({
            "area_id": area_id,
            "population": population,
            "nearest_time_min": nearest,
            "served": nearest is not None and nearest <= cutoff,
        })
    population = sum(row["population"] for row in rows)
    served = sum(row["population"] for row in rows if row["served"])
    reachable = sum(row["population"] for row in rows if row["nearest_time_min"] is not None)
    weighted_time = math.fsum(row["population"] * row["nearest_time_min"]
                              for row in rows if row["nearest_time_min"] is not None)
    return {
        "areas": rows,
        "cutoff_min": cutoff,
        "facility_count": width,
        "total_population": population,
        "served_population": served,
        "reachable_population": reachable,
        "served_fraction": _ratio(served, population),
        "served_fraction_status": "undefined_zero_population" if population == 0 else "defined",
        "mean_nearest_time_reachable_min": _ratio(weighted_time, reachable),
        "limitations": list(_ACCESSIBILITY_LIMITATIONS),
    }


OPERATIONS = {
    "geomatics.urban.indicators.v1": indicators,
    "geomatics.urban.accessibility.v1": accessibility,
}
EXAMPLES = {
    "geomatics.urban.indicators.v1": {
        "rows": [
            {"area_id": "synthetic-A", "population": 1000, "area_km2": 2.0, "event_count": 25},
            {"area_id": "synthetic-B", "population": 500, "area_km2": 0.5, "event_count": 5},
        ],
        "rate_per": 1000,
    },
    "geomatics.urban.accessibility.v1": {
        "rows": [
            {"area_id": "synthetic-A", "population": 1000, "travel_times_min": [10.0, 25.0]},
            {"area_id": "synthetic-B", "population": 500, "travel_times_min": [30.0, None]},
        ],
        "cutoff_min": 15.0,
    },
}
DESCRIPTIONS = {
    "geomatics.urban.indicators.v1": "Denominator-aware area population densities and event rates",
    "geomatics.urban.accessibility.v1": "Population-weighted accessibility from declared travel times",
}


def _output_number(value, name):
    if output_number(value) < 0:
        raise ValueError("Invalid retained " + name)


def _output_ratio(value, denominator, name):
    if denominator == 0:
        if value is not None:
            raise ValueError("Zero denominator requires null " + name)
    else:
        _output_number(value, name)


def _output_areas(params, output):
    source = _rows(params["rows"])
    if type(output["areas"]) is not list or len(output["areas"]) != len(source):
        raise ValueError("Retained area count does not match parameters")
    seen = set()
    for original, retained in zip(source, output["areas"]):
        if type(original) is not dict or type(retained) is not dict or "area_id" not in original:
            raise ValueError("Retained and input areas must be objects with identities")
        if retained.get("area_id") != _identity(original, seen):
            raise ValueError("Retained area identity does not match parameters")
    return source


def _validate_indicator_values(original, retained):
    for name in ("population", "area_km2", "event_count"):
        _output_number(retained[name], name)
        if retained[name] != original[name]:
            raise ValueError("Retained area value does not match input: " + name)
    _output_ratio(retained["population_density_per_km2"], retained["area_km2"], "density")
    _output_ratio(retained["event_rate"], retained["population"], "event_rate")
    if retained["density_status"] != ("undefined_zero_area" if retained["area_km2"] == 0 else "defined"):
        raise ValueError("Invalid retained density status")
    if retained["event_rate_status"] != ("undefined_zero_population" if retained["population"] == 0 else "defined"):
        raise ValueError("Invalid retained event-rate status")


def validate_indicators(params, output):
    keys(params, {"rows", "rate_per"})
    keys(output, {"areas", "totals", "rate_per", "limitations"})
    if _nonnegative(params["rate_per"], "rate_per") == 0:
        raise ValueError("rate_per must be positive")
    _output_number(output["rate_per"], "rate_per")
    if output["rate_per"] != params["rate_per"] or output["limitations"] != _INDICATOR_LIMITATIONS:
        raise ValueError("Invalid retained rate scale or limitations")
    source = _output_areas(params, output)
    fields = {"population", "area_km2", "event_count", "population_density_per_km2", "density_status", "event_rate", "event_rate_status"}
    for original, retained in zip(source, output["areas"]):
        keys(original, {"area_id", "population", "area_km2", "event_count"})
        _count(original["population"], "population")
        _count(original["event_count"], "event_count")
        _nonnegative(original["area_km2"], "area_km2")
        keys(retained, fields | {"area_id"})
        _validate_indicator_values(original, retained)
    keys(output["totals"], fields)
    declared_totals = {
        "population": sum(int(row["population"]) for row in source),
        "event_count": sum(int(row["event_count"]) for row in source),
        "area_km2": math.fsum(row["area_km2"] for row in source),
    }
    _validate_indicator_values(declared_totals, output["totals"])


def validate_accessibility(params, output):
    keys(params, {"rows", "cutoff_min"})
    keys(output, {"areas", "cutoff_min", "facility_count", "total_population", "served_population", "reachable_population", "served_fraction", "served_fraction_status", "mean_nearest_time_reachable_min", "limitations"})
    _nonnegative(params["cutoff_min"], "cutoff_min")
    _output_number(output["cutoff_min"], "cutoff_min")
    if output["cutoff_min"] != params["cutoff_min"] or output["limitations"] != _ACCESSIBILITY_LIMITATIONS:
        raise ValueError("Invalid retained cutoff or limitations")
    source = _output_areas(params, output)
    width = None
    for original, retained in zip(source, output["areas"]):
        keys(original, {"area_id", "population", "travel_times_min"})
        _count(original["population"], "population")
        times = original["travel_times_min"]
        if type(times) is not list or not times:
            raise ValueError("Require nonempty travel-time rows")
        if width is None:
            width = len(times)
        if len(times) != width or width * len(source) > MAX_CELLS:
            raise ValueError("Require bounded rectangular travel-time matrix")
        reachable_times = [_nonnegative(t, "travel time") for t in times if t is not None]
        keys(retained, {"area_id", "population", "nearest_time_min", "served"})
        _output_number(retained["population"], "population")
        if retained["population"] != original["population"] or type(retained["served"]) is not bool:
            raise ValueError("Invalid retained population or served flag")
        nearest = retained["nearest_time_min"]
        if nearest is None:
            if reachable_times:
                raise ValueError("Reachable area cannot have null nearest time")
        else:
            _output_number(nearest, "nearest_time_min")
            if nearest not in reachable_times:
                raise ValueError("Retained nearest time absent from declared travel times")
        if retained["served"] != (nearest is not None and nearest <= params["cutoff_min"]):
            raise ValueError("Invalid retained served status")
    if type(output["facility_count"]) is not int or output["facility_count"] != width:
        raise ValueError("Invalid retained facility count")
    declared = {
        "total_population": sum(row["population"] for row in output["areas"]),
        "served_population": sum(row["population"] for row in output["areas"] if row["served"]),
        "reachable_population": sum(row["population"] for row in output["areas"] if row["nearest_time_min"] is not None),
    }
    for name, expected in declared.items():
        _output_number(output[name], name)
        if output[name] != expected:
            raise ValueError("Invalid retained " + name)
    _output_ratio(output["served_fraction"], output["total_population"], "served_fraction")
    if output["served_fraction"] is not None and output["served_fraction"] > 1:
        raise ValueError("Served fraction must be at most one")
    _output_ratio(output["mean_nearest_time_reachable_min"], output["reachable_population"], "mean_nearest_time_reachable_min")
    status = "undefined_zero_population" if output["total_population"] == 0 else "defined"
    if output["served_fraction_status"] != status:
        raise ValueError("Invalid retained served-fraction status")


OUTPUT_VALIDATORS = {
    "geomatics.urban.indicators.v1": validate_indicators,
    "geomatics.urban.accessibility.v1": validate_accessibility,
}
