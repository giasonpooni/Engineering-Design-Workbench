"""Qualify the pipeline with real game-owned Foundry execution and offline reinspection.

Operator-supplied Godot only. No model, fake native worker, checkout mutation or
human approval is claimed. Candidate/review fixtures are explicitly authored.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from unittest.mock import patch
import uuid

from ciw import foundry_pipeline as pipeline, foundry_packets as packets
from ciw.control_contracts import bytes_ref, load, save_new


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--godot", required=True, type=Path)
    ap.add_argument("--game-root", required=True, type=Path)
    ap.add_argument("--output-dir", required=True, type=Path)
    args = ap.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    original = packets.inventory(args.game_root)
    project = pipeline.create_project("1792-production-qualification", args.game_root, args.output_dir / "project")
    observations = []
    def check(condition: bool, label: str):
        if not condition:
            raise RuntimeError(label)
        observations.append({"check": label, "status": "PASS"})
    initial = pipeline.assess(project, args.game_root)
    check(initial["metrics"]["unresolved_tasks"] == 60, "planning starts with no invented completed tasks")
    executable_id = bytes_ref(args.godot.read_bytes())
    campaigns = {}
    for name, trips, repair, expected in (("baseline", 2, False, "completed"), ("repair", 1, True, "completed"), ("exhausted", 1, False, "incomplete")):
        path = args.output_dir / name
        r = pipeline.run_task(project, "water-domain", args.game_root, args.godot, executable_id, path,
                              candidate_trips=trips, repair=repair)
        check(r["status"] == expected, name+" original production disposition")
        campaigns[name] = r
    retained = {p.relative_to(args.output_dir).as_posix(): p.read_bytes() for p in args.output_dir.rglob("*") if p.is_file()}
    with patch("subprocess.Popen", side_effect=AssertionError("offline status launched a process")):
        baseline = pipeline.assess(project, args.game_root, {"water-domain": args.output_dir / "baseline"})
        repaired = pipeline.assess(project, args.game_root, {"water-domain": args.output_dir / "repair"})
        exhausted = pipeline.assess(project, args.game_root, {"water-domain": args.output_dir / "exhausted"})
        check(baseline["metrics"]["machine_checked_tasks"] == repaired["metrics"]["machine_checked_tasks"] == 1,
              "only the bound water task advances after both original jobs pass")
        check(repaired["metrics"]["native_attempts"] == 3 and repaired["metrics"]["rejected_native_attempts"] == 1,
              "rejected candidate retained before declared correction and regression")
        check(exhausted["tasks"]["water-domain"]["status"] == "not_accepted", "exhausted correction cannot satisfy production prerequisite")
        check(exhausted["metrics"]["machine_checked_tasks"] == 0, "failed native evidence contributes no accepted task")
        check(all(r["tasks"]["release-signoff"]["status"] == "blocked" and not r["release_authorized"] for r in (baseline, repaired, exhausted)),
              "domain success is not vertical-slice or release completion")
        for p, raw in retained.items():
            check((args.output_dir / p).read_bytes() == raw, "offline byte preservation: "+p)
    # Bounded external-agent candidate. Explicit deterministic fixture, not an LLM call.
    task = pipeline.task_for(project, "vision")
    packet = packets.make_packet(project, task, args.game_root, writable=["docs/generated-production-note.md"],
                                  context=["territory/water_round_rules.gd"], assignee="fixture-external-host")
    save_new(args.output_dir / "agent-packet.json", packet)
    with tempfile.TemporaryDirectory(prefix="net-pipeline-candidate-") as directory:
        root = Path(directory)
        candidate = root / "candidate"
        shutil.copytree(args.game_root, candidate, ignore=shutil.ignore_patterns(*packets.IGNORED))
        p = candidate / "docs/generated-production-note.md"; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# Explicit candidate fixture\nNot a historical source or a completed design review.\n", encoding="utf-8")
        with patch("subprocess.Popen", side_effect=AssertionError("scope check executed code")):
            scope = packets.check_candidate(packet, project, task, candidate, expected_packet_id=packet["record_digest"])
        check(scope["status"] == "scope_passed" and scope["quality_acceptance"] == "not_performed", "bounded candidate passes scope but gains no quality approval")
        save_new(args.output_dir / "candidate-scope.json", scope)
        (candidate / "tests/aftermath_fixture.gd").write_text("# forbidden original-test replacement\n", encoding="utf-8")
        refused = packets.check_candidate(packet, project, task, candidate, expected_packet_id=packet["record_digest"])
        check(refused["status"] == "scope_refused", "editing original checks is refused")
        save_new(args.output_dir / "candidate-refusal.json", refused)
        # Restore that forbidden edit, then demonstrate impact without executing changed code.
        shutil.copyfile(args.game_root / "tests/aftermath_fixture.gd", candidate / "tests/aftermath_fixture.gd")
        changed = candidate / "territory/water_round_rules.gd"
        changed.write_bytes(changed.read_bytes()+b"\n# explicit source-drift fixture\n")
        impact = pipeline.impact(project, candidate)
        check("water-domain" in impact["direct_tasks"] and "release-signoff" in impact["affected_tasks"], "source drift propagates to dependent production work")
        report = pipeline.assess(project, candidate, {"water-domain": args.output_dir / "repair"})
        check(report["tasks"]["water-domain"]["status"] == "stale", "old native success not promoted against changed inputs")
        save_new(args.output_dir / "source-impact.json", impact)
    try:
        pipeline.run_task(project, "water-domain", args.game_root, args.godot, executable_id, args.output_dir / "over-budget", max_operations=1)
    except ValueError:
        check(not (args.output_dir / "over-budget").exists(), "budget refusal precedes native dispatch and destination creation")
    else:
        raise RuntimeError("operation budget not enforced")
    check(packets.inventory(args.game_root) == original, "game-owned source remains unchanged")
    save_new(args.output_dir / "status.json", repaired)
    (args.output_dir / "PRODUCTION_ROADMAP.md").write_text(pipeline.markdown_report(project, repaired), encoding="utf-8")
    record = {"schema": "ciw.foundry-pipeline-qualification.v1", "operation_id": "foundry-pipeline-native-qualification.v1",
        "execution_id": uuid.uuid4().hex, "verification_method": "original-native-gates-plus-explicit-boundary-assertions",
        "godot_sha256": executable_id, "project_digest": project["record_digest"],
        "native_attempts": sum(load(args.output_dir / n / "production/production.json")["attempt_count"] for n in campaigns),
        "native_campaigns": campaigns, "checks": observations, "fresh_native_execution": True,
        "model_calls": 0, "human_playtests": 0, "release_authorized": False,
        "scope": "pipeline and existing water-domain workload; no visual, historical or whole-game qualification"}
    save_new(args.output_dir / "qualification.json", record)
    print(f"FOUNDRY_PIPELINE_CHECKS: {len(observations)} passed; 0 failed; {record['native_attempts']} native attempts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
