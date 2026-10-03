"""Scientific and transport gates for covariance as a workbench operation."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from sensitivity.ciw_adapter import OPERATION_ID, handle_request, propagate_covariance
from sensitivity.covariance_artifact import content_id, make_covariance_artifact, validate_covariance_artifact


def artifact(covariance=None, *, quantity_ids=None, units=None, reference_values=None):
    covariance = [[1.0, 0.0], [0.0, 1.0]] if covariance is None else covariance
    size = len(covariance)
    return make_covariance_artifact(
        quantity_ids=quantity_ids or [f"input.{index}" for index in range(size)],
        units=units or ["m"] * size, frame="fixture-frame",
        reference_values=reference_values or [0.0] * size, matrix=covariance,
        method="declared_fixture_covariance", basis={"kind": "parameter", "id": "fixture-parameters"},
        provenance={"provider": "JSPT fixture", "source_evidence_ids": ["sha256:" + "a" * 64],
                    "source_covariance_ids": [], "metadata": {"fixture": True}},
        assumptions=["Synthetic fixture; no physical validation is asserted."],
    )


def inputs(source=None, jacobian=None, *, map_kind="linear", output_references=None):
    source = artifact() if source is None else source
    jacobian = [[1.0, 0.0], [0.0, 1.0]] if jacobian is None else jacobian
    return {
        "covariance": source, "jacobian": jacobian, "map_kind": map_kind,
        "output_quantity_ids": [f"output.{index}" for index in range(len(jacobian))],
        "output_units": ["m"] * len(jacobian), "output_frame": "derived-frame",
        "output_reference_values": output_references or [0.0] * len(jacobian),
    }


def request(declaration):
    return {"schema": "ciw.adapter-request.v1", "operation_id": OPERATION_ID, "inputs": declaration}


def reseal(record):
    record["covariance_id"] = content_id({key: value for key, value in record.items() if key != "covariance_id"})


def test_offdiagonal_shared_gain_offset_covariance_and_aggregation():
    source = artifact(quantity_ids=["gain", "zero"], units=["m/count", "count"], reference_values=[1.0, 0.0])
    calibrated = propagate_covariance(inputs(source, [[1.0, -1.0], [3.0, -1.0]], output_references=[1.0, 3.0]))
    covariance = calibrated["output_covariance"]
    np.testing.assert_allclose(covariance["matrix"], [[2.0, 4.0], [4.0, 10.0]])
    assert 4 / np.sqrt(20) < 1  # A shared parameter source need not imply perfect correlation.
    average = propagate_covariance(inputs(covariance, [[0.5, 0.5]], map_kind="weighted_aggregation"))
    contrast = propagate_covariance(inputs(covariance, [[-1.0, 1.0]], map_kind="weighted_aggregation"))
    assert average["output_covariance"]["matrix"] == [[5.0]]
    assert contrast["output_covariance"]["matrix"] == [[4.0]]
    assert average["output_covariance"]["provenance"]["source_covariance_ids"] == [covariance["covariance_id"]]


def test_shared_offset_cancels_in_contrast_and_survives_mean():
    source = artifact([[0.0, 0.0], [0.0, 2.0]])
    derived = propagate_covariance(inputs(source, [[1.0, -1.0], [3.0, -1.0]]))["output_covariance"]
    assert derived["matrix"] == [[2.0, 2.0], [2.0, 2.0]]
    contrast = propagate_covariance(inputs(derived, [[-1.0, 1.0]], map_kind="weighted_aggregation"))
    average = propagate_covariance(inputs(derived, [[0.5, 0.5]], map_kind="weighted_aggregation"))
    assert contrast["output_covariance"]["matrix"] == [[0.0]]
    assert average["output_covariance"]["matrix"] == [[2.0]]


def test_shared_offset_plus_independent_noise_averages_only_independent_part():
    fixture = json.loads((Path(__file__).parents[1] / "examples/covariance_request.json").read_text())
    reply = handle_request(fixture)
    assert reply["status"] == "ok"
    assert reply["data"]["output_covariance"]["matrix"][0][0] == pytest.approx(1.03)


def test_coordinate_push_keeps_full_covariance_units_and_order():
    source = artifact([[0.04, 0.015], [0.015, 0.09]], quantity_ids=["length", "time"], units=["m", "s"])
    declaration = inputs(source, [[1000.0, 0.0], [0.0, 0.001]], map_kind="coordinate_change")
    declaration.update(output_quantity_ids=["length_mm", "time_ks"], output_units=["mm", "ks"])
    before = deepcopy(declaration)
    result = propagate_covariance(declaration)
    np.testing.assert_allclose(result["output_covariance"]["matrix"], [[40000.0, 0.015], [0.015, 9e-8]])
    assert result["checks"]["coordinate_chart_guarded"] is True
    assert result["output_covariance"]["quantity_ids"] == ["length_mm", "time_ks"]
    assert result["output_covariance"]["units"] == ["mm", "ks"]
    assert result["input_covariance"] == source and declaration == before
    assert result["output_covariance"]["covariance_id"] != source["covariance_id"]
    assert propagate_covariance(declaration) == result


def test_reordering_input_covariance_and_jacobian_columns_preserves_output():
    source = artifact([[4.0, 1.0], [1.0, 9.0]], quantity_ids=["a", "b"])
    original = propagate_covariance(inputs(source, [[2.0, -1.0]]))
    reordered = artifact([[9.0, 1.0], [1.0, 4.0]], quantity_ids=["b", "a"])
    equivalent = propagate_covariance(inputs(reordered, [[-1.0, 2.0]]))
    assert original["output_covariance"]["matrix"] == equivalent["output_covariance"]["matrix"]
    assert original["input_covariance"]["quantity_ids"] != equivalent["input_covariance"]["quantity_ids"]


def test_rank_deficient_map_is_valid_but_not_an_invertible_coordinate_chart():
    jacobian = [[1.0, 1.0], [2.0, 2.0]]
    result = propagate_covariance(inputs(jacobian=jacobian))
    assert result["output_covariance"]["matrix"] == [[2.0, 4.0], [4.0, 8.0]]
    refused = handle_request(request(inputs(jacobian=jacobian, map_kind="coordinate_change")))
    assert refused["status"] == "refused" and refused["refusal"]["code"] == "numerical_refusal"
    assert "data" not in refused


def test_coordinate_condition_guard_is_retained():
    reply = handle_request(request(inputs(jacobian=[[1.0, 0.0], [0.0, 1e-13]], map_kind="coordinate_change")))
    assert reply["status"] == "refused" and reply["refusal"]["code"] == "numerical_refusal"


def test_local_linearization_preserves_reference_points_without_derivative_or_mc_claims():
    source = artifact(reference_values=[3.0, 4.0])
    result = propagate_covariance(inputs(source, [[6.0, 8.0]], map_kind="local_linearization", output_references=[25.0]))
    assert result["linearization_point"] == [3.0, 4.0]
    assert result["output_reference_values"] == [25.0]
    assert result["output_covariance"]["matrix"] == [[100.0]]
    assert result["jacobian_source"] == "caller_declared"
    for key in ("jacobian_verified", "reference_values_verified", "physical_units_verified", "monte_carlo_performed"):
        assert result["checks"][key] is False


@pytest.mark.parametrize("bad_covariance", [
    [[1.0, 2.0], [2.0, 1.0]], [[0.0, 0.1], [0.1, 1.0]], [[-0.01, 0.0], [0.0, 1.0]],
    [[1.0, 0.5], [0.1, 1.0]], [[True, 0.0], [0.0, 1.0]],
])
def test_resealed_invalid_covariances_are_refused(bad_covariance):
    declaration = inputs()
    declaration["covariance"]["matrix"] = bad_covariance
    reseal(declaration["covariance"])
    response = handle_request(request(declaration))
    assert response["status"] == "refused" and response["refusal"]["code"] == "invalid_input"
    assert "data" not in response


@pytest.mark.parametrize("bad_jacobian", [[[True, 1.0]], [["1", 1.0]], [[1j, 1.0]], [[float("inf"), 1.0]], [[1.0]]])
def test_jacobian_requires_finite_real_json_numbers_and_matching_dimension(bad_jacobian):
    response = handle_request(request(inputs(jacobian=bad_jacobian)))
    assert response["status"] == "refused" and "data" not in response


def test_output_overflow_is_numerical_refusal_without_result():
    reply = handle_request(request(inputs(jacobian=[[1e308, 1e308]])))
    assert reply["status"] == "refused" and reply["refusal"]["code"] == "numerical_refusal"
    assert "data" not in reply


def test_input_identity_and_metadata_are_checked_and_not_resealed():
    declaration = inputs()
    declaration["covariance"]["frame"] = "changed-frame"
    assert handle_request(request(declaration))["status"] == "refused"
    declaration = inputs()
    declaration["covariance"]["quantity_ids"] = ["duplicate", "duplicate"]
    reseal(declaration["covariance"])
    assert handle_request(request(declaration))["status"] == "refused"
    declaration = inputs()
    declaration["model_module"] = "os"
    assert handle_request(request(declaration))["status"] == "refused"


def test_partial_uncertainty_context_remains_in_standalone_derived_artifact():
    source = artifact()
    context = {
        "covariance_coverage": "declared_calibration_parameters_only",
        "completeness_claimed": False,
        "excluded_sources": ["unmodeled_sensor_drift"],
        "shared_source_ids": ["one_shared_reference"],
        "dependence": {"offset": "shared across observations"},
    }
    source["provenance"]["metadata"] = context
    reseal(source)
    result = propagate_covariance(inputs(source))
    assert result["output_covariance"]["provenance"]["metadata"]["source_uncertainty_context"] == context
    assert result["input_covariance"] == source


@pytest.mark.parametrize("covariance", [
    [[1.0, 0.5], [0.5 + 1e-11, 1.0]],
    [[1.0, 1.0 + 1.002e-10], [1.0 + 0.997e-10, 1.0]],
])
def test_wire_symmetry_and_both_stored_triangles_are_checked(covariance):
    declaration = inputs()
    declaration["covariance"]["matrix"] = covariance
    reseal(declaration["covariance"])
    reply = handle_request(request(declaration))
    assert reply["status"] == "refused" and reply["refusal"]["code"] == "invalid_input"


def test_existing_kernel_can_refuse_a_wire_admissible_marginal_covariance():
    source = artifact([[1.0, 1.0 + 5e-11], [1.0 + 5e-11, 1.0]])
    reply = handle_request(request(inputs(source)))
    assert reply["status"] == "refused" and reply["refusal"]["code"] == "numerical_refusal"


def test_duplicate_source_identities_are_refused():
    source = artifact()
    source["provenance"]["source_evidence_ids"] *= 2
    reseal(source)
    assert handle_request(request(inputs(source)))["status"] == "refused"


def test_unicode_identity_uses_ascii_canonical_json_and_validates_without_mutation():
    source = artifact(quantity_ids=["μ-position", "β-offset"])
    expected = content_id({key: value for key, value in source.items() if key != "covariance_id"})
    assert source["covariance_id"] == expected
    assert validate_covariance_artifact(source) == source


@pytest.mark.parametrize("payload", [
    '{"schema":"ciw.adapter-request.v1","schema":"duplicate","operation_id":"jspt.covariance-propagate.v1","inputs":{}}',
    '{"schema":"ciw.adapter-request.v1","operation_id":"jspt.covariance-propagate.v1","inputs":{"x":NaN}}',
])
def test_endpoint_rejects_duplicate_and_nonfinite_json(payload):
    child = subprocess.run([sys.executable, "-m", "sensitivity.ciw_adapter"], input=payload,
                           text=True, capture_output=True, check=True)
    result = json.loads(child.stdout)
    assert result["status"] == "refused" and result["refusal"]["code"] == "invalid_json"
    assert "data" not in result and child.stderr == ""


def test_json_endpoint_executes_supplied_fixture():
    fixture = (Path(__file__).parents[1] / "examples/covariance_request.json").read_text()
    child = subprocess.run([sys.executable, "-m", "sensitivity.ciw_adapter"], input=fixture,
                           text=True, capture_output=True, check=True)
    result = json.loads(child.stdout)
    assert result["status"] == "ok"
    assert result["data"]["output_covariance"]["matrix"][0][0] == pytest.approx(1.03)
    assert child.stderr == ""
