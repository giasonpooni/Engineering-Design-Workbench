import hashlib
import json
from pathlib import Path
import runpy

import pytest

GUARD = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "release_guard.py"))
check_request = GUARD["check_request"]
check_bundle = GUARD["check_bundle"]


def test_release_request():
    check_request("giasonpooni/Notations-ClockSync", "tag", "v0.1.0", "publish-v0.1.0", "0.1.0")


@pytest.mark.parametrize("arguments", [
    ("other/repo", "tag", "v0.1.0", "publish-v0.1.0", "0.1.0"),
    ("giasonpooni/Notations-ClockSync", "branch", "v0.1.0", "publish-v0.1.0", "0.1.0"),
    ("giasonpooni/Notations-ClockSync", "tag", "v0.2.0", "publish-v0.1.0", "0.1.0"),
    ("giasonpooni/Notations-ClockSync", "tag", "v0.1.0", "yes", "0.1.0"),
])
def test_release_request_refuses_mismatch(arguments):
    with pytest.raises(ValueError):
        check_request(*arguments)


def bundle(tmp_path):
    directory = tmp_path / "dist"
    directory.mkdir()
    names = ["notations_clocksync-0.1.0-py3-none-any.whl", "notations_clocksync-0.1.0.tar.gz"]
    entries = []
    for name in names:
        content = b"synthetic artifact-integrity fixture, not an installable package"
        (directory / name).write_bytes(content)
        entries.append({"filename": name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
    evidence = {"kind": "clocksync.distribution-check.v1", "source_commit": "a" * 40, "version": "0.1.0", "artifacts": entries}
    (tmp_path / "release-evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
    return evidence


def test_intact_bundle(tmp_path):
    bundle(tmp_path)
    check_bundle(tmp_path, "a" * 40, "0.1.0")


def test_changed_bytes_refused(tmp_path):
    evidence = bundle(tmp_path)
    (tmp_path / "dist" / evidence["artifacts"][0]["filename"]).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        check_bundle(tmp_path, "a" * 40, "0.1.0")


@pytest.mark.parametrize("commit,version", [("b" * 40, "0.1.0"), ("a" * 40, "0.2.0"), ("short", "0.1.0")])
def test_bundle_identity_refused(tmp_path, commit, version):
    bundle(tmp_path)
    with pytest.raises(ValueError):
        check_bundle(tmp_path, commit, version)


def test_extra_distribution_refused(tmp_path):
    bundle(tmp_path)
    (tmp_path / "dist" / "unexpected.whl").write_bytes(b"unexpected")
    with pytest.raises(ValueError):
        check_bundle(tmp_path, "a" * 40, "0.1.0")


def test_path_substitution_refused(tmp_path):
    evidence = bundle(tmp_path)
    evidence["artifacts"][0]["filename"] = "../outside.whl"
    (tmp_path / "release-evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
    with pytest.raises(ValueError):
        check_bundle(tmp_path, "a" * 40, "0.1.0")
