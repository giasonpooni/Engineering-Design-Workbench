"""Execute the existing synthetic thermal reference, export observations and compare replay.

Run against an installed candidate NET package with an explicit source file and
new output directory. No Julia, hardware or new estimator is introduced.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ciw import scientific
from ciw.control_contracts import bytes_ref, save_new
from ciw.control_checks import compare
from ciw.instruments import make_demo_run
from ciw.scientific_observations import export_observations, match_workspace
from ciw.session import Session


def run(source: Path, output: Path) -> dict:
    raw = scientific.read_source(source)
    scientific.source_payload("thermal-observer", raw, "declared synthetic thermal case")
    output.mkdir(parents=True, exist_ok=False)
    session = Session(make_demo_run(), output / "original")
    selected = scientific.execute(session, "thermal-observer", raw, label="declared synthetic thermal case")
    workspace = session.save_workspace(output / "original/workspace.json")
    digest = bytes_ref(workspace.read_bytes())
    views = {}
    for stage in ("predicted", "posterior", "measurement"):
        value = export_observations(workspace, expected_sha256=digest,
            bundle_id=selected["bundle_id"], stage=stage, entity_id="demo/core-shell")
        save_new(output / (stage + ".json"), value)
        match_workspace(value, workspace)
        views[stage] = value
    with scientific.open_workspace(workspace, output / "replay", expected_sha256=digest) as restored:
        replay = scientific.replay(restored, selected["bundle_id"], repositories={})
    replay_path = output / "replay/workspace.json"
    replay_digest = bytes_ref(replay_path.read_bytes())
    replayed = export_observations(replay_path, expected_sha256=replay_digest,
        bundle_id=replay["bundle"]["bundle_id"], stage="posterior", entity_id="demo/core-shell")
    save_new(output / "replayed-posterior.json", replayed)
    original_step, fresh_step = views["posterior"]["native_step"], replayed["native_step"]
    if original_step["execution_id"] == fresh_step["execution_id"]:
        raise ValueError("Replay must retain a fresh execution occurrence")
    checks = {}
    for label, left, right, atol in (
        ("replay-comparison", views["posterior"], replayed, 0.),
        ("measurement-comparison", views["posterior"], views["measurement"], 1.),
        ("prediction-comparison", views["posterior"], views["predicted"], 0.),
    ):
        result = compare(left["stream"]["observations"], right["stream"]["observations"], atol=atol)
        save_new(output / (label + ".json"), result)
        checks[label] = result["outcome"]
    if checks["replay-comparison"]["status"] != "PASS":
        raise ValueError("Existing same-runtime replay did not match its original posterior")
    report = {"status": "completed", "scope": "synthetic_python_reference_and_retained_projection_only",
        "source_sha256": bytes_ref(raw), "workspace_sha256": digest, "replay_workspace_sha256": replay_digest,
        "source_bundle_id": selected["bundle_id"], "replayed_bundle_id": replay["bundle"]["bundle_id"],
        "original_execution_id": original_step["execution_id"], "replay_execution_id": fresh_step["execution_id"],
        "samples": len(views["posterior"]["stream"]["observations"]), "checks": checks,
        "physical_validation": "not_established", "state_admission": "not_performed"}
    save_new(output / "demo-report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.source, args.output_dir), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
