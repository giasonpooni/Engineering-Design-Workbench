"""Legacy analysis must retain the same evidence that its reader validates."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch

import pytest

from ciw.adapters.protocol import AdapterRefusal
from ciw.instruments import make_demo_run
from ciw.operations.registry import Operation, OperationRegistry, default_registry
from ciw.session import Session, read_json, write_json

CASES = [("analysis.stats", "statistics.v1"),
         ("analysis.spectrum", "spectrum.periodogram.v1")]


def request(session, kind, payload=None):
    return session.handle({"protocol_version": 1, "request_id": "legacy-boundary",
                           "type": kind, "payload": {} if payload is None else payload})


def session_with(tmp_path, operation_id, execute, role="analysis"):
    registry = OperationRegistry()
    registry.register(Operation(operation_id, role, execute, lambda: {"version": "test"}))
    return Session(make_demo_run(), tmp_path, operations=registry)


def reference(operation_id, run=None, parameters=None):
    run = make_demo_run() if run is None else run
    parameters = {"channel": "q", "interval_s": [0.0, 12.0]} if parameters is None else parameters
    return default_registry().get(operation_id).execute(run, parameters)


@pytest.mark.parametrize("kind,operation_id", CASES)
def test_provider_input_cannot_mutate_session_evidence(tmp_path, kind, operation_id):
    retained_input = []

    def calculate(run, parameters):
        data = reference(operation_id, run, parameters)
        retained_input.append(run)
        run["metadata"]["provenance"]["provider_note"] = "must remain detached"
        run["channels"]["q"]["values"][0] = -999.0
        return data

    session = session_with(tmp_path, operation_id, calculate)
    original = deepcopy(session.run)
    response = request(session, kind)
    assert response["type"] == "response"
    assert session.run == original
    assert read_json(tmp_path / session.recording_file) == original
    retained_input[0]["metadata"]["coordinate_frame"] = "changed after return"
    assert session.run == original
    saved = session.save_workspace(tmp_path / "workspace.json")
    assert Session.from_workspace(saved, tmp_path / "restored").run == original


@pytest.mark.parametrize("kind,operation_id", CASES)
def test_cached_provider_output_cannot_mutate_retained_result(tmp_path, kind, operation_id):
    cached = reference(operation_id)
    session = session_with(tmp_path, operation_id, lambda run, parameters: cached)
    response = request(session, kind)
    assert response["type"] == "response"
    result = response["payload"]
    expected = deepcopy(result)
    if operation_id == "statistics.v1":
        cached["rms"] = -1.0
    else:
        cached["psd"][0] = -1.0
    assert session.results[result["result_id"]] == expected
    assert read_json(tmp_path / (result["result_id"] + ".json")) == expected
    result["data"]["unit"] = "caller mutation"
    assert session.results[expected["result_id"]] == expected
    saved = session.save_workspace(tmp_path / "workspace.json")
    assert Session.from_workspace(saved, tmp_path / "restored").results == session.results


@pytest.mark.parametrize("kind,operation_id", CASES)
def test_provider_parameter_mutation_cannot_retarget_result(tmp_path, kind, operation_id):
    held_parameters = []

    def calculate(run, parameters):
        data = reference(operation_id, run, parameters)
        held_parameters.append(parameters)
        parameters["interval_s"][0] = 0.5
        parameters["channel"] = "v"
        return data

    session = session_with(tmp_path, operation_id, calculate)
    response = request(session, kind, {"interval_s": [1.0, 2.0], "channel": "q"})
    assert response["type"] == "response"
    result = response["payload"]
    assert result["interval_s"] == [1.0, 2.0] and result["channel"] == "q"
    held_parameters[0]["interval_s"][1] = 5.0
    assert session.results[result["result_id"]]["interval_s"] == [1.0, 2.0]
    saved = session.save_workspace(tmp_path / "workspace.json")
    assert Session.from_workspace(saved, tmp_path / "restored").results == session.results


@pytest.mark.parametrize("kind,operation_id", CASES)
@pytest.mark.parametrize("corruption", ["count", "unit", "negative", "missing", "extra", "not_object"])
def test_invalid_provider_output_is_rejected_before_write(tmp_path, kind, operation_id, corruption):
    data = reference(operation_id)
    if corruption == "count":
        data["sample_count"] -= 1
    elif corruption == "unit":
        data["unit"] = "wrong-unit"
    elif corruption == "negative":
        if operation_id == "statistics.v1":
            data["rms"] = -1.0
        else:
            data["psd"][0] = -1.0
    elif corruption == "missing":
        del data["sample_count"]
    elif corruption == "extra":
        data["unbound"] = "not in the result contract"
    else:
        data = [data]
    session = session_with(tmp_path, operation_id, lambda run, parameters: data)
    with patch("ciw.session.write_json") as writer:
        response = request(session, kind)
        assert response["type"] == "error"
        assert response["payload"]["code"] == "invalid_payload"
        writer.assert_not_called()
    assert not session.results and not session.executions
    saved = session.save_workspace(tmp_path / "workspace.json")
    assert not Session.from_workspace(saved, tmp_path / "restored").results


@pytest.mark.parametrize("kind,operation_id", CASES)
def test_wrong_role_is_rejected_before_provider_invocation(tmp_path, kind, operation_id):
    called = []

    def calculate(run, parameters):
        called.append(True)
        return reference(operation_id, run, parameters)

    session = session_with(tmp_path, operation_id, calculate, role="verification")
    response = request(session, kind)
    assert response["type"] == "error" and response["payload"]["code"] == "invalid_payload"
    assert not called and not session.results


@pytest.mark.parametrize("kind,operation_id", CASES)
def test_valid_legacy_shape_and_provider_free_reopen_remain_compatible(tmp_path, kind, operation_id):
    session = Session(make_demo_run(), tmp_path)
    payload = {"channel": "v", "interval_s": [1.0, 2.0]}
    response = request(session, kind, payload)
    result = response["payload"]
    assert response["type"] == "response"
    assert result["data"] == reference(operation_id, parameters=payload)
    assert set(result) == {"result_id", "evidence_id", "operation_id", "execution_id",
                           "verification_id", "verification_status", "run_id", "selection_revision",
                           "channel", "interval_s", "created_at", "recording_file", "data"}
    assert not session.executions
    saved = session.save_workspace(tmp_path / "workspace.json")
    assert read_json(saved)["workspace_version"] == 1
    with patch("ciw.operations.registry.OperationRegistry.get", side_effect=AssertionError("no execution")):
        restored = Session.from_workspace(saved, tmp_path / "restored")
    assert restored.results == session.results
    assert restored.selection == session.selection


@pytest.mark.parametrize("kind,operation_id", CASES)
def test_concurrent_selection_and_caller_edits_do_not_retarget_analysis(tmp_path, kind, operation_id):
    entered, release = Event(), Event()

    def calculate(run, parameters):
        entered.set()
        assert release.wait(timeout=10)
        return reference(operation_id, run, parameters)

    session = session_with(tmp_path, operation_id, calculate)
    payload = {"channel": "q", "interval_s": [1.0, 2.0]}
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(request, session, kind, payload)
        try:
            assert entered.wait(timeout=5)
            payload["interval_s"][0] = 0.5
            update = pool.submit(request, session, "selection.update", {
                "expected_revision": 0, "channel": "v", "interval_s": [3.0, 4.0]}).result(timeout=3)
            assert update["type"] == "response"
            assert not pending.done()
        finally:
            release.set()
        result = pending.result(timeout=5)["payload"]
    assert result["selection_revision"] == 0 and result["channel"] == "q"
    assert result["interval_s"] == [1.0, 2.0]
    assert session.selection["revision"] == 1


@pytest.mark.parametrize("kind,operation_id", CASES)
def test_declared_refusal_has_no_legacy_success(tmp_path, kind, operation_id):
    def refuse(run, parameters):
        raise AdapterRefusal("test_refusal", "No measurement available")

    session = session_with(tmp_path, operation_id, refuse)
    response = request(session, kind)
    assert response["type"] == "error" and response["payload"]["code"] == "test_refusal"
    assert not session.results and not session.executions
    assert not list(tmp_path.glob("result-*.json"))


@pytest.mark.parametrize("kind,operation_id", CASES)
def test_storage_failure_preserves_prior_result_and_allows_retry(tmp_path, kind, operation_id):
    session = Session(make_demo_run(), tmp_path)
    first = request(session, kind)["payload"]
    with patch("ciw.session.write_json", side_effect=OSError("storage unavailable")):
        response = request(session, kind)
    assert response["type"] == "error" and response["payload"]["code"] == "storage_error"
    assert session.results == {first["result_id"]: first}
    assert request(session, kind)["type"] == "response"
    assert len(session.results) == 2


@pytest.mark.parametrize("kind,operation_id", CASES)
def test_offline_corruption_remains_rejected_without_writes(tmp_path, kind, operation_id):
    session = Session(make_demo_run(), tmp_path)
    request(session, kind)
    saved = session.save_workspace(tmp_path / "workspace.json")
    content = read_json(saved)
    content["results"][0]["data"]["unit"] = "corrupt"
    write_json(saved, content)
    with patch("ciw.session.write_json") as writer:
        with pytest.raises(ValueError, match="unit"):
            Session.from_workspace(saved, tmp_path / "rejected")
        writer.assert_not_called()


@pytest.mark.parametrize("kind,operation_id", CASES)
def test_live_socket_rejects_bad_legacy_output_then_recovers(tmp_path, kind, operation_id):
    import asyncio
    import json
    from websockets.asyncio.client import connect
    from websockets.asyncio.server import serve
    from ciw.server import WorkbenchServer

    state = {"invalid": True}

    def calculate(run, parameters):
        data = reference(operation_id, run, parameters)
        if state["invalid"]:
            data["unit"] = "invalid"
        return data

    session = session_with(tmp_path, operation_id, calculate)

    async def exercise():
        async with serve(WorkbenchServer(session).handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            async with connect(f"ws://127.0.0.1:{port}") as socket:
                async def receive():
                    return json.loads(await asyncio.wait_for(socket.recv(), timeout=5))

                assert (await receive())["type"] == "session.snapshot"
                message = {"protocol_version": 1, "request_id": "live-legacy",
                           "type": kind, "payload": {}}
                await socket.send(json.dumps(message))
                response = await receive()
                assert response["type"] == "error" and response["payload"]["code"] == "invalid_payload"
                assert not session.results
                state["invalid"] = False
                await socket.send(json.dumps(message))
                response = await receive()
                assert response["type"] == "response" and len(session.results) == 1
                assert response["payload"]["operation_id"] == operation_id

    asyncio.run(exercise())
