"""Deterministic synthetic replay; no real calibration or certification claim."""

from datetime import datetime, timezone
import json

from mcur import CalibrationProfile, JointCovariance, Observation, calibrate


def main() -> None:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 1, tzinfo=timezone.utc)
    observation = Observation(
        "observation:synthetic:1", "artifact:synthetic:raw:1", "sensor:synthetic:1",
        "pressure", "kPa", start, indicated_value=3.0, raw_value=300.0,
    )
    profile = CalibrationProfile(
        "profile:synthetic:1", "artifact:synthetic:calibration:1", "sensor:synthetic:1",
        "pressure", "kPa", "kPa", gain=2.0, offset=1.0,
        coefficient_covariance=((0.25, 0.05), (0.05, 1.0)),
        valid_from=start, valid_until=end, reference_ids=("reference:synthetic:1",),
    )
    covariance = JointCovariance(((4.0, 0.2, 0.1), (0.2, 0.25, 0.05), (0.1, 0.05, 1.0)))
    result = calibrate(observation, profile, covariance)
    assert result.corrected_value == 7.0
    assert abs(result.variance - 22.35) < 1e-12
    print(json.dumps({
        "operation_id": result.operation_id,
        "observation_id": result.observation_id,
        "profile_id": result.profile_id,
        "raw_value": result.raw_value,
        "indicated_value": result.indicated_value,
        "corrected_value": result.corrected_value,
        "unit": result.output_unit,
        "standard_uncertainty": result.standard_uncertainty,
        "variance": result.variance,
        "uncertainty_budget": {term.name: term.variance_contribution for term in result.uncertainty_budget},
        "diagnostics": result.diagnostics,
    }, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
