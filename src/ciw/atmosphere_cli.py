"""Compile, retain, inspect and export a declared reference atmosphere.

Use 'net atmosphere moist' to select the unsaturated moist-air request profile.
Use 'net atmosphere compare' for reference comparisons and the NIST benchmark.
Retained actions dispatch the fixed profile recorded in the bundle.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys

from .control_contracts import MAX_BYTES, json_tree, save_new
from . import atmosphere_workflow as workflow


def _regular_load(path: Path) -> dict:
    """Read bounded regular input without following links or blocking on a FIFO."""
    from .session import loads_json
    path = Path(path)
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError("Atmosphere inputs must be regular files without symlinks")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("Atmosphere input changed to a nonregular file")
        raw = stream.read(MAX_BYTES + 1)
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("Atmosphere input is empty or exceeds the 8 MiB budget")
    value = loads_json(raw.decode("utf-8"))
    json_tree(value)
    return value


def _comparison_main(argv: list[str]) -> int:
    from . import atmosphere_comparison_workflow as comparison
    parser = argparse.ArgumentParser(prog="net atmosphere compare",
        description="Compare exact retained atmospheric samples with declared independent reference evidence.")
    commands = parser.add_subparsers(dest="command", required=True)
    example = commands.add_parser("example")
    example.add_argument("--profile", choices=("dry", "moist"), default="dry")
    example.add_argument("--reference-output", type=Path, required=True)
    example.add_argument("--policy-output", type=Path, required=True)
    run = commands.add_parser("run")
    run.add_argument("directory", type=Path)
    run.add_argument("--reference", type=Path, required=True)
    run.add_argument("--policy", type=Path, required=True)
    run.add_argument("--output-dir", type=Path, required=True)
    for name in ("inspect", "verify", "export", "benchmark-inspect", "benchmark-verify"):
        command = commands.add_parser(name)
        command.add_argument("directory", type=Path)
        if name == "export":
            command.add_argument("--format", choices=("json", "csv"), default="json")
            command.add_argument("--output", type=Path, required=True)
    benchmark = commands.add_parser("benchmark")
    benchmark.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "example":
            outputs = (args.reference_output, args.policy_output)
            if outputs[0].resolve() == outputs[1].resolve():
                raise ValueError("Reference and policy outputs must be distinct paths")
            for output in outputs:
                if output.exists() or output.is_symlink():
                    raise ValueError("Reference and policy outputs must both be absent")
            from .atmosphere_comparison_contract import example_reference, example_policy
            if args.profile == "moist":
                from .atmosphere_moist_contract import example_request
            else:
                from .atmosphere_contract import example_request
            reference = example_reference(example_request())
            save_new(args.reference_output, reference)
            save_new(args.policy_output, example_policy(reference))
            result = {"status": "created", "reference": str(args.reference_output), "policy": str(args.policy_output)}
        elif args.command == "run":
            result = comparison.run(args.directory, _regular_load(args.reference),
                                    _regular_load(args.policy), args.output_dir)
        elif args.command == "inspect":
            result = comparison.inspect(args.directory)
        elif args.command == "verify":
            result = comparison.verify_retained(args.directory)
        elif args.command == "export":
            export = comparison.export_json if args.format == "json" else comparison.export_csv
            result = export(args.directory, args.output)
        elif args.command == "benchmark":
            result = comparison.run_benchmark(args.output_dir)
        elif args.command == "benchmark-inspect":
            result = comparison.inspect_benchmark(args.directory)
        else:
            result = comparison.verify_benchmark(args.directory)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 2 if result.get("status") in {"REFUSE", "EXPAND"} or result.get("agreement_status") == "FAIL" else 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        print(json.dumps({"status": "REFUSE", "reason": str(exc)}), file=sys.stderr)
        return 1


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "compare":
        return _comparison_main(argv[1:])
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
            request = _regular_load(args.request)
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
