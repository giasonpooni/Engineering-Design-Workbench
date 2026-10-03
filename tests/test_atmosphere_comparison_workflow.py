"""User-facing atmospheric reference comparison lifecycles and decisions."""
from copy import deepcopy
import csv
import json
from pathlib import Path
import stat
from unittest.mock import patch

import pytest

from ciw import atmosphere_cli
from ciw import atmosphere_workflow as atmosphere
from ciw import atmosphere_comparison_workflow as workflow
from ciw.atmosphere_comparison_contract import example_policy, example_reference
from ciw.atmosphere_contract import example_request as dry_request
from ciw.atmosphere_moist_contract import example_request as moist_request
from ciw.atmosphere_reference_benchmark import REFERENCE_POINTS, cases
from ciw.operations.runner import check_seal, seal
from ciw.session import read_json, write_json


def _contents(directory):
    return {str(path.relative_to(directory)): path.read_bytes()
            for path in directory.rglob("*") if path.is_file()}


def _comparison(directory):
    return workflow._read(directory)[3]["data"]


def _report(directory):
    return workflow._read(directory)[4]["data"]["report"]


@pytest.fixture(scope="module", params=["dry", "moist"])
def retained(tmp_path_factory, request):
    declaration = dry_request() if request.param == "dry" else moist_request()
    root = tmp_path_factory.mktemp("comparison-workflow-" + request.param)
    source = root / "atmosphere"
    atmosphere.run(declaration, source)
    reference = example_reference(declaration)
    policy = example_policy(reference)
    directory = root / "comparison"
    reply = workflow.run(source, reference, policy, directory)
    return {"profile": request.param, "request": declaration, "source": source,
            "reference": reference, "policy": policy, "directory": directory,
            "reply": reply}


def test_example_compares_declared_origin_without_promoting_it_to_measurement(retained):
    reference = read_json(retained["directory"] / "reference.json")
    comparison = _comparison(retained["directory"])
    assert reference == retained["reference"]
    assert reference["provenance"]["kind"] == "synthetic_fixture"
    assert reference["provenance"]["independent_of_candidate"] is False
    assert comparison["agreement_status"] == "PASS"
    assert comparison["qualification"]["action"] == "LOCAL"
    assert len(comparison["rows"]) == 2
    assert all(row["status"] == "PASS" for row in comparison["rows"])
    assert comparison["claims"]["measurement_authenticity_established"] is False
    assert comparison["claims"]["calibration_validation"] is False
    assert comparison["claims"]["physical_validation"] == "not_established"


def test_comparison_freshly_verifies_and_exports_json_and_scalar_csv(retained, tmp_path):
    original = _contents(retained["source"])
    before = _contents(retained["directory"])
    with patch("ciw.atmosphere_compiler.compile_atmosphere", side_effect=AssertionError("dry compilation")), \
            patch("ciw.atmosphere_moist_compiler.compile_atmosphere", side_effect=AssertionError("moist compilation")):
        verified = workflow.verify_retained(retained["directory"])
        workflow.export_json(retained["directory"], tmp_path / "comparison.json")
        workflow.export_csv(retained["directory"], tmp_path / "comparison.csv")
    assert verified["status"] == "LOCAL"
    assert verified["fresh_numerical_verification"] is True
    payload = read_json(tmp_path / "comparison.json")
    check_seal(payload)
    assert "temperature_k" in str(payload) and "pressure_pa" in str(payload)
    with (tmp_path / "comparison.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 2
    assert all(row["status"] == "PASS" for row in rows)
    assert {row["field"] for row in rows} == {"temperature_k", "pressure_pa"}
    assert _contents(retained["source"]) == original
    assert _contents(retained["directory"]) == before


def test_honest_reference_disagreement_remains_local_verified_and_exportable(retained, tmp_path):
    reference = deepcopy(retained["reference"])
    reference["observations"][0]["quantities"]["temperature_k"]["value"] += 5.0
    seal(reference)
    directory = tmp_path / "disagreement"
    original = _contents(retained["source"])
    reply = workflow.run(retained["source"], reference, retained["policy"], directory)
    assert reply["status"] == "LOCAL"
    comparison = _comparison(directory)
    assert comparison["agreement_status"] == "FAIL"
    assert sorted(row["status"] for row in comparison["rows"]) == ["FAIL", "PASS"]
    report = _report(directory)
    assert report["status"] == "PASS"
    assert all(check["status"] == "PASS" for check in report["checks"])
    before = _contents(directory)
    assert workflow.verify_retained(directory)["status"] == "LOCAL"
    workflow.export_json(directory, tmp_path / "disagreement.json")
    workflow.export_csv(directory, tmp_path / "disagreement.csv")
    assert "FAIL" in (tmp_path / "disagreement.csv").read_text(encoding="utf-8")
    assert _contents(directory) == before and _contents(retained["source"]) == original


@pytest.mark.parametrize("profile", ["dry", "moist"])
def test_declared_measurements_accept_matching_context_without_claiming_authentication(tmp_path, profile):
    declaration = dry_request() if profile == "dry" else moist_request()
    declaration["reference"]["context"] = {
        "source_kind": "declared_environment", "source_ref": "facility.boundary-declaration",
        "valid_time_utc": "2026-10-03T07:00:00Z"}
    source = tmp_path / "atmosphere"
    atmosphere.run(declaration, source)
    reference = example_reference(declaration)
    reference["provenance"].update(kind="declared_measurements", source_ref="fixture.sensor-log",
                                   independent_of_candidate=True)
    for field, datum in reference["observations"][0]["quantities"].items():
        datum["uncertainty"] = {
            "kind": "declared_expanded", "absolute_bound": 0.2 if field == "temperature_k" else 20.0,
            "coverage_factor": 2.0, "reference": "Declared test-fixture sensor allowance."}
        datum["instrument_ref"] = "fixture.thermometer" if field == "temperature_k" else "fixture.barometer"
        datum["calibration_ref"] = "fixture.declared-calibration-reference"
    seal(reference)
    policy = example_policy(reference)
    directory = tmp_path / "measurement-comparison"
    assert workflow.run(source, reference, policy, directory)["status"] == "LOCAL"
    comparison = _comparison(directory)
    assert comparison["agreement_status"] == "PASS"
    assert comparison["claims"]["independence_declared"] is True
    assert comparison["claims"]["independence_established"] is False
    assert comparison["claims"]["measurement_authenticity_established"] is False
    assert comparison["claims"]["calibration_validation"] is False
    assert comparison["claims"]["physical_validation"] == "not_established"
    assert read_json(directory / "reference.json") == reference


@pytest.mark.parametrize("alignment", ["frame", "height_origin_m", "valid_time_utc", "height_m"])
def test_misalignment_is_retained_as_a_verified_refusal_and_cannot_export(retained, tmp_path, alignment):
    reference = deepcopy(retained["reference"])
    if alignment == "frame":
        reference["context"][alignment] = "other.local_enu.v1"
    elif alignment == "height_origin_m":
        reference["context"][alignment] += 1.0
    elif alignment == "valid_time_utc":
        reference["context"][alignment] = "2026-10-03T07:00:00Z"
    else:
        reference["observations"][0][alignment] = 1.0
    seal(reference)
    directory = tmp_path / "misaligned"
    before = _contents(retained["source"])
    assert workflow.run(retained["source"], reference, retained["policy"], directory)["status"] == "REFUSE"
    comparison = _comparison(directory)
    assert comparison["qualification"]["action"] == "REFUSE"
    assert _report(directory)["status"] == "PASS"
    assert workflow.verify_retained(directory)["status"] == "REFUSE"
    for suffix, exporter in (("json", workflow.export_json), ("csv", workflow.export_csv)):
        output = tmp_path / ("blocked." + suffix)
        with pytest.raises(ValueError, match="LOCAL"):
            exporter(directory, output)
        assert not output.exists()
    assert _contents(retained["source"]) == before


@pytest.mark.parametrize("unsupported", ["wet_field", "humidity_convention"])
def test_unavailable_quantity_or_humidity_convention_expands_without_fabricating_rows(tmp_path, unsupported):
    declaration = dry_request() if unsupported == "wet_field" else moist_request()
    source = tmp_path / "atmosphere"
    atmosphere.run(declaration, source)
    reference = example_reference(declaration)
    reference["context"]["humidity_convention"] = "pressure_enhanced_relative_humidity"
    reference["observations"][0]["quantities"] = {
        "relative_humidity": {
            "value": 0.5, "unit": "1",
            "uncertainty": {"kind": "exact_fixture", "absolute_bound": 0.0,
                            "coverage_factor": None, "reference": "Synthetic convention boundary."},
            "instrument_ref": None, "calibration_ref": None}}
    seal(reference)
    policy = example_policy(reference)
    directory = tmp_path / "unsupported"
    assert workflow.run(source, reference, policy, directory)["status"] == "EXPAND"
    comparison = _comparison(directory)
    assert comparison["qualification"]["action"] == "EXPAND"
    assert comparison["agreement_status"] == "NOT_EVALUATED"
    assert all(row["status"] == "NOT_EVALUATED" for row in comparison["rows"])
    assert _report(directory)["status"] == "PASS"
    assert workflow.verify_retained(directory)["status"] == "EXPAND"
    with pytest.raises(ValueError, match="LOCAL"):
        workflow.export_json(directory, tmp_path / "unsupported.json")
    assert not (tmp_path / "unsupported.json").exists()


@pytest.mark.parametrize("artifact", ["run", "json", "csv"])
def test_destinations_are_create_only(retained, tmp_path, artifact):
    if artifact == "run":
        before = _contents(retained["directory"])
        with pytest.raises(FileExistsError):
            workflow.run(retained["source"], retained["reference"], retained["policy"], retained["directory"])
        assert _contents(retained["directory"]) == before
    else:
        output = tmp_path / ("already-present." + artifact)
        output.write_bytes(b"keep this existing artifact")
        exporter = workflow.export_json if artifact == "json" else workflow.export_csv
        with pytest.raises(FileExistsError):
            exporter(retained["directory"], output)
        assert output.read_bytes() == b"keep this existing artifact"


@pytest.mark.parametrize("profile", ["dry", "moist"])
def test_cli_example_and_complete_comparison_lifecycle(tmp_path, capsys, profile):
    declaration = dry_request() if profile == "dry" else moist_request()
    source = tmp_path / "atmosphere"
    atmosphere.run(declaration, source)
    reference, policy = tmp_path / "reference.json", tmp_path / "policy.json"
    arguments = ["compare", "example", "--profile", profile,
                 "--reference-output", str(reference), "--policy-output", str(policy)]
    assert atmosphere_cli.main(arguments) == 0
    assert read_json(reference) == example_reference(declaration)
    assert read_json(policy) == example_policy(read_json(reference))
    before_reference, before_policy = reference.read_bytes(), policy.read_bytes()
    assert atmosphere_cli.main(arguments) == 1
    assert reference.read_bytes() == before_reference and policy.read_bytes() == before_policy
    capsys.readouterr()
    directory = tmp_path / "comparison"
    assert atmosphere_cli.main(["compare", "run", str(source), "--reference", str(reference),
                                "--policy", str(policy), "--output-dir", str(directory)]) == 0
    assert atmosphere_cli.main(["compare", "inspect", str(directory)]) == 0
    assert atmosphere_cli.main(["compare", "verify", str(directory)]) == 0
    for format in ("json", "csv"):
        assert atmosphere_cli.main(["compare", "export", str(directory), "--format", format,
                                    "--output", str(tmp_path / ("export." + format))]) == 0
    assert '"status": "LOCAL"' in capsys.readouterr().out


@pytest.mark.parametrize("command", ["run", "inspect", "verify", "json", "csv"])
def test_cli_disagreement_uses_exit_two_even_when_correct_and_exported(retained, tmp_path, command, capsys):
    reference = deepcopy(retained["reference"])
    reference["observations"][0]["quantities"]["temperature_k"]["value"] += 5.0
    seal(reference)
    reference_path, policy_path = tmp_path / "reference.json", tmp_path / "policy.json"
    write_json(reference_path, reference)
    write_json(policy_path, retained["policy"])
    directory = tmp_path / "disagreement"
    if command == "run":
        arguments = ["compare", "run", str(retained["source"]), "--reference", str(reference_path),
                     "--policy", str(policy_path), "--output-dir", str(directory)]
    else:
        workflow.run(retained["source"], reference, retained["policy"], directory)
        arguments = ["compare", command if command in {"inspect", "verify"} else "export", str(directory)]
        if command in {"json", "csv"}:
            arguments += ["--format", command, "--output", str(tmp_path / ("disagreement." + command))]
    assert atmosphere_cli.main(arguments) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["status"] in {"LOCAL", "exported"}
    if command in {"json", "csv"}:
        assert (tmp_path / ("disagreement." + command)).is_file()


def test_published_reference_benchmark_is_four_fixed_independent_points(tmp_path):
    root = tmp_path / "benchmark"
    reply = workflow.run_benchmark(root)
    assert reply["status"] == "LOCAL"
    observed = []
    occurrences = set()
    for name, temperature, pressure in REFERENCE_POINTS:
        comparison_directory = root / "cases" / name / "comparison"
        assert (comparison_directory / "policy.json").is_file()
        comparison = _comparison(comparison_directory)
        assert comparison["agreement_status"] == "PASS"
        assert _report(comparison_directory)["status"] == "PASS"
        reference = read_json(comparison_directory / "reference.json")
        observation = reference["observations"][0]["quantities"]["liquid_water_saturation_pressure_pa"]
        assert observation["value"] == pressure
        assert observation["uncertainty"]["absolute_bound"] == 0.05
        assert reference["provenance"]["kind"] == "published_reference"
        assert reference["provenance"]["independent_of_candidate"] is True
        assert comparison["claims"]["independence_established"] is False
        assert comparison["claims"]["physical_validation"] == "not_established"
        workspace = read_json(comparison_directory / "workspace.json")
        # Count the retained comparison once: its old source occurrences are
        # intentional copies, while each independent case has distinct events.
        case_occurrences = {row["result_id"] for row in workspace["results"]}
        case_occurrences.update(row["execution_id"] for row in workspace["executions"])
        for result in workspace["results"]:
            if result["operation_id"] == workflow.VERIFY:
                case_occurrences.add(result["data"]["comparison_verification_id"])
            elif result["role"] == "verification":
                case_occurrences.add(result["data"]["verification_id"])
        assert len(case_occurrences) == 10
        assert occurrences.isdisjoint(case_occurrences)
        occurrences.update(case_occurrences)
        observed.append(temperature)
    assert observed == [293.15, 298.15, 303.15, 308.15]
    assert len(occurrences) == 40


def test_tightening_engineering_allowance_retains_correct_benchmark_disagreement(tmp_path):
    case = cases()[1]
    source = tmp_path / "atmosphere"
    atmosphere.run(case["request"], source)
    strict = deepcopy(case["policy"])
    strict["thresholds"]["liquid_water_saturation_pressure_pa"]["relative_tolerance"] = 0.0
    seal(strict)
    directory = tmp_path / "strict"
    assert workflow.run(source, case["reference"], strict, directory)["status"] == "LOCAL"
    assert _comparison(directory)["agreement_status"] == "FAIL"
    assert _report(directory)["status"] == "PASS"
    assert workflow.verify_retained(directory)["status"] == "LOCAL"


def test_cli_benchmark_creates_once_and_reports_the_declared_scope(tmp_path, capsys):
    root = tmp_path / "benchmark"
    assert atmosphere_cli.main(["compare", "benchmark", "--output-dir", str(root)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "LOCAL"
    before = _contents(root)
    assert atmosphere_cli.main(["compare", "benchmark-inspect", str(root)]) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["fresh_numerical_verification"] is False
    assert atmosphere_cli.main(["compare", "benchmark-verify", str(root)]) == 0
    verified = json.loads(capsys.readouterr().out)
    assert verified["fresh_numerical_verification"] is True
    assert verified["case_count"] == inspected["case_count"] == 4
    assert {case["comparison_result_id"] for case in inspected["cases"]} == {
        case["comparison_result_id"] for case in verified["cases"]}
    assert _contents(root) == before
    assert atmosphere_cli.main(["compare", "benchmark", "--output-dir", str(root)]) == 1
    assert _contents(root) == before


@pytest.mark.parametrize("profile", ["dry", "moist"])
@pytest.mark.parametrize("surface", ["symlink", "fifo"])
def test_ordinary_atmospheric_request_preflight_refuses_nonregular_surface_before_open(tmp_path, profile, surface):
    from types import SimpleNamespace
    request = tmp_path / "request.json"
    destination = tmp_path / "run"
    file_mode = stat.S_IFLNK if surface == "symlink" else stat.S_IFIFO
    # Exercise the real stat gate on both supported operating systems without
    # requiring Windows symlink privileges or an actual blocking pipe.
    with patch.object(Path, "lstat", return_value=SimpleNamespace(st_mode=file_mode)), \
            patch.object(atmosphere_cli.os, "open", side_effect=AssertionError("opened unsafe input")), \
            patch.object(atmosphere, "run", side_effect=AssertionError("provider reached")):
        arguments = [] if profile == "dry" else ["moist"]
        assert atmosphere_cli.main(arguments + ["run", str(request), "--output-dir", str(destination)]) == 1
    assert not destination.exists()


def test_cli_example_checks_both_create_only_destinations_before_writing_either(tmp_path):
    reference = tmp_path / "reference.json"
    policy = tmp_path / "policy.json"
    policy.write_bytes(b"existing policy")
    assert atmosphere_cli.main(["compare", "example", "--reference-output", str(reference),
                                "--policy-output", str(policy)]) == 1
    assert not reference.exists()
    assert policy.read_bytes() == b"existing policy"
