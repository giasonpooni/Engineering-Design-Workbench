"""Small, explicit Earth-observation calculations on already aligned rasters.

These operators do not fetch imagery, infer spectral band identity, train a
classifier, certify reference labels, or reproject inputs. ``None`` is the only
accepted nodata representation. Each operation retains the input grid.
"""

from datetime import datetime

import numpy as np

from .common import (aligned, example_raster, keys, number, output_number,
                     output_raster, raster, text, validate_output_raster)


def _same_unit(*rasters):
    if any(r["unit"] != rasters[0]["unit"] for r in rasters[1:]):
        raise ValueError("Raster units must match exactly; convert upstream")


def _integer(value, minimum, maximum, name):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")
    return value


def normalized_difference(parameters):
    """Return (a-b)/(a+b), without assuming or clipping a vegetation index."""
    keys(parameters, {"a", "b", "a_band", "b_band"})
    a_name, b_name = text(parameters["a_band"]), text(parameters["b_band"])
    if a_name == b_name:
        raise ValueError("Declare distinct spectral band labels")
    a, b = aligned(parameters["a"], parameters["b"])
    _same_unit(parameters["a"], parameters["b"])
    denominator = a + b
    valid = np.isfinite(a) & np.isfinite(b) & (denominator != 0)
    values = np.full(a.shape, np.nan)
    np.divide(a - b, denominator, out=values, where=valid)
    return {
        "raster": output_raster(parameters["a"], values, "1"),
        "definition": "(a-b)/(a+b)",
        "bands": {"a": a_name, "b": b_name},
        "valid_cell_count": int(valid.sum()),
        "zero_denominator_count": int((np.isfinite(denominator) & (denominator == 0)).sum()),
        "interpretation": "Band labels are operator declarations; values are not clipped or sensor-validated.",
    }


def _acquisition_time(value):
    text(value)
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Acquisition time must be ISO 8601 with timezone") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("Acquisition time must include a timezone")
    return result


def change(parameters):
    """Difference on a common grid; no claim of cross-sensor harmonization."""
    keys(parameters, {"before", "after", "before_time", "after_time", "quantity"})
    quantity = text(parameters["quantity"])
    before_time = _acquisition_time(parameters["before_time"])
    after_time = _acquisition_time(parameters["after_time"])
    if after_time <= before_time:
        raise ValueError("after_time must be later than before_time")
    before, after = aligned(parameters["before"], parameters["after"])
    _same_unit(parameters["before"], parameters["after"])
    values = after - before
    return {
        "raster": output_raster(parameters["before"], values),
        "definition": "after-before",
        "quantity": quantity,
        "before_time": parameters["before_time"],
        "after_time": parameters["after_time"],
        "elapsed_seconds": (after_time - before_time).total_seconds(),
        "valid_cell_count": int(np.isfinite(values).sum()),
        "interpretation": "Arithmetic change only; registration, seasonality, atmosphere and sensor comparability are not verified.",
    }


def _classes(value, prototypes=False):
    if type(value) is not list or not 1 <= len(value) <= 64:
        raise ValueError("Require 1 to 64 explicitly declared classes")
    identifiers, labels = [], []
    expected = {"class_id", "label", "values"} if prototypes else {"class_id", "label"}
    for item in value:
        keys(item, expected)
        identifiers.append(_integer(item["class_id"], 0, 2147483647, "class_id"))
        labels.append(text(item["label"]))
    if len(set(identifiers)) != len(identifiers) or len(set(labels)) != len(labels):
        raise ValueError("Class IDs and labels must be unique")
    return identifiers, labels


def classify(parameters):
    """Nearest supplied centroid in common-unit, unstandardized band space."""
    keys(parameters, {"bands", "prototypes"})
    bands = parameters["bands"]
    if type(bands) is not list or not 1 <= len(bands) <= 32:
        raise ValueError("Require 1 to 32 named bands")
    for band in bands:
        keys(band, {"name", "raster"})
        text(band["name"])
    names = [b["name"] for b in bands]
    if len(set(names)) != len(names):
        raise ValueError("Band names must be unique")
    rasters = [b["raster"] for b in bands]
    arrays = aligned(*rasters)
    _same_unit(*rasters)
    identifiers, labels = _classes(parameters["prototypes"], prototypes=True)
    centroids = []
    for prototype in parameters["prototypes"]:
        values = prototype["values"]
        if type(values) is not list or len(values) != len(bands):
            raise ValueError("Each prototype must provide one numeric value per band, in band order")
        centroids.append([number(v) for v in values])
    stack = np.stack(arrays, axis=-1)
    valid = np.isfinite(stack).all(axis=-1)
    best = np.full(arrays[0].shape, np.inf)
    result = np.full(arrays[0].shape, np.nan)
    # Stream prototypes so memory does not grow as cells * bands * classes.
    for class_id, centroid in zip(identifiers, centroids):
        distance = np.sum((stack - np.asarray(centroid)) ** 2, axis=-1)
        better = valid & (distance < best)
        best[better] = distance[better]
        result[better] = class_id
    best[~valid] = np.nan
    return {
        "raster": output_raster(rasters[0], result, "class_id"),
        "distance_raster": output_raster(rasters[0], np.sqrt(best), rasters[0]["unit"]),
        "classes": [{"class_id": i, "label": label} for i, label in zip(identifiers, labels)],
        "band_order": names,
        "distance": "Euclidean in supplied common-unit band coordinates; no standardization",
        "tie_rule": "First prototype in supplied order",
        "valid_cell_count": int(valid.sum()),
        "interpretation": "Operator-supplied prototypes; no model fitting or classification accuracy claim.",
    }


def accuracy(parameters):
    """Confusion statistics for supplied labels, with honest split provenance."""
    keys(parameters, {"reference", "predicted", "classes", "holdout_declared"})
    if type(parameters["holdout_declared"]) is not bool:
        raise ValueError("holdout_declared must be a boolean operator declaration")
    reference, predicted = aligned(parameters["reference"], parameters["predicted"])
    if parameters["reference"]["unit"] != "class_id" or parameters["predicted"]["unit"] != "class_id":
        raise ValueError("Reference and predicted rasters must use unit class_id")
    identifiers, labels = _classes(parameters["classes"])
    for data in (reference, predicted):
        if not np.isin(data[np.isfinite(data)], identifiers).all():
            raise ValueError("Every nonnull raster class ID must be in the declared classes")
    valid = np.isfinite(reference) & np.isfinite(predicted)
    count = int(valid.sum())
    if not count:
        raise ValueError("At least one paired nonnull reference and predicted label is required")
    lookup = {class_id: index for index, class_id in enumerate(identifiers)}
    matrix = np.zeros((len(identifiers), len(identifiers)), dtype=np.int64)
    for actual, inferred in zip(reference[valid], predicted[valid]):
        matrix[lookup[int(actual)], lookup[int(inferred)]] += 1
    rows, columns = matrix.sum(axis=1), matrix.sum(axis=0)
    per_class = []
    for index, (class_id, label) in enumerate(zip(identifiers, labels)):
        correct = int(matrix[index, index])
        per_class.append({
            "class_id": class_id,
            "label": label,
            "reference_count": int(rows[index]),
            "predicted_count": int(columns[index]),
            "producer_accuracy": correct / int(rows[index]) if rows[index] else None,
            "user_accuracy": correct / int(columns[index]) if columns[index] else None,
        })
    return {
        "confusion_matrix": matrix.tolist(),
        "matrix_axes": {"rows": "reference", "columns": "predicted", "class_order": identifiers},
        "overall_accuracy": int(np.trace(matrix)) / count,
        "per_class": per_class,
        "paired_cell_count": count,
        "unpaired_or_nodata_cell_count": int(valid.size - count),
        "reference_valid_count": int(np.isfinite(reference).sum()),
        "holdout_declared": parameters["holdout_declared"],
        "reference_authenticity_verified": False,
        "independence_verified": False,
        "interpretation": "Statistics describe the supplied paired labels only; holdout status is an unverified operator declaration.",
    }


def focal(parameters):
    """Clipped-window mean or population deviation, preserving center nodata."""
    keys(parameters, {"raster", "window_size", "statistic"})
    data = raster(parameters["raster"])
    window = _integer(parameters["window_size"], 1, 31, "window_size")
    if window % 2 != 1:
        raise ValueError("window_size must be odd")
    if parameters["statistic"] not in ("mean", "std"):
        raise ValueError("statistic must be mean or std")
    counts = np.zeros(data.shape, dtype=np.int64)
    means = np.zeros(data.shape)
    moment = np.zeros(data.shape)
    height, width = data.shape
    radius = window // 2
    # Welford accumulation avoids E[x^2]-E[x]^2 cancellation at large offsets.
    for dy in range(-min(radius, height - 1), min(radius, height - 1) + 1):
        for dx in range(-min(radius, width - 1), min(radius, width - 1) + 1):
            destination = (slice(max(0, -dy), min(height, height - dy)),
                           slice(max(0, -dx), min(width, width - dx)))
            source = (slice(max(0, dy), min(height, height + dy)),
                      slice(max(0, dx), min(width, width + dx)))
            sample = data[source]
            valid = np.isfinite(sample)
            n, mean, m2 = counts[destination], means[destination], moment[destination]
            n[valid] += 1
            delta = sample[valid] - mean[valid]
            mean[valid] += delta / n[valid]
            m2[valid] += delta * (sample[valid] - mean[valid])
    values = means if parameters["statistic"] == "mean" else np.sqrt(
        np.divide(np.maximum(moment, 0), counts, out=np.zeros(data.shape), where=counts > 0))
    values[~np.isfinite(data)] = np.nan
    sample_counts = counts.astype(float)
    sample_counts[~np.isfinite(data)] = np.nan
    return {
        "raster": output_raster(parameters["raster"], values),
        "sample_count_raster": output_raster(parameters["raster"], sample_counts, "count"),
        "window_size": window,
        "statistic": parameters["statistic"],
        "standard_deviation_ddof": 0 if parameters["statistic"] == "std" else None,
        "edge_rule": "Clip window at raster bounds; no padding or wrapping",
        "nodata_rule": "Preserve null centers; omit null neighbors; require at least one valid sample",
    }


def radiometry(parameters):
    """Apply explicitly supplied affine coefficients; no calibration claim."""
    keys(parameters, {"raster", "scale", "offset", "output_unit", "coefficient_source"})
    data = raster(parameters["raster"])
    scale, offset = number(parameters["scale"]), number(parameters["offset"])
    output_unit = text(parameters["output_unit"])
    source = text(parameters["coefficient_source"])
    return {
        "raster": output_raster(parameters["raster"], scale * data + offset, output_unit),
        "definition": "output=scale*input+offset",
        "scale": scale,
        "offset": offset,
        "coefficient_source": source,
        "interpretation": "Coefficients are operator supplied; calibration validity and physical range are not verified.",
    }


OPERATIONS = {
    "geomatics.image.normalized-difference.v1": normalized_difference,
    "geomatics.image.change.v1": change,
    "geomatics.image.classify.v1": classify,
    "geomatics.image.accuracy.v1": accuracy,
    "geomatics.image.focal.v1": focal,
    "geomatics.image.radiometry.v1": radiometry,
}

DESCRIPTIONS = {
    "geomatics.image.normalized-difference.v1": "Normalized band difference with explicit labels and null masking",
    "geomatics.image.change.v1": "Aligned before/after raster difference with ordered acquisition times",
    "geomatics.image.classify.v1": "Nearest operator-supplied centroid in multispectral band space",
    "geomatics.image.accuracy.v1": "Confusion matrix and producer/user accuracy for supplied reference labels",
    "geomatics.image.focal.v1": "Clipped-window mean or population standard deviation texture",
    "geomatics.image.radiometry.v1": "Operator-declared affine radiometric scale and offset",
}

EXAMPLES = {
    "geomatics.image.normalized-difference.v1": {
        "a": example_raster([[0.8, 0.2], [0.4, None]], "reflectance"),
        "b": example_raster([[0.2, 0.2], [0.1, 0.3]], "reflectance"),
        "a_band": "near_infrared", "b_band": "red",
    },
    "geomatics.image.change.v1": {
        "before": example_raster([[290, 291], [292, None]], "K"),
        "after": example_raster([[292, 290], [292, 294]], "K"),
        "before_time": "2026-06-01T12:00:00Z", "after_time": "2026-06-02T12:00:00Z",
        "quantity": "synthetic surface temperature",
    },
    "geomatics.image.classify.v1": {
        "bands": [
            {"name": "red", "raster": example_raster([[0.2, 0.7], [0.2, None]], "reflectance")},
            {"name": "near_infrared", "raster": example_raster([[0.8, 0.2], [0.7, 0.2]], "reflectance")},
        ],
        "prototypes": [
            {"class_id": 1, "label": "synthetic vegetation", "values": [0.2, 0.8]},
            {"class_id": 2, "label": "synthetic bare surface", "values": [0.7, 0.2]},
        ],
    },
    "geomatics.image.accuracy.v1": {
        "reference": example_raster([[1, 1], [2, 2]], "class_id"),
        "predicted": example_raster([[1, 2], [2, 2]], "class_id"),
        "classes": [{"class_id": 1, "label": "synthetic vegetation"},
                    {"class_id": 2, "label": "synthetic bare surface"}],
        "holdout_declared": False,
    },
    "geomatics.image.focal.v1": {
        "raster": example_raster([[1, 2, 3], [4, 5, 6], [7, 8, None]], "reflectance"),
        "window_size": 3, "statistic": "std",
    },
    "geomatics.image.radiometry.v1": {
        "raster": example_raster([[1000, 2000], [0, None]], "digital_number"),
        "scale": 0.0001, "offset": 0, "output_unit": "reflectance",
        "coefficient_source": "Synthetic example coefficients; not a sensor product calibration",
    },
}


def _assert(condition, message):
    if not condition:
        raise ValueError("Invalid Earth-observation output: " + message)


def _finite(value, minimum=None, maximum=None):
    output_number(value)
    _assert(minimum is None or value >= minimum, "numeric value below range")
    _assert(maximum is None or value <= maximum, "numeric value above range")


def _count(value, maximum):
    _integer(value, 0, maximum, "output count")


def _result_grid(result, template, unit):
    """Validate a result grid without evaluating any provider algorithm."""
    validate_output_raster(template, result, unit)
    return result["values"]


def _flat(rows):
    return [value for row in rows for value in row]


def _exact(result, **fields):
    for name, value in fields.items():
        _assert(result[name] == value and type(result[name]) is type(value),
                f"incorrect {name} declaration")


def validate_normalized_difference(parameters, result):
    keys(result, {"raster", "definition", "bands", "valid_cell_count", "zero_denominator_count", "interpretation"})
    rows = _result_grid(result["raster"], parameters["a"], "1")
    aligned(parameters["a"], parameters["b"])
    _same_unit(parameters["a"], parameters["b"])
    keys(result["bands"], {"a", "b"})
    _exact(result["bands"], a=parameters["a_band"], b=parameters["b_band"])
    _exact(result, definition="(a-b)/(a+b)",
           interpretation="Band labels are operator declarations; values are not clipped or sensor-validated.")
    cells, a, b = _flat(rows), _flat(parameters["a"]["values"]), _flat(parameters["b"]["values"])
    paired = sum(x is not None and y is not None for x, y in zip(a, b))
    _count(result["valid_cell_count"], len(cells))
    _count(result["zero_denominator_count"], len(cells))
    _assert(result["valid_cell_count"] == sum(x is not None for x in cells), "incorrect valid count")
    _assert(result["valid_cell_count"] + result["zero_denominator_count"] == paired,
            "valid and zero-denominator counts must partition input pairs")
    for x, y, value in zip(a, b, cells):
        _assert((x is not None and y is not None) or value is None, "nodata input must remain masked")


def validate_change(parameters, result):
    keys(result, {"raster", "definition", "quantity", "before_time", "after_time", "elapsed_seconds",
                  "valid_cell_count", "interpretation"})
    rows = _result_grid(result["raster"], parameters["before"], parameters["before"]["unit"])
    aligned(parameters["before"], parameters["after"])
    _same_unit(parameters["before"], parameters["after"])
    _exact(result, definition="after-before", quantity=parameters["quantity"],
           before_time=parameters["before_time"], after_time=parameters["after_time"],
           interpretation="Arithmetic change only; registration, seasonality, atmosphere and sensor comparability are not verified.")
    _finite(result["elapsed_seconds"], 0)
    _assert(result["elapsed_seconds"] > 0, "elapsed time must be positive")
    cells = _flat(rows)
    _count(result["valid_cell_count"], len(cells))
    _assert(result["valid_cell_count"] == sum(x is not None for x in cells), "incorrect valid count")
    for x, y, value in zip(_flat(parameters["before"]["values"]), _flat(parameters["after"]["values"]), cells):
        _assert((value is not None) == (x is not None and y is not None), "difference nodata mask differs")


def validate_classify(parameters, result):
    keys(result, {"raster", "distance_raster", "classes", "band_order", "distance", "tie_rule",
                  "valid_cell_count", "interpretation"})
    template = parameters["bands"][0]["raster"]
    rows = _result_grid(result["raster"], template, "class_id")
    distances = _result_grid(result["distance_raster"], template, template["unit"])
    identifiers, labels = _classes(parameters["prototypes"], prototypes=True)
    _classes(result["classes"])
    _exact(result,
           classes=[{"class_id": i, "label": label} for i, label in zip(identifiers, labels)],
           band_order=[band["name"] for band in parameters["bands"]],
           distance="Euclidean in supplied common-unit band coordinates; no standardization",
           tie_rule="First prototype in supplied order",
           interpretation="Operator-supplied prototypes; no model fitting or classification accuracy claim.")
    band_cells = [_flat(band["raster"]["values"]) for band in parameters["bands"]]
    cells = _flat(rows)
    for values, cell, distance in zip(zip(*band_cells), cells, _flat(distances)):
        expected_valid = all(value is not None for value in values)
        _assert((cell is not None) == expected_valid, "classification mask differs")
        _assert((distance is not None) == expected_valid, "distance mask differs")
        if expected_valid:
            _assert(cell in identifiers, "undeclared output class")
            _finite(distance, 0)
    _count(result["valid_cell_count"], len(cells))
    _assert(result["valid_cell_count"] == sum(x is not None for x in cells), "incorrect valid count")


def validate_accuracy(parameters, result):
    keys(result, {"confusion_matrix", "matrix_axes", "overall_accuracy", "per_class", "paired_cell_count",
                  "unpaired_or_nodata_cell_count", "reference_valid_count", "holdout_declared",
                  "reference_authenticity_verified", "independence_verified", "interpretation"})
    aligned(parameters["reference"], parameters["predicted"])
    identifiers, labels = _classes(parameters["classes"])
    keys(result["matrix_axes"], {"rows", "columns", "class_order"})
    _exact(result["matrix_axes"], rows="reference", columns="predicted", class_order=identifiers)
    _exact(result, holdout_declared=parameters["holdout_declared"], reference_authenticity_verified=False,
           independence_verified=False,
           interpretation="Statistics describe the supplied paired labels only; holdout status is an unverified operator declaration.")
    _assert(type(result["matrix_axes"]["class_order"]) is list and
            all(type(i) is int for i in result["matrix_axes"]["class_order"]), "invalid matrix class order")
    reference = _flat(parameters["reference"]["values"])
    predicted = _flat(parameters["predicted"]["values"])
    total = len(reference)
    for name in ("paired_cell_count", "unpaired_or_nodata_cell_count", "reference_valid_count"):
        _count(result[name], total)
    paired = sum(x is not None and y is not None for x, y in zip(reference, predicted))
    _assert(paired > 0 and result["paired_cell_count"] == paired, "incorrect paired count")
    _assert(result["unpaired_or_nodata_cell_count"] == total - paired, "incorrect unpaired count")
    _assert(result["reference_valid_count"] == sum(x is not None for x in reference), "incorrect reference count")
    matrix = result["confusion_matrix"]
    _assert(type(matrix) is list and len(matrix) == len(identifiers), "wrong matrix row count")
    for row in matrix:
        _assert(type(row) is list and len(row) == len(identifiers), "wrong matrix column count")
        for value in row:
            _count(value, paired)
    _assert(sum(sum(row) for row in matrix) == paired, "matrix count must equal paired count")
    _finite(result["overall_accuracy"], 0, 1)
    summaries = result["per_class"]
    _assert(type(summaries) is list and len(summaries) == len(identifiers), "wrong per-class count")
    for index, (item, class_id, label) in enumerate(zip(summaries, identifiers, labels)):
        keys(item, {"class_id", "label", "reference_count", "predicted_count", "producer_accuracy", "user_accuracy"})
        _exact(item, class_id=class_id, label=label)
        _count(item["reference_count"], paired)
        _count(item["predicted_count"], paired)
        _assert(item["reference_count"] == sum(matrix[index]), "reference count differs from matrix")
        _assert(item["predicted_count"] == sum(row[index] for row in matrix), "predicted count differs from matrix")
        for rate, count in (("producer_accuracy", "reference_count"), ("user_accuracy", "predicted_count")):
            if item[count]:
                _finite(item[rate], 0, 1)
            else:
                _assert(item[rate] is None, "undefined accuracy must be null")


def validate_focal(parameters, result):
    keys(result, {"raster", "sample_count_raster", "window_size", "statistic", "standard_deviation_ddof",
                  "edge_rule", "nodata_rule"})
    template = parameters["raster"]
    rows = _result_grid(result["raster"], template, template["unit"])
    counts = _result_grid(result["sample_count_raster"], template, "count")
    _exact(result, window_size=parameters["window_size"], statistic=parameters["statistic"],
           standard_deviation_ddof=0 if parameters["statistic"] == "std" else None,
           edge_rule="Clip window at raster bounds; no padding or wrapping",
           nodata_rule="Preserve null centers; omit null neighbors; require at least one valid sample")
    max_samples = min(parameters["window_size"] ** 2, len(_flat(rows)))
    for source, value, count in zip(_flat(template["values"]), _flat(rows), _flat(counts)):
        _assert((value is None) == (source is None), "focal center mask differs")
        _assert((count is None) == (source is None), "focal count mask differs")
        if source is not None:
            _finite(count, 1, max_samples)
            _assert(float(count).is_integer(), "sample count must be integral")
            if parameters["statistic"] == "std":
                _finite(value, 0)


def validate_radiometry(parameters, result):
    keys(result, {"raster", "definition", "scale", "offset", "coefficient_source", "interpretation"})
    rows = _result_grid(result["raster"], parameters["raster"], parameters["output_unit"])
    _finite(result["scale"])
    _finite(result["offset"])
    _assert(result["scale"] == parameters["scale"] and result["offset"] == parameters["offset"],
            "radiometric coefficients differ from declaration")
    _exact(result, definition="output=scale*input+offset", coefficient_source=parameters["coefficient_source"],
           interpretation="Coefficients are operator supplied; calibration validity and physical range are not verified.")
    for source, value in zip(_flat(parameters["raster"]["values"]), _flat(rows)):
        _assert((source is None) == (value is None), "radiometric nodata mask differs")


# Structural inspection is deliberately separate from replay. These validators
# check records without recomputing index, difference, classification, texture,
# calibration, or numerical accuracy results.
OUTPUT_VALIDATORS = {
    "geomatics.image.normalized-difference.v1": validate_normalized_difference,
    "geomatics.image.change.v1": validate_change,
    "geomatics.image.classify.v1": validate_classify,
    "geomatics.image.accuracy.v1": validate_accuracy,
    "geomatics.image.focal.v1": validate_focal,
    "geomatics.image.radiometry.v1": validate_radiometry,
}
