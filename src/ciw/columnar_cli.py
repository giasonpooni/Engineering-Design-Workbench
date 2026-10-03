"""Optional Apache Arrow IPC / Parquet representation for retained observations."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .columnar import export_file, import_file


def main(argv=None):
    parser = argparse.ArgumentParser(prog="net columnar", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export")
    export.add_argument("stream", type=Path)
    export.add_argument("--format", choices=("ipc", "parquet"), required=True)
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--artifact", type=Path, required=True)
    export.add_argument("--experiment-id", required=True)
    load = commands.add_parser("import")
    load.add_argument("payload", type=Path)
    load.add_argument("--format", choices=("ipc", "parquet"), required=True)
    load.add_argument("--artifact", type=Path, required=True)
    load.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        value = (export_file(args.stream, format=args.format, output=args.output,
                             artifact_path=args.artifact, experiment_id=args.experiment_id)
                 if args.command == "export"
                 else import_file(args.payload, format=args.format,
                                  artifact_path=args.artifact, output=args.output))
        print(json.dumps({
            "status": "completed",
            "schema": value["schema"],
            "record_digest": value["record_digest"],
            "canonical_evidence": False if args.command == "export" else "source_stream_reconstructed",
        }))
        return 0
    except (OSError, ValueError, TypeError, KeyError, UnicodeError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
