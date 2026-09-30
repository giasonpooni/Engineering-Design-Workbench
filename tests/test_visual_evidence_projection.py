from copy import deepcopy
import json
from http.client import HTTPConnection
import threading

import pytest

from ciw.core.identities import content_identity
from ciw.operations.runner import seal
from ciw.representation_realizations import (
    board_evidence_projection,
    finite_result_witness,
    operation_result_realization,
    source_channel_realization,
    validate_board_evidence_projection,
    validate_realization,
)
from ciw.visual_board_server import make_server
from test_visual_representation_gate import configured


def test_source_channel_realization_is_exact_retained_content_not_verification(tmp_path):
    board, source, registry, binding, semantic, work = configured(tmp_path, allow_run=False)
    value = source_channel_realization(source, registry, semantic, {
        "realization_id": "q-source",
        "representation_id": "signal.timeseries.uniform-scalar.v1",
        "channel": "q",
        "interval_s": [0.0, source["metadata"]["duration_s"]],
        "notes": "",
    })
    assert value["subject_kind"] == "SOURCE_CHANNEL"
    assert value["source_evidence_ref"] == source["evidence_id"]
    assert value["observed"]["unit"] == "m"
    assert value["observed"]["sample_count"] == source["metadata"]["sample_count"]
    assert value["record_verification"]["status"] == "not_applicable"
    assert value["claims"]["contract_realization_established"] is True
    assert value["claims"]["empirical_physical_validity_established"] is False
    assert validate_realization(value, source, registry, semantic) == value


def test_operation_result_realization_binds_exact_morphism_execution_and_result(tmp_path):
    board, source, registry, binding, semantic, work = configured(tmp_path)
    base = work.run_baseline()["run"]
    payload = base["nodes"]["spectrum"]
    value = operation_result_realization(
        source, payload["execution"], payload["result"], registry, semantic, {
            "realization_id": "periodogram-result",
            "morphism_id": "signal.periodogram.transform.v1",
            "notes": "",
        })
    assert value["subject_kind"] == "OPERATION_RESULT"
    assert value["representation_id"] == "signal.periodogram.one-sided-density.v1"
    assert value["execution_ref"] == content_identity(payload["execution"])
    assert value["result_ref"] == content_identity(payload["result"])
    assert value["realized_content_ref"] == content_identity(payload["result"]["data"])
    assert value["record_verification"] == {"status": "not_verified", "verification_id": None}
    assert value["uncertainty"]["morphism"]["behavior"] == "UNKNOWN"
    assert validate_realization(
        value, source, registry, semantic,
        execution=payload["execution"], result=payload["result"]) == value


def test_finite_morphism_witness_keeps_preservation_and_physical_validity_unresolved(tmp_path):
    board, source, registry, binding, semantic, work = configured(tmp_path)
    base = work.run_baseline()["run"]
    payload = base["nodes"]["spectrum"]
    src = source_channel_realization(source, registry, semantic, {
        "realization_id": "domain-q",
        "representation_id": "signal.timeseries.uniform-scalar.v1",
        "channel": "q", "interval_s": payload["result"]["interval_s"], "notes": "",
    })
    dst = operation_result_realization(
        source, payload["execution"], payload["result"], registry, semantic, {
            "realization_id": "codomain-periodogram",
            "morphism_id": "signal.periodogram.transform.v1", "notes": "",
        })
    witness = finite_result_witness(
        src, dst, source, payload["execution"], payload["result"],
        registry, semantic, "periodogram-finite-witness")
    counts = {status: sum(row["status"] == status for row in witness["checks"])
              for status in ("PASS", "FAIL", "UNRESOLVED")}
    assert counts == {"PASS": 4, "FAIL": 0, "UNRESOLVED": 2}
    assert witness["claims"]["general_morphism_law_proved"] is False
    assert witness["claims"]["physical_validity_established"] is False
    assert {row["kind"] for row in witness["checks"] if row["status"] == "UNRESOLVED"} == {
        "PRESERVATION", "VALIDITY"}


def test_board_projection_separates_source_and_result_realizations(tmp_path):
    board, source, registry, binding, semantic, work = configured(tmp_path)
    baseline = work.run_baseline()["run"]
    value = board_evidence_projection(
        board, baseline, source, registry, binding, semantic)
    assert set(value["nodes"]) == {"statistics", "spectrum", "energy_statistics"}
    stats = value["nodes"]["statistics"]
    spectrum = value["nodes"]["spectrum"]
    energy = value["nodes"]["energy_statistics"]
    assert stats["current_realization"]["subject_kind"] == "SOURCE_CHANNEL"
    assert stats["current_realization"]["observed"]["unit"] == "m"
    assert energy["current_realization"]["observed"]["unit"] == "J"
    assert spectrum["current_realization"]["subject_kind"] == "OPERATION_RESULT"
    assert spectrum["source_realization"]["subject_kind"] == "SOURCE_CHANNEL"
    assert spectrum["result_realization"]["representation_id"] == "signal.periodogram.one-sided-density.v1"
    assert spectrum["witness_summary"] == {
        "PASS": 4, "FAIL": 0, "UNRESOLVED": 2,
        "status": "FINITE_WITNESS_WITH_UNRESOLVED",
        "physical_validity_established": False,
    }
    assert spectrum["record_verification"]["status"] == "not_verified"
    assert spectrum["physical_validity"] == "NOT_ESTABLISHED"
    assert value["claims"]["intervention_authority_unchanged"] is True
    assert validate_board_evidence_projection(
        value, board, baseline, source, registry, binding, semantic) == value


def test_resealed_realization_and_projection_tampering_fail_recomputation(tmp_path):
    board, source, registry, binding, semantic, work = configured(tmp_path)
    baseline = work.run_baseline()["run"]
    projection = board_evidence_projection(
        board, baseline, source, registry, binding, semantic)
    spectrum = deepcopy(projection["nodes"]["spectrum"]["result_realization"])
    spectrum["realized_content_ref"] = "sha256:" + "0" * 64
    payload = baseline["nodes"]["spectrum"]
    with pytest.raises(ValueError, match="differs from exact retained content"):
        validate_realization(
            seal(spectrum), source, registry, semantic,
            execution=payload["execution"], result=payload["result"])

    projection["nodes"]["spectrum"]["physical_validity"] = "ESTABLISHED"
    with pytest.raises(ValueError, match="differs from exact retained evidence"):
        validate_board_evidence_projection(
            seal(projection), board, baseline, source, registry, binding, semantic)


def test_projection_refuses_different_source_or_board_baseline(tmp_path):
    board, source, registry, binding, semantic, work = configured(tmp_path)
    baseline = work.run_baseline()["run"]
    other = deepcopy(source)
    other["channels"]["q"]["values"][0] += 0.1
    from ciw.core.identities import evidence_id
    other["evidence_id"] = evidence_id(other)
    with pytest.raises(ValueError, match="baseline/source mismatch"):
        board_evidence_projection(board, baseline, other, registry, binding, semantic)

    changed = deepcopy(board)
    changed["title"] = "different"
    changed = seal(changed)
    with pytest.raises(ValueError, match="exact Board compilation"):
        board_evidence_projection(changed, baseline, source, registry, binding, semantic)


def test_workbench_retains_projection_only_after_completed_baseline(tmp_path):
    board, source, registry, binding, semantic, work = configured(tmp_path)
    assert work.evidence_projection is None
    out = work.run_baseline()
    assert out["evidence_projection"]["schema"] == "ciw.board-evidence-projection.v1"
    assert work.evidence_projection == out["evidence_projection"]
    retained = work.output_dir / out["retained_directory"]
    assert (retained / "evidence-projection.json").is_file()
    assert json.loads((retained / "evidence-projection.json").read_text()) == work.evidence_projection


def test_candidate_execution_does_not_rewrite_baseline_evidence_projection(tmp_path):
    board, source, registry, binding, semantic, work = configured(tmp_path)
    base = work.run_baseline()
    original = deepcopy(work.evidence_projection)
    request = {
        "schema": "ciw.board-parameter-edit.v1",
        "base_board_ref": board["record_digest"],
        "node_id": "statistics", "parameter": "channel", "replacement": "v",
    }
    work.run_candidate(request, base["baseline_ref"])
    assert work.evidence_projection == original
    assert work.evidence_projection["baseline_ref"] == base["baseline_ref"]


def _get(server, path):
    conn = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    conn.request("GET", path, headers={"X-NET-Board-Token": server.board_token})
    response = conn.getresponse()
    value = json.loads(response.read())
    code = response.status
    conn.close()
    return code, value


def test_api_state_exposes_retained_projection_without_new_provider_execution(tmp_path):
    board, source, registry, binding, semantic, work = configured(tmp_path)
    base = work.run_baseline()
    count = len(work.session.executions)
    server = make_server(work)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        code, state = _get(server, "/api/state")
        assert code == 200
        assert state["evidence_projection"] == work.evidence_projection
        assert state["evidence_projection"]["baseline_ref"] == base["baseline_ref"]
        assert len(work.session.executions) == count
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_no_scientific_binding_means_no_claimed_evidence_projection(tmp_path):
    from ciw.visual_board import demo_board
    from ciw.visual_board_server import BoardWorkbench
    from ciw.instruments import make_demo_run

    board = demo_board()
    work = BoardWorkbench(board, tmp_path / "ungated", source=make_demo_run(), allow_run=True)
    out = work.run_baseline()
    assert out["evidence_projection"] is None
    assert work.evidence_projection is None
