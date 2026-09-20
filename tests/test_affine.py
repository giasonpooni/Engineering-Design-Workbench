"""Analytic scientific checks plus adversarial contract/numerics boundaries."""

import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from cbsr import ContractError, OPERATION_ID, reconcile_affine_exact


def request():
    return json.loads((Path(__file__).parents[1] / "examples/affine_exact.json").read_text())


def test_balanced_mass_fixture_retains_raw_and_produces_analytic_projection():
    value = request()
    original = copy.deepcopy(value)
    result = reconcile_affine_exact(value)
    assert value == original
    assert result["status"] == "accepted"
    assert result["operation_id"] == OPERATION_ID
    assert result["candidate"] == {"estimate": [62., 41.], "covariance": [[4., 0.], [0., 4.]]}
    assert result["reconciled"] == {"estimate": [60.5, 39.5], "covariance": [[2., -2.], [-2., 2.]]}
    assert result["correction"] == [-1.5, -1.5]
    assert result["residual_pre"] == [3.]
    assert result["residual_post"] == [0.]
    assert result["residual_covariance_pre"] == [[8.]]
    assert result["residual_covariance_post"] == [[0.]]
    assert result["normalized_residual"] == 1.125
    assert result["condition_inf_independent_rows"] == 1
    assert result["rational_constraint_residual_zero"]
    assert result["output_constraint_residual_zero"]
    assert result["output_state_id"] != value["state_id"]
    assert result["claims"] == dict.fromkeys(("physical_validity", "fault_isolation", "evidence_admission", "stability"), False)


def test_input_and_receipt_do_not_share_mutable_containers():
    value = request()
    result = reconcile_affine_exact(value)
    value["estimate"][0] = 0
    assert result["candidate"]["estimate"][0] == 62


def test_declared_variance_controls_correction_not_arbitrary_equal_split():
    value = request()
    value["covariance"] = [[1, 0], [0, 100]]
    result = reconcile_affine_exact(value)
    assert result["status"] == "accepted"
    assert result["correction"][1] / result["correction"][0] == pytest.approx(100)


def test_joint_camera_gauge_common_reference_is_not_averaged_away():
    value = request()
    value.update(estimate=[1, 1], covariance=[[.20, .16], [.16, .17]], crosscov_policy="declared")
    value["constraints"].update(coefficients=[[1, -1]], rhs=[0])
    result = reconcile_affine_exact(value)
    assert result["status"] == "accepted"
    for row in result["reconciled"]["covariance"]:
        assert row == pytest.approx([.168, .168])


def test_duplicate_exact_rows_preserve_rank_and_projection():
    value = request()
    value["constraints"].update(coefficients=[[1, 1], [2, 2]], rhs=[100, 200], row_units=["kg", "kg"])
    result = reconcile_affine_exact(value)
    assert result["status"] == "accepted"
    assert result["residual_rank"] == 1
    assert result["reconciled"]["estimate"] == [60.5, 39.5]
    assert result["normalized_residual"] == 1.125


def test_infeasible_declaration_refused_without_projection():
    value = request()
    value["constraints"].update(coefficients=[[1, 1], [2, 2]], rhs=[100, 190], row_units=["kg", "kg"])
    result = reconcile_affine_exact(value)
    assert result["status"] == "refused" and result["feasible"] is False
    assert result["reason"] == "infeasible_constraint_declaration"
    assert result["reconciled"] is None


def test_hold_policy_preserves_raw_and_exposes_disagreement_without_isolation():
    value = request()
    value.update(estimate=[55, 35], covariance=[[.1, 0], [0, .1]])
    result = reconcile_affine_exact(value)
    assert result["status"] == "held"
    assert result["reconciled"] is None
    assert result["output_state_id"] is None
    assert result["candidate"]["estimate"] == [55, 35]
    assert result["normalized_residual"] > value["max_normalized_residual"]


def test_threshold_is_inclusive_and_replay_changes_preserve_numerical_identity():
    value = request()
    value["max_normalized_residual"] = 1.125
    first = reconcile_affine_exact(value)
    value["execution_id"] = "execution:second"
    second = reconcile_affine_exact(value)
    assert second["status"] == "accepted"
    assert first["numerical_result_id"] == second["numerical_result_id"]
    assert first["output_state_id"] == second["output_state_id"]
    assert first["result_id"] != second["result_id"]
    assert first["request_digest"] != second["request_digest"]


def test_source_result_and_evidence_bind_receipt_not_numerical_equivalence():
    value = request()
    first = reconcile_affine_exact(value)
    value.update(source_result_id="gsie:result", source_result_digest="a" * 64,
                 evidence_refs=["another-observation"])
    second = reconcile_affine_exact(value)
    assert first["result_id"] != second["result_id"]
    assert first["numerical_result_id"] == second["numerical_result_id"]
    assert second["request"]["source_result_digest"] == "a" * 64


def test_equivalent_integer_and_float_encodings_share_numerical_identity_only():
    value = request()
    first = reconcile_affine_exact(value)
    value["estimate"] = [62, 41]
    value["covariance"] = [[4, -0.0], [0, 4]]
    second = reconcile_affine_exact(value)
    assert first["numerical_result_id"] == second["numerical_result_id"]
    assert first["result_id"] != second["result_id"]


def test_constraint_declaration_label_is_bound_without_changing_numerical_identity():
    value = request()
    first = reconcile_affine_exact(value)
    value["constraints"]["constraint_id"] = "another-declaration-of-the-same-affine-law"
    second = reconcile_affine_exact(value)
    assert first["numerical_result_id"] == second["numerical_result_id"]
    assert first["result_id"] != second["result_id"]
    assert second["request"]["constraints"]["constraint_id"] == value["constraints"]["constraint_id"]


@pytest.mark.parametrize("field,value", [
    ("estimate", [True, 41]), ("estimate", ["62", 41]), ("estimate", [1 + 2j, 41]),
    ("estimate", [float("nan"), 41]), ("estimate", [float("inf"), 41]),
    ("estimate", [2**53 + 1, 41]), ("estimate", [2**2000, 41]),
    ("estimate", []), ("estimate", [0] * 17),
    ("covariance", [[4, False], [0, 4]]), ("covariance", [[4, 0]]),
    ("state_labels", ["mass", "mass"]), ("state_units", ["kg"]),
    ("frame_ref", ""), ("evidence_refs", []), ("execution_id", ""),
    ("max_normalized_residual", False), ("max_normalized_residual", 0),
    ("max_normalized_residual", float("inf")),
])
def test_malformed_contract_never_coerces_or_reconciles(field, value):
    original = request()
    original[field] = value
    with pytest.raises(ContractError):
        reconcile_affine_exact(original)


@pytest.mark.parametrize("field,value", [
    ("coefficients", [[True, 1]]), ("rhs", ["100"]),
    ("row_units", []), ("constraint_id", ""),
])
def test_constraint_contract_is_strict(field, value):
    original = request()
    original["constraints"][field] = value
    with pytest.raises(ContractError):
        reconcile_affine_exact(original)


def test_unknown_fields_cannot_smuggle_uncertain_coefficients():
    value = request()
    value["constraints"]["coefficient_covariance"] = [[1]]
    with pytest.raises(ContractError):
        reconcile_affine_exact(value)


@pytest.mark.parametrize("policy", ["declared_uncertain", "unknown", "nonlinear_local"])
def test_uncertain_or_nonlinear_rows_are_not_relabelled_as_exact(policy):
    value = request()
    value["constraints"]["coefficient_policy"] = policy
    result = reconcile_affine_exact(value)
    assert result["status"] == "refused"
    assert result["reason"] == "uncertain_or_undeclared_constraint_unsupported"


def test_unknown_crosscovariance_cannot_silently_become_block_diagonal():
    value = request()
    value["crosscov_policy"] = "unknown"
    assert reconcile_affine_exact(value)["reason"] == "unknown_or_unsupported_crosscovariance"
    value["crosscov_policy"] = "declared_zero"
    value["covariance"] = [[4, 1], [1, 4]]
    assert reconcile_affine_exact(value)["reason"] == "declared_zero_contradicts_covariance"


@pytest.mark.parametrize("covariance", [
    [[4, 1e-30], [0, 4]], [[4, 5], [5, 4]], [[1e300, 0], [0, -1e-300]],
    [[0, 1e-300], [1e-300, 1]], [[1, 1.0000000000000002], [1.0000000000000002, 1]],
])
def test_invalid_covariance_cannot_be_repaired_or_masked_by_scale(covariance):
    value = request()
    value.update(covariance=covariance, crosscov_policy="declared")
    assert reconcile_affine_exact(value)["status"] == "refused"


def test_exact_nullspace_is_accepted_only_when_it_already_satisfies_law():
    value = request()
    value.update(estimate=[60, 40], covariance=[[2, -2], [-2, 2]], crosscov_policy="declared")
    result = reconcile_affine_exact(value)
    assert result["status"] == "accepted"
    assert result["residual_rank"] == 0
    assert result["normalized_residual"] == 0
    assert result["reconciled"] == result["candidate"]
    value["estimate"][0] = 61
    result = reconcile_affine_exact(value)
    assert result["reason"] == "constraint_conflicts_with_exact_covariance_nullspace"


def test_fully_constrained_state_has_exact_zero_covariance():
    value = request()
    value["constraints"].update(coefficients=[[1, 0], [0, 1]], rhs=[60, 40], row_units=["kg", "kg"])
    result = reconcile_affine_exact(value)
    assert result["status"] == "accepted"
    assert result["reconciled"]["covariance"] == [[0, 0], [0, 0]]


def test_underflow_in_constraint_variance_is_not_reported_as_exact_certainty():
    value = request()
    value.update(estimate=[0, 0], covariance=[[1, 0], [0, 1]])
    value["constraints"].update(coefficients=[[1e-200, 0]], rhs=[0])
    result = reconcile_affine_exact(value)
    assert result["status"] == "refused"
    assert result["reason"] == "nonzero_numerical_output_underflow"
    assert result["residual_rank"] == 1


def test_cancellation_in_constraint_variance_does_not_become_zero():
    value = request()
    value.update(estimate=[0, 0], covariance=[[4, 19.4], [19.4, 94.08999999999999]], crosscov_policy="declared")
    value["constraints"].update(coefficients=[[9.7, -2]], rhs=[0])
    result = reconcile_affine_exact(value)
    assert result["residual_rank"] == 1
    assert result["residual_covariance_pre"][0][0] > 0


def test_posterior_variance_underflow_is_refused_not_clipped_to_zero():
    value = request()
    tiny = float.fromhex("0x0.0000000000001p-1022")
    value.update(estimate=[0, 0], covariance=[[tiny, 0], [0, tiny]])
    value["constraints"].update(rhs=[0])
    result = reconcile_affine_exact(value)
    assert result["status"] == "refused"
    assert result["reason"] == "nonzero_numerical_output_underflow"


def test_rounded_indefinite_posterior_is_refused_without_jitter_or_clipping():
    value = request()
    value.update(estimate=[0, 0, 0], covariance=[[4, 3, -1], [3, 28, -9], [-1, -9, 6]],
                 state_labels=["a", "b", "c"], state_units=["1"] * 3, crosscov_policy="declared")
    value["constraints"].update(coefficients=[[-1, 3, 1]], rhs=[0], row_units=["1"])
    result = reconcile_affine_exact(value)
    assert result["status"] == "refused"
    assert result["reason"] == "rounded_output_covariance_not_psd"
    assert result["reconciled"] is None


def test_ill_conditioned_declared_rows_are_reported_explicitly():
    value = request()
    value.update(estimate=[0, 0], covariance=[[1, 0], [0, 1e-13]])
    value["constraints"].update(coefficients=[[1, 0], [0, 1]], rhs=[0, 0], row_units=["kg", "kg"])
    result = reconcile_affine_exact(value)
    assert result["status"] == "refused"
    assert result["reason"] == "residual_system_ill_conditioned"
    assert result["condition_inf_independent_rows"] > 1e12


@pytest.mark.parametrize("extras", [
    {"source_result_id": "id"}, {"source_result_digest": "a" * 64},
    {"source_result_id": "id", "source_result_digest": "not-a-digest"},
])
def test_partial_source_binding_cannot_be_accepted(extras):
    value = request()
    value.update(extras)
    with pytest.raises(ContractError):
        reconcile_affine_exact(value)


@pytest.mark.parametrize("alias", [OPERATION_ID, "fixture:unreconciled-mass-pair",
                                    "fixture:declared-closed-mass-100kg-v1",
                                    "fixture:synthetic-observation-pair"])
def test_execution_id_cannot_alias_another_identity_kind(alias):
    value = request()
    value["execution_id"] = alias
    with pytest.raises(ContractError, match="identity"):
        reconcile_affine_exact(value)


def test_nonbinary_constraint_solution_reports_actual_encoded_output_residual():
    value = request()
    value.update(estimate=[0, 0])
    value["constraints"].update(coefficients=[[3, 0]], rhs=[1])
    result = reconcile_affine_exact(value)
    assert result["status"] == "accepted"
    assert result["rational_constraint_residual_zero"] is True
    assert result["output_constraint_residual_zero"] is False
    assert result["residual_post"][0] != 0
    # The receipt does not round the delivered residual away via 3 * (1/3).
    assert result["residual_post"][0] == -float.fromhex("0x1p-54")


def test_cli_and_direct_api_agree_and_malformed_contract_is_nonzero():
    value = request()
    result = subprocess.run([sys.executable, "-m", "cbsr"], input=json.dumps(value), text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == reconcile_affine_exact(value)
    value["estimate"] = [True, 41]
    result = subprocess.run([sys.executable, "-m", "cbsr"], input=json.dumps(value), text=True, capture_output=True)
    assert result.returncode == 2
    result = subprocess.run([sys.executable, "-m", "cbsr"], input='{"state_id":"a","state_id":"b"}', text=True, capture_output=True)
    assert result.returncode == 2 and "duplicate" in result.stderr


def test_cli_hold_cannot_look_like_success():
    value = request()
    value["max_normalized_residual"] = .1
    result = subprocess.run([sys.executable, "-m", "cbsr"], input=json.dumps(value), text=True, capture_output=True)
    assert result.returncode == 3
    assert json.loads(result.stdout)["status"] == "held"


@pytest.mark.parametrize("raw", ["[" * 2000 + "]" * 2000, "1" * 6000, " " * 1_048_577],
                         ids=["too_deep", "integer_too_long", "request_too_large"])
def test_cli_oversized_or_deep_malformed_json_is_a_structured_contract_error(raw):
    result = subprocess.run([sys.executable, "-m", "cbsr"], input=raw, text=True, capture_output=True)
    assert result.returncode == 2
    assert json.loads(result.stderr)["error"] == "invalid_contract"


@pytest.mark.parametrize("literal", ["1e-999", "-1e-999", "1e999", "NaN", "Infinity"])
def test_cli_decimal_literal_cannot_underflow_to_fake_exact_zero_or_overflow(literal):
    raw = json.dumps(request()).replace("62.0", literal)
    result = subprocess.run([sys.executable, "-m", "cbsr"], input=raw, text=True, capture_output=True)
    assert result.returncode == 2
    assert json.loads(result.stderr)["error"] == "invalid_contract"


def test_cli_genuine_zero_with_extreme_exponent_is_still_zero():
    value = request()
    value["max_normalized_residual"] = 1000
    raw = json.dumps(value).replace("62.0", "0e-999")
    result = subprocess.run([sys.executable, "-m", "cbsr"], input=raw, text=True, capture_output=True)
    assert result.returncode == 0
    assert json.loads(result.stdout)["candidate"]["estimate"][0] == 0
