"""Reject decimal exponents that overflow the protocol's floating-point reader."""
import asyncio
import json
import math
from unittest.mock import patch

import pytest
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from ciw.cli import main, request_remote, watch_remote
from ciw.instruments import make_demo_run
from ciw.server import WorkbenchServer
from ciw.session import Session, loads_json, read_json


@pytest.mark.parametrize("raw", [
    "1e309", "-1e309", "1E+9999", "1.7976931348623159e308",
    '{"parameters":{"gain":1e309}}', '[0,{"value":-1e9999}]',
])
def test_overflowing_json_numbers_are_rejected(raw):
    with pytest.raises(ValueError, match="Nonfinite JSON number"):
        loads_json(raw)


@pytest.mark.parametrize("raw", ["NaN", "Infinity", "-Infinity"])
def test_nonstandard_nonfinite_literals_remain_rejected(raw):
    with pytest.raises(ValueError, match="Nonfinite JSON number"):
        loads_json(raw)


@pytest.mark.parametrize("raw", [
    "1.7976931348623157e308", "-1.7976931348623157e308", "5e-324", "-0.0",
    '{"count":9007199254740993,"value":1.25,"text":"1e9999"}',
])
def test_finite_json_values_preserve_standard_representation(raw):
    expected = json.loads(raw)
    actual = loads_json(raw)
    assert actual == expected and type(actual) is type(expected)
    if isinstance(actual, float):
        assert math.isfinite(actual)
        assert actual.hex() == expected.hex()
    else:
        assert isinstance(actual["count"], int)


def test_read_json_rejects_overflow_in_nested_record(tmp_path):
    path = tmp_path / "record.json"
    path.write_text('{"result":{"value":1e9999}}', encoding="utf-8")
    with pytest.raises(ValueError, match="Nonfinite JSON number"):
        read_json(path)


@pytest.mark.parametrize("from_file", [False, True])
def test_cli_refuses_overflow_before_opening_connection(tmp_path, capsys, monkeypatch, from_file):
    raw = '{"parameters":{"gain":1e309}}'
    if from_file:
        path = tmp_path / "request.json"
        path.write_text(raw, encoding="utf-8")
        args = ["--payload-file", str(path)]
    else:
        args = ["--payload", raw]

    def do_not_start(coro):
        coro.close()
        raise AssertionError("invalid JSON must not start a connection")

    monkeypatch.setattr("ciw.cli.asyncio.run", do_not_start)
    assert main(["send", *args, "operation.execute"]) == 2
    assert "Nonfinite JSON number" in capsys.readouterr().err


def test_live_server_refuses_overflow_before_dispatch_and_remains_usable(tmp_path):
    session = Session(make_demo_run(), tmp_path)

    async def exercise():
        async with serve(WorkbenchServer(session).handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            async with connect(f"ws://127.0.0.1:{port}", proxy=None) as socket:
                await asyncio.wait_for(socket.recv(), 3)
                before = set(tmp_path.glob("*.json"))
                with patch.object(session, "handle", wraps=session.handle) as dispatch:
                    await socket.send(
                        '{"protocol_version":1,"request_id":"overflow","type":"session.get",'
                        '"payload":{"unexpected":1e309}}')
                    error = json.loads(await asyncio.wait_for(socket.recv(), 3))
                    assert error["type"] == "error"
                    assert error["payload"]["code"] == "invalid_request"
                    dispatch.assert_not_called()
                assert set(tmp_path.glob("*.json")) == before
                assert not session.results and not session.executions
                await socket.send(json.dumps({"protocol_version": 1, "request_id": "valid",
                                              "type": "session.get", "payload": {}}))
                reply = json.loads(await asyncio.wait_for(socket.recv(), 3))
                assert reply["type"] == "response" and reply["request_id"] == "valid"
    asyncio.run(exercise())


def test_remote_client_rejects_overflowing_result():
    async def exercise():
        async def handler(socket):
            request = json.loads(await socket.recv())
            await socket.send('{"protocol_version":1,"request_id":' + json.dumps(request["request_id"]) +
                              ',"type":"response","payload":{"value":1e309}}')
        async with serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            with pytest.raises(ValueError, match="Nonfinite JSON number"):
                await request_remote(f"ws://127.0.0.1:{port}", "session.get", {})
    asyncio.run(exercise())


def test_watch_rejects_overflow_before_printing(capsys):
    async def exercise():
        async def handler(socket):
            await socket.send('{"type":"session.snapshot","payload":{"value":1e309}}')
        async with serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            with pytest.raises(ValueError, match="Nonfinite JSON number"):
                await watch_remote(f"ws://127.0.0.1:{port}")
    asyncio.run(exercise())
    assert capsys.readouterr().out == ""
