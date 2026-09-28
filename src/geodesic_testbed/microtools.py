# SPDX-License-Identifier: MPL-2.0
"""Small array-facing operations over the existing constant-curvature transfer map.

No NET dependency, integrator, path planner, scene state or device authority.
Values are first-order transverse Jacobi responses at supplied arclength samples,
not a bound on finite nonlinear trajectories or on the intervals between samples.
"""
from __future__ import annotations

import json
import math
import sys
from copy import deepcopy
from decimal import Decimal
from numbers import Real
from typing import Any

import numpy as np

OPERATIONS = ("csr.pose-propagate.v1", "csr.error-box.v1", "csr.covariance-propagate.v1")
SCHEMA = "csr.microtool-result.v1"
MAX_SAMPLES = 512
MAX_REQUEST_BYTES = 65536
MODEL = "constant-curvature-transverse-jacobi.v1"
SCOPE = "first_order_at_supplied_arclengths_only"


def _number(value: Any) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError("Require real numeric values, not booleans or numeric strings")
    result = float(value)
    if not math.isfinite(result) or abs(result) > 1e100:
        raise ValueError("Numeric value is nonfinite or outside the bounded profile")
    if result != 0.0 and abs(result) < 1e-100:
        raise ValueError("Sub-profile nonzero magnitude; no underflow to zero is permitted")
    return result


def _array(value: Any, shape: tuple[int, ...] | None = None) -> np.ndarray:
    # Check leaves before coercion: np.asarray([True, 1]) would otherwise hide True.
    def check(item: Any) -> None:
        if isinstance(item, np.ndarray):
            if item.dtype.kind not in "iuf" or item.size > MAX_SAMPLES * 4:
                raise ValueError("Require bounded real numeric arrays")
            for child in item.flat:
                _number(child)
        elif isinstance(item, (list, tuple)):
            if len(item) > MAX_SAMPLES:
                raise ValueError("Array exceeds sample budget")
            for child in item:
                check(child)
        else:
            _number(item)
    check(value)
    result = np.asarray(value, dtype=np.float64)
    if shape is not None and result.shape != shape:
        raise ValueError(f"Require array shape {shape}")
    return result.copy()


def transfer_map(arc_length: Any, curvature: Real):
    """Validated array facade; the original provider owns all transfer mathematics.

    Profile: 1..512 strictly increasing nonnegative samples, s <= 1e6;
    K=0 or 1e-12 <= |K| <= 1e6; sqrt(|K|)*max(s) <= 4.
    Length and curvature must already use reciprocal units. No conversion occurs.
    """
    from .engine.transfer import constant_curvature_transfer
    grid = _array(arc_length)
    if grid.ndim != 1 or not 1 <= grid.size <= MAX_SAMPLES:
        raise ValueError("Require 1..512 arclength samples")
    if grid[0] < 0 or grid[-1] > 1e6 or np.any(np.diff(grid) <= 0):
        raise ValueError("Require increasing nonnegative bounded arclength, not timestamps")
    k = _number(curvature)
    if k and not 1e-12 <= abs(k) <= 1e6:
        raise ValueError("Curvature is outside the bounded numerical profile")
    if math.sqrt(abs(k)) * float(grid[-1]) > 4:
        raise ValueError("Scaled arclength exceeds the numerical profile")
    with np.errstate(over="raise", invalid="raise", divide="raise", under="raise"):
        result = constant_curvature_transfer(grid, k)
    if not np.isfinite(result.matrices()).all():
        raise ValueError("Nonfinite transfer map")
    return result


def propagate_pose(arc_length: Any, curvature: Real, initial_error: Any) -> np.ndarray:
    """Return (n,2) [lateral, heading-radian] first-order responses."""
    initial = _array(initial_error, (2,))
    mapping = transfer_map(arc_length, curvature)
    with np.errstate(over="raise", invalid="raise", under="raise"):
        result = np.column_stack(mapping.propagate(*initial))
    if not np.isfinite(result).all():
        raise ValueError("Nonfinite propagated error")
    return result


def propagate_box(arc_length: Any, curvature: Real, initial_bounds: Any) -> np.ndarray:
    """Exact sampled component bounds for a deterministic input box, not RSS.

    Reuses the original signed-pose operator at all four box corners. Each output
    component may attain its maximum at a different corner; this is not a joint
    probability region or a guarantee between supplied arclength samples.
    """
    bounds = _array(initial_bounds, (2,))
    if np.any(bounds < 0):
        raise ValueError("Box half-widths must be nonnegative")
    mapping = transfer_map(arc_length, curvature)
    with np.errstate(over="raise", invalid="raise", under="raise"):
        corners = [np.column_stack(mapping.propagate(x * bounds[0], y * bounds[1]))
                   for x in (-1, 1) for y in (-1, 1)]
        result = np.max(np.abs(corners), axis=0)
    if not np.isfinite(result).all():
        raise ValueError("Nonfinite propagated bound")
    return result


def propagate_covariance(arc_length: Any, curvature: Real, covariance: Any) -> np.ndarray:
    """Return full (n,2,2) marginal covariances using the existing strict kernel.

    Cross terms are retained. This does not invent measurement noise, confidence
    levels, independent errors, nonlinear validity or cross-sample independence.
    """
    covariance = _array(covariance, (2, 2))
    return transfer_map(arc_length, curvature).propagate_covariance(covariance).copy()


def evaluate(operation_id: str, request: dict) -> dict:
    """Language-neutral data operation; pure request in, detached finite JSON out."""
    if operation_id not in OPERATIONS:
        raise ValueError("Unknown micro-tool operation")
    extra = {OPERATIONS[0]: {"initial_error"}, OPERATIONS[1]: {"initial_bounds", "tolerances"},
             OPERATIONS[2]: {"covariance"}}[operation_id]
    common = {"arc_length", "curvature", "length_unit", "frame"}
    if type(request) is not dict or set(request) != common | extra:
        raise ValueError("Request fields differ from the selected operation")
    if request["length_unit"] not in ("m", "cm", "mm"):
        raise ValueError("Declare m, cm or mm; no implicit unit conversion")
    if (type(request["frame"]) is not str or not request["frame"].strip()
            or len(request["frame"]) > 256):
        raise ValueError("An explicit bounded frame identity is required")
    # The wire contract is JSON only. Arrays are supported by the three APIs above.
    captured = json.loads(json.dumps(request, allow_nan=False))
    mapping = transfer_map(captured["arc_length"], captured["curvature"])
    check = None
    if operation_id == OPERATIONS[0]:
        values = propagate_pose(
            captured["arc_length"], captured["curvature"], captured["initial_error"])
    elif operation_id == OPERATIONS[1]:
        limits = _array(captured["tolerances"], (2,))
        if np.any(limits < 0):
            raise ValueError("Tolerances must be nonnegative")
        values = propagate_box(
            captured["arc_length"], captured["curvature"], captured["initial_bounds"])
        excess = values - limits
        check = {"status": "PASS" if np.all(excess <= 0) else "FAIL",
                 "maximum_excess": np.max(excess, axis=0).tolist(),
                 "sample_pass": np.all(excess <= 0, axis=1).tolist()}
    else:
        values = propagate_covariance(
            captured["arc_length"], captured["curvature"], captured["covariance"])
    result = {"schema": SCHEMA, "operation_id": operation_id, "request": captured,
              "model": MODEL, "coordinate": "arc_length", "basis": ["lateral", "heading"],
              "units": [captured["length_unit"], "rad"], "scope": SCOPE,
              "transfer_matrices": mapping.matrices().tolist(), "values": values.tolist(),
              "tolerance_check": check, "verification_id": None,
              "verification_status": "not_verified"}
    json.dumps(result, allow_nan=False)
    return deepcopy(result)


def _decode(raw: bytes) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    def floating(text):
        value = float(text)
        if not math.isfinite(value) or (value == 0 and Decimal(text) != 0):
            raise ValueError("Nonfinite or underflowed JSON number")
        return value
    def constant(text):
        raise ValueError("Nonfinite JSON number: " + text)
    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                      parse_float=floating, parse_constant=constant)


def main() -> int:
    """One bounded CIW transport envelope on stdin/stdout; never import saved code."""
    try:
        raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES:
            raise ValueError("Request exceeds byte budget")
        envelope = _decode(raw)
        if (type(envelope) is not dict or set(envelope) != {"schema", "operation_id", "inputs"}
                or envelope["schema"] != "ciw.adapter-request.v1"):
            raise ValueError("Unknown adapter request envelope")
        data = evaluate(envelope["operation_id"], envelope["inputs"])
        response = {"schema": "ciw.adapter-response.v1", "status": "ok", "data": data}
    except (ValueError, TypeError, KeyError, OverflowError,
            FloatingPointError, RecursionError) as exc:
        response = {"schema": "ciw.adapter-response.v1", "status": "refused",
                    "refusal": {"code": "CSR_MICROTOOL_REFUSED",
                                "message": str(exc)[:512] or "Invalid request"}}
    print(json.dumps(response, allow_nan=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
