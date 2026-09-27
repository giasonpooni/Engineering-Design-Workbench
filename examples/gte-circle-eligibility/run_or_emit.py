#!/usr/bin/env python3
"""Emit HOST GTE circle eligibility presentation for Godot.

Teaching split from in-tree examples/geometric-circle/ fixtures + adapters/circle.json.
Reuses ciw.geometric-circle.v1 only — no new CIW kind. No surveyed frame / physical
accuracy / BIM acceptance claims. Numbers labeled HOST_FROM_PUBLISHED_FIXTURES.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

REPO_FOR_HELPER = Path(__file__).resolve().parents[2]
if str(REPO_FOR_HELPER / "examples") not in sys.path:
    sys.path.insert(0, str(REPO_FOR_HELPER / "examples"))
from _render_json import write_render as _shared_write_render  # noqa: E402

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent
OUT_DEFAULT = ROOT / "results" / "gte_circle_render.json"
ADAPTER = REPO / "examples" / "adapters" / "circle.json"
FIXTURES = REPO / "examples" / "geometric-circle"

OPERATION_ID = "ciw.geometric-circle.v1"

DATA_SOURCE = (
    "HOST_FROM_PUBLISHED_FIXTURES: in-tree examples/adapters/circle.json + "
    "examples/geometric-circle/{source,held,singular}.json. "
    "Projected points and radial residuals are HOST teaching arithmetic from the "
    "published observed points and unit-circle constraint — not a live GTE run."
)

CAPTION = (
    "No surveyed frame / physical accuracy / BIM acceptance. "
    "Declared frame bench-plane only; presentation of retained teaching values; "
    "meshes do not compute."
)


def _radial(point: list[float], center: list[float], radius: float) -> float:
    dx = point[0] - center[0]
    dy = point[1] - center[1]
    return math.hypot(dx, dy) - radius


def _project(point: list[float], center: list[float], radius: float) -> list[float] | None:
    dx = point[0] - center[0]
    dy = point[1] - center[1]
    norm = math.hypot(dx, dy)
    if norm <= 0.0:
        return None  # singular at center
    return [center[0] + radius * dx / norm, center[1] + radius * dy / norm]


def _point_records(
    observed: list[list[float]],
    center: list[float],
    radius: float,
) -> list[dict]:
    records: list[dict] = []
    for index, obs in enumerate(observed):
        residual = _radial(obs, center, radius)
        projected = _project(obs, center, radius)
        records.append(
            {
                "id": f"sample-{index}",
                "observed_m": list(obs),
                "projected_m": projected,
                "radial_residual_m": residual if projected is not None else None,
                "correction_m": abs(residual) if projected is not None else None,
                "singular": projected is None,
            }
        )
    return records


def _case_eligible() -> dict:
    # adapters/circle.json / geometric-circle/source.json
    observed = [[1.01, 0.0], [0.0, 0.99]]
    center = [0.0, 0.0]
    radius = 1.0
    max_correction = 0.05
    points = _point_records(observed, center, radius)
    return {
        "id": "eligible-source",
        "label": "Eligible · source.json / circle.json",
        "status": "LIVE",
        "native_outcome": "eligible",
        "reason": "corrections_within_policy",
        "fixture": "examples/geometric-circle/source.json",
        "adapter": "examples/adapters/circle.json",
        "constraint": {
            "center_m": center,
            "radius_m": radius,
            "coordinate_frame": "bench-plane",
            "geometry_uncertainty": "fixed_exact",
        },
        "policy": {
            "max_correction_m": max_correction,
            "max_linearization_ratio": 0.1,
        },
        "points": points,
        "radial_residuals_m": [p["radial_residual_m"] for p in points],
        "notes": [
            "HOST projection onto unit circle from published fixtures",
            "max_correction_m=0.05 admits |residual|=0.01",
        ],
    }


def _case_held() -> dict:
    observed = [[1.01, 0.0], [0.0, 0.99]]
    center = [0.0, 0.0]
    radius = 1.0
    max_correction = 0.001
    points = _point_records(observed, center, radius)
    return {
        "id": "held-correction-limit",
        "label": "Held · held.json correction limit",
        "status": "HELD",
        "native_outcome": "held",
        "reason": "correction_limit",
        "fixture": "examples/geometric-circle/held.json",
        "constraint": {
            "center_m": center,
            "radius_m": radius,
            "coordinate_frame": "bench-plane",
            "geometry_uncertainty": "fixed_exact",
        },
        "policy": {
            "max_correction_m": max_correction,
            "max_linearization_ratio": 0.1,
        },
        "points": points,
        "radial_residuals_m": [p["radial_residual_m"] for p in points],
        "notes": [
            "Same observed points as eligible; max_correction_m=0.001 holds candidates",
            "Original evidence retained; no silent promotion",
        ],
    }


def _case_refused() -> dict:
    # singular.json — observation at circle center
    observed = [[0.0, 0.0], [0.0, 0.99]]
    center = [0.0, 0.0]
    radius = 1.0
    points = _point_records(observed, center, radius)
    return {
        "id": "refused-singular-center",
        "label": "Refused · singular.json at circle center",
        "status": "REFUSED",
        "native_outcome": "refused",
        "reason": "numeric_geometry",
        "fixture": "examples/geometric-circle/singular.json",
        "constraint": {
            "center_m": center,
            "radius_m": radius,
            "coordinate_frame": "bench-plane",
            "geometry_uncertainty": "fixed_exact",
        },
        "policy": {
            "max_correction_m": 0.05,
            "max_linearization_ratio": 0.1,
        },
        "points": points,
        "radial_residuals_m": [
            p["radial_residual_m"] if p["radial_residual_m"] is not None else "singular"
            for p in points
        ],
        "notes": [
            "Observation at constraint center → numeric_geometry refusal",
            "No projected point for the singular sample",
        ],
    }


def build_payload() -> dict:
    cases = [_case_eligible(), _case_held(), _case_refused()]
    cards = [
        {
            "title": case["label"],
            "status": case["status"],
            "native_outcome": case["native_outcome"],
            "reason": case["reason"],
        }
        for case in cases
    ]
    # Schematic series for residual strip: radial residual magnitudes per case sample-0
    residual_series = []
    for index, case in enumerate(cases):
        residuals = case.get("radial_residuals_m", [])
        first = residuals[0] if residuals else None
        value = abs(float(first)) if isinstance(first, (int, float)) else 0.0
        residual_series.append(
            {
                "index": index,
                "case_id": case["id"],
                "radial_abs_m": value,
                "status": case["status"],
            }
        )
    return {
        "schema": "ciw.host-gte-circle-eligibility-render.v1",
        "kind": "gte-circle-eligibility-presentation",
        "source": "HOST_FROM_PUBLISHED_FIXTURES",
        "data_source": DATA_SOURCE,
        "claim_scope": "computational-integrity-only",
        "may_authorize": False,
        "operation_id": OPERATION_ID,
        "upstream_status": "HOST_FROM_PUBLISHED_FIXTURES",
        "references": {
            "adapter": str(ADAPTER.relative_to(REPO)),
            "fixtures_dir": str(FIXTURES.relative_to(REPO)),
        },
        "caption": CAPTION,
        "selected_case_index": 0,
        "cases": cases,
        "cards": cards,
        "residual_series": residual_series,
        "schematic": {
            "layout": "circle-points-plus-radial-strip",
            "note": "2D projected points + radial residual strip — presentation only",
        },
        "presentation_only": True,
        "forbidden_claims": [
            "surveyed frame",
            "physical accuracy",
            "BIM acceptance",
            "state admission",
            "trajectory",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT_DEFAULT)
    args = parser.parse_args()
    payload = build_payload()
    _shared_write_render(args.output, payload)
    print(f"wrote {args.output}")
    for case in payload["cases"]:
        print(
            f"  {case['id']}: status={case['status']} "
            f"outcome={case['native_outcome']} reason={case['reason']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
