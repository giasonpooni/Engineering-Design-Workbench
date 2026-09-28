"""Run the installed Godot provider through existing stateful campaigns/replay."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from pathlib import Path
import json
import sys
import tempfile

from .control_contracts import MAX_BYTES, bytes_ref, load, save_new
from .godot_simulation import DEFAULT, PROVIDER_ID, STEP, GodotProjectile, validate_configuration
from .simulation_campaign import plan, run_campaign, validate_plan
from .simulation_control import SimulationControl, completed, open_workspace
from .simulation_records import observer, require
from .simulation_replay import replay, validate_result


def demo(executable: Path, expected_sha256: str, output_dir: Path) -> dict:
    from .instruments import make_demo_run
    from .session import Session
    output_dir.mkdir(parents=True, exist_ok=False)
    session = Session(make_demo_run(), output_dir)
    providers = []
    summary = None
    try:
        with ExitStack() as stack:
            def factory():
                native = stack.enter_context(GodotProjectile(executable, expected_sha256=expected_sha256))
                providers.append(native)
                return native
            control = SimulationControl(session)
            native_parent = factory()
            parent = control.attach(native_parent, provider_id=PROVIDER_ID, experiment_id="native-source")
            call = lambda action, **args: completed(parent.command(action, **args))
            call("start")
            call("step", dt=STEP)
            call("step", dt=STEP)
            call("intervene", actor_id="operator", operation="projectile.queue-impulse.v1", target="projectile",
                 parameters={"at_tick": 6, "delta_v_m_s": [1, 0, 0]})
            call("pause")
            checkpoint = call("checkpoint")
            selected = observer("position-debugger", kind="debugger", channels=["position_x"])
            variants = [{"variant_id": "baseline", "interventions": []}]
            for delta in (-2, 2, 4):
                variants.append({"variant_id": f"impulse-{delta:+d}", "interventions": [{
                    "actor_id": "operator", "operation": "projectile.queue-impulse.v1", "target": "projectile",
                    "parameters": {"at_tick": 3, "delta_v_m_s": [delta, 0, 0]}}]})
            declared = plan(checkpoint, campaign_id="native-impulse-alternatives", variants=variants,
                            steps=8, dt=STEP, observer=selected, quantity="position_x", atol=0, rtol=0)
            save_new(output_dir / "plan.json", declared)
            before = parent.inspect()
            report = run_campaign(control, checkpoint, declared, factory)
            require(parent.inspect() == before, "Native campaign changed parent")
            save_new(output_dir / "campaign.json", report)
            suffix = [call("resume")]
            suffix += [call("step", dt=STEP) for _ in range(8)]
            suffix += [call("observe", observer=selected), call("pause")]
            child, reproduced = replay(control, checkpoint, suffix, factory(), experiment_id="native-replay")
            save_new(output_dir / "replay.json", reproduced)
            embodied = call("observe", observer=observer("player", kind="embodied_agent", channels=["position_x"]))
            summary = {"reference_only": False, "model_scope": "synthetic Godot-owned point dynamics, not contact physics",
                       "campaign": report["summary"], "replay": reproduced["outcome"],
                       "parent_unchanged_during_campaign": True,
                       "world_time_s": parent.inspect()["provider"]["clock"]["time_s"],
                       "player_latest_time_s": embodied["data"]["observations"]["samples"][-1]["clock"]["time_s"],
                       "max_differences_m": [c["comparison"]["outcome"]["metrics"]["max_abs_error"] for c in report["comparisons"]],
                       "runtime": native_parent.identity()["runtime"], "verification_status": "not_verified"}
            call("stop")
            completed(child.command("stop"))
        summary["processes"] = [p.diagnostics() for p in providers]
        require(all(p["returncode"] == 0 for p in summary["processes"]), "Native process did not close cleanly")
        summary["execution_count"] = len(session.executions)
        save_new(output_dir / "summary.json", summary)
        return summary
    finally:
        session.save_workspace(output_dir / "workspace.json")
        save_new(output_dir / "processes.json", {"processes": [p.diagnostics() for p in providers]})


def campaign(executable: Path, expected_sha256: str, workspace: Path, plan_path: Path, output_dir: Path) -> dict:
    # Freeze and validate selection in scratch before creating the requested output.
    declared = load(plan_path)
    validate_plan(declared)
    with workspace.open("rb") as source:
        raw = source.read(MAX_BYTES + 1)
    require(len(raw) <= MAX_BYTES, "Native source workspace exceeds 8 MiB")
    with tempfile.TemporaryDirectory(prefix="net-native-preflight-") as temp:
        frozen = Path(temp) / "source.json"
        frozen.write_bytes(raw)
        check = open_workspace(frozen, output_dir=Path(temp) / "reader")
        matches = [r for r in check.results.values() if r["record_digest"] == declared["checkpoint_result_ref"]]
        require(len(matches) == 1, "Select exactly one native checkpoint result")
        checkpoint = matches[0]
        validate_result(checkpoint)
        source = checkpoint["data"]["after"]
        require(source["provider_id"] == PROVIDER_ID and checkpoint["data"]["checkpoint"] is not None,
                "Selected checkpoint is not a Godot point provider")
        validate_configuration(source["configuration"])
        require(source["provider"]["runtime"].get("executable_sha256") == expected_sha256,
                "Selected native executable differs from checkpoint")
        output_dir.mkdir(parents=True, exist_ok=False)
        session = open_workspace(frozen, output_dir=output_dir)
    providers = []
    try:
        with ExitStack() as stack:
            def factory():
                provider = stack.enter_context(GodotProjectile(executable, expected_sha256=expected_sha256,
                    configuration=source["configuration"], simulation_id=source["provider"]["simulation_id"]))
                providers.append(provider)
                return provider
            control = SimulationControl(session)
            save_new(output_dir / "plan.json", declared)
            report = run_campaign(control, checkpoint, declared, factory)
            save_new(output_dir / "campaign.json", report)
        return report["summary"]
    finally:
        session.save_workspace(output_dir / "workspace.json")
        save_new(output_dir / "processes.json", {"processes": [p.diagnostics() for p in providers]})


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "capture":
        from .godot_capture import main as capture_main
        return capture_main(argv[1:])
    parser = argparse.ArgumentParser(prog="net simulation godot", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("capture", help="Render or inspect image evidence from selected retained observations")
    for name in ("demo", "campaign"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--godot", type=Path, required=True)
        cmd.add_argument("--godot-sha256", required=True)
        cmd.add_argument("--output-dir", type=Path, required=True)
        if name == "campaign":
            cmd.add_argument("--workspace", type=Path, required=True)
            cmd.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            result = demo(args.godot, args.godot_sha256, args.output_dir)
        else:
            result = campaign(args.godot, args.godot_sha256, args.workspace, args.plan, args.output_dir)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except (ValueError, TypeError, OSError, KeyError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
