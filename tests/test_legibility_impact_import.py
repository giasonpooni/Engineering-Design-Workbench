"""Read-only import of synthetic retained impact identities and commitments.

These fixtures exercise retained-record bindings, not an impact solver or a
scientific qualification. PASS is an explicitly illustrative report declaration.
"""

from copy import deepcopy
import hashlib
import json

import pytest

from ciw.core.identities import content_identity, digest, evidence_id
from ciw.instruments import make_demo_run
from ciw.legibility import compile_bundle, verify_bundle
from ciw.legibility_workflow import import_impact
from ciw.operations.runner import seal


STAMP = "2026-10-03T05:00:00+00:00"


def _records(run, selection, *, operation_id, role, occurrence, data, parameters):
    """Create a sealed retained pair without invoking any provider."""
    shared = {
        "execution_id": "execution-" + occurrence * 32,
        "operation_id": operation_id,
        "evidence_id": run["evidence_id"],
        "run_id": run["run_id"],
        "selection_revision": selection["revision"],
        "channel": selection["channel"],
        "interval_s": deepcopy(selection["interval_s"]),
        "parameters": deepcopy(parameters),
        "created_at": STAMP,
        "runtime": {"provider": "synthetic-retained-impact-fixture", "version": "1"},
    }
    result = seal({
        "schema": "ciw.operation-result.v1",
        "result_id": "result-" + occurrence * 32,
        **deepcopy(shared),
        "role": role,
        "recording_file": "recording-" + digest(run) + ".json",
        "verification_id": None,
        "verification_status": "not_verified",
        "data": deepcopy(data),
    })
    execution = seal({
        "schema": "ciw.execution.v1",
        **deepcopy(shared),
        "status": "completed",
        "result_id": result["result_id"],
    })
    return result, execution


def _workspace(report_status="PASS"):
    run = make_demo_run()
    request = {
        "schema": "test.synthetic-impact-request.v1",
        "model": {"mass_kg": 1.0, "stiffness_n_per_m": 25.0,
                  "initial_speed_m_per_s": 0.4},
    }
    run["metadata"]["impact_request"] = request
    run["evidence_id"] = evidence_id(run)
    selection = {
        "run_id": run["run_id"], "channel": "q",
        "interval_s": [0.0, run["metadata"]["duration_s"]],
        "cursor_s": run["time_s"][0],
        "coordinate_frame": run["metadata"]["coordinate_frame"], "revision": 0,
    }
    candidate_data = seal({
        "schema": "test.synthetic-impact-result.v1",
        "request_digest": content_identity(request),
        "primary": {"force_n": [0.0, 2.0, 0.0]},
        "claim_scope": "test-illustrative retained numerical declaration; no physical validation",
    })
    candidate, candidate_execution = _records(
        run, selection, operation_id="impact.spring-contact.v1", role="backend",
        occurrence="1", data=candidate_data, parameters={},
    )
    report = seal({
        "schema": "test.synthetic-impact-report.v1", "status": report_status,
        "request_digest": content_identity(request),
        "result_digest": candidate_data["record_digest"],
    })
    verification_data = {
        "schema": "ciw.impact-verification-payload.v1",
        "candidate_result_id": candidate["result_id"],
        "candidate_execution_id": candidate["execution_id"],
        "candidate_record_digest": candidate["record_digest"],
        "source_evidence_id": run["evidence_id"],
        "verification_id": "verification-" + "3" * 32,
        "report": report,
    }
    verification, verifier_execution = _records(
        run, selection, operation_id="impact.spring-contact-verify.v1", role="verification",
        occurrence="2", data=verification_data, parameters={"candidate": candidate},
    )
    return {
        "workspace_version": 2, "saved_at": STAMP, "run": run,
        "selection": selection, "view_settings": {},
        "results": [candidate, verification],
        "executions": [candidate_execution, verifier_execution],
    }


def _write(path, workspace):
    # Deliberate formatting belongs to the retained raw artifact commitment.
    raw = (json.dumps(workspace, indent=3, ensure_ascii=False) + "\n\n").encode("utf-8")
    path.write_bytes(raw)
    return raw


def _import(path):
    return import_impact(path, object_id="notations:specimen:retained-test",
                         version="7", label="Synthetic retained impact specimen")


def test_import_retains_exact_bytes_and_identities_without_write_or_solver(tmp_path, monkeypatch):
    workspace = _workspace()
    path = tmp_path / "workspace.json"
    raw = _write(path, workspace)
    before = {item.name: item.read_bytes() for item in tmp_path.iterdir()}

    def forbidden(*args, **kwargs):
        raise AssertionError("Retained impact import must not write records or execute providers")

    import ciw.operations.runner as runner
    import ciw.adapters.registry as adapters
    import ciw.session as session_module
    from ciw.operations.registry import OperationRegistry
    from ciw.session import Session

    monkeypatch.setattr(session_module, "write_json", forbidden)
    monkeypatch.setattr(runner, "execute", forbidden)
    monkeypatch.setattr(OperationRegistry, "get", forbidden)
    monkeypatch.setattr(adapters, "default_registry", forbidden)
    monkeypatch.setattr(Session, "__init__", forbidden)

    run, contract, artifacts = _import(path)
    candidate, verification = workspace["results"]
    assert run == workspace["run"]
    assert artifacts == {"impact-workspace": raw}
    assert contract["bindings"] == {
        "evidence_id": run["evidence_id"],
        "operation_id": candidate["operation_id"],
        "execution_id": candidate["execution_id"],
        "verification_id": verification["data"]["verification_id"],
    }
    assert contract["qualification"]["status"] == "numerical_only"
    assert contract["qualification"]["canonical_admission"] is False
    assert contract["semantics"]["relationships"] == [{
        "relation": "simulation-result", "target_id": candidate["result_id"],
        "target_version": candidate["record_digest"],
    }]
    properties = {item["property_id"]: item for item in contract["semantics"]["properties"]}
    assert properties["peak_force"]["value"] == 2.0
    assert properties["peak_force"]["unit"] == "N"
    assert properties["peak_force"]["uncertainty"] == {"status": "unknown", "standard_uncertainty": None}
    assert properties["mass_kg"]["value"] == 1.0
    assert properties["stiffness_n_per_m"]["unit"] == "N/m"
    assert contract["artifacts"][0]["sha256"] == "sha256:" + hashlib.sha256(raw).hexdigest()
    check = verify_bundle(compile_bundle(contract, artifacts), artifacts=artifacts)
    assert check["content_intact"] is True and check["artifact_status"] == "verified"
    assert check["physical_validation_status"] == "not_assessed"
    assert {item.name: item.read_bytes() for item in tmp_path.iterdir()} == before
    assert all(result["verification_id"] is None for result in workspace["results"])
    assert all(result["verification_status"] == "not_verified" for result in workspace["results"])


@pytest.mark.parametrize("field,value", [
    ("candidate_result_id", "result-" + "4" * 32),
    ("candidate_execution_id", "execution-" + "4" * 32),
    ("candidate_record_digest", "sha256:" + "0" * 64),
    ("source_evidence_id", "sha256:" + "0" * 64),
])
def test_resealed_verifier_with_wrong_candidate_binding_is_refused(tmp_path, field, value):
    workspace = _workspace()
    verifier = workspace["results"][1]
    verifier["data"][field] = value
    seal(verifier)
    path = tmp_path / "workspace.json"
    _write(path, workspace)
    with pytest.raises(ValueError, match="verification does not bind"):
        _import(path)


def test_duplicate_completed_execution_identity_is_refused(tmp_path):
    workspace = _workspace()
    workspace["executions"][1] = deepcopy(workspace["executions"][0])
    path = tmp_path / "workspace.json"
    _write(path, workspace)
    with pytest.raises(ValueError, match="Repeated or incomplete impact execution"):
        _import(path)


@pytest.mark.parametrize("field", ["request_digest", "result_digest"])
def test_resealed_numerical_report_with_wrong_request_or_result_is_refused(tmp_path, field):
    workspace = _workspace()
    verifier = workspace["results"][1]
    report = verifier["data"]["report"]
    report[field] = "sha256:" + "0" * 64
    seal(report)
    seal(verifier)
    path = tmp_path / "workspace.json"
    _write(path, workspace)
    with pytest.raises(ValueError, match="report request/result digest differs"):
        _import(path)


def test_retained_failed_report_remains_unqualified_without_physical_promotion(tmp_path):
    workspace = _workspace(report_status="FAIL")
    path = tmp_path / "workspace.json"
    raw = _write(path, workspace)
    _, contract, artifacts = _import(path)
    assert artifacts["impact-workspace"] == raw
    assert contract["qualification"]["status"] == "unqualified"
    assert contract["qualification"]["canonical_admission"] is False
    numerical_claim = next(claim for claim in contract["claims"] if claim["claim_id"] == "numerical-report")
    assert numerical_claim["statement"].endswith("FAIL")
    assert numerical_claim["status"] == "simulated"
    report = verify_bundle(compile_bundle(contract, artifacts), artifacts=artifacts)
    assert report["declared_qualification"]["status"] == "unqualified"
    assert report["physical_validation_status"] == "not_assessed"
    assert report["canonical_admission"] is False
