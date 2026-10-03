"""Local linear structure of a Jacobian: visible rank and invisible directions.

The mean of a derived quantity is an exact re-evaluation f(μ).
Covariance is first-order J Σ Jᵀ. J μ is not a substitute mean.

The null space of J is what this instantaneous map cannot see.
Not Kalman observability of a trajectory, not identifiability,
and not a Lyapunov certificate.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

from .covariance import first_order_covariance, _require_psd
from .jacobian import jacobian_at
from .models import DifferentiableModel, as_vector

Array = NDArray[np.floating]


@dataclass(frozen=True)
class Belief:
    mean: Array
    covariance: Array
    jacobian: Array
    rank: int
    invisible: Array


@dataclass(frozen=True)
class LocalStructure:
    jacobian: Array
    rank: int
    singular_values: Array
    invisible: Array
    visible: Array


def local_structure(jacobian: ArrayLike, *, singular_atol: float = 1e-10) -> LocalStructure:
    jac = np.asarray(jacobian, dtype=float)
    if jac.ndim != 2 or min(jac.shape) == 0:
        raise ValueError("jacobian must be a nonempty 2-D matrix")
    if not np.all(np.isfinite(jac)):
        raise ValueError("jacobian must be finite")
    _, svals, vt = np.linalg.svd(jac, full_matrices=True)
    rank = int(np.sum(svals > singular_atol))
    invisible = vt[rank:].T if rank < vt.shape[0] else np.zeros((vt.shape[1], 0))
    visible = vt[:rank].T if rank else np.zeros((vt.shape[1], 0))
    return LocalStructure(
        jacobian=jac,
        rank=rank,
        singular_values=svals,
        invisible=invisible,
        visible=visible,
    )


def propagate_belief(
    model: DifferentiableModel,
    mean: ArrayLike,
    covariance: ArrayLike,
    *,
    source: str = "auto",
    singular_atol: float = 1e-10,
) -> Belief:
    mu = as_vector(mean, "mean")
    if mu.size != model.input_dim:
        raise ValueError("mean does not match model input dimension")
    sigma = _require_psd(np.asarray(covariance, dtype=float), "input covariance")
    if sigma.shape != (mu.size, mu.size):
        raise ValueError("covariance must match the mean")
    value = model.evaluate(mu)
    jac = jacobian_at(model, mu, source=source).matrix
    structure = local_structure(jac, singular_atol=singular_atol)
    pushed = first_order_covariance(jac, sigma)
    return Belief(
        mean=value,
        covariance=pushed,
        jacobian=jac,
        rank=structure.rank,
        invisible=structure.invisible,
    )


def linearized_mean_gap(model: DifferentiableModel, x: ArrayLike, *, source: str = "auto") -> float:
    point = as_vector(x, "x")
    jac = jacobian_at(model, point, source=source).matrix
    return float(np.linalg.norm(model.evaluate(point) - jac @ point))
