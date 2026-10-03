"""Retained DSP orchestration; numerical kernels remain in the MPL STFE instrument.

Raw signal records are declarations inside a normal run.v1 envelope. This permits
quality inspection of broken timestamps without weakening the admitted run grid.
Inspection is structural/source validation; replay is a separate numerical check.
"""
from __future__ import annotations

from copy import deepcopy
import json
import math
import os
from pathlib import Path
import platform
import re
import tempfile
import uuid

from .adapters.protocol import InstrumentManifest
from .control_contracts import keys as exact_keys
from .core.identities import content_identity, evidence_id, new_identity, validate_evidence_identity
from .core.records import finite_tree, validate_run_structure
from .operations.registry import Operation, OperationRegistry

OPERATION = "signal.pipeline.v1"
MAX_BYTES = 48 * 1024 * 1024


def keys(value, expected, required=None):
    if required is None:
        return exact_keys(value, expected)
    if type(value) is not dict or not required <= value.keys() <= expected:
        raise ValueError("Unexpected DSP contract fields")


def read_bounded(path):
    from .session import loads_json
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError("Require a bounded regular DSP bundle file")
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("DSP document exceeds byte budget or is empty")
    return loads_json(raw.decode("utf-8"))


def save_new(path, value):
    """Create-only DSP documents with the DSP byte budget, not control-file limits."""
    raw = (json.dumps(value, indent=2, allow_nan=False) + "\n").encode("utf-8")
    if len(raw) > MAX_BYTES:
        raise ValueError("DSP document exceeds byte budget")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".dsp-", dir=path.parent) as directory:
        staged = Path(directory) / "record.json"
        with staged.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(staged, path)


def _request(request):
    """Structural ingress independent of optional numerical packages."""
    keys(request, {"schema", "signals", "steps", "provenance", "ground_truth"},
         {"schema", "signals", "steps"})
    finite_tree(request, "DSP request")
    if request["schema"] != "stfe.dsp-pipeline.v1":
        raise ValueError("Unsupported DSP pipeline declaration")
    if type(request["signals"]) is not dict or not 1 <= len(request["signals"]) <= 16:
        raise ValueError("Require 1..16 source signals")
    if type(request["steps"]) is not list or not 1 <= len(request["steps"]) <= 64:
        raise ValueError("Require 1..64 processing stages")
    available = set()
    for name, signal in request["signals"].items():
        if type(name) is not str or not name.strip():
            raise ValueError("Signal names must be nonempty text")
        _signal(signal)
        available.add(name)
    for step in request["steps"]:
        keys(step, {"id", "input", "method", "parameters", "reference"}, {"id", "input", "method", "parameters"})
        if type(step["id"]) is not str or not step["id"].strip() or step["id"] in available:
            raise ValueError("Processing stage identities must be unique")
        if step["input"] not in available or ("reference" in step and step["reference"] not in available):
            raise ValueError("Require a retained source or earlier stage reference")
        if type(step["method"]) is not str or type(step["parameters"]) is not dict:
            raise ValueError("Require a declared DSP method and parameters")
        available.add(step["id"])
    for optional in ("provenance", "ground_truth"):
        if optional in request and type(request[optional]) is not dict:
            raise ValueError("DSP provenance/ground truth must be objects")
    return deepcopy(request)


def _signal(signal):
    keys(signal, {"source_id", "unit", "clock_id", "sample_rate_hz", "time_s", "values"})
    for field in ("source_id", "unit", "clock_id"):
        if type(signal[field]) is not str or not signal[field].strip():
            raise ValueError("Require signal identity, units and clock")
    rate = signal["sample_rate_hz"]
    if type(rate) not in (int, float) or not math.isfinite(rate) or rate <= 0:
        raise ValueError("Require a finite positive declared sample rate")
    times, values = signal["time_s"], signal["values"]
    if type(times) is not list or type(values) is not list or not 1 <= len(times) <= 32768 or len(times) != len(values):
        raise ValueError("Require equal bounded time and sample arrays")
    if any(type(t) not in (int, float) or not math.isfinite(t) for t in times):
        raise ValueError("Timestamps must be finite numbers")
    if any(v is not None and (type(v) not in (int, float) or not math.isfinite(v)) for v in values):
        raise ValueError("Samples must be finite numbers or explicit nulls")


def make_source(request):
    request = _request(request)
    manifest = InstrumentManifest(instrument_id="stfe.dsp-pipeline-evidence.v1", role="signal_declaration",
        units={"declaration": "1"}, frames=("signal-declaration",),
        sampling={"kind": "one_declaration", "raw_channel_timing": "retained_independently"},
        supported_operations=(OPERATION,))
    source = {"run_schema": "run.v1", "run_id": "run-dsp-" + content_identity(request)[7:23],
        "instrument": manifest.instrument_id,
        "metadata": {"duration_s": 1.0, "sample_count": 1, "sample_rate_hz": None,
            "coordinate_frame": "signal-declaration", "manifest": manifest.to_dict(), "dsp_request": request,
            "provenance": {"source": "retained DSP declaration", "generator": "ciw.dsp_pipeline.make_source"}},
        "time_s": [0.0], "channels": {"declaration": {"unit": "1", "values": [1.0]}}, "render": {}}
    source["evidence_id"] = evidence_id(source)
    return source


def source_request(source):
    validate_run_structure(source)
    validate_evidence_identity(source)
    request = _request(source["metadata"]["dsp_request"])
    if content_identity(source) != content_identity(make_source(request)):
        raise ValueError("DSP source differs from its exact retained declaration")
    return request


def runtime_identity():
    import numpy
    import scipy
    from stfe_dsp import dsp, pipeline, pump
    from stfe import window
    from . import dsp_pipeline_contract
    modules = [dsp, pipeline, pump, window, dsp_pipeline_contract]
    files = {Path(module.__file__).name: content_identity(Path(module.__file__).read_text(encoding="utf8").replace("\r\n", "\n"))
             for module in modules}
    files["ciw.dsp_pipeline.py"] = content_identity(Path(__file__).read_text(encoding="utf8").replace("\r\n", "\n"))
    return {"provider": "stfe_dsp.dsp", "version": "1", "source_files": files,
            "python": platform.python_version(), "numpy": numpy.__version__, "scipy": scipy.__version__,
            "platform": platform.platform(), "precision": "binary64",
            "scope": "bounded numerical processing; no physical qualification"}


def _execute(source, parameters):
    keys(parameters, set())
    from stfe_dsp.pipeline import run_pipeline
    return run_pipeline(source_request(source))


def registry():
    value = OperationRegistry()
    value.register(Operation(OPERATION, "backend", _execute, runtime_identity))
    return value


def validate_payload(operation, data, source, parameters, selection):
    """Source/contract checking only; never execute the numerical provider."""
    from .dsp_pipeline_contract import validate_result
    if operation != OPERATION:
        raise ValueError("Wrong DSP operation")
    keys(parameters, set())
    try:
        validate_result(source_request(source), data)
    except (KeyError, TypeError, OverflowError) as exc:
        raise ValueError("Malformed retained DSP contract") from exc


def run(request, destination):
    from .session import Session
    from stfe_dsp.pipeline import validate_request
    request = validate_request(_request(request))
    source = make_source(request)
    runtime_identity()  # Optional dependency failures occur before bundle creation.
    destination = Path(destination)
    if destination.is_symlink():
        raise ValueError("Output cannot be a symlink")
    destination.mkdir(parents=True, exist_ok=False)
    save_new(destination / "request.json", request)
    session = Session(source, destination, operations=registry())
    try:
        response = session.handle({"protocol_version": 1, "request_id": uuid.uuid4().hex,
            "type": "operation.execute", "payload": {"operation_id": OPERATION, "parameters": {}}})
        if response["type"] != "response":
            raise ValueError(response["payload"]["message"])
    finally:
        session.save_workspace(destination / "workspace.json")
    return inspect(destination)


def _read(destination):
    from .session import Session
    destination = Path(destination)
    value = read_bounded(destination / "workspace.json")
    with tempfile.TemporaryDirectory(prefix="dsp-inspect-") as temporary:
        root = Path(temporary)
        save_new(root / "workspace.json", value)
        session = Session.from_workspace(root / "workspace.json", root / "reopened")
    request = source_request(session.run)
    if content_identity(read_bounded(destination / "request.json")) != content_identity(request):
        raise ValueError("DSP request sidecar differs from source evidence")
    if len(session.executions) != 1:
        raise ValueError("A DSP bundle must retain exactly one pipeline execution")
    occurrence = next(iter(session.executions.values()))
    if occurrence["operation_id"] != OPERATION or occurrence["parameters"] != {}:
        raise ValueError("Unexpected DSP operation")
    if len(session.results) != (1 if occurrence["status"] == "completed" else 0):
        raise ValueError("Unexpected DSP results")
    return session, request, occurrence, next(iter(session.results.values()), None)


def inspect(destination):
    session, request, occurrence, result = _read(destination)
    return {"schema": "ciw.dsp-pipeline-inspection.v1", "status": occurrence["status"],
        "evidence_id": session.run["evidence_id"], "operation_id": OPERATION,
        "execution_id": occurrence["execution_id"], "result_id": occurrence["result_id"],
        "stage_count": len(result["data"]["stages"]) if result else 0,
        "diagnostics": deepcopy(result["data"].get("diagnostics")) if result else None,
        "refusal": occurrence.get("refusal"), "fresh_execution": False,
        "numerical_verification": "not_performed", "state_admission": "not_performed"}


def _compare(left, right, atol, rtol):
    """Explicit finite numerical tolerance; all nonnumeric structure exact."""
    failures = []
    counts = {"numbers": 0, "max_absolute_error": 0.0}
    def walk(a, b, path):
        if type(a) in (int, float) and type(b) in (int, float):
            counts["numbers"] += 1
            delta = abs(a - b)
            counts["max_absolute_error"] = max(counts["max_absolute_error"], delta)
            if delta <= atol + rtol * abs(a):
                return
        elif type(a) is dict and type(b) is dict and a.keys() == b.keys():
            for key in a:
                # Content references are integrity-bound independently for each run.
                # Derived floating point content hashes may differ within tolerance.
                candidate_path = path + "." + key
                bound_path = re.fullmatch(r"payload\.stages\[\d+\]\.result\.(?:input_ref|output\.source_id|contract\.source_support\.(?:input_ref|reference_input_ref))", candidate_path)
                if bound_path and isinstance(a[key], str) and a[key].startswith(("sha256:", "stfe-derived:")):
                    continue
                walk(a[key], b[key], path + "." + key)
            return
        elif type(a) is list and type(b) is list and len(a) == len(b):
            for i, (x, y) in enumerate(zip(a, b)):
                walk(x, y, path + "[" + str(i) + "]")
            return
        elif type(a) is type(b) and a == b:
            return
        if len(failures) < 20:
            failures.append(path)
    walk(left, right, "payload")
    return {"status": "FAIL" if failures else "PASS", "mismatch_paths": failures, **counts}


def replay(destination, output, *, atol=1e-10, rtol=1e-9):
    for tolerance in (atol, rtol):
        if type(tolerance) not in (int, float) or not math.isfinite(tolerance) or tolerance < 0:
            raise ValueError("Replay tolerances must be finite nonnegative numbers")
    source_session, request, old_execution, old = _read(destination)
    if old is None:
        raise ValueError("Numerical replay requires a completed original execution")
    run(request, output)
    _, _, new_execution, new = _read(output)
    comparison = _compare(old["data"], new["data"], atol, rtol) if new else {
        "status": "FAIL", "mismatch_paths": ["replay_refused"], "numbers": 0, "max_absolute_error": 0.0}
    report = {"schema": "ciw.dsp-pipeline-replay.v1", "status": comparison["status"],
        "verification_id": new_identity("verification"), "source_evidence_id": source_session.run["evidence_id"],
        "original_execution_id": old_execution["execution_id"], "replay_execution_id": new_execution["execution_id"],
        "original_result_id": old["result_id"], "replay_result_id": new["result_id"] if new else None,
        "original_record_digest": old["record_digest"], "replay_record_digest": new["record_digest"] if new else None,
        "runtime_match": old_execution["runtime"] == new_execution["runtime"],
        "atol": atol, "rtol": rtol, "comparison": comparison,
        "scope": "fresh numerical replay of retained payload; not an independent algorithm or physical validation",
        "state_admission": "not_performed", "physical_validation": "not_performed"}
    save_new(Path(output) / "replay-verification.json", report)
    return report
