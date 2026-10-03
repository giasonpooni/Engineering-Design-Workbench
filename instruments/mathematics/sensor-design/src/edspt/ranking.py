"""Local Gaussian information ranking, with explicit coordinate contracts."""

from dataclasses import dataclass
import math
from typing import Literal, Sequence

import numpy as np
from numpy.typing import ArrayLike, NDArray

Criterion = Literal["d_opt", "a_opt"]
FloatArray = NDArray[np.float64]
_ROUND_OFF_FACTOR = 64.0


@dataclass(frozen=True)
class ParameterCoordinate:
    """One numerical parameter q: physical parameter theta = scale * q.

    Jacobians and prior precision must already use q, not theta. No automatic
    unit conversion or derivative rescaling is performed.
    """

    name: str
    scale: float
    unit: str


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    coordinates: tuple[ParameterCoordinate, ...]
    jacobian: ArrayLike
    noise_covariance: ArrayLike


@dataclass(frozen=True)
class PriorInformation:
    coordinates: tuple[ParameterCoordinate, ...]
    precision: ArrayLike


@dataclass(frozen=True)
class CandidateScore:
    candidate_id: str
    status: Literal["full_rank", "singular"]
    numerical_rank: int
    dimension: int
    d_opt_logdet: float | None
    a_opt_trace_covariance: float | None
    information: tuple[tuple[float, ...], ...]
    posterior_precision: tuple[tuple[float, ...], ...]
    relative_rank_threshold: float
    smallest_scaled_eigenvalue: float
    largest_scaled_eigenvalue: float

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "status": self.status,
            "numerical_rank": self.numerical_rank,
            "dimension": self.dimension,
            "d_opt_logdet": self.d_opt_logdet,
            "a_opt_trace_covariance": self.a_opt_trace_covariance,
            "information": [list(row) for row in self.information],
            "posterior_precision": [list(row) for row in self.posterior_precision],
            "relative_rank_threshold": self.relative_rank_threshold,
            "smallest_scaled_eigenvalue": self.smallest_scaled_eigenvalue,
            "largest_scaled_eigenvalue": self.largest_scaled_eigenvalue,
        }


@dataclass(frozen=True)
class RankingResult:
    criterion: Criterion
    coordinates: tuple[ParameterCoordinate, ...]
    selected_candidate_id: str | None
    ranked_candidate_ids: tuple[str, ...]
    scores: tuple[CandidateScore, ...]

    def to_dict(self) -> dict:
        return {
            "schema": "edspt.ranking.v1",
            "operation": "finite-candidate-information.v1",
            "advisory_only": True,
            "criterion": self.criterion,
            "coordinates": [
                {"name": c.name, "scale": float(c.scale), "unit": c.unit}
                for c in self.coordinates
            ],
            "selected_candidate_id": self.selected_candidate_id,
            "ranked_candidate_ids": list(self.ranked_candidate_ids),
            "scores": [s.to_dict() for s in self.scores],
            "assumptions": [
                "Local linear model with parameter-independent Gaussian noise covariance.",
                "Each candidate measurement block is independent of prior information.",
                "Within-block noise correlation is represented by the supplied covariance.",
                "All derivatives and precisions use the declared ordered scaled coordinates.",
            ],
        }


def _array(value: ArrayLike, label: str) -> FloatArray:
    raw = np.asarray(value)
    if raw.dtype.kind not in "iuf" or any(
        isinstance(v, (bool, np.bool_, str, bytes)) for v in np.asarray(value, dtype=object).flat
    ):
        raise ValueError(f"{label} must contain real numbers, not booleans or strings")
    try:
        result = np.array(value, dtype=np.float64, copy=True)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be a real numerical array") from exc
    if not np.all(np.isfinite(result)):
        raise ValueError(f"{label} must contain only finite values")
    return result


def _coordinates(values: Sequence[ParameterCoordinate]) -> tuple[ParameterCoordinate, ...]:
    result = tuple(values)
    if not result:
        raise ValueError("At least one parameter coordinate is required")
    names: set[str] = set()
    for c in result:
        if not isinstance(c, ParameterCoordinate):
            raise ValueError("Coordinates must be ParameterCoordinate instances")
        if not isinstance(c.name, str) or not c.name.strip() or c.name in names:
            raise ValueError("Coordinate names must be nonempty and unique")
        names.add(c.name)
        if not isinstance(c.unit, str) or not c.unit.strip():
            raise ValueError("Coordinate units must be explicit; use '1' for dimensionless")
        try:
            valid_scale = not isinstance(c.scale, (bool, np.bool_)) and math.isfinite(c.scale) and c.scale > 0
        except (TypeError, ValueError):
            valid_scale = False
        if not valid_scale:
            raise ValueError("Coordinate scales must be finite and positive")
    return result


def _supplied_psd(
    value: ArrayLike, dimension: int, label: str, *, require_positive: bool,
) -> tuple[FloatArray, FloatArray, FloatArray]:
    """Validate supplied matrices without modifying either stored triangle."""
    matrix = _array(value, label)
    if matrix.shape != (dimension, dimension):
        raise ValueError(f"{label} must have shape {(dimension, dimension)}")
    if not np.array_equal(matrix, matrix.T):
        raise ValueError(f"{label} must be exactly symmetric; no input averaging is performed")
    diagonal = np.diag(matrix)
    if np.any(diagonal < 0):
        raise ValueError(f"{label} must have nonnegative diagonal entries")
    zero = diagonal == 0
    if np.any(matrix[zero, :] != 0) or np.any(matrix[:, zero] != 0):
        raise ValueError(f"{label} zero diagonal requires an exactly zero row and column")
    if require_positive and np.any(zero):
        raise ValueError(f"{label} must be positive definite")
    active = diagonal > 0
    roots = np.sqrt(diagonal[active])
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        try:
            correlation = matrix[np.ix_(active, active)] / np.maximum.outer(roots, roots)
            correlation = correlation / np.minimum.outer(roots, roots)
        except FloatingPointError as exc:
            raise ValueError(f"{label} has nonfinite normalized correlation") from exc
    if roots.size:
        correlation_tolerance = _ROUND_OFF_FACTOR * np.finfo(np.float64).eps * dimension
        if float(np.max(np.abs(correlation))) > 1.0 + correlation_tolerance:
            raise ValueError(f"{label} correlation violates the positive semidefinite bound")
        eigenvalues = np.linalg.eigvalsh(correlation)
        threshold = _ROUND_OFF_FACTOR * np.finfo(np.float64).eps * dimension * float(np.max(np.abs(eigenvalues)))
        if float(eigenvalues[0]) < -threshold:
            raise ValueError(f"{label} must be positive semidefinite")
    if require_positive:
        try:
            np.linalg.cholesky(correlation)
        except np.linalg.LinAlgError as exc:
            raise ValueError(f"{label} must be numerically positive definite") from exc
    return matrix, correlation, roots


def _precision_diagnostics(
    matrix: FloatArray, label: str,
) -> tuple[FloatArray, float, FloatArray, float]:
    """Rank policy for computed information in the declared parameter coordinates."""
    dimension = matrix.shape[0]
    if not np.all(np.isfinite(matrix)):
        raise ValueError(f"{label} must contain only finite values")
    if not np.array_equal(matrix, matrix.T):
        raise ValueError(f"{label} computation produced asymmetric precision")
    scale = float(np.max(np.abs(matrix)))
    scaled = matrix / scale if scale else matrix.copy()
    threshold = _ROUND_OFF_FACTOR * np.finfo(np.float64).eps * dimension
    eigenvalues = np.linalg.eigvalsh(scaled)
    spectral_scale = float(np.max(np.abs(eigenvalues)))
    threshold *= spectral_scale
    if float(eigenvalues[0]) < -threshold:
        raise ValueError(f"{label} must be positive semidefinite")
    return scaled, scale, eigenvalues, threshold


def _rows(matrix: FloatArray) -> tuple[tuple[float, ...], ...]:
    return tuple(tuple(float(v) for v in row) for row in matrix)


def rank_candidates(
    candidates: Sequence[Candidate],
    *,
    prior: PriorInformation | None = None,
    criterion: Criterion = "d_opt",
) -> RankingResult:
    """Rank an explicitly supplied finite candidate set by posterior information.

    D-opt maximizes log det(precision); A-opt minimizes trace(precision^-1).
    Singular candidates have null scores and are never selected. Ties in the
    computed float64 score are broken lexicographically by candidate ID.
    Arrays are copied; inputs are not mutated. This function authorizes no action.
    """
    if criterion not in ("d_opt", "a_opt"):
        raise ValueError("criterion must be 'd_opt' or 'a_opt'")
    items = tuple(candidates)
    if not items:
        raise ValueError("At least one supplied candidate is required")
    if not all(isinstance(c, Candidate) for c in items):
        raise ValueError("Candidates must be Candidate instances")
    ids = [c.candidate_id for c in items]
    if any(not isinstance(v, str) or not v.strip() for v in ids) or len(set(ids)) != len(ids):
        raise ValueError("Candidate IDs must be nonempty and unique")
    coords = _coordinates(items[0].coordinates)
    n = len(coords)
    for candidate in items:
        if _coordinates(candidate.coordinates) != coords:
            raise ValueError("Candidates must use identical ordered coordinate names, scales, and units")
    prior_matrix = np.zeros((n, n), dtype=np.float64)
    if prior is not None:
        if not isinstance(prior, PriorInformation):
            raise ValueError("prior must be PriorInformation")
        if _coordinates(prior.coordinates) != coords:
            raise ValueError("Prior and candidates must use identical ordered coordinates")
        prior_matrix, _, _ = _supplied_psd(
            prior.precision, n, "prior precision", require_positive=False,
        )
    scores: list[CandidateScore] = []
    for candidate in sorted(items, key=lambda c: c.candidate_id):
        j = _array(candidate.jacobian, f"{candidate.candidate_id} Jacobian")
        if j.ndim != 2 or j.shape[0] == 0 or j.shape[1] != n:
            raise ValueError(f"{candidate.candidate_id} Jacobian must have shape (m, {n}) with m > 0")
        _, r_correlation, r_roots = _supplied_psd(
            candidate.noise_covariance, j.shape[0],
            f"{candidate.candidate_id} noise covariance", require_positive=True,
        )
        # Whiten via a solve, avoiding explicit covariance inversion.
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            try:
                whitened = np.linalg.solve(np.linalg.cholesky(r_correlation), j / r_roots[:, None])
                information = whitened.T @ whitened
                precision = prior_matrix + information
            except (FloatingPointError, np.linalg.LinAlgError) as exc:
                raise ValueError(f"{candidate.candidate_id} information is not representable in float64") from exc
        p_scaled, p_scale, eigenvalues, threshold = _precision_diagnostics(
            precision, f"{candidate.candidate_id} posterior precision",
        )
        rank = int(np.count_nonzero(eigenvalues > threshold))
        d_score = a_score = None
        if rank == n:
            sign, scaled_logdet = np.linalg.slogdet(p_scaled)
            if sign <= 0:
                raise ValueError("Posterior precision factorization disagrees with rank diagnostic")
            d_score = float(scaled_logdet + n * math.log(p_scale))
            with np.errstate(over="raise", invalid="raise", divide="raise"):
                try:
                    a_score = float(np.trace(np.linalg.solve(p_scaled, np.eye(n))) / p_scale)
                except (FloatingPointError, np.linalg.LinAlgError) as exc:
                    raise ValueError("Posterior covariance trace is not representable in float64") from exc
            if not math.isfinite(d_score) or not math.isfinite(a_score):
                raise ValueError("Scores must be finite in float64")
        scores.append(CandidateScore(
            candidate_id=candidate.candidate_id,
            status="full_rank" if rank == n else "singular",
            numerical_rank=rank,
            dimension=n,
            d_opt_logdet=d_score,
            a_opt_trace_covariance=a_score,
            information=_rows(information),
            posterior_precision=_rows(precision),
            relative_rank_threshold=float(threshold),
            smallest_scaled_eigenvalue=float(eigenvalues[0]),
            largest_scaled_eigenvalue=float(eigenvalues[-1]),
        ))

    def key(score: CandidateScore) -> tuple[bool, float, str]:
        value = score.d_opt_logdet if criterion == "d_opt" else score.a_opt_trace_covariance
        return (value is None, 0.0 if value is None else (-value if criterion == "d_opt" else value), score.candidate_id)

    ranked = sorted(scores, key=key)
    selected = ranked[0].candidate_id if ranked[0].status == "full_rank" else None
    return RankingResult(
        criterion, coords, selected,
        tuple(s.candidate_id for s in ranked), tuple(scores),
    )
