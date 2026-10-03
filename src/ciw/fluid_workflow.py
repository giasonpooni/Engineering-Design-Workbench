"""Retained synthetic fluid dynamics on the existing explicit Session substrate.

The evidence is exactly one declared model configuration. Computed trajectories
are operation results with a provider-owned model clock, never acquired samples.
"""
from __future__ import annotations

from copy import deepcopy
import csv
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import re
import stat
import tempfile

from .adapters.protocol import InstrumentManifest
from .control_contracts import content_ref, json_tree, keys, save_new
from .core.identities import evidence_id, new_identity, validate_evidence_identity, validate_identity
from .core.records import validate_run_structure
from . import fluid_contract as contract
from .operations.registry import Operation
from .operations.runner import check_seal, digest

FRAME = "fluid.synthetic_configuration.v1"
MAX_BUNDLE_FILE_BYTES = 128 * 1024 * 1024
MAX_DECLARATION_FILE_BYTES = 8 * 1024 * 1024
AUTHORITY = {
    "physical_validation": "not_established", "molecular_scale_preservation": "not_established",
    "resolved_vertical_flow": "not_established", "general_fluid_structure_coupling": "not_established",
    "state_admission": "not_performed", "hardware_actuation": "not_performed",
}
OPERATIONS = contract.ALL_OPERATIONS


def runtime_identity(profile: str, kind: str) -> dict:
    """Identify fixed installed code and dependencies; retained hashes load no code."""
    import numpy as np
    domain = contract.module(profile)
    if kind == "solver":
        provider = contract.provider_module(profile, "solver")
        modules = [domain, provider]
    elif kind == "verifier":
        provider = contract.provider_module(profile, "verification")
        reference = contract.provider_module(profile, "reference")
        modules = [domain, provider, reference]
    else:
        raise ValueError("Unsupported fluid runtime kind")
    modules += [contract, __import__(__name__, fromlist=["*"])]
    raw = b"\0".join(Path(item.__file__).name.encode() + b"\0" +
                     Path(item.__file__).read_text(encoding="utf-8").replace("\r\n", "\n").encode()
                     for item in modules)
    return {"provider": "ciw.fluid." + profile + "." + kind, "version": "1",
            "code_sha256": sha256(raw).hexdigest(), "source_normalization": "utf8_lf",
            "scope": domain.CLAIM_SCOPE,
            "environment": {"python": platform.python_version(), "numpy": np.__version__, "floating_point": "binary64"}}


def validate_runtime(operation: str, runtime: dict | None, *, allow_absent: bool = False) -> None:
    """Check provenance structurally without requiring installed historical code."""
    profile, kind = contract.profile_for_operation(operation)
    if runtime is None and allow_absent:
        return
    keys(runtime, {"provider", "version", "code_sha256", "source_normalization", "scope", "environment"})
    if (runtime["provider"] != "ciw.fluid." + profile + "." + kind or runtime["version"] != "1"
            or runtime["source_normalization"] != "utf8_lf" or runtime["scope"] != contract.module(profile).CLAIM_SCOPE):
        raise ValueError("Fluid runtime provider, version or scope binding differs")
    content_ref("sha256:" + runtime["code_sha256"] if type(runtime["code_sha256"]) is str else None)
    keys(runtime["environment"], {"python", "numpy", "floating_point"})
    if (type(runtime["environment"]["python"]) is not str
            or not 1 <= len(runtime["environment"]["python"]) <= 80
            or runtime["environment"]["floating_point"] != "binary64"):
        raise ValueError("Fluid runtime environment binding differs")
    numpy_version = runtime["environment"]["numpy"]
    if (type(numpy_version) is not str or len(numpy_version) > 80
            or re.fullmatch(r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}[A-Za-z0-9.+-]*", numpy_version) is None):
        raise ValueError("Fluid runtime NumPy version must be a bounded version string")


def make_source(request: dict) -> dict:
    request = contract.validate_request(request)
    profile = contract.profile_for_request(request)
    operations = OPERATIONS[profile]
    channels = {"configuration_declaration": {"unit": "1", "values": [0.0]}}
    manifest = InstrumentManifest(
        instrument_id="fluid-" + profile + "-configuration-declaration.v1",
        role="synthetic_model_configuration", units={"configuration_declaration": "1"},
        frames=(FRAME,), sampling={"kind": "one_synthetic_configuration_declaration",
                                   "time_semantics": "synthetic_selection_envelope_not_model_clock"},
        supported_operations=operations,
        calibration_requirements={"physical_measurements": "none; synthetic model configuration only"},
    )
    source = {"run_schema": "run.v1", "run_id": "run-fluid-" + profile + "-" + digest(request)[7:23],
              "instrument": manifest.instrument_id,
              "metadata": {"duration_s": 1.0, "sample_count": 1, "sample_rate_hz": None,
                           "coordinate_frame": FRAME, "manifest": manifest.to_dict(), "fluid_request": request,
                           "provenance": {"source": "exact synthetic model configuration declaration; not acquired measurements or a simulated trajectory",
                                          "generator": "ciw.fluid_workflow.make_source", "generator_version": 1}},
              "time_s": [0.0], "channels": channels, "render": {}}
    source["evidence_id"] = evidence_id(source)
    return source


def source_request(source: dict) -> dict:
    validate_run_structure(source)
    validate_evidence_identity(source)
    request = source["metadata"]["fluid_request"]
    if digest(source) != digest(make_source(request)):
        raise ValueError("Fluid source must be the exact synthetic configuration declaration")
    return deepcopy(request)


def _simulate(source: dict, parameters: dict) -> dict:
    keys(parameters, set())
    return contract.simulate(source_request(source))


def _candidate(source: dict, parameters: dict) -> dict:
    request = source_request(source)
    profile = contract.profile_for_request(request)
    keys(parameters, {"candidate"})
    candidate = parameters["candidate"]
    check_seal(candidate)
    if (candidate.get("schema") != "ciw.operation-result.v1" or candidate.get("operation_id") != OPERATIONS[profile][0]
            or candidate.get("role") != "backend" or candidate.get("evidence_id") != source["evidence_id"]
            or candidate.get("run_id") != source["run_id"] or candidate.get("parameters") != {}):
        raise ValueError("Fluid candidate must bind the exact source and profile simulation operation")
    validate_identity(candidate.get("result_id"), "result")
    validate_identity(candidate.get("execution_id"), "execution")
    validate_runtime(candidate["operation_id"], candidate.get("runtime"))
    contract.validate_result(request, candidate["data"])
    return candidate


def _verify(source: dict, parameters: dict) -> dict:
    candidate = _candidate(source, parameters)
    return {"schema": "ciw.fluid-verification-payload.v1", "verification_id": new_identity("verification"),
            "candidate_result_id": candidate["result_id"], "candidate_execution_id": candidate["execution_id"],
            "candidate_record_digest": candidate["record_digest"], "source_evidence_id": source["evidence_id"],
            "report": contract.verify(source_request(source), candidate["data"]), "authority": deepcopy(AUTHORITY)}


def operations() -> list[Operation]:
    result = []
    for profile, (simulation, verification) in OPERATIONS.items():
        result += [Operation(simulation, "backend", _simulate, lambda profile=profile: runtime_identity(profile, "solver")),
                   Operation(verification, "verification", _verify, lambda profile=profile: runtime_identity(profile, "verifier"))]
    return result


def registry():
    """Explicit trusted binding; default registries and archives activate nothing."""
    from .operations.registry import default_registry
    result = default_registry()
    for operation in operations():
        result.register(operation)
    return result


def validate_payload(operation: str, data: dict, source: dict, parameters: dict, selection: dict) -> None:
    """Validate stored content without numerical simulation or verification."""
    request = source_request(source)
    profile, kind = contract.profile_for_operation(operation)
    if profile != contract.profile_for_request(request):
        raise ValueError("Fluid operation profile differs from exact declared source")
    if kind == "solver":
        keys(parameters, set())
        contract.validate_result(request, data)
        return
    candidate = _candidate(source, parameters)
    keys(data, {"schema", "verification_id", "candidate_result_id", "candidate_execution_id",
                "candidate_record_digest", "source_evidence_id", "report", "authority"})
    validate_identity(data["verification_id"], "verification")
    if (data["schema"] != "ciw.fluid-verification-payload.v1" or data["authority"] != AUTHORITY
            or data["source_evidence_id"] != source["evidence_id"]
            or data["candidate_result_id"] != candidate["result_id"]
            or data["candidate_execution_id"] != candidate["execution_id"]
            or data["candidate_record_digest"] != candidate["record_digest"]):
        raise ValueError("Fluid verification identity or authority binding differs")
    contract.validate_report(request, candidate["data"], data["report"])


def validate_result_dependencies(results: dict) -> None:
    identities = set()
    for result in results.values():
        operation = result.get("operation_id")
        if operation not in {identity for pair in OPERATIONS.values() for identity in pair}:
            continue
        validate_runtime(operation, result.get("runtime"))
        profile, kind = contract.profile_for_operation(operation)
        if kind == "solver":
            continue
        candidate = result["parameters"]["candidate"]
        if results.get(candidate["result_id"]) != candidate:
            raise ValueError("Fluid verification candidate differs from retained simulation occurrence")
        identity = result["data"]["verification_id"]
        if identity in identities:
            raise ValueError("Duplicate fluid verification occurrence identity")
        identities.add(identity)


def validate_live_dependency(parameters: dict, retained_results: dict) -> None:
    """Only an actually retained simulation occurrence can be verified live."""
    keys(parameters, {"candidate"})
    candidate = parameters["candidate"]
    if (type(candidate) is not dict or type(candidate.get("result_id")) is not str
            or retained_results.get(candidate["result_id"]) != candidate):
        raise ValueError("Fluid verification dependency is not the actually retained simulation occurrence")


def _execute(session, operation: str, parameters: dict) -> dict:
    reply = session.handle({"protocol_version": 1, "request_id": "fluid-workload", "type": "operation.execute",
                            "payload": {"operation_id": operation, "parameters": parameters}})
    if reply["type"] != "response":
        raise ValueError(reply["payload"]["message"])
    return reply["payload"]


def run(request: dict, destination: Path) -> dict:
    from .session import Session
    from .fluid_preservation import build
    source = make_source(request)
    profile = contract.profile_for_request(source_request(source))
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    save_new(destination / "request.json", source_request(source))
    session = Session(source, destination, operations=registry())
    candidate = _execute(session, OPERATIONS[profile][0], {})
    verification = None
    if candidate["status"] == "completed":
        verification = _execute(session, OPERATIONS[profile][1], {"candidate": candidate["result"]})
    session.save_workspace(destination / "workspace.json")
    if candidate["status"] == "completed" and verification is not None and verification["status"] == "completed":
        save_new(destination / "verification.json", verification["result"]["data"])
        save_new(destination / "preservation.json", build(source_request(session.run), candidate["result"]["data"],
                                                         verification["result"]["data"]["report"]))
    return inspect(destination)


def load_regular(path: Path, *, max_bytes: int = MAX_DECLARATION_FILE_BYTES) -> dict:
    """Read a bounded regular file, refusing links, devices, pipes and huge JSON."""
    from .session import loads_json
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Fluid files must be regular files without symlinks")
    mode = path.stat().st_mode
    if not stat.S_ISREG(mode):
        raise ValueError("Fluid files must be regular files without symlinks")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    try:
        actual = os.fstat(descriptor)
        if not stat.S_ISREG(actual.st_mode):
            raise ValueError("Fluid files must be regular files without symlinks")
        if actual.st_size > max_bytes:
            raise ValueError("Fluid file exceeds the bounded byte budget")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            raw = stream.read(max_bytes + 1)
        if not raw or len(raw) > max_bytes:
            raise ValueError("Fluid file exceeds byte budget or is empty")
    finally:
        os.close(descriptor)
    value = loads_json(raw.decode("utf-8"))
    json_tree(value)
    return value


def _read(destination: Path):
    from .session import Session
    from .fluid_preservation import validate
    destination = Path(destination)
    # Read each external file once. Session validates a private bounded snapshot,
    # avoiding both an unbounded generic read and a preflight/read substitution.
    artifacts = {"workspace.json": load_regular(destination / "workspace.json", max_bytes=MAX_BUNDLE_FILE_BYTES),
                 "request.json": load_regular(destination / "request.json")}
    for name in ("verification.json", "preservation.json"):
        path = destination / name
        if path.exists() or path.is_symlink():
            artifacts[name] = load_regular(path)
    with tempfile.TemporaryDirectory(prefix="fluid-inspect-") as temporary:
        root = Path(temporary)
        snapshot = root / "snapshot.json"
        snapshot.write_text(json.dumps(artifacts["workspace.json"], allow_nan=False), encoding="utf-8")
        session = Session.from_workspace(snapshot, root / "restored")
    request = source_request(session.run)
    if digest(contract.validate_request(artifacts["request.json"])) != digest(request):
        raise ValueError("Retained fluid request differs from exact source declaration")
    profile = contract.profile_for_request(request)
    simulation_op, verification_op = OPERATIONS[profile]
    candidates = [row for row in session.results.values() if row["operation_id"] == simulation_op]
    verifications = [row for row in session.results.values() if row["operation_id"] == verification_op]
    executions = list(session.executions.values())
    if any(row["operation_id"] not in {simulation_op, verification_op} for row in executions):
        raise ValueError("Fluid bundle contains an unrelated execution")
    receipts = "verification.json" in artifacts or "preservation.json" in artifacts
    if len(executions) == 1 and executions[0]["operation_id"] == simulation_op and executions[0]["status"] == "refused":
        if session.results or receipts:
            raise ValueError("Refused fluid simulator bundle cannot contain results or receipts")
        return session, None, None
    if (len(executions) == 2 and len(candidates) == 1 and not verifications
            and sum(row["operation_id"] == verification_op and row["status"] == "refused" for row in executions) == 1):
        if len(session.results) != 1 or receipts:
            raise ValueError("Refused fluid verifier bundle contains unexpected results or receipts")
        return session, candidates[0], None
    if len(candidates) != 1 or len(verifications) != 1 or len(session.results) != 2 or len(executions) != 2:
        raise ValueError("Fluid bundle requires one simulation and one independent verification occurrence")
    candidate, verification = candidates[0], verifications[0]
    if verification["parameters"]["candidate"] != candidate:
        raise ValueError("Fluid verification differs from the retained candidate occurrence")
    if digest(artifacts.get("verification.json")) != digest(verification["data"]):
        raise ValueError("Fluid verification artifact differs from retained verification result")
    preservation = artifacts.get("preservation.json")
    validate(preservation, request, candidate["data"], verification["data"]["report"])
    session._fluid_preservation = deepcopy(preservation)
    return session, candidate, verification


def _inspection_from_read(session, candidate: dict | None, verification: dict | None) -> dict:
    request = source_request(session.run)
    base = {"schema": "ciw.fluid-inspection.v1", "profile": contract.profile_for_request(request),
            "evidence_id": session.run["evidence_id"], "fresh_execution": False,
            "fresh_numerical_verification": False, "authority": deepcopy(AUTHORITY)}
    if verification is None:
        base.update(status="REFUSE", executions=[{name: deepcopy(value) for name, value in entry.items() if name != "parameters"}
                                                 for entry in session.executions.values()])
        return base
    report = verification["data"]["report"]
    preservation = session._fluid_preservation
    base.update(status=report["qualification"]["action"], qualification=deepcopy(report["qualification"]),
                operation_id=candidate["operation_id"], execution_id=candidate["execution_id"], result_id=candidate["result_id"],
                verification_operation_id=verification["operation_id"], verification_execution_id=verification["execution_id"],
                verification_id=verification["data"]["verification_id"], checks=deepcopy(report["checks"]), metrics=deepcopy(report["metrics"]),
                preservation={"contract_ref": preservation["contract"]["record_digest"],
                              "verification_ref": preservation["verification"]["record_digest"],
                              "verification_status": preservation["verification"]["status"],
                              "admission_eligibility": preservation["admission_gate"]["decision"],
                              "state_admission_performed": False})
    return base


def inspect(destination: Path) -> dict:
    return _inspection_from_read(*_read(destination))


def _verify_read(session, candidate: dict | None, verification: dict | None) -> dict:
    from .session import Session
    if verification is None:
        return _inspection_from_read(session, candidate, verification)
    profile = contract.profile_for_request(source_request(session.run))
    # Every fresh audit is a new Session operation occurrence. The retained
    # candidate dependency is carried explicitly; the original bundle is read-only.
    with tempfile.TemporaryDirectory(prefix="fluid-verify-") as temporary:
        audit = Session(session.run, Path(temporary), operations=registry())
        audit.results[candidate["result_id"]] = deepcopy(candidate)
        audit.selection = deepcopy(session.selection)
        fresh = _execute(audit, OPERATIONS[profile][1], {"candidate": candidate})
    if fresh["status"] != "completed":
        raise ValueError("Fresh independent fluid verification refused: " + fresh["execution"]["refusal"]["message"])
    result = fresh["result"]
    if digest(result["data"]["report"]) != digest(verification["data"]["report"]):
        raise ValueError("Fresh independent fluid verification differs from retained report")
    checked = _inspection_from_read(session, candidate, verification)
    checked.update(fresh_execution=True, fresh_numerical_verification=True,
                   fresh_verification_id=result["data"]["verification_id"],
                   fresh_verification_execution_id=result["execution_id"], fresh_verification_result_id=result["result_id"],
                   fresh_verification_record=deepcopy(result["data"]),
                   recomputed_report_digest=result["data"]["report"]["record_digest"],
                   recomputed_with_runtime=deepcopy(result["runtime"]))
    return checked


def verify_retained(destination: Path) -> dict:
    return _verify_read(*_read(destination))


def _csv_rows(profile: str, result: dict):
    if profile in contract.EXTENDED_PROFILES:
        return contract.provider_module(profile, "solver").csv_rows(result)
    if profile == "reservoir":
        trace = result["resolutions"]["finer"]["trace"]
        names = list(trace)
        return names, zip(*(trace[name] for name in names))
    trace = result["primary"]
    names = ["time_s", "grid_index", "cell_x_m", "face_x_m", "free_surface_elevation_m",
             "depth_averaged_velocity_m_per_s", "volume_flux_m3_per_s", "bottom_gauge_pressure_pa",
             "liquid_volume_m3", "mechanical_energy_j"]
    rows = ([time, cell, trace["cell_x_m"][cell], trace["face_x_m"][cell],
             trace["free_surface_elevation_m"][index][cell], trace["depth_averaged_velocity_m_per_s"][index][cell],
             trace["volume_flux_m3_per_s"][index][cell], trace["bottom_gauge_pressure_pa"][index][cell],
             trace["liquid_volume_m3"][index], trace["mechanical_energy_j"][index]]
            for index, time in enumerate(trace["time_s"]) for cell in range(trace["cells"]))
    return names, rows


def export_csv(destination: Path, output: Path) -> dict:
    session, candidate, verification = _read(destination)
    checked = _verify_read(session, candidate, verification)
    if checked["status"] != "LOCAL":
        raise ValueError("Only a freshly numerically qualified LOCAL fluid trajectory can be exported")
    names, rows = _csv_rows(checked["profile"], candidate["data"])
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(names)
        writer.writerows(rows)
    return {"status": "exported", "file": str(output), "profile": checked["profile"],
            "source_evidence_id": session.run["evidence_id"], "source_result_id": candidate["result_id"],
            "source_execution_id": candidate["execution_id"], "source_record_digest": candidate["record_digest"],
            "retained_verification_id": checked["verification_id"],
            "fresh_verification_id": checked["fresh_verification_id"],
            "fresh_verification_execution_id": checked["fresh_verification_execution_id"],
            "fresh_verification_result_id": checked["fresh_verification_result_id"],
            "recomputed_report_digest": checked["recomputed_report_digest"], "authority": deepcopy(AUTHORITY)}


def reduce_particles(destination: Path, output: Path, *, sample_index: int, bins: list[int]) -> dict:
    """Freshly qualify a retained sample, then audit its instantaneous bin map."""
    from . import fluid_scale_maps as maps
    from .control_contracts import save_new
    session, candidate, verification = _read(destination)
    checked = _verify_read(session, candidate, verification)
    if checked["status"] != "LOCAL" or checked["profile"] not in {"molecular", "sph"}:
        raise ValueError("Particle reduction requires a freshly qualified LOCAL molecular or SPH trajectory")
    snapshot = maps.particle_snapshot(checked["profile"], source_request(session.run), candidate["data"],
                                     verification["data"]["report"], sample_index=sample_index)
    mapped = maps.reduce(snapshot, bins_per_axis=bins)
    report = maps.verify(snapshot, mapped)
    if report["status"] != "PASS":
        raise ValueError("Finite particle map conservation audit failed")
    artifact = {"schema": "ciw.fluid-retained-scale-map.v1", "snapshot": snapshot, "mapped": mapped,
                "map_verification": report,
                "source_occurrences": {"evidence_id": session.run["evidence_id"], "result_id": candidate["result_id"],
                                       "execution_id": candidate["execution_id"],
                                       "fresh_verification_id": checked["fresh_verification_id"],
                                       "fresh_verification_execution_id": checked["fresh_verification_execution_id"],
                                       "fresh_verification_result_id": checked["fresh_verification_result_id"]},
                "fresh_source_verification": checked["fresh_verification_record"], "authority": deepcopy(AUTHORITY)}
    save_new(output, artifact)
    return {"status": "LOCAL", "file": str(output), "profile": checked["profile"],
            "map_digest": mapped["record_digest"], "fresh_verification_id": checked["fresh_verification_id"],
            "scope": "instantaneous finite mass, momentum and kinetic-energy accounting; no constitutive closure"}
