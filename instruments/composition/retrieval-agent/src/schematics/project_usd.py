"""USD is a projection of the schematic. The schematic is not a stage."""

from __future__ import annotations

from .ir import EdgeKind, NodeKind, Schematic


def _prim(node_id: str) -> str:
    return node_id.replace(":", "_")


def _rel(path: str) -> str:
    return f"</World/{_prim(path)}>"


def usda(schematic: Schematic) -> str:
    lines = [
        "#usda 1.0", "(", '    defaultPrim = "World"', "    metersPerUnit = 1",
        "    customLayerData = {",
        '        string ns.schematicSchema = "NsObservabilitySchematic@0.1"',
        '        string ns.canonical = "function+factor graph, not this file"',
        "    }", ")", "", 'def Xform "World"', "{",
    ]
    api_for = {
        NodeKind.FUNCTION: "NsPlantAPI", NodeKind.VARIABLE: "NsPortAPI",
        NodeKind.MEASUREMENT: "NsSensorAPI", NodeKind.OBSERVER: "NsObserverAPI",
        NodeKind.CERTIFICATE: "NsCertificateAPI", NodeKind.EVIDENCE: "NsEvidenceAPI",
        NodeKind.CONSTRAINT: "NsConstraintAPI", NodeKind.PRIOR: "NsPriorAPI",
    }
    for node in schematic.nodes.values():
        lines.append(f'    def Scope "{_prim(node.id)}" (')
        lines.append(f'        apiSchemas = ["{api_for[node.kind]}"]')
        lines.append("    )")
        lines.append("    {")
        lines.append(f'        token ns:kind = "{node.kind.value}"')
        for key, value in node.attrs.items():
            if value is None:
                continue
            if isinstance(value, bool):
                lines.append(f"        bool ns:{key} = {1 if value else 0}")
            elif isinstance(value, (int, float)):
                lines.append(f"        double ns:{key} = {value}")
            elif isinstance(value, list) and value and isinstance(value[0], (int, float)):
                inner = ", ".join(str(v) for v in value)
                lines.append(f"        double[] ns:{key} = [{inner}]")
            else:
                text = str(value).replace('"', "'")
                lines.append(f'        string ns:{key} = "{text}"')
        lines.append("    }")
        lines.append("")
    lines.append('    def Scope "_edges"')
    lines.append("    {")
    for i, edge in enumerate(schematic.edges):
        lines.append(f'        def Scope "{edge.kind.value}_{i}"')
        lines.append("        {")
        lines.append(f'            token ns:edge = "{edge.kind.value}"')
        lines.append(f"            rel ns:src = {_rel(edge.src)}")
        lines.append(f"            rel ns:dst = {_rel(edge.dst)}")
        if edge.kind is EdgeKind.MEASURES:
            lines.append(f"            rel ns:sensor:measures = {_rel(edge.dst)}")
        lines.append("        }")
    lines.append("    }")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)
