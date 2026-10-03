"""Offline, script-free projection of a retained source selection."""
from __future__ import annotations

import base64
from hashlib import sha256
from html import escape
import json

from .computational_source import _lines, source_context

_CSS = """body{font:16px/1.6 system-ui,sans-serif;margin:0;background:#101820;color:#e8eff4}
main{max-width:1050px;margin:auto;padding:2rem}h1,h2{line-height:1.2}a{color:#9cd8ff}
nav{display:flex;gap:1rem;flex-wrap:wrap}.note,details{background:#1c2933;padding:1rem;border-radius:8px;margin:1rem 0}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#0b1218;padding:1rem;border-radius:6px}
summary{cursor:pointer;font-weight:600}code{font-family:ui-monospace,monospace}p{overflow-wrap:anywhere}
@media(max-width:600px){main{padding:1rem}h1{font-size:1.8rem}}
"""


def render_selection(capture: dict) -> str:
    context = source_context(capture)
    obj = context["context"]["object"]
    source = obj["source"]
    style_hash = base64.b64encode(sha256(_CSS.encode()).digest()).decode("ascii")
    csp = ("default-src 'none'; style-src 'sha256-" + style_hash
           + "'; base-uri 'none'; form-action 'none'; object-src 'none'")

    def block(name, value):
        return ("<details><summary>" + escape(name) + "</summary><pre>"
                + escape(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)) + "</pre></details>")

    numbered = "".join(f"{line:>5}  {text.decode('utf-8')}" for line, text in enumerate(
        _lines(context["excerpt"].encode("utf-8")), source["span"][0]))
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<meta http-equiv='Content-Security-Policy' content=\"" + escape(csp, quote=True) + "\">"
        "<title>NET source inspector</title><style>" + _CSS + "</style></head><body><main>"
        "<p>NOTATIONS ENGINEERING TERMINAL / SOURCE INSPECTION</p><h1>" + escape(obj["label"]) + "</h1>"
        "<nav><a href='#source'>Source</a><a href='#math'>Mathematics</a>"
        "<a href='#relations'>Relations</a><a href='#evidence'>Evidence</a></nav>"
        "<p class='note'>Read-only retained source. Mathematical claims and relations are declarations, not proofs. "
        "Selection does not execute code, authorize edits or establish repository authenticity.</p>"
        "<p>" + escape(source["repository"] + " / " + source["path"]) + "<br>Commit: <code>"
        + escape(source["revision"]) + "</code><br>Full-file content: <code>" + escape(source["sha256"])
        + "</code></p><section id='source'><h2>Selected source</h2><pre id='selected-code'>"
        + escape(numbered) + "</pre></section><section id='math'><h2>Declared mathematics</h2>"
        + block("Domain, codomain, expression and assumptions", obj["mathematics"])
        + block("Invariants: not assessed by inspection", obj["invariants"])
        + "</section><section id='relations'><h2>Relations</h2>"
        + block("Syntactic calls: unresolved, not a runtime call graph", context["syntactic_calls"])
        + block("Declared dependencies and compositions", obj["relations"])
        + "</section><section id='evidence'><h2>Evidence and boundaries</h2>"
        + block("Evidence references: not fetched or authenticated", obj["evidence"])
        + block("Experiment references", obj["experiments"])
        + block("Selection and proposed edit envelope", context["context"]["selection"])
        + block("Capture binding and limitations", {"capture_digest": context["capture_digest"], **context["limits"]})
        + "</section></main></body></html>")
