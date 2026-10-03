"""Exercise installed fluid CLI and immutable archived bundles outside source."""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path
import subprocess


def _snapshot(directory):
    return {str(path.relative_to(directory)): sha256(path.read_bytes()).hexdigest()
            for path in directory.rglob("*") if path.is_file()}


def qualify(executable: Path, destination: Path) -> dict:
    executable = executable.resolve(strict=True)
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=False)

    def command(*arguments, expected=0):
        completed = subprocess.run([str(executable), "fluid", *arguments], cwd=destination,
                                   capture_output=True, text=True, timeout=180)
        if completed.returncode != expected:
            raise AssertionError(f"fluid {arguments[0]} returned {completed.returncode}: "
                                 f"{completed.stderr or completed.stdout}")
        return json.loads(completed.stderr if expected == 1 else completed.stdout)

    profiles = {}
    for profile in ("reservoir", "wave"):
        command("example", "--profile", profile, "--output", profile + ".json")
        request = json.loads((destination / (profile + ".json")).read_text())
        result = command("run", "--request", profile + ".json", "--output-dir", profile)
        assert result["status"] == "LOCAL", result
        before = _snapshot(destination / profile)
        inspected = command("inspect", profile)
        verified = command("verify", profile, "--output", profile + "-fresh-audit.json")
        verified_again = command("verify", profile)
        assert inspected["fresh_numerical_verification"] is False
        assert verified["fresh_numerical_verification"] is True
        assert verified["status"] == verified_again["status"] == "LOCAL"
        for key in ("fresh_verification_id", "fresh_verification_execution_id", "fresh_verification_result_id"):
            assert verified[key] != verified_again[key]
        assert verified["fresh_verification_id"] != inspected["verification_id"]
        witness = json.loads((destination / (profile + "-fresh-audit.json")).read_text())
        assert witness["fresh_verification_record"]["verification_id"] == verified["fresh_verification_id"]
        command("export-csv", profile, "--output", profile + ".csv")
        with (destination / (profile + ".csv")).open(newline="", encoding="utf-8") as stream:
            reader = csv.reader(stream)
            columns = next(reader)
            rows = sum(1 for _ in reader)
        assert rows > 0 and "time_s" in columns
        if profile == "reservoir":
            command("handoff", profile, "--sample-index", "0", "--output", "state.json")
            sample = json.loads((destination / "state.json").read_text())
            assert sample["state"]["schema"] == "ciw.state.v1"
            assert sample["state"]["provenance"]["semantics"] == "simulated"
            assert sample["state"]["uncertainty"] is None
            assert sample["source_result_id"] == inspected["result_id"]
        assert _snapshot(destination / profile) == before
        profiles[profile] = {"status": "LOCAL", "checks": len(inspected["checks"]),
                             "csv_rows": rows, "new_verification_occurrences": True,
                             "retained_bundle_unchanged": True}
        request["desired_observables"].append("turbulence")
        expanded_name = profile + "-expand"
        (destination / (expanded_name + ".json")).write_text(json.dumps(request), encoding="utf-8")
        assert command("run", "--request", expanded_name + ".json", "--output-dir", expanded_name,
                       expected=2)["status"] == "EXPAND"
        assert command("export-csv", expanded_name, "--output", "blocked-" + profile + ".csv",
                       expected=1)["status"] == "REFUSE"
        assert not (destination / ("blocked-" + profile + ".csv")).exists()
    summary = {"status": "PASS", "profiles": profiles, "unsupported_request_action": "EXPAND",
               "export_gate": "fresh_LOCAL_only", "physical_validation": "not_established",
               "state_admission": "not_performed"}
    (destination / "qualification.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--net", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(qualify(arguments.net, arguments.output_dir), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
