"""Coordinator evidence must be fresh, well formed and tied to one revision."""
import importlib.util
from hashlib import sha256
import json
from pathlib import Path
from subprocess import CalledProcessError
import sys
from types import SimpleNamespace
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[1]
HEAD = "1" * 40
SOURCE_TREE = "a" * 40
SOURCE = {"revision": HEAD, "source_tree": SOURCE_TREE}
MEASUREMENT_SCHEMA = "notations.monorepo-gate-report.v1"


@pytest.fixture
def coordinator(monkeypatch):
    # Load the operator without changing the installed ciw package or Git state.
    spec = importlib.util.spec_from_file_location("superrepo_test_monorepo", ROOT / "scripts/monorepo.py")
    monorepo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monorepo)
    monkeypatch.setitem(sys.modules, "monorepo", monorepo)
    spec = importlib.util.spec_from_file_location("superrepo_test_coordinator", ROOT / "scripts/superrepo.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    state = {"head": HEAD, "source_tree": SOURCE_TREE, "dirty": False,
             "audits": 0, "source_audits": 0}

    def audit(root):
        state["audits"] += 1
        return {"provider": "preserved-source-tree"}

    def source_audit(root):
        state["source_audits"] += 1
        if state["dirty"]:
            raise ValueError("Terminal tracked working bytes differ from the reported source revision")
        return {"revision": state["head"], "source_tree": state["source_tree"]}

    monkeypatch.setattr(module, "git", lambda *args: state["head"].encode())
    monkeypatch.setattr(module, "verify_imports", audit)
    monkeypatch.setattr(module, "verify_terminal_source", source_audit)
    return module, state


def _arguments(output):
    return SimpleNamespace(group=["measurement"], output_dir=output,
                           node_bin=None, cargo=None, full_reproduction=False)


def _fresh_report(**overrides):
    return {"schema": MEASUREMENT_SCHEMA, "terminal_revision": HEAD,
            "terminal_source": dict(SOURCE),
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
    monkeypatch.setattr(module, "subprocess", SimpleNamespace(run=run, CalledProcessError=CalledProcessError))


def _report(output):
    return json.loads((output / "report.json").read_text())


def test_old_same_revision_evidence_cannot_substitute_for_a_missing_child_report(coordinator, monkeypatch, tmp_path):
    module, _ = coordinator
    old = tmp_path / "measurement/report.json"
    old.parent.mkdir()
    old.write_text(json.dumps(_fresh_report()))
    previous = old.read_bytes()
    monkeypatch.setattr(module, "subprocess", SimpleNamespace(
        run=lambda *args, **kwargs: SimpleNamespace(returncode=0), CalledProcessError=CalledProcessError))
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
    assert lane["terminal_source"] == result["terminal_source"] == SOURCE
    assert lane["report_sha256"] == sha256(Path(lane["report"]).read_bytes()).hexdigest()
    assert state["audits"] == 2
    assert state["source_audits"] == 2


def test_failed_child_retains_its_concrete_error(coordinator, monkeypatch, tmp_path):
    module, _ = coordinator
    error = {"type": "RuntimeError", "message": "original package check failed"}
    _child(monkeypatch, coordinator, _fresh_report(status="failed", error=error), returncode=1)
    assert module.check(_arguments(tmp_path)) == 1
    lane = _report(tmp_path)["groups"]["measurement"]
    assert lane["status"] == "failed"
    assert lane["error"] == error


def test_dirty_terminal_source_is_rejected_before_any_child_executes(coordinator, monkeypatch, tmp_path):
    module, state = coordinator
    state["dirty"] = True
    monkeypatch.setattr(module, "subprocess", SimpleNamespace(
        run=lambda *args, **kwargs: pytest.fail("Dirty source must not execute a child"),
        CalledProcessError=CalledProcessError))
    assert module.check(_arguments(tmp_path)) == 1
    result = _report(tmp_path)
    assert result["groups"] == {}
    assert "working bytes differ" in result["error"]["message"]
    assert state["audits"] == 0


def test_working_source_change_during_child_execution_invalidates_aggregate(coordinator, monkeypatch, tmp_path):
    module, state = coordinator
    _child(monkeypatch, coordinator, _fresh_report(), after=lambda: state.update(dirty=True))
    assert module.check(_arguments(tmp_path)) == 1
    result = _report(tmp_path)
    assert result["status"] == "failed"
    assert "working bytes differ" in result["error"]["message"]
    assert result["terminal_revision"] == HEAD
    assert state["source_audits"] == 2


@pytest.mark.parametrize("child_source", [None, {"revision": HEAD, "source_tree": "b" * 40}])
def test_child_source_binding_is_required_and_matches_aggregate(coordinator, monkeypatch, tmp_path, child_source):
    module, _ = coordinator
    payload = _fresh_report(terminal_source=child_source)
    _child(monkeypatch, coordinator, payload)
    assert module.check(_arguments(tmp_path)) == 1
    result = _report(tmp_path)
    assert "source identity differs" in result["error"]["message"]
    lane = result["groups"]["measurement"]
    assert lane["status"] == "failed"
    assert lane["terminal_source"] == child_source
    assert lane["report_sha256"] == sha256(Path(lane["report"]).read_bytes()).hexdigest()


@pytest.mark.parametrize("name", ["inference", "math", "flowstate", "operations", "surface", "web"])
@pytest.mark.parametrize("dirty_before", [True, False], ids=["dirty-before", "changed-during"])
def test_each_gate_binds_actual_terminal_source_around_execution(monkeypatch, tmp_path, name, dirty_before):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    path = ROOT / "scripts" / ("check_monorepo_" + name + ".py")
    spec = importlib.util.spec_from_file_location("superrepo_test_gate_" + name, path)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    state = {"dirty": dirty_before, "executions": 0, "audits": 0}

    def source_audit(*args, **kwargs):
        state["audits"] += 1
        if state["dirty"]:
            raise ValueError("Terminal tracked working bytes differ from the reported source revision")
        return dict(SOURCE)

    def qualify(*args, **kwargs):
        state["executions"] += 1
        state["dirty"] = True

    monkeypatch.setattr(gate, "_git", lambda *args: HEAD)
    monkeypatch.setattr(gate, "verify_terminal_source", source_audit)
    monkeypatch.setattr(gate, "qualify" if name in {"surface", "web"} else "_qualify", qualify)
    assert gate.main(["--output-dir", str(tmp_path)]) == 1
    result = _report(tmp_path)
    assert result["status"] == "failed"
    assert "working bytes differ" in result["error"]["message"]
    assert state["executions"] == (0 if dirty_before else 1)
    assert state["audits"] == (1 if dirty_before else 2)
    if not dirty_before:
        assert result["terminal_source"] == SOURCE


def test_surface_retry_preserves_old_evidence_before_rejecting_dirty_current_source(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("superrepo_test_surface_retry", ROOT / "scripts/check_monorepo_surface.py")
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    old_log = tmp_path / "commands.log"
    old_log.write_text("original fixture failure")
    old_revision = "2" * 40
    previous = {"terminal_revision": old_revision, "verification_id": "verification:" + uuid.uuid4().hex,
                "status": "failed", "log": str(old_log), "created_at": "2026-10-03T00:00:00Z"}
    previous_bytes = json.dumps(previous).encode()
    (tmp_path / "report.json").write_bytes(previous_bytes)
    monkeypatch.setattr(gate, "_git", lambda *args: HEAD)

    def dirty_source(*args, **kwargs):
        raise ValueError("Terminal tracked working bytes differ from the reported source revision")

    monkeypatch.setattr(gate, "verify_terminal_source", dirty_source)
    monkeypatch.setattr(gate, "resume_remaining", lambda *args: pytest.fail("Dirty source must not resume execution"))
    assert gate.main(["--output-dir", str(tmp_path), "--resume-remaining"]) == 1
    result = _report(tmp_path)
    retained = result["prefix_evidence"]["report"]
    assert result["terminal_revision"] == HEAD
    assert retained["terminal_revision"] == old_revision
    assert retained["verification_id"] == previous["verification_id"]
    assert Path(retained["path"]).read_bytes() == previous_bytes
    assert retained["sha256"] == sha256(previous_bytes).hexdigest()
    assert old_log.read_text() == "original fixture failure"
