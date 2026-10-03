"""Bounded GIS references with explicit units, frames and missing-data rules.

These operations do not silently assign a CRS, reproject data, transform a
vertical datum, interpolate missing cells or admit a result as verified state.
"""

import math

import numpy as np

from .common import (aligned, example_raster, keys, metric, number, output_number,
                     output_raster, raster, validate_assumptions, validate_output_raster)


WGS84_A_M = 6378137.0
WGS84_F = 1.0 / 298.257223563
_GEODETIC_KEYS = {"longitude_deg", "latitude_deg", "ellipsoid_height_m"}


def _geodetic(value):
    keys(value, _GEODETIC_KEYS)
    lon = number(value["longitude_deg"])
    lat = number(value["latitude_deg"])
    height = number(value["ellipsoid_height_m"])
    if not -180.0 <= lon <= 180.0 or not -90.0 <= lat <= 90.0:
        raise ValueError("Longitude must be [-180,180] and latitude [-90,90] degrees")
    if abs(height) > 1e7:
        raise ValueError("Ellipsoid height exceeds this reference's +/-10,000 km bound")
    return math.radians(lon), math.radians(lat), height


def _ecef(lon, lat, height):
    e2 = WGS84_F * (2.0 - WGS84_F)
    n = WGS84_A_M / math.sqrt(1.0 - e2 * math.sin(lat) ** 2)
    return np.array([
        (n + height) * math.cos(lat) * math.cos(lon),
        (n + height) * math.cos(lat) * math.sin(lon),
        (n * (1.0 - e2) + height) * math.sin(lat),
    ])


def coordinates_enu(parameters):
    """Convert WGS84 geodetic positions into ECEF and origin-fixed local ENU."""
    keys(parameters, {"origin", "points"})
    origin = _geodetic(parameters["origin"])
    points = parameters["points"]
    if type(points) is not list or not 1 <= len(points) <= 4096:
        raise ValueError("Require between 1 and 4096 point objects")
    locations = [_geodetic(point) for point in points]
    lon, lat, _ = origin
    rotation = np.array([
        [-math.sin(lon), math.cos(lon), 0.0],
        [-math.sin(lat) * math.cos(lon), -math.sin(lat) * math.sin(lon), math.cos(lat)],
        [math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat)],
    ])
    origin_ecef = _ecef(*origin)
    converted = []
    for location in locations:
        position = _ecef(*location)
        converted.append({"ecef_m": position.tolist(), "enu_m": (rotation @ (position - origin_ecef)).tolist()})
    return {
        "datum": "WGS84 ellipsoid",
        "origin_ecef_m": origin_ecef.tolist(),
        "points": converted,
        "assumptions": [
            "Input longitude/latitude are degrees; ellipsoid heights and outputs are metres.",
            "ECEF order is X,Y,Z; ENU order is east,north,up in one origin-fixed tangent frame.",
            "ENU is a Cartesian displacement, not a geodesic surface distance or map projection.",
            "No epoch, geoid, datum transformation or observational uncertainty is modeled.",
        ],
    }


def raster_zonal(parameters):
    """Population statistics for aligned integer zone labels and scalar values."""
    keys(parameters, {"values", "zones"})
    values, labels = aligned(parameters["values"], parameters["zones"])
    if parameters["zones"]["unit"] != "1":
        raise ValueError("Zone labels must use dimensionless unit '1'")
    labelled = np.isfinite(labels)
    finite_labels = labels[labelled]
    if np.any(finite_labels != np.floor(finite_labels)) or np.any(np.abs(finite_labels) > 2**53 - 1):
        raise ValueError("Zone labels must be exactly representable integers within +/- (2**53-1)")
    # Group once; one full-grid comparison per zone would make singleton-zone
    # rasters quadratic even within the public cell-count bound.
    order = np.argsort(finite_labels, kind="stable")
    ordered_values = values[labelled][order]
    unique_labels, group_sizes = np.unique(finite_labels[order], return_counts=True)
    results = []
    offset = 0
    for label, size in zip(unique_labels, group_sizes):
        members = ordered_values[offset:offset + size]
        offset += size
        valid = members[np.isfinite(members)]
        count = int(valid.size)
        results.append({
            "zone": int(label), "count": count, "missing_count": int(members.size - count),
            "mean": float(np.mean(valid)) if count else None,
            "min": float(np.min(valid)) if count else None,
            "max": float(np.max(valid)) if count else None,
            "population_std": float(np.std(valid, ddof=0)) if count else None,
        })
    return {
        "zones": results, "value_unit": parameters["values"]["unit"],
        "unassigned_cell_count": int(np.count_nonzero(np.isnan(labels))),
        "assumptions": [
            "CRS, north-up transform and array shape must match exactly; no resampling occurs.",
            "Null zone labels are unassigned. Null values are omitted and counted as missing.",
            "An all-missing zone retains count=0 with null statistics; zero is an ordinary value and zone label.",
            "Standard deviation is population standard deviation (ddof=0); cells have equal weight.",
        ],
    }


def terrain_slope(parameters):
    """Centered finite differences on a local metric north-up elevation grid."""
    keys(parameters, {"elevation"})
    elevation = parameters["elevation"]
    z = raster(elevation)
    metric(elevation)
    if elevation["unit"] != "m":
        raise ValueError("Elevation must use unit 'm' in the local metre frame")
    if min(z.shape) < 3:
        raise ValueError("Centered slope stencil requires at least 3 rows and 3 columns")
    dx, dy = elevation["transform"][1], elevation["transform"][5]
    dz_dx = np.full(z.shape, np.nan)
    dz_dy = np.full(z.shape, np.nan)
    valid = (np.isfinite(z[1:-1, 1:-1]) & np.isfinite(z[1:-1, 2:]) &
             np.isfinite(z[1:-1, :-2]) & np.isfinite(z[2:, 1:-1]) & np.isfinite(z[:-2, 1:-1]))
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        x_gradient = (z[1:-1, 2:] - z[1:-1, :-2]) / (2.0 * dx)
        y_gradient = (z[2:, 1:-1] - z[:-2, 1:-1]) / (2.0 * dy)
    if np.any(~np.isfinite(x_gradient[valid])) or np.any(~np.isfinite(y_gradient[valid])):
        raise ValueError("Numerical overflow in terrain gradient")
    dz_dx[1:-1, 1:-1] = np.where(valid, x_gradient, np.nan)
    dz_dy[1:-1, 1:-1] = np.where(valid, y_gradient, np.nan)
    with np.errstate(over="ignore", invalid="ignore"):
        gradient_norm = np.hypot(dz_dx, dz_dy)
    if np.isinf(gradient_norm).any():
        raise ValueError("Numerical overflow in terrain gradient magnitude")
    slope = np.degrees(np.arctan(gradient_norm))
    return {
        "slope_degrees": output_raster(elevation, slope, "deg"),
        "dz_dx": output_raster(elevation, dz_dx, "1"),
        "dz_dy": output_raster(elevation, dz_dy, "1"),
        "assumptions": [
            "Elevation and horizontal grid spacing are metres in an explicit LOCAL_METRE frame.",
            "Centered differences use the center and four axial neighbours; outer boundaries are null.",
            "Any null in that stencil makes all three outputs null; no interpolation occurs.",
            "x increases east and y increases north, while north-up raster row indices increase south.",
            "Slope is atan(sqrt((dz/dx)^2+(dz/dy)^2)); terrain is a single-valued height field.",
        ],
    }


def raster_suitability(parameters):
    """Weighted sum of explicitly normalized, aligned suitability criteria."""
    keys(parameters, {"criteria", "weights"})
    criteria, weights = parameters["criteria"], parameters["weights"]
    if type(criteria) is not list or not 1 <= len(criteria) <= 32:
        raise ValueError("Require between 1 and 32 criterion rasters")
    if type(weights) is not list or len(weights) != len(criteria):
        raise ValueError("Require exactly one weight per criterion")
    weights = [number(weight) for weight in weights]
    if any(weight < 0.0 for weight in weights) or not math.isclose(math.fsum(weights), 1.0, rel_tol=0, abs_tol=1e-12):
        raise ValueError("Nonnegative criterion weights must sum to one (absolute tolerance 1e-12)")
    arrays = aligned(*criteria)
    for criterion, values in zip(criteria, arrays):
        if criterion["unit"] != "1" or np.any(values < 0.0) or np.any(values > 1.0):
            raise ValueError("Every criterion must be dimensionless and normalized to [0,1]")
    # Correct only floating point summation tolerance; return effective weights.
    total = math.fsum(weights)
    effective_weights = [weight / total for weight in weights]
    stack = np.stack(arrays)
    complete = np.all(np.isfinite(stack), axis=0)
    score = np.sum(np.nan_to_num(stack, nan=0.0) * np.array(effective_weights)[:, None, None], axis=0)
    score = np.where(complete, np.clip(score, 0.0, 1.0), np.nan)
    return {
        "suitability": output_raster(criteria[0], score, "1"),
        "effective_weights": effective_weights,
        "assumptions": [
            "Criteria are supplied normalized to [0,1], with higher values always more suitable.",
            "Nonnegative weights sum to one within 1e-12; effective weights remove that rounding tolerance.",
            "A null in any criterion propagates, including zero-weight criteria; no imputation occurs.",
            "A weighted additive preference score is not a probability or empirical validation.",
        ],
    }


def _vector3(value):
    if type(value) is not list or len(value) != 3:
        raise ValueError("Retained Cartesian coordinate must have three components")
    for item in value:
        output_number(item)


def _validate_enu(parameters, output):
    keys(parameters, {"origin", "points"})
    _geodetic(parameters["origin"])
    if type(parameters["points"]) is not list or not 1 <= len(parameters["points"]) <= 4096:
        raise ValueError("Require between 1 and 4096 point objects")
    for point in parameters["points"]:
        _geodetic(point)
    keys(output, {"datum", "origin_ecef_m", "points", "assumptions"})
    validate_assumptions(output["assumptions"])
    if output["datum"] != "WGS84 ellipsoid":
        raise ValueError("Retained ENU datum differs from WGS84 ellipsoid")
    _vector3(output["origin_ecef_m"])
    if type(output["points"]) is not list or len(output["points"]) != len(parameters["points"]):
        raise ValueError("Retained ENU point count differs from the declaration")
    for point in output["points"]:
        keys(point, {"ecef_m", "enu_m"})
        _vector3(point["ecef_m"])
        _vector3(point["enu_m"])


def _count(value):
    if type(value) is not int or value < 0:
        raise ValueError("Retained count must be a nonnegative integer")


def _validate_zonal(parameters, output):
    keys(parameters, {"values", "zones"})
    keys(output, {"zones", "value_unit", "unassigned_cell_count", "assumptions"})
    validate_assumptions(output["assumptions"])
    values, labels = aligned(parameters["values"], parameters["zones"])
    finite_labels = labels[np.isfinite(labels)]
    if (parameters["zones"]["unit"] != "1" or np.any(finite_labels != np.floor(finite_labels)) or
            np.any(np.abs(finite_labels) > 2**53 - 1)):
        raise ValueError("Declared zone labels must be dimensionless exactly representable integers")
    if output["value_unit"] != parameters["values"]["unit"]:
        raise ValueError("Retained zonal statistic unit differs from the declared values")
    _count(output["unassigned_cell_count"])
    if output["unassigned_cell_count"] != int(np.count_nonzero(np.isnan(labels))):
        raise ValueError("Retained unassigned count differs from the input mask")
    # Check label/cardinality and null-mask structure, without recalculating
    # means, extrema or standard deviations.
    expected = {}
    for label, value in zip(labels.flat, values.flat):
        if np.isnan(label):
            continue
        counts = expected.setdefault(int(label), [0, 0])
        counts[int(np.isnan(value))] += 1
    if type(output["zones"]) is not list or len(output["zones"]) != len(expected):
        raise ValueError("Retained zone count differs from the declaration")
    actual_labels = []
    for zone in output["zones"]:
        keys(zone, {"zone", "count", "missing_count", "mean", "min", "max", "population_std"})
        label = zone["zone"]
        if type(label) is not int or label not in expected:
            raise ValueError("Unexpected retained integer zone label")
        actual_labels.append(label)
        _count(zone["count"]); _count(zone["missing_count"])
        if [zone["count"], zone["missing_count"]] != expected[label]:
            raise ValueError("Retained zone counts differ from the input mask")
        statistics = [zone[key] for key in ("mean", "min", "max", "population_std")]
        if zone["count"] == 0:
            if any(value is not None for value in statistics):
                raise ValueError("An empty zone must retain null statistics")
        else:
            mean, low, high, std = map(output_number, statistics)
            tolerance = 1e-12 * max(abs(mean), abs(low), abs(high))
            if low > high or mean < low - tolerance or mean > high + tolerance or std < 0:
                raise ValueError("Retained zone statistics violate range or dispersion constraints")
            if zone["count"] == 1 and std != 0:
                raise ValueError("A singleton zone must have zero population standard deviation")
    if actual_labels != sorted(expected):
        raise ValueError("Retained zone labels must be unique and sorted")


def _validate_slope(parameters, output):
    keys(parameters, {"elevation"})
    keys(output, {"slope_degrees", "dz_dx", "dz_dy", "assumptions"})
    validate_assumptions(output["assumptions"])
    elevation = parameters["elevation"]
    z = raster(elevation)
    metric(elevation)
    if elevation["unit"] != "m" or min(z.shape) < 3:
        raise ValueError("Declared elevation must use metres and have at least 3 rows and 3 columns")
    slope = validate_output_raster(elevation, output["slope_degrees"], "deg")
    dx = validate_output_raster(elevation, output["dz_dx"], "1")
    dy = validate_output_raster(elevation, output["dz_dy"], "1")
    valid = np.zeros(z.shape, dtype=bool)
    valid[1:-1, 1:-1] = (np.isfinite(z[1:-1, 1:-1]) & np.isfinite(z[1:-1, 2:]) &
                         np.isfinite(z[1:-1, :-2]) & np.isfinite(z[2:, 1:-1]) & np.isfinite(z[:-2, 1:-1]))
    if any(not np.array_equal(np.isfinite(array), valid) for array in (slope, dx, dy)):
        raise ValueError("Retained terrain null masks differ from the declared stencil")
    if np.any(slope < 0) or np.any(slope > 90):
        raise ValueError("Retained terrain slope must lie in [0,90] degrees")


def _validate_suitability(parameters, output):
    keys(parameters, {"criteria", "weights"})
    keys(output, {"suitability", "effective_weights", "assumptions"})
    validate_assumptions(output["assumptions"])
    criteria = parameters["criteria"]
    if type(criteria) is not list or not 1 <= len(criteria) <= 32:
        raise ValueError("Require between 1 and 32 criterion rasters")
    declared_weights = parameters["weights"]
    if type(declared_weights) is not list or len(declared_weights) != len(criteria):
        raise ValueError("Require exactly one declared weight per criterion")
    declared_weights = [number(weight) for weight in declared_weights]
    if (any(weight < 0 for weight in declared_weights) or
            not math.isclose(math.fsum(declared_weights), 1, rel_tol=0, abs_tol=1e-12)):
        raise ValueError("Declared nonnegative weights must sum to one")
    arrays = aligned(*criteria)
    if any(criterion["unit"] != "1" or np.any(array < 0) or np.any(array > 1)
           for criterion, array in zip(criteria, arrays)):
        raise ValueError("Declared criteria must be dimensionless and normalized to [0,1]")
    score = validate_output_raster(criteria[0], output["suitability"], "1")
    weights = output["effective_weights"]
    if type(weights) is not list or len(weights) != len(criteria):
        raise ValueError("Retained weight count differs from the declaration")
    weights = [output_number(weight) for weight in weights]
    if any(weight < 0 for weight in weights) or not math.isclose(math.fsum(weights), 1, rel_tol=0, abs_tol=1e-12):
        raise ValueError("Retained nonnegative weights must sum to one")
    # Compare declared weight metadata within its documented rounding allowance;
    # this does not rerun normalization or calculate any suitability scores.
    if any(not math.isclose(actual, declared, rel_tol=2e-12, abs_tol=1e-15)
           for actual, declared in zip(weights, parameters["weights"])):
        raise ValueError("Retained weights differ from the declaration")
    expected_mask = np.all(np.isfinite(np.stack(arrays)), axis=0)
    if not np.array_equal(np.isfinite(score), expected_mask):
        raise ValueError("Retained suitability null mask differs from the input criteria")
    if np.any(score < 0) or np.any(score > 1):
        raise ValueError("Retained suitability must lie in [0,1]")


OUTPUT_VALIDATORS = {
    "geomatics.coordinates.enu.v1": _validate_enu,
    "geomatics.raster.zonal.v1": _validate_zonal,
    "geomatics.terrain.slope.v1": _validate_slope,
    "geomatics.raster.suitability.v1": _validate_suitability,
}


OPERATIONS = {
    "geomatics.coordinates.enu.v1": coordinates_enu,
    "geomatics.raster.zonal.v1": raster_zonal,
    "geomatics.terrain.slope.v1": terrain_slope,
    "geomatics.raster.suitability.v1": raster_suitability,
}

DESCRIPTIONS = {
    "geomatics.coordinates.enu.v1": "WGS84 ellipsoid geodetic coordinates to ECEF and local ENU metres",
    "geomatics.raster.zonal.v1": "Aligned raster zonal counts and population statistics with explicit missing data",
    "geomatics.terrain.slope.v1": "Local metric terrain slope and gradients from a centered finite-difference stencil",
    "geomatics.raster.suitability.v1": "Explicit weighted suitability score over aligned normalized criterion rasters",
}

EXAMPLES = {
    "geomatics.coordinates.enu.v1": {
        "origin": {"longitude_deg": -79.5, "latitude_deg": 43.77, "ellipsoid_height_m": 160},
        "points": [
            {"longitude_deg": -79.5, "latitude_deg": 43.77, "ellipsoid_height_m": 170},
            {"longitude_deg": -79.499, "latitude_deg": 43.771, "ellipsoid_height_m": 162},
        ],
    },
    "geomatics.raster.zonal.v1": {
        "values": example_raster([[1, 3, None], [2, 4, 6], [None, 0, 8]], "m"),
        "zones": example_raster([[1, 1, 2], [1, 2, 2], [3, 0, None]]),
    },
    "geomatics.terrain.slope.v1": {
        "elevation": example_raster([[120, 130, 140], [100, 110, 120], [80, 90, 100]], "m"),
    },
    "geomatics.raster.suitability.v1": {
        "criteria": [
            example_raster([[0, 0.5, 1], [0.2, 0.6, 0.7], [0.4, None, 0.8]]),
            example_raster([[1, 0.5, 0], [0.8, 0.4, 0.3], [0.6, 0.9, 0.2]]),
        ],
        "weights": [0.75, 0.25],
    },
}
