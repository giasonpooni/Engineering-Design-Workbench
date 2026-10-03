"""Portable beam midspan map through compose, charts, and a declared metric.

Not GAT and not an AISC check. The formula is Euler-Bernoulli midspan
deflection of a simply supported beam.
"""

from __future__ import annotations

from pathlib import Path

from sensitivity.checks import (
    check_coordinate_consistency,
    check_derivative,
    check_metric_consistency,
)
from sensitivity.coordinates import AffineCoordinates
from sensitivity.jacobian import jacobian_at
from sensitivity.metrics import DeclaredMetric
from sensitivity.reference_models import simply_supported_midspan
from sensitivity.reports import format_checks, write_report


def main() -> None:
    model = simply_supported_midspan()
    point = [10.0, 4.0, 2.0e4]
    chart = AffineCoordinates.scale([1.0, 1000.0, 1.0e9], [1000.0], name="mm-N")
    metric = DeclaredMetric.identity(3, 1, name="si")
    estimate = jacobian_at(model, point)
    checks = [
        check_derivative(model, point),
        check_coordinate_consistency(model, point, chart, [0.05, 0.001, 0.0]),
        check_metric_consistency(model, point, chart, metric),
    ]
    print("Construction composition through sensitivity")
    print(f"delta({point}) = {model.evaluate(point)}")
    structure = estimate.structure()
    print(f"visible rank = {structure.rank} of {estimate.matrix.shape[1]}")
    print(f"invisible directions = {structure.invisible.shape[1]}")
    print(f"scaled gain = {metric.operator_gain(estimate.matrix):.6g}")
    for check in checks:
        mark = "PASS" if check.passed else "FAIL"
        print(f"[{mark}] {check.name}")
        print(f"       {check.details}")
    target = Path(__file__).resolve().parents[1] / "results" / "construction_composition.md"
    write_report(target, format_checks("Construction composition checks", checks))
    print(f"\nWrote {target}")
    if any(not check.passed for check in checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
