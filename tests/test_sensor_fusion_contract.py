"""Refusal boundaries for declarative fusion, before a native engine is bound."""
import base64
from copy import deepcopy
import json

import pytest

from ciw.adapters.protocol import AdapterRefusal
from ciw import sensor_fusion_contract as contract
from ciw.telemetry import byte_digest, canonical


def encoded(raw):
    return base64.b64encode(raw).decode()


def record(sensor, time, values, *, raw=None, clock="experiment-clock"):
    observation = {"schema": "ciw.fusion-observation.v1", "sensor_id": sensor["sensor_id"],
        "acquisition_id": sensor["sensor_id"] + ":" + str(time),
        "time": time, "clock_id": clock, "quantity_ids": deepcopy(sensor["quantity_ids"]),
        "units": deepcopy(sensor["units"]), "frame": sensor["frame"], "values": values,
        "calibration_ref": byte_digest(base64.b64decode(sensor["calibration"]["artifact_b64"])),
        "raw_evidence_b64": encoded(raw or (sensor["sensor_id"] + ":" + str(time)).encode())}
    return {"sensor_id": sensor["sensor_id"], "record_b64": encoded(canonical(observation))}


def scalar_source(*, joint=False, correlation=1):
    sensors = [{"sensor_id": name, "quantity_ids": ["indication"], "units": ["m"],
        "frame": "laboratory", "matrix": [[1]], "model_ref": "model:distance:identity",
        "calibration": {"artifact_b64": encoded(("calibration:" + name).encode()),
                        "valid_interval": [0, 10], "claim_scope": "caller_declared_not_verified"}}
        for name in (["a", "b"] if joint else ["a"])]
    return {"schema": contract.SOURCE_SCHEMA, "experiment_id": "analytic-scalar",
        "configuration": {
            "state": {"quantity_ids": ["position"], "units": ["m"], "frame": "laboratory",
                      "geometry": "euclidean.v1", "clock_id": "experiment-clock"},
            "configurations": [{"name": "position", "sensors": sensors}],
            "noise_policy": {"prior_measurement_crosscovariance": "declared_zero",
                "process_measurement_crosscovariance": "declared_zero",
                "process_prior_crosscovariance": "declared_zero",
                "across_batches": "declared_independent",
                "evidence_refs": [byte_digest(b"noise declaration")] }},
        "prior": {"time": 0, "mean": [0], "covariance": [[4]]},
        "batches": [{"time": 1, "configuration_ref": "position",
            "dynamics": {"matrix": [[1]], "process_covariance": [[0 if joint else 1]],
                         "model_ref": "model:stationary"},
            "observations": [record(sensor, 1, [2]) for sensor in sensors],
            "measurement_noise": {"channel_order": [sensor["sensor_id"] + "/indication" for sensor in sensors],
                "matrix": [[2, correlation], [correlation, 2]] if joint else [[5]],
                "cross_sensor_policy": "full_joint_declared" if joint else "declared_independent",
                "evidence_refs": [byte_digest(b"measurement noise declaration")] }}]}


def alter_record(source, modify, *, batch=0, index=0):
    observation = source["batches"][batch]["observations"][index]
    retained = json.loads(base64.b64decode(observation["record_b64"]))
    modify(retained)
    observation["record_b64"] = encoded(canonical(retained))


def test_retained_bytes_define_exact_observation_and_calibration_lineage():
    source = scalar_source(joint=True)
    raw = b"\n" + canonical(source) + b"\n "
    assert contract.validate_source(raw) == source
    inputs = contract.batch_inputs(source, 0)
    assert inputs["matrix"] == [[1], [1]]
    assert inputs["order"] == ["a/indication", "b/indication"]
    assert inputs["values"] == [2, 2]
    expected = []
    for observation, sensor in zip(source["batches"][0]["observations"], source["configuration"]["configurations"][0]["sensors"]):
        observation_raw = base64.b64decode(observation["record_b64"])
        expected.extend([byte_digest(observation_raw),
            byte_digest(base64.b64decode(json.loads(observation_raw)["raw_evidence_b64"])),
            byte_digest(base64.b64decode(sensor["calibration"]["artifact_b64"]))])
    assert inputs["evidence_refs"] == expected


@pytest.mark.parametrize("modify", [
    lambda s: s["prior"].update(mean=[True]),
    lambda s: s["prior"].update(mean=[2**54 + 1]),
    lambda s: s["prior"].update(mean=["2"]),
    lambda s: s["prior"].update(covariance=[[-1]]),
    lambda s: s["configuration"]["state"].update(geometry="se3_unqualified.v1"),
    lambda s: s["configuration"]["state"].update(quantity_ids=["position", "position"], units=["m", "m"]),
    lambda s: s["configuration"]["noise_policy"].update(prior_measurement_crosscovariance="unknown"),
    lambda s: s["configuration"]["noise_policy"].update(process_measurement_crosscovariance="unknown"),
    lambda s: s["configuration"]["noise_policy"].update(process_prior_crosscovariance="unknown"),
    lambda s: s["configuration"]["noise_policy"].update(across_batches="unknown"),
    lambda s: s["configuration"]["noise_policy"].update(evidence_refs=[]),
    lambda s: s["batches"][0].update(time=0),
    lambda s: s["batches"][0].update(configuration_ref="missing"),
    lambda s: s["batches"][0]["dynamics"].update(matrix=[[1, 0]]),
    lambda s: s["batches"][0]["measurement_noise"].update(cross_sensor_policy="unknown"),
    lambda s: s["batches"][0]["measurement_noise"].update(cross_sensor_policy=[]),
    lambda s: s["batches"][0]["measurement_noise"].update(channel_order=["a/other"]),
    lambda s: s["batches"][0]["measurement_noise"].update(matrix=[[-1]]),
    lambda s: s["batches"][0]["measurement_noise"].update(evidence_refs=[]),
    lambda s: s["batches"][0]["observations"].append(deepcopy(s["batches"][0]["observations"][0])),
    lambda s: s["configuration"]["configurations"].append(deepcopy(s["configuration"]["configurations"][0])),
    lambda s: s["configuration"]["configurations"][0]["sensors"].append(deepcopy(s["configuration"]["configurations"][0]["sensors"][0])),
    lambda s: s["configuration"].update(executable="untrusted.module"),
])
def test_undeclared_scientific_inputs_refuse(modify):
    source = scalar_source()
    modify(source)
    with pytest.raises(ValueError):
        contract.validate_source(canonical(source))


@pytest.mark.parametrize("modify", [
    lambda r: r.update(units=["cm"]),
    lambda r: r.update(frame="other-laboratory"),
    lambda r: r.update(clock_id="device-clock"),
    lambda r: r.update(time=1.00001),
    lambda r: r.update(quantity_ids=["velocity"]),
    lambda r: r.update(sensor_id="other"),
    lambda r: r.update(calibration_ref=byte_digest(b"other calibration")),
    lambda r: r.update(values=[False]),
    lambda r: r.update(raw_evidence_b64=""),
])
def test_observation_must_match_the_declared_adapter(modify):
    source = scalar_source()
    alter_record(source, modify)
    with pytest.raises(ValueError):
        contract.validate_source(canonical(source))


def test_identical_raw_values_from_distinct_acquisitions_are_retained():
    source = scalar_source(joint=True)
    first = json.loads(base64.b64decode(source["batches"][0]["observations"][0]["record_b64"]))
    alter_record(source, lambda r: r.update(raw_evidence_b64=first["raw_evidence_b64"]), index=1)
    contract.validate_source(canonical(source))
    inputs = contract.batch_inputs(source, 0)
    assert inputs["order"] == ["a/indication", "b/indication"]
    assert len(inputs["records"]) == 2


def test_same_acquisition_cannot_be_retimed_in_a_later_batch():
    source = scalar_source()
    source["batches"].append(deepcopy(source["batches"][0]))
    source["batches"][1]["time"] = 2
    alter_record(source, lambda r: r.update(time=2), batch=1)
    with pytest.raises(ValueError, match="acquisition"):
        contract.validate_source(canonical(source))


def test_same_acquisition_cannot_be_renamed_as_a_second_sensor():
    source = scalar_source(joint=True)
    alter_record(source, lambda r: r.update(acquisition_id="a:1"), index=1)
    with pytest.raises(ValueError, match="acquisition"):
        contract.validate_source(canonical(source))


def test_off_diagonal_correlation_requires_a_full_joint_declaration():
    source = scalar_source(joint=True)
    source["batches"][0]["measurement_noise"]["cross_sensor_policy"] = "declared_independent"
    with pytest.raises(ValueError, match="zero cross blocks"):
        contract.validate_source(canonical(source))


@pytest.mark.parametrize("matrix", [[[1, 2], [2, 1]], [[2, 1], [0, 2]], [[0, 1e-300], [1e-300, 2]]])
def test_covariance_is_not_repaired_or_diagonalized(matrix):
    source = scalar_source(joint=True)
    source["batches"][0]["measurement_noise"]["matrix"] = matrix
    retained = deepcopy(source)
    with pytest.raises(ValueError):
        contract.validate_source(canonical(source))
    assert source == retained


@pytest.mark.parametrize("interval", [[1, 2], [0, 1], [2, 1]])
def test_calibration_interval_is_half_open_and_ordered(interval):
    source = scalar_source()
    source["configuration"]["configurations"][0]["sensors"][0]["calibration"]["valid_interval"] = interval
    if interval == [1, 2]:
        contract.validate_source(canonical(source))
    else:
        with pytest.raises(ValueError):
            contract.validate_source(canonical(source))


def test_prediction_only_declares_absence_of_measurement_covariance():
    source = scalar_source()
    source["batches"][0]["observations"] = []
    source["batches"][0]["measurement_noise"] = None
    contract.validate_source(canonical(source))
    source["batches"][0]["measurement_noise"] = {"matrix": [[0]]}
    with pytest.raises(ValueError, match="Prediction-only"):
        contract.validate_source(canonical(source))


def test_duplicate_json_keys_inside_retained_observation_refuse():
    source = scalar_source()
    observation = source["batches"][0]["observations"][0]
    raw = base64.b64decode(observation["record_b64"])
    observation["record_b64"] = encoded(raw[:-1] + b',"values":[999]}')
    with pytest.raises(AdapterRefusal) as caught:
        contract.validate_source(canonical(source))
    assert caught.value.code == "MALFORMED_RESPONSE"


@pytest.mark.parametrize("raw", [b'{"schema":"a","schema":"b"}', b'{"schema":NaN}', b"{", b"[]"])
def test_strict_json_refuses_ambiguous_or_malformed_sources(raw):
    with pytest.raises((ValueError, AdapterRefusal)):
        contract.validate_source(raw)


def test_source_budget_and_exact_byte_type():
    with pytest.raises(ValueError):
        contract.validate_source("{}")
    with pytest.raises(ValueError):
        contract.validate_source(b" " * (contract.SOURCE_LIMIT + 1))


def test_sensor_maps_cannot_claim_an_unimplemented_angle_geometry():
    source = scalar_source()
    source["configuration"]["state"].update(geometry="so2_scalar_radians.v1", units=["rad"])
    sensor = source["configuration"]["configurations"][0]["sensors"][0]
    sensor.update(units=["rad"], matrix=[[2]])
    alter_record(source, lambda r: r.update(units=["rad"]))
    with pytest.raises(ValueError, match="identity H"):
        contract.validate_source(canonical(source))
