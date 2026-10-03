"""Analytic reference cases and scientific-boundary failures for GIS operations."""

from copy import deepcopy
import json
import math

import numpy as np
import pytest

from net_geomatics.common import example_raster
from net_geomatics.gis import (
    EXAMPLES, OPERATIONS, OUTPUT_VALIDATORS, WGS84_A_M, WGS84_F,
    coordinates_enu, raster_suitability, raster_zonal, terrain_slope,
)


def position(lon=0, lat=0, height=0):
    return {"longitude_deg": lon, "latitude_deg": lat, "ellipsoid_height_m": height}


def test_enu_equator_analytic_axes_and_pole():
    result = coordinates_enu({"origin": position(), "points": [
        position(), position(height=100), position(lon=90), position(lat=90),
    ]})
    a = WGS84_A_M
    b = a * (1 - WGS84_F)
    assert result["origin_ecef_m"] == pytest.approx([a, 0, 0], abs=1e-8)
    expected = [[0, 0, 0], [0, 0, 100], [a, 0, -a], [0, b, -a]]
    for point, local in zip(result["points"], expected):
        assert point["enu_m"] == pytest.approx(local, abs=1e-8)
    assert result["points"][-1]["ecef_m"] == pytest.approx([0, 0, b], abs=1e-8)


def test_local_up_and_cartesian_distance_preservation_at_oblique_origin():
    origin = position(lon=-79.5, lat=43.77, height=160)
    result = coordinates_enu({"origin": origin, "points": [
        position(lon=-79.5, lat=43.77, height=180), position(lon=-79.49, lat=43.78),
    ]})
    assert result["points"][0]["enu_m"] == pytest.approx([0, 0, 20], abs=1e-8)
    distant = result["points"][1]
    displacement = np.asarray(distant["ecef_m"]) - result["origin_ecef_m"]
    assert np.linalg.norm(displacement) == pytest.approx(np.linalg.norm(distant["enu_m"]), rel=1e-13)


@pytest.mark.parametrize("bad", [position(lon=181), position(lat=-91), position(height=1e8),
                                  position(lon=True), position(height=float("nan"))])
def test_coordinate_contract_rejects_invalid_numbers(bad):
    with pytest.raises(ValueError):
        coordinates_enu({"origin": position(), "points": [bad]})


def test_zonal_known_population_statistics_and_missing_zones():
    result = raster_zonal({
        "values": example_raster([[1, 3, None], [None, 99, 0]], "K"),
        "zones": example_raster([[2, 2, 3], [2, None, 0]]),
    })
    by_zone = {zone["zone"]: zone for zone in result["zones"]}
    assert by_zone[2] == {"zone": 2, "count": 2, "missing_count": 1,
                          "mean": 2.0, "min": 1.0, "max": 3.0, "population_std": 1.0}
    assert by_zone[3] == {"zone": 3, "count": 0, "missing_count": 1,
                          "mean": None, "min": None, "max": None, "population_std": None}
    assert by_zone[0]["mean"] == 0
    assert by_zone[0]["population_std"] == 0
    assert result["unassigned_cell_count"] == 1
    assert result["value_unit"] == "K"


def test_zonal_singleton_zones_and_empty_assignment():
    # Independent cells must retain their value, even with many distinct zones.
    result = raster_zonal({
        "values": example_raster([[11] * 64 for _ in range(64)]),
        "zones": example_raster([[row * 64 + col for col in range(64)] for row in range(64)]),
    })
    assert len(result["zones"]) == 4096
    assert all(zone["mean"] == 11 and zone["count"] == 1 and zone["population_std"] == 0
               for zone in result["zones"])
    empty = raster_zonal({"values": example_raster([[3]]), "zones": example_raster([[None]])})
    assert empty["zones"] == []
    assert empty["unassigned_cell_count"] == 1


@pytest.mark.parametrize("label", [1.25, 2**53, True, float("inf")])
def test_zonal_rejects_non_integer_and_unsafe_labels(label):
    with pytest.raises(ValueError):
        raster_zonal({"values": example_raster([[1]]), "zones": example_raster([[label]])})


@pytest.mark.parametrize("change", ["crs", "transform", "shape"])
def test_zonal_refuses_spatial_misalignment(change):
    values, zones = example_raster([[1, 2], [3, 4]]), example_raster([[1, 1], [2, 2]])
    if change == "crs":
        zones["crs"] = "LOCAL_METRE:another-site"
    elif change == "transform":
        zones["transform"][0] = 0.01
    else:
        zones["values"] = [[1, 2]]
    with pytest.raises(ValueError, match="must match"):
        raster_zonal({"values": values, "zones": zones})


def plane():
    # Raster row increases south: x=10*column, y=-10*row, z=2*x+3*y+100.
    return example_raster([[100 + 20 * col - 30 * row for col in range(5)] for row in range(5)], "m")


def test_slope_exact_plane_and_boundary_contract():
    result = terrain_slope({"elevation": plane()})
    slope = result["slope_degrees"]["values"]
    expected = math.degrees(math.atan(math.sqrt(13)))
    for row in range(1, 4):
        assert slope[row][1:4] == pytest.approx([expected] * 3)
        assert result["dz_dx"]["values"][row][1:4] == [2.0] * 3
        assert result["dz_dy"]["values"][row][1:4] == [3.0] * 3
    assert slope[0] == slope[-1] == [None] * 5
    assert all(row[0] is None and row[-1] is None for row in slope)


def test_slope_flat_terrain_and_missing_stencil():
    elevation = example_raster([[7] * 5 for _ in range(5)], "m")
    elevation["values"][2][2] = None
    output = terrain_slope({"elevation": elevation})["slope_degrees"]["values"]
    assert output[1][1] == output[1][3] == output[3][1] == output[3][3] == 0.0
    for row, col in [(1, 2), (2, 1), (2, 2), (2, 3), (3, 2)]:
        assert output[row][col] is None


@pytest.mark.parametrize("change", ["angular", "height_unit", "shape"])
def test_slope_rejects_unsupported_coordinate_or_height_contract(change):
    elevation = plane()
    if change == "angular":
        elevation["crs"] = "EPSG:4326"
    elif change == "height_unit":
        elevation["unit"] = "ft"
    else:
        elevation["values"] = [[1, 2], [3, 4]]
    with pytest.raises(ValueError):
        terrain_slope({"elevation": elevation})


def test_slope_rejects_overflow_in_declared_finite_difference():
    elevation = plane()
    elevation["transform"][1] = 1e-320
    with pytest.raises(ValueError, match="overflow"):
        terrain_slope({"elevation": elevation})


def test_suitability_known_weighted_score_and_conservative_mask():
    result = raster_suitability({
        "criteria": [example_raster([[0, 1, None], [0.5, 1, 0]]),
                     example_raster([[1, 0, 0.2], [0.5, None, 0]])],
        "weights": [0.75, 0.25],
    })
    assert result["suitability"]["values"] == [[0.25, 0.75, None], [0.5, None, 0.0]]
    assert result["effective_weights"] == [0.75, 0.25]


def test_suitability_zero_weight_does_not_erase_missing_data():
    result = raster_suitability({"criteria": [example_raster([[1]]), example_raster([[None]])],
                                 "weights": [1, 0]})
    assert result["suitability"]["values"] == [[None]]


@pytest.mark.parametrize("weights", [[1, 1], [-1, 2], [True, 0], [1], [float("inf"), 0]])
def test_suitability_rejects_bad_weights(weights):
    with pytest.raises(ValueError):
        raster_suitability({"criteria": [example_raster([[0]]), example_raster([[1]])], "weights": weights})


@pytest.mark.parametrize("value", [-0.01, 1.01, True, float("nan")])
def test_suitability_refuses_unnormalized_or_invalid_criteria(value):
    with pytest.raises(ValueError):
        raster_suitability({"criteria": [example_raster([[value]])], "weights": [1]})


def test_suitability_refuses_shifted_grid():
    first, second = example_raster([[1]]), example_raster([[1]])
    second["transform"][3] = 31
    with pytest.raises(ValueError, match="must match"):
        raster_suitability({"criteria": [first, second], "weights": [0.5, 0.5]})


@pytest.mark.parametrize("operation_id", sorted(OPERATIONS))
def test_examples_are_json_safe_deterministic_and_do_not_mutate_inputs(operation_id):
    params = deepcopy(EXAMPLES[operation_id])
    original = deepcopy(params)
    output = OPERATIONS[operation_id](params)
    assert output == OPERATIONS[operation_id](params)
    assert params == original
    assert output["assumptions"]
    json.dumps(output, allow_nan=False)
    with pytest.raises(ValueError, match="Unexpected or missing fields"):
        OPERATIONS[operation_id]({**params, "unexpected": 1})


@pytest.mark.parametrize("operation_id", sorted(OPERATIONS))
def test_output_validation_checks_structure_without_executing_provider(operation_id, monkeypatch):
    params = deepcopy(EXAMPLES[operation_id])
    output = OPERATIONS[operation_id](params)
    monkeypatch.setitem(OPERATIONS, operation_id, lambda *args: pytest.fail("validator executed operation"))
    OUTPUT_VALIDATORS[operation_id](params, output)
    with pytest.raises(ValueError):
        OUTPUT_VALIDATORS[operation_id](params, {})
    output["assumptions"] = []
    with pytest.raises(ValueError, match="assumptions"):
        OUTPUT_VALIDATORS[operation_id](params, output)


@pytest.mark.parametrize("change", ["count", "vector", "nonfinite", "datum"])
def test_enu_output_contract_rejects_impossible_representation(change):
    op = "geomatics.coordinates.enu.v1"
    params = deepcopy(EXAMPLES[op])
    output = OPERATIONS[op](params)
    if change == "count":
        output["points"].pop()
    elif change == "vector":
        output["points"][0]["enu_m"] = [0, 0]
    elif change == "nonfinite":
        output["origin_ecef_m"][0] = float("nan")
    else:
        output["datum"] = "unspecified"
    with pytest.raises(ValueError):
        OUTPUT_VALIDATORS[op](params, output)


@pytest.mark.parametrize("change", ["count", "duplicate", "negative_std", "unit", "all_missing"])
def test_zonal_output_contract_rejects_broken_counts_and_statistics(change):
    op = "geomatics.raster.zonal.v1"
    params = deepcopy(EXAMPLES[op])
    output = OPERATIONS[op](params)
    if change == "count":
        output["zones"][0]["count"] = True
    elif change == "duplicate":
        output["zones"][1] = deepcopy(output["zones"][0])
    elif change == "negative_std":
        output["zones"][1]["population_std"] = -1
    elif change == "unit":
        output["value_unit"] = "K"
    else:
        output["zones"][-1]["mean"] = 0
    with pytest.raises(ValueError):
        OUTPUT_VALIDATORS[op](params, output)


@pytest.mark.parametrize("change", ["shape", "transform", "unit", "mask", "range", "boolean"])
def test_terrain_output_contract_preserves_alignment_and_null_stencil(change):
    op = "geomatics.terrain.slope.v1"
    params = deepcopy(EXAMPLES[op])
    output = OPERATIONS[op](params)
    field = output["slope_degrees"]
    if change == "shape":
        field["values"].pop()
    elif change == "transform":
        field["transform"][0] = 1
    elif change == "unit":
        field["unit"] = "rad"
    elif change == "mask":
        field["values"][0][0] = 0
    elif change == "range":
        field["values"][1][1] = 91
    else:
        field["values"][1][1] = False
    with pytest.raises(ValueError):
        OUTPUT_VALIDATORS[op](params, output)


@pytest.mark.parametrize("change", ["weight_count", "weight_values", "range", "mask", "crs"])
def test_suitability_output_contract_checks_weights_and_supported_score_range(change):
    op = "geomatics.raster.suitability.v1"
    params = deepcopy(EXAMPLES[op])
    output = OPERATIONS[op](params)
    if change == "weight_count":
        output["effective_weights"] = [1]
    elif change == "weight_values":
        output["effective_weights"] = [0.25, 0.75]
    elif change == "range":
        output["suitability"]["values"][0][0] = 1.01
    elif change == "mask":
        output["suitability"]["values"][2][1] = 0
    else:
        output["suitability"]["crs"] = "LOCAL_METRE:another-frame"
    with pytest.raises(ValueError):
        OUTPUT_VALIDATORS[op](params, output)
