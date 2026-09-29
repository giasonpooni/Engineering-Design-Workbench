"""Portable artifact/IP provenance declarations.

This is descriptive provenance metadata, not a legal rights engine. A declaration
cannot prove ownership, adjudicate licence compatibility, transfer rights, or
authorize redistribution/execution.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
import re
from typing import Any

from .control_contracts import content_ref, detached, keys, text
from .core.identities import content_identity

SCHEMA = "notations.artifact-provenance.v1"
ASSET_CLASSES = {
    "OPEN_INFRASTRUCTURE",
    "PROPRIETARY_IP",
    "THIRD_PARTY",
    "INTERNAL",
    "MIXED",
}
ORIGIN_KINDS = {
    "ORIGINAL",
    "DERIVED",
    "GENERATED",
    "IMPORTED",
    "COMMISSIONED",
    "UPSTREAM",
}
RELATIONSHIPS = {
    "DEPENDS_ON",
    "DERIVED_FROM",
    "INCORPORATES",
    "GENERATED_WITH",
    "REFERENCES",
}
MAX_ITEMS = 128
URL = re.compile(r"https://[^\s]{1,2048}$")
REVISION = re.compile(r"[0-9a-fA-F]{7,64}$")
SPDXISH = re.compile(r"[A-Za-z0-9.+():\- ]{1,256}$")


def _bounded_list(value: Any, label: str, validator, maximum: int = MAX_ITEMS):
    if type(value) is not list or len(value) > maximum:
        raise ValueError(f"{label} must be a bounded list")
    result = [validator(item) for item in value]
    return result


def _unique_strings(value: Any, label: str, maximum: int = MAX_ITEMS) -> list[str]:
    result = _bounded_list(value, label, text, maximum)
    if len(result) != len(set(result)):
        raise ValueError(f"{label} contains duplicates")
    return result


def _url(value: Any) -> str:
    if type(value) is not str or URL.fullmatch(value) is None:
        raise ValueError("repository url must be bounded HTTPS")
    return value


def _revision(value: Any) -> str:
    if type(value) is not str or REVISION.fullmatch(value) is None:
        raise ValueError("repository revision must be a 7..64 hex identifier")
    return value.lower()


def _spdxish(value: Any) -> str:
    if type(value) is not str or SPDXISH.fullmatch(value) is None:
        raise ValueError("licence expression must be bounded SPDX-like text")
    return value


def _time(value: Any) -> str:
    value = text(value)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("declared_at must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("declared_at must be timezone-aware")
    return value


def _artifact(value: Any) -> dict:
    keys(value, {"artifact_id", "kind", "content_ref"})
    return {
        "artifact_id": text(value["artifact_id"]),
        "kind": text(value["kind"]),
        "content_ref": content_ref(value["content_ref"]),
    }


def _ownership(value: Any) -> dict:
    keys(value, {"declared_owner", "asset_class", "basis_refs"})
    if value["asset_class"] not in ASSET_CLASSES:
        raise ValueError("unknown asset_class")
    return {
        "declared_owner": text(value["declared_owner"]),
        "asset_class": value["asset_class"],
        "basis_refs": _unique_strings(value["basis_refs"], "ownership basis_refs"),
    }


def _repository(value: Any) -> dict | None:
    if value is None:
        return None
    keys(value, {"url", "revision", "path"})
    path = value["path"]
    if type(path) is not str or not path or len(path) > 1024 or path.startswith("/"):
        raise ValueError("repository path must be bounded and relative")
    if ".." in path.split("/"):
        raise ValueError("repository path cannot traverse")
    return {"url": _url(value["url"]), "revision": _revision(value["revision"]), "path": path}


def _origin(value: Any) -> dict:
    keys(value, {"kind", "description", "source_refs"})
    if value["kind"] not in ORIGIN_KINDS:
        raise ValueError("unknown origin kind")
    return {
        "kind": value["kind"],
        "description": text(value["description"]),
        "source_refs": _unique_strings(value["source_refs"], "origin source_refs"),
    }


def _license(value: Any) -> dict:
    keys(value, {"expression", "license_text_ref", "notice_refs"})
    return {
        "expression": _spdxish(value["expression"]),
        "license_text_ref": content_ref(value["license_text_ref"]),
        "notice_refs": _unique_strings(value["notice_refs"], "notice_refs"),
    }


def _contributors(value: Any) -> list[dict]:
    if type(value) is not list or len(value) > MAX_ITEMS:
        raise ValueError("contributors must be a bounded list")
    result = []
    seen = set()
    for row in value:
        keys(row, {"id", "role", "contribution_refs"})
        identity = text(row["id"])
        key = (identity, text(row["role"]))
        if key in seen:
            raise ValueError("duplicate contributor/role")
        seen.add(key)
        result.append({
            "id": identity,
            "role": row["role"],
            "contribution_refs": _unique_strings(
                row["contribution_refs"], "contribution_refs"),
        })
    return result


def _dependencies(value: Any) -> list[dict]:
    if type(value) is not list or len(value) > MAX_ITEMS:
        raise ValueError("dependencies must be a bounded list")
    result = []
    seen = set()
    for row in value:
        keys(row, {
            "artifact_id", "relationship", "content_ref",
            "license_expression", "source_ref",
        })
        artifact_id = text(row["artifact_id"])
        if artifact_id in seen:
            raise ValueError("duplicate dependency artifact")
        seen.add(artifact_id)
        if row["relationship"] not in RELATIONSHIPS:
            raise ValueError("unknown dependency relationship")
        result.append({
            "artifact_id": artifact_id,
            "relationship": row["relationship"],
            "content_ref": content_ref(row["content_ref"]),
            "license_expression": _spdxish(row["license_expression"]),
            "source_ref": text(row["source_ref"]),
        })
    return result


def _use_policy(value: Any) -> dict:
    keys(value, {
        "policy_id", "declared_allowed_contexts",
        "declared_prohibited_contexts", "basis_refs",
    })
    allowed = _unique_strings(value["declared_allowed_contexts"], "allowed contexts")
    prohibited = _unique_strings(value["declared_prohibited_contexts"], "prohibited contexts")
    if set(allowed) & set(prohibited):
        raise ValueError("use-policy context cannot be both allowed and prohibited")
    return {
        "policy_id": text(value["policy_id"]),
        "declared_allowed_contexts": allowed,
        "declared_prohibited_contexts": prohibited,
        "basis_refs": _unique_strings(value["basis_refs"], "use policy basis_refs"),
    }


def validate_declaration(value: dict) -> dict:
    keys(value, {
        "schema", "declaration_id", "declared_at", "artifact", "ownership",
        "repository", "origin", "license", "contributors", "dependencies",
        "use_policy", "claims",
    })
    if value["schema"] != SCHEMA:
        raise ValueError("unsupported artifact provenance schema")
    artifact = _artifact(value["artifact"])
    ownership = _ownership(value["ownership"])
    repository = _repository(value["repository"])
    origin = _origin(value["origin"])
    license_value = _license(value["license"])
    contributors = _contributors(value["contributors"])
    dependencies = _dependencies(value["dependencies"])
    use_policy = _use_policy(value["use_policy"])
    claims = value["claims"]
    expected_claims = {
        "descriptive_provenance": True,
        "ownership_verified": False,
        "rights_adjudicated": False,
        "license_compatibility_verified": False,
        "execution_authority": False,
    }
    if claims != expected_claims:
        raise ValueError("artifact provenance claims exceed descriptive authority")
    expected_id = content_identity({
        "schema": SCHEMA,
        "declared_at": _time(value["declared_at"]),
        "artifact": artifact,
        "ownership": ownership,
        "repository": repository,
        "origin": origin,
        "license": license_value,
        "contributors": contributors,
        "dependencies": dependencies,
        "use_policy": use_policy,
        "claims": expected_claims,
    })
    if value["declaration_id"] != expected_id:
        raise ValueError("artifact provenance declaration identity mismatch")
    return detached(value)


def declaration_from_spec(spec: dict) -> dict:
    keys(spec, {
        "declared_at", "artifact", "ownership", "repository", "origin",
        "license", "contributors", "dependencies", "use_policy",
    })
    normalized = {
        "schema": SCHEMA,
        "declared_at": _time(spec["declared_at"]),
        "artifact": _artifact(spec["artifact"]),
        "ownership": _ownership(spec["ownership"]),
        "repository": _repository(spec["repository"]),
        "origin": _origin(spec["origin"]),
        "license": _license(spec["license"]),
        "contributors": _contributors(spec["contributors"]),
        "dependencies": _dependencies(spec["dependencies"]),
        "use_policy": _use_policy(spec["use_policy"]),
        "claims": {
            "descriptive_provenance": True,
            "ownership_verified": False,
            "rights_adjudicated": False,
            "license_compatibility_verified": False,
            "execution_authority": False,
        },
    }
    normalized["declaration_id"] = content_identity(normalized)
    validate_declaration(normalized)
    return normalized


def inspect_declaration(value: dict) -> dict:
    value = validate_declaration(value)
    return {
        "schema": "notations.artifact-provenance-inspection.v1",
        "declaration_id": value["declaration_id"],
        "artifact": deepcopy(value["artifact"]),
        "declared_owner": value["ownership"]["declared_owner"],
        "asset_class": value["ownership"]["asset_class"],
        "license_expression": value["license"]["expression"],
        "origin_kind": value["origin"]["kind"],
        "dependencies": len(value["dependencies"]),
        "contributors": len(value["contributors"]),
        "use_policy_id": value["use_policy"]["policy_id"],
        "ownership_verified": False,
        "rights_adjudicated": False,
        "license_compatibility_verified": False,
        "execution_authority": False,
    }


def boundary_review(parent: dict, dependencies: list[dict]) -> dict:
    """Flag organization-boundary combinations for human/licensing review.

    This is a heuristic review surface, not a licence-compatibility decision.
    """
    parent = validate_declaration(parent)
    checked = [validate_declaration(item) for item in dependencies]
    by_ref = {item["artifact"]["content_ref"]: item for item in checked}
    findings = []
    for dependency in parent["dependencies"]:
        declared = by_ref.get(dependency["content_ref"])
        if declared is None:
            findings.append({
                "dependency": dependency["artifact_id"],
                "status": "UNRESOLVED_DECLARATION",
                "reason": "No matching provenance declaration supplied for dependency content_ref.",
            })
            continue
        parent_class = parent["ownership"]["asset_class"]
        child_class = declared["ownership"]["asset_class"]
        if parent_class == "OPEN_INFRASTRUCTURE" and child_class == "PROPRIETARY_IP":
            findings.append({
                "dependency": dependency["artifact_id"],
                "status": "REVIEW_REQUIRED",
                "reason": "Open-infrastructure artifact declares dependency on proprietary IP; confirm legal/architectural separation before distribution.",
            })
        elif (
            parent["ownership"]["declared_owner"]
            != declared["ownership"]["declared_owner"]
        ):
            findings.append({
                "dependency": dependency["artifact_id"],
                "status": "CROSS_OWNER",
                "reason": "Dependency crosses declared owner boundary; retain licence/use-policy review.",
            })
        else:
            findings.append({
                "dependency": dependency["artifact_id"],
                "status": "DECLARED",
                "reason": "Matching declaration supplied; no legal compatibility conclusion is made.",
            })
    return {
        "schema": "notations.artifact-boundary-review.v1",
        "parent_declaration_id": parent["declaration_id"],
        "findings": findings,
        "claims": {
            "legal_advice": False,
            "rights_adjudicated": False,
            "license_compatibility_verified": False,
            "execution_authority": False,
        },
    }
