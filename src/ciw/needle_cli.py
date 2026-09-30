"""Needle: local intervention, representation expansion, selective rerun and delta projection."""
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
from .representation_expansion import (
    expansion_from_spec,
    plan_after_verified_expansion,
    promote_expansion,
    validate_expansion,
    validate_expansion_verification,
    validate_promotion,
    verify_expansion,
)
from .representation_interventions import (
    gate_from_spec,
    inspect_gate,
    plan_represented_needle,
)
from .semantic_capabilities import builtin_semantic_registry
from .session import Session


def _expansion_context(args):
    concrete = builtin_registry(bind=True)
    semantic = builtin_semantic_registry(concrete)
    return (
        concrete,
        semantic,
        load(args.source_run),
        load(args.current_execution),
        load(args.current_result),
        load(args.gate),
        load(args.morphism_registry),
    )


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

    gate = commands.add_parser("gate")
    gate.add_argument("morphism_registry", type=Path)
    gate.add_argument("spec", type=Path)
    gate.add_argument("--output", type=Path, required=True)

    represented = commands.add_parser("plan-represented")
    represented.add_argument("baseline_graph_run", type=Path)
    represented.add_argument("spec", type=Path)
    represented.add_argument("gate", type=Path)
    represented.add_argument("morphism_registry", type=Path)
    represented.add_argument("--output", type=Path, required=True)

    for name in ("expand", "verify-expansion", "promote-expansion"):
        cmd = commands.add_parser(name)
        cmd.add_argument("source_run", type=Path)
        cmd.add_argument("current_execution", type=Path)
        cmd.add_argument("current_result", type=Path)
        cmd.add_argument("gate", type=Path)
        cmd.add_argument("morphism_registry", type=Path)
        if name in {"verify-expansion", "promote-expansion"}:
            cmd.add_argument("expansion", type=Path)
        if name == "promote-expansion":
            cmd.add_argument("verification", type=Path)
        if name in {"expand", "promote-expansion"}:
            cmd.add_argument("spec", type=Path)
        if name == "verify-expansion":
            cmd.add_argument("--session-dir", type=Path, required=True)
        cmd.add_argument("--output", type=Path, required=True)

    expanded_plan = commands.add_parser("plan-expanded")
    expanded_plan.add_argument("baseline_graph_run", type=Path)
    expanded_plan.add_argument("needle_spec", type=Path)
    expanded_plan.add_argument("source_run", type=Path)
    expanded_plan.add_argument("current_execution", type=Path)
    expanded_plan.add_argument("current_result", type=Path)
    expanded_plan.add_argument("gate", type=Path)
    expanded_plan.add_argument("morphism_registry", type=Path)
    expanded_plan.add_argument("expansion", type=Path)
    expanded_plan.add_argument("verification", type=Path)
    expanded_plan.add_argument("promotion", type=Path)
    expanded_plan.add_argument("--output", type=Path, required=True)

    inspect = commands.add_parser("inspect")
    inspect.add_argument("record", type=Path)
    args = parser.parse_args(argv)

    try:
        if args.command == "plan":
            value = plan_from_spec(load(args.baseline_graph_run), load(args.spec))
            save_new(args.output, value)
            print(json.dumps({
                "status": "planned", "needle_id": value["needle_id"], "target": value["target"],
                "execution_authority": False, "output": str(args.output),
            }))
            return 0

        if args.command == "gate":
            concrete = builtin_registry(bind=True)
            semantic = builtin_semantic_registry(concrete)
            value = gate_from_spec(load(args.morphism_registry), semantic, load(args.spec))
            save_new(args.output, value)
            print(json.dumps({
                "status": "assessed", "decision": value["decision"],
                "representation_id": value["representation_id"],
                "intervention_id": value["intervention_id"],
                "recovery_representation_id": value["recovery_representation_id"],
                "materialization_performed": False,
                "execution_authority": False, "output": str(args.output),
            }))
            return 0

        if args.command == "plan-represented":
            concrete = builtin_registry(bind=True)
            semantic = builtin_semantic_registry(concrete)
            value = plan_represented_needle(
                load(args.baseline_graph_run), load(args.spec), load(args.gate),
                load(args.morphism_registry), semantic)
            save_new(args.output, value)
            print(json.dumps({
                "status": "planned", "needle_id": value["needle_id"],
                "representation_gate_enforced": True,
                "execution_authority": False, "output": str(args.output),
            }))
            return 0

        if args.command in {"expand", "verify-expansion", "promote-expansion"}:
            _, semantic, source, execution, result, gate_value, registry = _expansion_context(args)
            if args.command == "expand":
                value = expansion_from_spec(
                    source, execution, result, gate_value, registry, semantic, load(args.spec))
                status = "resolved"
            elif args.command == "verify-expansion":
                value = verify_expansion(
                    load(args.expansion), source, execution, result, gate_value, registry,
                    semantic, args.session_dir)
                status = value["status"]
            else:
                value = promote_expansion(
                    load(args.expansion), load(args.verification), source, execution, result,
                    gate_value, registry, semantic, load(args.spec))
                status = value["local_gate"]["decision"]
            save_new(args.output, value)
            print(json.dumps({
                "status": status, "schema": value["schema"],
                "record_digest": value["record_digest"],
                "canonical_state_mutated": False,
                "state_admission": False,
                "execution_authority": False,
                "output": str(args.output),
            }))
            return 0 if status not in {"FAIL"} else 2

        if args.command == "plan-expanded":
            concrete = builtin_registry(bind=True)
            semantic = builtin_semantic_registry(concrete)
            value = plan_after_verified_expansion(
                load(args.baseline_graph_run), load(args.needle_spec), load(args.promotion),
                load(args.expansion), load(args.verification), load(args.source_run),
                load(args.current_execution), load(args.current_result), load(args.gate),
                load(args.morphism_registry), semantic)
            save_new(args.output, value)
            print(json.dumps({
                "status": "planned", "needle_id": value["needle_id"],
                "verified_expansion_enforced": True,
                "execution_authority": False, "output": str(args.output),
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
                "status": run["status"], "dependency_closure": run["dependency_closure"],
                "reused_nodes": run["reused_nodes"], "rerun_nodes": run["rerun_nodes"],
                "changed_output_nodes": delta["summary"]["changed_output_nodes"],
                "canonical_state_mutated": False,
                "run_output": str(args.run_output), "delta_output": str(args.delta_output),
            }))
            return 0

        value = load(args.record)
        schema = value.get("schema") if type(value) is dict else None
        if schema in {
            "ciw.intervention-gate.v1", "ciw.representation-expansion.v1",
            "ciw.representation-expansion-verification.v1",
            "ciw.representation-expansion-promotion.v1",
        }:
            raise ValueError(
                "Context-bound representation records must be inspected by recomputing "
                "them with their registry and retained evidence")
        if schema == "ciw.needle-plan.v1":
            checked = validate_plan(value)
            result = {
                "schema": "ciw.needle-plan-inspection.v1", "needle_id": checked["needle_id"],
                "target": checked["target"],
                "baseline_graph_run_ref": checked["baseline_graph_run_ref"],
                "execution_authority": False,
            }
        elif schema == "ciw.needle-run.v1":
            checked = validate_needle_run(value)
            result = {
                "schema": "ciw.needle-run-inspection.v1", "record_digest": checked["record_digest"],
                "status": checked["status"], "dependency_closure": checked["dependency_closure"],
                "reused_nodes": checked["reused_nodes"], "rerun_nodes": checked["rerun_nodes"],
                "canonical_state_mutated": False,
            }
        elif schema == "ciw.needle-delta.v1":
            checked = validate_delta(value)
            result = {
                "schema": "ciw.needle-delta-inspection.v1", "record_digest": checked["record_digest"],
                "target_node_id": checked["target_node_id"], "summary": checked["summary"],
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
