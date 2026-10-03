#!/usr/bin/env python3
"""Run the synthetic, provider-free encoder correction through Session requests."""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ciw.instruments import make_demo_run
from ciw.session import Session, read_json, write_json


def run(output_dir: Path) -> dict:
    if output_dir.exists():
        raise ValueError("Use a new output directory to preserve prior investigations")
    fixture_dir = ROOT / "examples" / "corrections"
    raw_original = (fixture_dir / "encoder-original.json").read_bytes()
    raw_corrected = (fixture_dir / "encoder-corrected.json").read_bytes()
    reference = read_json(fixture_dir / "encoder-reference.json")
    # CIW keeps its existing recording shell. The encoder sources/results are
    # native Workbench artifacts, not coerced into that oscillator recording.
    session = Session(make_demo_run(), output_dir)

    def call(request_type, **payload):
        response = session.handle({"protocol_version": 1, "request_id": "demo-" + request_type,
                                   "type": request_type, "payload": payload})
        if response["type"] != "response":
            raise ValueError(str(response))
        return response["payload"]

    def source(raw, label):
        return call("source.add", kind="machine-manifest", label=label,
                    bytes_b64=base64.b64encode(raw).decode())["source_id"]

    def execute(source_id):
        summary = call("operation.execute", operation_id="ciw.encoder-position.v1",
                       parameters={"source_id": source_id})
        bundle = call("bundle.get", bundle_id=summary["bundle_id"])
        return summary, bundle

    old_source = source(raw_original, "Synthetic original offset")
    reference_source = call("source.add", kind="reference-evidence", label="Withheld synthetic position reference",
                            bytes_b64=base64.b64encode((fixture_dir / "encoder-reference.json").read_bytes()).decode())["source_id"]
    old_summary, old_bundle = execute(old_source)
    original_artifacts = deepcopy(session.workbench.serialize())
    old_step = old_bundle["steps"][0]
    old_position = old_step["result"]["data"]["position"]["position"]
    residual_before = old_position - reference["value"]
    assert abs(residual_before) > reference["context"]["residual_bound_m"]
    first = call("claim.add", claim_type="predicted", predicate="Carriage position at 300 decoded counts",
                 scope="Synthetic declared encoder/gearbox/leadscrew model; no physical acquisition",
                 basis="ciw.encoder-position.v1 result under the original homing offset",
                 dependencies=[old_step["result_id"]])
    downstream = call("claim.add", claim_type="estimated", predicate="Position residual exceeds the fixture bound",
                      scope="One withheld synthetic point; bound is a diagnostic threshold",
                      basis="Original prediction compared with retained encoder-reference.json",
                      dependencies=[first["claim_id"], old_source, reference_source])
    new_source = source(raw_corrected, "Synthetic corrected offset")
    proposal = call("correction.propose", old_source_id=old_source, new_source_id=new_source,
                    kind="calibration", reason="Synthetic homing-offset correction after a 3 mm residual over a 0.5 mm bound")
    pending = call("dependency.inspect")
    assert pending["artifact_status"][old_step["result_id"]]["status"] == "current"
    call("correction.review", correction_id=proposal["correction_id"], decision="accept",
         expected_revision=pending["revision"], reviewer="synthetic-demo-operator",
         reason="Accept for local dependency re-evaluation only; no physical or canonical-state admission")
    reviewed = call("dependency.inspect")
    for identity in (old_source, old_summary["bundle_id"], old_step["execution_id"],
                     old_step["result_id"], first["claim_id"], downstream["claim_id"]):
        assert reviewed["artifact_status"][identity]["status"] == "stale"
    new_summary, new_bundle = execute(new_source)
    new_step = new_bundle["steps"][0]
    new_position = new_step["result"]["data"]["position"]["position"]
    residual_after = new_position - reference["value"]
    assert abs(residual_after) <= reference["context"]["residual_bound_m"]
    assert new_step["execution_id"] != old_step["execution_id"]
    assert new_step["result_id"] != old_step["result_id"]
    assert call("bundle.get", bundle_id=old_summary["bundle_id"]) == old_bundle
    # A historical re-execution remains inspectable, and cannot clear stale status.
    historical, _ = execute(old_source)
    final = call("dependency.inspect")
    assert final["artifact_status"][historical["result_ids"][0]]["status"] == "stale"
    assert final["artifact_status"][new_step["result_id"]]["status"] == "current"
    for retained in original_artifacts["sources"]:
        assert session.workbench.get_source(retained["source_id"]) == retained
    assert old_bundle["verification"]["authority"] == new_bundle["verification"]["authority"]
    workspace = session.save_workspace(output_dir / "workspace.json")
    write_json(output_dir / "correction-journal.json", session.correction_journal.serialize())
    # The original fixtures and held-out reference travel with the review bundle.
    for name in ("encoder-original.json", "encoder-corrected.json", "encoder-reference.json"):
        (output_dir / name).write_bytes((fixture_dir / name).read_bytes())
    before_bytes = workspace.read_bytes()
    reopened = Session.from_workspace(workspace, output_dir / "reopened")
    assert reopened.workbench.serialize() == session.workbench.serialize()
    assert reopened.correction_journal.serialize() == session.correction_journal.serialize()
    assert reopened.dependency_status() == final
    assert workspace.read_bytes() == before_bytes
    report = {
        "schema": "ciw.correction-loop-report.v1", "status": "passed",
        "origin": "synthetic_fixture", "reference": reference,
        "workspace_sha256": hashlib.sha256(before_bytes).hexdigest(),
        "source_sha256": {name: hashlib.sha256((fixture_dir / name).read_bytes()).hexdigest()
                          for name in ("encoder-original.json", "encoder-corrected.json", "encoder-reference.json")},
        "original": old_summary, "corrected": new_summary, "historical_reexecution": historical,
        "correction_id": proposal["correction_id"], "reference_source_id": reference_source,
        "positions_m": {"original": old_position, "corrected": new_position,
                        "reference": reference["value"]},
        "residuals_m": {"before": residual_before, "after": residual_after},
        "checks": {"proposal_inert": True, "transitive_staleness": True,
                   "fresh_execution_and_result": True, "old_artifacts_preserved": True,
                   "historical_reexecution_stays_stale": True, "exact_offline_restore": True},
        "physical_validation": "not_performed", "state_admission": "not_performed",
        "hardware_actuation": "not_performed", "verification_status": "not_verified",
    }
    write_json(output_dir / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.output_dir)
    print(f"{report['status']}: {report['residuals_m']}; workspace: {args.output_dir / 'workspace.json'}")
