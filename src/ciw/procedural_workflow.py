"""Declared procedural geometry on NET's retained operation substrate.

The one configuration sample provides selection support, not physical time or
acquired material evidence. Inspection validates retained data without executing
the generator or independent numerical verifier.
"""
from __future__ import annotations

from copy import deepcopy
import base64
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import re
import stat
import tempfile
import zlib

import numpy as np

from .adapters.protocol import InstrumentManifest
from .control_contracts import content_ref, keys, save_new
from .core.identities import evidence_id, new_identity, validate_evidence_identity, validate_identity
from .core.records import validate_run_structure
from .operations.registry import Operation
from .operations.runner import check_seal, digest, seal

GENERATE = "procedural.generate.v1"
VERIFY = "procedural.verify.v1"
FRAME = "procedural.local_xyz.v1"
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_WORKSPACE_BYTES = 32 * 1024 * 1024
AUTHORITY = {"visual_geometry": "declared_numerical_surface_only",
             "physical_material_validation": "not_established",
             "manufacturing_suitability": "not_established",
             "state_admission": "not_performed", "hardware_actuation": "not_performed"}

IMPLICIT_SCHEMA = "ciw.procedural-request.v1"
SURFACE_SCHEMA = "ciw.procedural-surface-request.v1"
TEXTURE_SCHEMA = "ciw.procedural-texture-request.v1"


def _authority(request: dict) -> dict:
    result = deepcopy(AUTHORITY)
    if request["schema"] == TEXTURE_SCHEMA:
        result.update(visual_geometry="not_applicable", visual_texture="declared_cpu_rgba8_only",
                      gpu_pixel_equivalence="not_established")
    return result


def validate_request(request: dict) -> dict:
    """Fixed data-only dispatch; retained declarations choose no import strings."""
    schema = request.get("schema") if type(request) is dict else None
    if schema == IMPLICIT_SCHEMA:
        from .procedural_contract import validate_request as validate
    elif schema == SURFACE_SCHEMA:
        from .procedural_surface import validate_surface_request as validate
    elif schema == TEXTURE_SCHEMA:
        from .procedural_texture import validate_texture_request as validate
    else:
        raise ValueError("Unsupported declared procedural representation")
    return validate(request)


def validate_result(request: dict, artifact: dict) -> dict:
    request = validate_request(request)
    if request["schema"] == IMPLICIT_SCHEMA:
        from .procedural_contract import validate_result as validate
    elif request["schema"] == SURFACE_SCHEMA:
        from .procedural_surface import validate_surface_result as validate
    else:
        from .procedural_texture import validate_texture_result as validate
    return validate(request, artifact)


def generate_artifact(request: dict) -> dict:
    request = validate_request(request)
    if request["schema"] == IMPLICIT_SCHEMA:
        from .procedural_compiler import generate
    elif request["schema"] == SURFACE_SCHEMA:
        from .procedural_surface import generate_surface as generate
    else:
        from .procedural_texture import generate_texture as generate
    return generate(request)


def verify_artifact(request: dict, artifact: dict) -> dict:
    request = validate_request(request)
    if request["schema"] == IMPLICIT_SCHEMA:
        from .procedural_verification import verify
    else:
        from .procedural_representation_verification import verify
    return verify(request, artifact)


def _validate_report(request: dict, artifact: dict, report: dict) -> dict:
    if request["schema"] == IMPLICIT_SCHEMA:
        from .procedural_verification import validate_report
    else:
        from .procedural_representation_verification import validate_report
    return validate_report(request, artifact, report)


def runtime_identity(kind: str) -> dict:
    from . import procedural_contract as contract
    from . import graphics_notation, procedural_surface, procedural_texture
    if kind == "compiler":
        from . import procedural_compiler as provider
    elif kind == "verifier":
        from . import procedural_verification as provider
    else:
        raise ValueError("Unsupported procedural runtime kind")
    modules = [contract, graphics_notation, procedural_surface, procedural_texture, provider]
    if kind == "verifier":
        from . import procedural_representation_verification
        modules.append(procedural_representation_verification)
    modules.append(__import__(__name__, fromlist=["*"]))
    raw = b"\0".join(Path(module.__file__).name.encode() + b"\0" +
                     Path(module.__file__).read_text(encoding="utf-8").replace("\r\n", "\n").encode()
                     for module in modules)
    return {"provider": "ciw.procedural." + kind, "version": "1",
            "code_sha256": sha256(raw).hexdigest(), "source_normalization": "utf8_lf",
            "scope": "declared_visual_procedural_artifact_only",
            "environment": {"python": platform.python_version(), "numpy": np.__version__,
                            "floating_point": "binary64", "zlib": zlib.ZLIB_RUNTIME_VERSION,
                            "zlib_compiled": zlib.ZLIB_VERSION}}


def validate_runtime(kind: str, runtime: dict) -> None:
    keys(runtime, {"provider", "version", "code_sha256", "source_normalization", "scope", "environment"})
    if type(runtime["environment"]) is not dict or set(runtime["environment"]) not in (
            {"python", "numpy", "floating_point"}, {"python", "numpy", "floating_point", "zlib"},
            {"python", "numpy", "floating_point", "zlib", "zlib_compiled"}):
        raise ValueError("Invalid retained procedural runtime environment")
    if (runtime["provider"] != "ciw.procedural." + kind or runtime["version"] != "1"
            or runtime["source_normalization"] != "utf8_lf"
            or runtime["scope"] not in {"declared_visual_implicit_surface_only", "declared_visual_procedural_artifact_only"}
            or type(runtime["code_sha256"]) is not str
            or re.fullmatch(r"[0-9a-f]{64}", runtime["code_sha256"]) is None
            or runtime["environment"]["floating_point"] != "binary64"
            or any(type(runtime["environment"][field]) is not str
                   or not 1 <= len(runtime["environment"][field]) <= 128
                   for field in set(runtime["environment"]) - {"floating_point"})):
        raise ValueError("Invalid retained procedural runtime identity")


def make_source(request: dict) -> dict:
    request = validate_request(request)
    texture = request["schema"] == TEXTURE_SCHEMA
    frame = request["domain"]["frame"]
    channels = {"program_declaration": {"unit": "1", "values": [1.0]}}
    manifest = InstrumentManifest(
        instrument_id="procedural-program-declaration.v1", role="declared_procedural_program",
        units={"program_declaration": "1"}, frames=(frame,),
        sampling={"kind": "one_configuration_declaration", "time_semantics": "selection_support_not_physical_time"},
        supported_operations=(GENERATE, VERIFY),
        calibration_requirements={"physical_measurements": "none; declared visual texture program" if texture
                                  else "none; declared visual geometry program"},
    )
    source = {"run_schema": "run.v1", "run_id": "run-procedural-" + digest(request)[7:23],
              "instrument": manifest.instrument_id,
              "metadata": {"duration_s": 1.0, "sample_count": 1, "sample_rate_hz": None,
                           "coordinate_frame": frame, "manifest": manifest.to_dict(), "procedural_request": request,
                           "provenance": {"source": ("declared procedural texture; not acquired material evidence" if texture
                                                      else "declared procedural geometry; not acquired material evidence"),
                                          "generator": "ciw.procedural_workflow.make_source", "generator_version": 1}},
              "time_s": [0.0], "channels": channels, "render": {}}
    source["evidence_id"] = evidence_id(source)
    return source


def source_request(source: dict) -> dict:
    validate_run_structure(source)
    validate_evidence_identity(source)
    request = source["metadata"]["procedural_request"]
    if source != make_source(request):
        raise ValueError("Procedural source must equal the exact declared program")
    return deepcopy(request)


def _generate(source: dict, parameters: dict) -> dict:
    keys(parameters, set())
    result = generate_artifact(source_request(source))
    # Leave bounded room for occurrence envelopes and the verifier's embedded
    # candidate. The compiler's stand-alone artifact has its own 8 MiB budget.
    if len((json.dumps(result, indent=2, allow_nan=False) + "\n").encode()) > MAX_FILE_BYTES - 128 * 1024:
        raise ValueError("Procedural mesh leaves insufficient bounded room for retained occurrence envelopes")
    return result


def _candidate(source: dict, parameters: dict) -> dict:
    keys(parameters, {"candidate"})
    candidate = parameters["candidate"]
    check_seal(candidate)
    if (candidate.get("schema") != "ciw.operation-result.v1" or candidate.get("operation_id") != GENERATE
            or candidate.get("role") != "backend" or candidate.get("evidence_id") != source["evidence_id"]
            or candidate.get("run_id") != source["run_id"] or candidate.get("parameters") != {}
            or candidate.get("channel") != "program_declaration" or candidate.get("interval_s") != [0.0, 1.0]):
        raise ValueError("Procedural verifier candidate must bind the declared source and generator")
    validate_identity(candidate.get("result_id"), "result")
    validate_identity(candidate.get("execution_id"), "execution")
    validate_runtime("compiler", candidate["runtime"])
    validate_result(source_request(source), candidate["data"])
    return candidate


def _verify(source: dict, parameters: dict) -> dict:
    candidate = _candidate(source, parameters)
    request = source_request(source)
    return {"schema": "ciw.procedural-verification-payload.v1", "verification_id": new_identity("verification"),
            "candidate_result_id": candidate["result_id"], "candidate_execution_id": candidate["execution_id"],
            "candidate_record_digest": candidate["record_digest"], "source_evidence_id": source["evidence_id"],
            "report": verify_artifact(request, candidate["data"]), "authority": _authority(request)}


def operations() -> list[Operation]:
    return [Operation(GENERATE, "backend", _generate, lambda: runtime_identity("compiler")),
            Operation(VERIFY, "verification", _verify, lambda: runtime_identity("verifier"))]


def registry():
    from .operations.registry import default_registry
    result = default_registry()
    for operation in operations():
        result.register(operation)
    return result


def validate_payload(operation: str, data: dict, source: dict, parameters: dict, selection: dict) -> None:
    """Static contract validation. Retained strings activate no providers."""
    request = source_request(source)
    if selection.get("channel") != "program_declaration" or selection.get("interval_s") != [0.0, 1.0]:
        raise ValueError("Procedural operations require the full declaration selection")
    if operation == GENERATE:
        keys(parameters, set())
        validate_result(request, data)
    elif operation == VERIFY:
        candidate = _candidate(source, parameters)
        keys(data, {"schema", "verification_id", "candidate_result_id", "candidate_execution_id",
                    "candidate_record_digest", "source_evidence_id", "report", "authority"})
        validate_identity(data["verification_id"], "verification")
        if (data["schema"] != "ciw.procedural-verification-payload.v1" or data["authority"] != _authority(request)
                or data["source_evidence_id"] != source["evidence_id"]
                or data["candidate_result_id"] != candidate["result_id"]
                or data["candidate_execution_id"] != candidate["execution_id"]
                or data["candidate_record_digest"] != candidate["record_digest"]):
            raise ValueError("Procedural verification identity or authority binding differs")
        _validate_report(request, candidate["data"], data["report"])
    else:
        raise ValueError("Unsupported procedural operation")


def validate_result_dependencies(results: dict) -> None:
    identities = set()
    for result in results.values():
        if result.get("operation_id") not in {GENERATE, VERIFY}:
            continue
        validate_runtime("compiler" if result["operation_id"] == GENERATE else "verifier", result["runtime"])
        if result["operation_id"] != VERIFY:
            continue
        candidate = result["parameters"]["candidate"]
        if results.get(candidate["result_id"]) != candidate:
            raise ValueError("Procedural verification candidate differs from retained generator occurrence")
        identity = result["data"]["verification_id"]
        if identity in identities:
            raise ValueError("Duplicate procedural verification occurrence identity")
        identities.add(identity)


def validate_live_dependency(parameters: dict, retained: dict) -> None:
    keys(parameters, {"candidate"})
    candidate = parameters["candidate"]
    if type(candidate) is not dict or retained.get(candidate.get("result_id")) != candidate:
        raise ValueError("Procedural verification requires the actually retained candidate occurrence")


def _execute(session, operation: str, parameters: dict) -> dict:
    reply = session.handle({"protocol_version": 1, "request_id": "procedural-workload", "type": "operation.execute",
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
    candidate = _execute(session, GENERATE, {})
    verification = None
    if candidate["status"] == "completed":
        verification = _execute(session, VERIFY, {"candidate": candidate["result"]})
    if len((json.dumps(session._workspace(), indent=2, allow_nan=False) + "\n").encode()) > MAX_WORKSPACE_BYTES:
        raise ValueError("Procedural workspace exceeds the bounded 32 MiB budget")
    session.save_workspace(destination / "workspace.json")
    if verification is not None and verification["status"] == "completed":
        save_new(destination / "verification.json", verification["result"]["data"])
    result = inspect(destination)
    result["fresh_execution"] = True
    result["fresh_numerical_verification"] = verification is not None and verification["status"] == "completed"
    return result


def _regular_bytes(path: Path, limit: int) -> bytes:
    original = path.lstat()
    if not stat.S_ISREG(original.st_mode):
        raise ValueError("Procedural artifacts must be regular files without symlinks")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (original.st_dev, original.st_ino):
            raise ValueError("Procedural artifact changed to a nonregular file")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            raw = stream.read(limit + 1)
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if not raw or len(raw) > limit:
        raise ValueError("Procedural artifact is empty or exceeds its byte budget")
    return raw


def _snapshot(destination: Path) -> dict[str, dict]:
    from .session import loads_json
    if not stat.S_ISDIR(destination.lstat().st_mode):
        raise ValueError("Procedural bundle must be a directory without symlinks")
    paths = list(destination.iterdir())
    if not 3 <= len(paths) <= 9:
        raise ValueError("Unexpected procedural bundle artifact count")
    result = {}
    for path in paths:
        raw = _regular_bytes(path, MAX_WORKSPACE_BYTES if path.name == "workspace.json" else MAX_FILE_BYTES)
        result[path.name] = loads_json(raw.decode("utf-8"))
    if not {"workspace.json", "request.json"} <= result.keys():
        raise ValueError("Procedural bundle requires a retained request and workspace")
    return result


def _read(destination: Path):
    """Read each original artifact once; generic restore writes only to a tempdir."""
    from .session import Session
    destination = Path(destination)
    files = _snapshot(destination)
    workspace = files["workspace.json"]
    keys(workspace, {"workspace_version", "saved_at", "run", "selection", "results", "view_settings", "executions"})
    if workspace["workspace_version"] != 2 or workspace["view_settings"] != {}:
        raise ValueError("Procedural bundle requires the bounded recording-operation workspace")
    with tempfile.TemporaryDirectory(prefix="procedural-inspect-") as temporary:
        scratch = Path(temporary)
        snapshot = scratch / "snapshot.json"
        snapshot.write_text(json.dumps(files["workspace.json"], allow_nan=False), encoding="utf-8")
        session = Session.from_workspace(snapshot, scratch / "restored")
    request = source_request(session.run)
    retained_request = validate_request(files["request.json"])
    if digest(request) != digest(retained_request):
        raise ValueError("Retained procedural request differs from source evidence")
    expected = {"request.json", "workspace.json", session.recording_file}
    if files.get(session.recording_file) != session.run:
        raise ValueError("Retained procedural recording differs from workspace source")
    for collection, field in ((session.results, "result_id"), (session.executions, "execution_id")):
        for record in collection.values():
            name = record[field] + ".json"
            expected.add(name)
            if files.get(name) != record:
                raise ValueError("Retained procedural occurrence artifact differs from workspace")
    if any(record["operation_id"] not in {GENERATE, VERIFY} for record in session.executions.values()):
        raise ValueError("Procedural bundle contains an unrelated operation")
    for record in session.executions.values():
        if record["runtime"] is not None:
            validate_runtime("compiler" if record["operation_id"] == GENERATE else "verifier", record["runtime"])
    validate_result_dependencies(session.results)
    candidates = [result for result in session.results.values() if result["operation_id"] == GENERATE]
    verifications = [result for result in session.results.values() if result["operation_id"] == VERIFY]
    executions = list(session.executions.values())
    if len(executions) == 1 and executions[0]["operation_id"] == GENERATE and executions[0]["status"] == "refused":
        if session.results or set(files) != expected:
            raise ValueError("Refused procedural generator cannot retain results or receipts")
        return session, None, None
    if (len(executions) == 2 and len(candidates) == 1 and not verifications
            and sum(entry["operation_id"] == VERIFY and entry["status"] == "refused" for entry in executions) == 1):
        if len(session.results) != 1 or set(files) != expected:
            raise ValueError("Refused procedural verifier retains unexpected results or receipts")
        return session, candidates[0], None
    if len(candidates) != 1 or len(verifications) != 1 or len(session.results) != 2 or len(executions) != 2:
        raise ValueError("Procedural bundle requires one generator and one independent verification occurrence")
    candidate, verification = candidates[0], verifications[0]
    expected.add("verification.json")
    if "replay.json" in files:
        expected.add("replay.json")
    if set(files) != expected:
        raise ValueError("Procedural bundle contains missing or unexpected artifacts")
    if files["verification.json"] != verification["data"] or verification["parameters"]["candidate"] != candidate:
        raise ValueError("Retained procedural verification receipt or candidate binding differs")
    if "replay.json" in files:
        summary = _inspection_from_read(session, candidate, verification)
        _validate_replay_receipt(files["replay.json"], summary)
        session._procedural_replay = deepcopy(files["replay.json"])
    return session, candidate, verification


def _inspection_from_read(session, candidate: dict | None, verification: dict | None) -> dict:
    report = None if verification is None else verification["data"]["report"]
    artifact = None if candidate is None else candidate["data"]
    kind = None if artifact is None else ("mesh" if "mesh" in artifact else "texture")
    mesh_digest = digest(artifact["mesh"]) if kind == "mesh" else None
    image_digest = (digest({name: artifact["image"][name] for name in
                           ("width", "height", "rgba_base64", "encoding")}) if kind == "texture" else None)
    summary = {"schema": "ciw.procedural-inspection.v1", "status": "LOCAL" if report and report["status"] == "PASS" else "REFUSE",
            "verification_status": "not_verified" if report is None else report["status"],
            "evidence_id": session.run["evidence_id"],
            "result_id": None if candidate is None else candidate["result_id"],
            "execution_id": None if candidate is None else candidate["execution_id"],
            "verification_id": None if verification is None else verification["data"]["verification_id"],
            "verification_execution_id": None if verification is None else verification["execution_id"],
            "artifact_kind": kind, "mesh_digest": mesh_digest, "image_digest": image_digest,
            "output_digest": mesh_digest if kind == "mesh" else image_digest,
            "png_digest": artifact["image"]["png_sha256"] if kind == "texture" else None,
            "artifact_digest": None if candidate is None else candidate["data"]["record_digest"],
            "metrics": {} if report is None else deepcopy(report["metrics"]),
            "checks": [] if report is None else deepcopy(report["checks"]),
            "executions": [{key: deepcopy(value) for key, value in entry.items() if key != "parameters"}
                           for entry in session.executions.values()],
            "fresh_execution": False, "fresh_numerical_verification": False, "authority": _authority(source_request(session.run))}
    if hasattr(session, "_procedural_replay"):
        summary["replay"] = deepcopy(session._procedural_replay)
    return summary


def inspect(destination: Path) -> dict:
    return _inspection_from_read(*_read(destination))


def read_bundle(destination: Path) -> dict:
    """One static snapshot for viewer/server consumers; no provider invocation."""
    session, candidate, verification = _read(destination)
    return {"request": source_request(session.run),
            "summary": _inspection_from_read(session, candidate, verification),
            "artifact": None if candidate is None else deepcopy(candidate["data"]),
            "report": None if verification is None else deepcopy(verification["data"]["report"])}


def _verify_read(session, candidate: dict | None, verification: dict | None) -> dict:
    result = _inspection_from_read(session, candidate, verification)
    if verification is None:
        return result
    fresh = verify_artifact(source_request(session.run), candidate["data"])
    if fresh != verification["data"]["report"]:
        raise ValueError("Fresh independent procedural verification differs from retained report")
    result["fresh_numerical_verification"] = True
    result["recomputed_report_digest"] = fresh["record_digest"]
    result["recomputed_with_runtime"] = runtime_identity("verifier")
    return result


def verify_retained(destination: Path) -> dict:
    return _verify_read(*_read(destination))


def replay(destination: Path, output: Path) -> dict:
    session, candidate, verification = _read(destination)
    checked = _verify_read(session, candidate, verification)
    if checked["status"] != "LOCAL":
        raise ValueError("Only a freshly qualified procedural artifact can be replayed")
    repeated = run(source_request(session.run), output)
    receipt = _make_replay_receipt(checked, repeated)
    # A comparison is a sealed declaration, not a new verification occurrence.
    # The source archive's authenticity is not conferred by recording its IDs.
    if repeated["verification_id"] is not None:
        save_new(Path(output) / "replay.json", receipt)
    repeated["replay"] = receipt
    if receipt["status"] != "PASS":
        raise ValueError("Procedural replay numerical artifact or occurrence comparison failed")
    return repeated


_BASE_REPLAY_FIELDS = ("evidence_id", "result_id", "execution_id", "verification_id", "verification_execution_id",
                       "mesh_digest", "artifact_digest")
_OUTPUT_REPLAY_FIELDS = ("artifact_kind", "output_digest", "image_digest", "png_digest")
_REPLAY_FIELDS = _BASE_REPLAY_FIELDS + _OUTPUT_REPLAY_FIELDS


def _make_replay_receipt(source: dict, candidate: dict, *, extended: bool = True) -> dict:
    fields = _REPLAY_FIELDS if extended else _BASE_REPLAY_FIELDS
    record = {"schema": "ciw.procedural-replay-comparison.v1",
              **{"source_" + name: source[name] for name in fields},
              **{"candidate_" + name: candidate[name] for name in fields},
              "evidence_equal": source["evidence_id"] == candidate["evidence_id"],
              "mesh_digest_equal": source["mesh_digest"] == candidate["mesh_digest"],
              "artifact_digest_equal": source["artifact_digest"] == candidate["artifact_digest"],
              "fresh_occurrences": all(source[name] != candidate[name] for name in
                                       ("result_id", "execution_id", "verification_id", "verification_execution_id")),
              "authority": {**candidate["authority"], "source_archive_authenticity": "not_established"}}
    if extended:
        record["output_digest_equal"] = (source["output_digest"] == candidate["output_digest"]
                                         and source["artifact_kind"] == candidate["artifact_kind"])
    record["status"] = "PASS" if candidate["status"] == "LOCAL" and all(record[name] for name in
                        ("evidence_equal", "mesh_digest_equal", "artifact_digest_equal", "fresh_occurrences")) and (
                        not extended or record["output_digest_equal"]) else "FAIL"
    return seal(record)


def _validate_replay_receipt(receipt: dict, candidate: dict) -> None:
    extended = "candidate_output_digest" in receipt
    fields = _REPLAY_FIELDS if extended else _BASE_REPLAY_FIELDS
    keys(receipt, {"schema", "record_digest", "status", "authority", "evidence_equal", "mesh_digest_equal",
                   "artifact_digest_equal", "fresh_occurrences"} |
                   ({"output_digest_equal"} if extended else set()) |
                   {prefix + name for prefix in ("source_", "candidate_") for name in fields})
    check_seal(receipt)
    if (receipt["schema"] != "ciw.procedural-replay-comparison.v1"
            or receipt["authority"] != {**candidate["authority"], "source_archive_authenticity": "not_established"}):
        raise ValueError("Procedural replay comparison schema or authority differs")
    source = {name: receipt["source_" + name] for name in fields}
    for name in ("evidence_id", "artifact_digest"):
        content_ref(source[name])
    if source["mesh_digest"] is not None:
        content_ref(source["mesh_digest"])
    if extended:
        if source["artifact_kind"] not in {"mesh", "texture"}:
            raise ValueError("Unsupported retained replay source representation")
        content_ref(source["output_digest"])
        for name in ("image_digest", "png_digest"):
            if source[name] is not None:
                content_ref(source[name])
        if ((source["artifact_kind"] == "mesh" and
                (source["mesh_digest"] != source["output_digest"] or source["image_digest"] is not None or source["png_digest"] is not None))
                or (source["artifact_kind"] == "texture" and
                    (source["mesh_digest"] is not None or source["image_digest"] != source["output_digest"] or source["png_digest"] is None))):
            raise ValueError("Retained replay source output identities contradict the representation")
    elif source["mesh_digest"] is None or candidate["artifact_kind"] != "mesh":
        raise ValueError("Legacy replay comparisons require a mesh representation")
    for name in ("result_id", "execution_id", "verification_id", "verification_execution_id"):
        validate_identity(source[name], "execution" if name == "verification_execution_id" else name.removesuffix("_id"))
    if any(receipt["candidate_" + name] != candidate[name] for name in fields):
        raise ValueError("Procedural replay comparison candidate binding differs")
    expected = _make_replay_receipt(source, candidate, extended=extended)
    if receipt != expected:
        raise ValueError("Procedural replay comparison claims differ from declared identity and artifact pairs")


def _export_bindings(session, candidate, checked) -> dict:
    return {"source_evidence_id": session.run["evidence_id"], "source_result_id": candidate["result_id"],
            "source_execution_id": candidate["execution_id"], "source_record_digest": candidate["record_digest"],
            "verification_id": checked["verification_id"], "mesh_digest": checked["mesh_digest"],
            "artifact_kind": checked["artifact_kind"], "output_digest": checked["output_digest"],
            "image_digest": checked["image_digest"], "png_digest": checked["png_digest"],
            "artifact_digest": checked["artifact_digest"], "recomputed_report_digest": checked["recomputed_report_digest"],
            "recomputed_with_runtime": checked["recomputed_with_runtime"]}


def _absent(path: Path) -> None:
    if path.exists() or path.is_symlink():
        raise FileExistsError("Export destination already exists: " + str(path))


def _obj_bytes(mesh: dict) -> bytes:
    raw = ("# NET declared numerical surface; physical suitability is unestablished\n" +
           "".join("v " + " ".join(format(float(value), ".17g") for value in vertex) + "\n" for vertex in mesh["vertices"]) +
           "".join("f " + " ".join(str(index + 1) for index in face) + "\n" for face in mesh["triangles"])).encode("ascii")
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("OBJ exceeds the bounded 8 MiB export budget")
    return raw


def _reopen_obj(staged: Path, mesh: dict) -> None:
    """Independent fixed-profile parser checks the bytes actually written."""
    raw = _regular_bytes(staged, MAX_FILE_BYTES)
    vertices, triangles = [], []
    for index, line in enumerate(raw.decode("ascii").splitlines()):
        if index == 0 and line == "# NET declared numerical surface; physical suitability is unestablished":
            continue
        tokens = line.split()
        if len(tokens) != 4:
            raise ValueError("Reopened OBJ contains a malformed bounded record")
        if tokens[0] == "v" and not triangles:
            point = [float(value) for value in tokens[1:]]
            if not all(np.isfinite(value) for value in point):
                raise ValueError("Reopened OBJ has a nonfinite coordinate")
            vertices.append(point)
        elif tokens[0] == "f":
            face = [int(value) - 1 for value in tokens[1:]]
            if any(index < 0 or index >= len(vertices) for index in face):
                raise ValueError("Reopened OBJ references an absent vertex")
            triangles.append(face)
        else:
            raise ValueError("Reopened OBJ contains unsupported records")
    if vertices != mesh["vertices"] or triangles != mesh["triangles"]:
        raise ValueError("Reopened OBJ differs from the retained mesh coordinates or connectivity")


def _reopen_png(staged: Path, image: dict) -> None:
    from .procedural_representation_verification import decode_texture_png
    raw = _regular_bytes(staged, MAX_FILE_BYTES)
    rgba = decode_texture_png(raw, image["width"], image["height"])
    if (rgba != base64.b64decode(image["rgba_base64"], validate=True)
            or "sha256:" + sha256(raw).hexdigest() != image["png_sha256"]):
        raise ValueError("Reopened PNG differs from retained RGBA bytes or PNG identity")


def _representation_bytes_and_receipt(session, candidate, checked):
    artifact = candidate["data"]
    bindings = _export_bindings(session, candidate, checked)
    if checked["artifact_kind"] == "mesh":
        mesh = artifact["mesh"]
        raw = _obj_bytes(mesh)
        receipt = {"schema": "ciw.procedural-obj-export.v1", "format": "obj", "units": mesh["units"], "frame": mesh["frame"],
                   "vertex_count": len(mesh["vertices"]), "triangle_count": len(mesh["triangles"])}
        reopen = lambda path: _reopen_obj(path, mesh)
    else:
        image = artifact["image"]
        raw = base64.b64decode(image["png_base64"], validate=True)
        receipt = {"schema": "ciw.procedural-png-export.v1", "format": "png",
                   "width": image["width"], "height": image["height"], "encoding": deepcopy(image["encoding"]),
                   "units": source_request(session.run)["domain"]["units"],
                   "frame": source_request(session.run)["domain"]["frame"]}
        reopen = lambda path: _reopen_png(path, image)
    if not raw or len(raw) > MAX_FILE_BYTES:
        raise ValueError("Representation export exceeds the bounded 8 MiB budget")
    receipt.update(output_sha256="sha256:" + sha256(raw).hexdigest(), checks=deepcopy(checked["checks"]),
                   metrics=deepcopy(checked["metrics"]), claims=deepcopy(artifact["claims"]),
                   authority=deepcopy(checked["authority"]), independent_reopen="PASS", **bindings)
    return raw, receipt, reopen


def _export_representation(session, candidate, checked, output: Path, kind: str) -> dict:
    if checked["status"] != "LOCAL" or checked["artifact_kind"] != kind:
        raise ValueError("Only a freshly qualified LOCAL " + kind + " artifact can use this export")
    output = Path(output)
    sidecar = Path(str(output) + ".json")
    _absent(output)
    _absent(sidecar)
    raw, receipt, reopen = _representation_bytes_and_receipt(session, candidate, checked)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".procedural-export-", dir=output.parent) as temporary:
        staged = Path(temporary) / ("artifact." + receipt["format"])
        staged.write_bytes(raw)
        reopen(staged)
        os.link(staged, output)
        try:
            save_new(sidecar, receipt)
        except BaseException:
            # Remove only the just-published same-inode object; never another file.
            try:
                if output.stat().st_ino == staged.stat().st_ino and output.stat().st_dev == staged.stat().st_dev:
                    output.unlink()
            except OSError:
                pass
            raise
    return {"status": "exported", "file": str(output), "sidecar": str(sidecar),
            "output_sha256": receipt["output_sha256"], "independent_reopen": "PASS",
            "authority": deepcopy(checked["authority"]), **_export_bindings(session, candidate, checked)}


def export_obj(destination: Path, output: Path) -> dict:
    session, candidate, verification = _read(destination)
    return _export_representation(session, candidate, _verify_read(session, candidate, verification), output, "mesh")


def export_png(destination: Path, output: Path) -> dict:
    session, candidate, verification = _read(destination)
    return _export_representation(session, candidate, _verify_read(session, candidate, verification), output, "texture")


def export_manifest(destination: Path, output: Path) -> dict:
    """One retained snapshot; private conversion/reopen followed by manifest only."""
    session, candidate, verification = _read(destination)
    checked = _verify_read(session, candidate, verification)
    if checked["status"] != "LOCAL":
        raise ValueError("Only a freshly qualified LOCAL artifact can export a conversion manifest")
    raw, receipt, reopen = _representation_bytes_and_receipt(session, candidate, checked)
    with tempfile.TemporaryDirectory(prefix="procedural-manifest-") as temporary:
        staged = Path(temporary) / ("artifact." + receipt["format"])
        staged.write_bytes(raw)
        reopen(staged)
    receipt["artifact_publication"] = "not_performed"
    save_new(output, receipt)
    return {"status": "exported", "file": str(output), "format": receipt["format"],
            "output_sha256": receipt["output_sha256"], "independent_reopen": "PASS",
            "authority": deepcopy(checked["authority"]), **_export_bindings(session, candidate, checked)}


def _save_bounded_export_json(output: Path, payload: dict) -> None:
    """Schema-validated image data has longer bounded base64 strings than controls."""
    raw = (json.dumps(payload, indent=2, allow_nan=False) + "\n").encode()
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("Procedural JSON export exceeds the bounded 8 MiB budget")
    output = Path(output)
    _absent(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".procedural-json-", dir=output.parent) as temporary:
        staged = Path(temporary) / "artifact.json"
        with staged.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(staged, output)


def export_json(destination: Path, output: Path) -> dict:
    session, candidate, verification = _read(destination)
    checked = _verify_read(session, candidate, verification)
    if checked["status"] != "LOCAL":
        raise ValueError("Only a freshly qualified LOCAL procedural artifact can be exported")
    bindings = _export_bindings(session, candidate, checked)
    payload = {"schema": "ciw.procedural-json-export.v1", "request": source_request(session.run),
               "artifact": deepcopy(candidate["data"]), "verification": deepcopy(verification["data"]["report"]),
               "authority": deepcopy(checked["authority"]), **bindings}
    _save_bounded_export_json(output, payload)
    return {"status": "exported", "file": str(output), "authority": deepcopy(checked["authority"]), **bindings}
