"""Production CLI: explicit profiles, bounded plans, retained checks and repairs.

python -m ciw.production_workflow --help
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import uuid

from .control_contracts import load, save_new
from .control_plane import CapabilityRegistry, builtin_registry, experiment
from .production import Worker, inspect_production, plan, run_production, validate_plan
from .production_gates import builtin_gates, game_gates


def _graph(name: str, operation: str, parameters: dict, *, model: str) -> dict:
    return experiment(name, model_id=model, nodes=[{"node_id": "candidate", "operation_id": operation,
                       "parameters": parameters, "inputs": {}, "depends_on": []}])


def _job(name, worker, requires, attempts, checks, depends=()):
    return {"job_id": name, "worker_id": worker, "requires": requires, "attempts": attempts,
            "checks": checks, "depends_on": list(depends)}


def builtin_plan(source: dict) -> dict:
    def graph(name, end):
        return _graph(name, "statistics.v1", {"channel": "q", "interval_s": [0, end]}, model="analytic-damped-oscillator.v1")
    checks = [{"check_id": "one-second-window", "node_id": "candidate", "gate_id": "result.equals.v1",
               "policy": {"path": ["sample_count"], "expected": 64}}]
    return plan("window-production-pilot", project_id="net-synthetic-production", source_evidence_id=source["evidence_id"], jobs=[
        _job("select-window", "local-analysis", ["statistics"], [graph("oversized-window", 2), graph("corrected-window", 1)], checks),
        _job("dependent-analysis", "local-analysis", ["statistics"], [graph("accepted-window", 1)], checks, ["select-window"])])


def game_plan(source: dict, *, fault: str = "early-knowledge", repair: bool = True) -> dict:
    from .game_workflow import CAPTURE_OP
    def graph(name, diagnostic):
        return _graph(name, CAPTURE_OP, {"nonce": uuid.uuid4().hex, "diagnostic_fault": diagnostic}, model="courier-message.v1")
    attempts = [graph("candidate", fault)]
    if repair:
        attempts.append(graph("declared-correction", "none"))
    checks = [{"check_id": "authored-game-rules", "node_id": "candidate", "gate_id": "game.authored-rules.v1", "policy": {}}]
    return plan("game-production-pilot", project_id="net-courier-synthetic-reference", source_evidence_id=source["evidence_id"], jobs=[
        _job("courier-candidate", "godot-capture", ["game.capture"], attempts, checks),
        _job("dependent-regression", "godot-capture", ["game.capture"], [graph("regression", "none")], checks, ["courier-candidate"])])


def game_registry(binding) -> CapabilityRegistry:
    """Expose the existing capture implementation through the original capability seam."""
    from .adapters.protocol import InstrumentManifest
    from .operations.registry import Operation
    from .game_workflow import CAPTURE_OP, _parameters, register_schemas
    register_schemas()
    registry = CapabilityRegistry()
    manifest = InstrumentManifest(instrument_id="org.notationsystems.game-production-capture", version="1", role="operation_provider",
        inputs=("run.v1",), outputs=("ciw.operation-result.v1",), units={}, frames=(),
        sampling={"mode": "explicit_capture"}, normalization={"state": "engine_owned"}, supported_operations=(CAPTURE_OP,),
        determinism={"claim": "none_from_declaration"}, tolerance_policy={"policy": "authored_game_rules"},
        calibration_requirements={"status": "not_applicable_simulated"})
    registry.advertise(manifest, runtime=binding.runtime_identity(), capabilities={CAPTURE_OP: ["game.capture"]})
    def capture(run, parameters):
        _parameters(CAPTURE_OP, parameters)
        return binding.invoke(run["metadata"]["game_scenario"], parameters)
    registry.bind(Operation(CAPTURE_OP, "backend", capture, binding.runtime_identity))
    return registry


def _source(profile: str):
    if profile == "builtin":
        from .instruments import make_demo_run
        return make_demo_run()
    from .game_workflow import courier_scenario, make_run
    return make_run(courier_scenario())


def _gates(profile: str):
    if profile == "builtin":
        return builtin_gates()
    from .game_workflow import register_schemas
    register_schemas()
    return game_gates()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="net production", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    example = commands.add_parser("example", help="write a synthetic plan and source; no execution")
    example.add_argument("--profile", choices=("builtin", "godot-courier"), default="builtin")
    example.add_argument("--output-dir", type=Path, required=True)
    demo = commands.add_parser("demo", help="run real built-in analyses, fail, repair, then unblock a dependent")
    demo.add_argument("--output-dir", type=Path, required=True)
    run = commands.add_parser("run", help="execute a data-only plan against an explicitly selected installed profile")
    run.add_argument("plan", type=Path)
    run.add_argument("--source", type=Path, required=True)
    run.add_argument("--profile", choices=("builtin", "godot-courier"), required=True)
    run.add_argument("--output-dir", type=Path, required=True)
    run.add_argument("--max-operations", type=int, default=128)
    run.add_argument("--godot", type=Path)
    run.add_argument("--godot-sha256")
    run.add_argument("--adapter-root", type=Path)
    inspect = commands.add_parser("inspect", help="recheck retained history without starting an engine")
    inspect.add_argument("output_dir", type=Path)
    inspect.add_argument("--profile", choices=("builtin", "godot-courier"), required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "example":
            source = _source(args.profile)
            specification = builtin_plan(source) if args.profile == "builtin" else game_plan(source)
            args.output_dir.mkdir(parents=True, exist_ok=False)
            save_new(args.output_dir / "source.json", source)
            save_new(args.output_dir / "plan.json", specification)
            print(json.dumps({"status": "declared", "fresh_execution": False, "output_dir": str(args.output_dir)}))
            return 0
        if args.command == "inspect":
            report = inspect_production(args.output_dir, _gates(args.profile))
        else:
            profile = "builtin" if args.command == "demo" else args.profile
            source = _source(profile) if args.command == "demo" else load(args.source)
            specification = builtin_plan(source) if args.command == "demo" else load(args.plan)
            validate_plan(specification)
            if profile == "builtin":
                registry = builtin_registry(bind=True)
                workers = (Worker("local-analysis", ("statistics.v1", "spectrum.periodogram.v1")),)
            else:
                from .game_workflow import CAPTURE_OP, GodotCourierBinding, validate_courier
                if args.godot is None or args.godot_sha256 is None or args.adapter_root is None:
                    raise ValueError("Godot requires an explicit executable, SHA256 reference and adapter root")
                validate_courier(source["metadata"]["game_scenario"])
                registry = game_registry(GodotCourierBinding(args.godot, args.adapter_root, expected_sha256=args.godot_sha256))
                workers = (Worker("godot-capture", (CAPTURE_OP,)),)
            report = run_production(source, specification, registry, workers, _gates(profile), args.output_dir,
                                    max_operations=getattr(args, "max_operations", 128))
        print(json.dumps(report, indent=2, allow_nan=False))
        return 0 if report["status"] == "completed" else 2
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
