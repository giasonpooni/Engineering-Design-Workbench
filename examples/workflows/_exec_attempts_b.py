"""Executable attempt implementations (part B)."""
from __future__ import annotations

import json
from pathlib import Path
import math
import subprocess
import sys
import time
import traceback
from typing import Any

from _exec_attempts_helpers import (
    EXAMPLES,
    EVIDENCE_DIR,
    ROOT,
    _cmd_record,
    _load_emitter,
    _write_evidence,
    inventory,
)
def attempt_residual_host() -> dict[str, Any]:
    """HOST CUSUM accumulation on synthetic windows (not native FDIR/OIT)."""
    started = time.monotonic()
    try:
        residual = _load_emitter("cov_residual_emit", "residual-cusum-teach/emit_render.py")

        quiet = residual._case_quiet()
        crossing = residual._case_crossing()
        held = residual._case_oit_held()
        threshold = float(residual.CUSUM_THRESHOLD)
        # Recompute teaching CUSUM update: max(0, s + abs(r) - 0.15)
        residuals = crossing["normalized_residuals"]
        s = 0.0
        series = []
        for r in residuals:
            s = max(0.0, s + abs(float(r)) - 0.15)
            series.append(round(s, 4))
        peak = max(series) if series else 0.0
        crossed = peak >= threshold and bool(crossing.get("crossed"))
        series_match = series == crossing["cusum"]
        held_cusum = held["cusum"]
        held_frozen = len(set(held_cusum)) == 1 and held.get("advances_cusum") is False
        ep = _write_evidence(
            "RESIDUAL_CUSUM",
            "host_cusum",
            {
                "path_class": "HOST_synthetic_CUSUM",
                "quiet_id": quiet["id"],
                "crossing_id": crossing["id"],
                "oit_held_id": held["id"],
                "recomputed_series": series,
                "emit_series": crossing["cusum"],
                "series_match": series_match,
                "independent_peak": peak,
                "crossed_threshold": crossed,
                "oit_held_frozen": held_frozen,
                "threshold": threshold,
            },
        )
        ok = crossed and held_frozen and series_match
        return {
            "family": "RESIDUAL_CUSUM",
            "path_class": "HOST_synthetic_CUSUM",
            "operation_id": "ciw.residual-monitor.v1",
            "layers": {
                "executable": "pass" if ok else "fail",
                "numerical": "pass" if ok else "fail",
                "checking": "pass" if ok else "fail",
                "replay": "pass" if ok else "fail",
            },
            "commands": [
                _cmd_record(
                    [
                        "python3",
                        "-c",
                        "residual-cusum-teach CUSUM accumulation (HOST synthetic)",
                    ],
                    returncode=0 if ok else 1,
                    stdout_tail=json.dumps(
                        {
                            "peak": peak,
                            "crossed": crossed,
                            "oit_held_frozen": held_frozen,
                            "evidence": ep,
                        }
                    ),
                    stderr_tail="",
                    elapsed_s=round(time.monotonic() - started, 3),
                    status="pass" if ok else "fail",
                )
            ],
            "evidence": [ep],
            "blocker": None if ok else "residual_host_cusum_failed",
            "note": (
                "HOST synthetic ordered-window CUSUM; native FDIR/OIT residual-monitor "
                "session NOT invoked."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "family": "RESIDUAL_CUSUM",
            "path_class": "HOST_synthetic_CUSUM",
            "operation_id": "ciw.residual-monitor.v1",
            "layers": {
                "executable": "fail",
                "numerical": "fail",
                "checking": "fail",
                "replay": "not_run",
            },
            "commands": [
                _cmd_record(
                    ["residual_host"],
                    returncode=1,
                    stdout_tail="",
                    stderr_tail=str(exc),
                    elapsed_s=round(time.monotonic() - started, 3),
                    status="fail",
                )
            ],
            "evidence": [],
            "blocker": str(exc),
            "note": "RESIDUAL_CUSUM HOST attempt raised",
        }


def attempt_plsr_host() -> dict[str, Any]:
    """HOST identity-certificate quadratic form (not live PLSR evaluate)."""
    started = time.monotonic()
    try:
        plsr = _load_emitter("cov_plsr_emit", "plsr-stability-verdict/emit_render.py")

        incon = plsr._case_numerical_inconclusive()
        outside = plsr._case_outside_level_set()
        # Independent check of identity certificate V = x·x
        state = incon["state_mean"]
        V = state[0] ** 2 + state[1] ** 2
        v_ok = abs(V - float(incon["quadratic_value"])) < 1e-15
        margin_ok = float(incon["margin"]) == 0.0
        outside_ok = outside["verdict"] == "OUTSIDE_LEVEL_SET"
        contour = plsr._contour_schematic(outside)
        samples = contour.get("contour_xy") or []
        ep = _write_evidence(
            "PLSR",
            "host_quadratic",
            {
                "path_class": "HOST_ANALOG_identity_certificate",
                "V": V,
                "documented_V": incon["quadratic_value"],
                "v_ok": v_ok,
                "margin_ok": margin_ok,
                "outside_verdict": outside["verdict"],
                "contour_samples": len(samples),
                "proof_status": incon.get("proof_status"),
            },
        )
        ok = v_ok and margin_ok and outside_ok and incon.get("proof_status") == "NOT_CHECKED"
        return {
            "family": "PLSR",
            "path_class": "HOST_ANALOG_identity_certificate",
            "operation_id": "ciw.identified-stability.v1",
            "layers": {
                "executable": "pass" if ok else "fail",
                "numerical": "pass" if ok else "fail",
                "checking": "pass" if ok else "fail",
                "replay": "pass" if ok else "fail",
            },
            "commands": [
                _cmd_record(
                    [
                        "python3",
                        "-c",
                        "plsr-stability-verdict identity certificate HOST analog",
                    ],
                    returncode=0 if ok else 1,
                    stdout_tail=json.dumps(
                        {
                            "V": V,
                            "verdicts": [incon["verdict"], outside["verdict"]],
                            "proof_status": incon.get("proof_status"),
                            "evidence": ep,
                        }
                    ),
                    stderr_tail="",
                    elapsed_s=round(time.monotonic() - started, 3),
                    status="pass" if ok else "fail",
                )
            ],
            "evidence": [ep],
            "blocker": None if ok else "plsr_host_failed",
            "note": (
                "HOST analog of documented PLSR teaching outcomes; optional PLSR package "
                "not installed; native identified-stability session NOT invoked; "
                "proof_status remains NOT_CHECKED."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "family": "PLSR",
            "path_class": "HOST_ANALOG_identity_certificate",
            "operation_id": "ciw.identified-stability.v1",
            "layers": {
                "executable": "fail",
                "numerical": "fail",
                "checking": "fail",
                "replay": "not_run",
            },
            "commands": [
                _cmd_record(
                    ["plsr_host"],
                    returncode=1,
                    stdout_tail="",
                    stderr_tail=str(exc),
                    elapsed_s=round(time.monotonic() - started, 3),
                    status="fail",
                )
            ],
            "evidence": [],
            "blocker": str(exc),
            "note": "PLSR HOST attempt raised",
        }


def attempt_cse_template() -> dict[str, Any]:
    """CSE teaching emit is templated posteriors — not executable numerics."""
    started = time.monotonic()
    try:
        cse = _load_emitter("cov_cse_emit", "cse-bim-quantity/emit_render.py")

        payload = cse.build_payload()
        cases = payload.get("cases") or []
        # Confirm hardcoded teaching numbers only (std = sqrt(var) is trivial)
        accepted = next(c for c in cases if c.get("id") == "conditioned-accept-recommendation")
        std_check = all(
            abs(q["std"] - math.sqrt(q["variance"])) < 1e-15
            for q in accepted["posterior"]["quantities"]
        )
        ep = _write_evidence(
            "CSE",
            "template_only",
            {
                "path_class": "HOST_teaching_template_no_conditioning",
                "case_ids": [c.get("id") for c in cases],
                "std_from_variance_ok": std_check,
                "live_gat_session": False,
                "ifc_present": (EXAMPLES / "bim-quantity" / "room.ifc").is_file(),
            },
        )
        return {
            "family": "CSE",
            "path_class": "HOST_teaching_template_no_conditioning",
            "operation_id": "ciw.bim-quantity.v1",
            "layers": {
                "executable": "not_run",
                "numerical": "not_run",
                "checking": "pass" if std_check else "fail",
                "replay": "not_run",
            },
            "commands": [
                _cmd_record(
                    [
                        "python3",
                        "-c",
                        "cse-bim-quantity.build_payload (template only; no GatSession)",
                    ],
                    returncode=0,
                    stdout_tail=json.dumps(
                        {
                            "cases": [c.get("id") for c in cases],
                            "evidence": ep,
                            "reason": "published teaching posteriors hardcoded; no live conditioning",
                        }
                    ),
                    stderr_tail="",
                    elapsed_s=round(time.monotonic() - started, 3),
                    status="not_run",
                ),
                _cmd_record(
                    ["ciw", "operation.execute", "ciw.bim-quantity.v1"],
                    returncode=None,
                    stdout_tail="CSE provider / GatSession not bound in this box",
                    stderr_tail="",
                    elapsed_s=0.0,
                    status="not_run",
                ),
            ],
            "evidence": [ep],
            "blocker": "native_session_ciw.bim-quantity.v1_not_invoked",
            "note": (
                "Teaching emit uses hardcoded published posteriors; sqrt(variance) only. "
                "Not counted as scientific executable numerics."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "family": "CSE",
            "path_class": "HOST_teaching_template_no_conditioning",
            "operation_id": "ciw.bim-quantity.v1",
            "layers": {
                "executable": "not_run",
                "numerical": "not_run",
                "checking": "fail",
                "replay": "not_run",
            },
            "commands": [
                _cmd_record(
                    ["cse_template"],
                    returncode=1,
                    stdout_tail="",
                    stderr_tail=str(exc),
                    elapsed_s=round(time.monotonic() - started, 3),
                    status="fail",
                )
            ],
            "evidence": [],
            "blocker": str(exc),
            "note": "CSE template inspection raised",
        }


def attempt_measurement_chain_template() -> dict[str, Any]:
    """Measurement-chain teaching is schematic stages — not native RCI/FSRT/JSPT."""
    started = time.monotonic()
    try:
        mc = _load_emitter("cov_mc_emit", "measurement-chain-teach/emit_render.py")

        payload = mc.build_payload()
        stages = payload.get("stages") or []
        ep = _write_evidence(
            "MEASUREMENT_CHAIN",
            "schematic_only",
            {
                "path_class": "HOST_SYNTHETIC_schematic_stages",
                "stage_ids": [s.get("id") for s in stages],
                "native_verified": False,
            },
        )
        return {
            "family": "MEASUREMENT_CHAIN",
            "path_class": "HOST_SYNTHETIC_schematic_stages",
            "operation_id": "ciw.measurement-chain.v1",
            "layers": {
                "executable": "not_run",
                "numerical": "not_run",
                "checking": "pass" if stages else "fail",
                "replay": "not_run",
            },
            "commands": [
                _cmd_record(
                    [
                        "python3",
                        "-c",
                        "measurement-chain-teach.build_payload (schematic; no native chain)",
                    ],
                    returncode=0,
                    stdout_tail=json.dumps(
                        {"stages": [s.get("id") for s in stages], "evidence": ep}
                    ),
                    stderr_tail="",
                    elapsed_s=round(time.monotonic() - started, 3),
                    status="not_run",
                ),
                _cmd_record(
                    ["ciw", "operation.execute", "ciw.measurement-chain.v1"],
                    returncode=None,
                    stdout_tail="RCI/FSRT/JSPT stack not bound in this box",
                    stderr_tail="",
                    elapsed_s=0.0,
                    status="not_run",
                ),
            ],
            "evidence": [ep],
            "blocker": "native_session_ciw.measurement-chain.v1_not_invoked",
            "note": (
                "HOST schematic stage cards only; native measurement-chain investigation "
                "NOT invoked; native results stay not_verified."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "family": "MEASUREMENT_CHAIN",
            "path_class": "HOST_SYNTHETIC_schematic_stages",
            "operation_id": "ciw.measurement-chain.v1",
            "layers": {
                "executable": "not_run",
                "numerical": "not_run",
                "checking": "fail",
                "replay": "not_run",
            },
            "commands": [
                _cmd_record(
                    ["measurement_chain_template"],
                    returncode=1,
                    stdout_tail="",
                    stderr_tail=str(exc),
                    elapsed_s=round(time.monotonic() - started, 3),
                    status="fail",
                )
            ],
            "evidence": [],
            "blocker": str(exc),
            "note": "MEASUREMENT_CHAIN template inspection raised",
        }


def attempt_proved_heat() -> dict[str, Any]:
    """SP1/proved-heat: unavailable without bound binaries; never fake VERIFIED."""
    started = time.monotonic()
    inv = inventory()
    scientific = "unavailable"
    reason = "host_binaries_absent_or_unbound"
    if inv["guest_elf_hits"] and inv["sp1_cli"]:
        scientific = "not_run"
        reason = "elf_present_but_fresh_verify_not_invoked"
    # Run check_proved_heat.py --help only; full gate needs --scr-repo etc.
    help_rc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_proved_heat.py"), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    # Confirm teaching refuse cases contain no VERIFIED
    ph = _load_emitter("cov_proved_heat_emit", "proved-heat/emit_proof_render.py")

    payload = ph.build_payload()
    case_ids = [c.get("id") for c in (payload.get("cases") or [])]
    verified_present = any(
        (c.get("proof_status") == "VERIFIED")
        or (c.get("status") == "VERIFIED")
        or (c.get("card_status") == "VERIFIED")
        for c in (payload.get("cases") or [])
    )
    ep = _write_evidence(
        "PROVED_HEAT",
        "unavailable",
        {
            "scientific_execution": scientific,
            "reason": reason,
            "sp1_cli": inv["sp1_cli"],
            "guest_elf_hits": inv["guest_elf_hits"],
            "case_ids": case_ids,
            "verified_present": verified_present,
            "check_proved_heat_help_rc": help_rc.returncode,
        },
    )
    return {
        "family": "PROVED_HEAT",
        "path_class": "sp1_binaries_gate",
        "operation_id": "ciw.proved-heat.v1",
        "layers": {
            "executable": scientific,
            "numerical": "unavailable",
            "checking": "pass" if (not verified_present and help_rc.returncode == 0) else "fail",
            "replay": "unavailable",
        },
        "commands": [
            _cmd_record(
                ["scripts/check_proved_heat.py", "--help"],
                returncode=help_rc.returncode,
                stdout_tail=(help_rc.stdout or "")[-300:],
                stderr_tail=(help_rc.stderr or "")[-200:],
                elapsed_s=round(time.monotonic() - started, 3),
                status="pass" if help_rc.returncode == 0 else "fail",
            ),
            _cmd_record(
                ["scripts/check_proved_heat.py", "(not invoked — binaries/providers unbound)"],
                returncode=None,
                stdout_tail=json.dumps(
                    {
                        "scientific_execution": scientific,
                        "reason": reason,
                        "evidence": ep,
                        "verified_present": verified_present,
                    }
                ),
                stderr_tail="",
                elapsed_s=0.0,
                status=scientific,
            ),
        ],
        "evidence": [ep],
        "blocker": "PROVED_HEAT_SP1_binaries_or_fresh_verify_unavailable",
        "note": (
            "SP1 CLI / guest ELF unbound; scientific execution unavailable; "
            "teaching refuse cases present; no VERIFIED invented."
        ),
    }

