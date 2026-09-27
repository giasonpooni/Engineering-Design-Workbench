"""A retained failed attempt invalidates views without creating a result."""
import asyncio
import json

import pytest
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

from ciw.adapters.protocol import AdapterRefusal
from ciw.server import WorkbenchServer
from ciw.thermal_workflow import ThermalWorkflow
from test_thermal_workflow import _session_with_source


@pytest.mark.parametrize("unexpected", [False, True])
def test_failed_workflow_notifies_observer_even_when_sender_errors(tmp_path, monkeypatch, unexpected):
    # This is a transport challenge, not a numerical or hardware qualification.
    session, source = _session_with_source(tmp_path)

    def fail(*_args, **_kwargs):
        if unexpected:
            raise RuntimeError("Deliberate test provider failure")
        raise AdapterRefusal("test_refusal", "Deliberate test refusal")

    monkeypatch.setattr(ThermalWorkflow, "create_session", fail)

    async def exercise():
        bridge = WorkbenchServer(session)
        async with serve(bridge.handler, "127.0.0.1", 0) as listener:
            address = f"ws://127.0.0.1:{listener.sockets[0].getsockname()[1]}"
            async with connect(address) as observer, connect(address) as sender:
                await observer.recv()
                await sender.recv()
                await sender.send(json.dumps({"protocol_version": 1, "request_id": "fail",
                    "type": "operation.execute", "payload": {
                        "operation_id": "ciw.thermal-observer.v1", "parameters": {"source_id": source["source_id"]}}}))
                event = json.loads(await asyncio.wait_for(observer.recv(), 5))
                assert event["type"] == "workbench.changed"
                if not unexpected:
                    reply = json.loads(await asyncio.wait_for(sender.recv(), 5))
                    assert reply["type"] == "error" and reply["payload"]["code"] == "test_refusal"
                else:
                    # Unexpected programmer errors keep the existing 1011 close
                    # behavior; their recorded failure is not a scientific refusal.
                    with pytest.raises(ConnectionClosed):
                        while True:
                            await asyncio.wait_for(sender.recv(), 5)
                await observer.send(json.dumps({"protocol_version": 1, "request_id": "history",
                                               "type": "execution.list", "payload": {}}))
                history = json.loads(await asyncio.wait_for(observer.recv(), 5))["payload"]["executions"]
                assert len(history) == 1
                assert history[0]["scope"] == "workflow_attempt"
                assert history[0]["result_id"] is None
                assert history[0]["status"] == ("failed" if unexpected else "refused")
                assert session.workbench.list_bundles() == []
                assert session.workbench.pending_operations == 0

    asyncio.run(exercise())
