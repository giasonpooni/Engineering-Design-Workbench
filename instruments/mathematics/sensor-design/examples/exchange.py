"""Run a synthetic ranking and export through the pinned SET contract.

The zero source revision and evidence references are explicitly synthetic,
caller-supplied values; this example does not attest a real execution.
"""

import json

from edspt import Candidate, ParameterCoordinate, rank_candidates
from edspt.exchange import export_result


def example_arguments() -> dict:
    coordinates = (
        ParameterCoordinate("x", 1.0, "m"),
        ParameterCoordinate("y", 1.0, "m"),
    )
    candidates = [
        Candidate("single-axis", coordinates, [[1.0, 0.0]], [[1.0]]),
        Candidate("two-axis", coordinates, [[1.0, 0.0], [0.0, 1.0]], [[1.0, 0.0], [0.0, 1.0]]),
    ]
    ranking = rank_candidates(candidates)
    numerical_result = ranking.to_dict()
    components = [
        {"name": "candidate_count", "unit": "1", "value": len(ranking.scores)},
        {"name": "full_rank_candidate_count", "unit": "1", "value": sum(s.status == "full_rank" for s in ranking.scores)},
    ]
    return {
        "operation_id": "operation:edspt:finite-candidate-information.v1",
        "execution_ref": "execution:edspt:synthetic-replay-001",
        "source_revision": "0" * 40,
        "created_at": "2026-09-20T00:00:00Z",
        "input_refs": ["fixture:edspt:synthetic-alternatives.v1"],
        "input_payload": {
            "synthetic": True,
            "criterion": "d_opt",
            "coordinates": numerical_result["coordinates"],
            "prior": None,
            "candidates": [
                {"candidate_id": c.candidate_id, "jacobian": c.jacobian, "noise_covariance": c.noise_covariance}
                for c in candidates
            ],
        },
        "numerical_result": numerical_result,
        "components": components,
        "covariance": {
            "status": "not_applicable",
            "variables": [c["name"] for c in components],
            "units": [c["unit"] for c in components],
            "frame": {"id": "frame:edspt:ranking-diagnostics", "semantics": "arbitrary_model_space"},
            "source_refs": ["fixture:edspt:synthetic-alternatives.v1"],
            "calibration_refs": [],
            "method": "Deterministic candidate counts; no random-variable covariance is modeled.",
        },
        "applicability": "Synthetic local Gaussian information ranking. Advisory only; no acquisition or physical-placement validation.",
    }


def main() -> None:
    artifact = export_result(**example_arguments())
    print(json.dumps(artifact, allow_nan=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
