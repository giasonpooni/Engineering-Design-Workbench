"""Thin routing and read-only projection checks, not private-provider qualification.

The thermal tests execute the existing Python reference on synthetic inputs.
The FSRT/JSPT projection cases use explicitly labelled pre-existing wire fixtures.
Real CSR qualification is required separately by validation/scientific_native.py.
"""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys

import pytest

from ciw import scientific as api
from ciw import thermal_contract, thermal_workflow
from ciw.adapters.protocol import AdapterRefusal
from ciw.control_contracts import validate_state
from ciw.control_plane import ParameterSpace, Interval, Fixed
from ciw.core.identities import content_identity
from ciw.instruments import make_demo_run
from ciw.net import main
from ciw.scientific_state import _project, select_state
from ciw.session import Session
from test_thermal_workflow import _source
from test_covariance_records import fsrt_record, jspt_record  # labelled wire fixtures

REF = content_identity({"scope": "wire-fixture"})
LIMITS = {"max_abs_lateral": .01, "max_abs_heading": .01, "units": {"length": "m", "angle": "radian"}}


def forbidden(*args, **kwargs):
    raise AssertionError("No provider execution or implicit binding was requested")


def thermal_bytes():
    return b"\n" + json.dumps(_source(), indent=2).encode() + b"\n"


def fresh(tmp_path):
    return Session(make_demo_run(), tmp_path)


def test_catalog_uses_existing_routes_without_binding(monkeypatch):
    monkeypatch.setattr(api.Workbench, "bind_workflow", forbidden)
    value = api.catalog()
    assert value["authorizes_execution"] is False
    assert len(value["operations"]) == 23
    assert all(row["qualification"] == "not_performed_by_catalog" for row in value["operations"])
    assert {row["source_kind"] for row in api.catalog("geometry")["operations"]} == {
        "geometric-circle", "flat-torus-reference", "curved-path-transfer", "covariance-geometry", "mesh-path", "translation-flow"}
    exchange = next(row for row in value["operations"] if row["source_kind"] == "instrument-exchange")
    assert exchange["instrument_highlights"] == ["SET"]
    assert "ICRH" in value["other_boundaries"]
    assert api.catalog("machine-motion")["operations"] == []


def test_source_exact_bytes_and_provider_free_preflight():
    import base64
    raw = thermal_bytes()
    payload = api.source_payload("thermal-observer", raw, "reference experiment")
    assert base64.b64decode(payload["bytes_b64"]) == raw


@pytest.mark.parametrize("raw", [b"", b"{}", b'{"schema":1,"schema":2}', b'{"a":NaN}', b"x" * (2 * 1024 * 1024 + 1)])
def test_invalid_source_refuses_before_bind_or_state_change(tmp_path, monkeypatch, raw):
    session = fresh(tmp_path)
    before = session.workbench.serialize()
    monkeypatch.setattr(session.workbench, "bind_workflow", forbidden)
    with pytest.raises((ValueError, AdapterRefusal)):
        api.execute(session, "thermal-observer", raw, label="invalid", repositories={})
    assert before == session.workbench.serialize()


@pytest.mark.parametrize("kind", ["unknown", "machine-manifest", "cnc-motion", "__import__"])
def test_unindexed_execution_is_not_authorized(tmp_path, kind):
    with pytest.raises(AdapterRefusal):
        api.execute(fresh(tmp_path), kind, thermal_bytes(), label="bad")


@pytest.mark.parametrize("bindings", [["x=relative"], ["x"], ["=x"], ["x="], ["x=/a", "x=/b"]])
def test_binding_parser_refuses_ambiguous_or_relative_paths(bindings):
    with pytest.raises(ValueError):
        api.parse_bindings(bindings)


def test_binding_parser_absolute_and_no_filesystem_discovery(tmp_path):
    path = tmp_path / "not-created"
    assert api.parse_bindings(["csg=" + str(path)]) == {"csg": path}
    assert not path.exists()


def test_original_thermal_execution_replay_and_same_session_state(tmp_path):
    session = fresh(tmp_path)
    selection_context = deepcopy(session.run)
    raw = thermal_bytes()
    first = api.execute(session, "thermal-observer", raw, label="synthetic reference", repositories={})
    original = session.workbench.get_bundle(first["bundle_id"])
    second = api.replay(session, first["bundle_id"], repositories={})
    reproduced = session.workbench.get_bundle(second["bundle"]["bundle_id"])
    a, b = original["steps"][0], reproduced["steps"][0]
    assert a["execution_id"] != b["execution_id"]
    assert a["result_id"] != b["result_id"]
    assert a["numerical_result_id"] == b["numerical_result_id"]
    assert second["replay_receipt"]["numerical_match"] is True
    assert original["verification"]["authority"]["state_admission"] == "not_performed"
    assert session.run == selection_context
    assert session.executions == {}  # no duplicate ordinary execution wrapper
    view = api.inspect(session, bundle_id=first["bundle_id"])
    assert view["panels"][0]["panel_id"] == "state"
    assert len(api.inspect(session)["bundles"]) == 2


def test_output_extension_and_inspection_preserve_original_workspace(tmp_path, monkeypatch):
    session = fresh(tmp_path / "source")
    first = api.execute(session, "thermal-observer", thermal_bytes(), label="synthetic reference")
    original = session.save_workspace(tmp_path / "original.json")
    before = original.read_bytes()
    with api.open_workspace(original, tmp_path / "extended") as reopened:
        api.replay(reopened, first["bundle_id"])
    assert original.read_bytes() == before
    monkeypatch.setattr(thermal_workflow.ThermalWorkflow, "create_session", forbidden)
    monkeypatch.setattr(thermal_workflow.ThermalWorkflow, "replay_session", forbidden)
    with api.open_workspace(tmp_path / "extended/workspace.json") as reopened:
        assert len(api.inspect(reopened)["bundles"]) == 2
    with pytest.raises(FileExistsError):
        with api.open_workspace(original, tmp_path / "extended"):
            pytest.fail("Must not overwrite existing experiment")


def test_original_failure_is_saved_not_rewritten_as_success(tmp_path, monkeypatch):
    source = fresh(tmp_path / "source").save_workspace(tmp_path / "original.json")
    def failed(*args, **kwargs):
        raise ValueError("intentional reference-operation failure")
    monkeypatch.setattr(thermal_workflow.ThermalWorkflow, "create_session", failed)
    with pytest.raises(AdapterRefusal):
        with api.open_workspace(source, tmp_path / "failed") as session:
            api.execute(session, "thermal-observer", thermal_bytes(), label="synthetic failure challenge")
    with api.open_workspace(tmp_path / "failed/workspace.json") as session:
        assert not session.workbench.list_bundles()
        assert len(session.workbench.list_failed_executions()) == 1
        assert len(api.inspect(session)["failed_executions"]) == 1


def test_cli_routes_native_session_and_refuses_non_overwrite(tmp_path, capsys):
    source = fresh(tmp_path / "seed").save_workspace(tmp_path / "seed.json")
    raw = tmp_path / "thermal.json"
    raw.write_bytes(thermal_bytes())
    args = ["science", "run", "--workspace", str(source), "--kind", "thermal-observer", "--source", str(raw),
            "--label", "synthetic reference", "--output-dir", str(tmp_path / "result"), "--json"]
    assert main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["kind"] == "thermal-observer"
    assert main(args) == 1
    assert json.loads(capsys.readouterr().err)["status"] == "refused"
    assert main(["science", "inspect", "--workspace", str(tmp_path / "result/workspace.json"), "--json"]) == 0
    assert len(json.loads(capsys.readouterr().out)["bundles"]) == 1
    assert main(["science", "catalog", "covariance", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["operations"]


def test_unknown_selection_refuses_without_provider(tmp_path, monkeypatch):
    session = fresh(tmp_path)
    monkeypatch.setattr(session.workbench, "bind_workflow", forbidden)
    with pytest.raises(ValueError):
        api.replay(session, "unknown", repositories={})
    with pytest.raises(ValueError):
        api.inspect(session, instrument="thermal")
    with pytest.raises(ValueError):
        api.inspect(session, bundle_id="unknown")


def domain(unit="radian"):
    return ParameterSpace({"initial_heading_radian": Interval(-.01, .01, unit)})


def test_parameter_domain_composes_existing_native_study_request():
    value = api.heading_request("selected-baseline", domain(), [.001, -.001], sample_index=4, limits=LIMITS, study_id="bounded-study")
    assert value["schema"] == "ciw.curved-path-study-request.v1"
    assert [row["initial_heading_radian"] for row in value["candidates"]] == [.001, -.001]
    assert [row["candidate_id"] for row in value["candidates"]] == ["case-001", "case-002"]


@pytest.mark.parametrize("headings", [[], [.001] * 2, [float("nan")], [True], [.02], [0.] * 9, "0.001"])
def test_heading_domain_refuses_invalid_candidates(headings):
    with pytest.raises(ValueError):
        api.heading_request("baseline", domain(), headings, sample_index=4, limits=LIMITS, study_id="study")


@pytest.mark.parametrize("space", [None, domain("degree"), ParameterSpace({"mass": Fixed(1., "kg")})])
def test_heading_domain_has_explicit_quantity_and_units(space):
    with pytest.raises(ValueError):
        api.heading_request("baseline", space, [.001], sample_index=4, limits=LIMITS, study_id="study")


def test_native_study_preflight_precedes_binding(tmp_path, monkeypatch):
    session = fresh(tmp_path)
    monkeypatch.setattr(session.workbench, "bind_workflow", forbidden)
    request = api.heading_request("nonexistent-baseline", domain(), [.001], sample_index=4, limits=LIMITS, study_id="study")
    with pytest.raises(ValueError):
        api.heading_study(session, request, repositories={"csg": tmp_path})
    assert session.workbench.serialize()["bundles"] == []


def fixture_session(data, parameters, operation, monkeypatch):
    """Projection-only wire fixture: no estimator/calibrator is invoked or claimed."""
    monkeypatch.setattr("ciw.investigation._validate_source", lambda run: {"sensors": [
        {"measurement": {"records": [{"observed_at": "2026-01-01T00:00:00Z"}]}} for _ in range(2)]})
    return SimpleNamespace(run={"instrument": "org.notationsystems.rci", "evidence_id": REF,
        "time_s": [0.0], "metadata": {"model": {"wrong-default": "do-not-use"}}},
        results={"selected-result": {"result_id": "selected-result", "operation_id": operation, "data": deepcopy(data),
            "parameters": parameters, "execution_id": "original-execution", "record_digest": content_identity(data),
            "runtime": {"scope": "wire-fixture"}, "verification_id": None, "verification_status": "not_verified"}})


@pytest.mark.parametrize("stage", ["prior", "posterior", "reconciled"])
def test_fsrt_projection_keeps_original_full_covariance_and_execution(fsrt_record, monkeypatch, stage):
    session = fixture_session(fsrt_record, {}, "fsrt.tank-reconstruct.v2", monkeypatch)
    value = _project(session, "selected-result", stage, "declared-two-tank-assembly")
    validate_state(value["state"])
    assert value["state"]["uncertainty"] == fsrt_record["covariance_artifacts"][stage]
    assert value["state"]["identity"]["execution_id"] == "original-execution"
    assert value["state"]["identity"]["model_id"] == content_identity(fsrt_record["model"])
    assert value["context"]["diagnostics"] == fsrt_record["diagnostics"]
    assert value["runtime_launched"] is False
    value["state"]["uncertainty"]["matrix"][0][0] = 1000
    assert session.results["selected-result"]["data"] == fsrt_record


def test_held_status_is_not_erased_by_typed_state(fsrt_record, monkeypatch):
    # Labelled projection-only challenge; no fabricated physical-acceptance claim.
    fsrt_record["diagnostics"]["reconciliation_status"] = "model_inconsistent"
    session = fixture_session(fsrt_record, {}, "fsrt.tank-reconstruct.v2", monkeypatch)
    value = _project(session, "selected-result", "reconciled", "declared-assembly")
    assert value["context"]["diagnostics"]["reconciliation_status"] == "model_inconsistent"
    assert value["context"]["verification_status"] == "not_verified"


def test_jspt_projection_does_not_invent_output_means(jspt_record, monkeypatch):
    data, parameters = jspt_record
    session = fixture_session(data, parameters, "jspt.covariance-propagate.v1", monkeypatch)
    value = _project(session, "selected-result", "output_covariance", "declared-assembly")
    validate_state(value["state"])
    assert value["state"]["provenance"]["semantics"] == "reference"
    assert value["state"]["uncertainty"] == data["output_covariance"]
    assert value["state"]["variables"]["mean_mass"]["value"] == 50
    assert value["context"]["diagnostics"]["reference_scope"].startswith("caller_declared")


@pytest.mark.parametrize("case", ["missing-result", "innovation", "unknown-operation", "synthetic-source", "non-snapshot"])
def test_state_selection_refuses_semantic_misrepresentation(fsrt_record, monkeypatch, case):
    session = fixture_session(fsrt_record, {}, "fsrt.tank-reconstruct.v2", monkeypatch)
    result, stage = "selected-result", "posterior"
    if case == "missing-result": result = "refused-with-no-result"
    elif case == "innovation": stage = "innovation"
    elif case == "unknown-operation": session.results[result]["operation_id"] = "unrelated.v1"
    elif case == "synthetic-source": session.run["instrument"] = "org.notationsystems.simulated-mass-observation"
    else: session.run["time_s"] = [0., 1.]
    with pytest.raises(ValueError):
        _project(session, result, stage, "entity")


def test_real_reader_refuses_unsupported_typed_state_source(tmp_path):
    with pytest.raises(ValueError, match="RCI"):
        select_state(fresh(tmp_path), result_id="absent", stage="posterior", entity_id="entity")


def test_offline_inspection_in_fresh_process_does_not_execute_provider(tmp_path):
    session = fresh(tmp_path / "seed")
    api.execute(session, "thermal-observer", thermal_bytes(), label="synthetic reference")
    source = session.save_workspace(tmp_path / "workspace.json")
    code = '''
import sys
from pathlib import Path
from ciw import scientific, thermal_workflow

def forbidden(*a, **kw): raise AssertionError("provider called")
thermal_workflow.ThermalWorkflow.create_session = forbidden
thermal_workflow.ThermalWorkflow.replay_session = forbidden
with scientific.open_workspace(Path(sys.argv[1])) as session:
    result = scientific.inspect(session)
    assert len(result["bundles"]) == 1
    scientific.inspect(session, bundle_id=result["bundles"][0]["bundle_id"])
'''
    completed = subprocess.run([sys.executable, "-c", code, str(source)], capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stderr
