"""Compile a human annotation into an explicit NISE query candidate.

The annotation contributes human intent and requested semantic capabilities.
An operator-authored seed plan supplies NISE focus identities and traversal policy.
No semantic retrieval, engine selection, graph traversal or execution happens here.
"""
from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from .annotations import validate_annotation
from .control_contracts import detached, keys, text
from .core.identities import content_identity

CAPABILITY = re.compile(r"[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+\.v[1-9][0-9]*$")
MAX_FOCUS = 64
MAX_CAPABILITIES = 64


def _capability(value: Any) -> str:
    if type(value) is not str or CAPABILITY.fullmatch(value) is None or len(value) > 160:
        raise ValueError("NISE capability seed must be a versioned semantic capability")
    return value


def _seed(value: dict) -> dict:
    keys(value, {
        "schema", "seed_id", "annotation_ref", "query_id", "focus_node_ids",
        "additional_capabilities", "max_hops", "node_budget",
        "include_hypotheses",
    })
    if value["schema"] != "ciw.annotation-nise-seed.v1":
        raise ValueError("Unsupported annotation→NISE seed schema")
    for name in ("seed_id", "annotation_ref", "query_id"):
        text(value[name])
    if type(value["focus_node_ids"]) is not list or not value["focus_node_ids"]:
        raise ValueError("Annotation→NISE seed requires explicit focus_node_ids")
    focus = [text(item) for item in value["focus_node_ids"]]
    if len(focus) > MAX_FOCUS or len(focus) != len(set(focus)):
        raise ValueError("focus_node_ids must be unique and bounded")
    if type(value["additional_capabilities"]) is not list:
        raise ValueError("additional_capabilities must be an array")
    capabilities = [_capability(item) for item in value["additional_capabilities"]]
    if len(capabilities) > MAX_CAPABILITIES or len(capabilities) != len(set(capabilities)):
        raise ValueError("additional_capabilities must be unique and bounded")
    if type(value["max_hops"]) is not int or not 0 <= value["max_hops"] <= 6:
        raise ValueError("max_hops must be in 0..6")
    if type(value["node_budget"]) is not int or not 1 <= value["node_budget"] <= 256:
        raise ValueError("node_budget must be in 1..256")
    if type(value["include_hypotheses"]) is not bool:
        raise ValueError("include_hypotheses must be boolean")
    return detached(value)


def compile_annotation_query(annotation: dict, seed: dict) -> dict:
    annotation = validate_annotation(annotation)
    seed = _seed(seed)
    if seed["annotation_ref"] != annotation["record_digest"]:
        raise ValueError("Seed plan targets a different annotation record")
    if annotation["status"] == "WITHDRAWN":
        raise ValueError("Withdrawn annotations cannot seed new NISE investigations in V1")

    capabilities = sorted(set(
        annotation["requested_operations"] + seed["additional_capabilities"]
    ))
    query = {
        "schema": "nise.query.v1",
        "query_id": seed["query_id"],
        "question": annotation["content"]["text"],
        "focus_node_ids": deepcopy(seed["focus_node_ids"]),
        "requested_capabilities": capabilities,
        "max_hops": seed["max_hops"],
        "node_budget": seed["node_budget"],
        "include_hypotheses": seed["include_hypotheses"],
    }
    receipt = {
        "schema": "ciw.annotation-nise-query.v1",
        "receipt_id": None,
        "seed_id": seed["seed_id"],
        "annotation_ref": annotation["record_digest"],
        "annotation_kind": annotation["kind"],
        "annotation_status": annotation["status"],
        "author": deepcopy(annotation["author"]),
        "target": deepcopy(annotation["target"]),
        "evidence_refs": deepcopy(annotation["evidence_refs"]),
        "model_refs": deepcopy(annotation["model_refs"]),
        "query": query,
        "claims": {
            "human_intent_attached": True,
            "semantic_retrieval_performed": False,
            "nise_graph_traversal_performed": False,
            "physical_truth_established": False,
            "execution_authority": False,
            "focus_inferred_from_annotation": False,
            "engine_selected": False,
        },
    }
    receipt["receipt_id"] = content_identity(
        {key: value for key, value in receipt.items() if key != "receipt_id"}
    )
    return receipt
