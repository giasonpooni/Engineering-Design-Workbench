"""Doctor checks local identities without becoming a provider execution path."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import socket
import subprocess
from types import SimpleNamespace

import pytest

from ciw import doctor


def git(path, *args):
    return subprocess.run(["git", "-C", str(path), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def checkout(path):
    path.mkdir(parents=True)
    git(path, "init", "-q")
    git(path, "config", "core.autocrlf", "false")
    git(path, "config", "user.name", "Doctor fixture")
    git(path, "config", "user.email", "doctor@example.invalid")
    (path / "source.txt").write_bytes(b"doctor fixture\n")
    git(path, "add", "source.txt")
    git(path, "commit", "-qm", "fixture")
    return git(path, "rev-parse", "HEAD"), git(path, "rev-parse", "HEAD^{tree}")


def digest(raw):
    return "sha256:" + sha256(raw).hexdigest()


def forbid_execution(monkeypatch):
    original = subprocess.run
    def run(command, **kwargs):
        assert command[0] == "git", "Doctor must not launch a provider/interpreter/package manager"
        assert not {"clone", "checkout", "config", "fetch", "pull", "reset"}.intersection(command)
        assert kwargs["env"]["GIT_OPTIONAL_LOCKS"] == "0"
        assert kwargs["env"]["GIT_NO_LAZY_FETCH"] == "1"
        return original(command, **kwargs)
    def forbidden(*args, **kwargs):
        raise AssertionError("Doctor must not execute providers or contact the network")
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    from ciw import native_interop
    from ciw.adapters.subprocess import PinnedSubprocessAdapter
    monkeypatch.setattr(native_interop, "_invoke", forbidden)
    monkeypatch.setattr(native_interop, "_runtime", forbidden)
    monkeypatch.setattr(PinnedSubprocessAdapter, "__init__", forbidden)


@pytest.fixture
def native(tmp_path, monkeypatch):
    from ciw import native_interop as ni
    revision, tree = checkout(tmp_path / "scr")
    (tmp_path / "host").write_bytes(b"not an executable: host fixture")
    (tmp_path / "worker-exe").write_bytes(b"not an executable: worker fixture")
    (tmp_path / "depot").mkdir()
    files = {}
    for name, data in {"Project.toml": b"project", "Manifest.toml": b"manifest", "worker.jl": b"worker"}.items():
        relative = "runtimes/fixture/" + name
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        files[relative] = digest(data)
    pin = {"scr_revisions": [revision], "scr_trees": {revision: tree}, "files": files,
           "executable_sha256": digest((tmp_path / "worker-exe").read_bytes()),
           "worker_identity": {"packages": {"fixture": "expected-only"}}}
    pins = {"scr_revisions": [revision], "julia_files": files, "interval_family": pin,
            "reaction_families": {"catalyst": deepcopy(pin), "cantera": deepcopy(pin)}}
    monkeypatch.setattr(ni, "_pins", lambda: deepcopy(pins))
    binding = {"scr": "scr", "host": "host", "host_sha256": digest((tmp_path / "host").read_bytes()),
               "provider": "intervals", "executable": "worker-exe", "runtime": ".", "depot": str(tmp_path / "depot")}
    path = tmp_path / "binding.json"
    path.write_text(json.dumps(binding))
    return tmp_path, path, binding, pins


def check(report, name):
    return next(row for row in report["checks"] if row["check"] == name)


def test_interval_preflight_is_read_only_and_does_not_claim_worker_identity(native, monkeypatch):
    root, path, _, pins = native
    tracked = [root / "scr/.git" / name for name in ("HEAD", "config", "index")]
    before = {str(item): item.read_bytes() for item in tracked}
    files_before = {str(item) for item in root.rglob("*")}
    forbid_execution(monkeypatch)
    result = doctor.diagnose("interval-requirement", binding=path)
    assert result["status"] == "preflight_passed"
    assert result["qualification"] == "not_performed"
    assert result["requirements"]["worker_identity"] == pins["interval_family"]["worker_identity"]
    assert "expected-only" not in json.dumps([row["observed"] for row in result["checks"]])
    assert {str(item): item.read_bytes() for item in tracked} == before
    assert {str(item) for item in root.rglob("*")} == files_before
    assert "worker loadability" in result["not_checked"]


@pytest.mark.parametrize("profile,provider", [("reaction-catalyst", "catalyst"), ("reaction-cantera", "cantera")])
def test_family_selection_reuses_its_authoritative_requirements(native, monkeypatch, profile, provider):
    _, path, binding, pins = native
    binding["provider"] = provider
    if provider == "cantera":
        binding.pop("depot")
    path.write_text(json.dumps(binding))
    forbid_execution(monkeypatch)
    result = doctor.diagnose(profile, binding=path)
    assert result["status"] == "preflight_passed"
    assert result["requirements"]["files"] == pins["reaction_families"][provider]["files"]


@pytest.mark.parametrize("change,classification,check_name", [
    ("missing_host", "dependency_unavailable", "host_binary"),
    ("changed_host", "identity_mismatch", "host_binary"),
    ("changed_worker", "identity_mismatch", "worker_files"),
    ("changed_executable", "identity_mismatch", "worker_executable"),
    ("wrong_pin", "identity_mismatch", "checkout:scr"),
    ("wrong_tree", "identity_mismatch", "checkout:scr"),
    ("wrong_family", "identity_mismatch", "runtime_binding"),
    ("extra_field", "setup_failure", "runtime_binding"),
    ("bad_digest", "setup_failure", "runtime_binding"),
])
def test_native_refusals_are_classified_without_execution(native, monkeypatch, change, classification, check_name):
    root, path, binding, pins = native
    if change == "missing_host":
        (root / "host").unlink()
    elif change == "changed_host":
        (root / "host").write_bytes(b"changed")
    elif change == "changed_worker":
        (root / "runtimes/fixture/worker.jl").write_bytes(b"changed")
    elif change == "changed_executable":
        (root / "worker-exe").write_bytes(b"changed")
    elif change == "wrong_pin":
        pins["interval_family"]["scr_revisions"] = ["f" * 40]
    elif change == "wrong_tree":
        pins["interval_family"]["scr_trees"] = {}
    elif change == "wrong_family":
        binding["provider"] = "cantera"
    elif change == "extra_field":
        binding["unreviewed"] = "value"
    elif change == "bad_digest":
        binding["host_sha256"] = "newest"
    path.write_text(json.dumps(binding))
    forbid_execution(monkeypatch)
    result = doctor.diagnose("interval-requirement", binding=path)
    assert result["status"] == "blocked"
    assert check(result, check_name)["classification"] == classification
    assert result["qualification"] == "not_performed"


def test_whole_historical_closure_is_allowed_but_mixing_is_rejected(native, monkeypatch):
    root, path, binding, pins = native
    binding = {key: binding[key] for key in ("scr", "host", "host_sha256")}
    binding.update(julia="worker-exe", julia_runtime=".", julia_depot=str(root / "depot"))
    path.write_text(json.dumps(binding))
    pins["historical_julia_files"] = [deepcopy(pins["julia_files"])]
    pins["julia_files"] = {name: digest(b"other") for name in pins["julia_files"]}
    forbid_execution(monkeypatch)
    assert doctor.diagnose("native-interop", binding=path)["status"] == "preflight_passed"
    (root / "runtimes/fixture/worker.jl").write_bytes(b"other")
    result = doctor.diagnose("native-interop", binding=path)
    assert check(result, "worker_files")["classification"] == "identity_mismatch"


@pytest.mark.parametrize("raw", [b"[]", b'{"host": 1, "host": 2}', b'{"host": NaN}', b"x" * 65537,
                                b'{"nested":' + b"[" * 5000 + b"0" + b"]" * 5000 + b"}"],
                         ids=["array", "duplicate", "nonfinite", "oversized", "deeply_nested"])
def test_malformed_binding_is_setup_failure(tmp_path, raw):
    path = tmp_path / "binding.json"
    path.write_bytes(raw)
    result = doctor.diagnose("native-interop", binding=path)
    assert result["classifications"] == ["setup_failure"]


def test_missing_binding_retains_requirements_and_stays_unqualified():
    from ciw.interval_runtime import qualification
    result = doctor.diagnose("interval-requirement")
    assert result["classifications"] == ["dependency_unavailable"]
    assert result["requirements"]["files"] == qualification()["files"]
    assert result["qualification"] == "not_performed"


def test_declared_pins_are_derived_and_unrelated_profiles_are_not_touched(tmp_path, monkeypatch):
    from ciw import declared_workload, native_interop
    revision, _ = checkout(tmp_path / "sra")
    pins = {"fixture-kind": {"role": "sra", "revision": revision, "source_root": ".", "module": "fixture"}}
    monkeypatch.setattr(declared_workload, "PINS", pins)
    monkeypatch.setattr(native_interop, "_pins", lambda: pytest.fail("unselected profile"))
    engine = tmp_path / "engine"
    engine.write_bytes(b"not an executable")
    forbid_execution(monkeypatch)
    result = doctor.diagnose("declared-workloads", stack_root=tmp_path, engine=engine)
    assert result["status"] == "preflight_passed"
    assert check(result, "checkout:sra")["expected"]["revision"] == revision
    assert check(result, "execution_engine")["expected"]["binding"] == "operator_asserted_not_attested"


def test_core_reads_distribution_metadata_without_importing_optional_packages(monkeypatch):
    calls = []
    def distribution(name):
        calls.append(name)
        if name == "computational-instrumentation-workbench":
            return SimpleNamespace(version="fixture", metadata={"Requires-Python": ">=3.11"},
                                   requires=['example==1.2.3', 'private @ https://example.invalid; extra == "optional"'])
        assert name == "example"
        return SimpleNamespace(version="1.2.3")
    monkeypatch.setattr(doctor.metadata, "distribution", distribution)
    forbid_execution(monkeypatch)
    result = doctor.diagnose("core")
    assert result["status"] == "preflight_passed"
    assert calls == ["computational-instrumentation-workbench", "example"]


def test_core_unknown_requirement_fails_closed(monkeypatch):
    monkeypatch.setattr(doctor.metadata, "distribution", lambda name: SimpleNamespace(
        version="fixture", metadata={"Requires-Python": ">=3.11"}, requires=["example>=1"]))
    assert doctor.diagnose("core")["classifications"] == ["setup_failure"]


def test_cli_returns_json_with_nonzero_missing_dependency(capsys):
    from ciw.cli import main
    assert main(["doctor", "--profile", "interval-requirement"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["profile"] == "interval-requirement"
    assert result["qualification"] == "not_performed"


def test_profile_options_fail_closed(tmp_path):
    result = doctor.diagnose("core", binding=tmp_path / "irrelevant.json")
    assert result["classifications"] == ["setup_failure"]


def test_depot_relative_and_literal_tilde_match_native_semantics(tmp_path, monkeypatch):
    from ciw.native_interop import _depot as native_depot
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError):
        doctor._depot("~")
    with pytest.raises(FileNotFoundError):
        native_depot("~")
    (tmp_path / "~").mkdir()
    (tmp_path / "ordinary").mkdir()
    for value in ("~", "ordinary", "."):
        observed, matches = doctor._depot(value)
        assert matches
        assert observed["paths"] == native_depot(value).split(doctor.os.pathsep)
