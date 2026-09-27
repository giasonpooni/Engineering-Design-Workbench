#!/usr/bin/env python3
"""Honest executable-layer attempts for the frozen 10 computational profiles.

Does not mint new CIW kinds, invent VERIFIED/qualified/calibrated, or expand the
9074 catalog. Distinguishes:
  - native/package operation paths (EnergyAccuracyWorkflow / ciw energy replay)
  - HOST synthetic numerics that actually compute (Jacobi, hard reconcile, …)
  - export-only teaching templates (not enough for executable=pass)
  - blocked / unavailable when the required operation or binaries are absent
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"
EVIDENCE_DIR = EXAMPLES / "workflows" / "executable_evidence"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cmd_record(command: list[str], **fields: Any) -> dict[str, Any]:
    return {"command": command, **fields}


def inventory() -> dict[str, Any]:
    ciw_bin = shutil.which("ciw")
    cargo = shutil.which("cargo")
    rustc = shutil.which("rustc")
    sp1 = shutil.which("sp1") or shutil.which("cargo-prove")
    elf_hits = [str(p.relative_to(ROOT)) for p in ROOT.glob("**/sp1-heat.elf")][:5]
    ciw_import = None
    try:
        import ciw  # noqa: WPS433

        ciw_import = getattr(ciw, "__file__", None)
    except Exception as exc:  # noqa: BLE001
        ciw_import = f"IMPORT_FAIL:{exc}"
    pip_editable = None
    try:
        import importlib.metadata as md

        dist = md.distribution("computational-instrumentation-workbench")
        pip_editable = {
            "version": dist.version,
            "locate": str(getattr(dist, "_path", "") or ""),
        }
    except Exception as exc:  # noqa: BLE001
        pip_editable = {"error": str(exc)}
    return {
        "generated_at": _now(),
        "python": sys.executable,
        "ciw_cli": ciw_bin,
        "ciw_import": ciw_import,
        "pip_editable": pip_editable,
        "cargo": bool(cargo),
        "rustc": bool(rustc),
        "sp1_cli": bool(sp1),
        "guest_elf_hits": elf_hits,
        "fluid_volume_operation_present": False,  # never minted in this surface
        "workbench_scripts": {
            "energy_run": str(EXAMPLES / "energy-accuracy" / "run.py"),
            "vfe_run": str(EXAMPLES / "variational-free-energy" / "run.py"),
            "proved_heat_run": str(EXAMPLES / "proved-heat" / "run.py"),
            "check_proved_heat": str(ROOT / "scripts" / "check_proved_heat.py"),
            "check_energy": str(ROOT / "scripts" / "check_energy.py"),
            "check_free_energy": str(ROOT / "scripts" / "check_free_energy.py"),
        },
    }



def _load_emitter(unique_name: str, relative: str):
    """Load an examples/*/emit script under a unique module name (avoid cache clash)."""
    import importlib.util

    path = EXAMPLES / relative
    spec = importlib.util.spec_from_file_location(unique_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load emitter {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def _write_evidence(family: str, name: str, payload: Any) -> str:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / f"{family.lower()}_{name}.json"
    if isinstance(payload, (bytes, bytearray)):
        path.write_bytes(payload)
    else:
        path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    return str(path.relative_to(ROOT))
