"""Check the existing retained thermal demo with declared numerical policies.

Run run_thermal_observation_demo.py first. This script does not run an estimator.
It exercises PASS, FAIL and INDETERMINATE without treating challenge results as
physical validation, execution authority or a source signature.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from ciw.check_suite import plan, validate_report
from ciw.control_contracts import bytes_ref, load, save_new


def run(evidence: Path, output: Path) -> dict:
    paths = {name: evidence / file for name, file in {
        "posterior": "posterior.json", "measurement": "measurement.json",
        "replay": "replay-comparison.json", "prediction": "prediction-comparison.json",
    }.items()}
    raw = {alias: path.read_bytes() for alias, path in paths.items()}
    # Values here come from the existing demo. The check CLI validates them independently.
    posterior = json.loads(raw["posterior"])
    covariance = posterior["stream"]["observations"][0]["uncertainty"]
    bounded = {"minimum": 250., "maximum": 350., "unit": "K"}
    pd = {key: covariance[key] for key in ("quantity_ids", "units", "frame")}
    pd["margin"] = 1e-12
    def check(name, kind, alias, policy):
        return {"name": name, "kind": kind, "input": alias, "policy": policy}
    scenarios = {
        "accepted": ("PASS", [check("Posterior inside declared temperature bounds", "bounded", "posterior", bounded),
            check("Every posterior marginal is numerically PD", "covariance_positive_definite", "posterior", pd),
            check("Fresh replay matches retained original", "close_to", "replay", {})]),
        "incomplete": ("INDETERMINATE", [check("All supplied measurements inside bounds", "bounded", "measurement", bounded)]),
        "different": ("FAIL", [check("Prediction equals posterior at zero tolerance", "close_to", "prediction", {})]),
    }
    output.mkdir(parents=True, exist_ok=False)
    outcomes = {}
    for label, (expected, checks) in scenarios.items():
        aliases = sorted({check["input"] for check in checks})
        spec = plan("synthetic-thermal-" + label, inputs={alias: {
            "schema": json.loads(raw[alias])["schema"], "sha256": bytes_ref(raw[alias])} for alias in aliases}, checks=checks)
        config, destination = output / (label + "-plan.json"), output / (label + "-report.json")
        save_new(config, spec)
        command = [sys.executable, "-I", "-m", "ciw.net", "check", "--plan", str(config.resolve()),
                   "--output", str(destination.resolve()), "--json"]
        for alias in aliases:
            command.extend(["--input", alias + "=" + str(paths[alias].resolve())])
        result = subprocess.run(command, capture_output=True, text=True, timeout=45)
        if result.returncode != {"PASS": 0, "FAIL": 2, "INDETERMINATE": 3}[expected]:
            raise ValueError("Unexpected check CLI result: " + result.stderr[-2048:])
        report = load(destination)
        validate_report(report)
        if report["summary"]["status"] != expected:
            raise ValueError("Retained report disagrees with expected demonstration condition")
        outcomes[label] = report["summary"]
    summary = {"scope": "existing_synthetic_reference_checks_only", "outcomes": outcomes,
               "physical_validation": "not_established", "state_admission": "not_performed"}
    save_new(output / "demo-check-summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.evidence_dir, args.output_dir), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
