"""A reference atmosphere extends NET's retained substrate with scoped claims."""
from copy import deepcopy
import csv
import sys
from unittest.mock import patch

import pytest

from ciw import atmosphere_cli, atmosphere_workflow as workflow
from ciw.atmosphere_contract import FRAME, STATE_FIELDS, example_request
from ciw.core.identities import evidence_id, new_identity, validate_identity
from ciw.operations.registry import default_registry
from ciw.operations.runner import check_seal, digest, seal
from ciw.session import Session, read_json, write_json


def _bundle(tmp_path, request=None, name="atmosphere"):
    directory = tmp_path / name
    return directory, workflow.run(example_request() if request is None else request, directory)


def _occurrences(directory):
    workspace = read_json(directory / "workspace.json")
    return (workspace, {item["operation_id"]: item for item in workspace["results"]},
            {item["operation_id"]: item for item in workspace["executions"]})


def _contents(directory):
    return {path.relative_to(directory): path.read_bytes()
            for path in directory.rglob("*") if path.is_file()}


def _reseal_bundle(directory, workspace, results, executions, *, preservation=False):
    candidate, verification = results[workflow.COMPILE], results[workflow.VERIFY]
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
    if preservation:
        from ciw.atmosphere_preservation import build
        write_json(directory / "preservation.json", build(
            read_json(directory / "request.json"), candidate["data"], payload["report"]))


def test_source_retains_only_declared_si_inputs_not_a_measured_altitude_or_time_profile():
    request = example_request()
    request["profile"]["wind_enu_m_per_s"] = [1.0, -2.0, 0.5]
    with patch("ciw.atmosphere_compiler.compile_atmosphere", side_effect=AssertionError("compiled source")), \
            patch("ciw.atmosphere_verification.verify", side_effect=AssertionError("verified source")):
        source = workflow.make_source(request)
        assert workflow.source_request(source) == request
    assert source["instrument"] == "atmosphere-configuration-declaration.v1"
    assert source["time_s"] == [0.0]
    assert source["metadata"]["sample_count"] == 1 and source["metadata"]["duration_s"] == 1.0
    assert source["metadata"]["sample_rate_hz"] is None
    manifest = source["metadata"]["manifest"]
    assert manifest["role"] == "synthetic_reference_configuration"
    assert manifest["frames"] == [FRAME]
    assert manifest["sampling"]["time_semantics"] == "synthetic_selection_envelope"
    assert manifest["supported_operations"] == [workflow.COMPILE, workflow.VERIFY]
    expected = {"declared_temperature": ("K", 288.15), "declared_pressure": ("Pa", 101325.0),
                "height_above_reference": ("m", 0.0), "declared_wind_east": ("m/s", 1.0),
                "declared_wind_north": ("m/s", -2.0), "declared_wind_up": ("m/s", 0.5)}
    assert set(source["channels"]) == set(expected)
    for name, (unit, value) in expected.items():
        assert source["channels"][name] == {"unit": unit, "values": [value]}
    assert "not acquired measurements" in source["metadata"]["provenance"]["source"]


def test_declared_external_context_remains_a_declaration():
    request = example_request()
    context = {"source_kind": "declared_environment", "source_ref": "facility.manual-boundary",
               "valid_time_utc": "2026-10-03T06:00:00Z"}
    request["reference"]["context"] = context
    source = workflow.make_source(request)
    assert source["metadata"]["manifest"]["role"] == "declared_reference_environment"
    assert workflow.source_request(source)["reference"]["context"] == context
    assert "measurements" in source["metadata"]["provenance"]["source"]
    assert workflow.AUTHORITY["physical_validation"] == "not_established"


@pytest.mark.parametrize("mutation", ["value", "unit", "time", "role", "frame", "provenance"])
def test_reidentified_source_must_equal_exact_configuration_declaration(mutation):
    source = workflow.make_source(example_request())
    if mutation == "value":
        source["channels"]["declared_temperature"]["values"][0] += 1.0
    elif mutation == "unit":
        source["channels"]["declared_temperature"]["unit"] = "C"
        source["metadata"]["manifest"]["units"]["declared_temperature"] = "C"
    elif mutation == "time":
        source["time_s"] = [0.25]
    elif mutation == "role":
        source["metadata"]["manifest"]["role"] = "measured_atmosphere"
    elif mutation == "frame":
        source["metadata"]["coordinate_frame"] = "geodetic"
    else:
        source["metadata"]["provenance"]["source"] = "experimentally validated"
    source["evidence_id"] = evidence_id(source)
    with pytest.raises(ValueError):
        workflow.source_request(source)


def test_installed_operations_are_explicit_and_default_registry_remains_unchanged():
    default = default_registry().describe()
    assert all(item["operation_id"] not in {workflow.COMPILE, workflow.VERIFY} for item in default)
    registered = workflow.registry().describe()
    assert registered == default + [{"operation_id": workflow.COMPILE, "role": "backend"},
                                    {"operation_id": workflow.VERIFY, "role": "verification"}]
    compiler, verifier = workflow.runtime_identity("compiler"), workflow.runtime_identity("verifier")
    assert compiler["code_sha256"] != verifier["code_sha256"]
    assert compiler["provider"] != verifier["provider"]
    assert compiler["environment"]["floating_point"] == "binary64"
    assert compiler["environment"]["python"]
    with pytest.raises(ValueError):
        workflow.runtime_identity("saved.import.path")


@pytest.mark.parametrize("operation", [workflow.COMPILE, workflow.VERIFY])
def test_other_workload_sources_refuse_before_atmospheric_callbacks(tmp_path, operation):
    from ciw.impact_contract import example_request as impact_request
    from ciw.impact_workflow import make_source as impact_source
    session = Session(impact_source(impact_request()), tmp_path / "cross-profile", operations=workflow.registry())
    with patch("ciw.atmosphere_compiler.compile_atmosphere", side_effect=AssertionError("compiler called")), \
            patch("ciw.atmosphere_verification.verify", side_effect=AssertionError("verifier called")):
        reply = workflow._execute(session, operation, {})
    assert reply["status"] == "refused" and not session.results
    assert len(session.executions) == 1
    check_seal(reply["execution"])


def test_local_run_keeps_evidence_operation_execution_result_and_verification_separate(tmp_path):
    directory, inspected = _bundle(tmp_path)
    assert inspected["status"] == "LOCAL"
    workspace, results, executions = _occurrences(directory)
    assert workspace["workspace_version"] == 2
    assert set(results) == set(executions) == {workflow.COMPILE, workflow.VERIFY}
    candidate, verification = results[workflow.COMPILE], results[workflow.VERIFY]
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
    for result in results.values():
        check_seal(result)
        assert result["verification_status"] == "not_verified" and result["verification_id"] is None
        assert executions[result["operation_id"]]["status"] == "completed"
    _, second = _bundle(tmp_path, name="second")
    assert second["evidence_id"] == inspected["evidence_id"]
    for name in ("execution_id", "result_id", "verification_execution_id", "verification_id"):
        assert second[name] != inspected[name]


def test_static_inspect_and_session_reopen_never_compile_integrate_or_verify(tmp_path):
    directory, original = _bundle(tmp_path)
    before = _contents(directory)
    with patch("ciw.atmosphere_compiler.compile_atmosphere", side_effect=AssertionError("compiler replay")), \
            patch("ciw.atmosphere_verification.verify", side_effect=AssertionError("verifier replay")), \
            patch("ciw.atmosphere_verification._quadrature_reference", side_effect=AssertionError("quadrature replay")), \
            patch("ciw.session.execute_operation", side_effect=AssertionError("operation replay")):
        assert workflow.inspect(directory) == original
        restored = Session.from_workspace(directory / "workspace.json", tmp_path / "reopened")
    assert len(restored.results) == len(restored.executions) == 2
    assert original["fresh_execution"] is False and original["fresh_numerical_verification"] is False
    assert _contents(directory) == before


def test_fresh_verify_and_scalar_csv_export_are_read_only_and_create_only(tmp_path):
    request = example_request()
    request["profile"]["wind_enu_m_per_s"] = [2.0, -1.0, 0.25]
    directory, original = _bundle(tmp_path, request)
    before = _contents(directory)
    output = tmp_path / "profile.csv"
    with patch("ciw.atmosphere_compiler.compile_atmosphere", side_effect=AssertionError("compiler replay")):
        verified = workflow.verify_retained(directory)
        exported = workflow.export_csv(directory, output)
    assert verified["status"] == "LOCAL" and verified["fresh_numerical_verification"] is True
    assert verified["execution_id"] == original["execution_id"]
    assert verified["verification_id"] == original["verification_id"]
    assert exported["source_result_id"] == original["result_id"]
    profile = _occurrences(directory)[1][workflow.COMPILE]["data"]["profile"]
    names = [name for name in STATE_FIELDS if name != "wind_enu_m_per_s"]
    with output.open(newline="") as stream:
        rows = list(csv.reader(stream))
    assert rows[0] == names + ["wind_east_m_per_s", "wind_north_m_per_s", "wind_up_m_per_s"]
    assert len(rows[0]) == 11
    assert [[float(value) for value in row] for row in rows[1:]] == [
        [profile[name][index] for name in names] + wind for index, wind in enumerate(profile["wind_enu_m_per_s"])]
    saved = output.read_bytes()
    with pytest.raises(FileExistsError):
        workflow.export_csv(directory, output)
    assert output.read_bytes() == saved
    with pytest.raises(FileExistsError):
        workflow.run(request, directory)
    assert _contents(directory) == before


@pytest.mark.parametrize("provider", ["impact", "fluid", "render"])
def test_handoff_exports_exact_freshly_verified_sample_and_bindings_only(tmp_path, provider):
    directory, original = _bundle(tmp_path)
    output = tmp_path / "handoff.json"
    before = _contents(directory)
    with patch("ciw.atmosphere_compiler.compile_atmosphere", side_effect=AssertionError("compiler replay")):
        reply = workflow.export_handoff(directory, output, sample_index=2, provider=provider)
    payload = read_json(output)
    check_seal(payload)
    assert payload["schema"] == "ciw.atmosphere-handoff.v1"
    assert payload["provider"] == provider and payload["sample_index"] == 2 and payload["height_m"] == 2000.0
    assert payload["source_evidence_id"] == original["evidence_id"]
    assert payload["source_result_id"] == original["result_id"]
    assert payload["source_execution_id"] == original["execution_id"]
    assert payload["verification_id"] == original["verification_id"]
    assert payload["recomputed_report_digest"] == reply["recomputed_report_digest"]
    assert payload["claims"]["exact_retained_sample"] is True
    assert all(payload["claims"][key] is False for key in (
        "interpolation_performed", "physical_validation_established", "receiver_model_validated",
        "state_admission_performed", "execution_authority", "forces_computed"))
    saved = output.read_bytes()
    with pytest.raises(FileExistsError):
        workflow.export_handoff(directory, output, sample_index=2, provider=provider)
    assert output.read_bytes() == saved and _contents(directory) == before


@pytest.mark.parametrize("sample,provider", [(-1, "impact"), (True, "impact"), (1.0, "impact"),
                                            (11, "fluid"), (0, "new.import.path"), (0, True)])
def test_invalid_handoff_indices_or_providers_never_create_output(tmp_path, sample, provider):
    directory, _ = _bundle(tmp_path)
    output = tmp_path / "bad-handoff.json"
    with pytest.raises(ValueError):
        workflow.export_handoff(directory, output, sample_index=sample, provider=provider)
    assert not output.exists()


@pytest.mark.parametrize("observable", ["material_conditioning", "weather_forecast", "visual_scattering"])
def test_unsupported_observables_expand_and_prevent_csv_or_handoff(tmp_path, observable):
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


@pytest.mark.parametrize("mutation", ["report_schema", "report_action", "report_dependency", "verification_identity",
                                      "candidate_result", "candidate_execution", "candidate_digest", "authority"])
def test_resealed_payload_binding_tampering_rejects_static_inspection(tmp_path, mutation):
    directory, _ = _bundle(tmp_path)
    workspace, results, executions = _occurrences(directory)
    payload = results[workflow.VERIFY]["data"]
    report = payload["report"]
    if mutation == "report_schema":
        report["schema"] = "imported.fake.report.v1"
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
    # Preserve the deliberately altered candidate digest after normal resealing.
    _reseal_bundle(directory, workspace, results, executions)
    if mutation == "candidate_digest":
        payload["candidate_record_digest"] = "sha256:" + "1" * 64
        seal(results[workflow.VERIFY])
        write_json(directory / "workspace.json", workspace)
        write_json(directory / "verification.json", payload)
    before = _contents(directory)
    with patch("ciw.session.write_json") as writer:
        with pytest.raises(ValueError):
            workflow.inspect(directory)
        writer.assert_not_called()
    assert _contents(directory) == before


@pytest.mark.parametrize("phase", ["compiler", "verifier"])
def test_provider_failure_retains_read_only_reopenable_refusal(tmp_path, phase):
    directory = tmp_path / "failed"
    target = "ciw.atmosphere_compiler.compile_atmosphere" if phase == "compiler" else "ciw.atmosphere_verification.verify"
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
    with patch("ciw.atmosphere_compiler.compile_atmosphere", side_effect=AssertionError("compiler replay")), \
            patch("ciw.atmosphere_verification.verify", side_effect=AssertionError("verifier replay")):
        restored = Session.from_workspace(directory / "workspace.json", tmp_path / "reopened")
        assert workflow.inspect(directory) == workflow.verify_retained(directory) == refused
    assert len(restored.executions) == len(workspace["executions"])
    assert _contents(directory) == before


@pytest.mark.parametrize("phase,receipt", [("compiler", "verification.json"), ("compiler", "preservation.json"),
                                         ("verifier", "verification.json"), ("verifier", "preservation.json")])
def test_refused_bundles_reject_unexpected_verification_and_preservation_receipts(tmp_path, phase, receipt):
    directory = tmp_path / "failed"
    target = "ciw.atmosphere_compiler.compile_atmosphere" if phase == "compiler" else "ciw.atmosphere_verification.verify"
    with patch(target, side_effect=RuntimeError("failure")):
        workflow.run(example_request(), directory)
    write_json(directory / receipt, {"unexpected": True})
    with pytest.raises(ValueError, match="receipt|results"):
        workflow.inspect(directory)


@pytest.mark.parametrize("action", ["inspect", "verify", "csv", "handoff"])
def test_public_read_actions_use_one_validated_snapshot(tmp_path, action):
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
            assert float(rows[1][1]) == 288.15
            assert reply["source_result_id"] == first["result_id"]
        else:
            output = tmp_path / "single.json"
            reply = workflow.export_handoff(first_dir, output, sample_index=0, provider="impact")
            assert read_json(output)["environment"]["temperature_k"] == 288.15
            assert reply["source_result_id"] == first["result_id"]
        assert reader.call_count == 1
    assert first["evidence_id"] != second["evidence_id"]


def test_cli_full_lifecycle_exit_codes_and_create_only_examples(tmp_path, capsys):
    request_path = tmp_path / "request.json"
    assert atmosphere_cli.main(["example", "--output", str(request_path)]) == 0
    saved = request_path.read_bytes()
    assert atmosphere_cli.main(["example", "--output", str(request_path)]) == 1
    assert request_path.read_bytes() == saved
    directory = tmp_path / "run"
    assert atmosphere_cli.main(["run", str(request_path), "--output-dir", str(directory)]) == 0
    assert atmosphere_cli.main(["inspect", str(directory)]) == 0
    assert atmosphere_cli.main(["verify", str(directory)]) == 0
    assert atmosphere_cli.main(["export", str(directory), "--output", str(tmp_path / "cli.csv")]) == 0
    assert atmosphere_cli.main(["handoff", str(directory), "--sample-index", "0", "--provider", "impact",
                                "--output", str(tmp_path / "cli.json")]) == 0
    expanded = example_request()
    expanded["desired_observables"].append("weather_forecast")
    write_json(request_path, expanded)
    expanded_dir = tmp_path / "expanded"
    assert atmosphere_cli.main(["run", str(request_path), "--output-dir", str(expanded_dir)]) == 2
    assert atmosphere_cli.main(["inspect", str(expanded_dir)]) == 2
    assert atmosphere_cli.main(["verify", str(expanded_dir)]) == 2
    assert '"status": "EXPAND"' in capsys.readouterr().out


def test_valid_long_height_interval_keeps_numerical_refusal_and_cannot_export(tmp_path):
    request = example_request()
    request["sampling"]["height_m"] = [0.0, 11000.0]
    request["profile"]["lapse_rate_k_per_m"] = 0.009
    directory, inspected = _bundle(tmp_path, request)
    assert inspected["status"] == "REFUSE"
    workspace, results, executions = _occurrences(directory)
    report = results[workflow.VERIFY]["data"]["report"]
    assert report["status"] == "FAIL"
    assert all(execution["status"] == "completed" for execution in executions.values())
    assert any(check["name"] == "quadrature_refinement" and check["status"] == "FAIL" for check in report["checks"])
    assert inspected["preservation"]["admission_eligibility"] == "REFUSED"
    assert workflow.verify_retained(directory)["status"] == "REFUSE"
    output = tmp_path / "refused.csv"
    with pytest.raises(ValueError, match="LOCAL"):
        workflow.export_csv(directory, output)
    assert not output.exists()


@pytest.mark.parametrize("name", ["workspace.json", "request.json", "verification.json", "preservation.json"])
def test_oversized_bundle_inputs_refuse_before_session_reopen(tmp_path, name):
    directory, _ = _bundle(tmp_path)
    with (directory / name).open("wb") as stream:
        stream.truncate(workflow.MAX_BUNDLE_FILE_BYTES + 1)
    with patch.object(Session, "from_workspace", side_effect=AssertionError("Session reader reached")):
        with pytest.raises(ValueError, match="budget"):
            workflow.inspect(directory)


def _symlink_or_mock(monkeypatch, link, target):
    """Use actual links where available; Windows privileges are not an engine gate."""
    from pathlib import Path
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        if sys.platform != "win32":
            raise
        # Exercise the same preflight rejection without requiring the runner's
        # optional Windows symlink privilege. No provider or reader is reached.
        link.write_bytes(target.read_bytes() if target.is_file() else b"{}")
        original = Path.is_symlink
        monkeypatch.setattr(Path, "is_symlink", lambda path: path == link or original(path))


@pytest.mark.parametrize("name", ["workspace.json", "request.json", "verification.json", "preservation.json"])
def test_bundle_symlinks_refuse_before_session_reopen(tmp_path, monkeypatch, name):
    directory, _ = _bundle(tmp_path)
    target = directory / name
    replacement = tmp_path / (name + ".real")
    target.rename(replacement)
    _symlink_or_mock(monkeypatch, target, replacement)
    with patch.object(Session, "from_workspace", side_effect=AssertionError("Session reader reached")):
        with pytest.raises(ValueError, match="symlink"):
            workflow.inspect(directory)


@pytest.mark.parametrize("name", ["verification.json", "preservation.json"])
def test_dangling_refusal_receipt_symlinks_refuse_before_session_reopen(tmp_path, monkeypatch, name):
    directory = tmp_path / "failed"
    with patch("ciw.atmosphere_compiler.compile_atmosphere", side_effect=ValueError("refused")):
        workflow.run(example_request(), directory)
    _symlink_or_mock(monkeypatch, directory / name, tmp_path / "missing.json")
    with patch.object(Session, "from_workspace", side_effect=AssertionError("Session reader reached")):
        with pytest.raises(ValueError, match="symlink"):
            workflow.inspect(directory)


@pytest.mark.parametrize("value", [False, 0])
def test_request_artifact_cannot_substitute_boolean_or_different_numeric_encoding(tmp_path, value):
    directory, _ = _bundle(tmp_path)
    retained = read_json(directory / "request.json")
    retained["reference"]["height_origin_m"] = value
    write_json(directory / "request.json", retained)
    with pytest.raises(ValueError):
        workflow.inspect(directory)
