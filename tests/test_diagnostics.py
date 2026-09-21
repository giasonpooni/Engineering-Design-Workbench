import numpy as np
import pytest

from oit import lti_observability, local_identifiability, rank_diagnostics


def test_position_velocity_observable_in_two_steps():
    result = lti_observability([[1, 1], [0, 1]], [[1, 0]], 2, state_names=("position", "velocity"))
    np.testing.assert_array_equal(result.observability_matrix, [[1, 0], [1, 1]])
    assert result.diagnostics.rank == 2
    assert result.diagnostics.full_column_rank
    assert result.diagnostics.numerical_nullspace.shape == (2, 0)
    assert result.coordinate_mode == "raw model coordinates and units"


def test_unobservable_direction_and_wide_matrix():
    result = lti_observability(np.eye(2), [[1, 0]], 1, state_names=("x", "y"))
    diagnostic = result.diagnostics
    assert diagnostic.rank == 1
    assert not diagnostic.full_column_rank
    assert np.isinf(diagnostic.condition_number)
    np.testing.assert_allclose(result.analyzed_matrix @ diagnostic.numerical_nullspace, 0, atol=1e-15)
    np.testing.assert_allclose(abs(diagnostic.numerical_nullspace), [[0], [1]], atol=1e-15)


def test_zero_matrix_has_complete_nullspace():
    result = rank_diagnostics(np.zeros((2, 3)))
    assert result.rank == 0
    np.testing.assert_allclose(result.numerical_nullspace.T @ result.numerical_nullspace, np.eye(3))
    assert result.weak_directions.shape == (3, 0)


def test_tiny_rank_uses_relative_scale_without_absolute_floor():
    base = np.diag([1.0, 1e-10, 1e-15])
    for scale in (1.0, 1e-250, 1e250):
        result = rank_diagnostics(base * scale, rank_rtol=1e-12)
        assert result.rank == 2
        assert result.weak_directions.shape == (3, 1)
        assert result.retained_condition_number == pytest.approx(1e10)
    # Explicit atol intentionally makes scale matter.
    assert rank_diagnostics(base * 1e-250, rank_atol=1e-240).rank == 0


def test_coordinate_scaling_is_explicit_and_changes_condition():
    result = lti_observability(np.eye(2), np.diag([1.0, 1e-8]), 1,
                               state_names=("x", "y"), state_scales=[1.0, 1e8])
    np.testing.assert_allclose(result.analyzed_matrix, np.eye(2))
    assert result.diagnostics.condition_number == pytest.approx(1.0)
    assert "scaled coordinates" in result.coordinate_mode


def test_underdetermined_local_sensitivity_and_fisher():
    result = local_identifiability([[1, 2]], [[4]], parameter_names=("a", "b"))
    np.testing.assert_allclose(result.fisher_information, [[0.25, 0.5], [0.5, 1.0]])
    assert result.diagnostics.rank == 1
    assert result.diagnostics.numerical_nullspace.shape == (2, 1)
    np.testing.assert_allclose(result.whitened_sensitivity @ result.diagnostics.numerical_nullspace, 0, atol=1e-15)
    assert result.scope.startswith("local sensitivity")


def test_correlated_covariance_information_analytic():
    # R inverse = (1/3) [[2, -1], [-1, 2]], computed analytically.
    result = local_identifiability(np.eye(2), [[2, 1], [1, 2]], parameter_names=("a", "b"))
    np.testing.assert_allclose(result.fisher_information, np.array([[2, -1], [-1, 2]]) / 3)
    assert result.diagnostics.full_column_rank


def test_parameter_scaling_and_tiny_positive_covariance():
    result = local_identifiability([[1e-150, 0], [0, 2e-150]], np.eye(2) * 1e-300,
                                  parameter_names=("a", "b"), parameter_scales=[2, 1])
    np.testing.assert_allclose(result.fisher_information, np.eye(2) * 4)
    assert result.diagnostics.rank == 2


def test_mixed_variance_scales_remain_eligible():
    result = local_identifiability(np.diag([1e-150, 1e150]), np.diag([1e-300, 1e300]),
                                  parameter_names=("a", "b"))
    np.testing.assert_allclose(result.fisher_information, np.eye(2))
    assert result.diagnostics.rank == 2


def test_covariance_asymmetry_on_small_coordinate_is_not_hidden():
    covariance = [[1e-20, 1e-25], [0, 1.0]]
    with pytest.raises(ValueError, match="exactly symmetric"):
        local_identifiability(np.eye(2), covariance, parameter_names=("a", "b"))


@pytest.mark.parametrize("covariance", [
    [[-1e-300]], [[0.0]], [[np.nan]], [[np.inf]], [[1, 2], [2, 1]],
    [[1, 0], [0, -1e-300]], [[1e-300, 1e-310], [0, 1e-300]],
    [[1, 1], [1, 1]],
])
def test_invalid_covariance_including_tiny_negative(covariance):
    size = len(covariance)
    with pytest.raises(ValueError):
        local_identifiability(np.ones((size, 1)), covariance, parameter_names=("a",))


@pytest.mark.parametrize("horizon", [0, -1, 1.0, True, np.bool_(True)])
def test_invalid_horizon(horizon):
    with pytest.raises(ValueError):
        lti_observability([[1]], [[1]], horizon, state_names=("x",))


@pytest.mark.parametrize("matrix", [[], [1, 2], [[np.nan]], [[np.inf]], [[1j]], [[True]], [["1"]], [[1, False]]])
def test_invalid_matrices(matrix):
    with pytest.raises(ValueError):
        rank_diagnostics(matrix)


def test_invalid_shapes_names_scales_and_tolerances():
    with pytest.raises(ValueError):
        lti_observability([[1, 2]], [[1, 0]], 1, state_names=("x",))
    with pytest.raises(ValueError):
        lti_observability(np.eye(2), [[1]], 1, state_names=("x", "y"))
    for names in (("x", "x"), ("x",), ("x", ""), "xy"):
        with pytest.raises(ValueError):
            lti_observability(np.eye(2), [[1, 0]], 1, state_names=names)
    for scales in ([1], [0, 1], [-1, 1], [1, np.inf], [1, 1j], [True, 1], ["1", "1"]):
        with pytest.raises(ValueError):
            lti_observability(np.eye(2), [[1, 0]], 1, state_names=("x", "y"), state_scales=scales)
    for kwargs in ({"rank_rtol": -1}, {"rank_rtol": 2}, {"rank_atol": np.nan}, {"weak_rtol": np.inf}):
        with pytest.raises(ValueError):
            rank_diagnostics([[1]], **kwargs)
    with pytest.raises(ValueError):
        local_identifiability([[1]], np.eye(2), parameter_names=("x",))


def test_overflow_rejected():
    with pytest.raises(ValueError, match="overflowed"):
        lti_observability([[1e308]], [[1e308]], 2, state_names=("x",))
    with pytest.raises(ValueError, match="overflowed"):
        lti_observability([[1]], [[1e308]], 1, state_names=("x",), state_scales=[2])
    with pytest.raises(ValueError, match="overflowed"):
        local_identifiability([[1e200]], [[1]], parameter_names=("a",))
    with pytest.raises(ValueError, match="overflowed"):
        rank_diagnostics(np.ones((2, 2)) * 1e308)


def test_inputs_not_mutated_and_results_readonly():
    a, c, covariance, scales = np.eye(2), np.eye(2), np.eye(2), np.array([2.0, 3.0])
    snapshots = [v.copy() for v in (a, c, covariance, scales)]
    observation = lti_observability(a, c, 2, state_names=("x", "y"), state_scales=scales)
    identified = local_identifiability(c, covariance, parameter_names=("a", "b"), parameter_scales=scales)
    for value, before in zip((a, c, covariance, scales), snapshots):
        np.testing.assert_array_equal(value, before)
    for value in (observation.observability_matrix, identified.fisher_information, identified.diagnostics.singular_values):
        with pytest.raises(ValueError):
            value.flat[0] = 7
