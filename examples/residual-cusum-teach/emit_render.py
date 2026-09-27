#!/usr/bin/env python3
"""Emit HOST residual-monitor CUSUM teaching presentation for Godot.

Synthetic ordered windows teaching residual-monitor / FDIR-OIT language from
docs/EXPERIMENT_VIEW.md — WITHOUT requiring stack-root providers.
Does not invent ciw.fluid-volume or new residual kinds.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_FOR_HELPER = Path(__file__).resolve().parents[2]
if str(REPO_FOR_HELPER / "examples") not in sys.path:
    sys.path.insert(0, str(REPO_FOR_HELPER / "examples"))
from _render_json import write_render as _shared_write_render  # noqa: E402

ROOT = Path(__file__).resolve().parent
OUT_DEFAULT = ROOT / "results" / "residual_cusum_render.json"

# Teaching threshold (normalized residual CUSUM) — HOST synthetic, not a live FDIR pin.
CUSUM_THRESHOLD = 5.0
OPERATION_LANGUAGE = "residual-monitor / FDIR-OIT (docs/EXPERIMENT_VIEW.md)"

DATA_SOURCE = (
    "HOST synthetic ordered windows teaching residual-monitor concepts from "
    "docs/EXPERIMENT_VIEW.md and examples/residual-monitor/. "
    "No stack-root providers; no live FDIR/OIT execution."
)

CAPTION = (
    "Physical drift and alarm probability unestablished; "
    "no joint covariance / cross-window confidence bars. "
    "OIT-held windows do not advance the CUSUM state. "
    "Native threshold crossings remain diagnostic candidates only."
)


def _window(*, window_id: str, label: str, status: str, residuals: list[float], cusum_path: list[float], crossed: bool, advances_cusum: bool, note: str) -> dict:
    return {"id": window_id, "label": label, "status": status, "normalized_residuals": residuals, "cusum": cusum_path, "threshold": CUSUM_THRESHOLD, "crossed": crossed, "advances_cusum": advances_cusum, "notes": [note]}


def _case_quiet() -> dict:
    residuals = [0.2, -0.1, 0.3, -0.2, 0.1, 0.0, -0.15, 0.25]
    cusum = []
    s = 0.0
    for r in residuals:
        s = max(0.0, s + abs(r) - 0.15)
        cusum.append(round(s, 4))
    return _window(window_id="quiet-no-cross", label="Quiet · CUSUM not crossed", status="LIVE", residuals=residuals, cusum_path=cusum, crossed=False, advances_cusum=True, note="Teaching quiet window: CUSUM stays below threshold")


def _case_crossing() -> dict:
    residuals = [0.4, 0.8, 1.2, 1.5, 1.1, 0.9, 1.3, 1.6]
    cusum = []
    s = 0.0
    crossed_at = None
    for index, r in enumerate(residuals):
        s = max(0.0, s + abs(r) - 0.15)
        cusum.append(round(s, 4))
        if crossed_at is None and s >= CUSUM_THRESHOLD:
            crossed_at = index
    return {**_window(window_id="diagnostic-candidate-cross", label="Diagnostic candidate · CUSUM crossed", status="REQUEST_EVIDENCE", residuals=residuals, cusum_path=cusum, crossed=True, advances_cusum=True, note="Threshold crossing is a diagnostic candidate only — not an alarm probability"), "crossed_at_index": crossed_at}


def _case_oit_held() -> dict:
    prior_cusum = 2.4
    residuals = [0.9, 1.1, 1.4, 1.8, 2.0, 1.7, 1.5, 1.2]
    cusum = [prior_cusum for _ in residuals]
    return _window(window_id="oit-held-no-advance", label="OIT-held · CUSUM does not advance", status="HELD", residuals=residuals, cusum_path=cusum, crossed=False, advances_cusum=False, note="OIT-held windows do not advance the CUSUM state (EXPERIMENT_VIEW.md)")


def build_payload() -> dict:
    windows = [_case_quiet(), _case_crossing(), _case_oit_held()]
    series: list[dict] = []
    for w_index, window in enumerate(windows):
        for i, residual in enumerate(window["normalized_residuals"]):
            series.append({"window_index": w_index, "window_id": window["id"], "sample_index": i, "x": w_index * 10 + i, "normalized_residual": residual, "cusum": window["cusum"][i], "threshold": CUSUM_THRESHOLD, "status": window["status"], "advances_cusum": window["advances_cusum"]})
    cards = [{"title": w["label"], "status": w["status"], "crossed": w["crossed"], "advances_cusum": w["advances_cusum"], "cusum_final": w["cusum"][-1] if w["cusum"] else None, "threshold": CUSUM_THRESHOLD} for w in windows]
    return {"schema": "ciw.host-residual-cusum-teach-render.v1", "kind": "residual-cusum-teach-presentation", "source": "HOST / synthetic ordered windows", "data_source": DATA_SOURCE, "claim_scope": "computational-integrity-only", "may_authorize": False, "operation_language": OPERATION_LANGUAGE, "upstream_status": "HOST_TEACHING_RESIDUAL_MONITOR", "caption": CAPTION, "selected_window_index": 0, "threshold": CUSUM_THRESHOLD, "windows": windows, "series": series, "cards": cards, "presentation_only": True, "forbidden_claims": ["physical drift established", "alarm probability", "joint covariance", "cross-window confidence bars", "ciw.fluid-volume", "new residual CIW kind"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT_DEFAULT)
    args = parser.parse_args()
    payload = build_payload()
    _shared_write_render(args.output, payload)
    print(f"wrote {args.output}")
    for window in payload["windows"]:
        print(f"  {window['id']}: status={window['status']} crossed={window['crossed']} advances={window['advances_cusum']} cusum_final={window['cusum'][-1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
