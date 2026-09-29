from copy import deepcopy
import json
import subprocess
import sys

import pytest

from ciw.control_plane import builtin_registry, run_graph
from ciw.instruments import make_demo_run
from ciw.parameter_program import expand_program, program_from_spec, validate_sweep
from ciw.semantic_capabilities import builtin_semantic_registry
from ciw.session import Session
from ciw.system_board import board_from_spec, compile_board


def scale(label="signal"):
    return {"length_m": None, "time_s": None, "energy_j": None, "label": label}


def result_socket():
    return {
        "socket_id": "result",
        "port": {"schema": "ciw.operation-result.v1", "unit": None, "frame": None},
        "scale": scale("signal-result"),
        "uncertainty_semantics": "UNKNOWN",
        "provenance_required": True,
    }


def board_spec(channel="q", exposed=True):
    parameter = {
        "type": "STRING", "value": channel, "unit": None, "exposed": exposed,
        "domain": {"kind": "ENUM", "minimum": None, "maximum": None,
                   "values": ["q", "v", "energy"], "log_base": None},
    }
    node = {
        "node_id": "statistics", "kind": "OPERATION", "label": "Statistics",
        "semantic_capability": "analysis.statistics.v1",
        "sockets": {"inputs": [], "outputs": [result_socket()]},
        "parameters": {"channel": parameter}, "resources": ["cpu"], "inspection": False,
        "scale": scale("signal-analysis"), "provenance_refs": [],
        "authority_requirements": ["read:recording"], "invariants": [],
        "validity_conditions": ["channel exists"],
    }
    return {
        "board_id": "parameter-board-v1", "title": "Parameter Board",
        "model_id": "analytic-damped-oscillator.v1", "nodes": [node],
        "edges": [], "groups": [], "board_invariants": [], "notes": "",
    }


def values_spec(board, values=None):
    return {
        "program_id": "channel-values",
        "board_ref": board["record_digest"],
        "target": {"node_id": "statistics", "parameter": "channel"},
        "generator": {"kind": "VALUES", "values": values or ["q", "v", "energy"],
                      "start": None, "stop": None, "count": None, "base": None},
        "notes": "Deterministic enum sweep.",
    }


def numeric_board(domain_kind="RANGE"):
    domain = {
        "kind": domain_kind,
        "minimum": 1e-6 if domain_kind == "LOG_RANGE" else 0.0,
        "maximum": 1e-2 if domain_kind == "LOG_RANGE" else 10.0,
        "values": None,
        "log_base": 10.0 if domain_kind == "LOG_RANGE" else None,
    }
    return board_from_spec({
        "board_id": "numeric-board", "title": "Numeric Board", "model_id": "fixture",
        "nodes": [{
            "node_id": "parameter", "kind": "PARAMETER", "label": "Parameter",
            "semantic_capability": None, "sockets": {"inputs": [], "outputs": []},
            "parameters": {"theta": {"type": "NUMBER",
                                    "value": 1e-4 if domain_kind == "LOG_RANGE" else 5.0,
                                    "unit": None, "domain": domain, "exposed": True}},
            "resources": [], "inspection": False, "scale": scale("parameter"),
            "provenance_refs": [], "authority_requirements": [], "invariants": [],
            "validity_conditions": [],
        }],
        "edges": [], "groups": [], "board_invariants": [], "notes": "",
    })


def test_explicit_values_generate_immutable_candidate_boards():
    board = board_from_spec(board_spec())
    before = deepcopy(board)
    program = program_from_spec(board, values_spec(board))
    sweep = expand_program(board, program)
    validate_sweep(sweep, board, program)
    assert board == before
    assert [row["coordinate"]["value"] for row in sweep["candidates"]] == ["q", "v", "energy"]
    assert len({row["board_ref"] for row in sweep["candidates"]}) == 3
    assert [row["board"]["nodes"][0]["parameters"]["channel"]["value"]
            for row in sweep["candidates"]] == ["q", "v", "energy"]
    assert sweep["claims"]["candidate_accepted"] is False


def test_candidate_board_ids_are_distinct_from_base_and_each_other():
    board = board_from_spec(board_spec())
    program = program_from_spec(board, values_spec(board))
    sweep = expand_program(board, program)
    ids = [row["board"]["board_id"] for row in sweep["candidates"]]
    assert board["board_id"] not in ids
    assert len(set(ids)) == 3


def test_values_outside_enum_refuse_before_expansion():
    board = board_from_spec(board_spec())
    with pytest.raises(ValueError, match="ENUM"):
        program_from_spec(board, values_spec(board, ["q", "pressure"]))


def test_unexposed_parameter_cannot_be_programmed():
    board = board_from_spec(board_spec(exposed=False))
    with pytest.raises(ValueError, match="exposed"):
        program_from_spec(board, values_spec(board))


def test_program_is_bound_to_exact_board_identity():
    board = board_from_spec(board_spec())
    spec = values_spec(board)
    spec["board_ref"] = "sha256:" + "f" * 64
    with pytest.raises(ValueError, match="different Board"):
        program_from_spec(board, spec)


def test_linear_generator_is_deterministic_and_inclusive():
    board = numeric_board("RANGE")
    spec = {
        "program_id": "linear", "board_ref": board["record_digest"],
        "target": {"node_id": "parameter", "parameter": "theta"},
        "generator": {"kind": "LINEAR", "values": None, "start": 0.0,
                      "stop": 10.0, "count": 3, "base": None},
        "notes": "",
    }
    program = program_from_spec(board, spec)
    assert program["generated_values"] == [0.0, 5.0, 10.0]
    sweep = expand_program(board, program)
    assert [row["coordinate"]["value"] for row in sweep["candidates"]] == [0.0, 5.0, 10.0]


def test_log_generator_is_deterministic_and_inclusive():
    board = numeric_board("LOG_RANGE")
    spec = {
        "program_id": "log", "board_ref": board["record_digest"],
        "target": {"node_id": "parameter", "parameter": "theta"},
        "generator": {"kind": "LOG", "values": None, "start": 1e-6,
                      "stop": 1e-2, "count": 3, "base": 10.0},
        "notes": "",
    }
    program = program_from_spec(board, spec)
    assert program["generated_values"][0] == 1e-6
    assert program["generated_values"][1] == pytest.approx(1e-4)
    assert program["generated_values"][2] == 1e-2


def test_log_generator_refuses_nonpositive_endpoints():
    board = numeric_board("LOG_RANGE")
    spec = {
        "program_id": "bad-log", "board_ref": board["record_digest"],
        "target": {"node_id": "parameter", "parameter": "theta"},
        "generator": {"kind": "LOG", "values": None, "start": 0.0,
                      "stop": 1e-2, "count": 3, "base": 10.0},
        "notes": "",
    }
    with pytest.raises(ValueError, match="positive"):
        program_from_spec(board, spec)


def test_parameter_program_does_not_optimize_or_execute():
    board = board_from_spec(board_spec())
    program = program_from_spec(board, values_spec(board))
    assert program["claims"]["optimization_performed"] is False
    assert program["claims"]["stochastic_sampling_performed"] is False
    assert program["claims"]["provider_execution"] is False
    assert program["claims"]["execution_authority"] is False


def test_candidate_board_can_compile_and_execute_through_existing_semantic_plane(tmp_path):
    board = board_from_spec(board_spec())
    program = program_from_spec(board, values_spec(board, ["v"]))
    candidate = expand_program(board, program)["candidates"][0]["board"]

    concrete = builtin_registry(bind=True)
    semantic = builtin_semantic_registry(concrete)
    compilation = compile_board(candidate, semantic)
    session = Session(make_demo_run(), tmp_path / "session", operations=concrete.operations)
    run = run_graph(session, compilation["semantic_compilation"]["experiment"], concrete)
    assert run["status"] == "completed"
    assert run["nodes"]["statistics"]["result"]["data"]["unit"] == "m/s"


def test_cli_create_expand_and_inspect(tmp_path):
    board = board_from_spec(board_spec())
    board_path = tmp_path / "board.json"
    spec_path = tmp_path / "program-spec.json"
    program_path = tmp_path / "program.json"
    sweep_path = tmp_path / "sweep.json"
    board_path.write_text(json.dumps(board))
    spec_path.write_text(json.dumps(values_spec(board, ["q", "v"])))
    subprocess.run([
        sys.executable, "-m", "ciw.net", "parameter", "create",
        str(board_path), str(spec_path), "--output", str(program_path),
    ], cwd=tmp_path, check=True)
    subprocess.run([
        sys.executable, "-m", "ciw.net", "parameter", "expand",
        str(board_path), str(program_path), "--output", str(sweep_path),
    ], cwd=tmp_path, check=True)
    result = json.loads(subprocess.check_output([
        sys.executable, "-m", "ciw.net", "parameter", "inspect", str(sweep_path),
    ], cwd=tmp_path, text=True))
    assert result["candidates"] == 2
    assert result["candidate_accepted"] is False
