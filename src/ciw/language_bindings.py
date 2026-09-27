"""Registered language bindings that can be inspected without a language chain.

Python remains the session authority. Julia, C/C++ and Rust appear only as
named bindings. A missing runtime is a refused inspect, not a silent fallback
solver.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

SCHEMA = "ciw.language-bindings.v1"

BINDINGS = (
    {
        "id": "python-session",
        "language": "python",
        "status": "implemented",
        "inspect": "ciw session and experiment.inspect",
        "execute": "existing ciw operations",
    },
    {
        "id": "julia-oscillator",
        "language": "julia",
        "status": "inspect_without_julia",
        "inspect": "ciw julia-oscillator inspect",
        "execute": "requires pinned julia runtime",
        "module": "ciw.julia_oscillator",
    },
    {
        "id": "native-interop-scr",
        "language": "c++-rust-julia",
        "status": "inspect_retained",
        "inspect": "ciw native-interop retained session",
        "execute": "requires pinned SCR host",
        "module": "ciw.native_interop",
    },
)


def catalog():
    return {
        "schema": SCHEMA,
        "authority": "python_session",
        "required_chain": False,
        "bindings": [deepcopy(item) for item in BINDINGS],
    }


def inspect_binding(binding_id, path=None):
    catalogued = next((item for item in BINDINGS if item["id"] == binding_id), None)
    if catalogued is None:
        raise ValueError("Unknown language binding")
    report = {"schema": SCHEMA, "binding": deepcopy(catalogued), "runtime_launched": False}
    if binding_id == "python-session":
        report["status"] = "inspectable"
        report["detail"] = "Python session is the retained authority"
        return report
    if path is None:
        report["status"] = "refused"
        report["detail"] = "Retained session path required; runtime was not launched"
        return report
    raw = Path(path).read_bytes()
    payload = __import__("json").loads(raw.decode("utf-8"))
    if binding_id == "julia-oscillator":
        from .julia_oscillator import SOURCE_SCHEMA, workflow as julia_workflow
        if payload.get("schema") == SOURCE_SCHEMA:
            if "model" not in payload or "time_s" not in payload:
                raise ValueError("Julia source inspect requires model and time samples")
            report["status"] = "inspectable"
            report["detail"] = "Julia source accepted without launching Julia"
            return report
        julia_workflow._validate(payload)
        report["status"] = "inspectable"
        report["detail"] = "Julia session accepted without launching Julia"
        return report
    if binding_id == "native-interop-scr":
        from .native_interop import SCHEMA as NATIVE_SCHEMA
        if payload.get("schema") != NATIVE_SCHEMA:
            raise ValueError("Native binding inspect requires a retained native-interop session")
        report["status"] = "inspectable"
        report["detail"] = "Native session accepted without launching SCR"
        return report
    raise ValueError("Unknown language binding")


def inspect_runtime_files(binding_id):
    """Hash pinned runtime files. Does not launch the runtime."""
    catalogued = next((item for item in BINDINGS if item["id"] == binding_id), None)
    if catalogued is None:
        raise ValueError("Unknown language binding")
    root = Path(__file__).resolve().parents[2]
    files = {
        "julia-oscillator": (
            "runtimes/julia-oscillator/oscillator_worker.jl",
            "runtimes/julia-oscillator/Project.toml",
        ),
        "native-interop-scr": (
            "runtimes/native-interop/worker.jl",
            "runtimes/native-interop/Project.toml",
        ),
    }.get(binding_id, ())
    from hashlib import sha256
    entries = []
    for relative in files:
        path = root / relative
        if not path.is_file():
            raise ValueError("Pinned runtime file is missing: " + relative)
        entries.append({
            "path": relative,
            "sha256": sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
        })
    return {
        "schema": SCHEMA,
        "binding": deepcopy(catalogued),
        "runtime_launched": False,
        "status": "inspectable",
        "files": entries,
        "detail": "Pinned runtime files hashed without launching the language",
    }


def create(binding_id, source_path, output_path, *, julia=None, runtime=None):
    """Run create through a pinned binding. Missing pins are refused."""
    if binding_id != "julia-oscillator":
        raise ValueError("Create is implemented for the julia-oscillator binding only")
    from pathlib import Path
    julia_bin = Path(julia) if julia else None
    runtime_dir = Path(runtime) if runtime else None
    if julia_bin is None or not julia_bin.is_file() or runtime_dir is None or not runtime_dir.is_dir():
        return {
            "schema": SCHEMA,
            "binding_id": binding_id,
            "status": "refused",
            "runtime_launched": False,
            "detail": "Pinned julia executable and julia-oscillator runtime directory are required",
        }
    from .julia_oscillator import workflow as julia_workflow
    from .session import write_json
    raw = Path(source_path).read_bytes()
    bundle = julia_workflow.create_session(raw, {"julia_runtime": runtime_dir, "julia": julia_bin})
    write_json(Path(output_path), bundle)
    return {
        "schema": SCHEMA,
        "binding_id": binding_id,
        "status": "created",
        "runtime_launched": True,
        "bundle_file": str(output_path),
        "bundle_id": bundle.get("bundle_digest"),
    }
