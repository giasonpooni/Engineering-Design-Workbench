"""Numerical diagnostics; these functions do not estimate or admit state."""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral, Real
from typing import Literal, Sequence

import numpy as np
from numpy.typing import ArrayLike, NDArray

FloatArray = NDArray[np.float64]
ObservabilityStatus = Literal["observable", "unobservable", "ill_conditioned", "unresolved"]


def _readonly(value: ArrayLike) -> FloatArray:
    result = np.array(value, dtype=np.float64, copy=True)
    result.setflags(write=False)
    return result


def _matrix(value: ArrayLike, name: str) -> FloatArray:
    try:
        raw = np.asarray(value, dtype=object)
        if any(isinstance(v, (bool, np.bool_)) or not isinstance(v, Real) for v in raw.flat):
            raise ValueError(f"{name} entries must be real numbers, not booleans or text")
        result = np.array(value, dtype=np.float64, copy=True)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite real matrix") from exc
    if result.ndim != 2 or 0 in result.shape or not np.isfinite(result).all():
        raise ValueError(f"{name} must be a nonempty finite 2-D matrix")
    return result


def _tolerance(value: float, name: str, *, relative: bool = False) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite nonnegative real number")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite nonnegative real number") from exc
    if not np.isfinite(number) or number < 0 or (relative and number > 1):
        raise ValueError(f"{name} must be finite and in {'[0, 1]' if relative else '[0, infinity)'}")
    return number


def _condition_limit(value: float | None) -> float | None:
    if value is None:
        return None
    limit = _tolerance(value, "condition_limit")
    if limit < 1:
        raise ValueError("condition_limit must be at least 1 or None")
    return limit


def _coordinates(
    names: Sequence[str], scales: ArrayLike | None, size: int, kind: str,
) -> tuple[tuple[str, ...], FloatArray | None]:
    if isinstance(names, str):
        raise ValueError(f"{kind}_names must be a sequence, not one string")
    ordered = tuple(names)
    if (len(ordered) != size or any(not isinstance(n, str) or not n.strip() for n in ordered)
            or len(set(ordered)) != size):
        raise ValueError(f"{kind}_names must contain {size} distinct nonempty strings")
    if scales is None:
        return ordered, None
    try:
        raw = np.asarray(scales, dtype=object)
        if any(isinstance(v, (bool, np.bool_)) or not isinstance(v, Real) for v in raw.flat):
            raise ValueError(f"{kind}_scales entries must be real numbers, not booleans or text")
        values = np.array(scales, dtype=np.float64, copy=True)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{kind}_scales must be a positive finite real vector") from exc
    if values.shape != (size,) or not np.isfinite(values).all() or np.any(values <= 0):
        raise ValueError(f"{kind}_scales must be a positive finite vector of length {size}")
    return ordered, _readonly(values)


def _finite_result(value: FloatArray, name: str) -> FloatArray:
    if not np.isfinite(value).all():
        raise ValueError(f"{name} overflowed or is nonfinite; rescale the declared model")
    return value


@dataclass(frozen=True)
class RankDiagnostics:
    """Right directions are columns in the matrix's input coordinates."""

    rank: int
    input_dimension: int
    full_column_rank: bool
    singular_values: FloatArray
    rank_rtol: float
    rank_atol: float
    rank_threshold: float
    weak_rtol: float
    condition_number: float
    retained_condition_number: float
    numerical_nullspace: FloatArray
    weak_directions: FloatArray


@dataclass(frozen=True)
class ObservabilityResult:
    state_names: tuple[str, ...]
    state_scales: FloatArray | None
    coordinate_mode: str
    horizon: int
    observability_matrix: FloatArray
    analyzed_matrix: FloatArray
    diagnostics: RankDiagnostics
    status: ObservabilityStatus
    condition_limit: float | None
    classification_reason: str

    @property
    def rank(self) -> int:
        return self.diagnostics.rank

    @property
    def condition_number(self) -> float:
        return self.diagnostics.condition_number


@dataclass(frozen=True)
class IdentifiabilityResult:
    parameter_names: tuple[str, ...]
    parameter_scales: FloatArray | None
    coordinate_mode: str
    sensitivity_matrix: FloatArray
    whitened_sensitivity: FloatArray
    fisher_information: FloatArray
    diagnostics: RankDiagnostics
    scope: str = "local sensitivity at the supplied evaluation point"


def rank_diagnostics(
    matrix: ArrayLike, *, rank_rtol: float | None = None, rank_atol: float = 0.0,
    weak_rtol: float = 1e-6,
) -> RankDiagnostics:
    """Analyze real matrix rank using a scale-normalized full right SVD.

    A singular direction is retained exactly when s > max(atol, rtol*s_max).
    Weak directions are retained directions with s <= weak_rtol*s_max.
    Relative tolerances are in [0, 1]; atol is in matrix singular-value units.
    """
    values = _matrix(matrix, "matrix")
    rows, columns = values.shape
    rtol = (max(rows, columns) * np.finfo(np.float64).eps if rank_rtol is None
            else _tolerance(rank_rtol, "rank_rtol", relative=True))
    atol = _tolerance(rank_atol, "rank_atol")
    weak = _tolerance(weak_rtol, "weak_rtol", relative=True)
    scale = float(np.max(np.abs(values)))
    normalized = values / scale if scale else values
    # Tall matrices already have a complete right basis in reduced SVD; avoid
    # allocating a horizon-by-horizon left basis. Wide matrices need full Vh.
    _, normalized_s, vh = np.linalg.svd(normalized, full_matrices=rows < columns)
    # Compare in normalized units, retaining relative rank even at tiny scales.
    # Infinite atol/scale intentionally means every singular value is below atol.
    with np.errstate(over="ignore", under="ignore", divide="ignore"):
        normalized_atol = float(np.divide(atol, scale)) if scale else (np.inf if atol else 0.0)
        threshold = max(normalized_atol, rtol * float(normalized_s[0]))
        singular_values = normalized_s * scale
    _finite_result(singular_values, "singular values")
    retained = normalized_s > threshold
    rank = int(np.count_nonzero(retained))
    weak_indices = np.flatnonzero(retained & (normalized_s <= weak * normalized_s[0]))
    with np.errstate(over="ignore", divide="ignore"):
        retained_condition = (float(normalized_s[0] / normalized_s[rank - 1]) if rank else np.inf)
    full_rank = rank == columns
    # Reporting a subnormal threshold may round to zero; the comparison above
    # remains in normalized units and is authoritative.
    reported_threshold = max(atol, rtol * float(singular_values[0]))
    return RankDiagnostics(
        rank=rank, input_dimension=columns, full_column_rank=full_rank,
        singular_values=_readonly(singular_values), rank_rtol=rtol, rank_atol=atol,
        rank_threshold=reported_threshold, weak_rtol=weak,
        condition_number=retained_condition if full_rank else np.inf,
        retained_condition_number=retained_condition,
        numerical_nullspace=_readonly(vh[rank:, :].T),
        weak_directions=_readonly(vh[weak_indices, :].T),
    )


def lti_observability(
    transition: ArrayLike, observation: ArrayLike, horizon: int, *,
    state_names: Sequence[str], state_scales: ArrayLike | None = None,
    rank_rtol: float | None = None, rank_atol: float = 0.0, weak_rtol: float = 1e-6,
    condition_limit: float | None = 1e8,
) -> ObservabilityResult:
    """Evaluate O_H = [C; CA; ...; CA**(H-1)] for a discrete-time LTI model.

    Names specify column order. With scales D, analyze O_H D where x = D z;
    without scales, diagnostics explicitly use raw model coordinates and units.
    """
    a = _matrix(transition, "transition")
    c = _matrix(observation, "observation")
    if a.shape[0] != a.shape[1] or c.shape[1] != a.shape[0]:
        raise ValueError("transition must be square and observation columns must match its dimension")
    if isinstance(horizon, (bool, np.bool_)) or not isinstance(horizon, Integral) or horizon < 1:
        raise ValueError("horizon must be a positive integer")
    names, scales = _coordinates(state_names, state_scales, a.shape[0], "state")
    limit = _condition_limit(condition_limit)
    blocks = []
    current = c
    with np.errstate(over="ignore", invalid="ignore", under="ignore"):
        for step in range(int(horizon)):
            blocks.append(current)
            if step + 1 < horizon:
                current = _finite_result(current @ a, "observability matrix")
        raw = np.vstack(blocks)
        analyzed = _finite_result(raw * scales if scales is not None else raw.copy(), "scaled observability matrix")
    diagnostics = rank_diagnostics(analyzed, rank_rtol=rank_rtol, rank_atol=rank_atol, weak_rtol=weak_rtol)
    if not diagnostics.full_column_rank:
        status: ObservabilityStatus = "unobservable"
        reason = "finite-horizon observability matrix is rank deficient under the declared tolerance"
    elif limit is None:
        status = "unresolved"
        reason = "full rank was found, but no conditioning acceptance limit was declared"
    elif diagnostics.condition_number > limit:
        status = "ill_conditioned"
        reason = "full rank was found, but the declared conditioning limit was exceeded"
    else:
        status = "observable"
        reason = "full rank and conditioning satisfy the declared finite-horizon policy"
    return ObservabilityResult(
        state_names=names,
        state_scales=scales,
        coordinate_mode=("scaled coordinates: x = diag(state_scales) z"
                         if scales is not None else "raw model coordinates and units"),
        horizon=int(horizon),
        observability_matrix=_readonly(raw),
        analyzed_matrix=_readonly(analyzed),
        diagnostics=diagnostics,
        status=status,
        condition_limit=limit,
        classification_reason=reason,
    )


def local_identifiability(
    sensitivity: ArrayLike, measurement_covariance: ArrayLike, *,
    parameter_names: Sequence[str], parameter_scales: ArrayLike | None = None,
    rank_rtol: float | None = None, rank_atol: float = 0.0, weak_rtol: float = 1e-6,
) -> IdentifiabilityResult:
    """Analyze local sensitivities J and Fisher matrix J.T solve(R, J).

    R must be SPD. This is the mean-sensitivity information for a model whose
    observation covariance is fixed with respect to the parameters. With scales
    D, the analyzed sensitivity is J D and information is in z coordinates.
    Rank is computed from the whitened Jacobian, avoiding squared conditioning.
    """
    j = _matrix(sensitivity, "sensitivity")
    covariance = _matrix(measurement_covariance, "measurement_covariance")
    if covariance.shape != (j.shape[0], j.shape[0]):
        raise ValueError("measurement_covariance must be square with one row per sensitivity observation")
    names, scales = _coordinates(parameter_names, parameter_scales, j.shape[1], "parameter")
    if not np.array_equal(covariance, covariance.T):
        raise ValueError("measurement_covariance must be exactly symmetric as supplied")
    variances = np.diag(covariance)
    if np.any(variances <= 0):
        raise ValueError("measurement_covariance must have strictly positive variances")
    roots = np.sqrt(variances)
    # Equilibrate by individual standard deviations so mixed units do not
    # conceal tiny negative variances or discard valid small coordinates.
    larger = np.maximum(roots[:, None], roots[None, :])
    smaller = np.minimum(roots[:, None], roots[None, :])
    with np.errstate(over="ignore", invalid="ignore", under="ignore"):
        correlation = _finite_result((covariance / larger) / smaller, "normalized covariance")
    try:
        factor = np.linalg.cholesky(correlation)
    except np.linalg.LinAlgError as exc:
        raise ValueError("measurement_covariance must be numerically positive definite") from exc
    with np.errstate(over="ignore", invalid="ignore", under="ignore"):
        analyzed = _finite_result(j * scales if scales is not None else j.copy(), "scaled sensitivity")
        standardized = _finite_result(analyzed / roots[:, None], "standardized sensitivity")
        whitened = _finite_result(np.linalg.solve(factor, standardized), "whitened sensitivity")
        fisher = _finite_result(whitened.T @ whitened, "Fisher information")
    diagnostics = rank_diagnostics(whitened, rank_rtol=rank_rtol, rank_atol=rank_atol, weak_rtol=weak_rtol)
    return IdentifiabilityResult(
        names, scales, "scaled coordinates: theta = diag(parameter_scales) z" if scales is not None else "raw parameter coordinates and units",
        _readonly(j), _readonly(whitened), _readonly(fisher), diagnostics,
    )
