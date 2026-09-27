"""Operator gate input/retention tests; these do not qualify a native engine."""
import base64
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest

from ciw.telemetry import byte_digest, canonical
from test_interval_contract import payload, declared_output

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("interval_requirement_gate", ROOT / "scripts/check_interval_requirement.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def fixtures():
    return {"schema": gate.FIXTURE_SCHEMA, "cases": [{"name": "baseline", "payload": payload()}]}


def forbidden(*args, **kwargs):
    raise AssertionError("Input/inspection unit test attempted a provider")


def test_strict_input_preserves_exact_fixture_bytes(tmp_path):
    raw = json.dumps(fixtures(), indent=4).encode() + b"\n"
    path = tmp_path / "input.json"; path.write_bytes(raw)
    original, value = gate.read_fixtures(path)
    assert original == raw
    assert value == fixtures()


def test_committed_fixture_set_has_six_bounded_cases():
    _, value = gate.read_fixtures(ROOT / "examples/interval-requirement/fixtures.json")
    assert [case["name"] for case in value["cases"]] == [
        "dyadic-boundary", "positive-box", "mixed-box", "rational-tenth-boundary",
        "zero-width-zero-limit", "negative-box"]


@pytest.mark.parametrize("mutation", ["malformed", "duplicate-key", "duplicate-rational-key", "duplicate-name",
    "not-list", "zero-cases", "too-many", "missing-name", "non-string-name", "empty-name", "long-name",
    "unknown-case-field", "bad-later-payload", "oversized", "nonfinite", "empty"])
def test_invalid_input_refused_before_provider_or_output(tmp_path, monkeypatch, mutation):
    value = fixtures()
    if mutation == "duplicate-name": value["cases"] *= 2
    elif mutation == "not-list": value["cases"] = {}
    elif mutation == "zero-cases": value["cases"] = []
    elif mutation == "too-many": value["cases"] = [{"name": str(i), "payload": payload()} for i in range(17)]
    elif mutation == "missing-name": del value["cases"][0]["name"]
    elif mutation == "non-string-name": value["cases"][0]["name"] = []
    elif mutation == "empty-name": value["cases"][0]["name"] = ""
    elif mutation == "long-name": value["cases"][0]["name"] = "a" * 128
    elif mutation == "unknown-case-field": value["cases"][0]["provider"] = "julia"
    elif mutation == "bad-later-payload":
        bad = payload(); bad["variation_lower"]["denominator"] = 0
        value["cases"].append({"name": "later", "payload": bad})
    raw = canonical(value)
    if mutation == "malformed": raw = b"{bad-json"
    elif mutation == "duplicate-key": raw = raw.replace(b'"cases":', b'"cases":[],"cases":', 1)
    elif mutation == "duplicate-rational-key": raw = raw.replace(b'"denominator":', b'"denominator":1,"denominator":', 1)
    elif mutation == "oversized": raw += b" " * gate.MAX_FIXTURE_BYTES
    elif mutation == "nonfinite": raw = raw.replace(b'"numerator":3', b'"numerator":NaN')
    elif mutation == "empty": raw = b""
    path = tmp_path / "input.json"; path.write_bytes(raw)
    destination = tmp_path / "output"
    monkeypatch.setattr(gate.ni.NativeInteropWorkflow, "_adapters", forbidden)
    monkeypatch.setattr(gate.ni, "_invoke", forbidden)
    with pytest.raises(ValueError): gate.run(tmp_path / "binding.json", path, destination)
    assert not destination.exists()


def test_runtime_failure_retains_exact_fixtures_report_and_workspace(tmp_path, monkeypatch):
    raw = json.dumps(fixtures(), indent=2).encode() + b"\n"
    path = tmp_path / "input.json"; path.write_bytes(raw)
    destination = tmp_path / "output"
    def unavailable(*args, **kwargs):
        raise ValueError("Explicit test: unavailable operator binding")
    monkeypatch.setattr(gate.ni.NativeInteropWorkflow, "_adapters", unavailable)
    monkeypatch.setattr(gate.ni, "_invoke", forbidden)
    with pytest.raises(ValueError, match="unavailable operator binding"):
        gate.run(tmp_path / "binding.json", path, destination)
    report = json.loads((destination / "report.json").read_bytes())
    assert report["outcome"] == "failed"
    assert report["fixture_sha256"] == byte_digest(raw)
    assert (destination / report["fixture_file"]).read_bytes() == raw
    assert report["rows"][-1]["envelope_status"] == "FAIL"
    assert report["rows"][-1]["gate"] == "runtime-binding"
    assert gate.inspect_workspace(destination / "workspace.json", tmp_path / "reopened") == []


def test_existing_output_is_never_overwritten(tmp_path, monkeypatch):
    path = tmp_path / "input.json"; path.write_bytes(canonical(fixtures()))
    destination = tmp_path / "output"; destination.mkdir()
    previous = destination / "report.json"; previous.write_bytes(b"prior evidence")
    monkeypatch.setattr(gate.ni.NativeInteropWorkflow, "_adapters", forbidden)
    with pytest.raises(FileExistsError): gate.run(tmp_path / "binding.json", path, destination)
    assert previous.read_bytes() == b"prior evidence"


def test_offline_reopen_compares_content_even_with_same_bundle_count(tmp_path, monkeypatch):
    session = gate.Session(gate.make_demo_run(), tmp_path / "original")
    declaration = gate.source(fixtures()["cases"][0])
    session.workbench.add_source({"kind": gate.ni.KIND, "label": "retained source",
        "bytes_b64": base64.b64encode(canonical(declaration)).decode("ascii")})
    expected = session.workbench.serialize()
    path = tmp_path / "workspace.json"; session.save_workspace(path)
    monkeypatch.setattr(gate.ni, "_invoke", forbidden)
    monkeypatch.setattr(gate.ic, "reference", forbidden)
    assert gate.inspect_workspace(path, tmp_path / "reopened", expected) == []
    changed = deepcopy(expected)
    changed["sources"][0]["label"] = "changed despite same bundle count"
    with pytest.raises(ValueError, match="Reopen changed retained identities or content"):
        gate.inspect_workspace(path, tmp_path / "changed", changed)


@pytest.mark.parametrize("lo,hi,requirement", [(1.0, 4.0, "fails_throughout"), (-1.0, 1.0, "inconclusive")])
def test_report_projection_separates_requirement_from_envelope(lo, hi, requirement):
    # Explicit projection-only fixture, never supplied to runtime qualification.
    output = declared_output(lo, hi)
    bundle = {"steps": [{"operation_id": "operation", "execution_id": "execution",
        "result_id": "result", "numerical_result_id": "numerical", "check_seconds": 0.2,
        "transport": {"process_seconds": 0.3}, "result": {"data": {"output": output,
        "reference_check": {"outcome": "passed"}}}}], "verification": {"verification_id": "verification"}}
    row = gate.result_row("fixture", {"source_id": "source", "evidence_id": "evidence"},
                          {"bundle_id": "bundle"}, bundle)
    assert row["envelope_status"] == "PASS"
    assert row["requirement"] == requirement
    assert row["enclosure"] == output["enclosure"]
    assert row["process_seconds"] == 0.3 and row["check_seconds"] == 0.2
    assert row["result_id"] == "result" and row["evidence_id"] == "evidence"
