"""Retained CSV preparation, independent mapping checks and user CLI lifecycle.

Every measurement row here is an illustrative fixture, not physical evidence.
"""
import csv
import io
import json
import os
from unittest.mock import patch

import pytest

from ciw import atmosphere_cli
from ciw import atmosphere_comparison_workflow as comparisons
from ciw import atmosphere_reference_preparation as preparation
from ciw import atmosphere_workflow as atmosphere
from ciw.atmosphere_contract import example_request
from ciw.atmosphere_comparison_contract import make_reference_source
from ciw.atmosphere_moist_contract import example_request as moist_request
from ciw.operations.runner import check_seal, seal
from ciw.session import read_json, write_json


HEADERS = ("sample_index", "height_m", "quantity", "value", "unit", "uncertainty_kind",
           "absolute_bound", "coverage_factor", "uncertainty_ref", "instrument_ref", "calibration_ref")
UTC = "2026-10-03T07:00:00Z"


def declaration():
    return {"schema": "ciw.atmosphere-measurement-import.v1",
            "provenance": {"kind": "declared_measurements", "source_ref": "illustrative.sensor-log",
                           "source_url": None, "independent_of_candidate": True},
            "context": {"frame": "atmosphere.local_enu.v1", "height_origin_m": 0.0,
                        "valid_time_utc": UTC, "humidity_convention": "not_applicable"},
            "thresholds": {"temperature_k": {"absolute_tolerance": 0.1, "relative_tolerance": 0.0},
                           "pressure_pa": {"absolute_tolerance": 1.0, "relative_tolerance": 0.0}}}


def csv_bytes(rows=None, *, bom=False):
    if rows is None:
        rows = [(0, 0, "temperature_k", 288.15, "K", "declared_expanded", 0.2, 2,
                 "Illustrative expanded allowance, not a sensor certificate.", "fixture.thermometer", "fixture.calibration-declaration"),
                (0, 0, "pressure_pa", 101325.0, "Pa", "declared_absolute_bound", 20, "",
                 "Illustrative absolute allowance.", "fixture.barometer", "fixture.calibration-declaration")]
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(HEADERS)
    writer.writerows(rows)
    return (b"\xef\xbb\xbf" if bom else b"") + stream.getvalue().encode("utf-8")


def files(tmp_path, raw=None, metadata=None):
    csv_path, metadata_path = tmp_path / "input.csv", tmp_path / "declaration.json"
    csv_path.write_bytes(csv_bytes() if raw is None else raw)
    write_json(metadata_path, declaration() if metadata is None else metadata)
    return csv_path, metadata_path


def snapshot(directory):
    return {str(path.relative_to(directory)): path.read_bytes()
            for path in directory.rglob("*") if path.is_file()}


@pytest.fixture
def prepared(tmp_path):
    csv_path, metadata_path = files(tmp_path)
    destination = tmp_path / "prepared"
    reply = preparation.prepare_files(csv_path, metadata_path, destination)
    return {"csv": csv_path, "declaration": metadata_path, "directory": destination, "reply": reply}


def test_preparation_retains_raw_input_and_distinct_reference_identity(prepared):
    directory = prepared["directory"]
    assert set(snapshot(directory)) == {"measurements.csv", "declaration.json", "reference.json", "policy.json", "preparation.json"}
    assert (directory / "measurements.csv").read_bytes() == prepared["csv"].read_bytes()
    assert read_json(directory / "declaration.json") == declaration()
    reference, policy = read_json(directory / "reference.json"), read_json(directory / "policy.json")
    check_seal(reference)
    check_seal(policy)
    check_seal(read_json(directory / "preparation.json"))
    reply = prepared["reply"]
    assert reply["status"] == "prepared"
    assert reply["reference_digest"] == reference["record_digest"]
    assert reply["policy_digest"] == policy["record_digest"]
    assert reply["reference_evidence_id"] != reply["reference_digest"]
    assert reply["observation_count"] == 1 and reply["scalar_count"] == 2
    assert "execution_id" not in reply and "verification_id" not in reply


def test_inspect_is_static_verify_fresh_and_both_are_immutable(prepared):
    directory = prepared["directory"]
    before = snapshot(directory)
    with patch("ciw.atmosphere_compiler.compile_atmosphere", side_effect=AssertionError("compiler activated")), \
            patch("ciw.atmosphere_moist_compiler.compile_atmosphere", side_effect=AssertionError("moist compiler activated")), \
            patch("ciw.atmosphere_verification.verify", side_effect=AssertionError("physical verifier activated")), \
            patch("ciw.atmosphere_moist_verification.verify", side_effect=AssertionError("moist verifier activated")):
        retained = preparation.inspect_preparation(directory)
        checked = preparation.verify_preparation(directory)
    assert retained["status"] == "retained" and retained["fresh_mapping_check"] is False
    assert checked["status"] == "checked" and checked["fresh_mapping_check"] is True
    for key in ("reference_digest", "policy_digest", "reference_evidence_id", "csv_content_digest", "declaration_digest"):
        assert retained[key] == checked[key] == prepared["reply"][key]
    assert snapshot(directory) == before
    authority = checked["authority"]
    assert authority["physical_validation"] == "not_established"
    assert authority["calibration_validation"] == "not_established"
    assert authority["measurement_authenticity"] == "not_established"
    assert authority["state_admission"] == "not_performed"


@pytest.mark.parametrize("profile", ["dry", "moist"])
def test_prepared_reference_executes_comparison_without_mutating_original(prepared, tmp_path, profile):
    request = example_request() if profile == "dry" else moist_request()
    request["sampling"]["height_m"] = [0.0, 100.0]
    request["reference"]["context"] = {"source_kind": "declared_environment", "source_ref": "fixture.boundary",
                                          "valid_time_utc": UTC}
    original = tmp_path / "atmosphere"
    atmosphere.run(request, original)
    before = snapshot(original)
    directory = prepared["directory"]
    if profile == "moist":
        # The moist provider's qualified origin domain starts at 293.15 K.
        # Prepare a matching authored fixture instead of widening that domain.
        csv_file = tmp_path / "moist-input.csv"
        csv_file.write_bytes(prepared["csv"].read_bytes().replace(b",288.15,", b",298.15,"))
        directory = tmp_path / "prepared-moist"
        preparation.prepare_files(csv_file, prepared["declaration"], directory)
    comparison = tmp_path / "comparison"
    reply = comparisons.run(original, read_json(directory / "reference.json"), read_json(directory / "policy.json"), comparison)
    assert reply["status"] == "LOCAL" and reply["agreement_status"] == "PASS"
    assert comparisons.verify_retained(comparison)["verification_status"] == "PASS"
    comparisons.export_json(comparison, tmp_path / "comparison.json")
    comparisons.export_csv(comparison, tmp_path / "comparison.csv")
    payload = read_json(tmp_path / "comparison.json")
    assert payload["comparison"]["claims"]["measurement_authenticity_established"] is False
    assert payload["comparison"]["claims"]["calibration_validation"] is False
    assert payload["comparison"]["claims"]["physical_validation"] == "not_established"
    assert snapshot(original) == before


@pytest.mark.parametrize("mismatch", ["frame", "valid_time_utc"])
def test_preparation_preserves_context_mismatch_for_verified_refusal(tmp_path, mismatch):
    metadata = declaration()
    metadata["context"][mismatch] = "other.local_enu.v1" if mismatch == "frame" else "2026-10-03T08:00:00Z"
    csv_path, sidecar = files(tmp_path, metadata=metadata)
    prepared = tmp_path / "prepared"
    preparation.prepare_files(csv_path, sidecar, prepared)
    request = example_request()
    request["reference"]["context"] = {"source_kind": "declared_environment", "source_ref": "fixture.boundary", "valid_time_utc": UTC}
    source = tmp_path / "source"
    atmosphere.run(request, source)
    target = tmp_path / "comparison"
    reply = comparisons.run(source, read_json(prepared / "reference.json"), read_json(prepared / "policy.json"), target)
    assert reply["status"] == "REFUSE"
    assert comparisons.verify_retained(target)["verification_status"] == "PASS"


def test_unsupported_humidity_convention_is_preserved_for_expansion(tmp_path):
    metadata = declaration()
    metadata["context"]["humidity_convention"] = "pressure_enhanced_relative_humidity"
    metadata["thresholds"] = {"relative_humidity": {"absolute_tolerance": 0.01, "relative_tolerance": 0}}
    raw = csv_bytes([(0, 0, "relative_humidity", 0.5, "1", "declared_absolute_bound", 0.01, "",
                      "Illustrative RH allowance.", "fixture.hygrometer", "fixture.calibration-declaration")])
    csv_path, sidecar = files(tmp_path, raw=raw, metadata=metadata)
    prepared = tmp_path / "prepared"
    preparation.prepare_files(csv_path, sidecar, prepared)
    request = moist_request()
    request["reference"]["context"] = {"source_kind": "declared_environment", "source_ref": "fixture.boundary", "valid_time_utc": UTC}
    source = tmp_path / "source"
    atmosphere.run(request, source)
    comparison = tmp_path / "comparison"
    reply = comparisons.run(source, read_json(prepared / "reference.json"), read_json(prepared / "policy.json"), comparison)
    assert reply["status"] == "EXPAND"
    assert comparisons.verify_retained(comparison)["verification_status"] == "PASS"


@pytest.mark.parametrize("invalid", ["duplicate", "wrong_unit", "missing_instrument", "zero_uncertainty", "header", "bad_utf8"])
def test_invalid_csv_creates_no_partial_destination(tmp_path, invalid):
    raw = csv_bytes()
    if invalid == "duplicate":
        lines = raw.splitlines(keepends=True)
        raw += lines[1]
    elif invalid == "wrong_unit":
        raw = raw.replace(b",K,", b",degC,")
    elif invalid == "missing_instrument":
        raw = raw.replace(b"fixture.thermometer", b"")
    elif invalid == "zero_uncertainty":
        raw = raw.replace(b",0.2,2,", b",0,2,")
    elif invalid == "header":
        raw = raw.replace(b"sample_index", b"index", 1)
    else:
        raw += b"\xff"
    csv_path, sidecar = files(tmp_path, raw=raw)
    target = tmp_path / "prepared"
    with pytest.raises((ValueError, UnicodeError)):
        preparation.prepare_files(csv_path, sidecar, target)
    assert not target.exists()


@pytest.mark.parametrize("invalid", ["missing_time", "duplicate_json_key", "extra_key", "missing_threshold"])
def test_invalid_sidecar_creates_no_partial_destination(tmp_path, invalid):
    metadata = declaration()
    if invalid == "missing_time":
        metadata["context"]["valid_time_utc"] = None
    elif invalid == "extra_key":
        metadata["physical_validation"] = True
    elif invalid == "missing_threshold":
        del metadata["thresholds"]["pressure_pa"]
    csv_path, sidecar = files(tmp_path, metadata=metadata)
    if invalid == "duplicate_json_key":
        sidecar.write_text('{"schema":"first",' + json.dumps(metadata)[1:], encoding="utf-8")
    target = tmp_path / "prepared"
    with pytest.raises(ValueError):
        preparation.prepare_files(csv_path, sidecar, target)
    assert not target.exists()


def test_bom_input_bytes_are_retained_exactly(tmp_path):
    csv_path, sidecar = files(tmp_path, raw=csv_bytes(bom=True))
    target = tmp_path / "prepared"
    preparation.prepare_files(csv_path, sidecar, target)
    assert (target / "measurements.csv").read_bytes() == csv_path.read_bytes()
    assert preparation.verify_preparation(target)["fresh_mapping_check"] is True


def test_existing_destination_is_untouched(prepared):
    before = snapshot(prepared["directory"])
    with pytest.raises((ValueError, FileExistsError)):
        preparation.prepare_files(prepared["csv"], prepared["declaration"], prepared["directory"])
    assert snapshot(prepared["directory"]) == before


@pytest.mark.parametrize("input_name", ["csv", "declaration"])
@pytest.mark.parametrize("surface", ["directory", "symlink", "oversize", "fifo"])
def test_input_regular_file_preflight(tmp_path, input_name, surface):
    csv_path, sidecar = files(tmp_path)
    original = csv_path if input_name == "csv" else sidecar
    unsafe = tmp_path / "unsafe"
    if surface == "directory":
        unsafe.mkdir()
    elif surface == "symlink":
        try:
            unsafe.symlink_to(original)
        except (OSError, NotImplementedError):
            return  # Windows installations may not grant symlink privileges.
    elif surface == "fifo":
        if not hasattr(os, "mkfifo"):
            return  # Windows has no FIFO surface; Linux exercises this branch.
        os.mkfifo(unsafe)
    else:
        with unsafe.open("wb") as stream:
            stream.truncate(8 * 1024 * 1024 + 1)
    target = tmp_path / "prepared"
    with pytest.raises((ValueError, OSError)):
        preparation.prepare_files(unsafe if input_name == "csv" else csv_path,
                                  unsafe if input_name == "declaration" else sidecar, target)
    assert not target.exists()


@pytest.mark.parametrize("artifact", ["measurements.csv", "declaration.json", "reference.json", "policy.json", "preparation.json"])
def test_retained_artifact_corruption_rejected_by_inspection(prepared, artifact):
    path = prepared["directory"] / artifact
    if artifact.endswith(".csv"):
        path.write_bytes(path.read_bytes() + b"\n")
    else:
        payload = read_json(path)
        payload["unexpected"] = True
        write_json(path, payload)
    with pytest.raises(ValueError):
        preparation.inspect_preparation(prepared["directory"])


@pytest.mark.parametrize("surface", ["directory", "symlink", "extra_file"])
def test_retained_bundle_preflight_is_exact(prepared, surface):
    directory = prepared["directory"]
    if surface == "extra_file":
        (directory / "unretained.txt").write_text("Unexpected evidence", encoding="utf-8")
    else:
        path = directory / "measurements.csv"
        path.unlink()
        if surface == "directory":
            path.mkdir()
        else:
            try:
                path.symlink_to(prepared["csv"])
            except (OSError, NotImplementedError):
                return
    with pytest.raises((ValueError, OSError)):
        preparation.inspect_preparation(directory)


def test_resealed_mapping_forgery_is_static_content_but_fails_fresh_check(prepared):
    directory = prepared["directory"]
    retained = read_json(directory / "preparation.json")
    retained["reference"]["observations"][0]["quantities"]["temperature_k"]["value"] += 5.0
    seal(retained["reference"])
    retained["reference_evidence_id"] = make_reference_source(retained["reference"])["evidence_id"]
    seal(retained)
    write_json(directory / "preparation.json", retained)
    write_json(directory / "reference.json", retained["reference"])
    before = snapshot(directory)
    inspected = preparation.inspect_preparation(directory)
    assert inspected["fresh_mapping_check"] is False
    with pytest.raises(ValueError):
        preparation.verify_preparation(directory)
    assert snapshot(directory) == before


def test_static_inspection_does_not_parse_csv_again(prepared):
    with patch("ciw.atmosphere_measurement_ingress.prepare", side_effect=AssertionError("CSV mapping replayed")), \
            patch("ciw.atmosphere_reference_preparation.prepare", side_effect=AssertionError("CSV mapping replayed")):
        reply = preparation.inspect_preparation(prepared["directory"])
    assert reply["fresh_mapping_check"] is False


@pytest.mark.parametrize("action", ["inspect_preparation", "verify_preparation"])
def test_actions_use_exactly_one_retained_snapshot(prepared, action):
    with patch.object(preparation, "_read_preparation", wraps=preparation._read_preparation) as reader:
        reply = getattr(preparation, action)(prepared["directory"])
    assert reader.call_count == 1
    assert reply["fresh_mapping_check"] is (action == "verify_preparation")


def test_cli_prepares_inspects_verifies_and_refuses_invalid_input(tmp_path, capsys):
    csv_path, sidecar = files(tmp_path)
    target = tmp_path / "prepared"
    assert atmosphere_cli.main(["compare", "prepare", str(csv_path), "--declaration", str(sidecar), "--output-dir", str(target)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "prepared"
    for name, status, fresh in (("preparation-inspect", "retained", False), ("preparation-verify", "checked", True)):
        assert atmosphere_cli.main(["compare", name, str(target)]) == 0
        reply = json.loads(capsys.readouterr().out)
        assert reply["status"] == status and reply["fresh_mapping_check"] is fresh
    rejected = tmp_path / "rejected"
    assert atmosphere_cli.main(["compare", "prepare", str(csv_path), "--declaration", str(csv_path), "--output-dir", str(rejected)]) == 1
    assert json.loads(capsys.readouterr().err)["status"] == "REFUSE"
    assert not rejected.exists()
