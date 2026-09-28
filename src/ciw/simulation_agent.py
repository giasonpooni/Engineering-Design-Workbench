"""Operator-granted stateful actions on existing AgentHost/SimulationControl.

The MCP transport, numerical comparator, Session and native provider stay their
original implementations. This adapter holds process-local grants and retry
receipts, not another live-world authority or durable exactly-once ledger.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
import threading
from typing import Callable
import uuid

from .agent_api import AgentHost, AUTHORITY, MAX_RESPONSE, encode, parse, identifier
from .control_contracts import bytes_ref, detached, keys, record, save_new
from .session import Session
from .simulation_control import SimulationControl, SimulationProvider
from .simulation_records import (require, validate_request, validate_observer,
                                 projected_samples, OPERATION)
from .simulation_agent_tools import TOOLS, validate_arguments

ACTIONS = {"start", "pause", "resume", "stop", "step", "observe", "intervene", "checkpoint"}


@dataclass(frozen=True)
class Binding:
    """A factory is trusted installed Python, never imported from a tool argument."""
    provider_id: str
    factory: Callable[[], SimulationProvider]
    policy: dict


def validate_policy(policy: dict) -> None:
    keys(policy, {"actions", "steps", "observers", "interventions"})
    actions = policy["actions"]
    require(type(actions) is list and len(actions) == len(set(actions)) and set(actions) <= ACTIONS,
            "Invalid action grants")
    require("stop" in actions, "Every executable binding must permit resource stop")
    for group in ("steps", "observers", "interventions"):
        require(type(policy[group]) is dict and len(policy[group]) <= 16, "Preset group exceeds bound")
        for name in policy[group]:
            identifier(name)
    for value in policy["observers"].values():
        validate_observer(value)
    for group, action in (("steps", "step"), ("interventions", "intervene")):
        for value in policy[group].values():
            validate_request({"instance_id": "policy", "command_id": "policy",
                "expected": {"owner_id": "policy", "revision": 0, "state_revision": 0},
                "action": action, "arguments": value})
    detached(policy)


def _metadata(instance) -> dict:
    view = instance.inspect()
    return {"instance_id": view["instance_id"], "experiment_id": view["experiment_id"],
        "model_id": view["provider"]["model_id"], "provider_id": view["provider_id"],
        "status": view["status"], "state_status": view["state_status"],
        "clock": view["provider"]["clock"], "parent": view["parent"],
        "expected": {"owner_id": view["provider"]["owner_id"], "revision": view["revision"],
                     "state_revision": view["provider"]["state_revision"]}}


class SimulationAgentHost:
    """Compose the original eleven agent tools with four stateful tools.

    New stateful work uses one existing Session. The wrapped AgentHost retains
    its original analysis-operation behavior and immutable policies. Inspection
    does not execute providers. Only explicit create/branch actions call factories.
    """
    def __init__(self, host: AgentHost, *, source: str, bindings: dict[str, Binding],
                 max_attempts: int = 64, max_instances: int = 8):
        require(type(max_attempts) is int and 1 <= max_attempts <= 128, "Attempt budget must be 1..128")
        require(type(max_instances) is int and 1 <= max_instances <= 16, "Instance budget must be 1..16")
        require(type(bindings) is dict and 1 <= len(bindings) <= 8, "Require 1..8 explicit model bindings")
        models = {}
        for name, binding in bindings.items():
            identifier(name)
            require(isinstance(binding, Binding) and callable(binding.factory), "Explicit trusted provider factory required")
            identifier(binding.provider_id.replace('.', '-'))
            policy = detached(binding.policy)
            validate_policy(policy)
            models[name] = Binding(binding.provider_id, binding.factory, policy)
        run = host._get(source)
        from .instruments import validate_run
        validate_run(run)
        self.host = host
        self._bindings = models
        self._maximum, self._max_instances = max_attempts, max_instances
        self._policy = {"schema": "ciw.simulation-agent-grants.v1", "source": host._binding(source),
            "models": {k: {"provider_id": b.provider_id, "policy": b.policy} for k, b in models.items()},
            "max_attempts": max_attempts, "max_instances": max_instances}
        self._policy = parse(encode(self._policy))
        self._policy_ref = bytes_ref(encode(self._policy))
        self._root = host._check_output() / "stateful"
        self._root.mkdir(exist_ok=False)
        save_new(self._root / "grants.json", self._policy)
        self.session = Session(run, self._root / "session")
        self.control = SimulationControl(self.session)
        self._attempts: dict[str, dict] = {}
        self._instances: dict[str, tuple[str, object]] = {}
        self._checkpoints: dict[str, tuple[str, dict]] = {}
        self._providers: list[object] = []
        self._lock = threading.Lock()
        self._blocked = False
        self._closed = False

    def capabilities(self) -> dict:
        value = self.host.capabilities()
        value["stateful"] = {"policy_ref": self._policy_ref, "grants": deepcopy(self._policy),
            "instances": {key: self.inspect(key) for key in self._instances},
            "attempts_used": len(self._attempts), "blocked": self._blocked, "closed": self._closed,
            "semantics": "on-demand commands; no background clock; retries are process-local"}
        return value

    def inspect(self, instance: str) -> dict:
        identifier(instance)
        require(instance in self._instances, "Unknown host-bound instance")
        model, world = self._instances[instance]
        return {"instance": instance, "model": model, **_metadata(world), "authority": deepcopy(AUTHORITY)}

    def _attempt(self, name: str, arguments: dict, execute) -> dict:
        attempt = identifier(arguments["attempt"])
        request = {"tool": name, "arguments": detached(arguments), "policy_ref": self._policy_ref}
        if attempt in self._attempts:
            previous = self._attempts[attempt]
            require(previous["request"] == request, "Attempt identity reused with different request")
            return deepcopy(previous["response"])
        require(not self._closed and not self._blocked, "Stateful host is closed or publication is uncertain")
        require(len(self._attempts) < self._maximum, "Stateful attempt budget exhausted")
        self.host._check_output()
        response = {"status": "incomplete", "attempt": attempt, "policy_ref": self._policy_ref,
                    "authority": deepcopy(AUTHORITY)}
        self._attempts[attempt] = {"request": request, "response": response}
        directory = self._root / ("attempt-" + attempt)
        touched = False
        try:
            directory.mkdir(exist_ok=False)
            save_new(directory / "request.json", request)
            touched = True
            response.update(execute())
        except Exception as exc:
            response.update(status="failed", reason=type(exc).__name__ + ": " + str(exc)[:1000])
            # An exception may follow native dispatch or observation publication.
            # Never silently retry or continue a possibly unretained mutation.
            if touched:
                self._blocked = True
        try:
            path = directory / "workspace.json"
            self.session.save_workspace(path)
            response["workspace_sha256"] = bytes_ref(path.read_bytes())
            require(len(encode(response)) <= MAX_RESPONSE, "Stateful response exceeds bound")
            save_new(directory / "response.json", response)
        except Exception as exc:
            self._blocked = True
            response.update(status="incomplete", retention_error=type(exc).__name__ + ": " + str(exc)[:1000])
        return deepcopy(response)

    def _fresh(self, model: str):
        require(len(self._instances) < self._max_instances, "Stateful instance budget exhausted")
        binding = self._bindings[model]
        provider = binding.factory()
        # Keep explicit cleanup ownership even if attach/restore later fails.
        if not any(provider is p for p in self._providers):
            self._providers.append(provider)
        return provider

    def create(self, model: str, attempt: str) -> dict:
        identifier(model)
        require(model in self._bindings, "Unknown operator-bound model")
        def execute():
            provider = self._fresh(model)
            world = self.control.attach(provider, provider_id=self._bindings[model].provider_id,
                                        experiment_id="agent-" + model)
            handle = "s-" + uuid.uuid4().hex
            self._instances[handle] = (model, world)
            return {"status": "completed", "attachment_only": True, "execution_id": None,
                    "instance": handle, "view": self.inspect(handle)}
        return self._attempt("net_sim_create", {"model": model, "attempt": attempt}, execute)

    def _receipt(self, model: str, handle: str, receipt: dict) -> dict:
        if receipt.get("type") != "response":
            raise ValueError("Session publication failed; inspect retained stateful attempt")
        payload = receipt["payload"]
        execution = payload["execution"]
        out = {"status": payload["status"], "instance": handle, "view": self.inspect(handle),
               "execution_id": execution["execution_id"], "result_id": execution["result_id"]}
        if payload["status"] != "completed":
            out["refusal"] = detached(execution["refusal"])
            return out
        result = payload["result"]
        out["result_ref"] = result["record_digest"]
        event = result["data"]
        if event["checkpoint"] is not None:
            key = "c-" + uuid.uuid4().hex
            self._checkpoints[key] = (model, detached(result))
            out["checkpoint"] = key
        if event["observations"] is not None:
            # Only observations reach the existing agent artifact store. Native
            # snapshot bytes and full operation records remain operator evidence.
            out["observations"] = {}
            for channel in event["observations"]["observer"]["channels"]:
                samples = projected_samples(result, quantity=channel)
                stream = record("observation-stream", observations=samples)
                out["observations"][channel] = self.host._retain(stream)
            out["available_at"] = event["observations"]["available_at"]
        return out

    def command(self, instance: str, attempt: str, expected: dict, action: str, preset: str | None) -> dict:
        identifier(instance)
        require(instance in self._instances, "Unknown host-bound instance")
        model, world = self._instances[instance]
        policy = self._bindings[model].policy
        require(action in policy["actions"], "Action was not granted by the operator")
        groups = {"step": "steps", "observe": "observers", "intervene": "interventions"}
        if action in groups:
            identifier(preset)
            require(preset in policy[groups[action]], "Preset was not granted by the operator")
            data = detached(policy[groups[action]][preset])
            args = {"observer": data} if action == "observe" else data
        else:
            require(preset is None, "This lifecycle action accepts no preset")
            args = {}
        request = {"instance_id": world.instance_id, "command_id": "agent-" + identifier(attempt),
                   "expected": detached(expected), "action": action, "arguments": args}
        validate_request(request)
        arguments = {"instance": instance, "attempt": attempt, "expected": expected, "action": action, "preset": preset}
        return self._attempt("net_sim_command", arguments,
            lambda: self._receipt(model, instance, self.control.submit(request)))

    def branch(self, checkpoint: str, attempt: str) -> dict:
        identifier(checkpoint)
        require(checkpoint in self._checkpoints, "Unknown host-captured checkpoint handle")
        model, result = self._checkpoints[checkpoint]
        def execute():
            provider = self._fresh(model)
            child, receipt = self.control.branch(result, provider, experiment_id="agent-" + model)
            handle = "s-" + uuid.uuid4().hex
            self._instances[handle] = (model, child)
            return self._receipt(model, handle, receipt)
        return self._attempt("net_sim_branch", {"checkpoint": checkpoint, "attempt": attempt}, execute)

    def call(self, name: str, arguments: dict) -> dict:
        if not self._lock.acquire(blocking=False):
            raise ValueError("Agent simulation call already in flight")
        try:
            if name == "net_capabilities":
                from .agent_tools import validate_arguments as original_validate
                original_validate(name, arguments)
                result = self.capabilities()
            elif name in TOOLS:
                validate_arguments(name, arguments)
                result = getattr(self, TOOLS[name]["method"])(**detached(arguments))
            else:
                result = self.host.call(name, arguments)
            require(len(encode(result)) <= MAX_RESPONSE, "Response exceeds bound; inspect a smaller selection")
            return deepcopy(result)
        finally:
            self._lock.release()

    def close(self) -> dict:
        """Retain original stop operations on EOF; never assume abrupt-kill recovery."""
        with self._lock:
            if self._closed:
                return deepcopy(self._shutdown)
            self._closed = True
            outcomes = []
            for handle, (_, world) in self._instances.items():
                try:
                    status = world.inspect()["status"]
                    if status == "refused":
                        world.discard()
                        outcomes.append({"instance": handle, "cleanup": "discarded_refused_owner"})
                    elif status != "stopped":
                        receipt = world.command("stop")
                        outcomes.append({"instance": handle, "cleanup": "stop_attempted", "receipt": receipt})
                except Exception as exc:
                    outcomes.append({"instance": handle, "cleanup": "failed", "reason": str(exc)[:1000]})
            for provider in self._providers:
                try:
                    close = getattr(provider, "close", None)
                    if close is not None:
                        close()
                    elif getattr(provider, "status", None) != "stopped":
                        provider.lifecycle("stop")
                except Exception as exc:
                    outcomes.append({"cleanup": "provider_close_failed", "reason": str(exc)[:1000]})
            self._shutdown = {"status": "closed", "cleanup": outcomes, "authority": deepcopy(AUTHORITY)}
            try:
                self.session.save_workspace(self._root / "workspace.json")
                save_new(self._root / "shutdown.json", self._shutdown)
            except Exception as exc:
                self._shutdown.update(status="incomplete", retention_error=str(exc)[:1000])
            return deepcopy(self._shutdown)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def from_profile(host: AgentHost, path: Path) -> SimulationAgentHost:
    """Operator startup selection only; no tool accepts this file or paths."""
    from .agent_mcp import _read
    path = Path(path).resolve(strict=True)
    profile = parse(_read(path))
    keys(profile, {"schema", "source", "models", "max_attempts", "max_instances"})
    require(profile["schema"] == "ciw.simulation-agent-profile.v1", "Unsupported simulation agent profile")
    bindings = {}
    require(type(profile["models"]) is dict, "Model bindings must be an object")
    for name, item in profile["models"].items():
        keys(item, {"provider", "configuration", "policy"})
        validate_policy(item["policy"])
        if item["provider"] == "reference":
            from .simulation_reference import ReferenceMotion, PROVIDER_ID
            config = detached(item["configuration"])
            keys(config, {"seed", "simulation_id"})
            require(type(config["seed"]) is int and 0 <= config["seed"] < 2**31, "Invalid reference seed")
            identifier(config["simulation_id"])
            factory = lambda config=config: ReferenceMotion(**config)
        elif item["provider"] == "godot-point":
            from .godot_simulation import GodotProjectile, PROVIDER_ID
            from .control_contracts import content_ref
            config = detached(item["configuration"])
            keys(config, {"executable", "sha256"})
            require(type(config["executable"]) is str, "Operator must select a native executable")
            executable = (path.parent / config["executable"]).resolve(strict=True)
            require(executable.is_file() and executable.stat().st_size <= 512 * 1024 * 1024, "Select a bounded regular Godot executable")
            pin = content_ref(config["sha256"])
            # Validate pin before allocating host output; native launch remains
            # deferred until an explicit create/branch tool call.
            from hashlib import file_digest
            with executable.open("rb") as stream:
                require("sha256:" + file_digest(stream, "sha256").hexdigest() == pin, "Godot executable digest mismatch")
            factory = lambda executable=executable, pin=pin: GodotProjectile(executable, expected_sha256=pin)
        else:
            raise ValueError("Only installed reference and godot-point startup routes are supported")
        bindings[name] = Binding(PROVIDER_ID, factory, item["policy"])
    return SimulationAgentHost(host, source=profile["source"], bindings=bindings,
        max_attempts=profile["max_attempts"], max_instances=profile["max_instances"])


def demo_profiles(destination: Path) -> tuple[Path, Path]:
    from .agent_mcp import demo_config
    from .simulation_records import observer
    base = demo_config(destination)
    policy = {"actions": sorted(ACTIONS), "steps": {"tick": {"dt": 1}},
        "observers": {"position": observer("position", kind="debugger", channels=["position"]),
                      "delayed": observer("delayed", kind="embodied_agent", channels=["position"])},
        "interventions": {"push": {"actor_id": "operator-granted-agent", "operation": "motion.queue-impulse.v1",
                                  "target": "body-1", "parameters": {"at_tick": 3, "delta_v": 2}}}}
    value = {"schema": "ciw.simulation-agent-profile.v1", "source": "source",
        "models": {"motion": {"provider": "reference", "configuration": {"seed": 7, "simulation_id": "agent-motion"}, "policy": policy}},
        "max_attempts": 64, "max_instances": 8}
    path = Path(destination) / "simulation-profile.json"
    save_new(path, value)
    return base, path
