#!/usr/bin/env python3
"""Orchestrate existing SP1 / proved-heat teaching emitters only.

Coverage layer this script can satisfy: **export** (render JSON).
It does NOT satisfy scientific execution, fresh verification, replay, tamper
rejection, or ESM capture. Those require pinned binaries + gate / verify paths
in examples/workflows/05_sp1_verifiable_experiment.md.

Calls:
  - examples/proved-heat/emit_proof_render.py
  - examples/usecase-thermal-proof-gate/emit_render.py

Does not mint proofs, guest ELFs, verification reports, or ciw.proved-heat.v2.
Pins and refuse/unavailable cases come from those emitters and docs/PROVED_HEAT.md.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EMITTERS = (
    REPO / "examples" / "proved-heat" / "emit_proof_render.py",
    REPO / "examples" / "usecase-thermal-proof-gate" / "emit_render.py",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print emitter paths without running them",
    )
    args = parser.parse_args()
    if args.dry_run:
        for emitter in EMITTERS:
            print(f"dry-run {emitter.relative_to(REPO)}")
        print(
            "dry-run=true layer_export=not_run "
            "layer_scientific_execution=not_run "
            "fake_proofs=false"
        )
        return 0

    failures: list[str] = []
    for emitter in EMITTERS:
        if not emitter.is_file():
            failures.append(f"missing {emitter.relative_to(REPO)}")
            continue
        rel = emitter.relative_to(REPO)
        result = subprocess.run(
            [sys.executable, str(emitter)],
            cwd=REPO,
            text=True,
        )
        if result.returncode:
            failures.append(f"{rel}: exit {result.returncode}")
        else:
            print(f"ok {rel}")
    if failures:
        print("failures:")
        for item in failures:
            print(f"- {item}")
        print(
            "layer_export=fail "
            "layer_scientific_execution=not_run "
            "layer_fresh_verify=not_run "
            "layer_replay=not_run "
            "layer_tamper=not_run "
            "layer_esm=cite_only"
        )
        return 1
    print(
        "orchestrated=2 emitters=proved-heat,usecase-thermal-proof-gate "
        "operation=ciw.proved-heat.v1 fake_proofs=false "
        "layer_export=pass "
        "layer_scientific_execution=not_run "
        "layer_fresh_verify=not_run "
        "layer_replay=not_run "
        "layer_tamper=not_run "
        "layer_esm=cite_only "
        "note=run scripts/check_proved_heat.py for execution+verify+tamper"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
