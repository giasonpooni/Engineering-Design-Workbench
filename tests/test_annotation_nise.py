import json
import subprocess
import sys

import pytest

from ciw.annotation_nise import compile_annotation_query
from ciw.annotations import annotation_from_spec


def ref(char):
    return "sha256:" + char * 64


def annotation():
    return annotation_from_spec({
        "author": {"kind": "human", "id": "engineer-17"},
        "authored_at": "2026-09-29T14:15:00-04:00",
        "target": {"kind": "ENTITY", "id": "oscillator", "version": ref("a")},
        "kind": "QUESTION",
        "content": {
            "text": "Inspect the retained oscillator observations.",
            "structured": {"intent": "inspect_oscillator"},
        },
        "evidence_refs": [ref("2")],
        "model_refs": ["analytic-damped-oscillator.v1"],
        "operation_refs": [],
        "requested_operations": [
            "analysis.statistics.v1",
            "analysis.spectrum.v1",
        ],
        "confidence": None,
        "status": "OPEN",
        "supersedes": None,
    })


def seed(annotation_ref):
    return {
        "schema": "ciw.annotation-nise-seed.v1",
        "seed_id": "seed-001",
        "annotation_ref": annotation_ref,
        "query_id": "annotation-oscillator-investigation",
        "focus_node_ids": ["oscillator"],
        "additional_capabilities": [],
        "max_hops": 2,
        "node_budget": 16,
        "include_hypotheses": False,
    }


def test_annotation_compiles_to_nise_query_without_semantic_inference():
    a = annotation()
    result = compile_annotation_query(a, seed(a["record_digest"]))
    assert result["schema"] == "ciw.annotation-nise-query.v1"
    assert result["query"]["schema"] == "nise.query.v1"
    assert result["query"]["question"] == a["content"]["text"]
    assert result["query"]["focus_node_ids"] == ["oscillator"]
    assert result["query"]["requested_capabilities"] == [
        "analysis.spectrum.v1", "analysis.statistics.v1"]
    assert result["claims"]["human_intent_attached"] is True
    assert result["claims"]["semantic_retrieval_performed"] is False
    assert result["claims"]["focus_inferred_from_annotation"] is False
    assert result["claims"]["execution_authority"] is False


def test_annotation_evidence_and_target_are_retained_in_receipt():
    a = annotation()
    result = compile_annotation_query(a, seed(a["record_digest"]))
    assert result["annotation_ref"] == a["record_digest"]
    assert result["target"] == a["target"]
    assert result["evidence_refs"] == a["evidence_refs"]
    assert result["model_refs"] == a["model_refs"]


def test_operator_may_add_semantic_capability_without_engine_selection():
    a = annotation()
    s = seed(a["record_digest"])
    s["additional_capabilities"] = ["analysis.diagnostics.v1"]
    result = compile_annotation_query(a, s)
    assert "analysis.diagnostics.v1" in result["query"]["requested_capabilities"]
    assert result["claims"]["engine_selected"] is False


def test_seed_cannot_target_different_annotation():
    a = annotation()
    s = seed(ref("f"))
    with pytest.raises(ValueError, match="different annotation"):
        compile_annotation_query(a, s)


def test_explicit_focus_is_required():
    a = annotation()
    s = seed(a["record_digest"])
    s["focus_node_ids"] = []
    with pytest.raises(ValueError, match="explicit focus"):
        compile_annotation_query(a, s)


def test_withdrawn_annotation_cannot_seed_new_investigation():
    a = annotation()
    changed = {
        "author": a["author"],
        "authored_at": "2026-09-29T14:30:00-04:00",
        "target": a["target"],
        "kind": a["kind"],
        "content": a["content"],
        "evidence_refs": a["evidence_refs"],
        "model_refs": a["model_refs"],
        "operation_refs": a["operation_refs"],
        "requested_operations": a["requested_operations"],
        "confidence": a["confidence"],
        "status": "WITHDRAWN",
        "supersedes": a["record_digest"],
    }
    withdrawn = annotation_from_spec(changed)
    with pytest.raises(ValueError, match="Withdrawn"):
        compile_annotation_query(withdrawn, seed(withdrawn["record_digest"]))


def test_seed_does_not_allow_provider_or_engine_fields():
    a = annotation()
    s = seed(a["record_digest"])
    s["engine_id"] = "python"
    with pytest.raises(ValueError):
        compile_annotation_query(a, s)


def test_cli_writes_query_and_receipt_create_only(tmp_path):
    a = annotation()
    annotation_path = tmp_path / "annotation.json"
    seed_path = tmp_path / "seed.json"
    query_path = tmp_path / "query.json"
    receipt_path = tmp_path / "receipt.json"
    annotation_path.write_text(json.dumps(a))
    seed_path.write_text(json.dumps(seed(a["record_digest"])))

    subprocess.run([
        sys.executable, "-m", "ciw.net", "annotation", "nise-query",
        str(annotation_path), str(seed_path),
        "--query-output", str(query_path),
        "--receipt-output", str(receipt_path),
    ], cwd=tmp_path, check=True)

    query = json.loads(query_path.read_text())
    receipt = json.loads(receipt_path.read_text())
    assert query["schema"] == "nise.query.v1"
    assert receipt["annotation_ref"] == a["record_digest"]

    second = subprocess.run([
        sys.executable, "-m", "ciw.net", "annotation", "nise-query",
        str(annotation_path), str(seed_path),
        "--query-output", str(query_path),
        "--receipt-output", str(tmp_path / "other-receipt.json"),
    ], cwd=tmp_path, text=True, capture_output=True)
    assert second.returncode == 1
