# SPDX-License-Identifier: AGPL-3.0-or-later
"""Actual pinned CSR execution through NET; no native substitute or skipped cases."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from ciw.csr_microtools import OPERATIONS, bind_csr, inspect, run
from ciw.instruments import make_demo_run
from ciw.session import Session, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csr-root", required=True, type=Path)
    parser.add_argument("--csr-revision", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    registry = bind_csr(args.csr_root, args.csr_revision)
    root = args.output_dir
    root.mkdir(parents=True, exist_ok=False)
    # Only a synthetic investigation context. The provider does not use its samples.
    context = Session(make_demo_run(), root / "context")
    context.save_workspace(root / "context.json")
    base = {"arc_length": [0, 1, 2], "curvature": 0, "length_unit": "m",
            "frame": "native-qualification/ideal-plane"}
    extras = [{"initial_error": [.002, -.001]},
              {"initial_bounds": [.002, .001], "tolerances": [.003, .001]},
              {"covariance": [[4e-6, 1e-6], [1e-6, 1e-6]]}]
    expected = [[0, -.001], [.004, .001], [[12e-6, 3e-6], [3e-6, 1e-6]]]
    cases = []
    for i, op in enumerate(OPERATIONS):
        first = run(root / "context.json", root / f"run-{i}", registry,
                    operation_id=op, request={**base, **extras[i]})
        assert first["status"] == "completed", first
        result = first["result"]
        assert result["runtime"]["revision"] == args.csr_revision
        assert result["verification_id"] is None
        np.testing.assert_allclose(result["data"]["values"][-1], expected[i], rtol=1e-13, atol=1e-18)
        if i == 1:
            assert result["data"]["tolerance_check"]["status"] == "FAIL"
        offline = inspect(Path(first["workspace"]))
        assert offline["results"] == [result]
        second = run(Path(first["workspace"]), root / f"replay-{i}", registry,
                     replay_result=result["result_id"])
        assert second["status"] == "completed" and second["same_runtime_exact_data_equal"] is True
        assert second["result"]["execution_id"] != result["execution_id"]
        assert second["result"]["result_id"] != result["result_id"]
        reopened = inspect(Path(second["workspace"]))
        assert len(reopened["results"]) == 2 and result in reopened["results"]
        cases.append({"operation_id": op, "result_id": result["result_id"],
            "reproduction_result_id": second["result"]["result_id"],
            "runtime": result["runtime"], "native_execution": True,
            "same_runtime_exact_data_equal": True})
    report = {"schema": "ciw.csr-microtools-qualification.v1", "cases": cases,
              "operations_checked": 3, "actual_executions": 6,
              "status": "PASS", "verification_status": "not_verified",
              "scope": "implementation qualification, not physical validation"}
    write_json(root / "qualification.json", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
