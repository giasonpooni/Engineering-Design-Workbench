# SPDX-License-Identifier: MPL-2.0
"""Deterministic linear Gaussian filtering with explicit local-angle support."""

import numpy as np

from .contracts import (
    Estimate, LinearDynamics, LinearObservation, Observation, StatePrior,
    _symmetric_average, _time,
)
from .geometry import EuclideanGeometry, SO2Geometry


def _geometry(value, size: int, units: tuple[str, ...]):
    geometry = EuclideanGeometry() if value is None else value
    if not isinstance(geometry, (EuclideanGeometry, SO2Geometry)):
        raise ValueError("supported geometry is EuclideanGeometry or scalar SO2Geometry")
    geometry.validate(size, units)
    return geometry


def predict(prior: StatePrior, dynamics: LinearDynamics, time: float,
            state_geometry=None) -> StatePrior:
    """Propagate using caller-discretized F and Q; time must increase strictly.

    No time scaling or discretization is inferred from a model identifier.
    The output retains its originating state_id and records dynamics.model_id.
    """
    time = _time(time)
    if time <= prior.time:
        raise ValueError("prediction time must be strictly greater than prior time")
    if dynamics.matrix.shape != (prior.mean.size, prior.mean.size):
        raise ValueError("dynamics matrix dimensions must match the state")
    geometry = _geometry(state_geometry, prior.mean.size, prior.units)
    if isinstance(geometry, SO2Geometry) and not np.array_equal(dynamics.matrix, [[1.0]]):
        raise ValueError("scalar SO2 propagation currently supports only identity dynamics")
    mean = geometry.normalize(dynamics.matrix @ prior.mean)
    covariance = dynamics.matrix @ prior.covariance @ dynamics.matrix.T + dynamics.process_covariance
    covariance = _symmetric_average(covariance)
    return StatePrior(time, mean, covariance, prior.frame_id, prior.units,
                      prior.state_id, dynamics.model_id)


def update(prior: StatePrior, observation: Observation, model: LinearObservation,
           state_geometry=None) -> Estimate:
    """Assimilate one independent measurement at exactly the prior timestamp.

    Uses linear solves and the Joseph covariance update. Singular innovation
    covariance is rejected rather than silently regularized. NIS is the squared
    Mahalanobis innovation; it is diagnostic and does not certify consistency.
    """
    if observation.time != prior.time:
        raise ValueError("observation time must equal prior time; predict explicitly first")
    matrix = model.matrix
    if matrix.shape != (observation.values.size, prior.mean.size):
        raise ValueError("observation matrix dimensions must match measurement and state")
    measurement_units = prior.units if model.measurement_units is None else model.measurement_units
    if len(measurement_units) != observation.values.size:
        raise ValueError("dimension-changing observation models require measurement_units")
    if observation.units != measurement_units:
        raise ValueError("observation units must match model measurement units")
    measurement_frame = prior.frame_id if model.measurement_frame_id is None else model.measurement_frame_id
    if observation.frame_id != measurement_frame:
        raise ValueError("observation frame must match model measurement frame")
    state_geom = _geometry(state_geometry, prior.mean.size, prior.units)
    measurement_geom = _geometry(model.measurement_geometry, observation.values.size, observation.units)
    if isinstance(state_geom, SO2Geometry):
        if not isinstance(measurement_geom, SO2Geometry) or not np.array_equal(matrix, [[1.0]]):
            raise ValueError("scalar SO2 updates require identity H and SO2 measurement geometry")
    elif isinstance(measurement_geom, SO2Geometry):
        raise ValueError("SO2 measurement geometry requires SO2 state geometry")

    innovation = measurement_geom.difference(observation.values, matrix @ prior.mean)
    cross_covariance = prior.covariance @ matrix.T
    innovation_covariance = matrix @ cross_covariance + observation.covariance
    innovation_covariance = _symmetric_average(innovation_covariance)
    if not np.all(np.isfinite(innovation_covariance)):
        raise ValueError("innovation covariance must be finite")
    try:
        np.linalg.cholesky(innovation_covariance)
        gain = np.linalg.solve(innovation_covariance, cross_covariance.T).T
        weighted_innovation = np.linalg.solve(innovation_covariance, innovation)
    except np.linalg.LinAlgError as exc:
        raise ValueError("innovation covariance must be positive definite") from exc
    mean = state_geom.retract(prior.mean, gain @ innovation)
    remainder = np.eye(prior.mean.size) - gain @ matrix
    covariance = (remainder @ prior.covariance @ remainder.T
                  + gain @ observation.covariance @ gain.T)
    covariance = _symmetric_average(covariance)
    residual = measurement_geom.difference(observation.values, matrix @ mean)
    nis = float(innovation @ weighted_innovation)
    return Estimate(prior.time, mean, covariance, prior.frame_id, prior.units,
                    innovation, innovation_covariance, residual, nis,
                    observation.observation_id, observation.evidence_refs,
                    model.model_id, prior.dynamics_model_id, prior.state_id)
