"""Prior-normalized covariance display, not inference or sensor optimization.

Compare retained P (before) and Q (after) in the same declared coordinate order.
The parent inspector establishes their scientific and provenance bindings.
"""
from __future__ import annotations

import math
import numpy as np

from .control_contracts import number
from .uncertainty_display import CONDITION_LIMIT, CONTOUR_SEGMENTS, covariance_geometry, _matrix

PROFILE = "ciw.covariance-contraction-display.v1"
DIRECTION_SAMPLES = 72
RELATION_TOLERANCE = 1e-10


def contraction_geometry(prior: list, posterior: list) -> dict:
    """Display W=L^-1 Q L^-T, P=LL^T, using triangular solves, not an inverse.

    Eigenvalues are generalized variance ratios; they are invariant under an
    invertible common coordinate change (within the numerical display domain).
    Angles live in the prior Cholesky basis, not physical sensor directions.
    Neither input is symmetrized, clipped, regularized, or modified.
    """
    _matrix(prior, 2)
    _matrix(posterior, 2)
    before, after = covariance_geometry(prior), covariance_geometry(posterior)
    absent = {"status": "unavailable", "reason": None, "normalized_covariance": None,
              "variance_ratios": None, "condition_number": None, "relation": None,
              "information_gain_nats": None, "area_ratio": None,
              "unit_contour": None, "directions": None}
    for label, value in (("prior", before), ("posterior", after)):
        if value["status"] != "available":
            return {**absent, "reason": label + ":" + value["reason"]}
    try:
        # B B^T forms the derived symmetric matrix directly; no repair of inputs.
        b = np.linalg.solve(np.asarray(before["lower_factor"]), np.asarray(after["lower_factor"]))
        w = b @ b.T
        singular = np.linalg.svd(b, compute_uv=False)
        ratios = (singular[::-1] ** 2).tolist()
        if any(not math.isfinite(x) or x <= 0 for x in ratios):
            return {**absent, "reason": "nonpositive_or_nonfinite_relative_variance"}
        condition = ratios[-1] / ratios[0]
        if not math.isfinite(condition) or condition > CONDITION_LIMIT:
            return {**absent, "reason": "relative_display_condition_limit"}
        gain = number(-sum(math.log(float(x)) for x in singular))
        expected = before["log_volume"] - after["log_volume"]
        if not math.isclose(gain, expected, rel_tol=1e-10, abs_tol=1e-12):
            return {**absent, "reason": "relative_volume_consistency_unresolved"}
        area = number(math.exp(-gain))
        contour = [(b @ np.array([math.cos(2 * math.pi * i / CONTOUR_SEGMENTS),
                                 math.sin(2 * math.pi * i / CONTOUR_SEGMENTS)])).tolist()
                   for i in range(CONTOUR_SEGMENTS)]
        contour.append(list(contour[0]))
        directions = []
        for i in range(DIRECTION_SAMPLES):
            theta = 2 * math.pi * i / DIRECTION_SAMPLES
            n = np.array([math.cos(theta), math.sin(theta)])
            variance = number(float(n @ w @ n))
            if variance <= 0:
                return {**absent, "reason": "directional_variance_outside_display_range"}
            sigma = math.sqrt(variance)
            # Support point on the ellipse in direction n; not its radial intercept.
            directions.append({"angle_degrees": i * 360 // DIRECTION_SAMPLES,
                "unit_direction": n.tolist(), "variance_ratio": variance,
                "standard_deviation_ratio": sigma,
                "support_point": (w @ n / sigma).tolist(),
                "projection_point": (sigma * n).tolist()})
    except (np.linalg.LinAlgError, ValueError, OverflowError, FloatingPointError):
        return {**absent, "reason": "relative_decomposition_unavailable"}
    t = RELATION_TOLERANCE
    if max(abs(x - 1) for x in ratios) <= t:
        relation = "unchanged_within_display_tolerance"
    elif ratios[-1] <= 1 + t:
        relation = "contraction_within_display_tolerance"
    elif ratios[0] >= 1 - t:
        relation = "expansion_within_display_tolerance"
    else:
        relation = "mixed_directional_change"
    return {"status": "available", "reason": "retained_covariance_pair_in_display_domain",
        "normalized_covariance": w.tolist(), "variance_ratios": ratios,
        "condition_number": number(condition), "relation": relation,
        "information_gain_nats": gain, "area_ratio": area,
        "unit_contour": contour, "directions": directions}
