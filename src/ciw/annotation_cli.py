"""Create and inspect immutable human annotation records."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .annotations import (
    annotation_from_spec,
    annotation_stream,
    inspect_annotation,
    validate_annotation_stream,
)
from .control_contracts import load, save_new


def main(argv=None):
    parser = argparse.ArgumentParser(prog="net annotation", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create")
    create.add_argument("spec", type=Path)
    create.add_argument("--output", type=Path, required=True)

    inspect = commands.add_parser("inspect")
    inspect.add_argument("annotation", type=Path)

    timeline = commands.add_parser("timeline")
    timeline.add_argument("annotations", nargs="+", type=Path)
    timeline.add_argument("--output", type=Path, required=True)

    timeline_inspect = commands.add_parser("inspect-timeline")
    timeline_inspect.add_argument("timeline", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            value = annotation_from_spec(load(args.spec))
            save_new(args.output, value)
            print(json.dumps({
                "status": "created",
                "record_digest": value["record_digest"],
                "canonical_evidence": False,
                "canonical_state": False,
                "output": str(args.output),
            }))
            return 0
        if args.command == "inspect":
            print(json.dumps(inspect_annotation(load(args.annotation)), indent=2))
            return 0
        if args.command == "timeline":
            value = annotation_stream([load(path) for path in args.annotations])
            save_new(args.output, value)
            print(json.dumps({
                "status": "created",
                "schema": value["schema"],
                "annotations": len(value["annotations"]),
                "output": str(args.output),
            }))
            return 0
        value = validate_annotation_stream(load(args.timeline))
        print(json.dumps({
            "schema": "ciw.annotation-stream-inspection.v1",
            "record_digest": value["record_digest"],
            "annotations": len(value["annotations"]),
            "first_authored_at": value["annotations"][0]["authored_at"],
            "last_authored_at": value["annotations"][-1]["authored_at"],
            "canonical_evidence": False,
            "canonical_state": False,
            "verification": False,
            "execution_authority": False,
        }, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
