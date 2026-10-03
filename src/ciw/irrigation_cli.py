"""Plan declared irrigation inputs, retain evidence, and independently audit them."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .control_contracts import save_new
from . import irrigation_workflow as workflow


def _exit_status(result: dict) -> int:
    if result.get("status") == "REFUSE":
        return 1
    if result.get("planning_status") in {"REVIEW", "ABSTAIN", "UNMET"}:
        return 2
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="net irrigation", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    example = commands.add_parser("example", help="Write a declared deterministic example request")
    example.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run", help="Create a retained plan and separate numerical verification")
    run.add_argument("request_path", type=Path, nargs="?")
    run.add_argument("--request", type=Path)
    run.add_argument("--output-dir", type=Path, required=True)
    for name in ("inspect", "verify", "replay", "export-csv", "report"):
        command = commands.add_parser(name)
        command.add_argument("directory", type=Path)
        if name == "replay":
            command.add_argument("--output-dir", type=Path, required=True)
        elif name in {"verify", "export-csv", "report"}:
            command.add_argument("--output", type=Path, required=name != "verify")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == "run" and (args.request is None) == (args.request_path is None):
        parser.error("run requires exactly one --request path or positional request path")
    try:
        if args.command == "example":
            save_new(args.output, workflow.contract.example_request())
            result = {"status": "created", "request": str(args.output), "scope": workflow.contract.SCOPE}
        elif args.command == "run":
            result = workflow.run(workflow.load_regular(args.request or args.request_path), args.output_dir)
        elif args.command == "inspect":
            result = workflow.inspect(args.directory)
        elif args.command == "verify":
            result = workflow.verify_retained(args.directory)
            if args.output is not None:
                save_new(args.output, result)
        elif args.command == "replay":
            result = workflow.replay(args.directory, args.output_dir)
        elif args.command == "export-csv":
            result = workflow.export_csv(args.directory, args.output)
        else:
            result = workflow.export_html(args.directory, args.output)
        print(json.dumps(result, indent=2, allow_nan=False))
        return _exit_status(result)
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        print(json.dumps({"status": "REFUSE", "reason": str(exc)}), file=sys.stderr)
        return 1
