"""Retained finite-interface operations preserve evidence/occurrence separation."""
from copy import deepcopy
from pathlib import Path
import json
import shutil
from unittest.mock import patch
from contextlib import ExitStack

import pytest

from ciw import fluid_coupling as coupling,fluid_interface_workflow as workflow
from ciw.core.identities import evidence_id
from ciw.fluid_interface_cli import main as interface_main
from ciw.operations.registry import default_registry
from ciw.operations.runner import check_seal,seal
from ciw.session import Session,read_json,write_json


@pytest.fixture(scope="module")
def archive(tmp_path_factory):
    destination=tmp_path_factory.mktemp("interface")/"bundle"
    inspected=workflow.run(workflow.example_declaration(),destination)
    assert inspected["status"]=="LOCAL"
    return destination,inspected


def content(destination):
    return {p.relative_to(destination):p.read_bytes() for p in destination.rglob("*") if p.is_file()}


def records(destination):
    workspace=read_json(destination/"workspace.json")
    results={row["operation_id"]:row for row in workspace["results"]}
    executions={row["operation_id"]:row for row in workspace["executions"]}
    return workspace,results,executions


def test_source_is_exact_configuration_declaration_and_detached():
    declaration=workflow.example_declaration()
    with patch("ciw.fluid_coupling.transfer",side_effect=AssertionError("transfer replay")),patch("ciw.fluid_coupling.verify",side_effect=AssertionError("verify replay")):
        source=workflow.make_source(declaration)
        returned=workflow.source_request(source)
    assert returned==declaration and returned is not declaration
    assert source["time_s"]==[0.0]
    assert source["channels"]=={"configuration_declaration":{"unit":"1","values":[0.0]}}
    assert source["metadata"]["sample_count"]==1
    assert source["evidence_id"]==evidence_id(source)
    source["channels"]["configuration_declaration"]["values"][0]=1.0
    source["evidence_id"]=evidence_id(source)
    with pytest.raises(ValueError,match="exact"):workflow.source_request(source)


def test_declared_solver_refs_are_explicit_unqualified_provenance():
    declaration=workflow.example_declaration()
    declaration["source"].update(kind="declared_solver_output",fluid_result_ref="sha256:"+"a"*64,structural_result_ref="sha256:"+"b"*64)
    source=workflow.make_source(declaration)
    assert workflow.source_request(source)==declaration
    assert workflow.AUTHORITY["input_content_refs"]=="declared_only_not_authenticated_or_replayed"
    assert workflow.AUTHORITY["coupled_model_qualification"]=="not_established"
    declaration["source"]["fluid_result_ref"]=None
    with pytest.raises(ValueError):workflow.validate_declaration(declaration)


@pytest.mark.parametrize("kind",["observed","measured",True,[],None])
def test_input_acquisition_or_unknown_source_kind_is_refused(kind):
    declaration=workflow.example_declaration();declaration["source"]["kind"]=kind
    with pytest.raises(ValueError):workflow.validate_declaration(declaration)


def test_default_registry_keeps_transfer_disabled(tmp_path):
    assert all(row["operation_id"] not in workflow.OPERATIONS for row in default_registry().describe())
    session=Session(workflow.make_source(workflow.example_declaration()),tmp_path/"disabled")
    with patch("ciw.fluid_coupling.transfer",side_effect=AssertionError("unbound provider")):
        refused=workflow._execute(session,workflow.OPERATION_ID,{})
    assert refused["status"]=="refused"
    assert refused["execution"]["refusal"]["code"]=="operation_unavailable"
    assert not session.results


def test_retained_identities_are_distinct_and_inputs_not_measurements(archive):
    destination,inspected=archive
    _,results,executions=records(destination)
    candidate,verification=results[workflow.OPERATION_ID],results[workflow.VERIFY_OPERATION_ID]
    assert candidate["role"]=="backend" and verification["role"]=="verification"
    assert candidate["evidence_id"]==verification["evidence_id"]==inspected["evidence_id"]
    assert candidate["result_id"]!=verification["result_id"]
    assert candidate["execution_id"]!=verification["execution_id"]
    assert verification["parameters"]["candidate"]==candidate
    assert verification["data"]["candidate_record_digest"]==candidate["record_digest"]
    assert verification["data"]["verification_id"]!=candidate["result_id"]
    assert verification["data"]["authority"]==workflow.AUTHORITY
    assert verification["data"]["report"]["qualification"]["coupled_model_qualified"] is False
    for result in results.values():
        check_seal(result)
        workflow.validate_runtime(result["operation_id"],result["runtime"])


def test_static_inspection_and_reopen_activate_no_providers(archive,tmp_path):
    destination,inspected=archive;before=content(destination)
    with ExitStack() as disabled:
        for target in ("ciw.fluid_coupling.transfer","ciw.fluid_coupling.verify","ciw.session.execute_operation",
                       "numpy.linalg.eigvalsh","numpy.linalg.eigh","numpy.linalg.cholesky"):
            disabled.enter_context(patch(target,side_effect=AssertionError("provider or factorization replay")))
        assert workflow.inspect(destination)==inspected
        reopened=Session.from_workspace(destination/"workspace.json",tmp_path/"restored")
    assert len(reopened.results)==len(reopened.executions)==2
    assert not inspected["fresh_execution"]
    assert content(destination)==before


def test_active_run_still_refuses_indefinite_input_covariance_before_publication(tmp_path):
    declaration=workflow.example_declaration()
    covariance=declaration["interface_request"]["uncertainty"]["traction_covariance_pa2"]
    covariance[0][1]=covariance[1][0]=10.0
    destination=tmp_path/"indefinite"
    with pytest.raises(ValueError,match="positive semidefinite"):
        workflow.run(declaration,destination)
    assert not destination.exists()


def test_fresh_verifications_create_new_occurrences_without_archive_mutation(archive):
    destination,inspected=archive;before=content(destination)
    first,second=workflow.verify_retained(destination),workflow.verify_retained(destination)
    for checked in (first,second):
        assert checked["status"]=="LOCAL" and checked["fresh_execution"] and checked["fresh_numerical_verification"]
        assert checked["verification_id"]==inspected["verification_id"]
        assert checked["fresh_verification_record"]["candidate_result_id"]==inspected["result_id"]
        assert checked["fresh_verification_record"]["report"]["record_digest"]==inspected["report_digest"]
    for field in ("fresh_verification_id","fresh_verification_execution_id","fresh_verification_result_id"):
        assert first[field]!=second[field]
    assert content(destination)==before


def test_nonretained_candidate_is_refused_before_verifier_activation(tmp_path):
    session=Session(workflow.make_source(workflow.example_declaration()),tmp_path/"live",operations=workflow.registry())
    candidate=workflow._execute(session,workflow.OPERATION_ID,{})["result"]
    forged=deepcopy(candidate);forged["data"]["data"]["structural_power_w"]+=1;seal(forged["data"]);seal(forged)
    with patch("ciw.fluid_coupling.verify",side_effect=AssertionError("unretained verifier activation")):
        outcome=workflow._execute(session,workflow.VERIFY_OPERATION_ID,{"candidate":forged})
    assert outcome["status"]=="refused"
    assert "retained" in outcome["execution"]["refusal"]["message"]
    assert len(session.results)==1


def test_duplicate_verification_identity_dependency_and_authority_forgery_rejected(archive):
    destination,_=archive
    _,results,_=records(destination)
    candidate=results[workflow.OPERATION_ID];verification=results[workflow.VERIFY_OPERATION_ID]
    forged=deepcopy(verification);forged["parameters"]["candidate"]["data"]["data"]["structural_power_w"]+=1
    with pytest.raises(ValueError,match="retained"):workflow.validate_result_dependencies({candidate["result_id"]:candidate,forged["result_id"]:forged})
    payload=deepcopy(verification["data"]);payload["authority"]["coupled_model_qualification"]="established"
    with pytest.raises(ValueError,match="authority"):
        workflow.validate_payload(workflow.VERIFY_OPERATION_ID,payload,workflow.make_source(workflow.example_declaration()),verification["parameters"],{})


def test_coherent_resealed_physics_forgery_passes_static_but_fresh_verification_detects(archive,tmp_path):
    original,_=archive;destination=tmp_path/"forged";shutil.copytree(original,destination)
    workspace,results,executions=records(destination)
    candidate=results[workflow.OPERATION_ID];verification=results[workflow.VERIFY_OPERATION_ID]
    candidate["data"]["data"]["structural_forces_n"][0][1]+=1.0
    seal(candidate["data"]);seal(candidate)
    verification["parameters"]["candidate"]=deepcopy(candidate)
    verification["data"]["candidate_record_digest"]=candidate["record_digest"]
    report=verification["data"]["report"];report["result_digest"]=candidate["data"]["record_digest"]
    for row in report["checks"]:row["value"]=0.0;row["status"]="PASS"
    seal(report);seal(verification)
    executions[workflow.VERIFY_OPERATION_ID]["parameters"]["candidate"]=deepcopy(candidate)
    seal(executions[workflow.VERIFY_OPERATION_ID])
    write_json(destination/"workspace.json",workspace)
    write_json(destination/"verification.json",verification["data"])
    assert workflow.inspect(destination)["status"]=="LOCAL"
    with pytest.raises(ValueError,match="differs from retained report"):workflow.verify_retained(destination)


def test_regular_file_budget_and_create_only_publication(tmp_path,archive):
    path=tmp_path/"linked";path.symlink_to(archive[0]/"request.json")
    with pytest.raises(ValueError,match="regular"):workflow.load_regular(path)
    path=tmp_path/"too-large.json";path.write_text(" "+"0"*64)
    with pytest.raises(ValueError,match="budget"):workflow.load_regular(path,max_bytes=16)
    with pytest.raises(FileExistsError):workflow.run(workflow.example_declaration(),archive[0])


def test_cli_template_run_inspect_verify(tmp_path,capsys):
    request=tmp_path/"request.json";destination=tmp_path/"bundle"
    assert interface_main(["template","--output",str(request)])==0
    assert json.loads(capsys.readouterr().out)["status"]=="created"
    assert interface_main(["run","--request",str(request),"--output-dir",str(destination)])==0
    assert json.loads(capsys.readouterr().out)["status"]=="LOCAL"
    assert interface_main(["inspect",str(destination)])==0
    assert json.loads(capsys.readouterr().out)["fresh_execution"] is False
    witness=tmp_path/"fresh.json"
    assert interface_main(["verify",str(destination),"--output",str(witness)])==0
    assert json.loads(capsys.readouterr().out)["fresh_execution"] is True
    assert workflow.load_regular(witness)["fresh_numerical_verification"] is True
