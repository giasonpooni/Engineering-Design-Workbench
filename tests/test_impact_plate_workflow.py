"""Finite plate contact extends retained NET Sessions and keeps profile boundaries."""
from contextlib import ExitStack
from copy import deepcopy
import csv
import math
import shutil

import pytest

from ciw import impact_cli, impact_workflow as workflow
from ciw.core.identities import evidence_id, new_identity, validate_identity
from ciw.impact_contract import example_request as elastic_request
from ciw.impact_crush_contract import example_request as crush_request
from ciw.impact_crush_solver import simulate as crush_simulate
from ciw.impact_plate_contract import example_request
from ciw.operations.registry import default_registry
from ciw.operations.runner import check_seal, digest, seal
from ciw.session import Session, read_json, write_json
from unittest.mock import patch


def _bundle(tmp_path, request=None, name="plate"):
    directory = tmp_path / name
    return directory, workflow.run(example_request() if request is None else request, directory)


@pytest.fixture(scope="module")
def retained_plate(tmp_path_factory):
    """Share one immutable baseline; retained modal histories are substantial."""
    return _bundle(tmp_path_factory.mktemp("plate-workflow-baseline"))


@pytest.fixture(scope="module")
def alternate_plate(tmp_path_factory):
    request = example_request()
    request["model"]["initial_speed_m_per_s"] = 0.02
    return _bundle(tmp_path_factory.mktemp("plate-workflow-alternate"), request)


def _clone_bundle(tmp_path, retained_plate):
    original, inspected = retained_plate
    directory = tmp_path / "plate"
    shutil.copytree(original, directory)
    return directory, inspected


def _occurrences(directory):
    workspace = read_json(directory / "workspace.json")
    return (workspace,
            {item["operation_id"]: item for item in workspace["results"]},
            {item["operation_id"]: item for item in workspace["executions"]})


def _contents(directory):
    return {path.relative_to(directory): path.read_bytes()
            for path in directory.rglob("*") if path.is_file()}


def _no_numerical_providers(*, verification=True):
    stack = ExitStack()
    for profile in ("impact", "impact_crush", "impact_plate"):
        stack.enter_context(patch(f"ciw.{profile}_solver.simulate", side_effect=AssertionError("solver replay")))
        if verification:
            stack.enter_context(patch(f"ciw.{profile}_verification.verify", side_effect=AssertionError("verifier replay")))
    return stack


def _reseal_bundle(directory, workspace, results, executions):
    """Refresh content seals, preserving the obligation to validate dependencies."""
    candidate, verification = results[workflow.PLATE_SIMULATE], results[workflow.PLATE_VERIFY]
    seal(candidate["data"])
    seal(candidate)
    verification["parameters"]["candidate"] = deepcopy(candidate)
    executions[workflow.PLATE_VERIFY]["parameters"] = deepcopy(verification["parameters"])
    payload = verification["data"]
    payload["candidate_record_digest"] = candidate["record_digest"]
    seal(payload["report"])
    seal(verification)
    for execution in executions.values():
        seal(execution)
    write_json(directory / "workspace.json", workspace)
    write_json(directory / "verification.json", payload)


def test_crush_content_and_trace_identity_are_preserved_by_plate_extension():
    request = crush_request()
    source = workflow.make_source(request)
    assert source["evidence_id"] == "sha256:2a7524e7df34f0c751eab120b72507c481ad08d32f46a136d3751a1bea75195a"
    assert digest(source) == "sha256:6c1e15ad02a8a95afa7a5b7db6463f7dc8c5546a35fbda4310e5c16dc98a3867"
    assert crush_simulate(request)["record_digest"] == "sha256:8950b66d6941d9f808f9c6039eb0edd89e2df0bd8aa3dc528d7b992163528ae7"


def test_plate_operations_require_explicit_trusted_workload_registry():
    assert {row["operation_id"] for row in default_registry().describe()} == {
        "statistics.v1", "spectrum.periodogram.v1"}
    operations = {row["operation_id"]: row["role"] for row in workflow.registry().describe()}
    assert operations[workflow.PLATE_SIMULATE] == "backend"
    assert operations[workflow.PLATE_VERIFY] == "verification"


def test_plate_source_is_one_declared_initial_state_and_not_a_modal_trajectory():
    request = example_request()
    source = workflow.make_source(request)
    assert workflow.source_request(source) == request
    assert source["instrument"] == "impact-plate-initial-state.v1"
    assert source["time_s"] == [0.0]
    assert source["metadata"]["sample_count"] == 1
    assert source["metadata"]["manifest"]["supported_operations"] == [workflow.PLATE_SIMULATE, workflow.PLATE_VERIFY]
    assert source["metadata"]["manifest"]["role"] == "synthetic_initial_conditions"
    assert "not acquired measurements" in source["metadata"]["provenance"]["source"]
    for channel in source["channels"].values():
        assert len(channel["values"]) == 1
    units = {"compression": "m", "velocity": "m/s", "force": "N", "striker_displacement": "m",
             "plate_contact_displacement": "m", "plate_contact_velocity": "m/s"}
    assert source["metadata"]["manifest"]["units"] == units
    assert set(source["channels"]) == set(units)
    for name, unit in units.items():
        assert source["channels"][name] == {
            "unit": unit, "values": [request["model"]["initial_speed_m_per_s"] if name == "velocity" else 0.0]}


@pytest.mark.parametrize("field,value", [("thickness_m", 0.0025), ("patch_center_x_m", 0.08)])
def test_plate_geometry_and_contact_location_are_bound_into_source_identity(field, value):
    original = workflow.make_source(example_request())
    request = example_request()
    request["model"][field] = value
    changed = workflow.make_source(request)
    assert changed["evidence_id"] != original["evidence_id"]
    assert changed["run_id"] != original["run_id"]
    assert workflow.source_request(changed) == request
    assert changed["time_s"] == original["time_s"] == [0.0]


@pytest.mark.parametrize("mutation", ["speed", "unit", "instrument", "extra_channel"])
def test_reidentified_plate_initial_state_cannot_override_exact_source_declaration(mutation):
    source = workflow.make_source(example_request())
    if mutation == "speed":
        source["channels"]["velocity"]["values"][0] *= 2.0
    elif mutation == "unit":
        source["channels"]["velocity"]["unit"] = "mm/s"
        source["metadata"]["manifest"]["units"]["velocity"] = "mm/s"
    elif mutation == "instrument":
        source["instrument"] = "impact-initial-state.v1"
    else:
        source["channels"]["fabricated_mode"] = {"unit": "m", "values": [0.0]}
    source["evidence_id"] = evidence_id(source)
    with pytest.raises(ValueError):
        workflow.source_request(source)


@pytest.mark.parametrize("source_profile,target_profile", [
    ("elastic", "crush"), ("elastic", "plate"),
    ("crush", "elastic"), ("crush", "plate"),
    ("plate", "elastic"), ("plate", "crush"),
])
@pytest.mark.parametrize("phase", ["solver", "verifier"])
def test_all_cross_profile_operations_refuse_before_numerical_execution(tmp_path, source_profile, target_profile, phase):
    request = {"elastic": elastic_request, "crush": crush_request, "plate": example_request}[source_profile]()
    operations = {"elastic": (workflow.SIMULATE, workflow.VERIFY),
                  "crush": (workflow.CRUSH_SIMULATE, workflow.CRUSH_VERIFY),
                  "plate": (workflow.PLATE_SIMULATE, workflow.PLATE_VERIFY)}
    operation = operations[target_profile][phase == "verifier"]
    session = Session(workflow.make_source(request), tmp_path / "session", operations=workflow.registry())
    with _no_numerical_providers():
        refused = workflow._execute(session, operation, {})
        assert refused["status"] == "refused"
        assert refused["execution"]["refusal"]["code"] == "invalid_operation"
        assert "physical profile" in refused["execution"]["refusal"]["message"]
        assert not session.results and len(session.executions) == 1
        session.save_workspace(tmp_path / "refused.json")
        reopened = Session.from_workspace(tmp_path / "refused.json", tmp_path / "reopened")
    assert not reopened.results and len(reopened.executions) == 1
    check_seal(next(iter(reopened.executions.values())))


def test_plate_run_keeps_distinct_content_operation_execution_result_and_verification_ids(tmp_path):
    directory, inspected = _bundle(tmp_path)
    assert inspected["status"] == "LOCAL"
    workspace, results, executions = _occurrences(directory)
    assert workspace["workspace_version"] == 2
    assert set(results) == set(executions) == {workflow.PLATE_SIMULATE, workflow.PLATE_VERIFY}
    candidate, verification = results[workflow.PLATE_SIMULATE], results[workflow.PLATE_VERIFY]
    assert candidate["role"] == "backend" and verification["role"] == "verification"
    assert candidate["evidence_id"] == verification["evidence_id"] == inspected["evidence_id"]
    assert candidate["execution_id"] != verification["execution_id"]
    assert candidate["result_id"] != verification["result_id"]
    assert candidate["runtime"]["provider"] == "ciw.impact.plate-solver"
    assert verification["runtime"]["provider"] == "ciw.impact.plate-verifier"
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
        assert executions[result["operation_id"]]["result_id"] == result["result_id"]
        assert executions[result["operation_id"]]["status"] == "completed"
    _, second = _bundle(tmp_path, name="second")
    assert second["evidence_id"] == inspected["evidence_id"]
    for name in ("execution_id", "result_id", "verification_execution_id", "verification_id"):
        assert second[name] != inspected[name]


def test_plate_typed_receipts_bind_exact_retained_content_and_no_physical_or_continuum_authority(retained_plate):
    directory, inspected = retained_plate
    _, results, _ = _occurrences(directory)
    candidate = results[workflow.PLATE_SIMULATE]["data"]
    report = results[workflow.PLATE_VERIFY]["data"]["report"]
    bundle = read_json(directory / "preservation.json")
    assert bundle["schema"] == "ciw.impact-plate-preservation.v1"
    assert bundle["request_digest"] == digest(example_request())
    assert bundle["result_digest"] == candidate["record_digest"]
    assert bundle["report_digest"] == report["record_digest"]
    refs = inspected["preservation"]
    assert refs["contract_ref"] == bundle["contract"]["record_digest"]
    assert refs["verification_ref"] == bundle["verification"]["record_digest"]
    assert refs["verification_status"] == "VERIFIED" and refs["admission_eligibility"] == "ELIGIBLE"
    assert refs["state_admission_performed"] is False
    for claim in ("physical_validation_established", "continuum_convergence_established",
                  "three_dimensional_solid_response_established", "local_contact_pressure_established",
                  "total_striker_plate_momentum_conservation_established", "hardness_established",
                  "material_damage_established", "molecular_response_established", "scale_preservation_established",
                  "cross_scale_commutative_witness_supplied", "canonical_state_mutated", "state_admission_performed"):
        assert bundle["claims"][claim] is False


def test_plate_inspection_and_session_reopen_are_readonly_without_solver_verifier_or_eigensystem(tmp_path, retained_plate):
    directory, original = retained_plate
    before = _contents(directory)
    with _no_numerical_providers(), \
            patch("numpy.linalg.eigh", side_effect=AssertionError("eigensystem replay")), \
            patch("numpy.linalg.eig", side_effect=AssertionError("eigensystem replay")), \
            patch("ciw.session.execute_operation", side_effect=AssertionError("operation replay")):
        assert workflow.inspect(directory) == original
        reopened = Session.from_workspace(directory / "workspace.json", tmp_path / "reopened")
    assert len(reopened.results) == len(reopened.executions) == 2
    assert original["fresh_execution"] is False and original["fresh_numerical_verification"] is False
    assert _contents(directory) == before


def test_plate_verify_and_csv_export_reuse_occurrence_ids_and_never_replay_solver(tmp_path, retained_plate):
    directory, original = retained_plate
    before = _contents(directory)
    with _no_numerical_providers(verification=False):
        verified = workflow.verify_retained(directory)
        output = tmp_path / "plate.csv"
        exported = workflow.export_csv(directory, output)
    assert verified["status"] == "LOCAL" and verified["fresh_numerical_verification"] is True
    assert verified["execution_id"] == original["execution_id"]
    assert verified["verification_id"] == original["verification_id"]
    assert "new_verification_id" not in verified
    results = _occurrences(directory)[1]
    assert verified["recomputed_report_digest"] == results[workflow.PLATE_VERIFY]["data"]["report"]["record_digest"]
    assert verified["recomputed_with_runtime"]["provider"] == "ciw.impact.plate-verifier"
    assert exported["source_result_id"] == original["result_id"]
    assert exported["source_execution_id"] == original["execution_id"]
    names = ["time_s", "striker_displacement_m", "compression_m", "velocity_m_per_s", "force_n",
             "plate_contact_displacement_m", "plate_contact_velocity_m_per_s"]
    with output.open(newline="") as stream:
        rows = list(csv.reader(stream))
    assert rows[0] == names
    primary = results[workflow.PLATE_SIMULATE]["data"]["primary"]
    assert len(rows) == len(primary["time_s"]) + 1
    assert [[float(value) for value in row] for row in rows[1:]] == [list(row) for row in zip(*(primary[name] for name in names))]
    saved = output.read_bytes()
    with pytest.raises(FileExistsError):
        workflow.export_csv(directory, output)
    assert output.read_bytes() == saved
    with pytest.raises(FileExistsError):
        workflow.run(example_request(), directory)
    assert _contents(directory) == before


def test_plate_field_export_binds_geometry_time_samples_and_verification_without_new_execution(tmp_path, retained_plate):
    directory, original = retained_plate
    before = _contents(directory)
    _, results, _ = _occurrences(directory)
    candidate, verification = results[workflow.PLATE_SIMULATE], results[workflow.PLATE_VERIFY]
    trace = candidate["data"]["primary"]
    time_index = len(trace["time_s"]) // 4
    output = tmp_path / "field.json"
    with _no_numerical_providers(verification=False):
        exported = workflow.export_plate_field(directory, output, time_index=time_index)
    payload = read_json(output)
    check_seal(payload)
    assert payload["schema"] == "ciw.impact-plate-field.v1"
    assert exported["field_digest"] == payload["record_digest"]
    assert payload["request_digest"] == digest(example_request())
    assert payload["source_evidence_id"] == original["evidence_id"]
    assert payload["source_result_id"] == candidate["result_id"]
    assert payload["source_execution_id"] == candidate["execution_id"]
    assert payload["source_record_digest"] == candidate["record_digest"]
    assert payload["verification_id"] == original["verification_id"]
    assert payload["recomputed_report_digest"] == verification["data"]["report"]["record_digest"]
    assert payload["time_index"] == exported["time_index"] == time_index
    assert payload["time_s"] == exported["time_s"] == trace["time_s"][time_index]
    assert payload["modes"] == trace["modes"]
    assert payload["modal_displacement_m"] == [samples[time_index] for samples in trace["modal_displacement_m"]]
    assert payload["units"] == {"x_m": "m", "y_m": "m", "deflection_m": "m", "time_s": "s"}
    model = example_request()["model"]
    assert payload["geometry"] == {key: model[key] for key in ("length_x_m", "length_y_m", "thickness_m", "support")}
    assert payload["authority"] == workflow.AUTHORITY
    assert "stress" not in payload and "strain" not in payload and "damage" not in payload
    assert _contents(directory) == before
    saved = output.read_bytes()
    with pytest.raises(FileExistsError):
        workflow.export_plate_field(directory, output, time_index=time_index)
    assert output.read_bytes() == saved and _contents(directory) == before


def test_field_grid_has_exact_support_boundaries_and_discrete_sine_projection_recovers_retained_modes(tmp_path, retained_plate):
    directory, _ = retained_plate
    trace = _occurrences(directory)[1][workflow.PLATE_SIMULATE]["data"]["primary"]
    output = tmp_path / "field.json"
    index, grid_size = len(trace["time_s"]) // 4, 17
    workflow.export_plate_field(directory, output, time_index=index, grid_size=grid_size)
    field = read_json(output)
    assert field["x_m"][0] == field["y_m"][0] == 0.0
    assert field["x_m"][-1] == field["geometry"]["length_x_m"]
    assert field["y_m"][-1] == field["geometry"]["length_y_m"]
    assert len(field["x_m"]) == len(field["y_m"]) == len(field["deflection_m"]) == grid_size
    assert all(len(row) == grid_size for row in field["deflection_m"])
    assert field["deflection_m"][0] == field["deflection_m"][-1] == [0.0] * grid_size
    assert all(row[0] == row[-1] == 0.0 for row in field["deflection_m"])
    assert any(value != 0.0 for row in field["deflection_m"] for value in row)
    # Discrete sine orthogonality is independent of pointwise reconstruction:
    # it checks orientation, mode association and amplitudes over the whole grid.
    for mode_index, (m, n) in enumerate(trace["modes"]):
        projection = 4.0 / (grid_size - 1) ** 2 * sum(
            field["deflection_m"][j][i] * math.sin(m * math.pi * i / (grid_size - 1))
            * math.sin(n * math.pi * j / (grid_size - 1))
            for j in range(1, grid_size - 1) for i in range(1, grid_size - 1))
        assert projection == pytest.approx(trace["modal_displacement_m"][mode_index][index], rel=1e-12, abs=1e-16)


@pytest.mark.parametrize("time_index,grid_size", [
    (-1, 17), (True, 17), (0.0, 17), (100000, 17),
    (0, True), (0, 2), (0, 4), (0, 35), (0, 17.0),
])
def test_invalid_field_grid_or_time_never_creates_output_or_replays_scientific_verifier(tmp_path, retained_plate, time_index, grid_size):
    directory, _ = retained_plate
    output = tmp_path / "new-parent" / "field.json"
    before = _contents(directory)
    with _no_numerical_providers():
        with pytest.raises(ValueError):
            workflow.export_plate_field(directory, output, time_index=time_index, grid_size=grid_size)
    assert not output.exists() and not output.parent.exists()
    assert _contents(directory) == before


@pytest.mark.parametrize("request_factory", [elastic_request, crush_request])
def test_plate_field_export_cannot_reinterpret_another_contact_profile(tmp_path, request_factory):
    directory, _ = _bundle(tmp_path, request_factory())
    output = tmp_path / "wrong-profile.json"
    with _no_numerical_providers():
        with pytest.raises(ValueError, match="plate"):
            workflow.export_plate_field(directory, output, time_index=0)
    assert not output.exists()


@pytest.mark.parametrize("command", ["verify", "csv", "field"])
def test_fresh_verification_and_exports_use_one_frozen_retained_snapshot(tmp_path, retained_plate, alternate_plate, command):
    directory, original = retained_plate
    alternate_directory, alternate = alternate_plate
    assert original["status"] == alternate["status"] == "LOCAL"
    first, second = workflow._read(directory), workflow._read(alternate_directory)
    assert first[1]["result_id"] != second[1]["result_id"]
    assert first[0].run["evidence_id"] != second[0].run["evidence_id"]
    before = _contents(directory)
    with patch.object(workflow, "_read", side_effect=[first, second]) as reader, _no_numerical_providers(verification=False):
        if command == "verify":
            checked = workflow.verify_retained(directory)
            assert checked["result_id"] == first[1]["result_id"]
            assert checked["verification_id"] == first[2]["data"]["verification_id"]
            assert checked["recomputed_report_digest"] == first[2]["data"]["report"]["record_digest"]
            assert checked["fresh_numerical_verification"] is True
        elif command == "csv":
            output = tmp_path / "snapshot.csv"
            exported = workflow.export_csv(directory, output)
            assert exported["source_result_id"] == first[1]["result_id"]
            with output.open(newline="") as stream:
                rows = list(csv.reader(stream))
            assert float(rows[2][4]) == first[1]["data"]["primary"]["force_n"][1]
            assert float(rows[2][4]) != second[1]["data"]["primary"]["force_n"][1]
        else:
            output = tmp_path / "snapshot.json"
            workflow.export_plate_field(directory, output, time_index=10)
            payload = read_json(output)
            assert payload["source_evidence_id"] == first[0].run["evidence_id"]
            assert payload["source_result_id"] == first[1]["result_id"]
            assert payload["source_record_digest"] == first[1]["record_digest"]
            assert payload["verification_id"] == first[2]["data"]["verification_id"]
            assert payload["recomputed_report_digest"] == first[2]["data"]["report"]["record_digest"]
            assert payload["modal_displacement_m"] == [values[10] for values in first[1]["data"]["primary"]["modal_displacement_m"]]
        reader.assert_called_once_with(directory)
    assert _contents(directory) == before


@pytest.mark.parametrize("observable", ["damage", "rate_response", "thermal_response", "molecular_response"])
def test_plate_unsupported_observables_expand_and_block_every_export(tmp_path, observable):
    request = example_request()
    request["desired_observables"].append(observable)
    directory, inspected = _bundle(tmp_path, request)
    assert inspected["status"] == "EXPAND"
    assert inspected["qualification"]["unsupported_observables"] == [observable]
    _, results, executions = _occurrences(directory)
    assert results[workflow.PLATE_VERIFY]["data"]["report"]["status"] == "PASS"
    assert all(execution["status"] == "completed" for execution in executions.values())
    assert inspected["preservation"]["admission_eligibility"] == "REFUSED"
    assert workflow.verify_retained(directory)["status"] == "EXPAND"
    for suffix, export in (("csv", lambda output: workflow.export_csv(directory, output)),
                           ("json", lambda output: workflow.export_plate_field(directory, output, time_index=0))):
        output = tmp_path / ("unqualified." + suffix)
        with pytest.raises(ValueError, match="LOCAL"):
            export(output)
        assert not output.exists()


@pytest.mark.parametrize("phase", ["solver", "verifier"])
def test_plate_provider_failure_retains_reopenable_refused_occurrence(tmp_path, phase):
    target = "ciw.impact_plate_solver.simulate" if phase == "solver" else "ciw.impact_plate_verification.verify"
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
    with _no_numerical_providers():
        assert workflow.inspect(directory) == refused
        assert workflow.verify_retained(directory) == refused
        reopened = Session.from_workspace(directory / "workspace.json", tmp_path / "reopened")
    assert len(reopened.executions) == len(workspace["executions"])
    assert _contents(directory) == before


def test_plate_linear_regime_failure_retains_failed_completed_numerical_occurrences(tmp_path):
    request = example_request()
    request["model"]["initial_speed_m_per_s"] = 0.3
    directory, inspected = _bundle(tmp_path, request)
    assert inspected["status"] == "REFUSE"
    _, results, executions = _occurrences(directory)
    assert len(results) == len(executions) == 2
    assert all(execution["status"] == "completed" for execution in executions.values())
    report = results[workflow.PLATE_VERIFY]["data"]["report"]
    assert report["status"] == "FAIL"
    assert any(check["name"].endswith("small_deflection_ratio") and check["status"] == "FAIL"
               for check in report["checks"])
    assert inspected["preservation"]["verification_status"] == "REFUTED"
    assert inspected["preservation"]["admission_eligibility"] == "REFUSED"
    assert workflow.inspect(directory)["status"] == workflow.verify_retained(directory)["status"] == "REFUSE"
    output = tmp_path / "outside-linear-regime.json"
    with pytest.raises(ValueError, match="LOCAL"):
        workflow.export_plate_field(directory, output, time_index=0)
    assert not output.exists()


@pytest.mark.parametrize("field,value", [
    ("contact_law", "polymer_viscoplastic"), ("support", "clamped_plate"),
    ("damping_n_s_per_m", 1.0), ("gravity_during_contact_m_per_s2", 9.81),
    ("initial_compression_m", 0.001), ("poissons_ratio", 0.5),
    ("patch_center_x_m", 0.0), ("patch_width_x_m", 0.001),
    ("thickness_m", 0.05), ("young_modulus_pa", True),
])
def test_invalid_plate_physics_refuses_before_creating_directory(tmp_path, field, value):
    request = example_request()
    request["model"][field] = value
    directory = tmp_path / "unsupported"
    with pytest.raises(ValueError):
        workflow.run(request, directory)
    assert not directory.exists()


@pytest.mark.parametrize("field,value", [
    ("modes_per_axis", 5), ("modes_per_axis", True), ("steps_per_contact", 256),
    ("spatial_refinement_increment", 1), ("duration_factor", 3.0),
])
def test_invalid_plate_resolution_refuses_before_creating_directory(tmp_path, field, value):
    request = example_request()
    request["integration"][field] = value
    directory = tmp_path / "unsupported"
    with pytest.raises(ValueError):
        workflow.run(request, directory)
    assert not directory.exists()


@pytest.mark.parametrize("field,value", [("schema", "untrusted.python.module"), ("scope", "molecular_impact")])
def test_unknown_plate_schema_or_scope_cannot_load_code_or_create_directory(tmp_path, field, value):
    request = example_request()
    request[field] = value
    directory = tmp_path / "unsupported"
    with pytest.raises(ValueError):
        workflow.run(request, directory)
    assert not directory.exists()


@pytest.mark.parametrize("mutation", ["report_schema", "report_dependency", "verification_identity", "candidate_dependency"])
def test_resealed_plate_verification_semantic_tampering_is_rejected_readonly(tmp_path, retained_plate, mutation):
    directory, _ = _clone_bundle(tmp_path, retained_plate)
    workspace, results, executions = _occurrences(directory)
    payload = results[workflow.PLATE_VERIFY]["data"]
    if mutation == "report_schema":
        payload["report"]["schema"] = "ciw.impact-crush-verification.v1"
    elif mutation == "report_dependency":
        payload["report"]["result_digest"] = "sha256:" + "0" * 64
    elif mutation == "verification_identity":
        payload["verification_id"] = new_identity("execution")
    else:
        payload["candidate_result_id"] = new_identity("result")
    _reseal_bundle(directory, workspace, results, executions)
    before = _contents(directory)
    with patch("ciw.session.write_json") as writer, _no_numerical_providers():
        with pytest.raises(ValueError):
            workflow.inspect(directory)
        writer.assert_not_called()
    assert _contents(directory) == before


@pytest.mark.parametrize("field", ["modal_displacement_m", "modal_velocity_m_per_s"])
def test_resealed_modal_trace_tampering_cannot_cross_retained_verification_dependency(tmp_path, retained_plate, field):
    directory, _ = _clone_bundle(tmp_path, retained_plate)
    workspace, results, executions = _occurrences(directory)
    trace = results[workflow.PLATE_SIMULATE]["data"]["primary"]
    trace[field][0][len(trace["time_s"]) // 3] += 0.000001
    _reseal_bundle(directory, workspace, results, executions)
    before = _contents(directory)
    with pytest.raises(ValueError):
        workflow.inspect(directory)
    with pytest.raises(ValueError):
        workflow.verify_retained(directory)
    output = tmp_path / "tampered.json"
    with pytest.raises(ValueError):
        workflow.export_plate_field(directory, output, time_index=0)
    assert not output.exists() and _contents(directory) == before


def test_detached_plate_candidate_cannot_replace_retained_solver_occurrence(tmp_path, retained_plate):
    directory, _ = _clone_bundle(tmp_path, retained_plate)
    workspace, results, executions = _occurrences(directory)
    verification = results[workflow.PLATE_VERIFY]
    detached = deepcopy(results[workflow.PLATE_SIMULATE])
    detached["result_id"], detached["execution_id"] = new_identity("result"), new_identity("execution")
    seal(detached)
    verification["parameters"]["candidate"] = detached
    executions[workflow.PLATE_VERIFY]["parameters"] = deepcopy(verification["parameters"])
    verification["data"].update(candidate_result_id=detached["result_id"],
                                  candidate_execution_id=detached["execution_id"],
                                  candidate_record_digest=detached["record_digest"])
    seal(verification)
    seal(executions[workflow.PLATE_VERIFY])
    write_json(directory / "workspace.json", workspace)
    write_json(directory / "verification.json", verification["data"])
    with patch("ciw.session.write_json") as writer:
        with pytest.raises(ValueError, match="candidate|occurrence|depend"):
            Session.from_workspace(directory / "workspace.json", tmp_path / "rejected")
        writer.assert_not_called()
        with pytest.raises(ValueError, match="candidate|occurrence|depend"):
            workflow.inspect(directory)


def test_structurally_plausible_energy_report_needs_independent_recomputation_before_export(tmp_path, retained_plate):
    from ciw.impact_plate_preservation import build
    directory, _ = _clone_bundle(tmp_path, retained_plate)
    workspace, results, executions = _occurrences(directory)
    report = results[workflow.PLATE_VERIFY]["data"]["report"]
    assert report["metrics"]["primary"]["maximum_energy_relative_drift"] != 0.0001
    report["metrics"]["primary"]["maximum_energy_relative_drift"] = 0.0001
    check = next(check for check in report["checks"] if check["name"] == "primary.maximum_energy_drift")
    check["value"] = 0.0001
    _reseal_bundle(directory, workspace, results, executions)
    write_json(directory / "preservation.json", build(
        read_json(directory / "request.json"), results[workflow.PLATE_SIMULATE]["data"], report))
    before = _contents(directory)
    with _no_numerical_providers():
        assert workflow.inspect(directory)["status"] == "LOCAL"
    with pytest.raises(ValueError, match="recomputation"):
        workflow.verify_retained(directory)
    output = tmp_path / "fabricated-field.json"
    with pytest.raises(ValueError, match="recomputation"):
        workflow.export_plate_field(directory, output, time_index=0)
    assert not output.exists() and _contents(directory) == before


def test_plate_cli_example_run_inspect_verify_csv_and_field(tmp_path, capsys):
    request_path, directory = tmp_path / "request.json", tmp_path / "run"
    assert impact_cli.main(["plate", "example", "--output", str(request_path)]) == 0
    original = request_path.read_bytes()
    assert read_json(request_path) == example_request()
    assert impact_cli.main(["plate", "example", "--output", str(request_path)]) == 1
    assert request_path.read_bytes() == original
    assert impact_cli.main(["plate", "run", str(request_path), "--output-dir", str(directory)]) == 0
    assert impact_cli.main(["plate", "inspect", str(directory)]) == 0
    assert impact_cli.main(["plate", "verify", str(directory)]) == 0
    assert impact_cli.main(["plate", "export", str(directory), "--output", str(tmp_path / "plate.csv")]) == 0
    assert impact_cli.main(["plate", "field", str(directory), "--time-index", "0", "--output", str(tmp_path / "field.json")]) == 0
    assert '"status": "LOCAL"' in capsys.readouterr().out


@pytest.mark.parametrize("command_profile,request_profile", [
    ("elastic", "crush"), ("elastic", "plate"),
    ("crush", "elastic"), ("crush", "plate"),
    ("plate", "elastic"), ("plate", "crush"),
])
def test_cli_rejects_every_other_profile_before_creating_directory(tmp_path, command_profile, request_profile):
    request = {"elastic": elastic_request, "crush": crush_request, "plate": example_request}[request_profile]()
    request_path, directory = tmp_path / "request.json", tmp_path / "wrong-profile"
    write_json(request_path, request)
    prefix = [] if command_profile == "elastic" else [command_profile]
    assert impact_cli.main(prefix + ["run", str(request_path), "--output-dir", str(directory)]) == 1
    assert not directory.exists()
