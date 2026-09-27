"""Merged native dependencies and failure history must retain the same bindings.

The native fixture is an explicit structural provider double. These tests do
not qualify Julia trajectories or C++ force calculations.
"""
import base64
from copy import deepcopy

import pytest

from ciw import native_interop as native, native_interop_contract as contract
from ciw import workbench as catalog
from ciw.adapters.protocol import AdapterRefusal
from ciw.instruments import make_demo_run
from ciw.session import Session
from ciw.telemetry import canonical, digest
from test_native_interop import mock_provider, add_and_execute


@pytest.fixture
def failed_force(tmp_path, monkeypatch, mock_provider):
    session = Session(make_demo_run(), tmp_path / "original")
    session.workbench.bind_workflow(native.KIND, {"runtime": tmp_path / "operator-binding.json"})
    model = {"mass_kg": 2, "omega_0_rad_s": 2, "gamma_s_inv": 0.1}
    trajectory = contract.make_source("control-oscillator.v1", "julia", {
        "model": model, "initial_state": {"q0_m": 1, "v0_m_s": -0.25}, "time_s": [0, 0.25, 0.5]})
    summary = add_and_execute(session, trajectory)
    original = session.workbench.get_bundle(summary["bundle_id"])
    step = original["steps"][0]
    output = step["result"]["data"]["output"]
    declaration = contract.make_source("oscillator-force-energy.v1", "cpp", {
        "model": model, **{key: output[key] for key in ("time_s", "q_m", "v_m_s")}},
        upstream={"bundle_digest": original["bundle_digest"], "result_id": step["result_id"]})
    source = session.workbench.add_source({"kind": native.KIND, "label": "Failed force fixture",
        "bytes_b64": base64.b64encode(canonical(declaration)).decode()})

    def refuse(*args, **kwargs):
        raise AdapterRefusal("TEST_NATIVE_REFUSAL", "Deliberate failure after dependency preflight")

    monkeypatch.setattr(native.NativeInteropWorkflow, "create_session", refuse)
    with pytest.raises(AdapterRefusal, match="after dependency preflight"):
        session.workbench.execute({"operation_id": native.OPERATION, "source_id": source["source_id"]})
    assert len(session.workbench.list_failed_executions()) == 1
    assert session.workbench.get_bundle(original["bundle_digest"]) == original
    return session, declaration, source


def forbid_execution(monkeypatch):
    def never(*args, **kwargs):
        pytest.fail("Offline dependency validation invoked a provider or numerical oracle")

    monkeypatch.setattr(native, "_invoke", never)
    monkeypatch.setattr(native, "_runtime", never)
    monkeypatch.setattr(native.NativeInteropWorkflow, "_adapters", never)
    monkeypatch.setattr(contract, "check_output", never)
    monkeypatch.setattr(contract, "oscillator_reference", never)
    monkeypatch.setattr(contract, "force_reference", never)


def test_native_failure_reopens_exact_history_without_provider_or_oracle(failed_force, tmp_path, monkeypatch):
    session, _, _ = failed_force
    retained = session.workbench.serialize()
    path = session.save_workspace(tmp_path / "workspace.json")
    forbid_execution(monkeypatch)
    restored = Session.from_workspace(path, tmp_path / "reopened")
    assert restored.workbench.serialize() == retained
    assert len(restored.workbench.list_bundles()) == 1
    assert restored.workbench.list_failed_executions() == session.workbench.list_failed_executions()


def test_failed_native_source_cannot_outlive_deleted_trajectory(failed_force, monkeypatch):
    session, _, _ = failed_force
    saved = session.workbench.serialize()
    saved["bundles"].clear()
    saved["revision"] -= 1
    forbid_execution(monkeypatch)
    with pytest.raises(ValueError, match="requires its retained trajectory"):
        catalog.Workbench.restore(saved)


@pytest.mark.parametrize("mutation", ["result", "position", "model"])
def test_resealed_failed_source_must_match_exact_trajectory(failed_force, monkeypatch, mutation):
    session, declaration, source = failed_force
    changed = deepcopy(declaration)
    if mutation == "result":
        changed["upstream"]["result_id"] = digest("another-result")
    elif mutation == "position":
        changed["payload"]["q_m"][1] += 0.5
    else:
        changed["payload"]["model"]["mass_kg"] = 3
    replacement = catalog._source({"kind": native.KIND, "label": source["label"],
        "bytes_b64": base64.b64encode(canonical(changed)).decode()})
    saved = session.workbench.serialize()
    saved["sources"] = [replacement if row["source_id"] == source["source_id"] else row
                        for row in saved["sources"]]
    failure, = saved["failed_executions"]
    failure["source_id"], failure["evidence_id"] = replacement["source_id"], replacement["evidence_id"]
    failure["request"]["source_id"] = replacement["source_id"]
    failure["request_sha256"] = digest(failure["request"])
    failure["record_sha256"] = digest({key: value for key, value in failure.items() if key != "record_sha256"})
    forbid_execution(monkeypatch)
    with pytest.raises(ValueError, match="not the named trajectory|differs from its retained trajectory"):
        catalog.Workbench.restore(saved)


def test_broken_native_dependency_is_rejected_before_another_attempt(failed_force, monkeypatch):
    session, declaration, _ = failed_force
    changed = deepcopy(declaration)
    changed["upstream"]["bundle_digest"] = digest("missing-trajectory")
    source = session.workbench.add_source({"kind": native.KIND, "label": "Unavailable trajectory",
        "bytes_b64": base64.b64encode(canonical(changed)).decode()})
    history = session.workbench.list_failed_executions()
    forbid_execution(monkeypatch)
    with pytest.raises(ValueError, match="requires its retained trajectory"):
        session.workbench.execute({"operation_id": native.OPERATION, "source_id": source["source_id"]})
    assert session.workbench.list_failed_executions() == history
    assert session.workbench.pending_operations == 0
