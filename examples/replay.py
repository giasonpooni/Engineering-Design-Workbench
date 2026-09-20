# SPDX-License-Identifier: MPL-2.0
"""Replay declared synthetic scalar observations and a heading branch crossing."""

import json
from pathlib import Path

import numpy as np

from geometric_state_inference import (
    LinearDynamics, LinearObservation, Observation, SO2Geometry, StatePrior,
    predict, update,
)


def replay():
    fixture = json.loads((Path(__file__).parent / "fixtures/scalar.json").read_text())
    initial = fixture["prior"]
    prior = StatePrior(initial["time"], initial["mean"], initial["covariance"],
                       fixture["frame_id"], tuple(fixture["units"]), "example:prior-0")
    dynamics = LinearDynamics([[1.0]], [[fixture["process_variance"]]],
                              "example:scalar-random-walk.v1")
    model = LinearObservation([[1.0]], "example:direct-scalar.v1")
    records = []
    for index, item in enumerate(fixture["observations"], 1):
        observation = Observation(item["time"], [item["value"]], [[item["variance"]]],
                                  fixture["frame_id"], tuple(fixture["units"]),
                                  item["id"], ("example:synthetic-scalar-fixture",))
        prior = predict(prior, dynamics, observation.time)
        estimate = update(prior, observation, model)
        records.append({"time": estimate.time, "mean": estimate.mean.tolist(),
                        "covariance": estimate.covariance.tolist(),
                        "innovation": estimate.innovation.tolist(),
                        "residual": estimate.residual.tolist(), "nis": estimate.nis})
        prior = estimate.as_prior(f"example:posterior-{index}")

    geometry = SO2Geometry()
    heading_prior = StatePrior(0, [np.deg2rad(179)], [[np.deg2rad(2)**2]],
                               "frame:synthetic-heading", ("rad",), "example:heading-prior")
    heading_observation = Observation(0, [np.deg2rad(-179)], [[np.deg2rad(2)**2]],
                                      "frame:synthetic-heading", ("rad",),
                                      "example:heading-observation", ("example:synthetic-heading",))
    heading = update(heading_prior, heading_observation,
                     LinearObservation([[1]], "example:direct-heading.v1", geometry),
                     state_geometry=geometry)
    return {"synthetic": True, "scalar_trajectory": records,
            "heading": {"mean_rad": heading.mean.tolist(),
                        "innovation_rad": heading.innovation.tolist(),
                        "covariance_rad2": heading.covariance.tolist(),
                        "nis": heading.nis}}


if __name__ == "__main__":
    print(json.dumps(replay(), indent=2, allow_nan=False))
