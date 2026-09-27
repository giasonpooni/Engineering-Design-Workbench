"""Genuine interval provider gates; no synthetic provider qualifies this workflow."""
import base64
from copy import deepcopy
import os
from pathlib import Path

import pytest

from ciw import interval_contract as ic, native_interop as ni, native_interop_contract as nc
from ciw.adapters.oscillator import make_demo_run
from ciw.session import Session
from ciw.telemetry import canonical, _bundle_digest
from ciw.workbench import Workbench
from test_interval_contract import payload


def forbidden(*args, **kwargs):
    raise AssertionError("Retained interval inspection attempted a provider or oracle")


def forbid_execution(monkeypatch):
    for module, name in ((ni, "_runtime"), (ni, "_invoke"), (nc, "check_output"),
                         (ic, "check_output"), (ic, "reference")):
        monkeypatch.setattr(module, name, forbidden)


@pytest.fixture(scope="module")
def live(tmp_path_factory):
    path = os.environ.get("CIW_INTERVAL_BINDING")
    if not path:
        pytest.skip("requires genuine qualified interval provider via CIW_INTERVAL_BINDING")
    binding = {"runtime": Path(path)}
    s = nc.make_source(ic.PROFILE, "intervals", payload(), experiment_id="interval-retention-gate")
    session = Session(make_demo_run(), tmp_path_factory.mktemp("interval-workflow"))
    session.workbench.bind_workflow(ni.KIND, binding)
    retained = session.workbench.add_source({"kind": ni.KIND, "label": "Genuine interval gate",
        "bytes_b64": base64.b64encode(canonical(s)).decode("ascii")})
    summary = session.workbench.execute({"operation_id": ni.OPERATION, "source_id": retained["source_id"]})
    return {"session": session, "binding": binding, "source": s, "source_record": retained,
            "summary": summary, "bundle": session.workbench.get_bundle(summary["bundle_id"])}


def test_live_exact_containment_and_occurrence_separation(live):
    bundle = live["bundle"]
    primary, reproduction = bundle["steps"][0], bundle["verification"]["reproduction"]
    assert primary["execution_id"] != reproduction["execution_id"]
    assert primary["result_id"] != reproduction["result_id"]
    assert primary["operation_id"] == reproduction["operation_id"] == ni.OPERATION
    assert primary["numerical_result_id"] == reproduction["numerical_result_id"]
    output = primary["result"]["data"]["output"]
    assert output["requirement"] == "holds_throughout"
    check = ic.check_output(live["source"], output)
    assert check == primary["result"]["data"]["reference_check"]
    assert check["policy"] == ic.CONFIGURATION
    assert check["authority"] == nc.AUTHORITY


def test_live_offline_save_reopen_preserves_all_retained_content(live, tmp_path, monkeypatch):
    session = live["session"]
    expected = session.workbench.serialize()
    path = tmp_path / "workspace.json"
    session.save_workspace(path)
    forbid_execution(monkeypatch)
    reopened = Session.from_workspace(path, tmp_path / "reopened")
    assert reopened.workbench.serialize() == expected
    assert reopened.workbench.get_bundle(live["summary"]["bundle_id"]) == live["bundle"]
    view = reopened.workbench.inspect_experiment({"bundle_id": live["summary"]["bundle_id"]})
    assert view["object_context"]["state_admission"] == "not_performed"


@pytest.mark.parametrize("mutation", ["decoration", "guarantee", "configuration", "occurrence", "authority", "method"])
def test_live_retained_metadata_corruption_is_refused(live, mutation, monkeypatch):
    bundle = deepcopy(live["bundle"])
    step = bundle["steps"][0]; data = step["result"]["data"]
    if mutation == "decoration": data["output"]["enclosure"]["decoration"] = "dac"
    elif mutation == "guarantee": data["output"]["enclosure"]["guaranteed"] = False
    elif mutation == "configuration": data["output"]["configuration"]["rounding"] = "fast"
    elif mutation == "occurrence": step["result"]["execution_ref"] = bundle["verification"]["reproduction"]["execution_id"]
    elif mutation == "authority": data["authority"]["physical_validation"] = "established"
    else: data["reference_check"]["method"] = "physical_validation"
    bundle["bundle_digest"] = _bundle_digest(bundle)
    forbid_execution(monkeypatch)
    with pytest.raises(ValueError): ni.NativeInteropWorkflow()._validate(bundle)


def test_live_replay_requires_binding_and_retains_new_occurrences(live, tmp_path, monkeypatch):
    workbench = Workbench.restore(live["session"].workbench.serialize())
    original = live["bundle"]
    bundle_id = live["summary"]["bundle_id"]
    with pytest.raises(ValueError): workbench.replay({"bundle_id": bundle_id})
    workbench.bind_workflow(ni.KIND, live["binding"])
    result = workbench.replay({"bundle_id": bundle_id})
    fresh = workbench.get_bundle(result["bundle"]["bundle_id"])
    old_occurrences = {step["execution_id"] for step in (original["steps"][0], original["verification"]["reproduction"])}
    new_occurrences = {step["execution_id"] for step in (fresh["steps"][0], fresh["verification"]["reproduction"])}
    assert len(old_occurrences | new_occurrences) == 4
    assert fresh["steps"][0]["result_id"] != original["steps"][0]["result_id"]
    assert fresh["steps"][0]["numerical_result_id"] == original["steps"][0]["numerical_result_id"]
    assert fresh["source"] == original["source"]
    assert fresh["runtimes"] == original["runtimes"]
    assert fresh["replay_receipts"][0]["source_bundle_digest"] == original["bundle_digest"]
    assert fresh["replay_receipts"][0]["admission"] == "not_performed"
    expected = workbench.serialize()
    session = Session(make_demo_run(), tmp_path / "fresh-session")
    session.workbench = workbench
    path = tmp_path / "replayed.json"; session.save_workspace(path)
    forbid_execution(monkeypatch)
    reopened = Session.from_workspace(path, tmp_path / "reopened")
    assert reopened.workbench.serialize() == expected


def test_live_replay_refuses_different_runtime(live):
    with pytest.raises(ValueError):
        ni.NativeInteropWorkflow()._adapters(live["binding"], {"scr": {}})
