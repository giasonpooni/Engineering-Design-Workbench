from __future__ import annotations

import copy

import pytest

from state_estimation_testbed.contracts import (
    ContractError,
    validate_observation_batch,
    validate_result_artifact,
    validate_verification_artifact,
)


def covariance(matrix=None, *, status="estimated"):
    return {
        "status": status,
        "variables": ["position", "velocity"],
        "units": ["m", "m/s"],
        "matrix": [[4.0, 0.5], [0.5, 1.0]] if matrix is None else matrix,
        "frame": {
            "id": "frame:enu:station-a",
            "semantics": "tangent",
            "basis": ["east", "north"],
            "evaluation_point": [-79.5, 43.7, 100.0],
        },
        "method": "joint-state estimator posterior",
        "source_refs": ["observation:batch-1"],
        "calibration_refs": ["calibration:receiver-7"],
    }


def components():
    return [
        {"name": "position", "value": 2.0, "unit": "m"},
        {"name": "velocity", "value": 0.5, "unit": "m/s"},
    ]


def observation_batch():
    return {
        "schema": "notation.instrument.observation-batch.v1",
        "batch_id": "batch:1",
        "observed_at": "2026-09-20T12:00:00Z",
        "received_at": "2026-09-20T12:00:01Z",
        "clock_basis": "sensor:gps-disciplined",
        "components": components(),
        "covariance": covariance(status="reported"),
        "source_artifact_refs": ["artifact:raw-1"],
        "calibration_refs": ["calibration:receiver-7"],
    }


def result_artifact():
    return {
        "schema": "notation.instrument.result-artifact.v1",
        "result_id": "sha256:" + "1" * 64,
        "execution_ref": "execution:2",
        "input_refs": ["observation:batch-1"],
        "model_refs": ["model:constant-velocity-v1"],
        "calibration_refs": ["calibration:receiver-7"],
        "components": components(),
        "covariance": covariance(),
        "applicability": "local ENU state at the declared epoch",
        "created_at": "2026-09-20T12:00:02Z",
    }


def test_valid_singular_covariance_is_eligible_and_ranked():
    batch = observation_batch()
    batch["covariance"]["matrix"] = [[1.0, 1.0], [1.0, 1.0]]
    verdict = validate_observation_batch(batch)
    assert verdict.dimension == 2
    assert verdict.effective_rank == 1


@pytest.mark.parametrize(
    "matrix, message",
    [
        ([[1.0, 0.2], [0.2]], "rectangular and square"),
        ([[1.0, 0.9], [0.1, 1.0]], "not symmetric"),
        ([[1.0, 2.0], [2.0, 1.0]], "not positive-semidefinite"),
        ([[1.0, float("nan")], [float("nan"), 1.0]], "must be finite"),
    ],
)
def test_invalid_covariance_claims_fail_at_the_numerical_boundary(matrix, message):
    batch = observation_batch()
    batch["covariance"]["matrix"] = matrix
    with pytest.raises(ContractError, match=message):
        validate_observation_batch(batch)


def test_order_units_frame_and_evaluation_point_travel_with_the_matrix():
    for mutation, message in [
        (lambda item: item["covariance"].update(variables=["velocity", "position"]), "component order"),
        (lambda item: item["covariance"].update(units=["m/s", "m"]), "component units"),
        (lambda item: item["covariance"]["frame"].pop("evaluation_point"), "evaluation_point"),
    ]:
        item = observation_batch()
        mutation(item)
        with pytest.raises(ContractError, match=message):
            validate_observation_batch(item)


def test_distinct_variables_may_legitimately_share_one_unit():
    item = observation_batch()
    item["components"][1]["unit"] = "m"
    item["covariance"]["units"] = ["m", "m"]
    assert validate_observation_batch(item).dimension == 2


def test_unknown_covariance_is_explicit_and_never_fabricated_as_zero():
    item = result_artifact()
    item["covariance"].update(status="unknown", matrix=None, method="not established")
    verdict = validate_result_artifact(item)
    assert verdict.effective_rank == 0

    item["covariance"]["matrix"] = [[0.0, 0.0], [0.0, 0.0]]
    with pytest.raises(ContractError, match="must be absent"):
        validate_result_artifact(item)


def test_calibration_and_source_references_are_not_dropped():
    item = result_artifact()
    item["covariance"].pop("calibration_refs")
    with pytest.raises(ContractError, match="calibration_refs"):
        validate_result_artifact(item)


def test_verification_identity_and_independence_are_separate_claims():
    artifact = {
        "schema": "notation.instrument.verification-artifact.v1",
        "verification_id": "verification:1",
        "subject_ref": "sha256:" + "1" * 64,
        "verifier_ref": "set:covariance-validator-v1",
        "created_at": "2026-09-20T12:00:03Z",
        "checks": [
            {"name": "covariance eligibility", "outcome": "passed", "basis": "LDL transpose check"}
        ],
        "outcome": "passed",
        "independent": False,
        "limitations": ["does not establish calibration validity"],
    }
    validate_verification_artifact(artifact)

    inflated = copy.deepcopy(artifact)
    inflated["independent"] = True
    with pytest.raises(ContractError, match="external_verifier_ref"):
        validate_verification_artifact(inflated)


def test_summary_outcome_cannot_contradict_a_failed_check():
    artifact = {
        "schema": "notation.instrument.verification-artifact.v1",
        "verification_id": "verification:2",
        "subject_ref": "result:2",
        "verifier_ref": "set:covariance-validator-v1",
        "created_at": "2026-09-20T12:00:03Z",
        "checks": [{"name": "PSD", "outcome": "failed", "basis": "negative LDL transpose pivot"}],
        "outcome": "passed",
        "independent": False,
        "limitations": [],
    }
    with pytest.raises(ContractError, match="does not summarize"):
        validate_verification_artifact(artifact)
