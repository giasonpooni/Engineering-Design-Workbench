"""Qualify the installed atmospheric reference CLI outside its source checkout.

Published-reference comparisons check four points and declared acceptance
bands. They do not establish atmospheric measurement or physical validation.
"""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import subprocess


def _snapshot(directory: Path) -> dict[str, str]:
    return {str(path.relative_to(directory)): sha256(path.read_bytes()).hexdigest()
            for path in sorted(directory.rglob("*")) if path.is_file()}


def qualify(executable: Path, destination: Path) -> dict:
    executable = executable.resolve(strict=True)
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    python = executable.parent / ("python.exe" if os.name == "nt" else "python")
    if not python.is_file():
        raise ValueError("The installed net command requires its adjacent environment interpreter")

    def command(*arguments: str, expected: int = 0) -> dict:
        result = subprocess.run([str(executable), "atmosphere", *arguments], cwd=destination,
                                text=True, capture_output=True, check=False, timeout=30)
        if result.returncode != expected:
            raise AssertionError(f"atmosphere {' '.join(arguments)} returned {result.returncode}: "
                                 f"{result.stderr or result.stdout}")
        return json.loads(result.stderr if expected == 1 else result.stdout)

    def reseal(path: Path) -> None:
        # This imports the installed runner from the installed interpreter;
        # command execution remains outside the checkout throughout.
        program = ("import json,sys; from pathlib import Path; "
                   "from ciw.operations.runner import seal; "
                   "p=Path(sys.argv[1]); d=json.loads(p.read_text(encoding='utf-8')); "
                   "seal(d); p.write_text(json.dumps(d,indent=2),encoding='utf-8')")
        subprocess.run([str(python), "-c", program, str(path)], cwd=destination,
                       text=True, capture_output=True, check=True, timeout=30)

    profiles = {}
    for profile in ("dry", "moist"):
        prefix = () if profile == "dry" else ("moist",)
        request_file = f"{profile}-request.json"
        original_name = f"{profile}-atmosphere"
        comparison_name = f"{profile}-comparison"
        command(*prefix, "example", "--output", request_file)
        original = command(*prefix, "run", request_file, "--output-dir", original_name)
        assert original["status"] == "LOCAL"
        original_before = _snapshot(destination / original_name)
        reference_file, policy_file = f"{profile}-reference.json", f"{profile}-policy.json"
        command("compare", "example", "--profile", profile,
                "--reference-output", reference_file, "--policy-output", policy_file)
        reference = json.loads((destination / reference_file).read_text(encoding="utf-8"))
        assert reference["provenance"]["kind"] == "synthetic_fixture"
        assert reference["provenance"]["independent_of_candidate"] is False
        compared = command("compare", "run", original_name, "--reference", reference_file,
                           "--policy", policy_file, "--output-dir", comparison_name)
        assert compared["status"] == "LOCAL" and compared["agreement_status"] == "PASS"
        before = _snapshot(destination / comparison_name)
        inspected = command("compare", "inspect", comparison_name)
        verified = command("compare", "verify", comparison_name)
        assert inspected["fresh_numerical_verification"] is False
        assert verified["fresh_numerical_verification"] is True
        assert inspected["agreement_status"] == verified["agreement_status"] == "PASS"
        for format in ("json", "csv"):
            exported = command("compare", "export", comparison_name, "--format", format,
                               "--output", f"{profile}-comparison.{format}")
            assert exported["status"] == "exported"
        payload = json.loads((destination / f"{profile}-comparison.json").read_text(encoding="utf-8"))
        assert payload["comparison"]["agreement_status"] == "PASS"
        assert payload["comparison"]["claims"]["physical_validation"] == "not_established"
        assert payload["comparison"]["claims"]["calibration_validation"] is False
        assert payload["verification"]["report"]["status"] == "PASS"
        with (destination / f"{profile}-comparison.csv").open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        assert len(rows) == 2 and {row["field"] for row in rows} == {"temperature_k", "pressure_pa"}
        assert all(row["status"] == "PASS" for row in rows)
        assert _snapshot(destination / comparison_name) == before

        # A reference disagreement is a valid, exportable diagnostic result.
        reference["observations"][0]["quantities"]["temperature_k"]["value"] += 5.0
        failed_reference = destination / f"{profile}-disagreement-reference.json"
        failed_reference.write_text(json.dumps(reference), encoding="utf-8")
        reseal(failed_reference)
        failed_name = f"{profile}-disagreement"
        failed = command("compare", "run", original_name, "--reference", failed_reference.name,
                         "--policy", policy_file, "--output-dir", failed_name, expected=2)
        assert failed["status"] == "LOCAL" and failed["agreement_status"] == "FAIL"
        failed_before = _snapshot(destination / failed_name)
        assert command("compare", "inspect", failed_name, expected=2)["status"] == "LOCAL"
        assert command("compare", "verify", failed_name, expected=2)["verification_status"] == "PASS"
        for format in ("json", "csv"):
            exported = command("compare", "export", failed_name, "--format", format,
                               "--output", f"{profile}-disagreement.{format}", expected=2)
            assert exported["status"] == "exported"
        assert _snapshot(destination / failed_name) == failed_before

        # Alignment and absent conventions are qualified decisions rather than
        # successful comparisons or permission to invent missing quantities.
        aligned_reference = json.loads((destination / reference_file).read_text(encoding="utf-8"))
        misaligned_reference = json.loads(json.dumps(aligned_reference))
        misaligned_reference["context"]["height_origin_m"] += 1.0
        misaligned_path = destination / f"{profile}-misaligned-reference.json"
        misaligned_path.write_text(json.dumps(misaligned_reference), encoding="utf-8")
        reseal(misaligned_path)
        misaligned_name = f"{profile}-misaligned"
        refused = command("compare", "run", original_name, "--reference", misaligned_path.name,
                          "--policy", policy_file, "--output-dir", misaligned_name, expected=2)
        assert refused["status"] == "REFUSE"
        assert command("compare", "verify", misaligned_name, expected=2)["verification_status"] == "PASS"
        command("compare", "export", misaligned_name, "--output", f"{profile}-misaligned-blocked.json",
                expected=1)
        assert not (destination / f"{profile}-misaligned-blocked.json").exists()

        unsupported_reference = json.loads(json.dumps(aligned_reference))
        unsupported_reference["context"]["humidity_convention"] = "pressure_enhanced_relative_humidity"
        unsupported_reference["observations"][0]["quantities"] = {
            "relative_humidity": {"value": 0.5, "unit": "1",
                "uncertainty": {"kind": "exact_fixture", "absolute_bound": 0.0,
                                "coverage_factor": None, "reference": "Synthetic convention boundary."},
                "instrument_ref": None, "calibration_ref": None}}
        unsupported_path = destination / f"{profile}-unsupported-reference.json"
        unsupported_path.write_text(json.dumps(unsupported_reference), encoding="utf-8")
        reseal(unsupported_path)
        unsupported_policy = json.loads((destination / policy_file).read_text(encoding="utf-8"))
        unsupported_policy["thresholds"] = {
            "relative_humidity": {"absolute_tolerance": 0.01, "relative_tolerance": 0.0}}
        unsupported_policy_path = destination / f"{profile}-unsupported-policy.json"
        unsupported_policy_path.write_text(json.dumps(unsupported_policy), encoding="utf-8")
        reseal(unsupported_policy_path)
        unsupported_name = f"{profile}-unsupported"
        expanded = command("compare", "run", original_name, "--reference", unsupported_path.name,
                           "--policy", unsupported_policy_path.name, "--output-dir", unsupported_name,
                           expected=2)
        assert expanded["status"] == "EXPAND"
        assert command("compare", "verify", unsupported_name, expected=2)["verification_status"] == "PASS"
        command("compare", "export", unsupported_name, "--output", f"{profile}-unsupported-blocked.json",
                expected=1)
        assert not (destination / f"{profile}-unsupported-blocked.json").exists()

        # Comparing references cannot confer physical validity on handoffs.
        command(*prefix, "handoff", original_name, "--sample-index", "0", "--provider", "impact",
                "--output", f"{profile}-impact.json")
        handoff = json.loads((destination / f"{profile}-impact.json").read_text(encoding="utf-8"))
        assert handoff["claims"]["physical_validation_established"] is False
        assert handoff["claims"]["receiver_model_validated"] is False
        assert _snapshot(destination / original_name) == original_before
        profiles[profile] = {"agreement": "PASS", "intentional_disagreement": "FAIL",
                             "disagreement_numerical_verification": "PASS",
                             "alignment_action": "REFUSE", "unsupported_quantity_or_convention_action": "EXPAND",
                             "original_bundle_unchanged": True, "comparison_bundles_unchanged": True}

    # File preflight must refuse untrusted input surfaces before JSON reading.
    regular_file_checks = ["directory", "oversize"]
    reference_directory = destination / "reference-directory"
    reference_directory.mkdir()
    oversize = destination / "reference-oversize.json"
    with oversize.open("wb") as stream:
        stream.truncate(8 * 1024 * 1024 + 1)
    unsafe = [reference_directory, oversize]
    link = destination / "reference-symlink.json"
    try:
        link.symlink_to(destination / "dry-reference.json")
    except (OSError, NotImplementedError):
        pass
    else:
        unsafe.append(link)
        regular_file_checks.append("symlink")
    if hasattr(os, "mkfifo"):
        fifo = destination / "reference-fifo.json"
        os.mkfifo(fifo)
        unsafe.append(fifo)
        regular_file_checks.append("fifo")
    try:
        for index, path in enumerate(unsafe):
            output_name = f"unsafe-{index}"
            refused = command("compare", "run", "dry-atmosphere", "--reference", path.name,
                              "--policy", "dry-policy.json", "--output-dir", output_name, expected=1)
            assert refused["status"] == "REFUSE" and not (destination / output_name).exists()
    finally:
        # Keep negative-test devices and links out of copied or uploaded artifacts.
        for path in unsafe:
            if path.is_symlink() or not path.is_dir():
                path.unlink(missing_ok=True)
            else:
                path.rmdir()

    # These references come from the published IAPWS-95 table, not the compiler.
    benchmark = command("compare", "benchmark", "--output-dir", "published-benchmark")
    assert benchmark["status"] == "LOCAL"
    benchmark_root = destination / "published-benchmark"
    benchmark_before = _snapshot(benchmark_root)
    inspected_benchmark = command("compare", "benchmark-inspect", "published-benchmark")
    verified_benchmark = command("compare", "benchmark-verify", "published-benchmark")
    assert inspected_benchmark["fresh_numerical_verification"] is False
    assert verified_benchmark["fresh_numerical_verification"] is True
    assert inspected_benchmark["case_count"] == verified_benchmark["case_count"] == 4
    assert {case["comparison_result_id"] for case in inspected_benchmark["cases"]} == {
        case["comparison_result_id"] for case in verified_benchmark["cases"]}
    comparison_directories = sorted(path.parent for path in benchmark_root.rglob("policy.json"))
    assert len(comparison_directories) == 4
    published_rows = []
    published_occurrences = set()
    for index, directory in enumerate(comparison_directories):
        relative = str(directory.relative_to(destination))
        inspected = command("compare", "inspect", relative)
        verified = command("compare", "verify", relative)
        assert inspected["agreement_status"] == verified["agreement_status"] == "PASS"
        assert inspected["fresh_numerical_verification"] is False
        assert verified["fresh_numerical_verification"] is True
        command("compare", "export", relative, "--format", "json", "--output", f"published-{index}.json")
        exported = json.loads((destination / f"published-{index}.json").read_text(encoding="utf-8"))
        assert exported["verification"]["report"]["status"] == "PASS"
        assert exported["comparison"]["claims"]["independence_established"] is False
        assert exported["comparison"]["claims"]["physical_validation"] == "not_established"
        published_rows.append(exported["comparison"]["rows"][0])
        workspace = json.loads((directory / "workspace.json").read_text(encoding="utf-8"))
        occurrences = {row["result_id"] for row in workspace["results"]}
        occurrences.update(row["execution_id"] for row in workspace["executions"])
        for result in workspace["results"]:
            if result["operation_id"] == "atmosphere.compare-verify.v1":
                occurrences.add(result["data"]["comparison_verification_id"])
            elif result["role"] == "verification":
                occurrences.add(result["data"]["verification_id"])
        assert len(occurrences) == 10 and published_occurrences.isdisjoint(occurrences)
        published_occurrences.update(occurrences)
    assert len(published_occurrences) == 40
    assert _snapshot(benchmark_root) == benchmark_before

    # Tight and wider policies belong to distinct comparisons; verification of
    # their arithmetic succeeds independently of scientific acceptance.
    first_comparison = comparison_directories[1]
    policy = json.loads((first_comparison / "policy.json").read_text(encoding="utf-8"))
    original_directory = first_comparison.parent / "atmosphere"
    if not original_directory.is_dir():
        original_directory = first_comparison.parent / "column"
    reference_file = first_comparison / "reference.json"
    policy_checks = {}
    for name, tolerance, expected in (("tight", 0.0, "FAIL"), ("wider", 0.005, "PASS")):
        policy["thresholds"]["liquid_water_saturation_pressure_pa"]["relative_tolerance"] = tolerance
        policy_path = destination / f"published-{name}-policy.json"
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        reseal(policy_path)
        directory_name = f"published-{name}"
        result = command("compare", "run", str(original_directory.relative_to(destination)),
                         "--reference", str(reference_file.relative_to(destination)),
                         "--policy", policy_path.name, "--output-dir", directory_name,
                         expected=2 if expected == "FAIL" else 0)
        assert result["status"] == "LOCAL" and result["agreement_status"] == expected
        before = _snapshot(destination / directory_name)
        checked = command("compare", "verify", directory_name, expected=2 if expected == "FAIL" else 0)
        assert checked["verification_status"] == "PASS"
        assert checked["agreement_status"] == expected
        assert _snapshot(destination / directory_name) == before
        policy_checks[name] = {"agreement": expected, "numerical_verification": "PASS"}

    assert all(stat.S_ISREG(path.lstat().st_mode) or stat.S_ISDIR(path.lstat().st_mode)
               for path in destination.rglob("*"))
    qualification = {"status": "PASS", "profiles": profiles,
                     "published_reference_points": len(published_rows),
                     "distinct_published_case_occurrences": len(published_occurrences),
                     "published_reference_acceptance": "four points within a declared 0.4% allowance plus 0.05 Pa rounding bound",
                     "policy_sensitivity": policy_checks, "regular_file_preflight": regular_file_checks,
                     "retained_bundles_unchanged": True, "artifact_tree_regular": True,
                     "physical_validation": "not_established"}
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
