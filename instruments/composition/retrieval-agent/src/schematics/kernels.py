"""Plan-only events and fixture A. Fixture A is not a JSPT sample."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .annotate import upsert_certificate
from .eligibility import Decision
from .ir import EdgeKind, Schematic, Status


@dataclass
class KernelEvent:
    tool: str
    owner: str
    node_id: str
    result: Status
    detail: dict[str, Any] = field(default_factory=dict)


def plan(decisions: list[Decision]) -> list[KernelEvent]:
    events: list[KernelEvent] = []
    for d in decisions:
        if d.status is Status.ELIGIBLE:
            events.append(KernelEvent(tool=d.tool, owner=d.owner, node_id=d.node_id, result=Status.NOT_CHECKED, detail={"reason": d.reason, "mode": "plan"}))
        else:
            events.append(KernelEvent(tool=d.tool, owner=d.owner, node_id=d.node_id, result=d.status, detail={"reason": d.reason, "mode": "blocked"}))
    return events


def attach_fixture_linearization(schematic: Schematic, function_id: str, *, A: list[list[float]], validity_radius: float | None = None) -> KernelEvent:
    node = schematic.node(function_id)
    model = node.get("model_ref")
    upsert_certificate(
        schematic,
        node_id=f"cert:jspt:{function_id}",
        owner="jspt",
        result=Status.SAMPLED,
        target=function_id,
        edge=EdgeKind.LINEARIZES,
        attrs={"tool": "jspt.jacobian_at", "A": A, "fixture": True, "model_ref": model, "validity_radius": validity_radius, "reason": "fixture linearization shipped with the example; pin JSPT to replace"},
    )
    return KernelEvent(tool="jspt.jacobian_at", owner="jspt", node_id=function_id, result=Status.SAMPLED, detail={"fixture": True, "A": A, "validity_radius": validity_radius})
