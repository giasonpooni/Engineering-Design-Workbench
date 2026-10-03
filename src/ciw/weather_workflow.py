"""Weather science through existing NET Session evidence and execution records."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import platform
import tempfile

from .adapters.protocol import InstrumentManifest
from .control_contracts import keys, load, save_new
from .core.identities import evidence_id, new_identity, validate_evidence_identity, validate_identity
from .core.records import validate_run_structure
from .operations.registry import Operation
from .operations.runner import check_seal, digest
from .weather_contract import AUTHORITY, COMPUTE, VERIFY, FRAME


def runtime_identity(kind: str) -> dict:
    from . import weather_contract as contract
    if kind not in {"calculator", "checker"}:
        raise ValueError("Unsupported weather runtime kind")
    modules = [contract, __import__(__name__, fromlist=["*"]), *set(contract.providers().values())]
    raw = b"\0".join(Path(module.__file__).name.encode() + b"\0" +
                     Path(module.__file__).read_text(encoding="utf-8").replace("\r\n", "\n").encode()
                     for module in sorted(modules, key=lambda item: item.__name__))
    return {"provider": "ciw.weather." + kind, "version": "1",
            "code_sha256": sha256(raw).hexdigest(), "source_normalization": "utf8_lf",
            "scope": "bounded_weather_science_profiles",
            "environment": {"python": platform.python_version(), "implementation": platform.python_implementation(),
                            "system": platform.system(), "machine": platform.machine(), "floating_point": "binary64"}}


def make_source(request: dict) -> dict:
    from .weather_contract import validate_request
    request = validate_request(request)
    manifest = InstrumentManifest(
        instrument_id="weather-input-declaration.v1", role="declared_model_inputs",
        units={"declaration_index": "1"}, frames=(FRAME,),
        sampling={"kind": "one_configuration_declaration", "time_semantics": "synthetic_selection_envelope"},
        supported_operations=(COMPUTE, VERIFY),
        calibration_requirements={"physical_measurements": "not qualified by this workload"})
    source = {"run_schema": "run.v1", "run_id": "run-weather-" + digest(request)[7:23],
              "instrument": manifest.instrument_id,
              "metadata": {"duration_s": 1.0, "sample_count": 1, "sample_rate_hz": None,
                           "coordinate_frame": FRAME, "manifest": manifest.to_dict(), "weather_request": request,
                           "provenance": {"source": "declared model inputs; not acquired measurements",
                                          "generator": "ciw.weather_workflow.make_source", "generator_version": 1}},
              "time_s": [0.0], "channels": {"declaration_index": {"unit": "1", "values": [0.0]}}, "render": {}}
    source["evidence_id"] = evidence_id(source)
    return source


def source_request(source: dict) -> dict:
    validate_run_structure(source)
    validate_evidence_identity(source)
    request = source["metadata"]["weather_request"]
    if source != make_source(request):
        raise ValueError("Weather source must bind the exact model-input declaration")
    return deepcopy(request)


def _compute(source: dict, parameters: dict) -> dict:
    from .weather_contract import calculate
    keys(parameters, set())
    return calculate(source_request(source))


def _candidate(source: dict, parameters: dict) -> dict:
    from .weather_contract import validate_result
    keys(parameters, {"candidate"})
    candidate = parameters["candidate"]
    check_seal(candidate)
    if (candidate.get("schema") != "ciw.operation-result.v1" or candidate.get("operation_id") != COMPUTE
            or candidate.get("role") != "backend" or candidate.get("evidence_id") != source["evidence_id"]
            or candidate.get("run_id") != source["run_id"] or candidate.get("parameters") != {}):
        raise ValueError("Weather verification requires an exact source-bound calculation")
    validate_identity(candidate.get("result_id"), "result")
    validate_identity(candidate.get("execution_id"), "execution")
    validate_result(source_request(source), candidate["data"])
    return candidate


def validate_live_dependency(parameters: dict, retained: dict) -> None:
    keys(parameters, {"candidate"})
    candidate = parameters["candidate"]
    if type(candidate) is not dict or retained.get(candidate.get("result_id")) != candidate:
        raise ValueError("Weather checker requires an actually retained calculation occurrence")


def _verify(source: dict, parameters: dict) -> dict:
    from .weather_contract import check
    candidate = _candidate(source, parameters)
    return {"schema": "ciw.weather-verification-payload.v1", "verification_id": new_identity("verification"),
            "candidate_result_id": candidate["result_id"], "candidate_execution_id": candidate["execution_id"],
            "candidate_record_digest": candidate["record_digest"], "source_evidence_id": source["evidence_id"],
            "report": check(source_request(source), candidate["data"]), "authority": deepcopy(AUTHORITY)}


def operations() -> list[Operation]:
    return [Operation(COMPUTE, "backend", _compute, lambda: runtime_identity("calculator")),
            Operation(VERIFY, "verification", _verify, lambda: runtime_identity("checker"))]


def registry():
    from .operations.registry import default_registry
    result = default_registry()
    for operation in operations():
        result.register(operation)
    return result


def validate_payload(operation: str, data: dict, source: dict, parameters: dict, selection: dict) -> None:
    from .weather_contract import validate_result, validate_report
    request = source_request(source)
    if operation == COMPUTE:
        keys(parameters, set())
        validate_result(request, data)
    elif operation == VERIFY:
        candidate = _candidate(source, parameters)
        keys(data, {"schema", "verification_id", "candidate_result_id", "candidate_execution_id",
                    "candidate_record_digest", "source_evidence_id", "report", "authority"})
        validate_identity(data["verification_id"], "verification")
        if (data["schema"] != "ciw.weather-verification-payload.v1" or data["authority"] != AUTHORITY
                or data["source_evidence_id"] != source["evidence_id"]
                or data["candidate_result_id"] != candidate["result_id"]
                or data["candidate_execution_id"] != candidate["execution_id"]
                or data["candidate_record_digest"] != candidate["record_digest"]):
            raise ValueError("Weather verification identity binding differs")
        validate_report(request, candidate["data"], data["report"])
    else:
        raise ValueError("Unsupported weather operation")


def validate_result_dependencies(results: dict) -> None:
    identities = set()
    for result in results.values():
        if result.get("operation_id") != VERIFY:
            continue
        validate_live_dependency(result["parameters"], results)
        identity = result["data"]["verification_id"]
        if identity in identities:
            raise ValueError("Duplicate weather verification identity")
        identities.add(identity)


def _execute(session, operation: str, parameters: dict) -> dict:
    reply = session.handle({"protocol_version": 1, "request_id": "weather-workload", "type": "operation.execute",
                            "payload": {"operation_id": operation, "parameters": parameters}})
    if reply["type"] != "response":
        raise ValueError(reply["payload"]["message"])
    return reply["payload"]


def run(request: dict, destination: Path) -> dict:
    from .session import Session
    source = make_source(request)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    save_new(destination / "request.json", source_request(source))
    session = Session(source, destination, operations=registry())
    candidate = _execute(session, COMPUTE, {})
    if candidate["status"] == "completed":
        _execute(session, VERIFY, {"candidate": candidate["result"]})
    session.save_workspace(destination / "workspace.json")
    return inspect(destination)


def _read(destination: Path):
    from .session import Session
    destination = Path(destination)
    for name in ("workspace.json", "request.json"):
        path = destination / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("Weather bundle requires bounded regular files")
    # Freeze the one bounded read before the generic Session reader writes into scratch.
    workspace = load(destination / "workspace.json")
    with tempfile.TemporaryDirectory(prefix="weather-inspect-") as temporary:
        root = Path(temporary)
        save_new(root / "workspace.json", workspace)
        session = Session.from_workspace(root / "workspace.json", root / "reopened")
    request = source_request(session.run)
    if load(destination / "request.json") != request:
        raise ValueError("Retained weather request differs from source evidence")
    results, executions = list(session.results.values()), list(session.executions.values())
    candidates = [r for r in results if r["operation_id"] == COMPUTE]
    verifications = [r for r in results if r["operation_id"] == VERIFY]
    if any(e["operation_id"] not in {COMPUTE, VERIFY} for e in executions):
        raise ValueError("Weather bundle contains unrelated executions")
    if len(executions) == 1 and executions[0]["operation_id"] == COMPUTE and executions[0]["status"] == "refused":
        if results:
            raise ValueError("Refused weather calculation cannot retain a result")
        return session, None, None
    if (len(executions) == 2 and len(candidates) == 1 and not verifications and len(results) == 1
            and sum(e["operation_id"] == VERIFY and e["status"] == "refused" for e in executions) == 1):
        return session, candidates[0], None
    if len(executions) != 2 or len(results) != 2 or len(candidates) != 1 or len(verifications) != 1:
        raise ValueError("Require one weather calculation and one verification occurrence")
    if verifications[0]["parameters"]["candidate"] != candidates[0]:
        raise ValueError("Weather verifier binds a different calculation")
    return session, candidates[0], verifications[0]


def _summary(session, candidate, verification) -> dict:
    report = verification["data"]["report"] if verification else None
    result = {"schema": "ciw.weather-inspection.v1", "profile": source_request(session.run)["profile"],
              "context": source_request(session.run)["context"],
              "status": "LOCAL" if report and report["status"] == "PASS" else "REFUSE",
              "evidence_id": session.run["evidence_id"], "fresh_execution": False,
              "fresh_numerical_verification": False, "authority": deepcopy(AUTHORITY)}
    if candidate:
        result.update({"operation_id": COMPUTE, "execution_id": candidate["execution_id"],
                       "result_id": candidate["result_id"], "result_digest": candidate["data"]["record_digest"],
                       "scope": candidate["data"]["scope"], "values": deepcopy(candidate["data"]["values"]),
                       "units": deepcopy(candidate["data"]["units"]),
                       "limitations": deepcopy(candidate["data"]["limitations"])})
    if verification:
        result.update({"verification_operation_id": VERIFY,
                       "verification_execution_id": verification["execution_id"],
                       "verification_id": verification["data"]["verification_id"], "checks": deepcopy(report["checks"])})
    else:
        result["refusals"] = [deepcopy(e.get("refusal")) for e in session.executions.values() if e["status"] == "refused"]
    return result


def inspect(destination: Path) -> dict:
    return _summary(*_read(destination))


def verify_retained(destination: Path) -> dict:
    from .weather_contract import check
    session, candidate, verification = _read(destination)
    result = _summary(session, candidate, verification)
    if verification is None:
        return result
    report = check(source_request(session.run), candidate["data"])
    if report != verification["data"]["report"]:
        raise ValueError("Fresh weather numerical checks differ from retained report")
    result.update(fresh_numerical_verification=True, recomputed_report_digest=report["record_digest"],
                  recomputed_with_runtime=runtime_identity("checker"))
    return result


def replay(destination: Path, output: Path) -> dict:
    session, candidate, verification = _read(destination)
    if not candidate or not verification or verification["data"]["report"]["status"] != "PASS":
        raise ValueError("Replay requires a retained numerically passing calculation")
    if candidate["runtime"] != runtime_identity("calculator") or verification["runtime"] != runtime_identity("checker"):
        raise ValueError("Weather replay requires the recorded source and Python runtime identity")
    result = run(source_request(session.run), output)
    matched = result.get("result_digest") == candidate["data"]["record_digest"] and result["status"] == "LOCAL"
    receipt = {"schema": "ciw.weather-replay.v1", "status": "PASS" if matched else "FAIL",
               "source_evidence_id": session.run["evidence_id"], "source_execution_id": candidate["execution_id"],
               "replay_execution_id": result.get("execution_id"), "result_digest_matches": matched,
               "claim": "same_runtime_deterministic_result_reproduction", "authority": deepcopy(AUTHORITY)}
    save_new(Path(output) / "replay.json", receipt)
    return receipt


def export_result(destination: Path, output: Path) -> dict:
    result = verify_retained(destination)
    if result["status"] != "LOCAL":
        raise ValueError("Export requires passing fresh weather numerical checks")
    save_new(output, result)
    return {"status": "exported", "file": str(output), "result_id": result["result_id"],
            "verification_id": result["verification_id"], "authority": deepcopy(AUTHORITY)}
