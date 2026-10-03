"""Public net fluid CLI lifecycle, artifact bounds and create-only operations."""
import json
from unittest.mock import patch

import pytest

from ciw import fluid_cli, fluid_workflow as workflow
from ciw import net
from ciw.session import read_json, write_json
from test_fluid_workflow import small_request


@pytest.mark.parametrize("profile", workflow.contract.PROFILES)
def test_cli_full_lifecycle_and_persisted_fresh_verification_witness(tmp_path, capsys, profile):
    request_path = tmp_path / "request.json"
    assert net.main(["fluid", "example", "--profile", profile, "--output", str(request_path)]) == 0
    saved = request_path.read_bytes()
    assert fluid_cli.main(["example", "--profile", profile, "--output", str(request_path)]) == 1
    assert request_path.read_bytes() == saved
    write_json(request_path, small_request(profile))
    directory = tmp_path / "run"
    assert fluid_cli.main(["run", "--request", str(request_path), "--output-dir", str(directory)]) == 0
    assert fluid_cli.main(["inspect", str(directory)]) == 0
    witness = tmp_path / "verification-witness.json"
    assert fluid_cli.main(["verify", str(directory), "--output", str(witness)]) == 0
    artifact = read_json(witness)
    assert artifact["fresh_numerical_verification"] is True
    assert artifact["fresh_verification_record"]["verification_id"] == artifact["fresh_verification_id"]
    assert artifact["fresh_verification_record"]["report"]["record_digest"] == artifact["recomputed_report_digest"]
    assert fluid_cli.main(["verify", str(directory), "--output", str(witness)]) == 1
    assert fluid_cli.main(["export-csv", str(directory), "--output", str(tmp_path / "trace.csv")]) == 0
    assert fluid_cli.main(["export-csv", str(directory), "--output", str(tmp_path / "trace.csv")]) == 1
    assert '"fresh_verification_record"' in capsys.readouterr().out


def test_cli_expand_and_refuse_exit_codes(tmp_path, capsys):
    request_path = tmp_path / "request.json"
    request = small_request()
    request["desired_observables"].append("molecular_transport")
    write_json(request_path, request)
    directory = tmp_path / "expanded"
    assert fluid_cli.main(["run", str(request_path), "--output-dir", str(directory)]) == 2
    assert fluid_cli.main(["inspect", str(directory)]) == 2
    assert fluid_cli.main(["verify", str(directory)]) == 2
    assert fluid_cli.main(["export-csv", str(directory), "--output", str(tmp_path / "denied.csv")]) == 1
    malformed = tmp_path / "malformed.json"
    malformed.write_text('{"schema": "wrong", "schema": "repeated"}')
    assert fluid_cli.main(["run", "--request", str(malformed), "--output-dir", str(tmp_path / "bad")]) == 1
    assert not (tmp_path / "bad").exists()
    emitted = capsys.readouterr()
    assert '"status": "EXPAND"' in emitted.out and '"status": "REFUSE"' in emitted.err


def test_cli_requires_exactly_one_request_path_and_never_overwrites_run(tmp_path):
    with pytest.raises(SystemExit):
        fluid_cli.main(["run", "--output-dir", str(tmp_path / "run")])
    with pytest.raises(SystemExit):
        fluid_cli.main(["run", "first.json", "--request", "second.json", "--output-dir", str(tmp_path / "run")])
    request_path = tmp_path / "request.json"
    write_json(request_path, small_request())
    directory = tmp_path / "run"
    assert fluid_cli.main(["run", str(request_path), "--output-dir", str(directory)]) == 0
    before = (directory / "workspace.json").read_bytes()
    assert fluid_cli.main(["run", str(request_path), "--output-dir", str(directory)]) == 1
    assert (directory / "workspace.json").read_bytes() == before


def test_cli_handoff_routes_to_exact_reservoir_snapshot(tmp_path, capsys):
    directory = tmp_path / "run"
    workflow.run(small_request(), directory)
    output = tmp_path / "snapshot.json"
    assert fluid_cli.main(["handoff", str(directory), "--sample-index", "1", "--output", str(output)]) == 0
    assert read_json(output)["state"]["provenance"]["semantics"] == "simulated"
    capsys.readouterr()
