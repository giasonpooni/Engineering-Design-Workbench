"""NET Game Foundry: compile a recipe, execute work orders, inspect and export.

Uses the existing production controller, Session, DAG, worker and gate registry.
There is no second scheduler, evidence store, game engine or release authority.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

from .control_contracts import bytes_ref, load, save_new
from .core.identities import content_identity
from .foundry_project import PROFILE, GodotProjectBinding, snapshot
from . import foundry_water as water
from .production import inspect_production, run_production
from .operations.runner import seal


def compile_order(game_root: Path, destination: Path, *, candidate_trips=1, repair=True) -> dict:
    lock, _ = snapshot(game_root)
    source = water.source(lock)
    specification = water.compile_plan(source, candidate_trips=candidate_trips, repair=repair)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    save_new(destination / "source-lock.json", lock)
    save_new(destination / "source.json", source)
    save_new(destination / "plan.json", specification)
    return {"status": "compiled", "profile": PROFILE, "source_lock_id": lock["source_lock_id"],
            "fresh_execution": False, "destination": str(destination)}


def run_order(order_dir: Path, game_root: Path, executable: Path, expected_sha256: str,
              destination: Path, *, max_operations=3) -> dict:
    source = load(Path(order_dir) / "source.json")
    specification = load(Path(order_dir) / "plan.json")
    lock = water.objective(source)["source_lock"]
    if load(Path(order_dir) / "source-lock.json") != lock:
        raise ValueError("Work order lock differs from its source evidence")
    binding = GodotProjectBinding(executable, game_root, expected_sha256=expected_sha256, source_lock=lock)
    return run_production(source, specification, water.registry(binding), water.WORKERS,
                          water.gates(), destination, max_operations=max_operations)


def inspect_order(destination: Path) -> dict:
    return inspect_production(destination, water.gates())


def _accepted_result(root: Path, inspection: dict, job_id: str):
    from .production import _read
    job = inspection["jobs"].get(job_id)
    if job is None or job["status"] != "accepted":
        raise ValueError("Only accepted work-order artifacts can be exported")
    ref = job["attempts"][-1]
    receipt = _read(root, ref["name"], ref)
    graph = _read(root, receipt["graph"]["name"], receipt["graph"])
    result = graph["nodes"]["candidate"]["result"]
    return receipt, result


def report_order(destination: Path) -> dict:
    """Derived counters, not a second mutable production/evidence ledger."""
    from .production import _read
    root = Path(destination)
    checked = inspect_order(root)
    attempts = []
    elapsed = 0.0
    for job_id, job in checked["jobs"].items():
        for ref in job["attempts"]:
            receipt = _read(root, ref["name"], ref)
            graph = _read(root, receipt["graph"]["name"], receipt["graph"])
            result = graph["nodes"]["candidate"].get("result")
            if result is not None:
                elapsed += result["data"]["elapsed_wall_s"]
            attempts.append({"job_id": job_id, "status": receipt["status"], "receipt_digest": receipt["record_digest"]})
    rejected = sum(a["status"] == "rejected" for a in attempts)
    return {"schema": "ciw.foundry-report.v1", "status": checked["status"], "integrity": checked["integrity"],
        "accepted_jobs": sum(j["status"] == "accepted" for j in checked["jobs"].values()),
        "blocked_jobs": sum(j["status"] == "blocked" for j in checked["jobs"].values()),
        "attempts": attempts, "rejected_attempts": rejected,
        "rejection_fraction": rejected / len(attempts) if attempts else None,
        "captured_native_wall_s": elapsed, "human_supervisory_hours": None,
        "model_token_cost": None, "playable_minutes": None,
        "fresh_execution": False, "scope": "derived_domain_production_counters_not_studio_productivity"}


def export_artifact(destination: Path, output_dir: Path, *, job_id="water-round") -> dict:
    root = Path(destination)
    checked = inspect_order(root)
    receipt, result = _accepted_result(root, checked, job_id)
    raw = result["data"]["source_utf8"].encode("utf-8")
    if bytes_ref(raw) != result["data"]["source_sha256"]:
        raise ValueError("Accepted source changed during export")
    manifest = seal({"schema": "ciw.foundry-export.v1", "job_id": job_id,
        "artifact": {"name": "water-round-observations.json", "sha256": bytes_ref(raw), "bytes": len(raw)},
        "source_result_id": result["result_id"], "source_execution_id": result["execution_id"],
        "source_record_digest": result["record_digest"], "acceptance_receipt_digest": receipt["record_digest"],
        "source_lock_id": result["data"]["request"]["source_lock_id"],
        "verification_id": None, "state_admission": "not_performed", "publication": "not_performed",
        "scope": "accepted_domain_observation_artifact_not_a_game_build_or_release"})
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    with (output_dir / manifest["artifact"]["name"]).open("xb") as stream:
        stream.write(raw)
    save_new(output_dir / "manifest.json", manifest)
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="net foundry", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    compile_cmd = commands.add_parser("compile", help="compile an installed recipe into locked, data-only work orders")
    compile_cmd.add_argument("profile", choices=[PROFILE])
    compile_cmd.add_argument("--game-root", type=Path, required=True)
    compile_cmd.add_argument("--output-dir", type=Path, required=True)
    compile_cmd.add_argument("--candidate-trips", type=int, choices=[1, 2], default=1)
    compile_cmd.add_argument("--no-repair", action="store_true")
    run = commands.add_parser("run", help="bind operator-selected Godot and execute the existing production controller")
    run.add_argument("order_dir", type=Path)
    run.add_argument("--game-root", type=Path, required=True)
    run.add_argument("--godot", type=Path, required=True)
    run.add_argument("--godot-sha256", required=True)
    run.add_argument("--max-operations", type=int, default=3)
    run.add_argument("--output-dir", type=Path, required=True)
    for name in ("inspect", "report", "export"):
        command = commands.add_parser(name)
        command.add_argument("output_dir", type=Path)
        if name == "export":
            command.add_argument("--destination", type=Path, required=True)
            command.add_argument("--job", default="water-round")
    args = parser.parse_args(argv)
    try:
        if args.command == "compile":
            report = compile_order(args.game_root, args.output_dir, candidate_trips=args.candidate_trips, repair=not args.no_repair)
        elif args.command == "run":
            report = run_order(args.order_dir, args.game_root, args.godot, args.godot_sha256, args.output_dir, max_operations=args.max_operations)
        elif args.command == "inspect":
            report = inspect_order(args.output_dir)
        elif args.command == "report":
            report = report_order(args.output_dir)
        else:
            report = export_artifact(args.output_dir, args.destination, job_id=args.job)
        print(json.dumps(report, indent=2, allow_nan=False))
        return 2 if report.get("status") == "incomplete" else 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
