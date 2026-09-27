"""Bounded failure history for outer workbench invocations.

These records establish a retained attempt, not that a scientific provider ran.
Successful native records keep their existing identities and validators. Saved
failures contain no executable bindings and grant no result or verification.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from datetime import datetime, timezone
import re
from subprocess import TimeoutExpired
from uuid import uuid4

from .adapters.protocol import AdapterRefusal

SCHEMA = "ciw.workflow-failure.v1"
MAX_OVERHEAD = 8192
_DIGEST = r"sha256:[a-f0-9]{64}"
_CONTEXT_KEYS = {"schema", "execution_id", "scope", "kind", "action", "operation_id",
                 "source_id", "evidence_id", "request", "request_sha256", "started_at"}
_RECORD_KEYS = _CONTEXT_KEYS | {"finished_at", "phase", "status", "runtime", "runtime_status",
                               "result_id", "bundle_id", "failure", "record_sha256"}
_FAILURES = {"timeout": "workflow_timeout", "io_error": "workflow_io",
             "invalid_workflow": "invalid_workflow", "unexpected_error": "workflow_error"}


def _canonical(value):
    # Avoid importing telemetry's Session dependency during module setup.
    from .telemetry import canonical
    return canonical(value)


def _digest(value):
    from .telemetry import digest
    return digest(value)


def _keys(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys() <= set(required) | set(optional):
        raise ValueError("Unexpected or missing workflow attempt fields")


def _bounded(value, limit, fallback):
    """Keep diagnostics finite, UTF-8 encodable and single-line."""
    try:
        text = str(value)[:limit * 4]
    except Exception:
        text = fallback
    text = text.encode("utf-8", errors="replace").decode("utf-8")
    text = " ".join("".join(c if c.isprintable() else " " for c in text).split())
    return text[:limit].strip() or fallback


def _text(value, limit):
    if (not isinstance(value, str) or not value or len(value) > limit
            or value != _bounded(value, limit, "")):
        raise ValueError("Invalid bounded workflow diagnostic")


def _identity(value, pattern):
    if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
        raise ValueError("Invalid workflow attempt identity")


def _timestamp(value):
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError("Invalid workflow attempt timestamp")
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
    except (ValueError, OverflowError) as exc:
        raise ValueError("Workflow attempt timestamps require an explicit UTC offset") from exc


def start(kind, action, request, source, *, operation_id):
    """Detach a validated request immediately before workflow dispatch."""
    if action not in {"execute", "replay"}:
        raise ValueError("Unsupported workflow attempt action")
    captured = deepcopy(request)
    context = {"schema": SCHEMA, "execution_id": "workflow-execution:" + uuid4().hex,
        "scope": "workflow_attempt", "kind": kind, "action": action,
        "operation_id": operation_id, "source_id": source["source_id"],
        "evidence_id": source["evidence_id"], "request": captured,
        "request_sha256": _digest(captured), "started_at": datetime.now(timezone.utc).isoformat()}
    _canonical(context)
    return context


def finish(context, phase, exc):
    """Seal a terminal failure; callers retain it before re-raising the error."""
    _keys(context, _CONTEXT_KEYS)
    if phase not in {"dispatch", "retention"} or not isinstance(exc, Exception):
        raise ValueError("Require a supported failure phase and ordinary exception")
    if isinstance(exc, AdapterRefusal):
        failure = {"kind": "adapter_refusal", "code": _bounded(exc.code, 128, "adapter_refusal"),
                   "message": _bounded(exc, 1024, "The workflow refused the request")}
        if exc.reason_code is not None:
            failure["reason_code"] = _bounded(exc.reason_code, 128, "unspecified")
        status = "refused"
    else:
        status = "failed"
        if isinstance(exc, (TimeoutExpired, TimeoutError)):
            kind, message = "timeout", "The workflow exceeded its execution deadline"
        elif isinstance(exc, OSError):
            kind, message = "io_error", "Workflow I/O failed; no result was retained"
        elif isinstance(exc, (ValueError, TypeError, KeyError, OverflowError)):
            kind, message = "invalid_workflow", _bounded(exc, 1024, "Invalid workflow data")
        else:
            kind, message = "unexpected_error", "The workflow failed with an unexpected error"
        failure = {"kind": kind, "code": _FAILURES[kind], "message": message}
    record = {**deepcopy(context), "finished_at": datetime.now(timezone.utc).isoformat(),
        "phase": phase, "status": status, "runtime": None, "runtime_status": "not_captured",
        "result_id": None, "bundle_id": None, "failure": failure}
    record["record_sha256"] = _digest(record)
    if len(_canonical(record)) - len(_canonical(record["request"])) > MAX_OVERHEAD:
        raise ValueError("Workflow failure exceeds its reserved metadata budget")
    return record


def validate(record, sources, bundles, operations, upstream_kinds):
    """Check retained content and links offline, without any runtime invocation."""
    try:
        _keys(record, _RECORD_KEYS)
        encoded = _canonical(record)
        if record["record_sha256"] != _digest({k: v for k, v in record.items() if k != "record_sha256"}):
            raise ValueError("Workflow failure content mismatch")
        _identity(record["record_sha256"], _DIGEST)
        _identity(record["execution_id"], r"workflow-execution:[a-f0-9]{32}")
        _identity(record["source_id"], r"source:sha256:[a-f0-9]{64}")
        _identity(record["evidence_id"], _DIGEST)
        _identity(record["request_sha256"], _DIGEST)
        if (record["schema"] != SCHEMA or record["scope"] != "workflow_attempt"
                or record["kind"] not in operations or record["action"] not in {"execute", "replay"}
                or record["operation_id"] != operations[record["kind"]]
                or record["phase"] not in {"dispatch", "retention"}
                or record["runtime"] is not None or record["runtime_status"] != "not_captured"
                or record["result_id"] is not None or record["bundle_id"] is not None):
            raise ValueError("Invalid workflow failure scope or output claims")
        for key in ("started_at", "finished_at"):
            _timestamp(record[key])
        source = sources.get(record["source_id"])
        if (not isinstance(source, dict) or source.get("source_id") != record["source_id"]
                or source.get("kind") != record["kind"] or source.get("evidence_id") != record["evidence_id"]):
            raise ValueError("Workflow attempt source binding mismatch")
        request = record["request"]
        if record["request_sha256"] != _digest(request):
            raise ValueError("Workflow attempt request digest mismatch")
        if record["action"] == "replay":
            _keys(request, {"bundle_id"})
            _identity(request["bundle_id"], _DIGEST)
            original = bundles.get(request["bundle_id"])
            if (not isinstance(original, dict) or original.get("bundle_id") != request["bundle_id"]
                    or original.get("kind") != record["kind"] or original.get("source_id") != record["source_id"]):
                raise ValueError("Failed replay must bind its retained original bundle")
        else:
            if record["kind"] == "telemetry":
                _keys(request, {"operation_id", "source_id", "configuration"})
                if not isinstance(request["configuration"], dict):
                    raise ValueError("Telemetry attempt requires a configuration object")
            else:
                _keys(request, {"operation_id", "source_id"}, {"upstream_bundle_id"})
            if request["operation_id"] != record["operation_id"] or request["source_id"] != record["source_id"]:
                raise ValueError("Workflow request identity binding mismatch")
            upstream_id = request.get("upstream_bundle_id")
            if record["kind"] in upstream_kinds:
                _identity(upstream_id, _DIGEST)
                upstream = bundles.get(upstream_id)
                if (not isinstance(upstream, dict) or upstream.get("bundle_id") != upstream_id
                        or upstream.get("kind") != upstream_kinds[record["kind"]]):
                    raise ValueError("Workflow attempt has no matching retained upstream")
            elif upstream_id is not None:
                raise ValueError("This workflow cannot claim an upstream bundle")
            if record["kind"] == "residual-monitor":
                # Match Workbench.execute's source-declared dependency check.
                # This parser validates data only; no FDIR/OIT provider runs.
                from .residual_monitor import workflow
                raw = base64.b64decode(source["bytes_b64"], validate=True)
                requested = workflow.requested_upstream_ids(raw)
                if any(identity not in bundles for identity in requested):
                    raise ValueError("Failed residual monitor requires all retained source-selected windows")
            if record["kind"] == "native-interop":
                # The optional force source names exact retained trajectory
                # bytes/results. Reuse dispatch's data-only binding check.
                from .native_interop import NativeInteropWorkflow, validate_dependency
                raw = base64.b64decode(source["bytes_b64"], validate=True)
                validate_dependency(NativeInteropWorkflow._source(raw), bundles)
        if len(encoded) - len(_canonical(request)) > MAX_OVERHEAD:
            raise ValueError("Workflow failure exceeds its metadata budget")
        failure = record["failure"]
        _keys(failure, {"kind", "code", "message"}, {"reason_code"})
        _text(failure["code"], 128)
        _text(failure["message"], 1024)
        if failure["kind"] == "adapter_refusal":
            if record["status"] != "refused":
                raise ValueError("Adapter refusal must remain refused")
            if "reason_code" in failure:
                _text(failure["reason_code"], 128)
        elif (record["status"] != "failed" or failure["kind"] not in _FAILURES
              or failure["code"] != _FAILURES[failure["kind"]] or "reason_code" in failure):
            raise ValueError("Workflow failure classification mismatch")
    except (KeyError, TypeError, AttributeError, OverflowError, RecursionError) as exc:
        raise ValueError("Malformed workflow failure record") from exc


def claims(record):
    """Identity claims for a record whose content and links already validated."""
    return {record["execution_id"]: ("workflow_execution", _digest(record)),
            record["record_sha256"]: ("workflow_failure", _digest(record))}
