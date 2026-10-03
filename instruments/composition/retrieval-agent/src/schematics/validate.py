"""Fail closed on undeclared wiring. No inferred edges."""

from __future__ import annotations

from .ir import EdgeKind, NodeKind, Schematic

SCHEMA = "NsObservabilitySchematic@0.1"


class SchematicError(ValueError):
    pass


_ALLOWED = {
    EdgeKind.INPUT: (NodeKind.VARIABLE, NodeKind.FUNCTION),
    EdgeKind.OUTPUT: (NodeKind.FUNCTION, NodeKind.VARIABLE),
    EdgeKind.MEASURES: (NodeKind.MEASUREMENT, NodeKind.VARIABLE),
    EdgeKind.ACTUATES: (NodeKind.VARIABLE, NodeKind.FUNCTION),
    EdgeKind.BINDS: (NodeKind.EVIDENCE, NodeKind.MEASUREMENT),
    EdgeKind.LINEARIZES: (NodeKind.CERTIFICATE, NodeKind.FUNCTION),
    EdgeKind.CERTIFIES: (NodeKind.CERTIFICATE, NodeKind.FUNCTION),
    EdgeKind.OBSERVES: (NodeKind.OBSERVER, NodeKind.FUNCTION),
    EdgeKind.SENSES: (NodeKind.OBSERVER, NodeKind.MEASUREMENT),
    EdgeKind.COMPOSED_IN: (NodeKind.FUNCTION, NodeKind.FUNCTION),
}


def validate(schematic: Schematic) -> list[str]:
    problems: list[str] = []
    if "schema" in schematic.meta and schematic.meta["schema"] != SCHEMA:
        problems.append("unknown schematic schema")
    for edge in schematic.edges:
        allowed = _ALLOWED.get(edge.kind)
        if allowed is None:
            problems.append(f"unknown edge kind {edge.kind}")
            continue
        src_ok, dst_ok = allowed
        try:
            src = schematic.node(edge.src)
            dst = schematic.node(edge.dst)
        except KeyError as exc:
            problems.append(str(exc))
            continue
        if src.kind is not src_ok or dst.kind is not dst_ok:
            problems.append(
                f"{edge.kind.value} {edge.src}->{edge.dst} "
                f"expects {src_ok.value}->{dst_ok.value}, "
                f"got {src.kind.value}->{dst.kind.value}"
            )
    for node in schematic.nodes.values():
        if node.kind is NodeKind.FUNCTION:
            klass = node.get("class", "unknown")
            if klass not in {"linear", "lpv", "nonlinear", "unknown"}:
                problems.append(f"{node.id} has illegal class {klass!r}")
        if node.kind is NodeKind.CERTIFICATE:
            owner = node.get("owner")
            if owner not in {"jspt", "plsr", "rci", "cse"}:
                problems.append(f"{node.id} certificate owner {owner!r} is not a kernel")
    return problems


def require(schematic: Schematic) -> Schematic:
    problems = validate(schematic)
    if problems:
        raise SchematicError("; ".join(problems))
    return schematic
