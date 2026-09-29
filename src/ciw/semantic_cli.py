"""Stable capability semantics; replaceable engines; existing NET graphs underneath."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from .control_contracts import load, save_new
from .control_plane import builtin_registry
from .semantic_capabilities import SemanticHost, builtin_semantic_registry, compile_graph


def demo_graph():
    return {
        "schema": "ciw.semantic-work-graph.v1",
        "graph_id": "semantic-headless-demo",
        "mandate": "Analyze one retained oscillator recording without requesting a visual projection.",
        "model_id": "analytic-damped-oscillator.v1",
        "nodes": [
            {"node_id": "statistics", "capability": "analysis.statistics.v1",
             "parameters": {"channel": "q"}, "inputs": {}, "depends_on": [],
             "resources": ["cpu"], "acceptance": {}, "inspection": False},
            {"node_id": "spectrum", "capability": "analysis.spectrum.v1",
             "parameters": {"channel": "q"}, "inputs": {}, "depends_on": ["statistics"],
             "resources": ["cpu"], "acceptance": {}, "inspection": False},
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(prog="net semantic", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("catalog")
    demo = commands.add_parser("demo")
    demo.add_argument("--output-dir", type=Path, required=True)
    compile_cmd = commands.add_parser("compile")
    compile_cmd.add_argument("graph", type=Path)
    compile_cmd.add_argument("--output", type=Path, required=True)
    commands.add_parser("serve")
    args = parser.parse_args(argv)

    try:
        concrete = builtin_registry(bind=True)
        semantic = builtin_semantic_registry(concrete)
        if args.command == "catalog":
            print(json.dumps(semantic.catalog(), indent=2))
            return 0
        if args.command == "demo":
            args.output_dir.mkdir(parents=True, exist_ok=False)
            graph = demo_graph()
            receipt = compile_graph(graph, semantic)
            save_new(args.output_dir / "semantic-graph.json", graph)
            save_new(args.output_dir / "semantic-compilation.json", receipt)
            save_new(args.output_dir / "experiment.json", receipt["experiment"])
            print(json.dumps({"status": "compiled", "authorizes_execution": False,
                              "output_dir": str(args.output_dir)}))
            return 0
        if args.command == "compile":
            receipt = compile_graph(load(args.graph), semantic)
            save_new(args.output, receipt)
            print(json.dumps({"status": "compiled", "authorizes_execution": False,
                              "output": str(args.output)}))
            return 0

        from .agent_mcp import serve
        with os.fdopen(os.dup(sys.stdout.fileno()), "wb", buffering=0) as wire:
            os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
            return serve(SemanticHost(semantic), sys.stdin.buffer, wire)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
