"""Correction lifecycle uses retained identities without rewriting evidence.

These tests exercise Session, workspace, CLI and socket surfaces using the
provider-free encoder reference. Synthetic fixtures test dependency handling;
they do not establish an independently validated physical calibration.
"""

import asyncio
import base64
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from ciw import cli, machine_workflow
from ciw.core.identities import content_identity
from ciw.dependency_graph import artifact_graph
from ciw.instruments import make_demo_run
from ciw.server import WorkbenchServer
from ciw.session import Session, read_json, write_json


EXAMPLES = Path(__file__).parents[1] / "examples" / "corrections"
OPERATION = "ciw.encoder-position.v1"


def _request(kind, payload=None):
    return {"protocol_version": 1, "request_id": "correction-" + kind,
            "type": kind, "payload": {} if payload is None else payload}


def _call(session, kind, payload=None):
    response = session.handle(_request(kind, payload))
    assert response["type"] == "response", response
    return response["payload"]


def _add_source(session, filename, label):
    raw = (EXAMPLES / filename).read_bytes()
    return _call(session, "source.add", {
        "kind": "machine-manifest", "label": label,
        "bytes_b64": base64.b64encode(raw).decode(),
    })


def _add_reference(session, value, label):
    raw = json.dumps(value, allow_nan=True).encode()
    return _call(session, "source.add", {"kind": "reference-evidence", "label": label,
                                        "bytes_b64": base64.b64encode(raw).decode()})


def _execute(session, source):
    completed = _call(session, "operation.execute", {
        "operation_id": OPERATION, "parameters": {"source_id": source["source_id"]},
    })
    return _call(session, "bundle.get", {"bundle_id": completed["bundle_id"]})


def _sources(tmp_path):
    session = Session(make_demo_run(), tmp_path)
    old = _add_source(session, "encoder-original.json", "original calibration")
    new = _add_source(session, "encoder-corrected.json", "corrected calibration")
    return session, old, new


def _claim_payload(dependencies, claim_type="estimated"):
    return {"claim_type": claim_type, "predicate": "carriage position is bounded",
            "scope": "synthetic encoder reference at 300 decoded counts",
            "basis": "declared manifest and algebraic position result",
            "dependencies": list(dependencies)}


def _proposal_payload(old, new):
    return {"old_source_id": old["source_id"], "new_source_id": new["source_id"],
            "kind": "calibration", "reason": "synthetic withheld reference exposes a zero offset"}


def _review_payload(session, proposal, decision="accept"):
    return {"correction_id": proposal["correction_id"], "decision": decision,
            "expected_revision": session.correction_journal.revision,
            "reviewer": "integration-test reviewer", "reason": "reviewed synthetic reference residual"}


def _accept(session, old, new):
    proposal = _call(session, "correction.propose", _proposal_payload(old, new))
    _call(session, "correction.review", _review_payload(session, proposal))
    return proposal


def test_accepted_correction_invalidates_transitive_claims_without_rewriting_artifacts(tmp_path):
    session, old, new = _sources(tmp_path)
    run_before = deepcopy(session.run)
    recording_before = (tmp_path / session.recording_file).read_bytes()
    recording_result = _call(session, "analysis.stats")
    original = _execute(session, old)
    original_step = original["steps"][0]
    original_source = _call(session, "source.get", {"source_id": old["source_id"]})
    estimated = _call(session, "claim.add", _claim_payload([original_step["result_id"]]))
    predicted = _call(session, "claim.add", _claim_payload([estimated["claim_id"]], "predicted"))
    for claim in (estimated, predicted):
        assert claim["verification_status"] == "not_verified"
        assert claim["verification_id"] is None
        assert claim["state_admission"] == "unadmitted"
        assert claim["execution_authorized"] is False

    proposal = _call(session, "correction.propose", _proposal_payload(old, new))
    pending = _call(session, "dependency.inspect")
    assert pending["corrections"][0]["status"] == "proposed"
    assert pending["artifact_status"][predicted["claim_id"]]["status"] == "current"
    _call(session, "correction.review", _review_payload(session, proposal))
    corrected = _execute(session, new)
    corrected_step = corrected["steps"][0]
    current_claim = _call(session, "claim.add", _claim_payload([corrected_step["result_id"]]))
    status = _call(session, "dependency.inspect")

    assert status["revision"] == 5
    assert status["corrections"][0]["status"] == "accepted"
    stale_ids = [old["source_id"], original["bundle_digest"], original_step["execution_id"],
                 original_step["result_id"], estimated["claim_id"], predicted["claim_id"]]
    for identity in stale_ids:
        assert status["artifact_status"][identity]["status"] == "stale"
        assert status["artifact_status"][identity]["stale_by"] == [proposal["correction_id"]]
    for identity in [new["source_id"], corrected["bundle_digest"], corrected_step["execution_id"],
                     corrected_step["result_id"], current_claim["claim_id"], old["evidence_id"],
                     session.run["evidence_id"], recording_result["result_id"]]:
        assert status["artifact_status"][identity]["status"] == "current"
    for key in ("execution_id", "result_id", "numerical_result_id"):
        assert corrected_step[key] != original_step[key]
    assert corrected["bundle_digest"] != original["bundle_digest"]
    assert original_step["result"]["data"]["position"]["position"] == pytest.approx(1.001)
    assert corrected_step["result"]["data"]["position"]["position"] == pytest.approx(0.998)

    assert _call(session, "bundle.get", {"bundle_id": original["bundle_digest"]}) == original
    assert _call(session, "source.get", {"source_id": old["source_id"]}) == original_source
    response = session.handle(_request("result.get", {"result_id": original_step["result_id"]}))
    assert response["payload"] == original_step["result"]
    assert response["dependency_status"]["status"] == "stale"
    assert "dependency_status" not in response["payload"]
    assert _call(session, "result.get", {"result_id": recording_result["result_id"]}) == recording_result
    assert session.run == run_before
    assert (tmp_path / session.recording_file).read_bytes() == recording_before


def test_rejected_correction_retains_history_and_leaves_dependencies_current(tmp_path):
    session, old, new = _sources(tmp_path)
    bundle = _execute(session, old)
    proposal = _call(session, "correction.propose", _proposal_payload(old, new))
    review = _call(session, "correction.review", _review_payload(session, proposal, "reject"))
    status = _call(session, "dependency.inspect")
    assert status["revision"] == 2
    assert status["corrections"][0] == {"proposal": proposal, "review": review, "status": "rejected"}
    assert all(row["status"] == "current" for row in status["artifact_status"].values())
    assert _call(session, "bundle.get", {"bundle_id": bundle["bundle_digest"]}) == bundle


def test_source_labels_cannot_make_withdrawn_evidence_current_again(tmp_path):
    session, old, new = _sources(tmp_path)
    before_alias = _add_source(session, "encoder-original.json", "independent looking label")
    assert before_alias["source_id"] != old["source_id"]
    assert before_alias["evidence_id"] == old["evidence_id"]
    _accept(session, old, new)
    after_alias = _add_source(session, "encoder-original.json", "label created after review")
    alias_bundle = _execute(session, after_alias)
    status = _call(session, "dependency.inspect")["artifact_status"]
    for identity in [old["source_id"], before_alias["source_id"], after_alias["source_id"],
                     alias_bundle["bundle_digest"], alias_bundle["steps"][0]["result_id"]]:
        assert status[identity]["status"] == "stale"
    assert status[old["evidence_id"]]["status"] == "current"


@pytest.mark.parametrize("mutation", ["schema", "extra_field", "boolean_value", "nonfinite_value",
                                      "nonfinite_context", "negative_uncertainty", "naive_timestamp",
                                      "undeclared_origin", "missing_unit"])
def test_scalar_reference_import_rejects_invalid_schema_without_retention(tmp_path, mutation):
    session = Session(make_demo_run(), tmp_path)
    value = json.loads((EXAMPLES / "encoder-reference.json").read_text())
    if mutation == "schema":
        value["schema"] = "ciw.reference-evidence.v999"
    elif mutation == "extra_field":
        value["execution_authorized"] = True
    elif mutation == "boolean_value":
        value["value"] = True
    elif mutation == "nonfinite_value":
        value["value"] = float("nan")
    elif mutation == "nonfinite_context":
        value["context"]["nested"] = {"unbounded": float("inf")}
    elif mutation == "negative_uncertainty":
        value["uncertainty"] = {"status": "declared", "standard_uncertainty": -0.001}
    elif mutation == "naive_timestamp":
        value["observed_at"] = "2026-10-03T00:00:00"
    elif mutation == "undeclared_origin":
        value["origin"] = "independently_validated_physical_measurement"
    else:
        value.pop("unit")
    before = session.workbench.serialize()
    response = session.handle(_request("source.add", {
        "kind": "reference-evidence", "label": "invalid scalar reference",
        "bytes_b64": base64.b64encode(json.dumps(value).encode()).decode(),
    }))
    assert response["type"] == "error"
    assert response["payload"]["code"] in {"invalid_payload", "MALFORMED_RESPONSE"}
    assert session.workbench.serialize() == before


def test_scalar_reference_is_retained_data_and_has_no_registered_executable_operation(tmp_path):
    session = Session(make_demo_run(), tmp_path)
    value = json.loads((EXAMPLES / "encoder-reference.json").read_text())
    value["origin"] = "operator_record"
    value["uncertainty"] = {"status": "declared", "standard_uncertainty": 0.0001}
    reference = _add_reference(session, value, "declared scalar observation")
    retained = _call(session, "source.get", {"source_id": reference["source_id"]})
    assert retained["source_schema"] == "ciw.reference-evidence.v1"
    assert json.loads(base64.b64decode(retained["bytes_b64"])) == value
    operation_ids = {row["operation_id"] for row in _call(session, "operation.list")["operations"]}
    assert "ciw.reference-evidence.v1" not in operation_ids
    with pytest.raises(ValueError, match="no executable operation"):
        session.workbench.bind_workflow("reference-evidence", {})
    attempt = _call(session, "operation.execute", {
        "operation_id": "ciw.reference-evidence.v1", "parameters": {"source_id": reference["source_id"]},
    })
    assert attempt["status"] == "refused" and attempt["result"] is None
    assert _call(session, "bundle.list")["bundles"] == []


def test_reference_correction_invalidates_residual_claim_without_invalidating_encoder_output(tmp_path):
    session, calibration, _ = _sources(tmp_path)
    encoder = _execute(session, calibration)
    result_id = encoder["steps"][0]["result_id"]
    value = json.loads((EXAMPLES / "encoder-reference.json").read_text())
    reference = _add_reference(session, value, "original withheld reference")
    residual_claim = _call(session, "claim.add", _claim_payload([result_id, reference["source_id"]]))
    amended = deepcopy(value)
    amended["value"] = 0.9981
    amended["observed_at"] = "2026-10-03T00:01:00Z"
    amended_reference = _add_reference(session, amended, "amended withheld reference")
    _accept(session, reference, amended_reference)
    status = _call(session, "dependency.inspect")["artifact_status"]
    assert status[reference["source_id"]]["status"] == "stale"
    assert status[residual_claim["claim_id"]]["status"] == "stale"
    assert status[amended_reference["source_id"]]["status"] == "current"
    assert status[calibration["source_id"]]["status"] == "current"
    assert status[result_id]["status"] == "current"
    assert status[encoder["bundle_digest"]]["status"] == "current"
    assert _call(session, "bundle.get", {"bundle_id": encoder["bundle_digest"]}) == encoder


def test_v4_restore_is_offline_and_preserves_journal_and_scientific_records(tmp_path):
    session, old, new = _sources(tmp_path / "original")
    old_bundle = _execute(session, old)
    _call(session, "claim.add", _claim_payload([old_bundle["steps"][0]["result_id"]]))
    _accept(session, old, new)
    new_bundle = _execute(session, new)
    saved = session.save_workspace(tmp_path / "workspace.json")
    assert read_json(saved)["workspace_version"] == 4
    with patch.object(machine_workflow.MachineManifestWorkflow, "create_session",
                      side_effect=AssertionError("restore executed the encoder provider")), \
         patch("ciw.operations.runner.execute", side_effect=AssertionError("restore executed an operation")), \
         patch("ciw.session.compute_statistics", side_effect=AssertionError("restore calculated statistics")), \
         patch("ciw.session.compute_spectrum", side_effect=AssertionError("restore calculated a spectrum")):
        restored = Session.from_workspace(saved, tmp_path / "restored")
        assert _call(restored, "dependency.inspect") == _call(session, "dependency.inspect")
        for bundle in (old_bundle, new_bundle):
            assert _call(restored, "bundle.get", {"bundle_id": bundle["bundle_digest"]}) == bundle
    assert restored.correction_journal.serialize() == session.correction_journal.serialize()
    assert restored.run == session.run


def test_accepted_correction_can_reopen_its_atomic_checkpoint_without_explicit_save(tmp_path):
    session, old, new = _sources(tmp_path / "original")
    old_source = _call(session, "source.get", {"source_id": old["source_id"]})
    new_source = _call(session, "source.get", {"source_id": new["source_id"]})
    old_bundle = _execute(session, old)
    new_bundle = _execute(session, new)
    _call(session, "claim.add", _claim_payload([old_bundle["steps"][0]["result_id"]]))
    _accept(session, old, new)
    # Journal publication itself must persist the journal and every referenced
    # source/bundle together. No workspace.save request appears in this test.
    checkpoint = tmp_path / "original" / "workspace.json"
    retained = read_json(checkpoint)
    assert retained["workspace_version"] == 4
    assert retained["correction_journal"] == session.correction_journal.serialize()
    with patch.object(machine_workflow.MachineManifestWorkflow, "create_session",
                      side_effect=AssertionError("checkpoint restore executed a provider")):
        restored = Session.from_workspace(checkpoint, tmp_path / "restored")
    assert _call(restored, "dependency.inspect") == _call(session, "dependency.inspect")
    for source in (old_source, new_source):
        assert _call(restored, "source.get", {"source_id": source["source_id"]}) == source
    for bundle in (old_bundle, new_bundle):
        assert _call(restored, "bundle.get", {"bundle_id": bundle["bundle_digest"]}) == bundle


def _reseal(record):
    record["record_digest"] = content_identity({key: value for key, value in record.items()
                                                if key != "record_digest"})


@pytest.mark.parametrize("mutation", ["unsealed", "authority", "missing_dependency", "revision",
                                      "source_binding", "review_revision", "event_order"])
def test_malformed_and_resealed_journals_refuse_before_any_restore_output(tmp_path, mutation):
    session, old, new = _sources(tmp_path / "original")
    _call(session, "claim.add", _claim_payload([old["source_id"]]))
    _accept(session, old, new)
    saved = session.save_workspace(tmp_path / "workspace.json")
    workspace = read_json(saved)
    journal = workspace["correction_journal"]
    claim, proposal, review = journal["events"]
    if mutation == "unsealed":
        claim["predicate"] = "changed after sealing"
    elif mutation == "authority":
        claim["execution_authorized"] = True
    elif mutation == "missing_dependency":
        claim["dependencies"] = ["claim-" + "f" * 32]
    elif mutation == "revision":
        claim["revision"] = 2
    elif mutation == "source_binding":
        proposal["old_evidence_id"] = new["evidence_id"]
    elif mutation == "review_revision":
        review["expected_revision"] = 0
    elif mutation == "event_order":
        review["created_at"] = "2000-01-01T00:00:00+00:00"
    if mutation != "unsealed":
        for event in journal["events"]:
            _reseal(event)
    _reseal(journal)
    write_json(saved, workspace)
    rejected = tmp_path / "rejected"
    with patch("ciw.session.write_json") as writer, \
         patch.object(machine_workflow.MachineManifestWorkflow, "create_session",
                      side_effect=AssertionError("malformed restore executed a provider")):
        with pytest.raises(ValueError):
            Session.from_workspace(saved, rejected)
        writer.assert_not_called()
    assert not rejected.exists()


@pytest.mark.parametrize("action", ["claim.add", "correction.propose", "correction.review"])
def test_failed_journal_storage_does_not_publish_an_event_in_memory(tmp_path, action):
    session, old, new = _sources(tmp_path)
    # Retain one event first, so failure must preserve an existing checkpoint.
    _call(session, "claim.add", _claim_payload([old["source_id"]]))
    if action == "claim.add":
        payload = _claim_payload([new["source_id"]])
    elif action == "correction.propose":
        payload = _proposal_payload(old, new)
    else:
        proposal = _call(session, "correction.propose", _proposal_payload(old, new))
        payload = _review_payload(session, proposal)
    before = session.correction_journal.serialize()
    dependency_before = _call(session, "dependency.inspect")
    checkpoint = tmp_path / "workspace.json"
    bytes_before = checkpoint.read_bytes()
    with patch("ciw.session.write_json", side_effect=OSError("test disk failure")) as writer:
        response = session.handle(_request(action, payload))
    writer.assert_called_once()
    assert Path(writer.call_args.args[0]) == checkpoint
    assert response["type"] == "error"
    assert response["payload"]["code"] == "storage_error"
    assert session.correction_journal.serialize() == before
    assert _call(session, "dependency.inspect") == dependency_before
    assert checkpoint.read_bytes() == bytes_before


def test_stale_review_revision_and_repeat_review_do_not_publish_events(tmp_path):
    session, old, new = _sources(tmp_path)
    proposal = _call(session, "correction.propose", _proposal_payload(old, new))
    payload = _review_payload(session, proposal)
    _call(session, "claim.add", _claim_payload([old["source_id"]]))
    before = session.correction_journal.serialize()
    stale = session.handle(_request("correction.review", payload))
    assert stale["type"] == "error" and "revision conflict" in stale["payload"]["message"]
    assert session.correction_journal.serialize() == before
    _call(session, "correction.review", _review_payload(session, proposal))
    before = session.correction_journal.serialize()
    duplicate = session.handle(_request("correction.review", _review_payload(session, proposal)))
    assert duplicate["type"] == "error" and "final decision" in duplicate["payload"]["message"]
    assert session.correction_journal.serialize() == before


@pytest.mark.parametrize("version", [1, 2, 3])
def test_older_workspaces_restore_with_empty_correction_history(tmp_path, version):
    session = Session(make_demo_run(), tmp_path / "original")
    if version == 1:
        _call(session, "analysis.stats")
    elif version == 2:
        _call(session, "operation.execute", {"operation_id": "statistics.v1", "parameters": {}})
    else:
        source = _add_source(session, "encoder-original.json", "legacy native workflow")
        _execute(session, source)
    saved = session.save_workspace(tmp_path / "workspace.json")
    assert read_json(saved)["workspace_version"] == version
    with patch.object(machine_workflow.MachineManifestWorkflow, "create_session",
                      side_effect=AssertionError("legacy restore executed a provider")), \
         patch("ciw.operations.runner.execute", side_effect=AssertionError("legacy restore ran analysis")):
        restored = Session.from_workspace(saved, tmp_path / "restored")
    assert restored.run == session.run
    assert restored.results == session.results
    assert restored.executions == session.executions
    assert restored.workbench.serialize() == session.workbench.serialize()
    status = _call(restored, "dependency.inspect")
    assert status["revision"] == 0 and status["claims"] == [] and status["corrections"] == []
    assert all(row["status"] == "current" for row in status["artifact_status"].values())


def _directory_state(directory):
    return {str(path.relative_to(directory)): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in directory.rglob("*") if path.is_file()}


def test_cli_dependencies_validates_offline_without_writing_beside_workspace(tmp_path, capsys):
    session, old, new = _sources(tmp_path / "retained")
    _execute(session, old)
    _accept(session, old, new)
    path = session.save_workspace(tmp_path / "retained" / "workspace.json")
    expected = _call(session, "dependency.inspect")
    before = _directory_state(tmp_path)
    with patch.object(machine_workflow.MachineManifestWorkflow, "create_session",
                      side_effect=AssertionError("dependency CLI executed a provider")):
        assert cli.main(["dependencies", str(path)]) == 0
    assert json.loads(capsys.readouterr().out) == expected
    assert _directory_state(tmp_path) == before


def test_dependency_graph_tracks_legacy_jspt_and_native_inputs_without_guessing():
    class RetainedWorkbench:
        def dependency_artifacts(self):
            return {"sources": [{"source_id": "source:native", "evidence_id": "evidence:native",
                                 "kind": "native-interop", "label": "native reference"}],
                    "bundles": [{"bundle_id": "bundle:native", "source_id": "source:native",
                                 "result_ids": ["result:native"], "kind": "native-interop",
                                 "upstream_bundle_id": None}],
                    "executions": [{"execution_id": "execution:native", "source_id": "source:native",
                                    "bundle_id": "bundle:native", "result_id": "result:native",
                                    "operation_id": "native-reference", "status": "completed",
                                    "input_refs": ["result:jspt", "unknown:declared-input"]}]}

    results = {
        "result:statistics": {"result_id": "result:statistics", "execution_id": "execution:statistics",
                              "evidence_id": "evidence:recording", "operation_id": "statistics.v1"},
        "result:jspt": {"result_id": "result:jspt", "execution_id": "execution:jspt",
                        "evidence_id": "evidence:recording", "operation_id": "jspt.spectrum.v1",
                        "parameters": {"source_result_id": "result:statistics"}},
    }
    before = deepcopy(results)
    graph = artifact_graph({"evidence_id": "evidence:recording", "run_id": "run:test"},
                           results, {}, RetainedWorkbench())
    assert graph["result:jspt"]["dependencies"] == ["execution:jspt"]
    assert "result:statistics" in graph["execution:jspt"]["dependencies"]
    assert "result:jspt" in graph["execution:native"]["dependencies"]
    assert graph["execution:native"]["unresolved_input_refs"] == ["unknown:declared-input"]
    assert "unknown:declared-input" not in graph
    assert results == before


def test_socket_dependency_changes_reach_native_observers_and_preserve_spatial_scope(tmp_path):
    async def exercise():
        session, old, _ = _sources(tmp_path)
        bridge = WorkbenchServer(session)
        async with serve(bridge.handler, "127.0.0.1", 0) as listener:
            url = "ws://127.0.0.1:" + str(listener.sockets[0].getsockname()[1])
            async with connect(url) as author, connect(url) as observer, connect(url + "/spatial") as spatial:
                assert json.loads(await asyncio.wait_for(author.recv(), 3))["type"] == "session.snapshot"
                assert json.loads(await asyncio.wait_for(observer.recv(), 3))["type"] == "session.snapshot"
                assert json.loads(await asyncio.wait_for(spatial.recv(), 3))["type"] == "spatial.ready"
                await author.send(json.dumps(_request("claim.add", _claim_payload([old["source_id"]]))))
                assert json.loads(await asyncio.wait_for(author.recv(), 3))["type"] == "response"
                changed = json.loads(await asyncio.wait_for(author.recv(), 3))
                assert changed["type"] == "dependencies.changed"
                assert changed["payload"] == {"session_id": session.session_id, "revision": 1}
                assert json.loads(await asyncio.wait_for(observer.recv(), 3)) == changed
                # The next spatial response proves no dependency event leaked
                # into this endpoint's queue.
                await spatial.send(json.dumps(_request("spatial.list")))
                assert json.loads(await asyncio.wait_for(spatial.recv(), 3))["type"] == "response"
                await spatial.send(json.dumps(_request("claim.add", _claim_payload([old["source_id"]]))))
                refused = json.loads(await asyncio.wait_for(spatial.recv(), 3))
                assert refused["payload"]["code"] == "read_only_view"
                await author.send(json.dumps(_request("claim.add", _claim_payload(["missing:artifact"]))))
                assert json.loads(await asyncio.wait_for(author.recv(), 3))["type"] == "error"
                await observer.send(json.dumps(_request("dependency.inspect")))
                inspected = json.loads(await asyncio.wait_for(observer.recv(), 3))
                assert inspected["type"] == "response"  # failed write emitted no change event
                assert inspected["payload"]["revision"] == 1
    asyncio.run(exercise())
