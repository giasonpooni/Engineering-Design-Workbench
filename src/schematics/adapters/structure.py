"""Hang local linear structure on a function after a non-fixture A.

ker J is what this instantaneous map cannot see.
Not Kalman observability, not identifiability, not a Lyapunov certificate.
"""

from __future__ import annotations

from typing import Any

from ..annotate import upsert_certificate
from ..eligibility import _written_A
from ..ir import EdgeKind, Node, NodeKind, Schematic, Status
from ..kernels import KernelEvent
from ..pins import JSPT
from .jspt import JsptUnavailable, load_sensitivity


def _cols(matrix: Any) -> list[list[float]]:
    if matrix is None:
        return []
    if hasattr(matrix, "shape"):
        if len(matrix.shape) != 2:
            return []
        n, k = matrix.shape
        return [[float(matrix[i, j]) for i in range(n)] for j in range(k)]
    try:
        if not len(matrix):
            return []
        width = len(matrix[0])
    except TypeError:
        return []
    if not width:
        return []
    n = len(matrix)
    return [[float(matrix[i][j]) for i in range(n)] for j in range(width)]


def _vals(vector: Any) -> list[float]:
    return [float(v) for v in vector]


def call_local_structure(schematic: Schematic, function_id: str) -> KernelEvent:
    cert_A = _written_A(schematic, function_id)
    if cert_A is None:
        return KernelEvent(tool="jspt.local_structure", owner="jspt", node_id=function_id, result=Status.NOT_ELIGIBLE, detail={"reason": "no non-fixture sampled A", "pin": JSPT})
    A = cert_A.get("A")
    try:
        sensitivity = load_sensitivity()
        structure = sensitivity.local_structure(A)
    except JsptUnavailable as exc:
        upsert_certificate(schematic, node_id=f"cert:jspt.structure:{function_id}", owner="jspt", result=Status.NOT_CHECKED, target=function_id, edge=EdgeKind.LINEARIZES, attrs={"tool": "jspt.local_structure", "pin": f"{JSPT['repo']}@{JSPT['sha']}", "reason": str(exc)})
        return KernelEvent(tool="jspt.local_structure", owner="jspt", node_id=function_id, result=Status.NOT_CHECKED, detail={"reason": str(exc), "pin": JSPT})
    except Exception as exc:
        upsert_certificate(schematic, node_id=f"cert:jspt.structure:{function_id}", owner="jspt", result=Status.REFUSED, target=function_id, edge=EdgeKind.LINEARIZES, attrs={"tool": "jspt.local_structure", "pin": f"{JSPT['repo']}@{JSPT['sha']}", "reason": str(exc)})
        return KernelEvent(tool="jspt.local_structure", owner="jspt", node_id=function_id, result=Status.REFUSED, detail={"reason": str(exc), "pin": JSPT})
    rank = int(structure.rank)
    invisible = _cols(structure.invisible)
    visible = _cols(structure.visible)
    svals = _vals(structure.singular_values)
    upsert_certificate(
        schematic,
        node_id=f"cert:jspt.structure:{function_id}",
        owner="jspt",
        result=Status.SAMPLED,
        target=function_id,
        edge=EdgeKind.LINEARIZES,
        attrs={"tool": "jspt.local_structure", "source_result_ref": cert_A.get("binding")["result_id"], "source_execution_ref": cert_A.get("binding")["execution_id"], "rank": rank, "invisible": invisible, "visible": visible, "singular_values": svals, "pin": f"{JSPT['repo']}@{JSPT['sha']}", "reason": "ker J at x_star; not Kalman observability"},
    )
    node = schematic.node(function_id)
    attrs = dict(node.attrs)
    attrs["rank"] = rank
    attrs["invisible_dim"] = len(invisible)
    schematic.replace(Node(id=node.id, kind=NodeKind.FUNCTION, attrs=attrs))
    return KernelEvent(tool="jspt.local_structure", owner="jspt", node_id=function_id, result=Status.SAMPLED, detail={"rank": rank, "invisible_dim": len(invisible), "pin": JSPT})
