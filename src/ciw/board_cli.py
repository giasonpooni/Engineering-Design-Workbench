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
from .board_visual import apply_visual_edit, visual_edit_to_needle_plan, write_html


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
    render = commands.add_parser("render")
    render.add_argument("board", type=Path)
    render.add_argument("--output", type=Path, required=True)

    apply_edit = commands.add_parser("apply-edit")
    apply_edit.add_argument("board", type=Path)
    apply_edit.add_argument("spec", type=Path)
    apply_edit.add_argument("--output", type=Path, required=True)

    plan_edit = commands.add_parser("plan-edit")
    plan_edit.add_argument("board", type=Path)
    plan_edit.add_argument("spec", type=Path)
    plan_edit.add_argument("baseline_graph_run", type=Path)
    plan_edit.add_argument("--output", type=Path, required=True)

    view = commands.add_parser("view")
    view.add_argument("board", type=Path)
    view.add_argument("--output", type=Path, required=True)
    edit = commands.add_parser("edit")
    edit.add_argument("board", type=Path)
    edit.add_argument("request", type=Path)
    edit.add_argument("--output", type=Path, required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("board", type=Path)
    serve.add_argument("--source", type=Path)
    serve.add_argument("--output-dir", type=Path, required=True)
    serve.add_argument("--port", type=int, default=0)
    serve.add_argument("--allow-run", action="store_true")
    serve.add_argument("--morphism-registry", type=Path)
    serve.add_argument("--intervention-binding", type=Path)
    demo = commands.add_parser("demo")
    demo.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command in {"view", "edit", "serve", "demo"}:
            from .visual_board import write_html as write_live_html, demo_board, apply_parameter_edit
            if args.command == "demo":
                from .instruments import make_demo_run
                args.output_dir.mkdir(parents=True, exist_ok=False)
                board = demo_board()
                concrete = builtin_registry(bind=True)
                semantic = builtin_semantic_registry(concrete)
                from .visual_representation_gate import demo_binding, demo_registry
                morphism_registry = demo_registry(semantic)
                intervention_binding = demo_binding(board, morphism_registry, semantic)
                save_new(args.output_dir / "board.json", board)
                save_new(args.output_dir / "source.json", make_demo_run())
                save_new(args.output_dir / "morphism-registry.json", morphism_registry)
                save_new(args.output_dir / "intervention-binding.json", intervention_binding)
                write_live_html(args.output_dir / "board.html", board)
                print(json.dumps({"status": "created", "output_dir": str(args.output_dir),
                                  "synthetic": True, "scientific_gate_fixture": True,
                                  "provider_execution": False}))
            elif args.command == "view":
                write_live_html(args.output, load(args.board))
                print(json.dumps({"status": "created", "output": str(args.output), "provider_execution": False}))
            elif args.command == "edit":
                semantic = builtin_semantic_registry(builtin_registry(bind=True))
                value = apply_parameter_edit(load(args.board), load(args.request), semantic)
                save_new(args.output, value)
                print(json.dumps({"status": "compiled-candidate", "output": str(args.output),
                                  "candidate_board_ref": value["candidate_board"]["record_digest"],
                                  "dependency_closure": value["dependency_closure"], "provider_execution": False}))
            else:
                from .visual_board_server import BoardWorkbench, make_server
                if (args.morphism_registry is None) != (args.intervention_binding is None):
                    raise ValueError("Supply both --morphism-registry and --intervention-binding")
                workbench = BoardWorkbench(
                    load(args.board), args.output_dir,
                    source=load(args.source) if args.source else None,
                    allow_run=args.allow_run,
                    morphism_registry=(load(args.morphism_registry) if args.morphism_registry else None),
                    intervention_binding=(load(args.intervention_binding) if args.intervention_binding else None),
                )
                server = make_server(workbench, port=args.port)
                print(json.dumps({"status": "serving", "url": server.board_url,
                                  "execution_enabled": args.allow_run, "loopback_only": True}), flush=True)
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    pass
                finally:
                    server.server_close()
            return 0
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
        if args.command == "render":
            board = load(args.board)
            write_html(args.output, board)
            print(json.dumps({
                "status": "created", "output": str(args.output),
                "network": "disabled", "provider_execution": False,
                "execution_authority": False,
            }))
            return 0
        if args.command == "apply-edit":
            candidate, summary = apply_visual_edit(load(args.board), load(args.spec))
            save_new(args.output, candidate)
            print(json.dumps({**summary, "status": "candidate_created", "output": str(args.output)}))
            return 0
        if args.command == "plan-edit":
            concrete = builtin_registry(bind=True)
            semantic = builtin_semantic_registry(concrete)
            plan = visual_edit_to_needle_plan(
                load(args.board), load(args.spec), load(args.baseline_graph_run), semantic
            )
            save_new(args.output, plan)
            print(json.dumps({
                "status": "planned", "needle_id": plan["needle_id"],
                "target": plan["target"], "execution_authority": False,
                "output": str(args.output),
            }))
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
