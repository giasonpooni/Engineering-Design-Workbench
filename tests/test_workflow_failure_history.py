"""Outer workflow failures survive inspection without inventing native results.

Proof boundaries below use deliberate failure doubles, never substitute proof
bytes or claim genuine SP1 qualification. Successful replay uses the existing
provider-free thermal reference fixture.
"""
import base64
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import re
import subprocess
from threading import Event

import pytest

from ciw import thermal_workflow
from ciw import workbench as catalog
from ciw.adapters.protocol import AdapterRefusal
from ciw.instruments import make_demo_run
from ciw.proved_heat import ProvedHeatWorkflow
from ciw.session import Session
from ciw.telemetry import digest
from test_thermal_workflow import _session_with_source


ROOT = Path(__file__).resolve().parents[1]


def _proof_source(tmp_path, monkeypatch, *, bound=True):
    session = Session(make_demo_run(), tmp_path)
    raw = (ROOT / "examples/proved-heat/source.json").read_bytes()
    source = session.workbench.add_source({
        "kind": "proved-heat", "label": "Failure history fixture, no proof",
        "bytes_b64": base64.b64encode(raw).decode(),
    })
    if bound:
        # Binding double authorizes only this test's deliberately failing call.
        monkeypatch.setattr(ProvedHeatWorkflow, "_adapters", lambda *args: None)
        session.workbench.bind_workflow("proved-heat", {
            role: tmp_path / role for role in ProvedHeatWorkflow.ROLES
        })
    return session, source


def _request(source):
    return {"operation_id": catalog.OPERATIONS[source["kind"]],
            "source_id": source["source_id"]}


def _raise(exc):
    def fail(*args, **kwargs):
        raise exc
    return fail


def _failed(session, source, request, *, action="execute", status="failed", phase="dispatch"):
    record, = session.workbench.list_failed_executions()
    assert record["schema"] == "ciw.workflow-failure.v1"
    assert re.fullmatch(r"workflow-execution:[0-9a-f]{32}", record["execution_id"])
    assert record["scope"] == "workflow_attempt"
    assert record["kind"] == source["kind"]
    assert record["action"] == action and record["phase"] == phase
    assert record["operation_id"] == catalog.OPERATIONS[source["kind"]]
    assert record["source_id"] == source["source_id"]
    assert record["evidence_id"] == source["evidence_id"]
    assert record["request"] == request and record["request_sha256"] == digest(request)
    assert record["status"] == status
    assert record["runtime"] is None and record["runtime_status"] == "not_captured"
    assert record["result_id"] is None and record["bundle_id"] is None
    started, finished = (datetime.fromisoformat(record[key]) for key in ("started_at", "finished_at"))
    assert started.utcoffset() is not None and finished.utcoffset() is not None
    assert started <= finished
    assert record["record_sha256"] == digest({key: value for key, value in record.items()
                                               if key != "record_sha256"})
    assert session.workbench.pending_operations == 0
    return record


@pytest.mark.parametrize("kind", ["proved-heat", "thermal-observer"])
def test_entered_workflow_refusal_is_retained_without_result(tmp_path, monkeypatch, kind):
    if kind == "proved-heat":
        session, source = _proof_source(tmp_path, monkeypatch)
        workflow = ProvedHeatWorkflow
    else:
        session, source = _session_with_source(tmp_path)
        workflow = thermal_workflow.ThermalWorkflow
    exc = AdapterRefusal("deliberate_refusal", "Declared failure", reason_code="fixture")
    monkeypatch.setattr(workflow, "create_session", _raise(exc))
    request = _request(source)
    with pytest.raises(AdapterRefusal) as caught:
        session.workbench.execute(request)
    assert caught.value is exc
    record = _failed(session, source, request, status="refused")
    assert record["failure"] == {"kind": "adapter_refusal", "code": "deliberate_refusal",
                                 "message": "Declared failure", "reason_code": "fixture"}
    assert not session.workbench.list_bundles()
    assert not session.workbench.native_result_summaries()
    summary, = session.workbench.failed_execution_summaries()
    assert summary["schema"] == "ciw.workflow-failure-summary.v1"
    assert summary["record_sha256"] == record["record_sha256"]
    assert summary["request_sha256"] == digest(request)
    assert "request" not in summary
    assert session.workbench.native_executions() == [summary]
    assert session.workbench.snapshot()["failed_executions"] == [summary]
    reply = session.handle({"protocol_version": 1, "request_id": "inspect-failure",
                            "type": "execution.list", "payload": {}})
    assert reply["payload"]["executions"] == [summary]


@pytest.mark.parametrize(("exc", "failure_kind"), [
    (TimeoutError("No worker response"), "timeout"),
    (subprocess.TimeoutExpired("fixture-worker", 1), "timeout"),
    (OSError("Read failed"), "io_error"),
    (RuntimeError("Worker crashed"), "unexpected_error"),
])
def test_workflow_errors_keep_original_exception_and_failed_attempt(tmp_path, monkeypatch, exc, failure_kind):
    session, source = _session_with_source(tmp_path)
    monkeypatch.setattr(thermal_workflow.ThermalWorkflow, "create_session", _raise(exc))
    request = _request(source)
    with pytest.raises(type(exc)) as caught:
        session.workbench.execute(request)
    assert caught.value is exc
    record = _failed(session, source, request)
    assert record["failure"]["kind"] == failure_kind
    assert not session.workbench.list_bundles()


def test_invalid_return_is_retention_failure_without_partial_catalog(tmp_path, monkeypatch):
    session, source = _session_with_source(tmp_path)
    monkeypatch.setattr(thermal_workflow.ThermalWorkflow, "create_session", lambda *args: {})
    request = _request(source)
    with pytest.raises(ValueError):
        session.workbench.execute(request)
    _failed(session, source, request, phase="retention")
    assert not session.workbench.list_bundles()
    assert not session.workbench.native_result_summaries()


def test_failure_workspace_reopens_without_provider_or_numerical_execution(tmp_path, monkeypatch):
    session, source = _proof_source(tmp_path / "first", monkeypatch)
    monkeypatch.setattr(ProvedHeatWorkflow, "create_session", _raise(AdapterRefusal("refused", "No proof")))
    with pytest.raises(AdapterRefusal):
        session.workbench.execute(_request(source))
    original = session.workbench.serialize()
    assert original["schema"] == "ciw.retained-workbench.v3"
    assert original["candidates"] == [] and len(original["failed_executions"]) == 1
    path = session.save_workspace(tmp_path / "workspace.json")

    def forbidden(*args, **kwargs):
        pytest.fail("Offline restore attempted provider execution or runtime binding")

    for method in ("_adapters", "create_session", "replay_session"):
        monkeypatch.setattr(ProvedHeatWorkflow, method, forbidden)
    restored = Session.from_workspace(path, tmp_path / "restored")
    assert restored.workbench.serialize() == original
    assert restored.workbench.native_executions() == session.workbench.native_executions()
    assert not next(row for row in restored.workbench.describe_operations()
                    if row["operation_id"] == "ciw.proved-heat.v1")["available"]


def test_replay_failure_keeps_original_then_allows_a_new_success(tmp_path, monkeypatch):
    session, source = _session_with_source(tmp_path)
    original = session.workbench.execute(_request(source))
    bundle = session.workbench.get_bundle(original["bundle_id"])
    replay_request = {"bundle_id": original["bundle_id"]}
    with monkeypatch.context() as patch:
        patch.setattr(thermal_workflow.ThermalWorkflow, "replay_session", _raise(TimeoutError("Replay timed out")))
        with pytest.raises(TimeoutError):
            session.workbench.replay(replay_request)
    failure = _failed(session, source, replay_request, action="replay")
    assert session.workbench.get_bundle(original["bundle_id"]) == bundle
    assert len(session.workbench.list_bundles()) == 1
    replay = session.workbench.replay(replay_request)
    fresh = session.workbench.get_bundle(replay["bundle"]["bundle_id"])
    assert fresh["bundle_digest"] != bundle["bundle_digest"]
    assert fresh["steps"][0]["execution_id"] != bundle["steps"][0]["execution_id"]
    assert fresh["steps"][0]["result_id"] != bundle["steps"][0]["result_id"]
    assert session.workbench.list_failed_executions() == [failure]
    restored = catalog.Workbench.restore(session.workbench.serialize())
    assert restored.get_bundle(original["bundle_id"]) == bundle
    assert restored.list_failed_executions() == [failure]


@pytest.mark.parametrize("preflight", ["unbound", "unknown_source", "unknown_operation", "extra_field"])
def test_predispatch_rejection_does_not_invent_an_execution(tmp_path, monkeypatch, preflight):
    session, source = _proof_source(tmp_path, monkeypatch, bound=preflight != "unbound")
    request = _request(source)
    if preflight == "unknown_source":
        request["source_id"] = "source:unknown"
    elif preflight == "unknown_operation":
        request["operation_id"] = "ciw.missing.v1"
    elif preflight == "extra_field":
        request["extra"] = "invalid"
    monkeypatch.setattr(ProvedHeatWorkflow, "create_session", lambda *args: pytest.fail("Preflight reached provider"))
    with pytest.raises((ValueError, AdapterRefusal)):
        session.workbench.execute(request)
    assert session.workbench.list_failed_executions() == []
    assert session.workbench.serialize()["schema"] == "ciw.retained-workbench.v1"
    assert "failed_executions" not in session.workbench.serialize()
    assert session.workbench.pending_operations == 0


def test_repeated_failures_use_capacity_and_release_pending_reservations(tmp_path, monkeypatch):
    session, source = _session_with_source(tmp_path)
    monkeypatch.setattr(catalog, "MAX_BUNDLES", 2)
    monkeypatch.setattr(thermal_workflow.ThermalWorkflow, "create_session", _raise(TimeoutError("No response")))
    for _ in range(2):
        with pytest.raises(TimeoutError):
            session.workbench.execute(_request(source))
        assert session.workbench.pending_operations == 0
        assert session.workbench._reserved_bytes == 0
    failures = session.workbench.list_failed_executions()
    assert len({record["execution_id"] for record in failures}) == 2
    with pytest.raises(AdapterRefusal) as caught:
        session.workbench.execute(_request(source))
    assert caught.value.code == "workbench_capacity"
    assert session.workbench.list_failed_executions() == failures
    assert session.workbench.pending_operations == 0
    assert catalog.Workbench.restore(session.workbench.serialize()).list_failed_executions() == failures


@pytest.mark.parametrize("mutation", ["evidence", "source", "operation", "request", "result", "duplicate"])
def test_resealed_failure_cannot_change_bindings_or_reuse_occurrences(tmp_path, monkeypatch, mutation):
    session, source = _session_with_source(tmp_path)
    monkeypatch.setattr(thermal_workflow.ThermalWorkflow, "create_session", _raise(TimeoutError("Timed out")))
    with pytest.raises(TimeoutError):
        session.workbench.execute(_request(source))
    saved = session.workbench.serialize()
    record = saved["failed_executions"][0]
    if mutation == "evidence":
        record["evidence_id"] = "sha256:" + "0" * 64
    elif mutation == "source":
        record["source_id"] = "source:" + "sha256:" + "0" * 64
    elif mutation == "operation":
        record["operation_id"] = "ciw.proved-heat.v1"
    elif mutation == "request":
        record["request"]["source_id"] = "source:other"
        record["request_sha256"] = digest(record["request"])
    elif mutation == "result":
        record["result_id"] = "result-" + "0" * 32
    else:
        saved["failed_executions"].append(deepcopy(record))
        saved["revision"] += 1
    record["record_sha256"] = digest({key: value for key, value in record.items() if key != "record_sha256"})
    with pytest.raises(ValueError):
        catalog.Workbench.restore(saved)


def test_blocked_failure_keeps_inspection_available_and_captures_detached_request(tmp_path, monkeypatch):
    session, source = _session_with_source(tmp_path)
    entered, release = Event(), Event()
    request = _request(source)
    original = deepcopy(request)

    def delayed_failure(*args):
        entered.set()
        if not release.wait(5):
            raise AssertionError("Test did not release provider")
        raise TimeoutError("No response")

    monkeypatch.setattr(thermal_workflow.ThermalWorkflow, "create_session", delayed_failure)
    with ThreadPoolExecutor(max_workers=2) as pool:
        attempt = pool.submit(session.workbench.execute, request)
        try:
            assert entered.wait(2)
            snapshot = pool.submit(session.workbench.snapshot).result(timeout=2)
            assert snapshot["bundles"] == []
            assert session.workbench.pending_operations == 1
            request["source_id"] = "source:caller-mutated-after-dispatch"
        finally:
            release.set()
        with pytest.raises(TimeoutError):
            attempt.result(timeout=3)
    record = _failed(session, source, original)
    for projected in (session.workbench.list_failed_executions(),
                      session.workbench.native_executions(),
                      session.workbench.snapshot()["failed_executions"],
                      session.workbench.serialize()["failed_executions"]):
        if "request" in projected[0]:
            projected[0]["request"]["source_id"] = "source:projection-mutation"
        projected[0]["failure"]["message"] = "changed"
        assert session.workbench.list_failed_executions() == [record]


def test_large_provider_reason_is_bounded_without_losing_failure_history(tmp_path, monkeypatch):
    session, source = _session_with_source(tmp_path)
    exc = RuntimeError("worker\n" + "x" * 100_000)
    monkeypatch.setattr(thermal_workflow.ThermalWorkflow, "create_session", _raise(exc))
    with pytest.raises(RuntimeError) as caught:
        session.workbench.execute(_request(source))
    assert caught.value is exc
    failure = _failed(session, source, _request(source))["failure"]
    assert 0 < len(failure["message"]) <= 1024
    assert len(failure["code"]) <= 128
    assert "\n" not in failure["message"]
    assert catalog.Workbench.restore(session.workbench.serialize()).list_failed_executions()


def test_provider_mutation_cannot_rewrite_nested_requested_configuration(tmp_path, monkeypatch):
    from ciw import telemetry

    session = Session(make_demo_run(), tmp_path)
    source = session.workbench.add_source({
        "kind": "telemetry", "label": "Synthetic nested request, no acquisition",
        "bytes_b64": base64.b64encode((ROOT / "examples/telemetry/source.json").read_bytes()).decode(),
    })
    monkeypatch.setattr(telemetry, "_adapters", lambda *args: None)
    session.workbench.bind_workflow("telemetry", {
        role: tmp_path / role for role in telemetry.ROLES - {"cbsr"}
    })
    request = {**_request(source), "configuration": json.loads(
        (ROOT / "examples/telemetry/configuration.json").read_text(encoding="utf-8"))}
    original = deepcopy(request)

    def mutate_and_fail(raw, configuration, repositories):
        configuration["gsie"]["prior"]["mean"][0] = 99
        request["configuration"]["gsie"]["prior"]["mean"][0] = 100
        raise RuntimeError("Deliberate provider mutation followed by failure")

    monkeypatch.setattr(telemetry, "create_session", mutate_and_fail)
    with pytest.raises(RuntimeError):
        session.workbench.execute(request)
    _failed(session, source, original)


def test_large_failed_requests_do_not_overflow_live_client_frames(tmp_path, monkeypatch):
    from ciw import telemetry

    session = Session(make_demo_run(), tmp_path)
    source = session.workbench.add_source({"kind": "telemetry", "label": "Large failure fixture",
        "bytes_b64": base64.b64encode((ROOT / "examples/telemetry/source.json").read_bytes()).decode()})
    monkeypatch.setattr(telemetry, "_adapters", lambda *args: None)
    session.workbench.bind_workflow("telemetry", {role: tmp_path / role for role in telemetry.ROLES - {"cbsr"}})
    monkeypatch.setattr(telemetry, "create_session", _raise(AdapterRefusal("test_rejection", "Deliberate invalid configuration")))
    request = {**_request(source), "configuration": {"padding": "x" * (7 * 1024 * 1024)}}
    assert len(telemetry.canonical(request)) < 8 * 1024 * 1024  # Server input-frame bound.
    for _ in range(5):
        with pytest.raises(AdapterRefusal, match="Deliberate"):
            session.workbench.execute(request)
    # Full retained history now exceeds the built-in clients' 32 MiB frame limit.
    # Live projections must remain small without deleting the original requests.
    saved = session.workbench.serialize()
    assert len(telemetry.canonical(saved)) > 32 * 1024 * 1024
    assert len(telemetry.canonical(session.snapshot())) < 1024 * 1024
    response = session.handle({"protocol_version": 1, "request_id": "bounded-history",
                               "type": "execution.list", "payload": {}})
    assert len(telemetry.canonical(response)) < 64 * 1024
    summaries = response["payload"]["executions"]
    assert len(summaries) == 5 and all("request" not in row for row in summaries)
    restored = catalog.Workbench.restore(saved)
    assert restored.failed_execution_summaries() == summaries
    for full in restored.list_failed_executions():
        assert full["request"] == request
        assert full["record_sha256"] in {row["record_sha256"] for row in summaries}
