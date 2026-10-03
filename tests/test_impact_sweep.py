"""Enumerated design conditions remain distinct from numerical qualification."""
from copy import deepcopy
from pathlib import Path
import shutil
from unittest.mock import patch

import pytest

from ciw import impact_sweep as sweep
from ciw.control_contracts import load
from ciw.impact_contract import example_request
from ciw.operations.runner import seal
from ciw.session import write_json


def _elastic_manifest():
    return {"schema": sweep.REQUEST_SCHEMA, "base_request": example_request(),
            "axes": {"initial_speed_m_per_s": [1.0, 2.0]},
            "requirements": [{"quantity": "peak_force_n", "unit": "N", "operator": "<=", "limit": 150.0}]}


def _contents(directory):
    return {path.relative_to(directory): path.read_bytes()
            for path in directory.rglob("*") if path.is_file()}


@pytest.fixture(scope="module")
def crush_bundle(tmp_path_factory):
    directory = tmp_path_factory.mktemp("crush-envelope") / "scenarios"
    report = sweep.run_sweep(sweep.example_manifest(), directory)
    return directory, report


def test_default_full_crush_grid_retains_two_separate_verdicts(crush_bundle):
    directory, report = crush_bundle
    assert report["case_count"] == 6
    assert report["status"] == "LOCAL"
    assert report["requirements_status"] == "FAIL"
    assert report["requirements_counts"] == {"PASS": 5, "FAIL": 1, "UNRESOLVED": 0}
    assert report["claims"]["failure_probability_estimated"] is False
    assert report["claims"]["global_robustness_established"] is False
    execution_ids, verification_ids = set(), set()
    for row in report["cases"]:
        assert row["directory"] == f"case-{row['index']:03d}"
        inspected = row["inspection"]
        assert row["numerical_status"] == inspected["status"] == "LOCAL"
        assert inspected["preservation"]["verification_status"] == "VERIFIED"
        assert set(row["files"]) == {"request.json", "workspace.json", "verification.json", "preservation.json"}
        assert inspected["execution_id"] != inspected["verification_execution_id"]
        execution_ids.add(inspected["execution_id"])
        verification_ids.add(inspected["verification_id"])
        for requirement in row["requirements"]:
            assert requirement["value"] == inspected["metrics"]["primary"][requirement["quantity"]]
            assert requirement["status"] == ("PASS" if requirement["value"] <= requirement["limit"] else "FAIL")
    assert len(execution_ids) == len(verification_ids) == 6
    # Selected plastic-work histories satisfy their declared irreversible model.
    for row in report["cases"]:
        workspace = load(directory / row["directory"] / "workspace.json")
        result = next(item for item in workspace["results"] if item["operation_id"] == "impact.crush-contact.v1")
        trace = result["data"]["primary"]
        assert all(later >= earlier for earlier, later in zip(trace["plastic_work_j"], trace["plastic_work_j"][1:]))
    for limit in (80.0, 100.0):
        selected = [row for row in report["cases"] if row["coordinate"]["yield_force_n"] == limit]
        energy = [row["inspection"]["metrics"]["primary"]["initial_energy_j"] for row in selected]
        work = [row["inspection"]["metrics"]["primary"]["plastic_work_j"] for row in selected]
        residual = [row["inspection"]["metrics"]["primary"]["residual_compression_m"] for row in selected]
        assert energy == sorted(energy)
        assert work == sorted(work)
        assert residual == sorted(residual)


def test_inspection_reopens_all_cases_without_any_numeric_replay(crush_bundle):
    directory, report = crush_bundle
    before = _contents(directory)
    with patch("ciw.impact_crush_solver.simulate", side_effect=AssertionError("solver replay")), \
            patch("ciw.impact_crush_verification.verify", side_effect=AssertionError("verifier replay")), \
            patch("ciw.session.execute_operation", side_effect=AssertionError("operation replay")):
        assert sweep.inspect_sweep(directory) == report
    assert _contents(directory) == before


def test_explicit_verify_reaudits_samples_without_solver_or_new_occurrences(crush_bundle):
    directory, report = crush_bundle
    before = _contents(directory)
    with patch("ciw.impact_crush_solver.simulate", side_effect=AssertionError("solver replay")), \
            patch("ciw.session.execute_operation", side_effect=AssertionError("operation replay")):
        verified = sweep.verify_sweep(directory)
    assert verified["summary_ref"] == report["record_digest"]
    assert verified["status"] == "LOCAL" and verified["requirements_status"] == "FAIL"
    assert verified["fresh_execution"] is False
    assert all(row["fresh_numerical_verification"] is True for row in verified["cases"])
    assert all(row["fresh_execution"] is False for row in verified["cases"])
    assert _contents(directory) == before


def test_local_design_failure_is_distinct_from_refused_numerical_acceptance(tmp_path):
    manifest = _elastic_manifest()
    report = sweep.run_sweep(manifest, tmp_path / "design-failure")
    assert report["status"] == "LOCAL" and report["requirements_status"] == "FAIL"
    assert [row["requirements_status"] for row in report["cases"]] == ["PASS", "FAIL"]
    manifest["base_request"]["integration"]["steps_per_contact"] = 16
    refused = sweep.run_sweep(manifest, tmp_path / "numerical-refusal")
    assert refused["status"] == "REFUSE" and refused["requirements_status"] == "UNRESOLVED"
    assert all(row["requirements"][0]["value"] is None for row in refused["cases"])
    assert all(row["requirements"][0]["status"] == "UNRESOLVED" for row in refused["cases"])
    assert sweep.verify_sweep(tmp_path / "numerical-refusal")["requirements_status"] == "UNRESOLVED"


def test_scope_expansion_leaves_requirements_unresolved(tmp_path):
    manifest = _elastic_manifest()
    manifest["base_request"]["desired_observables"].append("damage")
    report = sweep.run_sweep(manifest, tmp_path / "expansion")
    assert report["status"] == "EXPAND" and report["requirements_status"] == "UNRESOLVED"
    assert all(row["numerical_status"] == "EXPAND" for row in report["cases"])
    assert all(row["requirements"][0]["value"] is None for row in report["cases"])


@pytest.mark.parametrize("phase", ["solver", "verifier"])
def test_failed_provider_attempts_are_retained_and_propagated(tmp_path, phase):
    manifest = _elastic_manifest()
    manifest["axes"] = {"initial_speed_m_per_s": [1.0]}
    target = "ciw.impact_solver.simulate" if phase == "solver" else "ciw.impact_verification.verify"
    directory = tmp_path / phase
    with patch(target, side_effect=RuntimeError("provider-private-detail")):
        report = sweep.run_sweep(manifest, directory)
    row = report["cases"][0]
    assert report["status"] == "REFUSE" and report["requirements_status"] == "UNRESOLVED"
    assert any(attempt["status"] == "refused" for attempt in row["inspection"]["executions"])
    assert set(row["files"]) == {"request.json", "workspace.json"}
    with patch(target, side_effect=AssertionError("replay")):
        assert sweep.inspect_sweep(directory) == report
        assert sweep.verify_sweep(directory)["status"] == "REFUSE"


@pytest.mark.parametrize("mutation", ["schema", "unknown_field", "empty_axes", "four_axes", "unknown_axis",
    "too_many_values", "duplicate", "nan", "boolean", "negative_mass", "unsupported_base",
    "case_budget", "empty_requirements", "too_many_requirements", "quantity", "unit", "operator",
    "limit", "requirement_field", "plastic_in_elastic"])
def test_manifest_rejection_occurs_before_destination_creation(tmp_path, mutation):
    manifest = _elastic_manifest()
    if mutation == "schema": manifest["schema"] = "unknown"
    elif mutation == "unknown_field": manifest["extra"] = True
    elif mutation == "empty_axes": manifest["axes"] = {}
    elif mutation == "four_axes": manifest["axes"] = {name: [1.0] for name in sweep.AXIS_UNITS}
    elif mutation == "unknown_axis": manifest["axes"] = {"damping_n_s_per_m": [1.0]}
    elif mutation == "too_many_values": manifest["axes"] = {"initial_speed_m_per_s": list(range(1, 8))}
    elif mutation == "duplicate": manifest["axes"] = {"initial_speed_m_per_s": [1, 1.0]}
    elif mutation == "nan": manifest["axes"] = {"initial_speed_m_per_s": [float("nan")]}
    elif mutation == "boolean": manifest["axes"] = {"initial_speed_m_per_s": [True]}
    elif mutation == "negative_mass": manifest["axes"] = {"mass_kg": [1.0, -1.0]}
    elif mutation == "unsupported_base": manifest["base_request"]["model"]["support"] = "plate"
    elif mutation == "case_budget": manifest["axes"] = {"mass_kg": list(range(1, 7)), "initial_speed_m_per_s": list(range(1, 7))}
    elif mutation == "empty_requirements": manifest["requirements"] = []
    elif mutation == "too_many_requirements": manifest["requirements"] *= 5
    elif mutation == "quantity": manifest["requirements"][0]["quantity"] = "hardness"
    elif mutation == "unit": manifest["requirements"][0]["unit"] = "kN"
    elif mutation == "operator": manifest["requirements"][0]["operator"] = "<"
    elif mutation == "limit": manifest["requirements"][0]["limit"] = True
    elif mutation == "requirement_field": manifest["requirements"][0]["confidence"] = 0.95
    else: manifest["requirements"][0].update(quantity="plastic_work_j", unit="J")
    destination = tmp_path / "invalid"
    with patch("ciw.impact_workflow.run", side_effect=AssertionError("invalid execution")):
        with pytest.raises(ValueError):
            sweep.run_sweep(manifest, destination)
    assert not destination.exists()


def test_any_invalid_crush_coordinate_rejects_whole_grid_before_writing(tmp_path):
    manifest = sweep.example_manifest()
    manifest["axes"]["yield_force_n"] = [80.0, 20.0]
    with pytest.raises(ValueError, match="yield_ratio"):
        sweep.run_sweep(manifest, tmp_path / "invalid-grid")
    assert not (tmp_path / "invalid-grid").exists()


def test_dimensional_order_is_independent_of_manifest_object_key_order():
    manifest = sweep.example_manifest()
    changed = deepcopy(manifest)
    changed["axes"] = dict(reversed(list(changed["axes"].items())))
    assert sweep._grid(sweep.validate_manifest(manifest)) == sweep._grid(sweep.validate_manifest(changed))
    assert manifest == sweep.example_manifest()


def test_validated_upper_grid_budget_and_greater_equal_requirement():
    manifest = _elastic_manifest()
    manifest["axes"] = {"mass_kg": [1, 2, 3, 4], "initial_speed_m_per_s": [1, 2, 3, 4, 5, 6]}
    manifest["requirements"] = [{"quantity": "restitution", "unit": "1", "operator": ">=", "limit": 0.9}]
    assert len(sweep._grid(sweep.validate_manifest(manifest))[1]) == 24


def test_resealed_missing_case_cannot_hide_a_declared_scenario(tmp_path, crush_bundle):
    directory = tmp_path / "missing-case"
    shutil.copytree(crush_bundle[0], directory)
    summary = load(directory / "summary.json")
    summary["cases"].pop()
    summary["case_count"] = 5
    seal(summary)
    write_json(directory / "summary.json", summary)
    shutil.rmtree(directory / "case-005")
    with pytest.raises(ValueError, match="every declared case"):
        sweep.inspect_sweep(directory)


@pytest.mark.parametrize("mutation", ["status", "verdict", "value", "directory", "file_ref", "coordinate", "claims"])
def test_resealed_aggregate_corruption_is_rejected(tmp_path, crush_bundle, mutation):
    directory = tmp_path / mutation
    shutil.copytree(crush_bundle[0], directory)
    summary = load(directory / "summary.json")
    row = summary["cases"][0]
    if mutation == "status": row["numerical_status"] = "REFUSE"
    elif mutation == "verdict": row["requirements_status"] = "FAIL"
    elif mutation == "value": row["requirements"][0]["value"] += 1.0
    elif mutation == "directory": row["directory"] = "../untrusted"
    elif mutation == "file_ref": row["files"]["verification.json"] = "sha256:" + "0" * 64
    elif mutation == "coordinate": row["coordinate"]["initial_speed_m_per_s"] = 1.5
    else: summary["claims"]["failure_probability_estimated"] = True
    seal(summary)
    write_json(directory / "summary.json", summary)
    with pytest.raises(ValueError, match="complete case evidence"):
        sweep.inspect_sweep(directory)


def test_exact_case_file_bytes_are_bound_even_when_json_values_are_identical(tmp_path, crush_bundle):
    directory = tmp_path / "changed-bytes"
    shutil.copytree(crush_bundle[0], directory)
    path = directory / "case-000" / "verification.json"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="complete case evidence"):
        sweep.inspect_sweep(directory)


def test_workspace_binding_accepts_more_than_eight_mib_with_a_separate_finite_budget(tmp_path):
    path = tmp_path / "workspace.json"
    path.write_bytes(b"x" * (sweep.MAX_DOCUMENT_BYTES + 1))
    assert sweep._file_ref(path, maximum=sweep.MAX_WORKSPACE_BYTES).startswith("sha256:")
    with pytest.raises(ValueError, match="bounded file"):
        sweep._file_ref(path)
    with path.open("wb") as stream:
        stream.truncate(sweep.MAX_WORKSPACE_BYTES + 1)
    with patch.object(Path, "open", side_effect=AssertionError("oversized read")):
        with pytest.raises(ValueError, match="bounded file"):
            sweep._file_ref(path, maximum=sweep.MAX_WORKSPACE_BYTES)


def test_oversized_case_is_rejected_before_workflow_open(tmp_path, crush_bundle):
    directory = tmp_path / "oversized"
    shutil.copytree(crush_bundle[0], directory)
    with (directory / "case-000" / "workspace.json").open("wb") as stream:
        stream.truncate(sweep.MAX_WORKSPACE_BYTES + 1)
    with patch("ciw.impact_workflow.inspect", side_effect=AssertionError("workflow open")):
        with pytest.raises(ValueError, match="bounded file"):
            sweep.inspect_sweep(directory)


def test_symlinked_case_artifacts_are_rejected_before_workflow_open(tmp_path, crush_bundle):
    directory = tmp_path / "symlinked"
    shutil.copytree(crush_bundle[0], directory)
    original = directory / "case-000" / "workspace.json"
    copy = tmp_path / "workspace.json"
    original.rename(copy)
    original.symlink_to(copy)
    with patch("ciw.impact_workflow.inspect", side_effect=AssertionError("workflow open")):
        with pytest.raises(ValueError, match="regular files"):
            sweep.inspect_sweep(directory)


def test_no_overwrite_or_reuse_and_cli_reports_design_failure(tmp_path, capsys):
    path = tmp_path / "manifest.json"
    assert sweep.main(["example", "--output", str(path)]) == 0
    original = path.read_bytes()
    assert sweep.main(["example", "--output", str(path)]) == 1
    assert path.read_bytes() == original
    write_json(path, _elastic_manifest())
    directory = tmp_path / "sweep"
    assert sweep.main(["run", str(path), "--output-dir", str(directory)]) == 2
    original_contents = _contents(directory)
    with patch("ciw.impact_workflow.run", side_effect=AssertionError("reuse execution")):
        with pytest.raises(FileExistsError):
            sweep.run_sweep(_elastic_manifest(), directory)
    assert _contents(directory) == original_contents
    assert sweep.main(["inspect", str(directory)]) == 2
    assert sweep.main(["verify", str(directory)]) == 2
    output = capsys.readouterr()
    assert '"requirements_status": "FAIL"' in output.out
