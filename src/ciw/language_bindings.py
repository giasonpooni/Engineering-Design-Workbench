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
    if binding_id == "julia-oscillator":
        from .julia_oscillator import workflow as julia_workflow
        julia_workflow._validate(__import__("json").loads(raw.decode("utf-8")))
        report["status"] = "inspectable"
        report["detail"] = "Julia session accepted without launching Julia"
        return report
    if binding_id == "native-interop-scr":
        from .native_interop import SCHEMA as NATIVE_SCHEMA
        payload = __import__("json").loads(raw.decode("utf-8"))
        if payload.get("schema") != NATIVE_SCHEMA:
            raise ValueError("Native binding inspect requires a retained native-interop session")
        report["status"] = "inspectable"
        report["detail"] = "Native session accepted without launching SCR"
        return report
    raise ValueError("Unknown language binding")
