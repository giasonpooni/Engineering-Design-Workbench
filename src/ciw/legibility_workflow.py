"""NET attachment and read-only transport of retained impact identities.

Compilation is a representation operation. It never updates source scientific
verification, issues calibration, imports executable code, or admits a state.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import uuid

from .core.identities import content_identity, evidence_id, validate_evidence_identity, validate_identity
from .core.records import validate_run_structure
from .operations.registry import Operation
from .operations.runner import check_seal, validate_execution
from .session import loads_json
from .legibility_runtime import runtime_identity

OPERATION = "legibility.compile.v1"
IMPACT_PAIRS = {
    "impact.spring-contact.v1": "impact.spring-contact-verify.v1",
    "impact.crush-contact.v1": "impact.crush-contact-verify.v1",
    "impact.plate-contact.v1": "impact.plate-contact-verify.v1",
}


def _parameters(run, parameters):
    from .legibility import validate_contract
    if not isinstance(parameters, dict) or set(parameters) != {"contract"}:
        raise ValueError("Legibility compilation requires exactly one contract")
    contract = validate_contract(parameters["contract"])
    if contract["bindings"]["evidence_id"] != run["evidence_id"]:
        raise ValueError("Legibility source must bind this Session evidence")
    if contract["semantics"]["coordinate_frame"] != run["metadata"]["coordinate_frame"]:
        raise ValueError("Legibility source frame differs from retained evidence")
    return contract


def operation():
    from .legibility import compile_bundle
    return Operation(OPERATION, "backend", lambda run, parameters: compile_bundle(_parameters(run, parameters)),
                     runtime_identity)


def validate_payload(operation_id, data, run, parameters, selection):
    from .legibility import compile_bundle
    if operation_id != OPERATION or data != compile_bundle(_parameters(run, parameters)):
        raise ValueError("Legibility result differs from its deterministic source compilation")


def compile_in_session(run, contract, destination):
    """Execute through Session so representation occurrence identities persist."""
    from .session import Session
    session = Session(run, Path(destination))
    response = session.handle({"protocol_version": 1, "request_id": uuid.uuid4().hex,
                               "type": "operation.execute", "payload": {
                                   "operation_id": OPERATION, "parameters": {"contract": contract}}})
    if response["type"] == "error":
        raise ValueError(response["payload"]["message"])
    payload = response["payload"]
    session.save_workspace(Path(destination) / "workspace.json")
    if payload["status"] != "completed":
        raise ValueError(payload["execution"]["refusal"]["message"])
    return payload


def artifact(artifact_id, media_type, data):
    return {"artifact_id": artifact_id, "media_type": media_type,
            "sha256": "sha256:" + hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


def _property(name, value, unit, refs):
    return {"property_id": name, "value": value, "unit": unit,
            "uncertainty": {"status": "unknown", "standard_uncertainty": None},
            "evidence_refs": refs}


def import_impact(workspace_path, *, object_id, version, label):
    """Inspect existing NET seals/bindings, without loading or rerunning a solver.

    Numerical results are retained declarations. The exact workspace bytes are
    included as an artifact; no physical or fresh numerical check is asserted.
    """
    workspace_path = Path(workspace_path)
    raw = workspace_path.read_bytes()
    workspace = loads_json(raw.decode("utf-8"))
    if not isinstance(workspace, dict) or workspace.get("workspace_version") != 2:
        raise ValueError("Require an impact Session workspace v2")
    run = workspace["run"]
    validate_run_structure(run)
    validate_evidence_identity(run)
    results = workspace["results"]
    if not isinstance(results, list) or len(results) != 2:
        raise ValueError("Require one retained impact candidate and its verifier result")
    result_map = {}
    for result in results:
        check_seal(result)
        validate_identity(result.get("result_id"), "result")
        validate_identity(result.get("execution_id"), "execution")
        if (result.get("evidence_id") != run["evidence_id"] or result.get("run_id") != run["run_id"]
                or result.get("verification_id") is not None or result.get("verification_status") != "not_verified"
                or result.get("schema") != "ciw.operation-result.v1"):
            raise ValueError("Impact result source/verification binding differs")
        if result["result_id"] in result_map:
            raise ValueError("Repeated impact result identity")
        result_map[result["result_id"]] = result
    candidates = [result for result in results if result.get("operation_id") in IMPACT_PAIRS]
    if len(candidates) != 1:
        raise ValueError("Unsupported or ambiguous impact candidate")
    candidate = candidates[0]
    verification = next(result for result in results if result is not candidate)
    data = verification["data"]
    if (candidate.get("role") != "backend" or verification.get("role") != "verification"
            or verification.get("operation_id") != IMPACT_PAIRS[candidate["operation_id"]]
            or data.get("schema") != "ciw.impact-verification-payload.v1"
            or data.get("candidate_result_id") != candidate["result_id"]
            or data.get("candidate_execution_id") != candidate["execution_id"]
            or data.get("candidate_record_digest") != candidate["record_digest"]
            or data.get("source_evidence_id") != run["evidence_id"]
            or verification.get("parameters") != {"candidate": candidate}):
        raise ValueError("Impact verification does not bind the retained candidate")
    validate_identity(data.get("verification_id"), "verification")
    check_seal(candidate["data"])
    report = data["report"]
    check_seal(report)
    request_digest = content_identity(run["metadata"]["impact_request"])
    if (candidate["data"].get("request_digest") != request_digest
            or report.get("request_digest") != request_digest
            or report.get("result_digest") != candidate["data"]["record_digest"]):
        raise ValueError("Impact report request/result digest differs")
    executions = workspace["executions"]
    if not isinstance(executions, list) or len(executions) != 2:
        raise ValueError("Require both retained impact execution records")
    found = set()
    for execution in executions:
        validate_execution(execution, run, workspace["selection"]["revision"], result_map)
        if execution["execution_id"] in found or execution["status"] != "completed":
            raise ValueError("Repeated or incomplete impact execution")
        found.add(execution["execution_id"])
    if found != {result["execution_id"] for result in results}:
        raise ValueError("Impact execution coverage differs")
    refs = [run["evidence_id"], candidate["result_id"], data["verification_id"]]
    trace = candidate["data"]["primary"]
    force = trace["force_n"]
    if not isinstance(force, list) or not force:
        raise ValueError("Impact primary force trace is empty")
    # This extracts a retained scalar; the solver/report are not re-executed.
    properties = [_property("peak_force", max(force), "N", refs)]
    model = run["metadata"]["impact_request"]["model"]
    for field, unit in {"mass_kg": "kg", "stiffness_n_per_m": "N/m",
                        "initial_speed_m_per_s": "m/s", "youngs_modulus_pa": "Pa",
                        "thickness_m": "m"}.items():
        if field in model:
            properties.append(_property(field, model[field], unit, refs))
    claims = [{"claim_id": "retained-impact-scope", "statement": candidate["data"]["claim_scope"],
               "status": "simulated", "evidence_refs": refs},
              {"claim_id": "numerical-report", "statement": "Retained numerical report status: " + report["status"],
               "status": "simulated", "evidence_refs": refs},
              {"claim_id": "physical-validation", "statement": "Experimental material response is not established by this import.",
               "status": "unresolved", "evidence_refs": refs}]
    artifacts = {"impact-workspace": raw}
    contract = {"schema": "ciw.legibility-contract.v1",
                "object": {"object_id": object_id, "version": version, "label": label, "kind": "impact-specimen"},
                "bindings": {"evidence_id": run["evidence_id"], "operation_id": candidate["operation_id"],
                             "execution_id": candidate["execution_id"], "verification_id": data["verification_id"]},
                "semantics": {"coordinate_frame": run["metadata"]["coordinate_frame"], "properties": properties,
                              "relationships": [{"relation": "simulation-result", "target_id": candidate["result_id"],
                                                 "target_version": candidate["record_digest"]}],
                              "assumptions": ["Imported synthetic initial conditions; no acquired measurements.",
                                              "Existing seals and identity bindings checked; numerical verifier not re-executed.",
                                              "Declared model: " + str(model)]},
                "claims": claims,
                "qualification": {"status": "numerical_only" if report["status"] == "PASS" else "unqualified",
                                  "calibration_refs": [], "verification_refs": [data["verification_id"], report["record_digest"]],
                                  "canonical_admission": False},
                "vision": {"image_artifact_id": None, "annotations": []},
                "artifacts": [artifact("impact-workspace", "application/json", raw)]}
    return deepcopy(run), contract, artifacts


def demo_source(destination):
    """An illustrative synthetic coupon observation, with a real NET summary run."""
    from .session import Session
    from .adapters.protocol import InstrumentManifest
    from .operations.registry import OperationRegistry
    run = {"run_schema": "run.v1", "run_id": "run-legibility-synthetic-coupon-v1",
           "instrument": "legibility.synthetic-impact-fixture.v1",
           "metadata": {"duration_s": 0.003, "sample_count": 3, "sample_rate_hz": 1000.0,
                        "coordinate_frame": "impact.normal.inward_positive.v1",
                        "provenance": {"source": "illustrative synthetic fixture; not an experiment or qualified simulation"}},
           "time_s": [0.0, 0.001, 0.002], "channels": {"force": {"unit": "N", "values": [0.0, 200.0, 0.0]}},
           "render": {}}
    run["metadata"]["manifest"] = InstrumentManifest(
        instrument_id=run["instrument"], role="synthetic_fixture", units={"force": "N"},
        frames=(run["metadata"]["coordinate_frame"],),
        supported_operations=("legibility.fixture-summary.v1", OPERATION),
        sampling={"kind": "illustrative_fixture"}).to_dict()
    run["evidence_id"] = evidence_id(run)
    registry = OperationRegistry()
    registry.register(Operation("legibility.fixture-summary.v1", "backend", lambda run, parameters: fixture_summary(run, parameters), runtime_identity))
    registry.register(operation())
    session = Session(run, Path(destination), operations=registry)
    response = session.handle({"protocol_version": 1, "request_id": uuid.uuid4().hex,
                               "type": "operation.execute", "payload": {"operation_id": "legibility.fixture-summary.v1", "parameters": {}}})
    if response["type"] != "response" or response["payload"]["status"] != "completed":
        raise ValueError("Synthetic fixture summary failed")
    result = response["payload"]["result"]
    session.save_workspace(Path(destination) / "workspace.json")
    raw = (Path(destination) / "workspace.json").read_bytes()
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360">'
           '<rect width="640" height="360" fill="#11202d"/><rect x="128" y="126" width="384" height="108" rx="8" '
           'fill="#79b9b2"/><text x="320" y="290" text-anchor="middle" fill="white" font-size="20">'
           'Synthetic coupon diagram — no photograph</text></svg>').encode()
    artifacts = {"fixture-workspace": raw, "specimen-diagram": svg}
    refs = [run["evidence_id"], result["result_id"]]
    contract = {"schema": "ciw.legibility-contract.v1",
                "object": {"object_id": "notations:specimen:demo-coupon-001", "version": "1",
                           "label": "Polymer coupon / synthetic impact fixture", "kind": "impact-specimen"},
                "bindings": {"evidence_id": run["evidence_id"], "operation_id": result["operation_id"],
                             "execution_id": result["execution_id"], "verification_id": None},
                "semantics": {"coordinate_frame": run["metadata"]["coordinate_frame"],
                              "properties": [_property("peak_force", result["data"]["maximum"], "N", refs),
                                             _property("illustrative_acceptance_limit", 150.0, "N", refs),
                                             _property("material", "polymer grade unassigned", "1", refs)],
                              "relationships": [{"relation": "derived-statistics", "target_id": result["result_id"],
                                                 "target_version": result["record_digest"]}],
                              "assumptions": ["Force samples are a synthetic illustrative fixture, not acquired measurements.",
                                              "150 N is a demonstration threshold, not a manufacturing specification.",
                                              "The SVG is a diagram; no vision detector, pose estimator, or photograph is supplied."]},
                "claims": [{"claim_id": "threshold-failure", "statement": "Synthetic 200 N peak exceeds the illustrative 150 N limit.",
                            "status": "failed", "evidence_refs": refs},
                           {"claim_id": "physical-validation", "statement": "Real material and component performance remain unresolved.",
                            "status": "unresolved", "evidence_refs": refs}],
                "qualification": {"status": "unqualified", "calibration_refs": [], "verification_refs": [],
                                  "canonical_admission": False},
                "vision": {"image_artifact_id": "specimen-diagram", "annotations": [
                    {"annotation_id": "coupon-bbox", "coordinate_frame": "image:specimen-diagram:normalized-xy",
                     "bbox_xywh_normalized": [0.2, 0.35, 0.6, 0.3]}]},
                "artifacts": [artifact("fixture-workspace", "application/json", raw),
                              artifact("specimen-diagram", "image/svg+xml", svg)]}
    return run, contract, artifacts


def fixture_summary(run, parameters):
    if parameters != {} or run["instrument"] != "legibility.synthetic-impact-fixture.v1":
        raise ValueError("Fixture summary requires the explicit illustrative source")
    return {"maximum": max(run["channels"]["force"]["values"]), "unit": "N",
            "source_kind": "illustrative_synthetic_fixture", "sample_count": len(run["time_s"])}


def validate_fixture_payload(operation_id, data, run, parameters, selection):
    if operation_id != "legibility.fixture-summary.v1" or data != fixture_summary(run, parameters):
        raise ValueError("Fixture summary differs from its retained source")
