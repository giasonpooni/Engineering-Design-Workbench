"""One NET-owned oscillator state, advanced by existing persistent SCR providers.

Scientific time is an integer tick. Wall/render time never advances this state.
The native providers compute proposals; the controller alone commits them.
"""
from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import re
import tempfile
import threading
import uuid

from . import native_interop_contract as contract
from .persistent_native import ProviderPair, validate_step
from .session import ProtocolError, loads_json
from .telemetry import canonical, digest

SCHEMA = "notation.simulation-checkpoint.v1"
RATE = 120
MAX_EVENTS = 200
MAX_CHECKPOINT_BYTES = 32 * 1024 * 1024
CONFIGURATION = {"sample_rate_hz": RATE, "solver": {"abstol": 1e-11, "reltol": 1e-10,
                 "maxiters": 100000}, "integrator": "oscillator-tsit5.v1",
                 "observables": "oscillator-force-energy.v1", "stepping": "bounded-on-demand"}
AUTHORITY = {"physical_validation": "not_established", "state_admission": "not_performed",
             "sp1_verification": "not_performed", "covariance": "not_declared",
             "fresh_reproduction": "not_performed", "may_authorize": False}


def _identity(value, prefix):
    if type(value) is not str or not re.fullmatch(prefix + r"[0-9a-f]{32}", value):
        raise ValueError("Malformed " + prefix + " identity")


def _integer(value, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("Require an exact integer inside the declared budget")
    return value


def _state(value):
    contract.keys(value, {"tick", "q_m", "v_m_s"})
    _integer(value["tick"], 0, 24000)
    contract.number(value["q_m"], -10, 10)
    contract.number(value["v_m_s"], -100, 100)
    return deepcopy(value)


def model(parameters):
    contract.model(parameters)
    if parameters["mass_kg"] <= 1e-12 or parameters["omega_0_rad_s"] <= 1e-12:
        raise ValueError("The combined Julia/C++ model requires mass and frequency above 1e-12")
    return {"schema": "notation.damped-oscillator-model.v1", "parameters": deepcopy(parameters),
            "equations": "q'=v; v'=-2*gamma*v-omega_0^2*q", "frame": "one-dimensional-inertial",
            "state_order": ["q", "v"], "state_units": ["m", "m/s"]}


def _trajectory_source(m, state, command):
    ticks = _integer(command["ticks"], 1, 120)
    return contract.make_source("oscillator-tsit5.v1", "julia", {
        "model": m["parameters"], "initial_state": {"q0_m": state["q_m"], "v0_m_s": state["v_m_s"]},
        "time_s": [i / RATE for i in range(ticks + 1)], "solver": CONFIGURATION["solver"]},
        experiment_id="simulation:" + digest({"model": m, "before": state, "command": command}))


def _force_source(m, times, q, v, dependency):
    return contract.make_source("oscillator-force-energy.v1", "cpp", {
        "model": m["parameters"], "time_s": times, "q_m": q, "v_m_s": v},
        experiment_id="simulation-observables:" + digest(dependency))


def _command(action, payload, owner, revision, state):
    extra = {"ticks"} if action == "advance" else {"impulse_n_s"}
    contract.keys(payload, {"command_id", "owner_id", "expected_revision", "at_tick"} | extra)
    _identity(payload["command_id"], "command-")
    if payload["owner_id"] != owner:
        raise ProtocolError("stale_owner", "Refresh the simulation after a restart")
    _integer(payload["expected_revision"], 0, MAX_EVENTS)
    _integer(payload["at_tick"], 0, 24000)
    if payload["expected_revision"] != revision or payload["at_tick"] != state["tick"]:
        raise ProtocolError("stale_state", "Refresh before submitting a state-changing command")
    if action == "advance":
        _integer(payload["ticks"], 1, 120)
    elif action == "impulse":
        contract.number(payload["impulse_n_s"], -1, 1)
    else:
        raise ValueError("Unknown simulation mutation")


def _seal(value, key):
    result = deepcopy(value)
    result[key] = digest(result)
    return result


def _unseal(value, key):
    if value[key] != digest({k: v for k, v in value.items() if k != key}):
        raise ValueError("Retained " + key + " binding differs")


def publish(directory, name, value):
    """Atomic create-only publication of fully serialized immutable bytes."""
    raw = canonical(value)
    destination = Path(directory) / name
    if destination.exists():
        if destination.read_bytes() == raw:
            return destination
        raise ValueError("Refuse to replace an existing retained artifact")
    with tempfile.TemporaryDirectory(prefix=".simulation-", dir=directory) as temporary:
        staged = Path(temporary) / "artifact.json"
        with staged.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(staged, destination)
    return destination


def _native(step, source, runtime):
    if canonical(step["request"]) != canonical(source):
        raise ValueError("Simulation/native source binding differs")
    return validate_step(step, runtime)


def _event_result(m, before, action, command, steps, runtime):
    """Reassemble retained native values; this performs no new integration."""
    if action == "advance":
        if len(steps) != 2:
            raise ValueError("Advance requires Julia motion and C++ observables")
        motion = _native(steps[0], _trajectory_source(m, before, command), runtime)
        force = _native(steps[1], _force_source(m, motion["time_s"], motion["q_m"], motion["v_m_s"],
                                              steps[0]["result_id"]), runtime)
        after = {"tick": before["tick"] + command["ticks"],
                 "q_m": motion["q_m"][-1], "v_m_s": motion["v_m_s"][-1]}
        trajectory = {"start_tick": before["tick"], "sample_rate_hz": RATE,
                      "q_m": motion["q_m"], "v_m_s": motion["v_m_s"], "energy_j": force["energy_j"]}
    else:
        if len(steps) != 1:
            raise ValueError("Impulse requires one C++ observable evaluation")
        after = {**before, "v_m_s": before["v_m_s"] + command["impulse_n_s"] / m["parameters"]["mass_kg"]}
        force = _native(steps[0], _force_source(m, [0.0], [after["q_m"]], [after["v_m_s"]],
                                             {"model": m, "before": before, "command": command}), runtime)
        trajectory = {"start_tick": before["tick"], "sample_rate_hz": RATE,
                      "q_m": [after["q_m"]], "v_m_s": [after["v_m_s"]], "energy_j": force["energy_j"]}
    _state(after)
    observables = {key: force[key][-1] for key in ("net_force_n", "acceleration_m_s2", "energy_j")}
    return after, observables, trajectory


def inspect_checkpoint(cp, expected_id=None):
    """Validate complete retained history without providers or fresh reference checks.

    The external expected identity authenticates the *selection*, not the source
    physics. A consistently rehashed unauthenticated history is not a signature.
    """
    if len(canonical(cp)) > MAX_CHECKPOINT_BYTES:
        raise ValueError("Checkpoint exceeds byte budget")
    contract.keys(cp, {"schema", "simulation_id", "model", "model_id", "configuration", "initial_owner_id",
                       "initial_state", "initial_force", "runtime", "events", "authority", "checkpoint_id"})
    if (cp["schema"] != SCHEMA or canonical(cp["authority"]) != canonical(AUTHORITY)
            or canonical(cp["configuration"]) != canonical(CONFIGURATION)):
        raise ValueError("Unsupported simulation contract")
    _unseal(cp, "checkpoint_id")
    if expected_id is not None and cp["checkpoint_id"] != expected_id:
        raise ValueError("Checkpoint differs from independently selected identity")
    if (canonical(cp["model"]) != canonical(model(cp["model"]["parameters"]))
            or cp["model_id"] != digest(cp["model"])):
        raise ValueError("Model identity differs")
    _identity(cp["simulation_id"], "simulation-")
    _identity(cp["initial_owner_id"], "owner-")
    state = _state(cp["initial_state"])
    if state["tick"] != 0:
        raise ValueError("Initial simulation tick must be zero")
    initial = _native(cp["initial_force"], _force_source(cp["model"], [0.0], [state["q_m"]], [state["v_m_s"]],
                      {"simulation_id": cp["simulation_id"], "initial": state, "model_id": cp["model_id"]}), cp["runtime"])
    observable = {k: initial[k][0] for k in ("net_force_n", "acceleration_m_s2", "energy_j")}
    trajectory = {"start_tick": 0, "sample_rate_hz": RATE, "q_m": [state["q_m"]],
                  "v_m_s": [state["v_m_s"]], "energy_j": initial["energy_j"]}
    if type(cp["events"]) is not list or len(cp["events"]) > MAX_EVENTS:
        raise ValueError("Simulation event budget exceeded")
    previous, owner = None, cp["initial_owner_id"]
    seen = {cp["initial_force"]["execution_id"]}
    commands = set()
    for revision, event in enumerate(cp["events"], 1):
        contract.keys(event, {"schema", "action", "command", "owner_id", "revision", "before", "after",
                              "native_steps", "previous_event_id", "model_id", "simulation_id", "event_id"})
        _unseal(event, "event_id")
        _state(event["before"])
        _state(event["after"])
        if (event["schema"] != "notation.simulation-event.v1" or type(event["revision"]) is not int
                or event["revision"] != revision or event["before"] != state or event["previous_event_id"] != previous
                or event["model_id"] != cp["model_id"] or event["simulation_id"] != cp["simulation_id"]):
            raise ValueError("Simulation event chain differs")
        if event["action"] == "restore":
            contract.keys(event["command"], {"checkpoint_id", "previous_owner_id"})
            prior = {**cp, "events": cp["events"][:revision-1]}
            prior.pop("checkpoint_id")
            if (event["command"] != {"checkpoint_id": digest(prior), "previous_owner_id": owner}
                    or event["native_steps"] or event["after"] != state or event["owner_id"] == owner):
                raise ValueError("Restart lineage differs")
            _identity(event["owner_id"], "owner-")
            owner = event["owner_id"]
        else:
            if event["owner_id"] != owner:
                raise ValueError("Unexpected state owner change")
            _command(event["action"], event["command"], owner, revision-1, state)
            cid = event["command"]["command_id"]
            if cid in commands:
                raise ValueError("Repeated accepted command")
            commands.add(cid)
            state, observable, trajectory = _event_result(cp["model"], state, event["action"],
                                      event["command"], event["native_steps"], cp["runtime"])
            if canonical(event["after"]) != canonical(state):
                raise ValueError("State does not match retained provider outputs")
            for step in event["native_steps"]:
                if step["execution_id"] in seen:
                    raise ValueError("Reused native execution occurrence")
                seen.add(step["execution_id"])
        previous = event["event_id"]
    return {"simulation_id": cp["simulation_id"], "model_id": cp["model_id"], "owner_id": owner,
            "revision": len(cp["events"]), "state": state, "observables": observable,
            "trajectory": trajectory, "last_event_id": previous, "authority": deepcopy(AUTHORITY)}


class Simulation:
    """Serialized state mutations, non-blocking observation, explicit restart."""
    def __init__(self, parameters, initial, binding, directory, *, checkpoint=None, expected_id=None):
        self._operation = threading.Lock()
        self._read = threading.Lock()
        self._status = "initializing"
        self._receipts = {}
        self.directory = Path(directory)
        self.providers = None
        # Never reuse another controller's directory. mkdir is atomic even for competing starts.
        self.directory.mkdir(parents=True, exist_ok=False)
        try:
            if checkpoint is None:
                initial = _state(initial)
                if initial["tick"] != 0:
                    raise ValueError("New instances start at tick zero")
                m = model(parameters)
                self.providers = ProviderPair(binding)
                self._cp = {"schema": SCHEMA, "simulation_id": "simulation-" + uuid.uuid4().hex,
                            "model": m, "model_id": digest(m), "configuration": deepcopy(CONFIGURATION),
                            "initial_owner_id": "owner-" + uuid.uuid4().hex, "initial_state": initial,
                            "runtime": deepcopy(self.providers.runtime), "events": [], "authority": deepcopy(AUTHORITY)}
                source = _force_source(m, [0.0], [initial["q_m"]], [initial["v_m_s"]],
                         {"simulation_id": self._cp["simulation_id"], "initial": initial, "model_id": self._cp["model_id"]})
                self._cp["initial_force"] = self.providers.execute(source)
                self._view = inspect_checkpoint(_seal(self._cp, "checkpoint_id"))
            else:
                if expected_id is None:
                    raise ValueError("Restart requires an independently selected checkpoint identity")
                self._view = inspect_checkpoint(checkpoint, expected_id)
                self.providers = ProviderPair(binding, expected_runtime=checkpoint["runtime"])
                self._cp = deepcopy(checkpoint)
                self._cp.pop("checkpoint_id")
                if len(self._cp["events"]) >= MAX_EVENTS:
                    raise ValueError("Cannot restart an exhausted retained event history")
                new_owner = "owner-" + uuid.uuid4().hex
                event = self._event("restore", {"checkpoint_id": expected_id,
                      "previous_owner_id": self._view["owner_id"]}, self._view["state"], [], new_owner)
                self._commit(event, {**self._view, "owner_id": new_owner})
            self._status = "ready"
            self.checkpoint()
        except Exception:
            self._status = "failed"
            if self.providers is not None:
                self.providers.close()
            raise

    def inspect(self):
        with self._read:
            return {**deepcopy(self._view), "status": self._status}

    def _event(self, action, payload, after, steps, owner=None):
        return _seal({"schema": "notation.simulation-event.v1", "action": action,
            "command": deepcopy(payload), "owner_id": owner or self._view["owner_id"],
            "revision": self._view["revision"] + 1, "before": deepcopy(self._view["state"]),
            "after": deepcopy(after), "native_steps": steps, "previous_event_id": self._view["last_event_id"],
            "model_id": self._cp["model_id"], "simulation_id": self._cp["simulation_id"]}, "event_id")

    def _commit(self, event, next_view):
        # Refuse a result that cannot subsequently be retained as a checkpoint.
        candidate = _seal({**self._cp, "events": self._cp["events"] + [event]}, "checkpoint_id")
        if len(canonical(candidate)) > MAX_CHECKPOINT_BYTES:
            raise ValueError("Simulation checkpoint byte budget exhausted")
        # Publish immutable event before making its state visible. No solver runs under _read.
        publish(self.directory, "event-" + event["event_id"][7:] + ".json", event)
        with self._read:
            self._cp["events"].append(event)
            self._view = {**next_view, "state": deepcopy(event["after"]), "revision": event["revision"],
                          "last_event_id": event["event_id"]}

    def mutate(self, action, payload):
        if not self._operation.acquire(blocking=False):
            raise ProtocolError("simulation_busy", "One state-changing command may be in flight")
        steps = []
        executing = False
        try:
            request_digest = digest({"action": action, "payload": payload})
            cid = payload.get("command_id")
            if type(cid) is str and cid in self._receipts:
                previous, receipt = self._receipts[cid]
                if previous != request_digest:
                    raise ValueError("Command ID was already bound to another request")
                return deepcopy(receipt)
            if type(cid) is str and any(e["command"].get("command_id") == cid for e in self._cp["events"]):
                raise ProtocolError("prior_command", "Command ID belongs to the retained pre-restart history")
            if self._status != "ready" or len(self._cp["events"]) >= MAX_EVENTS:
                raise ValueError("Simulation is not ready or its retained event budget is exhausted")
            _command(action, payload, self._view["owner_id"], self._view["revision"], self._view["state"])
            m, before = self._cp["model"], self._view["state"]
            if action == "impulse":
                after = _state({**before, "v_m_s": before["v_m_s"] + payload["impulse_n_s"] / m["parameters"]["mass_kg"]})
                source = _force_source(m, [0.0], [after["q_m"]], [after["v_m_s"]],
                                       {"model": m, "before": before, "command": payload})
            else:
                source = _trajectory_source(m, before, payload)
            with self._read:
                self._status = "advancing"
            executing = True
            steps.append(self.providers.execute(source))
            if action == "advance":
                motion = validate_step(steps[0], self._cp["runtime"])
                steps.append(self.providers.execute(_force_source(m, motion["time_s"], motion["q_m"],
                                                                  motion["v_m_s"], steps[0]["result_id"])))
            after, observables, trajectory = _event_result(m, before, action, payload, steps, self._cp["runtime"])
            event = self._event(action, payload, after, steps)
            self._commit(event, {**self._view, "observables": observables, "trajectory": trajectory})
            with self._read:
                self._status = "ready"
            receipt = self.inspect()
            self._receipts[cid] = (request_digest, receipt)
            return receipt
        except Exception as exc:
            if executing:
                with self._read:
                    self._status = "failed"
                self.providers.close()
                failure = _seal({"schema": "notation.simulation-failure.v1", "failure_id": "failure-" + uuid.uuid4().hex,
                    "model_id": self._cp["model_id"], "simulation_id": self._cp["simulation_id"],
                    "command": deepcopy(payload), "action": action, "last_committed": deepcopy(self._view),
                    "completed_native_steps": steps, "code": type(exc).__name__,
                    "state_committed": False}, "failure_digest")
                publish(self.directory, "failure-" + failure["failure_digest"][7:] + ".json", failure)
            raise
        finally:
            self._operation.release()

    def checkpoint(self):
        if not self._operation.acquire(blocking=False):
            raise ProtocolError("simulation_busy", "Checkpoint requires a completed state boundary")
        try:
            cp = _seal(self._cp, "checkpoint_id")
            inspect_checkpoint(cp)
            path = publish(self.directory, "checkpoint-" + cp["checkpoint_id"][7:] + ".json", cp)
            return {"checkpoint_id": cp["checkpoint_id"], "filename": path.name,
                    "model_id": cp["model_id"], "simulation_id": cp["simulation_id"]}
        finally:
            self._operation.release()

    def close(self):
        if not self._operation.acquire(blocking=False):
            raise ProtocolError("simulation_busy", "Close requires a completed state boundary")
        try:
            if self.providers is not None:
                self.providers.close()
            with self._read:
                self._status = "closed"
        finally:
            self._operation.release()


def read_checkpoint(path):
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_CHECKPOINT_BYTES + 1)
    if len(raw) > MAX_CHECKPOINT_BYTES:
        raise ValueError("Checkpoint exceeds byte budget")
    return loads_json(raw.decode("utf-8"))
