# SPDX-License-Identifier: MPL-2.0
"""Deterministic linear Gaussian filtering with explicit local-angle support."""

import json

import numpy as np

from .contracts import (
    Estimate, LinearDynamics, LinearObservation, Observation, StatePrior,
    _digest, _json, _time,
)
from .geometry import EuclideanGeometry, SO2Geometry
from .numerics import covariance_sum


PREDICT_OPERATION = "geometric-state-inference.predict.v1"
UPDATE_OPERATION = "geometric-state-inference.update.v1"
REPLAY_SCHEMA = "geometric-state-inference.replay.v1"


def _geometry_name(geometry) -> str:
    return "so2_scalar_radians.v1" if isinstance(geometry, SO2Geometry) else "euclidean.v1"


def _state_snapshot(state: StatePrior) -> dict:
    return {"time": state.time, "mean": state.mean.tolist(),
            "covariance": state.covariance.tolist(), "frame_id": state.frame_id,
            "units": list(state.units), "state_id": state.state_id,
            "dynamics_model_id": state.dynamics_model_id,
            "predecessor_state_id": state.predecessor_state_id,
            "operation_ref": state.operation_ref, "replay": state.replay_snapshot}


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
    Output state identity binds the predecessor, operation, full numerical
    configuration and output. It is distinct from a runtime execution identity.
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
    covariance = covariance_sum((dynamics.matrix, prior.covariance),
                                (np.eye(prior.mean.size), dynamics.process_covariance))
    snapshot = {"schema": REPLAY_SCHEMA, "operation_ref": PREDICT_OPERATION,
                "prior": _state_snapshot(prior), "time": time,
                "dynamics": {"matrix": dynamics.matrix.tolist(),
                             "process_covariance": dynamics.process_covariance.tolist(),
                             "model_id": dynamics.model_id},
                "state_geometry": _geometry_name(geometry)}
    state_id = _digest("geometric-state-inference.state-transition.v1", {
        "configuration": snapshot, "mean": mean.tolist(), "covariance": covariance.tolist()})
    return StatePrior(time, mean, covariance, prior.frame_id, prior.units,
                      state_id, dynamics.model_id, prior.state_id,
                      PREDICT_OPERATION, _json(snapshot))


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
    innovation_covariance = covariance_sum((matrix, prior.covariance),
        (np.eye(observation.values.size), observation.covariance))
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
    covariance = covariance_sum((remainder, prior.covariance),
                                (gain, observation.covariance))
    residual = measurement_geom.difference(observation.values, matrix @ mean)
    nis = float(innovation @ weighted_innovation)
    if nis == 0 and np.any(innovation != 0):
        raise ValueError("NIS underflow would erase a nonzero innovation")
    snapshot = {"schema": REPLAY_SCHEMA, "operation_ref": UPDATE_OPERATION,
                "prior": _state_snapshot(prior),
                "observation": {"time": observation.time, "values": observation.values.tolist(),
                    "covariance": observation.covariance.tolist(), "frame_id": observation.frame_id,
                    "units": list(observation.units), "observation_id": observation.observation_id,
                    "evidence_refs": list(observation.evidence_refs)},
                "model": {"matrix": model.matrix.tolist(), "model_id": model.model_id,
                    "measurement_geometry": _geometry_name(measurement_geom),
                    "measurement_units": list(measurement_units),
                    "measurement_frame_id": measurement_frame},
                "state_geometry": _geometry_name(state_geom),
                "noise_policy": "measurement_independent_of_prior"}
    state_id = _digest("geometric-state-inference.state-transition.v1", {
        "configuration": snapshot, "mean": mean.tolist(), "covariance": covariance.tolist()})
    return Estimate(prior.time, mean, covariance, prior.frame_id, prior.units,
                    innovation, innovation_covariance, residual, nis,
                    observation.observation_id, observation.evidence_refs,
                    model.model_id, prior.dynamics_model_id, prior.state_id,
                    state_id, _json(snapshot))


def _restore_geometry(name: str):
    if name == "euclidean.v1":
        return EuclideanGeometry()
    if name == "so2_scalar_radians.v1":
        return SO2Geometry()
    raise ValueError("replay geometry is not a supported declared geometry")


def _replay(snapshot: dict, depth: int = 0):
    if depth > 64:
        raise ValueError("replay exceeds 64 predecessor transitions")
    if not isinstance(snapshot, dict) or snapshot.get("schema") != REPLAY_SCHEMA:
        raise ValueError("replay requires the supported schema")
    prior_data = dict(snapshot["prior"])
    preceding = prior_data.pop("replay", None)
    prior = StatePrior(**prior_data, replay_json=None if preceding is None else _json(preceding))
    if preceding is not None:
        rebuilt = _replay(preceding, depth + 1)
        if isinstance(rebuilt, Estimate):
            rebuilt = rebuilt.as_prior(prior.state_id)  # explicit caller aliases are retained
        if _state_snapshot(rebuilt) != _state_snapshot(prior):
            raise ValueError("replay prior differs from the preceding transition")
    geometry = _restore_geometry(snapshot["state_geometry"])
    if snapshot.get("operation_ref") == PREDICT_OPERATION:
        result = predict(prior, LinearDynamics(**snapshot["dynamics"]), snapshot["time"], geometry)
    elif snapshot.get("operation_ref") == UPDATE_OPERATION:
        if snapshot.get("noise_policy") != "measurement_independent_of_prior":
            raise ValueError("replay noise policy is not supported")
        observation = Observation(**snapshot["observation"])
        model_data = dict(snapshot["model"])
        model_data["measurement_geometry"] = _restore_geometry(model_data["measurement_geometry"])
        result = update(prior, observation, LinearObservation(**model_data), geometry)
    else:
        raise ValueError("replay operation is not supported")
    if result.replay_snapshot != snapshot:
        raise ValueError("replay content differs from normalized operation configuration")
    return result


def replay_estimate(snapshot: dict) -> Estimate:
    """Replay retained local operations only; never import artifact-named code.

    Content replay establishes agreement with this implementation, not an
    independent verification, authenticated source or scientific truth claim.
    """
    detached = json.loads(_json(snapshot))
    try:
        result = _replay(detached)
    except (KeyError, TypeError, RecursionError) as exc:
        raise ValueError("malformed replay snapshot") from exc
    if not isinstance(result, Estimate):
        raise ValueError("estimate replay must end with an update")
    return result
