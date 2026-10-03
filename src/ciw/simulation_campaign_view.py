"""Script-free observation-only projection of a validated campaign report.

No checkpoint bytes, provider configuration, interventions, other channels or
live execution are embedded. This is a display, not an authenticated source.
"""
from __future__ import annotations

from html import escape
import json
from pathlib import Path

from .simulation_campaign import validate_campaign


def _text(value) -> str:
    return escape(str(value), quote=True)


def _json(value) -> str:
    return _text(json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":")))


def _plot(samples: list[dict]) -> str:
    if not samples:
        return '<p class="empty">No samples available to this observer.</p>'
    if any(type(item["value"]) is list for item in samples):
        return '<p class="empty">Vector values are retained in the table; no scalar projection is invented.</p>'
    present = [s for s in samples if s["value"] is not None]
    if not present:
        return '<p class="empty">All samples are missing. No trajectory is drawn.</p>'
    signature = lambda s: (s["identity"]["model_id"], s["identity"]["entity_id"], s["quantity"],
                           s["unit"], s["frame"], s["clock"]["id"])
    if any(signature(s) != signature(samples[0]) for s in samples):
        return '<p class="empty">Mixed identities or units; inspect individual retained values below.</p>'
    lo_x, hi_x = min(s["clock"]["time_s"] for s in samples), max(s["clock"]["time_s"] for s in samples)
    lo_y, hi_y = min(s["value"] for s in present), max(s["value"] for s in present)
    points = []
    for sample in present:
        x = 56 + 550 * ((sample["clock"]["time_s"] - lo_x) / (hi_x - lo_x)) if hi_x != lo_x else 331
        y = 140 - 112 * ((sample["value"] - lo_y) / (hi_y - lo_y)) if hi_y != lo_y else 84
        label = f't={sample["clock"]["time_s"]} s; {sample["value"]} {sample["unit"]}'
        points.append(f'<circle cx="{x:.4f}" cy="{y:.4f}" r="4"><title>{_text(label)}</title></circle>')
    return (f'<svg viewBox="0 0 640 180" role="img" aria-label="Retained samples; independent axes; no interpolation">'
            '<path class="axis" d="M56 20 V140 H610"/>'
            f'<text x="56" y="161">{_text(lo_x)} s</text><text x="605" y="161" text-anchor="end">{_text(hi_x)} s</text>'
            f'<text x="56" y="16">{_text(hi_y)} {_text(samples[0]["unit"])}</text>'
            f'<text x="56" y="178">{_text(lo_y)} {_text(samples[0]["unit"])}</text>'
            + ''.join(points) + '</svg>')


def render_campaign(report: dict) -> str:
    """Validate first, then render a redacted projection without scripts or URLs."""
    validate_campaign(report)
    plan = report["plan"]
    comparisons = {item["variant_id"]: item["comparison"]["outcome"] for item in report["comparisons"]}
    cards, rows = [], []
    for index, case in enumerate(report["cases"]):
        result = next(r for r in case["results"] if r["data"]["request"]["action"] == "observe")
        batch = result["data"]["observations"]
        samples = batch["samples"]
        outcome = comparisons.get(case["variant_id"])
        status = outcome["status"] if outcome else "BASELINE"
        metric = outcome["metrics"]["max_abs_error"] if outcome and outcome["metrics"] else None
        unit = outcome["unit"] if outcome and outcome["unit"] is not None else ""
        rows.append(f'<tr><th scope="row"><a href="#variant-{index}">{_text(case["variant_id"])}</a></th>'
                    f'<td>{status}</td><td>{_text(metric) if metric is not None else "not available"} {_text(unit)}</td>'
                    f'<td>{_text(outcome["reason"]) if outcome else "Reference for every comparison"}</td></tr>')
        values = ''.join(f'<tr><td>{_text(s["clock"]["time_s"])}</td><td>{_json(s["value"]) if s["value"] is not None else "missing"}</td>'
                         f'<td>{_text(s["unit"])}</td><td>{_text(s["identity"]["entity_id"])}</td>'
                         f'<td>{_text(s["frame"])}</td><td>{_text(s["record_digest"])}</td></tr>' for s in samples)
        available = batch["available_at"]
        cards.append(f'<section class="card" id="variant-{index}"><div class="cardhead"><h2>{_text(case["variant_id"])}</h2><strong class="badge">{status}</strong></div>'
                     f'<p>Available at {_text(available["time_s"])} s on {_text(available["id"])}. {len(samples)} retained samples.</p>'
                     + _plot(samples) + '<p class="note">Each chart has independent axes. Points are samples, not interpolated paths. Missing values are not filled.</p>'
                     '<details><summary>Exact observations and provenance</summary><div class="scroll"><table><thead><tr>'
                     '<th>Sample time (s)</th><th>Value</th><th>Unit</th><th>Entity</th><th>Frame</th><th>Original sample digest</th>'
                     '</tr></thead><tbody>' + values + '</tbody></table></div>'
                     f'<p>Observation execution: <code>{_text(result["execution_id"])}</code></p>'
                     f'<p>Observation result: <code>{_text(result["record_digest"])}</code></p>'
                     '<p>Any declared covariance remains in the original report; this view does not calculate uncertainty bounds.</p></details></section>')
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'none'; img-src 'none'; base-uri 'none'; form-action 'none'">
<title>NET | Intervention campaign</title><style>
:root{color-scheme:dark;font-family:system-ui,sans-serif;background:#0c1420;color:#e8eef5}
*{box-sizing:border-box}body{margin:0}main{max-width:1120px;margin:auto;padding:32px 22px 60px}
h1{font-size:clamp(1.8rem,4vw,3rem);margin:12px 0}h2{font-size:1.2rem;margin:0;overflow-wrap:anywhere}
p{line-height:1.6}.eyebrow{color:#79d9cb;letter-spacing:.13em;font-size:.8rem}.lead{max-width:840px;color:#b8c9d9}
.summary,.card{border:1px solid #304156;border-radius:12px;padding:22px;background:#121f30;margin:22px 0}
.cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}.card{margin:0;min-width:0}.cardhead{display:flex;justify-content:space-between;gap:12px;align-items:center}
.badge{padding:5px 9px;border:1px solid #7eabb6;border-radius:5px;font-size:.74rem;white-space:nowrap}
.note,.empty{font-size:.85rem;color:#afc3d5}a{color:#88e6d7}a:focus,summary:focus{outline:3px solid #fff;outline-offset:3px}
.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:.9rem;text-align:left}td,th{padding:12px 10px;border-bottom:1px solid #304156;vertical-align:top}td{overflow-wrap:anywhere}th{color:#bcd3e5}
svg{width:100%;height:auto;background:#0c1725;border-radius:6px}svg text{font-size:11px;fill:#c4d7e6}circle{fill:#78ded1}.axis{stroke:#59738c;fill:none}
summary{cursor:pointer;padding:12px 0}code{font-size:.82rem;overflow-wrap:anywhere}footer{margin-top:30px;color:#a4b8cb;font-size:.85rem}
@media(max-width:720px){main{padding:24px 14px}.cards{grid-template-columns:1fr}.summary,.card{padding:16px}.cardhead{flex-wrap:wrap}}
</style></head><body><main><div class="eyebrow">NOTATIONS ENGINEERING TERMINAL / RETAINED EVIDENCE</div>
''' + f'<h1>{_text(plan["campaign_id"])}</h1><p class="lead">One checkpoint. Declared interventions. Independent branches. Compare the retained observations without restarting a simulation.</p>' \
        + f'<div class="summary"><p><strong>{len(report["cases"])} variants completed.</strong> Observer: {_text(plan["observer"]["observer_id"])} / {_text(plan["observer"]["kind"])}. Quantity: {_text(plan["quantity"])}.</p>' \
        + f'<p>Comparison policy: |candidate - baseline| &le; {_text(plan["policy"]["atol"])} + {_text(plan["policy"]["rtol"])} &times; |baseline|.</p>' \
        + '<p>FAIL means the declared equivalence condition was not met, not that the variant is worse. INDETERMINATE is not a pass. No optimization or ranking was performed.</p>' \
        + '<div class="scroll"><table><thead><tr><th>Variant</th><th>Comparison</th><th>Maximum difference</th><th>Meaning</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div></div>' \
        + '<div class="cards">' + ''.join(cards) + '</div>' \
        + f'<footer><p>Campaign record: <code>{_text(report["record_digest"])}</code></p><p>Read-only display. No providers, scripts or network requests. Checkpoint bytes, world configuration and intervention payloads are not embedded. This is a display projection, not independent evidence authentication or an access-control system. Numerical results remain not_verified; no physical validation or state admission.</p></footer></main></body></html>'


def save_view(report: dict, path: Path) -> None:
    html = render_campaign(report)
    with Path(path).open("x", encoding="utf-8", newline="\n") as output:
        output.write(html)
