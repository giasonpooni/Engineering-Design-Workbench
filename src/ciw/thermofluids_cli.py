"""Declared thermofluid reference tools with retained results and explicit replay."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import thermofluids_models as models, thermofluids_workflow as workflow
from .control_contracts import load, save_new


def main(argv=None):
    parser = argparse.ArgumentParser(prog="net thermofluids", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("catalog", help="List five bounded profiles and their limits")
    example = commands.add_parser("example", help="Write an editable synthetic request in SI units")
    example.add_argument("--profile", choices=list(models.PROFILES), required=True)
    example.add_argument("--output", type=Path, required=True)
    for name in ("run", "inspect", "verify", "replay"):
        command = commands.add_parser(name)
        command.add_argument("source", type=Path)
        if name != "inspect":
            command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "catalog":
            result = workflow.catalog()
        elif args.command == "example":
            result = models.example_request(args.profile)
        else:
            result = getattr(workflow, args.command)(load(args.source))
        if hasattr(args, "output"):
            save_new(args.output, result)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 2 if result.get("status") in {"REFUSE", "FAIL"} else 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        print(json.dumps({"status": "REFUSE", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
