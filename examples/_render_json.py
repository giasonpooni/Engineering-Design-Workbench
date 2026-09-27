"""Shared helper for host presentation render JSON.

Providers (Godot, Bevy, …) project the same retained record. This helper
ensures may_authorize is false and common claim fields are present. It does
not mint CIW kinds and does not compute science.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, MutableMapping


REQUIRED_DEFAULTS = {
    "may_authorize": False,
    "claim_scope": "computational-integrity-only",
    "presentation_only": True,
}


def normalize_render(payload: Mapping[str, Any]) -> dict:
    """Return a copy with required presentation fields enforced."""
    data: dict[str, Any] = dict(payload)
    data["may_authorize"] = False
    data.setdefault("claim_scope", REQUIRED_DEFAULTS["claim_scope"])
    data.setdefault("presentation_only", True)
    if "status" not in data and "upstream_status" in data:
        data["status"] = data["upstream_status"]
    data.setdefault("status", data.get("upstream_status", "HOST"))
    data.setdefault("source", data.get("source", "HOST / synthetic"))
    if "cards" not in data:
        # Prefer an explicit empty list so viewers can treat absence uniformly.
        # Dict-shaped cards (CSG) are preserved as-is when already present.
        data["cards"] = []
    # Never invent a fresh verifier occurrence.
    if "fresh_verifier_occurrence" not in data:
        data["fresh_verifier_occurrence"] = False
    return data


def write_render(path: Path | str, payload: Mapping[str, Any], *, indent: int = 2) -> Path:
    """Write normalized render JSON to path (parents created)."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    data = normalize_render(payload)
    out.write_text(json.dumps(data, indent=indent) + "\n", encoding="utf-8")
    return out
