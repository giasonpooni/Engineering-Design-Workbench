#!/usr/bin/env python3
"""Emit HOST energy-accuracy teaching presentation for Godot.

Teaching split from in-tree examples/energy-accuracy/ fixtures
(baseline / under-target / missing). Reuses ciw.energy-accuracy.v1 language —
no new CIW kind. Numbers labeled HOST_FROM_PUBLISHED_FIXTURES via analyze().
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
OUT_DEFAULT = ROOT / "results" / "energy_accuracy_render.json"
FIXTURES = REPO / "examples" / "energy-accuracy"

OPERATION_ID = "ciw.energy-accuracy.v1"

DATA_SOURCE = (
    "HOST_FROM_PUBLISHED_FIXTURES: in-tree examples/energy-accuracy/"
    "{baseline,under-target,missing}.json analyzed via ciw.energy_records.analyze. "
    "Synthetic fixtures — not a live GPU/NVML capture."
)

CAPTION = (
    "Synthetic fixtures; no calibrated uncertainty budget or whole-machine energy claim. "
    "Statistical free energy (nats), physical energy (joules), and elapsed time remain separate. "
    "Amortized joules/qualified-solve only when target is met and brackets are complete."
)


def _analyze(fixture_name: str) -> dict:
    """Import analyze lazily so emit still documents the seam if ciw is absent."""
    sys.path.insert(0, str(REPO / "src"))
    from ciw.energy_records import analyze  # noqa: WPS433

    log = json.loads((FIXTURES / fixture_name).read_text(encoding="utf-8"))
    return analyze(log)


def _phase_strip(report: dict) -> list[dict]:
    series: list[dict] = []
    for index, phase in enumerate(report.get("phases", [])):
        energy = phase.get("gross_energy_j")
        series.append(
            {
                "index": index,
                "phase": phase.get("name"),
                "gross_energy_j": float(energy) if energy is not None else 0.0,
                "energy_present": energy is not None,
                "elapsed_s": float(phase.get("elapsed_s", 0.0)),
                "energy_status": phase.get("energy_status", "unknown"),
            }
        )
    return series


def _case_baseline() -> dict:
    report = _analyze("baseline.json")
    measurement = report["measurement"]
    return {
        "id": "baseline-qualified",
        "label": "Baseline · qualified amortized cost",
        "status": "LIVE",
        "native_outcome": "qualified",
        "reason": "target_met_complete_brackets",
        "fixture": "examples/energy-accuracy/baseline.json",
        "log_digest": report.get("log_digest"),
        "origin": report.get("origin"),
        "measurement": {
            "target_kl_nats": measurement["target_kl_nats"],
            "max_kl_nats": measurement["max_kl_nats"],
            "target_met": measurement["target_met"],
            "qualified_solves": measurement["qualified_solves"],
            "total_solves": measurement["total_solves"],
            "gross_energy_j": measurement["gross_energy_j"],
            "amortized_j_per_qualified_solve": measurement[
                "amortized_domain_energy_j_per_qualified_solve"
            ],
        },
        "phase_series": _phase_strip(report),
        "notes": [
            "HOST analyze() of synthetic baseline fixture",
            "target_met with complete endpoint brackets → amortized cost retained",
        ],
    }


def _case_under_target() -> dict:
    report = _analyze("under-target.json")
    measurement = report["measurement"]
    return {
        "id": "under-target-not-met",
        "label": "Under-target · accuracy target not met",
        "status": "REFUSED",
        "native_outcome": "not_qualified",
        "reason": "accuracy_target_not_met_by_every_batch",
        "fixture": "examples/energy-accuracy/under-target.json",
        "log_digest": report.get("log_digest"),
        "origin": report.get("origin"),
        "measurement": {
            "target_kl_nats": measurement["target_kl_nats"],
            "max_kl_nats": measurement["max_kl_nats"],
            "target_met": measurement["target_met"],
            "qualified_solves": measurement["qualified_solves"],
            "total_solves": measurement["total_solves"],
            "gross_energy_j": measurement["gross_energy_j"],
            "amortized_j_per_qualified_solve": measurement[
                "amortized_domain_energy_j_per_qualified_solve"
            ],
        },
        "phase_series": _phase_strip(report),
        "notes": [
            "iterations=0 → KL above target; energy retained but not amortized",
            "Target miss cannot produce joules per qualified solve",
        ],
    }


def _case_missing() -> dict:
    report = _analyze("missing.json")
    measurement = report["measurement"]
    return {
        "id": "missing-endpoint-brackets",
        "label": "Missing · endpoint brackets incomplete",
        "status": "HELD",
        "native_outcome": "not_qualified",
        "reason": "missing_endpoint_brackets",
        "fixture": "examples/energy-accuracy/missing.json",
        "log_digest": report.get("log_digest"),
        "origin": report.get("origin"),
        "measurement": {
            "target_kl_nats": measurement["target_kl_nats"],
            "max_kl_nats": measurement["max_kl_nats"],
            "target_met": measurement["target_met"],
            "qualified_solves": measurement["qualified_solves"],
            "total_solves": measurement["total_solves"],
            "gross_energy_j": measurement["gross_energy_j"],
            "amortized_j_per_qualified_solve": measurement[
                "amortized_domain_energy_j_per_qualified_solve"
            ],
        },
        "phase_series": _phase_strip(report),
        "notes": [
            "Measurement phase lacks final counter read → gross energy null",
            "Invalid coverage yields null energy, not zero",
        ],
    }


def build_payload() -> dict:
    cases = [_case_baseline(), _case_under_target(), _case_missing()]
    cards = [
        {
            "title": case["label"],
            "status": case["status"],
            "native_outcome": case["native_outcome"],
            "reason": case["reason"],
            "amortized_j_per_qualified_solve": case["measurement"][
                "amortized_j_per_qualified_solve"
            ],
            "max_kl_nats": case["measurement"]["max_kl_nats"],
            "gross_energy_j": case["measurement"]["gross_energy_j"],
        }
        for case in cases
    ]
    # Strip across cases: max_kl vs amortized (null → 0 for display, flagged)
    residual_series = []
    for index, case in enumerate(cases):
        m = case["measurement"]
        amortized = m["amortized_j_per_qualified_solve"]
        residual_series.append(
            {
                "index": index,
                "case_id": case["id"],
                "max_kl_nats": float(m["max_kl_nats"]),
                "amortized_j": float(amortized) if amortized is not None else 0.0,
                "amortized_present": amortized is not None,
                "status": case["status"],
            }
        )
    return {
        "schema": "ciw.host-energy-accuracy-teach-render.v1",
        "kind": "energy-accuracy-teach-presentation",
        "source": "HOST_FROM_PUBLISHED_FIXTURES",
        "data_source": DATA_SOURCE,
        "claim_scope": "computational-integrity-only",
        "may_authorize": False,
        "operation_id": OPERATION_ID,
        "upstream_status": "HOST_FROM_PUBLISHED_FIXTURES",
        "references": {
            "fixtures_dir": str(FIXTURES.relative_to(REPO)),
            "docs": "docs/ENERGY_ACCURACY.md",
        },
        "caption": CAPTION,
        "selected_case_index": 0,
        "cases": cases,
        "cards": cards,
        "residual_series": residual_series,
        "schematic": {
            "layout": "phase-energy-strip-plus-cards",
            "note": "Phase energy strip + qualification cards — presentation only",
        },
        "presentation_only": True,
        "forbidden_claims": [
            "calibrated uncertainty budget",
            "whole-machine energy",
            "physical NVML verification",
            "wall-plug energy",
            "hardware authentication",
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
        m = case["measurement"]
        print(
            f"  {case['id']}: status={case['status']} reason={case['reason']} "
            f"max_kl={m['max_kl_nats']} amortized={m['amortized_j_per_qualified_solve']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
