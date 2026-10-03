"""Parameterized System Board V1.

The Board is a typed, parameterized relational graph above semantic capabilities
and below execution. It is intentionally not a UI and not a scheduler.

Humans, agents, Julia programs, optimizers, and later visual frontends can all
propose changes against the same board representation. Compilation lowers only
OPERATION nodes and executable DATAFLOW/DEPENDENCY edges through the existing
semantic capability compiler. Engine selection remains outside the board.
"""
from __future__ import annotations

from copy import deepcopy
import math
import re
from typing import Any

from .control_contracts import content_ref, detached, json_tree, keys, record, text
from .control_plane import Port
from .operations.runner import check_seal
from .semantic_capabilities import SemanticRegistry, compile_graph

CAPABILITY = re.compile(r"[a-z][a-z0-9]*(?:\.[a-z][a-z0-9_-]*)+\.v[1-9][0-9]*$")
NODE_KINDS = {"OPERATION", "STATE", "MODEL", "PARAMETER", "REPRESENTATION", "ENTITY"}
EDGE_KINDS = {"DATAFLOW", "DEPENDENCY", "SEMANTIC", "SPATIAL", "TEMPORAL", "AUTHORITY", "SCALE"}
PARAMETER_TYPES = {"NUMBER", "INTEGER", "STRING", "BOOLEAN"}
DOMAIN_KINDS = {"FIXED", "ENUM", "RANGE", "LOG_RANGE"}
UNCERTAINTY = {"NONE", "COVARIANCE", "INTERVAL", "DISTRIBUTION", "UNKNOWN"}
MAX_NODES = 256
MAX_EDGES = 2048
MAX_GROUPS = 128
MAX_PARAMETERS = 128
MAX_SOCKETS = 64
MAX_LIST = 128


def _capability(value: Any) -> str:
    if type(value) is not str or CAPABILITY.fullmatch(value) is None or len(value) > 160:
        raise ValueError("Board capability must be a bounded versioned semantic capability")
    return value


def _number_or_none(value: Any, label: str, *, positive=False):
    if value is None:
        return None
    if type(value) not in (int, float) or isinstance(value, bool):
        raise ValueError(f"{label} must be a number or null")
    number = float(value)
    if not math.isfinite(number) or abs(number) > 1e150:
        raise ValueError(f"{label} must be finite and bounded")
    if positive and number <= 0:
        raise ValueError(f"{label} must be positive when declared")
    return number


def _unique_text(values: Any, label: str, maximum=MAX_LIST) -> list[str]:
    if type(values) is not list or len(values) > maximum:
        raise ValueError(f"{label} must be a bounded list")
    result = [text(item) for item in values]
    if len(result) != len(set(result)):
        raise ValueError(f"{label} contains duplicates")
    return result


def _refs(values: Any, label: str) -> list[str]:
    if type(values) is not list or len(values) > MAX_LIST:
        raise ValueError(f"{label} must be a bounded list")
    result = [content_ref(item) for item in values]
    if len(result) != len(set(result)):
        raise ValueError(f"{label} contains duplicates")
    return result


def _scale(value: Any) -> dict:
    keys(value, {"length_m", "time_s", "energy_j", "label"})
    return {
        "length_m": _number_or_none(value["length_m"], "scale.length_m", positive=True),
        "time_s": _number_or_none(value["time_s"], "scale.time_s", positive=True),
        "energy_j": _number_or_none(value["energy_j"], "scale.energy_j", positive=True),
        "label": text(value["label"]),
    }


def _socket(value: Any) -> dict:
    keys(value, {"socket_id", "port", "scale", "uncertainty_semantics", "provenance_required"})
    if value["uncertainty_semantics"] not in UNCERTAINTY:
        raise ValueError("Unknown socket uncertainty semantics")
    if type(value["provenance_required"]) is not bool:
        raise ValueError("socket provenance_required must be boolean")
    return {
        "socket_id": text(value["socket_id"]),
        "port": Port.from_dict(value["port"]).to_dict(),
        "scale": _scale(value["scale"]),
        "uncertainty_semantics": value["uncertainty_semantics"],
        "provenance_required": value["provenance_required"],
    }


def _sockets(value: Any, label: str) -> dict:
    keys(value, {"inputs", "outputs"})
    result = {}
    for direction in ("inputs", "outputs"):
        rows = value[direction]
        if type(rows) is not list or len(rows) > MAX_SOCKETS:
            raise ValueError(f"{label}.{direction} must be a bounded list")
        checked = [_socket(item) for item in rows]
        ids = [item["socket_id"] for item in checked]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{label}.{direction} contains duplicate socket IDs")
        result[direction] = checked
    return result


def _domain(value: Any, parameter_type: str) -> dict:
    keys(value, {"kind", "minimum", "maximum", "values", "log_base"})
    kind = value["kind"]
    if kind not in DOMAIN_KINDS:
        raise ValueError("Unknown parameter domain kind")
    minimum = _number_or_none(value["minimum"], "parameter minimum")
    maximum = _number_or_none(value["maximum"], "parameter maximum")
    values = value["values"]
    if values is not None:
        if type(values) is not list or not 1 <= len(values) <= 256:
            raise ValueError("parameter domain values must be null or a bounded nonempty list")
        json_tree(values)
        if len({repr(item) for item in values}) != len(values):
            raise ValueError("parameter enum contains duplicate values")
    log_base = _number_or_none(value["log_base"], "parameter log_base", positive=True)

    if kind == "FIXED":
        if any(item is not None for item in (minimum, maximum, values, log_base)):
            raise ValueError("FIXED parameter domain carries no auxiliary bounds")
    elif kind == "ENUM":
        if values is None or any(item is not None for item in (minimum, maximum, log_base)):
            raise ValueError("ENUM parameter domain requires values only")
    elif kind == "RANGE":
        if minimum is None or maximum is None or minimum > maximum or values is not None or log_base is not None:
            raise ValueError("RANGE requires minimum<=maximum and no enum/log base")
        if parameter_type not in {"NUMBER", "INTEGER"}:
            raise ValueError("RANGE is valid only for numerical parameters")
    elif kind == "LOG_RANGE":
        if minimum is None or maximum is None or minimum <= 0 or minimum > maximum or values is not None:
            raise ValueError("LOG_RANGE requires positive minimum<=maximum and no enum")
        if log_base is None or log_base <= 1:
            raise ValueError("LOG_RANGE requires log_base > 1")
        if parameter_type not in {"NUMBER", "INTEGER"}:
            raise ValueError("LOG_RANGE is valid only for numerical parameters")
    return {"kind": kind, "minimum": minimum, "maximum": maximum, "values": deepcopy(values), "log_base": log_base}


def _parameter(value: Any) -> dict:
    keys(value, {"type", "value", "unit", "domain", "exposed"})
    parameter_type = value["type"]
    if parameter_type not in PARAMETER_TYPES:
        raise ValueError("Unknown parameter type")
    raw = value["value"]
    if parameter_type == "NUMBER":
        if type(raw) not in (int, float) or isinstance(raw, bool) or not math.isfinite(float(raw)):
            raise ValueError("NUMBER parameter requires a finite number")
        raw = float(raw)
    elif parameter_type == "INTEGER":
        if type(raw) is not int or isinstance(raw, bool):
            raise ValueError("INTEGER parameter requires an integer")
    elif parameter_type == "STRING":
        raw = text(raw)
    elif type(raw) is not bool:
        raise ValueError("BOOLEAN parameter requires true/false")
    unit = value["unit"]
    if unit is not None:
        unit = text(unit)
    if type(value["exposed"]) is not bool:
        raise ValueError("parameter exposed must be boolean")
    domain = _domain(value["domain"], parameter_type)
    if domain["kind"] == "ENUM" and raw not in domain["values"]:
        raise ValueError("parameter value is outside ENUM domain")
    if domain["kind"] in {"RANGE", "LOG_RANGE"} and not domain["minimum"] <= float(raw) <= domain["maximum"]:
        raise ValueError("parameter value is outside declared range")
    return {"type": parameter_type, "value": raw, "unit": unit, "domain": domain, "exposed": value["exposed"]}


def _parameters(value: Any) -> dict:
    if type(value) is not dict or len(value) > MAX_PARAMETERS:
        raise ValueError("node parameters must be a bounded object")
    return {text(name): _parameter(item) for name, item in value.items()}


def _node(value: Any) -> dict:
    keys(value, {
        "node_id", "kind", "label", "semantic_capability", "sockets", "parameters",
        "resources", "inspection", "scale", "provenance_refs",
        "authority_requirements", "invariants", "validity_conditions",
    })
    kind = value["kind"]
    if kind not in NODE_KINDS:
        raise ValueError("Unknown board node kind")
    capability = value["semantic_capability"]
    if kind == "OPERATION":
        capability = _capability(capability)
    elif capability is not None:
        raise ValueError("Only OPERATION nodes may name a semantic capability")
    if type(value["inspection"]) is not bool:
        raise ValueError("node inspection must be boolean")
    return {
        "node_id": text(value["node_id"]), "kind": kind, "label": text(value["label"]),
        "semantic_capability": capability, "sockets": _sockets(value["sockets"], "node sockets"),
        "parameters": _parameters(value["parameters"]),
        "resources": _unique_text(value["resources"], "node resources"),
        "inspection": value["inspection"], "scale": _scale(value["scale"]),
        "provenance_refs": _refs(value["provenance_refs"], "node provenance refs"),
        "authority_requirements": _unique_text(value["authority_requirements"], "node authority requirements"),
        "invariants": _unique_text(value["invariants"], "node invariants"),
        "validity_conditions": _unique_text(value["validity_conditions"], "node validity conditions"),
    }


def _group(value: Any) -> dict:
    keys(value, {"group_id", "label", "node_ids", "parent_group_id"})
    parent = value["parent_group_id"]
    if parent is not None:
        parent = text(parent)
    return {"group_id": text(value["group_id"]), "label": text(value["label"]),
            "node_ids": _unique_text(value["node_ids"], "group node_ids", MAX_NODES),
            "parent_group_id": parent}


def _edge(value: Any) -> dict:
    keys(value, {"edge_id", "kind", "source_node_id", "target_node_id", "source_socket", "target_socket", "relation", "metadata"})
    kind = value["kind"]
    if kind not in EDGE_KINDS:
        raise ValueError("Unknown board edge kind")
    source_socket = value["source_socket"]
    target_socket = value["target_socket"]
    if source_socket is not None:
        source_socket = text(source_socket)
    if target_socket is not None:
        target_socket = text(target_socket)
    if kind == "DATAFLOW":
        if source_socket is None or target_socket is None:
            raise ValueError("DATAFLOW edges require source and target sockets")
    elif source_socket is not None or target_socket is not None:
        raise ValueError("Only DATAFLOW edges may name sockets in Board V1")
    json_tree(value["metadata"])
    return {
        "edge_id": text(value["edge_id"]), "kind": kind,
        "source_node_id": text(value["source_node_id"]), "target_node_id": text(value["target_node_id"]),
        "source_socket": source_socket, "target_socket": target_socket,
        "relation": text(value["relation"]), "metadata": deepcopy(value["metadata"]),
    }


def _socket_map(node: dict, direction: str) -> dict[str, dict]:
    return {item["socket_id"]: item for item in node["sockets"][direction]}


def _compatible(left: dict, right: dict) -> bool:
    return (left["port"] == right["port"] and left["scale"] == right["scale"]
            and left["uncertainty_semantics"] == right["uncertainty_semantics"]
            and left["provenance_required"] == right["provenance_required"])


def _validate_structure(nodes: list[dict], edges: list[dict], groups: list[dict]) -> None:
    node_map = {node["node_id"]: node for node in nodes}
    if len(node_map) != len(nodes):
        raise ValueError("Board contains duplicate node IDs")
    edge_ids, input_bindings = set(), set()
    for edge in edges:
        if edge["edge_id"] in edge_ids:
            raise ValueError("Board contains duplicate edge IDs")
        edge_ids.add(edge["edge_id"])
        if edge["source_node_id"] not in node_map or edge["target_node_id"] not in node_map:
            raise ValueError("Board edge references an unknown node")
        if edge["source_node_id"] == edge["target_node_id"]:
            raise ValueError("Board edge cannot self-reference")
        if edge["kind"] == "DATAFLOW":
            source = _socket_map(node_map[edge["source_node_id"]], "outputs").get(edge["source_socket"])
            target = _socket_map(node_map[edge["target_node_id"]], "inputs").get(edge["target_socket"])
            if source is None or target is None:
                raise ValueError("DATAFLOW edge references an unknown socket")
            if not _compatible(source, target):
                raise ValueError("DATAFLOW requires exact type/unit/frame/scale/uncertainty/provenance compatibility")
            binding = (edge["target_node_id"], edge["target_socket"])
            if binding in input_bindings:
                raise ValueError("Board input socket has multiple DATAFLOW producers")
            input_bindings.add(binding)

    group_map = {group["group_id"]: group for group in groups}
    if len(group_map) != len(groups):
        raise ValueError("Board contains duplicate group IDs")
    membership = {}
    for group in groups:
        for node_id in group["node_ids"]:
            if node_id not in node_map:
                raise ValueError("Board group references an unknown node")
            if node_id in membership:
                raise ValueError("Board node may belong to only one direct group in V1")
            membership[node_id] = group["group_id"]
        parent = group["parent_group_id"]
        if parent is not None and (parent not in group_map or parent == group["group_id"]):
            raise ValueError("Board group has an invalid parent")
    for group_id in group_map:
        visited, current = set(), group_id
        while group_map[current]["parent_group_id"] is not None:
            if current in visited:
                raise ValueError("Board group hierarchy contains a cycle")
            visited.add(current)
            current = group_map[current]["parent_group_id"]


def board_from_spec(spec: dict) -> dict:
    keys(spec, {"board_id", "title", "model_id", "nodes", "edges", "groups", "board_invariants", "notes"})
    if type(spec["nodes"]) is not list or not 1 <= len(spec["nodes"]) <= MAX_NODES:
        raise ValueError("Board requires 1..256 nodes")
    if type(spec["edges"]) is not list or len(spec["edges"]) > MAX_EDGES:
        raise ValueError("Board edge count exceeds bound")
    if type(spec["groups"]) is not list or len(spec["groups"]) > MAX_GROUPS:
        raise ValueError("Board group count exceeds bound")
    nodes = [_node(item) for item in spec["nodes"]]
    edges = [_edge(item) for item in spec["edges"]]
    groups = [_group(item) for item in spec["groups"]]
    _validate_structure(nodes, edges, groups)
    notes = spec["notes"]
    if type(notes) is not str or len(notes) > 8192:
        raise ValueError("Board notes must be bounded text")
    value = record(
        "system-board", board_id=text(spec["board_id"]), title=text(spec["title"]),
        model_id=text(spec["model_id"]), nodes=nodes, edges=edges, groups=groups,
        board_invariants=_unique_text(spec["board_invariants"], "board invariants", MAX_LIST),
        notes=notes,
        claims={"parameterized_relational_graph": True, "engine_selected": False,
                "provider_execution": False, "canonical_state_mutated": False,
                "state_admission": False, "execution_authority": False},
    )
    validate_board(value)
    return value


def validate_board(value: dict) -> dict:
    keys(value, {"schema", "record_digest", "board_id", "title", "model_id", "nodes", "edges", "groups", "board_invariants", "notes", "claims"})
    if value["schema"] != "ciw.system-board.v1":
        raise ValueError("Wrong System Board schema")
    check_seal(value)
    text(value["board_id"]); text(value["title"]); text(value["model_id"])
    if type(value["nodes"]) is not list or not 1 <= len(value["nodes"]) <= MAX_NODES:
        raise ValueError("Board requires 1..256 nodes")
    if type(value["edges"]) is not list or len(value["edges"]) > MAX_EDGES:
        raise ValueError("Board edge count exceeds bound")
    if type(value["groups"]) is not list or len(value["groups"]) > MAX_GROUPS:
        raise ValueError("Board group count exceeds bound")
    nodes = [_node(item) for item in value["nodes"]]
    edges = [_edge(item) for item in value["edges"]]
    groups = [_group(item) for item in value["groups"]]
    _validate_structure(nodes, edges, groups)
    _unique_text(value["board_invariants"], "board invariants", MAX_LIST)
    if type(value["notes"]) is not str or len(value["notes"]) > 8192:
        raise ValueError("Board notes must be bounded text")
    if value["claims"] != {"parameterized_relational_graph": True, "engine_selected": False,
                            "provider_execution": False, "canonical_state_mutated": False,
                            "state_admission": False, "execution_authority": False}:
        raise ValueError("Board claims exceed descriptive/compilation authority")
    return detached(value)


def _operation_socket_contract(node: dict, morphism: dict) -> None:
    board_inputs = {item["socket_id"]: item["port"] for item in node["sockets"]["inputs"]}
    board_outputs = {item["socket_id"]: item["port"] for item in node["sockets"]["outputs"]}
    if board_inputs != morphism["inputs"] or board_outputs != morphism["outputs"]:
        raise ValueError("Board OPERATION sockets must exactly preserve semantic capability port contracts")


def compile_board(board: dict, registry: SemanticRegistry) -> dict:
    board = validate_board(board)
    if not isinstance(registry, SemanticRegistry):
        raise TypeError("Board compilation requires the existing SemanticRegistry")
    operation_nodes = [node for node in board["nodes"] if node["kind"] == "OPERATION"]
    if not operation_nodes:
        raise ValueError("Board has no executable OPERATION nodes")

    semantic_nodes = {}
    for node in operation_nodes:
        capability = node["semantic_capability"]
        if capability not in registry._morphisms:
            raise ValueError("Board operation names an unknown semantic capability")
        morphism = registry._morphisms[capability]
        _operation_socket_contract(node, morphism)
        semantic_nodes[node["node_id"]] = {
            "node_id": node["node_id"], "capability": capability,
            "parameters": {name: deepcopy(spec["value"]) for name, spec in node["parameters"].items()},
            "inputs": {}, "depends_on": [], "resources": deepcopy(node["resources"]),
            "acceptance": {"invariants": deepcopy(node["invariants"]),
                           "validity_conditions": deepcopy(node["validity_conditions"])},
            "inspection": node["inspection"],
        }

    ignored = []
    for edge in board["edges"]:
        source, target = edge["source_node_id"], edge["target_node_id"]
        if edge["kind"] not in {"DATAFLOW", "DEPENDENCY"}:
            ignored.append(edge["edge_id"])
            continue
        if source not in semantic_nodes or target not in semantic_nodes:
            raise ValueError("Executable DATAFLOW/DEPENDENCY edges must connect OPERATION nodes in V1")
        target_node = semantic_nodes[target]
        if edge["kind"] == "DEPENDENCY":
            if source not in target_node["depends_on"]:
                target_node["depends_on"].append(source)
        else:
            if edge["target_socket"] in target_node["inputs"]:
                raise ValueError("Board compilation found duplicate input binding")
            target_node["inputs"][edge["target_socket"]] = {
                "node_id": source, "port": edge["source_socket"]}

    semantic_graph = {
        "schema": "ciw.semantic-work-graph.v1", "graph_id": board["board_id"],
        "mandate": board["title"], "model_id": board["model_id"],
        "nodes": list(semantic_nodes.values()),
    }
    compilation = compile_graph(semantic_graph, registry)
    value = record(
        "board-compilation", board_ref=board["record_digest"], board_id=board["board_id"],
        parameter_values={node["node_id"]: {name: deepcopy(spec["value"]) for name, spec in node["parameters"].items()}
                          for node in operation_nodes},
        semantic_graph=semantic_graph, semantic_compilation=compilation,
        ignored_nonexecution_edges=ignored,
        claims={"board_compiled": True, "engine_selected_by_board": False,
                "provider_execution": False, "canonical_state_mutated": False,
                "state_admission": False, "execution_authority": False},
    )
    validate_compilation(value, board)
    return value


def validate_compilation(value: dict, board: dict | None = None) -> dict:
    keys(value, {"schema", "record_digest", "board_ref", "board_id", "parameter_values", "semantic_graph", "semantic_compilation", "ignored_nonexecution_edges", "claims"})
    if value["schema"] != "ciw.board-compilation.v1":
        raise ValueError("Wrong Board compilation schema")
    check_seal(value)
    content_ref(value["board_ref"]); text(value["board_id"])
    if type(value["parameter_values"]) is not dict:
        raise ValueError("Board compilation parameter_values must be an object")
    json_tree(value["parameter_values"])
    if type(value["semantic_graph"]) is not dict:
        raise ValueError("Board compilation semantic_graph must be an object")
    check_seal(value["semantic_compilation"])
    if value["semantic_compilation"].get("schema") != "ciw.semantic-compilation.v1":
        raise ValueError("Board compilation must retain a semantic compilation")
    if value["semantic_compilation"]["graph"] != value["semantic_graph"]:
        raise ValueError("Retained semantic compilation differs from board semantic graph")
    _unique_text(value["ignored_nonexecution_edges"], "ignored nonexecution edges", MAX_EDGES)
    if value["claims"] != {"board_compiled": True, "engine_selected_by_board": False,
                            "provider_execution": False, "canonical_state_mutated": False,
                            "state_admission": False, "execution_authority": False}:
        raise ValueError("Board compilation claims exceed compilation authority")
    if board is not None:
        checked = validate_board(board)
        if checked["record_digest"] != value["board_ref"] or checked["board_id"] != value["board_id"]:
            raise ValueError("Board compilation references a different board")
    return detached(value)


def inspect_board(value: dict) -> dict:
    value = validate_board(value)
    parameter_count = sum(len(node["parameters"]) for node in value["nodes"])
    exposed_count = sum(spec["exposed"] for node in value["nodes"] for spec in node["parameters"].values())
    return {
        "schema": "ciw.system-board-inspection.v1", "record_digest": value["record_digest"],
        "board_id": value["board_id"], "nodes": len(value["nodes"]),
        "operation_nodes": sum(node["kind"] == "OPERATION" for node in value["nodes"]),
        "edges": len(value["edges"]), "groups": len(value["groups"]),
        "parameters": parameter_count, "exposed_parameters": exposed_count,
        "scale_labels": sorted({node["scale"]["label"] for node in value["nodes"]}),
        "engine_selected": False, "provider_execution": False, "execution_authority": False,
    }
