"""Human sheet. Not canonical."""

from __future__ import annotations

from .ir import NodeKind, Schematic

_KIND_SHAPE = {
    NodeKind.VARIABLE: ("[", "]"),
    NodeKind.FUNCTION: ("[[", "]]"),
    NodeKind.MEASUREMENT: ("((", "))"),
    NodeKind.PRIOR: ("((", "))"),
    NodeKind.CONSTRAINT: ("{{", "}}"),
    NodeKind.CERTIFICATE: ("[/", "/]"),
    NodeKind.OBSERVER: ("([", "])"),
    NodeKind.EVIDENCE: ("[(", ")]"),
}


def mermaid(schematic: Schematic) -> str:
    lines = ["flowchart LR"]
    for node in schematic.nodes.values():
        left, right = _KIND_SHAPE[node.kind]
        label = node.id
        extra = node.get("class") or node.get("result") or node.get("status")
        if extra:
            label = f"{node.id}\\n{extra}"
        lines.append(f'  {node.id}{left}"{label}"{right}')
    for edge in schematic.edges:
        lines.append(f"  {edge.src} -->|{edge.kind.value}| {edge.dst}")
    return "\n".join(lines) + "\n"
