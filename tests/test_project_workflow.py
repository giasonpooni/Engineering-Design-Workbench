"""Shared CIW lifecycle coverage for the provider-free project graph."""

import base64
from copy import deepcopy

import pytest

from ciw import project_model as project
from ciw import project_workflow
from ciw.instruments import make_demo_run
from ciw.session import Session
from ciw.telemetry import canonical


def _fixture_project():
    value = project.create("project:workflow-fixture", "Workflow fixture",
                           {"place": {"value": None, "evidence_refs": []}})
    value = project.put(value, {
        "object_id": "evidence:manual", "kind": "evidence", "label": "Manual",
        "content": {"status": "documented", "source_digest": "sha256:" + "1" * 64,
                    "locator": "fixture://manual", "subject_id": "machine:fixture"},
    })
    value = project.put(value, {
        "object_id": "signal:position", "kind": "signal", "label": "Position",
        "content": {"quantity": "position", "unit": "m", "frame": "frame:carriage",
                    "time_basis": "clock:utc", "semantics": "observed"},
    })
    value = project.put(value, {
        "object_id": "computation:position", "kind": "computation", "label": "Position model",
        "content": {"operation": "ciw.encoder-position.v1", "parameters": {"mode": "declared"}},
    })
    objects = {item["object_id"]: item for item in project.inspect(value)["objects"]}
    value = project.put(value, {
        "object_id": "result:position", "kind": "result", "label": "Position estimate",
        "content": {
            "value": 1.0,
            "input_revisions": {
                "signal:position": objects["signal:position"]["revision"],
                "computation:position": objects["computation:position"]["revision"],
            },
            "unit": "m", "frame": "frame:carriage", "time_basis": "clock:utc",
            "semantics": "estimated", "claim_scope": "declared_kinematic_model",
        },
    })
    value = project.connect(value, {
        "edge_id": "edge:model-result", "relation": "computation",
        "from": "computation:position", "to": "result:position", "resolution": "resolved",
    })
    value = project.connect(value, {
        "edge_id": "edge:evidence-result", "relation": "evidence",
        "from": "evidence:manual", "to": "result:position", "resolution": "resolved",
    })
    return value


def _source():
    return {
        "schema": project_workflow.SOURCE_SCHEMA,
        "experiment_id": "project:workflow-fixture",
        "configuration": deepcopy(project_workflow.CONFIGURATION),
        "project": _fixture_project(),
    }


def _call(session, kind, payload):
    response = session.handle({"protocol_version": 1, "request_id": "test-" + kind,
                               "type": kind, "payload": payload})
    assert response["type"] == "response", response
    return response["payload"]


def _session_with_source(tmp_path):
    session = Session(make_demo_run(), tmp_path)
    raw = canonical(_source())
    descriptor = _call(session, "source.add", {"kind": "project-graph", "label": "project fixture",
                                                "bytes_b64": base64.b64encode(raw).decode()})
    return session, descriptor


def test_project_operation_save_reopen_and_replay_preserve_identities(tmp_path):
    session, source = _session_with_source(tmp_path / "original")
    operation = next(item for item in _call(session, "operation.list", {})["operations"]
                     if item["operation_id"] == "ciw.project-graph.v1")
    assert operation["available"] is True
    completed = _call(session, "operation.execute", {"operation_id": operation["operation_id"],
                                                      "parameters": {"source_id": source["source_id"]}})
    original = _call(session, "bundle.get", {"bundle_id": completed["bundle_id"]})
    step = original["steps"][0]
    assert step["operation_id"] == "ciw.project-graph.v1"
    assert step["result"]["data"]["inspection"]["status"] == "declared"
    assert step["result"]["data"]["authority"]["execution"] == "not_performed"
    assert original["verification"]["authority"]["state_admission"] == "not_performed"
    assert original["runtimes"]["project"]["execution_scope"] == "independent_python_reference_only"
    listed = _call(session, "result.list", {})["results"]
    assert any(item["result_id"] == step["result_id"] for item in listed)
    assert _call(session, "result.get", {"result_id": step["result_id"]}) == step["result"]
    view = _call(session, "experiment.inspect", {"bundle_id": completed["bundle_id"]})
    assert view["object_context"]["physical_validation"] == "not_performed"
    assert view["object_context"]["execution"] == "not_performed"
    assert view["panels"][0]["panel_id"] == "graph"

    saved = session.save_workspace(tmp_path / "saved.json")
    original_create = project_workflow.ProjectGraphWorkflow.create_session
    project_workflow.ProjectGraphWorkflow.create_session = lambda *args, **kwargs: pytest.fail("restore executed a provider")
    try:
        reopened = Session.from_workspace(saved, tmp_path / "reopened")
    finally:
        project_workflow.ProjectGraphWorkflow.create_session = original_create
    assert _call(reopened, "bundle.get", {"bundle_id": completed["bundle_id"]}) == original

    replay = _call(reopened, "bundle.replay", {"bundle_id": completed["bundle_id"]})
    fresh = _call(reopened, "bundle.get", {"bundle_id": replay["bundle"]["bundle_id"]})
    fresh_step = fresh["steps"][0]
    assert fresh["bundle_digest"] != original["bundle_digest"]
    assert fresh_step["execution_id"] != step["execution_id"]
    assert fresh_step["result_id"] != step["result_id"]
    assert fresh_step["numerical_result_id"] == step["numerical_result_id"]
    assert replay["replay_receipt"]["admission"] == "not_performed"
    assert replay["replay_receipt"]["numerical_match"] is True


def test_project_replay_refuses_changed_reference_identity(tmp_path, monkeypatch):
    session, source = _session_with_source(tmp_path)
    completed = _call(session, "operation.execute", {"operation_id": "ciw.project-graph.v1",
                                                      "parameters": {"source_id": source["source_id"]}})
    old_identity = project_workflow.runtime_identity

    def changed_identity():
        value = deepcopy(old_identity())
        value["algorithm"]["code_sha256"] = "0" * 64
        return value

    monkeypatch.setattr(project_workflow, "runtime_identity", changed_identity)
    response = session.handle({"protocol_version": 1, "request_id": "replay",
                               "type": "bundle.replay", "payload": {"bundle_id": completed["bundle_id"]}})
    assert response["type"] == "error"
    assert "runtime identity" in response["payload"]["message"]


def test_project_source_tampering_refuses_before_retention(tmp_path):
    session = Session(make_demo_run(), tmp_path)
    raw = canonical(_source())
    encoded = base64.b64encode(raw).decode()
    source = _call(session, "source.add", {"kind": "project-graph", "label": "project fixture",
                                             "bytes_b64": encoded})
    assert source["source_id"]
    retained = session.workbench.serialize()
    retained["sources"][0]["bytes_b64"] = base64.b64encode(raw + b" ").decode()
    with pytest.raises(ValueError):
        session.workbench.restore(retained)
