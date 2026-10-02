"""Run and inspect bounded elastic/crush contact benchmarks through NET."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .control_contracts import load, save_new
from . import impact_workflow as workflow


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "sweep":
        from .impact_sweep import main as sweep_main
        return sweep_main(argv[1:])
    crush = bool(argv and argv[0] == "crush")
    if crush:
        argv = argv[1:]
    parser = argparse.ArgumentParser(prog="net impact crush" if crush else "net impact", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    example = commands.add_parser("example")
    example.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run")
    run.add_argument("request", type=Path)
    run.add_argument("--output-dir", type=Path, required=True)
    for name in ("inspect", "verify", "export"):
        command = commands.add_parser(name)
        command.add_argument("directory", type=Path)
        if name == "export":
            command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "example":
            if crush:
                from .impact_crush_contract import example_request
            else:
                from .impact_contract import example_request
            save_new(args.output, example_request())
            result = {"status": "created", "request": str(args.output)}
        elif args.command == "run":
            request = load(args.request)
            if workflow._crush(request) != crush:
                raise ValueError("Request profile differs from the selected impact command")
            result = workflow.run(request, args.output_dir)
        elif args.command == "inspect":
            result = workflow.inspect(args.directory)
        elif args.command == "verify":
            result = workflow.verify_retained(args.directory)
        else:
            result = workflow.export_csv(args.directory, args.output)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 2 if result.get("status") in {"REFUSE", "EXPAND"} else 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        print(json.dumps({"status": "REFUSE", "reason": str(exc)}), file=sys.stderr)
        return 1
