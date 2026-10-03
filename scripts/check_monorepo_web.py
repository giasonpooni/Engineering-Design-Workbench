"""Build the preserved public views with their own locks and hermetic tests.

Dependency installation uses the public npm registry. Tests and builds receive
no operational credentials; this gate never starts an app, MCP server, smoke
client, live provider, or device gateway. Globe's default snapshot has no NET
client, so these checks do not claim attached-browser interoperability.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import uuid

if __package__:
    from .check_monorepo import _copy_source, _git
    from .monorepo import ROOT, load_manifest, provider_worktrees, verify_imports
else:
    from check_monorepo import _copy_source, _git
    from monorepo import ROOT, load_manifest, provider_worktrees, verify_imports

ROLES = frozenset({"gsv", "framemapper"})
SCOPE = ("Independent public web package tests, type checks and production builds; "
         "no live provider, freight dispatch, communication, device execution, "
         "coordinate transformation, scientific state admission, or attached NET browser qualification.")


def _node_environment(temporary: Path) -> dict[str, str]:
    # An app build must not inherit configured provider secrets or a user's npm
    # auth file. Retain only execution, temporary-file and registry transport.
    allowed = {"PATH", "HOME", "USER", "LOGNAME", "TMPDIR", "TEMP", "TMP",
               "SYSTEMROOT", "COMSPEC", "PATHEXT", "LANG", "LC_ALL",
               "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy",
               "https_proxy", "no_proxy", "SSL_CERT_FILE", "SSL_CERT_DIR",
               "NODE_EXTRA_CA_CERTS"}
    environment = {name: value for name, value in os.environ.items() if name in allowed}
    configuration = temporary / "empty-npmrc"
    configuration.write_text("")
    environment.update({"CI": "true", "NEXT_TELEMETRY_DISABLED": "1",
                        "npm_config_userconfig": str(configuration),
                        "npm_config_audit": "false", "npm_config_fund": "false"})
    return environment


def _run(arguments, *, cwd: Path, temporary: Path, log: Path, timeout=600) -> str:
    command = [str(argument) for argument in arguments]
    with log.open("ab") as stream:
        stream.write(("\n$ " + " ".join(command) + "\n").encode())
        result = subprocess.run(command, cwd=cwd, env=_node_environment(temporary),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                timeout=timeout, check=False)
        stream.write(result.stdout)
    if result.returncode:
        raise RuntimeError(f"Web command failed ({result.returncode}): {' '.join(command[:5])}\n"
                           + result.stdout.decode(errors="replace")[-6000:])
    return result.stdout.decode()


def qualify(report: dict, output: Path, log: Path) -> None:
    report["imports"] = verify_imports(ROOT)
    modules = {module["role"]: module for module in load_manifest(ROOT)["modules"]
               if module["role"] in ROLES}
    if set(modules) != ROLES:
        raise ValueError("Both public web snapshots must be registered before qualification")
    with tempfile.TemporaryDirectory(prefix="notations-web-") as directory:
        temporary = Path(directory)
        node = _run(["node", "--version"], cwd=temporary, temporary=temporary, log=log).strip()
        if int(node.removeprefix("v").split(".")[0]) < 24:
            raise RuntimeError("The Globe's native TypeScript tests require Node 24 or newer")
        report["node_version"] = node
        report["npm_version"] = _run(["npm", "--version"], cwd=temporary, temporary=temporary, log=log).strip()
        report["packages"] = {}
        with provider_worktrees(ROOT, revisions="import", roles=sorted(ROLES)) as sources:
            for role, source in sorted(sources.items()):
                work = temporary / role
                _copy_source(source, work)
                package = json.loads((work / "package.json").read_text())
                lock = work / "package-lock.json"
                raw_lock = lock.read_bytes()
                original_package = (work / "package.json").read_bytes()
                locked = json.loads(raw_lock)
                if locked["packages"][""]["version"] != package["version"]:
                    raise AssertionError("The preserved npm lock must retain its original package version")
                _run(["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"],
                     cwd=work, temporary=temporary, log=log, timeout=900)
                result = {"source_revision": modules[role]["import_revision"],
                          "source_tree": modules[role]["import_tree"],
                          "name": package["name"], "version": package["version"],
                          "npm_private": package.get("private", False),
                          "repository_visibility": "public", "license": modules[role]["license"],
                          "lock_sha256": sha256(raw_lock).hexdigest(),
                          # FrameMapper's upstream package was renamed without
                          # changing the root lock name. Record both original
                          # identities; npm ci checks their dependency contract.
                          "original_lock_name": locked["packages"][""]["name"]}
                if role == "gsv":
                    raw = _run(["npm", "run", "--offline", "build"], cwd=work,
                               temporary=temporary, log=log)
                    # Node 24 chooses its human reporter under CI; older TAP
                    # output uses '#'. Both expose the same terminal counters.
                    counts = {name: re.findall(r"^[#ℹ] " + name + r" (\d+)$", raw, re.MULTILINE)
                              for name in ("tests", "skipped", "fail", "cancelled", "todo")}
                    tests = counts["tests"]
                    if (len(tests) != 1 or int(tests[0]) < 1
                            or any(counts[name] != ["0"] for name in ("skipped", "fail", "cancelled", "todo"))):
                        raise AssertionError("Globe's unchanged node suite must execute with zero skips/failures")
                    result["tests"] = int(tests[0])
                    result["checks"] = ["layer_seam", "synthetic_provenance", "node_tests", "typescript", "vite_build"]
                else:
                    junit = output / "framemapper-tests.json"
                    _run(["npm", "run", "--offline", "test", "--", "--reporter=json",
                          "--outputFile=" + str(junit)], cwd=work, temporary=temporary, log=log)
                    tests = json.loads(junit.read_text())
                    if (not tests.get("success") or tests.get("numTotalTests", 0) < 1
                            or tests.get("numFailedTests") != 0 or tests.get("numPendingTests") != 0
                            or tests.get("numTodoTests", 0) != 0):
                        raise AssertionError("FrameMapper's unchanged hermetic suite must execute without skips/failures")
                    result["tests"] = tests["numTotalTests"]
                    result["test_report_sha256"] = sha256(junit.read_bytes()).hexdigest()
                    _run(["npm", "exec", "--offline", "--", "tsc", "--noEmit"],
                         cwd=work, temporary=temporary, log=log)
                    _run(["npm", "run", "--offline", "build"], cwd=work,
                         temporary=temporary, log=log, timeout=900)
                    result["checks"] = ["hermetic_vitest", "typescript", "next_build"]
                    result["live_tests_qualified"] = False
                    result["intel_service_started"] = False
                if lock.read_bytes() != raw_lock or (work / "package.json").read_bytes() != original_package:
                    raise AssertionError("npm execution must not rewrite the preserved package metadata or lock")
                result.update({"failures": 0, "skipped": 0, "build_passed": True,
                               "provider_credentials_supplied": False, "service_started": False})
                report["packages"][role] = result
        report["post_execution_imports"] = verify_imports(ROOT)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results/monorepo-web")
    args = parser.parse_args(argv)
    output = args.output_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    log = output / "commands.log"
    log.write_text("")
    report = {"schema": "notations.monorepo-web-gate.v1", "status": "running",
              "verification_id": "verification:" + uuid.uuid4().hex,
              "created_at": datetime.now(timezone.utc).isoformat(),
              "terminal_revision": _git(ROOT, "rev-parse", "HEAD"),
              "claim_scope": SCOPE, "log": str(log), "minimum_node": "24"}
    try:
        qualify(report, output, log)
    except Exception as error:
        report.update(status="failed", error={"type": type(error).__name__, "message": str(error)})
        print("Public web gate failed:", error)
    else:
        report["status"] = "passed"
        print("Public web gate passed: preserved locks, hermetic tests, type checks and independent builds")
    finally:
        (output / "report.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
