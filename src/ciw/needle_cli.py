"""Needle: local intervention, dependency closure, selective rerun and delta projection."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .control_contracts import load, save_new
from .control_plane import builtin_registry
from .needle import (
    delta_projection,
    execute_needle,
    plan_from_spec,
    validate_delta,
    validate_needle_run,
    validate_plan,
)
from .session import Session


def main(argv=None):
    parser = argparse.ArgumentParser(prog="net needle", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    plan = commands.add_parser("plan")
    plan.add_argument("baseline_graph_run", type=Path)
    plan.add_argument("spec", type=Path)
    plan.add_argument("--output", type=Path, required=True)

    execute = commands.add_parser("execute")
    execute.add_argument("source_run", type=Path)
    execute.add_argument("baseline_graph_run", type=Path)
    execute.add_argument("plan", type=Path)
    execute.add_argument("--session-dir", type=Path, required=True)
    execute.add_argument("--run-output", type=Path, required=True)
    execute.add_argument("--delta-output", type=Path, required=True)

    inspect = commands.add_parser("inspect")
    inspect.add_argument("record", type=Path)
    args = parser.parse_args(argv)

    try:
        if args.command == "plan":
            value = plan_from_spec(load(args.baseline_graph_run), load(args.spec))
            save_new(args.output, value)
            print(json.dumps({
                "status": "planned",
                "needle_id": value["needle_id"],
                "target": value["target"],
                "execution_authority": False,
                "output": str(args.output),
            }))
            return 0
        if args.command == "execute":
            registry = builtin_registry(bind=True)
            session = Session(load(args.source_run), args.session_dir, operations=registry.operations)
            baseline = load(args.baseline_graph_run)
            plan_value = load(args.plan)
            run = execute_needle(session, baseline, plan_value, registry)
            delta = delta_projection(baseline, run)
            save_new(args.run_output, run)
            save_new(args.delta_output, delta)
            print(json.dumps({
                "status": run["status"],
                "dependency_closure": run["dependency_closure"],
                "reused_nodes": run["reused_nodes"],
                "rerun_nodes": run["rerun_nodes"],
                "changed_output_nodes": delta["summary"]["changed_output_nodes"],
                "canonical_state_mutated": False,
                "run_output": str(args.run_output),
                "delta_output": str(args.delta_output),
            }))
            return 0
        value = load(args.record)
        schema = value.get("schema") if type(value) is dict else None
        if schema == "ciw.needle-plan.v1":
            checked = validate_plan(value)
            result = {
                "schema": "ciw.needle-plan-inspection.v1",
                "needle_id": checked["needle_id"],
                "target": checked["target"],
                "baseline_graph_run_ref": checked["baseline_graph_run_ref"],
                "execution_authority": False,
            }
        elif schema == "ciw.needle-run.v1":
            checked = validate_needle_run(value)
            result = {
                "schema": "ciw.needle-run-inspection.v1",
                "record_digest": checked["record_digest"],
                "status": checked["status"],
                "dependency_closure": checked["dependency_closure"],
                "reused_nodes": checked["reused_nodes"],
                "rerun_nodes": checked["rerun_nodes"],
                "canonical_state_mutated": False,
            }
        elif schema == "ciw.needle-delta.v1":
            checked = validate_delta(value)
            result = {
                "schema": "ciw.needle-delta-inspection.v1",
                "record_digest": checked["record_digest"],
                "target_node_id": checked["target_node_id"],
                "summary": checked["summary"],
                "causal_effects_established": False,
            }
        else:
            raise ValueError("Unsupported Needle record schema")
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
