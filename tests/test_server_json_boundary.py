"""Ambiguous JSON must not be executed, including on a live WebSocket."""
import asyncio
import json

import pytest
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from ciw.instruments import make_demo_run
from ciw.operations.registry import Operation, OperationRegistry, default_registry
from ciw.server import WorkbenchServer
from ciw.session import Session


AMBIGUOUS_REQUESTS = [
    '{"protocol_version":1,"request_id":"ambiguous","type":"session.get",'
    '"type":"operation.execute","payload":{"operation_id":"statistics.v1","parameters":{}}}',
    '{"protocol_version":1,"request_id":"first","request_id":"second",'
    '"type":"session.get","payload":{}}',
    '{"protocol_version":1,"request_id":"same","type":"session.get",'
    '"payload":{},"payload":{}}',
    '{"protocol_version":1,"request_id":"nested","type":"operation.execute",'
    '"payload":{"operation_id":"statistics.v1","parameters":{"channel":"q","channel":"v"}}}',
    '{"protocol_version":1,"request_id":"escaped","type":"operation.execute",'
    '"payload":{"operation_id":"statistics.v1","parameters":{"channel":"q","cha\\u006enel":"v"}}}',
]


@pytest.mark.parametrize("raw", AMBIGUOUS_REQUESTS)
def test_duplicate_keys_are_rejected_before_execution_and_connection_survives(tmp_path, raw):
    session = Session(make_demo_run(), tmp_path)

    async def exercise():
        bridge = WorkbenchServer(session)
        async with serve(bridge.handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            async with connect(f"ws://127.0.0.1:{port}") as client:
                assert json.loads(await asyncio.wait_for(client.recv(), 3))["type"] == "session.snapshot"
                await client.send(raw)
                response = json.loads(await asyncio.wait_for(client.recv(), 3))
                assert response["type"] == "error"
                assert response["payload"]["code"] == "invalid_request"
                assert "Duplicate" in response["payload"]["message"]
                assert response["request_id"] is None
                assert not session.executions and not session.results
                await client.send(json.dumps({"protocol_version": 1, "request_id": "valid",
                                              "type": "session.get", "payload": {}}))
                response = json.loads(await asyncio.wait_for(client.recv(), 3))
                assert response["type"] == "response" and response["request_id"] == "valid"

    asyncio.run(exercise())


def test_unexpected_provider_failure_does_not_close_websocket(tmp_path):
    reference = default_registry()
    registry = OperationRegistry()

    def fail(run, parameters):
        raise RuntimeError("controlled provider failure")

    registry.register(Operation("statistics.v1", "analysis", fail,
                                 lambda: {"provider": "failure-regression", "version": "1"}))
    registry.register(reference.get("spectrum.periodogram.v1"))
    session = Session(make_demo_run(), tmp_path, operations=registry)

    async def exercise():
        bridge = WorkbenchServer(session)
        async with serve(bridge.handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            async with connect(f"ws://127.0.0.1:{port}") as client:
                await asyncio.wait_for(client.recv(), 3)
                for operation, status in (("statistics.v1", "refused"),
                                          ("spectrum.periodogram.v1", "completed")):
                    await client.send(json.dumps({
                        "protocol_version": 1, "request_id": operation, "type": "operation.execute",
                        "payload": {"operation_id": operation, "parameters": {}},
                    }))
                    response = json.loads(await asyncio.wait_for(client.recv(), 3))
                    assert response["type"] == "response"
                    assert response["payload"]["status"] == status
        assert len(session.executions) == 2 and len(session.results) == 1

    asyncio.run(exercise())
