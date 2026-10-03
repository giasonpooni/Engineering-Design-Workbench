"""Small executable Python reference provider, NOT a Godot/SCR/physics adapter.

Integer motion, a documented toy PRNG, queued impulses and delayed observations
exercise the controller contract. This model is synthetic, not calibrated physics.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import platform
import uuid

from .control_contracts import bytes_ref, keys, observation
from .operations.runner import digest
from .simulation_records import count, require, validate_observer

PROVIDER_ID = "ciw.reference-motion"
MODEL_ID = "synthetic-integer-motion.v1"


class ReferenceMotion:
    def __init__(self, *, seed: int = 7, simulation_id: str = "reference-motion", owner_id: str | None = None):
        require(type(seed) is int and 0 <= seed < 2**31, "Seed must be a 31-bit unsigned integer")
        self._config = {"seed": seed, "tick_s": 1, "max_ticks": 128}
        self._runtime = {"provider": PROVIDER_ID, "reference_only": True,
                         "implementation_sha256": bytes_ref(Path(__file__).read_bytes()),
                         "python": platform.python_version(), "platform": platform.platform()}
        self.simulation_id, self.owner_id = simulation_id, owner_id or "owner-" + uuid.uuid4().hex
        self.status = "created"
        self._state = {"tick": 0, "revision": 0, "position": 0, "velocity": 1, "rng": seed,
                       "queued": [], "history": [[0, 0, 1]]}

    def configuration(self) -> dict:
        return deepcopy(self._config)

    def identity(self) -> dict:
        return {"runtime": deepcopy(self._runtime), "model_id": MODEL_ID, "simulation_id": self.simulation_id,
                "owner_id": self.owner_id, "state_revision": self._state["revision"],
                "clock": {"id": "reference-ticks", "time_s": self._state["tick"]}}

    def snapshot(self) -> bytes:
        return json.dumps({"configuration_ref": digest(self._config), "state": self._state},
                          sort_keys=True, separators=(",", ":"), allow_nan=False).encode()

    def restore(self, snapshot: bytes) -> None:
        from .session import loads_json
        value = loads_json(snapshot.decode("utf-8"))
        keys(value, {"configuration_ref", "state"})
        require(value["configuration_ref"] == digest(self._config), "Reference configuration mismatch")
        state = value["state"]
        keys(state, {"tick", "revision", "position", "velocity", "rng", "queued", "history"})
        for key in ("tick", "revision", "rng"):
            count(state[key])
        require(state["tick"] <= 128 and state["rng"] < 2**31, "Reference state outside bounds")
        require(type(state["position"]) is int and type(state["velocity"]) is int, "Integer reference state required")
        require(type(state["history"]) is list and len(state["history"]) == state["tick"] + 1, "Incomplete reference history")
        for tick, row in enumerate(state["history"]):
            require(type(row) is list and len(row) == 3 and all(type(x) is int for x in row) and row[0] == tick,
                    "Malformed reference history")
        require(state["history"][-1] == [state["tick"], state["position"], state["velocity"]], "Reference history/state mismatch")
        require(type(state["queued"]) is list and len(state["queued"]) <= 16, "Queue exceeds bound")
        for item in state["queued"]:
            keys(item, {"at_tick", "delta_v"})
            require(type(item["at_tick"]) is int and state["tick"] < item["at_tick"] <= 128
                    and type(item["delta_v"]) is int and abs(item["delta_v"]) <= 20, "Invalid queued impulse")
        self._state = deepcopy(state)
        self.status = "paused"

    def lifecycle(self, action: str) -> None:
        allowed = {"start": {"created"}, "pause": {"running"}, "resume": {"paused"},
                   "stop": {"created", "running", "paused", "stopped"}}
        require(action in allowed and self.status in allowed[action], "Reference lifecycle refused")
        self.status = {"start": "running", "pause": "paused", "resume": "running", "stop": "stopped"}[action]

    def step(self, dt: float) -> None:
        require(self.status == "running" and dt == 1 and self._state["tick"] < 128,
                "Reference provider supports one-second ticks up to tick 128")
        s = deepcopy(self._state)
        s["tick"] += 1
        s["rng"] = (1103515245 * s["rng"] + 12345) % 2**31
        s["velocity"] += s["rng"] % 3 - 1
        for item in s["queued"]:
            if item["at_tick"] == s["tick"]:
                s["velocity"] += item["delta_v"]
        s["queued"] = [x for x in s["queued"] if x["at_tick"] != s["tick"]]
        s["position"] += s["velocity"]
        s["revision"] += 1
        s["history"].append([s["tick"], s["position"], s["velocity"]])
        self._state = s

    def intervene(self, intervention: dict) -> None:
        require(intervention["operation"] == "motion.queue-impulse.v1" and intervention["target"] == "body-1",
                "Reference intervention is not supported")
        args = intervention["parameters"]
        keys(args, {"at_tick", "delta_v"})
        require(type(args["at_tick"]) is int and self._state["tick"] < args["at_tick"] <= 128
                and type(args["delta_v"]) is int and abs(args["delta_v"]) <= 20, "Invalid impulse time/magnitude")
        require(len(self._state["queued"]) < 16, "Reference event queue is full")
        self._state["queued"].append(deepcopy(args))
        self._state["revision"] += 1

    def observe_for(self, selected: dict) -> dict:
        validate_observer(selected)
        require(selected["policy"] == {} and selected["player_knowledge_transfer"] is False,
                "Reference observers do not modify agent knowledge")
        debug = selected["kind"] == "debugger"
        permitted = {"position", "velocity"} if debug else {"position"}
        require(set(selected["channels"]) <= permitted, "Observer is not allowed to receive hidden velocity")
        delay = 0 if debug or selected["kind"] == "retrospective_narrator" else 2
        cutoff = self._state["tick"] - delay
        rows = [row for row in self._state["history"] if row[0] <= cutoff][-8:]
        samples = []
        source = bytes_ref(self.snapshot())
        for tick, position, velocity in rows:
            for channel in selected["channels"]:
                samples.append(observation(identity={"model_id": MODEL_ID, "entity_id": "body-1", "execution_id": None},
                    clock={"id": "reference-ticks", "time_s": tick}, frame="reference/world",
                    quantity=channel, value=position if channel == "position" else velocity,
                    unit="m" if channel == "position" else "m/s",
                    provenance={"provider": PROVIDER_ID, "sources": [source], "semantics": "simulated"}))
        return {"observer": deepcopy(selected), "available_at": self.identity()["clock"], "samples": samples}

    def observe(self) -> dict:
        from .simulation_records import observer
        return self.observe_for(observer("debugger", kind="debugger", channels=["position", "velocity"]))
