"""Replay synthetic measurement alternatives; emits an advisory JSON result."""

import json

from edspt import Candidate, ParameterCoordinate, rank_candidates


def main() -> None:
    coordinates = (
        ParameterCoordinate("x", 1.0, "m"),
        ParameterCoordinate("y", 1.0, "m"),
    )
    candidates = [
        Candidate("collinear", coordinates, [[1, 0], [2, 0]], [[1, 0], [0, 1]]),
        Candidate("orthogonal", coordinates, [[1, 0], [0, 1]], [[1, 0], [0, 1]]),
        Candidate("precise-orthogonal", coordinates, [[2, 0], [0, 2]], [[1, 0], [0, 1]]),
    ]
    result = rank_candidates(candidates)
    assert result.selected_candidate_id == "precise-orthogonal"
    assert next(s for s in result.scores if s.candidate_id == "collinear").status == "singular"
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
