"""New controller with a real synthetic Python provider, not native-engine qualification."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import threading
from unittest.mock import patch

import pytest

from ciw.adapters.protocol import AdapterRefusal
from ciw.control_checks import compare, validate_comparison
from ciw.control_contracts import load
from ciw.instruments import make_demo_run
from ciw.operations.runner import seal
from ciw.session import Session
from ciw.simulation_cli import demo, inspect_workspace, main
from ciw.simulation_control import SimulationControl, completed, open_workspace
from ciw.simulation_records import (MAX_SNAPSHOT, OPERATION, decode_snapshot, encode_snapshot,
    observer, projected_samples, validate_event, validate_instance, validate_observer, validate_request)
from ciw.simulation_reference import PROVIDER_ID, ReferenceMotion
from ciw.simulation_replay import replay, validate_replay, validate_result, validate_source


@pytest.fixture
def lab(tmp_path):
    session = Session(make_demo_run(), tmp_path / "session")
    control = SimulationControl(session)
    provider = ReferenceMotion()
    instance = control.attach(provider, provider_id=PROVIDER_ID, experiment_id="baseline")
    return session, control, provider, instance


def ok(instance, action, **arguments):
    return completed(instance.command(action, **arguments))


def checkpoint_case(instance):
    ok(instance, "start")
    ok(instance, "step", dt=1)
    ok(instance, "intervene", actor_id="tester", operation="motion.queue-impulse.v1", target="body-1",
       parameters={"at_tick": 3, "delta_v": 4})
    ok(instance, "pause")
    cp = ok(instance, "checkpoint")
    suffix = [ok(instance, "resume"), ok(instance, "step", dt=1), ok(instance, "step", dt=1),
              ok(instance, "observe", observer=observer("debug", kind="debugger", channels=["position", "velocity"])),
              ok(instance, "pause")]
    return cp, suffix


def test_lifecycle_metadata_and_single_provider_owner(lab):
    session, _, provider, instance = lab
    initial = instance.inspect()
    assert initial["status"] == "created"
    for action in ["start", "pause", "resume", "stop"]:
        result = ok(instance, action)
        validate_result(result)
        assert result["verification_status"] == "not_verified"
        assert instance.inspect()["state_ref"] == initial["state_ref"]
        assert provider.identity() == initial["provider"]
    assert len(session.executions) == 4
    assert instance.inspect()["revision"] == 4
    assert instance.inspect()["instance_id"] != instance.inspect()["experiment_id"]
    validate_instance(instance.inspect())


@pytest.mark.parametrize("action", ["step", "resume", "pause", "intervene"])
def test_invalid_lifecycle_retained_without_touching_provider(lab, action):
    session, _, provider, instance = lab
    args = {"dt": 1} if action == "step" else ({"actor_id": "x", "operation": "motion.queue-impulse.v1",
        "target": "body-1", "parameters": {"at_tick": 1, "delta_v": 2}} if action == "intervene" else {})
    before = instance.inspect()
    with patch.object(provider, "snapshot", side_effect=AssertionError("must not touch")):
        response = instance.command(action, **args)
    assert response["payload"]["execution"]["refusal"]["code"] == "simulation_lifecycle"
    assert response["payload"]["result"] is None and instance.inspect() == before
    assert len(session.executions) == 1


@pytest.mark.parametrize("dt", [0, -1, True, float("nan"), float("inf"), "1", 3601])
def test_malformed_steps_rejected_before_execution(lab, dt):
    session, _, _, instance = lab
    with pytest.raises((ValueError, TypeError)):
        instance.command("step", dt=dt)
    assert len(session.executions) == 0


def test_retry_once_and_changed_id_cannot_poison_healthy_instance(lab):
    session, control, _, instance = lab
    request = instance.request("start", command_id="start-once")
    first = control.submit(request)
    assert control.submit(deepcopy(request)) == first
    assert len(session.executions) == 1
    changed = instance.request("pause", command_id="start-once")
    before = instance.inspect()
    with pytest.raises(AdapterRefusal, match="different data"):
        control.submit(changed)
    assert instance.inspect() == before
    assert ok(instance, "step", dt=1)["data"]["after"]["provider"]["clock"]["time_s"] == 1


@pytest.mark.parametrize("key,value", [("owner_id", "wrong-owner"), ("revision", 12), ("state_revision", 9)])
def test_fencing_refusal_is_retained_and_does_not_quarantine(lab, key, value):
    session, control, provider, instance = lab
    request = instance.request("start")
    request["expected"][key] = value
    response = control.submit(request)
    assert response["payload"]["execution"]["refusal"]["code"] == "stale_simulation_command"
    assert provider.status == "created" and instance.inspect()["status"] == "created"
    assert len(session.executions) == 1


def test_direct_session_operation_cannot_bypass_dispatch_gate(lab):
    session, _, provider, instance = lab
    result = session.handle({"protocol_version": 1, "request_id": "bypass", "type": "operation.execute",
        "payload": {"operation_id": OPERATION, "parameters": instance.request("start")}})
    assert result["payload"]["execution"]["refusal"]["code"] == "simulation_dispatch_only"
    assert provider.status == "created"


def test_inputs_results_and_metadata_are_detached(lab):
    _, control, provider, instance = lab
    request = instance.request("start")
    result = control.submit(request)
    request["expected"]["owner_id"] = "tampered"
    result["payload"]["result"]["data"]["after"]["status"] = "refused"
    view = instance.inspect()
    view["provider"]["runtime"]["provider"] = "tampered"
    assert instance.inspect()["status"] == "running"
    assert provider.identity()["runtime"]["provider"] == PROVIDER_ID


def test_concurrent_command_and_retry_cannot_execute_twice(lab):
    session, control, provider, instance = lab
    entered, release = threading.Event(), threading.Event()
    original = provider.lifecycle
    def block(action):
        entered.set()
        assert release.wait(timeout=10)
        original(action)
    request = instance.request("start")
    with patch.object(provider, "lifecycle", block), ThreadPoolExecutor(2) as pool:
        future = pool.submit(control.submit, request)
        assert entered.wait(timeout=10)
        try:
            with pytest.raises(AdapterRefusal, match="in flight"):
                control.submit(request)
        finally:
            release.set()
        first = future.result(timeout=10)
    assert control.submit(request) == first and len(session.executions) == 1


@pytest.mark.parametrize("failure", ["exception", "time", "state", "configuration", "observation"])
def test_provider_failures_quarantine_without_rollback_claim(lab, failure):
    session, _, provider, instance = lab
    ok(instance, "start")
    if failure == "exception":
        original = provider.step
        def broken(dt):
            original(dt)
            raise RuntimeError("intentional failure after mutation")
        target, replacement = "step", broken
    elif failure == "time":
        target, replacement = "step", lambda dt: None
    elif failure == "state":
        provider._state["velocity"] = 100
        target, replacement = "step", lambda dt: None
    elif failure == "configuration":
        provider._config["seed"] = 11
        target, replacement = "step", lambda dt: None
    else:
        target, replacement = "observe_for", lambda observer: {"hidden_world": provider._state}
    with patch.object(provider, target, replacement):
        response = instance.command("observe", observer=observer("p", kind="sensor", channels=["position"])) if failure == "observation" else instance.command("step", dt=1)
    assert response["payload"]["status"] == "refused" and response["payload"]["result"] is None
    assert instance.inspect()["status"] == "refused"
    assert instance.inspect()["state_status"] == "unknown_after_failure"
    assert instance.command("step", dt=1)["payload"]["execution"]["refusal"]["code"] == "simulation_lifecycle"
    instance.discard()
    assert provider.status == "stopped"


def test_publication_failure_quarantines_mutated_owner(lab):
    _, _, provider, instance = lab
    ok(instance, "start")
    with patch("ciw.session.write_json", side_effect=OSError("disk unavailable")):
        response = instance.command("step", dt=1)
    assert response["type"] == "error"
    assert provider.identity()["clock"]["time_s"] == 1
    assert instance.inspect()["state_status"] == "unknown_after_failure"


def test_provider_and_owner_cannot_be_attached_twice(lab):
    _, control, provider, _ = lab
    with pytest.raises(ValueError, match="already attached"):
        control.attach(provider, provider_id=PROVIDER_ID, experiment_id="other")
    with pytest.raises(ValueError, match="already used"):
        control.attach(ReferenceMotion(owner_id=provider.owner_id), provider_id=PROVIDER_ID, experiment_id="other")


def test_existing_session_operation_and_workbench_unchanged(lab):
    session, _, provider, instance = lab
    initial_run = deepcopy(session.run)
    original_workbench = session.workbench
    first = session.handle({"protocol_version": 1, "request_id": "stat-a", "type": "operation.execute",
        "payload": {"operation_id": "statistics.v1", "parameters": {}}})
    ok(instance, "start")
    ok(instance, "step", dt=1)
    before = provider.snapshot()
    second = session.handle({"protocol_version": 1, "request_id": "stat-b", "type": "operation.execute",
        "payload": {"operation_id": "statistics.v1", "parameters": {}}})
    assert completed(first)["data"] == completed(second)["data"]
    assert first["payload"]["result"]["execution_id"] != second["payload"]["result"]["execution_id"]
    assert provider.snapshot() == before and session.run == initial_run and session.workbench is original_workbench


def test_delayed_observations_separate_from_checkpoint_truth(lab):
    _, _, provider, instance = lab
    ok(instance, "start")
    early = ok(instance, "observe", observer=observer("player", kind="embodied_agent", channels=["position"]))
    assert early["data"]["observations"]["samples"] == []
    for _ in range(4):
        ok(instance, "step", dt=1)
    before = provider.snapshot()
    player = ok(instance, "observe", observer=observer("player", kind="embodied_agent", channels=["position"]))
    debug = ok(instance, "observe", observer=observer("debug", kind="debugger", channels=["position", "velocity"]))
    narrator = ok(instance, "observe", observer=observer("narrator", kind="retrospective_narrator", channels=["position"]))
    assert player["data"]["observations"]["samples"][-1]["clock"]["time_s"] == 2
    assert debug["data"]["observations"]["samples"][-1]["clock"]["time_s"] == 4
    assert narrator["data"]["observations"]["observer"]["player_knowledge_transfer"] is False
    assert all(x["quantity"] == "position" for x in player["data"]["observations"]["samples"])
    assert player["data"]["snapshot_b64"] is None and player["data"]["checkpoint"] is None
    assert provider.snapshot() == before


def test_observer_disallowed_channel_refuses(lab):
    _, _, _, instance = lab
    response = instance.command("observe", observer=observer("player", kind="embodied_agent", channels=["velocity"]))
    assert response["payload"]["status"] == "refused"
    assert "hidden velocity" in response["payload"]["execution"]["refusal"]["message"]


def test_sample_projection_preserves_original_execution_and_quantities(lab):
    _, _, _, instance = lab
    original = ok(instance, "observe", observer=observer("debug", kind="debugger", channels=["position", "velocity"]))
    before = deepcopy(original)
    result = projected_samples(original, quantity="position")
    assert len(result) == 1 and result[0]["identity"]["execution_id"] == original["execution_id"]
    assert result[0]["quantity"] == "position" and result[0]["unit"] == "m"
    assert original == before and original["data"]["observations"]["samples"][0]["identity"]["execution_id"] is None


@pytest.mark.parametrize("field,value", [("kind", "god-mode"), ("channels", []), ("channels", ["x", "x"]),
    ("player_knowledge_transfer", 1), ("policy", None)])
def test_resealed_observer_contract_corruption(field, value):
    record = observer("p", kind="sensor", channels=["position"])
    record[field] = value
    seal(record)
    with pytest.raises((ValueError, TypeError)):
        validate_observer(record)


def test_branch_isolation_rng_and_queue_continuation(lab):
    _, control, provider, instance = lab
    cp, suffix = checkpoint_case(instance)
    before = provider.snapshot()
    original_view = instance.inspect()
    child, report = replay(control, cp, suffix, ReferenceMotion(), experiment_id="replay")
    validate_replay(report)
    assert report["outcome"]["status"] == "PASS"
    assert child.instance_id != instance.instance_id
    assert child.inspect()["provider"]["owner_id"] != instance.inspect()["provider"]["owner_id"]
    assert child.inspect()["state_ref"] == instance.inspect()["state_ref"]
    assert instance.inspect() == original_view and provider.snapshot() == before
    assert child.inspect()["parent"]["checkpoint_ref"] == cp["data"]["checkpoint"]["record_digest"]


def test_real_bad_replay_detects_divergence(lab):
    _, control, _, instance = lab
    cp, suffix = checkpoint_case(instance)
    class Faulty(ReferenceMotion):
        # Intentionally dishonest same binding: outcome checker must detect it.
        def step(self, dt):
            super().step(dt)
            self._state["position"] += 10
            self._state["history"][-1][1] += 10
    child, report = replay(control, cp, suffix, Faulty(), experiment_id="fault-diagnostic")
    assert report["outcome"]["status"] == "FAIL"
    assert report["outcome"]["first_divergence"] == 1
    assert child.inspect()["status"] == "paused"
    validate_replay(report)


@pytest.mark.parametrize("wrong", ["configuration", "runtime", "lineage", "owner"])
def test_branch_binding_refusal_before_attach(lab, wrong):
    _, control, _, instance = lab
    cp, _ = checkpoint_case(instance)
    target = ReferenceMotion()
    if wrong == "configuration": target._config["seed"] = 11
    if wrong == "runtime": target._runtime["python"] = "different"
    if wrong == "lineage": target.simulation_id = "another-simulation"
    if wrong == "owner": target.owner_id = cp["data"]["after"]["provider"]["owner_id"]
    before = len(control._instances)
    with pytest.raises(ValueError):
        control.branch(cp, target, experiment_id="refused")
    assert len(control._instances) == before and target.status == "created"


def test_bad_restore_quarantines_only_child(lab):
    _, control, _, instance = lab
    cp, _ = checkpoint_case(instance)
    parent_before = instance.inspect()
    target = ReferenceMotion()
    with patch.object(target, "restore", lambda payload: None):
        child, receipt = control.branch(cp, target, experiment_id="bad-restore")
    assert receipt["payload"]["status"] == "refused"
    assert child.inspect()["status"] == "refused" and instance.inspect() == parent_before


@pytest.mark.parametrize("change", ["outcome", "authority", "continuity", "occurrence", "command", "checkpoint"])
def test_resealed_replay_corruption_is_rejected(lab, change):
    _, control, _, instance = lab
    cp, suffix = checkpoint_case(instance)
    _, value = replay(control, cp, suffix, ReferenceMotion(), experiment_id="replay")
    if change == "outcome": value["outcome"]["status"] = "FAIL"
    elif change == "authority": value["verification_status"] = "verified"
    elif change == "continuity": value["source"][0], value["source"][1] = value["source"][1], value["source"][0]
    elif change == "occurrence":
        value["replayed"][0]["execution_id"] = value["source"][0]["execution_id"]
        seal(value["replayed"][0])
    elif change == "command":
        event = value["replayed"][0]["data"]
        event["request"]["arguments"] = {"x": 1}
        seal(event)
        value["replayed"][0]["parameters"] = deepcopy(event["request"])
        seal(value["replayed"][0])
    else:
        value["restored"]["data"]["request"]["arguments"]["snapshot_b64"] = encode_snapshot(b"changed")
        seal(value["restored"]["data"])
        seal(value["restored"])
    seal(value)
    with pytest.raises(ValueError): validate_replay(value)


def test_gaps_and_running_checkpoints_not_replayable(lab):
    _, _, _, instance = lab
    cp, suffix = checkpoint_case(instance)
    with pytest.raises(ValueError, match="contiguous"):
        validate_source(cp, suffix[1:])
    ok(instance, "resume")
    running = ok(instance, "checkpoint")
    with pytest.raises(ValueError, match="paused checkpoint"):
        validate_source(running, [ok(instance, "step", dt=1)])


@pytest.mark.parametrize("payload", [b"x" * (MAX_SNAPSHOT + 1), "text-not-bytes", bytearray(b"x")])
def test_snapshot_budget_and_bytes_type(payload):
    with pytest.raises(ValueError): encode_snapshot(payload)


@pytest.mark.parametrize("encoded", ["%%%", "eA", "eA===", "eA==\n"])
def test_snapshot_encoding_is_canonical(encoded):
    with pytest.raises(ValueError): decode_snapshot(encoded)


def test_full_demo_reopen_inspect_compare_and_cli_without_provider(tmp_path):
    directory = tmp_path / "demo"
    summary = demo(directory)
    assert summary["parent_unchanged"] and summary["replay"]["status"] == "PASS"
    assert summary["branch_comparison"]["status"] == "FAIL"
    assert summary["branch_comparison"]["metrics"]["max_abs_error"] == 8
    assert summary["player_latest_sample_s"] == 4 and summary["debugger_latest_sample_s"] == 6
    validate_comparison(load(directory / "branch-comparison.json"))
    with patch.object(ReferenceMotion, "__init__", side_effect=AssertionError("must not start provider")):
        inspected = inspect_workspace(directory / "workspace.json")
        assert inspected["simulation_results"] == inspected["simulation_executions"] == 32
        assert inspected["live_providers_attached"] is False
        validate_replay(load(directory / "replay.json"))
        assert main(["inspect", str(directory / "workspace.json")]) == 0
        assert main(["check-replay", str(directory / "replay.json")]) == 0
    assert main(["demo", "--output-dir", str(directory)]) == 1


def test_reopened_session_does_not_reattach_provider(lab, tmp_path):
    session, _, _, instance = lab
    record = ok(instance, "start")
    path = tmp_path / "workspace.json"
    session.save_workspace(path)
    reopened = open_workspace(path, output_dir=tmp_path / "read")
    request = instance.request("step", dt=1)
    response = reopened.handle({"protocol_version": 1, "request_id": "unbound", "type": "operation.execute",
        "payload": {"operation_id": OPERATION, "parameters": request}})
    assert response["payload"]["status"] == "refused"
    assert record["result_id"] in reopened.results


def test_resealed_lifecycle_corruption_rejected(lab):
    _, _, _, instance = lab
    event = ok(instance, "start")["data"]
    event["after"]["provider"]["clock"]["time_s"] = 100
    seal(event["after"])
    seal(event)
    with pytest.raises(ValueError): validate_event(event)


def test_outer_result_authority_not_accepted(lab):
    _, _, _, instance = lab
    result = ok(instance, "start")
    result["verification_status"] = "verified"
    seal(result)
    with pytest.raises(ValueError): validate_result(result)


def test_projection_rejects_resealed_outer_authority(lab):
    _, _, _, instance = lab
    result = ok(instance, "observe", observer=observer("debug", kind="debugger", channels=["position"]))
    result["verification_status"] = "verified"
    seal(result)
    with pytest.raises(ValueError): projected_samples(result, quantity="position")


def test_branch_retains_selected_checkpoint_occurrence(lab):
    _, control, _, instance = lab
    cp, _ = checkpoint_case(instance)
    _, response = control.branch(cp, ReferenceMotion(), experiment_id="child")
    args = completed(response)["parameters"]["arguments"]
    assert args["source_execution_id"] == cp["execution_id"]
    assert args["source_result_ref"] == cp["record_digest"]
