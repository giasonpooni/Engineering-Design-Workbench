"""Run retained polymer-cycle metrology, reference estimates and control simulations."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .control_contracts import load, save_new
from .polymer_contract import MAX_BYTES, PROCESSES, example_request
from . import polymer_workflow as workflow


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="net polymer", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    example = commands.add_parser("example")
    example.add_argument("--process", choices=sorted(PROCESSES), default="injection_molding")
    example.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run")
    run.add_argument("request", type=Path)
    run.add_argument("--output-dir", type=Path, required=True)
    for name in ("inspect", "verify", "replay"):
        command = commands.add_parser(name)
        command.add_argument("directory", type=Path)
        if name == "replay":
            command.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "example":
            save_new(args.output, example_request(args.process))
            result = {"status": "created", "request": str(args.output)}
        elif args.command == "run":
            if args.request.is_symlink() or not args.request.is_file() or args.request.stat().st_size > MAX_BYTES:
                raise ValueError("Require a regular polymer request within the 2 MiB budget")
            result = workflow.run(load(args.request), args.output_dir)
        elif args.command == "inspect":
            result = workflow.inspect(args.directory)
        elif args.command == "verify":
            result = workflow.verify_retained(args.directory)
        else:
            result = workflow.replay(args.directory, args.output_dir)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 2 if result.get("status") in {"REFUSE", "FAIL"} else 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        print(json.dumps({"status": "REFUSE", "reason": str(exc)}), file=sys.stderr)
        return 1
