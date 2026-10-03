"""Deterministic Parameter Program V1 over the System Board.

A Parameter Program navigates one exposed Board coordinate and expands immutable
candidate Boards. It does not optimize, sample stochastic distributions, execute
providers, or mutate the base Board.

Supported generators:
- VALUES: explicit ordered values
- LINEAR: deterministic inclusive linear grid
- LOG: deterministic inclusive logarithmic grid
"""
from __future__ import annotations

from copy import deepcopy
import math
from typing import Any

from .control_contracts import content_ref, detached, json_tree, keys, record, text
from .operations.runner import check_seal
from .system_board import board_from_spec, validate_board

GENERATORS = {"VALUES", "LINEAR", "LOG"}
MAX_CANDIDATES = 64


def _target(value: Any) -> dict:
    keys(value, {"node_id", "parameter"})
    return {"node_id": text(value["node_id"]), "parameter": text(value["parameter"])}


def _number(value: Any, label: str) -> float:
    if type(value) not in (int, float) or isinstance(value, bool):
        raise ValueError(f"{label} must be numerical")
    result = float(value)
    if not math.isfinite(result) or abs(result) > 1e150:
        raise ValueError(f"{label} must be finite/bounded")
    return result


def _generator(value: Any) -> dict:
    keys(value, {"kind", "values", "start", "stop", "count", "base"})
    kind = value["kind"]
    if kind not in GENERATORS:
        raise ValueError("Unknown parameter generator kind")
    if kind == "VALUES":
        values = value["values"]
        if type(values) is not list or not 1 <= len(values) <= MAX_CANDIDATES:
            raise ValueError("VALUES generator requires 1..64 explicit values")
        json_tree(values)
        if any(item is not None for item in (value["start"], value["stop"], value["count"], value["base"])):
            raise ValueError("VALUES generator cannot also declare range fields")
        return {"kind": kind, "values": deepcopy(values), "start": None, "stop": None, "count": None, "base": None}

    if value["values"] is not None:
        raise ValueError("LINEAR/LOG generators cannot declare explicit values")
    start = _number(value["start"], "generator.start")
    stop = _number(value["stop"], "generator.stop")
    count = value["count"]
    if type(count) is not int or isinstance(count, bool) or not 2 <= count <= MAX_CANDIDATES:
        raise ValueError("LINEAR/LOG generator count must be 2..64")
    if kind == "LINEAR":
        if value["base"] is not None:
            raise ValueError("LINEAR generator cannot declare log base")
        return {"kind": kind, "values": None, "start": start, "stop": stop, "count": count, "base": None}

    base = _number(value["base"], "generator.base")
    if start <= 0 or stop <= 0 or base <= 1:
        raise ValueError("LOG generator requires positive endpoints and base > 1")
    return {"kind": kind, "values": None, "start": start, "stop": stop, "count": count, "base": base}


def _values(generator: dict) -> list[Any]:
    generator = _generator(generator)
    if generator["kind"] == "VALUES":
        values = deepcopy(generator["values"])
    elif generator["kind"] == "LINEAR":
        start, stop, count = generator["start"], generator["stop"], generator["count"]
        values = [start + (stop - start) * index / (count - 1) for index in range(count)]
    else:
        start, stop, count, base = generator["start"], generator["stop"], generator["count"], generator["base"]
        a = math.log(start, base)
        b = math.log(stop, base)
        values = [base ** (a + (b - a) * index / (count - 1)) for index in range(count)]
        values[0] = start
        values[-1] = stop
    if len({repr(item) for item in values}) != len(values):
        raise ValueError("Parameter generator produced duplicate candidate values")
    return values


def _parameter(board: dict, target: dict) -> dict:
    nodes = {node["node_id"]: node for node in board["nodes"]}
    if target["node_id"] not in nodes:
        raise ValueError("Parameter target node is absent from Board")
    parameters = nodes[target["node_id"]]["parameters"]
    if target["parameter"] not in parameters:
        raise ValueError("Parameter target is absent from Board node")
    parameter = parameters[target["parameter"]]
    if parameter["exposed"] is not True:
        raise ValueError("Parameter Program may only target an exposed Board parameter")
    return parameter


def _value_valid(parameter: dict, value: Any) -> Any:
    candidate = deepcopy(parameter)
    candidate["value"] = deepcopy(value)
    # Reuse the Board's own validator by embedding candidate into a tiny node is
    # intentionally avoided; validate directly against the retained normalized domain.
    kind = parameter["type"]
    if kind == "NUMBER":
        value = _number(value, "candidate value")
    elif kind == "INTEGER":
        if type(value) is not int or isinstance(value, bool):
            raise ValueError("INTEGER parameter candidates must be integers")
    elif kind == "STRING":
        value = text(value)
    elif type(value) is not bool:
        raise ValueError("BOOLEAN parameter candidates must be booleans")
    domain = parameter["domain"]
    if domain["kind"] == "FIXED" and value != parameter["value"]:
        raise ValueError("FIXED parameter cannot be varied")
    if domain["kind"] == "ENUM" and value not in domain["values"]:
        raise ValueError("candidate value is outside ENUM domain")
    if domain["kind"] in {"RANGE", "LOG_RANGE"}:
        if kind not in {"NUMBER", "INTEGER"}:
            raise ValueError("numerical range domain requires numerical parameter")
        if not domain["minimum"] <= float(value) <= domain["maximum"]:
            raise ValueError("candidate value is outside declared range")
    return value


def program_from_spec(board: dict, spec: dict) -> dict:
    board = validate_board(board)
    keys(spec, {"program_id", "board_ref", "target", "generator", "notes"})
    if spec["board_ref"] != board["record_digest"]:
        raise ValueError("Parameter Program targets a different Board")
    target = _target(spec["target"])
    parameter = _parameter(board, target)
    generator = _generator(spec["generator"])
    generated = [_value_valid(parameter, value) for value in _values(generator)]
    notes = spec["notes"]
    if type(notes) is not str or len(notes) > 4096:
        raise ValueError("Parameter Program notes must be bounded text")
    value = record(
        "parameter-program",
        program_id=text(spec["program_id"]),
        board_ref=board["record_digest"],
        board_id=board["board_id"],
        target=target,
        parameter_domain=deepcopy(parameter),
        generator=generator,
        generated_values=generated,
        notes=notes,
        claims={
            "deterministic_parameter_program": True,
            "optimization_performed": False,
            "stochastic_sampling_performed": False,
            "provider_execution": False,
            "base_board_mutated": False,
            "execution_authority": False,
        },
    )
    validate_program(value, board)
    return value


def validate_program(value: dict, board: dict | None = None) -> dict:
    keys(value, {
        "schema", "record_digest", "program_id", "board_ref", "board_id",
        "target", "parameter_domain", "generator", "generated_values",
        "notes", "claims",
    })
    if value["schema"] != "ciw.parameter-program.v1":
        raise ValueError("Wrong Parameter Program schema")
    check_seal(value)
    text(value["program_id"]); content_ref(value["board_ref"]); text(value["board_id"])
    target = _target(value["target"])
    generator = _generator(value["generator"])
    generated = _values(generator)
    if value["generated_values"] != generated:
        raise ValueError("Retained generated values differ from deterministic generator")
    if type(value["parameter_domain"]) is not dict:
        raise ValueError("Parameter Program requires retained parameter domain")
    json_tree(value["parameter_domain"])
    if type(value["notes"]) is not str or len(value["notes"]) > 4096:
        raise ValueError("Parameter Program notes must be bounded text")
    if value["claims"] != {
        "deterministic_parameter_program": True,
        "optimization_performed": False,
        "stochastic_sampling_performed": False,
        "provider_execution": False,
        "base_board_mutated": False,
        "execution_authority": False,
    }:
        raise ValueError("Parameter Program claims exceed deterministic expansion scope")
    if board is not None:
        checked = validate_board(board)
        if checked["record_digest"] != value["board_ref"] or checked["board_id"] != value["board_id"]:
            raise ValueError("Parameter Program references a different Board")
        parameter = _parameter(checked, target)
        if parameter != value["parameter_domain"]:
            raise ValueError("Parameter Program domain differs from current Board")
        for candidate in generated:
            _value_valid(parameter, candidate)
    return detached(value)


def _board_spec(board: dict, *, candidate_board_id: str, candidate_title: str) -> dict:
    return {
        "board_id": candidate_board_id,
        "title": candidate_title,
        "model_id": board["model_id"],
        "nodes": deepcopy(board["nodes"]),
        "edges": deepcopy(board["edges"]),
        "groups": deepcopy(board["groups"]),
        "board_invariants": deepcopy(board["board_invariants"]),
        "notes": board["notes"],
    }


def expand_program(board: dict, program: dict) -> dict:
    board = validate_board(board)
    program = validate_program(program, board)
    base_before = deepcopy(board)
    candidates = []
    for index, candidate_value in enumerate(program["generated_values"]):
        spec = _board_spec(
            board,
            candidate_board_id=f"{board['board_id']}.candidate.{index:03d}",
            candidate_title=f"{board['title']} / {program['target']['parameter']}={candidate_value}",
        )
        node = next(item for item in spec["nodes"] if item["node_id"] == program["target"]["node_id"])
        node["parameters"][program["target"]["parameter"]]["value"] = deepcopy(candidate_value)
        candidate = board_from_spec(spec)
        candidates.append({
            "index": index,
            "coordinate": {
                "node_id": program["target"]["node_id"],
                "parameter": program["target"]["parameter"],
                "value": deepcopy(candidate_value),
            },
            "board_ref": candidate["record_digest"],
            "board": candidate,
        })
    if board != base_before:
        raise AssertionError("Parameter expansion mutated base Board")
    value = record(
        "parameter-sweep",
        program_ref=program["record_digest"],
        base_board_ref=board["record_digest"],
        target=deepcopy(program["target"]),
        candidates=candidates,
        claims={
            "immutable_candidate_boards": True,
            "optimization_performed": False,
            "provider_execution": False,
            "base_board_mutated": False,
            "candidate_accepted": False,
            "execution_authority": False,
        },
    )
    validate_sweep(value, board, program)
    return value


def validate_sweep(value: dict, board: dict | None = None, program: dict | None = None) -> dict:
    keys(value, {
        "schema", "record_digest", "program_ref", "base_board_ref",
        "target", "candidates", "claims",
    })
    if value["schema"] != "ciw.parameter-sweep.v1":
        raise ValueError("Wrong Parameter Sweep schema")
    check_seal(value)
    content_ref(value["program_ref"]); content_ref(value["base_board_ref"])
    target = _target(value["target"])
    candidates = value["candidates"]
    if type(candidates) is not list or not 1 <= len(candidates) <= MAX_CANDIDATES:
        raise ValueError("Parameter Sweep requires 1..64 candidates")
    refs = set()
    for index, row in enumerate(candidates):
        keys(row, {"index", "coordinate", "board_ref", "board"})
        if row["index"] != index:
            raise ValueError("Parameter Sweep candidate indices must be contiguous")
        keys(row["coordinate"], {"node_id", "parameter", "value"})
        if row["coordinate"]["node_id"] != target["node_id"] or row["coordinate"]["parameter"] != target["parameter"]:
            raise ValueError("Parameter Sweep candidate coordinate differs from target")
        content_ref(row["board_ref"])
        candidate = validate_board(row["board"])
        if candidate["record_digest"] != row["board_ref"]:
            raise ValueError("Parameter Sweep candidate Board identity mismatch")
        if row["board_ref"] in refs:
            raise ValueError("Parameter Sweep contains duplicate candidate Boards")
        refs.add(row["board_ref"])
    if value["claims"] != {
        "immutable_candidate_boards": True,
        "optimization_performed": False,
        "provider_execution": False,
        "base_board_mutated": False,
        "candidate_accepted": False,
        "execution_authority": False,
    }:
        raise ValueError("Parameter Sweep claims exceed candidate-generation scope")
    if board is not None:
        checked = validate_board(board)
        if checked["record_digest"] != value["base_board_ref"]:
            raise ValueError("Parameter Sweep references a different base Board")
    if program is not None:
        checked_program = validate_program(program, board)
        if checked_program["record_digest"] != value["program_ref"]:
            raise ValueError("Parameter Sweep references a different program")
        if len(candidates) != len(checked_program["generated_values"]):
            raise ValueError("Parameter Sweep candidate count differs from program")
        for row, generated in zip(candidates, checked_program["generated_values"]):
            if row["coordinate"]["value"] != generated:
                raise ValueError("Parameter Sweep coordinate differs from program")
    return detached(value)


def inspect_program(value: dict) -> dict:
    checked = validate_program(value)
    return {
        "schema": "ciw.parameter-program-inspection.v1",
        "record_digest": checked["record_digest"],
        "program_id": checked["program_id"],
        "board_id": checked["board_id"],
        "target": checked["target"],
        "generator_kind": checked["generator"]["kind"],
        "candidates": len(checked["generated_values"]),
        "optimization_performed": False,
        "provider_execution": False,
        "execution_authority": False,
    }
