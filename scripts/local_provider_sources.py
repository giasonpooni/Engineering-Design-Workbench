"""Run an existing qualification command using verified local Git sources.

Only Git transport is made local-only. Package downloads and the selected command
are not sandboxed. Use on an operator-owned private host, never an untrusted PR.
This module creates no proof verdict and never marks a skipped gate as passed.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

# Match other source-tree integration scripts; reuse the existing byte validator.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ciw.provider_checkouts import validate_checkout

SCHEMA = "ciw-local-provider-sources-v1"
MAX_MANIFEST_BYTES = 65536
MAX_PROVIDERS = 64


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate source-manifest key")
        result[key] = value
    return result


def load_manifest(path: Path) -> tuple[bytes, tuple[tuple[str, str, Path], ...]]:
    with path.open("rb") as stream:
        raw = stream.read(MAX_MANIFEST_BYTES + 1)
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError("Source manifest exceeds 64 KiB")
    document = json.loads(raw, object_pairs_hook=_pairs)
    if not isinstance(document, dict) or set(document) != {"schema", "providers"} or document["schema"] != SCHEMA:
        raise ValueError("Invalid local-provider source manifest")
    values = document["providers"]
    if not isinstance(values, list) or not 1 <= len(values) <= MAX_PROVIDERS:
        raise ValueError("Require 1..64 explicit provider sources")
    entries, names, paths = [], set(), set()
    for entry in values:
        if not isinstance(entry, dict) or set(entry) != {"repository", "revision", "path"}:
            raise ValueError("Source entry must contain repository, revision and path only")
        name, revision, source = entry["repository"], entry["revision"], entry["path"]
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", name) or name.endswith(".git"):
            raise ValueError("Use an explicit owner/repository name, not a URL or .git alias")
        if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", revision):
            raise ValueError("A complete lowercase commit ID is required")
        if not isinstance(source, str) or any(c in source for c in "\r\n\0") or not Path(source).is_absolute():
            raise ValueError("Each source path must be absolute and unambiguous")
        source = Path(source).resolve(strict=True)
        if name.lower() in names or source in paths:
            raise ValueError("Duplicate or aliased provider source")
        names.add(name.lower()); paths.add(source)
        entries.append((name, revision, source))
    return raw, tuple(entries)


def local_environment(base: dict[str, str], mappings: list[tuple[str, str]]) -> dict[str, str]:
    """Process-scoped configuration; do not write gitconfig or credential files."""
    env = {key: value for key, value in base.items()
           if not key.startswith(("GIT_", "GH_")) and key not in
           {"GITHUB_TOKEN", "CIW_PROVIDER_READ_TOKEN", "SSH_ASKPASS", "GCM_INTERACTIVE"}}
    settings = [("credential.helper", ""), ("core.autocrlf", "false"),
                ("core.fsmonitor", "false"), ("gc.auto", "0"), ("maintenance.auto", "false")]
    for repository, uri in mappings:
        # Longer .git aliases win over the suffix-free alias. Unknown remote
        # sources cannot fall back to the network: GIT_ALLOW_PROTOCOL=file.
        for suffix in (".git", ""):
            settings.append(("url." + uri + ".insteadOf", "https://github.com/" + repository + suffix))
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_SYSTEM=os.devnull,
               GIT_CONFIG_GLOBAL=os.devnull, GIT_ALLOW_PROTOCOL="file",
               GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never",
               GIT_NO_LAZY_FETCH="1", GIT_OPTIONAL_LOCKS="0",
               GIT_CONFIG_COUNT=str(len(settings)))
    for index, (key, value) in enumerate(settings):
        env[f"GIT_CONFIG_KEY_{index}"] = key
        env[f"GIT_CONFIG_VALUE_{index}"] = value
    return env


@contextmanager
def _environment(env):
    # This is a single-process operator CLI, not a thread-safe service API.
    original = dict(os.environ)
    os.environ.clear(); os.environ.update(env)
    try:
        yield
    finally:
        os.environ.clear(); os.environ.update(original)


def _git(args: list[str], env: dict[str, str]) -> None:
    completed = subprocess.run(["git", "--no-replace-objects", *args], env=env,
                               capture_output=True, timeout=120, check=False)
    if completed.returncode:
        # Do not copy arbitrary provider diagnostics into the transport report.
        raise RuntimeError("Local Git snapshot construction failed")


def execute(manifest: Path, command: list[str], report: Path) -> int:
    if not command:
        raise ValueError("An explicit qualification command is required")
    # Reserve the report first: never overwrite prior evidence or source files.
    with report.open("x", encoding="utf-8") as retained:
        outcome = {"schema": "ciw-local-source-execution-v1", "status": "preflight",
                   "mode": "local_git_sources", "cryptographic_verification": "not_assessed_by_transport",
                   "admission": "not_performed"}
        try:
            raw, entries = load_manifest(manifest)
            outcome["manifest_sha256"] = hashlib.sha256(raw).hexdigest()
            outcome["providers"] = [{"repository": name, "revision": rev} for name, rev, _ in entries]
            base = local_environment(dict(os.environ), [])
            with _environment(base):
                for _, revision, source in entries:
                    validate_checkout(source, revision)
            with tempfile.TemporaryDirectory(prefix="ciw-local-sources-") as directory:
                mappings = []
                for index, (name, revision, source) in enumerate(entries):
                    target = Path(directory) / str(index)
                    _git(["init", "--bare", "--object-format=" + ("sha1" if len(revision) == 40 else "sha256"), str(target)], base)
                    _git(["-C", str(target), "fetch", "--no-tags", "--depth=1", source.as_uri(), revision], base)
                    _git(["-C", str(target), "update-ref", "refs/heads/pinned", revision], base)
                    _git(["-C", str(target), "symbolic-ref", "HEAD", "refs/heads/pinned"], base)
                    mappings.append((name, target.as_uri()))
                result = subprocess.run(command, env=local_environment(base, mappings), check=False)
                outcome["command_exit_code"] = result.returncode
                with _environment(base):
                    for _, revision, source in entries:
                        validate_checkout(source, revision)
                outcome["status"] = "command_succeeded" if result.returncode == 0 else "command_failed"
                return result.returncode if result.returncode >= 0 else 128 - result.returncode
        except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
            outcome.update(status="refused_or_failed", error_type=type(exc).__name__)
            print(f"Local provider route refused: {type(exc).__name__}", file=sys.stderr)
            return 2
        finally:
            retained.write(json.dumps(outcome, indent=2) + "\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    try:
        return execute(args.manifest, command, args.report)
    except (ValueError, OSError) as exc:
        print(f"Cannot start local provider route: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
