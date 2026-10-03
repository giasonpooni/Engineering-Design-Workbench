# SPDX-License-Identifier: MPL-2.0
"""Exercise shipped replay, including exact scalar fractions and branch crossing."""

from fractions import Fraction
import json
from pathlib import Path
import subprocess
import sys

import numpy as np


def test_replay_cli_matches_scalar_reference_and_repeats():
    path = Path(__file__).resolve().parents[1] / "examples/replay.py"
    first = subprocess.check_output([sys.executable, str(path)], text=True)
    assert subprocess.check_output([sys.executable, str(path)], text=True) == first
    output = json.loads(first)
    mean, variance = Fraction(0), Fraction(1)
    for row, value in zip(output["scalar_trajectory"], map(Fraction, ("1.2", "0.9", "1.1"))):
        variance += Fraction("0.1")
        # Independent scalar precision-weighted Gaussian combination.
        posterior_variance = 1 / (1 / variance + 1 / Fraction("0.25"))
        mean = posterior_variance * (mean / variance + value / Fraction("0.25"))
        variance = posterior_variance
        np.testing.assert_allclose(row["mean"], [float(mean)], rtol=1e-13)
        np.testing.assert_allclose(row["covariance"], [[float(variance)]], rtol=1e-13)
    np.testing.assert_allclose(output["heading"]["innovation_rad"], [np.deg2rad(2)], atol=1e-14)
    np.testing.assert_allclose(np.abs(output["heading"]["mean_rad"]), [np.pi], atol=1e-14)
