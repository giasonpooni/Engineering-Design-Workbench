from copy import deepcopy

import numpy as np
import pytest

pytest.importorskip("state_estimation_testbed.contracts")
from state_estimation_testbed.contracts import validate_result_artifact

from examples.exchange import export_candidate
from examples.replay import trajectory
from sidt import fit_lti
from sidt.exchange import export_result


def fixture():
    states, inputs = trajectory(100, 20)
    outputs = states[:, :1][:-1] + 0.5 * inputs
    candidate = fit_lti(states, inputs, sample_interval=0.1,
                        state_names=("position", "velocity"), state_units=("m", "m/s"),
                        input_names=("force",), input_units=("N",),
                        outputs=outputs, output_names=("sensor",), output_units=("m",))
    return candidate, states, inputs, outputs


def test_actual_candidate_mapping_has_ordered_values_units_unknown_covariance():
    candidate, states, inputs, outputs = fixture()
    artifact = export_candidate(candidate, states, inputs, outputs)
    validation = validate_result_artifact(artifact)
    assert validation.effective_rank is None
    assert artifact["covariance"]["status"] == "unknown"
    assert artifact["covariance"]["matrix"] is None
    assert [item["name"] for item in artifact["components"]] == [
        "A[position,position]", "A[position,velocity]", "A[velocity,position]", "A[velocity,velocity]",
        "B[position,force]", "B[velocity,force]", "C[sensor,position]", "C[sensor,velocity]", "D[sensor,force]",
    ]
    assert artifact["components"][1]["unit"] == "(m)/(m/s)"
    values = [item["value"] for item in artifact["components"]]
    np.testing.assert_array_equal(values, np.concatenate([matrix.ravel() for matrix in
                                                         (candidate.A, candidate.B, candidate.C, candidate.D)]))
    result = artifact["computation"]["numerical_result"]
    assert result["candidate_digest"] == candidate.candidate_digest
    assert result["diagnostics"]["state_residuals"] == candidate.diagnostics.state_residuals.tolist()
    assert artifact["computation"]["inputs"]["outputs"] == outputs.tolist()
    assert artifact["verification_refs"] == []


def test_candidate_input_execution_and_result_identities_remain_distinct():
    candidate, states, inputs, outputs = fixture()
    first = export_candidate(candidate, states, inputs, outputs, execution_ref="execution:one")
    second = export_candidate(candidate, states, inputs, outputs, execution_ref="execution:two")
    assert first["computation"]["input_digest"] == second["computation"]["input_digest"]
    assert first["result_id"] != second["result_id"]
    assert first["computation"]["numerical_result"]["candidate_digest"] == second["computation"]["numerical_result"]["candidate_digest"]
    assert first["computation"]["source_revision_status"] == "caller_supplied_unattested"
    with pytest.raises(ValueError):
        export_candidate(candidate, states, inputs, outputs, execution_ref="evidence:sidt-synthetic-trajectory")


def test_export_is_detached_and_does_not_mutate_source_arrays():
    candidate, states, inputs, outputs = fixture()
    before = [value.copy() for value in (states, inputs, outputs)]
    artifact = export_candidate(candidate, states, inputs, outputs)
    original = deepcopy(artifact)
    for actual, expected in zip((states, inputs, outputs), before):
        np.testing.assert_array_equal(actual, expected)
    states[:] = -999
    inputs[:] = -999
    outputs[:] = -999
    assert artifact == original


def test_generic_export_rejects_nonfinite_payload():
    candidate, states, inputs, outputs = fixture()
    artifact = export_candidate(candidate, states, inputs, outputs)
    with pytest.raises(ValueError):
        export_result(
            operation_id="sidt.discrete-lti-lstsq.v1", execution_ref="execution:bad",
            source_revision="0" * 40, created_at="2026-01-01T00:00:00Z",
            input_refs=["evidence:fixture"], input_payload={"x": float("nan")},
            numerical_result={}, components=artifact["components"],
            covariance=artifact["covariance"], applicability="test",
        )
