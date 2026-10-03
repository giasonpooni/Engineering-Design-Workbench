"""Fluid extends Session with explicit synthetic scope and read-only qualification."""
from contextlib import ExitStack
from copy import deepcopy
import csv
import math
from pathlib import Path
import shutil
from unittest.mock import patch

import pytest

from ciw import fluid_contract as contract, fluid_preservation, fluid_workflow as workflow
from ciw.core.identities import evidence_id, new_identity, validate_identity
from ciw.operations.registry import default_registry
from ciw.operations.runner import check_seal, digest, seal
from ciw.session import Session, read_json, write_json


def small_request(profile="reservoir"):
    request = contract.example_request(profile)
    if profile == "reservoir":
        request["clock"]["duration_s"] = 0.4
        request["clock"]["coarse_step_count"] = 32
    else:
        from ciw.fluid_wave_contract import wave_speed_m_per_s
        request["integration"]["cells"] = request["integration"]["steps"] = 32
        request["integration"]["duration_s"] = 0.1 * request["model"]["length_m"] / wave_speed_m_per_s(request["model"])
        for name in ("analytic_normalized", "wave_speed_relative", "spatial_refinement_normalized"):
            request["tolerances"][name] = 0.03
    return request


@pytest.fixture(scope="module", params=contract.PROFILES)
def archived(request, tmp_path_factory):
    profile = request.param
    directory = tmp_path_factory.mktemp("fluid-" + profile) / "run"
    inspected = workflow.run(small_request(profile), directory)
    assert inspected["status"] == "LOCAL"
    return profile, directory, inspected


def occurrences(directory):
    workspace = read_json(directory / "workspace.json")
    results = {row["operation_id"]: row for row in workspace["results"]}
    executions = {row["operation_id"]: row for row in workspace["executions"]}
    return workspace, results, executions


def content(directory):
    return {path.relative_to(directory): path.read_bytes() for path in directory.rglob("*") if path.is_file()}


def no_numerics(*, execute=False):
    stack = ExitStack()
    for profile in contract.PROFILES:
        for module, name in (("solver", "simulate"), ("verification", "verify"), ("reference", "reference")):
            stack.enter_context(patch("ciw.fluid_" + profile + "_" + module + "." + name,
                                      side_effect=AssertionError("Numerical replay")))
    if not execute:
        stack.enter_context(patch("ciw.session.execute_operation", side_effect=AssertionError("Operation replay")))
    return stack


@pytest.mark.parametrize("profile", contract.PROFILES)
def test_exact_declaration_evidence_has_no_computed_trajectory_or_acquisition(profile):
    request = small_request(profile)
    with no_numerics():
        source = workflow.make_source(request)
        assert workflow.source_request(source) == request
    assert source["evidence_id"] == evidence_id(source)
    assert source["time_s"] == [0.0] and source["metadata"]["sample_count"] == 1
    assert source["channels"] == {"configuration_declaration": {"unit": "1", "values": [0.0]}}
    assert source["metadata"]["manifest"]["role"] == "synthetic_model_configuration"
    assert source["metadata"]["manifest"]["supported_operations"] == list(contract.OPERATIONS[profile])
    detached = workflow.source_request(source)
    detached["desired_observables"].clear()
    assert source["metadata"]["fluid_request"]["desired_observables"]
    source["channels"]["configuration_declaration"]["values"][0] = 1.0
    source["evidence_id"] = evidence_id(source)
    with pytest.raises(ValueError, match="exact"):
        workflow.source_request(source)


@pytest.mark.parametrize("operation", [item for pair in contract.OPERATIONS.values() for item in pair])
def test_default_registry_refuses_every_fluid_operation_without_execution(tmp_path, operation):
    profile, _ = contract.profile_for_operation(operation)
    assert all(row["operation_id"] != operation for row in default_registry().describe())
    session = Session(workflow.make_source(small_request(profile)), tmp_path / operation)
    with no_numerics(execute=True):
        reply = workflow._execute(session, operation, {})
    assert reply["status"] == "refused" and reply["execution"]["runtime"] is None
    assert reply["execution"]["refusal"]["code"] == "operation_unavailable"
    assert len(session.executions) == 1 and not session.results


def test_retained_occurrences_are_distinct_and_dependency_bound(archived):
    profile, directory, inspected = archived
    workspace, results, executions = occurrences(directory)
    simulation, verify = contract.OPERATIONS[profile]
    assert workspace["workspace_version"] == 2
    assert set(results) == set(executions) == {simulation, verify}
    candidate, verification = results[simulation], results[verify]
    assert candidate["evidence_id"] == verification["evidence_id"] == inspected["evidence_id"]
    assert candidate["execution_id"] != verification["execution_id"]
    assert candidate["result_id"] != verification["result_id"]
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
    assert inspected["authority"] == workflow.AUTHORITY


def test_static_reopen_inspect_and_preservation_do_not_execute_any_provider(archived, tmp_path):
    _, directory, inspected = archived
    before = content(directory)
    with no_numerics():
        assert workflow.inspect(directory) == inspected
        restored = Session.from_workspace(directory / "workspace.json", tmp_path / "reopened")
        payload = read_json(directory / "preservation.json")
        _, results, _ = occurrences(directory)
        profile = inspected["profile"]
        candidate, verification = (results[item] for item in contract.OPERATIONS[profile])
        fluid_preservation.validate(payload, read_json(directory / "request.json"), candidate["data"], verification["data"]["report"])
    assert len(restored.results) == len(restored.executions) == 2
    assert not inspected["fresh_execution"] and not inspected["fresh_numerical_verification"]
    assert content(directory) == before


def test_fresh_checks_create_new_independent_occurrence_and_retained_witness(archived):
    _, directory, inspected = archived
    before = content(directory)
    first, second = workflow.verify_retained(directory), workflow.verify_retained(directory)
    assert first["status"] == second["status"] == "LOCAL"
    assert first["fresh_execution"] and first["fresh_numerical_verification"]
    assert first["verification_id"] == second["verification_id"] == inspected["verification_id"]
    assert first["execution_id"] == second["execution_id"] == inspected["execution_id"]
    for name in ("fresh_verification_id", "fresh_verification_execution_id", "fresh_verification_result_id"):
        assert first[name] != second[name]
    witness = first["fresh_verification_record"]
    assert witness["verification_id"] == first["fresh_verification_id"]
    assert witness["candidate_execution_id"] == inspected["execution_id"]
    assert witness["candidate_result_id"] == inspected["result_id"]
    assert witness["report"]["record_digest"] == first["recomputed_report_digest"]
    check_seal(witness["report"])
    assert content(directory) == before


def test_csv_export_is_gated_create_only_and_uses_explicit_model_grid(archived, tmp_path):
    profile, directory, inspected = archived
    before = content(directory)
    output = tmp_path / "trace.csv"
    exported = workflow.export_csv(directory, output)
    assert exported["source_result_id"] == inspected["result_id"]
    assert exported["fresh_verification_id"] != inspected["verification_id"]
    with output.open(newline="") as stream:
        rows = list(csv.reader(stream))
    _, results, _ = occurrences(directory)
    data = results[contract.OPERATIONS[profile][0]]["data"]
    if profile == "reservoir":
        trace = data["resolutions"]["finer"]["trace"]
        assert rows[0] == list(trace)
        assert len(rows) == len(trace["time_s"]) + 1
        assert [float(value) for value in rows[1]] == [trace[name][0] for name in rows[0]]
    else:
        trace = data["primary"]
        assert len(rows) == (trace["steps"] + 1) * trace["cells"] + 1
        assert rows[0][:4] == ["time_s", "grid_index", "cell_x_m", "face_x_m"]
        assert float(rows[1][2]) == trace["cell_x_m"][0]
        assert float(rows[1][3]) == trace["face_x_m"][0]
    saved = output.read_bytes()
    with pytest.raises(FileExistsError):
        workflow.export_csv(directory, output)
    assert output.read_bytes() == saved and content(directory) == before


@pytest.mark.parametrize("profile,observable", [("reservoir", "molecular_transport"), ("wave", "resolved_vertical_velocity")])
def test_expansion_scope_blocks_export_even_when_numerics_pass(tmp_path, profile, observable):
    request = small_request(profile)
    request["desired_observables"].append(observable)
    directory = tmp_path / "expanded"
    checked = workflow.run(request, directory)
    assert checked["status"] == "EXPAND"
    assert all(row["status"] == "PASS" for row in checked["checks"])
    assert workflow.verify_retained(directory)["status"] == "EXPAND"
    with pytest.raises(ValueError, match="LOCAL"):
        workflow.export_csv(directory, tmp_path / "blocked.csv")
    assert not (tmp_path / "blocked.csv").exists()


def test_receipt_declares_lost_spatial_vertical_molecular_and_receiver_scope(archived):
    profile, directory, _ = archived
    receipt = read_json(directory / "preservation.json")
    assert receipt["claims"] == fluid_preservation.CLAIMS
    assert receipt["model_scope"]["particle_meaning"] == "none"
    assert "absent" in receipt["model_scope"]["vertical_detail"]
    assert "no molecular" in receipt["model_scope"]["molecular_scope"]
    omissions = {row["property_id"] for row in receipt["contract"]["effects"] if row["effect"] == "FORGET"}
    assert "fluid." + profile + ".resolved-vertical-velocity.v1" in omissions
    assert "fluid." + profile + ".molecular-identity.v1" in omissions
    assert receipt["admission_gate"]["decision"] == "ELIGIBLE"


@pytest.mark.parametrize("mutation", ["candidate_identity", "authority", "runtime", "numpy_version", "report_action", "candidate_dependency"])
def test_resealed_binding_tamper_refuses_before_reopen_writes(archived, tmp_path, mutation):
    profile, original, _ = archived
    directory = tmp_path / "tampered"
    shutil.copytree(original, directory)
    workspace, results, executions = occurrences(directory)
    simulation, verification_op = contract.OPERATIONS[profile]
    candidate, verification = results[simulation], results[verification_op]
    payload = verification["data"]
    if mutation == "candidate_identity":
        payload["candidate_result_id"] = new_identity("result")
    elif mutation == "authority":
        payload["authority"]["physical_validation"] = "established"
    elif mutation in {"runtime", "numpy_version"}:
        if mutation == "runtime":
            verification["runtime"]["provider"] = "untrusted.provider.v1"
        else:
            verification["runtime"]["environment"]["numpy"] = "untrusted.import.path"
        executions[verification_op]["runtime"] = deepcopy(verification["runtime"])
        seal(executions[verification_op])
    elif mutation == "report_action":
        payload["report"]["qualification"]["action"] = "REFUSE"
        seal(payload["report"])
    else:
        ghost = deepcopy(candidate)
        ghost["result_id"] = new_identity("result")
        seal(ghost)
        verification["parameters"]["candidate"] = ghost
        payload["candidate_result_id"] = ghost["result_id"]
        payload["candidate_record_digest"] = ghost["record_digest"]
        executions[verification_op]["parameters"] = deepcopy(verification["parameters"])
        seal(executions[verification_op])
    seal(verification)
    write_json(directory / "workspace.json", workspace)
    write_json(directory / "verification.json", payload)
    before = content(directory)
    with no_numerics(), patch("ciw.session.write_json") as writer:
        with pytest.raises(ValueError):
            workflow.inspect(directory)
        writer.assert_not_called()
    assert content(directory) == before


def test_coherent_forged_reference_can_be_structural_but_fresh_verification_refuses(tmp_path):
    directory = tmp_path / "forged"
    workflow.run(small_request(), directory)
    workspace, results, _ = occurrences(directory)
    candidate, verification = (results[item] for item in contract.OPERATIONS["reservoir"])
    report = verification["data"]["report"]
    report["reference"]["state"][1][0] += 1e-5
    seal(report)
    seal(verification)
    write_json(directory / "workspace.json", workspace)
    write_json(directory / "verification.json", verification["data"])
    write_json(directory / "preservation.json", fluid_preservation.build(
        read_json(directory / "request.json"), candidate["data"], report))
    with no_numerics():
        assert workflow.inspect(directory)["status"] == "LOCAL"
    with pytest.raises(ValueError, match="differs from retained"):
        workflow.verify_retained(directory)
    with pytest.raises(ValueError, match="differs from retained"):
        workflow.export_csv(directory, tmp_path / "forged.csv")
    assert not (tmp_path / "forged.csv").exists()


@pytest.mark.parametrize("profile,phase", [(profile, phase) for profile in contract.PROFILES for phase in ("solver", "verification")])
def test_failed_provider_is_a_reopenable_refusal_with_no_receipts(tmp_path, profile, phase):
    directory = tmp_path / "failed"
    method = "simulate" if phase == "solver" else "verify"
    with patch("ciw.fluid_" + profile + "_" + phase + "." + method, side_effect=RuntimeError("private detail")):
        refused = workflow.run(small_request(profile), directory)
    assert refused["status"] == "REFUSE"
    assert not (directory / "verification.json").exists() and not (directory / "preservation.json").exists()
    before = content(directory)
    with no_numerics():
        assert workflow.inspect(directory) == workflow.verify_retained(directory) == refused
        Session.from_workspace(directory / "workspace.json", tmp_path / "reopened")
    assert content(directory) == before
    execution = read_json(directory / "workspace.json")["executions"][-1]
    assert execution["refusal"]["code"] == "operation_failed"
    assert "private detail" not in execution["refusal"]["message"]


@pytest.mark.parametrize("name", ["workspace.json", "request.json", "verification.json", "preservation.json"])
def test_bounded_regular_bundle_reader_rejects_oversize_and_symlink_before_session(archived, tmp_path, name):
    _, original, _ = archived
    directory = tmp_path / "invalid"
    shutil.copytree(original, directory)
    target = directory / name
    limit = workflow.MAX_BUNDLE_FILE_BYTES if name == "workspace.json" else workflow.MAX_DECLARATION_FILE_BYTES
    with target.open("wb") as stream:
        stream.truncate(limit + 1)
    with patch.object(Session, "from_workspace", side_effect=AssertionError("unbounded Session read")):
        with pytest.raises(ValueError, match="budget"):
            workflow.inspect(directory)
    target.unlink()
    target.symlink_to(original / name)
    with patch.object(Session, "from_workspace", side_effect=AssertionError("link followed")):
        with pytest.raises(ValueError, match="symlink"):
            workflow.inspect(directory)


def test_other_domain_workspace_reopens_without_fluid_provider_activation(tmp_path):
    from ciw import atmosphere_workflow
    from ciw.atmosphere_contract import example_request
    directory = tmp_path / "atmosphere"
    assert atmosphere_workflow.run(example_request(), directory)["status"] == "LOCAL"
    with no_numerics():
        archived = Session.from_workspace(directory / "workspace.json", tmp_path / "reopened")
    assert all(not row["operation_id"].startswith("fluid.") for row in archived.results.values())


def test_critical_damping_retains_completed_candidate_and_refused_verifier(tmp_path):
    request = small_request()
    request["structure"]["enabled"] = False
    rho = request["fluid"]["density_kg_per_m3"]
    inertia = rho * request["connector"]["length_m"] / request["connector"]["area_m2"]
    stiffness = rho * 9.80665 * (1 / request["reservoirs"]["area1_m2"] + 1 / request["reservoirs"]["area2_m2"])
    request["connector"]["resistance_pa_s_per_m3"] = 2 * math.sqrt(inertia * stiffness)
    directory = tmp_path / "critical"
    refused = workflow.run(request, directory)
    assert refused["status"] == "REFUSE"
    workspace, results, executions = occurrences(directory)
    simulation, verification = contract.OPERATIONS["reservoir"]
    assert set(results) == {simulation}
    assert executions[simulation]["status"] == "completed"
    assert executions[verification]["status"] == "refused"
    assert "ill-conditioned or defective" in executions[verification]["refusal"]["message"]
    assert not (directory / "verification.json").exists() and not (directory / "preservation.json").exists()
    with no_numerics():
        assert workflow.inspect(directory) == workflow.verify_retained(directory) == refused
    with pytest.raises(ValueError, match="LOCAL"):
        workflow.export_csv(directory, tmp_path / "critical.csv")
    assert not (tmp_path / "critical.csv").exists()


def test_default_wave_full_large_retained_bundle_runs_verifies_and_exports(tmp_path):
    directory = tmp_path / "default-wave"
    inspected = workflow.run(contract.example_request("wave"), directory)
    assert inspected["status"] == "LOCAL"
    assert (directory / "workspace.json").stat().st_size > 8 * 1024 * 1024
    fresh = workflow.verify_retained(directory)
    assert fresh["status"] == "LOCAL" and fresh["fresh_numerical_verification"]
    exported = workflow.export_csv(directory, tmp_path / "wave.csv")
    assert exported["status"] == "exported"
