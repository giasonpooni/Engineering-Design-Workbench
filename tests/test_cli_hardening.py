"""Regression tests for transport validation and installed product behavior."""
import copy
import io
import json
import math
import subprocess
import sys

import numpy as np
import pytest

from tbrt.cli import EXAMPLES, MAX_INPUT_CHARACTERS, example_payload, main, reconcile_payload


def request():
    return example_payload("correlated")


@pytest.mark.parametrize("value", [None, [], "request", 1, True])
def test_non_objects_refused(value):
    with pytest.raises(ValueError, match="object"):
        reconcile_payload(value)


@pytest.mark.parametrize("where", [None, "source_frame", "reference_frame", "observation", "model"])
def test_unknown_fields_refused(where):
    data = request()
    target = data if where is None else data[where]
    target["misspelled_field"] = 0
    with pytest.raises(ValueError, match="unknown fields"):
        reconcile_payload(data)


@pytest.mark.parametrize("field", ["source_frame", "reference_frame", "observation", "model", "joint_covariance"])
def test_missing_fields_refused(field):
    data = request()
    del data[field]
    with pytest.raises(ValueError, match="missing fields"):
        reconcile_payload(data)


@pytest.mark.parametrize("value", ["false", "true", 0, 1, [], {}, None])
def test_evidence_policy_is_not_truthiness_coerced(value):
    data = request()
    data["require_synchronization_evidence"] = value
    with pytest.raises(ValueError, match="must be boolean"):
        reconcile_payload(data)


@pytest.mark.parametrize("value", [True, False, "0.000001", None, float("nan"), float("inf")])
def test_covariance_types_reach_core_unchanged(value):
    data = request()
    data["joint_covariance"][0][0] = value
    with pytest.raises(ValueError):
        reconcile_payload(data)


@pytest.mark.parametrize("value", ["ab", None, 1, ["x", "x"], [""]])
def test_evidence_ids_not_split_or_repaired(value):
    data = request()
    data["model"]["synchronization_evidence_ids"] = value
    with pytest.raises(ValueError):
        reconcile_payload(data)


def test_required_evidence_is_enforced():
    data = request()
    data["model"]["synchronization_evidence_ids"] = []
    with pytest.raises(ValueError, match="evidence is required"):
        reconcile_payload(data)
    data["require_synchronization_evidence"] = False
    assert reconcile_payload(data)["request_options"]["require_synchronization_evidence"] is False


def test_independent_destination_pin():
    data = request()
    data["expected_reference"] = {**data["reference_frame"], "clock_id": "other"}
    with pytest.raises(ValueError, match="expected reference"):
        reconcile_payload(data)


@pytest.mark.parametrize("name", EXAMPLES)
def test_examples_match_analytic_variance(name):
    data = example_payload(name)
    before = copy.deepcopy(data)
    result = reconcile_payload(data)
    jacobian = np.array([data["model"]["skew"], data["observation"]["device_time"] - data["model"]["device_origin"], 1])
    expected = jacobian @ np.array(data["joint_covariance"]) @ jacobian
    assert result["variance"] == pytest.approx(expected, rel=1e-12)
    assert result["standard_uncertainty"] == pytest.approx(math.sqrt(expected))
    assert result["operation_id"] == "tbrt.affine-clock-reconcile.v1"
    assert data == before
    assert reconcile_payload(data) == result


def test_correlations_and_separate_timestamps_survive():
    data = request()
    result = reconcile_payload(data)
    assert result["event_time"] == pytest.approx(203.00036)
    assert result["observation"]["received_at"]["value"] == 203.5
    assert result["observation"]["known_at"]["value"] == 204.0
    assert result["joint_covariance"][0][1] == 2e-9
    diagonal_only = copy.deepcopy(data)
    diagonal_only["joint_covariance"] = np.diag(np.diag(data["joint_covariance"])).tolist()
    assert result["variance"] != reconcile_payload(diagonal_only)["variance"]
    data["model"]["offset"] = 999
    assert result["model"]["offset"] == 0.0003


@pytest.mark.parametrize("text", ['{"x": 1, "x": 2}', '{"nested": {"x": 1, "x": 2}}', '{"x": NaN}', '{"x": Infinity}', '{"x": -Infinity}', '{', '[]', 'null'])
def test_invalid_json_emits_no_partial_result(monkeypatch, capsys, text):
    monkeypatch.setattr(sys, "stdin", io.StringIO(text))
    assert main(["-"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("clocksync:")


def test_oversized_input_refused(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO(" " * (MAX_INPUT_CHARACTERS + 1)))
    assert main(["-"]) == 2
    assert "exceeds" in capsys.readouterr().err


def test_invalid_utf8_refused(tmp_path, capsys):
    path = tmp_path / "invalid.json"
    path.write_bytes(b"\xff")
    assert main([str(path)]) == 2
    assert capsys.readouterr().out == ""


def test_missing_file_refused(tmp_path, capsys):
    assert main([str(tmp_path / "absent.json")]) == 2
    assert capsys.readouterr().out == ""


def test_example_and_stdin_round_trip(monkeypatch, capsys):
    assert main(["--example", "offset", "--compact"]) == 0
    text = capsys.readouterr().out
    monkeypatch.setattr(sys, "stdin", io.StringIO(text))
    assert main(["-", "--compact"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["event_time"] == 203.25


@pytest.mark.parametrize("args", [[], ["anything", "--example", "offset"]])
def test_ambiguous_or_missing_input(args):
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == 2


def test_module_entrypoint():
    completed = subprocess.run([sys.executable, "-m", "tbrt", "--example", "offset"], text=True, capture_output=True, check=True)
    assert json.loads(completed.stdout)["model"]["offset"] == 0.25
