"""Accepted operation failures must remain inspectable and reopenable."""
from copy import deepcopy
from unittest.mock import patch

import pytest

from ciw.adapters.protocol import AdapterRefusal
from ciw.instruments import make_demo_run
from ciw.operations.registry import Operation, OperationRegistry, default_registry
from ciw.operations.runner import check_seal, seal
from ciw.session import Session, read_json, write_json


def request(session, operation="statistics.v1"):
    return session.handle({
        "protocol_version": 1, "request_id": "failure-audit",
        "type": "operation.execute",
        "payload": {"operation_id": operation, "parameters": {}},
    })


def failing_session(tmp_path, error, phase="execute"):
    reference = default_registry()
    runtime = {"provider": "failure-regression", "version": "1"}

    def identify():
        if phase == "identity":
            raise error
        return runtime

    def calculate(run, parameters):
        raise error

    registry = OperationRegistry()
    registry.register(Operation("statistics.v1", "analysis", calculate, identify))
    registry.register(reference.get("spectrum.periodogram.v1"))
    return Session(make_demo_run(), tmp_path / "original", operations=registry)


@pytest.mark.parametrize("phase", ["identity", "execute"])
@pytest.mark.parametrize("error_type", [RuntimeError, OSError, ZeroDivisionError, AssertionError])
def test_unexpected_failures_are_retained_and_reopenable(tmp_path, phase, error_type):
    # Raw provider diagnostics can contain private paths or data. Unexpected
    # exceptions retain their type, not an arbitrary message, in the public record.
    session = failing_session(tmp_path, error_type("private-provider-detail"), phase)
    response = request(session)
    assert response["type"] == "response"
    payload = response["payload"]
    assert payload["status"] == "refused" and payload["result"] is None
    execution = payload["execution"]
    assert execution["refusal"]["code"] == "operation_failed"
    assert error_type.__name__ in execution["refusal"]["message"]
    assert "private-provider-detail" not in execution["refusal"]["message"]
    assert (execution["runtime"] is None) == (phase == "identity")
    assert session._pending_operations == 0
    assert not session.results and len(session.executions) == 1
    check_seal(execution)
    assert read_json(session.output_dir / (execution["execution_id"] + ".json")) == execution

    path = session.save_workspace(tmp_path / "workspace.json")
    with patch("ciw.session.execute_operation", side_effect=AssertionError("no replay")):
        restored = Session.from_workspace(path, tmp_path / "reopened")
    assert restored.executions == session.executions and restored.results == {}
    # A refused call must not disable the session or consume its capacity twice.
    assert request(session, "spectrum.periodogram.v1")["payload"]["status"] == "completed"
    assert len(session.executions) == 2 and len(session.results) == 1
    assert session._pending_operations == 0


@pytest.mark.parametrize("error_type", [ValueError, TypeError, OverflowError])
@pytest.mark.parametrize("message", ["", " \n\t", "declared invalid input"])
def test_validation_failures_have_nonempty_reopenable_diagnostics(tmp_path, error_type, message):
    session = failing_session(tmp_path, error_type(message))
    payload = request(session)["payload"]
    assert payload["status"] == "refused" and payload["result"] is None
    refusal = payload["execution"]["refusal"]
    assert refusal["code"] == "invalid_operation"
    assert refusal["message"].strip()
    if message.strip():
        assert refusal["message"] == message
    path = session.save_workspace(tmp_path / "workspace.json")
    assert Session.from_workspace(path, tmp_path / "reopened").executions == session.executions


@pytest.mark.parametrize("message", ["", " \n\t", "Known provider limitation"])
def test_declared_refusal_preserves_code_and_reason_with_nonempty_message(tmp_path, message):
    session = failing_session(tmp_path, AdapterRefusal(
        "provider_refused", message, reason_code="unsupported_profile"))
    payload = request(session)["payload"]
    assert payload["status"] == "refused" and payload["result"] is None
    refusal = payload["execution"]["refusal"]
    assert refusal["code"] == "provider_refused"
    assert refusal["reason_code"] == "unsupported_profile"
    assert refusal["message"].strip()
    if message.strip():
        assert refusal["message"] == message
    path = session.save_workspace(tmp_path / "workspace.json")
    assert Session.from_workspace(path, tmp_path / "reopened").executions == session.executions


@pytest.mark.parametrize("error_type", [KeyboardInterrupt, SystemExit])
def test_process_control_exceptions_still_propagate(tmp_path, error_type):
    session = failing_session(tmp_path, error_type())
    with pytest.raises(error_type):
        request(session)
    assert not session.results and not session.executions
    assert session._pending_operations == 0


def test_real_storage_error_is_not_relabelled_as_provider_failure(tmp_path):
    session = Session(make_demo_run(), tmp_path / "original")
    with patch("ciw.session.write_json", side_effect=OSError("disk unavailable")):
        response = request(session)
    assert response["type"] == "error"
    assert response["payload"]["code"] == "storage_error"
    assert not session.executions and not session.results
    assert session._pending_operations == 0
    assert request(session)["payload"]["status"] == "completed"


def test_resealed_empty_refusal_is_still_rejected_without_writing(tmp_path):
    session = failing_session(tmp_path, ValueError("valid diagnostic"))
    request(session)
    path = session.save_workspace(tmp_path / "workspace.json")
    workspace = deepcopy(read_json(path))
    execution = workspace["executions"][0]
    execution["refusal"]["message"] = ""
    seal(execution)
    write_json(path, workspace)
    with patch("ciw.session.write_json") as writer:
        with pytest.raises(ValueError, match="reason"):
            Session.from_workspace(path, tmp_path / "rejected")
        writer.assert_not_called()
