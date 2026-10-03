"""Chart covariance. AffineCoordinates._map_covariance must call this."""

from __future__ import annotations

from numpy.typing import ArrayLike


def map_covariance(matrix: ArrayLike, covariance: ArrayLike, *, inverse: bool = False):
    from sensitivity.coordinates import push_covariance

    return push_covariance(matrix, covariance, inverse=inverse)
