"""Exercise the installed atmospheric CLI outside the source checkout.

This is a command-lifecycle qualification, not experimental weather validation.
Retained bundles must stay unchanged during inspection, verification and export.
"""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path
import subprocess


def _snapshot(directory: Path) -> dict[str, str]:
    return {str(path.relative_to(directory)): sha256(path.read_bytes()).hexdigest()
            for path in sorted(directory.rglob("*")) if path.is_file()}


def qualify(executable: Path, destination: Path) -> dict:
    executable = executable.resolve(strict=True)
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=False)

    def command(*arguments: str, expected: int = 0) -> dict:
        result = subprocess.run([str(executable), "atmosphere", *arguments], cwd=destination,
                                text=True, capture_output=True, check=False)
        if result.returncode != expected:
            raise AssertionError(f"atmosphere {arguments[0]} returned {result.returncode}: "
                                 f"{result.stderr or result.stdout}")
        return json.loads(result.stdout if expected != 1 else result.stderr)

    command("example", "--output", "request.json")
    request = json.loads((destination / "request.json").read_text(encoding="utf-8"))
    result = command("run", "request.json", "--output-dir", "column")
    assert result["status"] == "LOCAL"
    before = _snapshot(destination / "column")
    inspected = command("inspect", "column")
    verified = command("verify", "column")
    assert inspected["status"] == verified["status"] == "LOCAL"
    assert inspected["fresh_numerical_verification"] is False
    assert verified["fresh_numerical_verification"] is True
    command("export", "column", "--output", "column.csv")
    with (destination / "column.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    assert len(rows) == len(request["sampling"]["height_m"]) + 1
    assert all(len(row) == 11 for row in rows)
    assert rows[0][:4] == ["height_m", "temperature_k", "pressure_pa", "density_kg_per_m3"]
    assert float(rows[1][1]) == 288.15 and float(rows[1][2]) == 101325.0
    assert abs(float(rows[1][3]) - 1.225) < 0.0001
    handoffs = {}
    sample = len(request["sampling"]["height_m"]) // 2
    for provider in ("impact", "fluid", "render"):
        exported = command("handoff", "column", "--sample-index", str(sample),
                           "--provider", provider, "--output", f"{provider}.json")
        payload = json.loads((destination / f"{provider}.json").read_text(encoding="utf-8"))
        assert payload["schema"] == "ciw.atmosphere-handoff.v1"
        assert payload["provider"] == provider and payload["sample_index"] == sample
        assert payload["source_result_id"] == inspected["result_id"]
        assert payload["source_execution_id"] == inspected["execution_id"]
        assert payload["verification_id"] == inspected["verification_id"]
        assert payload["recomputed_report_digest"] == verified["recomputed_report_digest"]
        handoffs[provider] = payload["record_digest"]
        assert exported["status"] == "exported"
    assert before == _snapshot(destination / "column")

    isothermal = json.loads(json.dumps(request))
    isothermal["profile"]["lapse_rate_k_per_m"] = 0.0
    (destination / "isothermal.json").write_text(json.dumps(isothermal), encoding="utf-8")
    assert command("run", "isothermal.json", "--output-dir", "isothermal")["status"] == "LOCAL"
    isothermal_before = _snapshot(destination / "isothermal")
    assert command("verify", "isothermal")["status"] == "LOCAL"
    assert isothermal_before == _snapshot(destination / "isothermal")

    expansion = json.loads(json.dumps(request))
    expansion["desired_observables"].append("humidity")
    (destination / "expansion.json").write_text(json.dumps(expansion), encoding="utf-8")
    assert command("run", "expansion.json", "--output-dir", "expansion", expected=2)["status"] == "EXPAND"
    expansion_before = _snapshot(destination / "expansion")
    assert command("verify", "expansion", expected=2)["status"] == "EXPAND"
    assert command("export", "expansion", "--output", "blocked.csv", expected=1)["status"] == "REFUSE"
    assert not (destination / "blocked.csv").exists()
    assert expansion_before == _snapshot(destination / "expansion")
    qualification = {"status": "PASS", "profiles": ["linear_lapse", "isothermal"],
                     "checks": len(inspected["checks"]), "csv_samples": len(rows) - 1,
                     "handoffs": handoffs, "unsupported_observable_action": "EXPAND",
                     "retained_bundles_unchanged": True, "physical_validation": "not_established"}
    (destination / "qualification.json").write_text(json.dumps(qualification, indent=2), encoding="utf-8")
    return qualification


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--net", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(qualify(args.net, args.output_dir), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
