#!/usr/bin/env python3
"""Emit HOST variational-free-energy teaching presentation for Godot.

Teaching contrasts from examples/variational-free-energy/
(sensor-bias / ignored-correlation / wrong-curvature). HOST emit only —
does not run the free-energy solver. Caption: free-energy numerics are
computational, not physical calibration. Reuses ciw.variational-free-energy.v1
language — no new CIW kind.
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
OUT_DEFAULT = ROOT / "results" / "vfe_sensor_bias_render.json"
FIXTURES = REPO / "examples" / "variational-free-energy"

OPERATION_ID = "ciw.variational-free-energy.v1"

DATA_SOURCE = (
    "HOST_FROM_PUBLISHED_FIXTURES: in-tree examples/variational-free-energy/"
    "{sensor-bias,ignored-correlation,wrong-curvature}.json teaching contrasts. "
    "Declared generator vs assumed-model mismatches summarized for cards — "
    "not a live free-energy solve."
)

CAPTION = (
    "Free-energy numerics are computational, not physical calibration. "
    "Sensor calibration, surveyed geometry, physical state admission and "
    "physical stability remain unestablished. Lowering free energy does not "
    "make an assumed model physically correct."
)


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _noise_offdiag(cov: list) -> float:
    if not cov or not isinstance(cov[0], list) or len(cov[0]) < 2:
        return 0.0
    return float(cov[0][1])


def _bias_norm(bias: list) -> float:
    return math.hypot(float(bias[0]), float(bias[1])) if bias and len(bias) >= 2 else 0.0


def _case_sensor_bias() -> dict:
    data = _load("sensor-bias.json")
    gen = data["generator"]
    assumed = data["assumed_model"]
    heldout_bias = gen.get("heldout_bias", [0.0, 0.0])
    assumed_bias = assumed.get("heldout_bias", [0.0, 0.0])
    mismatch = _bias_norm(
        [heldout_bias[0] - assumed_bias[0], heldout_bias[1] - assumed_bias[1]]
    )
    return {
        "id": "sensor-bias",
        "label": "Sensor bias · generator bias absent from likelihood",
        "status": "REQUEST_EVIDENCE",
        "native_outcome": "teaching_contrast",
        "reason": "unmodelled_generator_bias",
        "fixture": "examples/variational-free-energy/sensor-bias.json",
        "experiment_id": data.get("experiment_id"),
        "contrast": {
            "kind": "sensor_bias",
            "generator_heldout_bias": heldout_bias,
            "assumed_heldout_bias": assumed_bias,
            "bias_mismatch_norm": mismatch,
            "generator_curvature": gen.get("gaussian_curvature"),
            "geometry_curvature": data.get("geometry", {}).get("gaussian_curvature"),
        },
        "notes": [
            "Optimization can converge while truth error and predictive error remain large",
            "docs/VARIATIONAL_FREE_ENERGY.md · sensor-bias.json",
        ],
    }


def _case_ignored_correlation() -> dict:
    data = _load("ignored-correlation.json")
    gen = data["generator"]
    assumed = data["assumed_model"]
    gen_off = _noise_offdiag(gen.get("training_noise_covariance", []))
    assumed_off = _noise_offdiag(assumed.get("training_noise_covariance", []))
    return {
        "id": "ignored-correlation",
        "label": "Ignored correlation · simplified assumed covariance",
        "status": "HELD",
        "native_outcome": "teaching_contrast",
        "reason": "omitted_noise_correlation",
        "fixture": "examples/variational-free-energy/ignored-correlation.json",
        "experiment_id": data.get("experiment_id"),
        "contrast": {
            "kind": "ignored_correlation",
            "generator_noise_offdiag": gen_off,
            "assumed_noise_offdiag": assumed_off,
            "offdiag_mismatch": abs(gen_off - assumed_off),
            "generator_curvature": gen.get("gaussian_curvature"),
            "geometry_curvature": data.get("geometry", {}).get("gaussian_curvature"),
        },
        "notes": [
            "Generate correlated noise while fitting the declared simplified covariance",
            "Omitted correlation does not distort every direction the same way",
        ],
    }


def _case_wrong_curvature() -> dict:
    data = _load("wrong-curvature.json")
    gen = data["generator"]
    geom = data.get("geometry", {})
    gen_k = float(gen.get("gaussian_curvature", 0.0))
    geom_k = float(geom.get("gaussian_curvature", 0.0))
    return {
        "id": "wrong-curvature",
        "label": "Wrong curvature · generator ≠ fitted geometry",
        "status": "REFUSED",
        "native_outcome": "teaching_contrast",
        "reason": "curvature_mismatch",
        "fixture": "examples/variational-free-energy/wrong-curvature.json",
        "experiment_id": data.get("experiment_id"),
        "contrast": {
            "kind": "wrong_curvature",
            "generator_curvature": gen_k,
            "geometry_curvature": geom_k,
            "curvature_delta": abs(gen_k - geom_k),
        },
        "notes": [
            "Posterior agreement validates inference for the fitted matrix, not that matrix's geometry",
            "Gaussian exactness does not certify continuous-surface approximation",
        ],
    }


def build_payload() -> dict:
    cases = [_case_sensor_bias(), _case_ignored_correlation(), _case_wrong_curvature()]
    cards = []
    residual_series = []
    for index, case in enumerate(cases):
        contrast = case["contrast"]
        if contrast["kind"] == "sensor_bias":
            metric = float(contrast["bias_mismatch_norm"])
            metric_key = "bias_mismatch_norm"
        elif contrast["kind"] == "ignored_correlation":
            metric = float(contrast["offdiag_mismatch"])
            metric_key = "offdiag_mismatch"
        else:
            metric = float(contrast["curvature_delta"])
            metric_key = "curvature_delta"
        cards.append(
            {
                "title": case["label"],
                "status": case["status"],
                "reason": case["reason"],
                "metric_key": metric_key,
                "metric_value": metric,
            }
        )
        residual_series.append(
            {
                "index": index,
                "case_id": case["id"],
                "mismatch_metric": metric,
                "status": case["status"],
            }
        )
    return {
        "schema": "ciw.host-vfe-sensor-bias-teach-render.v1",
        "kind": "vfe-sensor-bias-teach-presentation",
        "source": "HOST_FROM_PUBLISHED_FIXTURES",
        "data_source": DATA_SOURCE,
        "claim_scope": "computational-integrity-only",
        "may_authorize": False,
        "operation_id": OPERATION_ID,
        "upstream_status": "HOST_FROM_PUBLISHED_FIXTURES",
        "references": {
            "fixtures_dir": str(FIXTURES.relative_to(REPO)),
            "docs": "docs/VARIATIONAL_FREE_ENERGY.md",
        },
        "caption": CAPTION,
        "selected_case_index": 0,
        "cases": cases,
        "cards": cards,
        "residual_series": residual_series,
        "schematic": {
            "layout": "contrast-mismatch-strip",
            "note": "Declared generator vs assumed-model mismatch metrics — presentation only",
        },
        "presentation_only": True,
        "forbidden_claims": [
            "physical calibration",
            "sensor calibration established",
            "surveyed geometry",
            "physical state admission",
            "physical stability",
            "assumed model physically correct",
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
            f"  {case['id']}: status={case['status']} reason={case['reason']} "
            f"contrast={case['contrast']['kind']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
