"""Create and expand deterministic parameter programs over System Boards."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .control_contracts import load, save_new
from .parameter_program import (
    expand_program,
    inspect_program,
    program_from_spec,
    validate_sweep,
)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="net parameter", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create")
    create.add_argument("board", type=Path)
    create.add_argument("spec", type=Path)
    create.add_argument("--output", type=Path, required=True)

    expand = commands.add_parser("expand")
    expand.add_argument("board", type=Path)
    expand.add_argument("program", type=Path)
    expand.add_argument("--output", type=Path, required=True)

    inspect = commands.add_parser("inspect")
    inspect.add_argument("record", type=Path)
    args = parser.parse_args(argv)

    try:
        if args.command == "create":
            value = program_from_spec(load(args.board), load(args.spec))
            save_new(args.output, value)
            print(json.dumps({
                "status": "created", "program_id": value["program_id"],
                "candidates": len(value["generated_values"]),
                "optimization_performed": False,
                "output": str(args.output),
            }))
            return 0
        if args.command == "expand":
            value = expand_program(load(args.board), load(args.program))
            save_new(args.output, value)
            print(json.dumps({
                "status": "expanded", "candidates": len(value["candidates"]),
                "base_board_mutated": False, "provider_execution": False,
                "output": str(args.output),
            }))
            return 0
        value = load(args.record)
        if value.get("schema") == "ciw.parameter-program.v1":
            result = inspect_program(value)
        elif value.get("schema") == "ciw.parameter-sweep.v1":
            checked = validate_sweep(value)
            result = {
                "schema": "ciw.parameter-sweep-inspection.v1",
                "record_digest": checked["record_digest"],
                "candidates": len(checked["candidates"]),
                "target": checked["target"],
                "candidate_accepted": False,
                "provider_execution": False,
            }
        else:
            raise ValueError("Unsupported Parameter record schema")
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
