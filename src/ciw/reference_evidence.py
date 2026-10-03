"""Data-only retained scalar reference; import is not physical acquisition."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import math

from .adapters.subprocess import _json
from .core.records import finite_tree

SOURCE_SCHEMA = "ciw.reference-evidence.v1"
MAX_BYTES = 256 * 1024


def _source(raw: bytes) -> dict:
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_BYTES:
        raise ValueError("Reference evidence requires bounded exact JSON bytes")
    value = _json(raw)
    required = {"schema", "origin", "quantity_id", "value", "unit", "coordinate_frame",
                "observed_at", "uncertainty", "context"}
    if not isinstance(value, dict) or set(value) != required or value["schema"] != SOURCE_SCHEMA:
        raise ValueError("Malformed scalar reference evidence")
    finite_tree(value, "reference evidence")
    if value["origin"] not in {"synthetic_fixture", "operator_record"}:
        raise ValueError("Reference origin must be explicitly declared")
    for field in ("quantity_id", "unit", "coordinate_frame", "observed_at"):
        if not isinstance(value[field], str) or not value[field].strip() or len(value[field]) > 512:
            raise ValueError("Reference " + field + " requires bounded nonempty text")
    instant = datetime.fromisoformat(value["observed_at"].replace("Z", "+00:00"))
    if instant.utcoffset() is None:
        raise ValueError("Reference observed_at requires an explicit timezone")
    if type(value["value"]) not in (int, float) or not math.isfinite(value["value"]):
        raise ValueError("Reference value must be finite")
    uncertainty = value["uncertainty"]
    if uncertainty != {"status": "unspecified"}:
        if (not isinstance(uncertainty, dict) or set(uncertainty) != {"status", "standard_uncertainty"}
                or uncertainty["status"] != "declared"
                or type(uncertainty["standard_uncertainty"]) not in (int, float)
                or not math.isfinite(uncertainty["standard_uncertainty"])
                or uncertainty["standard_uncertainty"] < 0):
            raise ValueError("Reference uncertainty must be unspecified or a nonnegative declared standard uncertainty")
    if not isinstance(value["context"], dict):
        raise ValueError("Reference context must be a data object")
    return deepcopy(value)
