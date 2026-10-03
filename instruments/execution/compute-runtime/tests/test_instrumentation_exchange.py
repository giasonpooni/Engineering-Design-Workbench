from __future__ import annotations

from dataclasses import replace

import pytest

from execution.commitments import COMPUTATION_TAG, OUTPUT_TAG, canonical_u32, commit_hex
from execution.engine import ExecutionResult
from execution.instrumentation import result_artifact_v1, verification_artifact_v1
from execution.specification import ExecutionSpecification


SPEC = ExecutionSpecification(program=b"program", configuration=b"configuration", input_payload=b"input")


def execution(*, occurrence=0, status="completed"):
    output = b"output" if status == "completed" else None
    output_id = commit_hex(OUTPUT_TAG, [output]) if output is not None else None
    computation_id = commit_hex(COMPUTATION_TAG, [
        bytes.fromhex(SPEC.program_identity()), bytes.fromhex(SPEC.input_identity()),
        bytes.fromhex(output_id), canonical_u32(0),
    ]) if output_id is not None else None
    return ExecutionResult(
        specification=SPEC,
        specification_identity=SPEC.identity(),
        program_identity=SPEC.program_identity(),
        input_identity=SPEC.input_identity(),
        engine_occurrence=occurrence,
        status=status,
        exit_code=0 if status == "completed" else 1,
        output=output,
        output_identity=output_id,
        computation_identity=computation_id,
        detail=None,
    )


def build(result=None, **overrides):
    arguments = {
        "components": [
            {"name": "east", "value": 1.2, "unit": "m"},
            {"name": "north", "value": -0.4, "unit": "m"},
        ],
        "covariance_status": "estimated",
        "covariance": [[0.04, 0.01], [0.01, 0.09]],
        "frame": {
            "id": "frame:enu:station-a",
            "semantics": "tangent",
            "basis": ["east", "north"],
            "evaluation_point": [-79.5, 43.7, 100.0],
        },
        "covariance_method": "estimator posterior",
        "covariance_source_refs": ["observation-batch:gnss-1"],
        "input_refs": ["observation-batch:gnss-1"],
        "model_refs": ["model:constant-velocity-v1"],
        "calibration_refs": ["calibration:antenna-1"],
        "applicability": "local ENU state at the declared epoch",
        "created_at": "2026-09-20T12:00:02Z",
    }
    arguments.update(overrides)
    return result_artifact_v1(result or execution(), **arguments)


def test_result_binds_checked_execution_without_claiming_measurement():
    artifact = build()
    assert artifact["execution_ref"] == "computation:" + execution().computation_identity
    assert artifact["execution_output_ref"] == "output:" + execution().output_identity
    assert artifact["execution_program_ref"] == "program:" + SPEC.program_identity()
    assert artifact["execution_input_ref"] == "input:" + SPEC.input_identity()
    assert artifact["execution_binding"] == {
        "identity_status": "recomputed", "components_status": "caller_declared",
        "input_refs_status": "caller_declared", "behavior_status": "unverified",
    }
    assert artifact["epistemic_class"] == "computed_result"
    assert artifact["covariance"]["variables"] == ["east", "north"]
    assert artifact["covariance"]["calibration_refs"] == ["calibration:antenna-1"]
    assert artifact["covariance"]["numerical_status"] == "unchecked"


def test_occurrence_identity_does_not_contaminate_result_identity():
    assert build(execution(occurrence=0))["result_id"] == build(execution(occurrence=7))["result_id"]


def test_halted_execution_cannot_fabricate_a_result():
    with pytest.raises(ValueError, match="completed execution"):
        build(execution(status="halted"))


def test_unknown_covariance_is_not_encoded_as_zero():
    artifact = build(
        covariance_status="unknown",
        covariance=None,
        covariance_method="not established",
        covariance_source_refs=[],
    )
    assert artifact["covariance"]["matrix"] is None
    with pytest.raises(ValueError, match="must be absent"):
        build(covariance_status="unknown", covariance=[[0.0, 0.0], [0.0, 0.0]])


def test_verification_is_a_separate_identity_and_summary_is_derived():
    result = build()
    verification = verification_artifact_v1(
        subject_ref=result["result_id"],
        verifier_ref="set:covariance-validator-v1",
        checks=[
            {"name": "shape", "outcome": "passed", "basis": "two by two"},
            {"name": "PSD", "outcome": "failed", "basis": "negative pivot"},
        ],
        created_at="2026-09-20T12:00:03Z",
        limitations=["does not establish calibration validity"],
    )
    assert verification["subject_ref"] == result["result_id"]
    assert verification["verification_id"] != result["result_id"]
    assert verification["outcome"] == "failed"
    assert verification["independent"] is False


def test_internal_verification_cannot_be_relabelled_independent_without_a_verifier():
    with pytest.raises(ValueError, match="external_verifier_ref"):
        verification_artifact_v1(
            subject_ref="result:1",
            verifier_ref="ste:internal-check",
            checks=[{"name": "identity", "outcome": "passed", "basis": "recomputed"}],
            created_at="2026-09-20T12:00:03Z",
            independent=True,
        )


@pytest.mark.parametrize("field", [
    "specification_identity", "program_identity", "input_identity",
    "output_identity", "computation_identity",
])
def test_every_native_identity_is_recomputed_not_trusted(field):
    with pytest.raises(ValueError, match=field):
        build(replace(execution(), **{field: "0" * 64}))


@pytest.mark.parametrize("changes", [
    {"output": b"tampered"},
    {"specification": replace(SPEC, input_payload=b"tampered")},
    {"specification": replace(SPEC, configuration=b"tampered")},
    {"specification": replace(SPEC, program=b"tampered")},
    {"exit_code": 1},
])
def test_changed_execution_bytes_cannot_keep_an_old_commitment(changes):
    with pytest.raises(ValueError, match="recomputed native commitment"):
        build(replace(execution(), **changes))


def test_nested_input_mutation_cannot_change_an_identified_result():
    frame = {"id": "frame:local", "semantics": "tangent", "basis": ["east", "north"],
             "evaluation_point": [1.0, 2.0]}
    covariance = [[1.0, 0.0], [0.0, 2.0]]
    artifact = build(frame=frame, covariance=covariance)
    frame["basis"][0] = "changed"
    frame["evaluation_point"][0] = 999.0
    covariance[0][0] = 999.0
    assert artifact["covariance"]["frame"]["basis"] == ["east", "north"]
    assert artifact["covariance"]["frame"]["evaluation_point"] == [1.0, 2.0]
    assert artifact["covariance"]["matrix"][0][0] == 1.0


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "1", {"x": 1}])
def test_components_are_finite_numeric_scalars(value):
    with pytest.raises(ValueError, match="numeric|finite"):
        build(components=[{"name": "x", "unit": "1", "value": value}])


@pytest.mark.parametrize("field", ["input_refs", "model_refs", "calibration_refs", "covariance_source_refs"])
def test_reference_strings_are_not_split_into_characters(field):
    with pytest.raises(ValueError, match="sequence"):
        build(**{field: "ref:a"})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "1"])
def test_covariance_requires_finite_json_numbers_but_not_psd_validation(value):
    with pytest.raises(ValueError, match="numeric|finite"):
        build(covariance=[[value, 0.0], [0.0, 1.0]])
    assert build(covariance=[[1, 2], [2, 1]])["covariance"]["numerical_status"] == "unchecked"


def test_scalar_dimensionless_result_does_not_require_spatial_frame():
    artifact = build(components=[{"name": "gain", "value": 1, "unit": "1"}],
                     covariance=[[0.1]], frame={"id": "frame:gain", "semantics": "feature"})
    assert artifact["covariance"]["variables"] == ["gain"]


@pytest.mark.parametrize("independent", ["false", 0, 1, None])
def test_independent_flag_requires_boolean(independent):
    with pytest.raises(ValueError, match="boolean"):
        verification_artifact_v1(
            subject_ref="result:1", verifier_ref="verifier:1",
            checks=[{"name": "shape", "outcome": "passed", "basis": "declared check"}],
            created_at="2026-09-20T12:00:03Z", independent=independent,
        )


def test_external_reference_does_not_authenticate_independence():
    artifact = verification_artifact_v1(
        subject_ref="result:1", verifier_ref="verifier:1",
        checks=[{"name": "shape", "outcome": "passed", "basis": "declared check"}],
        created_at="2026-09-20T12:00:03Z", independent=True,
        external_verifier_ref="organization:declared",
    )
    assert artifact["independence_status"] == "caller_declared"


def test_nonfinite_nested_frame_is_not_a_valid_wire_artifact():
    with pytest.raises(ValueError, match="finite JSON"):
        build(frame={"id": "frame:bad", "semantics": "feature", "metadata": {"x": float("nan")}})
