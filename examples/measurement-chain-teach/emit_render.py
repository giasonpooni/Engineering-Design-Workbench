#!/usr/bin/env python3
"""Emit HOST measurement-chain teaching presentation for Godot.

Teaching from examples/measurement-chain/ + RCI/FSRT/JSPT language in
docs/RECONCILIATION.md. Two-node schematic + stage cards
(raw → calibrated → estimate → reconcile). Clearly HOST_SYNTHETIC —
no second FSRT solver. No new CIW kind.
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
OUT_DEFAULT = ROOT / "results" / "measurement_chain_render.json"
SOURCE = REPO / "examples" / "measurement-chain" / "source.json"

OPERATION_LANGUAGE = "RCI calibrate.v2 → FSRT snapshot → JSPT covariance (measurement-chain-testbed)"

DATA_SOURCE = (
    "HOST_SYNTHETIC: examples/measurement-chain/source.json assembling "
    "examples/adapters/two-reservoir-covariance.json and "
    "examples/adapters/tank-covariance-map.json. Software fixtures — not "
    "device data or physical calibration certificates. No second FSRT solver."
)

CAPTION = (
    "HOST_SYNTHETIC measurement-chain-testbed. Raw bytes, calibrated quantities, "
    "estimates and reconciliation remain distinct identities. Native results keep "
    "not_verified status; no GSIE fusion state or physical traceability. "
    "Viewport does not run RCI/FSRT/JSPT."
)


def _stages() -> list[dict]:
    """Teaching stage cards — vocabulary from docs/RECONCILIATION.md."""
    return [
        {
            "id": "raw",
            "label": "Raw",
            "status": "LIVE",
            "identity": "raw_record",
            "ops_language": "retained simultaneous records (adapter request)",
            "notes": [
                "Original raw JSON bytes remain base64 encoded and unchanged",
                "Distinct raw identity from calibrated / estimation identities",
            ],
        },
        {
            "id": "calibrated",
            "label": "Calibrated",
            "status": "LIVE",
            "identity": "calibrated_quantity",
            "ops_language": "rci.calibrate.v2",
            "notes": [
                "Synthetic scale/zero with declared parameter covariance",
                "Not a physical calibration certificate",
            ],
        },
        {
            "id": "estimate",
            "label": "Estimate",
            "status": "HISTORICAL",
            "identity": "estimation_result",
            "ops_language": "FSRT v2 snapshot investigation",
            "notes": [
                "Native FSRT result identity retained separately",
                "proof / verification status: not_verified",
            ],
        },
        {
            "id": "reconcile",
            "label": "Reconcile",
            "status": "RECONCILED",
            "identity": "reconciled_covariance",
            "ops_language": "FSRT reconcile + JSPT covariance propagation",
            "notes": [
                "Held FSRT reconciliation remains held",
                "JSPT Jacobian and output reference are caller declarations",
            ],
        },
    ]


def _nodes_from_source(source: dict) -> list[dict]:
    """Two-node schematic from investigation sensors (presentation levels only)."""
    investigation = source.get("investigation", {})
    sensors = investigation.get("sensors", [])
    nodes: list[dict] = []
    # Teaching display levels — HOST schematic, not solver mass.
    defaults = [
        {"name": "tank-1", "level": 0.62, "original": 0.70},
        {"name": "tank-2", "level": 0.48, "original": 0.55},
    ]
    for index, default in enumerate(defaults):
        name = default["name"]
        if index < len(sensors) and isinstance(sensors[index], dict):
            name = str(sensors[index].get("name", name))
        nodes.append(
            {
                "name": name,
                "level": default["level"],
                "original": default["original"],
                "note": "HOST schematic level — not a physical mass",
            }
        )
    return nodes


def build_payload() -> dict:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    stages = _stages()
    nodes = _nodes_from_source(source)
    config = source.get("configuration", {})
    cards = [
        {
            "title": stage["label"],
            "status": stage["status"],
            "identity": stage["identity"],
            "ops_language": stage["ops_language"],
        }
        for stage in stages
    ]
    # Stage strip: ordinal progression raw→…→reconcile for strip projector
    residual_series = [
        {
            "index": index,
            "stage_id": stage["id"],
            "stage_ordinal": float(index),
            "status": stage["status"],
        }
        for index, stage in enumerate(stages)
    ]
    return {
        "schema": "ciw.host-measurement-chain-teach-render.v1",
        "kind": "measurement-chain-teach-presentation",
        "source": "HOST_SYNTHETIC",
        "data_source": DATA_SOURCE,
        "claim_scope": "computational-integrity-only",
        "may_authorize": False,
        "operation_language": OPERATION_LANGUAGE,
        "upstream_status": "HOST_SYNTHETIC",
        "references": {
            "source": str(SOURCE.relative_to(REPO)),
            "docs": "docs/RECONCILIATION.md",
            "example_readme": "examples/measurement-chain/README.md",
        },
        "caption": CAPTION,
        "experiment_id": source.get("experiment_id"),
        "configuration": {
            "scope": config.get("scope", "measurement-chain-testbed"),
            "state_admission": config.get("state_admission", "not_performed"),
            "gsie_fusion": config.get("gsie_fusion", "not_performed"),
            "physical_traceability": config.get(
                "physical_traceability", "not_established"
            ),
        },
        "selected_stage_index": 0,
        "stages": stages,
        "nodes": nodes,
        "cards": cards,
        "residual_series": residual_series,
        "schematic": {
            "layout": "two-node-plus-stage-cards",
            "residual_norm": 0.22,
            "note": "Two-node HOST schematic + stage cards — no second FSRT solver",
        },
        "presentation_only": True,
        "forbidden_claims": [
            "physical calibration certificate",
            "device data",
            "GSIE fusion state",
            "physical traceability",
            "state admission",
            "second FSRT solver",
            "verified Jacobian",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT_DEFAULT)
    args = parser.parse_args()
    payload = build_payload()
    _shared_write_render(args.output, payload)
    print(f"wrote {args.output}")
    for stage in payload["stages"]:
        print(
            f"  {stage['id']}: status={stage['status']} "
            f"identity={stage['identity']} ops={stage['ops_language']}"
        )
    print(f"  nodes: {[n['name'] for n in payload['nodes']]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
