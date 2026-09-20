import copy

import pytest

from state_estimation_testbed import ContractError, evaluate_samples
from test_contracts import covariance, result_artifact


def sample():
    result = result_artifact()
    truth = copy.deepcopy(result["components"])
    truth[0]["value"] = 0.0
    truth[1]["value"] = 0.0
    result["covariance"]["matrix"] = [[4.0, 0.0], [0.0, 1.0]]
    return {"result": result, "truth_components": truth,
            "innovation": [2.0, 0.5],
            "innovation_covariance": covariance([[4.0, 0.0], [0.0, 1.0]])}


def evaluate(values):
    return evaluate_samples(values, model_ref="model:constant-velocity-v1")


def test_analytic_metrics_do_not_make_calibration_claim():
    actual = evaluate([sample()])
    assert actual["bias"] == [2.0, 0.5]
    assert actual["rmse"] == [2.0, 0.5]
    assert actual["nees"] == pytest.approx([1.25])
    assert actual["nis"] == pytest.approx([1.25])
    assert actual["claim_scope"] == "declared-reference-numerical-evaluation-only"
    assert "outcome" not in actual


def test_no_reference_or_innovation_yields_no_fabricated_metrics():
    actual = evaluate([{"result": result_artifact()}])
    assert actual["bias"] is None
    assert actual["rmse"] is None
    assert actual["nees"] == [] and actual["nis"] == []
    assert actual["reference_sample_count"] == 0


@pytest.mark.parametrize("matrix", [None, [[0.0, 0.0], [0.0, 0.0]], [[1.0, 1.0], [1.0, 1.0]]])
def test_unknown_and_singular_covariance_never_give_zero_nees(matrix):
    value = sample()
    value["result"]["covariance"].update(matrix=matrix)
    if matrix is None:
        value["result"]["covariance"]["status"] = "unknown"
    actual = evaluate([value])
    assert actual["nees"] == []
    assert actual["unavailable"][0]["metric"] == "NEES"


@pytest.mark.parametrize("bad", [True, "2.0", float("nan"), float("inf")])
@pytest.mark.parametrize("where", ["truth", "estimate", "innovation"])
def test_invalid_numeric_types_and_nonfinite_data_fail(where, bad):
    value = sample()
    if where == "truth":
        value["truth_components"][0]["value"] = bad
    elif where == "estimate":
        value["result"]["components"][0]["value"] = bad
    else:
        value["innovation"][0] = bad
    with pytest.raises(ContractError):
        evaluate([value])


def test_declared_model_must_be_retained_on_all_results():
    with pytest.raises(ContractError, match="model_ref"):
        evaluate_samples([sample()], model_ref="invented-model")


def test_reference_order_and_units_must_match():
    value = sample()
    value["truth_components"].reverse()
    with pytest.raises(ContractError, match="order and units"):
        evaluate([value])


def test_duplicate_results_are_not_additional_samples():
    with pytest.raises(ContractError, match="distinct result"):
        evaluate([sample(), sample()])


def test_multiple_samples_bias_and_rmse():
    first, second = sample(), sample()
    second["result"]["result_id"] = "result:second"
    second["result"]["components"][0]["value"] = -2.0
    actual = evaluate([first, second])
    assert actual["bias"] == [0.0, 0.5]
    assert actual["rmse"] == pytest.approx([2.0, 0.5])


def test_false_zero_normalized_error_refuses():
    value = sample()
    value["result"]["components"][0]["value"] = 1e-200
    value["result"]["components"][1]["value"] = 0.0
    with pytest.raises(ContractError, match="false zero"):
        evaluate([value])


def test_nonrepresentable_integer_cannot_be_rounded_into_perfect_estimate():
    value = sample()
    value["result"]["components"][0]["value"] = 2**53 + 1
    value["truth_components"][0]["value"] = 2**53
    with pytest.raises(ContractError, match="represented exactly"):
        evaluate([value])


def test_minimum_subnormal_bias_and_rmse_survive_aggregation():
    samples = []
    for index in range(4):
        value = sample()
        value["result"]["result_id"] = f"result:{index}"
        value["result"]["components"][0]["value"] = 5e-324
        value["result"]["components"][1]["value"] = 0.0
        value["result"]["covariance"].update(status="unknown", matrix=None)
        value.pop("innovation")
        value.pop("innovation_covariance")
        samples.append(value)
    report = evaluate(samples)
    assert report["bias"] == [5e-324, 0.0]
    assert report["rmse"] == [5e-324, 0.0]


def test_equal_units_do_not_justify_aggregation_across_different_frames():
    first, second = sample(), sample()
    second["result"]["result_id"] = "result:second"
    second["result"]["covariance"]["frame"]["id"] = "different-frame"
    with pytest.raises(ContractError, match="coordinate frame"):
        evaluate([first, second])


def test_explicit_reference_frame_must_match():
    value = sample()
    value["truth_frame"] = {"id": "wrong-frame"}
    with pytest.raises(ContractError, match="truth_frame"):
        evaluate([value])
