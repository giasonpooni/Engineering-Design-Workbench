"""Optional persistent Godot owner for the existing SimulationControl protocol.

NET transports commands; Godot owns motion, RNG, queues, history and observer
policy. No Python fallback, second integrator or frame-critical service. The
bounded local mailbox is a trusted-process adapter, not an OS security sandbox.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import file_digest
from importlib.resources import files
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import time
import uuid

from .adapters.protocol import AdapterRefusal
from .adapters.subprocess import _json, _stop
from .control_contracts import bytes_ref, keys, observation, text
from .operations.runner import digest
from .simulation_records import require, validate_observer, observer as make_observer
from .telemetry import canonical

PROVIDER_ID = "ciw.godot-motion"
MODEL_ID = "synthetic-integer-motion.v1"
CLOCK = "reference-ticks"
LIMIT = 128 * 1024
LOG_LIMIT = 64 * 1024
ASSETS = ("project.godot", "worker.gd")


def _integer(value, low, high):
    require(type(value) is int and low <= value <= high, "Expected a bounded integer, not a boolean")


def configuration(seed=7):
    _integer(seed, 0, 2**31 - 1)
    return {"seed": seed, "tick_s": 1, "max_ticks": 128}


def validate_snapshot(raw: bytes, config: dict) -> dict:
    """Shape/continuation completeness only. Does not rerun motion or prove history."""
    require(type(raw) is bytes and 0 < len(raw) <= 32768, "Snapshot exceeds 32 KiB")
    value = _json(raw)
    keys(value, {"configuration_ref", "state"})
    require(value["configuration_ref"] == digest(config), "Snapshot configuration mismatch")
    state = value["state"]
    keys(state, {"tick", "revision", "position", "velocity", "rng", "queued", "history"})
    _integer(state["tick"], 0, 128)
    _integer(state["revision"], state["tick"], 1024)
    _integer(state["rng"], 0, 2**31 - 1)
    _integer(state["position"], -10_000_000, 10_000_000)
    _integer(state["velocity"], -100_000, 100_000)
    history = state["history"]
    require(type(history) is list and len(history) == state["tick"] + 1, "Incomplete history")
    for tick, row in enumerate(history):
        require(type(row) is list and len(row) == 3, "Malformed history row")
        _integer(row[0], tick, tick)
        _integer(row[1], -10_000_000, 10_000_000)
        _integer(row[2], -100_000, 100_000)
    require(history[0] == [0, 0, 1] and history[-1] == [state["tick"], state["position"], state["velocity"]],
            "History and state disagree")
    require(type(state["queued"]) is list and len(state["queued"]) <= 16, "Queue exceeds bound")
    for item in state["queued"]:
        keys(item, {"at_tick", "delta_v"})
        _integer(item["at_tick"], state["tick"] + 1, 128)
        _integer(item["delta_v"], -20, 20)
    return value


class _Mailbox:
    """One request in flight, atomic files, nonce/sequence checks, bounded logs.

    The engine polls this private working directory but never advances world
    time without a command. Polling latency is not a real-time claim.
    """
    def __init__(self, command, root: Path, timeout=30.0):
        require(type(timeout) in (int, float) and 0 < timeout <= 120, "Invalid deadline")
        self.root, self.timeout = root, timeout
        self.sequence = 0
        self.closed = False
        self.error = None
        self.log = bytearray()
        self._lock = threading.Lock()
        env = dict(os.environ)
        for name in ("PYTHONPATH", "PYTHONHOME", "NODE_OPTIONS", "NODE_PATH"):
            env.pop(name, None)
        env["GODOT_SILENCE_ROOT_WARNING"] = "1"
        self.process = subprocess.Popen(command, cwd=root, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=os.name == "posix")
        self._reader = threading.Thread(target=self._drain, daemon=True)
        self._reader.start()

    def _drain(self):
        try:
            while data := self.process.stdout.read1(4096):
                remain = LOG_LIMIT - len(self.log)
                self.log.extend(data[:max(remain, 0)])
                if len(data) > remain:
                    self.error = "Godot diagnostic lifetime limit exceeded"
                    _stop(self.process)
                    return
                if re.search(rb"(?:^|\n)(?:SCRIPT ERROR|ERROR):|(?:Parse|Compile) Error:", self.log):
                    self.error = "Godot reported an engine or script error"
                    _stop(self.process)
                    return
        except (ValueError, OSError):
            if not self.closed:
                self.error = "Godot diagnostic pipe failed"

    def exchange(self, operation: str, arguments: dict) -> dict:
        if not self._lock.acquire(blocking=False):
            raise AdapterRefusal("ENGINE_BUSY", "One engine request may be in flight")
        try:
            if self.closed or self.error or self.process.poll() is not None:
                raise ValueError(self.error or "Engine process is unavailable")
            require(self.sequence < 4096, "Engine request budget exhausted")
            request_path, response_path = self.root / "request.json", self.root / "response.json"
            require(not request_path.exists() and not response_path.exists(), "Contaminated engine mailbox")
            nonce = uuid.uuid4().hex
            request = {"schema": "ciw.godot-motion-request.v1", "sequence": self.sequence,
                       "nonce": nonce, "operation": operation, "arguments": deepcopy(arguments)}
            raw = canonical(request)
            require(len(raw) <= LIMIT, "Engine request exceeds byte budget")
            pending = self.root / "request.pending"
            with pending.open("xb") as out:
                out.write(raw)
            os.replace(pending, request_path)
            end = time.monotonic() + self.timeout
            while not response_path.exists():
                if self.error or self.process.poll() is not None:
                    raise ValueError(self.error or "Engine exited before responding")
                if time.monotonic() >= end:
                    raise TimeoutError("Engine command deadline exceeded")
                time.sleep(.002)
            require(not response_path.is_symlink(), "Engine response is not a regular file")
            with response_path.open("rb") as stream:
                raw = stream.read(LIMIT + 1)
            require(len(raw) <= LIMIT, "Engine response exceeds byte budget")
            reply = _json(raw)
            keys(reply, {"schema", "sequence", "nonce", "status", "data", "error"})
            require(reply["schema"] == "ciw.godot-motion-response.v1" and type(reply["sequence"]) is int
                    and reply["sequence"] == self.sequence and reply["nonce"] == nonce,
                    "Engine response identity mismatch")
            response_path.unlink()
            self.sequence += 1
            require(not self.error, self.error or "Engine diagnostics failed")
            if reply["status"] != "ok" or reply["error"] is not None:
                raise ValueError("Engine refused: " + str(reply["error"])[:400])
            require(type(reply["data"]) is dict, "Engine response data must be an object")
            return reply["data"]
        except (ValueError, OSError, AdapterRefusal) as exc:
            self.error = str(exc)
            self.close()
            tail = bytes(self.log[-2000:]).decode("utf-8", errors="replace")
            raise AdapterRefusal("ENGINE_FAILED", str(exc) + ("; engine log: " + tail if tail else "")) from exc
        finally:
            self._lock.release()

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.process.poll() is None:
            _stop(self.process)
        self.process.wait(timeout=10)
        self._reader.join(timeout=2)
        self.process.stdout.close()


class GodotMotion:
    """Concrete provider for SimulationControl. Supply an operator-pinned binary.

    Snapshot bytes are emitted and restored by Godot, excluding only process/
    owner and lifecycle-control identities. A stopped process is kept until
    close() so the controller can capture its final unchanged state.
    """
    def __init__(self, executable: Path, expected_sha256: str, *, seed=7,
                 simulation_id="godot-motion", timeout=30.0):
        self._config = configuration(seed)
        text(simulation_id)
        self.simulation_id = simulation_id
        self.owner_id = "owner-" + uuid.uuid4().hex
        self._temporary = None
        self._mailbox = None
        executable = Path(executable).resolve(strict=True)
        require(type(expected_sha256) is str and re.fullmatch(r"sha256:[0-9a-f]{64}", expected_sha256),
                "Require an operator-supplied sha256:<64 hex> binary pin")
        require(executable.is_file(), "Godot executable is not a regular file")
        with executable.open("rb") as stream:
            actual = "sha256:" + file_digest(stream, "sha256").hexdigest()
        require(actual == expected_sha256, "Godot executable digest mismatch")
        assets = files("ciw").joinpath("engine_assets", "godot_motion")
        source = {name: assets.joinpath(name).read_bytes() for name in ASSETS}
        self._temporary = tempfile.TemporaryDirectory(prefix="net-godot-owner-")
        root = Path(self._temporary.name)
        try:
            for name, raw in source.items():
                (root / name).write_bytes(raw)
            self._mailbox = _Mailbox([str(executable), "--headless", "--path", str(root),
                "--script", "res://worker.gd"], root, timeout)
            hello = self._mailbox.exchange("init", {"seed": seed, "configuration_ref": digest(self._config)})
            keys(hello, {"engine_version", "platform", "pid", "configuration"})
            require(type(hello["engine_version"]) is str and
                    re.match(r"^4\.5\.2(?:[.\-\s]|$)", hello["engine_version"]), "This profile requires Godot 4.5.2")
            require(hello["configuration"] == self._config, "Engine configuration mismatch")
            _integer(hello["pid"], 1, 2**53)
            require(hello["pid"] == self._mailbox.process.pid, "Engine PID differs from launched process")
            text(hello["platform"])
            self._runtime = {"provider": PROVIDER_ID, "engine_version": hello["engine_version"],
                "platform": hello["platform"], "executable_sha256": actual,
                "implementation_sha256": bytes_ref(Path(__file__).read_bytes()),
                "assets": {name: bytes_ref(raw) for name, raw in source.items()},
                "model_semantics": "synthetic", "source_to_binary_attestation": "not_established"}
            validate_snapshot(self.snapshot(), self._config)
        except BaseException:
            self.close()
            raise

    @property
    def process_id(self):
        return self._mailbox.process.pid

    def configuration(self):
        return deepcopy(self._config)

    def identity(self):
        data = self._mailbox.exchange("identity", {})
        keys(data, {"tick", "revision", "node_x", "node_id"})
        _integer(data["tick"], 0, 128)
        _integer(data["revision"], data["tick"], 1024)
        _integer(data["node_x"], -10_000_000, 10_000_000)
        require(type(data["node_id"]) is str and data["node_id"].isdigit(), "Invalid process-local Node identity")
        return {"runtime": deepcopy(self._runtime), "model_id": MODEL_ID,
            "simulation_id": self.simulation_id, "owner_id": self.owner_id,
            "state_revision": data["revision"], "clock": {"id": CLOCK, "time_s": data["tick"]}}

    def snapshot(self):
        data = self._mailbox.exchange("snapshot", {})
        keys(data, {"snapshot"})
        require(type(data["snapshot"]) is str, "Snapshot must be explicit JSON text")
        raw = data["snapshot"].encode("utf-8")
        validate_snapshot(raw, self._config)
        return raw

    def restore(self, snapshot):
        validate_snapshot(snapshot, self._config)
        require(self.identity()["state_revision"] == 0, "Restore requires a fresh engine owner")
        self._empty_reply("restore", {"snapshot": snapshot.decode("utf-8")})
        require(self.snapshot() == snapshot, "Engine did not restore exact continuation bytes")

    def _empty_reply(self, action, arguments):
        require(self._mailbox.exchange(action, arguments) == {}, "Unexpected mutation response payload")

    def lifecycle(self, action):
        require(action in {"start", "pause", "resume", "stop"}, "Unsupported lifecycle action")
        self._empty_reply("lifecycle", {"action": action})

    def step(self, dt):
        require(type(dt) in (int, float) and dt == 1, "This profile advances exactly one-second logical ticks")
        self._empty_reply("step", {"dt": 1})

    def intervene(self, intervention):
        # The engine owns legality; the generic controller validates its envelope.
        self._empty_reply("intervene", deepcopy(intervention))

    def observe_for(self, selected):
        validate_observer(selected)
        selected = deepcopy(selected)
        source = bytes_ref(self.snapshot())
        data = self._mailbox.exchange("observe", {k: selected[k] for k in
            ("kind", "channels", "policy", "player_knowledge_transfer")})
        keys(data, {"available_at_tick", "samples"})
        _integer(data["available_at_tick"], 0, 128)
        require(type(data["samples"]) is list and len(data["samples"]) <= 16, "Observer output exceeds bound")
        samples = []
        for item in data["samples"]:
            keys(item, {"tick", "quantity", "value"})
            _integer(item["tick"], 0, data["available_at_tick"])
            require(item["quantity"] in selected["channels"] and item["quantity"] in {"position", "velocity"},
                    "Unrequested or unsupported observer field")
            _integer(item["value"], -10_000_000, 10_000_000)
            samples.append(observation(identity={"model_id": MODEL_ID, "entity_id": "body-1", "execution_id": None},
                clock={"id": CLOCK, "time_s": item["tick"]}, frame="reference/world", quantity=item["quantity"],
                value=item["value"], unit="m" if item["quantity"] == "position" else "m/s",
                provenance={"provider": PROVIDER_ID, "sources": [source], "semantics": "simulated"}))
        return {"observer": selected, "available_at": {"id": CLOCK, "time_s": data["available_at_tick"]}, "samples": samples}

    def observe(self):
        return self.observe_for(make_observer("debugger", kind="debugger", channels=["position", "velocity"]))

    def diagnostics(self):
        return {"pid": self.process_id, "requests": self._mailbox.sequence,
                "closed": self._mailbox.closed, "returncode": self._mailbox.process.poll(),
                "log": bytes(self._mailbox.log).decode("utf-8", errors="replace")}

    def close(self):
        if self._mailbox is not None:
            self._mailbox.close()
        if self._temporary is not None:
            self._temporary.cleanup()
