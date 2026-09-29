from copy import deepcopy
import json
import subprocess
import sys

import pytest

from ciw.control_plane import builtin_registry, run_graph
from ciw.instruments import make_demo_run
from ciw.needle import delta_projection, execute_needle, plan_from_spec
from ciw.semantic_capabilities import builtin_semantic_registry
from ciw.session import Session
from ciw.system_board import board_from_spec, compile_board, inspect_board


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


def channel_parameter(value="q"):
    return {
        "type": "STRING", "value": value, "unit": None, "exposed": True,
        "domain": {
            "kind": "ENUM", "minimum": None, "maximum": None,
            "values": ["q", "v", "energy"], "log_base": None,
        },
    }


def op(node_id, capability, channel):
    return {
        "node_id": node_id, "kind": "OPERATION", "label": node_id,
        "semantic_capability": capability,
        "sockets": {"inputs": [], "outputs": [result_socket()]},
        "parameters": {"channel": channel_parameter(channel)},
        "resources": ["cpu"], "inspection": False, "scale": scale("signal-analysis"),
        "provenance_refs": [], "authority_requirements": ["read:recording"],
        "invariants": ["source evidence identity remains retained"],
        "validity_conditions": ["channel exists in retained recording"],
    }


def board_spec():
    return {
        "board_id": "oscillator-board-v1",
        "title": "Parameterized oscillator analysis board",
        "model_id": "analytic-damped-oscillator.v1",
        "nodes": [
            op("statistics", "analysis.statistics.v1", "q"),
            op("spectrum", "analysis.spectrum.v1", "q"),
            op("energy_statistics", "analysis.statistics.v1", "energy"),
        ],
        "edges": [
            {
                "edge_id": "e-dependency", "kind": "DEPENDENCY",
                "source_node_id": "statistics", "target_node_id": "spectrum",
                "source_socket": None, "target_socket": None,
                "relation": "declared_execution_dependency", "metadata": {},
            },
            {
                "edge_id": "e-semantic", "kind": "SEMANTIC",
                "source_node_id": "statistics", "target_node_id": "energy_statistics",
                "source_socket": None, "target_socket": None,
                "relation": "same_operation_family", "metadata": {"meaning": "descriptive only"},
            },
        ],
        "groups": [
            {"group_id": "root", "label": "Oscillator", "node_ids": [], "parent_group_id": None},
            {"group_id": "analysis", "label": "Analysis", "node_ids": ["statistics", "spectrum", "energy_statistics"], "parent_group_id": "root"},
        ],
        "board_invariants": ["canonical source evidence is not mutated by board compilation"],
        "notes": "Synthetic fully observable Board qualification fixture.",
    }


def registry():
    concrete = builtin_registry(bind=True)
    return concrete, builtin_semantic_registry(concrete)


def test_board_is_parameterized_typed_graph_without_execution_authority():
    board = board_from_spec(board_spec())
    inspected = inspect_board(board)
    assert inspected["nodes"] == 3
    assert inspected["operation_nodes"] == 3
    assert inspected["parameters"] == 3
    assert inspected["exposed_parameters"] == 3
    assert board["claims"]["parameterized_relational_graph"] is True
    assert board["claims"]["engine_selected"] is False
    assert board["claims"]["execution_authority"] is False


def test_parameter_domain_rejects_out_of_enum():
    value = board_spec()
    value["nodes"][0]["parameters"]["channel"]["value"] = "pressure"
    with pytest.raises(ValueError, match="ENUM"):
        board_from_spec(value)


def test_log_parameter_requires_positive_range():
    value = board_spec()
    value["nodes"][0]["parameters"]["tolerance"] = {
        "type": "NUMBER", "value": 1e-6, "unit": None, "exposed": True,
        "domain": {
            "kind": "LOG_RANGE", "minimum": -1.0, "maximum": 1.0,
            "values": None, "log_base": 10.0,
        },
    }
    with pytest.raises(ValueError, match="LOG_RANGE"):
        board_from_spec(value)


def dataflow_board(target_unit="K", target_scale=None, target_uncertainty="COVARIANCE"):
    socket_out = {
        "socket_id": "state", "port": {"schema": "fixture.temperature.v1", "unit": "K", "frame": "field"},
        "scale": scale("plant"), "uncertainty_semantics": "COVARIANCE", "provenance_required": True,
    }
    socket_in = deepcopy(socket_out)
    socket_in["port"]["unit"] = target_unit
    socket_in["scale"] = target_scale or scale("plant")
    socket_in["uncertainty_semantics"] = target_uncertainty
    base_node = {
        "semantic_capability": None, "parameters": {}, "resources": [], "inspection": False,
        "scale": scale("plant"), "provenance_refs": [], "authority_requirements": [],
        "invariants": [], "validity_conditions": [],
    }
    return {
        "board_id": "typed-flow", "title": "Typed flow", "model_id": "fixture-model",
        "nodes": [
            {**base_node, "node_id": "source", "kind": "STATE", "label": "Source",
             "sockets": {"inputs": [], "outputs": [socket_out]}},
            {**base_node, "node_id": "sink", "kind": "STATE", "label": "Sink",
             "sockets": {"inputs": [socket_in], "outputs": []}},
        ],
        "edges": [{
            "edge_id": "flow", "kind": "DATAFLOW", "source_node_id": "source",
            "target_node_id": "sink", "source_socket": "state", "target_socket": "state",
            "relation": "typed_state_flow", "metadata": {},
        }],
        "groups": [], "board_invariants": [], "notes": "",
    }


def test_dataflow_requires_exact_unit_frame_scale_uncertainty_and_provenance():
    board_from_spec(dataflow_board())
    with pytest.raises(ValueError, match="exact type/unit/frame/scale"):
        board_from_spec(dataflow_board(target_unit="Pa"))
    changed_scale = scale("molecular")
    with pytest.raises(ValueError, match="exact type/unit/frame/scale"):
        board_from_spec(dataflow_board(target_scale=changed_scale))
    with pytest.raises(ValueError, match="exact type/unit/frame/scale"):
        board_from_spec(dataflow_board(target_uncertainty="INTERVAL"))


def test_group_hierarchy_refuses_cycles():
    value = board_spec()
    value["groups"][0]["parent_group_id"] = "analysis"
    with pytest.raises(ValueError, match="cycle"):
        board_from_spec(value)


def test_node_cannot_belong_to_two_direct_groups():
    value = board_spec()
    value["groups"].append({
        "group_id": "duplicate-membership", "label": "Other",
        "node_ids": ["statistics"], "parent_group_id": "root",
    })
    with pytest.raises(ValueError, match="one direct group"):
        board_from_spec(value)


def test_compile_lowers_board_through_existing_semantic_plane():
    concrete, semantic = registry()
    board = board_from_spec(board_spec())
    compiled = compile_board(board, semantic)
    assert compiled["schema"] == "ciw.board-compilation.v1"
    assert compiled["claims"]["engine_selected_by_board"] is False
    assert compiled["claims"]["provider_execution"] is False
    assert compiled["ignored_nonexecution_edges"] == ["e-semantic"]
    assert [node["operation_id"] for node in compiled["semantic_compilation"]["experiment"]["nodes"]] == [
        "statistics.v1", "statistics.v1", "spectrum.periodogram.v1"]
    assert compiled["parameter_values"]["statistics"]["channel"] == "q"
    assert set(compiled["semantic_graph"]["nodes"][1]["depends_on"]) == {"statistics"}


def test_compile_refuses_board_socket_contract_drift():
    _, semantic = registry()
    value = board_spec()
    value["nodes"][0]["sockets"]["outputs"][0]["port"]["unit"] = "K"
    board = board_from_spec(value)
    with pytest.raises(ValueError, match="exactly preserve semantic"):
        compile_board(board, semantic)


def test_compile_refuses_unknown_semantic_capability():
    _, semantic = registry()
    value = board_spec()
    value["nodes"][0]["semantic_capability"] = "analysis.unknown.v1"
    board = board_from_spec(value)
    with pytest.raises(ValueError, match="unknown semantic"):
        compile_board(board, semantic)


def test_board_has_no_engine_or_provider_field():
    value = board_spec()
    value["nodes"][0]["engine"] = "python"
    with pytest.raises(ValueError, match="Unexpected"):
        board_from_spec(value)


def test_board_compilation_does_not_mutate_board():
    _, semantic = registry()
    board = board_from_spec(board_spec())
    before = deepcopy(board)
    compile_board(board, semantic)
    assert board == before


def test_board_to_experiment_to_needle_uses_one_shared_graph_semantics(tmp_path):
    concrete, semantic = registry()
    board = board_from_spec(board_spec())
    compiled = compile_board(board, semantic)
    source = make_demo_run()
    session = Session(source, tmp_path / "session", operations=concrete.operations)
    baseline = run_graph(session, compiled["semantic_compilation"]["experiment"], concrete)
    assert baseline["status"] == "completed"

    needle = plan_from_spec(baseline, {
        "needle_id": "board-q-to-v",
        "target": {"kind": "NODE_PARAMETER", "node_id": "statistics", "parameter": "channel"},
        "replacement": "v",
        "propagation": {"relation": "DEPENDENCY", "scope": "DESCENDANTS_INCLUSIVE"},
    })
    run = execute_needle(session, baseline, needle, concrete)
    delta = delta_projection(baseline, run)
    assert run["dependency_closure"] == ["statistics", "spectrum"]
    assert run["reused_nodes"] == ["energy_statistics"]
    rows = {row["node_id"]: row for row in delta["nodes"]}
    assert rows["statistics"]["data_changed"] is True
    assert rows["spectrum"]["data_changed"] is False
    assert rows["energy_statistics"]["recomputation"] == "REUSED"


def test_cli_create_compile_and_inspect(tmp_path):
    spec_path = tmp_path / "board-spec.json"
    board_path = tmp_path / "board.json"
    compilation_path = tmp_path / "compilation.json"
    spec_path.write_text(json.dumps(board_spec()))
    subprocess.run([
        sys.executable, "-m", "ciw.net", "board", "create",
        str(spec_path), "--output", str(board_path),
    ], cwd=tmp_path, check=True)
    subprocess.run([
        sys.executable, "-m", "ciw.net", "board", "compile",
        str(board_path), "--output", str(compilation_path),
    ], cwd=tmp_path, check=True)
    result = json.loads(subprocess.check_output([
        sys.executable, "-m", "ciw.net", "board", "inspect", str(board_path)
    ], cwd=tmp_path, text=True))
    assert result["board_id"] == "oscillator-board-v1"
    assert result["engine_selected"] is False
