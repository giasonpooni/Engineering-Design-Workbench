# SPDX-License-Identifier: MPL-2.0
"""Residual diagnostics that report statistical anomalies, never control actions."""

from .diagnostics import (
    CusumResult,
    CusumState,
    ResidualDiagnostics,
    cusum_step,
    evaluate_residual,
)

__all__ = [
    "CusumResult", "CusumState", "ResidualDiagnostics",
    "cusum_step", "evaluate_residual",
]
