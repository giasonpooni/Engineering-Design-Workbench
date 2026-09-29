"""Read-only release request and artifact-integrity guards. No publishing code."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tomllib


def check_request(repository: str, ref_type: str, ref_name: str, confirmation: str, version: str) -> None:
    if repository != "giasonpooni/Notations-ClockSync":
        raise ValueError("wrong publishing repository")
    if ref_type != "tag" or ref_name != f"v{version}":
        raise ValueError("publish from the exact version tag, not a branch")
    if confirmation != f"publish-v{version}":
        raise ValueError("explicit version-bound publication confirmation is required")


def check_bundle(bundle: Path, expected_commit: str, expected_version: str) -> None:
    if re.fullmatch(r"[0-9a-f]{40}", expected_commit) is None:
        raise ValueError("expected a full source commit")
    evidence = json.loads((bundle / "release-evidence.json").read_text(encoding="utf-8"))
    if evidence.get("kind") != "clocksync.distribution-check.v1" or evidence.get("source_commit") != expected_commit or evidence.get("version") != expected_version:
        raise ValueError("bundle source/version identity mismatch")
    entries = evidence.get("artifacts")
    if not isinstance(entries, list) or len(entries) != 2:
        raise ValueError("expected one wheel and one sdist")
    names = [entry["filename"] for entry in entries]
    expected_names = {f"notations_clocksync-{expected_version}-py3-none-any.whl", f"notations_clocksync-{expected_version}.tar.gz"}
    if set(names) != expected_names or len(set(names)) != 2:
        raise ValueError("unexpected artifact filenames")
    if {item.name for item in (bundle / "dist").iterdir()} != expected_names:
        raise ValueError("unexpected dist contents")
    for entry in entries:
        path = bundle / "dist" / entry["filename"]
        if path.is_symlink() or not path.is_file():
            raise ValueError("artifact must be a regular file")
        if path.stat().st_size != entry["bytes"] or hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError("artifact checksum/size mismatch")


def main() -> None:
    if sys.argv[1:] == ["request"]:
        project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]
        check_request(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_REF_TYPE"], os.environ["GITHUB_REF_NAME"], os.environ["CONFIRMATION"], project["version"])
    elif len(sys.argv) == 3 and sys.argv[1] == "bundle":
        check_bundle(Path(sys.argv[2]), os.environ["GITHUB_SHA"], os.environ["GITHUB_REF_NAME"].removeprefix("v"))
    else:
        raise SystemExit("usage: release_guard.py request | bundle DIRECTORY")


if __name__ == "__main__":
    main()
