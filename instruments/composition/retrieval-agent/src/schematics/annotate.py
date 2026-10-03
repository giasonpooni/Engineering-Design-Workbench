"""Write SAMPLED / REFUSED / UNRESOLVED onto the schematic. Never clip."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .eligibility import Decision, _written_A
from .ir import EdgeKind, Node, NodeKind, Schematic, Status
from .binding import finite_matrix


def invalidate_stale_results(schematic: Schematic) -> None:
    """Retain old numeric evidence, but do not display it as current success."""
    dependent_tools = {"jspt.local_structure", "jspt.first_order_covariance",
                       "jspt.run_covariance_experiment", "lyapunov.evaluate"}
    for function in schematic.of_kind(NodeKind.FUNCTION):
        current = _written_A(schematic, function.id)
        current_ref = current.get("binding")["result_id"] if current else None
        for edge in schematic.in_edges(function.id):
            if edge.kind not in {EdgeKind.LINEARIZES, EdgeKind.CERTIFIES}:
                continue
            cert = schematic.node(edge.src)
            if cert.kind is not NodeKind.CERTIFICATE or cert.get("result") != Status.SAMPLED.value:
                continue
            dependent = cert.get("tool") in dependent_tools or cert.get("owner") == "plsr"
            jacobian = cert.get("owner") == "jspt" and cert.get("A") is not None
            covariance_stale = False
            if cert.get("tool") in {"jspt.first_order_covariance", "jspt.run_covariance_experiment"}:
                try:
                    covariance_stale = finite_matrix(function.get("sigma_x")) != cert.get("sigma_x")
                except (TypeError, ValueError, OverflowError):
                    covariance_stale = True
            if ((jacobian and current is None) or
                    (dependent and (current_ref is None or cert.get("source_result_ref") != current_ref)) or covariance_stale):
                attrs = {**dict(cert.attrs), "historical_result": cert.get("result"),
                         "result": Status.NOT_ELIGIBLE.value, "currentness": "stale",
                         "stale_reason": "missing, stale, ambiguous or superseded Jacobian/covariance input binding"}
                schematic.replace(Node(cert.id, cert.kind, attrs))


def upsert_certificate(schematic: Schematic, *, node_id: str, owner: str, result: Status, target: str, edge: EdgeKind, attrs: Mapping[str, Any] | None = None) -> Node:
    payload = {"owner": owner, "result": result.value, **dict(attrs or {})}
    if node_id in schematic.nodes:
        old = schematic.node(node_id)
        if result is not Status.SAMPLED:
            previous = old.get("historical_sample")
            if previous is None and (old.get("result") == Status.SAMPLED.value or old.get("historical_result") == Status.SAMPLED.value):
                previous = dict(old.attrs)
            if previous is not None:
                payload["historical_sample"] = deepcopy(previous)
        node = Node(id=node_id, kind=NodeKind.CERTIFICATE, attrs=payload)
        schematic.replace(node)
    else:
        node = schematic.add(Node(id=node_id, kind=NodeKind.CERTIFICATE, attrs=payload))
        schematic.connect(edge, node_id, target)
    return node


def apply_decision(schematic: Schematic, decision: Decision, **extra: Any) -> Node | None:
    if decision.owner == "jspt" and decision.tool.startswith("jspt."):
        if decision.status is Status.ELIGIBLE:
            return None
        cert_id = f"cert:{decision.tool}:{decision.node_id}"
        result = Status.NOT_ELIGIBLE if decision.status is Status.NOT_ELIGIBLE else decision.status
        return upsert_certificate(schematic, node_id=cert_id, owner="jspt", result=result, target=decision.node_id, edge=EdgeKind.LINEARIZES, attrs={"reason": decision.reason, "tool": decision.tool, **extra})
    if decision.tool == "lyapunov.evaluate" and decision.status is Status.NOT_ELIGIBLE:
        old = schematic.nodes.get(f"cert:lyapunov:{decision.node_id}")
        if old is not None and old.get("currentness") == "stale":
            return old
        return upsert_certificate(schematic, node_id=f"cert:lyapunov:{decision.node_id}", owner="plsr", result=Status.NOT_ELIGIBLE, target=decision.node_id, edge=EdgeKind.CERTIFIES, attrs={"reason": decision.reason, **extra})
    return None


def set_observer_status(schematic: Schematic, observer_id: str, status: Status, next_step: str) -> None:
    node = schematic.node(observer_id)
    attrs = dict(node.attrs)
    attrs["status"] = status.value
    attrs["next"] = next_step
    schematic.replace(Node(id=node.id, kind=node.kind, attrs=attrs))


def observer_next_step(schematic: Schematic) -> str:
    missing_digest = [n.id for n in schematic.of_kind(NodeKind.MEASUREMENT) if not n.get("rci_digest")]
    if missing_digest:
        return f"declare sensor quality or bind RCI digest on {missing_digest[0]}"
    if any(_written_A(schematic, n.id) is None for n in schematic.of_kind(NodeKind.FUNCTION)):
        return "current content-bound JSPT call not yet sampled"
    return "observer mapped; no further declared gap"
