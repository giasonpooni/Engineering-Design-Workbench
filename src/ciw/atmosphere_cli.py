"""Compile, retain, inspect and export a declared reference atmosphere.

Use 'net atmosphere moist' to select the unsaturated moist-air request profile.
Retained actions dispatch the fixed profile recorded in the bundle.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .control_contracts import load, save_new
from . import atmosphere_workflow as workflow


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    moist = bool(argv and argv[0] == "moist")
    if moist:
        argv.pop(0)
    parser = argparse.ArgumentParser(prog="net atmosphere moist" if moist else "net atmosphere", description=__doc__)
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
    handoff = commands.add_parser("handoff")
    handoff.add_argument("directory", type=Path)
    handoff.add_argument("--output", type=Path, required=True)
    handoff.add_argument("--sample-index", type=int, required=True)
    handoff.add_argument("--provider", choices=("impact", "fluid", "render"), required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "example":
            if moist:
                from .atmosphere_moist_contract import example_request
            else:
                from .atmosphere_contract import example_request
            save_new(args.output, example_request())
            result = {"status": "created", "request": str(args.output)}
        elif args.command == "run":
            request = load(args.request)
            if workflow._moist(request) != moist:
                raise ValueError("Atmosphere request profile differs from selected CLI command")
            result = workflow.run(request, args.output_dir)
        elif args.command == "inspect":
            result = workflow.inspect(args.directory)
        elif args.command == "verify":
            result = workflow.verify_retained(args.directory)
        elif args.command == "handoff":
            result = workflow.export_handoff(args.directory, args.output, sample_index=args.sample_index,
                                             provider=args.provider)
        else:
            result = workflow.export_csv(args.directory, args.output)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 2 if result.get("status") in {"REFUSE", "EXPAND"} else 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        print(json.dumps({"status": "REFUSE", "reason": str(exc)}), file=sys.stderr)
        return 1
