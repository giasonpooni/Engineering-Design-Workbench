from __future__ import annotations

import pytest

from execution.engine import ExecutionResult
from execution.instrumentation import result_artifact_v1, verification_artifact_v1
from execution.specification import ExecutionSpecification


SPEC = ExecutionSpecification(program=b"program", configuration=b"configuration", input_payload=b"input")


def execution(*, occurrence=0, status="completed"):
    return ExecutionResult(
        specification=SPEC,
        specification_identity=SPEC.identity(),
        program_identity=SPEC.program_identity(),
        input_identity=SPEC.input_identity(),
        engine_occurrence=occurrence,
        status=status,
        exit_code=0 if status == "completed" else 1,
        output=b"output" if status == "completed" else None,
        output_identity="a" * 64 if status == "completed" else None,
        computation_identity="b" * 64 if status == "completed" else None,
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
    assert artifact["execution_ref"] == "computation:" + "b" * 64
    assert artifact["execution_output_ref"] == "output:" + "a" * 64
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
