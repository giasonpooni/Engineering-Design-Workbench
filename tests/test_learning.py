"""Teaching uses the existing runner; inspection never upgrades a claim."""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ciw.cli import main
from ciw.learning import (TOPIC, LEVELS, catalog, lesson, work,
                          inspect_workspace, verify_workspace, replay_workspace)
from ciw.operations.registry import OperationRegistry
from ciw.operations.runner import seal
from ciw.session import Session, read_json, write_json


@pytest.fixture
def retained(tmp_path):
    reply = work(tmp_path / "original")
    assert reply["status"] == "completed"
    return Path(reply["workspace_file"]), reply["result"]


def directory_bytes(directory):
    return {str(path.relative_to(directory)): path.read_bytes()
            for path in directory.rglob("*") if path.is_file()}


def test_curriculum_is_an_outline_and_lessons_are_detached():
    value = catalog()
    assert [book["book"] for book in value["books"]] == ["I", "II", "III", "IV", "V", "VI"]
    assert {book["status"] for book in value["books"]} == {"curriculum_outline"}
    assert value["available_lessons"] == [TOPIC]
    content = lesson()
    content["derive"].clear()
    assert len(lesson()["derive"]) == 6
    assert "chronology" in lesson()["history"]["scope"]


@pytest.mark.parametrize("level", LEVELS)
def test_abstraction_changes_explanation_not_the_operation(level):
    content = lesson(level=level)
    assert content["level"] == level
    assert "statistics.v1" in content["computation"]
    assert content["verification"] == lesson()["verification"]
    assert "not claims that the dynamics preserve RMS" in content["invariants"]


@pytest.mark.parametrize("topic,level", [("proof", "formal"), (TOPIC, "proof"), ("sin(x)", "concrete")])
def test_unknown_language_is_refused(topic, level):
    with pytest.raises(ValueError, match="Unsupported"):
        lesson(topic, level)


def test_work_retains_standard_operation_and_execution(retained):
    path, result = retained
    workspace = read_json(path)
    assert workspace["workspace_version"] == 2
    assert result["schema"] == "ciw.operation-result.v1"
    assert result["operation_id"] == "statistics.v1"
    assert result["parameters"] == {"channel": "q", "interval_s": [0.0, 12.0]}
    assert result["data"]["sample_count"] == 768
    assert result["verification_status"] == "not_verified"
    execution = workspace["executions"][0]
    assert execution["execution_id"] == result["execution_id"]
    assert execution["result_id"] == result["result_id"]
    assert workspace["results"] == [result]


def test_inspection_preserves_records_and_never_calculates(retained):
    path, result = retained
    before = directory_bytes(path.parent)
    with patch("ciw.session.execute_operation", side_effect=AssertionError("no execution")), \
         patch("ciw.learning.make_demo_run", side_effect=AssertionError("no generation")), \
         patch("ciw.learning._compare_rms", side_effect=AssertionError("no check")):
        view = inspect_workspace(path, result["result_id"])
    assert view["result"] == result
    assert view["execution"]["execution_id"] == result["execution_id"]
    assert view["representation"]["coordinate_frame"] == "oscillator-state"
    assert view["representation"]["time_reference"] == "seconds since run start"
    assert view["representation"]["measurement_uncertainty"] == "not_declared_synthetic_source"
    assert view["authority"]["numerical_check"] == "not_performed_by_inspection"
    assert directory_bytes(path.parent) == before


def test_decimal_check_is_independent_and_does_not_admit(retained):
    path, result = retained
    before = directory_bytes(path.parent)
    with patch("ciw.session.execute_operation", side_effect=AssertionError("no provider")), \
         patch("ciw.adapters.oscillator.compute_statistics", side_effect=AssertionError("independent check")):
        report = verify_workspace(path, result["result_id"])
    assert report["status"] == "matched"
    assert report["sample_count"] == 768 and report["unit"] == "m"
    assert report["result_id"] == result["result_id"]
    assert report["verification_status"] == "not_verified"
    assert directory_bytes(path.parent) == before


def test_resealed_incorrect_rms_can_reopen_but_fails_numerical_check(retained):
    path, result = retained
    workspace = read_json(path)
    workspace["results"][0]["data"]["rms"] += 0.2
    seal(workspace["results"][0])
    write_json(path, workspace)
    before = directory_bytes(path.parent)
    assert inspect_workspace(path, result["result_id"])["result"]["data"]["rms"] == workspace["results"][0]["data"]["rms"]
    assert verify_workspace(path, result["result_id"])["status"] == "mismatch"
    assert directory_bytes(path.parent) == before


def test_replay_uses_same_evidence_and_new_occurrences(retained, tmp_path):
    path, result = retained
    before = directory_bytes(path.parent)
    replay = replay_workspace(path, result["result_id"], tmp_path / "replayed")
    fresh = replay["result"]
    assert replay["status"] == "matched"
    assert replay["comparison"]["data_match"] is True
    assert replay["comparison"]["runtime_match"] is True
    assert fresh["evidence_id"] == result["evidence_id"]
    assert fresh["operation_id"] == result["operation_id"]
    assert fresh["result_id"] != result["result_id"]
    assert fresh["execution_id"] != result["execution_id"]
    assert fresh["data"] == result["data"]
    assert fresh["verification_status"] == "not_verified"
    with patch("ciw.session.execute_operation", side_effect=AssertionError("reopen only")):
        Session.from_workspace(Path(replay["workspace_file"]), tmp_path / "reopened")
    assert directory_bytes(path.parent) == before


def test_replay_reports_runtime_drift_without_rewriting_old_records(retained, tmp_path):
    path, result = retained
    workspace = read_json(path)
    for record in [workspace["results"][0], workspace["executions"][0]]:
        record["runtime"]["educational_drift_fixture"] = "old"
        seal(record)
    write_json(path, workspace)
    before = directory_bytes(path.parent)
    replay = replay_workspace(path, result["result_id"], tmp_path / "drift")
    assert replay["status"] == "mismatch"
    assert replay["comparison"] == {
        "runtime_match": False, "data_match": True,
        "scope": "Exact equality of retained runtime declarations and statistics payloads",
        "verification_status": "not_verified",
    }
    assert directory_bytes(path.parent) == before


@pytest.mark.parametrize("action", [inspect_workspace, verify_workspace])
def test_unknown_result_does_not_execute_or_write_original(retained, action):
    path, _ = retained
    before = directory_bytes(path.parent)
    with pytest.raises(ValueError, match="Select a retained result_id"):
        action(path, "result-absent")
    assert directory_bytes(path.parent) == before


def test_wrong_operation_is_refused_before_creating_replay(retained, tmp_path):
    path, _ = retained
    restored = Session.from_workspace(path, tmp_path / "staged")
    response = restored.handle({
        "protocol_version": 1, "request_id": "spectrum", "type": "operation.execute",
        "payload": {"operation_id": "spectrum.periodogram.v1",
                    "parameters": {"channel": "q", "interval_s": [0.0, 12.0]}},
    })
    result = response["payload"]["result"]
    restored.save_workspace(path)
    destination = tmp_path / "refused"
    with pytest.raises(ValueError, match="Lesson requires"):
        replay_workspace(path, result["result_id"], destination)
    assert not destination.exists()


def test_corrupt_evidence_is_refused(retained):
    path, result = retained
    workspace = read_json(path)
    workspace["run"]["channels"]["q"]["values"][0] += 1
    write_json(path, workspace)
    before = directory_bytes(path.parent)
    with pytest.raises(ValueError):
        inspect_workspace(path, result["result_id"])
    assert directory_bytes(path.parent) == before


def test_operation_refusal_is_retained_without_result(tmp_path, monkeypatch):
    monkeypatch.setattr("ciw.session.default_operations", OperationRegistry)
    reply = work(tmp_path / "refused")
    assert reply["status"] == "refused" and reply["result"] is None
    workspace = read_json(Path(reply["workspace_file"]))
    assert workspace["results"] == []
    assert len(workspace["executions"]) == 1
    assert workspace["executions"][0]["status"] == "refused"


def test_existing_directory_is_not_overwritten(retained):
    path, result = retained
    before = directory_bytes(path.parent)
    with pytest.raises(FileExistsError):
        work(path.parent)
    with pytest.raises(FileExistsError):
        replay_workspace(path, result["result_id"], path.parent)
    assert directory_bytes(path.parent) == before


@pytest.mark.parametrize("arguments", [
    ["math"], ["math", "history", TOPIC, "--json"],
    ["math", "learn", TOPIC, "--json"],
    ["math", "explore", TOPIC, "--view", "derive", "--json"],
    ["math", "explore", TOPIC, "--view", "bridge", "--json"],
])
def test_reading_content_is_offline_and_does_not_create_session(arguments, capsys):
    with patch("ciw.learning.Session", side_effect=AssertionError("reading only")), \
         patch("socket.socket", side_effect=AssertionError("offline")):
        assert main(arguments) == 0
    assert isinstance(json.loads(capsys.readouterr().out), dict)


def test_cli_work_reopen_check_and_replay(tmp_path, capsys):
    with patch("socket.socket", side_effect=AssertionError("offline")):
        assert main(["math", "work", TOPIC, "--output-dir", str(tmp_path / "work")]) == 0
        work_reply = json.loads(capsys.readouterr().out)
        arguments = [work_reply["workspace_file"], "--result-id", work_reply["result"]["result_id"]]
        assert main(["math", "inspect", *arguments]) == 0
        assert json.loads(capsys.readouterr().out)["result"] == work_reply["result"]
        assert main(["math", "verify", *arguments]) == 0
        assert json.loads(capsys.readouterr().out)["status"] == "matched"
        assert main(["math", "replay", *arguments, "--output-dir", str(tmp_path / "replay")]) == 0
        assert json.loads(capsys.readouterr().out)["status"] == "matched"


def test_cli_mismatch_returns_failure(retained, capsys):
    path, result = retained
    workspace = read_json(path)
    workspace["results"][0]["data"]["rms"] += 0.2
    seal(workspace["results"][0])
    write_json(path, workspace)
    assert main(["math", "verify", str(path), "--result-id", result["result_id"]]) == 3
    assert json.loads(capsys.readouterr().out)["status"] == "mismatch"


def test_human_lesson_has_grammar_and_no_execution(capsys):
    assert main(["math", "learn", TOPIC, "--level", "concrete"]) == 0
    output = capsys.readouterr().out
    for heading in ("STATE", "STRUCTURE", "TRANSFORMATION", "COMPUTATION", "VERIFICATION"):
        assert heading in output
