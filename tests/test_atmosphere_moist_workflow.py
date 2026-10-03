"""Moist-air providers retain declarations and audit exports on the same substrate."""
from copy import deepcopy
import csv
import sys
from unittest.mock import patch

import pytest

from ciw import atmosphere_cli, atmosphere_workflow as workflow
from ciw.atmosphere_moist_contract import FRAME, STATE_FIELDS, example_request
from ciw.core.identities import evidence_id, new_identity, validate_identity
from ciw.operations.registry import default_registry
from ciw.operations.runner import check_seal, seal
from ciw.session import Session, read_json, write_json


def _bundle(tmp_path, request=None, name="moist"):
    directory = tmp_path / name
    reply = workflow.run(example_request() if request is None else request, directory)
    return directory, reply


def _occurrences(directory):
    workspace = read_json(directory / "workspace.json")
    return (workspace, {item["operation_id"]: item for item in workspace["results"]},
            {item["operation_id"]: item for item in workspace["executions"]})


def _contents(directory):
    return {path.relative_to(directory): path.read_bytes()
            for path in directory.rglob("*") if path.is_file()}


def _reseal_bundle(directory, workspace, results, executions):
    candidate, verification = results[workflow.MOIST_COMPILE], results[workflow.MOIST_VERIFY]
    seal(candidate["data"])
    seal(candidate)
    verification["parameters"]["candidate"] = deepcopy(candidate)
    executions[workflow.MOIST_VERIFY]["parameters"] = deepcopy(verification["parameters"])
    payload = verification["data"]
    payload["candidate_record_digest"] = candidate["record_digest"]
    seal(payload["report"])
    seal(verification)
    for execution in executions.values():
        seal(execution)
    write_json(directory / "workspace.json", workspace)
    write_json(directory / "verification.json", payload)


def _saturated_request():
    request = example_request()
    request["reference"]["temperature_k"] = 293.15
    request["reference"]["pressure_pa"] = 110000.0
    request["profile"]["water_mixing_ratio_kg_per_kg_dry_air"] = 0.02
    request["sampling"]["height_m"] = [0.0, 2000.0]
    return request


def test_source_retains_the_declared_mixing_ratio_without_derived_humidity():
    request = example_request()
    request["profile"]["wind_enu_m_per_s"] = [1.0, -2.0, 0.5]
    with patch("ciw.atmosphere_moist_compiler.compile_atmosphere", side_effect=AssertionError("compiled source")), \
            patch("ciw.atmosphere_moist_verification.verify", side_effect=AssertionError("verified source")):
        source = workflow.make_source(request)
        assert workflow.source_request(source) == request
    assert source["instrument"] == "atmosphere-moist-configuration-declaration.v1"
    assert source["run_id"].startswith("run-atmosphere-moist-")
    assert source["time_s"] == [0.0]
    assert source["metadata"]["sample_count"] == 1 and source["metadata"]["duration_s"] == 1.0
    assert source["metadata"]["sample_rate_hz"] is None
    manifest = source["metadata"]["manifest"]
    assert manifest["role"] == "synthetic_reference_configuration"
    assert manifest["frames"] == [FRAME]
    assert manifest["sampling"]["time_semantics"] == "synthetic_selection_envelope"
    assert manifest["supported_operations"] == [workflow.MOIST_COMPILE, workflow.MOIST_VERIFY]
    expected = {"declared_temperature": ("K", 298.15), "declared_pressure": ("Pa", 101325.0),
                "height_above_reference": ("m", 0.0), "declared_wind_east": ("m/s", 1.0),
                "declared_wind_north": ("m/s", -2.0), "declared_wind_up": ("m/s", 0.5),
                "declared_water_mixing_ratio": ("kg/kg dry air", 0.008)}
    assert set(source["channels"]) == set(expected)
    for name, (unit, value) in expected.items():
        assert source["channels"][name] == {"unit": unit, "values": [value]}
    assert "not acquired measurements" in source["metadata"]["provenance"]["source"]


def test_declared_environment_context_survives_without_becoming_a_measurement():
    request = example_request()
    context = {"source_kind": "declared_environment", "source_ref": "facility.manual-humidity",
               "valid_time_utc": "2026-10-03T06:00:00Z"}
    request["reference"]["context"] = context
    source = workflow.make_source(request)
    assert source["metadata"]["manifest"]["role"] == "declared_reference_environment"
    assert workflow.source_request(source)["reference"]["context"] == context
    assert workflow.AUTHORITY["physical_validation"] == "not_established"


@pytest.mark.parametrize("mutation", ["mixing_ratio", "unit", "humidity_channel", "time", "role", "frame"])
def test_reidentified_moist_source_must_equal_its_exact_input_declaration(mutation):
    source = workflow.make_source(example_request())
    if mutation == "mixing_ratio":
        source["channels"]["declared_water_mixing_ratio"]["values"][0] = 0.009
    elif mutation == "unit":
        source["channels"]["declared_water_mixing_ratio"]["unit"] = "percent"
        source["metadata"]["manifest"]["units"]["declared_water_mixing_ratio"] = "percent"
    elif mutation == "humidity_channel":
        source["channels"]["relative_humidity"] = {"unit": "1", "values": [0.4]}
        source["metadata"]["manifest"]["units"]["relative_humidity"] = "1"
    elif mutation == "time":
        source["time_s"] = [0.25]
    elif mutation == "role":
        source["metadata"]["manifest"]["role"] = "measured_humidity_profile"
    else:
        source["metadata"]["coordinate_frame"] = "geodetic"
    source["evidence_id"] = evidence_id(source)
    with pytest.raises(ValueError):
        workflow.source_request(source)


def test_registry_adds_explicit_moist_providers_without_changing_global_defaults():
    atmospheric = {workflow.COMPILE, workflow.VERIFY, workflow.MOIST_COMPILE, workflow.MOIST_VERIFY}
    default = default_registry().describe()
    assert not any(item["operation_id"] in atmospheric for item in default)
    registered = workflow.registry().describe()
    assert registered[:len(default)] == default
    assert {item["operation_id"]: item["role"] for item in registered[len(default):]} == {
        workflow.COMPILE: "backend", workflow.VERIFY: "verification",
        workflow.MOIST_COMPILE: "backend", workflow.MOIST_VERIFY: "verification"}
    compiler = workflow.runtime_identity("compiler", moist=True)
    verifier = workflow.runtime_identity("verifier", moist=True)
    dry = workflow.runtime_identity("compiler")
    assert compiler["code_sha256"] != verifier["code_sha256"] != dry["code_sha256"]
    assert len({compiler["provider"], verifier["provider"], dry["provider"]}) == 3
    assert compiler["environment"]["floating_point"] == "binary64"
    assert compiler["environment"]["python"]


def test_local_run_uses_moist_operation_occurrences_and_separate_verification_identity(tmp_path):
    directory, inspected = _bundle(tmp_path)
    assert inspected["status"] == "LOCAL"
    workspace, results, executions = _occurrences(directory)
    assert workspace["workspace_version"] == 2
    assert set(results) == set(executions) == {workflow.MOIST_COMPILE, workflow.MOIST_VERIFY}
    candidate, verification = results[workflow.MOIST_COMPILE], results[workflow.MOIST_VERIFY]
    assert candidate["data"]["schema"] == "ciw.atmosphere-moist-result.v1"
    assert verification["data"]["schema"] == "ciw.atmosphere-verification-payload.v1"
    assert verification["data"]["report"]["schema"] == "ciw.atmosphere-moist-verification.v1"
    assert candidate["role"] == "backend" and verification["role"] == "verification"
    assert candidate["evidence_id"] == verification["evidence_id"] == inspected["evidence_id"]
    assert candidate["execution_id"] != verification["execution_id"]
    assert candidate["result_id"] != verification["result_id"]
    payload = verification["data"]
    validate_identity(payload["verification_id"], "verification")
    assert payload["candidate_result_id"] == candidate["result_id"]
    assert payload["candidate_execution_id"] == candidate["execution_id"]
    assert payload["candidate_record_digest"] == candidate["record_digest"]
    assert verification["parameters"]["candidate"] == candidate
    assert payload["authority"] == inspected["authority"] == workflow.AUTHORITY
    assert inspected["preservation"]["admission_eligibility"] == "ELIGIBLE"
    assert inspected["preservation"]["state_admission_performed"] is False
    for result in results.values():
        check_seal(result)
        assert result["verification_status"] == "not_verified" and result["verification_id"] is None
        assert executions[result["operation_id"]]["status"] == "completed"
    _, second = _bundle(tmp_path, name="second")
    assert second["evidence_id"] == inspected["evidence_id"]
    for name in ("execution_id", "result_id", "verification_execution_id", "verification_id"):
        assert second[name] != inspected[name]


def test_static_inspection_and_reopen_do_not_activate_moist_or_dry_physics(tmp_path):
    directory, original = _bundle(tmp_path)
    before = _contents(directory)
    with patch("ciw.atmosphere_moist_compiler.compile_atmosphere", side_effect=AssertionError("compiler replay")), \
            patch("ciw.atmosphere_moist_verification.verify", side_effect=AssertionError("verifier replay")), \
            patch("ciw.atmosphere_compiler.compile_atmosphere", side_effect=AssertionError("dry compiler replay")), \
            patch("ciw.atmosphere_verification.verify", side_effect=AssertionError("dry verifier replay")), \
            patch("ciw.session.execute_operation", side_effect=AssertionError("operation replay")):
        assert workflow.inspect(directory) == original
        restored = Session.from_workspace(directory / "workspace.json", tmp_path / "reopened")
    assert len(restored.results) == len(restored.executions) == 2
    assert original["fresh_execution"] is False and original["fresh_numerical_verification"] is False
    assert _contents(directory) == before


def test_inspection_uses_the_preservation_from_its_validated_snapshot(tmp_path):
    directory, original = _bundle(tmp_path)
    retained = workflow._read(directory)
    with patch.object(workflow, "_read", return_value=retained) as reader, \
            patch("ciw.atmosphere_moist_preservation.build", side_effect=AssertionError("rebuilt receipt")):
        assert workflow.inspect(directory) == original
    assert reader.call_count == 1


@pytest.mark.parametrize("mixing_ratio", [0.0, 0.008])
def test_fresh_verification_and_csv_use_moist_fields_and_null_dry_limit_dew_point(tmp_path, mixing_ratio):
    request = example_request()
    request["profile"]["water_mixing_ratio_kg_per_kg_dry_air"] = mixing_ratio
    request["profile"]["wind_enu_m_per_s"] = [2.0, -1.0, 0.25]
    directory, original = _bundle(tmp_path, request)
    before = _contents(directory)
    output = tmp_path / "profile.csv"
    with patch("ciw.atmosphere_moist_compiler.compile_atmosphere", side_effect=AssertionError("compiler replay")):
        verified = workflow.verify_retained(directory)
        exported = workflow.export_csv(directory, output)
    assert verified["status"] == "LOCAL" and verified["fresh_numerical_verification"] is True
    assert verified["execution_id"] == original["execution_id"]
    assert verified["verification_id"] == original["verification_id"]
    assert verified["recomputed_with_runtime"] == workflow.runtime_identity("verifier", moist=True)
    assert exported["source_result_id"] == original["result_id"]
    profile = _occurrences(directory)[1][workflow.MOIST_COMPILE]["data"]["profile"]
    names = [name for name in STATE_FIELDS if name != "wind_enu_m_per_s"]
    with output.open(newline="") as stream:
        rows = list(csv.reader(stream))
    assert rows[0] == names + ["wind_east_m_per_s", "wind_north_m_per_s", "wind_up_m_per_s"]
    assert len(rows[0]) == 16 and len(rows) == len(profile["height_m"]) + 1
    assert not any("viscosity" in name for name in rows[0])
    for index, row in enumerate(rows[1:]):
        expected = [profile[name][index] for name in names] + profile["wind_enu_m_per_s"][index]
        assert [None if value == "" else float(value) for value in row] == expected
    saved = output.read_bytes()
    with pytest.raises(FileExistsError):
        workflow.export_csv(directory, output)
    assert output.read_bytes() == saved and _contents(directory) == before


@pytest.mark.parametrize("provider", ["impact", "fluid", "render"])
def test_handoff_exports_a_freshly_audited_exact_moist_sample_and_no_transport_law(tmp_path, provider):
    request = example_request()
    request["reference"]["height_origin_m"] = 10.0
    directory, original = _bundle(tmp_path, request)
    output = tmp_path / "handoff.json"
    before = _contents(directory)
    with patch("ciw.atmosphere_moist_compiler.compile_atmosphere", side_effect=AssertionError("compiler replay")):
        reply = workflow.export_handoff(directory, output, sample_index=2, provider=provider)
    payload = read_json(output)
    check_seal(payload)
    assert payload["schema"] == "ciw.atmosphere-moist-handoff.v1"
    assert payload["provider"] == provider and payload["sample_index"] == 2
    assert payload["height_m"] == 500.0 and payload["absolute_height_m"] == 510.0
    assert payload["composition"] == "dry_air_water_vapour"
    assert payload["source_evidence_id"] == original["evidence_id"]
    assert payload["source_result_id"] == original["result_id"]
    assert payload["source_execution_id"] == original["execution_id"]
    assert payload["verification_id"] == original["verification_id"]
    assert payload["recomputed_report_digest"] == reply["recomputed_report_digest"]
    assert payload["claims"]["exact_retained_sample"] is True
    assert all(payload["claims"][key] is False for key in (
        "interpolation_performed", "physical_validation_established", "receiver_model_validated",
        "state_admission_performed", "execution_authority", "forces_computed",
        "geodetic_transform_performed", "coordinate_transfer_validated"))
    assert not any("viscosity" in field for field in payload["environment"])
    assert payload["environment"]["relative_humidity"] > 0.0
    assert payload["environment"]["water_mixing_ratio_kg_per_kg_dry_air"] == 0.008
    saved = output.read_bytes()
    with pytest.raises(FileExistsError):
        workflow.export_handoff(directory, output, sample_index=2, provider=provider)
    assert output.read_bytes() == saved and _contents(directory) == before


@pytest.mark.parametrize("observable", ["viscosity", "clouds", "moist_adiabatic_response"])
def test_missing_transport_or_phase_models_expand_and_block_exports(tmp_path, observable):
    request = example_request()
    request["desired_observables"].append(observable)
    directory, inspected = _bundle(tmp_path, request)
    assert inspected["status"] == "EXPAND"
    assert inspected["qualification"]["unsupported_observables"] == [observable]
    assert all(check["status"] == "PASS" for check in inspected["checks"])
    assert workflow.verify_retained(directory)["status"] == "EXPAND"
    for output, exporter in [(tmp_path / "expanded.csv", lambda p: workflow.export_csv(directory, p)),
                             (tmp_path / "expanded.json", lambda p: workflow.export_handoff(
                                 directory, p, sample_index=0, provider="impact"))]:
        with pytest.raises(ValueError, match="LOCAL"):
            exporter(output)
        assert not output.exists()


@pytest.mark.parametrize("unsupported", [False, True])
def test_saturated_assumptions_refuse_before_expansion_and_remain_retained(tmp_path, unsupported):
    request = _saturated_request()
    if unsupported:
        request["desired_observables"].append("clouds")
    directory, inspected = _bundle(tmp_path, request)
    assert inspected["status"] == "REFUSE"
    _, results, executions = _occurrences(directory)
    report = results[workflow.MOIST_VERIFY]["data"]["report"]
    assert report["status"] == "FAIL" and report["qualification"]["action"] == "REFUSE"
    assert any(check["status"] == "FAIL" for check in report["checks"])
    assert results[workflow.MOIST_COMPILE]["data"]["profile"]["relative_humidity"][0] > 1.0
    assert all(execution["status"] == "completed" for execution in executions.values())
    assert inspected["preservation"]["admission_eligibility"] == "REFUSED"
    assert workflow.verify_retained(directory)["status"] == "REFUSE"
    before = _contents(directory)
    for output, exporter in [(tmp_path / "refused.csv", lambda p: workflow.export_csv(directory, p)),
                             (tmp_path / "refused.json", lambda p: workflow.export_handoff(
                                 directory, p, sample_index=0, provider="impact"))]:
        with pytest.raises(ValueError, match="LOCAL"):
            exporter(output)
        assert not output.exists()
    assert _contents(directory) == before


@pytest.mark.parametrize("mutation", ["report_schema", "report_action", "report_dependency", "verification_identity",
                                      "candidate_result", "candidate_execution", "candidate_digest", "authority"])
def test_resealed_moist_receipt_binding_tampering_rejects_static_inspection(tmp_path, mutation):
    directory, _ = _bundle(tmp_path)
    workspace, results, executions = _occurrences(directory)
    payload = results[workflow.MOIST_VERIFY]["data"]
    report = payload["report"]
    if mutation == "report_schema":
        report["schema"] = "ciw.atmosphere-verification.v1"
    elif mutation == "report_action":
        report["qualification"]["action"] = "REFUSE"
    elif mutation == "report_dependency":
        report["candidate_digest"] = "sha256:" + "0" * 64
    elif mutation == "verification_identity":
        payload["verification_id"] = new_identity("execution")
    elif mutation == "candidate_result":
        payload["candidate_result_id"] = new_identity("result")
    elif mutation == "candidate_execution":
        payload["candidate_execution_id"] = new_identity("execution")
    elif mutation == "candidate_digest":
        payload["candidate_record_digest"] = "sha256:" + "1" * 64
    else:
        payload["authority"]["physical_validation"] = "established"
    _reseal_bundle(directory, workspace, results, executions)
    if mutation == "candidate_digest":
        payload["candidate_record_digest"] = "sha256:" + "1" * 64
        seal(results[workflow.MOIST_VERIFY])
        write_json(directory / "workspace.json", workspace)
        write_json(directory / "verification.json", payload)
    before = _contents(directory)
    with patch("ciw.session.write_json") as writer:
        with pytest.raises(ValueError):
            workflow.inspect(directory)
        writer.assert_not_called()
    assert _contents(directory) == before


@pytest.mark.parametrize("phase", ["compiler", "verifier"])
def test_moist_provider_failures_retain_reopenable_refusals_without_private_details(tmp_path, phase):
    directory = tmp_path / "failed"
    target = "ciw.atmosphere_moist_compiler.compile_atmosphere" if phase == "compiler" else "ciw.atmosphere_moist_verification.verify"
    with patch(target, side_effect=RuntimeError("private-provider-detail")):
        refused = workflow.run(example_request(), directory)
    assert refused["status"] == "REFUSE"
    workspace = read_json(directory / "workspace.json")
    assert len(workspace["executions"]) == (1 if phase == "compiler" else 2)
    assert len(workspace["results"]) == (0 if phase == "compiler" else 1)
    execution = workspace["executions"][-1]
    assert execution["status"] == "refused" and execution["result_id"] is None
    assert execution["refusal"]["code"] == "operation_failed"
    assert "private-provider-detail" not in execution["refusal"]["message"]
    check_seal(execution)
    assert not (directory / "verification.json").exists() and not (directory / "preservation.json").exists()
    before = _contents(directory)
    with patch("ciw.atmosphere_moist_compiler.compile_atmosphere", side_effect=AssertionError("compiler replay")), \
            patch("ciw.atmosphere_moist_verification.verify", side_effect=AssertionError("verifier replay")):
        restored = Session.from_workspace(directory / "workspace.json", tmp_path / "reopened")
        assert workflow.inspect(directory) == workflow.verify_retained(directory) == refused
    assert len(restored.executions) == len(workspace["executions"])
    assert _contents(directory) == before


@pytest.mark.parametrize("phase,receipt", [("compiler", "verification.json"), ("compiler", "preservation.json"),
                                         ("verifier", "verification.json"), ("verifier", "preservation.json")])
def test_moist_provider_refusal_rejects_unexpected_receipts(tmp_path, phase, receipt):
    directory = tmp_path / "failed"
    target = "ciw.atmosphere_moist_compiler.compile_atmosphere" if phase == "compiler" else "ciw.atmosphere_moist_verification.verify"
    with patch(target, side_effect=RuntimeError("failure")):
        workflow.run(example_request(), directory)
    write_json(directory / receipt, {"unexpected": True})
    with pytest.raises(ValueError, match="receipt|results"):
        workflow.inspect(directory)


@pytest.mark.parametrize("action", ["inspect", "verify", "csv", "handoff"])
def test_moist_read_actions_use_one_validated_snapshot(tmp_path, action):
    first_dir, first = _bundle(tmp_path, name="first")
    second_request = example_request()
    second_request["reference"]["temperature_k"] += 5.0
    second_dir, second = _bundle(tmp_path, second_request, name="second")
    first_tuple, second_tuple = workflow._read(first_dir), workflow._read(second_dir)
    with patch.object(workflow, "_read", side_effect=[first_tuple, second_tuple]) as reader:
        if action == "inspect":
            reply = workflow.inspect(first_dir)
            assert reply["evidence_id"] == first["evidence_id"]
        elif action == "verify":
            reply = workflow.verify_retained(first_dir)
            assert reply["evidence_id"] == first["evidence_id"]
        elif action == "csv":
            output = tmp_path / "single.csv"
            reply = workflow.export_csv(first_dir, output)
            with output.open(newline="") as stream:
                rows = list(csv.reader(stream))
            assert float(rows[1][1]) == 298.15
            assert reply["source_result_id"] == first["result_id"]
        else:
            output = tmp_path / "single.json"
            reply = workflow.export_handoff(first_dir, output, sample_index=0, provider="impact")
            assert read_json(output)["environment"]["temperature_k"] == 298.15
            assert reply["source_result_id"] == first["result_id"]
        assert reader.call_count == 1
    assert first["evidence_id"] != second["evidence_id"]


def test_moist_cli_lifecycle_create_only_examples_and_qualification_exit_codes(tmp_path, capsys):
    request_path = tmp_path / "request.json"
    assert atmosphere_cli.main(["moist", "example", "--output", str(request_path)]) == 0
    assert read_json(request_path) == example_request()
    saved = request_path.read_bytes()
    assert atmosphere_cli.main(["moist", "example", "--output", str(request_path)]) == 1
    assert request_path.read_bytes() == saved
    directory = tmp_path / "run"
    assert atmosphere_cli.main(["moist", "run", str(request_path), "--output-dir", str(directory)]) == 0
    assert atmosphere_cli.main(["moist", "inspect", str(directory)]) == 0
    assert atmosphere_cli.main(["moist", "verify", str(directory)]) == 0
    assert atmosphere_cli.main(["moist", "export", str(directory), "--output", str(tmp_path / "cli.csv")]) == 0
    assert atmosphere_cli.main(["moist", "handoff", str(directory), "--sample-index", "0", "--provider", "impact",
                                "--output", str(tmp_path / "cli.json")]) == 0
    expanded = example_request()
    expanded["desired_observables"].append("viscosity")
    write_json(request_path, expanded)
    expanded_dir = tmp_path / "expanded"
    for command in (["moist", "run", str(request_path), "--output-dir", str(expanded_dir)],
                    ["moist", "inspect", str(expanded_dir)], ["moist", "verify", str(expanded_dir)]):
        assert atmosphere_cli.main(command) == 2
    write_json(request_path, _saturated_request())
    refused_dir = tmp_path / "saturated"
    for command in (["moist", "run", str(request_path), "--output-dir", str(refused_dir)],
                    ["moist", "inspect", str(refused_dir)], ["moist", "verify", str(refused_dir)]):
        assert atmosphere_cli.main(command) == 2
    output = capsys.readouterr().out
    assert '"status": "EXPAND"' in output and '"status": "REFUSE"' in output


@pytest.mark.parametrize("moist_prefix", [False, True])
def test_cli_run_prefix_refuses_the_other_request_profile_before_directory_creation(tmp_path, moist_prefix):
    from ciw.atmosphere_contract import example_request as dry_request
    request = dry_request() if moist_prefix else example_request()
    request_path = tmp_path / "request.json"
    write_json(request_path, request)
    directory = tmp_path / "wrong-profile"
    prefix = ["moist"] if moist_prefix else []
    assert atmosphere_cli.main(prefix + ["run", str(request_path), "--output-dir", str(directory)]) == 1
    assert not directory.exists()


@pytest.mark.parametrize("name", ["workspace.json", "request.json", "verification.json", "preservation.json"])
def test_moist_bundle_size_limits_apply_before_session_reader(tmp_path, name):
    directory, _ = _bundle(tmp_path)
    with (directory / name).open("wb") as stream:
        stream.truncate(workflow.MAX_BUNDLE_FILE_BYTES + 1)
    with patch.object(Session, "from_workspace", side_effect=AssertionError("Session reader reached")):
        with pytest.raises(ValueError, match="budget"):
            workflow.inspect(directory)


def _symlink_or_mock(monkeypatch, link, target):
    from pathlib import Path
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        if sys.platform != "win32":
            raise
        link.write_bytes(target.read_bytes() if target.is_file() else b"{}")
        original = Path.is_symlink
        monkeypatch.setattr(Path, "is_symlink", lambda path: path == link or original(path))


@pytest.mark.parametrize("name", ["workspace.json", "request.json", "verification.json", "preservation.json"])
def test_moist_bundle_symlinks_refuse_before_session_reader(tmp_path, monkeypatch, name):
    directory, _ = _bundle(tmp_path)
    target = directory / name
    replacement = tmp_path / (name + ".real")
    target.rename(replacement)
    _symlink_or_mock(monkeypatch, target, replacement)
    with patch.object(Session, "from_workspace", side_effect=AssertionError("Session reader reached")):
        with pytest.raises(ValueError, match="symlink"):
            workflow.inspect(directory)


@pytest.mark.parametrize("value", [False, 0])
def test_moist_request_artifact_preserves_numeric_encoding_as_well_as_value(tmp_path, value):
    directory, _ = _bundle(tmp_path)
    retained = read_json(directory / "request.json")
    retained["reference"]["height_origin_m"] = value
    write_json(directory / "request.json", retained)
    with pytest.raises(ValueError):
        workflow.inspect(directory)
