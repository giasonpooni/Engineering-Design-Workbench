"""Compile bounded workflow declarations; execute only explicit installed demos.

No JSON-selected provider imports, shell commands or credentials. Python hosts can
supply their existing registered operations and stage contracts through the API.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile

from . import workflow_algebra as algebra, workflow_production as production
from .control_contracts import bytes_ref, keys, load, save_new
from .control_plane import builtin_registry
from .core.identities import content_identity


def _builtin(*, bind=False):
    from .instruments import make_demo_run
    from .production_workflow import builtin_plan
    from .production_gates import builtin_gates
    source = make_demo_run()
    registry = builtin_registry(bind=bind)
    rights = algebra.grant(permissions=("analysis",))
    ops = {op: algebra.declare(registry, op, effect=algebra.effects(reads=("recording/synthetic",)),
                              permissions=("analysis",)) for op in registry.catalog()["operations"]}
    original = builtin_plan(source)
    templates = {job["job_id"]: job for job in original["jobs"]}
    stages = {name: production.declare_stage(job, effect=algebra.effects(reads=("recording/synthetic",)),
                                            permissions=("analysis",)) for name, job in templates.items()}
    return source, registry, rights, ops, templates, stages, builtin_gates(), original


def request(target):
    expr = (algebra.parallel(algebra.call("statistics", "statistics.v1", {"channel": "q"}),
                             algebra.call("spectrum", "spectrum.periodogram.v1", {"channel": "q"}))
            if target == "graph" else
            algebra.sequence(production.bounded_retry("select-window", max_attempts=2),
                             production.stage("dependent-analysis")))
    return {"schema": "ciw.workflow-request.v1", "target": target, "expression": expr}


def _compile_request(value, context):
    keys(value, {"schema", "target", "expression"})
    if value["schema"] != "ciw.workflow-request.v1" or value["target"] not in {"graph", "production"}:
        raise ValueError("Unsupported workflow request")
    source, registry, rights, ops, templates, stages, gates, original = context
    if value["target"] == "graph":
        return algebra.compile_graph(value["expression"], registry, ops, rights,
                                     experiment_id="workflow-analysis", model_id="analytic-damped-oscillator.v1")
    return production.compile_plan(value["expression"], templates, registry, stages, gates, rights,
        **{key: original[key] for key in ("plan_id", "project_id", "source_evidence_id")})


def inspect(value):
    if value.get("schema") == "ciw.workflow-compilation.v1":
        return algebra.inspect_compilation(value)
    if value.get("schema") == "ciw.workflow-production-compilation.v1":
        return production.inspect_compilation(value)
    raise ValueError("Not a supported compiled workflow")


def audit_slot(path):
    """Check compilation receipts and original native histories on one frozen copy.

    Uses existing bounded source readers: max 1024 files/32 MiB, 2 MiB per file.
    No signature or source-authentication claim; the operator supplies the path.
    """
    from .agent_api import identifier
    from .foundry_packets import inventory, read_file, root_dir
    from .workcell import inspect_attempt
    root = root_dir(path)
    snapshot = inventory(root)
    receipts = sorted(n for n in snapshot["files"] if "/" not in n and n.startswith("compilation-") and n.endswith(".json"))
    if not 1 <= len(receipts) <= 16:
        raise ValueError("Expected 1..16 compilation receipts")
    with tempfile.TemporaryDirectory(prefix="net-workflow-audit-") as directory:
        frozen = Path(directory)
        for name, spec in snapshot["files"].items():
            raw = read_file(root, name)
            if bytes_ref(raw) != spec["sha256"]:
                raise ValueError("Slot changed while freezing its evidence")
            dest = frozen / name
            dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(raw)
        checked = []
        for name in receipts:
            attempt = name[len("compilation-"):-len(".json")]
            identifier(attempt)
            receipt = load(frozen / name)
            production.inspect_compilation(receipt)
            native_plan = load(frozen / "runs" / attempt / "plan.json")
            if content_identity(native_plan) != content_identity(receipt["plan"]):
                raise ValueError("Executed plan differs from the compiled workflow")
            result = inspect_attempt(frozen / "runs" / attempt)
            checked.append({"attempt": attempt, "status": result["status"],
                            "execution_count": result["execution_count"],
                            "compilation_digest": receipt["record_digest"]})
    return {"schema": "ciw.workflow-slot-audit.v1", "fresh_execution": False,
            "checked": checked, "retained_files": len(snapshot["files"]), **algebra.AUTHORITY}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="net compose", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    example = sub.add_parser("example", help="Write graph and production declarations without dispatch")
    example.add_argument("--output-dir", type=Path, required=True)
    for verb in ("check", "compile"):
        item = sub.add_parser(verb, help="Type/effect/permission check the explicitly installed built-in profile")
        item.add_argument("source", type=Path)
        if verb == "compile": item.add_argument("--output", type=Path, required=True)
    read = sub.add_parser("inspect", help="Recompile a retained declaration; never execute")
    read.add_argument("source", type=Path)
    audit = sub.add_parser("inspect-slot", help="Recheck compiled/native workcell correspondence without providers")
    audit.add_argument("source", type=Path)
    demo = sub.add_parser("demo", help="Execute compiled built-in analyses and a bounded correction campaign")
    demo.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "example":
            args.output_dir.mkdir(parents=True, exist_ok=False)
            for target in ("graph", "production"):
                save_new(args.output_dir / (target + ".json"), request(target))
            result = {"status": "declared", "fresh_execution": False}
        elif args.command == "inspect":
            result = inspect(load(args.source))
        elif args.command == "inspect-slot":
            result = audit_slot(args.source)
        elif args.command in ("check", "compile"):
            result = _compile_request(load(args.source), _builtin())
            if args.command == "compile": save_new(args.output, result)
            result = {"status": "compiled", "record_digest": result["record_digest"], **inspect(result)}
        else:
            from .session import Session
            from .production import Worker, inspect_production
            context = _builtin(bind=True)
            source, registry, rights, ops, templates, stages, gates, _ = context
            graph = _compile_request(request("graph"), context)
            campaign = _compile_request(request("production"), context)
            args.output_dir.mkdir(parents=True, exist_ok=False)
            save_new(args.output_dir / "graph-compilation.json", graph)
            save_new(args.output_dir / "production-compilation.json", campaign)
            session = Session(source, args.output_dir / "analysis", operations=registry.operations)
            try:
                observed = algebra.run_compiled(session, graph, registry, ops, rights)
            finally:
                session.save_workspace(args.output_dir / "analysis" / "workspace.json")
            save_new(args.output_dir / "graph-run.json", observed)
            report = production.run_compiled(source, campaign, registry, templates, stages, gates,
                (Worker("local-analysis", ("statistics.v1", "spectrum.periodogram.v1")),), rights,
                args.output_dir / "production", max_operations=3)
            inspect_production(args.output_dir / "production", gates)
            result = {"status": "completed" if observed["status"] == report["status"] == "completed" else "incomplete",
                      "analysis_executions": len(session.executions), "production_executions": report["execution_count"],
                      "parallel_scheduling": False, "physical_qualification": "not_performed"}
            save_new(args.output_dir / "summary.json", result)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 2 if result.get("status") == "incomplete" else 0
    except (ValueError, TypeError, KeyError, OSError, OverflowError, RecursionError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
