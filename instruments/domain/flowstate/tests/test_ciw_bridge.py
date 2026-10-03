"""The JSON seam must preserve the domain kernel, covariance and refusals."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from set_lcm.bridge.ciw import evaluate
from set_lcm.lcm import chi2_quantile, consistency_stat, reconcile
from set_lcm.schema import ConstraintSet, Observation
from set_lcm.testbed.estimators import KalmanFilter

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def request_data():
    return json.loads((ROOT / "examples/ciw_tank_request.json").read_text())


def observation(request_data):
    return request_data["inputs"]["observations"][0]


def test_endpoint_matches_existing_domain_kernel_with_full_covariance(request_data):
    untouched = deepcopy(request_data)
    response = evaluate(request_data)
    assert response["status"] == "ok"
    out = response["data"]
    row = observation(request_data)
    kf = KalmanFilter([50, 50], 5, 1, np.zeros(1))
    kf.ingest(Observation(0., 0., np.array(row["values"]), np.array(row["covariance"]),
                          np.array(row["mask"]), tuple(row["source_ids"])), 0)
    x, P = kf.report(0)
    cs = ConstraintSet("direct", np.ones((1, 2)), np.array([100.]), "direct", b_var=np.array([.25]))
    score = consistency_stat(x, P, cs)
    expected = reconcile(x, P, cs, mode="hard", hold=score > chi2_quantile(1, .999))
    np.testing.assert_array_equal(out["estimate"]["values"], expected.x)
    np.testing.assert_array_equal(out["estimate"]["covariance"], expected.P)
    np.testing.assert_array_equal(out["unprojected_estimate"]["covariance"], P)
    assert out["calibrated_observation"]["covariance"][0][1] == .25
    assert out["diagnostics"]["physical_model_status"] == "consistent"
    assert out["diagnostics"]["fault_attribution"] == "not_tested"
    assert request_data == untouched
    assert evaluate(request_data) == response
    diagonal = deepcopy(request_data)
    observation(diagonal)["covariance"] = [[1., 0.], [0., 1.]]
    assert evaluate(diagonal)["data"]["estimate"]["covariance"] != out["estimate"]["covariance"]


def test_model_disagreement_retains_estimate_and_declines_fault_attribution(request_data):
    observation(request_data)["values"] = [60., 50.]
    out = evaluate(request_data)["data"]
    assert out["diagnostics"]["physical_model_status"] == "physical_model_disagreement"
    assert out["diagnostics"]["fault_attribution"] == "confounded_or_unidentifiable"
    assert out["diagnostics"]["reconciliation_status"] == "model_inconsistent"
    assert out["estimate"]["values"] == out["unprojected_estimate"]["values"]
    assert out["estimate"]["covariance"] == out["unprojected_estimate"]["covariance"]
    assert out["residuals"]["balance_before"][0] > 0
    assert out["residuals"]["balance_after"] is None
    assert out["residuals"]["correction"] is None
    assert not out["diagnostics"]["physical_truth_verified"]


def test_missing_channel_is_absent_not_zero_or_fabricated_observation(request_data):
    row = observation(request_data)
    row["values"][1] = None
    row["mask"][1] = False
    out = evaluate(request_data)["data"]
    assert out["calibrated_observation"]["values"][1] is None
    assert out["residuals"]["innovation"][1] is None
    assert out["residuals"]["innovation_variance"][1] is None
    assert out["diagnostics"]["missing_sources"] == ["SYNTHETIC-tank-2"]
    assert out["diagnostics"]["fault_attribution"] == "confounded_or_unidentifiable"
    assert out["unprojected_estimate"]["covariance"][1][1] == 25.
    json.dumps(out, allow_nan=False)


@pytest.mark.parametrize("field,value,code", [
    ("covariance", [[1., 2.], [2., 1.]], "numerical_refusal"),
    ("covariance", [[1., 1.], [1., 1.]], "numerical_refusal"),
    ("covariance", [[1., .1], [.2, 1.]], "numerical_refusal"),
    ("covariance", [1., 1.], "invalid_input"),
    ("covariance", [[True, 0], [0, 1]], "invalid_input"),
    ("values", [52., float("nan")], "invalid_input"),
    ("values", [True, 46.], "invalid_input"),
    ("values", [52., "46"], "invalid_input"),
    ("values", [-1., 46.], "invalid_input"),
    ("values", [52.], "invalid_input"),
    ("mask", [True, 1], "invalid_input"),
    ("mask", [True, False], "invalid_input"),
    ("mask", [False, False], "insufficient_observations"),
    ("arrival_t", -1., "invalid_input"),
    ("unit", "m", "unsupported_unit"),
    ("source_ids", ["tank", "tank"], "invalid_input"),
    ("evidence_ids", ["same", "same"], "invalid_input"),
])
def test_invalid_observations_refuse_without_result(request_data, field, value, code):
    observation(request_data)[field] = value
    out = evaluate(request_data)
    assert out["status"] == "refused"
    assert "data" not in out
    assert out["refusal"]["code"] == code
    json.dumps(out, allow_nan=False)


def test_unsupported_temporal_batch_never_drops_correlations(request_data):
    request_data["inputs"]["observations"].append(deepcopy(observation(request_data)))
    out = evaluate(request_data)
    assert out["refusal"]["code"] == "unsupported_temporal_covariance"
    assert "data" not in out


def test_balance_consistency_never_admits_negative_physical_mass(request_data):
    request_data["inputs"]["model"].update(prior_mean=[0, 0], prior_std=100,
                                           total_mass_kg=0, total_mass_variance_kg2=0)
    observation(request_data).update(values=[1, 2], covariance=[[100, 0], [0, 100]])
    out = evaluate(request_data)
    assert out["status"] == "refused"
    assert out["refusal"]["code"] == "physical_model_refusal"
    assert "data" not in out


def test_unknown_fields_and_hidden_truth_are_refused(request_data):
    request_data["inputs"]["truth"] = {"state": [50., 50.]}
    assert evaluate(request_data)["refusal"]["code"] == "invalid_input"


@pytest.mark.parametrize("field,value", [("prior_std", 0), ("prior_std", True),
                                         ("total_mass_variance_kg2", -1), ("prior_mean", [5])])
def test_invalid_model_fails_before_kernel(request_data, field, value):
    request_data["inputs"]["model"][field] = value
    assert evaluate(request_data)["refusal"]["code"] == "invalid_input"


def test_subprocess_strict_json_and_offline_fixture(request_data):
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    command = [sys.executable, "-m", "set_lcm.bridge.ciw"]
    proc = subprocess.run(command, input=json.dumps(request_data), text=True, capture_output=True,
                          check=True, cwd=ROOT, env=env, timeout=10)
    assert proc.stderr == ""
    assert json.loads(proc.stdout) == evaluate(request_data)
    for invalid in ('{"value":NaN}', '{"incomplete":', 'null', '{"inputs":{},"inputs":{}}'):
        proc = subprocess.run(command, input=invalid, text=True, capture_output=True,
                              check=True, cwd=ROOT, env=env, timeout=10)
        out = json.loads(proc.stdout)
        assert out["status"] == "refused"
        assert "data" not in out
