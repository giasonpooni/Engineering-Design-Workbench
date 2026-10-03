"""Affine Kalman identities on the additive group (R^n, +).

Left and right invariant errors coincide. Prediction of the error is exact.
The update is ordinary Gaussian conditioning. This is not an IEKF on a
non-commutative Lie group.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

from .coordinates import (
    AffineCoordinates,
    apply_input_map,
    check_mean_fidelity,
    invert_input_map,
    push_covariance,
)
from .covariance import first_order_covariance, _require_psd
from .models import as_vector

Array = NDArray[np.floating]


def _immutable(value: Array) -> Array:
    return np.frombuffer(value.tobytes(order="C"), dtype=value.dtype).reshape(value.shape)


@dataclass(frozen=True)
class GaussianState:
    mean: Array
    covariance: Array

    def __post_init__(self) -> None:
        mean = as_vector(self.mean, "mean")
        if mean.size < 1:
            raise ValueError("mean must contain at least one component")
        cov = _require_psd(np.asarray(self.covariance, dtype=float), "state covariance")
        if cov.shape != (mean.size, mean.size):
            raise ValueError("covariance must match the mean dimension")
        object.__setattr__(self, "mean", _immutable(mean))
        object.__setattr__(self, "covariance", _immutable(cov))

    @property
    def dim(self) -> int:
        return int(self.mean.size)


@dataclass(frozen=True)
class AffinePlant:
    F: Array
    drift: Array
    Q: Array
    H: Array
    offset: Array
    R: Array

    def __post_init__(self) -> None:
        F = np.asarray(self.F, dtype=float)
        H = np.asarray(self.H, dtype=float)
        if F.ndim != 2 or F.shape[0] != F.shape[1]:
            raise ValueError("F must be square")
        n = F.shape[0]
        drift = as_vector(self.drift, "drift")
        offset = as_vector(self.offset, "offset")
        if drift.size != n:
            raise ValueError("drift must match F")
        if H.ndim != 2 or H.shape[1] != n:
            raise ValueError("H must be (m, n)")
        if offset.size != H.shape[0]:
            raise ValueError("offset must match H rows")
        Q = _require_psd(np.asarray(self.Q, dtype=float), "Q")
        R = _require_psd(np.asarray(self.R, dtype=float), "R")
        if Q.shape != (n, n):
            raise ValueError("Q must be (n, n)")
        if R.shape != (H.shape[0], H.shape[0]):
            raise ValueError("R must be (m, m)")
        object.__setattr__(self, "F", np.asarray(F, dtype=float))
        object.__setattr__(self, "H", np.asarray(H, dtype=float))
        object.__setattr__(self, "drift", drift)
        object.__setattr__(self, "offset", offset)
        object.__setattr__(self, "Q", Q)
        object.__setattr__(self, "R", R)

    @property
    def state_dim(self) -> int:
        return int(self.F.shape[0])

    @property
    def measurement_dim(self) -> int:
        return int(self.H.shape[0])


@dataclass(frozen=True)
class UpdateResult:
    prior: GaussianState
    posterior: GaussianState
    innovation: Array
    innovation_covariance: Array
    gain: Array
    correction: Array
    statistic: float | None
    dof: int
    status: str


def invariant_error(reference: ArrayLike, state: ArrayLike) -> Array:
    ref = as_vector(reference, "reference")
    val = as_vector(state, "state")
    if ref.size != val.size:
        raise ValueError("reference and state must have the same dimension")
    return val - ref


def retract(reference: ArrayLike, error: ArrayLike) -> Array:
    ref = as_vector(reference, "reference")
    err = as_vector(error, "error")
    if ref.size != err.size:
        raise ValueError("reference and error must have the same dimension")
    return ref + err


def predict(state: GaussianState, plant: AffinePlant) -> GaussianState:
    if state.dim != plant.state_dim:
        raise ValueError("state dimension does not match the plant")
    mean = plant.F @ state.mean + plant.drift
    covariance = first_order_covariance(plant.F, state.covariance) + plant.Q
    return GaussianState(mean, covariance)


def update(state: GaussianState, plant: AffinePlant, measurement: ArrayLike) -> UpdateResult:
    if state.dim != plant.state_dim:
        raise ValueError("state dimension does not match the plant")
    z = as_vector(measurement, "measurement")
    if z.size != plant.measurement_dim:
        raise ValueError("measurement dimension does not match the plant")
    expected = plant.H @ state.mean + plant.offset
    innovation = invariant_error(expected, z)
    pht = state.covariance @ plant.H.T
    innovation_cov = plant.H @ pht + plant.R
    innovation_cov = _require_psd(innovation_cov, "innovation covariance")
    if np.any(np.diag(innovation_cov) <= 0.0):
        raise ValueError("innovation covariance must be positive definite")
    try:
        gain = np.linalg.solve(innovation_cov, pht.T).T
        whitened = np.linalg.solve(np.linalg.cholesky(innovation_cov), innovation)
    except np.linalg.LinAlgError as exc:
        raise ValueError("innovation covariance must be positive definite") from exc
    correction = gain @ innovation
    residual_map = np.eye(state.dim) - gain @ plant.H
    posterior_cov = residual_map @ state.covariance @ residual_map.T + gain @ plant.R @ gain.T
    statistic = float(whitened @ whitened)
    posterior = GaussianState(retract(state.mean, correction), posterior_cov)
    return UpdateResult(
        prior=state,
        posterior=posterior,
        innovation=innovation,
        innovation_covariance=innovation_cov,
        gain=gain,
        correction=correction,
        statistic=statistic,
        dof=int(z.size),
        status="updated",
    )


def transform_state(state: GaussianState, coordinates: AffineCoordinates) -> GaussianState:
    if coordinates.T.shape[0] != state.dim:
        raise ValueError("chart T does not match the state")
    mean = apply_input_map(state.mean, coordinates)
    recovered = invert_input_map(mean, coordinates)
    check_mean_fidelity(state.mean, recovered, state.covariance, "state mean")
    covariance = push_covariance(coordinates.T, state.covariance, name="state covariance")
    return GaussianState(mean, covariance)


def restore_state(state: GaussianState, coordinates: AffineCoordinates) -> GaussianState:
    if coordinates.T.shape[0] != state.dim:
        raise ValueError("chart T does not match the state")
    mean = invert_input_map(state.mean, coordinates)
    recovered = apply_input_map(mean, coordinates)
    check_mean_fidelity(state.mean, recovered, state.covariance, "state mean")
    covariance = push_covariance(
        coordinates.T, state.covariance, inverse=True, name="state covariance"
    )
    return GaussianState(mean, covariance)


def transform_plant(plant: AffinePlant, coordinates: AffineCoordinates) -> AffinePlant:
    if coordinates.T.shape[0] != plant.state_dim:
        raise ValueError("chart T does not match the plant state")
    if coordinates.S.shape[0] != plant.measurement_dim:
        raise ValueError("chart S does not match the measurement")
    t, s = coordinates.T, coordinates.S
    t_inv = coordinates.T_inv
    c = coordinates.input_offset
    b = coordinates.output_offset
    f_prime = t @ plant.F @ t_inv
    drift_prime = t @ plant.drift + c - f_prime @ c
    recovered_drift = t_inv @ (drift_prime - c + f_prime @ c)
    check_mean_fidelity(plant.drift, recovered_drift, plant.Q, "dynamics drift")
    q_prime = push_covariance(t, plant.Q, name="Q")
    h_prime = s @ plant.H @ t_inv
    offset_prime = s @ plant.offset + b - h_prime @ c
    r_prime = push_covariance(s, plant.R, name="R")
    return AffinePlant(f_prime, drift_prime, q_prime, h_prime, offset_prime, r_prime)
