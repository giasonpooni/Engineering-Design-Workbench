# SPDX-License-Identifier: MPL-2.0
"""Euclidean coordinates and a deliberately scalar SO(2) local-angle example."""

import numpy as np


class EuclideanGeometry:
    def validate(self, size: int, units: tuple[str, ...]) -> None:
        if size != len(units):
            raise ValueError("geometry dimension and units must match")

    def normalize(self, value: np.ndarray) -> np.ndarray:
        return np.asarray(value, dtype=float)

    def difference(self, value: np.ndarray, reference: np.ndarray) -> np.ndarray:
        return np.asarray(value) - np.asarray(reference)

    def retract(self, value: np.ndarray, tangent: np.ndarray) -> np.ndarray:
        return np.asarray(value) + np.asarray(tangent)


class SO2Geometry:
    """One angle in radians, with covariance in its local tangent coordinate.

    This is a local Gaussian approximation. It does not represent multimodal
    circular uncertainty, rotations in 3D, full poses, or a Lie-group EKF.
    """

    def validate(self, size: int, units: tuple[str, ...]) -> None:
        if size != 1 or units != ("rad",):
            raise ValueError("SO2Geometry requires exactly one angle with units ('rad',)")

    def normalize(self, value: np.ndarray) -> np.ndarray:
        value = np.asarray(value, dtype=float)
        if value.shape != (1,):
            raise ValueError("SO2Geometry requires one scalar angle")
        return (value + np.pi) % (2 * np.pi) - np.pi

    def difference(self, value: np.ndarray, reference: np.ndarray) -> np.ndarray:
        return self.normalize(np.asarray(value) - np.asarray(reference))

    def retract(self, value: np.ndarray, tangent: np.ndarray) -> np.ndarray:
        return self.normalize(np.asarray(value) + np.asarray(tangent))
