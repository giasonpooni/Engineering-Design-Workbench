"""Crush contact extends the retained Session workflow without changing V1."""
from copy import deepcopy
import csv
from unittest.mock import patch

import pytest

from ciw import impact_cli, impact_workflow as workflow
from ciw.core.identities import evidence_id, new_identity, validate_identity
from ciw.impact_contract import example_request as elastic_request
from ciw.impact_crush_contract import example_request
from ciw.impact_solver import simulate as elastic_simulate
from ciw.operations.runner import check_seal, digest, seal
from ciw.session import Session, read_json, write_json


def _bundle(tmp_path, request=None, name="crush"):
    directory = tmp_path / name
    return directory, workflow.run(example_request() if request is None else request, directory)


def _occurrences(directory):
    workspace = read_json(directory / "workspace.json")
    return (workspace,
            {item["operation_id"]: item for item in workspace["results"]},
            {item["operation_id"]: item for item in workspace["executions"]})


def _contents(directory):
    return {path.relative_to(directory): path.read_bytes()
            for path in directory.rglob("*") if path.is_file()}


def _reseal_bundle(directory, workspace, results, executions, *, preservation=False):
    """Recompute ordinary seals without conferring independent verification."""
    candidate, verification = results[workflow.CRUSH_SIMULATE], results[workflow.CRUSH_VERIFY]
    seal(candidate["data"])
    seal(candidate)
    verification["parameters"]["candidate"] = deepcopy(candidate)
    executions[workflow.CRUSH_VERIFY]["parameters"] = deepcopy(verification["parameters"])
    payload = verification["data"]
    payload["candidate_record_digest"] = candidate["record_digest"]
    seal(payload["report"])
    seal(verification)
    for execution in executions.values():
        seal(execution)
    write_json(directory / "workspace.json", workspace)
    write_json(directory / "verification.json", payload)
    if preservation:
        from ciw.impact_crush_preservation import build
        write_json(directory / "preservation.json", build(
            read_json(directory / "request.json"), candidate["data"], payload["report"]))


def test_v1_source_identity_and_numerical_trace_remain_exact():
    # Golden content identities captured from the pre-crush V1 implementation.
    request = elastic_request()
    source = workflow.make_source(request)
    assert source["evidence_id"] == "sha256:995cf780352e2f88636544cb20ef2a4f13e66e9efff6c308c90bcbf601607422"
    assert digest(source) == "sha256:80f1f8c60c72941f2ff57939a5f29e44209742c4148cfec1365eb8dc3a849de0"
    assert elastic_simulate(request)["record_digest"] == "sha256:66b439d87f207888439b443ec9bad52aee0e093374e9525db6f0a33e0a4ecfb1"
    assert set(source["channels"]) == {"compression", "velocity", "force"}


def test_crush_source_declares_exact_si_initial_plastic_state():
    request = example_request()
    source = workflow.make_source(request)
    assert workflow.source_request(source) == request
    assert source["instrument"] == "impact-crush-initial-state.v1"
    assert source["time_s"] == [0.0]
    expected = {"compression": "m", "velocity": "m/s", "force": "N",
                "plastic_compression": "m", "plastic_work": "J"}
    assert source["metadata"]["manifest"]["units"] == expected
    assert source["metadata"]["manifest"]["supported_operations"] == [workflow.CRUSH_SIMULATE, workflow.CRUSH_VERIFY]
    for name, unit in expected.items():
        assert source["channels"][name] == {
            "unit": unit, "values": [request["model"]["initial_speed_m_per_s"] if name == "velocity" else 0.0]}


@pytest.mark.parametrize("field,value", [("plastic_compression", 0.001), ("plastic_work", 1.0),
                                           ("plastic_compression", True), ("plastic_work", "0")])
def test_reidentified_source_cannot_change_initial_plastic_state(field, value):
    source = workflow.make_source(example_request())
    source["channels"][field]["values"][0] = value
    source["evidence_id"] = evidence_id(source)
    with pytest.raises((ValueError, TypeError)):
        workflow.source_request(source)


@pytest.mark.parametrize("field,unit", [("plastic_compression", "mm"), ("plastic_work", "kJ")])
def test_reidentified_source_cannot_change_plastic_si_units(field, unit):
    source = workflow.make_source(example_request())
    source["channels"][field]["unit"] = unit
    source["metadata"]["manifest"]["units"][field] = unit
    source["evidence_id"] = evidence_id(source)
    with pytest.raises(ValueError):
        workflow.source_request(source)


@pytest.mark.parametrize("crush_source,operation", [
    (True, workflow.SIMULATE), (True, workflow.VERIFY),
    (False, workflow.CRUSH_SIMULATE), (False, workflow.CRUSH_VERIFY),
])
def test_cross_profile_operation_is_retained_refusal_without_numerical_execution(tmp_path, crush_source, operation):
    request = example_request() if crush_source else elastic_request()
    session = Session(workflow.make_source(request), tmp_path / "session", operations=workflow.registry())
    with patch("ciw.impact_solver.simulate", side_effect=AssertionError("elastic solver executed")), \
            patch("ciw.impact_crush_solver.simulate", side_effect=AssertionError("crush solver executed")), \
            patch("ciw.impact_verification.verify", side_effect=AssertionError("elastic verifier executed")), \
            patch("ciw.impact_crush_verification.verify", side_effect=AssertionError("crush verifier executed")):
        reply = workflow._execute(session, operation, {})
        assert reply["status"] == "refused"
        assert reply["execution"]["refusal"]["code"] == "invalid_operation"
        assert "physical profile" in reply["execution"]["refusal"]["message"]
        assert not session.results and len(session.executions) == 1
        session.save_workspace(tmp_path / "cross-profile.json")
        reopened = Session.from_workspace(tmp_path / "cross-profile.json", tmp_path / "reopened")
    assert len(reopened.executions) == 1 and not reopened.results
    check_seal(next(iter(reopened.executions.values())))


def test_crush_run_keeps_distinct_occurrence_and_verification_identities(tmp_path):
    directory, inspected = _bundle(tmp_path)
    assert inspected["status"] == "LOCAL"
    workspace, results, executions = _occurrences(directory)
    assert workspace["workspace_version"] == 2
    assert set(results) == set(executions) == {workflow.CRUSH_SIMULATE, workflow.CRUSH_VERIFY}
    candidate, verification = results[workflow.CRUSH_SIMULATE], results[workflow.CRUSH_VERIFY]
    assert candidate["role"] == "backend" and verification["role"] == "verification"
    assert candidate["evidence_id"] == verification["evidence_id"] == inspected["evidence_id"]
    assert candidate["execution_id"] != verification["execution_id"]
    assert candidate["result_id"] != verification["result_id"]
    assert candidate["runtime"]["provider"] == "ciw.impact.crush-solver"
    assert verification["runtime"]["provider"] == "ciw.impact.crush-verifier"
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


def test_crush_static_inspection_reopens_without_numerical_execution_or_trace_reference(tmp_path):
    directory, original = _bundle(tmp_path)
    before = _contents(directory)
    with patch("ciw.impact_solver.simulate", side_effect=AssertionError("elastic solver replay")), \
            patch("ciw.impact_crush_solver.simulate", side_effect=AssertionError("crush solver replay")), \
            patch("ciw.impact_verification.verify", side_effect=AssertionError("elastic verifier replay")), \
            patch("ciw.impact_crush_verification.verify", side_effect=AssertionError("crush verifier replay")), \
            patch("ciw.impact_crush_reference.reference_values", side_effect=AssertionError("reference path replay")), \
            patch("ciw.session.execute_operation", side_effect=AssertionError("operation replay")):
        inspected = workflow.inspect(directory)
        reopened = Session.from_workspace(directory / "workspace.json", tmp_path / "reopened")
    assert inspected == original
    assert inspected["fresh_execution"] is False and inspected["fresh_numerical_verification"] is False
    assert len(reopened.results) == len(reopened.executions) == 2
    assert _contents(directory) == before


def test_crush_verify_export_six_si_fields_without_replaying_or_overwriting(tmp_path):
    directory, original = _bundle(tmp_path)
    before = _contents(directory)
    with patch("ciw.impact_solver.simulate", side_effect=AssertionError("elastic solver replay")), \
            patch("ciw.impact_crush_solver.simulate", side_effect=AssertionError("crush solver replay")):
        verified = workflow.verify_retained(directory)
        output = tmp_path / "crush.csv"
        exported = workflow.export_csv(directory, output)
    assert verified["status"] == "LOCAL" and verified["fresh_numerical_verification"] is True
    assert verified["execution_id"] == original["execution_id"]
    assert verified["verification_id"] == original["verification_id"]
    assert "new_verification_id" not in verified
    results = _occurrences(directory)[1]
    assert verified["recomputed_report_digest"] == results[workflow.CRUSH_VERIFY]["data"]["report"]["record_digest"]
    assert verified["recomputed_with_runtime"]["provider"] == "ciw.impact.crush-verifier"
    assert exported["source_result_id"] == original["result_id"]
    assert exported["source_execution_id"] == original["execution_id"]
    with output.open(newline="") as stream:
        rows = list(csv.reader(stream))
    names = ["time_s", "compression_m", "velocity_m_per_s", "force_n", "plastic_compression_m", "plastic_work_j"]
    assert rows[0] == names
    primary = results[workflow.CRUSH_SIMULATE]["data"]["primary"]
    assert len(rows) == len(primary["time_s"]) + 1
    assert [[float(value) for value in row] for row in rows[1:]] == [list(row) for row in zip(*(primary[name] for name in names))]
    saved = output.read_bytes()
    with pytest.raises(FileExistsError):
        workflow.export_csv(directory, output)
    assert output.read_bytes() == saved
    with pytest.raises(FileExistsError):
        workflow.run(example_request(), directory)
    assert _contents(directory) == before


def test_crush_receipts_bind_retained_content_and_only_numerical_eligibility(tmp_path):
    directory, inspected = _bundle(tmp_path)
    _, results, _ = _occurrences(directory)
    candidate = results[workflow.CRUSH_SIMULATE]["data"]
    report = results[workflow.CRUSH_VERIFY]["data"]["report"]
    bundle = read_json(directory / "preservation.json")
    refs = inspected["preservation"]
    assert bundle["schema"] == "ciw.impact-crush-preservation.v1"
    assert bundle["request_digest"] == digest(example_request())
    assert bundle["result_digest"] == candidate["record_digest"]
    assert bundle["report_digest"] == report["record_digest"]
    assert refs["contract_ref"] == bundle["contract"]["record_digest"]
    assert refs["verification_ref"] == bundle["verification"]["record_digest"]
    assert refs["verification_status"] == "VERIFIED" and refs["admission_eligibility"] == "ELIGIBLE"
    assert refs["state_admission_performed"] is False
    for claim in ("physical_validation_established", "material_damage_established", "molecular_response_established",
                  "scale_preservation_established", "cross_scale_commutative_witness_supplied", "state_admission_performed"):
        assert bundle["claims"][claim] is False


@pytest.mark.parametrize("observable", ["rate_response", "thermal_response", "damage"])
def test_unrepresented_rate_temperature_and_damage_expand_and_prevent_export(tmp_path, observable):
    request = example_request()
    request["desired_observables"].append(observable)
    directory, inspected = _bundle(tmp_path, request)
    assert inspected["status"] == "EXPAND"
    assert inspected["qualification"]["unsupported_observables"] == [observable]
    _, results, executions = _occurrences(directory)
    assert results[workflow.CRUSH_VERIFY]["data"]["report"]["status"] == "PASS"
    assert all(execution["status"] == "completed" for execution in executions.values())
    assert inspected["preservation"]["verification_status"] == "VERIFIED"
    assert inspected["preservation"]["admission_eligibility"] == "REFUSED"
    assert workflow.verify_retained(directory)["status"] == "EXPAND"
    output = tmp_path / "unqualified.csv"
    with pytest.raises(ValueError, match="LOCAL"):
        workflow.export_csv(directory, output)
    assert not output.exists()


def test_coarse_crush_trace_retains_two_completed_failed_occurrences(tmp_path):
    request = example_request()
    request["integration"]["steps_per_contact"] = 32
    directory, inspected = _bundle(tmp_path, request)
    assert inspected["status"] == "REFUSE"
    _, results, executions = _occurrences(directory)
    assert len(results) == len(executions) == 2
    assert all(execution["status"] == "completed" for execution in executions.values())
    report = results[workflow.CRUSH_VERIFY]["data"]["report"]
    assert report["status"] == "FAIL" and any(check["status"] == "FAIL" for check in report["checks"])
    assert inspected["preservation"]["verification_status"] == "REFUTED"
    assert inspected["preservation"]["admission_eligibility"] == "REFUSED"
    assert workflow.inspect(directory)["status"] == "REFUSE"
    assert workflow.verify_retained(directory)["status"] == "REFUSE"


@pytest.mark.parametrize("field,value", [("contact_law", "polymer_viscoplastic"), ("support", "plate"),
    ("damping_n_s_per_m", 1.0), ("gravity_during_contact_m_per_s2", 9.81),
    ("initial_compression_m", 0.001), ("initial_plastic_compression_m", 0.001), ("yield_force_n", True)])
def test_invalid_physical_request_rejects_before_creating_directory(tmp_path, field, value):
    request = example_request()
    request["model"][field] = value
    directory = tmp_path / "unsupported"
    with pytest.raises(ValueError):
        workflow.run(request, directory)
    assert not directory.exists()


@pytest.mark.parametrize("field,value", [("schema", "untrusted.python.module"), ("scope", "molecular_impact")])
def test_unknown_schema_and_scope_reject_before_creating_directory(tmp_path, field, value):
    request = example_request()
    request[field] = value
    directory = tmp_path / "unsupported"
    with pytest.raises(ValueError):
        workflow.run(request, directory)
    assert not directory.exists()


@pytest.mark.parametrize("phase", ["solver", "verifier"])
def test_crush_provider_failure_retains_reopenable_refused_occurrence(tmp_path, phase):
    target = "ciw.impact_crush_solver.simulate" if phase == "solver" else "ciw.impact_crush_verification.verify"
    directory = tmp_path / "failure"
    with patch(target, side_effect=RuntimeError("private-provider-detail")):
        refused = workflow.run(example_request(), directory)
    assert refused["status"] == "REFUSE"
    workspace = read_json(directory / "workspace.json")
    assert len(workspace["executions"]) == (1 if phase == "solver" else 2)
    assert len(workspace["results"]) == (0 if phase == "solver" else 1)
    occurrence = workspace["executions"][-1]
    assert occurrence["status"] == "refused" and occurrence["result_id"] is None
    assert occurrence["refusal"]["code"] == "operation_failed"
    assert "private-provider-detail" not in occurrence["refusal"]["message"]
    assert not (directory / "verification.json").exists()
    before = _contents(directory)
    with patch("ciw.impact_crush_solver.simulate", side_effect=AssertionError("solver replay")), \
            patch("ciw.impact_crush_verification.verify", side_effect=AssertionError("verifier replay")):
        assert workflow.inspect(directory) == refused
        assert workflow.verify_retained(directory) == refused
        reopened = Session.from_workspace(directory / "workspace.json", tmp_path / "reopened")
    assert len(reopened.executions) == len(workspace["executions"])
    assert _contents(directory) == before


@pytest.mark.parametrize("field", ["plastic_compression_m", "plastic_work_j"])
def test_resealed_plastic_trace_tampering_cannot_cross_retained_report_dependency(tmp_path, field):
    directory, _ = _bundle(tmp_path)
    workspace, results, executions = _occurrences(directory)
    trace = results[workflow.CRUSH_SIMULATE]["data"]["primary"]
    index = len(trace[field]) // 2
    trace[field][index] += 0.001
    _reseal_bundle(directory, workspace, results, executions)
    before = _contents(directory)
    with pytest.raises(ValueError):
        workflow.inspect(directory)
    with pytest.raises(ValueError):
        workflow.verify_retained(directory)
    output = tmp_path / "corrupted.csv"
    with pytest.raises(ValueError):
        workflow.export_csv(directory, output)
    assert not output.exists() and _contents(directory) == before


@pytest.mark.parametrize("mutation", ["report_schema", "report_dependency", "verification_identity", "candidate_dependency"])
def test_resealed_verification_semantic_tampering_is_rejected(tmp_path, mutation):
    directory, _ = _bundle(tmp_path)
    workspace, results, executions = _occurrences(directory)
    payload = results[workflow.CRUSH_VERIFY]["data"]
    if mutation == "report_schema":
        payload["report"]["schema"] = "ciw.impact-verification.v1"
    elif mutation == "report_dependency":
        payload["report"]["result_digest"] = "sha256:" + "0" * 64
    elif mutation == "verification_identity":
        payload["verification_id"] = new_identity("execution")
    else:
        payload["candidate_result_id"] = new_identity("result")
    _reseal_bundle(directory, workspace, results, executions)
    with patch("ciw.session.write_json") as writer:
        with pytest.raises(ValueError):
            workflow.inspect(directory)
        writer.assert_not_called()


def test_detached_candidate_cannot_replace_an_actual_solver_occurrence(tmp_path):
    directory, _ = _bundle(tmp_path)
    workspace, results, executions = _occurrences(directory)
    verification = results[workflow.CRUSH_VERIFY]
    detached = deepcopy(results[workflow.CRUSH_SIMULATE])
    detached["result_id"], detached["execution_id"] = new_identity("result"), new_identity("execution")
    seal(detached)
    verification["parameters"]["candidate"] = detached
    executions[workflow.CRUSH_VERIFY]["parameters"] = deepcopy(verification["parameters"])
    verification["data"].update(candidate_result_id=detached["result_id"],
                                  candidate_execution_id=detached["execution_id"],
                                  candidate_record_digest=detached["record_digest"])
    seal(verification)
    seal(executions[workflow.CRUSH_VERIFY])
    write_json(directory / "workspace.json", workspace)
    write_json(directory / "verification.json", verification["data"])
    with patch("ciw.session.write_json") as writer:
        with pytest.raises(ValueError, match="candidate|occurrence|depend"):
            Session.from_workspace(directory / "workspace.json", tmp_path / "rejected")
        writer.assert_not_called()
        with pytest.raises(ValueError, match="candidate|occurrence|depend"):
            workflow.inspect(directory)


def test_resealed_report_metric_requires_independent_recomputation(tmp_path):
    directory, _ = _bundle(tmp_path)
    workspace, results, executions = _occurrences(directory)
    report = results[workflow.CRUSH_VERIFY]["data"]["report"]
    errors = report["metrics"]["primary"]["analytic_maximum_normalized_errors"]
    errors["plastic_work_j"] += 0.0000001
    check = next(check for check in report["checks"] if check["name"] == "primary.analytic.plastic_work_j")
    check["value"] = errors["plastic_work_j"]
    # A structurally plausible report can have its typed receipts rebuilt,
    # but that does not establish that its numbers came from the verifier.
    _reseal_bundle(directory, workspace, results, executions, preservation=True)
    before = _contents(directory)
    assert workflow.inspect(directory)["status"] == "LOCAL"
    with pytest.raises(ValueError):
        workflow.verify_retained(directory)
    output = tmp_path / "fabricated.csv"
    with pytest.raises(ValueError):
        workflow.export_csv(directory, output)
    assert not output.exists() and _contents(directory) == before


def test_crush_cli_example_run_inspect_verify_and_export(tmp_path, capsys):
    request_path, directory, output = tmp_path / "request.json", tmp_path / "run", tmp_path / "trace.csv"
    assert impact_cli.main(["crush", "example", "--output", str(request_path)]) == 0
    original = request_path.read_bytes()
    assert read_json(request_path) == example_request()
    assert impact_cli.main(["crush", "example", "--output", str(request_path)]) == 1
    assert request_path.read_bytes() == original
    assert impact_cli.main(["crush", "run", str(request_path), "--output-dir", str(directory)]) == 0
    assert impact_cli.main(["crush", "inspect", str(directory)]) == 0
    assert impact_cli.main(["crush", "verify", str(directory)]) == 0
    assert impact_cli.main(["crush", "export", str(directory), "--output", str(output)]) == 0
    assert output.exists() and '"status": "LOCAL"' in capsys.readouterr().out


@pytest.mark.parametrize("crush_command", [True, False])
def test_cli_rejects_run_request_from_other_profile_before_mkdir(tmp_path, crush_command):
    request_path = tmp_path / "request.json"
    write_json(request_path, elastic_request() if crush_command else example_request())
    directory = tmp_path / "wrong-profile"
    prefix = ["crush"] if crush_command else []
    assert impact_cli.main(prefix + ["run", str(request_path), "--output-dir", str(directory)]) == 1
    assert not directory.exists()


def test_crush_cli_expansion_retains_numerical_evidence_and_returns_qualification_code(tmp_path, capsys):
    request = example_request()
    request["desired_observables"].append("damage")
    request_path, directory = tmp_path / "request.json", tmp_path / "expanded"
    write_json(request_path, request)
    assert impact_cli.main(["crush", "run", str(request_path), "--output-dir", str(directory)]) == 2
    assert impact_cli.main(["crush", "inspect", str(directory)]) == 2
    assert impact_cli.main(["crush", "verify", str(directory)]) == 2
    assert '"status": "EXPAND"' in capsys.readouterr().out
