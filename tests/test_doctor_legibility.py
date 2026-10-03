"""Legibility provisioning checks inspect metadata without executing the instrument."""
import builtins
import json
from pathlib import Path
import socket
import subprocess
import sys
from types import SimpleNamespace

import pytest

from ciw import doctor


CIW = "computational-instrumentation-workbench"
CORE = ["numpy==2.4.3", "websockets==16.0"]
LEGIBILITY = 'cryptography==46.0.0; extra == "legibility"'


def install_metadata(monkeypatch, *, requirements=None, versions=None, absent=()):
    calls = []
    requirements = [*CORE, LEGIBILITY] if requirements is None else requirements
    versions = {"numpy": "2.4.3", "websockets": "16.0", "cryptography": "46.0.0", **(versions or {})}

    def distribution(name):
        calls.append(name)
        if name in absent:
            raise doctor.metadata.PackageNotFoundError(name)
        if name == CIW:
            return SimpleNamespace(version="0.1.0", metadata={"Requires-Python": ">=3.11"},
                                   requires=list(requirements))
        assert name in versions, "Unselected distribution was inspected: " + name
        return SimpleNamespace(version=versions[name])

    monkeypatch.setattr(doctor.metadata, "distribution", distribution)
    return calls


def check(report, name):
    return next(row for row in report["checks"] if row["check"] == name)


def test_legibility_includes_core_and_exact_selected_optional_requirements(monkeypatch):
    calls = install_metadata(monkeypatch, requirements=[*CORE, LEGIBILITY,
        'private @ https://example.invalid/private; extra == "other"'])
    report = doctor.diagnose("legibility")
    assert report["status"] == "preflight_passed"
    assert report["read_only"] is True
    assert report["qualification"] == "not_performed"
    assert calls == [CIW, "numpy", "websockets", "cryptography"]
    assert check(report, "ciw_distribution")["status"] == "passed"
    assert check(report, "python_version")["status"] == "passed"
    assert check(report, "core_dependency:numpy")["status"] == "passed"
    assert check(report, "core_dependency:websockets")["status"] == "passed"
    assert check(report, "legibility_dependency:cryptography")["expected"] == LEGIBILITY
    assert report["requirements"]["authority"] == "installed CIW distribution metadata"
    assert report["requirements"]["distributions"] == [{"distribution": "cryptography", "version": "46.0.0",
                                                           "requirement": LEGIBILITY}]
    assert "key generation, signing, signature verification or issuer trust" in report["not_checked"]


def test_optional_version_is_derived_from_installed_ciw_metadata(monkeypatch):
    requirement = "Cryptography == 49.2.1 ; extra == 'legibility'"
    install_metadata(monkeypatch, requirements=[*CORE, requirement], versions={"cryptography": "49.2.1"})
    report = doctor.diagnose("legibility")
    assert report["status"] == "preflight_passed"
    assert check(report, "legibility_dependency:cryptography")["observed"]["version"] == "49.2.1"


def test_additional_exact_selected_requirements_are_checked(monkeypatch):
    calls = install_metadata(monkeypatch, requirements=[*CORE, LEGIBILITY, "Example_Package==1.2.3; extra == 'legibility'"],
                             versions={"example-package": "1.2.3"})
    report = doctor.diagnose("legibility")
    assert report["status"] == "preflight_passed"
    assert calls == [CIW, "numpy", "websockets", "cryptography", "example-package"]
    assert check(report, "legibility_dependency:example-package")["status"] == "passed"


@pytest.mark.parametrize("absent", [CIW, "numpy", "cryptography"])
def test_missing_installed_distribution_blocks_preflight(monkeypatch, absent):
    install_metadata(monkeypatch, absent=[absent])
    report = doctor.diagnose("legibility")
    assert report["status"] == "blocked"
    assert report["classifications"] == ["dependency_unavailable"]
    assert report["qualification"] == "not_performed"
    name = "ciw_distribution" if absent == CIW else ("core_dependency:" if absent == "numpy" else "legibility_dependency:") + absent
    assert check(report, name)["status"] == "failed"


@pytest.mark.parametrize("name, version", [("cryptography", "45.0.0"), ("numpy", "2.4.2")])
def test_wrong_installed_version_blocks_preflight(monkeypatch, name, version):
    install_metadata(monkeypatch, versions={name: version})
    report = doctor.diagnose("legibility")
    assert report["status"] == "blocked"
    assert report["classifications"] == ["identity_mismatch"]
    row = check(report, ("legibility_dependency:" if name == "cryptography" else "core_dependency:") + name)
    assert row["observed"]["version"] == version


@pytest.mark.parametrize("selected", [
    [],
    ['cryptography==46.0.0; extra == "other"'],
    ['other-package==1.0.0; extra == "legibility"'],
    ['cryptography>=46.0.0; extra == "legibility"'],
    ['cryptography===46.0.0; extra == "legibility"'],
    ['cryptography==not-a-version; extra == "legibility"'],
    ['cryptography @ https://example.invalid/cryptography.whl; extra == "legibility"'],
    ['cryptography[unexpected]==46.0.0; extra == "legibility"'],
    ['cryptography==46.0.0; extra == "legibility" and python_version >= "3.11"'],
    ['cryptography==46.0.0; extra != "legibility"'],
    [LEGIBILITY, LEGIBILITY],
    [LEGIBILITY, 'Cryptography==46.0.0; extra == "legibility"'],
])
def test_missing_unsupported_or_ambiguous_selected_metadata_refuses(monkeypatch, selected):
    calls = install_metadata(monkeypatch, requirements=[*CORE, *selected])
    report = doctor.diagnose("legibility")
    assert report["status"] == "blocked"
    assert report["classifications"] == ["setup_failure"]
    assert check(report, "legibility_requirements")["status"] == "failed"
    assert "cryptography" not in calls


@pytest.mark.parametrize("option", ["stack_root", "engine", "binding"])
def test_legibility_refuses_native_or_declared_workload_bindings(monkeypatch, tmp_path, option):
    calls = install_metadata(monkeypatch)
    report = doctor.diagnose("legibility", **{option: tmp_path / "never-read"})
    assert report["status"] == "blocked"
    assert report["classifications"] == ["setup_failure"]
    assert check(report, "profile_configuration")["reason"] == "Legibility doctor does not accept provider bindings"
    assert calls == []


def test_core_profile_still_does_not_inspect_legibility_dependency(monkeypatch):
    calls = install_metadata(monkeypatch, absent=["cryptography"])
    report = doctor.diagnose("core")
    assert report["status"] == "preflight_passed"
    assert calls == [CIW, "numpy", "websockets"]
    assert all(not row["check"].startswith("legibility_") for row in report["checks"])


def test_profile_has_no_dependency_import_execution_or_network_side_effects(monkeypatch):
    calls = install_metadata(monkeypatch)
    original_import = builtins.__import__
    forbidden = ("cryptography", "numpy", "websockets", "ciw.native_interop", "ciw.declared_workload")
    before = {name for name in sys.modules if name.startswith(forbidden)}

    def guarded_import(name, *args, **kwargs):
        if name.startswith(forbidden) or name in {"native_interop", "declared_workload"}:
            pytest.fail("Doctor imported an unselected executable dependency: " + name)
        return original_import(name, *args, **kwargs)

    def forbidden_call(*args, **kwargs):
        pytest.fail("Doctor attempted provider execution or network access")

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(doctor, "_git", forbidden_call)
    monkeypatch.setattr(doctor, "validate_checkout", forbidden_call)
    monkeypatch.setattr(subprocess, "Popen", forbidden_call)
    monkeypatch.setattr(socket, "socket", forbidden_call)
    monkeypatch.setattr(socket, "create_connection", forbidden_call)
    report = doctor.diagnose("legibility")
    assert report["status"] == "preflight_passed"
    assert calls == [CIW, "numpy", "websockets", "cryptography"]
    assert {name for name in sys.modules if name.startswith(forbidden)} == before


@pytest.mark.parametrize("absent, exit_code, status", [((), 0, "preflight_passed"), (("cryptography",), 2, "blocked")])
def test_cli_reports_json_and_appropriate_preflight_exit_status(monkeypatch, capsys, absent, exit_code, status):
    from ciw.cli import main
    install_metadata(monkeypatch, absent=absent)
    assert main(["doctor", "--profile", "legibility"]) == exit_code
    captured = capsys.readouterr()
    assert captured.err == ""
    report = json.loads(captured.out)
    assert report["profile"] == "legibility"
    assert report["status"] == status
    assert report["qualification"] == "not_performed"


def test_capability_profile_metadata_matches_without_importing_doctor():
    script = """
import json, sys
sys.path.insert(0, sys.argv[1])
from ciw.capabilities import get
profile = get("doctor.preflight")
assert "legibility" in profile["profiles"]
assert profile["qualification"] == "not_performed"
assert profile["authorizes_execution"] is False
forbidden = {"ciw.doctor", "ciw.native_interop", "ciw.declared_workload", "cryptography"}
print(json.dumps(sorted(forbidden & set(sys.modules))))
"""
    completed = subprocess.run([sys.executable, "-c", script, str(Path(doctor.__file__).resolve().parents[1])],
                               check=True, capture_output=True, text=True)
    assert json.loads(completed.stdout) == []
    from ciw.capabilities import get
    assert tuple(get("doctor.preflight")["profiles"]) == doctor.PROFILES


def test_fresh_doctor_import_and_preflight_do_not_load_optional_or_provider_modules():
    script = """
import builtins, json, socket, subprocess, sys
from types import SimpleNamespace
sys.path.insert(0, sys.argv[1])
original_import = builtins.__import__
forbidden = ("cryptography", "numpy", "websockets", "ciw.native_interop", "ciw.declared_workload")
def guarded_import(name, *args, **kwargs):
    if name.startswith(forbidden) or name in {"native_interop", "declared_workload"}:
        raise AssertionError("Unexpected import: " + name)
    return original_import(name, *args, **kwargs)
def blocked(*args, **kwargs):
    raise AssertionError("Execution or network call")
builtins.__import__ = guarded_import
subprocess.Popen = socket.socket = socket.create_connection = blocked
from ciw import doctor
versions = {"numpy": "2.4.3", "websockets": "16.0", "cryptography": "46.0.0"}
def distribution(name):
    if name == "computational-instrumentation-workbench":
        return SimpleNamespace(version="0.1.0", metadata={"Requires-Python": ">=3.11"},
            requires=["numpy==2.4.3", "websockets==16.0", 'cryptography==46.0.0; extra == "legibility"'])
    return SimpleNamespace(version=versions[name])
doctor.metadata.distribution = distribution
report = doctor.diagnose("legibility")
assert report["status"] == "preflight_passed"
assert report["qualification"] == "not_performed"
print(json.dumps(sorted(name for name in sys.modules if name.startswith(forbidden))))
"""
    completed = subprocess.run([sys.executable, "-c", script, str(Path(doctor.__file__).resolve().parents[1])],
                               check=True, capture_output=True, text=True)
    assert json.loads(completed.stdout) == []
