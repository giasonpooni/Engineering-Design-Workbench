"""Bounded display algebra for retained covariance/innovation records.

Not an estimator, covariance propagator, geodesic metric or statistical test.
Uses the installed NumPy decompositions; never repairs a supplied matrix.
"""
from __future__ import annotations

import math
import numpy as np

from .control_contracts import number

PROFILE = "ciw.uncertainty-display-algebra.v1"
CONDITION_LIMIT = 1e12
CONTOUR_SEGMENTS = 64


def _matrix(value: list, dimension: int) -> np.ndarray:
    if type(value) is not list or len(value) != dimension:
        raise ValueError("Display covariance dimension must match its values")
    if any(type(row) is not list or len(row) != dimension for row in value):
        raise ValueError("Display covariance must be a square matrix")
    return np.array([[number(entry) for entry in row] for row in value], dtype=float)


def covariance_geometry(matrix: list) -> dict:
    """One/two-dimensional same-unit covariance, for mathematical display only.

    A radius-k contour is mu + k L u(theta), LL^T=P. It is not a k-sigma
    simultaneous coverage assertion. Singular/asymmetric/ill-conditioned inputs
    remain visible as matrices, but receive no invented ellipse or repair.
    """
    if type(matrix) is not list or not 1 <= len(matrix) <= 2:
        raise ValueError("This display kernel supports one or two coordinates")
    p = _matrix(matrix, len(matrix))
    absent = {"status": "unavailable", "reason": None, "marginal_sigma": None,
              "correlation": None, "lower_factor": None, "principal_variances": None,
              "condition_number": None, "log_volume": None, "unit_contour": None}
    if not np.array_equal(p, p.T):
        return {**absent, "reason": "asymmetric_no_repair"}
    try:
        eigenvalues = np.linalg.eigvalsh(p)
        if not np.all(np.isfinite(eigenvalues)) or np.any(eigenvalues <= 0):
            return {**absent, "reason": "not_numerically_positive_definite"}
        condition = float(eigenvalues[-1] / eigenvalues[0])
        if not math.isfinite(condition) or condition > CONDITION_LIMIT:
            return {**absent, "reason": "display_condition_limit"}
        lower = np.linalg.cholesky(p)
    except np.linalg.LinAlgError:
        return {**absent, "reason": "decomposition_unavailable"}
    sigma = np.sqrt(np.diag(p))
    correlation = (p / sigma[:, None]) / sigma[None, :]
    contour = None
    if len(p) == 2:
        contour = [(lower @ np.array([math.cos(2 * math.pi * i / CONTOUR_SEGMENTS),
                                     math.sin(2 * math.pi * i / CONTOUR_SEGMENTS)])).tolist()
                   for i in range(CONTOUR_SEGMENTS)]
        contour.append(list(contour[0]))
    return {"status": "available", "reason": "positive_definite_in_display_profile",
            "marginal_sigma": sigma.tolist(), "correlation": correlation.tolist(),
            "lower_factor": lower.tolist(), "principal_variances": eigenvalues.tolist(),
            "condition_number": condition,
            "log_volume": float(sum(math.log(float(entry)) for entry in np.diag(lower))),
            "unit_contour": contour}


def whiten_innovation(innovation: list, matrix: list) -> dict:
    """Lz=r, LL^T=S. Components follow a triangular basis, not sensor attribution."""
    if type(innovation) is not list or len(innovation) > 2:
        raise ValueError("This display kernel supports at most two innovations")
    if not innovation:
        if matrix != []:
            raise ValueError("An absent innovation must have an empty covariance")
        return {"status": "missing", "reason": "no_available_measurements",
                "dimension": 0, "components": None, "squared_norm": None}
    vector = np.array([number(value) for value in innovation])
    _matrix(matrix, len(vector))
    geometry = covariance_geometry(matrix)
    if geometry["status"] != "available":
        return {"status": "unavailable", "reason": geometry["reason"],
                "dimension": len(vector), "components": None, "squared_norm": None}
    try:
        components = np.linalg.solve(np.array(geometry["lower_factor"]), vector)
        squared = number(float(components @ components))
    except (np.linalg.LinAlgError, ValueError, OverflowError):
        return {"status": "unavailable", "reason": "whitening_outside_display_range",
                "dimension": len(vector), "components": None, "squared_norm": None}
    return {"status": "available", "reason": "retained_prior_innovation_cholesky_basis",
            "dimension": len(vector), "components": components.tolist(), "squared_norm": squared}


def conditioning_gain(predicted: dict, posterior: dict) -> float | None:
    """Half log-determinant ratio, conditional on this declared Gaussian model.

    Not empirical information, not an independence assertion across ticks, and
    not an instruction to change the original sensor-selection decision.
    """
    if predicted["status"] != "available" or posterior["status"] != "available":
        return None
    return number(predicted["log_volume"] - posterior["log_volume"])
