"""Diagram / SVG backend (Section 15): Morpho IR -> a complete SVG
document string. Pure and deterministic -- `layout_algorithm` must never
use randomness or an unseeded stochastic process (Section 15, Section 20).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Tuple
from xml.sax.saxutils import escape

from core.canonical.schema import FieldValue
from morpho.ir import MorphoDocument

GRID_V1 = "grid_v1"
_BOX_SIZE = 80.0
_MARGIN = 40.0

# XML 1.0 legal character ranges (https://www.w3.org/TR/xml/#charsets):
#   0x9 | 0xA | 0xD | [0x20-0xD7FF] | [0xE000-0xFFFD] | [0x10000-0x10FFFF]
# Escaping &/</>/" alone is not sufficient to guarantee well-formed
# output: a control character such as U+000B is illegal in XML
# regardless of escaping and makes the document unparseable. Entity and
# relation ids ultimately come from schema-declared field data (or, via
# Morpho source text, user-authored content) passed through the
# pipeline -- compile_svg's contract is to return "a complete SVG
# document string" for any MorphoDocument, so illegal characters must be
# stripped, not merely escaped. Implemented via plain integer codepoint
# comparisons (not a regex literal) to avoid any risk of the boundary
# characters themselves being mis-transcribed in source.


def _is_xml_legal_char(ch: str) -> bool:
    codepoint = ord(ch)
    return (
        codepoint in (0x09, 0x0A, 0x0D)
        or 0x20 <= codepoint <= 0xD7FF
        or 0xE000 <= codepoint <= 0xFFFD
        or 0x10000 <= codepoint <= 0x10FFFF
    )


def _sanitize(value: str) -> str:
    return "".join(ch for ch in value if _is_xml_legal_char(ch))


def _escape_text(value: str) -> str:
    """For element text content: strip XML-illegal characters, then
    escape &/</>."""
    return escape(_sanitize(value))


def _escape_attr(value: str) -> str:
    """For "..."-delimited attribute values: strip XML-illegal
    characters, then escape &/</>/" (escape() alone does not escape the
    double quote that delimits the attribute, so unescaped hostile
    content could otherwise break out of it)."""
    return escape(_sanitize(value), {'"': "&quot;"})


@dataclass(frozen=True)
class DiagramLayoutConfig:
    layout_algorithm: str = GRID_V1
    spacing: float = 140.0
    canvas: Mapping[str, FieldValue] = field(default_factory=dict)


def _grid_v1_positions(entity_ids: Tuple[str, ...], spacing: float, columns: int):
    positions = {}
    for index, entity_id in enumerate(entity_ids):
        row, col = divmod(index, columns)
        x = _MARGIN + col * spacing
        y = _MARGIN + row * spacing
        positions[entity_id] = (x, y)
    return positions


def compile_svg(ir: MorphoDocument, config: DiagramLayoutConfig) -> str:
    if config.layout_algorithm != GRID_V1:
        raise ValueError(f"unsupported deterministic layout_algorithm: {config.layout_algorithm!r}")

    entity_ids = tuple(sorted(e.id for e in ir.entities))
    columns = max(1, int(len(entity_ids) ** 0.5)) if entity_ids else 1
    positions = _grid_v1_positions(entity_ids, config.spacing, columns)

    width = config.canvas.get("width") or (
        _MARGIN * 2 + min(len(entity_ids), columns) * config.spacing
    )
    rows = (len(entity_ids) + columns - 1) // columns if entity_ids else 0
    height = config.canvas.get("height") or (_MARGIN * 2 + rows * config.spacing)

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
    ]

    for relation in sorted(ir.relations, key=lambda r: r.id):
        if relation.from_id in positions and relation.to_id in positions:
            x1, y1 = positions[relation.from_id]
            x2, y2 = positions[relation.to_id]
            stroke = "#999999" if relation.inference_status == "inferred" else "#333333"
            dash = ' stroke-dasharray="4,3"' if relation.inference_status == "inferred" else ""
            lines.append(
                f'<line x1="{x1 + _BOX_SIZE / 2}" y1="{y1 + _BOX_SIZE / 2}" '
                f'x2="{x2 + _BOX_SIZE / 2}" y2="{y2 + _BOX_SIZE / 2}" '
                f'stroke="{stroke}"{dash} data-relation-id="{_escape_attr(relation.id)}" />'
            )

    for entity_id in entity_ids:
        x, y = positions[entity_id]
        entity = ir.entity_by_id(entity_id)
        value = entity.attributes.get("value") if entity is not None else None
        lines.append(
            f'<g data-entity-id="{_escape_attr(entity_id)}">'
            f'<rect x="{x}" y="{y}" width="{_BOX_SIZE}" height="{_BOX_SIZE}" '
            f'fill="#e8eef7" stroke="#3366cc" />'
            f'<text x="{x + _BOX_SIZE / 2}" y="{y + _BOX_SIZE / 2 - 8}" '
            f'text-anchor="middle" font-size="12">{_escape_text(entity_id)}</text>'
            f'<text x="{x + _BOX_SIZE / 2}" y="{y + _BOX_SIZE / 2 + 10}" '
            f'text-anchor="middle" font-size="11">{_escape_text(str(value))}</text>'
            f"</g>"
        )

    lines.append("</svg>")
    return "\n".join(lines)
