#!/usr/bin/env python3
"""Orchestrate existing SP1 / proved-heat teaching emitters only.

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
    failures: list[str] = []
    for emitter in EMITTERS:
        if not emitter.is_file():
            failures.append(f"missing {emitter.relative_to(REPO)}")
            continue
        rel = emitter.relative_to(REPO)
        if args.dry_run:
            print(f"dry-run {rel}")
            continue
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
        return 1
    print(
        "orchestrated=2 emitters=proved-heat,usecase-thermal-proof-gate "
        "operation=ciw.proved-heat.v1 fake_proofs=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
