#!/usr/bin/env python3
"""Emit HOST BIM quantity presentation for Godot — reuses ciw.bim-quantity.v1 only.

Teaching numbers from in-tree examples/bim-quantity/README.md and make_source.py.
Disposition vocabulary cited from MCP-read CSE README @ 4b74abda.
No building/Revit render. Does not mint a second BIM operation.
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
OUT_DEFAULT = ROOT / "results" / "cse_bim_render.json"
IFC = REPO / "examples" / "bim-quantity" / "room.ifc"
MAKE_SOURCE = REPO / "examples" / "bim-quantity" / "make_source.py"

CSE_PIN = "4b74abda40bba3277de69bf61e9e09283ae2d5b3"
OPERATION_ID = "ciw.bim-quantity.v1"

DATA_SOURCE = (
    "GitHub MCP read of giasonpooni/Construction-State-Estimator-for-BIM "
    f"README.md + sp1/ listing @ {CSE_PIN}; "
    "+ in-tree examples/bim-quantity/ (room.ifc, make_source.py) and "
    "ciw.bim-quantity.v1. git clone 403; MCP read succeeded. "
    "HOST presentation of published teaching quantities — not a live GatSession."
)

CAPTION = (
    "ACCEPT is recommendation not construction approval; "
    "demo IFC/--demo not field evidence; surveyed geometry separate. "
    "Quantity-only schematic — no building/Revit render."
)


def _qty(name: str, gid: str, unit: str, mean: float, variance: float) -> dict:
    return {
        "quantity": name,
        "global_id": gid,
        "unit": unit,
        "mean": mean,
        "variance": variance,
        "std": variance ** 0.5,
    }


def _case_accepted() -> dict:
    # Documented teaching: prior ClearHeight 3.0 (σ=0.01), obs 2.99 var 2.5e-5
    # → posterior 2.992 var 2e-5; volume 59.84 m³.
    prior = [
        _qty("ClearHeight", "CIWSTOREY00000000000015", "m", 3.0, 0.0001),
        _qty("Volume", "CIWSPACE0000000000001", "m3", 60.0, 0.04),
    ]
    posterior = [
        _qty("ClearHeight", "CIWSTOREY00000000000015", "m", 2.992, 0.00002),
        _qty("Volume", "CIWSPACE0000000000001", "m3", 59.84, 0.008),
    ]
    return {
        "id": "conditioned-accept-recommendation",
        "label": "Conditioned → SATISFIED / ACCEPT recommendation",
        "status": "accepted",
        "reason": "conditioned",
        "disposition": "ACCEPT",
        "criterion_state": "SATISFIED",
        "geometry_authority": "QUANTITY_ONLY",
        "prior": {"quantities": prior, "world_digest": "host-teaching-prior"},
        "posterior": {"quantities": posterior, "world_digest": "host-teaching-posterior"},
        "observation": {
            "value": 2.99,
            "variance": 0.000025,
            "unit": "m",
            "quantity": "ClearHeight",
        },
        "ledger_replay": {
            "accepted": 1,
            "rejected": 0,
            "non_state": 0,
            "present": True,
            "note": "HOST teaching replay counts from docs; not a native ledger",
        },
        "notes": [
            "Teaching posterior ClearHeight 2.992 m / Volume 59.84 m³ from bim-quantity README",
            "ACCEPT is recommendation not construction approval",
        ],
    }


def _case_request_evidence() -> dict:
    prior = [
        _qty("ClearHeight", "CIWSTOREY00000000000015", "m", 3.0, 0.0001),
        _qty("Volume", "CIWSPACE0000000000001", "m3", 60.0, 0.04),
    ]
    return {
        "id": "held-request-evidence",
        "label": "Held → UNRESOLVED / REQUEST_EVIDENCE",
        "status": "held",
        "reason": "unknown_cross_covariance",
        "disposition": "REQUEST_EVIDENCE",
        "criterion_state": "UNRESOLVED",
        "geometry_authority": "QUANTITY_ONLY",
        "prior": {"quantities": prior, "world_digest": "host-teaching-prior"},
        "posterior": {"quantities": prior, "world_digest": "host-teaching-prior"},
        "observation": {
            "value": 2.99,
            "variance": 0.000025,
            "unit": "m",
            "quantity": "ClearHeight",
            "cross_covariance_policy": "unknown",
        },
        "ledger_replay": {
            "accepted": 0,
            "rejected": 0,
            "non_state": 0,
            "present": True,
            "note": "Held path: unchanged world; genesis-only ledger topology",
        },
        "notes": [
            "Unknown cross-covariance → held; REQUEST_EVIDENCE disposition",
            "demo IFC/--demo not field evidence",
        ],
    }


def _case_violated() -> dict:
    prior = [
        _qty("ClearHeight", "CIWSTOREY00000000000015", "m", 3.0, 0.0001),
        _qty("Volume", "CIWSPACE0000000000001", "m3", 60.0, 0.04),
    ]
    return {
        "id": "refused-violated",
        "label": "Refused → VIOLATED / REJECT",
        "status": "refused",
        "reason": "invariant_rejection",
        "disposition": "REJECT",
        "criterion_state": "VIOLATED",
        "geometry_authority": "QUANTITY_ONLY",
        "prior": {"quantities": prior, "world_digest": "host-teaching-prior"},
        "posterior": {"quantities": prior, "world_digest": "host-teaching-prior"},
        "observation": {
            "value": -0.5,
            "variance": 0.000025,
            "unit": "m",
            "quantity": "ClearHeight",
            "note": "Negative height violates native constraints (teaching)",
        },
        "ledger_replay": {
            "accepted": 0,
            "rejected": 1,
            "non_state": 0,
            "present": True,
            "note": "Replayable rejected event; prior preserved",
        },
        "notes": [
            "Invariant rejection → refused; VIOLATED criterion → REJECT disposition",
            "surveyed geometry remains separate from QUANTITY_ONLY",
        ],
    }


def build_payload() -> dict:
    return {
        "schema": "ciw.host-bim-quantity-render.v1",
        "kind": "cse-bim-quantity-presentation",
        "source": "HOST / published teaching quantities",
        "data_source": DATA_SOURCE,
        "claim_scope": "computational-integrity-only",
        "may_authorize": False,
        "operation_id": OPERATION_ID,
        "upstream_status": "HOST_TEACHING_FROM_PUBLISHED_BIM_QUANTITY",
        "upstream_pins": {
            "cse_revision": CSE_PIN,
            "note": DATA_SOURCE,
        },
        "references": {
            "in_tree_ifc": str(IFC.relative_to(REPO)),
            "in_tree_make_source": str(MAKE_SOURCE.relative_to(REPO)),
            "upstream_sp1_cite": "examples/cse-bim-quantity/upstream/sp1/",
        },
        "caption": CAPTION,
        "selected_case_index": 0,
        "cases": [_case_accepted(), _case_request_evidence(), _case_violated()],
        "schematic": {
            "layout": "quantity-bars",
            "quantities": ["ClearHeight", "Volume"],
            "bar_axis": "y",
            "note": "Schematic quantity bars only — no building/Revit mesh",
        },
        "presentation_only": True,
        "forbidden_claims": [
            "construction approval",
            "field evidence",
            "surveyed geometry authority",
            "building render",
            "Revit render",
            "second bim-quantity operation",
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
            f"  {case['id']}: status={case['status']} "
            f"criterion={case['criterion_state']} disposition={case['disposition']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
