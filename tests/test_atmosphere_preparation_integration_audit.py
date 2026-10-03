"""Adversarial retained-ingress snapshots and declaration authority checks.

All values in these tests are authored fixtures, not acquired measurements.
"""
from copy import deepcopy
import csv
import io
from pathlib import Path
import shutil
from unittest.mock import patch

import pytest

from ciw import atmosphere_reference_preparation as preparation
from ciw.atmosphere_measurement_ingress import AUTHORITY, CSV_FIELDS
from ciw.operations.runner import digest
from ciw.session import read_json, write_json


def _inputs(tmp_path):
    declaration = {
        "schema": "ciw.atmosphere-measurement-import.v1",
        "provenance": {
            "kind": "declared_measurements", "source_ref": "authored-audit-fixture",
            "source_url": "https://example.invalid/declared-source",
            "independent_of_candidate": True,
        },
        "context": {
            "frame": "atmosphere.local_enu.v1", "height_origin_m": 0.0,
            "valid_time_utc": "2000-01-01T00:00:00Z", "humidity_convention": "not_applicable",
        },
        "thresholds": {"temperature_k": {"absolute_tolerance": 0.1, "relative_tolerance": 0.0}},
    }
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(CSV_FIELDS)
    writer.writerow((0, 0, "temperature_k", 288.15, "K", "declared_expanded", 0.2, 2,
                     "Authored expanded uncertainty declaration.", "fixture.instrument", "fixture.calibration"))
    raw = stream.getvalue().encode("utf-8")
    csv_path, declaration_path = tmp_path / "input.csv", tmp_path / "input.json"
    csv_path.write_bytes(raw)
    write_json(declaration_path, declaration)
    return csv_path, declaration_path, raw, declaration


def _snapshot(directory):
    return {path.name: path.read_bytes() for path in directory.iterdir()}


def test_creation_uses_captured_inputs_when_originals_change_after_read(tmp_path):
    csv_path, declaration_path, raw, declaration = _inputs(tmp_path)
    reader = preparation._regular_bytes
    calls = []

    def capture_then_modify(path):
        path = Path(path)
        captured = reader(path)
        calls.append(path)
        path.write_bytes(b"Modified after this input snapshot was captured.")
        return captured

    directory = tmp_path / "prepared"
    with patch.object(preparation, "_regular_bytes", side_effect=capture_then_modify):
        reply = preparation.prepare_files(csv_path, declaration_path, directory)
    assert calls == [csv_path, declaration_path]
    assert (directory / "measurements.csv").read_bytes() == raw
    assert read_json(directory / "declaration.json") == declaration
    assert preparation.verify_preparation(directory)["reference_digest"] == reply["reference_digest"]


@pytest.mark.parametrize("action", ["inspect_preparation", "verify_preparation"])
def test_directory_replacement_during_read_cannot_be_reported_as_one_snapshot(tmp_path, action):
    csv_path, declaration_path, _, _ = _inputs(tmp_path)
    directory = tmp_path / "prepared"
    preparation.prepare_files(csv_path, declaration_path, directory)
    replacement, moved = tmp_path / "replacement", tmp_path / "original"
    shutil.copytree(directory, replacement)
    reader = preparation._regular_bytes
    replaced = False

    def replace_after_first_read(path):
        nonlocal replaced
        captured = reader(path)
        if not replaced:
            directory.rename(moved)
            replacement.rename(directory)
            replaced = True
        return captured

    with patch.object(preparation, "_regular_bytes", side_effect=replace_after_first_read):
        with pytest.raises(ValueError, match="directory changed"):
            getattr(preparation, action)(directory)
    assert _snapshot(directory) == _snapshot(moved)


@pytest.mark.parametrize("action", ["inspect_preparation", "verify_preparation"])
def test_retained_actions_read_each_artifact_once_without_network_or_execution(tmp_path, action):
    csv_path, declaration_path, _, declaration = _inputs(tmp_path)
    directory = tmp_path / "prepared"
    preparation.prepare_files(csv_path, declaration_path, directory)
    before = _snapshot(directory)
    with patch.object(preparation, "_regular_bytes", wraps=preparation._regular_bytes) as reader, \
            patch("socket.create_connection", side_effect=AssertionError("Network acquisition activated")), \
            patch("ciw.session.execute_operation", side_effect=AssertionError("Scientific execution activated")):
        reply = getattr(preparation, action)(directory)
    assert sorted(call.args[0].name for call in reader.call_args_list) == sorted(preparation.FILES)
    assert reply["authority"] == AUTHORITY
    assert not {"operation_id", "execution_id", "verification_id", "admission_id"} & set(reply)
    reference = read_json(directory / "reference.json")
    assert reference["provenance"] == declaration["provenance"]
    assert reference["observations"][0]["quantities"]["temperature_k"]["calibration_ref"] == "fixture.calibration"
    assert _snapshot(directory) == before


def test_declared_independence_changes_content_without_promoting_authority(tmp_path):
    csv_path, declaration_path, _, declaration = _inputs(tmp_path)
    first, second = tmp_path / "declared-independent", tmp_path / "declared-dependent"
    independent = preparation.prepare_files(csv_path, declaration_path, first)
    dependent_declaration = deepcopy(declaration)
    dependent_declaration["provenance"]["independent_of_candidate"] = False
    write_json(declaration_path, dependent_declaration)
    dependent = preparation.prepare_files(csv_path, declaration_path, second)
    assert independent["csv_content_digest"] == dependent["csv_content_digest"]
    assert independent["declaration_digest"] == digest(declaration)
    assert independent["declaration_digest"] != dependent["declaration_digest"]
    assert independent["reference_evidence_id"] != dependent["reference_evidence_id"]
    assert independent["policy_digest"] == dependent["policy_digest"]
    assert independent["authority"] == dependent["authority"] == AUTHORITY
