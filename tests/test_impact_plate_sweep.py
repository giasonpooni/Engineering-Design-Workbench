"""Plate envelopes extend the original bounded contact scenario workflow."""
from copy import deepcopy
from hashlib import file_digest
import shutil
from unittest.mock import patch

import pytest

from ciw import impact_sweep as sweep
from ciw.control_contracts import load
from ciw.operations.runner import seal
from ciw.session import loads_json, write_json


def _contents(directory):
    contents = {}
    for path in directory.rglob("*"):
        if path.is_file():
            with path.open("rb") as stream:
                contents[path.relative_to(directory)] = file_digest(stream, "sha256").hexdigest()
    return contents


@pytest.fixture(scope="module")
def plate_bundle(tmp_path_factory):
    directory = tmp_path_factory.mktemp("plate-envelope") / "scenarios"
    report = sweep.run_sweep(sweep.example_manifest("plate"), directory)
    return directory, report


def test_plate_example_selects_installed_contract_and_preserves_default_crush():
    original = deepcopy(sweep.example_manifest())
    manifest = sweep.example_manifest("plate")
    checked = sweep.validate_manifest(manifest)
    assert checked == manifest
    assert sweep._contract(checked["base_request"]).__name__ == "ciw.impact_plate_contract"
    assert checked["base_request"]["schema"] == "ciw.impact-plate-request.v1"
    assert len(sweep._grid(checked)[1]) == 4
    assert sweep.example_manifest() == sweep.example_manifest("crush") == original
    with pytest.raises(ValueError, match="example profile"):
        sweep.example_manifest("import-from-retained-request")


@pytest.mark.parametrize("name,value,unit", [
    ("length_x_m", 0.21, "m"), ("length_y_m", 0.21, "m"),
    ("thickness_m", 0.0028, "m"), ("young_modulus_pa", 2.1e9, "Pa"),
    ("density_kg_per_m3", 1250.0, "kg/m^3"),
    ("patch_center_x_m", 0.095, "m"), ("patch_center_y_m", 0.095, "m"),
    ("patch_width_x_m", 0.025, "m"), ("patch_width_y_m", 0.025, "m"),
])
def test_geometry_axes_retain_declared_units_and_validate_full_requests(name, value, unit):
    manifest = sweep.example_manifest("plate")
    manifest["axes"] = {name: [value]}
    checked = sweep.validate_manifest(manifest)
    space, coordinates = sweep._grid(checked)
    assert coordinates == [{name: value}]
    assert space["parameters"][name]["unit"] == unit
    candidate = sweep._request(checked, coordinates[0])
    assert candidate["model"][name] == value
    assert manifest["base_request"]["model"][name] != value


@pytest.mark.parametrize("mutation", ["off_patch", "thin_wavelength", "patch_width",
    "time_resolution", "yield_axis", "plastic_requirement", "permanent_requirement",
    "plate_unit", "four_axes"])
def test_invalid_plate_grid_rejects_before_any_output_or_execution(tmp_path, mutation):
    manifest = sweep.example_manifest("plate")
    if mutation == "off_patch":
        manifest["axes"] = {"patch_center_x_m": [0.1, 0.001]}
    elif mutation == "thin_wavelength":
        manifest["axes"] = {"thickness_m": [0.003, 0.004]}
    elif mutation == "patch_width":
        manifest["axes"] = {"patch_width_x_m": [0.02, 0.004]}
    elif mutation == "time_resolution":
        manifest["axes"] = {"young_modulus_pa": [2e9, 1e12]}
    elif mutation == "yield_axis":
        manifest["axes"] = {"yield_force_n": [100.0]}
    elif mutation == "plastic_requirement":
        manifest["requirements"][0].update(quantity="plastic_work_j", unit="J")
    elif mutation == "permanent_requirement":
        manifest["requirements"][0].update(quantity="residual_compression_m", unit="m")
    elif mutation == "plate_unit":
        manifest["requirements"][1]["unit"] = "mm"
    else:
        manifest["axes"] = {name: [value] for name, value in
                            (("length_x_m", 0.2), ("length_y_m", 0.2),
                             ("thickness_m", 0.003), ("initial_speed_m_per_s", 0.02))}
    destination = tmp_path / "invalid"
    with patch("ciw.impact_workflow.run", side_effect=AssertionError("invalid execution")):
        with pytest.raises(ValueError):
            sweep.run_sweep(manifest, destination)
    assert not destination.exists()


def test_plate_requirements_are_profile_specific_and_schemas_remain_fixed():
    manifest = sweep.example_manifest("plate")
    manifest["requirements"] = [
        {"quantity": "plate_contact_peak_deflection_m", "unit": "m", "operator": "<=", "limit": 0.0003},
        {"quantity": "max_deflection_over_thickness", "unit": "1", "operator": "<=", "limit": 0.1},
    ]
    assert sweep.validate_manifest(manifest) == manifest
    crush = sweep.example_manifest()
    crush["requirements"] = deepcopy(manifest["requirements"])
    with pytest.raises(ValueError, match="requirement quantity"):
        sweep.validate_manifest(crush)


def test_plate_grid_retains_qualified_geometry_and_distinct_occurrences(plate_bundle):
    directory, report = plate_bundle
    assert report["case_count"] == 4
    assert report["status"] == "LOCAL"
    assert report["requirements_status"] == "PASS"
    assert report["claims"]["failure_probability_estimated"] is False
    execution_ids, verification_ids = set(), set()
    for row in report["cases"]:
        inspected = row["inspection"]
        metrics = inspected["metrics"]["primary"]
        assert row["numerical_status"] == inspected["status"] == "LOCAL"
        assert inspected["preservation"]["verification_status"] == "VERIFIED"
        assert inspected["execution_id"] != inspected["verification_execution_id"]
        execution_ids.add(inspected["execution_id"])
        verification_ids.add(inspected["verification_id"])
        assert metrics["plate_peak_deflection_m"] >= metrics["plate_contact_peak_deflection_m"]
        assert metrics["max_deflection_over_thickness"] == pytest.approx(
            metrics["plate_peak_deflection_m"] / row["coordinate"]["thickness_m"])
        assert all(requirement["value"] == metrics[requirement["quantity"]]
                   for requirement in row["requirements"])
        workspace = directory / row["directory"] / "workspace.json"
        assert workspace.stat().st_size <= sweep.MAX_PLATE_WORKSPACE_BYTES
        result = next(item for item in loads_json(workspace.read_text())["results"]
                      if item["operation_id"] == "impact.plate-contact.v1")
        assert result["data"]["claim_scope"] == "simply_supported_kirchhoff_love_plate_patch_contact"
    assert len(execution_ids) == len(verification_ids) == 4


def test_plate_sweep_inspection_is_read_only_without_provider_replay(plate_bundle):
    directory, report = plate_bundle
    before = _contents(directory)
    with patch("ciw.impact_plate_solver.simulate", side_effect=AssertionError("solver replay")), \
            patch("ciw.impact_plate_verification.verify", side_effect=AssertionError("verifier replay")), \
            patch("ciw.session.execute_operation", side_effect=AssertionError("operation replay")):
        assert sweep.inspect_sweep(directory) == report
    assert _contents(directory) == before


def test_plate_sweep_verifies_retained_samples_without_new_execution(plate_bundle):
    directory, report = plate_bundle
    before = _contents(directory)
    with patch("ciw.impact_plate_solver.simulate", side_effect=AssertionError("solver replay")), \
            patch("ciw.session.execute_operation", side_effect=AssertionError("operation replay")):
        verified = sweep.verify_sweep(directory)
    assert verified["summary_ref"] == report["record_digest"]
    assert verified["status"] == "LOCAL"
    assert verified["fresh_execution"] is False
    assert all(row["fresh_numerical_verification"] is True for row in verified["cases"])
    assert _contents(directory) == before


def test_plate_design_rejection_does_not_change_numerical_scope(plate_bundle):
    inspected = plate_bundle[1]["cases"][0]["inspection"]
    requirements = [{"quantity": "peak_force_n", "unit": "N", "operator": "<=", "limit": 0.0}]
    evaluated, status = sweep._requirements(requirements, inspected)
    assert inspected["status"] == "LOCAL"
    assert status == evaluated[0]["status"] == "FAIL"
    assert evaluated[0]["value"] > 0.0


def test_valid_thinner_plate_can_refuse_spatial_qualification_and_leave_requirements_unresolved(tmp_path):
    manifest = sweep.example_manifest("plate")
    manifest["axes"] = {"thickness_m": [0.0025]}
    manifest["base_request"]["model"]["initial_speed_m_per_s"] = 0.01
    assert sweep.validate_manifest(manifest) == manifest
    directory = tmp_path / "spatial-refusal"
    report = sweep.run_sweep(manifest, directory)
    assert report["status"] == "REFUSE"
    assert report["requirements_status"] == "UNRESOLVED"
    assert all(row["value"] is None and row["status"] == "UNRESOLVED"
               for row in report["cases"][0]["requirements"])
    verified = load(directory / "case-000" / "verification.json")
    assert any(row["name"].startswith("spatial_refinement.") and row["status"] == "FAIL"
               for row in verified["report"]["checks"])
    with patch("ciw.impact_plate_solver.simulate", side_effect=AssertionError("solver replay")), \
            patch("ciw.impact_plate_verification.verify", side_effect=AssertionError("verifier replay")):
        assert sweep.inspect_sweep(directory) == report


def test_resealed_plate_scalar_comparison_cannot_replace_case_evidence(tmp_path, plate_bundle):
    directory = tmp_path / "corruption"
    shutil.copytree(plate_bundle[0], directory)
    summary = load(directory / "summary.json")
    summary["cases"][0]["requirements"][1]["value"] += 0.001
    seal(summary)
    write_json(directory / "summary.json", summary)
    with pytest.raises(ValueError, match="complete case evidence"):
        sweep.inspect_sweep(directory)


def test_plate_example_cli_is_explicit_and_create_only(tmp_path, capsys):
    destination = tmp_path / "plate-manifest.json"
    assert sweep.main(["example", "--profile", "plate", "--output", str(destination)]) == 0
    original = destination.read_bytes()
    assert load(destination) == sweep.example_manifest("plate")
    assert sweep.main(["example", "--profile", "plate", "--output", str(destination)]) == 1
    assert destination.read_bytes() == original
    assert '"status": "created"' in capsys.readouterr().out


def test_plate_workspace_budget_is_fixed_and_does_not_relax_old_profiles(tmp_path):
    plate = sweep.validate_manifest(sweep.example_manifest("plate"))
    crush = sweep.validate_manifest(sweep.example_manifest())
    assert sweep._workspace_budget(plate["base_request"]) == sweep.MAX_PLATE_WORKSPACE_BYTES
    assert sweep._workspace_budget(crush["base_request"]) == sweep.MAX_WORKSPACE_BYTES
    assert sweep.MAX_PLATE_WORKSPACE_BYTES == 128 * 1024 * 1024
    directory = tmp_path / "case"
    directory.mkdir()
    write_json(directory / "request.json", plate["base_request"])
    with (directory / "workspace.json").open("wb") as stream:
        stream.truncate(sweep.MAX_WORKSPACE_BYTES + 1)
    sweep._preflight_case(directory, workspace_maximum=sweep._workspace_budget(plate["base_request"]))
    with pytest.raises(ValueError, match="bounded file"):
        sweep._preflight_case(directory, workspace_maximum=sweep._workspace_budget(crush["base_request"]))


def test_oversized_plate_workspace_rejects_before_session_open(tmp_path, plate_bundle):
    directory = tmp_path / "oversized"
    shutil.copytree(plate_bundle[0], directory)
    with (directory / "case-000" / "workspace.json").open("wb") as stream:
        stream.truncate(sweep.MAX_PLATE_WORKSPACE_BYTES + 1)
    with patch("ciw.impact_workflow.inspect", side_effect=AssertionError("Session open")):
        with pytest.raises(ValueError, match="bounded file"):
            sweep.inspect_sweep(directory)
