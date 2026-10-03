import numpy as np
import pytest

from sidt import NonIdentifiableError, evaluate_one_step, fit_lti


A = np.array([[0.78, 0.12], [-0.15, 0.65]])
B = np.array([[0.4], [0.2]])
C = np.array([[1.0, -0.25]])
D = np.array([[0.3]])
METADATA = dict(
    sample_interval=0.1, state_names=("displacement", "velocity"),
    state_units=("m", "m/s"), input_names=("force",), input_units=("N",),
)


def trajectory(seed=71, count=90, noise=0.0):
    rng = np.random.default_rng(seed)
    inputs = rng.normal(size=(count, 1))
    states = np.empty((count + 1, 2))
    states[0] = [0.2, -0.4]
    for k in range(count):
        states[k + 1] = A @ states[k] + B @ inputs[k] + rng.normal(scale=noise, size=2)
    outputs = states[:-1] @ C.T + inputs @ D.T
    return states, inputs, outputs


def test_exact_identification_and_independent_holdout():
    states, inputs, outputs = trajectory()
    candidate = fit_lti(states, inputs, outputs=outputs, output_names=("sensor",),
                        output_units=("m",), **METADATA)
    for actual, expected in [(candidate.A, A), (candidate.B, B), (candidate.C, C), (candidate.D, D)]:
        np.testing.assert_allclose(actual, expected, atol=2e-14)
    assert candidate.diagnostics.rank == 3
    assert candidate.diagnostics.degrees_of_freedom == 87
    assert candidate.diagnostics.singular_values.shape == (3,)
    x, u, y = trajectory(seed=92, count=31)
    evaluation = evaluate_one_step(candidate, x, u, outputs=y)
    np.testing.assert_allclose(evaluation.state_rmse, 0, atol=2e-14)
    np.testing.assert_allclose(evaluation.output_rmse, 0, atol=2e-14)
    assert evaluation.candidate_digest == candidate.candidate_digest
    assert evaluation.sample_count == 31


def test_noise_residuals_and_normal_equation_orthogonality():
    states, inputs, _ = trajectory(count=250, noise=0.025)
    candidate = fit_lti(states, inputs, **METADATA)
    residual = states[1:] - states[:-1] @ candidate.A.T - inputs @ candidate.B.T
    np.testing.assert_allclose(candidate.diagnostics.state_residuals, residual, atol=1e-15)
    np.testing.assert_allclose(candidate.diagnostics.state_residual_sum_squares,
                               np.sum(residual ** 2, axis=0), atol=1e-15)
    z = np.column_stack((states[:-1], inputs))
    np.testing.assert_allclose(z.T @ residual, 0, atol=2e-12)
    assert np.all(candidate.diagnostics.state_residual_sum_squares > 0)
    assert candidate.diagnostics.degrees_of_freedom == 247
    x, u, _ = trajectory(seed=125, count=100, noise=0.025)
    evaluation = evaluate_one_step(candidate, x, u)
    assert np.all((evaluation.state_rmse > 0.015) & (evaluation.state_rmse < 0.04))


def test_rank_deficiency_refuses_usable_model():
    states = np.ones((11, 2))
    inputs = np.ones((10, 1))
    with pytest.raises(NonIdentifiableError) as error:
        fit_lti(states, inputs, **METADATA)
    diagnostics = error.value.diagnostics
    assert diagnostics.rank == 1
    assert diagnostics.regressor_count == 3
    assert diagnostics.state_residuals is None
    assert len(diagnostics.singular_values) == 3
    assert not hasattr(error.value, "candidate")


def test_insufficient_transitions_refused():
    states, inputs, _ = trajectory(count=2)
    with pytest.raises(NonIdentifiableError):
        fit_lti(states, inputs, **METADATA)


def test_rank_cutoff_changes_identifiability():
    states = np.array([[1.0], [2.0], [4.0], [8.0]])
    inputs = states[:-1] + np.array([[1e-8], [-1e-8], [1e-8]])
    metadata = dict(sample_interval=1, state_names=("x",), state_units=("1",),
                    input_names=("u",), input_units=("1",))
    fit_lti(states, inputs, rcond=1e-12, **metadata)
    with pytest.raises(NonIdentifiableError):
        fit_lti(states, inputs, rcond=1e-6, **metadata)


def test_autonomous_system_and_zero_residual_degrees_freedom():
    candidate = fit_lti([[1.0], [0.5]], np.empty((1, 0)), sample_interval=1,
                        state_names=("x",), state_units=("1",), input_names=(), input_units=())
    np.testing.assert_allclose(candidate.A, [[0.5]])
    assert candidate.B.shape == (1, 0)
    assert candidate.diagnostics.degrees_of_freedom == 0
    np.testing.assert_allclose(candidate.predict_next([[0.5]], np.empty((1, 0))), [[0.25]])


def test_mixed_boolean_numeric_sequences_are_refused():
    with pytest.raises(ValueError):
        fit_lti([[True], [0.5]], np.empty((1, 0)), sample_interval=1,
                state_names=("x",), state_units=("1",), input_names=(), input_units=())


def test_input_nonmutation_and_result_immutability():
    states, inputs, outputs = trajectory()
    snapshots = [a.copy() for a in (states, inputs, outputs)]
    candidate = fit_lti(states, inputs, outputs=outputs, output_names=("sensor",),
                        output_units=("m",), **METADATA)
    evaluate_one_step(candidate, states, inputs, outputs=outputs)
    for actual, before in zip((states, inputs, outputs), snapshots):
        np.testing.assert_array_equal(actual, before)
    for array in (candidate.A, candidate.B, candidate.C, candidate.D,
                  candidate.diagnostics.state_residuals, candidate.diagnostics.singular_values):
        with pytest.raises(ValueError):
            array.setflags(write=True)
    states[:] = 999
    np.testing.assert_allclose(candidate.A, A, atol=2e-14)


def test_digest_binds_model_metadata_and_is_deterministic():
    states, inputs, _ = trajectory()
    candidate = fit_lti(states, inputs, **METADATA)
    assert candidate.candidate_digest == fit_lti(states, inputs, **METADATA).candidate_digest
    assert candidate.candidate_digest != fit_lti(states, inputs, **dict(METADATA, sample_interval=0.2)).candidate_digest
    assert candidate.candidate_digest != fit_lti(states, inputs, conditioning_reference="stfe:fixture-1", **METADATA).candidate_digest


@pytest.mark.parametrize("change", [
    {"sample_interval": 0}, {"sample_interval": -1}, {"sample_interval": float("nan")},
    {"sample_interval": float("inf")}, {"sample_interval": True},
    {"sample_interval": np.bool_(True)}, {"sample_interval": np.complex128(1 + 2j)},
    {"state_names": ("x",)}, {"state_names": ("x", "x")},
    {"input_units": ("",)}, {"input_names": "force"},
    {"output_names": ("unobserved",)}, {"conditioning_reference": ""},
    {"rcond": 0}, {"rcond": 1}, {"rcond": float("nan")}, {"rcond": True},
    {"rcond": np.bool_(True)}, {"rcond": np.complex128(1e-6 + 2j)},
])
def test_invalid_metadata(change):
    states, inputs, _ = trajectory()
    with pytest.raises(ValueError):
        fit_lti(states, inputs, **dict(METADATA, **change))


@pytest.mark.parametrize("kind", ["one_dim", "wrong_rows", "nan", "inf", "complex", "bool", "empty"])
def test_invalid_arrays(kind):
    states, inputs, _ = trajectory()
    if kind == "one_dim":
        inputs = inputs[:, 0]
    elif kind == "wrong_rows":
        inputs = inputs[:-1]
    elif kind == "nan":
        states[5, 1] = np.nan
    elif kind == "inf":
        inputs[1, 0] = np.inf
    elif kind == "complex":
        states = states.astype(complex)
    elif kind == "bool":
        inputs = inputs.astype(bool)
    elif kind == "empty":
        states = np.empty((0, 2))
        inputs = np.empty((0, 1))
    with pytest.raises(ValueError):
        fit_lti(states, inputs, **METADATA)


def test_output_and_prediction_shapes_are_checked_without_broadcasting():
    states, inputs, outputs = trajectory()
    with pytest.raises(ValueError):
        fit_lti(states, inputs, outputs=outputs[:-1], output_names=("y",), output_units=("1",), **METADATA)
    candidate = fit_lti(states, inputs, **METADATA)
    with pytest.raises(ValueError):
        candidate.predict_next(states[:-1, :1], inputs)
    with pytest.raises(ValueError):
        candidate.predict_next(states[:-1], inputs[:-1])
    with pytest.raises(ValueError):
        evaluate_one_step(candidate, states, inputs, outputs=outputs)
    candidate = fit_lti(states, inputs, outputs=outputs, output_names=("y",), output_units=("1",), **METADATA)
    with pytest.raises(ValueError):
        evaluate_one_step(candidate, states, inputs, outputs=np.repeat(outputs, 2, axis=1))
