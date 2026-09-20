from __future__ import annotations

import copy

import pytest

from state_estimation_testbed.contracts import (
    ContractError,
    validate_covariance,
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
    assert verdict.effective_rank is None

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


@pytest.mark.parametrize("name", ["symmetry_tolerance", "psd_tolerance"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1e-12, 1.0, True, "1e-12", 10**1000])
@pytest.mark.parametrize("status", ["estimated", "unknown"])
def test_invalid_tolerances_cannot_bypass_checks(name, value, status):
    item = covariance(status=status)
    if status == "unknown":
        item["matrix"] = None
    with pytest.raises(ContractError, match=name):
        validate_covariance(item, **{name: value})


@pytest.mark.parametrize("scale", [1e-300, 1e-30, 1.0, 1e30, 1e300])
def test_covariance_rank_and_psd_are_uniform_scale_invariant(scale):
    for raw, rank in [([[1, 0], [0, 1]], 2), ([[1, 1], [1, 1]], 1)]:
        item = covariance([[scale * entry for entry in row] for row in raw])
        assert validate_covariance(item).effective_rank == rank
    with pytest.raises(ContractError, match="positive-semidefinite"):
        validate_covariance(covariance([[scale, 2 * scale], [2 * scale, scale]]))


@pytest.mark.parametrize("scale", [1e-150, 1e-15, 1.0, 1e15, 1e150])
def test_individual_unit_rescaling_preserves_full_and_singular_rank(scale):
    assert validate_covariance(covariance([[scale**2, 0], [0, 1]])).effective_rank == 2
    assert validate_covariance(covariance([[scale**2, scale], [scale, 1]])).effective_rank == 1
    with pytest.raises(ContractError, match="positive-semidefinite"):
        validate_covariance(covariance([[scale**2, 2 * scale], [2 * scale, 1]]))


def test_extreme_mixed_units_do_not_overflow_and_rank_is_not_lost():
    assert validate_covariance(covariance([[1e-300, 0.5], [0.5, 1e300]])).effective_rank == 2
    assert validate_covariance(covariance([[5e-324, 0], [0, 5e-324]])).effective_rank == 2
    with pytest.raises(ContractError, match="nonfinite normalized"):
        validate_covariance(covariance([[5e-324, 1e308], [1e308, 5e-324]]))


def test_rank_one_outer_product_no_longer_fails_on_a_small_first_pivot():
    assert validate_covariance(covariance([[1e-14, 1e-7], [1e-7, 1]])).effective_rank == 1


def test_known_zero_rank_is_distinct_from_missing_covariance():
    assert validate_covariance(covariance([[0, 0], [0, 0]])).effective_rank == 0
    for status in ("unknown", "not_applicable"):
        item = covariance(status=status)
        item["matrix"] = None
        assert validate_covariance(item).effective_rank is None


@pytest.mark.parametrize("matrix", [
    [[0, 1e-300], [1e-300, 1]],
    [[0, 1e-300], [0, 1]],
    [[0, 0], [1e-300, 1]],
])
def test_zero_variance_demands_exact_zero_row_and_column(matrix):
    with pytest.raises(ContractError, match="exactly zero"):
        validate_covariance(covariance(matrix))


def test_any_negative_variance_is_invalid_even_beside_large_variance():
    with pytest.raises(ContractError, match="negative variance"):
        validate_covariance(covariance([[-1e-300, 0], [0, 1e300]]))


def test_huge_integer_is_a_contract_error_not_an_overflow_exception():
    with pytest.raises(ContractError, match="must be finite"):
        validate_covariance(covariance([[10**1000, 0], [0, 1]]))


def test_mixed_units_cannot_hide_asymmetry():
    with pytest.raises(ContractError, match="not symmetric"):
        validate_covariance(covariance([[1e-300, 0.1], [0.9, 1e300]]))


def test_both_triangles_are_checked_without_averaging_or_mutation():
    item = covariance([[1, 1 + 1.5e-12], [1 + 0.6e-12, 1]])
    original = copy.deepcopy(item)
    with pytest.raises(ContractError, match="positive-semidefinite"):
        validate_covariance(item)
    assert item == original


def test_three_variable_pairwise_valid_but_indefinite_matrix_is_rejected():
    item = covariance([[1, -0.9, -0.9], [-0.9, 1, -0.9], [-0.9, -0.9, 1]])
    item.update(variables=["x", "y", "z"], units=["m", "m", "m"])
    item["frame"]["basis"] = ["east", "north", "up"]
    with pytest.raises(ContractError, match="positive-semidefinite"):
        validate_covariance(item)


@pytest.mark.parametrize("instant", [
    "2026-09-20Z", "20260920Z", "2026-09-20 12:00:00Z",
    "2026-09-20T12:00Z", "2026-09-20T12:00:00+00:00",
    "2026-02-30T12:00:00Z", "2026-09-20T12:00:60Z",
])
def test_timestamps_require_complete_real_utc_instants(instant):
    item = observation_batch()
    item["observed_at"] = instant
    with pytest.raises(ContractError, match="observed_at"):
        validate_observation_batch(item)


def test_fractional_timestamps_and_distinct_clock_order_are_preserved():
    item = observation_batch()
    item["observed_at"] = "2026-09-20T12:00:00.123456789Z"
    item["received_at"] = "2026-09-20T11:59:59Z"
    # The timestamps need not be ordered without an established clock mapping.
    assert validate_observation_batch(item).dimension == 2


def test_tangent_basis_required_and_ambient_point_dimension_may_differ():
    item = covariance()
    assert validate_covariance(item).dimension == 2  # Three-coordinate base point.
    item["frame"].pop("basis")
    with pytest.raises(ContractError, match="ordered basis"):
        validate_covariance(item)


def test_covariance_calibration_refs_must_survive_in_outer_artifact():
    item = result_artifact()
    item["calibration_refs"] = []
    with pytest.raises(ContractError, match="must be retained"):
        validate_result_artifact(item)


def test_repeated_units_do_not_allow_repeated_variables():
    item = covariance()
    item.update(variables=["x", "x"], units=["m", "m"])
    with pytest.raises(ContractError, match="duplicates"):
        validate_covariance(item)


@pytest.mark.parametrize("field", ["execution_ref", "input_refs"])
def test_result_cannot_reuse_execution_or_input_identity(field):
    item = result_artifact()
    item[field] = [item["result_id"]] if field == "input_refs" else item["result_id"]
    with pytest.raises(ContractError, match="must differ"):
        validate_result_artifact(item)


def test_observation_batch_cannot_be_its_own_source():
    item = observation_batch()
    item["source_artifact_refs"] = [item["batch_id"]]
    with pytest.raises(ContractError, match="must differ"):
        validate_observation_batch(item)


def test_verification_cannot_be_its_own_subject():
    item = {"schema": "notation.instrument.verification-artifact.v1",
            "verification_id": "verification:1", "subject_ref": "verification:1"}
    with pytest.raises(ContractError, match="must differ"):
        validate_verification_artifact(item)
