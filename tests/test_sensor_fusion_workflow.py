"""Actual pinned GSIE execution, independent numerical oracles and retained boundaries."""
import base64
from copy import deepcopy
import math
from pathlib import Path

import numpy as np
import pytest

from ciw.adapters.protocol import AdapterRefusal
from ciw.cli import parser
from ciw.instruments import make_demo_run
from ciw.session import Session
from ciw import sensor_fusion_workflow as fusion
from ciw.telemetry import _bundle_digest, byte_digest, canonical, digest
from scripts.monorepo import provider_worktrees

from test_sensor_fusion_contract import alter_record, encoded, record, scalar_source

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def repositories():
    # The monorepo contains native upstream commits. The adapter requires a
    # detached original repository root, rather than accepting an import subtree.
    with provider_worktrees(ROOT, roles=["gsie"]) as binding:
        yield binding


@pytest.fixture(scope="module")
def bundle(repositories):
    return fusion.SensorFusionWorkflow().create_session(canonical(scalar_source()), repositories)


@pytest.fixture(scope="module")
def replayed(bundle, repositories):
    return fusion.SensorFusionWorkflow().replay_session(bundle, repositories)


def call(session, kind, payload=None, *, error=False):
    response = session.handle({"protocol_version": 1, "request_id": "fusion-test", "type": kind, "payload": payload or {}})
    assert response["type"] == ("error" if error else "response"), response
    return response["payload"]


def add(session, source):
    raw = canonical(source) if isinstance(source, dict) else source
    return call(session, "source.add", {"kind": "sensor-fusion", "label": "Declared fusion experiment",
                                       "bytes_b64": encoded(raw)})


def estimates(bundle):
    return bundle["steps"][0]["result"]["data"]["estimates"]


def reseal_step(step):
    result = step["result"]
    result["result_id"] = digest({k: v for k, v in result.items() if k != "result_id"})
    step["result_id"] = result["result_id"]
    step["result_sha256"] = digest(result)
    step["numerical_result"] = {"operation_id": fusion.OPERATION, "data": deepcopy(result["data"])}
    step["numerical_result_id"] = digest(step["numerical_result"])


def reseal_bundle(bundle):
    for step in (bundle["steps"][0], bundle["verification"]["reproduction"]):
        reseal_step(step)
    bundle["bundle_digest"] = _bundle_digest(bundle)
    bundle["verification"] = fusion._verification(bundle, bundle["verification"]["reproduction"])
    return bundle


def change_data(bundle, modify):
    altered = deepcopy(bundle)
    for step in (altered["steps"][0], altered["verification"]["reproduction"]):
        modify(step["result"]["data"])
    return reseal_bundle(altered)


def test_scalar_gaussian_posterior_and_diagnostics_match_closed_form(bundle):
    estimate, = estimates(bundle)
    # Prior variance4, independent process variance1 and observation variance5.
    assert estimate["mean"] == [1.0]
    assert estimate["covariance"] == [[2.5]]
    assert estimate["diagnostics"] == {"status": "updated", "innovation": [2.0],
        "innovation_covariance": [[10.0]], "residual": [1.0], "nis": .4}
    assert bundle["verification"]["outcome"] == "passed"
    assert bundle["verification"]["independent"] is False
    assert bundle["verification"]["authority"]["state_admission"] == "not_performed"
    assert bundle["verification"]["authority"]["physical_validation"] == "not_established"
    assert bundle["runtimes"]["gsie"]["revision"] == "5241eee6dab434533bdf0cf0e824bc43b4a79831"


def test_correlated_joint_fusion_does_not_claim_independent_sensor_precision(repositories):
    workflow = fusion.SensorFusionWorkflow()
    correlated = estimates(workflow.create_session(canonical(scalar_source(joint=True)), repositories))[0]
    independent_source = scalar_source(joint=True, correlation=0)
    independent_source["batches"][0]["measurement_noise"]["cross_sensor_policy"] = "declared_independent"
    independent = estimates(workflow.create_session(canonical(independent_source), repositories))[0]
    # For R=[[2,1],[1,2]], information1^T R^-1 1=2/3. Together
    # with prior precision1/4, posterior variance=12/11 and mean=16/11.
    assert correlated["covariance"][0][0] == pytest.approx(12 / 11)
    assert correlated["mean"][0] == pytest.approx(16 / 11)
    assert independent["covariance"][0][0] == pytest.approx(4 / 5)
    assert independent["mean"][0] == pytest.approx(8 / 5)
    assert correlated["covariance"][0][0] > independent["covariance"][0][0]
    np.testing.assert_allclose(correlated["diagnostics"]["innovation_covariance"], [[6, 5], [5, 6]])


def test_reconfiguration_preserves_state_and_covariance_then_prediction_only(repositories):
    source = scalar_source()
    sensor = deepcopy(source["configuration"]["configurations"][0]["sensors"][0])
    sensor.update(sensor_id="scaled", matrix=[[2]], model_ref="model:distance:twice")
    source["configuration"]["configurations"].append({"name": "scaled-position", "sensors": [sensor]})
    source["batches"].append({"time": 2, "configuration_ref": "scaled-position",
        "dynamics": {"matrix": [[1]], "process_covariance": [[.5]], "model_ref": "model:hold"},
        "observations": [record(sensor, 2, [4])], "measurement_noise": {
            "channel_order": ["scaled/indication"], "matrix": [[4]],
            "cross_sensor_policy": "declared_independent", "evidence_refs": source["configuration"]["noise_policy"]["evidence_refs"]}})
    source["batches"].append({"time": 3, "configuration_ref": "scaled-position",
        "dynamics": {"matrix": [[1]], "process_covariance": [[.25]], "model_ref": "model:hold"},
        "observations": [], "measurement_noise": None})
    result = fusion.SensorFusionWorkflow().create_session(canonical(source), repositories)
    first, changed, missing = estimates(result)
    assert first["mean"] == [1.0] and first["covariance"] == [[2.5]]
    assert changed["mean"][0] == pytest.approx(1.75)
    assert changed["covariance"][0][0] == pytest.approx(.75)
    assert missing["mean"] == changed["mean"]
    assert missing["covariance"][0][0] == pytest.approx(1)
    assert [e["epoch_index"] for e in estimates(result)] == [0, 1, 1]
    assert first["configuration_id"] != changed["configuration_id"] == missing["configuration_id"]
    assert changed["predecessor_state_id"] == first["state_id"]
    assert missing["predecessor_state_id"] == changed["state_id"]
    assert missing["predicted_state_id"] == missing["state_id"]
    assert missing["diagnostics"] == {"status": "prediction_only", "innovation": [],
        "innovation_covariance": [], "residual": [], "nis": None}


def test_so2_uses_local_wrapped_innovation_across_the_angle_chart_cut(repositories):
    source = scalar_source()
    source["configuration"]["state"].update(geometry="so2_scalar_radians.v1", units=["rad"])
    sensor = source["configuration"]["configurations"][0]["sensors"][0]
    sensor.update(units=["rad"], model_ref="model:angle:identity")
    source["prior"].update(mean=[math.pi - .05], covariance=[[.2]])
    source["batches"][0]["dynamics"]["process_covariance"] = [[0]]
    source["batches"][0]["observations"] = [record(sensor, 1, [-math.pi + .05])]
    source["batches"][0]["measurement_noise"]["matrix"] = [[.2]]
    estimate, = estimates(fusion.SensorFusionWorkflow().create_session(canonical(source), repositories))
    assert estimate["diagnostics"]["innovation"][0] == pytest.approx(.1)
    assert abs(abs(estimate["mean"][0]) - math.pi) < 1e-14
    assert -math.pi <= estimate["mean"][0] < math.pi
    assert estimate["covariance"][0][0] == pytest.approx(.1)


def test_replay_retains_numerical_identity_and_mints_fresh_occurrences(bundle, replayed):
    workflow = fusion.SensorFusionWorkflow()
    replay = replayed
    fresh = replay["session"]
    assert workflow._validate(fresh) == canonical(scalar_source())
    assert bundle["session_id"] != fresh["session_id"]
    assert bundle["bundle_digest"] != fresh["bundle_digest"]
    old, new = bundle["steps"][0], fresh["steps"][0]
    assert old["numerical_result_id"] == new["numerical_result_id"]
    assert old["execution_id"] != new["execution_id"]
    assert old["result_id"] != new["result_id"]
    assert bundle["verification"]["reproduction"]["execution_id"] != new["execution_id"]
    assert replay["replay_receipt"]["source_bundle_digest"] == bundle["bundle_digest"]
    assert replay["replay_receipt"]["numerical_match"] is True


@pytest.mark.parametrize("replacement", [{}, [], "not-content", "sha256:" + "0" * 63])
def test_resealed_replay_receipts_require_content_identity_for_original_bundle(replayed, replacement):
    changed = deepcopy(replayed["session"])
    receipt, = changed["replay_receipts"]
    receipt["source_bundle_digest"] = replacement
    verification = receipt["verification"]
    verification["subject_ref"] = deepcopy(replacement)
    verification["verification_id"] = byte_digest(verification["schema"].encode() + b"\0" +
        canonical({k: v for k, v in verification.items() if k != "verification_id"}))
    receipt["replay_id"] = digest({k: v for k, v in receipt.items() if k != "replay_id"})
    with pytest.raises(ValueError, match="receipt commitment"):
        fusion.SensorFusionWorkflow()._validate(changed)


def test_workbench_inspection_and_restore_are_read_only(repositories, tmp_path, monkeypatch):
    session = Session(make_demo_run(), tmp_path / "session")
    session.workbench.bind_workflow("sensor-fusion", repositories)
    raw = b"\n" + canonical(scalar_source()) + b"\n "
    source = add(session, raw)
    completed = call(session, "operation.execute", {"operation_id": fusion.OPERATION,
        "parameters": {"source_id": source["source_id"]}})
    bundle = call(session, "bundle.get", {"bundle_id": completed["bundle_id"]})
    replay = call(session, "bundle.replay", {"bundle_id": completed["bundle_id"]})
    path = session.save_workspace(tmp_path / "workspace.json")
    def forbidden(*args, **kwargs):
        raise AssertionError("Read-only retention must not execute the provider")
    monkeypatch.setattr(fusion.SensorFusionWorkflow, "_adapters", forbidden)
    before = session.workbench.serialize()
    view = call(session, "experiment.inspect", {"bundle_id": completed["bundle_id"]})
    assert view["panels"][0]["values"] == [1.0]
    assert view["panels"][0]["covariance"] == [[2.5]]
    assert view["object_context"]["state_admission"] == "not_performed"
    assert view["object_context"]["authority"]["physical_validation"] == "not_established"
    assert view["verification"] == bundle["verification"]
    restored = Session.from_workspace(path, tmp_path / "restored")
    assert call(restored, "experiment.inspect", {"bundle_id": completed["bundle_id"]}) == view
    assert base64.b64decode(call(restored, "source.get", {"source_id": source["source_id"]})["bytes_b64"]) == raw
    assert not next(o for o in call(restored, "operation.list")["operations"] if o["operation_id"] == fusion.OPERATION)["available"]
    view["panels"][0]["values"][0] = 900
    assert session.workbench.serialize() == before
    assert replay["bundle"]["bundle_id"] != completed["bundle_id"]


def test_unbound_runtime_is_unavailable_and_import_subtree_is_not_a_checkout(tmp_path):
    session = Session(make_demo_run(), tmp_path)
    source = add(session, scalar_source())
    entry, = [o for o in call(session, "operation.list")["operations"] if o["operation_id"] == fusion.OPERATION]
    assert entry["available"] is False
    call(session, "operation.execute", {"operation_id": fusion.OPERATION,
        "parameters": {"source_id": source["source_id"]}}, error=True)
    assert call(session, "bundle.list")["bundles"] == []
    with pytest.raises(AdapterRefusal):
        fusion.SensorFusionWorkflow().create_session(canonical(scalar_source()),
            {"gsie": ROOT / "instruments/inference/state-inference"})


def test_native_numerical_refusal_retains_an_attempt_without_result(repositories, tmp_path):
    source = scalar_source()
    source["prior"]["covariance"] = [[0]]
    source["batches"][0]["dynamics"]["process_covariance"] = [[0]]
    source["batches"][0]["measurement_noise"]["matrix"] = [[0]]
    session = Session(make_demo_run(), tmp_path)
    session.workbench.bind_workflow("sensor-fusion", repositories)
    descriptor = add(session, source)
    call(session, "operation.execute", {"operation_id": fusion.OPERATION,
        "parameters": {"source_id": descriptor["source_id"]}}, error=True)
    assert call(session, "bundle.list")["bundles"] == []
    failures = session.workbench.list_failed_executions()
    assert len(failures) == 1
    failure = failures[0]
    assert failure["status"] == "refused"
    assert failure["failure"]["code"] == "SENSOR_FUSION_REFUSED"
    assert failure["source_id"] == descriptor["source_id"]
    assert failure["result_id"] is None and failure["bundle_id"] is None
    assert session.workbench.pending_operations == 0
    saved = session.save_workspace(tmp_path / "failed.json")
    restored = Session.from_workspace(saved, tmp_path / "restored-failure")
    assert restored.workbench.list_failed_executions() == failures


@pytest.mark.parametrize("modify", [
    lambda d: d.update(authority={**d["authority"], "state_admission": "admitted"}),
    lambda d: d["state_contract"].update(units=["cm"]),
    lambda d: d["estimates"][0].update(configuration_id="sha256:" + "0" * 64),
    lambda d: d["estimates"][0].update(epoch_index=1),
    lambda d: d["estimates"][0].update(epoch_index=True),
    lambda d: d["estimates"][0].update(observation_refs=[]),
    lambda d: d["estimates"][0].update(observation_order=["a/different"]),
    lambda d: d["estimates"][0].update(predecessor_state_id="sha256:" + "0" * 64),
    lambda d: d["estimates"][0].update(predicted_state_id=d["initial_state_id"]),
    lambda d: d["estimates"][0].update(state_id=d["estimates"][0]["predicted_state_id"]),
    lambda d: d["estimates"][0]["diagnostics"].update(innovation_covariance=[[0]]),
    lambda d: d["estimates"][0]["diagnostics"].update(nis=-1),
])
def test_coherently_resealed_outputs_still_require_scientific_bindings(bundle, modify):
    altered = change_data(bundle, modify)
    with pytest.raises(ValueError):
        fusion.SensorFusionWorkflow()._validate(altered)


def test_source_configuration_cannot_change_even_if_outer_digest_is_resealed(bundle):
    changed = deepcopy(bundle)
    changed["configuration"]["configurations"][0]["sensors"][0]["matrix"][0][0] = 1.0
    changed["bundle_digest"] = _bundle_digest(changed)
    with pytest.raises(ValueError, match="configuration binding"):
        fusion.SensorFusionWorkflow()._validate(changed)


def test_fresh_reproduction_must_not_reuse_the_execution_occurrence(bundle):
    changed = deepcopy(bundle)
    changed["verification"] = fusion._verification(changed, changed["steps"][0])
    with pytest.raises(ValueError, match="fresh occurrences"):
        fusion.SensorFusionWorkflow()._validate(changed)


def test_numerical_projection_cannot_change_exact_json_number_types(bundle):
    changed = deepcopy(bundle)
    for step in (changed["steps"][0], changed["verification"]["reproduction"]):
        assert type(step["result"]["data"]["estimates"][0]["mean"][0]) is float
        step["numerical_result"]["data"]["estimates"][0]["mean"][0] = 1
        step["numerical_result_id"] = digest(step["numerical_result"])
    changed["bundle_digest"] = _bundle_digest(changed)
    changed["verification"] = fusion._verification(changed, changed["verification"]["reproduction"])
    with pytest.raises(ValueError, match="binding"):
        fusion.SensorFusionWorkflow()._validate(changed)


def test_offline_integrity_has_limited_authority_and_replay_detects_forged_numbers(bundle, repositories):
    changed = change_data(bundle, lambda d: d["estimates"][0].update(mean=[2.0]))
    workflow = fusion.SensorFusionWorkflow()
    # Content validation binds retained scientific domains and relationships;
    # it cannot independently recompute the scientific provider's arithmetic.
    workflow._validate(changed)
    with pytest.raises(AdapterRefusal) as caught:
        workflow.replay_session(changed, repositories)
    assert caught.value.code == "FUSION_REPLAY_MISMATCH"


def test_current_wrapper_drift_refuses_replay_but_preserves_offline_inspection(bundle, repositories, monkeypatch):
    monkeypatch.setattr(fusion, "algorithm_identity", lambda: "0" * 64)
    workflow = fusion.SensorFusionWorkflow()
    workflow._validate(bundle)
    with pytest.raises(AdapterRefusal) as caught:
        workflow.replay_session(bundle, repositories)
    assert caught.value.code == "RUNTIME_PIN_MISMATCH"


def test_invalid_source_refuses_before_any_executable_binding(monkeypatch):
    source = scalar_source()
    alter_record(source, lambda r: r.update(clock_id="undeclared-clock"))
    def forbidden(*a, **k):
        raise AssertionError("Invalid declaration reached a provider binding")
    monkeypatch.setattr(fusion.SensorFusionWorkflow, "_adapters", forbidden)
    with pytest.raises(ValueError):
        fusion.SensorFusionWorkflow().create_session(canonical(source), {})


def test_cli_exposes_binding_and_separate_read_only_inspection():
    args = parser().parse_args(["sensor-fusion", "create", "--input", "input.json",
                               "--gsie-repo", "/trusted/gsie", "--output", "new.json"])
    assert args.gsie_repo == Path("/trusted/gsie") and args.output == Path("new.json")
    inspect = parser().parse_args(["sensor-fusion", "inspect", "--input", "retained.json"])
    assert inspect.fusion_command == "inspect"
    startup = parser().parse_args(["serve", "--sensor-fusion-gsie-repo", "/trusted/gsie"])
    assert startup.sensor_fusion_gsie_repo == Path("/trusted/gsie")
