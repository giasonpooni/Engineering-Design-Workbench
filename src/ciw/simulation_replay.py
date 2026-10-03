"""Fresh-owner replay and data-only checks of a bounded accepted command suffix.

PASS means equality of captured bytes/observations for these executed commands
under matching declared bindings. It is not a general determinism claim, source
attestation, physical validation or permission to execute saved code.
"""
from __future__ import annotations

import re

from .control_contracts import detached, text
from .operations.runner import check_seal
from .simulation_records import OPERATION, packed, require, unpack, validate_event

SCOPE = "same-binding captured-state and observation equality for this executed suffix only"


def validate_result(result: dict) -> None:
    """Validate the retained result's simulation binding; Session checks the ledger."""
    result = detached(result)
    check_seal(result)
    require(result.get("schema") == "ciw.operation-result.v1" and result.get("operation_id") == OPERATION,
            "Require an existing CIW simulation operation result")
    for key, prefix in (("execution_id", "execution"), ("result_id", "result")):
        require(re.fullmatch(prefix + r"-[0-9a-f]{32}", str(result.get(key))) is not None, "Invalid occurrence identity")
    require(result.get("role") == "backend" and result.get("verification_id") is None
            and result.get("verification_status") == "not_verified", "Ordinary simulation result cannot grant authority")
    require(type(result.get("runtime")) is dict and result["runtime"].get("provider") == "ciw.simulation-control",
            "Wrong control operation binding")
    validate_event(result["data"])
    require(result["parameters"] == result["data"]["request"], "Result/request mismatch")


def validate_source(checkpoint: dict, suffix: list[dict]) -> None:
    validate_result(checkpoint)
    event = checkpoint["data"]
    require(event["checkpoint"] is not None and event["after"]["status"] == "paused",
            "Replay starts from an explicitly paused checkpoint")
    require(type(suffix) is list and 1 <= len(suffix) <= 128, "Select 1..128 accepted contiguous commands")
    previous = event["after"]
    occurrences = {checkpoint["execution_id"]}
    commands = {event["request"]["command_id"]}
    for result in suffix:
        validate_result(result)
        item = result["data"]
        require(item["before"] == previous and item["request"]["action"] != "restore", "Replay suffix is not a contiguous instance history")
        require(result["runtime"] == checkpoint["runtime"], "Control implementation changed within suffix")
        require(result["execution_id"] not in occurrences and item["request"]["command_id"] not in commands,
                "Repeated execution or command in suffix")
        occurrences.add(result["execution_id"])
        commands.add(item["request"]["command_id"])
        previous = item["after"]


def fingerprint(event: dict) -> dict:
    """Exclude only new investigation/owner/control/occurrence identities."""
    view = event["after"]
    provider = {k: v for k, v in view["provider"].items() if k != "owner_id"}
    return {"provider": provider, "provider_id": view["provider_id"], "configuration_ref": view["configuration_ref"],
            "state_ref": view["state_ref"], "status": view["status"], "observations": event["observations"]}


def _outcome(checkpoint: dict, source: list[dict], restored: dict, replayed: list[dict]) -> dict:
    validate_source(checkpoint, source)
    validate_result(restored)
    start = restored["data"]
    require(start["request"]["action"] == "restore" and start["request"]["arguments"] == {
        "source": checkpoint["data"]["after"], "checkpoint": checkpoint["data"]["checkpoint"],
        "snapshot_b64": checkpoint["data"]["snapshot_b64"], "source_result_ref": checkpoint["record_digest"],
        "source_execution_id": checkpoint["execution_id"]}, "Replay restored another checkpoint")
    require(len(replayed) == len(source), "Replay report requires a completed suffix; retain failed attempts in Session")
    previous = start["after"]
    old_ids = {x["execution_id"] for x in [checkpoint, *source]}
    new_ids = {restored["execution_id"]}
    require(not old_ids & new_ids, "Restoration must be a fresh execution")
    mismatches = []
    for index, (left, right) in enumerate(zip(source, replayed)):
        validate_result(right)
        event = right["data"]
        require(event["before"] == previous, "Replay instance history is discontinuous")
        require(right["runtime"] == left["runtime"], "Replay control binding mismatch")
        require(right["execution_id"] not in old_ids | new_ids and right["result_id"] != left["result_id"],
                "Replay must create new occurrence identities")
        new_ids.add(right["execution_id"])
        for key in ("action", "arguments"):
            require(event["request"][key] == left["data"]["request"][key], "Replay changed the requested experiment")
        if fingerprint(left["data"]) != fingerprint(event):
            mismatches.append(index)
        previous = event["after"]
    return {"status": "FAIL" if mismatches else "PASS", "checked_commands": len(source),
            "mismatch_indices": mismatches, "first_divergence": mismatches[0] if mismatches else None}


def validate_replay(report: dict) -> None:
    unpack(report, "ciw.simulation-replay.v1", {"checkpoint", "source", "restored", "replayed", "outcome", "claim_scope",
           "verification_id", "verification_status", "state_admission"})
    require(report["claim_scope"] == SCOPE and report["verification_id"] is None
            and report["verification_status"] == "not_verified" and report["state_admission"] == "not_performed",
            "Replay cannot grant scientific or execution authority")
    require(report["outcome"] == _outcome(report["checkpoint"], report["source"], report["restored"], report["replayed"]),
            "Replay outcome contradicts retained evidence")


def replay(control, checkpoint: dict, suffix: list[dict], provider, *, experiment_id: str):
    """Execute an explicitly supplied provider, not a name imported from a file.

    On provider refusal, stop immediately and raise; the existing Session retains
    the refusal and all completed prefix results. No successful report is emitted.
    """
    from .simulation_control import completed
    checkpoint, suffix = detached(checkpoint), detached(suffix)
    validate_source(checkpoint, suffix)
    text(experiment_id)
    child, receipt = control.branch(checkpoint, provider, experiment_id=experiment_id)
    restored = completed(receipt)
    results = []
    for source in suffix:
        req = source["data"]["request"]
        results.append(completed(child.command(req["action"], **req["arguments"])))
    report = packed("ciw.simulation-replay.v1", checkpoint=checkpoint, source=suffix, restored=restored,
                    replayed=results, outcome=_outcome(checkpoint, suffix, restored, results), claim_scope=SCOPE,
                    verification_id=None, verification_status="not_verified", state_admission="not_performed")
    validate_replay(report)
    return child, report
