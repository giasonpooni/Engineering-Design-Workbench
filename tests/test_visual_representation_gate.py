from copy import deepcopy
from http.client import HTTPConnection
import json
import threading

import pytest

from ciw.control_plane import builtin_registry
from ciw.instruments import make_demo_run
from ciw.operations.runner import seal
from ciw.semantic_capabilities import builtin_semantic_registry
from ciw.visual_board import demo_board
from ciw.visual_board_server import BoardWorkbench, make_server
from ciw.visual_representation_gate import (
    binding_from_spec,
    context_for_request,
    demo_binding,
    demo_registry,
    gate_for_request,
    validate_binding,
)


def configured(tmp_path, *, allow_run=True):
    board = demo_board()
    concrete = builtin_registry(bind=True)
    semantic = builtin_semantic_registry(concrete)
    registry = demo_registry(semantic)
    binding = demo_binding(board, registry, semantic)
    source = make_demo_run()
    work = BoardWorkbench(
        board, tmp_path / "work", source=source, allow_run=allow_run,
        morphism_registry=registry, intervention_binding=binding)
    return board, source, registry, binding, semantic, work


def edit(board, node="statistics", replacement="v"):
    return {
        "schema": "ciw.board-parameter-edit.v1",
        "base_board_ref": board["record_digest"],
        "node_id": node,
        "parameter": "channel",
        "replacement": replacement,
    }


def test_binding_covers_every_exposed_coordinate_and_recomputes(tmp_path):
    board, _, registry, binding, semantic, _ = configured(tmp_path, allow_run=False)
    assert set(binding["nodes"]) == {"statistics", "spectrum", "energy_statistics"}
    assert binding["nodes"]["spectrum"]["projection_morphism_id"] == "signal.periodogram.transform.v1"
    assert binding["nodes"]["spectrum"]["representation_id"] == "signal.periodogram.one-sided-density.v1"
    assert validate_binding(binding, board, registry, semantic) == binding


def test_incomplete_or_wrong_binding_refuses(tmp_path):
    board = demo_board()
    concrete = builtin_registry(bind=True)
    semantic = builtin_semantic_registry(concrete)
    registry = demo_registry(semantic)
    binding = demo_binding(board, registry, semantic)
    spec = {
        "binding_id": binding["binding_id"],
        "nodes": {
            nid: {
                "representation_id": row["representation_id"],
                "parameters": row["parameters"],
                "recovery_representation_id": row["recovery_representation_id"],
                "projection_morphism_id": row["projection_morphism_id"],
            }
            for nid, row in binding["nodes"].items()
        },
    }
    del spec["nodes"]["energy_statistics"]
    with pytest.raises(ValueError, match="cover every exposed"):
        binding_from_spec(board, registry, semantic, spec)

    spec = {
        "binding_id": "wrong-projection",
        "nodes": {
            nid: {
                "representation_id": row["representation_id"],
                "parameters": row["parameters"],
                "recovery_representation_id": row["recovery_representation_id"],
                "projection_morphism_id": row["projection_morphism_id"],
            }
            for nid, row in binding["nodes"].items()
        },
    }
    spec["nodes"]["spectrum"]["representation_id"] = "signal.timeseries.uniform-scalar.v1"
    with pytest.raises(ValueError, match="codomain"):
        binding_from_spec(board, registry, semantic, spec)


def test_gate_is_local_refuse_then_expand_from_same_declared_coordinate(tmp_path):
    board, source, registry, binding, semantic, _ = configured(tmp_path, allow_run=False)
    local = gate_for_request(board, registry, binding, semantic, edit(board, "statistics"))
    refused = gate_for_request(board, registry, binding, semantic, edit(board, "spectrum"))
    expanded = gate_for_request(
        board, registry, binding, semantic, edit(board, "spectrum"),
        recovery_evidence_ref=source["evidence_id"])
    assert local["decision"] == "LOCAL"
    assert refused["decision"] == "REFUSE"
    assert refused["recovery_route"] == "retained source recording"
    assert expanded["decision"] == "EXPAND"
    assert expanded["recovery_representation_id"] == "signal.timeseries.uniform-scalar.v1"
    assert expanded["recovery_evidence_ref"] == source["evidence_id"]


def test_scientific_context_is_exact_registry_content_not_label_inference(tmp_path):
    board, _, registry, binding, semantic, _ = configured(tmp_path, allow_run=False)
    context = context_for_request(board, registry, binding, semantic, edit(board, "spectrum"))
    assert context["current_representation"] == registry["representations"]["signal.periodogram.one-sided-density.v1"]
    assert context["recovery_representation"] == registry["representations"]["signal.timeseries.uniform-scalar.v1"]
    assert context["projection_morphism"] == registry["morphisms"]["signal.periodogram.transform.v1"]
    assert context["claims"]["inspectable_context_only"] is True
    assert context["claims"]["provider_execution"] is False
    assert context["claims"]["execution_authority"] is False


def test_preview_exposes_gate_without_provider_execution(tmp_path):
    board, _, _, _, _, work = configured(tmp_path)
    out = work.preview(edit(board, "spectrum"))
    assert out["intervention_gate"]["decision"] == "REFUSE"
    assert out["recovery_available"] is True
    assert work.session is None
    retained = work.output_dir / out["retained_directory"]
    assert (retained / "intervention-gate.json").is_file()
    assert (retained / "scientific-context.json").is_file()


def test_local_visual_edit_uses_existing_represented_needle(tmp_path):
    board, source, _, _, _, work = configured(tmp_path)
    baseline = work.run_baseline()
    out = work.run_candidate(edit(board, "statistics"), baseline["baseline_ref"])
    assert out["intervention_gate"]["decision"] == "LOCAL"
    assert out["promotion"] is None
    assert out["run"]["rerun_nodes"] == ["statistics", "spectrum"]
    assert out["receipt"]["claims"]["representation_expansion_authorized"] is False
    assert len(work.session.executions) == 5
    assert out["receipt"]["source_evidence_id"] == source["evidence_id"]


def test_lossy_visual_edit_cannot_execute_before_verified_expansion(tmp_path):
    board, _, _, _, _, work = configured(tmp_path)
    baseline = work.run_baseline()
    with pytest.raises(ValueError, match="verify and promote"):
        work.run_candidate(edit(board, "spectrum"), baseline["baseline_ref"])
    assert len(work.session.executions) == 3


def test_verified_visual_expansion_promotes_then_executes_ordinary_needle(tmp_path):
    board, source, _, _, _, work = configured(tmp_path)
    baseline = work.run_baseline()
    original = deepcopy(work.baseline)
    chain = work.qualify_expansion(edit(board, "spectrum"), baseline["baseline_ref"])
    assert chain["gate"]["decision"] == "EXPAND"
    assert chain["verification"]["status"] == "PASS"
    assert chain["promotion"]["local_gate"]["decision"] == "LOCAL"
    assert chain["promotion"]["local_gate"]["representation_id"] == "signal.timeseries.uniform-scalar.v1"
    # Projection verification is a separate Session occurrence, not hidden in the main workbench session.
    assert len(work.session.executions) == 3
    assert work.baseline == original
    out = work.run_candidate(
        edit(board, "spectrum"), baseline["baseline_ref"],
        chain["promotion"]["record_digest"])
    assert out["run"]["rerun_nodes"] == ["spectrum"]
    assert set(out["run"]["reused_nodes"]) == {"statistics", "energy_statistics"}
    assert out["receipt"]["claims"]["representation_expansion_authorized"] is True
    assert out["promotion"]["record_digest"] == chain["promotion"]["record_digest"]
    assert len(work.session.executions) == 4
    assert work.source["evidence_id"] == source["evidence_id"]


def test_promotion_is_bound_to_exact_request_and_baseline(tmp_path):
    board, _, _, _, _, work = configured(tmp_path)
    baseline = work.run_baseline()
    chain = work.qualify_expansion(edit(board, "spectrum"), baseline["baseline_ref"])
    with pytest.raises(ValueError, match="different visual request"):
        work.run_candidate(
            edit(board, "spectrum", "energy"), baseline["baseline_ref"],
            chain["promotion"]["record_digest"])
    with pytest.raises(ValueError, match="baseline"):
        work.run_candidate(
            edit(board, "spectrum"), "sha256:" + "0" * 64,
            chain["promotion"]["record_digest"])


def test_resealed_binding_cannot_change_scientific_identity(tmp_path):
    board, _, registry, binding, semantic, _ = configured(tmp_path, allow_run=False)
    binding["nodes"]["spectrum"]["representation_id"] = "signal.timeseries.uniform-scalar.v1"
    with pytest.raises(ValueError):
        validate_binding(seal(binding), board, registry, semantic)


def http(server, path, value):
    headers = {
        "X-NET-Board-Token": server.board_token,
        "Content-Type": "application/json",
    }
    raw = json.dumps(value)
    conn = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    conn.request("POST", path, body=raw, headers=headers)
    response = conn.getresponse()
    data = json.loads(response.read())
    code = response.status
    conn.close()
    return code, data


def test_http_refuse_expand_promote_execute_chain(tmp_path):
    board, _, _, _, _, work = configured(tmp_path)
    server = make_server(work)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        code, base = http(server, "/api/baseline", {"board_ref": board["record_digest"]})
        assert code == 200
        request = edit(board, "spectrum")
        code, preview = http(server, "/api/edit", request)
        assert code == 200
        assert preview["intervention_gate"]["decision"] == "REFUSE"
        assert preview["recovery_available"] is True
        code, refused = http(server, "/api/candidate", {
            "request": request, "baseline_ref": base["baseline_ref"], "promotion_ref": None})
        assert code == 400
        assert "verify and promote" in refused["reason"]
        code, chain = http(server, "/api/expand", {
            "request": request, "baseline_ref": base["baseline_ref"]})
        assert code == 200
        assert chain["verification"]["status"] == "PASS"
        code, executed = http(server, "/api/candidate", {
            "request": request, "baseline_ref": base["baseline_ref"],
            "promotion_ref": chain["promotion"]["record_digest"]})
        assert code == 200
        assert executed["receipt"]["claims"]["representation_expansion_authorized"] is True
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
