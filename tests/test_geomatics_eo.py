"""Analytic references and refusal tests for bounded EO operations."""

from copy import deepcopy
import json
import math

import numpy as np
import pytest

from net_geomatics import earth_observation as eo
from net_geomatics.common import example_raster


def params(suffix):
    return deepcopy(eo.EXAMPLES[f"geomatics.image.{suffix}.v1"])


@pytest.mark.parametrize("operation_id", eo.OPERATIONS)
def test_examples_serialize_strictly_without_mutating_inputs(operation_id):
    parameters = deepcopy(eo.EXAMPLES[operation_id])
    before = deepcopy(parameters)
    result = eo.OPERATIONS[operation_id](parameters)
    assert parameters == before
    json.dumps(result, allow_nan=False)


def test_normalized_difference_analytic_and_nodata():
    p = params("normalized-difference")
    p["a"]["values"] = [[0.8, 0], [1, None]]
    p["b"]["values"] = [[0.2, 0], [-1, 0.2]]
    result = eo.normalized_difference(p)
    assert result["raster"]["values"][0][0] == pytest.approx(0.6)
    assert result["raster"]["values"][0][1] is None
    assert result["raster"]["values"][1] == [None, None]
    assert result["zero_denominator_count"] == 2
    assert result["valid_cell_count"] == 1
    assert result["raster"]["unit"] == "1"


def test_normalized_difference_does_not_clip_negative_reflectance():
    p = params("normalized-difference")
    p["a"]["values"] = [[2]]
    p["b"]["values"] = [[-1]]
    assert eo.normalized_difference(p)["raster"]["values"] == [[3.0]]


@pytest.mark.parametrize("field,value", [("unit", "K"), ("crs", "EPSG:4326"),
                                          ("transform", [0, 20, 0, 30, 0, -10]),
                                          ("values", [[1]])])
def test_pair_refuses_incompatible_grids_or_units(field, value):
    p = params("normalized-difference")
    p["b"][field] = value
    with pytest.raises(ValueError):
        eo.normalized_difference(p)


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), "0.4", 1e101])
def test_reject_non_numeric_or_nonfinite_cells(value):
    p = params("normalized-difference")
    p["a"]["values"][0][0] = value
    with pytest.raises(ValueError):
        eo.normalized_difference(p)


def test_change_reports_temporal_difference_and_masks():
    result = eo.change(params("change"))
    assert result["raster"]["values"] == [[2.0, -1.0], [0.0, None]]
    assert result["elapsed_seconds"] == 86400
    assert result["valid_cell_count"] == 3
    assert result["raster"]["unit"] == "K"


@pytest.mark.parametrize("after", ["not-a-time", "2026-06-02T12:00:00", "2026-06-01T12:00:00Z",
                                   "2026-05-31T12:00:00Z"])
def test_change_refuses_missing_timezone_or_unordered_times(after):
    p = params("change")
    p["after_time"] = after
    with pytest.raises(ValueError):
        eo.change(p)


def test_change_converts_timezone_offsets_for_ordering():
    p = params("change")
    p["after_time"] = "2026-06-01T09:00:00-04:00"
    assert eo.change(p)["elapsed_seconds"] == 3600


def test_classifier_analytic_distances_and_missing_bands():
    result = eo.classify(params("classify"))
    assert result["raster"]["values"] == [[1.0, 2.0], [1.0, None]]
    assert result["distance_raster"]["values"][1][0] == pytest.approx(0.1)
    assert result["distance_raster"]["values"][1][1] is None
    assert result["valid_cell_count"] == 3


def test_classifier_ties_respect_explicit_prototype_order():
    p = {"bands": [{"name": "synthetic", "raster": example_raster([[0, 1, None]])}],
         "prototypes": [{"class_id": 9, "label": "left", "values": [-1]},
                        {"class_id": 2, "label": "right", "values": [1]}]}
    result = eo.classify(p)
    assert result["raster"]["values"] == [[9.0, 2.0, None]]
    assert result["distance_raster"]["values"] == [[1.0, 0.0, None]]


@pytest.mark.parametrize("mutation", ["units", "prototype_length", "duplicate_id", "duplicate_band", "null_prototype"])
def test_classifier_refuses_ambiguous_inputs(mutation):
    p = params("classify")
    if mutation == "units":
        p["bands"][1]["raster"]["unit"] = "K"
    elif mutation == "prototype_length":
        p["prototypes"][0]["values"] = [1]
    elif mutation == "duplicate_id":
        p["prototypes"][1]["class_id"] = 1
    elif mutation == "duplicate_band":
        p["bands"][1]["name"] = "red"
    else:
        p["prototypes"][0]["values"][0] = None
    with pytest.raises(ValueError):
        eo.classify(p)


def test_confusion_matrix_axes_and_accuracy_denominators():
    p = params("accuracy")
    p["classes"].append({"class_id": 3, "label": "absent"})
    p["holdout_declared"] = True
    result = eo.accuracy(p)
    assert result["confusion_matrix"] == [[1, 1, 0], [0, 2, 0], [0, 0, 0]]
    assert result["overall_accuracy"] == 0.75
    assert result["per_class"][0]["producer_accuracy"] == 0.5
    assert result["per_class"][0]["user_accuracy"] == 1
    assert result["per_class"][1]["producer_accuracy"] == 1
    assert result["per_class"][1]["user_accuracy"] == pytest.approx(2 / 3)
    assert result["per_class"][2]["producer_accuracy"] is None
    assert result["per_class"][2]["user_accuracy"] is None
    assert result["holdout_declared"] is True
    assert result["reference_authenticity_verified"] is False
    assert result["independence_verified"] is False


def test_accuracy_pairs_masks_and_rejects_empty_reference():
    p = params("accuracy")
    p["predicted"]["values"][0][1] = None
    result = eo.accuracy(p)
    assert result["overall_accuracy"] == 1
    assert result["paired_cell_count"] == 3
    assert result["unpaired_or_nodata_cell_count"] == 1
    assert result["reference_valid_count"] == 4
    p["reference"]["values"] = [[None, None], [None, None]]
    with pytest.raises(ValueError, match="paired"):
        eo.accuracy(p)


@pytest.mark.parametrize("invalid", [0, 1.5, 8])
def test_accuracy_rejects_unknown_class_ids(invalid):
    p = params("accuracy")
    p["predicted"]["values"][0][0] = invalid
    with pytest.raises(ValueError, match="declared classes"):
        eo.accuracy(p)


def test_accuracy_rejects_truthy_non_boolean_holdout():
    p = params("accuracy")
    p["holdout_declared"] = "true"
    with pytest.raises(ValueError):
        eo.accuracy(p)


@pytest.mark.parametrize("statistic", ["mean", "std"])
def test_focal_matches_independent_clipped_window_reference(statistic):
    p = params("focal")
    p["statistic"] = statistic
    result = eo.focal(p)
    data = np.array([[1, 2, 3], [4, 5, 6], [7, 8, np.nan]])
    for row in range(3):
        for column in range(3):
            if not np.isfinite(data[row, column]):
                assert result["raster"]["values"][row][column] is None
                continue
            local = data[max(0, row - 1):row + 2, max(0, column - 1):column + 2]
            local = local[np.isfinite(local)]
            expected = local.mean() if statistic == "mean" else local.std(ddof=0)
            assert result["raster"]["values"][row][column] == pytest.approx(expected)
            assert result["sample_count_raster"]["values"][row][column] == len(local)


def test_focal_deviation_is_stable_at_large_common_offset():
    p = {"raster": example_raster([[1e12, 1e12 + 1, 1e12 + 2]]), "window_size": 3, "statistic": "std"}
    result = eo.focal(p)["raster"]["values"][0]
    assert result == pytest.approx([0.5, math.sqrt(2 / 3), 0.5])


def test_focal_larger_window_and_single_sample_edges():
    p = {"raster": example_raster([[7, None]]), "window_size": 31, "statistic": "std"}
    assert eo.focal(p)["raster"]["values"] == [[0.0, None]]


@pytest.mark.parametrize("window", [0, 2, 33, True, 3.0])
def test_focal_refuses_unbounded_or_even_windows(window):
    p = params("focal")
    p["window_size"] = window
    with pytest.raises(ValueError):
        eo.focal(p)


def test_radiometry_applies_scale_offset_and_preserves_nodata():
    p = params("radiometry")
    p["offset"] = -0.1
    result = eo.radiometry(p)
    assert result["raster"]["values"] == [[0.0, 0.1], [-0.1, None]]
    assert result["raster"]["unit"] == "reflectance"


def test_all_operators_reject_unexpected_parameters():
    for operation_id, operation in eo.OPERATIONS.items():
        p = deepcopy(eo.EXAMPLES[operation_id])
        p["unreviewed_parameter"] = True
        with pytest.raises(ValueError, match="Unexpected"):
            operation(p)


def test_raster_size_limit_is_enforced():
    p = params("focal")
    p["raster"]["values"] = [[1] * 257 for _ in range(256)]
    with pytest.raises(ValueError, match="bound"):
        eo.focal(p)


@pytest.mark.parametrize("operation_id", eo.OPERATIONS)
def test_output_validation_accepts_real_results_without_running_provider(operation_id, monkeypatch):
    parameters = deepcopy(eo.EXAMPLES[operation_id])
    result = eo.OPERATIONS[operation_id](parameters)

    def forbidden(*args, **kwargs):
        raise AssertionError("Data-only validation must not execute a numerical provider")

    for function in eo.OPERATIONS.values():
        monkeypatch.setattr(eo, function.__name__, forbidden)
    eo.OUTPUT_VALIDATORS[operation_id](parameters, result)


@pytest.mark.parametrize("operation_id", eo.OPERATIONS)
def test_output_validation_rejects_empty_records_and_wrong_shapes(operation_id):
    parameters = deepcopy(eo.EXAMPLES[operation_id])
    validate = eo.OUTPUT_VALIDATORS[operation_id]
    with pytest.raises(ValueError):
        validate(parameters, {})
    result = eo.OPERATIONS[operation_id](parameters)
    if "raster" in result:
        result["raster"]["values"] = [[1]]
    else:
        result["confusion_matrix"] = [[1]]
    with pytest.raises(ValueError):
        validate(parameters, result)


@pytest.mark.parametrize("operation_id", [x for x in eo.OPERATIONS if "accuracy" not in x])
@pytest.mark.parametrize("field,value", [("unit", "unknown"), ("crs", "EPSG:4326"),
                                          ("transform", [100, 10, 0, 30, 0, -10]),
                                          ("values", [[float("nan"), 0], [0, None]])])
def test_output_validation_rejects_forged_grids_and_nonfinite_values(operation_id, field, value):
    parameters = deepcopy(eo.EXAMPLES[operation_id])
    result = eo.OPERATIONS[operation_id](parameters)
    result["raster"][field] = value
    with pytest.raises(ValueError):
        eo.OUTPUT_VALIDATORS[operation_id](parameters, result)


@pytest.mark.parametrize("operation_id", eo.OPERATIONS)
def test_output_validation_rejects_forged_semantic_declarations(operation_id):
    parameters = deepcopy(eo.EXAMPLES[operation_id])
    result = eo.OPERATIONS[operation_id](parameters)
    if "interpretation" in result:
        result["interpretation"] = "Scientifically and independently validated"
    else:
        result["edge_rule"] = "Periodic wrap"
    with pytest.raises(ValueError):
        eo.OUTPUT_VALIDATORS[operation_id](parameters, result)


def test_output_validation_rejects_mask_and_count_forgery():
    p = params("classify")
    result = eo.classify(p)
    result["raster"]["values"][1][1] = 1.0
    with pytest.raises(ValueError, match="mask"):
        eo.validate_classify(p, result)
    result = eo.classify(p)
    result["valid_cell_count"] = True
    with pytest.raises(ValueError):
        eo.validate_classify(p, result)
    p = params("accuracy")
    result = eo.accuracy(p)
    result["reference_authenticity_verified"] = True
    with pytest.raises(ValueError):
        eo.validate_accuracy(p, result)


def test_structural_validation_intentionally_does_not_certify_numerical_values():
    # Numeric replay, not schema inspection, must catch an otherwise well-formed
    # altered computation. This is a declared verification boundary.
    p = params("normalized-difference")
    result = eo.normalized_difference(p)
    result["raster"]["values"][0][0] = 0.123
    eo.validate_normalized_difference(p, result)
