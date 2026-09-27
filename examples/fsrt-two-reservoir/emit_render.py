#!/usr/bin/env python3
"""Emit HOST replay of published FSRT quickstart for the Godot Fluid balance tab.

HOST_REPLAY_OF_PUBLISHED_QUICKSTART: hard reconcile implemented locally with
P=I (no set_lcm import). Teaching inputs and constraint match
Fluid-State-Reconstruction-Testbed examples/quickstart.py @ 3674e0d…
Does not mint ciw.fluid-volume.v1.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_FOR_HELPER = Path(__file__).resolve().parents[2]
if str(REPO_FOR_HELPER / "examples") not in sys.path:
    sys.path.insert(0, str(REPO_FOR_HELPER / "examples"))
from _render_json import write_render as _shared_write_render  # noqa: E402

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent
OUT_DEFAULT = ROOT / "results" / "fsrt_render.json"
FIXTURE = REPO / "examples" / "adapters" / "two-reservoir.json"

FSRT_PIN = "3674e0d328bd63777486acd9d8b8b605a37d586f"
RCI_PIN = "f863bdd69d49224e0cdc871943bbb052e5b0a975"
# chi2.ppf(0.999, df=1); scipy unused here — hardcode published constant.
CHI2_0999_DF1 = 10.8275661707

DATA_SOURCE = (
    "GitHub MCP read of giasonpooni/Fluid-State-Reconstruction-Testbed "
    f"examples/quickstart.py @ {FSRT_PIN} "
    "(+ in-tree adapters/two-reservoir.json for model kind only). "
    "HOST_REPLAY_OF_PUBLISHED_QUICKSTART (not native set_lcm import). "
    "git clone 403; MCP read succeeded."
)

CAPTION = (
    "disagreement is not unique fault attribution. "
    "HOST replay of published quickstart teaching numbers; "
    "not a native FSRT/set_lcm receipt."
)


def _chi2_threshold(rank: int = 1, prob: float = 0.999) -> float:
    try:
        from scipy.stats import chi2  # type: ignore

        return float(chi2.ppf(prob, rank))
    except Exception:
        if rank == 1 and abs(prob - 0.999) < 1e-12:
            return CHI2_0999_DF1
        raise RuntimeError("scipy unavailable and no hardcode for this chi2 quantile")


def _hard_reconcile(x: list[float], *, hold: bool, threshold: float, stat: float) -> dict:
    """Hard reconcile with P=I, A=[[1,1]], b=[100], R=b_var=[0.25].

    S = A P A^T + R = 2.25; r = A x - b; when not held:
    x_hat = x - A^T/S * r; when held keep x and residual_post null.
    """
    a = [1.0, 1.0]
    b = 100.0
    s = 2.25
    r = a[0] * x[0] + a[1] * x[1] - b
    residual_pre = [r]
    if hold:
        return {
            "x": list(x),
            "x_unprojected": list(x),
            "residual_pre": residual_pre,
            "residual_post": None,
            "held": True,
            "consistency_stat": stat,
            "consistency_threshold": threshold,
            "status": "held",
        }
    # x_hat = x - A^T/S * r
    x_hat = [x[0] - (a[0] / s) * r, x[1] - (a[1] / s) * r]
    residual_post = [a[0] * x_hat[0] + a[1] * x_hat[1] - b]
    return {
        "x": x_hat,
        "x_unprojected": list(x),
        "residual_pre": residual_pre,
        "residual_post": residual_post,
        "held": False,
        "consistency_stat": stat,
        "consistency_threshold": threshold,
        "status": "reconciled",
    }


def _consistency_stat(x: list[float]) -> float:
    r = x[0] + x[1] - 100.0
    return (r * r) / 2.25


def _load_fixture_model() -> dict:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    model = raw["model"]
    return {
        "kind": model["kind"],
        "prior_mean": list(model["prior_mean"]),
        "prior_std": model["prior_std"],
        "total_mass_kg": model["total_mass_kg"],
        "total_mass_variance_kg2": model["total_mass_variance_kg2"],
        "fixture": str(FIXTURE.relative_to(REPO)),
        "constraint": {
            "A": [[1.0, 1.0]],
            "b": [100.0],
            "b_var": [0.25],
            "cov": "I",
            "note": "Published quickstart ConstraintSet; P=I for HOST replay",
        },
        "source_description": raw.get("source_description", ""),
    }


def _case_from_values(label: str, case_id: str, values: list[float], threshold: float) -> dict:
    score = _consistency_stat(values)
    held = score > threshold
    result = _hard_reconcile(values, hold=held, threshold=threshold, stat=score)
    x_hat = result["x"]
    originals = result["x_unprojected"]
    tanks = []
    for index, name in enumerate(("tank-1", "tank-2")):
        tanks.append(
            {
                "name": name,
                "original_kg": originals[index],
                "indicated_kg": originals[index],
                "reconciled_kg": None if held else x_hat[index],
                "display_kg": originals[index] if held else x_hat[index],
            }
        )
    balance_before = result["residual_pre"]
    balance_after = result["residual_post"]
    correction = None if held else [x_hat[0] - originals[0], x_hat[1] - originals[1]]
    return {
        "id": case_id,
        "label": label,
        "guard_status": "held" if held else "reconciled",
        "physical_model_status": (
            "physical_model_disagreement" if held else "consistent"
        ),
        "reconciliation_status": "model_inconsistent" if held else "ok",
        "fault_attribution": (
            "confounded_or_unidentifiable" if held else "not_tested"
        ),
        "consistency_statistic": score,
        "consistency_threshold": threshold,
        "tanks": tanks,
        "total_mass_kg": 100.0,
        "residuals": {
            "balance_before": balance_before,
            "balance_after": balance_after,
            "correction": correction,
            "unit": "kg",
            "residual_size_kg": abs(balance_before[0]),
        },
        "estimate": {
            "values": x_hat,
            "unit": "kg",
            "kind": "estimated_state",
        },
        "unprojected_estimate": {
            "values": originals,
            "unit": "kg",
        },
        "covariance": {
            "estimate": [[1.0, 0.0], [0.0, 1.0]],
            "note": "Published quickstart cov=I; HOST replay presentation",
        },
        "notes": [
            f"Published quickstart teaching inputs {values}",
            f"consistency_stat={score:.6g} vs chi2_0.999_df1={threshold:.10g}",
            "HOST hard reconcile P=I S=2.25; not native set_lcm",
        ],
    }


def build_payload() -> dict:
    fixture_model = _load_fixture_model()
    threshold = _chi2_threshold(1, 0.999)
    cases = [
        _case_from_values(
            "Small disagreement → reconcile",
            "small-disagreement-reconciled",
            [52.0, 46.0],
            threshold,
        ),
        _case_from_values(
            "Large disagreement → hold",
            "large-disagreement-held",
            [60.0, 50.0],
            threshold,
        ),
    ]
    return {
        "schema": "ciw.host-fsrt-render.v1",
        "kind": "fsrt-two-reservoir-presentation",
        "source": "HOST_REPLAY_OF_PUBLISHED_QUICKSTART",
        "data_source": DATA_SOURCE,
        "claim_scope": "computational-integrity-only",
        "may_authorize": False,
        "upstream_status": "HOST_REPLAY_OF_PUBLISHED_QUICKSTART",
        "upstream_pins": {
            "fsrt_revision": FSRT_PIN,
            "rci_revision": RCI_PIN,
            "note": DATA_SOURCE,
        },
        "model": fixture_model,
        "caption": CAPTION,
        "selected_case_index": 0,
        "cases": cases,
        "schematic": {
            "layout": "two-node-tanks",
            "node_positions": [[-1.2, 0.0, 0.0], [1.2, 0.0, 0.0]],
            "bar_axis": "y",
            "max_bar_kg": 100.0,
            "axis_labels": ["tank-1", "level", "tank-2"],
        },
        "presentation_only": True,
        "forbidden_claims": [
            "fluid volume field",
            "3DGS",
            "NeRF",
            "PDE field",
            "unique fault attribution",
            "physical verification",
            "native set_lcm import",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=OUT_DEFAULT,
        help="Path for fsrt_render.json (default: results/fsrt_render.json)",
    )
    args = parser.parse_args()
    payload = build_payload()
    _shared_write_render(args.output, payload)
    print(f"wrote {args.output}")
    for case in payload["cases"]:
        print(
            f"  {case['id']}: stat={case['consistency_statistic']:.6g} "
            f"thr={case['consistency_threshold']:.6g} "
            f"guard={case['guard_status']} estimate={case['estimate']['values']}"
        )
    print(f"source={payload['source']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
