"""CSG/FSRT/GTE HOST attempt implementations."""
from __future__ import annotations

import json
from pathlib import Path
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
)

def attempt_csg_host() -> dict[str, Any]:
    """HOST constant-curvature Jacobi strip (not native ciw.curved-path-transfer session)."""
    started = time.monotonic()
    try:
        csg = _load_emitter("cov_csg_emit", "csg-path-sensitivity/emit_render.py")

        baseline = json.loads(
            (EXAMPLES / "curved-path-study" / "baseline.json").read_text(encoding="utf-8")
        )
        arclength = [float(s) for s in baseline["arclength"]]
        curvature = float(baseline["gaussian_curvature"])
        pert = [float(v) for v in baseline["initial_perturbation"]]
        path = csg._sample_path(arclength, curvature)
        norms = csg._jacobi_norms(arclength, curvature, pert[0], pert[1])
        strip = csg._sensitivity_strip(path, norms)
        path_length = arclength[-1] - arclength[0]
        flat_end = abs(pert[0] + pert[1] * path_length)
        curved_end = norms[-1]
        residual = abs(curved_end - flat_end)
        # checks
        checks = []
        if len(path) != len(arclength):
            checks.append("path_len_mismatch")
        if len(norms) != len(arclength):
            checks.append("norms_len_mismatch")
        if not all(n >= 0 for n in norms):
            checks.append("negative_norm")
        if residual < 0:
            checks.append("negative_residual")
        # recompute once for replay
        norms2 = csg._jacobi_norms(arclength, curvature, pert[0], pert[1])
        replay_ok = norms2 == norms
        evidence = {
            "path_class": "HOST_SYNTHETIC_Jacobi_strip",
            "points": len(path),
            "path_length": path_length,
            "curvature": curvature,
            "declared_residual": residual,
            "strip_points": len(strip),
            "peak_norm": max(norms) if norms else None,
            "replay_identical": replay_ok,
        }
        ep = _write_evidence("CSG", "host_jacobi", evidence)
        ok = not checks and replay_ok and len(path) > 0
        return {
            "family": "CSG",
            "path_class": "HOST_SYNTHETIC_Jacobi_strip",
            "operation_id": "ciw.curved-path-transfer.v1",
            "layers": {
                "executable": "pass" if ok else "fail",
                "numerical": "pass" if ok else "fail",
                "checking": "pass" if ok else "fail",
                "replay": "pass" if replay_ok else "fail",
            },
            "commands": [
                _cmd_record(
                    [
                        "python3",
                        "-c",
                        "csg-path-sensitivity._jacobi_norms+_sample_path (HOST)",
                    ],
                    returncode=0 if ok else 1,
                    stdout_tail=json.dumps({**evidence, "evidence": ep, "issues": checks}),
                    stderr_tail="",
                    elapsed_s=round(time.monotonic() - started, 3),
                    status="pass" if ok else "fail",
                )
            ],
            "evidence": [ep],
            "blocker": None
            if ok
            else "host_jacobi_failed",
            "note": (
                "HOST synthetic constant-curvature Jacobi strip from published baseline; "
                "native CSG provider / workbench curved-path-transfer session NOT invoked."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "family": "CSG",
            "path_class": "HOST_SYNTHETIC_Jacobi_strip",
            "operation_id": "ciw.curved-path-transfer.v1",
            "layers": {
                "executable": "fail",
                "numerical": "fail",
                "checking": "fail",
                "replay": "not_run",
            },
            "commands": [
                _cmd_record(
                    ["csg_host_jacobi"],
                    returncode=1,
                    stdout_tail="",
                    stderr_tail=str(exc),
                    elapsed_s=round(time.monotonic() - started, 3),
                    status="fail",
                )
            ],
            "evidence": [],
            "blocker": str(exc),
            "note": "CSG HOST attempt raised",
        }


def attempt_fsrt_host() -> dict[str, Any]:
    """HOST hard reconcile numerics; executable stays blocked (no fluid-volume.v1)."""
    started = time.monotonic()
    try:
        fsrt = _load_emitter("cov_fsrt_emit", "fsrt-two-reservoir/emit_render.py")

        threshold = fsrt._chi2_threshold()
        cases = []
        for label, values in (
            ("agree", [49.0, 51.0]),
            ("small", [48.0, 51.0]),
            ("large-disagreement-held", [30.0, 30.0]),
        ):
            stat = fsrt._consistency_stat(values)
            hold = stat > threshold
            result = fsrt._hard_reconcile(
                values, hold=hold, threshold=threshold, stat=stat
            )
            cases.append({"label": label, "stat": stat, "hold": hold, "result": result})
        # replay identical
        replay = []
        for label, values in (
            ("agree", [49.0, 51.0]),
            ("small", [48.0, 51.0]),
            ("large-disagreement-held", [30.0, 30.0]),
        ):
            stat = fsrt._consistency_stat(values)
            hold = stat > threshold
            replay.append(
                fsrt._hard_reconcile(values, hold=hold, threshold=threshold, stat=stat)
            )
        replay_ok = [c["result"] for c in cases] == replay
        held_ok = cases[2]["result"]["held"] is True and cases[2]["result"]["status"] == "held"
        agree_ok = cases[0]["result"]["status"] == "reconciled"
        # check residual_post near 0 when reconciled
        residual_ok = abs(cases[0]["result"]["residual_post"][0]) < 1e-12
        ep = _write_evidence(
            "FSRT",
            "host_reconcile",
            {
                "path_class": "HOST_hard_reconcile_P=I",
                "threshold": threshold,
                "cases": cases,
                "replay_identical": replay_ok,
                "fluid_volume_minted": False,
            },
        )
        num_ok = replay_ok and held_ok and agree_ok and residual_ok
        return {
            "family": "FSRT",
            "path_class": "HOST_hard_reconcile_P=I",
            "operation_id": "BLOCKED",
            "layers": {
                "executable": "blocked",
                "numerical": "pass" if num_ok else "fail",
                "checking": "pass" if num_ok else "fail",
                "replay": "pass" if replay_ok else "fail",
            },
            "commands": [
                _cmd_record(
                    [
                        "python3",
                        "-c",
                        "fsrt-two-reservoir._hard_reconcile (HOST P=I; no fluid-volume)",
                    ],
                    returncode=0 if num_ok else 1,
                    stdout_tail=json.dumps(
                        {
                            "threshold": threshold,
                            "held_case": cases[2]["result"]["status"],
                            "agree_residual_post": cases[0]["result"]["residual_post"],
                            "evidence": ep,
                        }
                    ),
                    stderr_tail=(
                        "HOST replay of published FSRT quickstart; does not mint "
                        "ciw.fluid-volume.v1; no native set_lcm import"
                    ),
                    elapsed_s=round(time.monotonic() - started, 3),
                    status="blocked",  # executable layer remains blocked
                ),
                _cmd_record(
                    ["native_operation.execute", "ciw.fluid-volume.v1"],
                    returncode=None,
                    stdout_tail="",
                    stderr_tail="ciw.fluid-volume.v1 not minted in this repository surface",
                    elapsed_s=0.0,
                    status="blocked",
                ),
            ],
            "evidence": [ep],
            "blocker": "FSRT_ciw.fluid-volume.v1_not_minted",
            "note": (
                "HOST hard reconcile linear algebra ran and checked; "
                "executable remains blocked because ciw.fluid-volume.v1 is not minted."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "family": "FSRT",
            "path_class": "HOST_hard_reconcile_P=I",
            "operation_id": "BLOCKED",
            "layers": {
                "executable": "blocked",
                "numerical": "fail",
                "checking": "fail",
                "replay": "blocked",
            },
            "commands": [
                _cmd_record(
                    ["fsrt_host_reconcile"],
                    returncode=1,
                    stdout_tail="",
                    stderr_tail=str(exc),
                    elapsed_s=round(time.monotonic() - started, 3),
                    status="fail",
                )
            ],
            "evidence": [],
            "blocker": str(exc),
            "note": "FSRT HOST attempt raised; executable still blocked",
        }


def attempt_gte_host() -> dict[str, Any]:
    """HOST radial residual / projection arithmetic (not live GTE)."""
    started = time.monotonic()
    try:
        gte = _load_emitter("cov_gte_emit", "gte-circle-eligibility/run_or_emit.py")

        case = gte._case_eligible()
        points = case["points"]
        residuals = [p["radial_residual_m"] for p in points if not p.get("singular")]
        # recompute independently
        center = case["constraint"]["center_m"]
        radius = case["constraint"]["radius_m"]
        observed = [p["observed_m"] for p in points]
        recomputed = [gte._radial(o, center, radius) for o in observed]
        match = all(
            abs(a - b) < 1e-15 for a, b in zip(residuals, recomputed) if a is not None
        )
        held = gte._case_held()
        refused = gte._case_refused()
        ep = _write_evidence(
            "GTE_CIRCLE",
            "host_radial",
            {
                "path_class": "HOST_teaching_radial_residuals",
                "eligible_residuals": residuals,
                "recomputed": recomputed,
                "match": match,
                "held_id": held.get("id"),
                "refused_id": refused.get("id"),
                "refused_has_singular": any(p.get("singular") for p in refused.get("points") or []),
            },
        )
        ok = match and len(residuals) >= 2
        return {
            "family": "GTE_CIRCLE",
            "path_class": "HOST_teaching_radial_residuals",
            "operation_id": "ciw.geometric-circle.v1",
            "layers": {
                "executable": "pass" if ok else "fail",
                "numerical": "pass" if ok else "fail",
                "checking": "pass" if ok else "fail",
                "replay": "pass" if match else "fail",
            },
            "commands": [
                _cmd_record(
                    [
                        "python3",
                        "-c",
                        "gte-circle-eligibility._radial+_project (HOST teaching arithmetic)",
                    ],
                    returncode=0 if ok else 1,
                    stdout_tail=json.dumps(
                        {"residuals": residuals, "match": match, "evidence": ep}
                    ),
                    stderr_tail="",
                    elapsed_s=round(time.monotonic() - started, 3),
                    status="pass" if ok else "fail",
                )
            ],
            "evidence": [ep],
            "blocker": None if ok else "gte_host_radial_failed",
            "note": (
                "HOST teaching radial residuals from published observed points; "
                "native GTE provider / geometric-circle session NOT invoked."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "family": "GTE_CIRCLE",
            "path_class": "HOST_teaching_radial_residuals",
            "operation_id": "ciw.geometric-circle.v1",
            "layers": {
                "executable": "fail",
                "numerical": "fail",
                "checking": "fail",
                "replay": "not_run",
            },
            "commands": [
                _cmd_record(
                    ["gte_host"],
                    returncode=1,
                    stdout_tail="",
                    stderr_tail=str(exc),
                    elapsed_s=round(time.monotonic() - started, 3),
                    status="fail",
                )
            ],
            "evidence": [],
            "blocker": str(exc),
            "note": "GTE HOST attempt raised",
        }

