"""Offline attempt integrity and bounded diagnostics, not scientific validation."""
import base64
from copy import deepcopy
import json
from subprocess import TimeoutExpired

import pytest

from ciw.adapters.protocol import AdapterRefusal
from ciw import workflow_attempts as attempts
from ciw.telemetry import canonical, digest

OPERATIONS = {"proved-heat": "ciw.proved-heat.v1", "telemetry": "ciw.telemetry.v1",
              "identified-design": "ciw.identified-design.v1"}
UPSTREAM = {"identified-design": "calibrated-observable"}


def fixture(kind="proved-heat", action="execute"):
    source = {"source_id": "source:" + digest(kind), "kind": kind, "evidence_id": digest([kind])}
    original = {"bundle_id": digest("original"), "kind": kind, "source_id": source["source_id"]}
    upstream = {"bundle_id": digest("upstream"), "kind": "calibrated-observable"}
    request = {"operation_id": OPERATIONS[kind], "source_id": source["source_id"]}
    if kind == "telemetry":
        request["configuration"] = {"window": {"duration": 2, "channels": ["a"]}}
    if kind == "identified-design":
        request["upstream_bundle_id"] = upstream["bundle_id"]
    if action == "replay":
        request = {"bundle_id": original["bundle_id"]}
    context = attempts.start(kind, action, request, source, operation_id=OPERATIONS[kind])
    return context, {source["source_id"]: source}, {item["bundle_id"]: item for item in (original, upstream)}


def validate(record, sources, bundles):
    attempts.validate(record, sources, bundles, OPERATIONS, UPSTREAM)


def reseal(record, *, request=False):
    if request:
        record["request_sha256"] = digest(record["request"])
    record["record_sha256"] = digest({k: v for k, v in record.items() if k != "record_sha256"})


@pytest.mark.parametrize(("error", "kind", "status", "code"), [
    (AdapterRefusal("PROVED_HEAT_REFUSED", "Proof refused", reason_code="guest_mismatch"), "adapter_refusal", "refused", "PROVED_HEAT_REFUSED"),
    (TimeoutExpired(["private-executable", "private-argument"], 2, output=b"private-output", stderr=b"private-stderr"), "timeout", "failed", "workflow_timeout"),
    (TimeoutError("private deadline detail"), "timeout", "failed", "workflow_timeout"),
    (OSError("private-file-name"), "io_error", "failed", "workflow_io"),
    (ValueError("Invalid result"), "invalid_workflow", "failed", "invalid_workflow"),
    (TypeError("Invalid type"), "invalid_workflow", "failed", "invalid_workflow"),
    (KeyError("missing"), "invalid_workflow", "failed", "invalid_workflow"),
    (OverflowError("overflow"), "invalid_workflow", "failed", "invalid_workflow"),
    (RuntimeError("private implementation detail"), "unexpected_error", "failed", "workflow_error"),
])
def test_classifies_failure_without_output_or_runtime_claim(error, kind, status, code):
    context, sources, bundles = fixture()
    record = attempts.finish(context, "dispatch", error)
    validate(record, sources, bundles)
    assert record["status"] == status
    assert record["failure"]["kind"] == kind
    assert record["failure"]["code"] == code
    assert record["result_id"] is record["bundle_id"] is record["runtime"] is None
    assert record["runtime_status"] == "not_captured"
    assert b"private" not in canonical(record)
    claims = attempts.claims(record)
    assert claims[record["execution_id"]][0] == "workflow_execution"
    assert claims[record["record_sha256"]][0] == "workflow_failure"


def test_detaches_both_captured_request_and_finished_record():
    context, sources, bundles = fixture("telemetry")
    source = next(iter(sources.values()))
    request = deepcopy(context["request"])
    captured = attempts.start("telemetry", "execute", request, source, operation_id=OPERATIONS["telemetry"])
    request["configuration"]["window"]["channels"].append("changed")
    record = attempts.finish(captured, "retention", ValueError("Malformed output"))
    captured["request"]["configuration"]["window"]["channels"].append("later")
    validate(record, sources, bundles)
    assert record["request"]["configuration"]["window"]["channels"] == ["a"]


@pytest.mark.parametrize("action", ["execute", "replay"])
@pytest.mark.parametrize("kind", list(OPERATIONS))
def test_profile_specific_requests_and_replay_links_validate(kind, action):
    context, sources, bundles = fixture(kind, action)
    validate(attempts.finish(context, "dispatch", ValueError("declined")), sources, bundles)


@pytest.mark.parametrize(("key", "value"), [
    ("schema", "ciw.workflow-failure.v9"), ("scope", "provider_execution"),
    ("execution_id", "execution-" + "0" * 32), ("action", "retry"),
    ("kind", "unregistered"), ("operation_id", "ciw.telemetry.v1"),
    ("source_id", "source:" + digest("other")), ("evidence_id", digest("other")),
    ("request_sha256", digest("other")), ("started_at", "2026-09-27T12:00:00"),
    ("finished_at", "not-a-date"), ("phase", "verified"), ("status", "completed"),
    ("runtime", {"executable": "do-not-run"}), ("runtime_status", "observed"),
    ("result_id", digest("fabricated")), ("bundle_id", digest("fabricated")),
    ("verification", {"outcome": "passed"}),
])
def test_resealed_structural_or_binding_tampering_is_rejected(key, value):
    context, sources, bundles = fixture()
    record = attempts.finish(context, "dispatch", ValueError("Malformed output"))
    record[key] = value
    reseal(record)
    with pytest.raises(ValueError):
        validate(record, sources, bundles)


@pytest.mark.parametrize("mutation", ["extra", "wrong_operation", "wrong_source", "configuration", "upstream"])
def test_resealed_execute_request_cannot_escape_original_profile(mutation):
    context, sources, bundles = fixture()
    record = attempts.finish(context, "dispatch", ValueError("Malformed output"))
    changes = {"extra": ("command", "execute arbitrary program"),
               "wrong_operation": ("operation_id", OPERATIONS["telemetry"]),
               "wrong_source": ("source_id", "source:" + digest("other")),
               "configuration": ("configuration", {}),
               "upstream": ("upstream_bundle_id", digest("upstream"))}
    key, value = changes[mutation]
    record["request"][key] = value
    reseal(record, request=True)
    with pytest.raises(ValueError):
        validate(record, sources, bundles)


@pytest.mark.parametrize("mutation", ["missing", "wrong_kind", "wrong_source", "extra_request"])
def test_replay_requires_existing_bundle_of_same_source_and_kind(mutation):
    context, sources, bundles = fixture(action="replay")
    record = attempts.finish(context, "dispatch", ValueError("Replay failed"))
    original = bundles[record["request"]["bundle_id"]]
    if mutation == "missing":
        bundles.clear()
    elif mutation == "wrong_kind":
        original["kind"] = "telemetry"
    elif mutation == "wrong_source":
        original["source_id"] = "source:" + digest("other")
    else:
        record["request"]["configuration"] = {}
        reseal(record, request=True)
    with pytest.raises(ValueError):
        validate(record, sources, bundles)


@pytest.mark.parametrize("mutation", ["missing", "wrong_kind", "null"])
def test_upstream_dependency_cannot_be_dropped_or_rebound(mutation):
    context, sources, bundles = fixture("identified-design")
    record = attempts.finish(context, "dispatch", ValueError("Fit failed"))
    if mutation == "missing":
        bundles.pop(record["request"]["upstream_bundle_id"])
    elif mutation == "wrong_kind":
        bundles[record["request"]["upstream_bundle_id"]]["kind"] = "proved-heat"
    else:
        record["request"]["upstream_bundle_id"] = None
        reseal(record, request=True)
    with pytest.raises(ValueError):
        validate(record, sources, bundles)


@pytest.mark.parametrize("field", ["kind", "code", "message", "reason_code", "extra"])
def test_failure_classification_and_diagnostic_bounds_are_checked(field):
    context, sources, bundles = fixture()
    record = attempts.finish(context, "dispatch", ValueError("Invalid output"))
    record["failure"][field] = {"kind": "adapter_refusal", "code": "invented", "message": "x" * 1025,
                                "reason_code": "not_allowed_for_invalid_workflow", "extra": True}[field]
    reseal(record)
    with pytest.raises(ValueError):
        validate(record, sources, bundles)


def test_long_unicode_diagnostics_fit_reserved_overhead_and_are_utf8():
    context, sources, bundles = fixture()
    error = AdapterRefusal("x" * 500, "\ud800\x00\n" + "🌡" * 2000, reason_code="r" * 500)
    record = attempts.finish(context, "dispatch", error)
    validate(record, sources, bundles)
    failure = record["failure"]
    assert len(failure["code"]) == len(failure["reason_code"]) == 128
    assert len(failure["message"]) <= 1024
    assert "\ud800" not in failure["message"] and "\x00" not in failure["message"]
    assert len(canonical(record)) - len(canonical(record["request"])) <= attempts.MAX_OVERHEAD


def test_blank_and_unprintable_exception_messages_have_bounded_fallback():
    class BrokenMessage(ValueError):
        def __str__(self):
            raise RuntimeError("cannot format")

    context, sources, bundles = fixture()
    for error in (ValueError(" \n\x00"), BrokenMessage()):
        record = attempts.finish(context, "dispatch", error)
        validate(record, sources, bundles)
        assert record["failure"]["message"].strip()


@pytest.mark.parametrize("configuration", [None, [], "operator code"])
def test_telemetry_request_configuration_must_remain_data_object(configuration):
    context, sources, bundles = fixture("telemetry")
    record = attempts.finish(context, "dispatch", ValueError("Invalid output"))
    record["request"]["configuration"] = configuration
    reseal(record, request=True)
    with pytest.raises(ValueError):
        validate(record, sources, bundles)


def test_nonfinite_request_and_process_exit_are_not_accepted_as_records():
    context, sources, bundles = fixture("telemetry")
    context["request"]["configuration"]["value"] = float("nan")
    with pytest.raises(ValueError):
        attempts.finish(context, "dispatch", ValueError("Invalid output"))
    context, _, _ = fixture()
    with pytest.raises(ValueError):
        attempts.finish(context, "dispatch", KeyboardInterrupt())


def test_content_seal_is_not_authenticated_wall_clock_or_phase_evidence():
    context, sources, bundles = fixture()
    record = attempts.finish(context, "dispatch", ValueError("Invalid output"))
    record["started_at"] = "2026-01-01T00:00:00+00:00"
    record["finished_at"] = "2026-01-01T00:00:01+00:00"
    record["phase"] = "retention"
    reseal(record)
    validate(record, sources, bundles)


@pytest.mark.parametrize("remove", ["first", "second", "all"])
def test_offline_residual_attempt_cannot_lose_source_declared_windows(monkeypatch, remove):
    from ciw import residual_monitor as monitor
    from ciw.workbench import _source

    ids = [digest("earlier-window"), digest("later-window")]
    raw = canonical({"schema": monitor.SOURCE_SCHEMA, "experiment_id": "failure-history-dependencies",
                     "window_bundle_ids": ids, "configuration": deepcopy(monitor.DEFAULT_CONFIGURATION)})
    source = _source({"kind": "residual-monitor", "label": "Declared monitor dependency fixture",
                      "bytes_b64": base64.b64encode(raw).decode()})
    request = {"operation_id": monitor.OPERATION, "source_id": source["source_id"]}
    context = attempts.start("residual-monitor", "execute", request, source, operation_id=monitor.OPERATION)
    record = attempts.finish(context, "dispatch", AdapterRefusal("RESIDUAL_MONITOR_REFUSED", "Deliberate provider refusal"))
    # The caller validates bundle contents independently; this unit test checks
    # exactly the source-selected availability rule of dispatch and restoration.
    bundles = {identity: {"bundle_id": identity, "kind": "calibrated-window"} for identity in ids}
    saved = json.loads(canonical({"attempt": record, "sources": {source["source_id"]: source}, "bundles": bundles}))

    def never(*args, **kwargs):
        pytest.fail("Offline dependency validation invoked a scientific provider")

    for method in ("_adapters", "create_session", "replay_session", "_step"):
        monkeypatch.setattr(monitor.workflow, method, never)
    assert monitor.workflow.requested_upstream_ids(raw) == ids
    operations = {"residual-monitor": monitor.OPERATION}
    attempts.validate(saved["attempt"], saved["sources"], saved["bundles"], operations, {})
    if remove == "all":
        saved["bundles"].clear()
    else:
        del saved["bundles"][ids[0 if remove == "first" else 1]]
    with pytest.raises(ValueError, match="source-selected windows"):
        attempts.validate(saved["attempt"], saved["sources"], saved["bundles"], operations, {})
