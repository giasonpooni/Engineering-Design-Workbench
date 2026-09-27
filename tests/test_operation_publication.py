"""A failed operation publication must not leave a completed orphan record."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest

from ciw.instruments import make_demo_run
from ciw.session import Session, read_json, write_json


def execute(session, operation_id="statistics.v1"):
    return session.handle({"protocol_version": 1, "request_id": "publication-test",
                           "type": "operation.execute", "payload": {"operation_id": operation_id}})


@pytest.mark.parametrize("fail_kind", ["result", "execution"])
@pytest.mark.parametrize("after_write", [False, True])
def test_publication_failure_removes_only_new_records_and_allows_retry(tmp_path, fail_kind, after_write):
    session = Session(make_demo_run(), tmp_path)
    original = execute(session)["payload"]
    before_results, before_executions = deepcopy(session.results), deepcopy(session.executions)
    prior_bytes = {p.name: p.read_bytes() for p in tmp_path.glob("*.json")}

    def interrupted_write(path, data):
        path = Path(path)
        if path.name.startswith(fail_kind + "-"):
            if after_write:
                write_json(path, data)
            raise OSError("injected publication failure")
        return write_json(path, data)

    with patch("ciw.session.write_json", side_effect=interrupted_write):
        response = execute(session)
    assert response["type"] == "error" and response["payload"]["code"] == "storage_error"
    assert session.results == before_results and session.executions == before_executions
    assert session._pending_operations == 0
    current_bytes = {p.name: p.read_bytes() for p in tmp_path.glob("*.json")}
    assert current_bytes.keys() == prior_bytes.keys()
    for name, content in prior_bytes.items():
        assert current_bytes[name] == content
    assert not list(tmp_path.glob(".ciw-*.tmp"))
    again = execute(session)["payload"]
    assert again["status"] == "completed"
    assert again["execution"]["execution_id"] != original["execution"]["execution_id"]
    assert len(session.results) == len(session.executions) == 2
    saved = session.save_workspace(tmp_path / "workspace.json")
    restored = Session.from_workspace(saved, tmp_path / "restored")
    assert restored.results == session.results and restored.executions == session.executions


def test_result_is_written_before_completed_execution(tmp_path):
    session = Session(make_demo_run(), tmp_path)
    observed = []

    def record_write(path, data):
        observed.append(data["schema"])
        if data["schema"] == "ciw.execution.v1" and data["status"] == "completed":
            result_path = tmp_path / (data["result_id"] + ".json")
            assert result_path.is_file()
            assert read_json(result_path)["execution_id"] == data["execution_id"]
        return write_json(path, data)

    with patch("ciw.session.write_json", side_effect=record_write):
        response = execute(session)
    assert response["payload"]["status"] == "completed"
    assert observed == ["ciw.operation-result.v1", "ciw.execution.v1"]


def test_refused_operation_still_persists_only_execution(tmp_path):
    session = Session(make_demo_run(), tmp_path)
    response = execute(session, "not-registered.v1")["payload"]
    assert response["status"] == "refused" and response["result"] is None
    assert not list(tmp_path.glob("result-*.json"))
    assert len(list(tmp_path.glob("execution-*.json"))) == 1
    saved = session.save_workspace(tmp_path / "workspace.json")
    assert Session.from_workspace(saved, tmp_path / "restored").executions == session.executions


def test_cleanup_failure_does_not_publish_or_mask_storage_error(tmp_path, caplog):
    session = Session(make_demo_run(), tmp_path)
    original_unlink = Path.unlink

    def interrupted_write(path, data):
        if Path(path).name.startswith("execution-"):
            raise OSError("original publication failure")
        return write_json(path, data)

    def deny_result_cleanup(path, *args, **kwargs):
        if path.name.startswith("result-"):
            raise PermissionError("injected cleanup failure")
        return original_unlink(path, *args, **kwargs)

    with patch("ciw.session.write_json", side_effect=interrupted_write), \
            patch.object(Path, "unlink", deny_result_cleanup):
        response = execute(session)
    assert response["type"] == "error" and response["payload"]["code"] == "storage_error"
    assert not session.results and not session.executions and session._pending_operations == 0
    assert not list(tmp_path.glob("execution-*.json"))
    assert "Unable to remove unpublished operation record" in caplog.text


def test_failed_execution_cleanup_preserves_its_result_dependency(tmp_path, caplog):
    session = Session(make_demo_run(), tmp_path)
    original_unlink = Path.unlink

    def interrupted_write(path, data):
        write_json(path, data)
        if Path(path).name.startswith("execution-"):
            raise OSError("failure after completion file was written")
        return path

    def deny_execution_cleanup(path, *args, **kwargs):
        if path.name.startswith("execution-"):
            raise PermissionError("cannot remove completion file")
        return original_unlink(path, *args, **kwargs)

    with patch("ciw.session.write_json", side_effect=interrupted_write), \
            patch.object(Path, "unlink", deny_execution_cleanup):
        response = execute(session)
    assert response["type"] == "error" and response["payload"]["code"] == "storage_error"
    assert not session.results and not session.executions and session._pending_operations == 0
    paths = list(tmp_path.glob("execution-*.json"))
    assert len(paths) == 1
    execution = read_json(paths[0])
    result = read_json(tmp_path / (execution["result_id"] + ".json"))
    assert result["execution_id"] == execution["execution_id"]
    assert "Unable to remove unpublished operation record" in caplog.text
