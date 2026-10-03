"""Optional differential checks; NumPy is not a runtime dependency."""

from itertools import product

import pytest

from state_estimation_testbed.contracts import ContractError, validate_covariance

np = pytest.importorskip("numpy")


def claim(matrix):
    size = len(matrix)
    return {
        "status": "estimated",
        "variables": [f"x{index}" for index in range(size)],
        "units": ["m"] * size,
        "matrix": matrix.tolist(),
        "frame": {"id": "frame:synthetic", "semantics": "arbitrary_model_space"},
        "method": "synthetic differential test",
        "source_refs": [],
        "calibration_refs": [],
    }


@pytest.mark.parametrize("size,seed", list(product([1, 2, 3, 5, 8, 16, 32], range(5))))
def test_psd_rank_matches_numpy_across_individual_unit_scales(size, seed):
    generator = np.random.default_rng(seed)
    for rank in sorted({1, max(1, size // 2), size}):
        factor = generator.normal(size=(size, rank))
        matrix = factor @ factor.T
        roots = np.sqrt(np.diag(matrix))
        correlation = matrix / roots[:, None] / roots[None, :]
        scale = 10.0 ** generator.uniform(-140, 140, size=size)
        scaled = correlation * scale[:, None] * scale[None, :]
        original = scaled.copy()
        expected_rank = int(np.sum(np.linalg.eigvalsh(correlation) > 1e-12))
        assert validate_covariance(claim(scaled)).effective_rank == expected_rank
        # Non-mutating validation and variable-order covariance permutation.
        assert np.array_equal(original, scaled)
        permutation = generator.permutation(size)
        assert validate_covariance(claim(scaled[np.ix_(permutation, permutation)])).effective_rank == expected_rank


@pytest.mark.parametrize("size,seed", list(product([3, 5, 8, 16], range(10))))
def test_indefinite_correlations_match_numpy_negative_eigenvalues(size, seed):
    generator = np.random.default_rng(seed)
    raw = generator.uniform(-0.99, 0.99, size=(size, size))
    correlation = (raw + raw.T) * 0.5
    np.fill_diagonal(correlation, 1)
    scale = 10.0 ** generator.uniform(-140, 140, size=size)
    scaled = correlation * scale[:, None] * scale[None, :]
    eigenvalues = np.linalg.eigvalsh(correlation)
    if min(eigenvalues) < -1e-12:
        with pytest.raises(ContractError, match="positive-semidefinite"):
            validate_covariance(claim(scaled))
    else:
        assert validate_covariance(claim(scaled)).effective_rank == int(np.sum(eigenvalues > 1e-12))
