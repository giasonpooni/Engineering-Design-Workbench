"""The default pilot uses the existing engine; extras cannot inflate its claims."""
from pathlib import Path
from copy import deepcopy
import json
import sys

import pytest
from ciw import pilot
from ciw.learning import inspect_workspace
from ciw.telemetry import digest


def test_default_pilot_runs_and_retains_one_shared_investigation(tmp_path):
    root = tmp_path / "pilot"
    report = pilot.run(root)
    assert report["status"] == "passed" and report["scene"]["status"] == "not_requested"
    assert len(report["results"]) == 3
    assert all(c["status"] == "matched" for c in report["rms_checks"].values())
    assert report["window_comparison"]["late_minus_early_m"] < 0
    assert set(report["authority"].values()) == {"not_performed"}
    assert report["replay"]["execution_id"] != report["results"]["early"]["execution_id"]
    assert report["replay"]["comparison"]["data_match"]
    assert report["report_id"] == digest({k: v for k, v in report.items() if k != "report_id"})
    workspace = json.loads((root / "workspace.json").read_bytes())
    assert len(workspace["executions"]) == 3 and len(workspace["results"]) == 3
    assert not (root / "failure.json").exists()


def test_inspection_reopens_without_running_an_operation(tmp_path, monkeypatch):
    root = tmp_path / "pilot"
    report = pilot.run(root)
    before = (root / "workspace.json").read_bytes()
    monkeypatch.setattr("ciw.operations.registry.OperationRegistry.get", lambda *_: pytest.fail("Inspection dispatched"))
    view = inspect_workspace(root / "workspace.json", report["results"]["early"]["result_id"])
    assert view["result"]["data"]["sample_count"] == 384
    assert (root / "workspace.json").read_bytes() == before


def test_missing_requested_sdk_fails_before_creating_output(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "pxr", None)
    with pytest.raises(RuntimeError, match="OpenUSD is unavailable"):
        pilot.run(tmp_path / "pilot", with_usd=True)
    assert not (tmp_path / "pilot").exists()


def test_numerical_failure_cannot_publish_success(tmp_path, monkeypatch):
    monkeypatch.setattr(pilot, "verify_workspace", lambda *_: {"status": "mismatch"})
    root = tmp_path / "pilot"
    with pytest.raises(ValueError, match="comparison failed"):
        pilot.run(root)
    assert not (root / "pilot.json").exists()
    assert json.loads((root / "failure.json").read_bytes())["status"] == "failed"
    assert (root / "workspace.json").exists()


def test_reused_directory_is_not_overwritten(tmp_path):
    root = tmp_path / "pilot"
    pilot.run(root)
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*.json")}
    with pytest.raises(FileExistsError):
        pilot.run(root)
    assert {p.relative_to(root): p.read_bytes() for p in root.rglob("*.json")} == before


def test_cli_runs_headlessly_and_returns_nonzero_on_refusal(tmp_path):
    assert pilot.main(["--output-dir", str(tmp_path / "pilot")]) == 0
    assert pilot.main(["--output-dir", str(tmp_path / "pilot")]) == 2


@pytest.mark.parametrize("value", [0, 1, None, "true"])
def test_option_types_do_not_silently_change_scope(tmp_path, value):
    with pytest.raises(ValueError):
        pilot.run(tmp_path / "pilot", with_usd=value)
    assert not (tmp_path / "pilot").exists()
