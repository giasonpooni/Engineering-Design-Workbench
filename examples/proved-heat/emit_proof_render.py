#!/usr/bin/env python3
"""Emit HOST proved-heat presentation JSON for the Godot Proof tab.

Pins from docs/PROVED_HEAT.md exactly. Reuses ciw.proved-heat.v1 only —
no ciw.proved-heat.v2. Godot must NOT reverify; retained reports carry
retained_runtime_report_requires_fresh_verification. Missing binaries are
UNAVAILABLE/STALE (unavailable ≠ passed). Presentation only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_FOR_HELPER = Path(__file__).resolve().parents[2]
if str(REPO_FOR_HELPER / "examples") not in sys.path:
    sys.path.insert(0, str(REPO_FOR_HELPER / "examples"))
from _render_json import write_render as _shared_write_render  # noqa: E402

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent
OUT_DEFAULT = ROOT / "results" / "proved_heat_render.json"
DOCS = REPO / "docs" / "PROVED_HEAT.md"
SOURCE = ROOT / "source.json"

# Exact pins from docs/PROVED_HEAT.md
SCR_REVISION = "a59aba283b0304faeeb3e5d305087e7709e171ca"
SP1_REVISION = "b38b61209e45e969289e70d5cf79dc763460bc41"
GUEST_ELF_SHA256 = "a14e3750da7e221d31842bd6cf983fcc8c0f530b2811537e2a9a9fe803dacf82"
GUEST_RECIPE = "6e5d1687bcc55243d712553a2b7768b6c587a76418bb48a7a2c44224470d423d"
BACKEND = "sp1-cpu v6.1.0"
OPERATION_ID = "ciw.proved-heat.v1"
TRUST_SCOPE = "retained_runtime_report_requires_fresh_verification"

INITIAL = [0, 100, 200, 100, 0]
FINAL = [0, 65, 92, 65, 0]
STEPS = 4

CAPTION = (
    "proof-before-result. "
    "Godot does not reverify; retained_runtime_report_requires_fresh_verification. "
    "Statement scope: bounded registered guest only "
    f"({INITIAL}→{FINAL} teaching). "
    "Non-claims: not Gaussian update, not observations, not building-safe, "
    "not physical heat, not state admission; JSPT owns sensitivity. "
    "Unavailable ≠ passed."
)


def _pins() -> dict:
    return {
        "scr_revision": SCR_REVISION,
        "sp1_revision": SP1_REVISION,
        "guest_elf_sha256": GUEST_ELF_SHA256,
        "guest_recipe_identity": GUEST_RECIPE,
        "backend_report": BACKEND,
        "docs": str(DOCS.relative_to(REPO)),
    }


def _statement() -> dict:
    return {
        "scope": "bounded_registered_guest_only",
        "initial_values": list(INITIAL),
        "steps": STEPS,
        "final_values": list(FINAL),
        "unit": "1",
        "arithmetic": "signed_integer_truncation_toward_zero",
        "proof_policy": "required_before_result",
        "non_claims": [
            "not Gaussian update",
            "not observations",
            "not building-safe",
            "not physical heat",
            "not state admission",
            "JSPT owns sensitivity",
        ],
    }


def _case_teaching_unavailable() -> dict:
    # Binaries absent in this workspace → UNAVAILABLE/STALE with pins listed.
    return {
        "id": "teaching-statement-binaries-absent",
        "label": "Teaching statement · binaries absent",
        "card_status": "UNAVAILABLE",
        "proof_status": "UNAVAILABLE",
        "never_green": True,
        "reason": "host_binaries_absent",
        "trust_scope": TRUST_SCOPE,
        "proof_before_result": True,
        "identities": {
            "execution": None,
            "result": None,
            "verification": None,
        },
        "statement": _statement(),
        "pins": _pins(),
        "notes": [
            "Missing artifacts are unavailable, not passed",
            "Teaching final field [0,65,92,65,0] is the declared integer claim only",
            "Fresh verification requires pinned SCR/SP1 host + guest ELF",
        ],
    }


def _case_missing_proof() -> dict:
    return {
        "id": "missing-proof-refused",
        "label": "Missing proof → REFUSED",
        "card_status": "REFUSED",
        "proof_status": "REFUSED",
        "never_green": True,
        "reason": "missing_proof",
        "trust_scope": TRUST_SCOPE,
        "proof_before_result": True,
        "identities": {
            "execution": "execution-teachingplaceholder00000001",
            "result": None,
            "verification": None,
        },
        "statement": _statement(),
        "pins": _pins(),
        "notes": [
            "A failed or absent proof produces a refusal and no successful result",
            "Never show green for missing proof",
        ],
    }


def _case_missing_guest_pin() -> dict:
    return {
        "id": "missing-guest-elf-pin-refused",
        "label": "Missing guest ELF pin → REFUSED",
        "card_status": "REFUSED",
        "proof_status": "REFUSED",
        "never_green": True,
        "reason": "missing_guest_elf_pin",
        "trust_scope": TRUST_SCOPE,
        "proof_before_result": True,
        "identities": {
            "execution": "execution-teachingplaceholder00000002",
            "result": None,
            "verification": None,
        },
        "statement": _statement(),
        "pins": _pins(),
        "observed_guest_sha256": None,
        "notes": [
            "Guest ELF SHA-256 must match a14e3750… exactly",
            "Never show green when guest pin is missing or mismatched",
        ],
    }


def _case_resealed_corrupt() -> dict:
    # Synthetic corrupt proof digest — presentation only; not cryptographic evidence.
    corrupt = hashlib.sha256(b"resealed-corrupt-teaching-fixture").hexdigest()
    return {
        "id": "resealed-corrupt-refused",
        "label": "Resealed-corrupt proof → REFUSED",
        "card_status": "REFUSED",
        "proof_status": "REFUSED",
        "never_green": True,
        "reason": "resealed_corrupt_proof",
        "trust_scope": TRUST_SCOPE,
        "proof_before_result": True,
        "identities": {
            "execution": "execution-teachingplaceholder00000003",
            "result": "result-teachingplaceholder000000003",
            "verification": None,
        },
        "statement": _statement(),
        "pins": _pins(),
        "corrupt_proof_sha256_teaching": corrupt,
        "notes": [
            "Corrupted proof whose surrounding JSON commitments were resealed must refuse",
            "Godot never reverifies; card stays REFUSED / never green",
            "Ordinary local structural fixtures are not cryptographic evidence",
        ],
    }


def build_payload() -> dict:
    cases = [
        _case_teaching_unavailable(),
        _case_missing_proof(),
        _case_missing_guest_pin(),
        _case_resealed_corrupt(),
    ]
    return {
        "schema": "ciw.host-proved-heat-render.v1",
        "kind": "proved-heat-presentation",
        "source": "HOST / synthetic",
        "operation_id": OPERATION_ID,
        "claim_scope": "computational-integrity-only",
        "may_authorize": False,
        "godot_must_not_reverify": True,
        "trust_scope": TRUST_SCOPE,
        "proof_before_result": True,
        "upstream_status": "binaries-absent-or-unavailable",
        "pins": _pins(),
        "caption": CAPTION,
        "selected_case_index": 0,
        "cases": cases,
        "statement": _statement(),
        "source_example": str(SOURCE.relative_to(REPO)),
        "presentation_only": True,
        "forbidden_claims": [
            "fresh cryptographic verification by Godot",
            "Gaussian update",
            "observations",
            "building-safe",
            "physical heat",
            "state admission",
            "ciw.proved-heat.v2",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=OUT_DEFAULT,
        help="Path for proved_heat_render.json (default: results/proved_heat_render.json)",
    )
    args = parser.parse_args()
    payload = build_payload()
    _shared_write_render(args.output, payload)
    print(f"wrote {args.output}")
    print(
        f"cases={[c['id'] for c in payload['cases']]} "
        f"operation={OPERATION_ID} trust_scope={TRUST_SCOPE}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
