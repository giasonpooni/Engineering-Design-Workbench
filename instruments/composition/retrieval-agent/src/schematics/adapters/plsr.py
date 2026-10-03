"""Wrap PLSR without importing it at module load.

Pin is schematics.pins.PLSR. Missing lyapunov is NOT_CHECKED.
A fixture A is refused. PLSR never forms J.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

from ..annotate import upsert_certificate
from ..eligibility import _written_A
from ..ir import EdgeKind, Schematic, Status
from ..kernels import KernelEvent
from ..pins import PLSR


class PlsrUnavailable(RuntimeError):
    pass


def load_lyapunov() -> Any:
    try:
        return import_module(PLSR["import"])
    except ImportError as exc:
        raise PlsrUnavailable(
            f"{PLSR['import']} is not installed; pin {PLSR['repo']}@{PLSR['sha']}"
        ) from exc


def _matrix(value: Any) -> list[list[float]]:
    return [[float(v) for v in row] for row in value]


def call_evaluate(schematic: Schematic, function_id: str) -> KernelEvent:
    node = schematic.node(function_id)
    cert_A = _written_A(schematic, function_id)
    if cert_A is None:
        upsert_certificate(
            schematic,
            node_id=f"cert:lyapunov:{function_id}",
            owner="plsr",
            result=Status.NOT_ELIGIBLE,
            target=function_id,
            edge=EdgeKind.CERTIFIES,
            attrs={"tool": "lyapunov.evaluate", "pin": f"{PLSR['repo']}@{PLSR['sha']}", "reason": "no non-fixture sampled JSPT A"},
        )
        return KernelEvent(tool="lyapunov.evaluate", owner="plsr", node_id=function_id, result=Status.NOT_ELIGIBLE, detail={"reason": "no non-fixture sampled JSPT A", "pin": PLSR})
    A = cert_A.get("A")
    x_star = node.get("x_star")
    try:
        lyapunov = load_lyapunov()
        plant = lyapunov.plant_from_jacobian(A, name=f"A=J({function_id})", time="continuous")
        certificate = lyapunov.certificate_for_plant(plant)
        sample = lyapunov.evaluate(plant, certificate, x_star)
        judged = lyapunov.verdict(plant, certificate, x_star)
    except PlsrUnavailable as exc:
        upsert_certificate(
            schematic,
            node_id=f"cert:lyapunov:{function_id}",
            owner="plsr",
            result=Status.NOT_CHECKED,
            target=function_id,
            edge=EdgeKind.CERTIFIES,
            attrs={"tool": "lyapunov.evaluate", "pin": f"{PLSR['repo']}@{PLSR['sha']}", "reason": str(exc)},
        )
        return KernelEvent(tool="lyapunov.evaluate", owner="plsr", node_id=function_id, result=Status.NOT_CHECKED, detail={"reason": str(exc), "pin": PLSR})
    except Exception as exc:
        upsert_certificate(
            schematic,
            node_id=f"cert:lyapunov:{function_id}",
            owner="plsr",
            result=Status.REFUSED,
            target=function_id,
            edge=EdgeKind.CERTIFIES,
            attrs={"tool": "lyapunov.evaluate", "A": A, "pin": f"{PLSR['repo']}@{PLSR['sha']}", "reason": str(exc)},
        )
        return KernelEvent(tool="lyapunov.evaluate", owner="plsr", node_id=function_id, result=Status.REFUSED, detail={"reason": str(exc), "pin": PLSR})
    upsert_certificate(
        schematic,
        node_id=f"cert:lyapunov:{function_id}",
        owner="plsr",
        result=Status.SAMPLED,
        target=function_id,
        edge=EdgeKind.CERTIFIES,
        attrs={
            "tool": "lyapunov.evaluate",
            "A": A,
            "source_result_ref": cert_A.get("binding")["result_id"],
            "source_execution_ref": cert_A.get("binding")["execution_id"],
            "P": _matrix(sample.P),
            "V": float(sample.value),
            "decrease": float(sample.decrease),
            "verdict": judged.status,
            "details": judged.details,
            "pin": f"{PLSR['repo']}@{PLSR['sha']}",
            "reason": "evaluate via pinned lyapunov; A was an input",
        },
    )
    return KernelEvent(
        tool="lyapunov.evaluate",
        owner="plsr",
        node_id=function_id,
        result=Status.SAMPLED,
        detail={"verdict": judged.status, "V": float(sample.value), "decrease": float(sample.decrease), "pin": PLSR},
    )
