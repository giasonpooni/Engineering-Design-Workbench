"""Discover, run, inspect, numerically check and replay bounded weather tools."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .control_contracts import load, save_new


def main(argv=None) -> int:
    from . import weather_contract as contract, weather_workflow as workflow
    parser = argparse.ArgumentParser(prog="net weather", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("catalog")
    example = commands.add_parser("example")
    example.add_argument("profile", choices=sorted(contract.providers()))
    example.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run")
    run.add_argument("request", type=Path)
    run.add_argument("--output-dir", type=Path, required=True)
    for name in ("inspect", "verify", "replay", "export"):
        command = commands.add_parser(name)
        command.add_argument("directory", type=Path)
        if name == "replay":
            command.add_argument("--output-dir", type=Path, required=True)
        if name == "export":
            command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "catalog":
            result = contract.catalog()
        elif args.command == "example":
            save_new(args.output, contract.example_request(args.profile))
            result = {"status": "created", "request": str(args.output)}
        elif args.command == "run":
            result = workflow.run(load(args.request), args.output_dir)
        elif args.command == "inspect":
            result = workflow.inspect(args.directory)
        elif args.command == "verify":
            result = workflow.verify_retained(args.directory)
        elif args.command == "replay":
            result = workflow.replay(args.directory, args.output_dir)
        else:
            result = workflow.export_result(args.directory, args.output)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 2 if result.get("status") in {"REFUSE", "FAIL"} else 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        print(json.dumps({"status": "REFUSE", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
