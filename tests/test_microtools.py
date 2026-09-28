# SPDX-License-Identifier: MPL-2.0
"""Numerical and transport checks for the real CSR kernel, not a reference double."""
import json
import math
import subprocess
import sys
from copy import deepcopy

import numpy as np
import pytest

from geodesic_testbed import microtools as m


def source(**changes):
    value = {"arc_length": [0.0, 1.0, 2.0], "curvature": 0.0,
             "length_unit": "m", "frame": "example/surface"}
    value.update(changes)
    return value


@pytest.mark.parametrize("curvature", [-1.0, 0.0, 1.0])
def test_transfer_against_independent_closed_form(curvature):
    grid = np.array([0.0, 0.2, 0.9, 1.7])
    actual = m.transfer_map(grid, curvature).matrices()
    for s, matrix in zip(grid, actual, strict=True):
        a = math.cosh(s) if curvature < 0 else math.cos(s) if curvature > 0 else 1.0
        b = math.sinh(s) if curvature < 0 else math.sin(s) if curvature > 0 else s
        np.testing.assert_allclose(matrix, [[a, b], [-curvature*b, a]], rtol=1e-13, atol=1e-14)
    np.testing.assert_allclose(np.linalg.det(actual), 1.0, rtol=1e-12, atol=1e-12)


@pytest.mark.parametrize("curvature", [-0.7, 0.0, 0.7])
def test_semigroup(curvature):
    phi = m.transfer_map([0.2, 0.7, 0.9], curvature).matrices()
    np.testing.assert_allclose(phi[0] @ phi[1], phi[2], atol=1e-13)


def test_plane_pose_and_no_mutation():
    grid = np.array([0.0, 1.0, 2.0])
    initial = np.array([0.002, -0.001])
    grid_before, initial_before = grid.copy(), initial.copy()
    result = m.propagate_pose(grid, 0, initial)
    np.testing.assert_allclose(result, [[0.002, -0.001], [0.001, -0.001], [0, -0.001]])
    np.testing.assert_array_equal(grid, grid_before)
    np.testing.assert_array_equal(initial, initial_before)
    result[0, 0] = 999
    assert initial[0] == 0.002


def test_box_is_not_rss_and_uses_both_axes():
    result = m.propagate_box([0, 1, 2], 0, [0.002, 0.001])
    np.testing.assert_allclose(result, [[0.002, 0.001], [0.003, 0.001], [0.004, 0.001]])
    assert result[-1, 0] > math.hypot(0.002, 0.002)
    curved = m.propagate_box([0, 0.5], 1, [0.002, 0.001])
    assert curved[-1, 1] > 0.001


def test_full_correlated_covariance_and_exact_singular_zero():
    # Plane at s=2: [[1,2],[0,1]] [[4,1],[1,1]] Phi^T = [[12,3],[3,1]].
    covariance = np.array([[4.0, 1.0], [1.0, 1.0]])
    result = m.propagate_covariance([0, 2], 0, covariance)
    np.testing.assert_allclose(result[1], [[12, 3], [3, 1]])
    np.testing.assert_array_equal(covariance, [[4, 1], [1, 1]])
    np.testing.assert_array_equal(m.propagate_covariance([0, 2], 0, [[0, 0], [0, 0]]),
                                  np.zeros((2, 2, 2)))


@pytest.mark.parametrize("covariance", [[[1, 2], [2, 1]], [[1, 0.1], [0.2, 1]],
                                        [[True, 0], [0, 1]], [[1, 0], [0, float("nan")]]])
def test_covariance_refuses_without_repair(covariance):
    with pytest.raises(ValueError):
        m.propagate_covariance([0, 1], 0, covariance)


@pytest.mark.parametrize("operation,extra", [
    (m.OPERATIONS[0], {"initial_error": [0.002, 0.001]}),
    (m.OPERATIONS[1], {"initial_bounds": [0.002, 0.001], "tolerances": [0.004, 0.001]}),
    (m.OPERATIONS[2], {"covariance": [[4e-6, 1e-6], [1e-6, 1e-6]]}),
])
def test_evaluate_is_detached_and_preserves_scope(operation, extra):
    request = source(**extra)
    before = deepcopy(request)
    result = m.evaluate(operation, request)
    assert request == before and result["request"] == before
    assert result["coordinate"] == "arc_length" and result["scope"] == m.SCOPE
    assert result["verification_id"] is None and result["verification_status"] == "not_verified"
    assert result["units"] == ["m", "rad"]
    result["request"]["arc_length"][0] = 99
    assert request == before
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("limit,status", [(0.004, "PASS"), (0.003, "FAIL")])
def test_sampled_tolerance_boundary(limit, status):
    result = m.evaluate(m.OPERATIONS[1], source(initial_bounds=[0.002, 0.001],
                                              tolerances=[limit, 0.001]))
    assert result["tolerance_check"]["status"] == status
    assert result["tolerance_check"]["sample_pass"][-1] == (status == "PASS")


@pytest.mark.parametrize("grid,curvature", [([], 0), ([[0, 1]], 0), ([0, 0], 0),
    ([1, 0], 0), ([-1, 0], 0), ([0, 1e7], 0), ([0, 5], 1), ([0, 1], 1e-15),
    ([0, 1], 1e7), ([0, True], 0), ([0, "1"], 0), ([0, float("inf")], 0),
    ([0, 1], True), (list(range(513)), 0), ([0, 1e-200], 0)])
def test_grid_profile_refusals(grid, curvature):
    with pytest.raises((ValueError, TypeError)):
        m.transfer_map(grid, curvature)


@pytest.mark.parametrize("extra", [{"initial_error": [0]}, {"initial_error": [0, True]},
    {"initial_error": [0, "1"]}, {"initial_error": [0, float("nan")]}])
def test_pose_refusals(extra):
    with pytest.raises(ValueError):
        m.evaluate(m.OPERATIONS[0], source(**extra))


@pytest.mark.parametrize("bounds,limits", [([-1, 0], [1, 1]), ([0, 0], [-1, 1]),
                                            ([0, 0], [1, True]), ([0], [1, 1])])
def test_box_refusals(bounds, limits):
    with pytest.raises(ValueError):
        m.evaluate(m.OPERATIONS[1], source(initial_bounds=bounds, tolerances=limits))


@pytest.mark.parametrize("changes", [{"length_unit": "ft"}, {"frame": " "},
    {"frame": "x"*257}, {"unexpected": 2}, {"curvature": "0"}])
def test_metadata_refusals(changes):
    with pytest.raises(ValueError):
        m.evaluate(m.OPERATIONS[0], source(initial_error=[0, 0], **changes))


def test_no_claim_of_independent_samples():
    result = m.evaluate(m.OPERATIONS[2], source(covariance=[[1, 0], [0, 1]]))
    assert result["tolerance_check"] is None
    assert "confidence" not in result and "joint_covariance" not in result


def test_unit_rescaling_of_pose():
    metres = m.propagate_pose([0, 0.5], 1, [0.002, 0.001])
    millimetres = m.propagate_pose([0, 500], 1e-6, [2, 0.001])
    np.testing.assert_allclose(millimetres[:, 0]/1000, metres[:, 0], rtol=1e-13)
    np.testing.assert_allclose(millimetres[:, 1], metres[:, 1], rtol=1e-13)


def worker(raw):
    completed = subprocess.run([sys.executable, "-m", "geodesic_testbed.microtools"],
                               input=raw, capture_output=True, timeout=15, check=True)
    return json.loads(completed.stdout)


def test_real_worker():
    request = {"schema": "ciw.adapter-request.v1", "operation_id": m.OPERATIONS[1],
               "inputs": source(initial_bounds=[0.002, 0.001], tolerances=[0.003, 0.001])}
    result = worker(json.dumps(request).encode())
    assert result["status"] == "ok" and result["data"]["tolerance_check"]["status"] == "FAIL"


@pytest.mark.parametrize("raw", [b'{"schema":1,"schema":2}', b'{"x":NaN}',
    b'{"x":1e-999}', b'{"x":1e999}', b'not json', b'\xff', b' '*65537,
    b'{"schema":"ciw.adapter-request.v1","operation_id":"unknown.v1","inputs":{}}'])
def test_worker_refusal_has_no_numerical_result(raw):
    result = worker(raw)
    assert result["status"] == "refused" and "data" not in result
