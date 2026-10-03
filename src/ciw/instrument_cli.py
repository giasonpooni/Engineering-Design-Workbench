"""Inspect/advertise portable Notation Systems instruments without executing them."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .instrument_contracts import ingest_files


def main(argv=None):
    parser = argparse.ArgumentParser(prog="net instrument", description=__doc__)
    command = parser.add_subparsers(dest="command", required=True)
    inspect = command.add_parser("inspect")
    inspect.add_argument("manifest", type=Path)
    inspect.add_argument("--verification", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        value = ingest_files(args.manifest, args.verification)
        print(json.dumps(value, indent=2, allow_nan=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
