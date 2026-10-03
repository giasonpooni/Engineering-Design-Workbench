"""Data-only records for provider-owned interactive experiments.

Reuse CIW seals, typed observations and opaque checkpoints. No code loading,
state reconstruction, numerical provider or authority is inferred from a record.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from typing import Any

from .control_checkpoint import _identity, validate_checkpoint
from .control_contracts import (
    bytes_ref, content_ref, detached, json_tree, keys, number, text,
    validate_observation,
)
from .operations.registry import valid_operation_id
from .operations.runner import check_seal, seal

OPERATION = "simulation.control.v1"
MAX_SNAPSHOT = 32 * 1024
ACTIONS = {"start", "pause", "resume", "stop", "step", "intervene", "observe", "checkpoint", "restore"}
STATUSES = {"created", "running", "paused", "stopped", "refused"}
_REGISTERED = False


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def packed(schema: str, **fields: Any) -> dict:
    return seal(detached({"schema": schema, **fields}))


def unpack(value: dict, schema: str, fields: set[str]) -> None:
    json_tree(value)
    keys(value, fields | {"schema", "record_digest"})
    require(value["schema"] == schema, "Unexpected simulation record schema")
    check_seal(value)


def count(value: Any) -> None:
    require(type(value) is int and 0 <= value <= 2**53, "Require a bounded nonnegative integer")


def encode_snapshot(payload: bytes) -> str:
    require(type(payload) is bytes and len(payload) <= MAX_SNAPSHOT,
            "This pilot requires an opaque snapshot of at most 32 KiB")
    return base64.b64encode(payload).decode("ascii")


def decode_snapshot(value: str) -> bytes:
    require(type(value) is str and len(value) <= 4 * ((MAX_SNAPSHOT + 2) // 3),
            "Snapshot encoding exceeds the pilot budget")
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid snapshot encoding") from exc
    require(encode_snapshot(raw) == value, "Snapshot must use canonical base64")
    return raw


def observer(observer_id: str, *, kind: str, channels: list[str],
             policy: dict | None = None, player_knowledge_transfer: bool = False) -> dict:
    value = packed("ciw.observer.v1", observer_id=observer_id, kind=kind,
                   channels=channels, policy={} if policy is None else policy,
                   player_knowledge_transfer=player_knowledge_transfer)
    validate_observer(value)
    return value


def validate_observer(value: dict) -> None:
    unpack(value, "ciw.observer.v1", {"observer_id", "kind", "channels", "policy", "player_knowledge_transfer"})
    text(value["observer_id"])
    require(value["kind"] in {"sensor", "embodied_agent", "retrospective_narrator", "debugger"},
            "Unknown observer kind")
    channels = value["channels"]
    require(type(channels) is list and 1 <= len(channels) <= 16, "Require 1..16 observer channels")
    for channel in channels:
        text(channel)
    require(len(set(channels)) == len(channels), "Duplicate observer channel")
    require(type(value["policy"]) is dict, "Observer policy must be an object")
    require(type(value["player_knowledge_transfer"]) is bool, "Declare knowledge transfer explicitly")


def validate_instance(value: dict) -> None:
    unpack(value, "ciw.simulation-instance.v1", {
        "instance_id", "experiment_id", "provider_id", "configuration", "configuration_ref",
        "initial_state_ref", "provider", "state_ref", "status", "state_status", "revision", "parent",
    })
    for name in ("instance_id", "experiment_id", "provider_id"):
        text(value[name])
    require(type(value["configuration"]) is dict, "Configuration must be data")
    from .operations.runner import digest
    require(value["configuration_ref"] == digest(value["configuration"]), "Configuration binding mismatch")
    for name in ("initial_state_ref", "state_ref"):
        content_ref(value[name])
    _identity(value["provider"])
    require(value["status"] in STATUSES, "Unknown instance status")
    require(value["state_status"] == ("unknown_after_failure" if value["status"] == "refused" else "captured"), "State availability contradicts lifecycle")
    count(value["revision"])
    if value["parent"] is not None:
        keys(value["parent"], {"instance_id", "checkpoint_ref"})
        text(value["parent"]["instance_id"])
        content_ref(value["parent"]["checkpoint_ref"])
        require(value["parent"]["instance_id"] != value["instance_id"], "A branch must have a new instance identity")


def validate_request(value: dict) -> None:
    json_tree(value)
    keys(value, {"instance_id", "command_id", "expected", "action", "arguments"})
    text(value["instance_id"])
    require(len(text(value["command_id"])) <= 128, "Command identity exceeds bound")
    expected = value["expected"]
    keys(expected, {"owner_id", "revision", "state_revision"})
    text(expected["owner_id"])
    count(expected["revision"])
    count(expected["state_revision"])
    action, args = value["action"], value["arguments"]
    require(type(action) is str and action in ACTIONS, "Unknown lifecycle action")
    if action == "step":
        keys(args, {"dt"})
        require(0 < number(args["dt"]) <= 3600, "Step duration must be in (0, 3600] seconds")
    elif action == "intervene":
        keys(args, {"actor_id", "operation", "target", "parameters"})
        text(args["actor_id"])
        text(args["target"])
        require(valid_operation_id(args["operation"]), "An intervention needs a versioned provider operation")
        require(type(args["parameters"]) is dict, "Intervention parameters must be data")
    elif action == "observe":
        keys(args, {"observer"})
        validate_observer(args["observer"])
    elif action == "restore":
        keys(args, {"source", "checkpoint", "snapshot_b64", "source_result_ref", "source_execution_id"})
        content_ref(args["source_result_ref"])
        text(args["source_execution_id"])
        validate_instance(args["source"])
        validate_checkpoint(args["checkpoint"], decode_snapshot(args["snapshot_b64"]))
        source, checkpoint = args["source"], args["checkpoint"]
        require(checkpoint["provider"] == source["provider"]
                and checkpoint["sha256"] == source["state_ref"]
                and checkpoint["experiment_id"] == source["experiment_id"], "Checkpoint source binding mismatch")
    else:
        keys(args, set())


def validate_batch(value: dict, instance: dict, selected: dict) -> None:
    keys(value, {"observer", "available_at", "samples"})
    require(value["observer"] == selected, "Provider substituted the selected observer")
    require(value["available_at"] == instance["provider"]["clock"], "Observation availability differs from world clock")
    samples = value["samples"]
    require(type(samples) is list and len(samples) <= 256, "Observation batch exceeds budget")
    previous: dict[tuple, float] = {}
    for sample in samples:
        validate_observation(sample)
        require(sample["identity"]["model_id"] == instance["provider"]["model_id"], "Observation model mismatch")
        require(sample["identity"]["execution_id"] is None, "Inner samples use the enclosing CIW execution, not an invented occurrence")
        require(sample["provenance"]["provider"] == instance["provider_id"], "Observation provider mismatch")
        require(sample["quantity"] in selected["channels"], "Provider returned an unrequested channel")
        require(sample["clock"]["id"] == value["available_at"]["id"]
                and sample["clock"]["time_s"] <= value["available_at"]["time_s"], "Future or wrong-clock observation")
        stream = (sample["identity"]["entity_id"], sample["quantity"])
        stamp = sample["clock"]["time_s"]
        require(stream not in previous or stamp > previous[stream], "Duplicate/out-of-order observation sample")
        previous[stream] = stamp


def validate_event(value: dict) -> None:
    unpack(value, "ciw.simulation-event.v1", {
        "request", "before", "after", "observations", "checkpoint", "snapshot_b64",
        "verification_id", "verification_status", "state_admission",
    })
    require(value["verification_id"] is None and value["verification_status"] == "not_verified"
            and value["state_admission"] == "not_performed", "Simulation records cannot grant scientific authority")
    req, before, after = value["request"], value["before"], value["after"]
    validate_request(req)
    validate_instance(before)
    validate_instance(after)
    require(req["instance_id"] == before["instance_id"], "Request instance mismatch")
    require(req["expected"] == {"owner_id": before["provider"]["owner_id"],
            "revision": before["revision"], "state_revision": before["provider"]["state_revision"]}, "Stale request recorded as accepted")
    require(after["revision"] == before["revision"] + 1, "Control revision did not advance once")
    for name in ("instance_id", "experiment_id", "provider_id", "configuration", "configuration_ref"):
        require(after[name] == before[name], "Stable instance binding changed")
    bp, ap = before["provider"], after["provider"]
    for name in ("runtime", "model_id", "simulation_id", "owner_id"):
        require(ap[name] == bp[name], "Provider identity drift")
    require(ap["clock"]["id"] == bp["clock"]["id"], "Clock identity changed")
    action, args = req["action"], req["arguments"]
    allowed = {"start": {"created"}, "pause": {"running"}, "resume": {"paused"},
               "stop": {"created", "running", "paused"}, "step": {"running"},
               "intervene": {"running", "paused"}, "observe": {"created", "running", "paused"},
               "checkpoint": {"created", "running", "paused"}, "restore": {"created"}}
    require(before["status"] in allowed[action], "Illegal lifecycle transition")
    status = {"start": "running", "pause": "paused", "resume": "running", "stop": "stopped", "restore": "paused"}.get(action, before["status"])
    require(after["status"] == status, "Lifecycle result contradicts command")
    if action == "restore":
        cp, source = args["checkpoint"], args["source"]
        require(bp["state_revision"] == 0 and bp["owner_id"] != cp["provider"]["owner_id"], "Restore target is not a fresh owner")
        for name in ("runtime", "model_id", "simulation_id", "clock", "state_revision"):
            require(ap[name] == cp["provider"][name], "Restoration identity/clock/revision differs from checkpoint")
        require(before["configuration_ref"] == source["configuration_ref"]
                and after["state_ref"] == cp["sha256"] and after["initial_state_ref"] == cp["sha256"], "Restoration state/configuration mismatch")
        require(after["parent"] == {"instance_id": source["instance_id"], "checkpoint_ref": cp["record_digest"]}, "Branch lineage mismatch")
    else:
        require(after["parent"] == before["parent"] and after["initial_state_ref"] == before["initial_state_ref"], "Lineage changed without restore")
        if action in {"step", "intervene"}:
            require(ap["state_revision"] > bp["state_revision"], "Provider mutation did not advance its revision")
            if action == "step":
                require(ap["clock"]["time_s"] == bp["clock"]["time_s"] + args["dt"]
                        and ap["clock"]["time_s"] > bp["clock"]["time_s"], "Provider did not reach the requested step boundary")
            else:
                require(ap["clock"] == bp["clock"], "An intervention cannot silently advance time")
        else:
            require(ap == bp and after["state_ref"] == before["state_ref"], "Read/lifecycle operation mutated world state")
    if action == "observe":
        validate_batch(value["observations"], after, args["observer"])
    else:
        require(value["observations"] is None, "Unexpected observations")
    if action == "checkpoint":
        cp = value["checkpoint"]
        validate_checkpoint(cp, decode_snapshot(value["snapshot_b64"]))
        require(cp["provider"] == ap and cp["sha256"] == after["state_ref"]
                and cp["experiment_id"] == after["experiment_id"], "Checkpoint differs from captured instance")
    else:
        require(value["checkpoint"] is None and value["snapshot_b64"] is None, "Unexpected world snapshot disclosure")


def _payload(operation_id: str, data: dict, run: dict, parameters: dict, selection: dict) -> None:
    require(operation_id == OPERATION, "Wrong simulation operation")
    validate_event(data)
    require(data["request"] == parameters, "Event differs from the retained request")


def register_records() -> None:
    """Trusted fixed reader registration only; reopening never binds a provider."""
    global _REGISTERED
    if not _REGISTERED:
        from .operations.schemas import register_payload_validator
        register_payload_validator(OPERATION, _payload)
        _REGISTERED = True


def projected_samples(result: dict, *, quantity: str) -> list[dict]:
    """Attach the enclosing occurrence without rewriting original saved samples."""
    from .simulation_replay import validate_result
    validate_result(result)
    batch = result["data"]["observations"]
    require(batch is not None, "Result is not an observation")
    projected = []
    for sample in batch["samples"]:
        if sample["quantity"] == quantity:
            item = deepcopy(sample)
            item["identity"]["execution_id"] = result["execution_id"]
            if sample["record_digest"] not in item["provenance"]["sources"]:
                item["provenance"]["sources"].append(sample["record_digest"])
            item = seal(item)
            validate_observation(item)
            projected.append(item)
    return projected
