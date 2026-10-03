# SPDX-License-Identifier: AGPL-3.0-or-later
"""Optional CSR micro-tools on the existing NET registry, Session and subprocess seam.

This module validates/retains declarations and results. CSR owns the mathematics.
Inspection never imports CSR or binds executable paths from a saved workspace.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
from decimal import Decimal
import json
import math
from pathlib import Path
import sys
import tempfile
import threading
import uuid

from .adapters.protocol import InstrumentManifest
from .adapters.subprocess import PinnedSubprocessAdapter
from .control_plane import CapabilityRegistry, Port
from .core.covariance import _validate_matrix
from .operations.registry import Operation
from .operations.schemas import register_payload_validator
from .session import Session, unique_object_pairs

OPERATIONS = ("csr.pose-propagate.v1", "csr.error-box.v1", "csr.covariance-propagate.v1")
SCHEMA = "csr.microtool-result.v1"
MODULE = "geodesic_testbed.microtools"
MODEL = "constant-curvature-transverse-jacobi.v1"
SCOPE = "first_order_at_supplied_arclengths_only"
CONTEXT = "investigation_context_only_not_computational_input"
_PROVIDER = "org.notationsystems.csr.microtools"
_registered = False
_lock = threading.Lock()


def _keys(value, expected):
    if type(value) is not dict or set(value) != set(expected):
        raise ValueError("Unexpected or missing micro-tool fields")


def _number(value, *, input_value=True):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("Require finite JSON numbers, not booleans or numeric strings")
    if input_value and (abs(value) > 1e100 or (value != 0 and abs(value) < 1e-100)):
        raise ValueError("Input is outside the micro-tool numeric profile")
    return value


def _shape(value, shape, *, input_value=True):
    if not shape:
        return _number(value, input_value=input_value)
    if type(value) is not list or len(value) != shape[0]:
        raise ValueError("Micro-tool array shape mismatch")
    for item in value:
        _shape(item, shape[1:], input_value=input_value)
    return value


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def validate_request(operation_id: str, request: dict) -> dict:
    if operation_id not in OPERATIONS:
        raise ValueError("Unsupported micro-tool operation")
    extras = {OPERATIONS[0]: {"initial_error"}, OPERATIONS[1]: {"initial_bounds", "tolerances"},
              OPERATIONS[2]: {"covariance"}}[operation_id]
    _keys(request, {"arc_length", "curvature", "length_unit", "frame"} | extras)
    if request["length_unit"] not in ("m", "cm", "mm"):
        raise ValueError("Declare m, cm or mm; no implicit conversions")
    if (type(request["frame"]) is not str or not request["frame"].strip()
            or len(request["frame"]) > 256):
        raise ValueError("Require a bounded explicit frame")
    grid = request["arc_length"]
    if type(grid) is not list or not 1 <= len(grid) <= 512:
        raise ValueError("Require 1..512 arclength samples")
    _shape(grid, (len(grid),))
    if grid[0] < 0 or grid[-1] > 1e6 or any(b <= a for a, b in zip(grid, grid[1:])):
        raise ValueError("Require increasing, nonnegative, bounded arclength")
    k = _number(request["curvature"])
    if (k != 0 and not 1e-12 <= abs(k) <= 1e6) or math.sqrt(abs(k)) * grid[-1] > 4:
        raise ValueError("Curvature/arclength is outside the numerical profile")
    for key in extras:
        _shape(request[key], (2, 2) if key == "covariance" else (2,))
        if key in ("initial_bounds", "tolerances") and min(request[key]) < 0:
            raise ValueError("Bounds and tolerances must be nonnegative")
    # This is a wire/covariance eligibility check, not propagation or covariance repair.
    if "covariance" in extras:
        _validate_matrix(request["covariance"], 2)
    envelope = {"schema": "ciw.adapter-request.v1", "operation_id": operation_id,
                "inputs": request}
    if len(json.dumps(envelope, allow_nan=False).encode()) > 65536:
        raise ValueError("Request exceeds provider byte budget")
    return deepcopy(request)


def validate_result(operation_id: str, data: dict, run: dict, parameters: dict,
                    selection: dict) -> None:
    """Provider-free structural and declaration consistency; not a solver rerun."""
    _keys(parameters, {"request", "recording_role"})
    if parameters["recording_role"] != CONTEXT:
        raise ValueError("Recording cannot be reclassified as this tool's input evidence")
    request = validate_request(operation_id, parameters["request"])
    _keys(data, {"schema", "operation_id", "request", "model", "coordinate", "basis", "units",
                 "scope", "transfer_matrices", "values", "tolerance_check", "verification_id",
                 "verification_status"})
    if (data["schema"] != SCHEMA or data["operation_id"] != operation_id
            or _json(data["request"]) != _json(request) or data["model"] != MODEL
            or data["coordinate"] != "arc_length" or data["basis"] != ["lateral", "heading"]
            or data["units"] != [request["length_unit"], "rad"] or data["scope"] != SCOPE
            or data["verification_id"] is not None or data["verification_status"] != "not_verified"):
        raise ValueError("Micro-tool identity, source, units, scope or authority mismatch")
    n = len(request["arc_length"])
    _shape(data["transfer_matrices"], (n, 2, 2), input_value=False)
    shape = (n, 2, 2) if operation_id == OPERATIONS[2] else (n, 2)
    _shape(data["values"], shape, input_value=False)
    if operation_id == OPERATIONS[2]:
        for matrix in data["values"]:
            _validate_matrix(matrix, 2)
    if operation_id == OPERATIONS[1]:
        if any(min(row) < 0 for row in data["values"]):
            raise ValueError("Negative deterministic bound")
        limits = request["tolerances"]
        excess = [[row[i] - limits[i] for i in range(2)] for row in data["values"]]
        passed = [all(value <= 0 for value in row) for row in excess]
        expected = {"status": "PASS" if all(passed) else "FAIL", "sample_pass": passed,
                    "maximum_excess": [max(row[i] for row in excess) for i in range(2)]}
        # Canonical JSON equality also refuses integers standing in for booleans.
        if _json(data["tolerance_check"]) != _json(expected):
            raise ValueError("Retained tolerance verdict disagrees with retained values")
    elif data["tolerance_check"] is not None:
        raise ValueError("Only the error-box operation has a declared tolerance check")


def register_readers() -> None:
    global _registered
    with _lock:
        if not _registered:
            for operation_id in OPERATIONS:
                register_payload_validator(operation_id, validate_result)
            _registered = True


def register_csr(registry: CapabilityRegistry, adapter: PinnedSubprocessAdapter) -> None:
    """Attach an explicitly supplied trusted adapter; discovery never calls this."""
    register_readers()
    runtime = adapter.runtime_identity()
    if runtime.get("module") != MODULE:
        raise ValueError("The CSR micro-tool module binding must be explicit")
    manifest = InstrumentManifest(
        instrument_id=_PROVIDER, role="backend", inputs=("csr.microtool-request.v1",),
        outputs=(SCHEMA,), supported_operations=OPERATIONS,
        units={"lateral": "caller_declared_length", "heading": "rad"},
        sampling={"coordinate": "arc_length", "max_samples": 512},
        determinism={"claim": "same-runtime reproduction must be explicitly executed"})
    registry.advertise(manifest, runtime=runtime,
        capabilities={op: ["geometry.surface_path", op.split(".")[1]] for op in OPERATIONS},
        outputs={op: {"response": {"type": Port(SCHEMA).to_dict(), "path": ["data"]}}
                 for op in OPERATIONS})

    def operation(op):
        def execute(_run, parameters):
            _keys(parameters, {"request", "recording_role"})
            if parameters["recording_role"] != CONTEXT:
                raise ValueError("Require explicit recording-context-only semantics")
            request = validate_request(op, parameters["request"])
            return adapter.invoke(op, request)
        return Operation(op, "backend", execute, adapter.runtime_identity)
    for op in OPERATIONS:
        registry.bind(operation(op))


def bind_csr(root: Path, revision: str, *, python: str = sys.executable) -> CapabilityRegistry:
    adapter = PinnedSubprocessAdapter(root, revision, MODULE, python_executable=python,
                                      timeout_seconds=30, max_output_bytes=1024 * 1024)
    registry = CapabilityRegistry()
    register_csr(registry, adapter)
    return registry


def catalog() -> dict:
    return {"schema": "ciw.microtool-catalog.v1", "authorizes_execution": False,
            "tools": [{"name": name, "operation_id": op, "capability": "geometry.surface_path",
                       "provider": _PROVIDER, "binding": "explicit_csr_checkout_required",
                       "implemented": True, "scope": SCOPE}
                      for name, op in zip(("Surface pose error", "Surface tolerance box",
                                           "Surface covariance"), OPERATIONS)]}


def _load(path: Path, limit: int):
    def floating(text):
        value = float(text)
        if not math.isfinite(value) or (value == 0 and Decimal(text) != 0):
            raise ValueError("Nonfinite or underflowed JSON number")
        return value
    def constant(_):
        raise ValueError("Nonfinite JSON constant")
    with Path(path).open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Input exceeds byte budget")
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object_pairs,
                       parse_float=floating, parse_constant=constant)
    return value, raw


@contextmanager
def _workspace(path: Path):
    register_readers()
    _, raw = _load(path, 8 * 1024 * 1024)
    with tempfile.TemporaryDirectory(prefix="ciw-microtools-") as tmp:
        frozen = Path(tmp) / "source.json"
        frozen.write_bytes(raw)
        reader = Session.from_workspace(frozen, Path(tmp) / "reader")
        yield reader, frozen


def inspect(workspace: Path) -> dict:
    with _workspace(workspace) as (session, _):
        return {"schema": "ciw.microtool-inspection.v1", "recording_role": CONTEXT,
                "results": [deepcopy(r) for r in session.results.values()
                            if r.get("operation_id") in OPERATIONS],
                "executions": [deepcopy(e) for e in session.executions.values()
                               if e.get("operation_id") in OPERATIONS]}


def run(workspace: Path, output: Path, registry: CapabilityRegistry, *,
        operation_id: str | None = None, request: dict | None = None,
        replay_result: str | None = None) -> dict:
    """Execute once in a fresh destination, preserving original records and refusals."""
    with _workspace(workspace) as (reader, frozen):
        original = None
        if replay_result is not None:
            if operation_id is not None or request is not None:
                raise ValueError("Replay selects one retained result, not replacement inputs")
            original = reader.results.get(replay_result)
            if original is None or original.get("operation_id") not in OPERATIONS:
                raise ValueError("Select an exact retained CSR micro-tool result")
            operation_id = original["operation_id"]
            request = original["parameters"]["request"]
        request = validate_request(operation_id, request)
        contract = registry.contract(operation_id)
        # Confirm executable registration and identity before any requested output exists.
        actual_runtime = registry.operations.get(operation_id).runtime_identity()
        if actual_runtime != contract["runtime"]:
            raise ValueError("Binding identity drift")
        if original is not None and actual_runtime != original["runtime"]:
            raise ValueError("Same-runtime reproduction requires the exact original binding")
        Path(output).mkdir(parents=True, exist_ok=False)
        session = Session.from_workspace(frozen, Path(output))
        session.operations = registry.operations
        response = session.handle({"protocol_version": 1, "request_id": str(uuid.uuid4()),
            "type": "operation.execute", "payload": {"operation_id": operation_id,
            "parameters": {"request": request, "recording_role": CONTEXT}}})
        session.save_workspace(Path(output) / "workspace.json")
        if response["type"] != "response":
            raise ValueError("Session refused dispatch: " + response["payload"]["message"])
        payload = response["payload"]
        # Equality is a scoped diagnostic, not a proof or a new numerical comparator.
        equality = None
        if original is not None and payload["result"] is not None:
            equality = _json(original["data"]) == _json(payload["result"]["data"])
        return {"workspace": str(Path(output) / "workspace.json"), **payload,
                "replayed_result_id": replay_result, "same_runtime_exact_data_equal": equality}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="NET Surface Path micro-tools")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("catalog")
    example = commands.add_parser("example")
    example.add_argument("--operation", choices=OPERATIONS, default=OPERATIONS[1])
    read = commands.add_parser("inspect")
    read.add_argument("workspace", type=Path)
    for name in ("run", "replay"):
        command = commands.add_parser(name)
        command.add_argument("--workspace", type=Path, required=True)
        command.add_argument("--output-dir", type=Path, required=True)
        command.add_argument("--csr-root", type=Path, required=True)
        command.add_argument("--csr-revision", required=True)
        command.add_argument("--python", default=sys.executable)
        if name == "run":
            command.add_argument("--operation", choices=OPERATIONS, required=True)
            command.add_argument("--request", type=Path, required=True)
        else:
            command.add_argument("--result", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "catalog":
            result = catalog()
        elif args.command == "example":
            result = {"arc_length": [0, 1, 2], "curvature": 0, "length_unit": "m",
                      "frame": "example/surface"}
            result.update({OPERATIONS[0]: {"initial_error": [0.002, -0.001]},
                OPERATIONS[1]: {"initial_bounds": [0.002, 0.001], "tolerances": [0.003, 0.001]},
                OPERATIONS[2]: {"covariance": [[4e-6, 1e-6], [1e-6, 1e-6]]}}[args.operation])
        elif args.command == "inspect":
            result = inspect(args.workspace)
        else:
            registry = bind_csr(args.csr_root, args.csr_revision, python=args.python)
            if args.command == "run":
                request, _ = _load(args.request, 65536)
                result = run(args.workspace, args.output_dir, registry,
                             operation_id=args.operation, request=request)
            else:
                result = run(args.workspace, args.output_dir, registry, replay_result=args.result)
        print(json.dumps(result, indent=2, allow_nan=False))
        # A valid calculation with a failed tolerance check is not an execution refusal.
        return 1 if result.get("status") == "refused" else 0
    except (ValueError, TypeError, KeyError, OSError, OverflowError, RecursionError) as exc:
        print(json.dumps({"status": "refused", "message": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
