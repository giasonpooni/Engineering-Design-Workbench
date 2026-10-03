# SPDX-License-Identifier: MPL-2.0
"""Explicit mapping into the existing SET result artifact, with synthetic IDs."""

from dataclasses import asdict
import json

from fdir import evaluate_residual
from fdir.exchange import export_result


def example_arguments() -> dict:
    inputs = {
        "residual": [2.0, 3.0],
        "innovation_covariance": [[4.0, 2.0], [2.0, 5.0]],
        "threshold": 4.0,
        "variable_order": ["position_x_m", "position_y_m"],
        "source_ids": ["fixture:gsie-innovation:0001"],
    }
    result = evaluate_residual(**inputs)
    return {
        "operation_id": "operation:fdir:nis-cholesky.v1",
        "execution_ref": "execution:synthetic-fdir-example:0001",
        # Deliberate sentinel, not a claim that any Git source was verified.
        "source_revision": "0" * 40,
        "created_at": "2026-01-01T00:00:00Z",
        "input_refs": list(result.source_ids),
        "input_payload": inputs,
        "numerical_result": asdict(result),
        "components": [{"name": "nis", "unit": "1", "value": result.nis}],
        "covariance": {
            "status": "not_applicable",
            "variables": ["nis"],
            "units": ["1"],
            "frame": {"id": "frame:statistical-score", "semantics": "feature_space"},
            "source_refs": list(result.source_ids),
            "calibration_refs": [],
            "method": "NIS is a diagnostic score; no score uncertainty model is asserted.",
        },
        "applicability": "Synthetic residual diagnostic fixture; no physical fault inference or operational authorization.",
    }


def example_artifact() -> dict:
    return export_result(**example_arguments())


if __name__ == "__main__":
    print(json.dumps(example_artifact(), indent=2, sort_keys=True, allow_nan=False))
