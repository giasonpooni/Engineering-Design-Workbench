"""Exercise the four first-release responsibilities on declared maps."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from sensitivity.checks import (
    check_composition,
    check_coordinate_consistency,
    check_covariance_affine,
    check_derivative,
)
from sensitivity.composition import compose
from sensitivity.coordinates import AffineCoordinates
from sensitivity.perturbation import local_validity, sweep_perturbation_scale
from sensitivity.reference_models import componentwise_exp, reference_catalogue, scaled_rotation
from sensitivity.reports import format_checks, format_sweep, write_report


def main() -> None:
    catalogue = reference_catalogue()
    affine = catalogue["affine2"]
    quadratic = catalogue["quadratic"]
    tanks = catalogue["two-tank"]
    polar = catalogue["polar"]

    checks = [
        check_derivative(affine, [0.4, -1.2]),
        check_derivative(quadratic, [0.7, 0.2]),
        check_derivative(polar, [1.2, 0.4]),
        check_derivative(tanks, [12.0, 8.0, 1.1]),
        check_composition(
            [scaled_rotation(), componentwise_exp(dim=2)],
            [0.25, -0.1],
        ),
        check_coordinate_consistency(
            tanks,
            [10.0, 4.0, 0.9],
            AffineCoordinates.scale([1000.0, 1000.0, 1.0], [1000.0, 1000.0], name="milli"),
            [0.05, -0.02, 0.0],
        ),
        check_covariance_affine(
            affine,
            [0.2, -0.4],
            [[0.04, 0.01], [0.01, 0.09]],
            samples=4000,
        ),
    ]

    print("Jacobian and Sensitivity Propagation Testbed")
    print("Local first-order checks on declared reference maps.\n")
    for check in checks:
        mark = "PASS" if check.passed else "FAIL"
        print(f"[{mark}] {check.name}")
        print(f"       {check.details}")

    sweep = sweep_perturbation_scale(
        catalogue["exp2"],
        [0.0, 0.0],
        [1.0, 0.25],
        scales=[1e-4, 1e-3, 1e-2, 1e-1, 0.5, 1.5],
    )
    validity = local_validity(sweep)
    print("\nExponential map remainder along one direction:")
    for sample in sweep.samples:
        print(
            f"  scale={sample.scale:.3e}  "
            f"|remainder|={sample.absolute_error:.3e}  "
            f"rel={sample.relative_error:.3e}"
        )
    print(
        f"Declared local radius: {validity.valid_scale} "
        f"(fails at {validity.first_invalid_scale})"
    )

    composed = compose([scaled_rotation(), componentwise_exp(dim=2)])
    print(f"\nReusable composed map: {composed.name}")
    print(f"F([0.2, -0.1]) = {composed.evaluate([0.2, -0.1])}")

    report = format_checks("Quickstart checks", checks) + format_sweep(sweep, validity)
    target = Path(__file__).resolve().parents[1] / "results" / "quickstart.md"
    write_report(target, report)
    print(f"\nWrote {target}")

    if any(not check.passed for check in checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
