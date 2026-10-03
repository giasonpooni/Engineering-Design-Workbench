"""Independent numerical references and strict covariance provenance contracts."""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from set_lcm.bridge.ciw import evaluate
from set_lcm.bridge.ciw_covariance import validate_artifact

ROOT = Path(__file__).resolve().parents[1]


def content_id(artifact):
    body = {key: value for key, value in artifact.items() if key != "covariance_id"}
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def resign(request):
    artifact = request["inputs"]["observation_covariance"]
    artifact["covariance_id"] = content_id(artifact)


@pytest.fixture
def request_data():
    return json.loads((ROOT / "examples/ciw_tank_request_v2.json").read_text())


def row(request):
    return request["inputs"]["observations"][0]


def test_v2_keeps_v1_exact_scientific_values_and_output_identity_separate(request_data):
    original = deepcopy(request_data)
    out = evaluate(request_data)
    assert out["status"] == "ok", out
    base_request = deepcopy(request_data)
    base_request["operation_id"] = "fsrt.tank-reconstruct.v1"
    del base_request["inputs"]["state_order"]
    del base_request["inputs"]["observation_covariance"]
    base_data = {key: value for key, value in out["data"].items()
                 if key not in ("covariance_artifacts", "state_order")}
    assert base_data == evaluate(base_request)["data"]
    assert request_data == original
    assert out == evaluate(request_data)
    assert out["data"]["diagnostics"]["physical_truth_verified"] is False
    assert not any("verification_id" in artifact for artifact in out["data"]["covariance_artifacts"].values())


def test_full_innovation_and_posterior_match_independent_rational_reference(request_data):
    # Exact rational conditioning for P0=25 I and R=[[1,1/4],[1/4,1]].
    # K=25*(25I+R)^-1, P=(P0^-1+R^-1)^-1. These fractions
    # come from the scalar 2x2 inverse, independently of FSRT's Joseph update.
    expected_P = np.array([[Fraction(2075, 2163), Fraction(500, 2163)],
                           [Fraction(500, 2163), Fraction(2075, 2163)]], dtype=float)
    expected_x = np.array([Fraction(112390, 2163), Fraction(99790, 2163)], dtype=float)
    data = evaluate(request_data)["data"]
    arts = data["covariance_artifacts"]
    np.testing.assert_array_equal(arts["innovation"]["matrix"], [[26, .25], [.25, 26]])
    np.testing.assert_allclose(arts["posterior"]["matrix"], expected_P, atol=1e-14, rtol=1e-14)
    np.testing.assert_allclose(arts["posterior"]["reference_values"], expected_x, atol=1e-13, rtol=0)
    np.testing.assert_array_equal(arts["posterior"]["matrix"], data["unprojected_estimate"]["covariance"])
    np.testing.assert_array_equal(arts["reconciled"]["matrix"], data["estimate"]["covariance"])
    diagonal_request = deepcopy(request_data)
    row(diagonal_request)["covariance"] = [[1, 0], [0, 1]]
    diagonal_request["inputs"]["observation_covariance"]["matrix"] = [[1, 0], [0, 1]]
    resign(diagonal_request)
    diagonal_data = evaluate(diagonal_request)["data"]
    assert diagonal_data["unprojected_estimate"] != data["unprojected_estimate"]
    assert diagonal_data["covariance_artifacts"]["posterior"]["covariance_id"] != arts["posterior"]["covariance_id"]


def test_covariance_sources_reference_known_artifacts_and_retain_dependencies(request_data):
    metadata = request_data["inputs"]["observation_covariance"]["provenance"]["metadata"]
    metadata["coverage"] = {"includes": ["shared calibration reference"], "excludes": ["unknown ageing drift"]}
    resign(request_data)
    arts = evaluate(request_data)["data"]["covariance_artifacts"]
    assert set(arts) == {"observation", "prior", "declared_total", "innovation", "posterior", "reconciled"}
    assert arts["observation"] == request_data["inputs"]["observation_covariance"]
    assert arts["prior"]["basis"]["kind"] == arts["declared_total"]["basis"]["kind"] == "parameter"
    for name, artifact in arts.items():
        assert artifact["covariance_id"] == content_id(artifact)
        assert validate_artifact(artifact) is artifact
        assert artifact["provenance"]["metadata"]["shared_dependencies"] == ["SYNTHETIC-shared-mass-reference"]
        if name != "observation":
            assert artifact["provenance"]["metadata"]["stage"] == name
            assert artifact["provenance"]["metadata"]["upstream_covariance_metadata"] == metadata
    assert arts["innovation"]["provenance"]["source_covariance_ids"] == [
        arts["observation"]["covariance_id"], arts["prior"]["covariance_id"]]
    assert arts["posterior"]["provenance"]["source_covariance_ids"] == arts["innovation"]["provenance"]["source_covariance_ids"]
    assert arts["reconciled"]["provenance"]["source_covariance_ids"] == [
        arts["posterior"]["covariance_id"], arts["declared_total"]["covariance_id"]]


def test_missing_channel_uses_observed_principal_matrix_without_false_independence(request_data):
    row(request_data)["values"][1] = None
    row(request_data)["mask"][1] = False
    data = evaluate(request_data)["data"]
    arts = data["covariance_artifacts"]
    assert arts["innovation"]["matrix"] == [[26.]]
    assert arts["innovation"]["quantity_ids"] == [row(request_data)["source_ids"][0]]
    assert arts["innovation"]["reference_values"] == [2.]
    assert arts["observation"]["matrix"] == [[1., .25], [.25, 1.]]
    assert arts["observation"]["reference_values"][1] == 46.  # declared reference, not a measurement
    assert data["calibrated_observation"]["values"][1] is None
    assert data["residuals"]["innovation"][1] is None
    assert arts["posterior"]["matrix"][1][1] == 25.
    assert arts["posterior"]["reference_values"][1] == 50.  # prior, never missing reference 46
    assert arts["posterior"]["provenance"]["metadata"]["observed_mask"] == [True, False]


def test_all_missing_preserves_existing_refusal_gate(request_data):
    row(request_data).update(values=[None, None], mask=[False, False])
    out = evaluate(request_data)
    assert out["status"] == "refused" and "data" not in out
    assert out["refusal"]["code"] == "insufficient_observations"


def test_exact_total_produces_valid_rank_deficient_posterior_artifact(request_data):
    request_data["inputs"]["model"]["total_mass_variance_kg2"] = 0.
    out = evaluate(request_data)
    assert out["status"] == "ok", out
    arts = out["data"]["covariance_artifacts"]
    matrix = np.array(arts["reconciled"]["matrix"])
    np.testing.assert_allclose(matrix @ np.ones(2), np.zeros(2), atol=1e-15)
    assert np.linalg.matrix_rank(matrix, tol=1e-12) == 1
    assert arts["declared_total"]["matrix"] == [[0.]]


def test_physical_disagreement_remains_held_with_separate_covariance_identity(request_data):
    row(request_data)["values"] = [60., 50.]
    request_data["inputs"]["observation_covariance"]["reference_values"] = [60., 50.]
    resign(request_data)
    data = evaluate(request_data)["data"]
    arts = data["covariance_artifacts"]
    assert data["diagnostics"]["physical_model_status"] == "physical_model_disagreement"
    assert arts["reconciled"]["matrix"] == arts["posterior"]["matrix"]
    assert arts["reconciled"]["reference_values"] == arts["posterior"]["reference_values"]
    assert arts["reconciled"]["covariance_id"] != arts["posterior"]["covariance_id"]
    assert arts["reconciled"]["provenance"]["metadata"]["reconciliation_status"] == "model_inconsistent"


@pytest.mark.parametrize("key,value", [
    ("quantity_ids", ["SYNTHETIC-tank-2", "SYNTHETIC-tank-1"]),
    ("quantity_ids", ["SYNTHETIC-tank-1", "SYNTHETIC-tank-1"]),
    ("units", ["kg", "g"]), ("frame", "another-frame"),
    ("reference_values", [51., 46.]), ("reference_values", [52., None]),
    ("matrix", [[1., True], [True, 1.]]), ("matrix", [[1.]]),
    ("basis", {"kind": "estimated_state", "id": "wrong-kind"}),
])
def test_malformed_or_mismatched_covariance_contract_refuses(request_data, key, value):
    request_data["inputs"]["observation_covariance"][key] = value
    resign(request_data)
    out = evaluate(request_data)
    assert out["status"] == "refused" and "data" not in out
    assert out["refusal"]["code"] == "invalid_covariance_contract"


@pytest.mark.parametrize("matrix", [[[1., 1.], [1., 1.]], [[1., 2.], [2., 1.]],
                                    [[0., .1], [.1, 1.]], [[1., .25], [.2, 1.]],
                                    [[1., .25], [.25 + 2e-12, 1.]]])
def test_singular_indefinite_and_asymmetric_measurement_covariance_refuse(request_data, matrix):
    row(request_data)["covariance"] = matrix
    request_data["inputs"]["observation_covariance"]["matrix"] = matrix
    resign(request_data)
    out = evaluate(request_data)
    assert out["status"] == "refused" and "data" not in out
    assert out["refusal"]["code"] == "numerical_refusal"


@pytest.mark.parametrize("key", ["prior_independent_of_observations", "declared_total_independent_of_observations",
                                 "prior_independent_of_declared_total"])
@pytest.mark.parametrize("value", [None, False, 1, "true"])
def test_unsupported_or_undeclared_dependence_is_not_silently_dropped(request_data, key, value):
    metadata = request_data["inputs"]["observation_covariance"]["provenance"]["metadata"]
    if value is None:
        del metadata[key]
    else:
        metadata[key] = value
    resign(request_data)
    out = evaluate(request_data)
    assert out["status"] == "refused" and "data" not in out
    assert out["refusal"]["code"] == "unsupported_covariance_dependence"


def test_state_and_evidence_order_and_hash_must_agree(request_data):
    bad_order = deepcopy(request_data)
    bad_order["inputs"]["state_order"].reverse()
    assert evaluate(bad_order)["status"] == "refused"
    bad_evidence = deepcopy(request_data)
    bad_evidence["inputs"]["observation_covariance"]["provenance"]["source_evidence_ids"].reverse()
    resign(bad_evidence)
    assert evaluate(bad_evidence)["status"] == "refused"
    request_data["inputs"]["observation_covariance"]["method"] = "changed-without-new-identity"
    assert evaluate(request_data)["status"] == "refused"


def test_subprocess_v2_roundtrip_has_only_strict_json(request_data):
    proc = subprocess.run([sys.executable, "-m", "set_lcm.bridge.ciw"], input=json.dumps(request_data),
                          text=True, capture_output=True, check=True, cwd=ROOT,
                          env={**os.environ, "PYTHONPATH": str(ROOT / "src")}, timeout=10)
    assert proc.stderr == ""
    assert json.loads(proc.stdout) == evaluate(request_data)
