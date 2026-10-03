"""Independent retained-evidence and lifecycle audit of atmosphere comparisons."""
from contextlib import ExitStack
from copy import deepcopy
import csv
import os
from pathlib import Path
import shutil
import stat
from unittest.mock import patch

import pytest

from ciw import atmosphere_workflow as atmosphere
from ciw import atmosphere_comparison_workflow as workflow
from ciw import atmosphere_cli
from ciw.atmosphere_comparison_contract import example_policy, example_reference
from ciw.atmosphere_contract import example_request as dry_request
from ciw.atmosphere_moist_contract import example_request as moist_request
from ciw.core.identities import evidence_id
from ciw.operations.registry import default_registry
from ciw.operations.runner import check_seal, digest, seal
from ciw.session import Session, read_json, write_json

COMPARE = "atmosphere.compare.v1"
VERIFY = "atmosphere.compare-verify.v1"


def _contents(directory):
    return {path.relative_to(directory): path.read_bytes()
            for path in directory.rglob("*") if path.is_file()}


def _occurrences(directory):
    workspace = read_json(directory / "workspace.json")
    results = {row["operation_id"]: row for row in workspace["results"]}
    executions = {row["operation_id"]: row for row in workspace["executions"]}
    return workspace, results, executions


def _no_providers(*, numerical=True, operations=True):
    stack = ExitStack()
    for namespace in ("atmosphere", "atmosphere_moist"):
        stack.enter_context(patch(f"ciw.{namespace}_compiler.compile_atmosphere",
                                  side_effect=AssertionError("atmospheric compiler replay")))
        if numerical:
            stack.enter_context(patch(f"ciw.{namespace}_verification.verify",
                                      side_effect=AssertionError("atmospheric verifier replay")))
    if numerical:
        stack.enter_context(patch("ciw.atmosphere_comparison.compare",
                                  side_effect=AssertionError("comparison provider replay")))
        stack.enter_context(patch("ciw.atmosphere_comparison_verification.verify",
                                  side_effect=AssertionError("comparison verifier replay")))
    if operations:
        stack.enter_context(patch("ciw.session.execute_operation",
                                  side_effect=AssertionError("operation replay")))
    return stack


@pytest.fixture(scope="module", params=["dry", "moist"])
def retained(tmp_path_factory, request):
    declaration = dry_request() if request.param == "dry" else moist_request()
    root = tmp_path_factory.mktemp("comparison-audit-" + request.param)
    original = root / "atmosphere"
    atmosphere.run(declaration, original)
    reference = example_reference(declaration)
    policy = example_policy(reference)
    directory = root / "comparison"
    inspected = workflow.run(original, reference, policy, directory)
    return {"request": declaration, "original": original, "reference": reference,
            "policy": policy, "directory": directory, "inspected": inspected}


@pytest.fixture(scope="module", params=["dry", "moist"])
def alternate(tmp_path_factory, request):
    declaration = dry_request() if request.param == "dry" else moist_request()
    declaration["reference"]["temperature_k"] = 303.15
    root = tmp_path_factory.mktemp("comparison-audit-alternate-" + request.param)
    original = root / "atmosphere"
    atmosphere.run(declaration, original)
    reference = example_reference(declaration)
    policy = example_policy(reference)
    directory = root / "comparison"
    workflow.run(original, reference, policy, directory)
    return {"request": declaration, "original": original, "reference": reference,
            "policy": policy, "directory": directory}


def test_comparison_registry_extends_explicit_atmosphere_registry_and_never_default():
    base = {row["operation_id"]: row["role"] for row in atmosphere.registry().describe()}
    extended = {row["operation_id"]: row["role"] for row in workflow.registry().describe()}
    assert {key: extended[key] for key in base} == base
    assert extended[COMPARE] == "backend" and extended[VERIFY] == "verification"
    assert {row["operation_id"] for row in default_registry().describe()} == {
        "statistics.v1", "spectrum.periodogram.v1"}


def test_comparison_clones_actual_occurrences_and_keeps_external_evidence_separate(retained):
    original, original_results, original_executions = _occurrences(retained["original"])
    copied, results, executions = _occurrences(retained["directory"])
    assert len(results) == len(executions) == 4
    assert original["run"] == copied["run"]
    assert copied["run"]["evidence_id"] == original["run"]["evidence_id"]
    for operation in original_results:
        assert digest(results[operation]) == digest(original_results[operation])
        assert digest(executions[operation]) == digest(original_executions[operation])
    external = results[COMPARE]["parameters"]["reference_source"]
    assert external["evidence_id"] == evidence_id(external)
    assert external["evidence_id"] != copied["run"]["evidence_id"]
    assert workflow.reference_from_source(external) == retained["reference"]
    assert len({row["result_id"] for row in results.values()}) == 4
    assert len({row["execution_id"] for row in executions.values()}) == 4
    science_id = results[atmosphere._operation_ids(retained["request"])[1]]["data"]["verification_id"]
    assert results[VERIFY]["data"]["comparison_verification_id"] != science_id


def test_reference_source_is_one_declaration_and_never_relabels_height_as_time(retained):
    with _no_providers():
        source = workflow.make_reference_source(retained["reference"])
        assert workflow.reference_from_source(source) == retained["reference"]
    assert source["time_s"] == [0.0]
    assert source["metadata"]["sample_count"] == 1
    assert set(source["channels"]) == {"reference_record_declaration"}
    assert source["channels"]["reference_record_declaration"] == {"unit": "1", "values": [1]}
    assert source["metadata"]["reference"] == retained["reference"]


def test_static_inspection_and_generic_reopen_never_execute_providers(retained, tmp_path):
    directory = retained["directory"]
    before = _contents(directory)
    with _no_providers():
        inspected = workflow.inspect(directory)
        reopened = Session.from_workspace(directory / "workspace.json", tmp_path / "reopened")
    assert inspected == retained["inspected"]
    assert len(reopened.results) == len(reopened.executions) == 4
    assert {COMPARE, VERIFY}.isdisjoint(row["operation_id"] for row in reopened.operations.describe())
    assert _contents(directory) == before


def test_fresh_verification_reconstructs_without_compiler_or_comparator_replay(retained):
    with _no_providers(numerical=False):
        with patch("ciw.atmosphere_comparison.compare", side_effect=AssertionError("comparator replay")):
            inspected = workflow.verify_retained(retained["directory"])
    assert inspected["status"] == "LOCAL" and inspected["verification_status"] == "PASS"
    assert inspected["fresh_numerical_verification"] is True
    assert inspected["fresh_execution"] is False


def test_run_uses_one_fresh_verified_source_snapshot(retained, alternate, tmp_path):
    first = atmosphere._read(retained["original"])
    second = atmosphere._read(alternate["original"])
    before = _contents(retained["original"])
    destination = tmp_path / "single-source-snapshot"
    with patch.object(atmosphere, "_read", side_effect=[first, second]) as read:
        with patch.object(atmosphere, "_verify_read", wraps=atmosphere._verify_read) as verified:
            workflow.run(retained["original"], retained["reference"], retained["policy"], destination)
    assert read.call_count == verified.call_count == 1
    workspace, results, _ = _occurrences(destination)
    assert workspace["run"]["evidence_id"] == first[0].run["evidence_id"]
    assert results[COMPARE]["parameters"]["atmospheric_candidate"]["result_id"] == first[1]["result_id"]
    assert _contents(retained["original"]) == before


@pytest.mark.parametrize("command", ["verify", "json", "csv"])
def test_fresh_actions_use_one_retained_comparison_snapshot(retained, alternate, tmp_path, command):
    first = workflow._read(retained["directory"])
    second = workflow._read(alternate["directory"])
    with patch.object(workflow, "_read", side_effect=[first, second]) as read:
        if command == "verify":
            output = workflow.verify_retained(retained["directory"])
        elif command == "json":
            output = workflow.export_json(retained["directory"], tmp_path / "single-snapshot.json")
            check_seal(read_json(tmp_path / "single-snapshot.json"))
        else:
            output = workflow.export_csv(retained["directory"], tmp_path / "single-snapshot.csv")
            assert list(csv.reader((tmp_path / "single-snapshot.csv").read_text(encoding="utf-8").splitlines()))
    assert read.call_count == 1
    # Every action reports the comparison occurrence actually audited.
    assert first[3]["result_id"] in str(output)
    assert second[3]["result_id"] not in str(output)


@pytest.mark.parametrize("command", ["inspect", "verify", "json", "csv"])
def test_retained_actions_preserve_original_and_comparison_bytes(retained, tmp_path, command):
    old_before = _contents(retained["original"])
    before = _contents(retained["directory"])
    if command == "inspect":
        workflow.inspect(retained["directory"])
    elif command == "verify":
        workflow.verify_retained(retained["directory"])
    elif command == "json":
        workflow.export_json(retained["directory"], tmp_path / "out.json")
    else:
        workflow.export_csv(retained["directory"], tmp_path / "out.csv")
    assert _contents(retained["directory"]) == before
    assert _contents(retained["original"]) == old_before


@pytest.mark.parametrize("artifact", ["atmosphere-request.json", "reference.json", "policy.json", "comparison-verification.json"])
def test_detached_artifact_substitution_cannot_change_retained_inputs(retained, alternate, tmp_path, artifact):
    directory = tmp_path / "substituted"
    shutil.copytree(retained["directory"], directory)
    # Some policy defaults are identical. An unknown field still forces a
    # coherently sealed but noncanonical detached replacement.
    replacement = read_json(alternate["directory"] / artifact)
    replacement["foreign_reference"] = "coherently sealed substituted artifact"
    if "record_digest" in replacement:
        seal(replacement)
    write_json(directory / artifact, replacement)
    with _no_providers(), pytest.raises((ValueError, KeyError, TypeError)):
        workflow.inspect(directory)


def test_reference_evidence_rejects_coherently_resealed_scientific_channel_forgery(retained):
    source = workflow.make_reference_source(retained["reference"])
    source["channels"]["reference_record_declaration"]["values"] = [2]
    source["evidence_id"] = evidence_id(source)
    with _no_providers(), pytest.raises(ValueError):
        workflow.reference_from_source(source)


@pytest.mark.parametrize("extra", ["provider_import_path", "operation_id", "canonical_admission"])
def test_saved_reference_fields_never_activate_code_or_authority(retained, tmp_path, extra):
    reference = deepcopy(retained["reference"])
    reference[extra] = "untrusted.module.activate.v1"
    seal(reference)
    destination = tmp_path / "untrusted-reference"
    with _no_providers(), pytest.raises((ValueError, KeyError, TypeError)):
        workflow.run(retained["original"], reference, retained["policy"], destination)
    assert not destination.exists()


@pytest.mark.parametrize("kind", ["json", "csv"])
def test_exports_are_create_only_for_existing_files(retained, tmp_path, kind):
    output = tmp_path / ("existing." + kind)
    output.write_bytes(b"original recipient bytes")
    export = workflow.export_json if kind == "json" else workflow.export_csv
    with pytest.raises((FileExistsError, ValueError, OSError)):
        export(retained["directory"], output)
    assert output.read_bytes() == b"original recipient bytes"


@pytest.mark.parametrize("mismatch", ["frame", "origin", "height", "sample", "time"])
def test_context_mismatches_retain_refusal_without_inventing_alignment(retained, tmp_path, mismatch):
    reference = deepcopy(retained["reference"])
    if mismatch == "frame":
        reference["context"]["frame"] = "unqualified.foreign.frame.v1"
    elif mismatch == "origin":
        reference["context"]["height_origin_m"] += 1.0
    elif mismatch == "height":
        reference["observations"][0]["height_m"] = 1.0
    elif mismatch == "sample":
        reference["observations"][0]["sample_index"] = 128
        reference["observations"][0]["height_m"] = 2000.0
    else:
        reference["context"]["valid_time_utc"] = "2000-01-01T00:00:00Z"
    seal(reference)
    inspected = workflow.run(retained["original"], reference, example_policy(reference), tmp_path / "mismatch")
    assert inspected["status"] == "REFUSE"
    assert inspected["verification_status"] == "PASS"
    _, results, _ = _occurrences(tmp_path / "mismatch")
    assert results[COMPARE]["data"]["qualification"]["action"] == "REFUSE"
    assert results[VERIFY]["data"]["report"]["status"] == "PASS"


def test_bad_alignment_takes_refuse_precedence_over_unsupported_humidity(retained, tmp_path):
    reference = deepcopy(retained["reference"])
    reference["context"].update(frame="unqualified.foreign.frame.v1",
                                 humidity_convention="pressure_enhanced_relative_humidity")
    reference["observations"][0]["quantities"]["relative_humidity"] = {
        "value": 0.5, "unit": "1", "uncertainty": {
            "kind": "exact_fixture", "absolute_bound": 0.0, "coverage_factor": None,
            "reference": "Synthetic incompatible humidity convention fixture"},
        "instrument_ref": None, "calibration_ref": None}
    seal(reference)
    inspected = workflow.run(retained["original"], reference, example_policy(reference), tmp_path / "precedence")
    assert inspected["status"] == "REFUSE" and inspected["verification_status"] == "PASS"


def test_reference_independence_claim_never_becomes_physical_validation(retained, tmp_path):
    reference = deepcopy(retained["reference"])
    reference["provenance"]["independent_of_candidate"] = True
    seal(reference)
    inspected = workflow.run(retained["original"], reference, example_policy(reference), tmp_path / "declared-independence")
    _, results, _ = _occurrences(tmp_path / "declared-independence")
    claims = results[COMPARE]["data"]["claims"]
    assert inspected["status"] == "LOCAL" and inspected["agreement_status"] == "PASS"
    assert claims["independence_declared"] is True
    assert claims["independence_established"] is False
    assert claims["measurement_authenticity_established"] is False
    assert claims["calibration_validation"] is False
    assert claims["physical_validation"] == "not_established"
    assert claims["state_admission_performed"] is False


@pytest.mark.parametrize("timestamp", [None, "2026-02-30T12:00:00Z", "2026-10-03T08:00:00-04:00"])
def test_declared_measurements_require_valid_utc_context_before_publication(retained, tmp_path, timestamp):
    reference = deepcopy(retained["reference"])
    reference["provenance"]["kind"] = "declared_measurements"
    reference["context"]["valid_time_utc"] = timestamp
    for datum in reference["observations"][0]["quantities"].values():
        datum["uncertainty"].update(kind="declared_absolute_bound", absolute_bound=0.1)
        datum["instrument_ref"] = "declared-instrument-not-authenticated"
    seal(reference)
    destination = tmp_path / "invalid-measurement"
    with pytest.raises(ValueError):
        workflow.run(retained["original"], reference, retained["policy"], destination)
    assert not destination.exists()


@pytest.mark.parametrize("datum_error", ["gauge_unit", "zero_uncertainty", "missing_instrument"])
def test_measurement_contract_cannot_claim_gauge_pressure_or_unbounded_certainty(retained, tmp_path, datum_error):
    reference = deepcopy(retained["reference"])
    reference["provenance"]["kind"] = "declared_measurements"
    reference["context"]["valid_time_utc"] = "2026-10-03T12:00:00Z"
    for datum in reference["observations"][0]["quantities"].values():
        datum["uncertainty"].update(kind="declared_absolute_bound", absolute_bound=0.1)
        datum["instrument_ref"] = "declared-instrument-not-authenticated"
    datum = reference["observations"][0]["quantities"]["pressure_pa"]
    if datum_error == "gauge_unit":
        datum["unit"] = "Pa gauge"
    elif datum_error == "zero_uncertainty":
        datum["uncertainty"]["absolute_bound"] = 0.0
    else:
        datum["instrument_ref"] = None
    seal(reference)
    destination = tmp_path / "invalid-measurement"
    with pytest.raises(ValueError):
        workflow.run(retained["original"], reference, retained["policy"], destination)
    assert not destination.exists()


@pytest.mark.parametrize("mutation", ["provider", "version"])
def test_coherently_resealed_verifier_runtime_cannot_relabel_fixed_provider(retained, tmp_path, mutation):
    directory = tmp_path / "foreign-runtime"
    shutil.copytree(retained["directory"], directory)
    workspace, results, executions = _occurrences(directory)
    result, execution = results[VERIFY], executions[VERIFY]
    result["runtime"][mutation] = "untrusted.saved-provider.v999"
    execution["runtime"] = deepcopy(result["runtime"])
    seal(result)
    seal(execution)
    write_json(directory / "workspace.json", workspace)
    with _no_providers(), pytest.raises(ValueError):
        workflow.inspect(directory)


def test_comparison_verification_identity_cannot_reuse_science_verification_occurrence(retained, tmp_path):
    directory = tmp_path / "duplicated-verification-identity"
    shutil.copytree(retained["directory"], directory)
    workspace, results, _ = _occurrences(directory)
    science_id = results[atmosphere._operation_ids(retained["request"])[1]]["data"]["verification_id"]
    payload = results[VERIFY]["data"]
    payload["comparison_verification_id"] = science_id
    seal(results[VERIFY])
    write_json(directory / "workspace.json", workspace)
    write_json(directory / "comparison-verification.json", payload)
    with _no_providers(), pytest.raises(ValueError):
        workflow.inspect(directory)


@pytest.mark.parametrize("input_name", ["reference_source", "atmospheric_candidate", "atmospheric_verification", "policy"])
def test_comparison_parameters_cannot_replace_retained_evidence_with_just_a_label(retained, tmp_path, input_name):
    directory = tmp_path / "unbound-input"
    shutil.copytree(retained["directory"], directory)
    workspace, results, executions = _occurrences(directory)
    comparison, execution = results[COMPARE], executions[COMPARE]
    comparison["parameters"][input_name] = {"source_ref": "claimed but not retained scientific evidence"}
    execution["parameters"] = deepcopy(comparison["parameters"])
    seal(comparison)
    seal(execution)
    write_json(directory / "workspace.json", workspace)
    with _no_providers(), pytest.raises((ValueError, KeyError, TypeError)):
        workflow.inspect(directory)


@pytest.mark.parametrize("kind", ["symlink", "non_regular"])
def test_reference_cli_preflight_refuses_before_reading_symlinks_or_fifo_like_input(retained, tmp_path, monkeypatch, kind):
    reference_path = tmp_path / "reference.json"
    policy_path = tmp_path / "policy.json"
    write_json(reference_path, retained["reference"])
    write_json(policy_path, retained["policy"])
    # Model the boundary portably, including Windows environments where real
    # symlinks require extra privilege and FIFOs are not available.
    original_lstat = Path.lstat
    fields = list(reference_path.lstat())
    fields[0] = (stat.S_IFLNK if kind == "symlink" else stat.S_IFIFO) | 0o600
    fake_stat = os.stat_result(fields)
    monkeypatch.setattr(Path, "lstat", lambda path: fake_stat if path == reference_path else original_lstat(path))
    open_file = os.open

    def refuse_reference_open(path, flags, *args, **kwargs):
        if Path(path) == reference_path:
            raise AssertionError("Untrusted nonregular reference input reached the OS reader")
        return open_file(path, flags, *args, **kwargs)

    monkeypatch.setattr(atmosphere_cli.os, "open", refuse_reference_open)
    destination = tmp_path / "preflight-refused"
    with _no_providers():
        status = atmosphere_cli.main(["compare", "run", str(retained["original"]),
                                      "--reference", str(reference_path), "--policy", str(policy_path),
                                      "--output-dir", str(destination)])
    assert status == 1
    assert not destination.exists()


@pytest.mark.parametrize("artifact", ["workspace.json", "atmosphere-request.json", "reference.json", "policy.json", "preservation.json", "comparison-verification.json"])
def test_comparison_bundle_byte_budget_is_checked_before_generic_session_reader(retained, tmp_path, artifact):
    directory = tmp_path / "oversized-comparison"
    shutil.copytree(retained["directory"], directory)
    with (directory / artifact).open("wb") as stream:
        stream.truncate(8 * 1024 * 1024 + 1)
    with patch.object(Session, "from_workspace", side_effect=AssertionError("unbounded generic reader")):
        with pytest.raises(ValueError, match="budget"):
            workflow.inspect(directory)


@pytest.mark.parametrize("profile", ["dry", "moist"])
def test_historical_measurements_and_equivalent_utc_syntax_do_not_imply_expiry(tmp_path, profile):
    request = dry_request() if profile == "dry" else moist_request()
    request["reference"]["context"] = {
        "source_kind": "declared_environment", "source_ref": "historical-declared-environment",
        "valid_time_utc": "2000-01-01T00:00:00Z"}
    original = tmp_path / "historical-atmosphere"
    atmosphere.run(request, original)
    reference = example_reference(request)
    reference["provenance"].update(kind="declared_measurements", independent_of_candidate=True)
    reference["context"]["valid_time_utc"] = "2000-01-01T00:00:00+00:00"
    for datum in reference["observations"][0]["quantities"].values():
        datum["uncertainty"].update(kind="declared_absolute_bound", absolute_bound=0.1)
        datum["instrument_ref"] = "declared-historical-instrument"
        datum["calibration_ref"] = "declared-calibration-not-authenticated"
    seal(reference)
    directory = tmp_path / "historical-comparison"
    inspected = workflow.run(original, reference, example_policy(reference), directory)
    assert inspected["status"] == "LOCAL" and inspected["agreement_status"] == "PASS"
    _, results, _ = _occurrences(directory)
    claims = results[COMPARE]["data"]["claims"]
    assert claims["measurement_authenticity_established"] is False
    assert claims["calibration_validation"] is False
    assert claims["physical_validation"] == "not_established"


def test_declared_published_source_url_is_retained_without_fetch_or_authentication(retained, tmp_path):
    reference = deepcopy(retained["reference"])
    reference["provenance"].update(kind="published_reference", independent_of_candidate=True,
                                  source_url="https://example.invalid/reference-table")
    for datum in reference["observations"][0]["quantities"].values():
        datum["uncertainty"].update(kind="rounding_bound", absolute_bound=0.05)
    seal(reference)
    with patch("urllib.request.urlopen", side_effect=AssertionError("unrequested reference retrieval")):
        with patch("socket.create_connection", side_effect=AssertionError("unrequested network connection")):
            inspected = workflow.run(retained["original"], reference, example_policy(reference), tmp_path / "offline-reference")
    assert inspected["status"] == "LOCAL" and inspected["agreement_status"] == "PASS"
    assert read_json(tmp_path / "offline-reference" / "reference.json") == reference


def _rebind_comparison_verification(results, executions):
    comparison, verification = results[COMPARE], results[VERIFY]
    verification["parameters"]["candidate"] = deepcopy(comparison)
    executions[VERIFY]["parameters"] = deepcopy(verification["parameters"])
    payload = verification["data"]
    payload["candidate_record_digest"] = comparison["record_digest"]
    payload["report"]["candidate_digest"] = comparison["data"]["record_digest"]
    seal(payload["report"])
    seal(verification)
    seal(executions[VERIFY])


def _assert_static_only_forgery_is_not_exportable(directory, tmp_path):
    before = _contents(directory)
    with _no_providers():
        inspected = workflow.inspect(directory)
    assert inspected["status"] == "LOCAL" and inspected["verification_status"] == "PASS"
    with _no_providers(numerical=False):
        with patch("ciw.atmosphere_comparison.compare", side_effect=AssertionError("comparator replay")):
            with pytest.raises(ValueError, match="[Rr]ecomputation differs|verification differs"):
                workflow.verify_retained(directory)
            for name, export in (("forged.json", workflow.export_json), ("forged.csv", workflow.export_csv)):
                output = tmp_path / name
                with pytest.raises(ValueError, match="[Rr]ecomputation differs|verification differs"):
                    export(directory, output)
                assert not output.exists()
    assert _contents(directory) == before


def test_coherent_arithmetic_forgery_requires_fresh_independent_verification(retained, tmp_path):
    directory = tmp_path / "arithmetic-forgery"
    shutil.copytree(retained["directory"], directory)
    workspace, results, executions = _occurrences(directory)
    comparison = results[COMPARE]
    comparison["data"]["rows"][0]["signed_difference"] = 0.5
    seal(comparison["data"])
    seal(comparison)
    _rebind_comparison_verification(results, executions)
    write_json(directory / "workspace.json", workspace)
    write_json(directory / "comparison-verification.json", results[VERIFY]["data"])
    _assert_static_only_forgery_is_not_exportable(directory, tmp_path)


def _scientific_forgery(retained, tmp_path):
    directory = tmp_path / "scientific-forgery"
    shutil.copytree(retained["directory"], directory)
    workspace, results, executions = _occurrences(directory)
    compile_id, verify_id = atmosphere._operation_ids(retained["request"])
    candidate, verification = results[compile_id], results[verify_id]
    # Interior density is deliberately absent from the origin T/p reference.
    # Correct comparison arithmetic therefore cannot qualify this altered law.
    candidate["data"]["profile"]["density_kg_per_m3"][1] *= 1.001
    seal(candidate["data"])
    seal(candidate)
    verification["parameters"]["candidate"] = deepcopy(candidate)
    executions[verify_id]["parameters"] = deepcopy(verification["parameters"])
    payload = verification["data"]
    payload["candidate_record_digest"] = candidate["record_digest"]
    payload["report"]["candidate_digest"] = candidate["data"]["record_digest"]
    seal(payload["report"])
    seal(verification)
    seal(executions[verify_id])
    comparison = results[COMPARE]
    comparison["parameters"]["atmospheric_candidate"] = deepcopy(candidate)
    comparison["parameters"]["atmospheric_verification"] = deepcopy(verification)
    executions[COMPARE]["parameters"] = deepcopy(comparison["parameters"])
    comparison["data"]["atmosphere_result_digest"] = candidate["data"]["record_digest"]
    comparison["data"]["source_record_digest"] = candidate["record_digest"]
    comparison["data"]["recomputed_report_digest"] = payload["report"]["record_digest"]
    seal(comparison["data"])
    seal(comparison)
    seal(executions[COMPARE])
    report = results[VERIFY]["data"]["report"]
    for name in ("atmosphere_result_digest", "source_record_digest", "recomputed_report_digest"):
        report[name] = comparison["data"][name]
    _rebind_comparison_verification(results, executions)
    preservation = atmosphere._modules(retained["request"])[3].build(
        retained["request"], candidate["data"], payload["report"])
    write_json(directory / "workspace.json", workspace)
    write_json(directory / "preservation.json", preservation)
    write_json(directory / "comparison-verification.json", results[VERIFY]["data"])
    return directory


def test_coherent_scientific_forgery_cannot_hide_behind_correct_reference_arithmetic(retained, tmp_path):
    directory = _scientific_forgery(retained, tmp_path)
    _assert_static_only_forgery_is_not_exportable(directory, tmp_path)


@pytest.mark.parametrize("phase", ["comparator", "verifier"])
def test_direct_protocol_callbacks_freshly_refuse_coherent_scientific_forgery(retained, tmp_path, phase):
    directory = _scientific_forgery(retained, tmp_path)
    stored, _, _, comparison, _ = workflow._read(directory)
    operation = COMPARE if phase == "comparator" else VERIFY
    parameters = comparison["parameters"] if phase == "comparator" else {"candidate": comparison}
    callback = workflow._compare if phase == "comparator" else workflow._verify
    with _no_providers(numerical=False):
        with pytest.raises(ValueError, match="Fresh atmospheric verification differs"):
            callback(stored.run, parameters)
    # The actual dispatcher retains a refused attempt under explicit trusted
    # bindings; it cannot bypass source science by invoking the new operation.
    protocol = Session(stored.run, tmp_path / "direct-protocol", operations=workflow.registry())
    with patch("ciw.atmosphere_compiler.compile_atmosphere", side_effect=AssertionError("dry compiler replay")):
        with patch("ciw.atmosphere_moist_compiler.compile_atmosphere", side_effect=AssertionError("moist compiler replay")):
            refused = atmosphere._execute(protocol, operation, parameters)
    assert refused["status"] == "refused"
    assert refused["execution"]["refusal"]["code"] == "invalid_operation"
    assert "Fresh atmospheric verification differs" in refused["execution"]["refusal"]["message"]
    assert not protocol.results and len(protocol.executions) == 1


@pytest.fixture(scope="module")
def retained_benchmark(tmp_path_factory):
    directory = tmp_path_factory.mktemp("comparison-benchmark-audit") / "benchmark"
    workflow.run_benchmark(directory)
    return directory


@pytest.mark.parametrize("kind", ["science", "comparison"])
def test_distinct_benchmark_cases_cannot_share_coherently_rebound_verification_occurrence(retained_benchmark, tmp_path, kind):
    directory = tmp_path / "duplicated-benchmark-occurrence"
    shutil.copytree(retained_benchmark, directory)
    cases = read_json(directory / "benchmark.json")["cases"]
    first = directory / cases[0]["comparison_directory"]
    second = directory / cases[1]["comparison_directory"]
    source = second.parent / "atmosphere"
    _, first_results, _ = _occurrences(first)
    workspace, results, executions = _occurrences(second)
    if kind == "science":
        duplicate = first_results[atmosphere.MOIST_VERIFY]["data"]["verification_id"]
        old_verification = results[atmosphere.MOIST_VERIFY]
        old_verification["data"]["verification_id"] = duplicate
        seal(old_verification)
        # The actual source and intentional comparison copy both retain the
        # same relabeled occurrence, so per-case copying checks still pass.
        source_workspace, source_results, _ = _occurrences(source)
        source_results[atmosphere.MOIST_VERIFY]["data"]["verification_id"] = duplicate
        seal(source_results[atmosphere.MOIST_VERIFY])
        write_json(source / "workspace.json", source_workspace)
        write_json(source / "verification.json", source_results[atmosphere.MOIST_VERIFY]["data"])
        write_json(source / (old_verification["result_id"] + ".json"), old_verification)
        comparison = results[COMPARE]
        comparison["parameters"]["atmospheric_verification"] = deepcopy(old_verification)
        executions[COMPARE]["parameters"] = deepcopy(comparison["parameters"])
        comparison["data"]["verification_id"] = duplicate
        seal(comparison["data"])
        seal(comparison)
        seal(executions[COMPARE])
        results[VERIFY]["data"]["report"]["verification_id"] = duplicate
        _rebind_comparison_verification(results, executions)
    else:
        duplicate = first_results[VERIFY]["data"]["comparison_verification_id"]
        results[VERIFY]["data"]["comparison_verification_id"] = duplicate
        seal(results[VERIFY])
    write_json(second / "workspace.json", workspace)
    write_json(second / "comparison-verification.json", results[VERIFY]["data"])
    for record in list(results.values()) + list(executions.values()):
        identity = record["result_id"] if record["schema"] == "ciw.operation-result.v1" else record["execution_id"]
        write_json(second / (identity + ".json"), record)
    summary = read_json(directory / "benchmark.json")
    entry = summary["cases"][1]
    entry["comparison_verification_id"] = results[VERIFY]["data"]["comparison_verification_id"]
    entry["comparison_digest"] = results[COMPARE]["data"]["record_digest"]
    entry["recomputed_verification_report_digest"] = results[VERIFY]["data"]["report"]["record_digest"]
    seal(summary)
    write_json(directory / "benchmark.json", summary)
    # Every isolated source and comparison remains valid and freshly
    # computable. Only the cross-case event identity invariant rejects it.
    with _no_providers():
        assert atmosphere.inspect(source)["status"] == "LOCAL"
        assert workflow.inspect(second)["status"] == "LOCAL"
        with pytest.raises(ValueError, match="Distinct benchmark cases cannot share scientific occurrence identities"):
            workflow.inspect_benchmark(directory)
    assert workflow.verify_retained(second)["verification_status"] == "PASS"
