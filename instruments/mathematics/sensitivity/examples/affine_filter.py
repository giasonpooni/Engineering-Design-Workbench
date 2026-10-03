"""Additive-group Kalman step on two-tank masses.

Ordinary affine Kalman filter. Not an IEKF on SE(3).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from sensitivity.affine import AffinePlant, GaussianState, predict, update
from sensitivity.checks import check_filter_chart_equivariance, check_translation_invariance
from sensitivity.coordinates import AffineCoordinates
from sensitivity.reports import format_checks, write_report


def main() -> None:
    state = GaussianState([40.0, 60.0], [[1.0, 0.2], [0.2, 1.5]])
    plant = AffinePlant(
        F=[[0.96, 0.03], [0.04, 0.97]],
        drift=[0.2, -0.2],
        Q=0.01 * np.array([[1.0, -1.0], [-1.0, 1.0]]),
        H=np.eye(2),
        offset=[0.7, -0.4],
        R=[[0.25, 0.08], [0.08, 0.36]],
    )
    measurement = [40.9, 59.6]
    chart = AffineCoordinates(
        T=np.diag([1000.0, 1000.0]),
        S=np.diag([1000.0, 1000.0]),
        name="grams-datum",
        input_offset=[0.0, 100.0],
        output_offset=[0.0, 100.0],
    )
    prior = predict(state, plant)
    result = update(prior, plant, measurement)
    checks = [
        check_translation_invariance(state.mean, prior.mean, [5.0, -3.0]),
        check_filter_chart_equivariance(state, plant, measurement, chart),
    ]
    print("Affine Kalman step on (R^n, +)")
    print(f"prior mean     {np.round(prior.mean, 4).tolist()}")
    print(f"posterior mean {np.round(result.posterior.mean, 4).tolist()}")
    print(f"NIS            {result.statistic:.4f}  dof={result.dof}")
    for check in checks:
        mark = "PASS" if check.passed else "FAIL"
        print(f"[{mark}] {check.name}")
        print(f"       {check.details}")
    target = Path(__file__).resolve().parents[1] / "results" / "affine_filter.md"
    write_report(target, format_checks("Affine filter invariant checks", checks))
    print(f"\nWrote {target}")
    if any(not check.passed for check in checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
