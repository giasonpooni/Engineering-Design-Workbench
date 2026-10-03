"""Compile USDA that carries NsObservabilitySchematic@0.1.

Accepts SRA projections and hand-authored scenes.
Geometry prims without ns:kind are ignored.
"""

from __future__ import annotations

import re
from pathlib import Path

from .ir import EdgeKind, Node, NodeKind, Schematic
from .validate import require

_KIND = {kind.value: kind for kind in NodeKind}
_EDGE = {kind.value: kind for kind in EdgeKind}
_PRIM = re.compile(r'^\s*def (?:Scope|Xform) "([^"]+)"')
_KIND_LINE = re.compile(r'token ns:kind = "([^"]+)"')


def _node_id(prim: str) -> str:
    if prim.startswith("cert_"):
        return "cert:" + prim[5:].replace("_", ":")
    return prim


def _attrs(body: str) -> dict[str, object]:
    attrs: dict[str, object] = {}
    for key, raw in re.findall(r'(?:string|token) ns:([A-Za-z0-9_]+) = "([^"]*)"', body):
        if key != "kind":
            attrs[key] = raw
    for key, raw in re.findall(r"double ns:([A-Za-z0-9_]+) = ([0-9eE.+-]+)", body):
        attrs[key] = float(raw)
    for key, raw in re.findall(r"double\[\] ns:([A-Za-z0-9_]+) = \[([^\]]*)\]", body):
        attrs[key] = [float(p.strip()) for p in raw.split(",") if p.strip()]
    for key, raw in re.findall(r"bool ns:([A-Za-z0-9_]+) = ([01])", body):
        attrs[key] = raw == "1"
    return attrs


def _prim_bodies(text: str) -> list[tuple[str, str]]:
    lines = text.splitlines()
    found: list[tuple[str, str]] = []
    i = 0
    while i < len(lines):
        match = _PRIM.match(lines[i])
        if not match:
            i += 1
            continue
        name = match.group(1)
        j = i + 1
        own: list[str] = []
        started = False
        depth = 0
        while j < len(lines):
            if started and _PRIM.match(lines[j]) and depth == 1:
                break
            depth += lines[j].count("{") - lines[j].count("}")
            if "{" in lines[j]:
                started = True
            if started:
                own.append(lines[j])
            if started and depth <= 0:
                break
            j += 1
        found.append((name, "\n".join(own)))
        i += 1
    return found


def read_usda(text: str) -> Schematic:
    if "NsObservabilitySchematic@0.1" not in text:
        raise ValueError("UNRESOLVED: USDA is not an observability schematic (missing schema tag)")
    sch = Schematic(meta={"schema": "NsObservabilitySchematic@0.1", "source": "usda"})
    found = False
    for name, body in _prim_bodies(text):
        kind_m = _KIND_LINE.search(body)
        if kind_m is None:
            continue
        kind = _KIND.get(kind_m.group(1))
        if kind is None:
            raise ValueError(f"UNRESOLVED: {name} has unknown kind {kind_m.group(1)}")
        found = True
        sch.add(Node(id=_node_id(name), kind=kind, attrs=_attrs(body)))
    if not found:
        raise ValueError("UNRESOLVED: no prims with ns:kind")
    for kind_s, src, dst in re.findall(r'token ns:edge = "([^"]+)"\s+rel ns:src = </World/([^>]+)>\s+rel ns:dst = </World/([^>]+)>', text):
        edge = _EDGE.get(kind_s)
        if edge is None:
            raise ValueError(f"UNRESOLVED: unknown edge {kind_s}")
        src_id, dst_id = _node_id(src), _node_id(dst)
        if src_id not in sch.nodes or dst_id not in sch.nodes:
            raise ValueError(f"UNRESOLVED: edge {kind_s} {src}->{dst} missing endpoint")
        sch.connect(edge, src_id, dst_id)
    kinds = {n.kind.value for n in sch.nodes.values()}
    if "function" not in kinds:
        raise ValueError("UNRESOLVED: authored USDA has no function node")
    if "variable" not in kinds:
        raise ValueError("UNRESOLVED: authored USDA has no port / variable")
    return require(sch)


def compile_authored(path: str | Path) -> Schematic:
    return read_usda(Path(path).read_text(encoding="utf-8"))
