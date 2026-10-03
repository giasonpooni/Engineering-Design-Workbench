"""Compose a two-tank holdup map with balance and measurement fragments.

This is a portable fluid example inside the sensitivity testbed. It does
not import the Fluid-State-Reconstruction-Testbed package and does not
claim that plant's reconciliation or invariant filter.
"""

from __future__ import annotations

from pathlib import Path

from sensitivity.checks import (
    check_composition,
    check_coordinate_consistency,
    check_derivative,
    check_metric_consistency,
)
from sensitivity.coordinates import AffineCoordinates
from sensitivity.jacobian import jacobian_at
from sensitivity.metrics import DeclaredMetric
from sensitivity.reference_models import reference_catalogue
from sensitivity.reports import format_checks, write_report


def main() -> None:
    catalogue = reference_catalogue()
    reconstruction = catalogue["fluid-balance"]
    observer = catalogue["fluid-observer"]
    levels = [1.2, 0.8]
    chart = AffineCoordinates.scale([1000.0, 1000.0], [1.0, 1.0], name="level-mm")
    metric = DeclaredMetric.identity(2, 2, name="si")

    checks = [
        check_derivative(catalogue["storage"], levels),
        check_composition([catalogue["storage"], catalogue["balance"]], levels),
        check_composition([catalogue["storage"], catalogue["gauge-totalizer"]], levels),
        check_coordinate_consistency(reconstruction, levels, chart, [0.01, -0.005]),
        check_coordinate_consistency(observer, levels, chart, [0.01, -0.005]),
        check_metric_consistency(observer, levels, chart, metric),
    ]

    print("Fluid composition through sensitivity.compose")
    print(f"reconstruction F({levels}) = {reconstruction.evaluate(levels)}")
    print(f"observer        F({levels}) = {observer.evaluate(levels)}")
    raw = jacobian_at(observer, levels).matrix
    print(f"unscaled ||J||_2 = {float(__import__('numpy').linalg.norm(raw, ord=2)):.6g}")
    print(f"scaled   ||J||_2 = {metric.operator_gain(raw):.6g}")
    print()
    for check in checks:
        mark = "PASS" if check.passed else "FAIL"
        print(f"[{mark}] {check.name}")
        print(f"       {check.details}")

    target = Path(__file__).resolve().parents[1] / "results" / "fluid_composition.md"
    write_report(target, format_checks("Fluid composition checks", checks))
    print(f"\nWrote {target}")
    if any(not check.passed for check in checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
