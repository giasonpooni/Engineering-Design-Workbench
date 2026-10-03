"""Public irrigation commands, explicit planning holds and create-only artifacts."""
import pytest

from ciw import irrigation_cli, irrigation_workflow as workflow, net
from ciw.session import read_json, write_json


def test_cli_full_lifecycle_with_separate_qualification_and_review_status(tmp_path, capsys):
    request_path = tmp_path / "request.json"
    assert net.main(["irrigation", "example", "--output", str(request_path)]) == 0
    request_bytes = request_path.read_bytes()
    assert irrigation_cli.main(["example", "--output", str(request_path)]) == 1
    assert request_path.read_bytes() == request_bytes
    request = read_json(request_path)
    request["zones"][1]["soil_measurements"]["observations"][0]["calibrated_theta_m3_m3"] = 0.24
    write_json(request_path, request)
    directory = tmp_path / "run"
    assert irrigation_cli.main(["run", "--request", str(request_path), "--output-dir", str(directory)]) == 2
    assert irrigation_cli.main(["inspect", str(directory)]) == 2
    witness = tmp_path / "audit.json"
    assert irrigation_cli.main(["verify", str(directory), "--output", str(witness)]) == 2
    saved = read_json(witness)
    assert saved["status"] == "LOCAL" and saved["planning_status"] == "REVIEW"
    assert saved["fresh_numerical_verification"]
    assert saved["fresh_verification_record"]["verification_id"] == saved["fresh_verification_id"]
    assert saved["fresh_verification_record"]["report"]["record_digest"] == saved["recomputed_report_digest"]
    assert irrigation_cli.main(["verify", str(directory), "--output", str(witness)]) == 1
    assert irrigation_cli.main(["replay", str(directory), "--output-dir", str(tmp_path / "replay")]) == 2
    for command, extension in (("export-csv", "csv"), ("report", "html")):
        output = tmp_path / ("proposal." + extension)
        assert irrigation_cli.main([command, str(directory), "--output", str(output)]) == 2
        assert output.is_file()
        before = output.read_bytes()
        assert irrigation_cli.main([command, str(directory), "--output", str(output)]) == 1
        assert output.read_bytes() == before
    emitted = capsys.readouterr()
    assert '"status": "LOCAL"' in emitted.out and '"planning_status": "REVIEW"' in emitted.out
    assert '"status": "REFUSE"' in emitted.err


@pytest.mark.parametrize("status,planning,expected", [
    ("LOCAL", "READY", 0), ("LOCAL", "REVIEW", 2), ("LOCAL", "ABSTAIN", 2),
    ("LOCAL", "UNMET", 2), ("REFUSE", "READY", 1), ("exported", "REVIEW", 2),
])
def test_cli_exit_status_never_equates_numerical_qualification_with_a_ready_plan(status, planning, expected):
    assert irrigation_cli._exit_status({"status": status, "planning_status": planning}) == expected


def test_cli_malformed_and_ambiguous_inputs_leave_no_bundle(tmp_path, capsys):
    malformed = tmp_path / "malformed.json"
    malformed.write_text('{"schema":"wrong","schema":"duplicate"}', encoding="utf-8")
    output = tmp_path / "bad"
    assert irrigation_cli.main(["run", str(malformed), "--output-dir", str(output)]) == 1
    assert not output.exists()
    for arguments in (["run", "--output-dir", str(output)],
                      ["run", "one.json", "--request", "two.json", "--output-dir", str(output)]):
        with pytest.raises(SystemExit):
            irrigation_cli.main(arguments)
    assert '"status": "REFUSE"' in capsys.readouterr().err


def test_cli_run_and_replay_never_replace_an_existing_bundle(tmp_path):
    request = tmp_path / "request.json"
    write_json(request, workflow.contract.example_request())
    directory = tmp_path / "run"
    assert irrigation_cli.main(["run", str(request), "--output-dir", str(directory)]) == 0
    before = (directory / "workspace.json").read_bytes()
    assert irrigation_cli.main(["run", str(request), "--output-dir", str(directory)]) == 1
    assert (directory / "workspace.json").read_bytes() == before
    assert irrigation_cli.main(["replay", str(directory), "--output-dir", str(directory)]) == 1
    assert (directory / "workspace.json").read_bytes() == before
