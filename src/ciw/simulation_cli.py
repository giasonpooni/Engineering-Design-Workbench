"""Run or inspect the bounded stateful-simulation reference experiment."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile

from .control_checks import compare
from .control_contracts import load, save_new
from .simulation_control import SimulationControl, completed, open_workspace
from .simulation_records import OPERATION, observer, projected_samples
from .simulation_reference import PROVIDER_ID, ReferenceMotion
from .simulation_replay import replay, validate_replay, validate_result


def demo(output_dir: Path) -> dict:
    from .instruments import make_demo_run
    from .session import Session
    output_dir.mkdir(parents=True, exist_ok=False)
    # Existing scientific recording remains intact and independent of the live
    # reference world. No motion observation is relabelled as oscillator evidence.
    session = Session(make_demo_run(), output_dir)
    control = SimulationControl(session)
    player = observer("player", kind="embodied_agent", channels=["position"])
    debugger = observer("debugger", kind="debugger", channels=["position", "velocity"])
    original = control.attach(ReferenceMotion(), provider_id=PROVIDER_ID, experiment_id="baseline")
    call = lambda action, **args: completed(original.command(action, **args))
    report = None
    try:
        call("start")
        call("step", dt=1)
        call("step", dt=1)
        call("intervene", actor_id="operator", operation="motion.queue-impulse.v1", target="body-1",
             parameters={"at_tick": 4, "delta_v": 3})
        call("pause")
        checkpoint = call("checkpoint")
        suffix = [call("resume")]
        suffix += [call("step", dt=1) for _ in range(4)]
        player_result = call("observe", observer=player)
        debug_result = call("observe", observer=debugger)
        suffix += [player_result, debug_result, call("pause")]
        parent_before = original.inspect()
        alternate, restored = control.branch(checkpoint, ReferenceMotion(), experiment_id="alternate")
        completed(restored)
        completed(alternate.command("intervene", actor_id="operator", operation="motion.queue-impulse.v1",
            target="body-1", parameters={"at_tick": 3, "delta_v": 2}))
        completed(alternate.command("resume"))
        for _ in range(4):
            completed(alternate.command("step", dt=1))
        alternative_result = completed(alternate.command("observe", observer=debugger))
        completed(alternate.command("pause"))
        _, replay_report = replay(control, checkpoint, suffix, ReferenceMotion(), experiment_id="reproduction")
        comparison = compare(projected_samples(debug_result, quantity="position"),
                             projected_samples(alternative_result, quantity="position"), atol=0.0, rtol=0.0)
        report = {"reference_only": True, "session_id": session.session_id,
                  "baseline_instance": original.instance_id, "alternate_instance": alternate.instance_id,
                  "parent_unchanged": original.inspect() == parent_before,
                  "replay": replay_report["outcome"], "branch_comparison": comparison["outcome"],
                  "world_time_s": original.inspect()["provider"]["clock"]["time_s"],
                  "player_latest_sample_s": player_result["data"]["observations"]["samples"][-1]["clock"]["time_s"],
                  "debugger_latest_sample_s": debug_result["data"]["observations"]["samples"][-1]["clock"]["time_s"],
                  "verification_status": "not_verified"}
        save_new(output_dir / "replay.json", replay_report)
        save_new(output_dir / "branch-comparison.json", comparison)
        save_new(output_dir / "summary.json", report)
    finally:
        # Includes every completed occurrence/refusal even if a demo stage raises.
        session.save_workspace(output_dir / "workspace.json")
    return report


def inspect_workspace(path: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="net-simulation-inspect-") as temp:
        session = open_workspace(path, output_dir=Path(temp))
        records = [r for r in session.results.values() if r.get("operation_id") == OPERATION]
        for result in records:
            validate_result(result)
        return {"reader_session_id": session.session_id, "simulation_results": len(records),
                "simulation_executions": sum(e["operation_id"] == OPERATION for e in session.executions.values()),
                "refusals": sum(e["operation_id"] == OPERATION and e["status"] == "refused" for e in session.executions.values()),
                "instance_ids": sorted({r["data"]["after"]["instance_id"] for r in records}),
                "live_providers_attached": False, "provider_executed": False, "verification_status": "not_verified"}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "godot":
        from .godot_simulation_cli import main as native_main
        return native_main(argv[1:])
    parser = argparse.ArgumentParser(prog="net simulation", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("godot", help="Explicit pinned native point-provider demo and campaigns")
    command = sub.add_parser("demo", help="Execute the synthetic Python reference workload")
    command.add_argument("--output-dir", type=Path, required=True)
    command = sub.add_parser("inspect", help="Reopen existing Session records without providers")
    command.add_argument("workspace", type=Path)
    command = sub.add_parser("check-replay", help="Recheck a retained report; does not execute a replay")
    command.add_argument("report", type=Path)
    command = sub.add_parser("campaign-demo", help="Run four independent reference intervention variants")
    command.add_argument("--output-dir", type=Path, required=True)
    command = sub.add_parser("campaign-reference", help="Run an explicit plan using the built-in reference provider")
    command.add_argument("workspace", type=Path)
    command.add_argument("--plan", type=Path, required=True)
    command.add_argument("--output-dir", type=Path, required=True)
    command = sub.add_parser("campaign-check", help="Recompute retained campaign comparisons without providers")
    command.add_argument("report", type=Path)
    command.add_argument("--expected-sha256")
    command = sub.add_parser("campaign-view", help="Create an observation-only offline campaign inspector")
    command.add_argument("report", type=Path)
    command.add_argument("--expected-sha256", required=True)
    command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "campaign-demo":
            from .simulation_campaign import reference_demo
            result = reference_demo(args.output_dir)
        elif args.command == "campaign-reference":
            from .simulation_campaign import run_reference
            result = run_reference(args.workspace, args.plan, args.output_dir)
        elif args.command in {"campaign-check", "campaign-view"}:
            from .simulation_campaign import read_campaign
            report = read_campaign(args.report, expected_sha256=args.expected_sha256)
            if args.command == "campaign-view":
                from .simulation_campaign_view import save_view
                save_view(report, args.output)
            result = report["summary"]
        elif args.command == "demo":
            result = demo(args.output_dir)
        elif args.command == "inspect":
            result = inspect_workspace(args.workspace)
        else:
            value = load(args.report)
            validate_replay(value)
            result = value["outcome"]
        print(json.dumps(result, indent=2, allow_nan=False))
        return 2 if result.get("status") == "FAIL" else 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
