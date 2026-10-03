"""Author, preview, retain and replay bounded procedural graphics programs."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys

from .control_contracts import json_tree, save_new
from .session import loads_json


def _load(path: Path):
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError("Graphics requests must be regular files without symlinks")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("Graphics input changed to a nonregular file")
        raw = stream.read(64 * 1024 + 1)
    if not raw or len(raw) > 64 * 1024:
        raise ValueError("Graphics request exceeds the 64 KiB input budget or is empty")
    value = loads_json(raw.decode("utf-8"))
    json_tree(value)
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(prog="net graphics", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    example = commands.add_parser("example")
    example.add_argument("--profile", choices=("sphere", "gyroid", "wave", "parametric", "texture"), default="gyroid")
    example.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run")
    run.add_argument("request", type=Path)
    run.add_argument("--output-dir", type=Path, required=True)
    for name in ("inspect", "verify", "replay", "export"):
        command = commands.add_parser(name)
        command.add_argument("directory", type=Path)
        if name == "replay":
            command.add_argument("--output-dir", type=Path, required=True)
        elif name == "export":
            command.add_argument("--format", choices=("obj", "json", "png"), default="obj")
            command.add_argument("--output", type=Path, required=True)
    server = commands.add_parser("serve", help="Open a local editor with transient preview and retained run history")
    server.add_argument("--output-dir", type=Path, required=True)
    server.add_argument("--port", type=int, default=8788)
    args = parser.parse_args(argv)
    try:
        from . import procedural_workflow as workflow
        if args.command == "example":
            if args.profile == "parametric":
                from .procedural_surface import example_surface
                request = example_surface()
            elif args.profile == "texture":
                from .procedural_texture import example_texture
                request = example_texture()
            else:
                from .procedural_contract import example_request
                request = example_request(args.profile)
            save_new(args.output, request)
            result = {"status": "created", "output": str(args.output)}
        elif args.command == "run":
            result = workflow.run(_load(args.request), args.output_dir)
        elif args.command == "inspect":
            result = workflow.inspect(args.directory)
        elif args.command == "verify":
            result = workflow.verify_retained(args.directory)
        elif args.command == "replay":
            result = workflow.replay(args.directory, args.output_dir)
        elif args.command == "export":
            export = {"obj": workflow.export_obj, "json": workflow.export_json, "png": workflow.export_png}[args.format]
            result = export(args.directory, args.output)
        else:
            from .procedural_server import serve
            serve(args.output_dir, args.port)
            return 0
        print(json.dumps(result, indent=2, allow_nan=False))
        return 2 if result.get("status") in {"REFUSE", "FAIL"} or result.get("verification_status") == "FAIL" else 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        print(json.dumps({"status": "REFUSE", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
