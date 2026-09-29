"""NET source selection. No selected code is imported or executed."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .computational_objects import _PERTURB, perturbation_request
from .computational_source import (
    MAX_SOURCE_BYTES, bind_source, capture_git, check_edit, compare_series,
    index_source, source_context, validate_capture,
)
from .control_contracts import load, save_new


def _stream(path: Path) -> list:
    value = load(path)
    if type(value) is list:
        return value
    from .control_checks import inspect_record
    inspect_record(value)
    if value.get("schema") != "ciw.observation-stream.v1":
        raise ValueError("Require an observation list or ciw.observation-stream.v1")
    return value["observations"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="net object", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("capture", "index"):
        command = commands.add_parser(name)
        command.add_argument("--repo-root", required=True, type=Path)
        command.add_argument("--repository", required=True, help="Declared repository label, not an authentication credential")
        command.add_argument("--revision", required=True, help="Local Git ref resolved to a commit; worktree edits are excluded")
        command.add_argument("--path", required=True)
        command.add_argument("--language", choices=["python", "rust", "cpp", "julia", "wgsl", "gdscript", "typescript"], default="python")
        command.add_argument("--output", required=True, type=Path)
        if name == "capture":
            command.add_argument("--symbol")
            command.add_argument("--line", type=int)
            command.add_argument("--span", type=int, nargs=2, metavar=("START", "END"))
            command.add_argument("--declaration", type=Path)
            command.add_argument("--editable", action="store_true", help="Propose a scope; grants no edit permission")
    for name in ("inspect", "context", "perturb", "compare", "check-edit", "view"):
        command = commands.add_parser(name)
        command.add_argument("capture", type=Path)
        command.add_argument("--output", type=Path, required=name == "view")
        if name == "perturb":
            command.add_argument("--dimension", required=True, choices=sorted(_PERTURB))
            command.add_argument("--change", required=True, type=Path, help="Data-only JSON change, not executable code")
        elif name == "compare":
            command.add_argument("left", type=Path)
            command.add_argument("right", type=Path)
            command.add_argument("--atol", required=True, type=float)
            command.add_argument("--rtol", type=float, default=0.0)
        elif name == "check-edit":
            command.add_argument("--candidate", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        exit_code = 0
        if args.command in {"capture", "index"}:
            snapshot = capture_git(args.repo_root, repository=args.repository, revision=args.revision,
                                   path=args.path, language=args.language)
            if args.command == "index":
                result = index_source(snapshot)
            else:
                result = bind_source(snapshot, {"symbol": args.symbol, "line": args.line, "span": args.span},
                    declaration=load(args.declaration) if args.declaration else None, editable=args.editable)
        else:
            capture = validate_capture(load(args.capture))
            if args.command == "view":
                from .computational_view import render_selection
                html = render_selection(capture)
                args.output.parent.mkdir(parents=True, exist_ok=True)
                with args.output.open("x", encoding="utf-8", newline="") as target:
                    target.write(html)
                print(json.dumps({"status": "created", "output": str(args.output)}))
                return 0
            if args.command in {"inspect", "context"}:
                result = source_context(capture)
            elif args.command == "perturb":
                result = perturbation_request(capture["object"], dimension=args.dimension, change=load(args.change))
            elif args.command == "check-edit":
                with args.candidate.open("rb") as stream:
                    candidate = stream.read(MAX_SOURCE_BYTES + 1)
                result = check_edit(capture, candidate)
                exit_code = 0 if result["status"] == "PASS" else 2
            else:
                result = compare_series(capture, _stream(args.left), _stream(args.right), atol=args.atol, rtol=args.rtol)
                exit_code = {"PASS": 0, "FAIL": 2, "INDETERMINATE": 3}[result["comparison"]["outcome"]["status"]]
        if args.output:
            save_new(args.output, result)
            print(json.dumps({"status": "created", "schema": result["schema"], "output": str(args.output)}))
        else:
            print(json.dumps(result, indent=2, allow_nan=False))
        return exit_code
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
