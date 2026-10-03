from copy import deepcopy
import json
import subprocess
import sys

import pytest

from ciw.annotations import (
    annotation_from_spec,
    annotation_stream,
    inspect_annotation,
    validate_annotation,
)
from ciw.core.identities import content_identity


def ref(char="1"):
    return "sha256:" + char * 64


def spec(**updates):
    value = {
        "author": {"kind": "human", "id": "engineer-17"},
        "authored_at": "2026-09-29T14:15:00-04:00",
        "target": {"kind": "OBSERVATION", "id": "pressure_sensor_17:82914", "version": ref("a")},
        "kind": "HYPOTHESIS",
        "content": {
            "text": "Possible calibration drift.",
            "structured": {"assertion": "possible_calibration_drift"},
        },
        "evidence_refs": [ref("2")],
        "model_refs": ["pressure-loop-model.v3"],
        "operation_refs": ["analysis.residual.v1"],
        "requested_operations": ["measure.calibrate.v1"],
        "confidence": 0.65,
        "status": "OPEN",
        "supersedes": None,
    }
    value.update(updates)
    return value


def test_annotation_is_first_class_human_interpretive_state():
    value = annotation_from_spec(spec())
    validate_annotation(value)
    assert value["schema"] == "ciw.annotation.v1"
    assert value["kind"] == "HYPOTHESIS"
    assert value["claims"] == {
        "human_interpretive_state": True,
        "canonical_evidence": False,
        "canonical_state": False,
        "verification": False,
        "execution_authority": False,
    }
    assert value["requested_operations"] == ["measure.calibrate.v1"]


def test_annotation_retains_target_version_and_structured_content():
    value = annotation_from_spec(spec())
    assert value["target"]["version"] == ref("a")
    assert value["content"]["structured"]["assertion"] == "possible_calibration_drift"


def test_machine_authorship_is_separate_from_annotation_v1():
    value = spec()
    value["author"] = {"kind": "agent", "id": "model-1"}
    with pytest.raises(ValueError, match="human-authored"):
        annotation_from_spec(value)


@pytest.mark.parametrize("confidence", [-0.1, 1.1, float("nan"), True])
def test_invalid_self_assessed_confidence_refuses(confidence):
    with pytest.raises(ValueError, match="confidence"):
        annotation_from_spec(spec(confidence=confidence))


def test_evidence_refs_are_content_identities_not_free_text():
    with pytest.raises(ValueError, match="SHA256"):
        annotation_from_spec(spec(evidence_refs=["document-17"]))


def test_requested_operations_are_semantic_not_engine_names():
    with pytest.raises(ValueError, match="semantic capability"):
        annotation_from_spec(spec(requested_operations=["python:calibrate"]))


def test_unexpected_authority_field_refuses():
    value = spec()
    value["release_authorized"] = True
    with pytest.raises(ValueError, match="Unexpected"):
        annotation_from_spec(value)


def test_correction_is_a_new_record_that_can_supersede_prior_annotation():
    first = annotation_from_spec(spec())
    second_spec = spec(
        authored_at="2026-09-29T14:22:00-04:00",
        kind="INTERPRETATION",
        content={
            "text": "Calibration drift not supported after the calibration check.",
            "structured": {"interpretation": "drift_not_supported"},
        },
        requested_operations=[],
        confidence=0.9,
        status="RESOLVED",
        supersedes=first["record_digest"],
    )
    second = annotation_from_spec(second_spec)
    assert second["record_digest"] != first["record_digest"]
    assert second["supersedes"] == first["record_digest"]
    assert first["status"] == "OPEN"


def test_timeline_is_chronological_even_when_inputs_are_not():
    late = annotation_from_spec(spec(authored_at="2026-09-29T14:20:00-04:00"))
    early = annotation_from_spec(spec(authored_at="2026-09-29T14:10:00-04:00"))
    value = annotation_stream([late, early])
    assert [row["authored_at"] for row in value["annotations"]] == [
        "2026-09-29T14:10:00-04:00",
        "2026-09-29T14:20:00-04:00",
    ]
    assert value["claims"]["chronological_projection"] is True
    assert value["claims"]["canonical_evidence"] is False


def test_timeline_refuses_duplicate_records():
    value = annotation_from_spec(spec())
    with pytest.raises(ValueError, match="duplicate"):
        annotation_stream([value, value])


def test_tamper_breaks_annotation_integrity():
    value = annotation_from_spec(spec())
    value["content"]["text"] = "tampered"
    with pytest.raises(ValueError):
        validate_annotation(value)


def test_inspection_preserves_epistemic_boundary():
    value = annotation_from_spec(spec())
    inspected = inspect_annotation(value)
    assert inspected["human_interpretive_state"] is True
    assert inspected["canonical_evidence"] is False
    assert inspected["canonical_state"] is False
    assert inspected["verification"] is False
    assert inspected["execution_authority"] is False


def test_cli_create_inspect_and_timeline(tmp_path):
    spec_path = tmp_path / "spec.json"
    annotation_path = tmp_path / "annotation.json"
    second_path = tmp_path / "second.json"
    timeline_path = tmp_path / "timeline.json"
    spec_path.write_text(json.dumps(spec()))
    subprocess.run([
        sys.executable, "-m", "ciw.net", "annotation", "create",
        str(spec_path), "--output", str(annotation_path),
    ], cwd=tmp_path, check=True)
    first = json.loads(annotation_path.read_text())
    second_spec = spec(
        authored_at="2026-09-29T14:30:00-04:00",
        supersedes=first["record_digest"],
        status="RESOLVED",
    )
    second_spec_path = tmp_path / "second-spec.json"
    second_spec_path.write_text(json.dumps(second_spec))
    subprocess.run([
        sys.executable, "-m", "ciw.net", "annotation", "create",
        str(second_spec_path), "--output", str(second_path),
    ], cwd=tmp_path, check=True)
    output = subprocess.check_output([
        sys.executable, "-m", "ciw.net", "annotation", "inspect",
        str(annotation_path),
    ], cwd=tmp_path, text=True)
    assert json.loads(output)["kind"] == "HYPOTHESIS"
    subprocess.run([
        sys.executable, "-m", "ciw.net", "annotation", "timeline",
        str(second_path), str(annotation_path), "--output", str(timeline_path),
    ], cwd=tmp_path, check=True)
    timeline = json.loads(timeline_path.read_text())
    assert timeline["schema"] == "ciw.annotation-stream.v1"
    assert len(timeline["annotations"]) == 2
