"""Opt-in suffix reproduction on the original SimulationAgentHost and replay engine.

The source is selected from this host's retained results, not agent-supplied
commands. Full replay evidence stays operator-side; only bounded outcomes and
typed observations cross the agent boundary. No new execution ledger or solver.
"""
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
import uuid

from .agent_api import identifier
from .agent_tools import _shape
from .control_contracts import detached, keys, save_new
from .simulation_records import OPERATION, require
from .simulation_agent_tools import EXPECTED
from .simulation_replay import replay, validate_source


def validate_grant(value: dict | None) -> dict | None:
    """An absent grant preserves the previous fifteen-tool stateful profile."""
    if value is None:
        return None
    keys(value, {"max_commands", "max_executions"})
    require(type(value["max_commands"]) is int and 1 <= value["max_commands"] <= 32,
            "Replay permits 1..32 accepted source commands")
    require(type(value["max_executions"]) is int and 2 <= value["max_executions"] <= 128,
            "Replay execution reservation budget must be 2..128")
    return detached(value)


def _selection(host, checkpoint: str, instance: str, expected: dict):
    model, source = host._instances[instance]
    cp_model, cp = host._checkpoints[checkpoint]
    view = source.inspect()
    require(host.inspect(instance)["expected"] == expected, "Stale replay source fence; inspect the selected instance")
    require(view["status"] in {"paused", "stopped"}, "Replay source must be paused or stopped")
    require(model == cp_model and view["instance_id"] == cp["data"]["after"]["instance_id"],
            "Checkpoint does not belong to the selected source instance")
    require(host.session.results.get(cp["result_id"]) == cp, "Checkpoint differs from the retained occurrence")
    begin, end = cp["data"]["after"]["revision"], view["revision"]
    suffix = [detached(r) for r in host.session.results.values()
        if r.get("operation_id") == OPERATION
        and r["data"]["after"]["instance_id"] == view["instance_id"]
        and begin < r["data"]["after"]["revision"] <= end]
    suffix.sort(key=lambda r: r["data"]["after"]["revision"])
    require(1 <= len(suffix) <= host._replay_policy["max_commands"], "Selected replay suffix is empty or exceeds command grant")
    validate_source(cp, suffix)
    require(suffix[-1]["data"]["after"] == view, "Source boundary is not backed by the complete retained suffix")
    policy = host._bindings[model].policy
    groups = {"step": "steps", "observe": "observers", "intervene": "interventions"}
    for result in suffix:
        req = result["data"]["request"]
        action, args = req["action"], req["arguments"]
        require(action in policy["actions"], "Replay contains an action outside current fixed grants")
        if action in groups:
            allowed = policy[groups[action]].values()
            candidate = args["observer"] if action == "observe" else args
            require(candidate in allowed, "Replay contains parameters outside current fixed presets")
    cost = 1 + len(suffix)  # The actual restore is an execution as well.
    require(host._replay_reserved + cost <= host._replay_policy["max_executions"], "Replay execution reservation budget exhausted")
    require(len(host._instances) < host._max_instances, "Stateful instance budget exhausted before replay")
    return model, source, view, detached(cp), suffix, cost


def request_replay(host, checkpoint: str, instance: str, expected: dict, attempt: str) -> dict:
    """One retryable aggregate request; all work uses existing CIW occurrences.

    Preflight rejection consumes an agent attempt but dispatches no simulation
    operation. A reservation includes the restore plus the complete requested
    suffix and is not refunded after factory/provider/publication failure. Cleanup
    retains its original separate semantics and is not charged to this reservation.
    """
    require(host.replay_enabled, "Simulation replay was not granted by the operator")
    identifier(checkpoint); identifier(instance); identifier(attempt)
    _shape(expected, EXPECTED)
    require(checkpoint in host._checkpoints, "Unknown host-captured checkpoint handle")
    require(instance in host._instances, "Unknown host-bound source instance")
    arguments = detached({"checkpoint": checkpoint, "instance": instance, "expected": expected, "attempt": attempt})

    def execute():
        try:
            model, parent, before, cp, suffix, cost = _selection(host, checkpoint, instance, arguments["expected"])
        except ValueError as exc:
            return {"status": "refused", "dispatch_performed": False, "source_instance": instance,
                    "refusal": {"code": "simulation_replay_preflight", "message": str(exc)}}
        host._replay_reserved += cost
        directory = host._root / ("attempt-" + attempt)
        selected = {"schema": "ciw.simulation-agent-replay-selection.v1",
            "checkpoint_result_ref": cp["record_digest"], "source_instance": instance,
            "expected": arguments["expected"], "source_execution_ids": [r["execution_id"] for r in suffix],
            "source_result_refs": [r["record_digest"] for r in suffix], "reserved_executions": cost,
            "total_reserved_executions": host._replay_reserved}
        # Exact source selection and reservation precede any provider creation.
        save_new(directory / "replay-selection.json", selected)
        provider = host._fresh(model)
        existing = set(host.control._instances)
        handle = None

        def branch(*args, **kwargs):
            nonlocal handle
            try:
                return host.control.branch(*args, **kwargs)
            finally:
                # This hook only registers ownership. The original control still
                # attaches/restores and records every command. Track an attached
                # child even if restore/publication raises before returning it.
                new = [world for key, world in host.control._instances.items() if key not in existing]
                require(len(new) <= 1, "Replay unexpectedly attached multiple owners")
                if new:
                    handle = "s-" + uuid.uuid4().hex
                    host._instances[handle] = (model, new[0])

        child, report = replay(SimpleNamespace(branch=branch), cp, suffix, provider,
                               experiment_id="agent-" + model)
        require(handle is not None and host._instances[handle][1] is child, "Replay owner was not retained")
        require(parent.inspect() == before, "Replay changed the captured parent view")
        save_new(directory / "replay.json", report)
        occurrences = [report["restored"], *report["replayed"]]
        response = {"status": "completed", "dispatch_performed": True, "source_instance": instance,
            "instance": handle, "view": host.inspect(handle), "report_ref": report["record_digest"],
            "claim_scope": report["claim_scope"], "outcome": deepcopy(report["outcome"]),
            "reserved_executions": cost, "source_execution_ids": selected["source_execution_ids"],
            "execution_ids": [r["execution_id"] for r in occurrences],
            "result_ids": [r["result_id"] for r in occurrences]}
        # Only the last observation batch is projected into the existing agent
        # artifact store. Every earlier batch remains in the original Session.
        observed = [(left, right) for left, right in zip(suffix, report["replayed"])
                    if right["data"]["observations"] is not None]
        if observed:
            original, latest = observed[-1]
            response.update(host._observation_artifacts(latest))
            response["observation_source_execution_id"] = original["execution_id"]
            response["observation_execution_id"] = latest["execution_id"]
        return response

    # Crucially, retry lookup precedes current-boundary checks or a new factory:
    # an identical request still returns its original receipt after parent changes.
    return host._attempt("net_sim_replay", arguments, execute)
