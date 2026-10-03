"""Bounded nonlinear estimation, actual pinned engines and retained refusal gates.

The numerical oracles below use direct Gaussian conditioning and hand-derived
Jacobians. They do not call either provider's estimator or differentiation APIs.
"""
import base64
from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pytest

from ciw import sensor_fusion_ekf as contract
from ciw import sensor_fusion_ekf_workflow as workflow
from ciw import sensor_fusion_workflow as linear
from ciw.adapters.protocol import AdapterRefusal
from ciw.cli import parser
from ciw.instruments import make_demo_run
from ciw.session import Session
from ciw.telemetry import _bundle_digest, byte_digest, canonical, digest
from scripts.monorepo import provider_worktrees

from test_sensor_fusion_contract import alter_record, encoded, record, scalar_source

ROOT = Path(__file__).resolve().parents[1]
METHOD = "jspt.analytic-gsie.error-state-ekf.v1"


def model(family="affine.v1", **parameters):
    return {"family": family, "parameters": parameters,
            "evidence_b64": encoded(("Declared analytic parameters: " + family).encode())}


def ekf_source(*, joint=False):
    source = scalar_source(joint=joint)
    source["schema"] = "ciw.sensor-fusion-ekf-source.v1"
    source["experiment_id"] = "analytic:bounded-ekf"
    source["configuration"]["method"] = METHOD
    for configuration in source["configuration"]["configurations"]:
        for sensor in configuration["sensors"]:
            sensor["model"] = model(matrix=sensor.pop("matrix"), offset=[0])
    for batch in source["batches"]:
        batch["dynamics"]["model"] = model(matrix=batch["dynamics"].pop("matrix"), offset=[0])
    return source


def affine_plane_source():
    source = ekf_source(joint=True)
    source["configuration"]["state"].update(quantity_ids=["x", "v"], units=["m", "m"])
    source["prior"].update(mean=[1, -.5], covariance=[[2, .3], [.3, 1]])
    a, b = source["configuration"]["configurations"][0]["sensors"]
    a.update(model=model(matrix=[[1, .2]], offset=[.6]), model_ref="model:a-affine")
    b.update(model=model(matrix=[[-.1, 1]], offset=[-.4]), model_ref="model:b-affine")
    batch = source["batches"][0]
    batch["dynamics"].update(model=model(matrix=[[.8, .4], [-.2, 1.1]], offset=[.3, -.2]),
                             process_covariance=[[.4, .08], [.08, .3]])
    batch["observations"] = [record(a, 1, [1.8]), record(b, 1, [-.1])]
    batch["measurement_noise"]["matrix"] = [[.5, .1], [.1, .4]]
    return source


def gaussian_oracle(mean, covariance, transition, drift, process_noise, observation,
                    sensor_matrix, sensor_offset, measurement_noise):
    mean = np.asarray(mean, float)
    covariance = np.asarray(covariance, float)
    transition, process_noise = np.asarray(transition, float), np.asarray(process_noise, float)
    matrix, noise = np.asarray(sensor_matrix, float), np.asarray(measurement_noise, float)
    predicted = transition @ mean + drift
    predicted_covariance = transition @ covariance @ transition.T + process_noise
    expected = matrix @ predicted + sensor_offset
    innovation = np.asarray(observation) - expected
    innovation_covariance = matrix @ predicted_covariance @ matrix.T + noise
    gain = np.linalg.solve(innovation_covariance, matrix @ predicted_covariance).T
    posterior = predicted + gain @ innovation
    # Joseph form gives an independently stated covariance identity.
    residual_map = np.eye(len(mean)) - gain @ matrix
    posterior_covariance = (residual_map @ predicted_covariance @ residual_map.T + gain @ noise @ gain.T)
    return {"predicted": predicted, "predicted_covariance": predicted_covariance,
            "mean": posterior, "covariance": posterior_covariance,
            "innovation": innovation, "innovation_covariance": innovation_covariance,
            "residual": np.asarray(observation) - (matrix @ posterior + sensor_offset),
            "nis": innovation @ np.linalg.solve(innovation_covariance, innovation)}


@pytest.fixture(scope="module")
def repositories():
    with provider_worktrees(ROOT, roles=["gsie", "jspt"]) as binding:
        yield binding


@pytest.fixture(scope="module")
def bundle(repositories):
    return workflow.SensorFusionEKFWorkflow().create_session(canonical(ekf_source()), repositories)


def data(bundle):
    return bundle["steps"][0]["result"]["data"]


def estimates(bundle):
    return data(bundle)["estimates"]


def reseal_step(step):
    result = step["result"]
    result["result_id"] = digest({key: value for key, value in result.items() if key != "result_id"})
    step["result_id"] = result["result_id"]
    step["result_sha256"] = digest(result)
    step["numerical_result"] = {"operation_id": "ciw.sensor-fusion-ekf.v1", "data": deepcopy(result["data"])}
    step["numerical_result_id"] = digest(step["numerical_result"])


def reseal(bundle):
    for step in (bundle["steps"][0], bundle["verification"]["reproduction"]):
        reseal_step(step)
    bundle["bundle_digest"] = _bundle_digest(bundle)
    bundle["verification"] = workflow._verification(bundle, bundle["verification"]["reproduction"])
    return bundle


def change_data(bundle, mutation):
    changed = deepcopy(bundle)
    for step in (changed["steps"][0], changed["verification"]["reproduction"]):
        mutation(step["result"]["data"])
    return reseal(changed)


def call(session, kind, payload=None, *, error=False):
    response = session.handle({"protocol_version": 1, "request_id": "ekf-test", "type": kind,
                               "payload": payload or {}})
    assert response["type"] == ("error" if error else "response"), response
    return response["payload"]


def add(session, source):
    raw = canonical(source) if isinstance(source, dict) else source
    return call(session, "source.add", {"kind": "sensor-fusion-ekf", "label": "Declared nonlinear experiment",
                                        "bytes_b64": encoded(raw)})


def test_affine_zero_offset_agrees_with_existing_linear_instrument(bundle, repositories):
    old = linear.SensorFusionWorkflow().create_session(canonical(scalar_source()), {"gsie": repositories["gsie"]})
    actual, = estimates(bundle)
    expected, = estimates(old)
    assert actual["mean"] == expected["mean"] == [1.0]
    assert actual["covariance"] == expected["covariance"] == [[2.5]]
    assert {key: actual["diagnostics"][key] for key in expected["diagnostics"]} == expected["diagnostics"]
    assert actual["diagnostics"]["linearized_residual"] == expected["diagnostics"]["residual"]
    details = actual["linearization"]
    assert details["dynamics_center"] == [0.0]
    assert details["dynamics_value"] == [0.0]
    assert details["dynamics_jacobian"] == [[1.0]]
    assert details["predicted_mean"] == [0.0]
    assert details["predicted_covariance"] == [[5.0]]
    assert details["observation_value"] == [0.0]
    assert details["observation_jacobian"] == [[1.0]]
    assert details["correction"] == [1.0]
    assert details["post_observation_value"] == [1.0]
    assert details["kernel_prediction"]["mean"] == [0.0]
    assert details["kernel_prediction"]["covariance"] == [[5.0]]
    assert details["kernel_update"]["mean"] == [1.0]
    assert details["kernel_update"]["covariance"] == [[2.5]]
    assert actual["predicted_state_id"] != details["kernel_prediction"]["state_id"]
    assert actual["state_id"] != details["kernel_update"]["state_id"]
    assert data(bundle)["method"] == METHOD
    assert bundle["verification"]["outcome"] == "passed"
    assert bundle["verification"]["independent"] is False
    assert data(bundle)["authority"]["state_admission"] == "not_performed"
    assert data(bundle)["authority"]["physical_validation"] == "not_established"


def test_nonzero_affine_drifts_and_joint_correlated_sensors_match_gaussian_conditioning(repositories):
    source = affine_plane_source()
    result = workflow.SensorFusionEKFWorkflow().create_session(canonical(source), repositories)
    actual, = estimates(result)
    oracle = gaussian_oracle([1, -.5], [[2, .3], [.3, 1]], [[.8, .4], [-.2, 1.1]],
        [.3, -.2], [[.4, .08], [.08, .3]], [1.8, -.1], [[1, .2], [-.1, 1]], [.6, -.4], [[.5, .1], [.1, .4]])
    for key in ("mean", "covariance"):
        np.testing.assert_allclose(actual[key], oracle[key], rtol=3e-13, atol=3e-13)
    for key in ("innovation", "innovation_covariance", "residual"):
        np.testing.assert_allclose(actual["diagnostics"][key], oracle[key], rtol=3e-13, atol=3e-13)
    assert actual["diagnostics"]["nis"] == pytest.approx(oracle["nis"], rel=3e-13)
    assert actual["observation_order"] == ["a/indication", "b/indication"]


def test_quadratic_sensor_uses_predicted_center_and_true_nonlinear_posterior_residual(repositories):
    source = ekf_source()
    source["prior"].update(mean=[2], covariance=[[.5]])
    batch = source["batches"][0]
    batch["dynamics"].update(model=model(matrix=[[1]], offset=[1]), process_covariance=[[.25]])
    sensor = source["configuration"]["configurations"][0]["sensors"][0]
    sensor["model"] = model("quadratic.v1", hessian=[[2]], gradient=[0])
    batch["observations"] = [record(sensor, 1, [10])]
    batch["measurement_noise"]["matrix"] = [[1]]
    actual, = estimates(workflow.SensorFusionEKFWorkflow().create_session(canonical(source), repositories))
    # f(2)=3, P-=.75; h(3)=9, h'(3)=6; S=28, K=4.5/28.
    posterior = 3 + 4.5 / 28
    assert actual["mean"][0] == pytest.approx(posterior, rel=2e-14)
    assert actual["covariance"][0][0] == pytest.approx(.75 / 28, rel=2e-14)
    assert actual["diagnostics"]["innovation"] == [1.0]
    assert actual["diagnostics"]["innovation_covariance"] == [[28.0]]
    assert actual["diagnostics"]["nis"] == pytest.approx(1 / 28)
    assert actual["diagnostics"]["residual"][0] == pytest.approx(10 - posterior ** 2, rel=3e-13)
    assert actual["diagnostics"]["residual"][0] != pytest.approx(1 - 6 * (posterior - 3))
    assert actual["diagnostics"]["linearized_residual"][0] == pytest.approx(1 - 6 * (posterior - 3))
    details = actual["linearization"]
    assert details["dynamics_center"] == [2.0]
    assert details["dynamics_value"] == [3.0]
    assert details["observation_value"] == [9.0]
    assert details["observation_jacobian"] == [[6.0]]
    assert details["correction"][0] == pytest.approx(4.5 / 28)
    assert details["post_observation_value"][0] == pytest.approx(posterior ** 2)


def test_correlated_nonlinear_sensors_share_one_prediction_center_and_one_joint_update(repositories):
    source = ekf_source(joint=True)
    source["prior"].update(mean=[2], covariance=[[.3]])
    first, second = source["configuration"]["configurations"][0]["sensors"]
    first["model"] = model("quadratic.v1", hessian=[[2]], gradient=[0])
    second["model"] = model("quadratic.v1", hessian=[[1]], gradient=[0])
    batch = source["batches"][0]
    batch["dynamics"]["process_covariance"] = [[.1]]
    batch["observations"] = [record(first, 1, [4.3]), record(second, 1, [1.8])]
    batch["measurement_noise"]["matrix"] = [[.5, .15], [.15, .3]]
    estimate, = estimates(workflow.SensorFusionEKFWorkflow().create_session(canonical(source), repositories))
    oracle = gaussian_oracle([2], [[.3]], [[1]], [0], [[.1]], [4.3, 1.8], [[4], [2]], [-4, -2], [[.5, .15], [.15, .3]])
    np.testing.assert_allclose(estimate["mean"], oracle["mean"], rtol=2e-13, atol=2e-13)
    np.testing.assert_allclose(estimate["covariance"], oracle["covariance"], rtol=2e-13, atol=2e-13)
    np.testing.assert_allclose(estimate["linearization"]["observation_value"], [4, 2])
    np.testing.assert_allclose(estimate["linearization"]["observation_jacobian"], [[4], [2]])
    posterior = estimate["mean"][0]
    np.testing.assert_allclose(estimate["diagnostics"]["residual"], [4.3 - posterior ** 2, 1.8 - .5 * posterior ** 2],
                               rtol=2e-13, atol=2e-13)


def test_quadratic_dynamics_and_sensor_reconfiguration_propagate_actual_posterior(repositories):
    source = ekf_source()
    source["prior"].update(mean=[1], covariance=[[.2]])
    batch = source["batches"][0]
    batch["dynamics"].update(model=model("quadratic.v1", hessian=[[2]], gradient=[.5]),
                             process_covariance=[[.1]])
    sensor = source["configuration"]["configurations"][0]["sensors"][0]
    sensor["model"] = model("quadratic.v1", hessian=[[2]], gradient=[0])
    batch["observations"] = [record(sensor, 1, [2.5])]
    batch["measurement_noise"]["matrix"] = [[.5]]
    changed_sensor = deepcopy(sensor)
    changed_sensor.update(sensor_id="replacement", model=model(matrix=[[2]], offset=[.3]))
    source["configuration"]["configurations"].append({"name": "replacement", "sensors": [changed_sensor]})
    second = deepcopy(batch)
    second.update(time=2, configuration_ref="replacement", observations=[record(changed_sensor, 2, [4])])
    second["measurement_noise"] = {**batch["measurement_noise"], "matrix": [[.4]],
                                     "channel_order": ["replacement/indication"]}
    third = deepcopy(second)
    third.update(time=3, observations=[], measurement_noise=None)
    source["batches"].extend([second, third])
    actual = estimates(workflow.SensorFusionEKFWorkflow().create_session(canonical(source), repositories))
    center, covariance = 1.0, .2
    for index, estimate in enumerate(actual):
        predicted = center ** 2 + .5 * center
        variance = (2 * center + .5) ** 2 * covariance + .1
        if index < 2:
            expected, derivative, observation, noise = (predicted ** 2, 2 * predicted, 2.5, .5) if index == 0 else (2 * predicted + .3, 2, 4, .4)
            innovation = observation - expected
            gain = variance * derivative / (derivative ** 2 * variance + noise)
            center = predicted + gain * innovation
            covariance = variance * noise / (derivative ** 2 * variance + noise)
        else:
            center, covariance = predicted, variance
        assert estimate["mean"][0] == pytest.approx(center, rel=3e-13)
        assert estimate["covariance"][0][0] == pytest.approx(covariance, rel=3e-13)
    assert [entry["epoch_index"] for entry in actual] == [0, 1, 1]
    assert actual[1]["predecessor_state_id"] == actual[0]["state_id"]
    assert actual[2]["predecessor_state_id"] == actual[1]["state_id"]
    assert actual[2]["state_id"] == actual[2]["predicted_state_id"]
    assert actual[2]["diagnostics"] == {"status": "prediction_only", "innovation": [],
        "innovation_covariance": [], "residual": [], "linearized_residual": [], "nis": None}
    assert actual[2]["linearization"]["kernel_update"] is None
    assert actual[1]["linearization"]["dynamics_center"] == actual[0]["mean"]
    assert actual[2]["linearization"]["dynamics_center"] == actual[1]["mean"]


def test_dimensionless_componentwise_exponential_matches_analytic_ekf_oracle(repositories):
    source = ekf_source()
    source["configuration"]["state"]["units"] = ["1"]
    source["prior"].update(mean=[0], covariance=[[.2]])
    sensor = source["configuration"]["configurations"][0]["sensors"][0]
    sensor.update(units=["1"], model=model("componentwise-exp.v1"))
    batch = source["batches"][0]
    batch["dynamics"].update(model=model("componentwise-exp.v1"), process_covariance=[[.1]])
    batch["observations"] = [record(sensor, 1, [3])]
    batch["measurement_noise"]["matrix"] = [[.4]]
    estimate, = estimates(workflow.SensorFusionEKFWorkflow().create_session(canonical(source), repositories))
    predicted, variance = 1.0, .3
    derivative = np.exp(predicted)
    innovation = 3 - derivative
    innovation_variance = derivative ** 2 * variance + .4
    posterior = predicted + variance * derivative / innovation_variance * innovation
    assert estimate["mean"][0] == pytest.approx(posterior, rel=2e-13)
    assert estimate["covariance"][0][0] == pytest.approx(variance * .4 / innovation_variance, rel=2e-13)
    assert estimate["diagnostics"]["innovation"][0] == pytest.approx(innovation)
    assert estimate["diagnostics"]["residual"][0] == pytest.approx(3 - np.exp(posterior))


def range_source():
    source = ekf_source()
    source["configuration"]["state"].update(quantity_ids=["x", "y"], units=["m", "m"])
    source["prior"].update(mean=[3, 4], covariance=[[.2, .02], [.02, .3]])
    sensor = source["configuration"]["configurations"][0]["sensors"][0]
    sensor["model"] = model("planar-range.v1", position_matrix=[[1, 0], [0, 1]], anchor=[0, 0], minimum_range=1e-6)
    batch = source["batches"][0]
    batch["dynamics"].update(model=model(matrix=[[1, 0], [0, 1]], offset=[0, 0]), process_covariance=[[0, 0], [0, 0]])
    batch["observations"] = [record(sensor, 1, [5.3])]
    batch["measurement_noise"]["matrix"] = [[.1]]
    return source


def test_planar_range_composition_uses_radial_jacobian_and_true_residual(repositories):
    source = range_source()
    estimate, = estimates(workflow.SensorFusionEKFWorkflow().create_session(canonical(source), repositories))
    covariance = np.asarray(source["prior"]["covariance"])
    jacobian = np.asarray([[.6, .8]])
    innovation_covariance = float((jacobian @ covariance @ jacobian.T)[0, 0] + .1)
    gain = covariance @ jacobian.T / innovation_covariance
    posterior = np.asarray([3, 4]) + gain[:, 0] * .3
    posterior_covariance = covariance - gain @ jacobian @ covariance
    np.testing.assert_allclose(estimate["mean"], posterior, rtol=2e-13, atol=2e-13)
    np.testing.assert_allclose(estimate["covariance"], posterior_covariance, rtol=2e-13, atol=2e-13)
    assert estimate["diagnostics"]["innovation"][0] == pytest.approx(.3)
    assert estimate["diagnostics"]["residual"][0] == pytest.approx(5.3 - np.linalg.norm(posterior))


def test_posterior_cannot_cross_into_a_declared_excluded_range_domain(repositories):
    source = range_source()
    source["prior"].update(mean=[1, 0], covariance=[[1, 0], [0, 0]])
    sensor = source["configuration"]["configurations"][0]["sensors"][0]
    source["batches"][0]["observations"] = [record(sensor, 1, [-1])]
    source["batches"][0]["measurement_noise"]["matrix"] = [[1]]
    # h=1, J=[1,0], S=2 and K=[.5,0] send m+ exactly to the anchor.
    with pytest.raises((ValueError, AdapterRefusal)):
        workflow.SensorFusionEKFWorkflow().create_session(canonical(source), repositories)


@pytest.mark.parametrize("center", [[0, 0], [1e-7, 0]])
def test_range_chart_domain_refuses_the_origin_and_declared_guard_region(repositories, center):
    source = range_source()
    source["prior"]["mean"] = center
    with pytest.raises((ValueError, AdapterRefusal)):
        workflow.SensorFusionEKFWorkflow().create_session(canonical(source), repositories)


def test_mean_correction_below_float_resolution_refuses_instead_of_erasing_measurement(repositories):
    source = ekf_source()
    source["prior"].update(mean=[1e20], covariance=[[1]])
    batch = source["batches"][0]
    batch["dynamics"]["process_covariance"] = [[0]]
    sensor = source["configuration"]["configurations"][0]["sensors"][0]
    sensor["model"] = model(matrix=[[1]], offset=[-1e20])
    batch["observations"] = [record(sensor, 1, [1])]
    batch["measurement_noise"]["matrix"] = [[1]]
    with pytest.raises((ValueError, AdapterRefusal)):
        workflow.SensorFusionEKFWorkflow().create_session(canonical(source), repositories)


@pytest.mark.parametrize("variance,coefficient,noise", [(1e-200, 1e-200, 1), (1e-180, 1e-180, 1e-300)])
def test_joint_kernel_cross_covariance_underflow_cannot_silently_remove_a_sensor(repositories, variance, coefficient, noise):
    source = ekf_source()
    source["prior"].update(mean=[0], covariance=[[variance]])
    sensor = source["configuration"]["configurations"][0]["sensors"][0]
    sensor["model"] = model(matrix=[[coefficient]], offset=[0])
    batch = source["batches"][0]
    batch["dynamics"]["process_covariance"] = [[0]]
    batch["observations"] = [record(sensor, 1, [1])]
    batch["measurement_noise"]["matrix"] = [[noise]]
    with pytest.raises((ValueError, AdapterRefusal)):
        workflow.SensorFusionEKFWorkflow().create_session(canonical(source), repositories)


def test_exponential_overflow_and_underflow_refuse(repositories):
    for center in (-1000, 1000):
        source = ekf_source()
        source["configuration"]["state"]["units"] = ["1"]
        source["prior"]["mean"] = [center]
        sensor = source["configuration"]["configurations"][0]["sensors"][0]
        sensor.update(units=["1"], model=model("componentwise-exp.v1"))
        source["batches"][0]["observations"] = [record(sensor, 1, [1])]
        with pytest.raises((ValueError, AdapterRefusal)):
            workflow.SensorFusionEKFWorkflow().create_session(canonical(source), repositories)


def test_affine_dot_product_cancellation_cannot_silently_erase_a_unit_signal(repositories):
    source = ekf_source()
    source["configuration"]["state"].update(quantity_ids=["a", "b", "c"], units=["m", "m", "m"])
    source["prior"].update(mean=[1e16, 1, -1e16], covariance=np.eye(3).tolist())
    sensor = source["configuration"]["configurations"][0]["sensors"][0]
    sensor["model"] = model(matrix=[[1, 1, 1]], offset=[0])
    batch = source["batches"][0]
    batch["dynamics"].update(model=model(matrix=np.eye(3).tolist(), offset=[0, 0, 0]),
                             process_covariance=np.zeros((3, 3)).tolist())
    batch["observations"] = [record(sensor, 1, [2])]
    with pytest.raises((ValueError, AdapterRefusal)):
        workflow.SensorFusionEKFWorkflow().create_session(canonical(source), repositories)


@pytest.mark.parametrize("center,minimum", [([1e200, 1e200], 1e-6), ([2e-200, 2e-200], 1e-201)])
def test_range_derivative_overflow_and_underflow_cannot_produce_a_false_zero_jacobian(repositories, center, minimum):
    source = range_source()
    source["prior"].update(mean=center, covariance=[[0, 0], [0, 0]])
    sensor = source["configuration"]["configurations"][0]["sensors"][0]
    sensor["model"]["parameters"]["minimum_range"] = minimum
    source["batches"][0]["observations"] = [record(sensor, 1, [float(np.hypot(*center))])]
    with pytest.raises((ValueError, AdapterRefusal)):
        workflow.SensorFusionEKFWorkflow().create_session(canonical(source), repositories)


@pytest.mark.parametrize("mutation", [
    lambda s: s["configuration"].update(method="unsafe.autodiff.v1"),
    lambda s: s["configuration"]["state"].update(geometry="so2_scalar_radians.v1", units=["rad"]),
    lambda s: s["configuration"]["configurations"][0]["sensors"][0]["model"].update(family="python.eval"),
    lambda s: s["configuration"]["configurations"][0]["sensors"][0]["model"].update(code="__import__('os')"),
    lambda s: s["configuration"]["configurations"][0]["sensors"][0]["model"].update(evidence_b64=""),
    lambda s: s["configuration"]["configurations"][0]["sensors"][0]["model"]["parameters"].update(offset=[0, 0]),
    lambda s: s["configuration"]["configurations"][0]["sensors"][0]["model"]["parameters"].update(matrix=[[True]]),
    lambda s: s["configuration"]["configurations"][0]["sensors"][0]["model"]["parameters"].update(matrix=[[2 ** 54 + 1]]),
    lambda s: s["configuration"]["configurations"][0]["sensors"][0]["model"]["parameters"].update(executable="untrusted.module"),
    lambda s: s["configuration"]["configurations"][0]["sensors"][0].update(matrix=[[999]]),
    lambda s: s["batches"][0]["dynamics"].update(matrix=[[999]]),
    lambda s: s["batches"][0]["dynamics"].update(model=model("quadratic.v1", hessian=[[1, 0]], gradient=[0])),
    lambda s: s["batches"][0]["dynamics"].update(model=model("componentwise-exp.v1")),
    lambda s: s["prior"].update(covariance=[[-1]]),
    lambda s: s["batches"][0]["measurement_noise"].update(matrix=[[-1]]),
    lambda s: s["batches"][0].update(time=0),
    lambda s: s["configuration"]["noise_policy"].update(across_batches="unknown"),
])
def test_declared_model_and_scientific_inputs_refuse_before_provider_binding(mutation):
    source = ekf_source()
    mutation(source)
    with pytest.raises((ValueError, AdapterRefusal)):
        contract.validate_source(canonical(source))


def test_quadratic_hessian_must_be_symmetric_but_can_be_indefinite():
    source = affine_plane_source()
    sensor = source["configuration"]["configurations"][0]["sensors"][0]
    sensor["model"] = model("quadratic.v1", hessian=[[1, .3], [.2, -1]], gradient=[0, 0])
    with pytest.raises((ValueError, AdapterRefusal)):
        contract.validate_source(canonical(source))
    sensor["model"]["parameters"]["hessian"] = [[1, .2], [.2, -1]]
    assert contract.validate_source(canonical(source)) == source


def test_state_dimension_is_explicitly_bounded_and_scalar_quadratic_cannot_be_vector_dynamics():
    source = ekf_source()
    count = 17
    source["configuration"]["state"].update(quantity_ids=["q" + str(i) for i in range(count)], units=["m"] * count)
    source["prior"].update(mean=[0] * count, covariance=np.eye(count).tolist())
    source["configuration"]["configurations"][0]["sensors"][0]["model"] = model(matrix=[[1] * count], offset=[0])
    source["batches"][0]["dynamics"].update(model=model(matrix=np.eye(count).tolist(), offset=[0] * count),
        process_covariance=np.zeros((count, count)).tolist())
    with pytest.raises((ValueError, AdapterRefusal)):
        contract.validate_source(canonical(source))
    source = affine_plane_source()
    source["batches"][0]["dynamics"]["model"] = model("quadratic.v1", hessian=[[2, 0], [0, 2]], gradient=[0, 0])
    with pytest.raises((ValueError, AdapterRefusal)):
        contract.validate_source(canonical(source))


@pytest.mark.parametrize("mutation", [
    lambda r: r.update(clock_id="device-clock"),
    lambda r: r.update(units=["cm"]),
    lambda r: r.update(frame="undeclared-frame"),
    lambda r: r.update(time=1.001),
    lambda r: r.update(calibration_ref=byte_digest(b"different calibration")),
    lambda r: r.update(values=[False]),
])
def test_observation_identity_clock_units_and_calibration_are_bound(mutation):
    source = ekf_source()
    alter_record(source, mutation)
    with pytest.raises((ValueError, AdapterRefusal)):
        contract.validate_source(canonical(source))


def test_correlated_noise_and_unique_acquisitions_retain_existing_contract():
    source = ekf_source(joint=True)
    source["batches"][0]["measurement_noise"]["cross_sensor_policy"] = "declared_independent"
    with pytest.raises((ValueError, AdapterRefusal)):
        contract.validate_source(canonical(source))
    source["batches"][0]["measurement_noise"]["cross_sensor_policy"] = "full_joint_declared"
    first = json.loads(base64.b64decode(source["batches"][0]["observations"][0]["record_b64"]))
    alter_record(source, lambda r: r.update(raw_evidence_b64=first["raw_evidence_b64"]), index=1)
    assert contract.validate_source(canonical(source)) == source
    alter_record(source, lambda r: r.update(acquisition_id=first["acquisition_id"]), index=1)
    with pytest.raises((ValueError, AdapterRefusal)):
        contract.validate_source(canonical(source))


@pytest.mark.parametrize("raw", [b'{"schema":"a","schema":"b"}', b'{"schema":NaN}', b"{", b"[]"])
def test_strict_json_refuses_ambiguous_nonlinear_sources(raw):
    with pytest.raises((ValueError, AdapterRefusal)):
        contract.validate_source(raw)


def test_replay_has_stable_numerical_identity_and_fresh_execution_occurrences(bundle, repositories):
    replay = workflow.SensorFusionEKFWorkflow().replay_session(bundle, repositories)
    fresh = replay["session"]
    assert workflow.SensorFusionEKFWorkflow()._validate(fresh) == canonical(ekf_source())
    assert fresh["session_id"] != bundle["session_id"]
    assert fresh["bundle_digest"] != bundle["bundle_digest"]
    for old, new in zip((bundle["steps"][0], bundle["verification"]["reproduction"]),
                        (fresh["steps"][0], fresh["verification"]["reproduction"]), strict=True):
        assert old["execution_id"] != new["execution_id"]
        assert old["result_id"] != new["result_id"]
        assert old["numerical_result_id"] == new["numerical_result_id"]
    assert replay["replay_receipt"]["numerical_match"] is True


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(method="unqualified.ekf"),
    lambda d: d.update(authority={**d["authority"], "state_admission": "admitted"}),
    lambda d: d["state_contract"].update(units=["cm"]),
    lambda d: d["estimates"][0].update(configuration_id="sha256:" + "0" * 64),
    lambda d: d["estimates"][0].update(epoch_index=True),
    lambda d: d["estimates"][0].update(observation_refs=[]),
    lambda d: d["estimates"][0].update(predecessor_state_id="sha256:" + "0" * 64),
    lambda d: d["estimates"][0]["diagnostics"].update(innovation_covariance=[[0]]),
    lambda d: d["estimates"][0]["diagnostics"].update(nis=-1),
    lambda d: d["estimates"][0]["linearization"].update(dynamics_center=[1.0]),
    lambda d: d["estimates"][0]["linearization"].update(predicted_mean=[1.0]),
    lambda d: d["estimates"][0]["linearization"].update(predicted_covariance=[[0.0]]),
    lambda d: d["estimates"][0]["linearization"].update(dynamics_jacobian=[[1.0, 0.0]]),
    lambda d: d["estimates"][0]["linearization"]["kernel_prediction"].update(covariance=[[0.0]]),
    lambda d: d["estimates"][0]["linearization"]["kernel_update"].update(covariance=[[0.0]]),
])
def test_coherently_resealed_scientific_bindings_cannot_change(bundle, mutation):
    with pytest.raises(ValueError):
        workflow.SensorFusionEKFWorkflow()._validate(change_data(bundle, mutation))


def kernel_identity(kernel):
    return byte_digest(b"geometric-state-inference.state-transition.v1\0" + canonical({
        "configuration": kernel["replay"], "mean": kernel["mean"], "covariance": kernel["covariance"]}))


def rebind_linked_kernel_ids(source, estimate, *, update_model_id=None, observation_id=None):
    """Reseal all affected inner/outer commitments so syntax alone cannot catch a forgery."""
    details = estimate["linearization"]
    prediction = details["kernel_prediction"]
    prediction["state_id"] = kernel_identity(prediction)
    prediction_fields = {key: details[key] for key in contract.PREDICTION_FIELDS}
    predicted_id = contract.state_identity(source, 0, "prediction", estimate["predecessor_state_id"],
        details["predicted_mean"], details["predicted_covariance"], prediction_fields)
    estimate["predicted_state_id"] = predicted_id
    update = details["kernel_update"]
    prior = update["replay"]["prior"]
    prior.update(state_id=prediction["state_id"], replay=deepcopy(prediction["replay"]),
                 dynamics_model_id=prediction["replay"]["dynamics"]["model_id"],
                 predecessor_state_id=prediction["replay"]["prior"]["state_id"])
    batch = source["batches"][0]
    update["replay"]["observation"]["observation_id"] = observation_id or digest({
        "schema": "ciw.sensor-fusion-ekf-linearized-observation.v1", "batch_id": digest(batch),
        "predecessor_state_id": predicted_id, "values": contract.batch_inputs(source, 0)["values"],
        "observation_value": details["observation_value"], "innovation": estimate["diagnostics"]["innovation"]})
    update["replay"]["model"]["model_id"] = update_model_id or digest({
        "schema": "ciw.sensor-fusion-ekf-linearized-observation-model.v1", "batch_id": digest(batch),
        "configuration_id": estimate["configuration_id"], "predecessor_state_id": predicted_id,
        "matrix": details["observation_jacobian"]})
    update["state_id"] = kernel_identity(update)
    estimate["state_id"] = contract.state_identity(source, 0, "update", predicted_id,
        estimate["mean"], estimate["covariance"], details)


@pytest.mark.parametrize("forgery", ["initial_predecessor", "error_prior", "dynamics_model", "observation_model", "observation_id"])
def test_coherent_inner_and_outer_rehashes_cannot_fork_declared_initial_lineage_or_model_ids(bundle, forgery):
    source = ekf_source()
    unrelated = "sha256:" + "0" * 64
    def mutate(retained):
        estimate = retained["estimates"][0]
        details = estimate["linearization"]
        prediction = details["kernel_prediction"]
        if forgery == "initial_predecessor":
            estimate["predecessor_state_id"] = unrelated
            prediction["replay"]["prior"]["state_id"] = digest({
                "schema": "ciw.sensor-fusion-ekf-error-prior.v1", "phase": "prediction-prior", "method": METHOD,
                "predecessor_state_id": unrelated, "batch_id": digest(source["batches"][0])})
            prediction["replay"]["dynamics"]["model_id"] = digest({
                "schema": "ciw.sensor-fusion-ekf-linearized-dynamics.v1", "predecessor_state_id": unrelated,
                "batch_id": digest(source["batches"][0]), "center": details["dynamics_center"],
                "model": source["batches"][0]["dynamics"]})
        elif forgery == "error_prior":
            prediction["replay"]["prior"]["state_id"] = unrelated
        elif forgery == "dynamics_model":
            prediction["replay"]["dynamics"]["model_id"] = unrelated
        rebind_linked_kernel_ids(source, estimate,
            update_model_id=unrelated if forgery == "observation_model" else None,
            observation_id=unrelated if forgery == "observation_id" else None)
    changed = change_data(bundle, mutate)
    # Every generic hash and numerical projection is valid after this reseal.
    with pytest.raises(ValueError):
        workflow.SensorFusionEKFWorkflow()._validate(changed)


@pytest.mark.parametrize("forgery", ["correction", "innovation", "residual"])
def test_rehashed_numeric_claims_still_bind_the_declared_operand_relations(bundle, forgery):
    source = ekf_source()
    def mutate(retained):
        estimate = retained["estimates"][0]
        if forgery == "correction":
            estimate["linearization"]["correction"] = [2.0]
            estimate["linearization"]["kernel_update"]["mean"] = [2.0]
        elif forgery == "innovation":
            estimate["diagnostics"]["innovation"] = [3.0]
            estimate["linearization"]["kernel_update"]["replay"]["observation"]["values"] = [3.0]
        else:
            estimate["diagnostics"]["residual"] = [0.0]
        rebind_linked_kernel_ids(source, estimate)
    with pytest.raises(ValueError):
        workflow.SensorFusionEKFWorkflow()._validate(change_data(bundle, mutate))


@pytest.mark.parametrize("forgery", ["prediction_f", "prediction_q", "observation_h", "observation_time"])
def test_rehashed_inner_replay_cannot_alias_numeric_one_to_a_boolean(bundle, forgery):
    source = ekf_source()
    def mutate(retained):
        estimate = retained["estimates"][0]
        details = estimate["linearization"]
        if forgery == "prediction_f":
            details["kernel_prediction"]["replay"]["dynamics"]["matrix"][0][0] = True
        elif forgery == "prediction_q":
            details["kernel_prediction"]["replay"]["dynamics"]["process_covariance"][0][0] = True
        elif forgery == "observation_h":
            details["kernel_update"]["replay"]["model"]["matrix"][0][0] = True
        else:
            details["kernel_update"]["replay"]["observation"]["time"] = True
        rebind_linked_kernel_ids(source, estimate)
    with pytest.raises(ValueError):
        workflow.SensorFusionEKFWorkflow()._validate(change_data(bundle, mutate))


def test_offline_integrity_remains_limited_and_live_replay_detects_coherent_forged_arithmetic(bundle, repositories):
    source = ekf_source()
    def mutate(retained):
        estimate = retained["estimates"][0]
        details = estimate["linearization"]
        # Retained claims form a consistent Gaussian subproblem, but f(0)=.5
        # contradicts the declared affine dynamics. Offline inspection does
        # not execute JSPT to independently establish that model evaluation.
        details.update(dynamics_value=[.5], predicted_mean=[.5], observation_value=[.5],
                       correction=[.75], post_observation_value=[1.25])
        details["kernel_update"]["mean"] = [.75]
        details["kernel_update"]["replay"]["observation"]["values"] = [1.5]
        estimate["mean"] = [1.25]
        estimate["diagnostics"].update(innovation=[1.5], residual=[.75], linearized_residual=[.75], nis=.225)
        rebind_linked_kernel_ids(source, estimate)
    changed = change_data(bundle, mutate)
    instrument = workflow.SensorFusionEKFWorkflow()
    instrument._validate(changed)
    with pytest.raises(AdapterRefusal) as caught:
        instrument.replay_session(changed, repositories)
    assert caught.value.code == "EKF_REPLAY_MISMATCH"


def test_fresh_reproduction_cannot_reuse_primary_execution(bundle):
    changed = deepcopy(bundle)
    changed["verification"] = workflow._verification(changed, changed["steps"][0])
    with pytest.raises(ValueError):
        workflow.SensorFusionEKFWorkflow()._validate(changed)


def test_source_configuration_binding_is_exact_despite_resealing(bundle):
    changed = deepcopy(bundle)
    changed["configuration"]["configurations"][0]["sensors"][0]["model"]["parameters"]["offset"][0] = 0.0
    changed["bundle_digest"] = _bundle_digest(changed)
    with pytest.raises(ValueError):
        workflow.SensorFusionEKFWorkflow()._validate(changed)


@pytest.mark.parametrize("role,key,value", [
    ("gsie", "revision", "0" * 40),
    ("gsie", "adapter_version", "ciw-pinned-subprocess-v1;sensor-fusion-ekf:unbound"),
    ("jspt", "revision", "0" * 40),
    ("jspt", "source_tree", "0" * 40),
    ("jspt", "module", "untrusted.eval"),
    ("jspt", "adapter_version", "ciw-pinned-subprocess-v1;unqualified"),
])
def test_both_retained_runtime_pins_are_required_even_with_fresh_content_digests(bundle, role, key, value):
    changed = deepcopy(bundle)
    runtime = changed["runtimes"]["gsie"]
    target = runtime if role == "gsie" else runtime["companions"]["jspt"]
    target[key] = value
    reseal(changed)
    with pytest.raises(ValueError):
        workflow.SensorFusionEKFWorkflow()._validate(changed)


def test_wrapper_drift_preserves_inspection_and_refuses_live_replay(bundle, repositories, monkeypatch):
    monkeypatch.setattr(workflow, "algorithm_identity", lambda: "0" * 64)
    workflow.SensorFusionEKFWorkflow()._validate(bundle)
    with pytest.raises(AdapterRefusal) as caught:
        workflow.SensorFusionEKFWorkflow().replay_session(bundle, repositories)
    assert caught.value.code == "RUNTIME_PIN_MISMATCH"


def test_unbound_and_incomplete_engine_bindings_are_unavailable(repositories, tmp_path):
    session = Session(make_demo_run(), tmp_path)
    source = add(session, ekf_source())
    entry, = [entry for entry in call(session, "operation.list")["operations"]
              if entry["operation_id"] == "ciw.sensor-fusion-ekf.v1"]
    assert entry["available"] is False
    call(session, "operation.execute", {"operation_id": "ciw.sensor-fusion-ekf.v1",
                                        "parameters": {"source_id": source["source_id"]}}, error=True)
    assert call(session, "bundle.list")["bundles"] == []
    for mapping in ({"gsie": repositories["gsie"]}, {"jspt": repositories["jspt"]}):
        with pytest.raises((ValueError, AdapterRefusal)):
            workflow.SensorFusionEKFWorkflow().create_session(canonical(ekf_source()), mapping)


def test_inspection_and_workspace_restore_do_not_execute_either_engine(repositories, tmp_path, monkeypatch):
    session = Session(make_demo_run(), tmp_path / "session")
    session.workbench.bind_workflow("sensor-fusion-ekf", repositories)
    raw = b"\n" + canonical(ekf_source()) + b"\n "
    source = add(session, raw)
    completed = call(session, "operation.execute", {"operation_id": "ciw.sensor-fusion-ekf.v1",
        "parameters": {"source_id": source["source_id"]}})
    replay = call(session, "bundle.replay", {"bundle_id": completed["bundle_id"]})
    path = session.save_workspace(tmp_path / "workspace.json")
    def forbidden(*args, **kwargs):
        raise AssertionError("Read-only nonlinear inspection reached an engine binding")
    monkeypatch.setattr(workflow.SensorFusionEKFWorkflow, "_adapters", forbidden)
    view = call(session, "experiment.inspect", {"bundle_id": completed["bundle_id"]})
    before = session.workbench.serialize()
    assert view["panels"][0]["values"] == [1.0]
    assert view["panels"][0]["covariance"] == [[2.5]]
    assert view["fusion_context"]["state_admission"] == "not_performed"
    restored = Session.from_workspace(path, tmp_path / "restored")
    assert call(restored, "experiment.inspect", {"bundle_id": completed["bundle_id"]}) == view
    assert base64.b64decode(call(restored, "source.get", {"source_id": source["source_id"]})["bytes_b64"]) == raw
    entry, = [entry for entry in call(restored, "operation.list")["operations"]
              if entry["operation_id"] == "ciw.sensor-fusion-ekf.v1"]
    assert entry["available"] is False
    view["panels"][0]["values"][0] = 900
    assert session.workbench.serialize() == before
    assert replay["bundle"]["bundle_id"] != completed["bundle_id"]


def test_engine_domain_refusal_retains_failed_attempt_without_result(repositories, tmp_path):
    source = range_source()
    source["prior"]["mean"] = [0, 0]
    session = Session(make_demo_run(), tmp_path)
    session.workbench.bind_workflow("sensor-fusion-ekf", repositories)
    descriptor = add(session, source)
    call(session, "operation.execute", {"operation_id": "ciw.sensor-fusion-ekf.v1",
        "parameters": {"source_id": descriptor["source_id"]}}, error=True)
    assert call(session, "bundle.list")["bundles"] == []
    failure, = session.workbench.list_failed_executions()
    assert failure["status"] == "refused"
    assert failure["result_id"] is None and failure["bundle_id"] is None
    assert failure["source_id"] == descriptor["source_id"]
    assert session.workbench.pending_operations == 0
    restored = Session.from_workspace(session.save_workspace(tmp_path / "refused.json"), tmp_path / "restored")
    assert restored.workbench.list_failed_executions() == [failure]


def test_cli_requires_both_engine_bindings_and_exposes_read_only_inspection():
    args = parser().parse_args(["sensor-fusion-ekf", "create", "--input", "source.json", "--gsie-repo", "/trusted/gsie",
                               "--jspt-repo", "/trusted/jspt", "--output", "new.json"])
    assert args.gsie_repo == Path("/trusted/gsie") and args.jspt_repo == Path("/trusted/jspt")
    inspect = parser().parse_args(["sensor-fusion-ekf", "inspect", "--input", "retained.json"])
    assert inspect.ekf_command == "inspect"
    startup = parser().parse_args(["serve", "--sensor-fusion-ekf-gsie-repo", "/trusted/gsie",
                                   "--sensor-fusion-ekf-jspt-repo", "/trusted/jspt"])
    assert startup.sensor_fusion_ekf_gsie_repo == Path("/trusted/gsie")
    assert startup.sensor_fusion_ekf_jspt_repo == Path("/trusted/jspt")
