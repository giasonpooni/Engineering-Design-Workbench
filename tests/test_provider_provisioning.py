"""Offline gates reuse exact operator-owned checkouts without rewriting them."""
import importlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


def git(path, *arguments):
    return subprocess.run(["git", "-C", str(path), *arguments], check=True,
                          capture_output=True, text=True).stdout.strip()


def repository(path):
    path.mkdir(parents=True)
    git(path, "init", "-q")
    git(path, "config", "core.autocrlf", "false")
    git(path, "config", "user.name", "Provider test")
    git(path, "config", "user.email", "provider@example.invalid")
    (path / "source.txt").write_bytes(b"pinned provider\n")
    git(path, "add", "source.txt")
    git(path, "commit", "-qm", "provider fixture")
    return git(path, "rev-parse", "HEAD")


@pytest.fixture
def helpers(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    return importlib.import_module("provider_checkouts")


def configured_gate(name, tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    gate = importlib.import_module("check_" + name)
    root = tmp_path / "project"
    manifests = root / "src" / "ciw"
    manifests.mkdir(parents=True)
    stack = tmp_path / "stack"
    path = stack / ("Example-Provider" if name == "telemetry" else "engine")
    previous = repository(path)
    historical = None
    pin = {"revision": previous, "repository": "https://example.invalid/provider", "module": "provider"}
    if name == "adapters":
        historical = stack / "engine-legacy"
        subprocess.run(["git", "-c", "core.autocrlf=false", "clone", "--quiet", "--no-hardlinks", str(path), str(historical)], check=True)
        (path / "source.txt").write_bytes(b"current pinned provider\n")
        git(path, "add", "source.txt")
        git(path, "commit", "-qm", "current fixture")
        pin["revision"] = git(path, "rev-parse", "HEAD")
        pin["historical"] = [{"revision": previous, "module": "provider"}]
        manifest = "adapter-runtimes.json"
        monkeypatch.setattr(gate, "ROOT", root)
    else:
        monkeypatch.setattr(gate, "__file__", str(root / "scripts" / ("check_" + name + ".py")))
        monkeypatch.setattr(gate, "REPOSITORIES", {"engine": "Example-Provider"})
        manifest = "telemetry-runtimes.json" if name == "telemetry" else "calibrated-observable-runtimes.json"
    (manifests / manifest).write_text(json.dumps({"engine": pin}), encoding="utf-8")
    return gate, stack, path, historical, previous


def guard_processes(monkeypatch):
    """Run only local read-only Git probes; capture the final pytest process."""
    original = subprocess.run
    invocations = []

    def run(arguments, **kwargs):
        if arguments[0] == "git":
            assert not {"clone", "checkout", "config", "fetch", "pull"}.intersection(arguments)
            return original(arguments, **kwargs)
        assert arguments[1:3] == ["-m", "pytest"]
        invocations.append((arguments, kwargs))
        return subprocess.CompletedProcess(arguments, 0)

    def call(arguments, **kwargs):
        return run(arguments, **kwargs).returncode

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(subprocess, "call", call)
    return invocations


@pytest.mark.parametrize("name", ["adapters", "telemetry", "calibrated_observable"])
def test_local_stack_uses_exact_pins_without_rewriting_checkouts(name, tmp_path, monkeypatch):
    gate, stack, path, historical, _ = configured_gate(name, tmp_path, monkeypatch)
    checkouts = [path] + ([historical] if historical else [])
    before = {(checkout, filename): (checkout / ".git" / filename).read_bytes()
              for checkout in checkouts for filename in ("HEAD", "config", "index")}
    invocations = guard_processes(monkeypatch)
    gate.main(["--stack-root", str(stack)])
    assert len(invocations) == 1
    environment = invocations[0][1]["env"]
    if name == "adapters":
        assert environment["CIW_ENGINE_REPO"] == str(path.resolve())
        assert environment["CIW_ENGINE_LEGACY_REPO"] == str(historical.resolve())
    else:
        key = "CIW_TELEMETRY_STACK_ROOT" if name == "telemetry" else "CIW_CALIBRATED_STACK_ROOT"
        assert environment[key] == str(stack.resolve())
    assert all((checkout / ".git" / filename).read_bytes() == value
               for (checkout, filename), value in before.items())


@pytest.mark.parametrize("name", ["adapters", "telemetry", "calibrated_observable"])
@pytest.mark.parametrize("failure", ["wrong_pin", "dirty", "missing"])
def test_local_stack_refuses_before_starting_integration_tests(name, failure, tmp_path, monkeypatch):
    gate, stack, path, _, _ = configured_gate(name, tmp_path, monkeypatch)
    if failure == "wrong_pin":
        (path / "source.txt").write_bytes(b"unapproved revision\n")
        git(path, "add", "source.txt")
        git(path, "commit", "-qm", "unapproved change")
    elif failure == "dirty":
        (path / "source.txt").write_bytes(b"uncommitted change\n")
    else:
        stack = tmp_path / "unavailable"
    invocations = guard_processes(monkeypatch)
    with pytest.raises(ValueError, match="wrong pin|dirty|unavailable"):
        gate.main(["--stack-root", str(stack)])
    assert not invocations


def test_separate_historical_stack_is_explicitly_bound(tmp_path, monkeypatch):
    gate, stack, path, historical, previous = configured_gate("adapters", tmp_path, monkeypatch)
    historic_root = tmp_path / "historical"
    historic = historic_root / "engine"
    historic_root.mkdir()
    subprocess.run(["git", "-c", "core.autocrlf=false", "clone", "--quiet", "--no-hardlinks", str(historical), str(historic)], check=True)
    invocations = guard_processes(monkeypatch)
    gate.main(["--stack-root", str(stack), "--historical-stack-root", str(historic_root)])
    assert invocations[0][1]["env"]["CIW_ENGINE_LEGACY_REPO"] == str(historic.resolve())
    assert git(historic, "rev-parse", "HEAD") == previous


def test_historical_checkout_must_match_its_own_pin(tmp_path, monkeypatch):
    gate, stack, _, historical, _ = configured_gate("adapters", tmp_path, monkeypatch)
    (historical / "source.txt").write_bytes(b"modified historical evidence\n")
    invocations = guard_processes(monkeypatch)
    with pytest.raises(ValueError, match="dirty"):
        gate.main(["--stack-root", str(stack)])
    assert not invocations


def test_assume_unchanged_does_not_hide_raw_byte_drift(tmp_path, helpers):
    path = tmp_path / "provider"
    revision = repository(path)
    (path / ".git" / "info" / "attributes").write_text("*.txt text\n", encoding="utf-8")
    (path / "source.txt").write_bytes(b"pinned provider\r\n")
    git(path, "update-index", "--assume-unchanged", "source.txt")
    assert git(path, "status", "--porcelain") == ""
    with pytest.raises(ValueError, match="tracked bytes"):
        helpers.validate_checkout(path, revision)


def test_ignored_noncache_source_is_not_an_approved_pin(tmp_path, helpers):
    path = tmp_path / "provider"
    revision = repository(path)
    (path / ".git" / "info" / "exclude").write_text("shadow.py\n", encoding="utf-8")
    (path / "shadow.py").write_text("raise RuntimeError('unapproved')\n", encoding="utf-8")
    assert git(path, "status", "--porcelain") == ""
    with pytest.raises(ValueError, match="untracked"):
        helpers.validate_checkout(path, revision)


def test_uninitialized_pinned_gitlink_needs_no_symlink_or_download(tmp_path, helpers):
    path = tmp_path / "provider"
    linked_revision = repository(path)
    git(path, "update-index", "--add", "--cacheinfo", f"160000,{linked_revision},vendor/scout")
    git(path, "commit", "-qm", "retain submodule boundary")
    (path / "vendor" / "scout").mkdir(parents=True)
    revision = git(path, "rev-parse", "HEAD")
    assert helpers.validate_checkout(path, revision) == path.resolve()


@pytest.mark.parametrize("failure,classification,code", [
    ("missing", "dependency_unavailable", "CHECKOUT_UNAVAILABLE"),
    ("invalid_revision", "setup_failure", "INVALID_REVISION"),
    ("wrong_pin", "identity_mismatch", "WRONG_PIN"),
    ("dirty", "identity_mismatch", "TRACKED_BYTES_MISMATCH"),
    ("untracked", "identity_mismatch", "UNTRACKED_FILES"),
])
def test_checkout_refusals_have_stable_categories(failure, classification, code, tmp_path, helpers):
    path = tmp_path / "provider"
    revision = "a" * 40 if failure == "missing" else repository(path)
    if failure == "invalid_revision":
        revision = "not-a-commit"
    elif failure == "wrong_pin":
        revision = "0" * 40
    elif failure == "dirty":
        (path / "source.txt").write_bytes(b"uncommitted change\n")
    elif failure == "untracked":
        (path / "extra.py").write_bytes(b"# unapproved source\n")
    with pytest.raises(helpers.ProviderCheckoutError) as caught:
        helpers.validate_checkout(path, revision)
    assert isinstance(caught.value, ValueError)
    assert (caught.value.classification, caught.value.code) == (classification, code)


@pytest.mark.parametrize("error,classification,code", [
    (FileNotFoundError("git unavailable"), "dependency_unavailable", "GIT_UNAVAILABLE"),
    (subprocess.TimeoutExpired("git", 60), "setup_failure", "GIT_TIMEOUT"),
    (subprocess.CalledProcessError(1, "git"), "setup_failure", "GIT_FAILED"),
])
def test_git_failures_have_stable_categories(error, classification, code, tmp_path, helpers, monkeypatch):
    def fail(arguments, **kwargs):
        assert kwargs["env"]["GIT_OPTIONAL_LOCKS"] == "0"
        raise error

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(helpers.ProviderCheckoutError) as caught:
        helpers._git(tmp_path, "rev-parse", "HEAD")
    assert (caught.value.classification, caught.value.code) == (classification, code)
    assert str(caught.value) == f"Cannot verify provider checkout: {tmp_path}"


def test_script_wrapper_loads_source_package_without_installation(tmp_path):
    code = """
import importlib.util
from pathlib import Path
import sys
spec = importlib.util.spec_from_file_location('provider_script_fixture', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
from ciw import provider_checkouts
assert module.validate_checkout is provider_checkouts.validate_checkout
assert module._git is provider_checkouts._git
assert module.ProviderCheckoutError is provider_checkouts.ProviderCheckoutError
assert Path(provider_checkouts.__file__).resolve() == Path(sys.argv[2]).resolve()
"""
    subprocess.run([sys.executable, "-I", "-S", "-B", "-c", code,
                    str(ROOT / "scripts" / "provider_checkouts.py"),
                    str(ROOT / "src" / "ciw" / "provider_checkouts.py")],
                   cwd=tmp_path, check=True, capture_output=True, timeout=30)


@pytest.mark.parametrize("dirty", [False, True])
def test_configured_clean_filter_never_runs_during_validation(tmp_path, helpers, monkeypatch, dirty):
    path = tmp_path / "provider"
    revision = repository(path)
    marker = tmp_path / "clean-filter-ran"
    command = "printf '%s' called > " + shlex.quote(marker.as_posix()) + "; cat"
    git(path, "config", "filter.doctor-probe.clean", command)
    (path / ".git" / "info" / "attributes").write_text("*.txt filter=doctor-probe\n", encoding="utf-8")
    # Activate the filter only after the fixture commit. Changed stat metadata
    # makes even a byte-clean file require content inspection by `git status`.
    source = path / "source.txt"
    if dirty:
        source.write_bytes(b"uncommitted provider change\n")
    stat = source.stat()
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))
    before = {name: (path / name).read_bytes()
              for name in ("source.txt", ".git/HEAD", ".git/index", ".git/config", ".git/info/attributes")}
    original_run = subprocess.run
    invocations = []

    def observe(arguments, **kwargs):
        invocations.append(arguments)
        return original_run(arguments, **kwargs)

    monkeypatch.setattr(subprocess, "run", observe)
    assert not marker.exists()
    if dirty:
        with pytest.raises(helpers.ProviderCheckoutError) as caught:
            helpers.validate_checkout(path, revision)
        assert caught.value.classification == "identity_mismatch"
        assert caught.value.code == "TRACKED_BYTES_MISMATCH"
    else:
        assert helpers.validate_checkout(path, revision) == path.resolve()
    assert not marker.exists(), "Read-only validation invoked the configured clean filter"
    assert all(arguments[0] == "git" and "status" not in arguments for arguments in invocations)
    assert all((path / name).read_bytes() == data for name, data in before.items())


@pytest.mark.parametrize("change", ["staged_content", "staged_mode"])
def test_index_only_drift_is_refused_with_unchanged_working_bytes(tmp_path, helpers, change):
    path = tmp_path / "provider"
    revision = repository(path)
    source = path / "source.txt"
    original = source.read_bytes()
    if change == "staged_content":
        source.write_bytes(b"index-only unapproved provider\n")
        git(path, "add", "source.txt")
        source.write_bytes(original)
    else:
        blob = git(path, "rev-parse", "HEAD:source.txt")
        git(path, "update-index", "--cacheinfo", f"100755,{blob},source.txt")
    index = (path / ".git" / "index").read_bytes()
    with pytest.raises(helpers.ProviderCheckoutError) as caught:
        helpers.validate_checkout(path, revision)
    assert caught.value.classification == "identity_mismatch"
    assert caught.value.code == "DIRTY_CHECKOUT"
    assert source.read_bytes() == original
    assert (path / ".git" / "index").read_bytes() == index


@pytest.mark.parametrize("change", ["clean", "revision", "tracked_bytes", "index_only"])
def test_initialized_submodule_is_checked_without_git_status(tmp_path, helpers, monkeypatch, change):
    path = tmp_path / "provider"
    repository(path)
    upstream = tmp_path / "local-scout"
    repository(upstream)
    git(path, "-c", "core.autocrlf=false", "-c", "protocol.file.allow=always",
        "submodule", "add", "--quiet", str(upstream), "vendor/scout")
    git(path, "commit", "-qm", "retain initialized submodule")
    revision = git(path, "rev-parse", "HEAD")
    child = path / "vendor" / "scout"
    source = child / "source.txt"
    if change == "revision":
        git(child, "-c", "user.name=Provider test", "-c", "user.email=provider@example.invalid",
            "commit", "--allow-empty", "-qm", "unapproved submodule revision")
    elif change == "tracked_bytes":
        source.write_bytes(b"uncommitted submodule source\n")
    elif change == "index_only":
        blob = git(child, "rev-parse", "HEAD:source.txt")
        git(child, "update-index", "--cacheinfo", f"100755,{blob},source.txt")
    original_run = subprocess.run
    invocations = []

    def observe(arguments, **kwargs):
        invocations.append(arguments)
        assert arguments[0] == "git" and "status" not in arguments
        return original_run(arguments, **kwargs)

    monkeypatch.setattr(subprocess, "run", observe)
    if change == "clean":
        assert helpers.validate_checkout(path, revision) == path.resolve()
    else:
        with pytest.raises(helpers.ProviderCheckoutError) as caught:
            helpers.validate_checkout(path, revision)
        assert caught.value.classification == "identity_mismatch"
    assert invocations
