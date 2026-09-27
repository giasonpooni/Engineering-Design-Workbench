#!/usr/bin/env python3
"""Emit HOST / synthetic CSG path+sensitivity presentation JSON for Godot.

Attaches conceptually to existing ciw.curved-path-transfer.v1 (pin bbc535af…).
Does not mint a second curved-path operation. Full CSG module tree not vendored
(git clone 403; gh unauthenticated). HOST surface+path+Jacobi strip from
in-tree curved-path-study/baseline.json; boundary params cited from MCP-read
examples/replay_path_artefact.py @ bbc535af.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

REPO_FOR_HELPER = Path(__file__).resolve().parents[2]
if str(REPO_FOR_HELPER / "examples") not in sys.path:
    sys.path.insert(0, str(REPO_FOR_HELPER / "examples"))
from _render_json import write_render as _shared_write_render  # noqa: E402

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent
OUT_DEFAULT = ROOT / "results" / "csg_render.json"
BASELINE = REPO / "examples" / "curved-path-study" / "baseline.json"
GEODESIC_REF = REPO / "examples" / "geodesic-reference" / "curved-path.json"

CSG_REVISION = "bbc535af29c30997e56fd120320c570830676462"
CSG_SOURCE_TREE = "181b6eb73288d001f45c39bb149b1a80a431f34b"
OPERATION_ID = "ciw.curved-path-transfer.v1"

DATA_SOURCE = (
    "GitHub MCP read of giasonpooni/Curved-Surface-Geodesic-Sensitivity-Runtime "
    f"examples/replay_path_artefact.py @ {CSG_REVISION} "
    "(hyperbolic_paraboloid 0.6, u0=0.15, v0=-0.1, heading=0.65, length=1.5, "
    "n_steps=600) and examples/emit_boundary_record.py (torus 200/60 mm); "
    "+ in-tree curved-path-study/baseline.json for HOST constant-curvature "
    "path+Jacobi strip. git clone 403; MCP read succeeded; full CSG package "
    "not vendored. Status HOST_SYNTHETIC_FROM_PUBLISHED_BOUNDARY_PARAMS."
)

POLICIES_CURVED = {
    "geometry_basis": "declared_constant_curvature",
    "solver": "native_rk4",
    "observation_mode": "intrinsic-surface-distance",
    "uncertainty": "conditional_on_declared_starting_covariance",
    "physical_geometry": "not_established",
}


def _sample_path(arclength: list[float], curvature: float) -> list[list[float]]:
    """Presentation embedding of a constant-curvature geodesic arc (not surveyed BIM)."""
    if curvature <= 0:
        return [[float(s), 0.0, 0.0] for s in arclength]
    radius = 1.0 / math.sqrt(curvature)
    points: list[list[float]] = []
    for s in arclength:
        theta = float(s) / radius
        x = radius * math.sin(theta)
        z = radius * (1.0 - math.cos(theta))
        points.append([x, 0.0, z])
    return points


def _jacobi_norms(arclength: list[float], curvature: float, y0: float, yp0: float) -> list[float]:
    norms: list[float] = []
    kappa = math.sqrt(abs(curvature)) if curvature != 0 else 0.0
    for s in arclength:
        s = float(s)
        if curvature > 0:
            y = y0 * math.cos(kappa * s) + (yp0 / kappa) * math.sin(kappa * s)
            yp = -y0 * kappa * math.sin(kappa * s) + yp0 * math.cos(kappa * s)
        elif curvature < 0:
            y = y0 * math.cosh(kappa * s) + (yp0 / kappa) * math.sinh(kappa * s)
            yp = y0 * kappa * math.sinh(kappa * s) + yp0 * math.cosh(kappa * s)
        else:
            y = y0 + yp0 * s
            yp = yp0
        norms.append(math.sqrt(y * y + yp * yp))
    return norms


def _sensitivity_strip(
    path: list[list[float]], norms: list[float], scale: float = 8.0
) -> list[list[float]]:
    if not norms:
        return []
    peak = max(norms) or 1.0
    strip: list[list[float]] = []
    for point, norm in zip(path, norms):
        strip.append([point[0], scale * (norm / peak), point[2]])
    return strip


def build_payload() -> dict:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    geodesic = json.loads(GEODESIC_REF.read_text(encoding="utf-8"))
    arclength = [float(s) for s in baseline["arclength"]]
    curvature = float(baseline["gaussian_curvature"])
    perturbation = [float(v) for v in baseline["initial_perturbation"]]
    path = _sample_path(arclength, curvature)
    norms = _jacobi_norms(arclength, curvature, perturbation[0], perturbation[1])
    strip = _sensitivity_strip(path, norms)
    path_length = arclength[-1] - arclength[0]
    flat_end = abs(perturbation[0] + perturbation[1] * path_length)
    curved_end = norms[-1]
    declared_residual = abs(curved_end - flat_end)

    return {
        "schema": "ciw.host-csg-render.v1",
        "kind": "csg-path-sensitivity-presentation",
        "source": "HOST_SYNTHETIC_FROM_PUBLISHED_BOUNDARY_PARAMS",
        "data_source": DATA_SOURCE,
        "claim_scope": "computational-integrity-only",
        "may_authorize": False,
        "operation_id": OPERATION_ID,
        "upstream_status": "HOST_SYNTHETIC_FROM_PUBLISHED_BOUNDARY_PARAMS",
        "upstream_pins": {
            "csg_revision": CSG_REVISION,
            "csg_source_tree": CSG_SOURCE_TREE,
            "note": DATA_SOURCE,
        },
        "published_boundary_params": {
            "replay_path_artefact": {
                "surface": "hyperbolic_paraboloid(0.6)",
                "u0": 0.15,
                "v0": -0.1,
                "heading": 0.65,
                "length": 1.5,
                "n_steps": 600,
            },
            "emit_boundary_record": {
                "surface": "torus(R=200 mm, r=60 mm)",
            },
            "note": (
                "Cited from MCP-read examples; HOST presentation path uses "
                "in-tree baseline constant-curvature sampling, not a native "
                "CSG integrate_paths receipt."
            ),
        },
        "configuration": dict(POLICIES_CURVED),
        "references": {
            "baseline": str(BASELINE.relative_to(REPO)),
            "geodesic_reference": str(GEODESIC_REF.relative_to(REPO)),
            "upstream_cites": [
                "examples/csg-path-sensitivity/upstream/replay_path_artefact.py",
                "examples/csg-path-sensitivity/upstream/emit_boundary_record.py",
            ],
            "baseline_experiment_id": baseline.get("experiment_id"),
            "geodesic_experiment_id": geodesic.get("experiment_id"),
        },
        "units": baseline.get("units", {"length": "m", "angle": "radian"}),
        "gaussian_curvature": curvature,
        "arclength": arclength,
        "initial_perturbation": perturbation,
        "path_polyline": path,
        "sensitivity_norm": norms,
        "sensitivity_strip": strip,
        "cards": {
            "path_length_m": path_length,
            "declared_residual": declared_residual,
            "sensitivity_norm_endpoint": norms[-1] if norms else None,
            "sensitivity_norm_peak": max(norms) if norms else None,
            "native_status": "HOST_SYNTHETIC_FROM_PUBLISHED_BOUNDARY_PARAMS",
        },
        "caption": (
            "HOST-sampled constant-curvature presentation polyline and Jacobi norms "
            "from in-tree baseline; boundary params cited from MCP-read CSG examples. "
            "Not surveyed BIM or physical geodesic truth. Attached conceptually to "
            "ciw.curved-path-transfer.v1 — no second op."
        ),
        "presentation_only": True,
        "forbidden_claims": [
            "surveyed BIM",
            "physical geodesic truth",
            "second curved-path operation",
            "physical calibration",
            "native CSG integrate_paths receipt",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=OUT_DEFAULT,
        help="Path for csg_render.json (default: results/csg_render.json)",
    )
    args = parser.parse_args()
    payload = build_payload()
    _shared_write_render(args.output, payload)
    print(f"wrote {args.output}")
    cards = payload["cards"]
    print(
        f"points={len(payload['path_polyline'])} path_length={cards['path_length_m']} "
        f"residual={cards['declared_residual']:.6g} status={cards['native_status']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
