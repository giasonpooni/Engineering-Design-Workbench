"""Provider-dispatched stateful experiments on the existing CIW Session.

This is a process-local handle table and command gate, not a world-state store,
new Session, scheduler, solver or distributed lease. Only explicitly supplied
trusted provider objects can execute. Saved workspaces never reattach them.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import threading
from typing import Protocol
import uuid

from .adapters.protocol import AdapterRefusal
from .control_checkpoint import CheckpointProvider, capture_checkpoint, restore_checkpoint
from .control_contracts import bytes_ref, detached
from .operations.registry import Operation
from .operations.runner import digest, seal
from .simulation_records import (
    OPERATION, decode_snapshot, encode_snapshot, packed, register_records,
    require, validate_event, validate_instance, validate_request,
)


class SimulationProvider(CheckpointProvider, Protocol):
    """Opt-in on-demand adapter; its snapshot must contain all continuation state.

    Include RNG state, queued events and any integrator/agent memory needed to
    continue. Exclude process handles and owner IDs from opaque snapshot bytes.
    Lifecycle/observation calls must not change state, revision or world time.
    """
    def configuration(self) -> dict: ...
    def lifecycle(self, action: str) -> None: ...
    def intervene(self, intervention: dict) -> None: ...
    def observe_for(self, observer: dict) -> dict: ...


class SimulationInstance:
    """An explicitly bound provider plus experimental metadata; never the solver."""

    def __init__(self, controller, provider: SimulationProvider, *, provider_id: str,
                 experiment_id: str):
        self._controller, self._provider = controller, provider
        self._lock = threading.Lock()
        self._active = None
        self._touched = False
        self._receipts: dict[str, tuple[dict, dict]] = {}
        configuration = detached(provider.configuration())
        require(type(configuration) is dict, "Provider configuration must be an object")
        checkpoint, payload = capture_checkpoint(provider, experiment_id=experiment_id)
        encode_snapshot(payload)
        self._view = packed("ciw.simulation-instance.v1",
            instance_id="instance-" + uuid.uuid4().hex, experiment_id=experiment_id,
            provider_id=provider_id, configuration=configuration,
            configuration_ref=digest(configuration), initial_state_ref=bytes_ref(payload),
            provider=checkpoint["provider"], state_ref=bytes_ref(payload), status="created",
            state_status="captured", revision=0, parent=None)
        validate_instance(self._view)

    @property
    def instance_id(self) -> str:
        return self._view["instance_id"]

    def inspect(self) -> dict:
        """Last retained controller view, not a provider call or live observation."""
        return deepcopy(self._view)

    def request(self, action: str, *, command_id: str | None = None, **arguments) -> dict:
        view = self.inspect()
        return {"instance_id": self.instance_id, "command_id": command_id or "command-" + uuid.uuid4().hex,
                "expected": {"owner_id": view["provider"]["owner_id"], "revision": view["revision"],
                             "state_revision": view["provider"]["state_revision"]},
                "action": action, "arguments": detached(arguments)}

    def command(self, action: str, *, command_id: str | None = None, **arguments) -> dict:
        return self._controller.submit(self.request(action, command_id=command_id, **arguments))

    def _quarantine(self) -> None:
        self._view = seal({**self._view, "status": "refused", "state_status": "unknown_after_failure"})

    def _capture(self) -> tuple[dict, bytes]:
        require(detached(self._provider.configuration()) == self._view["configuration"], "Provider configuration drift")
        checkpoint, payload = capture_checkpoint(self._provider, experiment_id=self._view["experiment_id"])
        encode_snapshot(payload)
        return checkpoint, payload

    def _apply(self, request: dict) -> dict:
        before = self.inspect()
        expected = {"owner_id": before["provider"]["owner_id"], "revision": before["revision"],
                    "state_revision": before["provider"]["state_revision"]}
        if request["expected"] != expected:
            raise AdapterRefusal("stale_simulation_command", "Refresh the owner and both revisions before retrying")
        action, args = request["action"], request["arguments"]
        allowed = {"start": {"created"}, "pause": {"running"}, "resume": {"paused"},
                   "stop": {"created", "running", "paused"}, "step": {"running"},
                   "intervene": {"running", "paused"}, "observe": {"created", "running", "paused"},
                   "checkpoint": {"created", "running", "paused"}, "restore": {"created"}}
        if before["status"] not in allowed[action]:
            raise AdapterRefusal("simulation_lifecycle", "Action is unavailable in this instance status")
        # Once a provider is called, failure is not assumed to roll back its state.
        self._touched = True
        try:
            cp, payload = self._capture()
            require(cp["provider"] == before["provider"] and cp["sha256"] == before["state_ref"],
                    "Provider changed outside the bound command stream")
            observations, checkpoint, snapshot_b64 = None, None, None
            after = deepcopy(before)
            if action in {"start", "pause", "resume", "stop"}:
                self._provider.lifecycle(action)
                after["status"] = {"start": "running", "pause": "paused", "resume": "running", "stop": "stopped"}[action]
            elif action == "step":
                self._provider.step(args["dt"])
            elif action == "intervene":
                self._provider.intervene(detached(args))
            elif action == "observe":
                observations = detached(self._provider.observe_for(detached(args["observer"])))
            elif action == "checkpoint":
                checkpoint, snapshot_b64 = cp, encode_snapshot(payload)
            elif action == "restore":
                require(before["configuration_ref"] == args["source"]["configuration_ref"], "Branch configuration mismatch")
                restore_checkpoint(self._provider, args["checkpoint"], decode_snapshot(args["snapshot_b64"]))
                after.update(status="paused", initial_state_ref=args["checkpoint"]["sha256"],
                             parent={"instance_id": args["source"]["instance_id"],
                                     "checkpoint_ref": args["checkpoint"]["record_digest"]})
            cp_after, _ = self._capture()
            after.update(provider=cp_after["provider"], state_ref=cp_after["sha256"], revision=before["revision"] + 1)
            after = seal(after)
            event = packed("ciw.simulation-event.v1", request=request, before=before, after=after,
                           observations=observations, checkpoint=checkpoint, snapshot_b64=snapshot_b64,
                           verification_id=None, verification_status="not_verified", state_admission="not_performed")
            validate_event(event)
            self._view = after
            return event
        except BaseException:
            self._quarantine()
            raise

    def discard(self) -> None:
        """Explicit best-effort owner cleanup after quarantine; no restore/rollback claim.

        This is resource disposal, not a retained successful simulation stop.
        An ordinary healthy instance should use command('stop') instead.
        """
        if not self._lock.acquire(blocking=False):
            raise AdapterRefusal("simulation_busy", "An instance command is already in flight")
        try:
            require(self._view["status"] == "refused", "Discard is only for quarantined owners")
            self._provider.lifecycle("stop")
        finally:
            self._lock.release()


class SimulationControl:
    """Attach to one existing Session; reuse its registry and execution/result ledger."""

    def __init__(self, session):
        register_records()
        self.session = session
        self._instances: dict[str, SimulationInstance] = {}
        self._owners: set[str] = set()
        self._binding_lock = threading.Lock()
        self._runtime = {"provider": "ciw.simulation-control", "contract": "1",
                         "implementation_sha256": bytes_ref(Path(__file__).read_bytes())}
        # Never replace the Session's registry or an already-bound operation.
        session.operations.register(Operation(OPERATION, "backend", self._execute, lambda: deepcopy(self._runtime)))

    def attach(self, provider: SimulationProvider, *, provider_id: str, experiment_id: str) -> SimulationInstance:
        with self._binding_lock:
            require(len(self._instances) < 64, "Live instance budget exhausted")
            require(not any(item._provider is provider for item in self._instances.values()), "Provider object is already attached")
            instance = SimulationInstance(self, provider, provider_id=provider_id, experiment_id=experiment_id)
            owner = instance.inspect()["provider"]["owner_id"]
            require(owner not in self._owners, "Owner identity was already used in this Session")
            self._owners.add(owner)
            self._instances[instance.instance_id] = instance
            return instance

    def submit(self, request: dict) -> dict:
        request = detached(request)
        validate_request(request)
        instance = self._instances.get(request["instance_id"])
        require(instance is not None, "No live provider is explicitly attached for this instance")
        if not instance._lock.acquire(blocking=False):
            raise AdapterRefusal("simulation_busy", "An instance command is already in flight")
        instance._touched = False
        try:
            prior = instance._receipts.get(request["command_id"])
            if prior is not None:
                if prior[0] != request:
                    raise AdapterRefusal("command_identity_reused", "Command identity cannot be reused with different data")
                return deepcopy(prior[1])
            require(len(instance._receipts) < 1024, "Instance command budget exhausted")
            instance._active = (threading.get_ident(), digest(request))
            instance._touched = False
            response = self.session.handle({"protocol_version": 1, "request_id": request["command_id"],
                "type": "operation.execute", "payload": {"operation_id": OPERATION, "parameters": request}})
            # Publication/storage failures can follow an actual provider mutation.
            if instance._touched and (response["type"] != "response" or response["payload"]["status"] != "completed"):
                instance._quarantine()
            instance._receipts[request["command_id"]] = (request, deepcopy(response))
            return response
        except BaseException:
            if instance._touched:
                instance._quarantine()
            raise
        finally:
            instance._active = None
            instance._lock.release()

    def _execute(self, run: dict, parameters: dict) -> dict:
        validate_request(parameters)
        instance = self._instances.get(parameters["instance_id"])
        if instance is None or instance._active != (threading.get_ident(), digest(parameters)):
            raise AdapterRefusal("simulation_dispatch_only", "Use the bound control submit gate; records cannot attach a provider")
        return instance._apply(parameters)

    def branch(self, checkpoint_result: dict, provider: SimulationProvider, *, experiment_id: str) -> tuple[SimulationInstance, dict]:
        """Restore into an explicitly supplied fresh owner; never mutate the parent."""
        from .simulation_replay import validate_result
        validate_result(checkpoint_result)
        event = checkpoint_result["data"]
        require(event["checkpoint"] is not None, "Select a checkpoint result, not an observation")
        # Check all source/target compatibility before a restore can be attempted.
        source = event["after"]
        identity = detached(provider.identity())
        for key in ("runtime", "model_id", "simulation_id"):
            require(identity[key] == source["provider"][key], "Branch provider binding mismatch")
        require(identity["owner_id"] != source["provider"]["owner_id"] and identity["state_revision"] == 0,
                "Branch needs a fresh provider owner")
        require(provider.configuration() == source["configuration"], "Branch configuration mismatch")
        instance = self.attach(provider, provider_id=source["provider_id"], experiment_id=experiment_id)
        receipt = instance.command("restore", source=source, checkpoint=event["checkpoint"], snapshot_b64=event["snapshot_b64"],
                                   source_result_ref=checkpoint_result["record_digest"], source_execution_id=checkpoint_result["execution_id"])
        return instance, receipt


def completed(receipt: dict) -> dict:
    """Require a retained successful result; preserve refusal receipts for callers."""
    require(receipt.get("type") == "response" and receipt["payload"].get("status") == "completed",
            "Simulation command did not complete; inspect its retained refusal or storage error")
    return detached(receipt["payload"]["result"])


def open_workspace(path: Path, *, output_dir: Path):
    """Register only installed readers, then use the original provider-free reader."""
    register_records()
    from .session import Session
    return Session.from_workspace(path, output_dir=output_dir)
