"""Immutable Git source -> bounded symbol selection -> inert agent context.

Only capture_git invokes Git. Retained readers never load code, run commands,
fetch dependencies or infer scientific meaning from names or docstrings.
"""
from __future__ import annotations

import ast
from copy import deepcopy
from hashlib import sha1
import os
from pathlib import Path
import re
import subprocess

from .computational_objects import (
    _canonical, _digest, _keys, _text, context_package, make_object, select, source_path,
)
from .control_contracts import bytes_ref
from .operations.runner import check_seal, seal

MAX_SOURCE_BYTES = 65536
MAX_SYMBOLS = 512
SNAPSHOT_SCHEMA = "ciw.source-snapshot.v1"
CAPTURE_SCHEMA = "ciw.source-selection.v1"
CONTEXT_SCHEMA = "ciw.source-context.v1"
_LANGUAGES = {"python", "rust", "cpp", "julia", "wgsl", "gdscript", "typescript"}
_DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _raw(value: bytes) -> bytes:
    if type(value) is not bytes or not 0 < len(value) <= MAX_SOURCE_BYTES or b"\0" in value:
        raise ValueError("Require 1..65536 bytes of non-NUL UTF-8 source")
    value.decode("utf-8")
    return value


def _lines(raw: bytes) -> list[bytes]:
    # Match Python's physical CR/LF lines, not Unicode text separators in strings.
    return [line for line in re.findall(rb"[^\r\n]*(?:\r\n|\r|\n|$)", raw) if line]


def _span(span, raw: bytes) -> list[int]:
    if (type(span) is not list or len(span) != 2 or any(type(x) is not int for x in span)
            or not 1 <= span[0] <= span[1] <= len(_lines(raw))):
        raise ValueError("Source span lies outside the retained file")
    return span


def _snapshot(raw: bytes, repository: str, revision: str, path: str, language: str) -> dict:
    raw = _raw(raw)
    _text(repository, "repository label")
    if type(revision) is not str or re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise ValueError("Source snapshots require a resolved SHA-1 Git commit")
    source_path(path)
    if type(language) is not str or language not in _LANGUAGES:
        raise ValueError("Unsupported source language")
    return seal({"schema": SNAPSHOT_SCHEMA, "repository": repository, "revision": revision,
        "path": path, "language": language, "content": raw.decode("utf-8"),
        "sha256": bytes_ref(raw), "git_blob_id": sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()})


def validate_snapshot(value: dict) -> dict:
    _keys(value, {"schema", "repository", "revision", "path", "language", "content", "sha256", "git_blob_id", "record_digest"})
    if type(value["content"]) is not str:
        raise ValueError("Source content must be UTF-8 text")
    expected = _snapshot(value["content"].encode("utf-8"), value["repository"],
                         value["revision"], value["path"], value["language"])
    if _canonical(value) != _canonical(expected):
        raise ValueError("Source snapshot content or identity mismatch")
    return deepcopy(value)


def _git(root: Path, *args: str) -> bytes:
    # No shell, hooks, filters, replacement objects, credential prompts or lazy fetch.
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_NO_REPLACE_OBJECTS="1", GIT_NO_LAZY_FETCH="1",
               GIT_TERMINAL_PROMPT="0", GIT_LITERAL_PATHSPECS="1")
    try:
        result = subprocess.run(["git", "--no-pager", "-c", "protocol.allow=never", "-C", str(root), *args],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15, env=env)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("Cannot read the requested local Git object") from exc
    return result.stdout


def capture_git(root: Path, *, repository: str, revision: str, path: str, language: str) -> dict:
    """Read committed bytes only. Uncommitted workstation edits are not captured."""
    source_path(path)
    _text(revision, "Git ref")
    commit = _git(root, "rev-parse", "--verify", "--end-of-options", revision + "^{commit}").decode().strip()
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("This source adapter requires SHA-1 Git object format")
    listing = _git(root, "ls-tree", "-z", commit, "--", path)
    entries = [item for item in listing.split(b"\0") if item]
    if len(entries) != 1:
        raise ValueError("Source must name exactly one tracked regular file")
    metadata, name = entries[0].split(b"\t", 1)
    mode, kind, blob = metadata.split()
    if name.decode("utf-8") != path or kind != b"blob" or mode not in (b"100644", b"100755"):
        raise ValueError("Symlinks, directories and submodules are not source files")
    blob_id = blob.decode("ascii")
    size = int(_git(root, "cat-file", "-s", blob_id))
    if not 0 < size <= MAX_SOURCE_BYTES:
        raise ValueError("Source exceeds the 65536-byte capture budget")
    raw = _git(root, "cat-file", "blob", blob_id)
    value = _snapshot(raw, repository, commit, path, language)
    if len(raw) != size or value["git_blob_id"] != blob_id:
        raise ValueError("Git source object changed or failed its content binding")
    return value


def _definitions(raw: bytes):
    try:
        tree = ast.parse(raw)
    except (SyntaxError, RecursionError, ValueError) as exc:
        raise ValueError("Cannot parse this source with the running Python grammar") from exc
    if sum(1 for _ in ast.walk(tree)) > 20000:
        raise ValueError("Python AST exceeds the node budget")
    definitions = []

    def visit(node, prefix=""):
        if isinstance(node, _DEFINITIONS):
            name = prefix + node.name
            start = min([node.lineno] + [item.lineno for item in node.decorator_list])
            definitions.append(({"name": name, "kind": "type" if isinstance(node, ast.ClassDef) else "function",
                                 "span": [start, node.end_lineno]}, node))
            prefix = name + "."
        for child in ast.iter_child_nodes(node):
            visit(child, prefix)

    try:
        visit(tree)
    except RecursionError as exc:
        raise ValueError("Python AST exceeds the traversal depth") from exc
    if len(definitions) > MAX_SYMBOLS:
        raise ValueError("Source exceeds the symbol budget")
    return definitions


def index_source(snapshot: dict) -> dict:
    snapshot = validate_snapshot(snapshot)
    if snapshot["language"] != "python":
        raise ValueError("Automatic symbol indexing currently supports Python only; use an explicit span")
    return seal({"schema": "ciw.source-index.v1", "source_digest": snapshot["record_digest"],
        "symbols": [item for item, _ in _definitions(snapshot["content"].encode("utf-8"))],
        "resolution": "syntax_only_not_runtime_binding"})


def _locate(snapshot: dict, locator: dict):
    _keys(locator, {"symbol", "line", "span"})
    raw = snapshot["content"].encode("utf-8")
    if locator["span"] is not None:
        if locator["symbol"] is not None or locator["line"] is not None:
            raise ValueError("Explicit span and Python symbol selection are mutually exclusive")
        return {"name": "explicit-span", "kind": "module", "span": _span(locator["span"], raw)}, None
    if snapshot["language"] != "python":
        raise ValueError("This language requires an explicit source span")
    symbol, line = locator["symbol"], locator["line"]
    if symbol is not None:
        _text(symbol, "qualified symbol")
    if line is not None and (type(line) is not int or not 1 <= line <= len(_lines(raw))):
        raise ValueError("Selection line lies outside the source")
    if symbol is None and line is None:
        raise ValueError("Choose a Python qualified symbol or line")
    choices = [(item, node) for item, node in _definitions(raw)
               if (symbol is None or item["name"] == symbol)
               and (line is None or item["span"][0] <= line <= item["span"][1])]
    if symbol is None and choices:
        width = min(item["span"][1] - item["span"][0] for item, _ in choices)
        choices = [(item, node) for item, node in choices if item["span"][1] - item["span"][0] == width]
    if len(choices) != 1:
        raise ValueError("Symbol selection is missing or ambiguous; supply a qualified name and line")
    return choices[0]


def _calls(node) -> list[dict]:
    calls = []

    def name(expr):
        if isinstance(expr, ast.Name):
            return expr.id
        if isinstance(expr, ast.Attribute):
            return name(expr.value) + "." + expr.attr
        return "<dynamic>"

    def visit(current):
        if current is not node and isinstance(current, (*_DEFINITIONS, ast.Lambda)):
            return
        if isinstance(current, ast.Call):
            target = name(current.func)
            _text(target, "call expression")
            calls.append({"expression": target, "line": current.lineno, "resolution": "unresolved"})
        for child in ast.iter_child_nodes(current):
            visit(child)

    if node is not None:
        visit(node)
    if len(calls) > 128:
        raise ValueError("Selected source exceeds the call-reference budget")
    return calls


def bind_source(snapshot: dict, locator: dict, *, declaration: dict | None = None,
                views: list[str] | None = None, editable: bool = False) -> dict:
    snapshot = validate_snapshot(snapshot)
    item, node = _locate(snapshot, locator)
    if type(editable) is not bool:
        raise ValueError("Editable must be a boolean declaration, not authority")
    declaration = {} if declaration is None else deepcopy(declaration)
    _keys(declaration, set(), {"object_id", "operation_id", "mathematics", "relations", "invariants", "evidence", "experiments"})
    source = {key: snapshot[key] for key in ("repository", "revision", "path", "language", "sha256")}
    source["span"] = item["span"]
    stable_locator = {"repository": source["repository"], "path": source["path"], "symbol": item["name"]}
    if item["name"] == "explicit-span":
        stable_locator["span"] = item["span"]
    obj = make_object(object_id=declaration.get("object_id", "source.s" + _digest(stable_locator)[7:] + ".v1"),
        kind=item["kind"], label=item["name"], operation_id=declaration.get("operation_id"), source=source,
        mathematics=declaration.get("mathematics", {"domain": "undeclared", "codomain": "undeclared",
            "expression": "undeclared", "units": {}, "assumptions": []}),
        **{key: declaration.get(key) for key in ("relations", "invariants", "evidence", "experiments")})
    selection = select(obj, views=views, edit_paths=[source["path"]] if editable else [])
    return seal({"schema": CAPTURE_SCHEMA, "snapshot": snapshot, "locator": deepcopy(locator),
        "declaration": declaration, "object": obj, "selection": selection, "syntactic_calls": _calls(node)})


def validate_capture(value: dict) -> dict:
    _keys(value, {"schema", "snapshot", "locator", "declaration", "object", "selection", "syntactic_calls", "record_digest"})
    check_seal(value)
    selection = value["selection"]
    # Validate all nested selection fields before using them as reconstruction inputs.
    context_package(value["object"], selection)
    expected = bind_source(value["snapshot"], value["locator"], declaration=value["declaration"],
        views=selection["views"], editable=bool(selection["edit_envelope"]["paths"]))
    if _canonical(value) != _canonical(expected):
        raise ValueError("Retained selection contradicts its exact source or declaration")
    return deepcopy(value)


def source_context(value: dict) -> dict:
    value = validate_capture(value)
    obj, snapshot = value["object"], value["snapshot"]
    start, end = obj["source"]["span"]
    excerpt = b"".join(_lines(snapshot["content"].encode("utf-8"))[start - 1:end])
    return seal({"schema": CONTEXT_SCHEMA, "capture_digest": value["record_digest"],
        "context": context_package(obj, value["selection"]), "source_binding": deepcopy(obj["source"]),
        "excerpt": excerpt.decode("utf-8"), "excerpt_sha256": bytes_ref(excerpt),
        "syntactic_calls": deepcopy(value["syntactic_calls"]),
        "limits": {"semantic_claims": "declared_not_verified", "relations": "declared_not_resolved",
                   "repository_authenticity": "not_established", "context_completeness": "not_established",
                   "source_text_is_untrusted_data": True}})


def check_edit(value: dict, candidate: bytes) -> dict:
    """Check bytes outside the selected original span; never apply the edit."""
    value = validate_capture(value)
    candidate = _raw(candidate)
    obj = value["object"]
    start, end = obj["source"]["span"]
    lines = _lines(value["snapshot"]["content"].encode("utf-8"))
    prefix, suffix = b"".join(lines[:start - 1]), b"".join(lines[end:])
    permitted = bool(value["selection"]["edit_envelope"]["paths"])
    passed = (permitted and len(candidate) >= len(prefix) + len(suffix)
              and candidate.startswith(prefix) and candidate.endswith(suffix))
    return seal({"schema": "ciw.source-edit-check.v1", "capture_digest": value["record_digest"],
        "candidate_sha256": bytes_ref(candidate), "status": "PASS" if passed else "FAIL",
        "claim_scope": "unchanged_bytes_outside_selected_span_only", "applied": False,
        "semantic_correctness": "not_assessed", "verification_id": None})


def compare_series(value: dict, left: list[dict], right: list[dict], *, atol: float, rtol: float = 0.0) -> dict:
    """Reuse the existing units/frame/time/shape-aware comparison without new math."""
    from .control_checks import compare
    value = validate_capture(value)
    return seal({"schema": "ciw.source-comparison.v1", "capture_digest": value["record_digest"],
        "object_digest": value["selection"]["object_digest"], "comparison": compare(left, right, atol=atol, rtol=rtol),
        "implementation_binding": "not_established_by_selection", "verification_id": None,
        "verification_status": "not_verified", "state_admission": "not_performed"})


def validate_source_context(value: dict, capture: dict) -> dict:
    if _canonical(value) != _canonical(source_context(capture)):
        raise ValueError("Source context differs from its capture")
    return deepcopy(value)


def validate_source_comparison(value: dict, capture: dict) -> dict:
    _keys(value, {"schema", "capture_digest", "object_digest", "comparison", "implementation_binding",
                  "verification_id", "verification_status", "state_admission", "record_digest"})
    from .control_checks import validate_comparison
    native = value["comparison"]
    validate_comparison(native)
    expected = compare_series(capture, native["left"], native["right"], **native["policy"])
    if _canonical(value) != _canonical(expected):
        raise ValueError("Source comparison differs from its evidence or selected object")
    return deepcopy(value)
