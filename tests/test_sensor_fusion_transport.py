"""Coordinate continuation, retained provenance and refusal gates using real providers."""
import base64
from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pytest

from ciw import sensor_fusion_transport as transport
from ciw import sensor_fusion_transport_workflow as workflow
from ciw import sensor_fusion_workflow as fusion
from ciw.adapters.protocol import AdapterRefusal
from ciw.instruments import make_demo_run
from ciw.session import Session
from ciw.telemetry import _bundle_digest, byte_digest, canonical, digest
from scripts.monorepo import provider_worktrees

from test_sensor_fusion_contract import alter_record, encoded, record, scalar_source

ROOT = Path(__file__).resolve().parents[1]


def plane_source():
    source = scalar_source(joint=True)
    source["experiment_id"] = "analytic:correlated-plane"
    source["configuration"]["state"].update(quantity_ids=["axis-a", "axis-b"], units=["m", "m"])
    a, b = source["configuration"]["configurations"][0]["sensors"]
    a.update(matrix=[[1, .2]], model_ref="model:a-linear-mixture")
    b.update(matrix=[[.1, 1]], model_ref="model:b-linear-mixture")
    source["prior"].update(mean=[1, -.5], covariance=[[2, .3], [.3, 1]])
    batch = source["batches"][0]
    batch["dynamics"].update(matrix=[[1, 0], [0, 1]], process_covariance=[[.2, 0], [0, .2]])
    batch["observations"] = [record(a, 1, [1.4]), record(b, 1, [-.1])]
    batch["measurement_noise"]["matrix"] = [[.5, .1], [.1, .4]]
    return source


def continuation_source(upstream):
    original = plane_source()
    selected = upstream["steps"][0]["result"]["data"]["estimates"][-1]
    original["experiment_id"] = "analytic:original-basis-continuation"
    original["prior"] = {"time": selected["time"], "mean": selected["mean"], "covariance": selected["covariance"]}
    a, b = original["configuration"]["configurations"][0]["sensors"]
    batch = original["batches"][0]
    batch["time"] = 2
    batch["dynamics"] = {"matrix": [[.8, .4], [-.2, 1.1]],
                         "process_covariance": [[.4, .08], [.08, .3]], "model_ref": "model:coupled-plane"}
    batch["observations"] = [record(a, 2, [1.8]), record(b, 2, [.2])]
    missing = deepcopy(batch)
    missing.update(time=3, observations=[], measurement_noise=None)
    original["batches"].append(missing)
    return original


def transport_source(upstream, matrix=None, target=None):
    selected = upstream["steps"][0]["result"]["data"]["estimates"][-1]
    step = upstream["steps"][0]
    original = continuation_source(upstream)
    return {"schema": "ciw.sensor-fusion-transport-source.v1", "experiment_id": "analytic:transport-and-continue",
        "configuration": deepcopy(transport.POLICY),
        "selection": {"upstream_bundle_id": upstream["bundle_digest"], "upstream_result_id": step["result_id"],
            "upstream_execution_id": step["execution_id"], "upstream_numerical_result_id": step["numerical_result_id"],
            "state_id": selected["state_id"], "batch_index": selected["batch_index"]},
        "transport": {"matrix": matrix or [[1, 1], [0, 1]],
            "target_state": deepcopy(target or {**original["configuration"]["state"],
                "quantity_ids": ["mixed-a", "mixed-b"], "frame": "declared-mixed-basis"}),
            "map_evidence_b64": encoded(b"Caller declaration of an invertible coordinate map; no physical calibration claim")},
        "continuation": {"configuration": original["configuration"], "batches": original["batches"]}}


@pytest.fixture(scope="module")
def repositories():
    with provider_worktrees(ROOT, roles=["jspt", "gsie"]) as binding:
        yield binding


@pytest.fixture(scope="module")
def upstream(repositories):
    return fusion.SensorFusionWorkflow().create_session(canonical(plane_source()), {"gsie": repositories["gsie"]})


@pytest.fixture(scope="module")
def bundle(upstream, repositories):
    return workflow.SensorFusionTransportWorkflow().create_session(canonical(transport_source(upstream)), upstream, repositories)


def child(bundle):
    return bundle["steps"][0]["result"]["data"]["continuation"]


def estimates(bundle):
    return bundle["steps"][0]["result"]["data"]["estimates"]


def reseal_step(step):
    result = step["result"]
    result["result_id"] = digest({key: value for key, value in result.items() if key != "result_id"})
    step["result_id"] = result["result_id"]
    step["result_sha256"] = digest(result)
    step["numerical_result"] = workflow.numerical_projection(result["data"])
    step["numerical_result_id"] = digest(step["numerical_result"])


def reseal(bundle):
    for step in (bundle["steps"][0], bundle["verification"]["reproduction"]):
        reseal_step(step)
    bundle["bundle_digest"] = _bundle_digest(bundle)
    bundle["verification"] = workflow._verification(bundle, bundle["verification"]["reproduction"])
    return bundle


def call(session, kind, payload=None, *, error=False):
    response = session.handle({"protocol_version": 1, "request_id": "transport-test", "type": kind, "payload": payload or {}})
    assert response["type"] == ("error" if error else "response"), response
    return response["payload"]


def add(session, kind, source):
    raw = canonical(source) if isinstance(source, dict) else source
    return call(session, "source.add", {"kind": kind, "label": "Declared transport experiment", "bytes_b64": encoded(raw)})


def test_full_coordinate_transport_commutes_with_correlated_fusion_and_prediction(bundle, upstream, repositories):
    original = fusion.SensorFusionWorkflow().create_session(canonical(continuation_source(upstream)), {"gsie": repositories["gsie"]})
    transformed = child(bundle)
    chart = np.asarray([[1, 1], [0, 1]], dtype=float)
    for old, new in zip(estimates(original), estimates(transformed), strict=True):
        np.testing.assert_allclose(new["mean"], chart @ old["mean"], rtol=2e-13, atol=2e-13)
        np.testing.assert_allclose(new["covariance"], chart @ old["covariance"] @ chart.T, rtol=2e-13, atol=2e-13)
        np.testing.assert_allclose(new["diagnostics"]["innovation"], old["diagnostics"]["innovation"], atol=2e-13)
        if old["diagnostics"]["nis"] is not None:
            assert new["diagnostics"]["nis"] == pytest.approx(old["diagnostics"]["nis"], rel=2e-13)
    raw = base64.b64decode(transformed["source"]["evidence"][0]["bytes_b64"])
    declaration = json.loads(raw)
    source = continuation_source(upstream)
    np.testing.assert_allclose(declaration["batches"][0]["dynamics"]["matrix"], chart @ source["batches"][0]["dynamics"]["matrix"] @ np.linalg.inv(chart))
    np.testing.assert_allclose(declaration["batches"][0]["dynamics"]["process_covariance"], chart @ source["batches"][0]["dynamics"]["process_covariance"] @ chart.T)
    for old, new in zip(source["configuration"]["configurations"][0]["sensors"], declaration["configuration"]["configurations"][0]["sensors"], strict=True):
        np.testing.assert_allclose(new["matrix"], np.asarray(old["matrix"]) @ np.linalg.inv(chart))
    assert declaration["batches"][0]["observations"] == source["batches"][0]["observations"]
    assert declaration["batches"][0]["measurement_noise"] == source["batches"][0]["measurement_noise"]
    assert estimates(transformed)[-1]["diagnostics"]["status"] == "prediction_only"
    assert bundle["upstream_fusion"] == upstream
    assert bundle["verification"]["independent"] is False
    assert bundle["verification"]["authority"]["state_admission"] == "not_performed"


@pytest.mark.parametrize("chart,target_units", [([[0, 1], [1, 0]], ["m", "m"]),
    ([[1000, 0], [0, -.5]], ["mm", "m"]), ([[1, 0], [0, 1]], ["m", "m"])])
def test_permutation_scaling_orientation_and_identity_preserve_continuation(upstream, repositories, chart, target_units):
    source = transport_source(upstream, chart)
    source["transport"]["target_state"]["units"] = target_units
    result = workflow.SensorFusionTransportWorkflow().create_session(canonical(source), upstream, repositories)
    original = fusion.SensorFusionWorkflow().create_session(canonical(continuation_source(upstream)), {"gsie": repositories["gsie"]})
    matrix = np.asarray(chart)
    for old, new in zip(estimates(original), estimates(child(result)), strict=True):
        np.testing.assert_allclose(new["mean"], matrix @ old["mean"], rtol=2e-12, atol=2e-12)
        np.testing.assert_allclose(new["covariance"], matrix @ old["covariance"] @ matrix.T, rtol=2e-12, atol=2e-12)
    assert child(result)["configuration"]["state"]["units"] == target_units


def test_replay_preserves_projection_and_mints_all_nested_occurrences(bundle, repositories):
    replay = workflow.SensorFusionTransportWorkflow().replay_session(bundle, repositories)
    fresh = replay["session"]
    assert fresh["steps"][0]["numerical_result_id"] == bundle["steps"][0]["numerical_result_id"]
    assert fresh["session_id"] != bundle["session_id"]
    assert fresh["bundle_digest"] != bundle["bundle_digest"]
    assert fresh["upstream_fusion"] == bundle["upstream_fusion"]
    def occurrences(retained):
        values = set()
        for step in (retained["steps"][0], retained["verification"]["reproduction"]):
            values.update((step["execution_id"], step["result_id"]))
            nested = step["result"]["data"]["continuation"]
            values.add(nested["session_id"])
            for native in (nested["steps"][0], nested["verification"]["reproduction"]):
                values.update((native["execution_id"], native["result_id"]))
        return values
    assert occurrences(bundle).isdisjoint(occurrences(fresh))
    assert replay["replay_receipt"]["numerical_match"] is True
    assert workflow.SensorFusionTransportWorkflow()._validate(fresh) == canonical(transport_source(bundle["upstream_fusion"]))


@pytest.mark.parametrize("modify", [
    lambda s: s["selection"].update(upstream_result_id="sha256:" + "0" * 64),
    lambda s: s["selection"].update(upstream_execution_id="execution-" + "0" * 32),
    lambda s: s["selection"].update(upstream_numerical_result_id="sha256:" + "0" * 64),
    lambda s: s["selection"].update(state_id="sha256:" + "0" * 64),
    lambda s: s["selection"].update(batch_index=True),
    lambda s: s["selection"].update(batch_index=1),
    lambda s: s["transport"]["target_state"].update(clock_id="different-clock"),
    lambda s: s["transport"]["target_state"].update(geometry="so2_scalar_radians.v1"),
    lambda s: s["transport"]["target_state"].update(quantity_ids=["single"], units=["m"]),
    lambda s: s["continuation"]["configuration"]["state"].update(units=["cm", "m"]),
    lambda s: s["continuation"]["configuration"]["state"].update(clock_id="different-clock"),
    lambda s: s["continuation"]["batches"][0].update(time=1),
    lambda s: s["transport"].update(matrix=[[1, 0, 0], [0, 1, 0]]),
])
def test_exact_selection_state_contract_and_forward_clock_are_required(upstream, repositories, modify):
    source = transport_source(upstream)
    modify(source)
    with pytest.raises((ValueError, AdapterRefusal)):
        workflow.SensorFusionTransportWorkflow().create_session(canonical(source), upstream, repositories)


@pytest.mark.parametrize("matrix", [[[1, 0], [0, 0]], [[1, 0], [0, 1e-13]], [[1e200, 0], [0, 1e200]]])
def test_native_chart_domain_refuses_singular_ill_conditioned_and_overflow_maps(upstream, repositories, matrix):
    source = transport_source(upstream, matrix)
    with pytest.raises((ValueError, AdapterRefusal)):
        workflow.SensorFusionTransportWorkflow().create_session(canonical(source), upstream, repositories)


def test_transported_model_cannot_silently_erase_a_nonzero_transition_coefficient(upstream, repositories):
    source = transport_source(upstream, [[1e-6, 0], [0, 1e6]])
    source["continuation"]["batches"][0]["dynamics"]["matrix"] = [[1, 1e-312], [0, 1]]
    with pytest.raises((ValueError, AdapterRefusal)):
        workflow.SensorFusionTransportWorkflow().create_session(canonical(source), upstream, repositories)


def test_transported_observation_model_cannot_silently_underflow_to_zero(repositories):
    original = scalar_source()
    original["prior"]["covariance"] = [[1e-300]]
    original["batches"][0].update(observations=[], measurement_noise=None)
    original["batches"][0]["dynamics"]["process_covariance"] = [[0]]
    retained = fusion.SensorFusionWorkflow().create_session(canonical(original), {"gsie": repositories["gsie"]})
    source = transport_source(retained, [[1e150]])
    configuration = deepcopy(original["configuration"])
    configuration["configurations"][0]["sensors"][0]["matrix"] = [[1e-180]]
    source["transport"]["target_state"] = {**configuration["state"], "quantity_ids": ["scaled-position"]}
    source["continuation"] = {"configuration": configuration, "batches": [{"time": 2,
        "configuration_ref": "position", "dynamics": {"matrix": [[1]], "process_covariance": [[0]], "model_ref": "model:hold"},
        "observations": [], "measurement_noise": None}]}
    with pytest.raises((ValueError, AdapterRefusal)):
        workflow.SensorFusionTransportWorkflow().create_session(canonical(source), retained, repositories)


def test_finite_invertible_chart_refuses_transition_round_trip_cancellation(repositories):
    original = plane_source()
    original["prior"].update(mean=[1, 2], covariance=[[0, 0], [0, 0]])
    original["batches"][0].update(observations=[], measurement_noise=None)
    original["batches"][0]["dynamics"]["process_covariance"] = [[0, 0], [0, 0]]
    retained = fusion.SensorFusionWorkflow().create_session(canonical(original), {"gsie": repositories["gsie"]})
    source = transport_source(retained, [[1, 1], [1, 1 + 1e-6]])
    for batch in source["continuation"]["batches"]:
        batch.update(observations=[], measurement_noise=None)
        batch["dynamics"].update(matrix=[[.96, .03], [.04, .97]], process_covariance=[[0, 0], [0, 0]])
    with pytest.raises((ValueError, AdapterRefusal)):
        workflow.SensorFusionTransportWorkflow().create_session(canonical(source), retained, repositories)


def test_cross_session_acquisition_cannot_be_consumed_twice(upstream, repositories):
    source = transport_source(upstream)
    batch_source = {"batches": source["continuation"]["batches"]}
    alter_record(batch_source, lambda observation: observation.update(acquisition_id="a:1"))
    with pytest.raises((ValueError, AdapterRefusal)):
        workflow.SensorFusionTransportWorkflow().create_session(canonical(source), upstream, repositories)


def test_repeated_raw_reading_bytes_are_valid_for_distinct_acquisitions(upstream, repositories):
    source = transport_source(upstream)
    batch_source = {"batches": source["continuation"]["batches"]}
    alter_record(batch_source, lambda observation: observation.update(raw_evidence_b64=encoded(b"a:1")))
    result = workflow.SensorFusionTransportWorkflow().create_session(canonical(source), upstream, repositories)
    assert estimates(child(result))[0]["diagnostics"]["status"] == "updated"


def test_all_missing_measurements_still_transports_prediction_model(upstream, repositories):
    source = transport_source(upstream)
    for batch in source["continuation"]["batches"]:
        batch.update(observations=[], measurement_noise=None)
    transformed = workflow.SensorFusionTransportWorkflow().create_session(canonical(source), upstream, repositories)
    original_source = continuation_source(upstream)
    original_source["batches"] = source["continuation"]["batches"]
    original = fusion.SensorFusionWorkflow().create_session(canonical(original_source), {"gsie": repositories["gsie"]})
    matrix = np.asarray(source["transport"]["matrix"])
    for old, new in zip(estimates(original), estimates(child(transformed)), strict=True):
        assert new["diagnostics"]["status"] == "prediction_only"
        np.testing.assert_allclose(new["mean"], matrix @ old["mean"], rtol=2e-13, atol=2e-13)
        np.testing.assert_allclose(new["covariance"], matrix @ old["covariance"] @ matrix.T, rtol=2e-13, atol=2e-13)


def test_every_reconfigured_sensor_profile_is_transported(upstream, repositories):
    source = transport_source(upstream)
    configuration = source["continuation"]["configuration"]
    sensor = deepcopy(configuration["configurations"][0]["sensors"][1])
    sensor.update(matrix=[[.4, 2]], model_ref="model:b-rescaled-mixture")
    configuration["configurations"].append({"name": "scaled-b-only", "sensors": [sensor]})
    batch = source["continuation"]["batches"][1]
    batch.update(configuration_ref="scaled-b-only", observations=[record(sensor, 3, [.6])],
        measurement_noise={"channel_order": ["b/indication"], "matrix": [[.4]],
            "cross_sensor_policy": "declared_independent", "evidence_refs": configuration["noise_policy"]["evidence_refs"]})
    transformed = workflow.SensorFusionTransportWorkflow().create_session(canonical(source), upstream, repositories)
    original_source = continuation_source(upstream)
    original_source.update(configuration=configuration, batches=source["continuation"]["batches"])
    original = fusion.SensorFusionWorkflow().create_session(canonical(original_source), {"gsie": repositories["gsie"]})
    matrix = np.asarray(source["transport"]["matrix"])
    for old, new in zip(estimates(original), estimates(child(transformed)), strict=True):
        np.testing.assert_allclose(new["mean"], matrix @ old["mean"], rtol=2e-13, atol=2e-13)
        np.testing.assert_allclose(new["covariance"], matrix @ old["covariance"] @ matrix.T, rtol=2e-13, atol=2e-13)
    assert [entry["epoch_index"] for entry in estimates(child(transformed))] == [0, 1]


def test_historical_posterior_cannot_masquerade_as_latest_selected_state(upstream, repositories):
    original = plane_source()
    later = deepcopy(original["batches"][0])
    later.update(time=2, observations=[], measurement_noise=None)
    original["batches"].append(later)
    retained = fusion.SensorFusionWorkflow().create_session(canonical(original), {"gsie": repositories["gsie"]})
    source = transport_source(retained)
    first = estimates(retained)[0]
    source["selection"].update(batch_index=0, state_id=first["state_id"])
    for batch in source["continuation"]["batches"]:
        batch.update(time=batch["time"] + 2, observations=[], measurement_noise=None)
    with pytest.raises((ValueError, AdapterRefusal)):
        workflow.SensorFusionTransportWorkflow().create_session(canonical(source), retained, repositories)


def test_wrong_upstream_occurrence_refuses_even_when_numerical_outputs_match(upstream, repositories):
    fresh = fusion.SensorFusionWorkflow().replay_session(upstream, {"gsie": repositories["gsie"]})["session"]
    assert fresh["steps"][0]["numerical_result_id"] == upstream["steps"][0]["numerical_result_id"]
    with pytest.raises((ValueError, AdapterRefusal)):
        workflow.SensorFusionTransportWorkflow().create_session(canonical(transport_source(upstream)), fresh, repositories)


def test_wrapped_angle_posterior_requires_a_separate_transport_capability(repositories):
    original = scalar_source()
    original["configuration"]["state"].update(geometry="so2_scalar_radians.v1", units=["rad"])
    original["configuration"]["configurations"][0]["sensors"][0].update(units=["rad"])
    original["batches"][0].update(observations=[], measurement_noise=None)
    retained = fusion.SensorFusionWorkflow().create_session(canonical(original), {"gsie": repositories["gsie"]})
    source = transport_source(retained, [[1]])
    source["transport"]["target_state"] = {**original["configuration"]["state"], "geometry": "euclidean.v1"}
    later = deepcopy(original["batches"][0])
    later["time"] = 2
    source["continuation"] = {"configuration": original["configuration"], "batches": [later]}
    with pytest.raises((ValueError, AdapterRefusal)):
        workflow.SensorFusionTransportWorkflow().create_session(canonical(source), retained, repositories)


@pytest.mark.parametrize("modify", [
    lambda d: d["authority"].update(state_admission="admitted"),
    lambda d: d["selection"].update(state_id="sha256:" + "0" * 64),
    lambda d: d["transport"].update(map_id="sha256:" + "0" * 64),
    lambda d: d["transport"]["target_state"].update(clock_id="undeclared-clock"),
])
def test_outer_resealing_does_not_authorize_changed_selection_or_admission(bundle, modify):
    altered = deepcopy(bundle)
    for step in (altered["steps"][0], altered["verification"]["reproduction"]):
        modify(step["result"]["data"])
    with pytest.raises(ValueError):
        workflow.SensorFusionTransportWorkflow()._validate(reseal(altered))


def test_corrupted_nested_child_is_rejected_even_with_fresh_outer_commitments(bundle):
    altered = deepcopy(bundle)
    for step in (altered["steps"][0], altered["verification"]["reproduction"]):
        step["result"]["data"]["continuation"]["configuration"]["state"]["units"][0] = "unbound-unit"
    with pytest.raises(ValueError):
        workflow.SensorFusionTransportWorkflow()._validate(reseal(altered))


def test_valid_resealed_child_must_still_consume_exact_provider_source_bytes(bundle):
    altered = deepcopy(bundle)
    for parent in (altered["steps"][0], altered["verification"]["reproduction"]):
        nested = parent["result"]["data"]["continuation"]
        evidence = nested["source"]["evidence"][0]
        raw = b"\n" + base64.b64decode(evidence["bytes_b64"]) + b"\n"
        reference = byte_digest(raw)
        evidence.update(artifact_ref=reference, sha256=reference, bytes_b64=encoded(raw))
        for native in (nested["steps"][0], nested["verification"]["reproduction"]):
            native["input_refs"] = [reference]
            native["result"]["input_refs"] = [reference]
            result = native["result"]
            result["result_id"] = digest({key: value for key, value in result.items() if key != "result_id"})
            native["result_id"] = result["result_id"]
            native["result_sha256"] = digest(result)
        nested["bundle_digest"] = _bundle_digest(nested)
        nested["verification"] = fusion._verification(nested, nested["verification"]["reproduction"])
        # The child is content consistent in isolation; the exact source-byte
        # contract still differs from the JSPT provider's retained output.
        assert fusion.SensorFusionWorkflow()._validate(nested) == raw
    with pytest.raises(ValueError, match="exact transported"):
        workflow.SensorFusionTransportWorkflow()._validate(reseal(altered))


@pytest.mark.parametrize("role", ["jspt", "gsie"])
def test_coherently_resealed_runtime_cannot_select_an_unapproved_provider(bundle, role):
    altered = deepcopy(bundle)
    runtime = altered["runtimes"]["jspt"]
    if role == "gsie":
        runtime = runtime["companions"]["gsie"]
    runtime["revision"] = "0" * 40
    with pytest.raises(ValueError):
        workflow.SensorFusionTransportWorkflow()._validate(reseal(altered))


def test_resealed_parent_reproduction_cannot_reuse_the_primary_child_occurrence(bundle):
    altered = deepcopy(bundle)
    altered["verification"]["reproduction"]["result"]["data"]["continuation"] = deepcopy(child(altered))
    with pytest.raises(ValueError, match="distinct occurrences"):
        workflow.SensorFusionTransportWorkflow()._validate(reseal(altered))


def test_changed_wrapper_refuses_replay_but_preserves_offline_validation(bundle, repositories, monkeypatch):
    monkeypatch.setattr(workflow, "algorithm_identity", lambda: "0" * 64)
    current = workflow.SensorFusionTransportWorkflow()
    current._validate(bundle)
    with pytest.raises(AdapterRefusal) as caught:
        current.replay_session(bundle, repositories)
    assert caught.value.code == "RUNTIME_PIN_MISMATCH"


def test_transport_workbench_execute_inspect_save_restore_and_explicit_replay(repositories, tmp_path, monkeypatch):
    session = Session(make_demo_run(), tmp_path / "session")
    session.workbench.bind_workflow("sensor-fusion", {"gsie": repositories["gsie"]})
    session.workbench.bind_workflow("sensor-fusion-transport", repositories)
    original = add(session, "sensor-fusion", plane_source())
    completed = call(session, "operation.execute", {"operation_id": fusion.OPERATION, "parameters": {"source_id": original["source_id"]}})
    upstream = call(session, "bundle.get", {"bundle_id": completed["bundle_id"]})
    source_raw = b"\n" + canonical(transport_source(upstream)) + b"\n "
    source = add(session, "sensor-fusion-transport", source_raw)
    transported = call(session, "operation.execute", {"operation_id": transport.OPERATION,
        "parameters": {"source_id": source["source_id"], "upstream_bundle_id": completed["bundle_id"]}})
    replay = call(session, "bundle.replay", {"bundle_id": transported["bundle_id"]})
    assert replay["bundle"]["bundle_id"] != transported["bundle_id"]
    view = call(session, "experiment.inspect", {"bundle_id": transported["bundle_id"]})
    saved = session.save_workspace(tmp_path / "transported.json")
    def forbidden(*args, **kwargs):
        raise AssertionError("Inspection and restoration must not execute scientific providers")
    monkeypatch.setattr(workflow.SensorFusionTransportWorkflow, "_adapters", forbidden)
    restored = Session.from_workspace(saved, tmp_path / "restored")
    assert call(restored, "experiment.inspect", {"bundle_id": transported["bundle_id"]}) == view
    assert base64.b64decode(call(restored, "source.get", {"source_id": source["source_id"]})["bytes_b64"]) == source_raw
    operation, = [item for item in call(restored, "operation.list")["operations"] if item["operation_id"] == transport.OPERATION]
    assert operation["available"] is False


def test_native_transport_refusal_retains_failure_without_result_or_bundle(repositories, tmp_path):
    session = Session(make_demo_run(), tmp_path / "session")
    session.workbench.bind_workflow("sensor-fusion", {"gsie": repositories["gsie"]})
    session.workbench.bind_workflow("sensor-fusion-transport", repositories)
    original = add(session, "sensor-fusion", plane_source())
    completed = call(session, "operation.execute", {"operation_id": fusion.OPERATION, "parameters": {"source_id": original["source_id"]}})
    upstream = call(session, "bundle.get", {"bundle_id": completed["bundle_id"]})
    declaration = transport_source(upstream, [[1e-6, 0], [0, 1e6]])
    declaration["continuation"]["batches"][0]["dynamics"]["matrix"] = [[1, 1e-312], [0, 1]]
    source = add(session, "sensor-fusion-transport", declaration)
    call(session, "operation.execute", {"operation_id": transport.OPERATION,
        "parameters": {"source_id": source["source_id"], "upstream_bundle_id": completed["bundle_id"]}}, error=True)
    failures = session.workbench.list_failed_executions()
    failure, = failures
    assert failure["status"] == "refused"
    assert failure["failure"]["code"] == "FUSION_TRANSPORT_REFUSED"
    assert failure["source_id"] == source["source_id"]
    assert failure["result_id"] is None and failure["bundle_id"] is None
    assert session.workbench.pending_operations == 0
    assert len(call(session, "bundle.list")["bundles"]) == 1
    saved = session.save_workspace(tmp_path / "failure.json")
    assert Session.from_workspace(saved, tmp_path / "restored-failure").workbench.list_failed_executions() == failures
