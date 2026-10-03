"""Impact qualification stays on the existing retained Session substrate."""
from copy import deepcopy
import csv
from unittest.mock import patch

import pytest

from ciw import impact_cli, impact_workflow as workflow
from ciw.core.identities import new_identity, validate_identity
from ciw.impact_contract import example_request
from ciw.operations.runner import check_seal, seal
from ciw.session import Session, read_json, write_json


def _bundle(tmp_path, request=None, name="impact"):
    directory = tmp_path / name
    report = workflow.run(example_request() if request is None else request, directory)
    return directory, report


def _occurrences(directory):
    workspace = read_json(directory / "workspace.json")
    results = {item["operation_id"]: item for item in workspace["results"]}
    executions = {item["operation_id"]: item for item in workspace["executions"]}
    return workspace, results, executions


def _contents(directory):
    return {path.relative_to(directory): path.read_bytes()
            for path in directory.rglob("*") if path.is_file()}


def _reseal_bundle(directory, workspace, results, executions):
    """Update all ordinary envelopes so corruption tests cross semantic gates."""
    candidate, verification = results[workflow.SIMULATE], results[workflow.VERIFY]
    seal(candidate["data"])
    seal(candidate)
    verification["parameters"]["candidate"] = deepcopy(candidate)
    executions[workflow.VERIFY]["parameters"] = deepcopy(verification["parameters"])
    payload = verification["data"]
    payload["candidate_record_digest"] = candidate["record_digest"]
    seal(payload["report"])
    seal(verification)
    for execution in executions.values():
        seal(execution)
    write_json(directory / "workspace.json", workspace)
    write_json(directory / "verification.json", payload)


def test_local_run_separates_evidence_operation_execution_and_verification(tmp_path):
    directory, inspected = _bundle(tmp_path)
    assert inspected["status"] == "LOCAL"
    workspace, results, executions = _occurrences(directory)
    assert workspace["workspace_version"] == 2
    assert set(results) == set(executions) == {workflow.SIMULATE, workflow.VERIFY}
    assert len(workspace["results"]) == len(workspace["executions"]) == 2
    candidate, verification = results[workflow.SIMULATE], results[workflow.VERIFY]
    assert candidate["role"] == "backend" and verification["role"] == "verification"
    assert candidate["evidence_id"] == verification["evidence_id"] == inspected["evidence_id"]
    assert candidate["execution_id"] != verification["execution_id"]
    assert candidate["result_id"] != verification["result_id"]
    assert candidate["runtime"]["provider"] != verification["runtime"]["provider"]
    assert candidate["runtime"]["code_sha256"] != verification["runtime"]["code_sha256"]
    payload = verification["data"]
    validate_identity(payload["verification_id"], "verification")
    assert payload["candidate_result_id"] == candidate["result_id"]
    assert payload["candidate_execution_id"] == candidate["execution_id"]
    assert payload["candidate_record_digest"] == candidate["record_digest"]
    assert verification["parameters"]["candidate"] == candidate
    assert payload["authority"] == inspected["authority"] == workflow.AUTHORITY
    for result in results.values():
        check_seal(result)
        assert result["verification_status"] == "not_verified" and result["verification_id"] is None
        assert executions[result["operation_id"]]["status"] == "completed"
        assert executions[result["operation_id"]]["result_id"] == result["result_id"]
    _, second = _bundle(tmp_path, name="second")
    assert second["evidence_id"] == inspected["evidence_id"]
    for name in ("execution_id", "result_id", "verification_execution_id", "verification_id"):
        assert second[name] != inspected[name]


def test_inspect_and_reopen_do_not_execute_solver_or_numerical_verifier(tmp_path):
    directory, original = _bundle(tmp_path)
    before = _contents(directory)
    with patch("ciw.impact_solver.simulate", side_effect=AssertionError("solver replay")), \
            patch("ciw.impact_verification.verify", side_effect=AssertionError("verifier replay")), \
            patch("ciw.session.execute_operation", side_effect=AssertionError("operation replay")):
        inspected = workflow.inspect(directory)
        restored = Session.from_workspace(directory / "workspace.json", tmp_path / "reopened")
    assert inspected == original
    assert inspected["fresh_execution"] is False
    assert inspected["fresh_numerical_verification"] is False
    assert len(restored.results) == len(restored.executions) == 2
    assert _contents(directory) == before


def test_run_verify_and_export_do_not_overwrite_retained_files(tmp_path):
    directory, original = _bundle(tmp_path)
    before = _contents(directory)
    with pytest.raises(FileExistsError):
        workflow.run(example_request(), directory)
    with patch("ciw.impact_solver.simulate", side_effect=AssertionError("solver replay")):
        verified = workflow.verify_retained(directory)
        output = tmp_path / "trace.csv"
        exported = workflow.export_csv(directory, output)
    assert verified["status"] == "LOCAL" and verified["fresh_numerical_verification"] is True
    assert verified["execution_id"] == original["execution_id"]
    assert verified["verification_id"] == original["verification_id"]
    assert "new_verification_id" not in verified
    retained = _occurrences(directory)[1][workflow.VERIFY]
    assert verified["recomputed_report_digest"] == retained["data"]["report"]["record_digest"]
    assert verified["recomputed_with_runtime"]["provider"] == retained["runtime"]["provider"]
    assert exported["source_result_id"] == original["result_id"]
    assert exported["source_execution_id"] == original["execution_id"]
    with output.open(newline="") as stream:
        rows = list(csv.reader(stream))
    assert rows[0] == ["time_s", "compression_m", "velocity_m_per_s", "force_n"]
    assert len(rows) == len(_occurrences(directory)[1][workflow.SIMULATE]["data"]["primary"]["time_s"]) + 1
    saved_csv = output.read_bytes()
    with pytest.raises(FileExistsError):
        workflow.export_csv(directory, output)
    assert output.read_bytes() == saved_csv
    assert _contents(directory) == before


def test_requested_damage_expands_scope_but_retains_valid_numerical_trace(tmp_path):
    request = example_request()
    request["desired_observables"].append("damage")
    directory, inspected = _bundle(tmp_path, request)
    assert inspected["status"] == "EXPAND"
    assert inspected["qualification"]["unsupported_observables"] == ["damage"]
    _, results, executions = _occurrences(directory)
    report = results[workflow.VERIFY]["data"]["report"]
    assert report["status"] == "PASS"
    assert all(check["status"] == "PASS" for check in report["checks"])
    assert all(execution["status"] == "completed" for execution in executions.values())
    assert results[workflow.SIMULATE]["data"]["primary"]["force_n"]
    assert workflow.verify_retained(directory)["status"] == "EXPAND"
    output = tmp_path / "unqualified.csv"
    with pytest.raises(ValueError, match="LOCAL"):
        workflow.export_csv(directory, output)
    assert not output.exists()


def test_coarse_trace_refusal_retains_two_completed_occurrences(tmp_path):
    request = example_request()
    request["integration"]["steps_per_contact"] = 16
    # Keep the default 0.001 acceptance profile rather than relaxing the gate.
    directory, inspected = _bundle(tmp_path, request)
    assert inspected["status"] == "REFUSE"
    _, results, executions = _occurrences(directory)
    assert len(results) == len(executions) == 2
    assert all(execution["status"] == "completed" for execution in executions.values())
    report = results[workflow.VERIFY]["data"]["report"]
    assert report["status"] == "FAIL"
    assert any(check["status"] == "FAIL" for check in report["checks"])
    assert workflow.inspect(directory)["status"] == "REFUSE"
    assert workflow.verify_retained(directory)["status"] == "REFUSE"


@pytest.mark.parametrize("mutation", ["report_schema", "report_action", "report_dependency",
                                      "verification_identity", "candidate_dependency"])
def test_resealed_semantic_tampering_is_rejected_before_inspection(tmp_path, mutation):
    request = example_request()
    if mutation == "report_action":
        request["integration"]["steps_per_contact"] = 16
    directory, _ = _bundle(tmp_path, request)
    workspace, results, executions = _occurrences(directory)
    verification = results[workflow.VERIFY]
    payload, report = verification["data"], verification["data"]["report"]
    if mutation == "report_schema":
        report["schema"] = "fabricated.report.v1"
    elif mutation == "report_action":
        report["qualification"]["action"] = "LOCAL"
    elif mutation == "report_dependency":
        report["result_digest"] = "sha256:" + "0" * 64
    elif mutation == "verification_identity":
        payload["verification_id"] = new_identity("execution")
    else:
        payload["candidate_result_id"] = new_identity("result")
    _reseal_bundle(directory, workspace, results, executions)
    before = _contents(directory)
    with patch("ciw.session.write_json") as writer:
        with pytest.raises(ValueError):
            workflow.inspect(directory)
        writer.assert_not_called()
    assert _contents(directory) == before


def test_resealed_candidate_changes_cannot_be_exported(tmp_path):
    directory, _ = _bundle(tmp_path)
    workspace, results, executions = _occurrences(directory)
    trace = results[workflow.SIMULATE]["data"]["primary"]
    index = len(trace["compression_m"]) // 4
    trace["compression_m"][index] *= 1.25
    trace["force_n"][index] = example_request()["model"]["stiffness_n_per_m"] * trace["compression_m"][index]
    _reseal_bundle(directory, workspace, results, executions)
    with pytest.raises(ValueError):
        workflow.verify_retained(directory)
    output = tmp_path / "tampered.csv"
    with pytest.raises(ValueError):
        workflow.export_csv(directory, output)
    assert not output.exists()


def test_embedded_candidate_cannot_substitute_a_detached_execution_occurrence(tmp_path):
    directory, _ = _bundle(tmp_path)
    workspace, results, executions = _occurrences(directory)
    verification = results[workflow.VERIFY]
    detached = deepcopy(results[workflow.SIMULATE])
    detached["result_id"] = new_identity("result")
    detached["execution_id"] = new_identity("execution")
    seal(detached)
    verification["parameters"]["candidate"] = detached
    executions[workflow.VERIFY]["parameters"] = deepcopy(verification["parameters"])
    payload = verification["data"]
    payload.update(candidate_result_id=detached["result_id"],
                   candidate_execution_id=detached["execution_id"],
                   candidate_record_digest=detached["record_digest"])
    seal(verification)
    seal(executions[workflow.VERIFY])
    write_json(directory / "workspace.json", workspace)
    write_json(directory / "verification.json", payload)
    with patch("ciw.session.write_json") as writer:
        with pytest.raises(ValueError, match="candidate|occurrence|depend"):
            Session.from_workspace(directory / "workspace.json", tmp_path / "rejected")
        writer.assert_not_called()
        with pytest.raises(ValueError, match="candidate|occurrence|depend"):
            workflow.inspect(directory)
        writer.assert_not_called()


def test_distinct_verification_executions_cannot_reuse_a_verification_identity(tmp_path):
    directory, _ = _bundle(tmp_path)
    workspace, results, executions = _occurrences(directory)
    duplicate_result = deepcopy(results[workflow.VERIFY])
    duplicate_execution = deepcopy(executions[workflow.VERIFY])
    duplicate_result["result_id"] = new_identity("result")
    duplicate_result["execution_id"] = new_identity("execution")
    duplicate_execution.update(result_id=duplicate_result["result_id"],
                               execution_id=duplicate_result["execution_id"])
    seal(duplicate_result)
    seal(duplicate_execution)
    workspace["results"].append(duplicate_result)
    workspace["executions"].append(duplicate_execution)
    write_json(directory / "workspace.json", workspace)
    with patch("ciw.session.write_json") as writer:
        with pytest.raises(ValueError, match="verification|identity"):
            Session.from_workspace(directory / "workspace.json", tmp_path / "rejected")
        writer.assert_not_called()


def test_resealed_report_metrics_cannot_replace_independent_recomputation(tmp_path):
    directory, _ = _bundle(tmp_path)
    workspace, results, executions = _occurrences(directory)
    results[workflow.VERIFY]["data"]["report"]["metrics"]["primary"]["restitution"] += 0.0001
    _reseal_bundle(directory, workspace, results, executions)
    # A data-only validator may reject it or accept its bounded structure;
    # independent recomputation must never accept the altered report.
    with pytest.raises(ValueError):
        workflow.verify_retained(directory)
    output = tmp_path / "fabricated-report.csv"
    with pytest.raises(ValueError):
        workflow.export_csv(directory, output)
    assert not output.exists()


@pytest.mark.parametrize("phase", ["solver", "verifier"])
def test_provider_failure_retains_reopenable_refused_execution(tmp_path, phase):
    directory = tmp_path / "failed"
    target = "ciw.impact_solver.simulate" if phase == "solver" else "ciw.impact_verification.verify"
    with patch(target, side_effect=RuntimeError("private-provider-detail")):
        refused = workflow.run(example_request(), directory)
    assert refused["status"] == "REFUSE"
    workspace = read_json(directory / "workspace.json")
    assert len(workspace["executions"]) == (1 if phase == "solver" else 2)
    assert len(workspace["results"]) == (0 if phase == "solver" else 1)
    execution = workspace["executions"][-1]
    assert execution["status"] == "refused" and execution["result_id"] is None
    assert execution["refusal"]["code"] == "operation_failed"
    assert "RuntimeError" in execution["refusal"]["message"]
    assert "private-provider-detail" not in execution["refusal"]["message"]
    check_seal(execution)
    assert not (directory / "verification.json").exists()
    before = _contents(directory)
    with patch("ciw.impact_solver.simulate", side_effect=AssertionError("solver replay")), \
            patch("ciw.impact_verification.verify", side_effect=AssertionError("verifier replay")):
        restored = Session.from_workspace(directory / "workspace.json", tmp_path / "reopened")
        inspected = workflow.inspect(directory)
        verified = workflow.verify_retained(directory)
    assert len(restored.executions) == len(workspace["executions"])
    assert any(item["status"] == "refused" for item in restored.executions.values())
    assert inspected == refused == verified
    assert inspected["fresh_execution"] is False and inspected["fresh_numerical_verification"] is False
    assert _contents(directory) == before


@pytest.mark.parametrize(("field", "value"), [("contact_law", "hertzian_contact"),
    ("support", "deformable_plate"), ("damping_n_s_per_m", 1.0),
    ("gravity_during_contact_m_per_s2", 9.81), ("initial_compression_m", 0.001)])
def test_unsupported_physical_laws_reject_before_creating_run_directory(tmp_path, field, value):
    request = example_request()
    request["model"][field] = value
    directory = tmp_path / "unsupported"
    with pytest.raises(ValueError):
        workflow.run(request, directory)
    assert not directory.exists()


def test_cli_preserves_existing_example_and_reports_qualification_exit_codes(tmp_path, capsys):
    request_path = tmp_path / "request.json"
    assert impact_cli.main(["example", "--output", str(request_path)]) == 0
    original = request_path.read_bytes()
    assert impact_cli.main(["example", "--output", str(request_path)]) == 1
    assert request_path.read_bytes() == original
    request = read_json(request_path)
    request["desired_observables"].append("damage")
    write_json(request_path, request)
    directory = tmp_path / "expanded"
    assert impact_cli.main(["run", str(request_path), "--output-dir", str(directory)]) == 2
    assert impact_cli.main(["inspect", str(directory)]) == 2
    assert impact_cli.main(["verify", str(directory)]) == 2
    assert '"status": "EXPAND"' in capsys.readouterr().out
