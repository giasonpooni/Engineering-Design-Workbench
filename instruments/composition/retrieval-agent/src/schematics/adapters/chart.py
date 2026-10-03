"""Coordinate-consistency adapter. Identity is not a transport."""

from __future__ import annotations

from ..annotate import upsert_certificate
from ..ir import EdgeKind, Schematic, Status
from ..kernels import KernelEvent
from ..pins import JSPT
from .jspt import JsptUnavailable, load_sensitivity, resolve_model


def call_coordinate_consistency(schematic: Schematic, function_id: str) -> KernelEvent:
    node = schematic.node(function_id)
    chart = node.get("chart", "identity")
    T = node.get("chart_T")
    S = node.get("chart_S")
    dx = node.get("chart_dx")
    if chart in {None, "identity"} or T is None or S is None:
        return KernelEvent(
            tool="jspt.check_coordinate_consistency",
            owner="jspt",
            node_id=function_id,
            result=Status.NOT_ELIGIBLE,
            detail={"reason": "identity chart or missing T,S; no transport to check", "pin": JSPT},
        )
    if dx is None:
        dx = [1e-3] * len(list(node.get("x_star") or [0.0]))
    try:
        sensitivity = load_sensitivity()
        model = resolve_model(sensitivity, str(node.get("model_ref")), dict(node.attrs))
        coords = sensitivity.AffineCoordinates(T=T, S=S, name=str(chart))
        result = sensitivity.check_coordinate_consistency(model, node.get("x_star"), coords, dx)
    except JsptUnavailable as exc:
        return KernelEvent(
            tool="jspt.check_coordinate_consistency",
            owner="jspt",
            node_id=function_id,
            result=Status.NOT_CHECKED,
            detail={"reason": str(exc), "pin": JSPT},
        )
    except Exception as exc:
        upsert_certificate(
            schematic,
            node_id=f"cert:jspt.chart:{function_id}",
            owner="jspt",
            result=Status.REFUSED,
            target=function_id,
            edge=EdgeKind.LINEARIZES,
            attrs={"tool": "jspt.check_coordinate_consistency", "pin": f"{JSPT['repo']}@{JSPT['sha']}", "reason": str(exc)},
        )
        return KernelEvent(
            tool="jspt.check_coordinate_consistency",
            owner="jspt",
            node_id=function_id,
            result=Status.REFUSED,
            detail={"reason": str(exc), "pin": JSPT},
        )
    status = Status.SAMPLED if result.passed else Status.REFUSED
    upsert_certificate(
        schematic,
        node_id=f"cert:jspt.chart:{function_id}",
        owner="jspt",
        result=status,
        target=function_id,
        edge=EdgeKind.LINEARIZES,
        attrs={
            "tool": "jspt.check_coordinate_consistency",
            "passed": bool(result.passed),
            "residual": float(result.residual),
            "details": result.details,
            "chart": str(chart),
            "pin": f"{JSPT['repo']}@{JSPT['sha']}",
            "reason": "physical pushforward J' dx' = S J dx",
        },
    )
    return KernelEvent(
        tool="jspt.check_coordinate_consistency",
        owner="jspt",
        node_id=function_id,
        result=status,
        detail={"passed": bool(result.passed), "residual": float(result.residual), "pin": JSPT},
    )
