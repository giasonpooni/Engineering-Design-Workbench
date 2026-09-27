"""Legacy analysis failures stay in the record and do not publish a result."""
import asyncio
import json

import pytest
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from ciw.adapters.protocol import AdapterRefusal
from ciw.instruments import make_demo_run
from ciw.operations.registry import Operation, OperationRegistry, default_registry
from ciw.operations.runner import check_seal
from ciw.server import WorkbenchServer
from ciw.session import Session, read_json


def request(session, kind="analysis.stats", payload=None):
    return session.handle({
        "protocol_version": 1, "request_id": "legacy-failure",
        "type": kind,
        "payload": {} if payload is None else payload,
    })


def failing_session(tmp_path, error, operation="statistics.v1"):
    reference = default_registry()
    registry = OperationRegistry()

    def calculate(run, parameters):
        raise error

    registry.register(Operation(operation, "analysis", calculate,
                                lambda: {"provider": "legacy-failure", "version": "1"}))
    other = "spectrum.periodogram.v1" if operation == "statistics.v1" else "statistics.v1"
    registry.register(reference.get(other))
    return Session(make_demo_run(), tmp_path / "original", operations=registry)


def test_successful_legacy_analysis_still_publishes_only_a_result(tmp_path):
    session = Session(make_demo_run(), tmp_path)
    response = request(session)
    assert response["type"] == "response"
    result = response["payload"]
    assert result["operation_id"] == "statistics.v1"
    assert "schema" not in result and "record_digest" not in result
    assert result["verification_status"] == "not_verified"
    assert not session.executions and len(session.results) == 1
    names = sorted(path.name for path in session.output_dir.glob("*.json"))
    assert names == sorted([session.recording_file, result["result_id"] + ".json"])


@pytest.mark.parametrize("error_type", [RuntimeError, OSError, ZeroDivisionError])
def test_provider_failures_are_retained_without_a_result(tmp_path, error_type):
    session = failing_session(tmp_path, error_type("private-provider-detail"))
    response = request(session)
    assert response["type"] == "error"
    assert response["payload"]["code"] == "operation_failed"
    assert "private-provider-detail" not in response["payload"]["message"]
    assert error_type.__name__ in response["payload"]["message"]
    assert not session.results and len(session.executions) == 1
    execution = next(iter(session.executions.values()))
    assert execution["status"] == "refused" and execution["result_id"] is None
    assert execution["runtime"] is None
    assert execution["refusal"]["code"] == "operation_failed"
    assert "private-provider-detail" not in json.dumps(execution)
    check_seal(execution)
    assert read_json(session.output_dir / (execution["execution_id"] + ".json")) == execution
    assert session._pending_operations == 0
    path = session.save_workspace(tmp_path / "workspace.json")
    restored = Session.from_workspace(path, tmp_path / "reopened")
    assert restored.executions == session.executions and restored.results == {}
    assert request(session, "analysis.spectrum")["type"] == "response"


@pytest.mark.parametrize("message", ["", " \n\t", "declared invalid interval"])
def test_validation_failure_keeps_a_nonempty_diagnostic(tmp_path, message):
    session = failing_session(tmp_path, ValueError(message))
    response = request(session)
    assert response["type"] == "error"
    assert response["payload"]["code"] == "invalid_operation"
    assert response["payload"]["message"].strip()
    execution = next(iter(session.executions.values()))
    assert execution["refusal"]["message"].strip()
    if message.strip():
        assert execution["refusal"]["message"] == message
    assert not session.results
    Session.from_workspace(session.save_workspace(tmp_path / "workspace.json"), tmp_path / "reopened")


def test_declared_refusal_keeps_its_code(tmp_path):
    session = failing_session(tmp_path, AdapterRefusal(
        "provider_refused", "Known limit", reason_code="unsupported_profile"),
        operation="spectrum.periodogram.v1")
    response = request(session, "analysis.spectrum")
    assert response["payload"]["code"] == "provider_refused"
    assert response["payload"]["message"] == "Known limit"
    execution = next(iter(session.executions.values()))
    assert execution["operation_id"] == "spectrum.periodogram.v1"
    assert execution["refusal"]["reason_code"] == "unsupported_profile"
    assert not session.results


def test_invalid_channel_still_writes_nothing(tmp_path):
    session = Session(make_demo_run(), tmp_path)
    before = sorted(session.output_dir.rglob("*.json"))
    response = request(session, payload={"channel": "missing"})
    assert response["type"] == "error"
    assert response["payload"]["code"] == "invalid_payload"
    assert sorted(session.output_dir.rglob("*.json")) == before
    assert not session.executions and not session.results


@pytest.mark.parametrize("error_type", [KeyboardInterrupt, SystemExit])
def test_process_control_exceptions_do_not_write_a_refusal(tmp_path, error_type):
    session = failing_session(tmp_path, error_type(1))
    before = sorted(path.name for path in (tmp_path / "original").glob("*.json"))
    with pytest.raises(error_type):
        request(session)
    assert not session.executions and not session.results
    assert sorted(path.name for path in (tmp_path / "original").glob("*.json")) == before


def test_result_write_failure_is_still_storage_error(tmp_path, monkeypatch):
    session = Session(make_demo_run(), tmp_path)
    real = __import__("ciw.session", fromlist=["write_json"]).write_json

    def fail_result(path, data):
        if "result-" in path.name:
            raise OSError("disk unavailable")
        return real(path, data)

    monkeypatch.setattr("ciw.session.write_json", fail_result)
    response = request(session)
    assert response["type"] == "error"
    assert response["payload"]["code"] == "storage_error"
    assert not session.results and not session.executions


def test_provider_failure_does_not_close_the_websocket(tmp_path):
    session = failing_session(tmp_path, RuntimeError("controlled provider failure"))

    async def exercise():
        bridge = WorkbenchServer(session)
        async with serve(bridge.handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            async with connect(f"ws://127.0.0.1:{port}") as client:
                assert json.loads(await asyncio.wait_for(client.recv(), 3))["type"] == "session.snapshot"
                await client.send(json.dumps({
                    "protocol_version": 1, "request_id": "stats",
                    "type": "analysis.stats", "payload": {},
                }))
                failed = json.loads(await asyncio.wait_for(client.recv(), 3))
                assert failed["type"] == "error"
                assert failed["payload"]["code"] == "operation_failed"
                await client.send(json.dumps({
                    "protocol_version": 1, "request_id": "again",
                    "type": "session.get", "payload": {},
                }))
                followed = json.loads(await asyncio.wait_for(client.recv(), 3))
                assert followed["type"] == "response" and followed["request_id"] == "again"
        assert len(session.executions) == 1 and not session.results

    asyncio.run(exercise())
