"""Representation integrity and current dependency eligibility remain separate."""

import base64
from copy import deepcopy
from pathlib import Path

import pytest

from ciw.instruments import make_demo_run
from ciw.legibility import sign_bundle, verify_bundle
from ciw.legibility_workflow import OPERATION, import_impact
from ciw.operations.runner import check_seal
from ciw.session import Session, read_json


EXAMPLES = Path(__file__).parents[1] / "examples" / "corrections"


def _call(session, kind, payload=None):
    reply = session.handle({"protocol_version": 1, "request_id": "legibility-correction-" + kind,
                            "type": kind, "payload": {} if payload is None else payload})
    assert reply["type"] == "response", reply
    return reply["payload"]


def _source(session, filename):
    return _call(session, "source.add", {
        "kind": "machine-manifest", "label": filename,
        "bytes_b64": base64.b64encode((EXAMPLES / filename).read_bytes()).decode(),
    })


def _accept(session, old, new):
    proposal = _call(session, "correction.propose", {
        "old_source_id": old["source_id"], "new_source_id": new["source_id"],
        "kind": "calibration", "reason": "synthetic encoder offset correction",
    })
    _call(session, "correction.review", {
        "correction_id": proposal["correction_id"], "decision": "accept",
        "expected_revision": session.correction_journal.revision,
        "reviewer": "declared integration reviewer", "reason": "reviewed synthetic offset",
    })
    return proposal


def _contract(session, neutral):
    return {
        "schema": "ciw.legibility-contract.v1",
        "object": {"object_id": "notations:synthetic-encoder", "version": "1",
                   "label": "Synthetic encoder representation", "kind": "simulation-result"},
        "bindings": {"evidence_id": session.run["evidence_id"],
                     "operation_id": neutral["operation_id"],
                     "execution_id": neutral["execution_id"], "verification_id": None},
        "semantics": {"coordinate_frame": session.run["metadata"]["coordinate_frame"],
                      "properties": [{"property_id": "position", "value": 1.001, "unit": "m",
                                      "uncertainty": {"status": "unknown", "standard_uncertainty": None},
                                      "evidence_refs": []}],
                      "relationships": [], "assumptions": ["Synthetic reference only."]},
        "claims": [{"claim_id": "synthetic-position", "statement": "Illustrative encoder position.",
                    "status": "simulated", "evidence_refs": []}],
        "qualification": {"status": "unqualified", "calibration_refs": [],
                          "verification_refs": [], "canonical_admission": False},
        "vision": {"image_artifact_id": None, "annotations": []}, "artifacts": [],
    }


@pytest.fixture
def prepared(tmp_path):
    session = Session(make_demo_run(), tmp_path / "original")
    neutral = _call(session, "analysis.stats")
    old = _source(session, "encoder-original.json")
    new = _source(session, "encoder-corrected.json")
    completed = _call(session, "operation.execute", {
        "operation_id": "ciw.encoder-position.v1", "parameters": {"source_id": old["source_id"]},
    })
    original = _call(session, "bundle.get", {"bundle_id": completed["bundle_id"]})
    return session, old, new, neutral, original["steps"][0]


def _compile(session, contract):
    completed = _call(session, "operation.execute", {
        "operation_id": OPERATION, "parameters": {"contract": contract},
    })
    assert completed["status"] == "completed", completed
    return completed["result"]


@pytest.mark.parametrize("reference_slot", [
    "relationship", "property_evidence", "claim_evidence", "execution_binding",
    "calibration_reference", "verification_reference",
])
def test_each_declared_reference_slot_propagates_source_result_staleness(prepared, reference_slot):
    session, old, new, neutral, step = prepared
    contract = _contract(session, neutral)
    result_id = step["result_id"]
    if reference_slot == "relationship":
        contract["semantics"]["relationships"] = [{"relation": "derived-result", "target_id": result_id,
                                                    "target_version": step["numerical_result_id"]}]
    elif reference_slot == "property_evidence":
        contract["semantics"]["properties"][0]["evidence_refs"] = [result_id]
    elif reference_slot == "claim_evidence":
        contract["claims"][0]["evidence_refs"] = [result_id]
    elif reference_slot == "execution_binding":
        contract["bindings"].update(operation_id=step["operation_id"], execution_id=step["execution_id"])
    else:
        field = "calibration_refs" if reference_slot == "calibration_reference" else "verification_refs"
        contract["qualification"][field] = [result_id]
    compiled = _compile(session, contract)
    before = deepcopy(compiled)
    assert _call(session, "dependency.inspect")["artifact_status"][compiled["result_id"]]["status"] == "current"
    proposal = _accept(session, old, new)
    status = _call(session, "dependency.inspect")
    for identity in (step["result_id"], compiled["execution_id"], compiled["result_id"]):
        assert status["artifact_status"][identity]["status"] == "stale"
        assert status["artifact_status"][identity]["stale_by"] == [proposal["correction_id"]]
    # The source recording and unrelated operation remain current. Only the
    # declared downstream path is withdrawn from current dependency use.
    for identity in (session.run["evidence_id"], neutral["result_id"], new["source_id"]):
        assert status["artifact_status"][identity]["status"] == "current"
    assert session.results[compiled["result_id"]] == before
    check_seal(compiled)
    assert compiled["verification_id"] is None
    assert compiled["verification_status"] == "not_verified"
    assert compiled["data"]["source"]["qualification"]["canonical_admission"] is False
    assert status["state_admission"] == "not_performed"
    assert status["hardware_actuation"] == "not_performed"


def test_valid_signature_and_immutable_exports_do_not_make_stale_dependencies_current(prepared, tmp_path, monkeypatch):
    pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")
    session, old, new, neutral, step = prepared
    contract = _contract(session, neutral)
    contract["semantics"]["relationships"] = [{"relation": "derived-result", "target_id": step["result_id"],
                                               "target_version": step["numerical_result_id"]}]
    compiled = _compile(session, contract)
    bundle = compiled["data"]
    envelope = sign_bundle(bundle, b"1" * 32)
    trusted = {envelope["key_id"]: base64.b64decode(envelope["public_key_b64"])}
    result_bytes = (session.output_dir / (compiled["result_id"] + ".json")).read_bytes()
    _accept(session, old, new)
    claim = _call(session, "claim.add", {
        "claim_type": "predicted", "predicate": "representation may inform a position estimate",
        "scope": "synthetic encoder", "basis": "retained representation",
        "dependencies": [compiled["result_id"]],
    })
    dependency = _call(session, "dependency.inspect")
    assert dependency["artifact_status"][claim["claim_id"]]["status"] == "stale"
    for field, expected in {"verification_status": "not_verified", "verification_id": None,
                            "state_admission": "unadmitted", "execution_authorized": False}.items():
        assert claim[field] == expected
    inspection = verify_bundle(bundle, envelope, trusted_keys=trusted)
    assert inspection["content_intact"] is True
    assert inspection["signature_valid"] is True
    assert inspection["issuer_trusted"] is True
    assert inspection["physical_validation_status"] == "not_assessed"
    assert inspection["canonical_admission"] is False
    assert dependency["artifact_status"][compiled["result_id"]]["status"] == "stale"
    assert (session.output_dir / (compiled["result_id"] + ".json")).read_bytes() == result_bytes
    saved = session.save_workspace(tmp_path / "corrected-workspace.json")
    raw = saved.read_bytes()
    assert read_json(saved)["workspace_version"] == 4
    # The v2 impact importer must not drop a v4 correction journal to make a
    # historical representation appear current.
    with pytest.raises(ValueError, match="workspace v2"):
        import_impact(saved, object_id="notations:synthetic-encoder", version="1", label="Synthetic encoder")
    assert saved.read_bytes() == raw

    def no_execution(*args, **kwargs):
        raise AssertionError("Dependency restore must not execute a provider")

    monkeypatch.setattr("ciw.session.execute_operation", no_execution)
    monkeypatch.setattr("ciw.machine_workflow.MachineManifestWorkflow.create_session", no_execution)
    restored = Session.from_workspace(saved, tmp_path / "restored")
    assert _call(restored, "dependency.inspect") == dependency
    assert restored.results[compiled["result_id"]] == compiled


def test_external_references_stay_unresolved_and_embedded_strings_create_no_edges(prepared):
    session, old, new, neutral, step = prepared
    contract = _contract(session, neutral)
    old_id = step["result_id"]
    contract["object"]["label"] = old_id
    contract["semantics"]["properties"][0]["value"] = {"looks_like_a_ref": old_id}
    contract["semantics"]["assumptions"] = [old_id]
    contract["claims"][0]["statement"] = old_id
    external_verification = "verification-" + "7" * 32
    contract["bindings"]["verification_id"] = external_verification
    contract["semantics"]["relationships"] = [{"relation": old_id, "target_id": "external:result",
                                               "target_version": old_id}]
    compiled = _compile(session, contract)
    _accept(session, old, new)
    status = _call(session, "dependency.inspect")
    for identity in (compiled["execution_id"], compiled["result_id"]):
        node = status["nodes"][identity]
        assert old_id not in node["dependencies"]
        assert node["unresolved_input_refs"] == ["external:result", external_verification]
        assert status["artifact_status"][identity]["status"] == "current"
    assert external_verification not in status["nodes"]
    assert "external:result" not in status["nodes"]
    assert compiled["verification_id"] is None


def test_refused_compilation_does_not_project_an_unvalidated_contract(prepared):
    session, _, _, _, step = prepared
    failed = _call(session, "operation.execute", {
        "operation_id": OPERATION, "parameters": {"contract": {"arbitrary": step["result_id"]}},
    })
    assert failed["status"] == "refused"
    graph = _call(session, "dependency.inspect")["nodes"]
    assert graph[failed["execution"]["execution_id"]]["dependencies"] == [session.run["evidence_id"]]
