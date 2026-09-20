from __future__ import annotations

import base64
import copy
import hashlib
import os
from pathlib import Path

import pytest

from state_estimation_testbed import (
    ContractError, bytes_digest, canonical_bytes, content_digest,
    replay_bundle_digest, verify_replay_bundle,
)
from test_contracts import observation_batch, result_artifact


def runtime():
    return {"schema": "ciw.subprocess-runtime.v1", "revision": "1" * 40,
            "source_tree": "2" * 40, "python_sha256": "3" * 64,
            "python_version": "3.11.8", "dependencies": {"numpy": "2.1.0"}}


def bind_result(value):
    payload = {key: item for key, item in value.items() if key != "result_id"}
    value["result_id"] = "sha256:" + hashlib.sha256(value["schema"].encode() + b"\x00" + canonical_bytes(payload)).hexdigest()
    return value


def step(role, operation, execution, inputs, result, numerical):
    request = {"inputs": inputs, "model": {"id": "declared-model", "matrix": [[1.0]]}}
    return {"operation_id": operation, "runtime_ref": role, "execution_id": execution,
            "input_refs": inputs, "request": request, "request_sha256": content_digest(request),
            "result": result, "result_sha256": content_digest(result),
            "result_id": result.get("result_id", result.get("batch_id")),
            "numerical_result": numerical, "numerical_result_id": content_digest(numerical)}


def bundle():
    batch = observation_batch()
    batch["covariance"]["source_refs"] = ["artifact:raw-1"]
    result = result_artifact()
    result["input_refs"] = [batch["batch_id"]]
    result["execution_ref"] = "execution:gsie:1"
    bind_result(result)
    raw = b'{"samples":[2.0,0.5]}'
    value = {
        "schema": "ciw.telemetry-session.v1", "session_id": "session:1",
        "created_at": "2026-09-20T12:00:04Z",
        "source": {"batch": batch, "batch_sha256": bytes_digest(canonical_bytes(batch)),
                   "batch_bytes_b64": base64.b64encode(canonical_bytes(batch)).decode(),
                   "evidence": [{"artifact_ref": "artifact:raw-1", "sha256": bytes_digest(raw),
                                 "bytes_b64": base64.b64encode(raw).decode()}]},
        "configuration": {"prior": [0.0], "model": [[1.0]], "window": {"start": 0, "end": 2}},
        "runtimes": {"ppda": runtime(), "gsie": runtime(), "set": runtime()},
        "steps": [step("ppda", "ppda.project.v1", "execution:ppda:1", ["artifact:raw-1"],
                       batch, {"components": batch["components"], "covariance": batch["covariance"]}),
                  step("gsie", "gsie.linear.v1", "execution:gsie:1", [batch["batch_id"]],
                       result, {"components": result["components"], "covariance": result["covariance"]})],
    }
    value["bundle_digest"] = replay_bundle_digest(value)
    return value


def seal(value):
    """Rehash outer only; internal bindings must still catch tampering."""
    value["bundle_digest"] = replay_bundle_digest(value)
    return value


def replay(value):
    return {item["execution_id"]: copy.deepcopy(item["numerical_result"]) for item in value["steps"]}


def test_binding_alone_cannot_claim_numerical_replay():
    receipt = verify_replay_bundle(bundle())
    assert receipt["outcome"] == "indeterminate"
    assert receipt["independent"] is False
    assert receipt["checks"][0]["outcome"] == "passed"


def test_fresh_replay_receipt_binds_every_identity_and_is_deterministic():
    value = bundle()
    receipt = verify_replay_bundle(value, replay_results=replay(value))
    assert receipt["outcome"] == "passed"
    assert receipt == verify_replay_bundle(value, replay_results=replay(value))
    assert receipt["binding"]["bundle_digest"] == value["bundle_digest"]
    assert receipt["binding"]["execution_ids"] == ["execution:gsie:1", "execution:ppda:1"]
    assert receipt["verification_id"] not in receipt["binding"]["execution_ids"]
    payload = {key: item for key, item in receipt.items() if key != "verification_id"}
    expected = "sha256:" + hashlib.sha256(receipt["schema"].encode() + b"\x00" + canonical_bytes(payload)).hexdigest()
    assert receipt["verification_id"] == expected


@pytest.mark.skipif(not os.environ.get("SET_CIW_REPO"), reason="optional existing CIW exchange inspector")
def test_verification_receipt_passes_existing_ciw_inspector(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(os.environ["SET_CIW_REPO"]) / "src"))
    from ciw.exchange import inspect_exchange
    value = bundle()
    receipt = verify_replay_bundle(value, replay_results=replay(value))
    path = tmp_path / "verification.json"
    path.write_bytes(canonical_bytes(receipt))
    report = inspect_exchange([path], validator_repo=Path(__file__).parents[1])
    assert report["artifacts"][0]["conformance"] == "passed"


def test_receipt_cannot_replace_reexecution_and_does_not_change_subject_digest():
    value = bundle()
    original = value["bundle_digest"]
    value["verification"] = {"outcome": "passed", "independent": True}
    assert replay_bundle_digest(value) == original
    assert verify_replay_bundle(value)["outcome"] == "indeterminate"


@pytest.mark.parametrize("mutation,message", [
    (lambda v: v["source"]["evidence"][0].update(bytes_b64="e30="), "evidence digest"),
    (lambda v: v["source"].update(evidence=[]), "source.evidence"),
    (lambda v: v["source"]["evidence"][0].update(artifact_ref="unbound"), "missing retained evidence"),
    (lambda v: v["source"].update(batch_sha256="sha256:" + "0" * 64), "retained batch bytes"),
    (lambda v: v["steps"][1]["request"].update(prior=[99]), "request_sha256"),
    (lambda v: v["steps"][1]["result"].update(applicability="tampered"), "result_sha256"),
    (lambda v: v["steps"][1]["numerical_result"].update(extra=1), "numerical_result_id"),
    (lambda v: v["steps"][1].update(input_refs=["missing"]), "input references"),
    (lambda v: v["steps"][1].update(execution_id="execution:ppda:1"), "distinct occurrences"),
    (lambda v: v["steps"][1].update(result_id="artifact:raw-1"), "result identities"),
    (lambda v: v["steps"][1].update(runtime_ref="not-pinned"), "runtime_ref"),
    (lambda v: v["runtimes"]["gsie"].update(revision="main"), "full Git"),
    (lambda v: v["runtimes"]["gsie"].update(python_sha256="bad"), "interpreter bytes"),
    (lambda v: v.update(configuration={}), "configuration"),
    (lambda v: v["steps"].reverse(), "input references"),
])
def test_tampering_and_incomplete_binding_refuse_even_with_resealed_outer_digest(mutation, message):
    value = bundle()
    mutation(value)
    seal(value)
    with pytest.raises(ContractError, match=message):
        verify_replay_bundle(value)


def test_new_outer_digest_required_when_prior_model_settings_change():
    value = bundle()
    value["configuration"]["prior"] = [999.0]
    with pytest.raises(ContractError, match="bundle_digest"):
        verify_replay_bundle(value)


def test_numerical_difference_fails_replay_even_when_all_hashes_are_valid():
    value = bundle()
    actual = replay(value)
    actual["execution:gsie:1"]["components"][0]["value"] += 1
    assert verify_replay_bundle(value, replay_results=actual)["outcome"] == "failed"


@pytest.mark.parametrize("key", ["execution:gsie:1", "execution:ppda:1"])
def test_missing_fresh_execution_cannot_pass(key):
    value = bundle()
    actual = replay(value)
    del actual[key]
    with pytest.raises(ContractError, match="missing a step"):
        verify_replay_bundle(value, replay_results=actual)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_json_cannot_be_hashed(bad):
    with pytest.raises(ContractError, match="nonfinite"):
        content_digest({"covariance": [[bad]]})


def test_boolean_in_numeric_exchange_cannot_hide_behind_valid_hashes():
    value = bundle()
    result = value["steps"][1]["result"]
    result["components"][0]["value"] = True
    value["steps"][1]["result_sha256"] = content_digest(result)
    value["steps"][1]["numerical_result_id"] = content_digest(value["steps"][1]["numerical_result"])
    with pytest.raises(ContractError, match="must be numeric"):
        verify_replay_bundle(seal(value))


def test_exact_retained_batch_bytes_may_use_noncanonical_whitespace():
    value = bundle()
    blob = b"\n" + canonical_bytes(value["source"]["batch"]) + b"\n"
    value["source"]["batch_bytes_b64"] = base64.b64encode(blob).decode()
    value["source"]["batch_sha256"] = bytes_digest(blob)
    assert verify_replay_bundle(seal(value))["checks"][0]["outcome"] == "passed"


def test_duplicate_json_keys_in_retained_batch_are_rejected():
    value = bundle()
    blob = canonical_bytes(value["source"]["batch"])
    blob = b'{"batch_id":"forged",' + blob[1:]
    value["source"]["batch_bytes_b64"] = base64.b64encode(blob).decode()
    value["source"]["batch_sha256"] = bytes_digest(blob)
    with pytest.raises(ContractError, match="strict JSON"):
        verify_replay_bundle(seal(value))


def test_operation_identity_cannot_contradict_retained_native_operation():
    value = bundle()
    value["steps"][1]["result"]["operation_ref"] = "different-operation"
    value["steps"][1]["result_sha256"] = content_digest(value["steps"][1]["result"])
    with pytest.raises(ContractError, match="operation identity"):
        verify_replay_bundle(seal(value), replay_results=replay(value))


def test_nesting_is_bounded_before_recursive_inspection():
    value = 0
    for _ in range(66):
        value = [value]
    with pytest.raises(ContractError, match="nesting"):
        content_digest(value)


def test_retained_batch_cannot_decode_nonzero_float_literal_as_zero():
    value = bundle()
    batch = value["source"]["batch"]
    batch["components"][0]["value"] = 0.0
    blob = canonical_bytes(batch).replace(b'"value":0.0', b'"value":1e-999', 1)
    value["source"]["batch_bytes_b64"] = base64.b64encode(blob).decode()
    value["source"]["batch_sha256"] = bytes_digest(blob)
    with pytest.raises(ContractError, match="strict JSON"):
        verify_replay_bundle(seal(value))


def composite_bundle():
    value = bundle()
    step = value["steps"][1]
    native = step["result"]
    native["operation_ref"] = "geometric-state-inference.update.v1"
    bind_result(native)
    step["result_id"] = native["result_id"]
    step["operation_id"] = "ciw.gsie-predict-update.v1"
    step["result"] = {"schema": "ciw.estimation-step.v1", "operation_id": step["operation_id"],
                      "component_operations": ["geometric-state-inference.predict.v1", "geometric-state-inference.update.v1"],
                      "result_artifact": native}
    step["result_sha256"] = content_digest(step["result"])
    return seal(value)


def test_declared_gsie_composite_retains_native_update_identity():
    value = composite_bundle()
    assert verify_replay_bundle(value, replay_results=replay(value))["outcome"] == "passed"
    assert value["steps"][1]["result"]["result_artifact"]["operation_ref"] == "geometric-state-inference.update.v1"


@pytest.mark.parametrize("mutation", [
    lambda s: s["result"]["component_operations"].reverse(),
    lambda s: s["result"].update(component_operations=["geometric-state-inference.update.v1"]),
    lambda s: s["result"]["result_artifact"].update(operation_ref="ciw.gsie-predict-update.v1"),
    lambda s: s.update(runtime_ref="ppda"),
])
def test_composite_alias_does_not_permit_missing_reordered_or_relabelled_operations(mutation):
    value = composite_bundle()
    mutation(value["steps"][1])
    value["steps"][1]["result_sha256"] = content_digest(value["steps"][1]["result"])
    with pytest.raises(ContractError, match="GSIE composite"):
        verify_replay_bundle(seal(value), replay_results=replay(value))


@pytest.mark.parametrize("wrapped", [False, True])
def test_resealed_outer_bundle_cannot_hide_stale_native_exchange_result_identity(wrapped):
    value = composite_bundle() if wrapped else bundle()
    step = value["steps"][1]
    native = step["result"].get("result_artifact", step["result"])
    native["applicability"] = "changed after result identity was assigned"
    step["result_sha256"] = content_digest(step["result"])
    with pytest.raises(ContractError, match="result artifact identity"):
        verify_replay_bundle(seal(value), replay_results=replay(value))
