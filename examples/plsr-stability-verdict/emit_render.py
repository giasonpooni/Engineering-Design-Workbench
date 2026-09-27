#!/usr/bin/env python3
"""Emit HOST identified-stability / PLSR verdict teaching presentation for Godot.

Teaching from examples/identified-stability/README.md:
  identity certificate → NUMERICAL_INCONCLUSIVE
  level=0 → OUTSIDE_LEVEL_SET
Pin PLSR commit cited in README. Reuses ciw.identified-stability.v1 only.
HOST_ANALOG / HOST_FROM_DOCUMENTED_OUTCOMES — does not certify the inequality.
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
OUT_DEFAULT = ROOT / "results" / "plsr_stability_render.json"
README = REPO / "examples" / "identified-stability" / "README.md"

PLSR_COMMIT = "19ea6967060166ba09db6cd4563bd87bd6b3d196"
OPERATION_ID = "ciw.identified-stability.v1"

DATA_SOURCE = (
    "HOST_FROM_DOCUMENTED_OUTCOMES / HOST_ANALOG: "
    "examples/identified-stability/README.md teaching outcomes at PLSR commit "
    f"{PLSR_COMMIT}. Identity-matrix certificate and level=0 helper paths. "
    "Not a live PLSR evaluation; parameter covariance unknown."
)

CAPTION = (
    "Does not certify the requested inequality; parameter covariance unknown; "
    "not physical equilibrium. Proof status NOT_CHECKED. "
    "Completed computation retained with explicit inconclusive / outside-level outcomes."
)


def _case_numerical_inconclusive() -> dict:
    # Neutral conservation mode with identity certificate → NUMERICAL_INCONCLUSIVE.
    # HOST teaching numbers: quadratic form ≈ state·state, decrease ≈ 0 (neutral mode).
    state = [1.0, 1.0]  # equal reservoirs — conservation mode
    V = state[0] ** 2 + state[1] ** 2  # identity certificate
    V_next = V  # neutral: no decrease
    decrease = V - V_next
    margin = decrease  # zero margin → inconclusive numerically
    return {
        "id": "identity-certificate-inconclusive",
        "label": "Identity certificate → NUMERICAL_INCONCLUSIVE",
        "status": "HISTORICAL",
        "verdict": "NUMERICAL_INCONCLUSIVE",
        "reason": "neutral_conservation_mode",
        "level": None,
        "certificate": "identity",
        "state_mean": state,
        "quadratic_value": V,
        "quadratic_next": V_next,
        "decrease": decrease,
        "margin": margin,
        "proof_status": "NOT_CHECKED",
        "booleans": {
            "inside_level_set": True,
            "decrease_nonnegative": True,
            "margin_positive": False,
        },
        "notes": [
            "Synthetic two-reservoir identity certificate: native status NUMERICAL_INCONCLUSIVE",
            "Does not certify the requested inequality",
            f"PLSR pin {PLSR_COMMIT}",
        ],
    }


def _case_outside_level_set() -> dict:
    # level=0 with nonzero retained state → OUTSIDE_LEVEL_SET.
    state = [1.0, 1.0]
    level = 0.0
    V = state[0] ** 2 + state[1] ** 2
    # Outside: V > level
    margin = level - V  # negative
    return {
        "id": "level-zero-outside",
        "label": "level=0 → OUTSIDE_LEVEL_SET",
        "status": "REFUSED",
        "verdict": "OUTSIDE_LEVEL_SET",
        "reason": "nonzero_state_outside_zero_level",
        "level": level,
        "certificate": "identity",
        "state_mean": state,
        "quadratic_value": V,
        "quadratic_next": None,
        "decrease": None,
        "margin": margin,
        "proof_status": "NOT_CHECKED",
        "booleans": {
            "inside_level_set": False,
            "decrease_nonnegative": None,
            "margin_positive": False,
        },
        "notes": [
            "Helper level=0 with nonzero retained state → OUTSIDE_LEVEL_SET",
            "Not physical equilibrium; parameter covariance unknown",
            f"PLSR pin {PLSR_COMMIT}",
        ],
    }


def _contour_schematic(case: dict) -> dict:
    """Simple quadratic contour samples for presentation (identity V=x²+y²)."""
    level = case.get("level")
    V = float(case["quadratic_value"])
    # Sample a unit circle scaled by sqrt(V) as the V-level set schematic.
    samples = []
    for k in range(24):
        theta = 2.0 * math.pi * k / 24.0
        r = math.sqrt(max(V, 1e-9))
        samples.append([r * math.cos(theta), r * math.sin(theta)])
    return {
        "kind": "identity_quadratic_contour",
        "level_value": V,
        "requested_level": level,
        "state_mean": case["state_mean"],
        "contour_xy": samples,
        "note": "Presentation contour only — not a solver mesh",
    }


def build_payload() -> dict:
    cases = [_case_numerical_inconclusive(), _case_outside_level_set()]
    for case in cases:
        case["schematic"] = _contour_schematic(case)
    cards = [
        {
            "title": case["label"],
            "status": case["status"],
            "verdict": case["verdict"],
            "quadratic_value": case["quadratic_value"],
            "margin": case["margin"],
            "proof_status": case["proof_status"],
        }
        for case in cases
    ]
    return {
        "schema": "ciw.host-plsr-stability-verdict-render.v1",
        "kind": "plsr-stability-verdict-presentation",
        "source": "HOST_FROM_DOCUMENTED_OUTCOMES",
        "data_source": DATA_SOURCE,
        "claim_scope": "computational-integrity-only",
        "may_authorize": False,
        "operation_id": OPERATION_ID,
        "upstream_status": "HOST_FROM_DOCUMENTED_OUTCOMES",
        "upstream_pins": {
            "plsr_commit": PLSR_COMMIT,
            "readme": str(README.relative_to(REPO)),
        },
        "caption": CAPTION,
        "selected_case_index": 0,
        "cases": cases,
        "cards": cards,
        "presentation_only": True,
        "forbidden_claims": [
            "certified inequality",
            "parameter covariance known",
            "physical equilibrium",
            "fresh proof",
            "state admission",
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
            f"  {case['id']}: verdict={case['verdict']} "
            f"status={case['status']} V={case['quadratic_value']} "
            f"margin={case['margin']} proof={case['proof_status']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
