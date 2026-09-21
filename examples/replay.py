"""Deterministic synthetic example; execute after `pip install -e .`."""

from dataclasses import asdict
import json

import numpy as np

from tbrt import AffineClockModel, ClockFrame, TimePoint, TimestampObservation, reconcile_time


def main():
    device = ClockFrame("synthetic-sensor/clock-1", "device-monotonic")
    reference = ClockFrame("synthetic-reference/clock-1", "reference-monotonic")
    observation = TimestampObservation(
        device_time=1003.0,
        frame=device,
        evidence_id="synthetic-observation-0001",
        received_at=TimePoint(203.5, reference),
        known_at=TimePoint(204.0, reference),
    )
    model = AffineClockModel(
        model_id="synthetic-affine-map-0001",
        source_frame=device,
        reference_frame=reference,
        device_origin=1000.0,
        reference_origin=200.0,
        skew=1.00002,
        offset=0.0003,
        valid_device_interval=(1000.0, 1010.0),
    )
    covariance = np.diag([1e-6, 1e-10, 4e-6])
    result = reconcile_time(observation, model, covariance, expected_reference=reference)
    output = asdict(result)
    output["event_time"] = result.event_time
    output["standard_uncertainty"] = result.standard_uncertainty
    print(json.dumps(output, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
