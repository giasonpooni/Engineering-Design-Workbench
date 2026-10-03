from copy import deepcopy
import json
import subprocess
import sys

import pytest

from ciw.board_visual import apply_visual_edit, render_html, visual_edit_to_needle_plan
from ciw.control_plane import builtin_registry, run_graph
from ciw.instruments import make_demo_run
from ciw.semantic_capabilities import builtin_semantic_registry
from ciw.session import Session
from ciw.system_board import board_from_spec, compile_board, validate_board


def scale(label="system"):
    return {"length_m": None, "time_s": None, "energy_j": None, "label": label}


def node(node_id, kind, parameters=None):
    return {
        "node_id": node_id,
        "kind": kind,
        "label": node_id.replace("_", " ").title(),
        "semantic_capability": None,
        "sockets": {"inputs": [], "outputs": []},
        "parameters": parameters or {},
        "resources": [],
        "inspection": False,
        "scale": scale(),
        "provenance_refs": [],
        "authority_requirements": [],
        "invariants": ["identity remains explicit"],
        "validity_conditions": ["synthetic visual qualification fixture"],
    }


def gain_parameter(value=1.0, exposed=True):
    return {
        "type": "NUMBER",
        "value": value,
        "unit": "1",
        "exposed": exposed,
        "domain": {
            "kind": "RANGE",
            "minimum": 0.1,
            "maximum": 10.0,
            "values": None,
            "log_base": None,
        },
    }


def board_spec(exposed=True):
    return {
        "board_id": "visual-board-v1",
        "title": "Hierarchical visual Board fixture",
        "model_id": "visual-fixture-model.v1",
        "nodes": [
            node("model", "MODEL", {"gain": gain_parameter(exposed=exposed)}),
            node("state", "STATE"),
        ],
        "edges": [{
            "edge_id": "depends",
            "kind": "DEPENDENCY",
            "source_node_id": "model",
            "target_node_id": "state",
            "source_socket": None,
            "target_socket": None,
            "relation": "declared_execution_dependency",
            "metadata": {},
        }],
        "groups": [
            {"group_id": "root", "label": "System", "node_ids": [], "parent_group_id": None},
            {"group_id": "dynamics", "label": "Dynamics", "node_ids": ["model", "state"], "parent_group_id": "root"},
        ],
        "board_invariants": ["visual projection never mutates base Board"],
        "notes": "Synthetic visual editor fixture.",
    }



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
        "type": "STRING",
        "value": value,
        "unit": None,
        "exposed": True,
        "domain": {
            "kind": "ENUM",
            "minimum": None,
            "maximum": None,
            "values": ["q", "v", "energy"],
            "log_base": None,
        },
    }


def operation_node(node_id, capability, channel):
    value = node(node_id, "OPERATION", {"channel": channel_parameter(channel)})
    value["semantic_capability"] = capability
    value["sockets"] = {"inputs": [], "outputs": [result_socket()]}
    value["resources"] = ["cpu"]
    value["authority_requirements"] = ["read:recording"]
    value["invariants"] = ["source evidence identity remains retained"]
    value["validity_conditions"] = ["channel exists in retained recording"]
    return value


def operation_board_spec(channel="q"):
    return {
        "board_id": "visual-oscillator-v1",
        "title": "Visual oscillator Board",
        "model_id": "analytic-damped-oscillator.v1",
        "nodes": [
            operation_node("statistics", "analysis.statistics.v1", channel),
            operation_node("spectrum", "analysis.spectrum.v1", "q"),
            operation_node("energy_statistics", "analysis.statistics.v1", "energy"),
        ],
        "edges": [{
            "edge_id": "stats-to-spectrum",
            "kind": "DEPENDENCY",
            "source_node_id": "statistics",
            "target_node_id": "spectrum",
            "source_socket": None,
            "target_socket": None,
            "relation": "declared_execution_dependency",
            "metadata": {},
        }],
        "groups": [
            {"group_id": "root", "label": "Oscillator", "node_ids": [], "parent_group_id": None},
            {
                "group_id": "analysis",
                "label": "Analysis",
                "node_ids": ["statistics", "spectrum", "energy_statistics"],
                "parent_group_id": "root",
            },
        ],
        "board_invariants": ["canonical source evidence is not mutated"],
        "notes": "Synthetic visual Needle lowering fixture.",
    }


def visual_channel_edit(board, replacement="v"):
    return {
        "schema": "ciw.board-visual-edit-spec.v1",
        "edit_id": "visual-statistics-channel",
        "board_ref": board["record_digest"],
        "target": {"node_id": "statistics", "parameter": "channel"},
        "replacement": replacement,
        "notes": "Visual channel edit.",
    }


def edit_spec(board, replacement=2.0):
    return {
        "schema": "ciw.board-visual-edit-spec.v1",
        "edit_id": "visual-model-gain-test",
        "board_ref": board["record_digest"],
        "target": {"node_id": "model", "parameter": "gain"},
        "replacement": replacement,
        "notes": "Synthetic visual edit.",
    }


def test_render_is_self_contained_and_network_disabled():
    board = board_from_spec(board_spec())
    raw = render_html(board)
    text = raw.decode("utf-8")
    assert b"__DATA__" not in raw
    assert "__SCRIPT__" not in text
    assert "__STYLE__" not in text
    assert "connect-src 'none'" in text
    assert "CANDIDATE EDITS ONLY" in text
    assert "ciw.board-visual-edit-spec.v1" in text
    assert len(raw) < 8 * 1024 * 1024


def test_visual_edit_creates_new_candidate_without_mutating_base():
    board = board_from_spec(board_spec())
    before = deepcopy(board)
    candidate, summary = apply_visual_edit(board, edit_spec(board, 2.5))
    validate_board(candidate)
    assert board == before
    assert candidate["record_digest"] != board["record_digest"]
    model = next(node for node in candidate["nodes"] if node["node_id"] == "model")
    assert model["parameters"]["gain"]["value"] == 2.5
    assert summary["base_board_ref"] == board["record_digest"]
    assert summary["candidate_board_ref"] == candidate["record_digest"]
    assert summary["base_board_mutated"] is False
    assert summary["candidate_accepted"] is False
    assert summary["provider_execution"] is False
    assert summary["canonical_state_mutated"] is False
    assert summary["execution_authority"] is False


def test_visual_edit_is_bound_to_exact_base_board_identity():
    board = board_from_spec(board_spec())
    spec = edit_spec(board)
    spec["board_ref"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="different Board"):
        apply_visual_edit(board, spec)


def test_visual_edit_refuses_unexposed_parameter():
    board = board_from_spec(board_spec(exposed=False))
    with pytest.raises(ValueError, match="exposed"):
        apply_visual_edit(board, edit_spec(board))


def test_visual_edit_reuses_board_domain_validation():
    board = board_from_spec(board_spec())
    with pytest.raises(ValueError, match="outside declared range"):
        apply_visual_edit(board, edit_spec(board, 50.0))


def test_visual_edit_refuses_type_drift():
    board = board_from_spec(board_spec())
    with pytest.raises(ValueError, match="numerical"):
        apply_visual_edit(board, edit_spec(board, "fast"))



def test_visual_edit_lowers_to_existing_needle_plan_for_exact_board_baseline(tmp_path):
    concrete = builtin_registry(bind=True)
    semantic = builtin_semantic_registry(concrete)
    board = board_from_spec(operation_board_spec())
    compiled = compile_board(board, semantic)
    source = make_demo_run()
    session = Session(source, tmp_path / "session", operations=concrete.operations)
    baseline = run_graph(session, compiled["semantic_compilation"]["experiment"], concrete)
    assert baseline["status"] == "completed"

    plan = visual_edit_to_needle_plan(board, visual_channel_edit(board), baseline, semantic)
    assert plan["schema"] == "ciw.needle-plan.v1"
    assert plan["target"] == {
        "kind": "NODE_PARAMETER",
        "node_id": "statistics",
        "parameter": "channel",
    }
    assert plan["before"] == "q"
    assert plan["replacement"] == "v"
    assert plan["baseline_graph_run_ref"] == baseline["record_digest"]
    assert plan["claims"]["execution_authority"] is False


def test_visual_edit_to_needle_refuses_nonoperation_target():
    concrete = builtin_registry(bind=True)
    semantic = builtin_semantic_registry(concrete)
    board = board_from_spec(board_spec())
    fake_baseline = {"schema": "ciw.graph-run.v1"}
    with pytest.raises(ValueError, match="OPERATION"):
        visual_edit_to_needle_plan(board, edit_spec(board), fake_baseline, semantic)


def test_cli_render_and_apply_edit(tmp_path):
    board = board_from_spec(board_spec())
    board_path = tmp_path / "board.json"
    board_path.write_text(json.dumps(board), encoding="utf-8")
    html_path = tmp_path / "board.html"
    subprocess.run([
        sys.executable, "-m", "ciw.net", "board", "render",
        str(board_path), "--output", str(html_path),
    ], check=True)
    assert html_path.exists()
    assert "NO NETWORK" in html_path.read_text(encoding="utf-8")

    spec_path = tmp_path / "edit.json"
    spec_path.write_text(json.dumps(edit_spec(board, 3.0)), encoding="utf-8")
    candidate_path = tmp_path / "candidate.json"
    subprocess.run([
        sys.executable, "-m", "ciw.net", "board", "apply-edit",
        str(board_path), str(spec_path), "--output", str(candidate_path),
    ], check=True)
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    validate_board(candidate)
    model = next(node for node in candidate["nodes"] if node["node_id"] == "model")
    assert model["parameters"]["gain"]["value"] == 3.0
