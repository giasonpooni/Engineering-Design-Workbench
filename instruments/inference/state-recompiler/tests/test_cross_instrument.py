"""Live pinned-provider comparisons, not an integration claim from a citation."""

import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from cbsr import reconcile_affine_exact


ROOT = Path(__file__).parents[1]
PINS = json.loads((ROOT / "validation/cross-instrument-pins.json").read_text())


def _provider(name):
    location = os.environ.get(f"CBSR_{name.upper()}_REPO")
    if location is None:
        pytest.skip(f"set CBSR_{name.upper()}_REPO to run pinned cross-instrument checks")
    path = Path(location).resolve()
    pin = PINS[name]
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=path, text=True).strip()
    assert actual == pin["commit"], f"{name}: provider revision differs from declared pin"
    subprocess.run(["git", "diff", "--exit-code", "HEAD", "--"], cwd=path, check=True, capture_output=True)
    for file, expected in pin["files"].items():
        assert hashlib.sha256((path / file).read_bytes()).hexdigest() == expected
    sys.path.insert(0, str(path / "src"))
    return path


def _request():
    return json.loads((ROOT / "examples/affine_exact.json").read_text())


def test_fsrt_pinned_mass_balance_projects_same_declared_exact_system():
    path = _provider("fsrt")
    module = importlib.import_module("set_lcm.lcm")
    assert Path(module.__file__).is_relative_to(path / "src")
    schema = importlib.import_module("set_lcm.schema")
    value = _request()
    constraint = schema.ConstraintSet("closed-v1", np.array([[1., 1.]]), np.array([100.]), "declared mass sum")
    expected_x, expected_P = module.project_hard(np.array(value["estimate"]), np.array(value["covariance"]), constraint)
    actual = reconcile_affine_exact(value)
    assert actual["status"] == "accepted"
    np.testing.assert_allclose(actual["reconciled"]["estimate"], expected_x, atol=1e-13)
    np.testing.assert_allclose(actual["reconciled"]["covariance"], expected_P, atol=1e-13)
    expected_stat = module.consistency_stat(np.array(value["estimate"]), np.array(value["covariance"]), constraint)
    assert actual["normalized_residual"] == pytest.approx(expected_stat)


def test_fsrt_pinned_camera_gauge_fusion_matches_declared_common_level_constraint():
    _provider("fsrt")
    camera = importlib.import_module("set_lcm.camera")
    fusion = importlib.import_module("set_lcm.camera_fusion")
    values = np.array([1.2, .9])
    joint = np.array([[.04, .006], [.006, .09]])
    level = camera.LevelSeries(values[1:], joint[1:, 1:], values[1:], ("ok",), (0,), ("calibration:test",), ())
    expected = fusion.compare_level_sources([0], values[:1], joint[:1, :1], [0], level,
                                           cross_covariance=joint[:1, 1:])
    value = _request()
    value.update(estimate=values.tolist(), covariance=joint.tolist(), crosscov_policy="declared",
                 state_labels=["gauge_level", "camera_level"], state_units=["m", "m"])
    value["constraints"].update(coefficients=[[1, -1]], rhs=[0], row_units=["m"],
                                constraint_id="fixture:declared-common-level")
    actual = reconcile_affine_exact(value)
    assert actual["status"] == "accepted"
    np.testing.assert_allclose(actual["reconciled"]["estimate"], np.repeat(expected.series["combined"].heights[0], 2))
    np.testing.assert_allclose(actual["reconciled"]["covariance"], np.full((2, 2), expected.series["combined"].covariance[0, 0]))
    # The agreement law is caller-declared; CBSR does not infer which port failed.
    assert actual["claims"]["fault_isolation"] is False


def test_gte_pinned_fixture_tangent_at_basepoint_has_same_covariance_projection():
    path = _provider("gte")
    geometry = importlib.import_module("geodesic_telemetry.geometry")
    assert Path(geometry.__file__).is_relative_to(path / "src")
    fixture = json.loads((path / "examples/circle.json").read_text())
    constraint = fixture["constraint"]
    projected, _ = geometry.project_circle(fixture["observations"]["points_m"], constraint["center_m"], constraint["radius_m"])
    # Evaluate the Jacobian at the circle, not at the off-circle raw samples:
    # away from the circle GTE also includes radius/distance scaling.
    _, jacobian = geometry.project_circle(projected[:1], constraint["center_m"], constraint["radius_m"])
    expected_P = geometry.propagate_joint_covariance(np.eye(2), jacobian)
    value = _request()
    value.update(estimate=projected[0].tolist(), covariance=[[1, 0], [0, 1]],
                 state_labels=["x", "y"], state_units=["m", "m"], frame_ref="bench-plane")
    value["constraints"].update(coefficients=[[1, 0]], rhs=[1], row_units=["m"],
                                constraint_id="fixture:declared-tangent-x-equals-1-at-circle-basepoint")
    actual = reconcile_affine_exact(value)
    assert actual["status"] == "accepted"
    np.testing.assert_allclose(actual["reconciled"]["covariance"], expected_P, atol=1e-14)
    np.testing.assert_allclose(actual["reconciled"]["estimate"], projected[0])


def test_affine_tangent_is_not_silently_promoted_to_global_circle_projection():
    _provider("gte")
    geometry = importlib.import_module("geodesic_telemetry.geometry")
    value = _request()
    value.update(estimate=[1, .2], covariance=[[1, 0], [0, 1]],
                 state_labels=["x", "y"], state_units=["m", "m"])
    value["constraints"].update(coefficients=[[1, 0]], rhs=[1], row_units=["m"],
                                constraint_id="fixture:declared-tangent-not-circle")
    affine = reconcile_affine_exact(value)
    nonlinear, _ = geometry.project_circle([value["estimate"]], [0, 0], 1)
    assert affine["reconciled"]["estimate"] == [1, .2]
    assert np.linalg.norm(affine["reconciled"]["estimate"]) > 1
    assert np.linalg.norm(nonlinear[0]) == pytest.approx(1)
    assert not np.allclose(affine["reconciled"]["estimate"], nonlinear[0])
