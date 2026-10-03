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

    command("moist", "example", "--output", "moist-request.json")
    moist_request = json.loads((destination / "moist-request.json").read_text(encoding="utf-8"))
    moist = command("moist", "run", "moist-request.json", "--output-dir", "moist-column")
    assert moist["status"] == "LOCAL" and moist["operation_id"] == "atmosphere.moist-compile.v1"
    moist_before = _snapshot(destination / "moist-column")
    moist_checked = command("moist", "verify", "moist-column")
    assert moist_checked["status"] == "LOCAL" and moist_checked["fresh_numerical_verification"] is True
    command("moist", "export", "moist-column", "--output", "moist-column.csv")
    with (destination / "moist-column.csv").open(encoding="utf-8", newline="") as stream:
        moist_rows = list(csv.DictReader(stream))
    assert len(moist_rows) == len(moist_request["sampling"]["height_m"])
    assert len(moist_rows[0]) == 16 and float(moist_rows[0]["temperature_k"]) == 298.15
    assert 0.0 < float(moist_rows[0]["relative_humidity"]) < 0.95
    assert "dynamic_viscosity_pa_s" not in moist_rows[0]
    moist_handoffs = {}
    for provider in ("impact", "fluid", "render"):
        command("moist", "handoff", "moist-column", "--sample-index", "2",
                "--provider", provider, "--output", f"moist-{provider}.json")
        payload = json.loads((destination / f"moist-{provider}.json").read_text(encoding="utf-8"))
        assert payload["schema"] == "ciw.atmosphere-moist-handoff.v1"
        assert payload["source_result_id"] == moist["result_id"]
        assert payload["recomputed_report_digest"] == moist_checked["recomputed_report_digest"]
        assert not any("viscosity" in name for name in payload["environment"])
        moist_handoffs[provider] = payload["record_digest"]
    assert moist_before == _snapshot(destination / "moist-column")

    for name, modification in (("moist-isothermal", ("lapse_rate_k_per_m", 0.0)),
                               ("moist-dry-limit", ("water_mixing_ratio_kg_per_kg_dry_air", 0.0))):
        variant = json.loads(json.dumps(moist_request))
        variant["profile"][modification[0]] = modification[1]
        (destination / f"{name}.json").write_text(json.dumps(variant), encoding="utf-8")
        assert command("moist", "run", f"{name}.json", "--output-dir", name)["status"] == "LOCAL"
        variant_before = _snapshot(destination / name)
        assert command("moist", "verify", name)["status"] == "LOCAL"
        command("moist", "export", name, "--output", f"{name}.csv")
        if name == "moist-dry-limit":
            with (destination / f"{name}.csv").open(encoding="utf-8", newline="") as stream:
                dry_rows = list(csv.DictReader(stream))
            assert all(row["liquid_equilibrium_dew_point_k"] == "" for row in dry_rows)
            assert all(float(row["relative_humidity"]) == 0.0 for row in dry_rows)
        assert variant_before == _snapshot(destination / name)

    for name, expected_action in (("moist-transport", "EXPAND"), ("moist-saturation", "REFUSE")):
        variant = json.loads(json.dumps(moist_request))
        if expected_action == "EXPAND":
            variant["desired_observables"].append("viscosity")
        else:
            variant["reference"]["temperature_k"] = 293.15
            variant["reference"]["pressure_pa"] = 110000.0
            variant["profile"]["water_mixing_ratio_kg_per_kg_dry_air"] = 0.02
            variant["sampling"]["height_m"] = [0.0, 1000.0, 2000.0]
            variant["desired_observables"].append("clouds")
        (destination / f"{name}.json").write_text(json.dumps(variant), encoding="utf-8")
        assert command("moist", "run", f"{name}.json", "--output-dir", name, expected=2)["status"] == expected_action
        variant_before = _snapshot(destination / name)
        assert command("moist", "verify", name, expected=2)["status"] == expected_action
        assert command("moist", "export", name, "--output", f"{name}-blocked.csv", expected=1)["status"] == "REFUSE"
        assert command("moist", "handoff", name, "--sample-index", "0", "--provider", "impact",
                       "--output", f"{name}-blocked.json", expected=1)["status"] == "REFUSE"
        assert not (destination / f"{name}-blocked.csv").exists()
        assert not (destination / f"{name}-blocked.json").exists()
        assert variant_before == _snapshot(destination / name)
    qualification = {"status": "PASS", "profiles": ["linear_lapse", "isothermal"],
                     "checks": len(inspected["checks"]), "csv_samples": len(rows) - 1,
                     "handoffs": handoffs, "unsupported_observable_action": "EXPAND",
                     "moist_profiles": ["linear_lapse", "isothermal", "dry_limit"],
                     "moist_checks": len(moist["checks"]), "moist_handoffs": moist_handoffs,
                     "moist_transport_action": "EXPAND", "moist_saturation_action": "REFUSE",
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
