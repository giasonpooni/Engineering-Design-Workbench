"""v2 provenance gates and analytic shared-error covariance checks."""

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
for name in ("ciw_calibration", "ciw_calibration_v2"):
    spec = importlib.util.spec_from_file_location(name, _ROOT / "examples" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
_V1 = sys.modules["ciw_calibration"]
_V2 = sys.modules["ciw_calibration_v2"]


@pytest.fixture
def calibration_request():
    return _V2.synthetic_v2_request(_V1.request(
        default_assembly_path().read_text(), [100.0, 200.0], "v2-test",
    ))


def data(request):
    response = handle_request(request)
    assert response["status"] == "ok", response
    return response["data"]


def refuse(request, reason=None):
    response = handle_request(request)
    assert response["status"] == "refused", response
    assert "data" not in response
    if reason is not None:
        assert response["refusal"]["reason_code"] == reason
    return response


def basis(request):
    return request["inputs"]["calibration"]["covariance_basis"]


def test_v1_stdout_matches_pinned_97fcc01_byte_for_byte():
    request = _V1.request(default_assembly_path().read_text(), [100.0, 200.0], "regression-v1")
    completed = subprocess.run(
        [sys.executable, "-m", "instrument_chain.ciw_adapter"], input=json.dumps(request),
        text=True, capture_output=True, check=True,
    )
    # Captured by executing the endpoint source at pinned revision 97fcc01.
    assert hashlib.sha256(completed.stdout.encode()).hexdigest() == "f4810276121f1b63161bd66c67fa6592c5b675685ba048ec28285e10cdfc6991"
    assert not completed.stderr


def test_v2_preserves_numerics_raw_bytes_and_commits_basis(calibration_request):
    before = deepcopy(calibration_request)
    v1_request = deepcopy(calibration_request)
    v1_request["operation_id"] = "rci.calibrate.v1"
    v1_request["inputs"]["calibration"]["schema"] = "rci-calibration-binding.v1"
    del v1_request["inputs"]["calibration"]["covariance_basis"]
    v1, v2 = data(v1_request), data(calibration_request)
    assert before == calibration_request
    assert v2["schema"] == "measurement-record-batch.v2"
    for name in ("parameter_covariance", "parameter_jacobian", "output_covariance", "raw_covariance", "residual_covariance"):
        assert v1["uncertainty"][name] == v2["uncertainty"][name]
    assert v2["uncertainty"]["parameterization"] == {
        "name": "scale_zero_raw", "order": ["scale", "zero_raw"],
        "values": [0.01, 0.0], "units": ["mm/count", "count"],
    }
    for old, new in zip(v1["records"], v2["records"]):
        assert new["schema"] == "measurement-record.v2"
        assert new["source_evidence_digest"] == old["source_evidence_digest"]
        assert new["derived_evidence_digest"] != old["derived_evidence_digest"]
        assert new["raw_record_b64"] == old["raw_record_b64"]
        raw_bytes = base64.b64decode(new["raw_record_b64"])
        assert new["source_evidence_digest"] == hashlib.sha256(raw_bytes).hexdigest()
    assert v2["covariance_basis_digest"] == canonical_digest(basis(calibration_request))
    assert v2["uncertainty"]["traceability"] == "none_claimed"


def test_basis_only_change_changes_derived_evidence_without_changing_covariance(calibration_request):
    before = data(calibration_request)
    basis(calibration_request)["parameter_components"][0]["reason"] += "; additional declared context"
    after = data(calibration_request)
    assert before["uncertainty"]["output_covariance"] == after["uncertainty"]["output_covariance"]
    assert before["records"][0]["source_evidence_digest"] == after["records"][0]["source_evidence_digest"]
    assert before["records"][0]["derived_evidence_digest"] != after["records"][0]["derived_evidence_digest"]


def test_acquisition_applicability_is_immutable_historical_context(calibration_request):
    result = data(calibration_request)
    for record in result["records"]:
        assert record["acquisition_applicability"] == {
            "observed_at": "2026-01-15T12:00:00Z", "applicable": True,
            "valid_from": "2026-01-01T00:00:00Z", "valid_until": "2026-02-01T00:00:00Z",
            "basis": "caller_declared_acquisition_time",
        }
        assert "serving_status" not in record
    assert result == data(deepcopy(calibration_request))


def test_expired_at_acquisition_still_refuses(calibration_request):
    calibration_request["inputs"]["records"][1]["observed_at"] = "2026-02-01T00:00:00Z"
    refuse(calibration_request, "calibration_expired")


def test_missing_basis_refuses(calibration_request):
    del calibration_request["inputs"]["calibration"]["covariance_basis"]
    refuse(calibration_request, "covariance_basis_missing")


@pytest.mark.parametrize("kind", ["fitting", "reference_standard", "shared_systematic"])
def test_each_required_kind_explicitly_covered(calibration_request, kind):
    basis(calibration_request)["parameter_components"] = [
        c for c in basis(calibration_request)["parameter_components"] if c["kind"] != kind
    ]
    refuse(calibration_request, "covariance_basis_missing")


@pytest.mark.parametrize("field,value", [
    ("reason", ""), ("evidence_ids", []), ("dependency_ids", None),
    ("shared_source_ids", ["ambiguous", "ambiguous"]), ("status", "unknown"),
])
def test_missing_or_ambiguous_provenance_refuses(calibration_request, field, value):
    basis(calibration_request)["parameter_components"][0][field] = value
    refuse(calibration_request, "covariance_basis_ambiguous")


def test_component_sum_must_match_total(calibration_request):
    basis(calibration_request)["parameter_components"][0]["covariance"][1][1] *= 2
    refuse(calibration_request, "covariance_basis_mismatch")


@pytest.mark.parametrize("matrix", [
    [[1, 2], [2, 1]], [[1e20, 1e10], [1e10, 0.5]], [[0, 1], [1, 1]],
    [[float("nan"), 0], [0, 1]], [[True, 0], [0, 1]],
])
def test_invalid_component_covariance_refuses(calibration_request, matrix):
    basis(calibration_request)["parameter_components"][0]["covariance"] = matrix
    refuse(calibration_request)


def test_reference_already_inside_fit_is_represented_once(calibration_request):
    components = basis(calibration_request)["parameter_components"]
    fit, reference = components[:2]
    fit["covariance"] = deepcopy(calibration_request["inputs"]["calibration"]["parameter_covariance"])
    fit["dependency_ids"] += reference["dependency_ids"]
    fit["shared_source_ids"] += reference["shared_source_ids"]
    reference.update(status="excluded", covariance=None, represented_by="fit")
    result = data(calibration_request)
    coverage = result["uncertainty"]["covariance_coverage"]
    assert coverage["represented_component_ids"] == ["reference"]
    assert coverage["excluded_component_ids"] == ["other-systematics"]
    assert coverage["completeness_claimed"] is False


@pytest.mark.parametrize("mutation", ["included_twice", "raw_parameter", "residual_raw"])
def test_overlapping_sources_refuse_independent_addition(calibration_request, mutation):
    b = basis(calibration_request)
    if mutation == "included_twice":
        b["parameter_components"][1]["dependency_ids"] += b["parameter_components"][0]["dependency_ids"]
    elif mutation == "raw_parameter":
        b["raw"]["shared_source_ids"] = b["parameter_components"][1]["shared_source_ids"]
    else:
        b["residual"]["dependency_ids"] = b["raw"]["dependency_ids"]
    refuse(calibration_request, "unsupported_dependence")


def test_excluded_source_found_in_included_component_needs_explicit_representation(calibration_request):
    components = basis(calibration_request)["parameter_components"]
    components[2]["dependency_ids"] = components[0]["dependency_ids"]
    refuse(calibration_request, "covariance_basis_ambiguous")


@pytest.mark.parametrize("field", ["parameter_components", "raw_parameter", "residual_other"])
@pytest.mark.parametrize("value", [False, None, 1])
def test_distinct_ids_do_not_establish_independence(calibration_request, field, value):
    basis(calibration_request)["independence"][field] = value
    refuse(calibration_request, "unsupported_dependence")


def test_total_sigma_cannot_be_added_again_as_residual(calibration_request):
    basis(calibration_request)["residual"]["scope"] = "total_uncertainty_including_parameter_fit"
    refuse(calibration_request, "covariance_double_counting")


def test_common_reference_provenance_survives_distinct_assemblies():
    first, second = [data(_V2.synthetic_v2_request(r, common_reference=True)) for r in _V1.reservoir_requests()]
    assert first["calibration"]["assembly_id"] != second["calibration"]["assembly_id"]
    shared = set(first["uncertainty"]["shared_source_ids"]) & set(second["uncertainty"]["shared_source_ids"])
    assert shared == {"synthetic-reference:common-mass-standard"}


def synthetic_shared_parameter_request(n, parameter_covariance):
    request = _V2.synthetic_v2_request(_V1.request(
        default_assembly_path().read_text(), [100.0] * n, "averaging",
    ))
    binding = request["inputs"]["calibration"]
    binding["parameter_covariance"] = parameter_covariance
    components = basis(request)["parameter_components"]
    components[0]["covariance"] = parameter_covariance
    components[1].update(status="excluded", covariance=None)
    components[1]["reason"] = "No reference contribution in this explicitly limited analytic fixture"
    return request


@pytest.mark.parametrize("n", [1, 2, 8])
def test_averaging_does_not_remove_shared_zero_error(n):
    result = data(synthetic_shared_parameter_request(n, [[0.0, 0.0], [0.0, 4.0]]))
    covariance = np.array(result["uncertainty"]["output_covariance"])
    weights = np.full(n, 1 / n)
    # Common offset contribution s^2 Var(z) persists; independent noise / n.
    expected = 0.01**2 * 4 + (0.01**2 * 0.25 + 0.02**2) / n
    assert weights @ covariance @ weights == pytest.approx(expected)
    if n > 1:
        assert covariance[0, 1] == pytest.approx(0.01**2 * 4)


def test_gain_error_changes_with_operating_point_and_difference(calibration_request):
    request = synthetic_shared_parameter_request(2, [[1e-6, 0.0], [0.0, 0.0]])
    second = request["inputs"]["records"][1]
    source = json.loads(base64.b64decode(second["raw_record_b64"]))
    source["raw"] = 200.0
    second["raw_record_b64"] = base64.b64encode(json.dumps(source).encode()).decode()
    covariance = np.array(data(request)["uncertainty"]["parameter_contribution_covariance"])
    np.testing.assert_allclose(covariance, [[0.01, 0.02], [0.02, 0.04]])
    difference = np.array([-1.0, 1.0])
    assert difference @ covariance @ difference == pytest.approx((200 - 100)**2 * 1e-6)


def test_difference_cancels_shared_zero_but_not_independent_noise():
    result = data(synthetic_shared_parameter_request(2, [[0.0, 0.0], [0.0, 4.0]]))
    difference = np.array([-1.0, 1.0])
    parameter = np.array(result["uncertainty"]["parameter_contribution_covariance"])
    covariance = np.array(result["uncertainty"]["output_covariance"])
    assert difference @ parameter @ difference == pytest.approx(0.0)
    assert difference @ covariance @ difference == pytest.approx(2 * (0.01**2 * 0.25 + 0.02**2))


def test_v2_subprocess_refusal_and_success_have_clean_protocol(calibration_request):
    for expected in ("ok", "refused"):
        completed = subprocess.run(
            [sys.executable, "-m", "instrument_chain.ciw_adapter"], input=json.dumps(calibration_request),
            text=True, capture_output=True, check=True,
        )
        assert not completed.stderr
        assert json.loads(completed.stdout)["status"] == expected
        assert len(completed.stdout.splitlines()) == 1
        if expected == "ok":
            del calibration_request["inputs"]["calibration"]["covariance_basis"]
