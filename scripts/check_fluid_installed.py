"""Exercise all installed fluid profiles, reductions and held-out comparison."""
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
    all_profiles = ("reservoir", "wave", "molecular", "sph", "fsi")
    expansion_observables = {"reservoir": "turbulence", "wave": "turbulence",
                             "molecular": "viscosity", "sph": "surface_gravity_wave", "fsi": "turbulence"}
    for profile in all_profiles:
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
        assert rows > 0
        if profile == "molecular":
            assert "time_reduced" in columns and "time_s" not in columns
            assert request["si_scaling"] is None
        else:
            assert "time_s" in columns
        if profile == "reservoir":
            command("handoff", profile, "--sample-index", "0", "--output", "state.json")
            sample = json.loads((destination / "state.json").read_text())
            assert sample["state"]["schema"] == "ciw.state.v1"
            assert sample["state"]["provenance"]["semantics"] == "simulated"
            assert sample["state"]["uncertainty"] is None
            assert sample["source_result_id"] == inspected["result_id"]
        reduction = None
        if profile in {"molecular", "sph"}:
            bins = ["2", "2", "2"] if profile == "molecular" else ["4"]
            reduction = command("reduce", profile, "--sample-index", "0", "--bins", *bins,
                                "--output", profile + "-reduction.json")
            assert reduction["status"] == "LOCAL"
            artifact = json.loads((destination / (profile + "-reduction.json")).read_text())
            assert artifact["schema"] == "ciw.fluid-retained-scale-map.v1"
            assert artifact["map_verification"]["status"] == "PASS"
            claims = artifact["map_verification"]["claims"]
            assert claims["constitutive_model_supplied"] is False
            assert claims["physical_validation_established"] is False
            assert claims["si_parameter_calibration_established"] is False
            assert claims["state_admission_performed"] is False
            assert artifact["snapshot"]["unit_system"] == ("reduced_lj" if profile == "molecular" else "SI")
            assert artifact["source_occurrences"]["result_id"] == inspected["result_id"]
        assert _snapshot(destination / profile) == before
        profiles[profile] = {"status": "LOCAL", "checks": len(inspected["checks"]),
                             "csv_rows": rows, "new_verification_occurrences": True,
                             "retained_bundle_unchanged": True,
                             "time_unit": "reduced_lj" if profile == "molecular" else "s",
                             "si_scaling_status": "not_declared" if profile == "molecular" else "declared_not_empirically_calibrated",
                             "instantaneous_conservative_reduction": reduction is not None}
        request["desired_observables"].append(expansion_observables[profile])
        expanded_name = profile + "-expand"
        (destination / (expanded_name + ".json")).write_text(json.dumps(request), encoding="utf-8")
        assert command("run", "--request", expanded_name + ".json", "--output-dir", expanded_name,
                       expected=2)["status"] == "EXPAND"
        assert command("export-csv", expanded_name, "--output", "blocked-" + profile + ".csv",
                       expected=1)["status"] == "REFUSE"
        assert not (destination / ("blocked-" + profile + ".csv")).exists()
    command("coupling", "template", "--output", "interface.json")
    interface_run = command("coupling", "run", "--request", "interface.json", "--output-dir", "interface")
    interface_before = _snapshot(destination / "interface")
    interface_inspected = command("coupling", "inspect", "interface")
    interface_verified = command("coupling", "verify", "interface", "--output", "interface-fresh.json")
    interface_verified_again = command("coupling", "verify", "interface")
    assert interface_run["status"] == interface_inspected["status"] == interface_verified["status"] == "LOCAL"
    assert interface_verified_again["status"] == "LOCAL"
    assert interface_inspected["fresh_numerical_verification"] is False
    assert interface_verified["fresh_numerical_verification"] is True
    assert interface_run["source_kind"] == "synthetic"
    assert interface_run["qualification"]["coupled_model_qualified"] is False
    assert interface_run["qualification"]["physical_validation_established"] is False
    assert interface_run["authority"]["receiving_solver_qualification"] == "required_separately"
    for key in ("coupled_model_qualification", "physical_measurement_validation"):
        assert interface_run["authority"][key] == "not_established"
    for key in ("solver_activation", "state_admission", "hardware_actuation"):
        assert interface_run["authority"][key] == "not_performed"
    for key in ("fresh_verification_id", "fresh_verification_execution_id", "fresh_verification_result_id"):
        assert interface_verified[key] != interface_verified_again[key]
    assert interface_verified["fresh_verification_id"] != interface_inspected["verification_id"]
    interface_witness = json.loads((destination / "interface-fresh.json").read_text())
    assert interface_witness["fresh_verification_record"]["verification_id"] == interface_verified["fresh_verification_id"]
    assert all(row["status"] == "PASS" for row in interface_verified["checks"])
    assert _snapshot(destination / "interface") == interface_before
    command("experiment", "template", "--profile", "reservoir", "--output", "experiment-template.json")
    template = json.loads((destination / "experiment-template.json").read_text())
    metadata = template["metadata"]
    with (destination / "reservoir.csv").open(newline="", encoding="utf-8") as stream:
        exported = list(csv.DictReader(stream))
    csv_path = destination / "synthetic-holdout.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(template["csv_header"])
        for index, source_index in enumerate((1, 3, 5)):
            row = exported[source_index]
            writer.writerow(["s" + str(index), row["time_s"], "holdout", row["head1_m"]])
    metadata["csv_sha256"] = "sha256:" + sha256(csv_path.read_bytes()).hexdigest()
    assert metadata["provenance"]["source_kind"] == "synthetic_fixture"
    (destination / "synthetic-metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    model_before = _snapshot(destination / "reservoir")
    command("experiment", "ingest", "--csv", "synthetic-holdout.csv", "--metadata", "synthetic-metadata.json",
            "--output-dir", "measurement")
    compared = command("experiment", "compare", "--model-dir", "reservoir", "--measurement-dir", "measurement",
                       "--output-dir", "comparison")
    comparison_before = _snapshot(destination / "comparison")
    experiment_inspected = command("experiment", "inspect", "comparison")
    experiment_verified = command("experiment", "verify", "comparison", "--output", "experiment-fresh-audit.json")
    assert compared["status"] == experiment_inspected["status"] == experiment_verified["status"] == "LOCAL"
    assert compared["outcome"] == "EMPIRICALLY_COMPATIBLE"
    assert compared["source_kind"] == "synthetic_fixture"
    assert compared["conditional_measured_support"] is False
    assert compared["authority"]["physical_validation"] == "not_established"
    assert _snapshot(destination / "reservoir") == model_before
    assert _snapshot(destination / "comparison") == comparison_before
    summary = {"status": "PASS", "profiles": profiles, "unsupported_request_action": "EXPAND",
               "export_gate": "fresh_LOCAL_only", "physical_validation": "not_established",
               "state_admission": "not_performed", "experiment": {
                   "status": "LOCAL", "outcome": "EMPIRICALLY_COMPATIBLE", "source_kind": "synthetic_fixture",
                   "conditional_measured_support": False, "model_and_comparison_bundles_unchanged": True},
               "coupling": {"status": "LOCAL", "scope": "finite_supplied_interface_algebra_only",
                            "new_verification_occurrences": True, "retained_bundle_unchanged": True,
                            "coupled_model_qualification": "not_established", "solver_activation": "not_performed"}}
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
