"""Benchmark input/failure retention checks; these do not qualify an engine."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest

from ciw.telemetry import byte_digest, canonical
from test_reaction_contract import payload

MODULE = Path(__file__).resolve().parents[1] / "scripts/check_reaction_benchmark.py"
spec = importlib.util.spec_from_file_location("reaction_benchmark_gate", MODULE)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def fixtures():
    return {"schema": "ciw.reaction-benchmark-fixtures.v1",
            "cases": [{"name": "baseline", "payload": payload()}]}


def forbidden(*args, **kwargs):
    raise AssertionError("Input/inspection test attempted provider execution")


def test_strict_read_preserves_exact_fixture_bytes(tmp_path):
    raw = json.dumps(fixtures(), indent=4).encode() + b"\n"
    path = tmp_path / "input.json"
    path.write_bytes(raw)
    original, value = gate.read_fixtures(path)
    assert original == raw
    assert value == fixtures()


@pytest.mark.parametrize("mutation", ["duplicate-key", "duplicate-name", "not-list",
    "missing-name", "non-string-name", "empty-name", "long-name", "bad-later-payload",
    "oversized", "nonfinite", "empty"])
def test_invalid_fixture_refused_before_output_or_provider(tmp_path, monkeypatch, mutation):
    value = fixtures()
    if mutation == "duplicate-name": value["cases"] *= 2
    elif mutation == "not-list": value["cases"] = {"name": "baseline"}
    elif mutation == "missing-name": del value["cases"][0]["name"]
    elif mutation == "non-string-name": value["cases"][0]["name"] = []
    elif mutation == "empty-name": value["cases"][0]["name"] = ""
    elif mutation == "long-name": value["cases"][0]["name"] = "a" * 128
    elif mutation == "bad-later-payload":
        value["cases"].append({"name": "later", "payload": deepcopy(payload())})
        value["cases"][1]["payload"]["temperature_k"] = 100
    raw = canonical(value)
    if mutation == "duplicate-key": raw = raw.replace(b'"cases":', b'"cases":[],"cases":', 1)
    elif mutation == "oversized": raw += b" " * gate.MAX_FIXTURE_BYTES
    elif mutation == "nonfinite": raw = raw.replace(b'"rate_constant_s_inv":0.5', b'"rate_constant_s_inv":NaN')
    elif mutation == "empty": raw = b""
    path = tmp_path / "input.json"
    path.write_bytes(raw)
    destination = tmp_path / "output"
    monkeypatch.setattr(gate.ni.NativeInteropWorkflow, "_adapters", forbidden)
    with pytest.raises(ValueError):
        gate.run(tmp_path / "catalyst.json", tmp_path / "cantera.json", path, destination)
    assert not destination.exists()


def test_runtime_refusal_retains_fixture_report_and_reopenable_workspace(tmp_path, monkeypatch):
    raw = json.dumps(fixtures(), indent=2).encode() + b"\n"
    path = tmp_path / "input.json"
    path.write_bytes(raw)
    destination = tmp_path / "output"
    def unavailable(*args, **kwargs):
        raise ValueError("Explicit test: unavailable operator binding")
    monkeypatch.setattr(gate.ni.NativeInteropWorkflow, "_adapters", unavailable)
    monkeypatch.setattr(gate.ni, "_invoke", forbidden)
    with pytest.raises(ValueError, match="unavailable operator binding"):
        gate.run(tmp_path / "catalyst.json", tmp_path / "cantera.json", path, destination)
    report = json.loads((destination / "report.json").read_bytes())
    assert report["outcome"] == "failed"
    assert report["fixture_sha256"] == byte_digest(raw)
    assert (destination / "fixtures.json").read_bytes() == raw
    assert report["rows"][-1]["status"] == "FAIL"
    assert gate.inspect_workspace(destination / "workspace.json", tmp_path / "reopened") == []


def test_existing_destination_is_never_overwritten(tmp_path, monkeypatch):
    path = tmp_path / "input.json"
    path.write_bytes(canonical(fixtures()))
    destination = tmp_path / "output"
    destination.mkdir()
    prior = destination / "report.json"
    prior.write_bytes(b"prior evidence")
    monkeypatch.setattr(gate.ni.NativeInteropWorkflow, "_adapters", forbidden)
    with pytest.raises(FileExistsError):
        gate.run(tmp_path / "catalyst.json", tmp_path / "cantera.json", path, destination)
    assert prior.read_bytes() == b"prior evidence"


def test_reopen_compares_complete_retained_state_without_execution(tmp_path, monkeypatch):
    import base64
    session = gate.Session(gate.make_demo_run(), tmp_path / "original")
    source = gate.nc.make_source(gate.rc.PROFILE, "cantera", payload())
    session.workbench.add_source({"kind": gate.ni.KIND, "label": "retained source",
        "bytes_b64": base64.b64encode(canonical(source)).decode()})
    expected = session.workbench.serialize()
    workspace = tmp_path / "workspace.json"
    session.save_workspace(workspace)
    monkeypatch.setattr(gate.ni, "_invoke", forbidden)
    assert gate.inspect_workspace(workspace, tmp_path / "reopened", expected) == []
    different = deepcopy(expected)
    different["sources"][0]["label"] = "changed despite same bundle count"
    with pytest.raises(ValueError, match="Reopen changed retained identities or content"):
        gate.inspect_workspace(workspace, tmp_path / "changed", different)
