from dataclasses import replace
import json

import numpy as np
import pytest

from edspt import (
    BudgetedCandidate, Candidate, ModelPrior, ParameterCoordinate,
    rank_budgeted_candidates,
)


COORDINATES = (ParameterCoordinate("tank_1", 1.0, "kg"), ParameterCoordinate("tank_2", 1.0, "kg"))
MODEL = "result:identified-process:synthetic"


def candidate(identifier="sample", jacobian=((1, 0),), covariance=((1,),), cost=1.0, **kwargs):
    return BudgetedCandidate(
        Candidate(identifier, COORDINATES, jacobian, covariance), cost, "sample_credit",
        MODEL, "declared_zero", **kwargs,
    )


def rank(candidates=None, *, prior=None, budget=3.0, **kwargs):
    return rank_budgeted_candidates(
        [candidate()] if candidates is None else candidates,
        prior=ModelPrior(MODEL, COORDINATES, covariance=[[4, 0], [0, 9]]) if prior is None else prior,
        available_budget=budget, budget_unit="sample_credit", **kwargs,
    )


def test_analytic_reduction_ranks_only_affordable_alternatives():
    choices = [candidate("tank-1", cost=1), candidate("tank-2", ((0, 1),), cost=3)]
    result = rank(choices, budget=1)
    assert result.prior_a_opt_trace_covariance == pytest.approx(13)
    assert result.prior_d_opt_logdet == pytest.approx(-np.log(36))
    scores = {score.candidate_id: score for score in result.scores}
    assert scores["tank-1"].a_opt_trace_reduction == pytest.approx(3.2)
    assert scores["tank-2"].a_opt_trace_reduction == pytest.approx(8.1)
    assert scores["tank-1"].d_opt_logdet_gain == pytest.approx(np.log(5))
    assert scores["tank-2"].d_opt_logdet_gain == pytest.approx(np.log(10))
    assert scores["tank-2"].eligibility == "over_budget"
    assert result.selected_candidate_id == "tank-1"
    assert result.ranked_candidate_ids == ("tank-1",)
    assert rank(choices, budget=3).selected_candidate_id == "tank-2"
    payload = result.to_dict()
    assert payload["advisory_only"] is True
    assert payload["selection_scope"] == "one_candidate_block"
    assert payload["model_result_id"] == MODEL
    assert payload["scores"][1]["model_result_id"] == MODEL
    json.dumps(payload, allow_nan=False)


def test_correlated_prior_and_noise_match_conditional_gaussian_formula():
    p = np.array([[2.0, 0.5], [0.5, 1.0]])
    h = np.array([[1.0, 0.5], [0.0, 1.0]])
    r = np.array([[1.0, 0.25], [0.25, 2.0]])
    result = rank([candidate(jacobian=h, covariance=r)], prior=ModelPrior(MODEL, COORDINATES, covariance=p))
    expected_posterior = p - p @ h.T @ np.linalg.solve(h @ p @ h.T + r, h @ p)
    score = result.scores[0]
    assert score.a_opt_trace_reduction == pytest.approx(np.trace(p) - np.trace(expected_posterior))
    assert score.d_opt_logdet_gain == pytest.approx(np.linalg.slogdet(p)[1] - np.linalg.slogdet(expected_posterior)[1])


def test_covariance_and_precision_inputs_give_same_scientific_result():
    from_covariance = rank().scores[0]
    from_precision = rank(prior=ModelPrior(MODEL, COORDINATES, precision=[[0.25, 0], [0, 1 / 9]])).scores[0]
    assert from_covariance.d_opt_logdet_gain == pytest.approx(from_precision.d_opt_logdet_gain)
    assert from_covariance.a_opt_trace_reduction == pytest.approx(from_precision.a_opt_trace_reduction)


def test_objective_is_reduction_not_reduction_per_cost():
    choices = [candidate("cheap", cost=0.001), candidate("valuable", ((0, 1),), cost=3)]
    assert rank(choices).selected_candidate_id == "valuable"


def test_no_combination_or_budget_reservation_and_zero_cost_is_allowed():
    choices = [candidate("a", cost=0), candidate("z", ((0, 1),), cost=0)]
    result = rank(choices, budget=0)
    assert result.selected_candidate_id == "z"
    assert result.available_budget == 0
    assert result.ranked_candidate_ids == ("z", "a")
    assert "remaining_budget" not in result.to_dict()


def test_no_affordable_alternative_returns_no_selection_with_scores_retained():
    result = rank(budget=0)
    assert result.selected_candidate_id is None
    assert result.ranked_candidate_ids == ()
    assert result.scores[0].a_opt_trace_reduction == pytest.approx(3.2)


def test_exact_budget_boundary_is_not_rounded_into_affordability():
    result = rank([candidate(cost=np.nextafter(1.0, np.inf))], budget=1)
    assert result.selected_candidate_id is None


def test_integer_rounding_cannot_turn_overspending_into_affordability():
    with pytest.raises(ValueError, match="exactly representable"):
        rank([candidate(cost=2 ** 53 + 1)], budget=2 ** 53)
    with pytest.raises(ValueError, match="exactly representable"):
        rank(budget=2 ** 53 + 1)


def test_ties_permutations_and_zero_gain_have_deterministic_meaning():
    choices = [candidate("z", ((0, 0),)), candidate("a", ((0, 0),))]
    forward = rank(choices)
    assert forward.to_dict() == rank(list(reversed(choices))).to_dict()
    assert forward.selected_candidate_id == "a"
    assert forward.scores[0].expected_uncertainty_reduction == 0


def test_a_and_d_objectives_can_select_different_candidates():
    prior = ModelPrior(MODEL, COORDINATES, covariance=np.eye(2))
    choices = [candidate("balanced", [[2, 0], [0, 2]], np.eye(2)),
               candidate("unbalanced", [[10, 0], [0, 0.5]], np.eye(2))]
    assert rank(choices, prior=prior, criterion="a_opt").selected_candidate_id == "balanced"
    assert rank(choices, prior=prior, criterion="d_opt").selected_candidate_id == "unbalanced"


def test_extreme_information_does_not_hide_posterior_rank_policy():
    result = rank([candidate(jacobian=[[1e15, 0]])])
    assert result.scores[0].eligibility == "unresolved"
    assert result.scores[0].numerical_score.status == "singular"
    assert result.scores[0].expected_uncertainty_reduction is None
    assert result.selected_candidate_id is None


@pytest.mark.parametrize("policy", ["unknown", "known", "assumed_independent", None])
def test_cross_covariance_is_never_inferred_from_absence(policy):
    with pytest.raises(ValueError, match="cross-covariance"):
        rank([replace(candidate(), prior_cross_covariance_policy=policy)])
    assert BudgetedCandidate(candidate().candidate, 1, "sample_credit", MODEL).prior_cross_covariance_policy == "unknown"


@pytest.mark.parametrize("field,value,match", [
    ("model_result_id", "result:another-model", "bindings"),
    ("model_result_id", "", "nonempty"),
    ("cost_unit", "seconds", "units"),
    ("cost_unit", "", "nonempty"),
])
def test_explicit_model_and_budget_unit_bindings(field, value, match):
    with pytest.raises(ValueError, match=match):
        rank([replace(candidate(), **{field: value})])


@pytest.mark.parametrize("value", [-1, np.inf, np.nan, True, "1", 1 + 0j, 10 ** 1000])
def test_nonphysical_budget_or_cost_is_refused(value):
    with pytest.raises(ValueError, match="finite nonnegative"):
        rank(budget=value)
    with pytest.raises(ValueError, match="finite nonnegative"):
        rank([replace(candidate(), cost=value)])


@pytest.mark.parametrize("kwargs", [
    {}, {"covariance": np.eye(2), "precision": np.eye(2)},
    {"covariance": [[1, 0], [0, 0]]}, {"precision": [[1, 0], [0, 0]]},
    {"covariance": [[1, 0.1], [0, 1]]}, {"precision": [[1, 0], [0, -1]]},
    {"covariance": [[1e-20, 0], [0, 1]]}, {"precision": [[1, 0], [0, 1e-20]]},
    {"covariance": [[True, 0], [0, 1]]},
])
def test_prior_requires_exactly_one_valid_full_rank_spd_representation(kwargs):
    with pytest.raises(ValueError):
        rank(prior=ModelPrior(MODEL, COORDINATES, **kwargs))


def test_coordinate_reorder_and_duplicate_candidates_refused():
    mismatched = replace(candidate(), candidate=replace(candidate().candidate, coordinates=tuple(reversed(COORDINATES))))
    with pytest.raises(ValueError, match="coordinates"):
        rank([mismatched])
    with pytest.raises(ValueError, match="unique"):
        rank([candidate(), candidate()])


def test_unaffordable_candidates_are_still_scientifically_validated():
    with pytest.raises(ValueError, match="nonnegative diagonal"):
        rank([candidate(covariance=[[-1]], cost=100)])


def test_result_snapshot_does_not_share_mutable_inputs():
    p = np.diag([4.0, 9.0])
    h = np.array([[1.0, 0.0]])
    r = np.array([[1.0]])
    originals = [p.copy(), h.copy(), r.copy()]
    result = rank([candidate(jacobian=h, covariance=r)], prior=ModelPrior(MODEL, COORDINATES, covariance=p))
    payload = result.to_dict()
    for source, original in zip([p, h, r], originals):
        np.testing.assert_array_equal(source, original)
        source[:] = 999
    assert result.to_dict() == payload


@pytest.mark.parametrize("scale", [1e-300, 1e300])
def test_extreme_but_finite_common_scales(scale):
    prior = ModelPrior(MODEL, COORDINATES, covariance=np.eye(2) * scale)
    result = rank([candidate(jacobian=np.eye(2), covariance=np.eye(2) * scale)], prior=prior)
    assert result.scores[0].a_opt_trace_reduction == pytest.approx(scale)
    assert result.scores[0].d_opt_logdet_gain == pytest.approx(2 * np.log(2))


def test_roundoff_sized_negative_gain_is_zero_but_material_negative_refuses():
    from edspt.budgeted import _gain
    assert _gain(1.0, np.nextafter(1.0, np.inf), 2) == 0
    with pytest.raises(ValueError, match="materially negative"):
        _gain(1.0, 2.0, 2)
