"""Analytical fixtures and boundary tests for the declared identification adapter."""
import copy
import hashlib
import json

import numpy as np
import pytest

from sidt import DECLARED_OPERATION, identify_declared, replay_identification


def declaration():
    # Independently constructed exact model x[k+1] = 0.5*x[k] + 2*u[k].
    return {
        "schema": "sidt.declared-identification-input.v1",
        "model_id": "model:bench-1",
        "clock_frame": "clock:reference-seconds",
        "state_frame": "frame:reservoir-mass",
        "sample_interval": 0.5,
        "state_names": ["mass"], "state_units": ["kg"],
        "input_names": ["feed"], "input_units": ["kg/s"],
        "condition_limit": 1e6,
        "training": {
            "states": [[1.0], [2.5], [1.25], [4.625], [0.3125]],
            "inputs": [[1.0], [0.0], [2.0], [-1.0]],
            "sample_times": [0.0, 0.5, 1.0, 1.5, 2.0],
            "sample_refs": [f"sample:training:{i}" for i in range(5)],
            "evidence_refs": ["evidence:training"],
        },
        "holdout": {
            "states": [[-1.0], [3.5], [3.75]],
            "inputs": [[2.0], [1.0]],
            "sample_times": [3.0, 3.5, 4.0],
            "sample_refs": [f"sample:holdout:{i}" for i in range(3)],
            "evidence_refs": ["evidence:holdout"],
            "independence": "declared_disjoint",
        },
    }


def test_analytical_model_and_holdout_with_unknown_parameter_covariance():
    result = identify_declared(declaration(), execution_ref="execution:original")
    numerical = result["numerical_result"]
    assert numerical["status"] == "identified"
    np.testing.assert_allclose(numerical["candidate"]["A"], [[0.5]], atol=1e-14)
    np.testing.assert_allclose(numerical["candidate"]["B"], [[2.0]], atol=1e-14)
    np.testing.assert_allclose(numerical["holdout_evaluation"]["state_rmse"], [0], atol=1e-14)
    z = np.array([[1, 1], [2.5, 0], [1.25, 2], [4.625, -1]])
    assert numerical["diagnostics"]["rank"] == 2
    assert numerical["diagnostics"]["condition_number"] == pytest.approx(np.linalg.cond(z))
    assert numerical["parameter_covariance"]["status"] == "unknown"
    assert numerical["parameter_covariance"]["matrix"] is None
    assert result["verification_refs"] == []
    assert numerical["holdout_evaluation"]["evidence_status"] == "caller_declared_unattested"


def test_replay_preserves_numerical_identity_changes_execution_and_result():
    original = identify_declared(declaration(), execution_ref="execution:original")
    replay = replay_identification(original, execution_ref="execution:replay")
    assert original["inputs"] == replay["inputs"]
    assert original["input_digest"] == replay["input_digest"]
    assert original["numerical_id"] == replay["numerical_id"]
    assert original["numerical_result"] == replay["numerical_result"]
    assert original["result_id"] != replay["result_id"]
    with pytest.raises(ValueError, match="fresh execution"):
        replay_identification(original, execution_ref="execution:original")


def test_evidence_changes_source_result_identity_without_changing_mathematics():
    source = declaration()
    a = identify_declared(source, execution_ref="execution:a")
    source["training"]["evidence_refs"] = ["evidence:other-source"]
    b = identify_declared(source, execution_ref="execution:a")
    assert a["input_digest"] != b["input_digest"]
    assert a["result_id"] != b["result_id"]
    assert a["numerical_id"] == b["numerical_id"]


def test_refused_fit_retains_rank_and_no_candidate():
    source = declaration()
    source["training"]["states"] = [[1.0]] * 5
    source["training"]["inputs"] = [[1.0]] * 4
    result = identify_declared(source, execution_ref="execution:rank")
    numerical = result["numerical_result"]
    assert numerical["status"] == "nonidentifiable"
    assert numerical["diagnostics"]["rank"] == 1
    assert numerical["diagnostics"]["condition_number"] is None
    assert numerical["candidate"] is None
    assert numerical["holdout_evaluation"] is None


def test_full_rank_poor_conditioning_refuses_candidate():
    source = declaration()
    source["condition_limit"] = 1.1
    result = identify_declared(source, execution_ref="execution:condition")
    numerical = result["numerical_result"]
    assert numerical["status"] == "ill_conditioned"
    assert numerical["diagnostics"]["rank"] == 2
    assert numerical["diagnostics"]["condition_number"] > 1.1
    assert numerical["candidate"] is None


def test_svd_failure_is_unresolved_without_a_candidate(monkeypatch):
    def fail(*args, **kwargs):
        raise np.linalg.LinAlgError("backend detail deliberately not part of result")
    monkeypatch.setattr(np.linalg, "lstsq", fail)
    numerical = identify_declared(declaration(), execution_ref="execution:svd")["numerical_result"]
    assert numerical["status"] == "unresolved"
    assert numerical["reason"] == "svd_did_not_converge"
    assert numerical["candidate"] is None


@pytest.mark.parametrize("mutation,match", [
    (lambda d: d.update(state_frame=""), "state_frame"),
    (lambda d: d.update(clock_frame=""), "clock_frame"),
    (lambda d: d.update(sample_interval=True), "sample_interval"),
    (lambda d: d.update(condition_limit=0.9), "condition_limit"),
    (lambda d: d.update(state_names=["wrong", "width"]), "state_names"),
    (lambda d: d.update(undeclared=1), "extra"),
    (lambda d: d["training"].update(sample_times=[0, 0.5, 1, 1.7, 2]), "uniformly"),
    (lambda d: d["training"].update(sample_times=[0, 0.5, 1, 0.5, 2]), "uniformly"),
    (lambda d: d["training"].update(sample_times=[0, 0.5, 1, 1.5]), "align"),
    (lambda d: d["training"].update(sample_refs=["one"] * 5), "unique"),
    (lambda d: d["training"].update(evidence_refs=[]), "nonempty"),
    (lambda d: d["holdout"].update(independence="assumed"), "declared_disjoint"),
    (lambda d: d["holdout"]["sample_refs"].__setitem__(0, "sample:training:0"), "disjoint"),
    (lambda d: d["holdout"].update(evidence_refs=["evidence:training"]), "disjoint"),
    (lambda d: d["holdout"].update(sample_times=[2, 2.5, 3]), "time intervals"),
    (lambda d: d["holdout"].update(states=[[0, 0], [1, 1], [2, 2]]), "widths"),
    (lambda d: d["holdout"].update(inputs=[[True], [0.0]]), "booleans"),
])
def test_invalid_declarations_are_refused(mutation, match):
    source = declaration()
    mutation(source)
    with pytest.raises(ValueError, match=match):
        identify_declared(source, execution_ref="execution:invalid")


@pytest.mark.parametrize("identity", [DECLARED_OPERATION, "model:bench-1", "sample:training:0", "evidence:holdout"])
def test_execution_cannot_alias_source_model_or_operation(identity):
    with pytest.raises(ValueError, match="identities"):
        identify_declared(declaration(), execution_ref=identity)


def test_lost_epoch_precision_refused_and_raw_input_not_mutated():
    source = declaration()
    snapshot = copy.deepcopy(source)
    result = identify_declared(source, execution_ref="execution:immutable")
    assert source == snapshot
    source["training"]["states"][0][0] = 999
    assert result["inputs"] == snapshot
    huge = declaration()
    huge["training"]["sample_times"] = [float(2**54) + i * 0.5 for i in range(5)]
    with pytest.raises(ValueError, match="uniformly"):
        identify_declared(huge, execution_ref="execution:epoch")


def test_rehashing_forged_numerics_does_not_make_replay_valid():
    original = identify_declared(declaration(), execution_ref="execution:original")
    original["numerical_result"]["candidate"]["A"] = [[9.0]]
    def digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    original["numerical_id"] = "sidt:numerical:sha256:" + digest(original["numerical_result"])
    del original["result_id"]
    original["result_id"] = "sidt:result:sha256:" + digest(original)
    with pytest.raises(ValueError, match="does not reproduce"):
        replay_identification(original, execution_ref="execution:replay")


def test_replay_comparison_does_not_alias_boolean_with_numeric_diagnostics():
    source = declaration()
    source["training"]["states"] = [[1.0]] * 5
    source["training"]["inputs"] = [[1.0]] * 4
    original = identify_declared(source, execution_ref="execution:original")
    assert original["numerical_result"]["diagnostics"]["rank"] == 1
    original["numerical_result"]["diagnostics"]["rank"] = True
    with pytest.raises(ValueError, match="does not reproduce"):
        replay_identification(original, execution_ref="execution:replay")


def test_autonomous_input_and_absent_holdout_remain_supported():
    source = declaration()
    del source["holdout"]
    source["input_names"], source["input_units"] = [], []
    source["training"]["inputs"] = [[], [], [], []]
    source["training"]["states"] = [[1], [0.5], [0.25], [0.125], [0.0625]]
    numerical = identify_declared(source, execution_ref="execution:autonomous")["numerical_result"]
    assert numerical["status"] == "identified"
    np.testing.assert_allclose(numerical["candidate"]["A"], [[0.5]], atol=1e-14)
    assert numerical["candidate"]["B"] == [[]]
    assert numerical["holdout_evaluation"] is None


def test_unrepresentable_integer_sample_interval_never_changes_model_metadata():
    source = declaration()
    del source["holdout"]
    source["sample_interval"] = 9007199254740993
    source["input_names"], source["input_units"] = [], []
    source["training"].update(
        states=[[1], [2], [4]], inputs=[[], []],
        sample_times=[0, 9007199254740993, 18014398509481986],
        sample_refs=["sample:training:0", "sample:training:1", "sample:training:2"],
    )
    with pytest.raises(ValueError, match="sample_interval must be exactly representable"):
        identify_declared(source, execution_ref="execution:lossy-interval")


@pytest.mark.parametrize("field", ["condition_limit", "rcond"])
def test_numeric_policy_rejects_lossy_integer_conversion(field):
    source = declaration()
    source[field] = 2**53 + 1
    with pytest.raises(ValueError, match=f"{field} must be exactly representable"):
        identify_declared(source, execution_ref="execution:lossy-policy")


def test_integer_epoch_requires_exact_representation_but_large_exact_times_work():
    source = declaration()
    del source["holdout"]
    source["sample_interval"] = 4
    source["training"]["sample_times"] = [2**54 + 4 * i for i in range(5)]
    result = identify_declared(source, execution_ref="execution:exact-epoch")
    assert result["numerical_result"]["status"] == "identified"
    source["training"]["sample_times"] = [2**54 + 1 + 4 * i for i in range(5)]
    with pytest.raises(ValueError, match="sample_times must be exactly representable"):
        identify_declared(source, execution_ref="execution:lossy-epoch")


def test_integer_delta_cannot_round_even_when_endpoints_are_representable():
    source = declaration()
    del source["holdout"]
    source["sample_interval"] = 2**53
    source["training"].update(
        states=[[1], [2], [4]], inputs=[[1], [0]],
        sample_times=[-(2**53), 1, 2**53],
        sample_refs=["sample:training:0", "sample:training:1", "sample:training:2"],
    )
    with pytest.raises(ValueError, match="sample_times interval must be exactly representable"):
        identify_declared(source, execution_ref="execution:lossy-delta")


def test_fractional_times_keep_declared_interval_with_representation_tolerance():
    source = declaration()
    del source["holdout"]
    source["sample_interval"] = 0.1
    source["rcond"] = 1e-12
    source["training"]["sample_times"] = [0.0, 0.1, 0.2, 0.3, 0.4]
    result = identify_declared(source, execution_ref="execution:fractional")
    assert result["numerical_result"]["status"] == "identified"
    assert result["numerical_result"]["candidate"]["metadata"]["sample_interval"] == 0.1
    assert result["numerical_result"]["diagnostics"]["relative_rank_cutoff"] == 1e-12
