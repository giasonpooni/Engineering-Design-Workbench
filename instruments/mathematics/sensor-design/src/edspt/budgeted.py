"""Advisory selection of one affordable observation using a declared model prior.

This is additive to ``rank_candidates``. It does not combine alternatives,
reserve funds, infer cross-covariance, or authorize an observation.
"""

from dataclasses import dataclass
import math
from numbers import Real
from typing import Literal, Sequence

import numpy as np
from numpy.typing import ArrayLike

from .ranking import (
    Candidate, CandidateScore, Criterion, ParameterCoordinate, PriorInformation,
    _coordinates, _precision_diagnostics, _rows, _supplied_psd, rank_candidates,
)


@dataclass(frozen=True)
class ModelPrior:
    """Conditional uncertainty in coordinates bound to a retained model result.

    Supply exactly one of covariance or precision. This uncertainty need not be
    model-parameter uncertainty: coordinates declare what is being measured.
    The binding is a caller assertion; the runtime does not authenticate it.
    """

    model_result_id: str
    coordinates: tuple[ParameterCoordinate, ...]
    covariance: ArrayLike | None = None
    precision: ArrayLike | None = None


@dataclass(frozen=True)
class BudgetedCandidate:
    candidate: Candidate
    cost: float
    cost_unit: str
    model_result_id: str
    prior_cross_covariance_policy: Literal["declared_zero", "unknown"] = "unknown"


@dataclass(frozen=True)
class BudgetedCandidateScore:
    candidate_id: str
    model_result_id: str
    cost: float
    cost_unit: str
    prior_cross_covariance_policy: str
    affordable: bool
    eligibility: Literal["eligible", "over_budget", "unresolved"]
    d_opt_logdet_gain: float | None
    a_opt_trace_reduction: float | None
    expected_uncertainty_reduction: float | None
    numerical_score: CandidateScore

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "model_result_id": self.model_result_id,
            "cost": self.cost,
            "cost_unit": self.cost_unit,
            "prior_cross_covariance_policy": self.prior_cross_covariance_policy,
            "affordable": self.affordable,
            "eligibility": self.eligibility,
            "d_opt_logdet_gain": self.d_opt_logdet_gain,
            "a_opt_trace_reduction": self.a_opt_trace_reduction,
            "expected_uncertainty_reduction": self.expected_uncertainty_reduction,
            "numerical_score": self.numerical_score.to_dict(),
        }


@dataclass(frozen=True)
class BudgetedRankingResult:
    model_result_id: str
    criterion: Criterion
    coordinates: tuple[ParameterCoordinate, ...]
    prior_representation: Literal["covariance", "precision"]
    prior_covariance: tuple[tuple[float, ...], ...]
    prior_precision: tuple[tuple[float, ...], ...]
    prior_d_opt_logdet: float
    prior_a_opt_trace_covariance: float
    available_budget: float
    budget_unit: str
    selected_candidate_id: str | None
    ranked_candidate_ids: tuple[str, ...]
    scores: tuple[BudgetedCandidateScore, ...]

    def to_dict(self) -> dict:
        return {
            "schema": "edspt.budgeted-ranking.v1",
            "operation": "budgeted-next-observation.v1",
            "advisory_only": True,
            "selection_scope": "one_candidate_block",
            "model_result_id": self.model_result_id,
            "criterion": self.criterion,
            "coordinates": [
                {"name": c.name, "scale": float(c.scale), "unit": c.unit}
                for c in self.coordinates
            ],
            "prior_representation": self.prior_representation,
            "prior_covariance": [list(row) for row in self.prior_covariance],
            "prior_precision": [list(row) for row in self.prior_precision],
            "prior_d_opt_logdet": self.prior_d_opt_logdet,
            "prior_a_opt_trace_covariance": self.prior_a_opt_trace_covariance,
            "available_budget": self.available_budget,
            "budget_unit": self.budget_unit,
            "selected_candidate_id": self.selected_candidate_id,
            "ranked_candidate_ids": list(self.ranked_candidate_ids),
            "scores": [score.to_dict() for score in self.scores],
            "assumptions": [
                "Local linear Gaussian observation conditional on the declared model result.",
                "Each candidate's noise has declared zero cross-covariance with the prior error.",
                "Within-block noise correlation is supplied in the full covariance.",
                "Reduction is measured in the shared declared ordered scaled coordinates.",
                "Each alternative is assessed separately; no joint acquisition is proposed.",
                "Model binding and independence declarations require external verification.",
            ],
        }


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be explicit nonempty text")
    return value


def _nonnegative(value: object, label: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{label} must be a finite nonnegative real number")
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f"{label} must be a finite nonnegative real number") from exc
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{label} must be a finite nonnegative real number")
    if result != value:
        raise ValueError(f"{label} must be exactly representable in float64")
    return result


def _inverse_spd(matrix: np.ndarray, label: str) -> np.ndarray:
    scaled, scale, eigenvalues, threshold = _precision_diagnostics(matrix, label)
    if np.count_nonzero(eigenvalues > threshold) != len(matrix):
        raise ValueError(f"{label} must be numerically full rank in declared coordinates")
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        try:
            inverse_factor = np.linalg.solve(np.linalg.cholesky(scaled), np.eye(len(matrix)))
            # A Gram matrix preserves computed symmetry without repairing input.
            inverse = (inverse_factor.T @ inverse_factor) / scale
        except (np.linalg.LinAlgError, FloatingPointError) as exc:
            raise ValueError(f"{label} inverse is not representable in float64") from exc
    if not np.all(np.isfinite(inverse)):
        raise ValueError(f"{label} inverse is not representable in float64")
    return inverse


def _gain(earlier: float, later: float, dimension: int) -> float:
    """Keep roundoff from claiming a negative reduction, without hiding drift."""
    gain = earlier - later
    if not math.isfinite(gain):
        raise ValueError("Expected uncertainty reduction is not representable in float64")
    if gain < 0:
        tolerance = 64.0 * np.finfo(np.float64).eps * dimension * max(abs(earlier), abs(later))
        if -gain > tolerance:
            raise ValueError("Expected uncertainty reduction is materially negative")
        return 0.0
    return float(gain)


def rank_budgeted_candidates(
    candidates: Sequence[BudgetedCandidate], *, prior: ModelPrior,
    available_budget: float, budget_unit: str, criterion: Criterion = "a_opt",
) -> BudgetedRankingResult:
    """Rank affordable individual alternatives by expected uncertainty reduction.

    A-opt is prior covariance trace minus posterior trace. D-opt is posterior
    precision log determinant minus prior log determinant (twice the Gaussian
    entropy reduction). Equal float64 reductions use lexicographic candidate
    IDs; cost is a feasibility constraint, not a gain-per-cost objective.
    """
    if criterion not in ("a_opt", "d_opt"):
        raise ValueError("criterion must be 'd_opt' or 'a_opt'")
    if not isinstance(prior, ModelPrior):
        raise ValueError("prior must be ModelPrior")
    model_id = _text(prior.model_result_id, "model_result_id")
    coordinates = _coordinates(prior.coordinates)
    dimension = len(coordinates)
    budget = _nonnegative(available_budget, "available_budget")
    unit = _text(budget_unit, "budget_unit")
    if (prior.covariance is None) == (prior.precision is None):
        raise ValueError("Supply exactly one prior covariance or precision")
    representation = "covariance" if prior.covariance is not None else "precision"
    matrix, _, _ = _supplied_psd(
        prior.covariance if representation == "covariance" else prior.precision,
        dimension, f"prior {representation}", require_positive=True,
    )
    inverse = _inverse_spd(matrix, f"prior {representation}")
    covariance, precision = (matrix, inverse) if representation == "covariance" else (inverse, matrix)
    prior_information = PriorInformation(coordinates, precision)
    # The zero-sensitivity observation gives the existing operation's baseline
    # and applies its rank/score policy to the same prior precision.
    baseline = rank_candidates(
        [Candidate("prior-baseline", coordinates, np.zeros((1, dimension)), [[1.0]])],
        prior=prior_information, criterion=criterion,
    ).scores[0]
    if baseline.status != "full_rank":
        raise ValueError("Prior precision must be numerically full rank in declared coordinates")
    baseline_d = baseline.d_opt_logdet
    baseline_a = baseline.a_opt_trace_covariance
    assert baseline_d is not None and baseline_a is not None

    items = tuple(candidates)
    if not items or not all(isinstance(item, BudgetedCandidate) for item in items):
        raise ValueError("A nonempty sequence of BudgetedCandidate instances is required")
    cost_by_id: dict[str, float] = {}
    for item in items:
        if not isinstance(item.candidate, Candidate):
            raise ValueError("Budgeted candidates must wrap Candidate instances")
        if _text(item.model_result_id, "candidate model_result_id") != model_id:
            raise ValueError("Candidate and prior model_result_id bindings must match")
        if item.prior_cross_covariance_policy != "declared_zero":
            raise ValueError("Prior/candidate cross-covariance requires explicit declared_zero; unknown refuses")
        if _text(item.cost_unit, "candidate cost_unit") != unit:
            raise ValueError("All candidate cost units must exactly match budget_unit")
        identifier = _text(item.candidate.candidate_id, "candidate_id")
        if identifier in cost_by_id:
            raise ValueError("Candidate IDs must be nonempty and unique")
        cost_by_id[identifier] = _nonnegative(item.cost, "candidate cost")
    numerical = rank_candidates(
        [item.candidate for item in items], prior=prior_information, criterion=criterion,
    )
    scores: list[BudgetedCandidateScore] = []
    for score in numerical.scores:
        cost = cost_by_id[score.candidate_id]
        affordable = cost <= budget
        d_gain = a_gain = reduction = None
        if score.status == "full_rank":
            assert score.d_opt_logdet is not None and score.a_opt_trace_covariance is not None
            d_gain = _gain(score.d_opt_logdet, baseline_d, dimension)
            a_gain = _gain(baseline_a, score.a_opt_trace_covariance, dimension)
            reduction = a_gain if criterion == "a_opt" else d_gain
        eligibility = "over_budget" if not affordable else ("eligible" if reduction is not None else "unresolved")
        scores.append(BudgetedCandidateScore(
            score.candidate_id, model_id, cost, unit, "declared_zero", affordable,
            eligibility, d_gain, a_gain, reduction, score,
        ))
    eligible = sorted(
        (score for score in scores if score.eligibility == "eligible"),
        key=lambda score: (-score.expected_uncertainty_reduction, score.candidate_id),
    )
    return BudgetedRankingResult(
        model_id, criterion, coordinates, representation, _rows(covariance), _rows(precision),
        baseline_d, baseline_a, budget, unit,
        eligible[0].candidate_id if eligible else None,
        tuple(score.candidate_id for score in eligible), tuple(scores),
    )
