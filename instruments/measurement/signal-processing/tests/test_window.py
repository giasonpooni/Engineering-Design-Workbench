# SPDX-License-Identifier: MPL-2.0
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from stfe import ContractError, OPERATION_ID, window_mean
from stfe.window import canonical, digest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def request_data():
    return json.loads((ROOT / "examples/window_mean.json").read_text())


def test_full_covariance_not_silent_independence(request_data):
    result = window_mean(request_data)
    artifact = result["result_artifact"]
    assert artifact["components"] == [{"name": "temperature.mean", "value": 12.0, "unit": "degC"}]
    assert artifact["covariance"]["matrix"] == [[3.0]]  # not 2 from silently dropping crosscov
    assert artifact["covariance"]["status"] == "propagated"
    assert result["window"]["samples"][0]["value"] == 10.0
    assert artifact["authority"]["may_authorize"] is False


def test_unknown_is_not_zero(request_data):
    request_data["uncertainty"].update(status="unknown", crosscov_policy="unknown", matrix=None)
    result = window_mean(request_data)
    assert result["result_artifact"]["covariance"]["matrix"] is None
    assert result["result_artifact"]["covariance"]["status"] == "unknown"


def test_declared_independence_must_be_explicit(request_data):
    request_data["uncertainty"].update(crosscov_policy="declared_zero", matrix=[[4, 0], [0, 4]])
    assert window_mean(request_data)["result_artifact"]["covariance"]["matrix"] == [[2.0]]


@pytest.mark.parametrize("values,matrix,message", [
    ([10, 14], [[1, 2], [2, 1]], "positive semidefinite"),
    ([10, 14], [[0, 1], [1, 4]], "zero covariance pivot"),
    ([10, 14], [[4, 2], [2.000000000000001, 4]], "symmetric"),
    ([10, 14], [[-1e-200, 0], [0, 4]], "positive semidefinite"),
    ([10, 14], [[5e-324, 0], [0, 0]], "underflow"),
    ([5e-324, 0], [[4, 2], [2, 4]], "underflow"),
])
def test_numerical_refusals(request_data, values, matrix, message):
    for sample, value in zip(request_data["samples"], values):
        sample["value"] = value
    request_data["uncertainty"]["matrix"] = matrix
    with pytest.raises(ContractError, match=message):
        window_mean(request_data)


def test_cancellation_retains_positive_variance(request_data):
    request_data["uncertainty"]["matrix"] = [[1, -1], [-1, math.nextafter(1, 2)]]
    result = window_mean(request_data)
    assert result["result_artifact"]["covariance"]["matrix"] == [[2.0**-54]]


def test_exact_singular_zero_is_allowed(request_data):
    request_data["uncertainty"]["matrix"] = [[1, -1], [-1, 1]]
    assert window_mean(request_data)["result_artifact"]["covariance"]["matrix"] == [[0.0]]


def test_mean_avoids_intermediate_overflow(request_data):
    for sample in request_data["samples"]:
        sample["value"] = 1e308
    assert window_mean(request_data)["result_artifact"]["components"][0]["value"] == 1e308


def test_complete_covariance_avoids_intermediate_overflow(request_data):
    request_data["uncertainty"]["matrix"] = [[1e308, 1e308], [1e308, 1e308]]
    assert window_mean(request_data)["result_artifact"]["covariance"]["matrix"] == [[1e308]]


@pytest.mark.parametrize("value", [True, False, "1.2", None, float("nan"), float("inf"), 2**53+1])
@pytest.mark.parametrize("location", ["value", "time", "covariance", "window"])
def test_strict_numerical_typing(request_data, value, location):
    if location == "value":
        request_data["samples"][0]["value"] = value
    elif location == "time":
        request_data["samples"][0]["event_time"] = value
    elif location == "covariance":
        request_data["uncertainty"]["matrix"][0][0] = value
    else:
        request_data["window"]["decision_time"] = value
    with pytest.raises(ContractError):
        window_mean(request_data)


@pytest.mark.parametrize("mutation", [
    lambda r: r["samples"].reverse(),
    lambda r: r["samples"][1].update(event_time=0),
    lambda r: r["samples"][1].update(event_time=1.01),
    lambda r: r["samples"].pop(),
    lambda r: r["samples"][0].update(missing=True),
    lambda r: r["samples"][0].update(missing=0),
    lambda r: r["samples"][0].update(received_at=0.51),
    lambda r: r["samples"][0].update(received_at=-0.1),
    lambda r: r["samples"][1].update(received_at=3),
    lambda r: r["window"].update(received_by=1.9),
    lambda r: r["window"].update(decision_time=1.9),
    lambda r: r["window"].update(sample_period=0),
    lambda r: r["window"].update(sample_period=0.3),
    lambda r: r["window"].update(end=33),
    lambda r: r["window"].update(max_lateness=-0.01),
    lambda r: r["uncertainty"].update(observation_refs=["observation:1", "observation:0"]),
    lambda r: r["uncertainty"].update(crosscov_policy="declared_zero"),
    lambda r: r["uncertainty"].update(crosscov_policy="unknown"),
    lambda r: r["uncertainty"].update(status="unknown"),
    lambda r: r["uncertainty"].update(matrix=[[4], [4]]),
    lambda r: r["samples"][1].update(observation_ref="observation:0"),
    lambda r: r.update(source_batch_ref="observation:0"),
    lambda r: r.update(execution_id=OPERATION_ID),
    lambda r: r.update(execution_id=r["source_batch_ref"]),
    lambda r: r.update(operation_id="invented.v1"),
    lambda r: r.update(source_batch_digest="sha256:wrong"),
    lambda r: r.update(implementation_revision="main"),
    lambda r: r.update(created_at="2026-02-30T00:00:00Z"),
    lambda r: r.update(created_at="2026-09-20"),
    lambda r: r.update(extra_policy="impute"),
    lambda r: r.update(clock_mapping_ref=""),
    lambda r: r.update(frame_mapping_ref=""),
])
def test_contract_refusals(request_data, mutation):
    mutation(request_data)
    with pytest.raises(ContractError):
        window_mean(request_data)


def test_receipt_reordering_is_refused(request_data):
    request_data["window"]["max_lateness"] = 2
    request_data["samples"][0]["received_at"] = 1.8
    request_data["samples"][1]["received_at"] = 1.7
    with pytest.raises(ContractError, match="out-of-order delivery"):
        window_mean(request_data)


def test_half_open_future_noninterference(request_data):
    original = window_mean(request_data)
    future = {"observation_ref": "future", "event_time": 2, "received_at": 999,
              "value": -999999, "missing": True}
    request_data["samples"].append(future)
    assert window_mean(request_data) == original
    future["value"] = "not evaluated because outside support"
    future["received_at"] = 1000000
    assert window_mean(request_data) == original


def test_changed_full_source_digest_retains_numerical_equivalence(request_data):
    original = window_mean(request_data)
    request_data["source_batch_digest"] = "sha256:" + "b" * 64
    changed = window_mean(request_data)
    assert original["numerical_result_id"] == changed["numerical_result_id"]
    assert original["window"]["window_id"] != changed["window"]["window_id"]
    assert original["result_artifact"]["result_id"] != changed["result_artifact"]["result_id"]


def test_distinct_execution_and_stable_numerical_identity(request_data):
    original = window_mean(request_data)
    request_data.update(execution_id="execution:replay", created_at="2026-09-21T00:00:00Z")
    replay = window_mean(request_data)
    assert original["numerical_result_id"] == replay["numerical_result_id"]
    assert original["window"]["window_id"] == replay["window"]["window_id"]
    assert original["result_artifact"]["result_id"] != replay["result_artifact"]["result_id"]
    assert len({original["result_artifact"]["result_id"], original["execution"]["execution_id"],
                original["window"]["window_id"], original["numerical_result_id"], OPERATION_ID}) == 5


def test_changed_input_config_is_not_same_numerical_result(request_data):
    original = window_mean(request_data)
    request_data["samples"][0]["value"] += 1
    assert window_mean(request_data)["numerical_result_id"] != original["numerical_result_id"]


def test_input_not_mutated_and_result_is_detached(request_data):
    before = deepcopy(request_data)
    result = window_mean(request_data)
    assert before == request_data
    result["window"]["samples"][0]["value"] = -100
    assert before == request_data


def test_documented_hashes_bind_content(request_data):
    receipt = window_mean(request_data)
    artifact = deepcopy(receipt["result_artifact"])
    actual = artifact.pop("result_id")
    assert actual == "sha256:" + sha256(
        artifact["schema"].encode() + b"\x00" + canonical(artifact).encode()
    ).hexdigest()
    for key, field, prefix in [("window", "window_id", "stfe-window:"),
                               ("quality", "quality_id", "stfe-quality:")]:
        record = deepcopy(receipt[key])
        actual = record.pop(field)
        assert actual == prefix + digest(record).split(":")[1]
    assert receipt["numerical_result_id"] == "stfe-numerical:" + digest(receipt["numerical_result"]).split(":")[1]


@pytest.mark.parametrize("count", [1, 2, 3, 8, 32])
def test_numpy_oracle(request_data, count):
    rng = np.random.default_rng(count)
    # Integer PSD matrices are exact binary64 fixtures, unlike a silently
    # repaired random floating near-singular covariance.
    matrix = rng.integers(-5, 6, size=(count, count))
    matrix = matrix @ matrix.T
    values = rng.normal(size=count)
    refs = [f"observation:{i}" for i in range(count)]
    request_data["samples"] = [{"observation_ref": refs[i], "event_time": i,
        "received_at": i, "value": float(values[i]), "missing": False} for i in range(count)]
    request_data["window"].update(end=count, received_by=count, decision_time=count)
    request_data["uncertainty"].update(matrix=matrix.tolist(), observation_refs=refs)
    artifact = window_mean(request_data)["result_artifact"]
    weights = np.full(count, 1.0 / count)
    assert artifact["components"][0]["value"] == pytest.approx(float(np.mean(values)), rel=2e-14, abs=1e-15)
    assert artifact["covariance"]["matrix"][0][0] == pytest.approx(float(weights @ matrix @ weights), rel=2e-14)


def test_zero_mean_linear_drift_and_dc(request_data):
    for samples, expected in [([-2, 2], 0), ([7, 7], 7), ([0, 2], 1)]:
        for record, value in zip(request_data["samples"], samples):
            record["value"] = value
        assert window_mean(request_data)["result_artifact"]["components"][0]["value"] == expected


def test_cli_roundtrip(request_data):
    completed = subprocess.run([sys.executable, "-m", "stfe"], input=canonical(request_data),
                               text=True, cwd=ROOT, capture_output=True, check=True)
    assert not completed.stderr
    assert json.loads(completed.stdout) == window_mean(request_data)


@pytest.mark.parametrize("raw", ['{"x":1,"x":2}', '{"value":NaN}', '{}', 'x' * 1048577,
                                '{"value":1e-999}', '{"value":1e999}'],
                         ids=["duplicate", "nonfinite", "empty", "oversize", "underflow", "overflow"])
def test_cli_refusals(raw):
    completed = subprocess.run([sys.executable, "-m", "stfe"], input=raw, text=True,
                               cwd=ROOT, capture_output=True)
    assert completed.returncode == 2
    assert not completed.stdout
    assert json.loads(completed.stderr)["status"] == "refused"


def test_set_exchange_projection(request_data):
    repo = os.environ.get("STFE_SET_REPO")
    if not repo:
        pytest.skip("set STFE_SET_REPO to run the adjacent SET exchange checker")
    path = Path(repo) / "state_estimation_testbed" / "contracts.py"
    spec = importlib.util.spec_from_file_location("_stfe_test_set", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        module.validate_result_artifact(window_mean(request_data)["result_artifact"])
        request_data["uncertainty"].update(status="unknown", crosscov_policy="unknown", matrix=None)
        check = module.validate_result_artifact(window_mean(request_data)["result_artifact"])
        assert check.effective_rank is None
    finally:
        del sys.modules[spec.name]


def test_ciw_exchange_inspection(request_data, tmp_path, monkeypatch):
    set_repo = os.environ.get("STFE_SET_REPO")
    ciw_repo = os.environ.get("STFE_CIW_REPO")
    if not set_repo or not ciw_repo:
        pytest.skip("set STFE_SET_REPO and STFE_CIW_REPO to inspect through CIW")
    monkeypatch.syspath_prepend(str(Path(ciw_repo) / "src"))
    from ciw.exchange import inspect_exchange
    artifact = window_mean(request_data)["result_artifact"]
    path = tmp_path / "result.json"
    path.write_text(canonical(artifact), encoding="utf-8")
    report = inspect_exchange([path], validator_repo=Path(set_repo))
    assert report["status"] == "conformant"
    assert report["artifacts"][0]["identity_status"] == "content_recomputed_not_authenticated"
    assert report["authority"]["may_authorize"] is False
    artifact["components"][0]["value"] += 1
    path.write_text(canonical(artifact), encoding="utf-8")
    with pytest.raises(ValueError, match="result_id does not match"):
        inspect_exchange([path], validator_repo=Path(set_repo))
