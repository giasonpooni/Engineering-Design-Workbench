"""Local retained typed hypergraph derivations; no numerical provider binding."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import hypergraph_rewrite as rewrite
from .control_contracts import load, save_new


def main(argv=None):
    parser = argparse.ArgumentParser(prog="net rewrite", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    example = commands.add_parser("example", help="Write a complete runnable declaration")
    example.add_argument("--profile", choices=("thermal", "ensemble"), default="thermal")
    example.add_argument("--output", required=True, type=Path)
    for name in ("run", "explore", "inspect", "verify", "orders"):
        command = commands.add_parser(name)
        command.add_argument("source", type=Path)
        if name != "inspect":
            command.add_argument("--output", required=True, type=Path)
        if name == "orders":
            command.add_argument("--left", required=True, help="Comma-separated rule IDs")
            command.add_argument("--right", required=True, help="Comma-separated rule IDs")
    args = parser.parse_args(argv)
    try:
        if args.command == "example":
            result = rewrite.example_request(args.profile)
        else:
            source = load(args.source)
            if args.command == "orders":
                result = rewrite.compare_orders(source, args.left.split(","), args.right.split(","))
            else:
                function = {"run": rewrite.run, "explore": rewrite.explore,
                            "inspect": rewrite.inspect, "verify": rewrite.verify}[args.command]
                result = function(source)
        if args.command != "inspect":
            save_new(args.output, result)
        # Full histories are retained in the output; keep terminal attention bounded.
        if args.command in {"run", "explore"}:
            summary = rewrite.inspect(result)
        elif args.command == "orders":
            summary = {key: value for key, value in result.items() if key != "histories"}
            summary["history_digests"] = [item["record_digest"] for item in result["histories"]]
        elif args.command == "example":
            summary = {"schema": result["schema"], "profile": args.profile, "output": str(args.output)}
        else:
            summary = result
        print(json.dumps(summary, indent=2, allow_nan=False))
        return 0 if result.get("status", "PASS") in {"COMPLETE", "PASS"} else 2
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        print(json.dumps({"status": "REFUSE", "message": str(exc) or type(exc).__name__}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
