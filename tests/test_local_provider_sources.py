"""Real local Git transport tests; not scientific or cryptographic qualification."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/local_provider_sources.py"
spec = importlib.util.spec_from_file_location("local_provider_sources", SCRIPT)
local = importlib.util.module_from_spec(spec)
spec.loader.exec_module(local)
NAME = "giasonpooni/Parameterized-Lyapunov-Stability-Runtime"


def git(path, *args):
    return subprocess.run(["git", "-C", str(path), *args], env=local.local_environment(dict(os.environ), []),
                          check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source space"
    root.mkdir()
    git(root, "init")
    git(root, "config", "user.name", "Transport Fixture")
    git(root, "config", "user.email", "test@example.invalid")
    (root / "payload.txt").write_bytes(b"fixture bytes\n")
    git(root, "add", ".")
    git(root, "commit", "-m", "fixture")
    revision = git(root, "rev-parse", "HEAD")
    value = {"schema": local.SCHEMA, "providers": [{"repository": NAME, "revision": revision, "path": str(root)}]}
    path = tmp_path / "sources.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return root, revision, path, value


def run(tmp_path, path, code):
    report = tmp_path / "report.json"
    exit_code = local.execute(path, [sys.executable, "-c", code], report)
    return exit_code, json.loads(report.read_text())


@pytest.mark.parametrize("suffix", [".git", ""], ids=["git-suffix", "bare-name"])
def test_real_clone_uses_exact_local_objects_without_token(source, tmp_path, monkeypatch, suffix):
    root, revision, path, _ = source
    config = (root / ".git/config").read_bytes()
    monkeypatch.setenv("CIW_PROVIDER_READ_TOKEN", "synthetic-must-not-reach-child")
    monkeypatch.setenv("GITHUB_TOKEN", "synthetic-must-not-reach-child")
    dest = tmp_path / "cloned"
    code = ("import os,subprocess,pathlib; "
            "assert 'CIW_PROVIDER_READ_TOKEN' not in os.environ and 'GITHUB_TOKEN' not in os.environ; "
            f"subprocess.run(['git','clone','https://github.com/{NAME}{suffix}',{str(dest)!r}],check=True); "
            f"assert pathlib.Path({str(dest / 'payload.txt')!r}).read_bytes()==b'fixture bytes\\n'; "
            f"assert subprocess.check_output(['git','-C',{str(dest)!r},'rev-parse','HEAD'],text=True).strip()=={revision!r}")
    rc, report = run(tmp_path, path, code)
    assert rc == 0 and report["status"] == "command_succeeded"
    assert report["cryptographic_verification"] == "not_assessed_by_transport"
    assert report["providers"] == [{"repository": NAME, "revision": revision}]
    assert (root / ".git/config").read_bytes() == config
    assert os.environ["CIW_PROVIDER_READ_TOKEN"] == "synthetic-must-not-reach-child"
    assert "synthetic-must-not-reach-child" not in json.dumps(report)


@pytest.mark.parametrize("url", [
    "https://github.com/other/missing.git", "http://example.invalid/provider.git",
    "ssh://git@example.invalid/source.git", "git://example.invalid/source.git",
], ids=["unmapped-https", "http", "ssh", "git-protocol"])
def test_missing_provider_does_not_attempt_network(source, tmp_path, url):
    _, _, path, _ = source
    code = ("import subprocess; "
            f"p=subprocess.run(['git','ls-remote',{url!r}],capture_output=True,text=True,timeout=5); "
            "assert p.returncode!=0 and 'not allowed' in p.stderr")
    rc, _ = run(tmp_path, path, code)
    assert rc == 0


@pytest.mark.parametrize("change", ["wrong-pin", "tracked-edit", "untracked", "index-edit"])
def test_bad_source_refuses_before_command(source, tmp_path, change):
    root, _, path, value = source
    if change == "wrong-pin":
        value["providers"][0]["revision"] = "0" * 40
        path.write_text(json.dumps(value))
    elif change == "tracked-edit":
        (root / "payload.txt").write_text("changed")
    elif change == "index-edit":
        (root / "payload.txt").write_text("changed"); git(root, "add", ".")
    else:
        (root / "unexpected").write_text("untracked")
    sentinel = tmp_path / "ran"
    rc, report = run(tmp_path, path, f"from pathlib import Path; Path({str(sentinel)!r}).touch()")
    assert rc == 2 and not sentinel.exists() and report["status"] == "refused_or_failed"


@pytest.mark.parametrize("key,value", [
    ("repository", "../evil"), ("repository", "owner/repo.git"),
    ("repository", "https://github.com/owner/repo"), ("revision", "main"),
    ("revision", "A" * 40), ("path", "relative"), ("path", "/tmp/line\nbreak"),
], ids=["traversal", "alias", "url", "floating-pin", "uppercase-pin", "relative-path", "newline-path"])
def test_manifest_fields_refuse(source, key, value):
    _, _, path, document = source
    document["providers"][0][key] = value
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError): local.load_manifest(path)


@pytest.mark.parametrize("raw", [b"{}", b"null", b"[]", b'{"schema":1,"schema":2}', b" " * 65537],
                         ids=["object", "null", "array", "duplicate-key", "oversize"])
def test_malformed_manifest_refuses(tmp_path, raw):
    path = tmp_path / "bad.json"; path.write_bytes(raw)
    with pytest.raises(ValueError): local.load_manifest(path)


@pytest.mark.parametrize("change", ["duplicate-repo", "same-path", "extra-key", "empty", "too-many"])
def test_manifest_cardinality_and_duplicates_refuse(source, change):
    _, _, path, value = source
    if change == "duplicate-repo": value["providers"] *= 2
    elif change == "same-path":
        second = deepcopy(value["providers"][0]); second["repository"] = "other/repo"; value["providers"].append(second)
    elif change == "extra-key": value["providers"][0]["token"] = "not-accepted"
    elif change == "empty": value["providers"] = []
    else: value["providers"] *= 65
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError): local.load_manifest(path)


def test_child_failure_propagates(source, tmp_path):
    rc, report = run(tmp_path, source[2], "raise SystemExit(7)")
    assert rc == 7 and report["status"] == "command_failed"
    assert report["command_exit_code"] == 7


def test_source_mutation_during_command_is_not_success(source, tmp_path):
    root, _, path, _ = source
    rc, report = run(tmp_path, path, f"from pathlib import Path; Path({str(root / 'payload.txt')!r}).write_text('changed')")
    assert rc == 2 and report["status"] == "refused_or_failed"


def test_no_existing_report_overwrite(source, tmp_path):
    report = tmp_path / "prior.json"; report.write_bytes(b"prior evidence")
    with pytest.raises(FileExistsError):
        local.execute(source[2], [sys.executable, "-c", "pass"], report)
    assert report.read_bytes() == b"prior evidence"


def test_no_command_refuses(source, tmp_path):
    report = tmp_path / "report.json"
    with pytest.raises(ValueError): local.execute(source[2], [], report)
    assert not report.exists()


def test_protocol_config_is_ephemeral_and_credentials_are_scrubbed():
    original = {"PATH": os.environ["PATH"], "CIW_PROVIDER_READ_TOKEN": "synthetic", "GH_TOKEN": "synthetic",
                "GIT_CONFIG_PARAMETERS": "unsafe", "GIT_ALLOW_PROTOCOL": "https", "GIT_ASKPASS": "evil",
                "CIW_SCR_ENGINE": "/operator/engine"}
    env = local.local_environment(original, [])
    assert env["GIT_ALLOW_PROTOCOL"] == "file" and env["CIW_SCR_ENGINE"] == "/operator/engine"
    assert not any(env.get(k) == "synthetic" for k in original)
    assert "GIT_CONFIG_PARAMETERS" not in env and "GIT_ASKPASS" not in env
    assert original["GH_TOKEN"] == "synthetic"


def test_sha256_git_objects_remain_sha256(tmp_path):
    root = tmp_path / "sha256-source"; root.mkdir()
    git(root, "init", "--object-format=sha256")
    git(root, "config", "user.name", "Transport Fixture")
    git(root, "config", "user.email", "test@example.invalid")
    (root / "payload.txt").write_bytes(b"sha256 fixture\n")
    git(root, "add", "."); git(root, "commit", "-m", "fixture")
    revision = git(root, "rev-parse", "HEAD"); assert len(revision) == 64
    manifest = tmp_path / "sources.json"
    manifest.write_text(json.dumps({"schema": local.SCHEMA, "providers": [
        {"repository": NAME, "revision": revision, "path": str(root)}]}))
    dest = tmp_path / "sha256-clone"
    code = ("import subprocess; "
            f"subprocess.run(['git','clone','https://github.com/{NAME}.git',{str(dest)!r}],check=True); "
            f"assert subprocess.check_output(['git','-C',{str(dest)!r},'rev-parse','HEAD'],text=True).strip()=={revision!r}")
    rc, report = run(tmp_path, manifest, code)
    assert rc == 0 and report['status'] == 'command_succeeded'
