"""Independent adversarial audit of atmosphere handoffs and retained Sessions."""
from contextlib import ExitStack
from copy import deepcopy
import csv
import shutil
from unittest.mock import patch

import pytest

from ciw import atmosphere_workflow as workflow
from ciw.atmosphere_contract import FRAME, example_request
from ciw.core.identities import evidence_id, new_identity
from ciw.operations.registry import default_registry
from ciw.operations.runner import check_seal, seal
from ciw.session import Session, read_json, write_json


@pytest.fixture(scope="module")
def retained_atmosphere(tmp_path_factory):
    directory = tmp_path_factory.mktemp("atmosphere-audit") / "column"
    return directory, workflow.run(example_request(), directory)


@pytest.fixture(scope="module")
def alternate_atmosphere(tmp_path_factory):
    request = example_request()
    request["reference"]["temperature_k"] = 300.0
    request["profile"]["wind_enu_m_per_s"] = [12.0, -5.0, 1.0]
    directory = tmp_path_factory.mktemp("atmosphere-audit-alternate") / "column"
    return directory, workflow.run(request, directory)


def _contents(directory):
    return {path.relative_to(directory): path.read_bytes()
            for path in directory.rglob("*") if path.is_file()}


def _clone(tmp_path, retained_atmosphere):
    original, inspected = retained_atmosphere
    directory = tmp_path / "column"
    shutil.copytree(original, directory)
    return directory, inspected


def _occurrences(directory):
    workspace = read_json(directory / "workspace.json")
    results = {row["operation_id"]: row for row in workspace["results"]}
    executions = {row["operation_id"]: row for row in workspace["executions"]}
    return workspace, results, executions


def _no_providers(*, verifier=True, operations=True):
    stack = ExitStack()
    stack.enter_context(patch("ciw.atmosphere_compiler.compile_atmosphere",
                              side_effect=AssertionError("atmosphere compiler replay")))
    if verifier:
        stack.enter_context(patch("ciw.atmosphere_verification.verify",
                                  side_effect=AssertionError("atmosphere verifier replay")))
    if operations:
        stack.enter_context(patch("ciw.session.execute_operation",
                                  side_effect=AssertionError("operation replay")))
    return stack


def test_atmosphere_operations_are_explicit_and_do_not_mutate_impact_or_default_registry():
    from ciw import impact_workflow
    assert {row["operation_id"] for row in default_registry().describe()} == {
        "statistics.v1", "spectrum.periodogram.v1"}
    described = {row["operation_id"]: row["role"] for row in workflow.registry().describe()}
    assert described[workflow.COMPILE] == "backend"
    assert described[workflow.VERIFY] == "verification"
    assert {workflow.COMPILE, workflow.VERIFY}.isdisjoint(
        row["operation_id"] for row in impact_workflow.registry().describe())


@pytest.mark.parametrize("profile", ["elastic", "crush", "plate"])
@pytest.mark.parametrize("phase", ["backend", "verification"])
@pytest.mark.parametrize("direction", ["atmosphere_to_impact", "impact_to_atmosphere"])
def test_cross_domain_operations_refuse_before_entering_either_numerical_provider(
        tmp_path, profile, phase, direction):
    from ciw import impact_workflow
    from ciw.impact_contract import example_request as elastic_request
    from ciw.impact_crush_contract import example_request as crush_request
    from ciw.impact_plate_contract import example_request as plate_request
    factories = {"elastic": elastic_request, "crush": crush_request, "plate": plate_request}
    impact_ids = {"elastic": (impact_workflow.SIMULATE, impact_workflow.VERIFY),
                  "crush": (impact_workflow.CRUSH_SIMULATE, impact_workflow.CRUSH_VERIFY),
                  "plate": (impact_workflow.PLATE_SIMULATE, impact_workflow.PLATE_VERIFY)}
    if direction == "atmosphere_to_impact":
        source = workflow.make_source(example_request())
        operation = impact_ids[profile][phase == "verification"]
    else:
        source = impact_workflow.make_source(factories[profile]())
        operation = (workflow.COMPILE, workflow.VERIFY)[phase == "verification"]
    # Register both fixed installed domains explicitly; input data never does so.
    registry = workflow.registry()
    for installed in impact_workflow.operations():
        registry.register(installed)
    session = Session(source, tmp_path / "session", operations=registry)
    with ExitStack() as stack:
        stack.enter_context(_no_providers(verifier=True, operations=False))
        for namespace in ("impact", "impact_crush", "impact_plate"):
            stack.enter_context(patch(f"ciw.{namespace}_solver.simulate",
                                      side_effect=AssertionError("impact solver entered")))
            stack.enter_context(patch(f"ciw.{namespace}_verification.verify",
                                      side_effect=AssertionError("impact verifier entered")))
        refused = workflow._execute(session, operation, {})
        assert refused["status"] == "refused"
        assert refused["execution"]["refusal"]["code"] == "invalid_operation"
        assert not session.results and len(session.executions) == 1
        session.save_workspace(tmp_path / "refused.json")
        restored = Session.from_workspace(tmp_path / "refused.json", tmp_path / "restored")
    assert not restored.results and len(restored.executions) == 1


def test_atmosphere_source_declares_one_configuration_sample_without_relabeling_height_as_time():
    request = example_request()
    with _no_providers():
        source = workflow.make_source(request)
        assert workflow.source_request(source) == request
    assert source["time_s"] == [0.0]
    assert source["metadata"]["sample_count"] == 1
    assert source["metadata"]["coordinate_frame"] == FRAME
    assert source["metadata"]["duration_s"] == 1.0
    assert source["metadata"]["manifest"]["role"] == "synthetic_reference_configuration"
    assert source["metadata"]["manifest"]["supported_operations"] == [workflow.COMPILE, workflow.VERIFY]
    assert not {"density", "sound_speed", "viscosity", "pressure_profile"} & set(source["channels"])
    assert all(len(channel["values"]) == 1 for channel in source["channels"].values())


@pytest.mark.parametrize("mutation", ["origin", "wind", "source", "time", "temperature"])
def test_external_input_and_context_changes_bind_new_evidence_identity(mutation):
    request = example_request()
    original = workflow.make_source(request)
    if mutation == "origin":
        request["reference"]["height_origin_m"] = 1500.0
    elif mutation == "wind":
        request["profile"]["wind_enu_m_per_s"] = [8.0, -4.0, 1.0]
    elif mutation == "source":
        request["reference"]["context"]["source_ref"] = "declared.boundary.observation"
        request["reference"]["context"]["source_kind"] = "declared_environment"
    elif mutation == "time":
        request["reference"]["context"]["valid_time_utc"] = "2026-10-03T06:00:00Z"
    else:
        request["reference"]["temperature_k"] = 300.0
    changed = workflow.make_source(request)
    assert changed["evidence_id"] != original["evidence_id"]
    assert changed["run_id"] != original["run_id"]
    assert workflow.source_request(changed) == request


@pytest.mark.parametrize("mutation", ["channel", "unit", "instrument", "extra"])
def test_reidentified_source_cannot_override_exact_configuration_declaration(mutation):
    source = workflow.make_source(example_request())
    name = next(iter(source["channels"]))
    if mutation == "channel":
        source["channels"][name]["values"][0] = 2.0
    elif mutation == "unit":
        source["channels"][name]["unit"] = "mm"
        source["metadata"]["manifest"]["units"][name] = "mm"
    elif mutation == "instrument":
        source["instrument"] = "fabricated-atmosphere-observations.v1"
    else:
        source["channels"]["measured_material_temperature"] = {"unit": "K", "values": [288.15]}
    source["evidence_id"] = evidence_id(source)
    with pytest.raises(ValueError):
        workflow.source_request(source)


def test_inspect_and_reopen_never_replay_compiler_verifier_or_operations(tmp_path, retained_atmosphere):
    directory, original = retained_atmosphere
    before = _contents(directory)
    with _no_providers():
        assert workflow.inspect(directory) == original
        restored = Session.from_workspace(directory / "workspace.json", tmp_path / "reopened")
    assert len(restored.executions) == len(restored.results) == 2
    assert _contents(directory) == before
    assert {workflow.COMPILE, workflow.VERIFY}.isdisjoint(
        row["operation_id"] for row in restored.operations.describe())


def test_verification_and_csv_keep_retained_occurrence_ids_without_new_execution(tmp_path, retained_atmosphere):
    directory, original = retained_atmosphere
    before = _contents(directory)
    output = tmp_path / "column.csv"
    with _no_providers(verifier=False):
        checked = workflow.verify_retained(directory)
        exported = workflow.export_csv(directory, output)
    assert checked["status"] == "LOCAL"
    assert checked["fresh_numerical_verification"] is True
    assert checked["fresh_execution"] is False
    assert _contents(directory) == before
    for key in ("evidence_id", "result_id", "execution_id", "verification_id"):
        assert checked[key] == original[key]
    assert exported["source_result_id"] == original["result_id"]
    assert exported["source_execution_id"] == original["execution_id"]
    rows = list(csv.reader(output.read_text(encoding="utf-8").splitlines()))
    assert len(rows) == len(example_request()["sampling"]["height_m"]) + 1
    assert all(len(row) == len(rows[0]) for row in rows)
    with pytest.raises(FileExistsError):
        workflow.export_csv(directory, output)


@pytest.mark.parametrize("command", ["verify", "csv", "handoff"])
def test_fresh_commands_consume_one_frozen_retained_snapshot(tmp_path, retained_atmosphere,
                                                           alternate_atmosphere, command):
    directory, _ = retained_atmosphere
    first = workflow._read(directory)
    second = workflow._read(alternate_atmosphere[0])
    with patch.object(workflow, "_read", side_effect=[first, second]) as read:
        if command == "verify":
            checked = workflow.verify_retained(directory)
            assert checked["evidence_id"] == first[0].run["evidence_id"]
            assert checked["result_id"] == first[1]["result_id"]
            assert checked["recomputed_report_digest"] == first[2]["data"]["report"]["record_digest"]
        elif command == "csv":
            output = tmp_path / "snapshot.csv"
            exported = workflow.export_csv(directory, output)
            assert exported["source_result_id"] == first[1]["result_id"]
            header, *rows = list(csv.reader(output.read_text(encoding="utf-8").splitlines()))
            index = header.index("temperature_k")
            assert float(rows[0][index]) == first[1]["data"]["profile"]["temperature_k"][0]
            assert float(rows[0][index]) != second[1]["data"]["profile"]["temperature_k"][0]
        else:
            output = tmp_path / "snapshot.json"
            workflow.export_handoff(directory, output, sample_index=0, provider="impact")
            payload = read_json(output)
            assert payload["source_evidence_id"] == first[0].run["evidence_id"]
            assert payload["source_result_id"] == first[1]["result_id"]
            assert payload["source_record_digest"] == first[1]["record_digest"]
            assert payload["verification_id"] == first[2]["data"]["verification_id"]
            assert payload["recomputed_report_digest"] == first[2]["data"]["report"]["record_digest"]
            assert payload["environment"]["temperature_k"] == first[1]["data"]["profile"]["temperature_k"][0]
            assert payload["environment"]["temperature_k"] != second[1]["data"]["profile"]["temperature_k"][0]
        assert read.call_count == 1


@pytest.mark.parametrize("artifact", ["verification.json", "preservation.json"])
def test_refused_provider_cannot_acquire_completed_receipts(tmp_path, artifact):
    directory = tmp_path / "refused"
    with patch("ciw.atmosphere_compiler.compile_atmosphere", side_effect=RuntimeError("private-detail")):
        inspected = workflow.run(example_request(), directory)
    assert inspected["status"] == "REFUSE"
    workspace = read_json(directory / "workspace.json")
    assert workspace["results"] == []
    execution, = workspace["executions"]
    assert execution["status"] == "refused" and execution["result_id"] is None
    assert "private-detail" not in execution["refusal"]["message"]
    check_seal(execution)
    write_json(directory / artifact, {"schema": "fabricated-receipt.v1"})
    before = _contents(directory)
    with _no_providers(), pytest.raises(ValueError):
        workflow.inspect(directory)
    assert _contents(directory) == before


@pytest.mark.parametrize("observable", ["weather_forecast", "fluid_dynamics", "material_conditioning"])
def test_requested_richer_physics_expands_and_blocks_csv(tmp_path, observable):
    request = example_request()
    request["desired_observables"].append(observable)
    directory = tmp_path / observable
    inspected = workflow.run(request, directory)
    assert inspected["status"] == "EXPAND"
    assert all(row["status"] == "PASS" for row in inspected["checks"])
    assert inspected["authority"]["physical_validation"] == "not_established"
    assert inspected["authority"]["state_admission"] == "not_performed"
    output = tmp_path / (observable + ".csv")
    with pytest.raises(ValueError):
        workflow.export_csv(directory, output)
    assert not output.exists()


def test_detached_candidate_snapshot_cannot_replace_retained_compiler_occurrence(tmp_path, retained_atmosphere):
    directory, _ = _clone(tmp_path, retained_atmosphere)
    workspace, results, executions = _occurrences(directory)
    verification = results[workflow.VERIFY]
    detached = deepcopy(results[workflow.COMPILE])
    detached["result_id"] = new_identity("result")
    detached["execution_id"] = new_identity("execution")
    seal(detached)
    verification["parameters"]["candidate"] = detached
    verification["data"].update(candidate_result_id=detached["result_id"],
                                candidate_execution_id=detached["execution_id"],
                                candidate_record_digest=detached["record_digest"])
    executions[workflow.VERIFY]["parameters"] = deepcopy(verification["parameters"])
    seal(verification)
    seal(executions[workflow.VERIFY])
    write_json(directory / "workspace.json", workspace)
    write_json(directory / "verification.json", verification["data"])
    before = _contents(directory)
    with _no_providers(), pytest.raises(ValueError):
        workflow.inspect(directory)
    assert _contents(directory) == before


def test_duplicate_scientific_verification_identity_is_rejected_by_session_dependency_check(
        tmp_path, retained_atmosphere):
    directory, _ = _clone(tmp_path, retained_atmosphere)
    workspace, results, executions = _occurrences(directory)
    duplicated = deepcopy(results[workflow.VERIFY])
    duplicate_execution = deepcopy(executions[workflow.VERIFY])
    duplicated["result_id"] = new_identity("result")
    duplicated["execution_id"] = new_identity("execution")
    duplicate_execution["execution_id"] = duplicated["execution_id"]
    duplicate_execution["result_id"] = duplicated["result_id"]
    seal(duplicated)
    seal(duplicate_execution)
    workspace["results"].append(duplicated)
    workspace["executions"].append(duplicate_execution)
    write_json(directory / "workspace.json", workspace)
    before = _contents(directory)
    with _no_providers(), pytest.raises(ValueError, match="Duplicate atmosphere verification"):
        Session.from_workspace(directory / "workspace.json", tmp_path / "reopened")
    assert _contents(directory) == before


@pytest.mark.parametrize("field,value", [("schema", "importlib.ciw.weather"),
                                         ("scope", "global_weather_forecast")])
def test_unknown_provider_scope_refuses_before_creating_destination(tmp_path, field, value):
    request = example_request()
    request[field] = value
    directory = tmp_path / "invalid"
    with _no_providers(), pytest.raises(ValueError):
        workflow.run(request, directory)
    assert not directory.exists()


@pytest.mark.parametrize("provider", ["impact", "fluid", "render"])
def test_handoff_is_exact_external_boundary_and_never_material_or_receiver_validation(
        tmp_path, retained_atmosphere, provider):
    directory, original = retained_atmosphere
    before = _contents(directory)
    output = tmp_path / (provider + ".json")
    with _no_providers(verifier=False):
        exported = workflow.export_handoff(directory, output, sample_index=3, provider=provider)
    payload = read_json(output)
    check_seal(payload)
    assert _contents(directory) == before
    assert exported["source_result_id"] == payload["source_result_id"] == original["result_id"]
    assert payload["source_execution_id"] == original["execution_id"]
    assert payload["sample_index"] == 3 and payload["height_m"] == 3000.0
    assert payload["absolute_height_m"] == payload["reference_height_origin_m"] + payload["height_m"]
    assert payload["frame"] == FRAME
    assert payload["context"] == example_request()["reference"]["context"]
    assert payload["environment"]["temperature_k"] == 268.65
    for claim in ("physical_validation_established", "receiver_model_validated",
                  "material_conditioning_established", "forces_computed", "visual_scattering_established",
                  "canonical_state_mutated", "state_admission_performed", "execution_authority"):
        assert payload["claims"][claim] is False
    assert payload["claims"]["data_only_environmental_boundary"] is True
    assert "material_temperature" not in payload["environment"]
    assert "material_conditioning" not in payload["environment"]
    effects = {row["property"]: row["effect"] for row in payload["effects"]}
    assert effects["material_temperature"] == effects["material_conditioning"] == "FORGET"
    assert effects["weather_evolution"] == effects["fluid_dynamics"] == "FORGET"
    assert payload["receiver_requirements"]


@pytest.mark.parametrize("mutation", ["height_bool", "wind_bool", "authority_number", "preserve_number"])
def test_resealed_handoff_rejects_boolean_numeric_aliases(tmp_path, retained_atmosphere, mutation):
    from ciw.atmosphere_handoff import BINDING_KEYS, validate_handoff
    directory, _ = retained_atmosphere
    output = tmp_path / "boundary.json"
    workflow.export_handoff(directory, output, sample_index=0, provider="impact")
    payload = read_json(output)
    _, candidate, _ = workflow._read(directory)
    bindings = {name: payload[name] for name in BINDING_KEYS}
    if mutation == "height_bool":
        payload["height_m"] = False
    elif mutation == "wind_bool":
        payload["environment"]["wind_enu_m_per_s"][0] = False
    elif mutation == "authority_number":
        payload["claims"]["execution_authority"] = 0
    else:
        payload["claims"]["exact_retained_sample"] = 1
    seal(payload)
    with _no_providers(), pytest.raises(ValueError):
        validate_handoff(example_request(), candidate["data"], payload, bindings)


@pytest.mark.parametrize("sample_index,provider", [(True, "impact"), (-1, "impact"),
                                                   (129, "impact"), (0, "importlib.weather")])
def test_invalid_handoff_selector_rejects_before_fresh_provider_or_output(
        tmp_path, retained_atmosphere, sample_index, provider):
    output = tmp_path / "invalid.json"
    with _no_providers(), pytest.raises(ValueError):
        workflow.export_handoff(retained_atmosphere[0], output, sample_index=sample_index, provider=provider)
    assert not output.exists()


def test_coherent_forged_scientific_report_needs_fresh_verification_before_export(tmp_path, retained_atmosphere):
    from ciw.atmosphere_preservation import build
    directory, original = _clone(tmp_path, retained_atmosphere)
    workspace, results, executions = _occurrences(directory)
    candidate, verification = results[workflow.COMPILE], results[workflow.VERIFY]
    # A small interior change preserves array bounds, extrema and terminal values.
    candidate["data"]["profile"]["density_kg_per_m3"][1] *= 1.001
    seal(candidate["data"])
    seal(candidate)
    payload = verification["data"]
    report = payload["report"]
    report["candidate_digest"] = candidate["data"]["record_digest"]
    seal(report)
    verification["parameters"]["candidate"] = deepcopy(candidate)
    payload["candidate_record_digest"] = candidate["record_digest"]
    executions[workflow.VERIFY]["parameters"] = deepcopy(verification["parameters"])
    seal(verification)
    seal(executions[workflow.VERIFY])
    write_json(directory / "workspace.json", workspace)
    write_json(directory / "verification.json", payload)
    write_json(directory / "preservation.json", build(example_request(), candidate["data"], report))
    before = _contents(directory)
    with _no_providers():
        inspected = workflow.inspect(directory)
    assert inspected["status"] == "LOCAL" and inspected["result_id"] == original["result_id"]
    with _no_providers(verifier=False), pytest.raises(ValueError, match="recomputation differs"):
        workflow.verify_retained(directory)
    for name, export in (("forged.csv", lambda out: workflow.export_csv(directory, out)),
                         ("forged.json", lambda out: workflow.export_handoff(directory, out, sample_index=1, provider="impact"))):
        output = tmp_path / name
        with pytest.raises(ValueError, match="recomputation differs"):
            export(output)
        assert not output.exists()
    assert _contents(directory) == before
