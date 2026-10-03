# SPDX-License-Identifier: MPL-2.0
"""Bounded signal-domain operations; no evidence admission or estimation."""

from .window import ContractError, OPERATION_ID, window_mean

__all__ = ["ContractError", "OPERATION_ID", "window_mean"]

