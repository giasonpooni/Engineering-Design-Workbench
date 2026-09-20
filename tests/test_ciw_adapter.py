"""Calibration boundary gates, using analytic covariances and immutable bytes."""

from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from instrument_chain.ciw_adapter import handle_request
from instrument_chain.digest import canonical_digest
from instrument_chain.manifest import default_assembly_path


_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("ciw_example", _ROOT / "examples" / "ciw_calibration.py")
_EXAMPLE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_EXAMPLE)


@pytest.fixture
def calibration_request():
    return _EXAMPLE.request(default_assembly_path().read_text(), [100.0, 200.0], "test")


def result(calibration_request):
    response = handle_request(calibration_request)
    assert response["status"] == "ok", response
    return response["data"]


def refused(calibration_request, reason=None):
    response = handle_request(calibration_request)
    assert response["status"] == "refused"
    assert "data" not in response
    if reason is not None:
        assert response["refusal"]["reason_code"] == reason
    return response


def replace_source(calibration_request, index=0, **updates):
    item = calibration_request["inputs"]["records"][index]
    source = json.loads(base64.b64decode(item["raw_record_b64"]))
    source.update(updates)
    item["raw_record_b64"] = base64.b64encode(json.dumps(source).encode()).decode()


def test_raw_bytes_and_request_unchanged_derived_evidence_distinct(calibration_request):
    before = deepcopy(calibration_request)
    data = result(calibration_request)
    assert calibration_request == before
    for source, derived in zip(before["inputs"]["records"], data["records"]):
        assert derived["raw_record_b64"] == source["raw_record_b64"]
        raw = base64.b64decode(source["raw_record_b64"])
        assert raw.endswith(b"\n") and b"\n  " in raw  # formatting was not normalized
        assert derived["source_evidence_digest"] == hashlib.sha256(raw).hexdigest()
        assert derived["source_evidence_digest"] != derived["derived_evidence_digest"]
    assert [r["calibrated"]["value"] for r in data["records"]] == [1.0, 2.0]


def test_covariance_retains_parameter_cross_terms_and_cross_record_correlation(calibration_request):
    uncertainty = result(calibration_request)["uncertainty"]
    # y = s(r-z), dy/d(s,z) = (r-z,-s).
    expected_j = np.array([[100, -0.01], [200, -0.01]])
    theta_cov = np.array([[1e-10, 1e-7], [1e-7, 0.04]])
    expected_parameter = expected_j @ theta_cov @ expected_j.T
    expected_total = expected_parameter + np.eye(2) * (0.01**2 * 0.25 + 0.02**2)
    np.testing.assert_allclose(uncertainty["parameter_covariance"], theta_cov)
    np.testing.assert_allclose(uncertainty["parameter_jacobian"], expected_j)
    np.testing.assert_allclose(uncertainty["output_covariance"], expected_total)
    assert uncertainty["output_covariance"][0][1] == pytest.approx(5.7e-6)
    assert uncertainty["residual_sigma_reason"]
    assert uncertainty["traceability"] == "none_claimed"


def test_correlated_raw_covariance_is_retained(calibration_request):
    calibration_request["inputs"]["raw_covariance"] = [[0.25, 0.1], [0.1, 0.25]]
    data = result(calibration_request)
    assert data["uncertainty"]["raw_contribution_covariance"][0][1] == pytest.approx(1e-5)


def test_changed_covariance_changes_derived_evidence_but_not_raw_evidence(calibration_request):
    first = result(calibration_request)
    calibration_request["inputs"]["calibration"]["parameter_covariance"][0][0] *= 2
    second = result(calibration_request)
    assert first["records"][0]["source_evidence_digest"] == second["records"][0]["source_evidence_digest"]
    assert first["records"][0]["derived_evidence_digest"] != second["records"][0]["derived_evidence_digest"]


def test_missing_calibration_produces_no_result(calibration_request):
    calibration_request["inputs"]["calibration"] = None
    refused(calibration_request, "calibration_missing")


@pytest.mark.parametrize("observed_at,reason", [
    ("2025-12-31T23:59:59Z", "calibration_not_yet_valid"),
    ("2026-02-01T00:00:00Z", "calibration_expired"),
    ("2026-02-02T00:00:00Z", "calibration_expired"),
])
def test_observation_time_validity_atomic_refusal(calibration_request, observed_at, reason):
    calibration_request["inputs"]["records"][1]["observed_at"] = observed_at
    refused(calibration_request, reason)


def test_valid_from_inclusive_and_historical_replay_not_wall_clock(calibration_request):
    for item in calibration_request["inputs"]["records"]:
        item["observed_at"] = "2026-01-01T00:00:00Z"
    assert result(calibration_request) == result(deepcopy(calibration_request))


@pytest.mark.parametrize("key,value", [
    ("assembly_id", "other"), ("assembly_version", "2"),
    ("installation_id", "moved"), ("calibration_id", "another-profile"),
    ("assembly_digest", "0" * 64),
])
def test_binding_mismatch_produces_no_result(calibration_request, key, value):
    calibration_request["inputs"]["calibration"][key] = value
    refused(calibration_request, "calibration_mismatch")


def test_changed_assembly_cannot_reuse_binding(calibration_request):
    calibration_request["inputs"]["assembly_toml"] += "\n# changed declaration\n"
    refused(calibration_request, "calibration_mismatch")


def test_observation_mismatch_and_unavailable(calibration_request):
    replace_source(calibration_request, calibration_id="another")
    refused(calibration_request, "calibration_mismatch")
    replace_source(calibration_request, calibration_id="linear-v1", raw=None)
    refused(calibration_request, "raw_unavailable")


@pytest.mark.parametrize("raw", [True, float("nan"), float("inf"), -1.0, 2501.0])
def test_invalid_raw_or_range_cannot_produce_result(calibration_request, raw):
    replace_source(calibration_request, raw=raw)
    refused(calibration_request)


@pytest.mark.parametrize("matrix", [
    [[1, 2], [2, 1]], [[1, 1], [0, 1]], [[-1e-30, 0], [0, 1]],
    [[True, 0], [0, 1]], [[1, 0]], [[float("nan"), 0], [0, 1]],
    [[1e20, 1e10], [1e10, 0.5]], [[1, 1e-30], [1e-30, 0]],
    [[1e20, 0], [1e-10, 1e-30]],
])
def test_invalid_covariance_is_not_clipped_or_dropped(calibration_request, matrix):
    calibration_request["inputs"]["calibration"]["parameter_covariance"] = matrix
    refused(calibration_request)


def test_unknown_correlation_cannot_be_assumed_independent(calibration_request):
    calibration_request["inputs"]["calibration"]["raw_parameter_independent"] = False
    refused(calibration_request, "unsupported_uncertainty_model")


def test_native_digest_is_verified_with_unicode_and_delivery_excluded(calibration_request):
    item = calibration_request["inputs"]["records"][0]
    source = json.loads(base64.b64decode(item["raw_record_b64"]))
    source["sigma_reason"] = "étalon μ"
    source["digest"] = canonical_digest(source)
    source["delivery"] = {"attempt": 1}
    item["raw_record_b64"] = base64.b64encode(json.dumps(source).encode()).decode()
    result(calibration_request)
    source["raw"] = 101
    item["raw_record_b64"] = base64.b64encode(json.dumps(source).encode()).decode()
    refused(calibration_request, "source_digest_mismatch")


def test_affine_keeps_legacy_scale_times_raw_minus_zero_semantics(calibration_request):
    inputs = calibration_request["inputs"]
    inputs["assembly_toml"] = inputs["assembly_toml"].replace('method = "linear"', 'method = "affine"').replace(
        'theta = [0.01, 0.0]', 'theta = [0.01, 2.0]',
    )
    inputs["calibration"]["assembly_digest"] = hashlib.sha256(inputs["assembly_toml"].encode()).hexdigest()
    assert result(calibration_request)["records"][0]["calibrated"]["value"] == pytest.approx(0.98)


def test_offline_subprocess_deterministic_payload_and_clean_stdout(calibration_request):
    responses = []
    for _ in range(2):
        completed = subprocess.run(
            [sys.executable, "-m", "instrument_chain.ciw_adapter"],
            input=json.dumps(calibration_request), text=True, capture_output=True, check=True,
        )
        assert not completed.stderr
        assert len(completed.stdout.splitlines()) == 1
        responses.append(json.loads(completed.stdout))
    assert responses[0] == responses[1]
    assert responses[0]["status"] == "ok"
    assert not ({"execution_id", "result_id"} & responses[0]["data"].keys())


def test_invalid_json_subprocess_returns_refusal_not_traceback():
    completed = subprocess.run(
        [sys.executable, "-m", "instrument_chain.ciw_adapter"], input='{"schema":1,"schema":2}',
        text=True, capture_output=True, check=True,
    )
    assert json.loads(completed.stdout)["status"] == "refused"
    assert not completed.stderr


def test_two_reservoir_fixture_has_distinct_calibrations_and_mass_units():
    first, second = map(result, _EXAMPLE.reservoir_requests())
    assert first["calibration"]["calibration_id"] != second["calibration"]["calibration_id"]
    assert first["records"][0]["calibrated"] == {"value": 70.0, "unit": "kg"}
    assert second["records"][0]["calibrated"] == {"value": 30.0, "unit": "kg"}
