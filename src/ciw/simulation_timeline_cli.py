"""Build or recheck an offline index of selected, existing Session evidence."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from .simulation_timeline import build, inspect_bundle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="net simulation timeline", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    cmd = commands.add_parser("build", help="Read selected workspaces/captures/reports; create an offline timeline")
    cmd.add_argument("--workspace", type=Path, action="append", default=[])
    cmd.add_argument("--capture", type=Path, action="append", default=[])
    cmd.add_argument("--report", type=Path, action="append", default=[])
    cmd.add_argument("--output-dir", type=Path, required=True)
    cmd = commands.add_parser("inspect", help="Rebuild and compare every bundle artifact without providers")
    cmd.add_argument("directory", type=Path)
    cmd.add_argument("--expected-manifest-sha256")
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            result = build(args.output_dir, workspaces=args.workspace, captures=args.capture, reports=args.report)
        else:
            result = inspect_bundle(args.directory, expected_manifest_sha256=args.expected_manifest_sha256)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
