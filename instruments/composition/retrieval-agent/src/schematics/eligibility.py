"""Tool authorization is a table on declared nodes. Not a prompt."""

from __future__ import annotations

from dataclasses import dataclass

from .ir import EdgeKind, Node, NodeKind, PlantClass, Schematic, Status
from .binding import matches


@dataclass(frozen=True)
class Decision:
    tool: str
    owner: str
    status: Status
    node_id: str
    reason: str


def _class(node: Node) -> str:
    return str(node.get("class", PlantClass.UNKNOWN.value))


def _has_model(node: Node) -> bool:
    ref = node.get("model_ref")
    return isinstance(ref, str) and bool(ref.strip())


def _has_xstar(node: Node) -> bool:
    return node.get("x_star") is not None


def _written_A(schematic: Schematic, function_id: str) -> Node | None:
    latest = schematic.nodes.get(f"cert:jspt:{function_id}")
    if latest is not None and not matches(schematic, function_id, latest):
        return None
    candidates = {}
    for edge in schematic.in_edges(function_id, EdgeKind.LINEARIZES):
        cert = schematic.nodes.get(edge.src)
        if cert is None:
            return None
        if matches(schematic, function_id, cert):
            candidates[cert.id] = cert
    # Multiple records require an explicit caller selection, never edge-order
    # arbitration. Old/foreign annotations remain readable but non-authoritative.
    return next(iter(candidates.values())) if len(candidates) == 1 else None


def _digest(node: Node) -> bool:
    digest = node.get("rci_digest")
    return isinstance(digest, str) and bool(digest.strip())


def decisions_for_function(schematic: Schematic, node: Node) -> list[Decision]:
    out: list[Decision] = []
    klass = _class(node)
    if not _has_model(node) or klass == PlantClass.UNKNOWN.value:
        out.append(Decision(tool="jspt.jacobian_at", owner="jspt", status=Status.NOT_ELIGIBLE, node_id=node.id, reason="no declared model_ref or class is unknown"))
    elif not _has_xstar(node):
        out.append(Decision(tool="jspt.jacobian_at", owner="jspt", status=Status.NOT_ELIGIBLE, node_id=node.id, reason="nonlinear/linear map declared but x_star missing"))
    else:
        out.append(Decision(tool="jspt.jacobian_at", owner="jspt", status=Status.ELIGIBLE, node_id=node.id, reason=f"declared {klass} map with model_ref and x_star"))
        if klass in {PlantClass.NONLINEAR.value, PlantClass.LINEAR.value, PlantClass.LPV.value}:
            out.append(Decision(tool="jspt.sweep_perturbation_scale", owner="jspt", status=Status.ELIGIBLE, node_id=node.id, reason="local validity is a JSPT experiment, not a schematic color"))
    chart = node.get("chart", "identity")
    has_chart = chart not in {None, "identity"} and node.get("chart_T") is not None and node.get("chart_S") is not None
    if has_chart and _has_model(node) and _has_xstar(node):
        out.append(Decision(tool="jspt.check_coordinate_consistency", owner="jspt", status=Status.ELIGIBLE, node_id=node.id, reason="declared non-identity chart with T,S; physical pushforward is the invariant"))
    else:
        out.append(Decision(tool="jspt.check_coordinate_consistency", owner="jspt", status=Status.NOT_ELIGIBLE, node_id=node.id, reason="identity chart or missing T,S; no transport to check"))
    if _written_A(schematic, node.id) is not None:
        out.append(Decision(tool="jspt.local_structure", owner="jspt", status=Status.ELIGIBLE, node_id=node.id, reason="non-fixture A present; rank and ker J are JSPT structure, not an observer claim"))
        sigma = node.get("sigma_x")
        if isinstance(sigma, list) and sigma:
            out.append(Decision(tool="jspt.first_order_covariance", owner="jspt", status=Status.ELIGIBLE, node_id=node.id, reason="declared sigma_x and non-fixture A; same J, second use"))
        else:
            out.append(Decision(tool="jspt.first_order_covariance", owner="jspt", status=Status.NOT_ELIGIBLE, node_id=node.id, reason="no declared sigma_x; do not invent a covariance"))
        out.append(Decision(tool="lyapunov.evaluate", owner="plsr", status=Status.ELIGIBLE, node_id=node.id, reason="non-fixture JSPT certificate wrote A; PLSR may evaluate V"))
    else:
        out.append(Decision(tool="jspt.local_structure", owner="jspt", status=Status.NOT_ELIGIBLE, node_id=node.id, reason="no non-fixture sampled JSPT A on this function"))
        out.append(Decision(tool="jspt.first_order_covariance", owner="jspt", status=Status.NOT_ELIGIBLE, node_id=node.id, reason="no non-fixture sampled JSPT A on this function"))
        out.append(Decision(tool="lyapunov.evaluate", owner="plsr", status=Status.NOT_ELIGIBLE, node_id=node.id, reason="no non-fixture sampled JSPT A on this function"))
    return out


def decisions_for_measurement(node: Node) -> list[Decision]:
    if _digest(node):
        return [Decision(tool="rci.bind", owner="rci", status=Status.ELIGIBLE, node_id=node.id, reason="measurement carries an RCI digest")]
    return [Decision(tool="rci.bind", owner="rci", status=Status.NOT_ELIGIBLE, node_id=node.id, reason="measurement has no rci_digest; do not invent a sample")]


def decisions_for_constraint(node: Node) -> list[Decision]:
    if node.get("intent") and node.get("evidence"):
        return [Decision(tool="cse.dispose", owner="cse", status=Status.ELIGIBLE, node_id=node.id, reason="intent and evidence declared; CSE owns the disposition")]
    return [Decision(tool="cse.dispose", owner="cse", status=Status.NOT_ELIGIBLE, node_id=node.id, reason="constraint missing intent or evidence")]


def decide(schematic: Schematic) -> list[Decision]:
    found: list[Decision] = []
    for node in schematic.nodes.values():
        if node.kind is NodeKind.FUNCTION:
            found.extend(decisions_for_function(schematic, node))
        elif node.kind is NodeKind.MEASUREMENT:
            found.extend(decisions_for_measurement(node))
        elif node.kind is NodeKind.CONSTRAINT:
            found.extend(decisions_for_constraint(node))
    return found


def eligible(schematic: Schematic, tool: str | None = None) -> list[Decision]:
    rows = [d for d in decide(schematic) if d.status is Status.ELIGIBLE]
    if tool is not None:
        rows = [d for d in rows if d.tool == tool]
    return rows
