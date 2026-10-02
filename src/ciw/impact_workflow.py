"""Impact workload using existing Session evidence and operation envelopes."""
from __future__ import annotations

from copy import deepcopy
import csv
from hashlib import sha256
import math
from pathlib import Path
import tempfile

from .adapters.protocol import InstrumentManifest
from .control_contracts import keys, load, save_new
from .core.identities import evidence_id, new_identity, validate_evidence_identity, validate_identity
from .core.records import validate_run_structure
from .operations.registry import Operation
from .operations.runner import check_seal, digest, seal

SIMULATE = "impact.spring-contact.v1"
VERIFY = "impact.spring-contact-verify.v1"
FRAME = "impact.normal.inward_positive.v1"
AUTHORITY = {"physical_validation": "not_established", "scale_preservation": "not_established",
             "state_admission": "not_performed", "hardware_actuation": "not_performed"}


def runtime_identity(kind: str) -> dict:
    from . import impact_contract, impact_reference, impact_solver, impact_verification
    modules = [impact_contract, impact_solver] if kind == "solver" else [impact_contract, impact_reference, impact_verification]
    modules.append(__import__(__name__, fromlist=["*"]))
    raw = b"\0".join(Path(m.__file__).name.encode() + b"\0" +
                     Path(m.__file__).read_text(encoding="utf-8").replace("\r\n", "\n").encode()
                     for m in modules)
    return {"provider": "ciw.impact." + kind, "version": "1", "code_sha256": sha256(raw).hexdigest(),
            "source_normalization": "utf8_lf", "scope": "synthetic_elastic_contact_only"}


def make_source(request: dict) -> dict:
    from .impact_contract import validate_request
    request = validate_request(request)
    model = request["model"]
    duration = math.pi * math.sqrt(model["mass_kg"] / model["stiffness_n_per_m"]) * request["integration"]["duration_factor"]
    manifest = InstrumentManifest(
        instrument_id="impact-initial-state.v1", role="synthetic_initial_conditions",
        units={"compression": "m", "velocity": "m/s", "force": "N"}, frames=(FRAME,),
        sampling={"kind": "one_initial_state_at_first_contact"},
        supported_operations=(SIMULATE, VERIFY),
        calibration_requirements={"physical_measurements": "none; synthetic benchmark"},
    )
    run = {"run_schema": "run.v1", "run_id": "run-impact-" + digest(request)[7:23],
           "instrument": manifest.instrument_id,
           "metadata": {"duration_s": duration, "sample_count": 1, "sample_rate_hz": None,
                        "coordinate_frame": FRAME, "manifest": manifest.to_dict(), "impact_request": request,
                        "provenance": {"source": "synthetic initial conditions, not acquired measurements",
                                       "generator": "ciw.impact_workflow.make_source", "generator_version": 1}},
           "time_s": [0.0], "channels": {"compression": {"unit": "m", "values": [0.0]},
                                         "velocity": {"unit": "m/s", "values": [model["initial_speed_m_per_s"]]},
                                         "force": {"unit": "N", "values": [0.0]}}, "render": {}}
    run["evidence_id"] = evidence_id(run)
    return run


def source_request(run: dict) -> dict:
    validate_run_structure(run)
    validate_evidence_identity(run)
    request = run["metadata"]["impact_request"]
    if run != make_source(request):
        raise ValueError("Impact source must be the exact declared synthetic initial conditions")
    return deepcopy(request)


def _simulate(run: dict, parameters: dict) -> dict:
    from .impact_solver import simulate
    keys(parameters, set())
    return simulate(source_request(run))


def _candidate(run: dict, parameters: dict) -> dict:
    from .impact_contract import validate_result
    keys(parameters, {"candidate"})
    candidate = parameters["candidate"]
    check_seal(candidate)
    if (candidate.get("schema") != "ciw.operation-result.v1" or candidate.get("operation_id") != SIMULATE
            or candidate.get("role") != "backend" or candidate.get("evidence_id") != run["evidence_id"]
            or candidate.get("run_id") != run["run_id"] or candidate.get("parameters") != {}):
        raise ValueError("Verification candidate must bind the exact impact source and simulation operation")
    validate_identity(candidate.get("result_id"), "result")
    validate_identity(candidate.get("execution_id"), "execution")
    validate_result(source_request(run), candidate["data"])
    return candidate


def _verify(run: dict, parameters: dict) -> dict:
    from .impact_verification import verify
    candidate = _candidate(run, parameters)
    return {"schema": "ciw.impact-verification-payload.v1", "verification_id": new_identity("verification"),
            "candidate_result_id": candidate["result_id"], "candidate_execution_id": candidate["execution_id"],
            "candidate_record_digest": candidate["record_digest"], "source_evidence_id": run["evidence_id"],
            "report": verify(source_request(run), candidate["data"]), "authority": deepcopy(AUTHORITY)}


def operations() -> list[Operation]:
    return [Operation(SIMULATE, "backend", _simulate, lambda: runtime_identity("solver")),
            Operation(VERIFY, "verification", _verify, lambda: runtime_identity("verifier"))]


def registry():
    """Explicit trusted binding; saved data never activates these operations."""
    from .operations.registry import default_registry
    result = default_registry()
    for operation in operations():
        result.register(operation)
    return result


def validate_payload(operation: str, data: dict, run: dict, parameters: dict, selection: dict) -> None:
    """Read stored contracts without rerunning either numerical implementation."""
    from .impact_contract import validate_result
    if operation == SIMULATE:
        keys(parameters, set())
        validate_result(source_request(run), data)
    elif operation == VERIFY:
        from .impact_verification import validate_report
        candidate = _candidate(run, parameters)
        keys(data, {"schema", "verification_id", "candidate_result_id", "candidate_execution_id",
                    "candidate_record_digest", "source_evidence_id", "report", "authority"})
        validate_identity(data["verification_id"], "verification")
        if (data["schema"] != "ciw.impact-verification-payload.v1" or data["authority"] != AUTHORITY
                or data["source_evidence_id"] != run["evidence_id"]
                or data["candidate_result_id"] != candidate["result_id"]
                or data["candidate_execution_id"] != candidate["execution_id"]
                or data["candidate_record_digest"] != candidate["record_digest"]):
            raise ValueError("Impact verification identity or authority binding differs")
        validate_report(source_request(run), candidate["data"], data["report"])
    else:
        raise ValueError("Unsupported impact operation")


def validate_result_dependencies(results: dict) -> None:
    """Verification snapshots must match an actually retained solver occurrence."""
    verification_ids = set()
    for result in results.values():
        if result.get("operation_id") != VERIFY:
            continue
        candidate = result["parameters"]["candidate"]
        if results.get(candidate["result_id"]) != candidate:
            raise ValueError("Impact verification candidate differs from its retained solver occurrence")
        identity = result["data"]["verification_id"]
        if identity in verification_ids:
            raise ValueError("Duplicate impact verification occurrence identity")
        verification_ids.add(identity)


def _execute(session, operation: str, parameters: dict) -> dict:
    reply = session.handle({"protocol_version": 1, "request_id": "impact-workload",
                            "type": "operation.execute", "payload": {"operation_id": operation, "parameters": parameters}})
    if reply["type"] != "response":
        raise ValueError(reply["payload"]["message"])
    return reply["payload"]


def run(request: dict, destination: Path) -> dict:
    from .session import Session
    source = make_source(request)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    save_new(destination / "request.json", source["metadata"]["impact_request"])
    session = Session(source, destination, operations=registry())
    candidate = _execute(session, SIMULATE, {})
    verification = None
    if candidate["status"] == "completed":
        verification = _execute(session, VERIFY, {"candidate": candidate["result"]})
    session.save_workspace(destination / "workspace.json")
    if candidate["status"] != "completed" or verification is None or verification["status"] != "completed":
        return inspect(destination)
    save_new(destination / "verification.json", verification["result"]["data"])
    from .impact_preservation import build
    save_new(destination / "preservation.json", build(source_request(session.run), candidate["result"]["data"],
                                                     verification["result"]["data"]["report"]))
    return inspect(destination)


def _read(destination: Path):
    from .session import Session
    destination = Path(destination)
    with tempfile.TemporaryDirectory(prefix="impact-inspect-") as temporary:
        session = Session.from_workspace(destination / "workspace.json", Path(temporary))
    if load(destination / "request.json") != source_request(session.run):
        raise ValueError("Retained request differs from source evidence")
    candidates = [r for r in session.results.values() if r["operation_id"] == SIMULATE]
    verifications = [r for r in session.results.values() if r["operation_id"] == VERIFY]
    executions = list(session.executions.values())
    if any(e["operation_id"] not in {SIMULATE, VERIFY} for e in executions):
        raise ValueError("Impact bundle contains an unrelated execution")
    if len(executions) == 1 and executions[0]["operation_id"] == SIMULATE and executions[0]["status"] == "refused":
        if session.results or (destination / "verification.json").exists():
            raise ValueError("Refused solver bundle cannot contain results")
        return session, None, None
    if (len(executions) == 2 and len(candidates) == 1 and not verifications
            and sum(e["status"] == "refused" and e["operation_id"] == VERIFY for e in executions) == 1):
        if len(session.results) != 1 or (destination / "verification.json").exists():
            raise ValueError("Refused verifier bundle contains unexpected results")
        return session, candidates[0], None
    if len(candidates) != 1 or len(verifications) != 1 or len(session.results) != 2 or len(executions) != 2:
        raise ValueError("Impact bundle requires one solver and one independent verification occurrence")
    candidate, verification = candidates[0], verifications[0]
    if verification["parameters"]["candidate"] != candidate:
        raise ValueError("Verification does not bind the retained candidate occurrence")
    if load(destination / "verification.json") != verification["data"]:
        raise ValueError("Verification artifact differs from retained verification result")
    from .impact_preservation import validate
    validate(load(destination / "preservation.json"), source_request(session.run), candidate["data"],
             verification["data"]["report"])
    return session, candidate, verification


def inspect(destination: Path) -> dict:
    session, candidate, verification = _read(destination)
    if verification is None:
        attempts = [{name: deepcopy(value) for name, value in entry.items() if name != "parameters"}
                    for entry in session.executions.values()]
        return {"schema": "ciw.impact-inspection.v1", "status": "REFUSE",
                "evidence_id": session.run["evidence_id"], "executions": attempts,
                "fresh_execution": False, "fresh_numerical_verification": False, "authority": deepcopy(AUTHORITY)}
    report = verification["data"]["report"]
    preservation = load(Path(destination) / "preservation.json")
    return {"schema": "ciw.impact-inspection.v1", "status": report["qualification"]["action"],
            "qualification": report["qualification"], "evidence_id": session.run["evidence_id"],
            "operation_id": SIMULATE, "execution_id": candidate["execution_id"], "result_id": candidate["result_id"],
            "verification_operation_id": VERIFY, "verification_execution_id": verification["execution_id"],
            "verification_id": verification["data"]["verification_id"], "checks": report["checks"],
            "metrics": report["metrics"], "fresh_execution": False, "fresh_numerical_verification": False,
            "preservation": {"contract_ref": preservation["contract"]["record_digest"],
                             "verification_ref": preservation["verification"]["record_digest"],
                             "verification_status": preservation["verification"]["status"],
                             "admission_eligibility": preservation["admission_gate"]["decision"],
                             "state_admission_performed": False},
            "authority": deepcopy(AUTHORITY)}


def verify_retained(destination: Path) -> dict:
    from .impact_verification import verify
    session, candidate, verification = _read(destination)
    if verification is None:
        return inspect(destination)
    fresh = verify(source_request(session.run), candidate["data"])
    if fresh != verification["data"]["report"]:
        raise ValueError("Independent recomputation differs from retained verification report")
    result = inspect(destination)
    result["fresh_numerical_verification"] = True
    result["recomputed_report_digest"] = fresh["record_digest"]
    result["recomputed_with_runtime"] = runtime_identity("verifier")
    return result


def export_csv(destination: Path, output: Path) -> dict:
    checked = verify_retained(destination)
    if checked["status"] != "LOCAL":
        raise ValueError("Only a numerically qualified LOCAL trace can be exported")
    _, candidate, _ = _read(destination)
    trace = candidate["data"]["primary"]
    names = ["time_s", "compression_m", "velocity_m_per_s", "force_n"]
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(names)
        writer.writerows(zip(*(trace[name] for name in names)))
    return {"status": "exported", "file": str(output), "source_result_id": candidate["result_id"],
            "source_execution_id": candidate["execution_id"], "authority": deepcopy(AUTHORITY)}
