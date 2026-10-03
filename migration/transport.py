"""One-time exact-history transport; project code runs only in the read job."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

REPOSITORY = "atomtrapping/Notations-Systems-Terminal"
EXPECTED_REVISION = "aa4981b510c72eaedc91acaadf697f97f33238d4"
BASE_REVISION = "890055df183c52908ea186fb8f5984e9d47d9a29"
TARGET_REF = "refs/heads/feat/monorepo-continuation-20261003"
STAGING_REF = "refs/heads/transport/monorepo-aa4981b5-20261003"
PLAN_SHA256 = "ede8ff7466420f1a383b24dd4a9d11e4862aad1aedc40717fa50db164d4afaa5"
BUNDLE_SHA256 = "de26b1db1d9150dcde558e1859549d434990c0a638b5f79b3ef0ece53a961e4d"
BUNDLE_SIZE = 132377
FULL_BUNDLE_LIMIT = 1024 * 1024 * 1024
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def environment(*, publish: bool = False) -> dict[str, str]:
    result = {key: value for key, value in os.environ.items()
              if not key.startswith("GIT_") and key not in {
                  "GH_TOKEN", "GITHUB_TOKEN", "TRANSPORT_TOKEN", "PYTHONPATH", "PYTHONHOME"}}
    result.update({"LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1",
                   "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0",
                   "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"})
    if publish:
        token = os.environ.get("TRANSPORT_TOKEN", "")
        require(bool(token), "Final push requires its ephemeral job token")
        # Git reads this header from the child process environment only. No
        # token is placed in a URL, command argument, configuration file or log.
        import base64
        header = base64.b64encode(("x-access-token:" + token).encode()).decode()
        result.update({"GIT_CONFIG_COUNT": "1",
                       "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
                       "GIT_CONFIG_VALUE_0": "AUTHORIZATION: basic " + header})
    return result


def run(arguments: list[str], *, cwd: Path, evidence: Path,
        timeout: int = 180, publish: bool = False) -> str:
    result = subprocess.run(arguments, cwd=cwd, env=environment(publish=publish),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=timeout, check=False)
    # Process output is bounded in failure reports. The sole authenticated
    # command is an ordinary push to a constant public URL, without tracing.
    output = result.stdout.decode("utf-8", errors="replace")
    errors = result.stderr.decode("utf-8", errors="replace")
    with (evidence / "commands.log").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(arguments) + "\n" + output + errors + "\n")
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {arguments[:3]}\n"
                           + (output + errors)[-12000:])
    return output.strip()


def git(repo: Path, *arguments: str, evidence: Path,
        timeout: int = 180, publish: bool = False) -> str:
    return run(["git", "--no-replace-objects", "-c", "core.fsmonitor=false",
                "-c", "core.autocrlf=false", "-c", "core.hooksPath=" + os.devnull,
                *arguments], cwd=repo, evidence=evidence, timeout=timeout, publish=publish)


def plan(path: Path) -> dict:
    require(path.is_file() and not path.is_symlink(), "Plan must be a regular file")
    require(digest(path) == PLAN_SHA256, "Reviewed plan checksum differs")
    value = json.loads(path.read_text(encoding="utf-8"))
    require(value["schema"] == "notations.native-monorepo-transfer.v1", "Unknown plan schema")
    expected = {"repository": REPOSITORY, "expected_revision": EXPECTED_REVISION,
                "base_revision": BASE_REVISION, "target_ref": TARGET_REF,
                "bundle_sha256": BUNDLE_SHA256, "bundle_size_bytes": BUNDLE_SIZE}
    require(all(value[key] == expected[key] for key in expected), "Plan identity differs")
    require(len(value["prerequisites"]) == 21, "Expected exactly 21 public module prerequisites")
    for item in value["prerequisites"]:
        require(re.fullmatch(r"atomtrapping/[A-Za-z0-9_.-]+", item["repository"]) is not None,
                "Prerequisite URL is outside the reviewed public account")
        require(bool(item["revisions"]) and all(SHA40.fullmatch(sha) for sha in item["revisions"]),
                "Prerequisites must contain full immutable commit SHAs")
    return value


def bundle_header(path: Path, *, self_contained: bool) -> None:
    require(path.is_file() and not path.is_symlink(), "Bundle must be a regular file")
    with path.open("rb") as stream:
        lines = []
        for _ in range(100):
            line = stream.readline(512)
            require(len(line) <= 511, "Bundle header line exceeds bounds")
            if line == b"\n":
                break
            require(bool(line), "Bundle header is incomplete")
            lines.append(line.decode("ascii").rstrip("\n"))
        else:
            raise ValueError("Bundle header exceeds bounds")
    require(lines[0] in {"# v2 git bundle", "# v3 git bundle"}, "Unknown Git bundle version")
    refs = []
    for line in lines[1:]:
        if line.startswith("@"):
            require(line == "@object-format=sha1", "Unexpected bundle capability")
        elif line.startswith("-"):
            require(not self_contained, "Publisher bundle must have no prerequisites")
            require(SHA40.fullmatch(line[1:41]) is not None, "Malformed prerequisite SHA")
        else:
            refs.append(line)
    require(refs == [EXPECTED_REVISION + " " + TARGET_REF], "Unexpected bundle refs or native HEAD")


def event_gate() -> None:
    require(os.environ.get("GITHUB_REPOSITORY") == REPOSITORY, "Unexpected workflow repository")
    require(os.environ.get("GITHUB_REF") == STAGING_REF, "Unexpected workflow staging ref")
    require(os.environ.get("GITHUB_EVENT_NAME") == "push", "Only the isolated staging push is permitted")
    require(SHA40.fullmatch(os.environ.get("GITHUB_SHA", "")) is not None, "Missing staging commit SHA")


def initialize(path: Path, evidence: Path) -> None:
    require(not path.exists(), "Transport work directory must be fresh")
    path.mkdir(parents=True)
    git(path, "init", "--quiet", evidence=evidence)


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def audit(args: argparse.Namespace, evidence: Path, report: dict) -> None:
    value = plan(args.plan)
    require(args.bundle.stat().st_size == BUNDLE_SIZE and digest(args.bundle) == BUNDLE_SHA256,
            "Thin bundle size or checksum differs")
    bundle_header(args.bundle, self_contained=False)
    initialize(args.work, evidence)
    url = "https://github.com/" + REPOSITORY + ".git"
    git(args.work, "fetch", "--no-tags", url,
        BASE_REVISION + ":refs/transport/base", evidence=evidence, timeout=300)
    fetched = []
    for index, item in enumerate(value["prerequisites"]):
        for subindex, revision in enumerate(item["revisions"]):
            ref = f"refs/transport/prerequisites/{index}/{subindex}"
            source = "https://github.com/" + item["repository"] + ".git"
            git(args.work, "fetch", "--no-tags", source, revision + ":" + ref,
                evidence=evidence, timeout=300)
            require(git(args.work, "rev-parse", ref, evidence=evidence) == revision,
                    "Fetched prerequisite identity differs")
            require(git(args.work, "cat-file", "-t", revision, evidence=evidence) == "commit",
                    "Prerequisite is not a commit")
            fetched.append({"repository": item["repository"], "revision": revision})
    report["fetched_prerequisites"] = fetched
    git(args.work, "bundle", "verify", str(args.bundle), evidence=evidence)
    git(args.work, "fetch", "--no-tags", str(args.bundle), TARGET_REF + ":" + TARGET_REF,
        evidence=evidence)
    require(git(args.work, "rev-parse", TARGET_REF, evidence=evidence) == EXPECTED_REVISION,
            "Imported native HEAD differs")
    git(args.work, "merge-base", "--is-ancestor", BASE_REVISION, EXPECTED_REVISION, evidence=evidence)
    git(args.work, "fsck", "--full", "--no-reflogs", evidence=evidence, timeout=300)
    git(args.work, "checkout", "--detach", EXPECTED_REVISION, evidence=evidence)
    for name, arguments in [
        ("source-audit.json", [sys.executable, "scripts/monorepo.py"]),
        ("modules.json", [sys.executable, "scripts/superrepo.py", "list", "--json"]),
        ("terminal-source.json", [sys.executable, "-c",
            "import json, sys; sys.path.insert(0, 'scripts'); "
            "from monorepo import verify_terminal_source; "
            "print(json.dumps(verify_terminal_source(), indent=2))"]),
    ]:
        output = run(arguments, cwd=args.work, evidence=evidence, timeout=180)
        json.loads(output)
        (evidence / name).write_text(output + "\n", encoding="utf-8")
    require(git(args.work, "rev-parse", "HEAD", evidence=evidence) == EXPECTED_REVISION,
            "Audit moved native HEAD")
    require(not git(args.work, "status", "--porcelain", "--untracked-files=all", evidence=evidence),
            "Audit changed the native checkout")
    args.output.mkdir(parents=True, exist_ok=False)
    full = args.output / "audited-native.bundle"
    git(args.work, "bundle", "create", str(full), TARGET_REF, evidence=evidence, timeout=300)
    bundle_header(full, self_contained=True)
    require(full.stat().st_size <= FULL_BUNDLE_LIMIT, "Full native artifact exceeds transport bound")
    checksum = digest(full)
    report.update({"audit_status": "passed", "artifact_sha256": checksum,
                   "artifact_size_bytes": full.stat().st_size,
                   "qualification_scope": "Git identity, complete history, preserved source and migration audit only"})
    write_json(args.output / "audit-manifest.json", report)
    (args.output / "audited-native.bundle.sha256").write_text(
        checksum + "  audited-native.bundle\n", encoding="ascii")
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as stream:
        stream.write("artifact_sha256=" + checksum + "\n")


def publish(args: argparse.Namespace, evidence: Path, report: dict) -> None:
    plan(args.plan)
    require(SHA64.fullmatch(args.sha256) is not None, "Audit output checksum is malformed")
    require(0 < args.bundle.stat().st_size <= FULL_BUNDLE_LIMIT, "Full bundle size is outside bounds")
    require(digest(args.bundle) == args.sha256, "Audited artifact checksum differs")
    bundle_header(args.bundle, self_contained=True)
    initialize(args.work, evidence)
    git(args.work, "bundle", "verify", str(args.bundle), evidence=evidence)
    git(args.work, "fetch", "--no-tags", str(args.bundle), TARGET_REF + ":" + TARGET_REF,
        evidence=evidence, timeout=300)
    require(git(args.work, "rev-parse", TARGET_REF, evidence=evidence) == EXPECTED_REVISION,
            "Publisher native HEAD differs")
    require(git(args.work, "cat-file", "-t", EXPECTED_REVISION, evidence=evidence) == "commit",
            "Expected native HEAD is not a commit")
    git(args.work, "merge-base", "--is-ancestor", BASE_REVISION, EXPECTED_REVISION, evidence=evidence)
    git(args.work, "fsck", "--full", "--no-reflogs", evidence=evidence, timeout=300)
    url = "https://github.com/" + REPOSITORY + ".git"
    remote = git(args.work, "ls-remote", "--heads", url, TARGET_REF, evidence=evidence)
    old = None
    if remote:
        entries = [line.split() for line in remote.splitlines()]
        require(len(entries) == 1 and len(entries[0]) == 2 and entries[0][1] == TARGET_REF,
                "Unexpected remote continuation refs")
        old = entries[0][0]
        require(SHA40.fullmatch(old) is not None, "Unexpected remote continuation SHA")
        git(args.work, "fetch", "--no-tags", url, TARGET_REF + ":refs/transport/previous",
            evidence=evidence, timeout=300)
        git(args.work, "merge-base", "--is-ancestor", old, EXPECTED_REVISION, evidence=evidence)
    report.update({"previous_remote_revision": old, "artifact_sha256": args.sha256,
                   "push_policy": "ordinary fast-forward-only exact continuation ref"})
    # This is the only child process receiving the ephemeral write token.
    git(args.work, "push", "--porcelain", url, EXPECTED_REVISION + ":" + TARGET_REF,
        evidence=evidence, timeout=300, publish=True)
    observed = git(args.work, "ls-remote", "--heads", url, TARGET_REF, evidence=evidence)
    require(observed.split() == [EXPECTED_REVISION, TARGET_REF], "Published continuation differs")
    report.update({"published_revision": EXPECTED_REVISION, "publish_status": "passed"})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    for command in ("audit", "publish"):
        sub = subcommands.add_parser(command)
        sub.add_argument("--plan", type=Path, required=True)
        sub.add_argument("--bundle", type=Path, required=True)
        sub.add_argument("--work", type=Path, required=True)
        sub.add_argument("--evidence", type=Path, required=True)
        if command == "audit":
            sub.add_argument("--output", type=Path, required=True)
        else:
            sub.add_argument("--sha256", required=True)
    args = parser.parse_args()
    for attribute in ("plan", "bundle", "work", "evidence", "output"):
        if hasattr(args, attribute):
            setattr(args, attribute, getattr(args, attribute).resolve())
    args.evidence.mkdir(parents=True, exist_ok=True)
    report = {"schema": "notations.native-monorepo-transport-evidence.v1",
              "phase": args.command, "status": "running", "repository": REPOSITORY,
              "native_revision": EXPECTED_REVISION, "target_ref": TARGET_REF,
              "created_at": datetime.now(timezone.utc).isoformat(),
              "staging_revision": os.environ.get("GITHUB_SHA"),
              "run_id": os.environ.get("GITHUB_RUN_ID"),
              "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT")}
    try:
        event_gate()
        (audit if args.command == "audit" else publish)(args, args.evidence, report)
        report["status"] = "passed"
        print(json.dumps({"phase": args.command, "status": "passed",
                          "native_revision": EXPECTED_REVISION}))
        return 0
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
        print(str(error), file=sys.stderr)
        return 1
    finally:
        write_json(args.evidence / "transport-report.json", report)


if __name__ == "__main__":
    raise SystemExit(main())
