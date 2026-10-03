"""Actual pinned CSE execution, independent mapping checks and refused handoff."""
from __future__ import annotations

import base64
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

import pytest

from ciw import ifc_transition as boundary
from ciw.declared_workload import _verification
from ciw.operations.runner import seal
from ciw.telemetry import byte_digest, canonical, digest, _bundle_digest

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "examples/ifc-transition/buildingSMART-wall-opening-window.ifc"
PUBLIC_SHA = "sha256:73b0e45d931d5dc13bfee5fdc7bd80f796526445458b2de74c4168d209097832"


def declaration(public=False):
    ifc = (PUBLIC if public else ROOT / "examples/bim-quantity/room.ifc").read_bytes()
    target = {"ifc_class": "IfcBuildingStorey", "global_id": "2GNgSHJ5j9BRUjqT$7tE8w" if public else "CIWSTOREY00000000000015", "quantity": "ClearHeight"}
    frame = "synthetic-declared-model-frame"
    spec = {"run_id": "experiment.ifc-public-wall.v1" if public else "experiment.ifc-room.v1", "canonical_entity_id": "candidate:logical-ifc-target",
            "required_admission_authority": "authority.external-review.v1", "target": target, "model_frame": frame,
            "source_provenance": {"kind": "PUBLIC_REFERENCE" if public else "SYNTHETIC_FIXTURE",
                "source_uri": "https://github.com/buildingSMART/Sample-Test-Files" if public else "repository:examples/bim-quantity/room.ifc",
                "revision": "e6f1c1d80ac216e1c1d6f88d4650f13d8c8277b7" if public else "ciw.bim-quantity-source.v1",
                "source_path": "IFC 4.0.2.1 (IFC 4)/ISO Spec - ReferenceView_V1.2/wall-with-opening-and-window.ifc" if public else "examples/bim-quantity/room.ifc",
                "license": "CC-BY-4.0" if public else "AGPL-3.0-or-later", "sha256": byte_digest(ifc)}}
    observation = {"schema": "ciw.bim-scalar-observation.v1", "value": 2.99, "variance": .000025, "unit": "m", "frame": frame,
                   "ifc_sha256": byte_digest(ifc), "cross_covariance_policy": "independent", **target}
    return ifc, canonical(observation), spec


@pytest.fixture(scope="module")
def repositories():
    path = os.environ.get("CIW_CSE_REPO")
    if not path:
        pytest.skip("set CIW_CSE_REPO for exact pinned native IFC execution")
    return {"cse": Path(path)}


@pytest.fixture(scope="module")
def room(repositories):
    return boundary.execute_ifc(*declaration(), repositories)


@pytest.fixture(scope="module")
def public_wall(repositories):
    return boundary.execute_ifc(*declaration(public=True), repositories)


def test_original_public_reference_identity_and_attribution():
    raw = PUBLIC.read_bytes()
    assert len(raw) == 12492 and byte_digest(raw) == PUBLIC_SHA
    attribution = PUBLIC.with_name("ATTRIBUTION.md").read_text()
    assert "CC" not in attribution or "Creative Commons" in attribution
    assert "e6f1c1d80ac216e1c1d6f88d4650f13d8c8277b7" in attribution


def test_positive_actual_native_mapping_enters_existing_review_envelope(room, repositories):
    summary = boundary.verify_ifc(room, repositories)
    records = room["records"]
    assert summary["native_status"] == "accepted" and summary["qualification"] == "QUALIFIED"
    assert summary["transition_readiness"] == "READY_FOR_AUTHORITY_REVIEW"
    assert summary["verified_raw_posterior_entries"] == 9
    assert summary["current_runtime_checked"]
    prior, posterior = records["source_state"], records["candidate_state"]
    assert prior["variables"]["ClearHeight"]["value"] == 3
    assert posterior["variables"]["ClearHeight"]["value"] == pytest.approx(2.992)
    assert posterior["uncertainty"]["matrix"][0][0] == pytest.approx(.00002)
    assert prior["clock"] == posterior["clock"] == {"id": "declared-model-reference-no-acquisition-time", "time_s": 0}
    assert records["preservation_gate"]["decision"] == "ELIGIBLE"
    assert records["entity_binding"]["claims"]["canonical_entity_created"] is False
    assert room["native_session"]["verification"]["independent"] is False
    assert records["mapping_verification"]["derived_output_independently_verified"] is False
    assert not summary["state_admission_performed"] and not summary["physical_validity_established"]


def test_public_whole_original_parses_but_refuses_missing_quantity_without_world(public_wall):
    summary = boundary.verify_ifc(public_wall)
    native = public_wall["native_session"]["steps"][0]["result"]["data"]
    audit = public_wall["native_audit"]["data"]
    assert boundary._unblob(public_wall["ifc_artifact"]) == PUBLIC.read_bytes()
    assert native["status"] == "refused" and native["reason"] == "native_refusal"
    assert native["prior"] is native["posterior"] is native["ledger"] is None
    assert audit["parse"]["status"] == "PASS" and audit["inventory"]["instance_count"] == 127
    assert audit["pipeline"]["lowering"]["status"] == "BLOCKED"
    assert audit["pipeline"]["world_digest"] is None
    assert summary["qualification"] == "REFUSED" and summary["reason"] == "source_target_quantity_missing"
    assert summary["transition_readiness"] == "REFUSED"
    records = public_wall["records"]
    assert records["source_state"]["variables"]["ClearHeight"]["value"] is None
    assert records["candidate_state"]["variables"]["ClearHeight"]["value"] is None
    assert records["candidate_state"]["uncertainty"] is None
    assert records["identity_verification"]["status"] == "VERIFIED"
    assert records["preservation_verification"]["status"] == "REFUTED"
    assert records["preservation_gate"]["decision"] == "REFUSED"
    assert not summary["canonical_state_mutated"]


def test_transport_bytes_and_verifier_occurrences_remain_distinct(room):
    first = room["native_session"]["steps"][0]
    reproduction = room["native_session"]["verification"]["reproduction"]
    assert first["execution_id"] != reproduction["execution_id"]
    assert first["result_id"] != reproduction["result_id"]
    assert first["numerical_result_id"] == reproduction["numerical_result_id"]
    for step in (first, reproduction):
        assert json.loads(boundary._unblob(step["transport_output"])) == step["result"]["data"]
    receipt = room["records"]["mapping_verification"]
    assert receipt["execution_ref"] == first["result_id"]
    assert receipt["verification_id"] != first["execution_id"]


def test_read_only_verification_does_not_launch_or_bind_provider(room, monkeypatch):
    before = canonical(room)
    monkeypatch.setattr(boundary.workflow, "_adapters", lambda *args: pytest.fail("offline verifier attempted runtime binding"))
    assert boundary.verify_ifc(room)["qualification"] == "QUALIFIED"
    assert canonical(room) == before


@pytest.mark.parametrize("record_name,field,forged", [
    ("qualification", "status", "QUALIFIED"), ("preservation_gate", "decision", "ELIGIBLE"),
    ("transition_envelope", "readiness", "READY_FOR_AUTHORITY_REVIEW"),
    ("identity_verification", "canonical_entity_id", "other:entity"),
    ("candidate_state", "frame", "different-frame"),
])
def test_fully_resealed_generic_receipts_cannot_upgrade_or_rebind_public_refusal(public_wall, record_name, field, forged):
    value = deepcopy(public_wall)
    value["records"][record_name][field] = forged
    seal(value["records"][record_name])
    seal(value)
    with pytest.raises(ValueError, match="recomputed evidence"):
        boundary.verify_ifc(value)


@pytest.mark.parametrize("fault", ["input", "observation", "missing-output", "output", "tree", "verifier", "binding", "audit-units", "audit-authority", "audit-world"])
def test_fully_resealed_byte_tool_binding_and_audit_tampering_is_refused(room, public_wall, fault):
    value = deepcopy(public_wall if fault.startswith("audit") else room)
    if fault == "input": value["ifc_artifact"] = boundary._blob(boundary._unblob(value["ifc_artifact"]) + b"\n")
    if fault == "observation": value["observation_artifact"] = boundary._blob(b"{}")
    if fault == "missing-output": del value["native_session"]["steps"][0]["transport_output"]
    if fault == "output": value["native_session"]["steps"][0]["transport_output"] = boundary._blob(b"{}")
    if fault == "tree": value["native_session"]["runtimes"]["cse"]["source_tree"] = "0" * 40
    if fault == "verifier": value["records"]["mapping_verification"]["verifier_identity"]["ifc_transition.py"] = "sha256:" + "0" * 64
    if fault == "binding": value["spec"]["canonical_entity_id"] = "other:entity"
    if fault.startswith("audit"):
        report = value["native_audit"]["data"]
        if fault == "audit-units": report["units"][0]["scale_to_metres"] = 1
        if fault == "audit-authority": report["assurance"]["audit_authorizes_decisions"] = True
        if fault == "audit-world": report["pipeline"].update(world_digest="0" * 64, pipeline_ready=True)
        value["native_audit"]["transport_output"] = boundary._blob(canonical(report))
        seal(value["native_audit"])
    value["native_session"]["bundle_digest"] = _bundle_digest(value["native_session"])
    seal(value)
    with pytest.raises(ValueError):
        boundary.verify_ifc(value)


@pytest.mark.parametrize("changes,expected", [({"cross_covariance_policy": "unknown"}, "unknown_cross_covariance"),
                                           ({"frame": "other"}, "frame_mismatch"),
                                           ({"ifc_sha256": "sha256:" + "0" * 64}, "ifc_binding_mismatch")])
def test_actual_inapplicable_measurement_keeps_native_hold_and_unresolved_transition(repositories, changes, expected):
    ifc, observation, spec = declaration()
    obs = json.loads(observation) | changes
    run = boundary.execute_ifc(ifc, canonical(obs), spec, repositories)
    summary = boundary.verify_ifc(run)
    assert summary["native_status"] == "held" and summary["reason"] == expected
    assert summary["qualification"] == "UNRESOLVED" and summary["transition_readiness"] == "UNRESOLVED"
    native = run["native_session"]["steps"][0]["result"]["data"]
    assert native["prior"] == native["posterior"]


def test_tiny_variance_is_verified_without_absolute_floor(repositories):
    ifc, observation, spec = declaration()
    observation = canonical(json.loads(observation) | {"variance": 1e-20})
    run = boundary.execute_ifc(ifc, observation, spec, repositories)
    assert boundary.verify_ifc(run)["qualification"] == "QUALIFIED"
    with pytest.raises(ValueError):
        boundary._near(1e-13, 1e-20)
    with pytest.raises(ValueError):
        boundary._near(1e-30, 0)


def _recommit_step(step):
    data = step["result"]["data"]
    state = data["posterior"]
    module = data["ledger"]["events"][0]["operation"]["module_digest"]
    packed = lambda entries: b"".join(struct.pack("<d", float(x)) for x in entries)
    raw = [i for i, q in enumerate(state["quantities"]) if q["role"] == "raw"]
    state["belief_digest"] = sha256(packed(state["mean"][i] for i in raw) + packed(state["covariance"][i][j] for i in raw for j in raw)).hexdigest()
    state["world_digest"] = sha256(module.encode() + packed(state["mean"]) + packed(x for row in state["covariance"] for x in row)).hexdigest()
    event = data["ledger"]["events"][-1]
    event["result_world_digest"] = state["world_digest"]
    event["event_hash"] = sha256(canonical({key: value for key, value in event.items() if key != "event_hash"})).hexdigest()
    data["ledger"]["integrity"]["head"] = event["event_hash"]
    data["ledger_replay"].update(head=event["event_hash"], world_digest=state["world_digest"])
    step["transport_output"] = boundary._blob(canonical(data))
    step["result"]["result_id"] = digest({key: value for key, value in step["result"].items() if key != "result_id"})
    step.update(result_id=step["result"]["result_id"], result_sha256=digest(step["result"]), numerical_result={"operation_id": boundary.workflow.operation, "data": data})
    step["numerical_result_id"] = digest(step["numerical_result"])


def test_coherently_resealed_numerical_fault_is_refuted_and_retained(room):
    value = deepcopy(room)
    native = value["native_session"]
    for step in (native["steps"][0], native["verification"]["reproduction"]):
        data = step["result"]["data"]
        # Forged posterior target mean, all state/ledger/result/transport hashes
        # consistently recomputed. Source binding and native structure still pass.
        row = next(i for i, q in enumerate(data["posterior"]["quantities"]) if q["quantity"] == "ClearHeight")
        data["posterior"]["mean"][row] += .01
        _recommit_step(step)
    native["bundle_digest"] = _bundle_digest(native)
    native["verification"] = _verification(native, native["verification"]["reproduction"])
    source = boundary.workflow._source(boundary.workflow._validate(native))
    inspected = boundary.inspect_source(boundary._unblob(value["ifc_artifact"]), value["spec"]["target"])
    verdict = boundary._independent(source, native["steps"][0]["result"]["data"], inspected)
    assert verdict["mapping_status"] == "REFUTED" and verdict["reason"] == "independent_mapping_disagreement"
    # Old READY records cannot survive even when their seals are valid.
    seal(value)
    with pytest.raises(ValueError, match="recomputed evidence"):
        boundary.verify_ifc(value)
    # A rejected numerical result may still be retained as counterevidence.
    value["records"] = boundary._records(native, value["native_audit"], value["spec"], inspected, verdict)
    value["claims"]["independent_raw_conditioning_verified"] = False
    seal(value)
    summary = boundary.verify_ifc(value)
    assert summary["native_status"] == "accepted" and summary["qualification"] == "REFUSED"
    assert summary["transition_readiness"] == "REFUSED"
    assert value["records"]["candidate_state"]["variables"]["ClearHeight"]["value"] is None


def test_absent_frame_label_stays_unresolved_property(repositories):
    ifc, observation, spec = declaration()
    spec["model_frame"] = None
    observation = canonical(json.loads(observation) | {"frame": None})
    run = boundary.execute_ifc(ifc, observation, spec, repositories)
    summary = boundary.verify_ifc(run)
    assert summary["native_status"] == "held" and summary["reason"] == "frame_unresolved"
    check = next(row for row in run["records"]["preservation_verification"]["checks"] if row["property_id"] == "frame.declared-label.v1")
    assert check["status"] == "UNRESOLVED" and check["method"] == "NOT_PERFORMED" and check["evidence_ref"] is None


def test_fully_resealed_audit_compiled_world_rebinding_is_refused(room):
    value = deepcopy(room)
    value["native_audit"]["data"]["pipeline"]["world_digest"] = "0" * 64
    value["native_audit"]["transport_output"] = boundary._blob(canonical(value["native_audit"]["data"]))
    seal(value["native_audit"])
    seal(value)
    with pytest.raises(ValueError, match="compiled world differs"):
        boundary.verify_ifc(value)


@pytest.mark.parametrize("fault", ["role-swap", "unrelated-raw-mean", "source-prior-covariance"])
def test_independent_source_inventory_and_all_raw_entries_cannot_be_bypassed(room, fault):
    native = room["native_session"]
    source = boundary.workflow._source(base64.b64decode(native["source"]["evidence"][0]["bytes_b64"]))
    inspected = boundary.inspect_source(boundary._unblob(room["ifc_artifact"]), room["spec"]["target"])
    data = deepcopy(native["steps"][0]["result"]["data"])
    row = next(i for i, q in enumerate(data["prior"]["quantities"]) if q["quantity"] == "Length")
    if fault == "role-swap":
        data["prior"]["quantities"][row]["role"] = "derived"
        data["posterior"]["quantities"][row]["role"] = "derived"
    if fault == "unrelated-raw-mean": data["prior"]["mean"][row] += 1
    if fault == "source-prior-covariance": data["prior"]["covariance"][row][row] *= 2
    verdict = boundary._independent(source, data, inspected)
    assert verdict["mapping_status"] == "REFUTED" and verdict["reason"] == "independent_mapping_disagreement"


def test_changed_current_provider_and_changed_executable_are_refused(room, repositories, monkeypatch):
    from ciw.adapters.protocol import AdapterRefusal
    runtime = room["native_session"]["runtimes"]["cse"]
    with monkeypatch.context() as context:
        context.setattr(boundary.workflow, "pin", boundary.workflow.pin | {"revision": "0" * 40})
        with pytest.raises(ValueError, match="runtime pin"):
            boundary.verify_ifc(room)
    from ciw.adapters.subprocess import PinnedSubprocessAdapter
    with monkeypatch.context() as context:
        context.setattr(PinnedSubprocessAdapter, "_executable_digest", lambda self: "0" * 64)
        with pytest.raises(AdapterRefusal, match="Python executable digest"):
            boundary.verify_ifc(room, repositories)
    assert runtime["revision"] == boundary.bim_quantity.PIN["revision"]


def test_cli_publishes_create_only_and_retained_verification_runs_without_provider(room, tmp_path):
    record = tmp_path / "room-run.json"
    record.write_bytes(canonical(room))
    process = subprocess.run([sys.executable, "-m", "ciw.net", "interop", "verify-ifc", str(record)], capture_output=True, text=True, cwd=ROOT)
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout)["qualification"] == "QUALIFIED"
