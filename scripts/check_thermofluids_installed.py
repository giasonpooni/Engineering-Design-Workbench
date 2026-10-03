"""Qualify the installed thermofluids CLI outside the source checkout.

This is command-lifecycle qualification, not independent physical validation.
Uses the current Python interpreter in isolated mode, with no source-tree imports.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


PROFILES = ("convection", "heat-exchanger", "pipe-flow", "radiation", "two-phase")


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def qualify(destination: Path) -> dict:
    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError(f"Qualification destination already exists: {destination}")

    with tempfile.TemporaryDirectory(prefix="net-thermofluids-installed-") as temporary:
        working = Path(temporary)

        def command(*arguments: str, expected: int = 0) -> dict:
            completed = subprocess.run(
                [sys.executable, "-I", "-m", "ciw.net", "thermofluids", *arguments],
                cwd=working, text=True, capture_output=True, check=False, timeout=60,
            )
            if completed.returncode != expected:
                raise AssertionError(
                    f"thermofluids {arguments[0]} returned {completed.returncode}; "
                    f"expected {expected}: {completed.stderr or completed.stdout}"
                )
            return json.loads(completed.stderr if expected == 1 else completed.stdout)

        catalog = command("catalog")
        assert {item["profile"] for item in catalog["profiles"]} == set(PROFILES)
        assert catalog["read_only"] is True
        assert catalog["authorizes_execution"] is False
        assert catalog["qualification"] == "not_performed_by_catalog"
        (working / "catalog.json").write_text(json.dumps(catalog, indent=2), encoding="utf-8")

        profiles = {}
        for profile in PROFILES:
            request_name = f"{profile}-request.json"
            run_name = f"{profile}-run.json"
            verification_name = f"{profile}-verification.json"
            replay_name = f"{profile}-replay.json"
            request = command("example", "--profile", profile, "--output", request_name)
            request_path = working / request_name
            assert json.loads(request_path.read_text(encoding="utf-8")) == request
            request_before = _digest(request_path)
            run = command("run", request_name, "--output", run_name)
            run_path = working / run_name
            assert json.loads(run_path.read_text(encoding="utf-8")) == run
            run_before = _digest(run_path)
            assert run["request"] == request
            assert len({run[key] for key in (
                "evidence_id", "operation_id", "execution_id", "result_id"
            )}) == 4
            assert run["authority"]["physical_validation"] == "not_established"
            assert run["authority"]["state_admission"] == "not_performed"
            assert run["authority"]["hardware_actuation"] == "not_performed"

            inspected = command("inspect", run_name)
            assert inspected["integrity"] == "PASS"
            assert inspected["numerical_verification"] == "not_performed_by_inspection"
            for name in ("evidence_id", "operation_id", "execution_id", "result_id"):
                assert inspected[name] == run[name]
            assert inspected["data"] == run["data"]

            verification = command("verify", run_name, "--output", verification_name)
            second = command("verify", run_name, "--output", f"{profile}-verification-2.json")
            assert verification["status"] == second["status"] == "PASS"
            assert verification["scope"] == "same_implementation_exact_recomputation"
            assert verification["independent"] is False
            assert verification["checks"] == {
                "retained_integrity": True, "same_runtime": True, "exact_recomputation": True,
            }
            assert verification["verification_id"] != second["verification_id"]
            assert verification["verification_id"] not in {
                run["evidence_id"], run["operation_id"], run["execution_id"], run["result_id"]
            }
            assert verification["record_ref"] == run["record_digest"]
            assert verification["execution_ref"] == run["execution_id"]
            assert verification["result_ref"] == run["result_id"]

            replay = command("replay", run_name, "--output", replay_name)
            assert replay["execution_id"] != run["execution_id"]
            assert replay["result_id"] != run["result_id"]
            assert replay["evidence_id"] == run["evidence_id"]
            assert replay["operation_id"] == run["operation_id"]
            assert replay["numerical_digest"] == run["numerical_digest"]
            assert replay["replay_of"] == {
                name: run[name] for name in ("record_digest", "execution_id", "result_id")
            }
            assert command("verify", replay_name, "--output", f"{profile}-replay-verification.json")["status"] == "PASS"

            refused = command("example", "--profile", profile, "--output", request_name, expected=1)
            assert refused["status"] == "REFUSE"
            assert command("run", request_name, "--output", run_name, expected=1)["status"] == "REFUSE"
            assert _digest(request_path) == request_before
            assert _digest(run_path) == run_before

            malformed = dict(request, unsupported_requested_capability="outside_declared_scope")
            malformed_name = f"{profile}-invalid-request.json"
            malformed_path = working / malformed_name
            malformed_path.write_text(json.dumps(malformed, indent=2), encoding="utf-8")
            malformed_before = _digest(malformed_path)
            blocked_name = f"{profile}-blocked-run.json"
            assert command("run", malformed_name, "--output", blocked_name, expected=1)["status"] == "REFUSE"
            assert not (working / blocked_name).exists()
            assert _digest(malformed_path) == malformed_before

            profiles[profile] = {
                "status": "PASS", "evidence_id": run["evidence_id"],
                "operation_id": run["operation_id"], "execution_id": run["execution_id"],
                "result_id": run["result_id"], "verification_id": verification["verification_id"],
                "numerical_digest": run["numerical_digest"],
                "new_verification_and_replay_occurrences": True,
                "request_and_retained_run_unchanged": True,
                "overwrite_and_malformed_request_refused": True,
            }

        summary = {
            "schema": "ciw.thermofluids-installed-qualification.v1", "status": "PASS",
            "profiles": profiles, "python_executable": sys.executable,
            "isolated_installed_execution": True,
            "scope": "installed_command_lifecycle", "physical_validation": "not_established",
            "independent_scientific_validation": "not_performed", "state_admission": "not_performed",
        }
        (working / "qualification.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        shutil.copytree(working, destination)
        return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(qualify(arguments.output_dir), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
