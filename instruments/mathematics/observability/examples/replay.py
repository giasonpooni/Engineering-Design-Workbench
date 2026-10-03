"""Run after `python -m pip install -e .`; no network or input files required."""

import json

from oit import lti_observability, local_identifiability


def main() -> None:
    observation = lti_observability(
        [[1.0, 1.0], [0.0, 1.0]], [[1.0, 0.0]], 2,
        state_names=("position_m", "velocity_m_per_s"), state_scales=[1.0, 1.0],
        rank_rtol=1e-12,
    )
    parameters = local_identifiability(
        [[1.0, 2.0]], [[4.0]], parameter_names=("offset", "gain"),
        rank_rtol=1e-12,
    )
    # A deterministic numerical fixture; no physical validation is implied.
    print(json.dumps({
        "fixture": "position-velocity-and-underdetermined-sensitivity.v1",
        "observability_rank": observation.diagnostics.rank,
        "observability_matrix": observation.observability_matrix.tolist(),
        "parameter_rank": parameters.diagnostics.rank,
        "parameter_count": len(parameters.parameter_names),
        "fisher_information": parameters.fisher_information.tolist(),
        "scope": parameters.scope,
    }, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
