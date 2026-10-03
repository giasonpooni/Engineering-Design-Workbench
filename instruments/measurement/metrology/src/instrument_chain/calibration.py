"""Declared conversion y = g(r; theta). Not a buried firmware constant."""

from __future__ import annotations

from .manifest import Calibration


class CalibrationError(ValueError):
    """Conversion refused: range, method, or missing raw."""


def apply_calibration(raw: float | None, cal: Calibration) -> float:
    if raw is None:
        raise CalibrationError("no raw observation to convert")
    raw = float(raw)
    if raw < cal.range_min or raw > cal.range_max:
        raise CalibrationError(
            f"raw {raw} outside declared calibration range [{cal.range_min}, {cal.range_max}]"
        )
    if cal.method in {"linear", "affine"}:
        scale, zero_or_offset = cal.theta
        # linear: y = scale * (raw - zero_raw)
        # affine stored the same way for this release
        return scale * (raw - zero_or_offset)
    raise CalibrationError(f"unsupported method {cal.method!r}")
