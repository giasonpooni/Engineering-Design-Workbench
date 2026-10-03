"""Visual notation over the existing System Board; never a second state owner.

View state only references graph identities. Parameter requests reuse Parameter
Program and Board compilation. Numerical execution stays in ordinary Session /
Needle and is not performed by these projection/edit functions.
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
import tempfile

from .control_contracts import detached, keys, record, text
from .core.identities import content_identity
from .needle import dependency_closure
from .operations.runner import check_seal
from .parameter_program import expand_program, program_from_spec
from .semantic_capabilities import SemanticRegistry
from .system_board import board_from_spec, compile_board, validate_board

MODES = {
    "ALL": None,
    "DEPENDENCY": {"DATAFLOW", "DEPENDENCY"},
    "SCIENTIFIC": {"SEMANTIC", "SPATIAL", "TEMPORAL", "SCALE"},
    "AUTHORITY": {"AUTHORITY"},
}
VIEW_CLAIMS = {"view_only": True, "board_mutated": False, "provider_execution": False,
               "state_admission": False, "execution_authority": False}
EDIT_CLAIMS = {"uses_parameter_program": True, "uses_board_compiler": True,
               "base_board_mutated": False, "candidate_accepted": False,
               "provider_execution": False, "state_admission": False,
               "execution_authority": False}


def default_view(board: dict) -> dict:
    board = validate_board(board)
    return {"board_ref": board["record_digest"], "mode": "ALL", "collapsed_groups": [],
            "selected_node_id": None, "positions": {},
            "viewport": {"x": 0, "y": 0, "zoom": 1}}


def view_from_spec(board: dict, spec: dict) -> dict:
    board = validate_board(board)
    keys(spec, {"board_ref", "mode", "collapsed_groups", "selected_node_id", "positions", "viewport"})
    if spec["board_ref"] != board["record_digest"]:
        raise ValueError("View targets a different Board revision")
    if type(spec["mode"]) is not str or spec["mode"] not in MODES:
        raise ValueError("Unknown view mode")
    groups = {g["group_id"] for g in board["groups"]}
    nodes = {n["node_id"] for n in board["nodes"]}
    collapsed = spec["collapsed_groups"]
    if (type(collapsed) is not list or len(collapsed) > len(groups)
            or any(type(g) is not str or g not in groups for g in collapsed)
            or len(set(collapsed)) != len(collapsed)):
        raise ValueError("Collapsed groups must be distinct existing group identities")
    selected = spec["selected_node_id"]
    if selected is not None and (type(selected) is not str or selected not in nodes):
        raise ValueError("Selected node is not in this Board")
    positions = spec["positions"]
    valid_keys = {"node:" + n for n in nodes} | {"group:" + g for g in groups}
    if type(positions) is not dict or not set(positions) <= valid_keys:
        raise ValueError("Layout positions must reference exact node/group identities")
    for point in positions.values():
        keys(point, {"x", "y"})
        _bounded_numbers(point, 100000)
    keys(spec["viewport"], {"x", "y", "zoom"})
    _bounded_numbers(spec["viewport"], 100000)
    if not 0.2 <= spec["viewport"]["zoom"] <= 3:
        raise ValueError("View zoom must be within 0.2..3")
    return record("board-view", specification=detached(spec), claims=VIEW_CLAIMS)


def _bounded_numbers(value: dict, bound: float) -> None:
    for n in value.values():
        if type(n) not in (int, float) or not math.isfinite(n) or abs(n) > bound:
            raise ValueError("View coordinates must be finite bounded numbers")


def validate_view(value: dict, board: dict) -> dict:
    keys(value, {"schema", "record_digest", "specification", "claims"})
    check_seal(value)
    if value != view_from_spec(board, value["specification"]):
        raise ValueError("View differs from recomputed projection contract")
    return detached(value)


def project_scene(board: dict, view: dict) -> dict:
    """A display quotient with complete membership/edge provenance, not execution."""
    board = validate_board(board)
    view = validate_view(view, board)
    spec = view["specification"]
    groups = {g["group_id"]: g for g in board["groups"]}
    owner = {n: g["group_id"] for g in board["groups"] for n in g["node_ids"]}
    collapsed = set(spec["collapsed_groups"])

    def representative(group_id):
        chosen = None
        while group_id is not None:
            if group_id in collapsed:
                chosen = group_id  # outermost collapsed ancestor wins
            group_id = groups[group_id]["parent_group_id"]
        return chosen

    items = {}
    node_to_visual = {}
    for node in board["nodes"]:
        parent = representative(owner.get(node["node_id"]))
        visual = "group:" + parent if parent is not None else "node:" + node["node_id"]
        node_to_visual[node["node_id"]] = visual
        if visual not in items:
            items[visual] = {"visual_id": visual, "kind": "GROUP" if parent is not None else "NODE",
                             "source_id": parent if parent is not None else node["node_id"],
                             "label": groups[parent]["label"] if parent is not None else node["label"],
                             "node_ids": []}
        items[visual]["node_ids"].append(node["node_id"])
    # Empty groups are inspectable; collapsing does not delete their identity.
    for gid in spec["collapsed_groups"]:
        if representative(gid) == gid and "group:" + gid not in items:
            items["group:" + gid] = {"visual_id": "group:" + gid, "kind": "GROUP",
                                     "source_id": gid, "label": groups[gid]["label"], "node_ids": []}
    edges, hidden, filtered = [], [], []
    allowed = MODES[spec["mode"]]
    for edge in board["edges"]:
        if allowed is not None and edge["kind"] not in allowed:
            filtered.append(edge["edge_id"])
            continue
        a, b = node_to_visual[edge["source_node_id"]], node_to_visual[edge["target_node_id"]]
        if a == b:
            hidden.append(edge["edge_id"])
        else:
            edges.append({"edge_id": edge["edge_id"], "kind": edge["kind"],
                          "source_visual_id": a, "target_visual_id": b,
                          "source_node_id": edge["source_node_id"], "target_node_id": edge["target_node_id"]})
    return {"schema": "ciw.board-scene.v1", "board_ref": board["record_digest"],
            "view_ref": view["record_digest"], "items": list(items.values()),
            "node_to_visual": node_to_visual, "edges": edges,
            "hidden_internal_edge_ids": hidden, "filtered_edge_ids": filtered,
            "claims": deepcopy(VIEW_CLAIMS)}


def apply_parameter_edit(board: dict, request: dict, semantic: SemanticRegistry) -> dict:
    """Same notation/validator entrypoint for browser, CLI or a calling program."""
    board = validate_board(board)
    keys(request, {"schema", "base_board_ref", "node_id", "parameter", "replacement"})
    if request["schema"] != "ciw.board-parameter-edit.v1":
        raise ValueError("Only an explicit Board parameter edit is supported")
    if request["base_board_ref"] != board["record_digest"]:
        raise ValueError("Edit targets a stale or different Board revision")
    node_id, parameter = text(request["node_id"]), text(request["parameter"])
    node = next((n for n in board["nodes"] if n["node_id"] == node_id), None)
    if node is None or node["kind"] != "OPERATION":
        raise ValueError("V1 edits target an existing OPERATION node")
    if parameter not in node["parameters"]:
        raise ValueError("Unknown Board parameter")
    if request["replacement"] == node["parameters"][parameter]["value"]:
        raise ValueError("Replacement must differ from the baseline value")
    request = detached(request)
    program = program_from_spec(board, {
        "program_id": "visual-edit-" + content_identity(request)[7:31],
        "board_ref": board["record_digest"],
        "target": {"node_id": node_id, "parameter": parameter},
        "generator": {"kind": "VALUES", "values": [request["replacement"]],
                      "start": None, "stop": None, "count": None, "base": None}, "notes": "",
    })
    sweep = expand_program(board, program)
    candidate = sweep["candidates"][0]["board"]
    compilation = compile_board(candidate, semantic)
    baseline = compile_board(board, semantic)
    affected = dependency_closure(baseline["semantic_compilation"]["experiment"], node_id)
    return record("board-edit-preview", request=request, base_board_ref=board["record_digest"],
                  program=program, candidate_board=candidate, compilation=compilation,
                  dependency_closure=affected,
                  unaffected_operation_ids=[n["node_id"] for n in board["nodes"]
                                            if n["kind"] == "OPERATION" and n["node_id"] not in affected],
                  claims=EDIT_CLAIMS)


def validate_edit(value: dict, board: dict, semantic: SemanticRegistry) -> dict:
    keys(value, {"schema", "record_digest", "request", "base_board_ref", "program", "candidate_board",
                 "compilation", "dependency_closure", "unaffected_operation_ids", "claims"})
    check_seal(value)
    if value != apply_parameter_edit(board, value["request"], semantic):
        raise ValueError("Edit preview differs from recomputed candidate and compilation")
    return detached(value)


def render_html(board: dict | None, *, live=False) -> bytes:
    """Reuse the existing mathematical-viewer pattern: inert data + hashed assets."""
    if board is not None:
        board = validate_board(board)
    if live and board is not None:
        raise ValueError("Live HTML must not expose Board data before authentication")
    assets = files("ciw").joinpath("web")
    template = assets.joinpath("system_board.html").read_text(encoding="utf-8")
    css = assets.joinpath("system_board.css").read_text(encoding="utf-8")
    js = assets.joinpath("system_board.js").read_text(encoding="utf-8")
    hashed = lambda s: base64.b64encode(sha256(s.encode()).digest()).decode("ascii")
    csp = ("default-src 'none'; base-uri 'none'; form-action 'none'; "
           + ("connect-src 'self'; " if live else "connect-src 'none'; ")
           + f"script-src 'sha256-{hashed(js)}'; style-src 'sha256-{hashed(css)}'; img-src data:")
    payload = {"live": live, "board": board, "view": default_view(board) if board is not None else None}
    for marker, value in {"__CSP__": csp, "__STYLE__": css, "__SCRIPT__": js,
                          "__DATA__": base64.b64encode(json.dumps(payload, allow_nan=False).encode()).decode()}.items():
        if template.count(marker) != 1:
            raise ValueError("Packaged Board template is inconsistent")
        template = template.replace(marker, value)
    raw = template.encode()
    if len(raw) > 12 * 1024 * 1024:
        raise ValueError("Board HTML exceeds byte budget")
    return raw


def write_html(path: Path, board: dict) -> None:
    raw = render_html(board)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".net-board-", dir=path.parent) as tmp:
        staged = Path(tmp) / "board.html"
        with staged.open("xb") as f:
            f.write(raw); f.flush(); os.fsync(f.fileno())
        os.link(staged, path)


def demo_board() -> dict:
    """An actual existing oscillator workload, not an unimplemented plant model."""
    scale = {"length_m": None, "time_s": None, "energy_j": None, "label": "retained signal"}
    socket = {"socket_id": "result", "port": {"schema": "ciw.operation-result.v1", "unit": None, "frame": None},
              "scale": scale, "uncertainty_semantics": "UNKNOWN", "provenance_required": True}
    def node(nid, label, kind, capability=None, channel=None):
        return {"node_id": nid, "label": label, "kind": kind, "semantic_capability": capability,
                "sockets": {"inputs": [], "outputs": [deepcopy(socket)] if capability else []},
                "parameters": {} if channel is None else {"channel": {"type": "STRING", "value": channel,
                    "unit": None, "exposed": True, "domain": {"kind": "ENUM", "minimum": None,
                    "maximum": None, "values": ["q", "v", "energy"], "log_base": None}}},
                "resources": ["cpu"] if capability else [], "inspection": False, "scale": deepcopy(scale),
                "provenance_refs": [], "authority_requirements": ["read:recording"] if capability else [],
                "invariants": ["source evidence identity retained"],
                "validity_conditions": ["Synthetic analytic evidence; physical validation unresolved"]}
    def edge(eid, a, b, kind):
        return {"edge_id": eid, "kind": kind, "source_node_id": a, "target_node_id": b,
                "source_socket": None, "target_socket": None, "relation": "declared_" + kind.lower(), "metadata": {}}
    return board_from_spec({
        "board_id": "visual-oscillator-v1", "title": "Oscillator investigation",
        "model_id": "analytic-damped-oscillator.v1",
        "nodes": [node("recording", "Retained recording", "STATE"),
                  node("model", "Damped oscillator", "MODEL"),
                  node("signal", "Time-series representation", "REPRESENTATION"),
                  node("statistics", "Signal statistics", "OPERATION", "analysis.statistics.v1", "q"),
                  node("spectrum", "Periodogram", "OPERATION", "analysis.spectrum.v1", "q"),
                  node("energy_statistics", "Energy statistics", "OPERATION", "analysis.statistics.v1", "energy")],
        "edges": [edge("signal-dependency", "statistics", "spectrum", "DEPENDENCY"),
                  edge("evidence-signal", "recording", "signal", "SEMANTIC"),
                  edge("model-signal", "model", "signal", "SEMANTIC"),
                  edge("signal-analysis", "signal", "statistics", "SEMANTIC")],
        "groups": [{"group_id": "instrument", "label": "Oscillator instrument", "parent_group_id": None,
                    "node_ids": ["recording", "model", "signal"]},
                   {"group_id": "analysis", "label": "Signal analysis", "parent_group_id": "instrument",
                    "node_ids": ["statistics", "spectrum"]},
                   {"group_id": "energy", "label": "Energy branch", "parent_group_id": "instrument",
                    "node_ids": ["energy_statistics"]}],
        "board_invariants": ["View changes never modify Board identity", "Dependency is not physical causality"],
        "notes": "Synthetic oscillator. Groups are existing Board hierarchy, not container contracts."
    })
