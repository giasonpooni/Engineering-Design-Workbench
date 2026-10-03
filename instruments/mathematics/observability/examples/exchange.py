"""Explicit SET exchange mapping; all references here are synthetic fixtures."""

import json
import math

from oit import lti_observability
from oit.exchange import export_result


def build_artifact(execution_ref: str = "execution:oit-example-1") -> dict:
    inputs = {
        "transition": [[1.0, 1.0], [0.0, 1.0]],
        "observation": [[1.0, 0.0]],
        "horizon": 2,
        "state_names": ["position_m", "velocity_m_per_s"],
        "state_scales": [1.0, 1.0],
        "rank_rtol": 1e-12,
        "rank_atol": 0.0,
        "weak_rtol": 1e-6,
    }
    result = lti_observability(**inputs)
    diagnostic = result.diagnostics

    def condition(value: float) -> dict:
        return {"value": value if math.isfinite(value) else None,
                "status": "finite" if math.isfinite(value) else "unbounded_or_no_retained_subspace"}

    numerical_result = {
        "state_names": list(result.state_names),
        "state_scales": result.state_scales.tolist(),
        "coordinate_mode": result.coordinate_mode,
        "horizon": result.horizon,
        "observability_matrix": result.observability_matrix.tolist(),
        "analyzed_matrix": result.analyzed_matrix.tolist(),
        "diagnostics": {
            "rank": diagnostic.rank,
            "input_dimension": diagnostic.input_dimension,
            "full_column_rank": diagnostic.full_column_rank,
            "singular_values": diagnostic.singular_values.tolist(),
            "rank_rtol": diagnostic.rank_rtol,
            "rank_atol": diagnostic.rank_atol,
            "rank_threshold": diagnostic.rank_threshold,
            "weak_rtol": diagnostic.weak_rtol,
            "condition_number": condition(diagnostic.condition_number),
            "retained_condition_number": condition(diagnostic.retained_condition_number),
            "numerical_nullspace": diagnostic.numerical_nullspace.tolist(),
            "weak_directions": diagnostic.weak_directions.tolist(),
        },
    }
    return export_result(
        operation_id="operation:lti-observability.v1",
        execution_ref=execution_ref,
        source_revision="0" * 40,  # Synthetic caller claim; never an attested commit.
        created_at="2026-01-01T00:00:00Z",
        input_refs=["evidence:synthetic-position-velocity-model"],
        model_refs=["model:synthetic-discrete-position-velocity"],
        input_payload=inputs,
        numerical_result=numerical_result,
        components=[
            {"name": "observability_rank", "unit": "1", "value": diagnostic.rank},
            {"name": "state_dimension", "unit": "1", "value": diagnostic.input_dimension},
        ],
        covariance={
            "status": "not_applicable",
            "variables": ["observability_rank", "state_dimension"],
            "units": ["1", "1"],
            "frame": {"id": "frame:oit-diagnostics", "semantics": "arbitrary_model_space"},
            "source_refs": ["evidence:synthetic-position-velocity-model"],
            "calibration_refs": [],
            "method": "Deterministic numerical diagnostics, not an estimated state or stochastic uncertainty claim.",
        },
        applicability="Finite-horizon LTI numerical fixture at declared coordinates and tolerance; no physical validation.",
    )


if __name__ == "__main__":
    print(json.dumps(build_artifact(), indent=2, sort_keys=True, allow_nan=False))
