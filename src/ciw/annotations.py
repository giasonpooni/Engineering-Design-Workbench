"""Immutable human annotations as first-class NET records.

Annotation is human interpretive state. It is deliberately distinct from evidence,
canonical state, verification and machine proposals. Corrections create new
records; they never mutate prior annotation bytes.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import math
import re
from typing import Any

from .control_contracts import (
    content_ref,
    detached,
    json_tree,
    keys,
    record,
    text,
)
from .operations.runner import check_seal

ANNOTATION_KINDS = {
    "OBSERVATION",
    "HYPOTHESIS",
    "INTERPRETATION",
    "CONSTRAINT",
    "QUESTION",
    "DECISION",
    "INSTRUCTION",
}
TARGET_KINDS = {
    "ENTITY",
    "OBSERVATION",
    "STATE",
    "ARTIFACT",
    "MODEL",
    "RESULT",
    "VERIFICATION",
    "OPERATION",
    "SCHEMATIC",
    "REPRESENTATION",
}
STATUSES = {"OPEN", "RESOLVED", "WITHDRAWN"}
CAPABILITY = re.compile(r"[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+\.v[1-9][0-9]*$")
MAX_REFS = 64
MAX_TEXT = 8192


def _long_text(value: Any, label: str) -> str:
    if type(value) is not str or not value.strip() or len(value) > MAX_TEXT:
        raise ValueError(f"{label} must be bounded nonempty text")
    return value


def _time(value: Any) -> str:
    value = text(value)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("authored_at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("authored_at must carry a timezone")
    return value


def _refs(values: Any, label: str, validator) -> list[str]:
    if type(values) is not list or len(values) > MAX_REFS:
        raise ValueError(f"{label} must be a bounded list")
    result = [validator(value) for value in values]
    if len(result) != len(set(result)):
        raise ValueError(f"{label} contains duplicates")
    return result


def _semantic(value: Any) -> str:
    if type(value) is not str or CAPABILITY.fullmatch(value) is None or len(value) > 160:
        raise ValueError("operation references must be versioned semantic capability IDs")
    return value


def _author(value: Any) -> dict:
    keys(value, {"kind", "id"})
    if value["kind"] != "human":
        raise ValueError("Annotation V1 is human-authored interpretive state; machine proposals use a separate record class")
    return {"kind": "human", "id": text(value["id"])}


def _target(value: Any) -> dict:
    keys(value, {"kind", "id", "version"})
    if value["kind"] not in TARGET_KINDS:
        raise ValueError("Unknown annotation target kind")
    target = {"kind": value["kind"], "id": text(value["id"]), "version": None}
    if value["version"] is not None:
        target["version"] = text(value["version"])
    return target


def _content(value: Any) -> dict:
    keys(value, {"text", "structured"})
    structured = value["structured"]
    if structured is not None:
        if type(structured) is not dict:
            raise ValueError("annotation structured content must be an object or null")
        json_tree(structured)
    return {"text": _long_text(value["text"], "annotation content"), "structured": deepcopy(structured)}


def annotation_from_spec(spec: dict) -> dict:
    """Create one immutable annotation from a bounded explicit specification."""
    keys(spec, {
        "author", "authored_at", "target", "kind", "content",
        "evidence_refs", "model_refs", "operation_refs", "requested_operations",
        "confidence", "status", "supersedes",
    })
    author = _author(spec["author"])
    authored_at = _time(spec["authored_at"])
    target = _target(spec["target"])
    if spec["kind"] not in ANNOTATION_KINDS:
        raise ValueError("Unknown annotation kind")
    content = _content(spec["content"])
    evidence_refs = _refs(spec["evidence_refs"], "evidence_refs", content_ref)
    model_refs = _refs(spec["model_refs"], "model_refs", text)
    operation_refs = _refs(spec["operation_refs"], "operation_refs", _semantic)
    requested_operations = _refs(
        spec["requested_operations"], "requested_operations", _semantic)

    confidence = spec["confidence"]
    if confidence is not None:
        if type(confidence) not in (int, float) or isinstance(confidence, bool):
            raise ValueError("annotation confidence must be a number in [0,1] or null")
        confidence = float(confidence)
        if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            raise ValueError("annotation confidence must be a number in [0,1] or null")

    if spec["status"] not in STATUSES:
        raise ValueError("Unknown annotation status")
    supersedes = spec["supersedes"]
    if supersedes is not None:
        supersedes = content_ref(supersedes)

    value = record(
        "annotation",
        author=author,
        authored_at=authored_at,
        target=target,
        kind=spec["kind"],
        content=content,
        evidence_refs=evidence_refs,
        model_refs=model_refs,
        operation_refs=operation_refs,
        requested_operations=requested_operations,
        confidence=confidence,
        status=spec["status"],
        supersedes=supersedes,
        claims={
            "human_interpretive_state": True,
            "canonical_evidence": False,
            "canonical_state": False,
            "verification": False,
            "execution_authority": False,
        },
    )
    validate_annotation(value)
    return value


def validate_annotation(value: dict) -> dict:
    keys(value, {
        "schema", "record_digest", "author", "authored_at", "target", "kind",
        "content", "evidence_refs", "model_refs", "operation_refs",
        "requested_operations", "confidence", "status", "supersedes", "claims",
    })
    if value["schema"] != "ciw.annotation.v1":
        raise ValueError("Wrong annotation schema")
    check_seal(value)
    _author(value["author"])
    _time(value["authored_at"])
    _target(value["target"])
    if value["kind"] not in ANNOTATION_KINDS:
        raise ValueError("Unknown annotation kind")
    _content(value["content"])
    _refs(value["evidence_refs"], "evidence_refs", content_ref)
    _refs(value["model_refs"], "model_refs", text)
    _refs(value["operation_refs"], "operation_refs", _semantic)
    _refs(value["requested_operations"], "requested_operations", _semantic)
    if value["confidence"] is not None:
        confidence = value["confidence"]
        if type(confidence) not in (int, float) or isinstance(confidence, bool):
            raise ValueError("Invalid annotation confidence")
        if not math.isfinite(float(confidence)) or not 0.0 <= float(confidence) <= 1.0:
            raise ValueError("Invalid annotation confidence")
    if value["status"] not in STATUSES:
        raise ValueError("Unknown annotation status")
    if value["supersedes"] is not None:
        content_ref(value["supersedes"])
        if value["supersedes"] == value["record_digest"]:
            raise ValueError("Annotation cannot supersede itself")
    expected_claims = {
        "human_interpretive_state": True,
        "canonical_evidence": False,
        "canonical_state": False,
        "verification": False,
        "execution_authority": False,
    }
    if value["claims"] != expected_claims:
        raise ValueError("Annotation claims exceed human interpretive-state authority")
    return detached(value)


def annotation_stream(values: list[dict]) -> dict:
    """Create a chronological read projection over immutable annotations."""
    if type(values) is not list or not 1 <= len(values) <= 4096:
        raise ValueError("annotation stream requires 1..4096 annotations")
    checked = [validate_annotation(value) for value in values]
    digests = [value["record_digest"] for value in checked]
    if len(digests) != len(set(digests)):
        raise ValueError("annotation stream contains duplicate records")
    ordered = sorted(checked, key=lambda item: (item["authored_at"], item["record_digest"]))
    result = record(
        "annotation-stream",
        annotations=ordered,
        order="authored_at_then_record_digest",
        claims={
            "chronological_projection": True,
            "canonical_evidence": False,
            "canonical_state": False,
            "verification": False,
            "execution_authority": False,
        },
    )
    validate_annotation_stream(result)
    return result


def validate_annotation_stream(value: dict) -> dict:
    keys(value, {"schema", "record_digest", "annotations", "order", "claims"})
    if value["schema"] != "ciw.annotation-stream.v1":
        raise ValueError("Wrong annotation-stream schema")
    check_seal(value)
    if value["order"] != "authored_at_then_record_digest":
        raise ValueError("Unknown annotation stream ordering")
    if type(value["annotations"]) is not list or not 1 <= len(value["annotations"]) <= 4096:
        raise ValueError("annotation stream requires 1..4096 annotations")
    checked = [validate_annotation(item) for item in value["annotations"]]
    digests = [item["record_digest"] for item in checked]
    if len(digests) != len(set(digests)):
        raise ValueError("annotation stream contains duplicate records")
    expected = sorted(checked, key=lambda item: (item["authored_at"], item["record_digest"]))
    if [item["record_digest"] for item in checked] != [item["record_digest"] for item in expected]:
        raise ValueError("annotation stream is not chronological")
    expected_claims = {
        "chronological_projection": True,
        "canonical_evidence": False,
        "canonical_state": False,
        "verification": False,
        "execution_authority": False,
    }
    if value["claims"] != expected_claims:
        raise ValueError("Annotation stream claims exceed projection authority")
    return detached(value)


def inspect_annotation(value: dict) -> dict:
    value = validate_annotation(value)
    return {
        "schema": "ciw.annotation-inspection.v1",
        "record_digest": value["record_digest"],
        "author": deepcopy(value["author"]),
        "authored_at": value["authored_at"],
        "target": deepcopy(value["target"]),
        "kind": value["kind"],
        "status": value["status"],
        "confidence": value["confidence"],
        "evidence_refs": len(value["evidence_refs"]),
        "model_refs": len(value["model_refs"]),
        "requested_operations": deepcopy(value["requested_operations"]),
        "human_interpretive_state": True,
        "canonical_evidence": False,
        "canonical_state": False,
        "verification": False,
        "execution_authority": False,
    }
