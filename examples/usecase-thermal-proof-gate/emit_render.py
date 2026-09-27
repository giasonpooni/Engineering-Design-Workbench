#!/usr/bin/env python3
"""Emit HOST thermal proof-gate presentation (owned proved-heat rules).

HOST_FROM_OWNED_CONFIG: reuses examples/proved-heat strengthen rules
(HISTORICAL / REFUSED / missing proof / binaries absent). Framed as a thermal
guest proof gate for Godot. Does not mint ciw.proved-heat.v2. Inspect does not
reverify; no proof bytes on screen; unavailable ≠ passed.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

REPO_FOR_HELPER = Path(__file__).resolve().parents[2]
if str(REPO_FOR_HELPER / "examples") not in sys.path:
    sys.path.insert(0, str(REPO_FOR_HELPER / "examples"))
from _render_json import write_render as _shared_write_render  # noqa: E402

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent
OUT_DEFAULT = ROOT / "results" / "thermal_proof_render.json"

_PH = REPO / "examples" / "proved-heat" / "emit_proof_render.py"
_spec = importlib.util.spec_from_file_location("owned_proved_heat_for_thermal", _PH)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"cannot load {_PH}")
_ph = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ph)

CAPTION = (
    "Integer heat / thermal guest proof gate before releasing a retained result. "
    "Inspect does not reverify; no proof bytes on screen. HOST_FROM_OWNED_CONFIG — "
    "owned proved-heat strengthen rules; unavailable ≠ passed."
)
DATA_SOURCE = (
    "HOST_FROM_OWNED_CONFIG citing examples/proved-heat/ (emit_proof_render.py, "
    "source.json) and docs/PROVED_HEAT.md pins. Framed as thermal proof gate — "
    "Godot does not reverify; retained_runtime_report_requires_fresh_verification."
)


def build_payload() -> dict:
    base = _ph.build_payload()
    cases: list[dict] = []
    for case in base.get("cases") or []:
        c = dict(case)
        cid = c.get("id")
        if cid == "teaching-statement-binaries-absent":
            c["label"] = "Thermal gate · binaries absent → UNAVAILABLE"
            c["notes"] = list(c.get("notes") or []) + [
                "Use-case: cannot release retained result without host binaries",
                "Inspect does not reverify; no proof bytes on screen",
            ]
        elif cid == "missing-proof-refused":
            c["label"] = "Thermal gate · missing proof → REFUSED"
            c["notes"] = list(c.get("notes") or []) + [
                "Use-case: proof-before-result refuses release",
            ]
        elif cid == "missing-guest-elf-pin-refused":
            c["label"] = "Thermal gate · missing guest ELF pin → REFUSED"
        elif cid == "resealed-corrupt-refused":
            c["label"] = "Thermal gate · resealed-corrupt → REFUSED"
        cases.append(c)

    # Teaching historical card — retained report requires fresh verification.
    historical = {
        "id": "retained-historical-requires-fresh",
        "label": "Thermal gate · retained HISTORICAL report",
        "card_status": "HISTORICAL",
        "proof_status": "HISTORICAL",
        "never_green": True,
        "reason": "retained_runtime_report_requires_fresh_verification",
        "trust_scope": _ph.TRUST_SCOPE,
        "proof_before_result": True,
        "identities": {
            "execution": "execution-teachingplaceholder-historical",
            "result": "result-teachingplaceholder-historical",
            "verification": None,
        },
        "statement": _ph._statement(),
        "pins": _ph._pins(),
        "notes": [
            "Inspect does not reverify",
            "Retained report stays HISTORICAL until fresh verification",
        ],
    }
    cases.append(historical)

    cards = []
    for case in cases:
        cards.append(
            {
                "title": case.get("label"),
                "status": str(case.get("card_status") or "").upper(),
                "reason": case.get("reason"),
                "id": case.get("id"),
            }
        )

    return {
        "schema": "ciw.host-usecase-thermal-proof-render.v1",
        "kind": "usecase-thermal-proof-gate-presentation",
        "source": "HOST_FROM_OWNED_CONFIG",
        "data_source": DATA_SOURCE,
        "claim_scope": "computational-integrity-only",
        "may_authorize": False,
        "operation_id": "ciw.proved-heat.v1",
        "godot_must_not_reverify": True,
        "trust_scope": _ph.TRUST_SCOPE,
        "proof_before_result": True,
        "upstream_status": "HOST_FROM_OWNED_CONFIG",
        "owned_configs": ["examples/proved-heat/", "docs/PROVED_HEAT.md"],
        "pins": _ph._pins(),
        "caption": CAPTION,
        "selected_case_index": 0,
        "cases": cases,
        "cards": cards,
        "statement": _ph._statement(),
        "presentation_only": True,
        "canonicalAdmission": False,
        "evidence_seam": {
            "url": "https://github.com/giasonpooni/Evidence-and-State-Management",
            "role": "cite_only",
            "note": "No invented ESM pin; real bindings absent",
        },
        "forbidden_claims": [
            "physical heat",
            "reverification by Godot",
            "ciw.proved-heat.v2",
            "operational authorization",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT_DEFAULT)
    args = parser.parse_args()
    payload = build_payload()
    _shared_write_render(args.output, payload)
    print(f"wrote {args.output}")
    for case in payload.get("cases") or []:
        print(f"  {case.get('id')}: card={case.get('card_status')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
