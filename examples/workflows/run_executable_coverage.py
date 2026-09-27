#!/usr/bin/env python3
"""Run strongest honest executable coverage for the frozen 10 profiles.

Regenerates coverage_report.md/.json via build_coverage_report.py --attempt-execute
when available; otherwise overlays attempts via _bcr_attempt_shim.apply().
Does not create usecase folders, mint CIW kinds, or invent VERIFIED/qualified/calibrated.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = Path(__file__).resolve().parent


def main() -> int:
    sys.path.insert(0, str(WORKFLOWS))
    from executable_attempts import attempt_all, inventory
    from build_coverage_report import main as build_main
    import build_coverage_report as bcr

    inv = inventory()
    print(json.dumps({"phase": "inventory", **{k: inv[k] for k in (
        "python", "ciw_cli", "ciw_import", "cargo", "rustc", "sp1_cli", "guest_elf_hits"
    )}}, indent=2))
    attempts = attempt_all()
    summary = {
        family: result["layers"]
        for family, result in (attempts.get("attempts") or {}).items()
    }
    print(json.dumps({"phase": "attempts", "layers": summary, "path": attempts.get("attempts_path")}, indent=2))

    supports_flag = "--attempt-execute" in Path(bcr.__file__).read_text(encoding="utf-8")
    if supports_flag:
        rc = build_main(["--attempt-execute"])
    else:
        try:
            rc = build_main()
        except TypeError:
            rc = build_main([])
        from _bcr_attempt_shim import apply as overlay_apply

        overlay_apply()
        print(json.dumps({"phase": "attempt_overlay", "via": "_bcr_attempt_shim"}, indent=2))

    report = json.loads((WORKFLOWS / "coverage_report.json").read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "phase": "coverage_report",
                "returncode": rc,
                "layer_counts": report.get("layer_counts_representatives"),
                "attempt_execute": report.get("attempt_execute"),
                "failures": report.get("summary", {}).get("failures"),
                "supports_attempt_execute_flag": supports_flag,
            },
            indent=2,
        )
    )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
