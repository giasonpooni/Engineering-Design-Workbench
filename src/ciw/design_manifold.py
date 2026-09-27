"""Named design charts over declared coordinates.

A chart maps a point between two named frames. Changing domain is not the
same chart. This is not a category-theoretic runtime and does not admit state.
"""
from __future__ import annotations

from copy import deepcopy

SCHEMA = "ciw.design-chart.v1"

CHARTS = {
    "identity": {"id": "identity", "kind": "identity", "note": "Same coordinates, declared frame change only"},
    "scale": {"id": "scale", "kind": "diagonal_scale", "note": "Per-axis scale; frame must change"},
}


def catalog():
    return {"schema": SCHEMA, "charts": [deepcopy(item) for item in CHARTS.values()],
            "authority": "chart_application_is_not_state_admission"}


def apply_chart(chart_id, point, *, source_frame, target_frame, scales=None):
    if chart_id not in CHARTS:
        raise ValueError("Unknown design chart")
    if not isinstance(point, (list, tuple)) or not point:
        raise ValueError("Design chart requires a finite coordinate list")
    values = []
    for item in point:
        if type(item) not in (int, float) or item != item or abs(item) == float("inf"):
            raise ValueError("Design chart requires finite coordinates")
        values.append(float(item))
    if not source_frame or not target_frame:
        raise ValueError("Design chart requires declared source and target frames")
    if chart_id == "identity":
        if source_frame == target_frame:
            raise ValueError("Identity chart cannot collapse two frames into one name")
        mapped = list(values)
    else:
        if source_frame == target_frame:
            raise ValueError("Scale chart requires a distinct target frame")
        factors = list(scales or [1.0] * len(values))
        if len(factors) != len(values):
            raise ValueError("Scale chart factors must match the point")
        mapped = []
        for value, factor in zip(values, factors):
            if type(factor) not in (int, float) or factor != factor or abs(factor) == float("inf"):
                raise ValueError("Scale chart requires finite factors")
            mapped.append(float(value) * float(factor))
    return {
        "schema": SCHEMA,
        "chart_id": chart_id,
        "source_frame": source_frame,
        "target_frame": target_frame,
        "source": values,
        "target": mapped,
        "authority": "chart_application_is_not_state_admission",
    }


def compose(first_id, second_id, point, *, source_frame, mid_frame, target_frame, first_scales=None, second_scales=None):
    """Apply two charts in order. The midpoint frame must be declared."""
    if source_frame == mid_frame or mid_frame == target_frame or source_frame == target_frame:
        raise ValueError("Composed charts require three distinct frames")
    first = apply_chart(first_id, point, source_frame=source_frame, target_frame=mid_frame, scales=first_scales)
    second = apply_chart(second_id, first["target"], source_frame=mid_frame, target_frame=target_frame, scales=second_scales)
    return {
        "schema": SCHEMA,
        "chart_id": first_id + " then " + second_id,
        "source_frame": source_frame,
        "mid_frame": mid_frame,
        "target_frame": target_frame,
        "source": first["source"],
        "mid": first["target"],
        "target": second["target"],
        "authority": "chart_application_is_not_state_admission",
    }


def apply_document(document):
    """Apply a declared chart document."""
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise ValueError("Design chart document requires schema " + SCHEMA)
    if document.get("compose"):
        first, second = document["compose"]
        return compose(
            first, second, document.get("point"),
            source_frame=document.get("source_frame"),
            mid_frame=document.get("mid_frame"),
            target_frame=document.get("target_frame"),
            first_scales=document.get("first_scales"),
            second_scales=document.get("second_scales"),
        )
    return apply_chart(
        document.get("chart_id"), document.get("point"),
        source_frame=document.get("source_frame"),
        target_frame=document.get("target_frame"),
        scales=document.get("scales"),
    )
