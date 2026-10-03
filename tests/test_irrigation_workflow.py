"""Retained irrigation occurrence, read-only inspection and fresh-audit boundaries."""
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import csv
from pathlib import Path
import shutil
from unittest.mock import patch

import pytest

from ciw import irrigation_contract as contract, irrigation_workflow as workflow
from ciw.core.identities import evidence_id, new_identity, validate_identity
from ciw.dependency_graph import artifact_graph
from ciw.operations.registry import default_registry
from ciw.operations.runner import check_seal, digest, seal
from ciw.session import Session, read_json, write_json


@pytest.fixture(scope="module")
def archived(tmp_path_factory):
    directory = tmp_path_factory.mktemp("irrigation") / "run"
    inspected = workflow.run(contract.example_request(), directory)
    assert inspected["status"] == "LOCAL" and inspected["planning_status"] in contract.PLANNING_STATUSES
    return directory, inspected


def occurrences(directory):
    workspace = read_json(directory / "workspace.json")
    results = {row["operation_id"]: row for row in workspace["results"]}
    executions = {row["operation_id"]: row for row in workspace["executions"]}
    return workspace, results, executions


def content(directory):
    return {path.relative_to(directory): path.read_bytes() for path in directory.rglob("*") if path.is_file()}


@contextmanager
def no_numerics(*, execute=False):
    with ExitStack() as stack:
        for target in ("ciw.irrigation_solver.simulate", "ciw.irrigation_verification.verify", "ciw.irrigation_reference.reference"):
            stack.enter_context(patch(target, side_effect=AssertionError("Unexpected numerical computation")))
        if not execute:
            stack.enter_context(patch("ciw.session.execute_operation", side_effect=AssertionError("Unexpected operation execution")))
        yield


def test_evidence_is_exact_declaration_with_detached_request():
    request = contract.example_request()
    with no_numerics():
        source = workflow.make_source(request)
        detached = workflow.source_request(source)
    assert source["evidence_id"] == evidence_id(source)
    assert source["channels"] == {"configuration_declaration": {"unit": "1", "values": [0.0]}}
    assert source["metadata"]["manifest"]["supported_operations"] == list(workflow.OPERATIONS)
    detached.clear()
    assert source["metadata"]["irrigation_request"] == request
    source["channels"]["configuration_declaration"]["values"][0] = 1.0
    source["evidence_id"] = evidence_id(source)
    with pytest.raises(ValueError, match="exact"):
        workflow.source_request(source)


@pytest.mark.parametrize("operation", workflow.OPERATIONS)
def test_operations_never_activate_from_a_saved_declaration(tmp_path, operation):
    assert operation not in {row["operation_id"] for row in default_registry().describe()}
    session = Session(workflow.make_source(contract.example_request()), tmp_path / operation)
    with no_numerics(execute=True):
        outcome = workflow._execute(session, operation, {})
    assert outcome["status"] == "refused"
    assert outcome["execution"]["refusal"]["code"] == "operation_unavailable"
    assert outcome["execution"]["runtime"] is None and not session.results


def test_retained_plan_and_verification_have_separate_bound_occurrences(archived):
    directory, inspected = archived
    workspace, results, executions = occurrences(directory)
    assert workspace["workspace_version"] == 2
    assert set(results) == set(executions) == set(workflow.OPERATIONS)
    candidate, verification = (results[item] for item in workflow.OPERATIONS)
    assert candidate["result_id"] != verification["result_id"]
    assert candidate["execution_id"] != verification["execution_id"]
    assert candidate["evidence_id"] == verification["evidence_id"] == inspected["evidence_id"]
    assert candidate["role"] == "backend" and verification["role"] == "verification"
    payload = verification["data"]
    validate_identity(payload["verification_id"], "verification")
    assert payload["candidate_result_id"] == candidate["result_id"]
    assert payload["candidate_execution_id"] == candidate["execution_id"]
    assert payload["candidate_record_digest"] == candidate["record_digest"]
    assert verification["parameters"]["candidate"] == candidate
    for row in results.values():
        check_seal(row)
        workflow.validate_runtime(row["operation_id"], row["runtime"])
        assert isinstance(row["runtime"]["environment"]["numpy"], str)
        assert row["verification_id"] is None and row["verification_status"] == "not_verified"
    assert read_json(directory / "verification.json") == payload


def test_inspection_is_stable_structural_and_does_not_recompute(archived):
    directory, inspected = archived
    before = content(directory)
    with no_numerics():
        assert workflow.inspect(directory) == inspected
        assert workflow.inspect(directory) == inspected
    assert not inspected["fresh_execution"] and not inspected["fresh_numerical_verification"]
    assert content(directory) == before


def test_every_fresh_audit_has_new_ids_and_keeps_retained_bundle_immutable(archived):
    directory, inspected = archived
    before = content(directory)
    first, second = workflow.verify_retained(directory), workflow.verify_retained(directory)
    assert first["status"] == second["status"] == "LOCAL"
    assert first["fresh_execution"] and first["fresh_numerical_verification"]
    assert first["verification_id"] == second["verification_id"] == inspected["verification_id"]
    for field in ("fresh_verification_id", "fresh_verification_execution_id", "fresh_verification_result_id"):
        assert first[field] != second[field]
    witness = first["fresh_verification_record"]
    assert witness["candidate_result_id"] == inspected["result_id"]
    assert witness["candidate_execution_id"] == inspected["execution_id"]
    assert witness["verification_id"] == first["fresh_verification_id"]
    assert witness["report"]["record_digest"] == first["recomputed_report_digest"]
    check_seal(witness["report"])
    assert content(directory) == before


def test_replay_preserves_data_and_evidence_but_creates_new_occurrences(archived, tmp_path):
    directory, original = archived
    before = content(directory)
    output = tmp_path / "replayed"
    checked = workflow.replay(directory, output)
    assert checked["status"] == "LOCAL" and checked["reproducible_planning_data"]
    assert checked["evidence_id"] == original["evidence_id"]
    assert checked["replay_source_result_id"] == original["result_id"]
    for field in ("result_id", "execution_id", "verification_id", "verification_execution_id"):
        assert checked[field] != original[field]
    _, left, _ = occurrences(directory)
    _, right, _ = occurrences(output)
    assert digest(left[workflow.PLAN]["data"]) == digest(right[workflow.PLAN]["data"])
    assert content(directory) == before
    with pytest.raises(FileExistsError):
        workflow.replay(directory, output)


def test_verification_dependency_projects_to_actual_candidate_result(archived, tmp_path):
    directory, _ = archived
    session = Session.from_workspace(directory / "workspace.json", tmp_path / "restored")
    graph = artifact_graph(session.run, session.results, session.executions, session.workbench)
    candidate = next(row for row in session.results.values() if row["operation_id"] == workflow.PLAN)
    verification = next(row for row in session.results.values() if row["operation_id"] == workflow.VERIFY)
    assert candidate["result_id"] in graph[verification["execution_id"]]["dependencies"]
    assert candidate["result_id"] in graph[verification["result_id"]]["dependencies"]


def test_live_verification_refuses_invented_external_candidate(archived, tmp_path):
    directory, _ = archived
    _, results, _ = occurrences(directory)
    source = workflow.make_source(contract.example_request())
    session = Session(source, tmp_path / "external", operations=workflow.registry())
    with no_numerics(execute=True):
        outcome = workflow._execute(session, workflow.VERIFY, {"candidate": results[workflow.PLAN]})
    assert outcome["status"] == "refused" and not session.results
    assert "retained" in outcome["execution"]["refusal"]["message"]


def test_narrowed_selection_is_refused_before_result_publication(tmp_path):
    session = Session(workflow.make_source(contract.example_request()), tmp_path / "narrowed", operations=workflow.registry())
    session.selection["interval_s"] = [0.0, 0.5]
    outcome = workflow._execute(session, workflow.PLAN, {})
    assert outcome["status"] == "refused" and not session.results
    assert "full" in outcome["execution"]["refusal"]["message"]


@pytest.mark.parametrize("mutation", ["candidate_identity", "authority", "runtime", "numpy_version", "candidate_dependency", "receipt"])
def test_resealed_binding_corruption_refuses_without_computation_or_retained_writes(archived, tmp_path, mutation):
    original, _ = archived
    directory = tmp_path / "tampered"
    shutil.copytree(original, directory)
    workspace, results, executions = occurrences(directory)
    candidate, verification = (results[item] for item in workflow.OPERATIONS)
    payload = verification["data"]
    if mutation == "candidate_identity":
        payload["candidate_result_id"] = new_identity("result")
    elif mutation == "authority":
        payload["authority"]["hardware_actuation"] = "performed"
    elif mutation in {"runtime", "numpy_version"}:
        if mutation == "runtime":
            verification["runtime"]["provider"] = "untrusted.provider.v1"
        else:
            verification["runtime"]["environment"]["numpy"] = "untrusted.import.path"
        executions[workflow.VERIFY]["runtime"] = deepcopy(verification["runtime"])
        seal(executions[workflow.VERIFY])
    elif mutation == "candidate_dependency":
        ghost = deepcopy(candidate)
        ghost["result_id"] = new_identity("result")
        seal(ghost)
        verification["parameters"]["candidate"] = ghost
        payload["candidate_result_id"] = ghost["result_id"]
        payload["candidate_record_digest"] = ghost["record_digest"]
        executions[workflow.VERIFY]["parameters"] = deepcopy(verification["parameters"])
        seal(executions[workflow.VERIFY])
    seal(verification)
    write_json(directory / "workspace.json", workspace)
    receipt = deepcopy(payload)
    if mutation == "receipt":
        receipt["verification_id"] = new_identity("verification")
    write_json(directory / "verification.json", receipt)
    before = content(directory)
    with no_numerics(), patch("ciw.session.write_json") as writer:
        with pytest.raises(ValueError):
            workflow.inspect(directory)
        assert all(directory.resolve() not in Path(call.args[0]).resolve().parents
                   for call in writer.call_args_list)
    assert content(directory) == before


def test_bounded_reads_refuse_links_and_oversized_or_duplicate_json(tmp_path):
    file = tmp_path / "request.json"
    file.write_text('{}', encoding="utf-8")
    assert workflow.load_regular(file, max_bytes=2) == {}
    with pytest.raises(ValueError, match="budget"):
        workflow.load_regular(file, max_bytes=1)
    with patch.object(Path, "is_symlink", return_value=True):
        with pytest.raises(ValueError, match="symlink"):
            workflow.load_regular(file)
    file.write_text('{"key":1,"key":2}', encoding="utf-8")
    with pytest.raises(ValueError, match="[Dd]uplicate"):
        workflow.load_regular(file)


def test_coherent_resealed_numerical_forgery_needs_fresh_verification_to_refuse(archived, tmp_path):
    original, _ = archived
    directory = tmp_path / "forged"
    shutil.copytree(original, directory)
    workspace, results, executions = occurrences(directory)
    candidate, verification = (results[item] for item in workflow.OPERATIONS)
    candidate["data"]["days"][0]["et0_mm"] += 0.1
    seal(candidate["data"])
    seal(candidate)
    verification["parameters"]["candidate"] = deepcopy(candidate)
    payload = verification["data"]
    payload["candidate_record_digest"] = candidate["record_digest"]
    payload["report"]["candidate_digest"] = candidate["data"]["record_digest"]
    seal(payload["report"])
    seal(verification)
    executions[workflow.VERIFY]["parameters"] = deepcopy(verification["parameters"])
    seal(executions[workflow.VERIFY])
    write_json(directory / "workspace.json", workspace)
    write_json(directory / "verification.json", payload)
    before = content(directory)
    with no_numerics():
        assert workflow.inspect(directory)["status"] == "LOCAL"
    with pytest.raises(ValueError, match="differs"):
        workflow.verify_retained(directory)
    for export, filename in ((workflow.export_csv, "forged.csv"), (workflow.export_html, "forged.html")):
        path = tmp_path / filename
        with pytest.raises(ValueError, match="differs"):
            export(directory, path)
        assert not path.exists()
    assert content(directory) == before


def test_receipt_missing_or_additional_occurrence_refuses(archived, tmp_path):
    original, _ = archived
    directory = tmp_path / "missing"
    shutil.copytree(original, directory)
    (directory / "verification.json").unlink()
    with pytest.raises(ValueError, match="receipt"):
        workflow.inspect(directory)
    shutil.copyfile(original / "verification.json", directory / "verification.json")
    workspace = read_json(directory / "workspace.json")
    workspace["results"].append(deepcopy(workspace["results"][0]))
    write_json(directory / "workspace.json", workspace)
    with pytest.raises(ValueError, match="[Dd]uplic|mismatch"):
        workflow.inspect(directory)


def test_exports_are_fresh_gated_create_only_and_offline(archived, tmp_path):
    directory, inspected = archived
    before = content(directory)
    csv_path, html_path = tmp_path / "plan.csv", tmp_path / "report.html"
    receipt = workflow.export_csv(directory, csv_path)
    assert receipt["status"] == "exported" and receipt["source_result_id"] == inspected["result_id"]
    assert receipt["fresh_verification_id"] != inspected["verification_id"]
    with csv_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.reader(stream))
    assert len(rows) > 1 and "zone_id" in rows[0] and "day_index" in rows[0]
    report = workflow.export_html(directory, html_path)
    assert report["fresh_verification_id"] != receipt["fresh_verification_id"]
    markup = html_path.read_text(encoding="utf-8")
    assert inspected["evidence_id"] in markup and report["fresh_verification_id"] in markup
    assert "<script" not in markup.lower() and "https://" not in markup and "http://" not in markup
    assert "mm" in markup and "m3" in markup and "not_performed" in markup
    for export, path in ((workflow.export_csv, csv_path), (workflow.export_html, html_path)):
        saved = path.read_bytes()
        with pytest.raises(FileExistsError):
            export(directory, path)
        assert path.read_bytes() == saved
    assert content(directory) == before
