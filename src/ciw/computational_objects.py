"""Descriptive computational objects. Selection is never execution or edit authority."""
from __future__ import annotations

from copy import deepcopy
import math
from pathlib import PurePosixPath
import re
from typing import Any

from .control_contracts import json_tree
from .core.identities import canonical_json, content_identity
from .operations.registry import valid_operation_id

SCHEMA = "ciw.computational-object.v1"
SELECTION_SCHEMA = "ciw.computational-selection.v1"
CONTEXT_SCHEMA = "ciw.context-package.v1"
PERTURBATION_SCHEMA = "ciw.perturbation-request.v1"
COMPARISON_SCHEMA = "ciw.computational-comparison.v1"
_KINDS = frozenset({"function", "module", "type", "trait", "ecs-system", "shader",
    "numerical-kernel", "solver", "state-transition", "coordinate-transform",
    "graph-substructure", "dataflow", "experiment", "proof-obligation"})
_VIEWS = frozenset({"source", "state", "algebra", "graph", "geometry", "topology",
    "composition", "evidence", "experiments"})
_PERTURB = frozenset({"input", "parameter", "implementation", "precision", "solver", "backend", "representation"})
_COMPARE = frozenset({"output", "residual", "covariance", "invariant", "topology", "performance", "provenance"})
_AUTHORITY = {"may_execute": False, "may_edit": False, "may_verify": False, "may_admit_state": False}


def _canonical(value: Any) -> bytes:
    json_tree(value)
    raw = canonical_json(value).encode("utf-8")
    if len(raw) > 1024 * 1024:
        raise ValueError("Computational record exceeds byte budget")
    return raw


def _digest(value: Any) -> str:
    _canonical(value)
    return content_identity(value)


def _keys(value: Any, required: set[str], optional=frozenset()) -> None:
    if type(value) is not dict or not required <= value.keys() <= required | optional:
        raise ValueError("Unexpected or missing computational-object fields")


def _text(value: Any, name: str, limit: int = 512) -> str:
    if type(value) is not str or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} must be a nonempty bounded string")
    return value


def source_path(value: Any) -> str:
    """One canonical repository-relative path, never a filesystem capability."""
    _text(value, "source path")
    if (PurePosixPath(value).is_absolute() or "\\" in value or ":" in value
            or any(ord(c) < 32 or ord(c) == 127 for c in value)
            or any(p in {"", ".", "..", ".git"} for p in value.split("/"))):
        raise ValueError("Require a canonical repository-relative source path")
    return value


def _string_list(value: Any, name: str, *, allowed=None, maximum: int = 64) -> list[str]:
    if type(value) is not list or len(value) > maximum:
        raise ValueError(f"{name} must be a bounded string list")
    for item in value:
        _text(item, name)
    if len(set(value)) != len(value) or (allowed is not None and any(x not in allowed for x in value)):
        raise ValueError(f"{name} contains duplicate or unsupported values")
    return value


def validate_object(value: Any) -> dict:
    _canonical(value)
    _keys(value, {"schema", "object_id", "kind", "label", "operation_id", "source",
                  "mathematics", "relations", "invariants", "evidence", "experiments", "authority"})
    if value["schema"] != SCHEMA or not valid_operation_id(value["object_id"]):
        raise ValueError("Unsupported computational object identity")
    if type(value["kind"]) is not str or value["kind"] not in _KINDS:
        raise ValueError("Unsupported computational object kind")
    _text(value["label"], "label")
    if value["operation_id"] is not None and not valid_operation_id(value["operation_id"]):
        raise ValueError("operation_id must be null or a versioned operation identity")
    source = value["source"]
    _keys(source, {"repository", "revision", "path", "span", "language", "sha256"})
    for key in ("repository", "revision", "language"):
        _text(source[key], "source." + key)
    source_path(source["path"])
    if type(source["sha256"]) is not str or re.fullmatch(r"sha256:[0-9a-f]{64}", source["sha256"]) is None:
        raise ValueError("source.sha256 must bind exact full-file bytes")
    span = source["span"]
    if (type(span) is not list or len(span) != 2 or any(type(x) is not int for x in span)
            or not 1 <= span[0] <= span[1] <= 1000000):
        raise ValueError("source.span must be bounded inclusive positive line bounds")
    mathematics = value["mathematics"]
    _keys(mathematics, {"domain", "codomain", "expression", "units", "assumptions"})
    for key in ("domain", "codomain", "expression"):
        _text(mathematics[key], "mathematics." + key, 4096)
    if type(mathematics["units"]) is not dict or len(mathematics["units"]) > 64:
        raise ValueError("mathematics.units must be a bounded object")
    for name, unit in mathematics["units"].items():
        _text(name, "quantity")
        _text(unit, "unit")
    _string_list(mathematics["assumptions"], "assumptions")
    _keys(value["relations"], {"dependencies", "consumers", "equivalent_implementations", "compositions"})
    for key, items in value["relations"].items():
        _string_list(items, "relations." + key)
    for key in ("invariants", "evidence", "experiments"):
        _string_list(value[key], key)
    if _canonical(value["authority"]) != _canonical({"describes": True, **_AUTHORITY}):
        raise ValueError("Computational-object records are descriptive only")
    return deepcopy(value)


def make_object(*, object_id: str, kind: str, label: str, operation_id: str | None,
                source: dict, mathematics: dict, relations: dict | None = None,
                invariants: list[str] | None = None, evidence: list[str] | None = None,
                experiments: list[str] | None = None) -> dict:
    return validate_object({"schema": SCHEMA, "object_id": object_id, "kind": kind,
        "label": label, "operation_id": operation_id, "source": source, "mathematics": mathematics,
        "relations": {"dependencies": [], "consumers": [], "equivalent_implementations": [],
                      "compositions": []} if relations is None else relations,
        "invariants": [] if invariants is None else invariants,
        "evidence": [] if evidence is None else evidence, "experiments": [] if experiments is None else experiments,
        "authority": {"describes": True, **_AUTHORITY}})


def select(obj: dict, *, views: list[str] | None = None, edit_paths: list[str] | None = None) -> dict:
    obj = validate_object(obj)
    views = _string_list(["source", "algebra", "evidence"] if views is None else views,
                         "views", allowed=_VIEWS, maximum=len(_VIEWS))
    paths = _string_list([] if edit_paths is None else edit_paths, "edit_paths")
    if not views or any(path != obj["source"]["path"] for path in paths):
        raise ValueError("Require a view and an edit envelope limited to the selected source path")
    body = {"schema": SELECTION_SCHEMA, "object_id": obj["object_id"], "object_digest": _digest(obj),
        "views": deepcopy(views), "edit_envelope": {"paths": deepcopy(paths),
        "requires_human_or_executor_authorization": True}, "authority": dict(_AUTHORITY)}
    return {**body, "selection_id": "selection:" + _digest(body)}


def validate_selection(obj: dict, value: dict) -> dict:
    _keys(value, {"schema", "selection_id", "object_id", "object_digest", "views", "edit_envelope", "authority"})
    _keys(value["edit_envelope"], {"paths", "requires_human_or_executor_authorization"})
    expected = select(obj, views=value["views"], edit_paths=value["edit_envelope"]["paths"])
    if _canonical(value) != _canonical(expected):
        raise ValueError("Selection is stale, tampered, or claims authority")
    return deepcopy(value)


def context_package(obj: dict, selection: dict) -> dict:
    obj = validate_object(obj)
    selection = validate_selection(obj, selection)
    body = {"schema": CONTEXT_SCHEMA, "selection": selection, "object": obj,
        "direct_context": {"dependencies": obj["relations"]["dependencies"],
            "consumers": obj["relations"]["consumers"], "evidence": obj["evidence"],
            "experiments": obj["experiments"], "invariants": obj["invariants"]},
        "instructions": {"preserve_invariants": True, "stay_within_edit_envelope": True,
            "execution_requires_separate_authority": True, "verification_requires_separate_identity": True}}
    return {**body, "context_digest": _digest(body)}


def validate_context(value: dict) -> dict:
    _keys(value, {"schema", "selection", "object", "direct_context", "instructions", "context_digest"})
    expected = context_package(value["object"], value["selection"])
    if _canonical(value) != _canonical(expected):
        raise ValueError("Context differs from its selected object")
    return deepcopy(value)


def perturbation_request(obj: dict, *, dimension: str, change: dict) -> dict:
    obj = validate_object(obj)
    if type(dimension) is not str or dimension not in _PERTURB or type(change) is not dict or not change:
        raise ValueError("Perturbation needs a supported dimension and nonempty declared change")
    _canonical(change)
    body = {"schema": PERTURBATION_SCHEMA, "object_id": obj["object_id"], "object_digest": _digest(obj),
        "dimension": dimension, "change": deepcopy(change), "execute": False,
        "required_observations": ["result", "invariants", "residuals", "provenance"]}
    return {**body, "request_id": "perturbation:" + _digest(body)}


def validate_perturbation(obj: dict, value: dict) -> dict:
    _keys(value, {"schema", "object_id", "object_digest", "dimension", "change", "execute", "required_observations", "request_id"})
    expected = perturbation_request(obj, dimension=value["dimension"], change=value["change"])
    if _canonical(value) != _canonical(expected):
        raise ValueError("Perturbation differs from its declaration")
    return deepcopy(value)


def compare_observations(obj: dict, left: dict, right: dict, *, metrics: list[str]) -> dict:
    """Legacy structural diagnostic only. Use control_checks.compare for typed evidence.

    Unlike the initial implementation, fields, shapes and nonnumeric labels must
    match. The aggregate has no physical-unit or invariant-verification meaning.
    """
    obj = validate_object(obj)
    metrics = _string_list(metrics, "metrics", allowed=_COMPARE, maximum=len(_COMPARE))
    if not metrics or type(left) is not dict or type(right) is not dict:
        raise ValueError("Require observation objects and declared metrics")
    _canonical(left)
    _canonical(right)
    errors = []

    def walk(a, b):
        if type(a) in (int, float) and type(b) in (int, float):
            errors.append(abs(a - b))
        elif type(a) is dict and type(b) is dict and a.keys() == b.keys():
            for key in sorted(a):
                walk(a[key], b[key])
        elif type(a) is list and type(b) is list and len(a) == len(b):
            for u, v in zip(a, b):
                walk(u, v)
        elif type(a) is not type(b) or type(a) in (dict, list) or a != b:
            raise ValueError("Comparison requires matching fields, shapes and nonnumeric labels")

    walk(left, right)
    numerical = {"count": len(errors), "max_abs": max(errors), "l2": math.hypot(*errors)} if errors else None
    result = {"schema": COMPARISON_SCHEMA, "object_id": obj["object_id"], "object_digest": _digest(obj),
        "metrics": deepcopy(metrics), "left_digest": _digest(left), "right_digest": _digest(right),
        "numerical_summary": numerical, "invariants_assessed": False, "verification_status": "not_verified"}
    return {**result, "comparison_digest": _digest(result)}
