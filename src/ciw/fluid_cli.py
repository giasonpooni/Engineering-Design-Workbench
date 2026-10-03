"""Run, inspect, independently verify and export qualified synthetic fluid models."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .control_contracts import save_new
from . import fluid_workflow as workflow


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="net fluid", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    example = commands.add_parser("example")
    example.add_argument("--profile", choices=workflow.contract.PROFILES, default="reservoir")
    example.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run")
    run.add_argument("request_path", type=Path, nargs="?")
    run.add_argument("--request", type=Path)
    run.add_argument("--output-dir", type=Path, required=True)
    for name in ("inspect", "verify", "export-csv"):
        command = commands.add_parser(name)
        command.add_argument("directory", type=Path)
        if name in {"verify", "export-csv"}:
            command.add_argument("--output", type=Path, required=name == "export-csv")
    handoff = commands.add_parser("handoff")
    handoff.add_argument("directory", type=Path)
    handoff.add_argument("--sample-index", type=int, required=True)
    handoff.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == "run" and (args.request is None) == (args.request_path is None):
        parser.error("run requires exactly one --request path or positional request path")
    try:
        if args.command == "example":
            save_new(args.output, workflow.contract.example_request(args.profile))
            result = {"status": "created", "profile": args.profile, "request": str(args.output)}
        elif args.command == "run":
            result = workflow.run(workflow.load_regular(args.request or args.request_path), args.output_dir)
        elif args.command == "inspect":
            result = workflow.inspect(args.directory)
        elif args.command == "verify":
            result = workflow.verify_retained(args.directory)
            if args.output is not None:
                save_new(args.output, result)
        elif args.command == "handoff":
            from .fluid_handoff import export_snapshot
            result = export_snapshot(args.directory, args.output, sample_index=args.sample_index)
        else:
            result = workflow.export_csv(args.directory, args.output)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 2 if result.get("status") in {"REFUSE", "EXPAND"} else 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        print(json.dumps({"status": "REFUSE", "reason": str(exc)}), file=sys.stderr)
        return 1
