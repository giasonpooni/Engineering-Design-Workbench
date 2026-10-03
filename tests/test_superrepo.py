"""Coordinator evidence must be fresh, well formed and tied to one revision."""
import importlib.util
import json
from pathlib import Path
from subprocess import SubprocessError, TimeoutExpired
import sys
from types import SimpleNamespace
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[1]
HEAD = "1" * 40
MEASUREMENT_SCHEMA = "notations.monorepo-gate-report.v1"


@pytest.fixture
def coordinator(monkeypatch):
    # Load the operator without changing the installed ciw package or Git state.
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("superrepo_test_monorepo", ROOT / "scripts/monorepo.py")
    monorepo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monorepo)
    monkeypatch.setitem(sys.modules, "monorepo", monorepo)
    spec = importlib.util.spec_from_file_location("superrepo_test_coordinator", ROOT / "scripts/superrepo.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    state = {"head": HEAD, "audits": 0}

    def audit(root):
        state["audits"] += 1
        return {"provider": "preserved-source-tree"}

    monkeypatch.setattr(module, "git", lambda *args: state["head"].encode())
    monkeypatch.setattr(module, "verify_imports", audit)
    return module, state


def _arguments(output):
    return SimpleNamespace(group=["measurement"], output_dir=output,
                           node_bin=None, cargo=None, full_reproduction=False)


def _fresh_report(**overrides):
    return {"schema": MEASUREMENT_SCHEMA, "terminal_revision": HEAD,
            "verification_id": "verification:" + uuid.uuid4().hex,
            "status": "passed", **overrides}


def _child(monkeypatch, coordinator, payload, *, returncode=0, after=None):
    module, _ = coordinator

    def run(command, **kwargs):
        output = Path(command[command.index("--output-dir") + 1])
        output.mkdir(parents=True)
        (output / "report.json").write_text(json.dumps(payload))
        if after is not None:
            after()
        return SimpleNamespace(returncode=returncode)

    # Substitute only this coordinator's process object, not global subprocess.
    monkeypatch.setattr(module, "subprocess", SimpleNamespace(run=run, SubprocessError=SubprocessError))


def _report(output):
    return json.loads((output / "report.json").read_text())


def test_old_same_revision_evidence_cannot_substitute_for_a_missing_child_report(coordinator, monkeypatch, tmp_path):
    module, _ = coordinator
    old = tmp_path / "measurement/report.json"
    old.parent.mkdir()
    old.write_text(json.dumps(_fresh_report()))
    previous = old.read_bytes()
    monkeypatch.setattr(module, "subprocess", SimpleNamespace(
        run=lambda *args, **kwargs: SimpleNamespace(returncode=0), SubprocessError=SubprocessError))
    assert module.check(_arguments(tmp_path)) == 1
    result = _report(tmp_path)
    assert result["status"] == "failed"
    assert result["groups"]["measurement"]["error"]["type"] == "MissingEvidence"
    assert Path(result["groups"]["measurement"]["report"]) != old
    assert old.read_bytes() == previous


@pytest.mark.parametrize("payload", [
    [],
    _fresh_report(verification_id="verification:" + "g" * 32),
    _fresh_report(schema="notations.unrelated-gate.v1"),
])
def test_malformed_or_unrelated_child_evidence_fails_with_a_final_report(coordinator, monkeypatch, tmp_path, payload):
    module, _ = coordinator
    _child(monkeypatch, coordinator, payload)
    assert module.check(_arguments(tmp_path)) == 1
    result = _report(tmp_path)
    assert result["status"] == "failed"
    assert result["error"]["type"] == "ValueError"


def test_revision_change_after_a_successful_child_invalidates_the_aggregate(coordinator, monkeypatch, tmp_path):
    module, state = coordinator
    _child(monkeypatch, coordinator, _fresh_report(), after=lambda: state.update(head="2" * 40))
    assert module.check(_arguments(tmp_path)) == 1
    result = _report(tmp_path)
    assert result["status"] == "failed"
    assert "revision changed" in result["error"]["message"]
    assert state["audits"] == 2


def test_fresh_valid_evidence_passes_and_preserves_its_identity(coordinator, monkeypatch, tmp_path):
    module, state = coordinator
    payload = _fresh_report()
    _child(monkeypatch, coordinator, payload)
    assert module.check(_arguments(tmp_path)) == 0
    result = _report(tmp_path)
    lane = result["groups"]["measurement"]
    assert result["status"] == lane["status"] == "passed"
    assert lane["verification_id"] == payload["verification_id"]
    assert state["audits"] == 2


def test_failed_child_retains_its_concrete_error(coordinator, monkeypatch, tmp_path):
    module, _ = coordinator
    error = {"type": "RuntimeError", "message": "original package check failed"}
    _child(monkeypatch, coordinator, _fresh_report(status="failed", error=error), returncode=1)
    assert module.check(_arguments(tmp_path)) == 1
    lane = _report(tmp_path)["groups"]["measurement"]
    assert lane["status"] == "failed"
    assert lane["error"] == error


def test_child_launch_removes_import_and_git_environment_overrides(coordinator, monkeypatch, tmp_path):
    module, _ = coordinator
    for name in ("PYTHONPATH", "PYTHONHOME", "PYTEST_PLUGINS", "GIT_DIR",
                 "GIT_INDEX_FILE", "GIT_ALTERNATE_OBJECT_DIRECTORIES"):
        monkeypatch.setenv(name, "untrusted-override")
    observed = {}

    def run(command, **kwargs):
        observed.update(kwargs["env"])
        output = Path(command[command.index("--output-dir") + 1])
        output.mkdir(parents=True)
        (output / "report.json").write_text(json.dumps(_fresh_report()))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module, "subprocess", SimpleNamespace(run=run, SubprocessError=SubprocessError))
    assert module.check(_arguments(tmp_path)) == 0
    assert not {"PYTHONPATH", "PYTHONHOME", "PYTEST_PLUGINS", "GIT_DIR",
                "GIT_INDEX_FILE", "GIT_ALTERNATE_OBJECT_DIRECTORIES"}.intersection(observed)
    assert observed["PYTHONNOUSERSITE"] == "1"


def test_audit_timeout_retains_a_failed_report(coordinator, monkeypatch, tmp_path):
    module, _ = coordinator

    def timeout(root):
        raise TimeoutExpired(["git", "ls-tree"], 30)

    monkeypatch.setattr(module, "verify_imports", timeout)
    assert module.check(_arguments(tmp_path)) == 1
    result = _report(tmp_path)
    assert result["status"] == "failed"
    assert result["error"]["type"] == "TimeoutExpired"
