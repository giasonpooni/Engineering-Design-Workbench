"""Polymer workloads on existing NET Session evidence and execution identities."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import platform
import tempfile
import uuid

from .adapters.protocol import InstrumentManifest
from .control_contracts import detached, keys, load, save_new
from .core.identities import evidence_id, new_identity, validate_evidence_identity, validate_identity
from .core.records import validate_run_structure
from .operations.registry import Operation
from .operations.runner import check_seal, digest
from .polymer_contract import AUTHORITY, validate_request

ASSESS = "polymer.assess-cycle.v1"
COPILOT = "polymer.copilot-context.v1"
SIMULATE = "polymer.control-simulate.v1"
VERIFY = "polymer.verify-cycle.v1"
OPERATIONS = {ASSESS, COPILOT, SIMULATE, VERIFY}
MAX_WORKSPACE_BYTES = 24 * 1024 * 1024


def runtime_identity(kind: str) -> dict:
    from . import polymer_contract, polymer_metrology, polymer_models, polymer_copilot, polymer_verification, polymer_ingress
    modules = [polymer_contract, polymer_metrology, polymer_models, polymer_copilot, polymer_verification, polymer_ingress,
               __import__(__name__, fromlist=["*"])]
    raw = b"\0".join(Path(m.__file__).name.encode() + b"\0" +
                     Path(m.__file__).read_text(encoding="utf-8").replace("\r\n", "\n").encode()
                     for m in modules)
    return {"provider": "ciw.polymer." + kind, "version": "1", "code_sha256": sha256(raw).hexdigest(),
            "source_normalization": "utf8_lf", "scope": "retained_cycle_reference_models_and_simulated_control_only",
            "environment": {"python": platform.python_version(), "floating_point": "binary64"}}


def make_source(request: dict, *, ingress: dict | None = None) -> dict:
    request = validate_request(request)
    if ingress is not None:
        from . import polymer_ingress
        ingress = polymer_ingress.validate(ingress)
        if digest(polymer_ingress.derive(ingress)) != digest(request):
            raise ValueError("Polymer request differs from retained native ingress derivation")
    # A transport selection contains one declaration. Original nonuniform sensor
    # histories and their acquisition timestamps remain exact in metadata.
    manifest = InstrumentManifest(instrument_id="polymer-cycle-evidence.v1", role="retained_cycle_features",
        units={"cycle_declaration": "1"}, frames=(request["frame"],),
        sampling={"kind": "one_cycle_evidence_declaration", "time_semantics": "synthetic_selection_envelope"},
        supported_operations=(ASSESS, COPILOT, SIMULATE, VERIFY),
        calibration_requirements={"quantitative_features": "explicit calibration and clock references; traceability not established by ingress"})
    source = {"run_schema": "run.v1", "run_id": "run-polymer-" + digest(request)[7:23],
              "instrument": manifest.instrument_id,
              "metadata": {"duration_s": 1.0, "sample_count": 1, "sample_rate_hz": None,
                           "coordinate_frame": request["frame"], "manifest": manifest.to_dict(),
                           "polymer_request": request,
                           "provenance": {"source": request["source_kind"],
                                          "generator": "ciw.polymer_workflow.make_source", "generator_version": 1}},
              "time_s": [0.0], "channels": {"cycle_declaration": {"unit": "1", "values": [1.0]}}, "render": {}}
    if ingress is not None:
        source["metadata"]["polymer_ingress"] = ingress
    source["evidence_id"] = evidence_id(source)
    return source


def source_request(source: dict) -> dict:
    validate_run_structure(source)
    validate_evidence_identity(source)
    request = validate_request(source["metadata"]["polymer_request"])
    if source != make_source(request, ingress=source["metadata"].get("polymer_ingress")):
        raise ValueError("Polymer source differs from its exact retained cycle declaration")
    return request


def _assess(source: dict, parameters: dict) -> dict:
    from .polymer_metrology import assess_metrology
    from .polymer_models import engineering_estimate, control_proposal
    keys(parameters, set())
    request = source_request(source)
    metrology = assess_metrology(request)
    return {"schema": "ciw.polymer-assessment.v1", "source_ref": digest(request),
            "identity": deepcopy(request["identity"]), "process": request["process"],
            "source_kind": request["source_kind"], "metrology": metrology,
            "engineering": engineering_estimate(request), "control": control_proposal(request, metrology),
            "authority": deepcopy(AUTHORITY)}


def _candidate(source: dict, parameters: dict) -> dict:
    keys(parameters, {"assessment"})
    candidate = parameters["assessment"]
    check_seal(candidate)
    if (candidate.get("schema") != "ciw.operation-result.v1" or candidate.get("operation_id") != ASSESS
            or candidate.get("role") != "backend" or candidate.get("evidence_id") != source["evidence_id"]
            or candidate.get("run_id") != source["run_id"] or candidate.get("parameters") != {}):
        raise ValueError("Require the exact source-bound polymer assessment occurrence")
    validate_identity(candidate.get("execution_id"), "execution")
    validate_identity(candidate.get("result_id"), "result")
    _validate_assessment(source_request(source), candidate["data"])
    return deepcopy(candidate)


def _copilot(source: dict, parameters: dict) -> dict:
    from .polymer_copilot import build_context
    candidate = _candidate(source, parameters)
    return {"schema": "ciw.polymer-copilot-payload.v1", "assessment_result_id": candidate["result_id"],
            "assessment_execution_id": candidate["execution_id"], "assessment_record_digest": candidate["record_digest"],
            "context": build_context(source_request(source), candidate["data"]), "authority": deepcopy(AUTHORITY)}


def _simulate(source: dict, parameters: dict) -> dict:
    from .polymer_models import simulate_control
    keys(parameters, set())
    request = source_request(source)
    return {"schema": "ciw.polymer-simulation-payload.v1", "source_ref": digest(request),
            "simulation": simulate_control(request["control"]), "authority": deepcopy(AUTHORITY)}


def _verify(source: dict, parameters: dict) -> dict:
    from .polymer_verification import verify
    candidate = _candidate(source, parameters)
    return {"schema": "ciw.polymer-verification-payload.v1", "verification_id": new_identity("verification"),
            "assessment_result_id": candidate["result_id"], "assessment_execution_id": candidate["execution_id"],
            "assessment_record_digest": candidate["record_digest"], "source_ref": digest(source_request(source)),
            "report": verify(source_request(source), candidate["data"]), "authority": deepcopy(AUTHORITY)}


def operations() -> list[Operation]:
    return [Operation(ASSESS, "backend", _assess, lambda: runtime_identity("assessment")),
            Operation(COPILOT, "backend", _copilot, lambda: runtime_identity("copilot_context")),
            Operation(SIMULATE, "backend", _simulate, lambda: runtime_identity("control_simulation")),
            Operation(VERIFY, "verification", _verify, lambda: runtime_identity("verification"))]


def registry():
    from .operations.registry import default_registry
    value = default_registry()
    for operation in operations():
        value.register(operation)
    return value


def capability_registry(*, bind: bool = False):
    """Explicit operator-owned advertisement for the existing AgentHost."""
    from .control_plane import CapabilityRegistry, Port
    value = CapabilityRegistry()
    names = {ASSESS: ["polymer.cycle.assess"], COPILOT: ["polymer.copilot.context"],
             SIMULATE: ["polymer.control.simulate"], VERIFY: ["polymer.cycle.verify"]}
    for operation in operations():
        manifest = InstrumentManifest(instrument_id=operation.operation_id, role=operation.role, units={},
            frames=(), sampling={"kind": "retained_cycle_evidence"}, supported_operations=(operation.operation_id,),
            calibration_requirements={"authority": "no machine actuation"})
        value.advertise(manifest, runtime=operation.runtime_identity(),
            capabilities={operation.operation_id: names[operation.operation_id]},
            inputs={operation.operation_id: {"assessment": Port("ciw.operation-result.v1").to_dict()}
                    if operation.operation_id in {COPILOT, VERIFY} else {}})
        if bind:
            value.bind(operation)
    return value


def _validate_assessment(request: dict, data: dict) -> None:
    """Read retained results without running engineering, control or inference."""
    keys(data, {"schema", "source_ref", "identity", "process", "source_kind", "metrology", "engineering", "control", "authority"})
    detached(data)
    if (data["schema"] != "ciw.polymer-assessment.v1" or data["source_ref"] != digest(request)
            or data["identity"] != request["identity"] or data["process"] != request["process"]
            or data["source_kind"] != request["source_kind"] or data["authority"] != AUTHORITY):
        raise ValueError("Assessment evidence or authority binding differs")
    from .polymer_verification import validate_assessment
    validate_assessment(request, data)


def validate_payload(operation: str, data: dict, source: dict, parameters: dict, selection: dict) -> None:
    request = source_request(source)
    detached(data)
    if operation == ASSESS:
        keys(parameters, set())
        _validate_assessment(request, data)
        return
    if operation == SIMULATE:
        keys(parameters, set())
        keys(data, {"schema", "source_ref", "simulation", "authority"})
        if data["schema"] != "ciw.polymer-simulation-payload.v1" or data["source_ref"] != digest(request) or data["authority"] != AUTHORITY:
            raise ValueError("Simulation source or authority binding differs")
        from .polymer_verification import validate_simulation
        validate_simulation(request["control"], data["simulation"])
        return
    candidate = _candidate(source, parameters)
    shared = {"schema", "assessment_result_id", "assessment_execution_id", "assessment_record_digest", "authority"}
    keys(data, shared | ({"context"} if operation == COPILOT else {"verification_id", "source_ref", "report"}))
    if (data["authority"] != AUTHORITY or data["assessment_result_id"] != candidate["result_id"]
            or data["assessment_execution_id"] != candidate["execution_id"]
            or data["assessment_record_digest"] != candidate["record_digest"]):
        raise ValueError("Dependent polymer result differs from its retained assessment")
    if operation == COPILOT:
        if data["schema"] != "ciw.polymer-copilot-payload.v1":
            raise ValueError("Wrong copilot payload schema")
        from .polymer_copilot import validate_context
        validate_context(request, candidate["data"], data["context"])
    elif operation == VERIFY:
        if data["schema"] != "ciw.polymer-verification-payload.v1" or data["source_ref"] != digest(request):
            raise ValueError("Wrong verification source or schema")
        validate_identity(data["verification_id"], "verification")
        from .polymer_verification import validate_report
        validate_report(data["report"])
        if (data["report"]["request_ref"] != digest(request)
                or data["report"]["assessment_ref"] != digest(candidate["data"])):
            raise ValueError("Numerical verification report differs from its exact request and assessment")
    else:
        raise ValueError("Unsupported polymer operation")


def validate_result_dependencies(results: dict) -> None:
    verification_ids = set()
    for result in results.values():
        if result.get("operation_id") not in {COPILOT, VERIFY}:
            continue
        candidate = result["parameters"]["assessment"]
        if results.get(candidate["result_id"]) != candidate:
            raise ValueError("Polymer dependency is not the actually retained assessment occurrence")
        if result["operation_id"] == VERIFY:
            identity = result["data"]["verification_id"]
            if identity in verification_ids:
                raise ValueError("Duplicate polymer verification identity")
            verification_ids.add(identity)


def validate_live_dependency(parameters: dict, retained_results: dict) -> None:
    """Refuse invented dependency occurrences before provider dispatch/publication."""
    keys(parameters, {"assessment"})
    candidate = parameters["assessment"]
    if (type(candidate) is not dict or type(candidate.get("result_id")) is not str
            or retained_results.get(candidate["result_id"]) != candidate):
        raise ValueError("Polymer dependency is not the actually retained assessment occurrence")


def _execute(session, operation, parameters):
    reply = session.handle({"protocol_version": 1, "request_id": uuid.uuid4().hex, "type": "operation.execute",
                            "payload": {"operation_id": operation, "parameters": parameters}})
    if reply["type"] != "response":
        raise ValueError(reply["payload"]["message"])
    return reply["payload"]


def run(request: dict, destination: Path, *, ingress: dict | None = None) -> dict:
    from .session import Session
    source = make_source(request, ingress=ingress)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    save_new(destination / "request.json", source_request(source))
    if ingress is not None:
        from .polymer_ingress import save_file
        save_file(destination / "ingress.json", source["metadata"]["polymer_ingress"])
    session = Session(source, destination, operations=registry())
    assessment = _execute(session, ASSESS, {})
    if assessment["status"] == "completed":
        candidate = {"assessment": assessment["result"]}
        _execute(session, COPILOT, candidate)
        _execute(session, SIMULATE, {})
        _execute(session, VERIFY, candidate)
    session.save_workspace(destination / "workspace.json")
    return inspect(destination)


def _read(destination: Path):
    from .session import Session
    destination = Path(destination)
    for name in ("request.json", "workspace.json"):
        path = destination / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_WORKSPACE_BYTES:
            raise ValueError("Require bounded regular polymer bundle files")
    with tempfile.TemporaryDirectory(prefix="polymer-inspect-") as directory:
        session = Session.from_workspace(destination / "workspace.json", Path(directory))
    request = source_request(session.run)
    if digest(validate_request(load(destination / "request.json"))) != digest(request):
        raise ValueError("Retained request differs from source evidence")
    ingress = session.run["metadata"].get("polymer_ingress")
    ingress_path = destination / "ingress.json"
    if ingress is not None:
        from . import polymer_ingress
        if (ingress_path.is_symlink() or not ingress_path.is_file()
                or ingress_path.stat().st_size > polymer_ingress.MAX_BYTES
                or digest(polymer_ingress.load_file(ingress_path)) != digest(ingress)):
            raise ValueError("Retained native ingress sidecar differs from source evidence")
    elif ingress_path.exists() or ingress_path.is_symlink():
        raise ValueError("Unexpected native ingress sidecar without source binding")
    executions = list(session.executions.values())
    if not executions or any(e["operation_id"] not in OPERATIONS for e in executions):
        raise ValueError("Polymer bundle contains missing or unrelated executions")
    operations_seen = [e["operation_id"] for e in executions]
    if len(set(operations_seen)) != len(operations_seen) or operations_seen[0] != ASSESS:
        raise ValueError("Require at most one attempt per polymer operation, assessment first")
    if executions[0]["status"] == "refused":
        if len(executions) != 1 or session.results:
            raise ValueError("Refused assessment cannot have dependent results")
    elif set(operations_seen) != OPERATIONS:
        raise ValueError("Completed assessment requires the declared copilot, simulation and verification attempts")
    return session, request


def inspect(destination: Path) -> dict:
    session, request = _read(destination)
    results = {r["operation_id"]: r for r in session.results.values()}
    completed = all(e["status"] == "completed" for e in session.executions.values())
    verified = results.get(VERIFY, {}).get("data", {}).get("report", {}).get("status") == "PASS"
    return {"schema": "ciw.polymer-inspection.v1", "status": "PASS" if completed and verified else "REFUSE",
            "evidence_id": session.run["evidence_id"], "identity": deepcopy(request["identity"]),
            "source_kind": request["source_kind"], "assessment": deepcopy(results.get(ASSESS, {}).get("data")),
            "ingress_ref": digest(session.run["metadata"]["polymer_ingress"]) if "polymer_ingress" in session.run["metadata"] else None,
            "copilot": deepcopy(results.get(COPILOT, {}).get("data")),
            "simulation": deepcopy(results.get(SIMULATE, {}).get("data")),
            "verification": deepcopy(results.get(VERIFY, {}).get("data")),
            "occurrences": [{"operation_id": e["operation_id"], "execution_id": e["execution_id"],
                             "result_id": e["result_id"], "status": e["status"],
                             **({"refusal": e["refusal"]} if "refusal" in e else {})} for e in session.executions.values()],
            "fresh_execution": False, "fresh_numerical_verification": False, "authority": deepcopy(AUTHORITY)}


def verify_retained(destination: Path) -> dict:
    from .polymer_verification import verify
    session, request = _read(destination)
    assessment = next((r for r in session.results.values() if r["operation_id"] == ASSESS), None)
    if assessment is None:
        return inspect(destination)
    report = verify(request, assessment["data"])
    # A fresh audit is a separate verification occurrence; it does not edit or
    # rewrite the saved operation result's verification status.
    return {"schema": "ciw.polymer-fresh-verification.v1", "verification_id": new_identity("verification"),
            "assessment_result_id": assessment["result_id"], "assessment_execution_id": assessment["execution_id"],
            "assessment_record_digest": assessment["record_digest"], "source_evidence_id": session.run["evidence_id"],
            "status": report["status"], "report": report, "fresh_numerical_verification": True,
            "authority": deepcopy(AUTHORITY)}


def replay(destination: Path, output: Path) -> dict:
    session, request = _read(destination)
    result = run(request, output, ingress=session.run["metadata"].get("polymer_ingress"))
    result["replay_source_evidence_id"] = session.run["evidence_id"]
    return result
