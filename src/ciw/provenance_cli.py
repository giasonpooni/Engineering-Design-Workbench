"""Create and inspect portable artifact provenance declarations."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .artifact_provenance import (
    boundary_review,
    declaration_from_spec,
    inspect_declaration,
    validate_declaration,
)
from .control_contracts import load, save_new


def main(argv=None):
    parser = argparse.ArgumentParser(prog="net provenance", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create")
    create.add_argument("spec", type=Path)
    create.add_argument("--output", type=Path, required=True)

    inspect = commands.add_parser("inspect")
    inspect.add_argument("declaration", type=Path)

    review = commands.add_parser("review")
    review.add_argument("parent", type=Path)
    review.add_argument("dependencies", nargs="*", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            value = declaration_from_spec(load(args.spec))
            save_new(args.output, value)
            print(json.dumps({
                "status": "created",
                "declaration_id": value["declaration_id"],
                "rights_adjudicated": False,
                "output": str(args.output),
            }))
            return 0
        if args.command == "inspect":
            print(json.dumps(inspect_declaration(load(args.declaration)), indent=2))
            return 0
        result = boundary_review(
            load(args.parent), [load(path) for path in args.dependencies])
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError, UnicodeError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
