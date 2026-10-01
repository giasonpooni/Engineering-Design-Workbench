"""Self-contained local System Board visual editor.

The browser is a projection/editing surface over a sealed ciw.system-board.v1.
It never executes providers, mutates the base Board, admits canonical state, or
performs verification. Visual edits are exported as bounded specs and must be
revalidated by Python before a candidate Board is sealed.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from hashlib import sha256
from importlib.resources import files
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

from .control_contracts import content_ref, keys, text
from .system_board import board_from_spec, validate_board

MAX_HTML_BYTES = 8 * 1024 * 1024
EDIT_SCHEMA = "ciw.board-visual-edit-spec.v1"


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _board_spec(board: dict, *, board_id: str, title: str) -> dict:
    return {
        "board_id": board_id,
        "title": title,
        "model_id": board["model_id"],
        "nodes": deepcopy(board["nodes"]),
        "edges": deepcopy(board["edges"]),
        "groups": deepcopy(board["groups"]),
        "board_invariants": deepcopy(board["board_invariants"]),
        "notes": board["notes"],
    }


def _replacement_type(parameter: dict, value: Any) -> Any:
    kind = parameter["type"]
    if kind == "NUMBER":
        if type(value) not in (int, float) or isinstance(value, bool):
            raise ValueError("Visual NUMBER edit requires a numerical replacement")
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("Visual NUMBER edit requires a finite replacement")
        return result
    if kind == "INTEGER":
        if type(value) is not int or isinstance(value, bool):
            raise ValueError("Visual INTEGER edit requires an integer replacement")
        return value
    if kind == "STRING":
        return text(value)
    if type(value) is not bool:
        raise ValueError("Visual BOOLEAN edit requires true/false")
    return value


def validate_edit_spec(board: dict, spec: dict) -> dict:
    """Validate a browser-generated edit spec against the exact sealed Board."""
    board = validate_board(board)
    keys(spec, {"schema", "edit_id", "board_ref", "target", "replacement", "notes"})
    if spec["schema"] != EDIT_SCHEMA:
        raise ValueError("Wrong visual Board edit-spec schema")
    edit_id = text(spec["edit_id"])
    if spec["board_ref"] != board["record_digest"]:
        raise ValueError("Visual edit targets a different Board identity")
    content_ref(spec["board_ref"])
    target = spec["target"]
    keys(target, {"node_id", "parameter"})
    node_id = text(target["node_id"])
    parameter_name = text(target["parameter"])
    nodes = {node["node_id"]: node for node in board["nodes"]}
    if node_id not in nodes:
        raise ValueError("Visual edit target node is absent from Board")
    parameters = nodes[node_id]["parameters"]
    if parameter_name not in parameters:
        raise ValueError("Visual edit target parameter is absent from Board node")
    parameter = parameters[parameter_name]
    if parameter["exposed"] is not True:
        raise ValueError("Visual editor may only stage exposed Board parameters")
    replacement = _replacement_type(parameter, spec["replacement"])
    notes = spec["notes"]
    if type(notes) is not str or len(notes) > 4096:
        raise ValueError("Visual edit notes must be bounded text")
    return {
        "schema": EDIT_SCHEMA,
        "edit_id": edit_id,
        "board_ref": board["record_digest"],
        "target": {"node_id": node_id, "parameter": parameter_name},
        "replacement": replacement,
        "notes": notes,
    }


def apply_visual_edit(board: dict, spec: dict) -> tuple[dict, dict]:
    """Create an immutable candidate Board from one validated visual edit.

    Board reconstruction intentionally delegates parameter type/domain checking to
    board_from_spec, so the browser can never weaken the authoritative Board rules.
    """
    board = validate_board(board)
    checked = validate_edit_spec(board, spec)
    before = deepcopy(board)
    target = checked["target"]
    candidate_spec = _board_spec(
        board,
        board_id=f"{board['board_id']}.visual.{checked['edit_id']}",
        title=(
            f"{board['title']} / visual edit "
            f"{target['node_id']}.{target['parameter']}={checked['replacement']}"
        ),
    )
    node = next(item for item in candidate_spec["nodes"] if item["node_id"] == target["node_id"])
    node["parameters"][target["parameter"]]["value"] = deepcopy(checked["replacement"])
    candidate = board_from_spec(candidate_spec)
    if board != before:
        raise AssertionError("Visual edit mutated the base Board")
    summary = {
        "schema": "ciw.board-visual-edit-summary.v1",
        "edit_id": checked["edit_id"],
        "base_board_ref": board["record_digest"],
        "candidate_board_ref": candidate["record_digest"],
        "target": deepcopy(target),
        "before": next(
            item for item in board["nodes"] if item["node_id"] == target["node_id"]
        )["parameters"][target["parameter"]]["value"],
        "replacement": deepcopy(checked["replacement"]),
        "base_board_mutated": False,
        "candidate_accepted": False,
        "provider_execution": False,
        "canonical_state_mutated": False,
        "execution_authority": False,
    }
    return candidate, summary


def render_html(board: dict) -> bytes:
    """Validate and embed a sealed Board in a no-network local editor."""
    board = validate_board(board)
    assets = files("ciw").joinpath("web")
    template = assets.joinpath("system_board.html").read_text(encoding="utf-8")
    css = assets.joinpath("system_board.css").read_text(encoding="utf-8")
    js = "\n".join(\n        assets.joinpath(name).read_text(encoding="utf-8")\n        for name in (\n            "system_board_core.js",\n            "system_board_graph.js",\n            "system_board_inspector.js",\n            "system_board_init.js",\n        )\n    )\n
    def digest(source: str) -> str:
        return base64.b64encode(sha256(source.encode("utf-8")).digest()).decode("ascii")

    csp = (
        "default-src 'none'; base-uri 'none'; form-action 'none'; connect-src 'none'; "
        f"script-src 'sha256-{digest(js)}'; style-src 'sha256-{digest(css)}'; img-src data:"
    )
    replacements = {
        "__CSP__": csp,
        "__STYLE__": css,
        "__SCRIPT__": js,
        "__DATA__": base64.b64encode(_canonical(board)).decode("ascii"),
    }
    for marker, replacement in replacements.items():
        if template.count(marker) != 1:
            raise ValueError("Packaged System Board viewer template is inconsistent")
        template = template.replace(marker, replacement)
    raw = template.encode("utf-8")
    if len(raw) > MAX_HTML_BYTES:
        raise ValueError("System Board viewer exceeds its HTML byte budget")
    return raw


def write_html(path: Path, board: dict) -> None:
    raw = render_html(board)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".net-board-", dir=path.parent) as directory:
        staged = Path(directory) / "board.html"
        with staged.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(staged, path)


def main(argv: list[str] | None = None) -> int:
    import argparse

    from .control_contracts import load, save_new

    parser = argparse.ArgumentParser(prog="net board-visual", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    render = commands.add_parser("render")
    render.add_argument("board", type=Path)
    render.add_argument("--output", type=Path, required=True)

    apply_edit = commands.add_parser("apply-edit")
    apply_edit.add_argument("board", type=Path)
    apply_edit.add_argument("spec", type=Path)
    apply_edit.add_argument("--output", type=Path, required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "render":
            board = load(args.board)
            write_html(args.output, board)
            print(json.dumps({
                "status": "created",
                "output": str(args.output),
                "network": "disabled",
                "provider_execution": False,
                "execution_authority": False,
            }))
            return 0

        candidate, summary = apply_visual_edit(load(args.board), load(args.spec))
        save_new(args.output, candidate)
        print(json.dumps({**summary, "status": "candidate_created", "output": str(args.output)}))
        return 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
