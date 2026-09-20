"""Explicitly synthetic covariance-basis fixtures for rci.calibrate.v2.

This extends fixture declarations; it does not infer a real covariance basis
from an old profile. Each provenance reference names a synthetic assumption.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json

from ciw_calibration import reservoir_requests


def synthetic_v2_request(v1_request: dict, *, common_reference: bool = False) -> dict:
    request = deepcopy(v1_request)
    request["operation_id"] = "rci.calibrate.v2"
    binding = request["inputs"]["calibration"]
    binding["schema"] = "rci-calibration-binding.v2"
    assembly_id = binding["assembly_id"]
    declaration = f"synthetic-fixture:{assembly_id}:covariance-basis-v2"
    reference_source = "synthetic-reference:common-mass-standard" if common_reference else f"synthetic-reference:{assembly_id}"

    def provenance(reason, dependencies, shared=()):
        return {
            "reason": reason, "evidence_ids": [declaration],
            "dependency_ids": list(dependencies), "shared_source_ids": list(shared),
        }

    binding["covariance_basis"] = {
        "schema": "rci-covariance-basis.v1",
        "parameter_components": [
            {
                "component_id": "fit", "kind": "fitting", "status": "included",
                "covariance": [[0.0, 0.0], [0.0, 0.02]], "represented_by": None,
                **provenance("Synthetic fit contributes zero-parameter variance 0.02 count^2; independent of declared reference contribution", [f"synthetic-fit:{assembly_id}"]),
            },
            {
                "component_id": "reference", "kind": "reference_standard", "status": "included",
                "covariance": [[1e-10, 1e-7], [1e-7, 0.02]], "represented_by": None,
                **provenance("Synthetic reference contribution is already expressed in native [scale,zero_raw] parameter coordinates and is added exactly once", [reference_source], [reference_source]),
            },
            {
                "component_id": "other-systematics", "kind": "shared_systematic", "status": "excluded",
                "covariance": None, "represented_by": None,
                **provenance("Synthetic fixture models no additional shared environmental/systematic effects; this exclusion is a scope limitation, not a physical completeness claim", []),
            },
        ],
        "raw": provenance("Independent synthetic acquisition noise; matrix order matches records", [f"synthetic-acquisition:{assembly_id}"]),
        "residual": {
            "scope": "additional_independent_output_residual",
            **provenance("Synthetic residual excludes all parameter/reference/raw contributions and is independent across records and of the other components", [f"synthetic-residual:{assembly_id}"]),
        },
        "independence": {
            "parameter_components": True, "raw_parameter": True, "residual_other": True,
            "reason": "The synthetic generative construction specifies independent fit, reference, raw-noise, and residual latent variables; identifiers alone do not establish this",
            "evidence_ids": [declaration],
        },
    }
    return request


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--common-reference", action="store_true")
    args = parser.parse_args()
    print(json.dumps([
        synthetic_v2_request(request, common_reference=args.common_reference)
        for request in reservoir_requests()
    ], indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
