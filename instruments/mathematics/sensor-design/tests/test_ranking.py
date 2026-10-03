import json

import numpy as np
import pytest

from edspt import Candidate, ParameterCoordinate, PriorInformation, rank_candidates


COORDS = (ParameterCoordinate("x", 1.0, "m"), ParameterCoordinate("y", 1.0, "m"))


def candidate(identifier, j, r=None, coordinates=COORDS):
    return Candidate(identifier, coordinates, j, np.eye(len(j)) if r is None else r)


def test_known_full_and_singular_information():
    result = rank_candidates([
        candidate("weak", [[1, 0], [0, 1]]),
        candidate("strong", [[2, 0], [0, 3]]),
        candidate("singular", [[1, 1]]),
    ])
    scores = {s.candidate_id: s for s in result.scores}
    assert result.selected_candidate_id == "strong"
    assert result.ranked_candidate_ids == ("strong", "weak", "singular")
    assert scores["strong"].d_opt_logdet == pytest.approx(np.log(36))
    assert scores["strong"].a_opt_trace_covariance == pytest.approx(1 / 4 + 1 / 9)
    np.testing.assert_allclose(scores["strong"].information, [[4, 0], [0, 9]])
    assert scores["singular"].status == "singular"
    assert scores["singular"].numerical_rank == 1
    assert scores["singular"].d_opt_logdet is None
    assert scores["singular"].a_opt_trace_covariance is None
    json.dumps(result.to_dict(), allow_nan=False)


def test_correlated_noise_uses_entire_covariance():
    result = rank_candidates([candidate("correlated", np.eye(2), [[2, 1], [1, 2]])])
    score = result.scores[0]
    np.testing.assert_allclose(score.information, [[2 / 3, -1 / 3], [-1 / 3, 2 / 3]])
    assert score.d_opt_logdet == pytest.approx(-np.log(3))
    assert score.a_opt_trace_covariance == pytest.approx(4)


def test_a_and_d_criteria_have_distinct_meanings():
    candidates = [
        candidate("balanced", np.diag([2.0, 2.0])),
        candidate("unbalanced", np.diag([10.0, 0.5])),
    ]
    assert rank_candidates(candidates, criterion="d_opt").selected_candidate_id == "unbalanced"
    assert rank_candidates(candidates, criterion="a_opt").selected_candidate_id == "balanced"


def test_semidefinite_prior_completes_missing_coordinate():
    result = rank_candidates(
        [candidate("x", [[2, 0]])],
        prior=PriorInformation(COORDS, [[0, 0], [0, 9]]),
    )
    np.testing.assert_allclose(result.scores[0].posterior_precision, [[4, 0], [0, 9]])
    assert result.scores[0].status == "full_rank"


def test_all_singular_has_no_advisory_selection():
    result = rank_candidates([candidate("z", [[0, 0]]), candidate("a", [[1, 0]])])
    assert result.selected_candidate_id is None
    assert result.ranked_candidate_ids == ("a", "z")
    assert result.scores[1].numerical_rank == 0


def test_exact_ties_and_output_are_permutation_invariant():
    candidates = [candidate("z", np.eye(2)), candidate("a", np.eye(2))]
    forward = rank_candidates(candidates).to_dict()
    backward = rank_candidates(list(reversed(candidates))).to_dict()
    assert forward == backward
    assert forward["selected_candidate_id"] == "a"
    assert forward["ranked_candidate_ids"] == ["a", "z"]


def test_inputs_are_never_mutated_and_result_is_detached():
    j = np.eye(2)
    r = np.array([[2.0, 0.5], [0.5, 2.0]])
    p = np.eye(2)
    before = [value.copy() for value in [j, r, p]]
    result = rank_candidates([candidate("sample", j, r)], prior=PriorInformation(COORDS, p))
    for source, original in zip([j, r, p], before):
        np.testing.assert_array_equal(source, original)
    saved = result.to_dict()
    j[:] = 999
    r[:] = 999
    p[:] = 999
    assert result.to_dict() == saved


@pytest.mark.parametrize("scale", [1e-300, 1e-200, 1e-20, 1.0, 1e200, 1e300])
def test_covariance_validation_is_relative_at_tiny_and_large_scales(scale):
    j = np.eye(2) * np.sqrt(scale)
    result = rank_candidates([candidate("sample", j, np.eye(2) * scale)])
    np.testing.assert_allclose(result.scores[0].information, np.eye(2), rtol=1e-14, atol=0)
    assert result.scores[0].status == "full_rank"


def test_tiny_full_rank_precision_has_valid_scores():
    result = rank_candidates([candidate("tiny", np.eye(2) * 1e-150)])
    assert result.scores[0].numerical_rank == 2
    assert result.scores[0].d_opt_logdet == pytest.approx(2 * np.log(1e-300))
    assert result.scores[0].a_opt_trace_covariance == pytest.approx(2e300)


@pytest.mark.parametrize("r", [
    [[1, 1], [0, 1]],
    [[1e-300, 1e-300], [0, 1e-300]],
    [[1, 0], [0, -1]],
    [[1e-300, 0], [0, -1e-300]],
    [[1, 0], [0, 0]],
    [[0, 0], [0, 0]],
    [[1, 0], [0, float("inf")]],
    [[1]],
])
def test_invalid_noise_covariances_rejected(r):
    with pytest.raises(ValueError):
        rank_candidates([candidate("bad", np.eye(2), r)])


@pytest.mark.parametrize("precision", [
    [[1e-300, 0], [0, -1e-300]],
    [[1, 1], [0, 1]],
    [[1, 0], [0, float("nan")]],
])
def test_invalid_priors_rejected(precision):
    with pytest.raises(ValueError):
        rank_candidates([candidate("sample", np.eye(2))], prior=PriorInformation(COORDS, precision))


def test_tiny_negative_prior_variance_is_never_hidden_by_global_scale():
    with pytest.raises(ValueError, match="nonnegative"):
        rank_candidates([candidate("sample", np.eye(2))], prior=PriorInformation(COORDS, [[1, 0], [0, -1e-20]]))


def test_mixed_measurement_units_do_not_make_noise_covariance_singular():
    result = rank_candidates([candidate("mixed", [[1e-10, 0], [0, 1]], [[1e-20, 0], [0, 1]])])
    np.testing.assert_allclose(result.scores[0].information, np.eye(2))
    assert result.scores[0].status == "full_rank"


def test_zero_prior_diagonal_requires_exact_zero_row():
    with pytest.raises(ValueError, match="zero row"):
        rank_candidates([candidate("sample", np.eye(2))], prior=PriorInformation(COORDS, [[1, 1e-20], [1e-20, 0]]))


def test_tiny_stored_asymmetry_is_refused_without_input_repair():
    with pytest.raises(ValueError, match="exactly symmetric"):
        rank_candidates([candidate("sample", np.eye(2), [[1, 1e-20], [0, 1]])])


def test_huge_invalid_correlations_fail_before_spectrum_overflow():
    with pytest.raises(ValueError, match="correlation"):
        rank_candidates([candidate("sample", np.eye(2))], prior=PriorInformation(COORDS, [[1, 1e308], [1e308, 1]]))


@pytest.mark.parametrize("j", [[[True, 0]], [["1", "0"]], np.array([[False, True]])])
def test_boolean_and_string_arrays_are_refused(j):
    with pytest.raises(ValueError, match="booleans or strings"):
        rank_candidates([candidate("bad", j)])


@pytest.mark.parametrize("coords", [
    tuple(reversed(COORDS)),
    (ParameterCoordinate("x", 1000.0, "m"), COORDS[1]),
    (ParameterCoordinate("x", 1.0, "mm"), COORDS[1]),
    (ParameterCoordinate("z", 1.0, "m"), COORDS[1]),
])
def test_coordinate_mismatch_rejected_for_candidates_and_prior(coords):
    with pytest.raises(ValueError, match="ordered"):
        rank_candidates([candidate("a", np.eye(2)), candidate("b", np.eye(2), coordinates=coords)])
    with pytest.raises(ValueError, match="ordered"):
        rank_candidates([candidate("a", np.eye(2))], prior=PriorInformation(coords, np.eye(2)))


@pytest.mark.parametrize("j", [[[float("nan"), 1]], [[1, 2, 3]], [], [1, 2], [[1j, 0]]])
def test_invalid_jacobians_rejected(j):
    with pytest.raises(ValueError):
        rank_candidates([candidate("bad", j)])


def test_identity_and_empty_input_validation():
    with pytest.raises(ValueError):
        rank_candidates([])
    with pytest.raises(ValueError, match="unique"):
        rank_candidates([candidate("a", np.eye(2)), candidate("a", np.eye(2))])
    with pytest.raises(ValueError):
        rank_candidates([candidate(" ", np.eye(2))])
    with pytest.raises(ValueError):
        rank_candidates([candidate("a", np.eye(2))], criterion="unknown")


@pytest.mark.parametrize("scale", [0, -1, float("nan"), float("inf"), True])
def test_invalid_coordinate_scale_rejected(scale):
    coords = (ParameterCoordinate("x", scale, "1"),)
    with pytest.raises(ValueError, match="scales"):
        rank_candidates([candidate("a", [[1]], coordinates=coords)])


def test_unrepresentable_information_fails_without_nonfinite_output():
    with pytest.raises(ValueError, match="representable"):
        rank_candidates([candidate("huge", np.eye(2) * 1e308)])
