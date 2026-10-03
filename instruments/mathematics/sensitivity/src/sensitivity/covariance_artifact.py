"""Content-addressed covariance declarations shared with domain repositories.

This record layer adds ordered quantities and provenance using the shared wire
contract. It does not infer physical units or independence. Scientific kernels
retain their own, sometimes stricter, numerical admissibility checks.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import math
import re
from typing import Any

import numpy as np

SCHEMA = "covariance-artifact.v1"
MAX_DIMENSION = 256
SYMMETRY_ATOL = 1e-12
PSD_ATOL = 1e-10
_FIELDS = {
    "schema", "covariance_id", "quantity_ids", "units", "frame", "reference_values",
    "matrix", "method", "basis", "provenance", "assumptions",
}
_BASIS_KINDS = {
    "observation", "calibrated_observation", "estimated_state", "parameter", "coordinate", "residual",
}


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def content_id(value: Any) -> str:
    return "sha256:" + sha256(canonical(value)).hexdigest()


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _strings(value: Any, name: str, *, size: int | None = None, unique: bool = False) -> list[str]:
    if not isinstance(value, list) or (size is not None and len(value) != size):
        raise ValueError(f"{name} must be an ordered array with the declared dimension")
    for entry in value:
        _string(entry, f"{name} entry")
    if unique and len(set(value)) != len(value):
        raise ValueError(f"{name} must contain unique ordered identifiers")
    return value


def _number(value: Any, name: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be a real JSON number, not a boolean or string")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} must be finite in float64") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite in float64")
    return number


def vector(value: Any, size: int, name: str) -> np.ndarray:
    if not isinstance(value, list) or len(value) != size:
        raise ValueError(f"{name} must contain exactly {size} ordered numbers")
    return np.array([_number(entry, name) for entry in value], dtype=float)


def matrix(value: Any, rows: int, columns: int, name: str) -> np.ndarray:
    if not isinstance(value, list) or len(value) != rows:
        raise ValueError(f"{name} must be a {rows} by {columns} matrix")
    return np.array([vector(row, columns, name) for row in value], dtype=float)


def _json_tree(value: Any) -> None:
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("metadata object keys must be strings")
        for child in value.values():
            _json_tree(child)
    elif isinstance(value, list):
        for child in value:
            _json_tree(child)
    elif type(value) in (int, float):
        _number(value, "metadata number")
    elif value is not None and type(value) not in (str, bool):
        raise ValueError("metadata must be JSON-only domain declarations")


def _validate_wire_matrix(covariance: np.ndarray) -> None:
    """Check both stored triangles; never repair a received wire artifact."""
    variances = np.diag(covariance)
    if np.any(variances < 0):
        raise ValueError("Covariance variances must be nonnegative")
    zero = variances == 0
    if np.any(covariance[zero, :] != 0) or np.any(covariance[:, zero] != 0):
        raise ValueError("Zero variance requires exactly zero covariance row and column")
    active = ~zero
    if not np.any(active):
        return
    scales = np.sqrt(variances[active])
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        correlation = covariance[np.ix_(active, active)] / scales[:, None] / scales[None, :]
    if not np.all(np.isfinite(correlation)):
        raise ValueError("Covariance has nonfinite normalized correlations")
    if not np.allclose(correlation, correlation.T, rtol=0, atol=SYMMETRY_ATOL):
        raise ValueError("Covariance must be symmetric in correlation coordinates")
    try:
        for triangle in ("L", "U"):
            eigenvalues = np.linalg.eigvalsh(correlation, UPLO=triangle)
            if not np.all(np.isfinite(eigenvalues)) or np.min(eigenvalues) < -PSD_ATOL:
                raise ValueError("Covariance must be positive semidefinite in correlation coordinates")
    except np.linalg.LinAlgError as exc:
        raise ValueError("Covariance positive-semidefinite validation did not converge") from exc


def validate_covariance_artifact(value: Any) -> dict:
    """Validate the exact identity, ordering and shared wire PSD law without edits.

    Singular and zero covariance matrices are accepted. Small numerical
    asymmetry is bounded by the shared correlation-coordinate tolerance;
    validation itself never changes the supplied record or its identity.
    """
    if not isinstance(value, dict) or set(value) != _FIELDS or value["schema"] != SCHEMA:
        raise ValueError(f"Expected exact {SCHEMA} fields")
    quantities = _strings(value["quantity_ids"], "quantity_ids", unique=True)
    size = len(quantities)
    if not 1 <= size <= MAX_DIMENSION:
        raise ValueError(f"Covariance dimension must be between 1 and {MAX_DIMENSION}")
    _strings(value["units"], "units", size=size)
    _string(value["frame"], "frame")
    _string(value["method"], "method")
    vector(value["reference_values"], size, "reference_values")
    covariance = matrix(value["matrix"], size, size, "matrix")
    _validate_wire_matrix(covariance)
    basis = value["basis"]
    if (not isinstance(basis, dict) or set(basis) != {"kind", "id"}
            or basis["kind"] not in _BASIS_KINDS):
        raise ValueError("basis must declare a supported kind and an identifier")
    _string(basis["id"], "basis.id")
    provenance = value["provenance"]
    required = {"provider", "source_evidence_ids", "source_covariance_ids"}
    if (not isinstance(provenance, dict) or not required <= provenance.keys()
            or provenance.keys() - required - {"metadata"}):
        raise ValueError("provenance must declare provider and source identity arrays")
    _string(provenance["provider"], "provenance.provider")
    for field in ("source_evidence_ids", "source_covariance_ids"):
        identifiers = _strings(provenance[field], f"provenance.{field}", unique=True)
        if any(not re.fullmatch(r"sha256:[0-9a-f]{64}", entry) for entry in identifiers):
            raise ValueError(f"provenance.{field} must contain sha256 content identifiers")
    if "metadata" in provenance:
        if not isinstance(provenance["metadata"], dict):
            raise ValueError("provenance.metadata must be an object")
        _json_tree(provenance["metadata"])
    _strings(value["assumptions"], "assumptions")
    body = {key: item for key, item in value.items() if key != "covariance_id"}
    if value["covariance_id"] != content_id(body):
        raise ValueError("Covariance artifact content identity mismatch")
    return deepcopy(value)


def make_covariance_artifact(**declaration: Any) -> dict:
    """Seal a new declaration; received artifacts must be validated, not resealed."""
    if "covariance_id" in declaration or "schema" in declaration:
        raise ValueError("New declarations cannot supply a schema or covariance identity")
    record = {"schema": SCHEMA, **deepcopy(declaration)}
    record["covariance_id"] = content_id(record)
    return validate_covariance_artifact(record)
