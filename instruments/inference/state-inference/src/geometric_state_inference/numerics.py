# SPDX-License-Identifier: MPL-2.0
"""Guard covariance congruences against floating-point false certainty.

The ordinary path uses float64 products. Cancellation-prone or zero output
variances trigger exact rational evaluation of the stored binary64 operands.
This is a numerical reference fallback, not a covariance repair or an assertion
that the supplied covariance accurately models a physical process.
"""

from fractions import Fraction

import numpy as np

from .contracts import _covariance, _symmetric_average


def covariance_sum(*terms: tuple[np.ndarray, np.ndarray]) -> np.ndarray:
    """Return sum(A P A.T), refusing nonzero uncertainty rounded to zero."""
    size = terms[0][0].shape[0]
    result = np.zeros((size, size))
    magnitude = np.zeros_like(result)
    support = np.zeros((size, size), dtype=bool)
    dimension = max(covariance.shape[0] for _, covariance in terms)
    with np.errstate(over="ignore", under="ignore", invalid="ignore"):
        for matrix, covariance in terms:
            result += matrix @ covariance @ matrix.T
            absolute = np.abs(matrix)
            magnitude += absolute @ np.abs(covariance) @ absolute.T
            # Boolean products preserve possible paths even where float64
            # magnitudes underflow. Correlation must not disappear silently
            # merely because the component variances remain healthy.
            active = matrix != 0
            support |= active @ (covariance != 0) @ active.T
    diagonal = np.diag(result)
    threshold = 64 * np.finfo(float).eps * dimension * np.diag(magnitude)
    suspect = (not np.all(np.isfinite(result))
               or not np.all(np.isfinite(magnitude))
               or np.any((diagonal <= threshold) & np.diag(support))
               or np.any((result == 0) & support))
    if not suspect:
        return _covariance(_symmetric_average(result), size, "computed covariance")

    # Matrix multiplication with exact rational binary64 inputs. Unlike a
    # higher-precision float, this can decide true zero even after cancellation
    # and detect values below the float64 subnormal range on every platform.
    exact = [[Fraction(0) for _ in range(size)] for _ in range(size)]
    for matrix, covariance in terms:
        a = [[Fraction(float(v)) for v in row] for row in matrix]
        p = [[Fraction(float(v)) for v in row] for row in covariance]
        count = len(p)
        ap = [[sum((a[i][k] * p[k][j] for k in range(count)), Fraction(0))
               for j in range(count)] for i in range(size)]
        for i in range(size):
            for j in range(i, size):
                exact[i][j] += sum((ap[i][k] * a[j][k] for k in range(count)), Fraction(0))
    for i in range(size):
        for j in range(i, size):
            value = exact[i][j]
            try:
                rounded = float(value)
            except OverflowError as exc:
                raise ValueError("computed covariance overflows float64") from exc
            if value and rounded == 0:
                raise ValueError("computed covariance underflow would erase nonzero uncertainty")
            result[i, j] = result[j, i] = rounded
    return _covariance(result, size, "computed covariance")
