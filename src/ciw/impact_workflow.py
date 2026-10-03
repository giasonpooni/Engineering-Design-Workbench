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
CRUSH_SIMULATE = "impact.crush-contact.v1"
CRUSH_VERIFY = "impact.crush-contact-verify.v1"
PLATE_SIMULATE = "impact.plate-contact.v1"
PLATE_VERIFY = "impact.plate-contact-verify.v1"
FRAME = "impact.normal.inward_positive.v1"
AUTHORITY = {"physical_validation": "not_established", "scale_preservation": "not_established",
             "state_admission": "not_performed", "hardware_actuation": "not_performed"}


def _crush(request: dict) -> bool:
    return isinstance(request, dict) and request.get("schema") == "ciw.impact-crush-request.v1"


def _plate(request: dict) -> bool:
    return isinstance(request, dict) and request.get("schema") == "ciw.impact-plate-request.v1"


def _modules(request: dict):
    # Fixed installed profiles only. Saved schema IDs never name import paths.
    if _plate(request):
        from . import impact_plate_contract as contract, impact_plate_solver as solver
        from . import impact_plate_verification as verification, impact_plate_preservation as preservation
    elif _crush(request):
        from . import impact_crush_contract as contract, impact_crush_solver as solver
        from . import impact_crush_verification as verification, impact_crush_preservation as preservation
    else:
        from . import impact_contract as contract, impact_solver as solver
        from . import impact_verification as verification, impact_preservation as preservation
    return contract, solver, verification, preservation


def _operation_ids(request: dict) -> tuple[str, str]:
    if _plate(request):
        return PLATE_SIMULATE, PLATE_VERIFY
    return (CRUSH_SIMULATE, CRUSH_VERIFY) if _crush(request) else (SIMULATE, VERIFY)


def runtime_identity(kind: str, *, crush: bool = False, plate: bool = False) -> dict:
    if plate:
        from . import impact_plate_contract as contract, impact_plate_reference as reference
        from . import impact_plate_solver as solver, impact_plate_verification as verification
    elif crush:
        from . import impact_crush_contract as contract, impact_crush_reference as reference
        from . import impact_crush_solver as solver, impact_crush_verification as verification
    else:
        from . import impact_contract as contract, impact_reference as reference
        from . import impact_solver as solver, impact_verification as verification
    modules = [contract, solver] if kind == "solver" else [contract, reference, verification]
    modules.append(__import__(__name__, fromlist=["*"]))
    raw = b"\0".join(Path(m.__file__).name.encode() + b"\0" +
                     Path(m.__file__).read_text(encoding="utf-8").replace("\r\n", "\n").encode()
                     for m in modules)
    identity = {"provider": "ciw.impact." + ("plate-" if plate else "crush-" if crush else "") + kind,
            "version": "1", "code_sha256": sha256(raw).hexdigest(), "source_normalization": "utf8_lf",
            "scope": "synthetic_modal_plate_contact_only" if plate else
                     "synthetic_elastic_plastic_crush_only" if crush else "synthetic_elastic_contact_only"}
    if plate:
        import platform
        import numpy
        identity["environment"] = {"python": platform.python_version(), "numpy": numpy.__version__,
                                   "floating_point": "binary64"}
    return identity


def make_source(request: dict) -> dict:
    contract, _, _, _ = _modules(request)
    request = contract.validate_request(request)
    model = request["model"]
    duration = math.pi * math.sqrt(model["mass_kg"] / model["stiffness_n_per_m"]) * request["integration"]["duration_factor"]
    if _crush(request):
        from .impact_crush_reference import reference
        duration = reference(request)["contact_duration_s"] * request["integration"]["duration_factor"]
    simulate_id, verify_id = _operation_ids(request)
    units = {"compression": "m", "velocity": "m/s", "force": "N"}
    if _crush(request):
        units.update(plastic_compression="m", plastic_work="J")
    if _plate(request):
        units.update(striker_displacement="m", plate_contact_displacement="m", plate_contact_velocity="m/s")
    manifest = InstrumentManifest(
        instrument_id="impact-plate-initial-state.v1" if _plate(request) else
                      "impact-crush-initial-state.v1" if _crush(request) else "impact-initial-state.v1",
        role="synthetic_initial_conditions",
        units=units, frames=(FRAME,),
        sampling={"kind": "one_initial_state_at_first_contact"},
        supported_operations=(simulate_id, verify_id),
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
    if _crush(request):
        run["channels"].update(plastic_compression={"unit": "m", "values": [0.0]},
                               plastic_work={"unit": "J", "values": [0.0]})
    if _plate(request):
        run["channels"].update(striker_displacement={"unit": "m", "values": [0.0]},
                               plate_contact_displacement={"unit": "m", "values": [0.0]},
                               plate_contact_velocity={"unit": "m/s", "values": [0.0]})
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
    keys(parameters, set())
    request = source_request(run)
    return _modules(request)[1].simulate(request)


def _candidate(run: dict, parameters: dict) -> dict:
    request = source_request(run)
    simulate_id, _ = _operation_ids(request)
    keys(parameters, {"candidate"})
    candidate = parameters["candidate"]
    check_seal(candidate)
    if (candidate.get("schema") != "ciw.operation-result.v1" or candidate.get("operation_id") != simulate_id
            or candidate.get("role") != "backend" or candidate.get("evidence_id") != run["evidence_id"]
            or candidate.get("run_id") != run["run_id"] or candidate.get("parameters") != {}):
        raise ValueError("Verification candidate must bind the exact impact source and simulation operation")
    validate_identity(candidate.get("result_id"), "result")
    validate_identity(candidate.get("execution_id"), "execution")
    _modules(request)[0].validate_result(request, candidate["data"])
    return candidate


def _verify(run: dict, parameters: dict) -> dict:
    candidate = _candidate(run, parameters)
    request = source_request(run)
    return {"schema": "ciw.impact-verification-payload.v1", "verification_id": new_identity("verification"),
            "candidate_result_id": candidate["result_id"], "candidate_execution_id": candidate["execution_id"],
            "candidate_record_digest": candidate["record_digest"], "source_evidence_id": run["evidence_id"],
            "report": _modules(request)[2].verify(request, candidate["data"]), "authority": deepcopy(AUTHORITY)}


def operations() -> list[Operation]:
    def bind(operation_id, callback):
        def execute(run, parameters):
            if operation_id not in _operation_ids(source_request(run)):
                raise ValueError("Impact operation cannot execute a different physical profile")
            return callback(run, parameters)
        return execute
    return [Operation(SIMULATE, "backend", bind(SIMULATE, _simulate), lambda: runtime_identity("solver")),
            Operation(VERIFY, "verification", bind(VERIFY, _verify), lambda: runtime_identity("verifier")),
            Operation(CRUSH_SIMULATE, "backend", bind(CRUSH_SIMULATE, _simulate), lambda: runtime_identity("solver", crush=True)),
            Operation(CRUSH_VERIFY, "verification", bind(CRUSH_VERIFY, _verify), lambda: runtime_identity("verifier", crush=True)),
            Operation(PLATE_SIMULATE, "backend", bind(PLATE_SIMULATE, _simulate), lambda: runtime_identity("solver", plate=True)),
            Operation(PLATE_VERIFY, "verification", bind(PLATE_VERIFY, _verify), lambda: runtime_identity("verifier", plate=True))]


def registry():
    """Explicit trusted binding; saved data never activates these operations."""
    from .operations.registry import default_registry
    result = default_registry()
    for operation in operations():
        result.register(operation)
    return result


def validate_payload(operation: str, data: dict, run: dict, parameters: dict, selection: dict) -> None:
    """Read stored contracts without rerunning either numerical implementation."""
    request = source_request(run)
    simulate_id, verify_id = _operation_ids(request)
    contract, _, verifier, _ = _modules(request)
    if operation == simulate_id:
        keys(parameters, set())
        contract.validate_result(request, data)
    elif operation == verify_id:
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
        verifier.validate_report(request, candidate["data"], data["report"])
    else:
        raise ValueError("Unsupported impact operation")


def validate_result_dependencies(results: dict) -> None:
    """Verification snapshots must match an actually retained solver occurrence."""
    verification_ids = set()
    for result in results.values():
        if result.get("operation_id") not in {VERIFY, CRUSH_VERIFY, PLATE_VERIFY}:
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
    simulate_id, verify_id = _operation_ids(source_request(session.run))
    candidate = _execute(session, simulate_id, {})
    verification = None
    if candidate["status"] == "completed":
        verification = _execute(session, verify_id, {"candidate": candidate["result"]})
    session.save_workspace(destination / "workspace.json")
    if candidate["status"] != "completed" or verification is None or verification["status"] != "completed":
        return inspect(destination)
    save_new(destination / "verification.json", verification["result"]["data"])
    build = _modules(source_request(session.run))[3].build
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
    simulate_id, verify_id = _operation_ids(source_request(session.run))
    candidates = [r for r in session.results.values() if r["operation_id"] == simulate_id]
    verifications = [r for r in session.results.values() if r["operation_id"] == verify_id]
    executions = list(session.executions.values())
    if any(e["operation_id"] not in {simulate_id, verify_id} for e in executions):
        raise ValueError("Impact bundle contains an unrelated execution")
    if len(executions) == 1 and executions[0]["operation_id"] == simulate_id and executions[0]["status"] == "refused":
        if session.results or (destination / "verification.json").exists():
            raise ValueError("Refused solver bundle cannot contain results")
        return session, None, None
    if (len(executions) == 2 and len(candidates) == 1 and not verifications
            and sum(e["status"] == "refused" and e["operation_id"] == verify_id for e in executions) == 1):
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
    validate = _modules(source_request(session.run))[3].validate
    preservation = load(destination / "preservation.json")
    validate(preservation, source_request(session.run), candidate["data"], verification["data"]["report"])
    # Ephemeral inspection state only. Keep the exact validated receipt with
    # this snapshot; subsequent inspection/export never reopens another epoch.
    session._impact_preservation = deepcopy(preservation)
    return session, candidate, verification


def _inspection_from_read(session, candidate: dict | None, verification: dict | None) -> dict:
    if verification is None:
        attempts = [{name: deepcopy(value) for name, value in entry.items() if name != "parameters"}
                    for entry in session.executions.values()]
        return {"schema": "ciw.impact-inspection.v1", "status": "REFUSE",
                "evidence_id": session.run["evidence_id"], "executions": attempts,
                "fresh_execution": False, "fresh_numerical_verification": False, "authority": deepcopy(AUTHORITY)}
    report = verification["data"]["report"]
    preservation = session._impact_preservation
    return {"schema": "ciw.impact-inspection.v1", "status": report["qualification"]["action"],
            "qualification": report["qualification"], "evidence_id": session.run["evidence_id"],
            "operation_id": candidate["operation_id"], "execution_id": candidate["execution_id"], "result_id": candidate["result_id"],
            "verification_operation_id": verification["operation_id"], "verification_execution_id": verification["execution_id"],
            "verification_id": verification["data"]["verification_id"], "checks": report["checks"],
            "metrics": report["metrics"], "fresh_execution": False, "fresh_numerical_verification": False,
            "preservation": {"contract_ref": preservation["contract"]["record_digest"],
                             "verification_ref": preservation["verification"]["record_digest"],
                             "verification_status": preservation["verification"]["status"],
                             "admission_eligibility": preservation["admission_gate"]["decision"],
                             "state_admission_performed": False},
            "authority": deepcopy(AUTHORITY)}


def inspect(destination: Path) -> dict:
    return _inspection_from_read(*_read(destination))


def _verify_read(session, candidate: dict | None, verification: dict | None) -> dict:
    if verification is None:
        return _inspection_from_read(session, candidate, verification)
    request = source_request(session.run)
    fresh = _modules(request)[2].verify(request, candidate["data"])
    if fresh != verification["data"]["report"]:
        raise ValueError("Independent recomputation differs from retained verification report")
    result = _inspection_from_read(session, candidate, verification)
    result["fresh_numerical_verification"] = True
    result["recomputed_report_digest"] = fresh["record_digest"]
    result["recomputed_with_runtime"] = runtime_identity("verifier", crush=_crush(request), plate=_plate(request))
    return result


def verify_retained(destination: Path) -> dict:
    return _verify_read(*_read(destination))


def export_csv(destination: Path, output: Path) -> dict:
    session, candidate, verification = _read(destination)
    checked = _verify_read(session, candidate, verification)
    if checked["status"] != "LOCAL":
        raise ValueError("Only a numerically qualified LOCAL trace can be exported")
    trace = candidate["data"]["primary"]
    names = ["time_s", "compression_m", "velocity_m_per_s", "force_n"]
    if candidate["operation_id"] == CRUSH_SIMULATE:
        names.extend(["plastic_compression_m", "plastic_work_j"])
    if candidate["operation_id"] == PLATE_SIMULATE:
        names = ["time_s", "striker_displacement_m", "compression_m", "velocity_m_per_s", "force_n",
                 "plate_contact_displacement_m", "plate_contact_velocity_m_per_s"]
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(names)
        writer.writerows(zip(*(trace[name] for name in names)))
    return {"status": "exported", "file": str(output), "source_result_id": candidate["result_id"],
            "source_execution_id": candidate["execution_id"], "authority": deepcopy(AUTHORITY)}


def export_plate_field(destination: Path, output: Path, *, time_index: int, grid_size: int = 17) -> dict:
    """Reconstruct one retained finite-basis displacement field after fresh audit."""
    if type(time_index) is not int or time_index < 0:
        raise ValueError("time_index must be a nonnegative integer")
    if type(grid_size) is not int or not 3 <= grid_size <= 33 or grid_size % 2 != 1:
        raise ValueError("grid_size must be an odd integer inside 3..33")
    session, candidate, verification = _read(destination)
    request = source_request(session.run)
    if not _plate(request) or candidate is None:
        raise ValueError("A retained plate result is required for spatial field export")
    trace = candidate["data"]["primary"]
    if time_index >= len(trace["time_s"]):
        raise ValueError("time_index lies outside the retained primary trace")
    checked = _verify_read(session, candidate, verification)
    if checked["status"] != "LOCAL":
        raise ValueError("Only a numerically qualified LOCAL plate field can be exported")
    model = request["model"]
    x = [model["length_x_m"] * i / (grid_size - 1) for i in range(grid_size)]
    y = [model["length_y_m"] * i / (grid_size - 1) for i in range(grid_size)]
    modes = trace["modes"]
    amplitudes = [values[time_index] for values in trace["modal_displacement_m"]]
    field = [[0.0 if i in {0, grid_size - 1} or j in {0, grid_size - 1} else
              sum(amplitude * math.sin(m * math.pi * xi / model["length_x_m"])
                  * math.sin(n * math.pi * yj / model["length_y_m"])
                  for (m, n), amplitude in zip(modes, amplitudes))
              for i, xi in enumerate(x)] for j, yj in enumerate(y)]
    payload = seal({"schema": "ciw.impact-plate-field.v1", "request_digest": digest(request),
                    "source_evidence_id": session.run["evidence_id"], "source_result_id": candidate["result_id"],
                    "source_execution_id": candidate["execution_id"], "source_record_digest": candidate["record_digest"],
                    "verification_id": checked["verification_id"],
                    "recomputed_report_digest": checked["recomputed_report_digest"],
                    "time_index": time_index, "time_s": trace["time_s"][time_index],
                    "units": {"x_m": "m", "y_m": "m", "deflection_m": "m", "time_s": "s"},
                    "geometry": {"length_x_m": model["length_x_m"], "length_y_m": model["length_y_m"],
                                 "thickness_m": model["thickness_m"], "support": model["support"]},
                    "modes": deepcopy(modes), "modal_displacement_m": amplitudes,
                    "x_m": x, "y_m": y, "deflection_m": field,
                    "interpretation": "finite-basis displacement at one retained primary-grid time; no interpolation, stress, damage or continuum qualification",
                    "authority": deepcopy(AUTHORITY)})
    save_new(output, payload)
    return {"status": "exported", "file": str(output), "field_digest": payload["record_digest"],
            "source_result_id": candidate["result_id"], "source_execution_id": candidate["execution_id"],
            "time_index": time_index, "time_s": trace["time_s"][time_index],
            "authority": deepcopy(AUTHORITY)}
