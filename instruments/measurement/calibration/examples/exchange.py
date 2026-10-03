"""A synthetic numerical result mapped into SET's existing exchange contract.

The all-zero source revision is an explicitly synthetic, unattested placeholder.
Supply the actual source commit and execution identity in a real invocation.
"""

from dataclasses import asdict
from datetime import datetime, timezone
import json

from mcur import CalibrationProfile, JointCovariance, Observation, calibrate
from mcur.exchange import export_result


def _record(value) -> dict:
    """Example-owned dataclass mapping; datetime encoding is explicit."""
    def convert(item):
        if isinstance(item, datetime):
            return item.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        raise TypeError(f"unsupported JSON value: {type(item).__name__}")
    return json.loads(json.dumps(asdict(value), default=convert, allow_nan=False))


def build_artifact(execution_ref: str = "execution:synthetic:1") -> dict:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    observation = Observation(
        "observation:synthetic:1", "artifact:synthetic:raw:1", "sensor:synthetic:1",
        "pressure", "kPa", start, indicated_value=3.0, raw_value=300.0,
    )
    profile = CalibrationProfile(
        "profile:synthetic:1", "artifact:synthetic:calibration:1", "sensor:synthetic:1",
        "pressure", "kPa", "kPa", gain=2.0, offset=1.0,
        coefficient_covariance=((0.25, 0.05), (0.05, 1.0)),
        valid_from=start, valid_until=datetime(2026, 1, 1, tzinfo=timezone.utc),
        reference_ids=("reference:synthetic:1",),
    )
    covariance = JointCovariance(((4.0, 0.2, 0.1), (0.2, 0.25, 0.05), (0.1, 0.05, 1.0)))
    result = calibrate(observation, profile, covariance)
    calibration_refs = [profile.profile_id, profile.artifact_id, *profile.reference_ids]
    return export_result(
        operation_id=result.operation_id,
        execution_ref=execution_ref,
        source_revision="0" * 40,
        created_at="2026-01-02T00:00:00Z",
        input_refs=[observation.observation_id, observation.artifact_id],
        input_payload={
            "observation": _record(observation), "profile": _record(profile),
            "joint_covariance": _record(covariance), "serving_status": None,
        },
        numerical_result=_record(result),
        components=[{"name": "pressure", "value": result.corrected_value, "unit": result.output_unit}],
        covariance={
            "status": "propagated", "variables": ["pressure"], "units": [result.output_unit],
            "matrix": [[result.variance]],
            "frame": {"id": "measurement:pressure:scalar", "semantics": "intrinsic_physical"},
            "source_refs": [observation.observation_id], "calibration_refs": calibration_refs,
            "method": "first-order J Sigma J^T for ordered [x,g,b]",
        },
        applicability="synthetic affine calibration candidate; no traceability certification or admission",
        calibration_refs=calibration_refs,
    )


if __name__ == "__main__":
    print(json.dumps(build_artifact(), sort_keys=True, indent=2))
