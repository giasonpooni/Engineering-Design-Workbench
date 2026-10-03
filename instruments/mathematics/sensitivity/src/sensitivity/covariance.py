"""First-order covariance propagation and Monte Carlo comparison."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

from .jacobian import jacobian_at
from .models import DifferentiableModel, as_vector

Array = NDArray[np.floating]
_PSD_REL_TOL = 1e-12


def _require_psd(matrix: Array, name: str) -> Array:
    cov = np.asarray(matrix, dtype=float)
    if cov.ndim != 2 or cov.shape[0] != cov.shape[1]:
        raise ValueError(f"{name} must be square")
    if not np.all(np.isfinite(cov)):
        raise ValueError(f"{name} must contain finite numbers")
    variances = np.diag(cov)
    if np.any(variances < 0.0):
        raise ValueError(f"{name} variances must be nonnegative")
    zero = variances == 0.0
    if np.any(cov[zero, :] != 0.0) or np.any(cov[:, zero] != 0.0):
        raise ValueError(f"{name} zero-variance rows must have zero cross-covariance")
    positive = ~zero
    if np.any(positive):
        scales = np.sqrt(variances[positive])
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            correlation = cov[np.ix_(positive, positive)] / scales[:, None] / scales[None, :]
        if not np.all(np.isfinite(correlation)):
            raise ValueError(f"{name} has invalid normalized correlations")
        if not np.allclose(correlation, correlation.T, rtol=1e-10, atol=1e-12):
            raise ValueError(f"{name} must be symmetric in correlation coordinates")
        correlation = 0.5 * correlation + 0.5 * correlation.T
        eigenvalues = np.linalg.eigvalsh(correlation)
        if eigenvalues[0] < -_PSD_REL_TOL * float(np.max(np.abs(eigenvalues))):
            raise ValueError(f"{name} must be positive semidefinite")
    return 0.5 * (cov + cov.T)


def first_order_covariance(jacobian: ArrayLike, sigma_x: ArrayLike) -> Array:
    jac = np.asarray(jacobian, dtype=float)
    cov = _require_psd(np.asarray(sigma_x, dtype=float), "Sigma_x")
    if jac.ndim != 2 or jac.shape[1] != cov.shape[0]:
        raise ValueError(f"J is {jac.shape}, Sigma_x is {cov.shape}")
    return jac @ cov @ jac.T


def monte_carlo_covariance(
    model: DifferentiableModel,
    mean: ArrayLike,
    sigma_x: ArrayLike,
    *,
    samples: int = 4000,
    rng: np.random.Generator | None = None,
) -> Array:
    mu = as_vector(mean, "mean")
    cov = _require_psd(np.asarray(sigma_x, dtype=float), "Sigma_x")
    if mu.size != model.input_dim or cov.shape[0] != model.input_dim:
        raise ValueError("mean and Sigma_x must match the model input dimension")
    if samples < 2:
        raise ValueError("samples must be at least 2")
    engine = rng or np.random.default_rng(0)
    evals, evecs = np.linalg.eigh(cov)
    evals = np.maximum(evals, 0.0)
    draws = mu + (engine.standard_normal((samples, mu.size)) * np.sqrt(evals)) @ evecs.T
    outputs = np.vstack([model.evaluate(row) for row in draws])
    centered = outputs - outputs.mean(axis=0)
    return (centered.T @ centered) / (samples - 1)


@dataclass(frozen=True)
class CovarianceExperiment:
    model: str
    first_order: Array
    monte_carlo: Array
    frobenius_gap: float
    relative_gap: float
    samples: int
    notes: str


def run_covariance_experiment(
    model: DifferentiableModel,
    mean: ArrayLike,
    sigma_x: ArrayLike,
    *,
    samples: int = 4000,
    source: str = "auto",
    rng: np.random.Generator | None = None,
) -> CovarianceExperiment:
    mu = as_vector(mean, "mean")
    jac = jacobian_at(model, mu, source=source)  # type: ignore[arg-type]
    linear = first_order_covariance(jac.matrix, sigma_x)
    empirical = monte_carlo_covariance(model, mu, sigma_x, samples=samples, rng=rng)
    gap = linear - empirical
    fro = float(np.linalg.norm(gap, ord="fro"))
    denom = max(float(np.linalg.norm(empirical, ord="fro")), 1e-16)
    return CovarianceExperiment(
        model=model.name,
        first_order=linear,
        monte_carlo=empirical,
        frobenius_gap=fro,
        relative_gap=fro / denom,
        samples=samples,
        notes=(
            "First-order covariance is exact for affine maps. "
            "The Monte Carlo comparison measures the local remainder."
        ),
    )
