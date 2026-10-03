"""Exact mean, first-order covariance, and the midspan null space."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from sensitivity.reference_models import simply_supported_midspan
from sensitivity.reports import write_report
from sensitivity.structure import linearized_mean_gap, local_structure, propagate_belief


def main() -> None:
    model = simply_supported_midspan()
    x = np.array([10.0e3, 4.0, 8.0e6])
    belief = propagate_belief(model, x, np.diag([25.0, 1e-4, 1e10]))
    structure = local_structure(belief.jacobian)
    gap = linearized_mean_gap(model, x)
    print("beam midspan structure")
    print(f"exact mean        {belief.mean[0]:.6e} m")
    print(f"||f(x) - J x||    {gap:.6e} m")
    print(f"visible rank      {structure.rank} of {x.size}")
    print(f"invisible cols    {structure.invisible.shape[1]}")
    target = Path(__file__).resolve().parents[1] / "results" / "beam_structure.md"
    write_report(
        target,
        (
            "# Beam local structure\n\n"
            f"- exact mean {belief.mean[0]:.6e} m\n"
            f"- linearized-through-origin gap {gap:.6e} m\n"
            f"- rank {structure.rank}; invisible directions {structure.invisible.shape[1]}\n"
        ),
    )
    print(f"Wrote {target}")
    if structure.rank != 1 or gap <= 0.0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
