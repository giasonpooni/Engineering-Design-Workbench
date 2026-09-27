"""Real SCR/Cantera failure history across the combined shared-session lifecycle.

The optional local test needs an exact operator binding. A selected qualification
gate must supply that binding and reject skips; no provider double qualifies it.
"""
import base64
from copy import deepcopy
import os
from pathlib import Path

import pytest

from ciw import native_interop as native, native_interop_contract as contract
from ciw import reaction_contract as reaction
from ciw.adapters.protocol import AdapterRefusal
from ciw.instruments import make_demo_run
from ciw.session import Session
from ciw.telemetry import canonical
from test_reaction_cantera_worker import payload


def _source(session, declaration):
    source = session.workbench.add_source({"kind": native.KIND,
        "label": declaration["experiment_id"], "bytes_b64": base64.b64encode(canonical(declaration)).decode()})
    return {"operation_id": native.OPERATION, "source_id": source["source_id"]}


def _forbid_execution(patch):
    def never(*args, **kwargs):
        pytest.fail("Offline recovery-history inspection invoked a provider or numerical oracle")

    patch.setattr(native, "_runtime", never)
    patch.setattr(native, "_invoke", never)
    patch.setattr(native.NativeInteropWorkflow, "_adapters", never)
    patch.setattr(contract, "check_output", never)
    patch.setattr(reaction, "reference", never)
    patch.setattr(reaction, "check_output", never)


def test_real_cantera_exhaustion_preserves_history_and_allows_explicit_recovery(tmp_path, monkeypatch):
    configured = os.environ.get("CIW_REACTION_CANTERA_BINDING")
    if not configured:
        pytest.skip("requires genuine qualified Cantera via CIW_REACTION_CANTERA_BINDING")
    binding = {"runtime": Path(configured).resolve(strict=True)}
    session = Session(make_demo_run(), tmp_path / "original")
    session.workbench.bind_workflow(native.KIND, binding)
    normal = contract.make_source(reaction.PROFILE, "cantera", payload(), experiment_id="cantera-recovery-baseline")
    normal_request = _source(session, normal)
    summary = session.workbench.execute(normal_request)
    original = session.workbench.get_bundle(summary["bundle_id"])
    step = original["steps"][0]
    assert step["result"]["data"]["reference_check"]["outcome"] == "passed"

    exhausted = deepcopy(normal)
    exhausted["experiment_id"] = "cantera-valid-step-budget-exhaustion"
    exhausted["payload"]["time_s"] = [0.0, 10.0]
    exhausted["payload"]["solver"]["max_steps"] = 1
    # These inputs satisfy the source contract. The real solver, not input
    # validation, must refuse when its permitted step budget is exhausted.
    assert native.NativeInteropWorkflow._source(canonical(exhausted)) == exhausted
    failed_request = _source(session, exhausted)
    with pytest.raises(AdapterRefusal) as caught:
        session.workbench.execute(failed_request)
    # This SCR revision terminates a refused worker and reports host failure.
    # Retain that observed boundary; do not invent an unreturned provider code.
    assert caught.value.code == "RUNTIME_FAILED"
    reason = "failed Cantera worker terminated and reaped; start a fresh host occurrence"
    assert reason in str(caught.value)

    failure, = session.workbench.list_failed_executions()
    assert failure["scope"] == "workflow_attempt"
    assert failure["phase"] == "dispatch" and failure["status"] == "refused"
    assert failure["runtime_status"] == "not_captured"
    assert failure["runtime"] is failure["result_id"] is failure["bundle_id"] is None
    assert failure["failure"]["code"] == "RUNTIME_FAILED"
    assert reason in failure["failure"]["message"]
    assert failure["request"] == failed_request
    assert failure["execution_id"] != step["execution_id"]
    assert session.workbench.get_bundle(original["bundle_digest"]) == original
    assert len(session.workbench.list_bundles()) == len(session.workbench.native_results()) == 1
    assert session.workbench.pending_operations == 0
    assert session.workbench._reserved_bytes == 0

    retained = session.workbench.serialize()
    workspace = session.save_workspace(tmp_path / "failed-history.json")
    with monkeypatch.context() as patch:
        _forbid_execution(patch)
        reopened = Session.from_workspace(workspace, tmp_path / "reopened")
        assert reopened.workbench.serialize() == retained
        assert reopened.workbench.get_bundle(original["bundle_digest"]) == original
        assert reopened.workbench.list_failed_executions() == [failure]
    assert not next(item for item in reopened.workbench.describe_operations()
                    if item["operation_id"] == native.OPERATION)["available"]

    # Reopening never activates a provider. An explicit host binding and new
    # request start the recovery computation; the old refusal stays immutable.
    reopened.workbench.bind_workflow(native.KIND, binding)
    recovered_summary = reopened.workbench.execute(normal_request)
    recovered = reopened.workbench.get_bundle(recovered_summary["bundle_id"])
    fresh = recovered["steps"][0]
    assert recovered["bundle_digest"] != original["bundle_digest"]
    assert fresh["execution_id"] != step["execution_id"]
    assert fresh["result_id"] != step["result_id"]
    assert fresh["input_refs"] == step["input_refs"]
    assert fresh["result"]["data"]["reference_check"]["outcome"] == "passed"
    assert reopened.workbench.get_bundle(original["bundle_digest"]) == original
    assert reopened.workbench.list_failed_executions() == [failure]
    assert len(reopened.workbench.list_bundles()) == len(reopened.workbench.native_results()) == 2
    executions = reopened.workbench.native_executions()
    assert len({record["execution_id"] for record in executions}) == len(executions) == 3
    for bundle in (original, recovered):
        authority = bundle["steps"][0]["result"]["data"]["authority"]
        assert authority["sp1_verification"] == "not_performed"
        assert authority["physical_validation"] == "not_established"
        assert authority["state_admission"] == authority["hardware_actuation"] == "not_performed"

    recovered_history = reopened.workbench.serialize()
    checkpoint = reopened.save_workspace(tmp_path / "recovered-history.json")
    with monkeypatch.context() as patch:
        _forbid_execution(patch)
        final = Session.from_workspace(checkpoint, tmp_path / "final")
        assert final.workbench.serialize() == recovered_history
