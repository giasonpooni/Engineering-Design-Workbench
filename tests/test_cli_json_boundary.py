"""Operator JSON uses the same duplicate-key rule as retained workspaces."""
import asyncio
import json

import pytest
from websockets.asyncio.server import serve

from ciw.cli import main, request_remote
from ciw.session import loads_json, read_json


AMBIGUOUS = [
    '{"channel":"q","channel":"v"}',
    '{"channel":"q","cha\\u006enel":"v"}',
    '{"a":1,"a":1}',
    '{"outer":{"inner":1,"inner":2}}',
]


@pytest.mark.parametrize("raw", AMBIGUOUS)
def test_loads_json_rejects_duplicate_keys(raw):
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        loads_json(raw)


def test_loads_json_rejects_nonfinite_and_non_text():
    with pytest.raises(ValueError, match="Nonfinite"):
        loads_json('{"a":NaN}')
    with pytest.raises(ValueError, match="string"):
        loads_json(b'{"a":1}')


def test_loads_json_keeps_distinct_objects():
    assert loads_json('{"a":1,"b":{"a":2}}') == {"a": 1, "b": {"a": 2}}


def test_read_json_still_rejects_duplicate_keys(tmp_path):
    path = tmp_path / "ambiguous.json"
    path.write_text('{"channel":"q","channel":"v"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate JSON key: channel"):
        read_json(path)


@pytest.mark.parametrize("argv", [
    ["send", "--payload", '{"channel":"q","channel":"v"}', "session.get"],
    ["send", "--payload", '{"channel":"q","cha\\u006enel":"q"}', "session.get"],
])
def test_send_rejects_ambiguous_payload_before_connecting(argv, capsys, monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("ambiguous payload must not open a socket")
    monkeypatch.setattr("ciw.cli.asyncio.run", explode)
    assert main(argv) == 2
    assert "Duplicate JSON key" in capsys.readouterr().err


def test_send_rejects_ambiguous_payload_file(tmp_path, capsys, monkeypatch):
    path = tmp_path / "payload.json"
    path.write_text('{"operation_id":"statistics.v1","operation_id":"spectrum.periodogram.v1"}\n',
                    encoding="utf-8")
    monkeypatch.setattr("ciw.cli.asyncio.run", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("ambiguous file must not open a socket")))
    assert main(["send", "--payload-file", str(path), "operation.execute"]) == 2
    assert "Duplicate JSON key" in capsys.readouterr().err


def test_remote_response_duplicate_keys_are_rejected(tmp_path):
    async def exercise():
        async def handler(websocket):
            await websocket.recv()
            await websocket.send(
                '{"protocol_version":1,"type":"response","type":"error","payload":{}}')

        async with serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            with pytest.raises(ValueError, match="Duplicate JSON key: type"):
                await request_remote(f"ws://127.0.0.1:{port}", "session.get", {})

    asyncio.run(exercise())
