#!/usr/bin/env python3
"""Honest executable-layer attempts for the frozen 10 computational profiles.

See _exec_attempts_a / _exec_attempts_b for per-profile implementations.
"""
from __future__ import annotations

import json
from typing import Any

from _exec_attempts_a import (
    attempt_csg_host,
    attempt_energy_accuracy,
    attempt_fsrt_host,
    attempt_gte_host,
    attempt_vfe,
    inventory,
    EVIDENCE_DIR,
    ROOT,
    _now,
)
from _exec_attempts_b import (
    attempt_cse_template,
    attempt_measurement_chain_template,
    attempt_plsr_host,
    attempt_proved_heat,
    attempt_residual_host,
)

ATTEMPTERS = {
    "ENERGY_ACCURACY": attempt_energy_accuracy,
    "VFE": attempt_vfe,
    "CSG": attempt_csg_host,
    "FSRT": attempt_fsrt_host,
    "GTE_CIRCLE": attempt_gte_host,
    "RESIDUAL_CUSUM": attempt_residual_host,
    "PLSR": attempt_plsr_host,
    "CSE": attempt_cse_template,
    "MEASUREMENT_CHAIN": attempt_measurement_chain_template,
    "PROVED_HEAT": attempt_proved_heat,
}


def attempt_all() -> dict[str, Any]:
    inv = inventory()
    results: dict[str, dict[str, Any]] = {}
    for family, fn in ATTEMPTERS.items():
        results[family] = fn()
    doc = {
        "schema": "executable-coverage-attempts.v1",
        "generated_at": _now(),
        "inventory": inv,
        "attempts": results,
        "freeze": {"max_catalog_dirs": 9074, "no_new_ciw_kinds": True},
        "non_claims": [
            "No false qualified/proved/calibrated/VERIFIED",
            "ESM remains cite_only without artifact bindings",
            "FSRT executable remains blocked (no ciw.fluid-volume.v1)",
            "HOST synthetic numerics ≠ native provider session",
        ],
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    out = EVIDENCE_DIR / "attempts.json"
    out.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    doc["attempts_path"] = str(out.relative_to(ROOT))
    return doc


if __name__ == "__main__":
    print(json.dumps(attempt_all(), indent=2, default=str))
