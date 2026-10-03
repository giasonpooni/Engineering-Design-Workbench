"""Offline operator timeline; no execution, source snapshots or remote assets.

Only a derived index and explicitly validated PNG bytes enter the HTML. Full
original workspaces remain separate privileged evidence files in the bundle.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from .control_contracts import bytes_ref
from .operations.runner import check_seal
from .simulation_capture import png_info
from .simulation_records import require


def render(timeline: dict, files: dict[str, bytes]) -> str:
    check_seal(timeline)
    require(timeline.get("schema") == "ciw.simulation-timeline.v1", "Unsupported timeline view")
    images = {}
    for event in timeline["entries"]:
        image = event["image"]
        if image and image["bytes_checked"]:
            raw = files[image["asset"]]
            require(bytes_ref(raw) == image["sha256"], "Image/index hash mismatch")
            png_info(raw)
            images[image["sha256"]] = "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
    assets = Path(__file__).with_name("web")
    js = assets.joinpath("simulation_timeline.js").read_text(encoding="utf-8")
    css = assets.joinpath("simulation_timeline.css").read_text(encoding="utf-8")
    data = json.dumps({"timeline": timeline, "images": images}, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    # JSON is inert text, not HTML. Escape terminators even in hostile labels.
    data = data.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    def sri(text):
        return base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode("ascii")
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'sha256-{sri(js)}'; style-src 'sha256-{sri(css)}'; img-src data:; base-uri 'none'; form-action 'none'; connect-src 'none'">
<title>NET | Evidence timeline</title><style>{css}</style></head>
<body><main>
<header><div class="eyebrow">NOTATIONS ENGINEERING TERMINAL / INVESTIGATION</div>
<h1>Evidence timeline</h1><p class="lead">Commands, observations and images. One linked history, without restarting a provider.</p>
<div class="scope"><strong>Operator view · retained evidence only</strong><p>World time, sample time and delivery time are different. Links come from recorded dependencies; independent branches have no inferred global chronology. Observer labels are not access controls.</p></div>
</header>
<section class="metrics" aria-label="Evidence counts"><div><b id="executions">0</b><span>Unique executions</span></div><div><b id="instances">0</b><span>Simulation instances</span></div><div><b id="images">0</b><span>Checked images</span></div><div><b id="refusals">0</b><span>Retained refusals</span></div></section>
<p class="note" id="dedup"></p><p class="warning" id="gaps" hidden></p>
<section class="filters" aria-label="Timeline filters">
<label>Kind<select id="kind"><option value="">All kinds</option></select></label>
<label>Instance<select id="instance"><option value="">All instances</option></select></label>
<label>Observer<select id="observer"><option value="">All observers</option></select></label>
<label>Search<input type="search" id="search" placeholder="Action, identity, quantity…" autocomplete="off"></label>
<button id="reset" type="button">Reset filters</button></section>
<div class="workspace"><section class="events"><h2>Recorded occurrences <span id="visible-count"></span></h2>
<p class="note">Dependency order; UTC/identity breaks unrelated ties.</p><div id="event-list" role="list" aria-label="Recorded occurrences"></div><p id="empty" hidden>No retained occurrences match these filters.</p></section>
<section class="detail" aria-label="Selected occurrence"><div class="detail-nav"><span id="selected-kind" class="badge">No selection</span><div><button id="previous" type="button" aria-label="Previous visible occurrence">Previous</button><button id="next" type="button" aria-label="Next visible occurrence">Next</button></div></div>
<h2 id="selected-title">Select an occurrence</h2><p id="selected-execution" class="mono"></p>
<dl id="facts"></dl><div id="relations" class="relations"></div>
<div id="image-panel" hidden><img id="capture-image" alt="Derived Godot visualization of selected retained position observations"><p id="image-caption" class="note"></p></div>
<p id="observation-note" class="note"></p><div class="table-scroll" id="sample-panel" hidden><table><thead><tr><th>Sample time (s)</th><th>Entity</th><th>Quantity</th><th>Value</th><th>Unit</th></tr></thead><tbody id="samples"></tbody></table></div>
<details id="record-details"><summary>Exact indexed record and provenance</summary><pre id="record-json"></pre></details>
</section></div>
<section class="analyses"><h2>Campaign and replay checks</h2><p class="note">These are rechecked derived reports, not new executions. FAIL means the declared comparison was not met; it does not rank alternatives.</p><div id="analysis-list"></div></section>
<footer><p id="source-ref" class="mono"></p><p>Full source workspaces stay in the evidence bundle. This page embeds no checkpoints, world configuration, intervention payloads or saved code. The operator index can include multiple named observers. Unknown history stays unknown. All ordinary results remain not_verified; no physical validation or state admission.</p><p>Check the bundle with <code>net simulation timeline inspect DIRECTORY</code>. Hashes check consistency, not publisher identity.</p></footer>
<noscript>This offline inspector requires its packaged script for navigation. The bundle also includes timeline.json and original evidence; no network is required.</noscript>
<script id="timeline-data" type="application/json">{data}</script><script>{js}</script>
</main></body></html>'''
