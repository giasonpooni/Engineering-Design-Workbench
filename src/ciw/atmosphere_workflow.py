"""Reference atmosphere compilation on the existing retained Session substrate.

The source is one declared configuration sample. The compiler's altitude profile
is a spatial model result, never a recording of acquired atmospheric observations.
"""
from __future__ import annotations

from copy import deepcopy
import csv
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

COMPILE = "atmosphere.compile.v1"
VERIFY = "atmosphere.verify.v1"
MOIST_COMPILE = "atmosphere.moist-compile.v1"
MOIST_VERIFY = "atmosphere.moist-verify.v1"
FRAME = "atmosphere.local_enu.v1"
MAX_BUNDLE_FILE_BYTES = 8 * 1024 * 1024
AUTHORITY = {"physical_validation": "not_established", "weather_prediction": "not_established",
             "scale_preservation": "not_established", "state_admission": "not_performed",
             "hardware_actuation": "not_performed"}


def _moist(request: dict) -> bool:
    """Select only explicitly trusted profiles; saved import paths activate nothing."""
    if type(request) is not dict:
        raise ValueError("Atmosphere request must be an object")
    schema = request.get("schema")
    if schema == "ciw.atmosphere-request.v1":
        return False
    if schema == "ciw.atmosphere-moist-request.v1":
        return True
    raise ValueError("Unsupported atmosphere request schema")


def _modules(request: dict):
    if _moist(request):
        from . import atmosphere_moist_contract as contract
        from . import atmosphere_moist_compiler as compiler
        from . import atmosphere_moist_verification as verification
        from . import atmosphere_moist_preservation as preservation
        from . import atmosphere_moist_handoff as handoff
    else:
        from . import atmosphere_contract as contract
        from . import atmosphere_compiler as compiler
        from . import atmosphere_verification as verification
        from . import atmosphere_preservation as preservation
        from . import atmosphere_handoff as handoff
    return contract, compiler, verification, preservation, handoff


def _operation_ids(request: dict) -> tuple[str, str]:
    return (MOIST_COMPILE, MOIST_VERIFY) if _moist(request) else (COMPILE, VERIFY)


def runtime_identity(kind: str, *, moist: bool = False) -> dict:
    """Identify installed fixed providers; retained identities never load code."""
    if moist:
        from . import atmosphere_moist_contract as contract
    else:
        from . import atmosphere_contract as contract
    if kind == "compiler":
        if moist:
            from . import atmosphere_moist_compiler as provider
        else:
            from . import atmosphere_compiler as provider
    elif kind == "verifier":
        if moist:
            from . import atmosphere_moist_verification as provider
        else:
            from . import atmosphere_verification as provider
    else:
        raise ValueError("Unsupported atmospheric runtime kind")
    modules = [contract, provider, __import__(__name__, fromlist=["*"])]
    raw = b"\0".join(Path(module.__file__).name.encode() + b"\0" +
                     Path(module.__file__).read_text(encoding="utf-8").replace("\r\n", "\n").encode()
                     for module in modules)
    return {"provider": ("ciw.atmosphere.moist." if moist else "ciw.atmosphere.") + kind, "version": "1",
            "code_sha256": sha256(raw).hexdigest(), "source_normalization": "utf8_lf",
            "scope": ("declared_unsaturated_frozen_composition_reference_atmosphere_only" if moist
                      else "declared_dry_hydrostatic_reference_atmosphere_only"),
            "environment": {"python": platform.python_version(), "floating_point": "binary64"}}


def make_source(request: dict) -> dict:
    """Capture declared model inputs without compiling an altitude profile."""
    contract = _modules(request)[0]
    request = contract.validate_request(request)
    moist = _moist(request)
    reference = request["reference"]
    wind = request["profile"]["wind_enu_m_per_s"]
    channels = {"declared_temperature": {"unit": "K", "values": [reference["temperature_k"]]},
                "declared_pressure": {"unit": "Pa", "values": [reference["pressure_pa"]]},
                "height_above_reference": {"unit": "m", "values": [0.0]},
                "declared_wind_east": {"unit": "m/s", "values": [wind[0]]},
                "declared_wind_north": {"unit": "m/s", "values": [wind[1]]},
                "declared_wind_up": {"unit": "m/s", "values": [wind[2]]}}
    if moist:
        channels["declared_water_mixing_ratio"] = {
            "unit": "kg/kg dry air", "values": [request["profile"]["water_mixing_ratio_kg_per_kg_dry_air"]]}
    manifest = InstrumentManifest(
        instrument_id=("atmosphere-moist-configuration-declaration.v1" if moist
                       else "atmosphere-configuration-declaration.v1"),
        role=("synthetic_reference_configuration" if reference["context"]["source_kind"] == "synthetic"
              else "declared_reference_environment"),
        units={name: channel["unit"] for name, channel in channels.items()},
        frames=(FRAME,), sampling={"kind": "one_configuration_declaration", "time_semantics": "synthetic_selection_envelope"},
        supported_operations=_operation_ids(request),
        calibration_requirements={"physical_measurements": "none; declared reference-model configuration"},
    )
    source = {"run_schema": "run.v1", "run_id": ("run-atmosphere-moist-" if moist else "run-atmosphere-") + digest(request)[7:23],
              "instrument": manifest.instrument_id,
              "metadata": {"duration_s": 1.0, "sample_count": 1, "sample_rate_hz": None,
                           "coordinate_frame": FRAME, "manifest": manifest.to_dict(), "atmosphere_request": request,
                           "provenance": {"source": "declared reference-model configuration; not acquired measurements or an atmospheric profile",
                                          "generator": "ciw.atmosphere_workflow.make_source", "generator_version": 1}},
              "time_s": [0.0], "channels": channels,
              "render": {}}
    source["evidence_id"] = evidence_id(source)
    return source


def source_request(source: dict) -> dict:
    validate_run_structure(source)
    validate_evidence_identity(source)
    request = source["metadata"]["atmosphere_request"]
    if source != make_source(request):
        raise ValueError("Atmosphere source must be the exact declared reference-model configuration")
    return deepcopy(request)


def _validate_runtime(operation: str, runtime: dict) -> None:
    """Bind the fixed provider profile while retaining historical code hashes."""
    moist = operation in {MOIST_COMPILE, MOIST_VERIFY}
    kind = "compiler" if operation in {COMPILE, MOIST_COMPILE} else "verifier"
    provider = ("ciw.atmosphere.moist." if moist else "ciw.atmosphere.") + kind
    scope = ("declared_unsaturated_frozen_composition_reference_atmosphere_only" if moist
             else "declared_dry_hydrostatic_reference_atmosphere_only")
    if (type(runtime) is not dict or runtime.get("provider") != provider
            or runtime.get("scope") != scope or runtime.get("version") != "1"
            or runtime.get("source_normalization") != "utf8_lf"):
        raise ValueError("Atmosphere runtime identity contradicts the fixed provider profile")
    keys(runtime, {"provider", "scope", "version", "source_normalization", "code_sha256", "environment"})
    code_hash = runtime["code_sha256"]
    if (type(code_hash) is not str or len(code_hash) != 64
            or any(character not in "0123456789abcdef" for character in code_hash)):
        raise ValueError("Atmosphere runtime requires a retained SHA-256 code identity")
    environment = runtime["environment"]
    keys(environment, {"python", "floating_point"})
    if (type(environment["python"]) is not str or not environment["python"].strip()
            or len(environment["python"]) > 40 or environment["floating_point"] != "binary64"):
        raise ValueError("Atmosphere runtime environment declaration differs")


def _compile(source: dict, parameters: dict, *, moist: bool = False) -> dict:
    keys(parameters, set())
    request = source_request(source)
    if _moist(request) != moist:
        raise ValueError("Atmosphere compiler operation contradicts source profile")
    return _modules(request)[1].compile_atmosphere(request)


def _candidate(source: dict, parameters: dict) -> dict:
    request = source_request(source)
    contract = _modules(request)[0]
    compile_id, _ = _operation_ids(request)
    keys(parameters, {"candidate"})
    candidate = parameters["candidate"]
    check_seal(candidate)
    if (candidate.get("schema") != "ciw.operation-result.v1" or candidate.get("operation_id") != compile_id
            or candidate.get("role") != "backend" or candidate.get("evidence_id") != source["evidence_id"]
            or candidate.get("run_id") != source["run_id"] or candidate.get("parameters") != {}):
        raise ValueError("Atmosphere verification candidate must bind the exact source and compiler operation")
    validate_identity(candidate.get("result_id"), "result")
    validate_identity(candidate.get("execution_id"), "execution")
    _validate_runtime(compile_id, candidate.get("runtime"))
    contract.validate_result(request, candidate["data"])
    return candidate


def _verify(source: dict, parameters: dict, *, moist: bool = False) -> dict:
    request = source_request(source)
    if _moist(request) != moist:
        raise ValueError("Atmosphere verifier operation contradicts source profile")
    candidate = _candidate(source, parameters)
    return {"schema": "ciw.atmosphere-verification-payload.v1", "verification_id": new_identity("verification"),
            "candidate_result_id": candidate["result_id"], "candidate_execution_id": candidate["execution_id"],
            "candidate_record_digest": candidate["record_digest"], "source_evidence_id": source["evidence_id"],
            "report": _modules(request)[2].verify(request, candidate["data"]), "authority": deepcopy(AUTHORITY)}


def operations() -> list[Operation]:
    return [Operation(COMPILE, "backend", _compile, lambda: runtime_identity("compiler")),
            Operation(VERIFY, "verification", _verify, lambda: runtime_identity("verifier")),
            Operation(MOIST_COMPILE, "backend", lambda source, parameters: _compile(source, parameters, moist=True),
                      lambda: runtime_identity("compiler", moist=True)),
            Operation(MOIST_VERIFY, "verification", lambda source, parameters: _verify(source, parameters, moist=True),
                      lambda: runtime_identity("verifier", moist=True))]


def registry():
    """Explicit trusted binding; saved schemas and import strings activate nothing."""
    from .operations.registry import default_registry
    result = default_registry()
    for operation in operations():
        result.register(operation)
    return result


def validate_payload(operation: str, data: dict, source: dict, parameters: dict, selection: dict) -> None:
    """Validate stored contracts without invoking compiler or numerical verifier."""
    request = source_request(source)
    contract, _, verifier, _, _ = _modules(request)
    compile_id, verify_id = _operation_ids(request)
    if operation == compile_id:
        keys(parameters, set())
        contract.validate_result(request, data)
    elif operation == verify_id:
        candidate = _candidate(source, parameters)
        keys(data, {"schema", "verification_id", "candidate_result_id", "candidate_execution_id",
                    "candidate_record_digest", "source_evidence_id", "report", "authority"})
        validate_identity(data["verification_id"], "verification")
        if (data["schema"] != "ciw.atmosphere-verification-payload.v1" or data["authority"] != AUTHORITY
                or data["source_evidence_id"] != source["evidence_id"]
                or data["candidate_result_id"] != candidate["result_id"]
                or data["candidate_execution_id"] != candidate["execution_id"]
                or data["candidate_record_digest"] != candidate["record_digest"]):
            raise ValueError("Atmosphere verification identity or authority binding differs")
        verifier.validate_report(request, candidate["data"], data["report"])
    else:
        raise ValueError("Unsupported atmosphere operation")


def validate_result_dependencies(results: dict) -> None:
    """An embedded candidate must equal an actually retained compiler occurrence."""
    identities = set()
    for result in results.values():
        if result.get("operation_id") in {COMPILE, VERIFY, MOIST_COMPILE, MOIST_VERIFY}:
            _validate_runtime(result["operation_id"], result.get("runtime"))
        if result.get("operation_id") not in {VERIFY, MOIST_VERIFY}:
            continue
        candidate = result["parameters"]["candidate"]
        if results.get(candidate["result_id"]) != candidate:
            raise ValueError("Atmosphere verification candidate differs from retained compiler occurrence")
        identity = result["data"]["verification_id"]
        if identity in identities:
            raise ValueError("Duplicate atmosphere verification occurrence identity")
        identities.add(identity)


def _execute(session, operation: str, parameters: dict) -> dict:
    reply = session.handle({"protocol_version": 1, "request_id": "atmosphere-workload", "type": "operation.execute",
                            "payload": {"operation_id": operation, "parameters": parameters}})
    if reply["type"] != "response":
        raise ValueError(reply["payload"]["message"])
    return reply["payload"]


def run(request: dict, destination: Path) -> dict:
    from .session import Session
    source = make_source(request)
    compile_id, verify_id = _operation_ids(request)
    preservation = _modules(request)[3]
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    save_new(destination / "request.json", source_request(source))
    session = Session(source, destination, operations=registry())
    candidate = _execute(session, compile_id, {})
    verification = None
    if candidate["status"] == "completed":
        verification = _execute(session, verify_id, {"candidate": candidate["result"]})
    session.save_workspace(destination / "workspace.json")
    if candidate["status"] != "completed" or verification is None or verification["status"] != "completed":
        return inspect(destination)
    save_new(destination / "verification.json", verification["result"]["data"])
    save_new(destination / "preservation.json", preservation.build(source_request(session.run), candidate["result"]["data"],
                                                     verification["result"]["data"]["report"]))
    return inspect(destination)


def _preflight(destination: Path) -> None:
    """Bound untrusted files before the generic Session JSON reader allocates."""
    for name in ("workspace.json", "request.json", "verification.json", "preservation.json"):
        path = destination / name
        present = path.exists() or path.is_symlink()
        if not present and name not in {"workspace.json", "request.json"}:
            continue
        if path.is_symlink() or not path.is_file():
            raise ValueError("Atmosphere bundle files must be regular files without symlinks")
        if path.stat().st_size > MAX_BUNDLE_FILE_BYTES:
            raise ValueError("Atmosphere bundle file exceeds the bounded 8 MiB budget")


def _read(destination: Path):
    from .session import Session
    destination = Path(destination)
    _preflight(destination)
    with tempfile.TemporaryDirectory(prefix="atmosphere-inspect-") as temporary:
        session = Session.from_workspace(destination / "workspace.json", Path(temporary))
    request = source_request(session.run)
    contract, _, _, preservation_module, _ = _modules(request)
    compile_id, verify_id = _operation_ids(request)
    retained_request = contract.validate_request(load(destination / "request.json"))
    if digest(retained_request) != digest(request):
        raise ValueError("Retained atmosphere request differs from source evidence")
    candidates = [result for result in session.results.values() if result["operation_id"] == compile_id]
    verifications = [result for result in session.results.values() if result["operation_id"] == verify_id]
    executions = list(session.executions.values())
    if any(execution["operation_id"] not in {compile_id, verify_id} for execution in executions):
        raise ValueError("Atmosphere bundle contains an unrelated execution")
    unexpected_receipt = any((destination / name).exists() or (destination / name).is_symlink()
                             for name in ("verification.json", "preservation.json"))
    if len(executions) == 1 and executions[0]["operation_id"] == compile_id and executions[0]["status"] == "refused":
        if session.results or unexpected_receipt:
            raise ValueError("Refused atmospheric compiler bundle cannot contain results or receipts")
        return session, None, None
    if (len(executions) == 2 and len(candidates) == 1 and not verifications
            and sum(execution["status"] == "refused" and execution["operation_id"] == verify_id for execution in executions) == 1):
        if len(session.results) != 1 or unexpected_receipt:
            raise ValueError("Refused atmospheric verifier bundle contains unexpected results or receipts")
        return session, candidates[0], None
    if len(candidates) != 1 or len(verifications) != 1 or len(session.results) != 2 or len(executions) != 2:
        raise ValueError("Atmosphere bundle requires one compiler and one independent verification occurrence")
    candidate, verification = candidates[0], verifications[0]
    if verification["parameters"]["candidate"] != candidate:
        raise ValueError("Atmospheric verification does not bind the retained candidate occurrence")
    if digest(load(destination / "verification.json")) != digest(verification["data"]):
        raise ValueError("Atmospheric verification artifact differs from retained verification result")
    preservation = load(destination / "preservation.json")
    preservation_module.validate(preservation, request, candidate["data"], verification["data"]["report"])
    session._atmosphere_preservation = deepcopy(preservation)
    return session, candidate, verification


def _inspection_from_read(session, candidate: dict | None, verification: dict | None) -> dict:
    if verification is None:
        attempts = [{name: deepcopy(value) for name, value in entry.items() if name != "parameters"}
                    for entry in session.executions.values()]
        return {"schema": "ciw.atmosphere-inspection.v1", "status": "REFUSE", "evidence_id": session.run["evidence_id"],
                "executions": attempts, "fresh_execution": False, "fresh_numerical_verification": False,
                "authority": deepcopy(AUTHORITY)}
    report = verification["data"]["report"]
    preservation = session._atmosphere_preservation
    return {"schema": "ciw.atmosphere-inspection.v1", "status": report["qualification"]["action"],
            "qualification": deepcopy(report["qualification"]), "evidence_id": session.run["evidence_id"],
            "operation_id": candidate["operation_id"], "execution_id": candidate["execution_id"], "result_id": candidate["result_id"],
            "verification_operation_id": verification["operation_id"], "verification_execution_id": verification["execution_id"],
            "verification_id": verification["data"]["verification_id"], "checks": deepcopy(report["checks"]),
            "metrics": deepcopy(report["metrics"]), "fresh_execution": False, "fresh_numerical_verification": False,
            "preservation": {"contract_ref": preservation["contract"]["record_digest"],
                             "verification_ref": preservation["verification"]["record_digest"],
                             "verification_status": preservation["verification"]["status"],
                             "admission_eligibility": preservation["admission_gate"]["decision"],
                             "state_admission_performed": False}, "authority": deepcopy(AUTHORITY)}


def inspect(destination: Path) -> dict:
    return _inspection_from_read(*_read(destination))


def _verify_read(session, candidate: dict | None, verification: dict | None) -> dict:
    if verification is None:
        return _inspection_from_read(session, candidate, verification)
    request = source_request(session.run)
    fresh = _modules(request)[2].verify(request, candidate["data"])
    if fresh != verification["data"]["report"]:
        raise ValueError("Independent atmospheric recomputation differs from retained verification report")
    result = _inspection_from_read(session, candidate, verification)
    result["fresh_numerical_verification"] = True
    result["recomputed_report_digest"] = fresh["record_digest"]
    result["recomputed_with_runtime"] = runtime_identity("verifier", moist=_moist(request))
    return result


def verify_retained(destination: Path) -> dict:
    return _verify_read(*_read(destination))


def export_csv(destination: Path, output: Path) -> dict:
    session, candidate, verification = _read(destination)
    checked = _verify_read(session, candidate, verification)
    if checked["status"] != "LOCAL":
        raise ValueError("Only a numerically qualified LOCAL atmosphere profile can be exported")
    profile = candidate["data"]["profile"]
    contract = _modules(source_request(session.run))[0]
    scalar_names = [name for name in contract.STATE_FIELDS if name != "wind_enu_m_per_s"]
    names = scalar_names + ["wind_east_m_per_s", "wind_north_m_per_s", "wind_up_m_per_s"]
    rows = [[profile[name][index] for name in scalar_names] + list(wind)
            for index, wind in enumerate(profile["wind_enu_m_per_s"])]
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(names)
        writer.writerows(rows)
    return {"status": "exported", "file": str(output), "source_evidence_id": session.run["evidence_id"],
            "source_result_id": candidate["result_id"], "source_execution_id": candidate["execution_id"],
            "source_record_digest": candidate["record_digest"], "verification_id": checked["verification_id"],
            "recomputed_report_digest": checked["recomputed_report_digest"], "authority": deepcopy(AUTHORITY)}


def export_handoff(destination: Path, output: Path, *, sample_index: int, provider: str) -> dict:
    """Export an exact retained altitude sample after fresh independent audit."""
    if type(sample_index) is not int or sample_index < 0:
        raise ValueError("sample_index must be a nonnegative integer")
    if type(provider) is not str or provider not in {"impact", "fluid", "render"}:
        raise ValueError("Unsupported atmospheric handoff provider")
    session, candidate, verification = _read(destination)
    if candidate is None:
        raise ValueError("A retained atmospheric compiler result is required for handoff")
    if sample_index >= len(candidate["data"]["profile"]["height_m"]):
        raise ValueError("sample_index lies outside the retained height grid")
    checked = _verify_read(session, candidate, verification)
    if checked["status"] != "LOCAL":
        raise ValueError("Only a numerically qualified LOCAL atmosphere sample can be handed off")
    bindings = {"source_evidence_id": session.run["evidence_id"], "source_result_id": candidate["result_id"],
                "source_execution_id": candidate["execution_id"], "source_record_digest": candidate["record_digest"],
                "verification_id": checked["verification_id"],
                "recomputed_report_digest": checked["recomputed_report_digest"]}
    request = source_request(session.run)
    payload = _modules(request)[4].build_handoff(request, candidate["data"], bindings,
                            sample_index=sample_index, provider=provider)
    save_new(output, payload)
    return {"status": "exported", "file": str(output), "handoff_digest": payload["record_digest"],
            "sample_index": sample_index, "provider": provider, **bindings, "authority": deepcopy(AUTHORITY)}
