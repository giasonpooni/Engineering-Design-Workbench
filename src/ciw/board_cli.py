"""Create, inspect and compile the parameterized System Board."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .board_morphisms import bind_board, compile_bound_board
from .control_contracts import load, save_new
from .control_plane import builtin_registry
from .semantic_capabilities import builtin_semantic_registry
from .system_board import board_from_spec, compile_board, inspect_board, validate_compilation


def main(argv=None):
    parser = argparse.ArgumentParser(prog="net board", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create")
    create.add_argument("spec", type=Path)
    create.add_argument("--output", type=Path, required=True)

    inspect = commands.add_parser("inspect")
    inspect.add_argument("record", type=Path)

    compile_cmd = commands.add_parser("compile")
    compile_cmd.add_argument("board", type=Path)
    compile_cmd.add_argument("--output", type=Path, required=True)

    bind = commands.add_parser("bind-morphisms")
    bind.add_argument("board", type=Path)
    bind.add_argument("registry", type=Path)
    bind.add_argument("spec", type=Path)
    bind.add_argument("--output", type=Path, required=True)

    bound = commands.add_parser("compile-bound")
    bound.add_argument("board", type=Path)
    bound.add_argument("registry", type=Path)
    bound.add_argument("binding", type=Path)
    bound.add_argument("--output", type=Path, required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            value = board_from_spec(load(args.spec))
            save_new(args.output, value)
            print(json.dumps({
                "status": "created", "board_id": value["board_id"],
                "record_digest": value["record_digest"],
                "execution_authority": False, "output": str(args.output),
            }))
            return 0
        if args.command in {"bind-morphisms", "compile-bound"}:
            semantic = builtin_semantic_registry(builtin_registry(bind=True))
            board, registry = load(args.board), load(args.registry)
            if args.command == "bind-morphisms":
                value = bind_board(board, registry, semantic, load(args.spec))
            else:
                value = compile_bound_board(board, load(args.binding), registry, semantic)
            save_new(args.output, value)
            print(json.dumps({"status": "created", "schema": value["schema"],
                              "record_digest": value["record_digest"],
                              "provider_execution": False, "execution_authority": False,
                              "output": str(args.output)}))
            return 0
        if args.command == "compile":
            concrete = builtin_registry(bind=True)
            semantic = builtin_semantic_registry(concrete)
            value = compile_board(load(args.board), semantic)
            save_new(args.output, value)
            print(json.dumps({
                "status": "compiled", "board_id": value["board_id"],
                "experiment_id": value["semantic_compilation"]["experiment"]["experiment_id"],
                "engine_selected_by_board": False, "provider_execution": False,
                "output": str(args.output),
            }))
            return 0
        value = load(args.record)
        if value.get("schema") == "ciw.system-board.v1":
            result = inspect_board(value)
        elif value.get("schema") == "ciw.board-compilation.v1":
            checked = validate_compilation(value)
            result = {
                "schema": "ciw.board-compilation-inspection.v1",
                "record_digest": checked["record_digest"], "board_id": checked["board_id"],
                "semantic_nodes": len(checked["semantic_graph"]["nodes"]),
                "concrete_nodes": len(checked["semantic_compilation"]["experiment"]["nodes"]),
                "ignored_nonexecution_edges": checked["ignored_nonexecution_edges"],
                "engine_selected_by_board": False, "provider_execution": False,
            }
        else:
            raise ValueError("Unsupported Board record schema")
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
