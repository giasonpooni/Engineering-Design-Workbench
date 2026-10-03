"""Map an actual synthetic reconciliation to SET's existing result contract."""

from dataclasses import asdict
import json

import numpy as np

from tbrt import AffineClockModel, ClockFrame, TimestampObservation, reconcile_time
from tbrt.exchange import export_result


def build_export_arguments():
    device = ClockFrame("synthetic-sensor/clock-1", "device-monotonic")
    reference = ClockFrame("synthetic-reference/clock-1", "reference-monotonic")
    raw = TimestampObservation(1003.0, device, "synthetic-observation-0001")
    model = AffineClockModel(
        "synthetic-clock-map-0001", device, reference,
        1000.0, 200.0, 1.00002, 0.0003, (1000.0, 1010.0),
    )
    joint_covariance = np.diag([1e-6, 1e-10, 4e-6])
    result = reconcile_time(raw, model, joint_covariance, expected_reference=reference)
    return dict(
        operation_id="tbrt.affine-clock.first-order.v1",
        execution_ref="synthetic-execution-0001",
        # Explicit synthetic placeholder, not a claim about a checked-out commit.
        source_revision="0" * 40,
        # Caller-supplied record creation time, NOT the reconciled event time.
        created_at="2026-01-01T00:00:00Z",
        input_refs=[raw.evidence_id],
        model_refs=[model.model_id],
        input_payload={
            "observation": asdict(raw),
            "model": asdict(model),
            "joint_covariance": joint_covariance.tolist(),
            "expected_reference": asdict(reference),
        },
        numerical_result=asdict(result),
        components=[{"name": "event_time_delta", "value": result.event_time_delta, "unit": "s"}],
        covariance={
            "status": "propagated",
            "variables": ["event_time_delta"],
            "units": ["s"],
            "matrix": [[result.variance]],
            "frame": {
                "id": "synthetic-reference/clock-1:reference-monotonic:origin=200s",
                "semantics": "intrinsic_physical",
            },
            "source_refs": [raw.evidence_id, model.model_id],
            "calibration_refs": [],
            "method": "tbrt.affine-clock.first-order.v1",
        },
        applicability="Nominal device timestamp within [1000, 1010] s; supplied affine clock model.",
    )


def main():
    print(json.dumps(export_result(**build_export_arguments()), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
