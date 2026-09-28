"""Explicit pinned Godot process adapter for the existing SimulationProvider.

No dynamics are computed here. The bundled native point model owns its Node3D,
velocity, queue, history, clock and opaque Variant snapshot. This is bounded
headless stepping, not arbitrary scene deserialization or an OS sandbox.
"""
from __future__ import annotations

import json
from pathlib import Path
import queue
import struct
import subprocess
import tempfile
import threading
import uuid
from copy import deepcopy

from .control_contracts import bytes_ref, content_ref, detached, keys, number, observation, text
from .operations.runner import digest
from .simulation_records import decode_snapshot, encode_snapshot, require, validate_observer

PROVIDER_ID = "godot.point-projectile"
MODEL_ID = "godot-point-projectile.v1"
STEP = 1 / 64
LIMIT = 65536
DEFAULT = {"p0_m": [0, 0, 0], "v0_m_s": [2, 3, 0], "gravity_m_s2": [0, -8, 0],
           "step_hz": 64, "max_ticks": 128}
CHANNELS = {f"{kind}_{axis}" for kind in ("position", "velocity") for axis in "xyz"}


def vector(value) -> None:
    require(type(value) is list and len(value) == 3, "Require a three-component vector")
    require(all(abs(number(v)) <= 1000 for v in value), "Vector outside bounded point-model range")


def validate_configuration(value: dict) -> None:
    keys(value, set(DEFAULT))
    require(type(value["step_hz"]) is int and value["step_hz"] == 64
            and type(value["max_ticks"]) is int and value["max_ticks"] == 128,
            "Native pilot requires 64 Hz and at most 128 ticks")
    for name in ("p0_m", "v0_m_s", "gravity_m_s2"):
        vector(value[name])


class _Pipe:
    """One framed request in flight; a deadline covers both pipe write and read."""
    def __init__(self, command: list[str], *, cwd: Path, timeout: float):
        require(0 < number(timeout) <= 60, "RPC timeout must be in (0, 60] seconds")
        self.timeout = timeout
        self.process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        self._requests = queue.Queue(maxsize=1)
        self._lock = threading.Lock()
        self._stderr = bytearray()
        self._closed = False
        self.count = 0
        self._io_thread = threading.Thread(target=self._io, daemon=True)
        self._err_thread = threading.Thread(target=self._drain, daemon=True)
        self._io_thread.start()
        self._err_thread.start()

    def _drain(self):
        total = 0
        while True:
            part = self.process.stderr.read(1024)
            if not part:
                return
            total += len(part)
            self._stderr.extend(part)
            del self._stderr[:-16384]
            if total > 262144:
                self.process.kill()
                return

    def _io(self):
        while True:
            job = self._requests.get()
            if job is None:
                return
            raw, result = job
            try:
                packet = memoryview(struct.pack("<I", len(raw)) + raw)
                while packet:
                    written = self.process.stdin.write(packet)
                    if not written:
                        raise OSError("Native stdin closed")
                    packet = packet[written:]
                self.process.stdin.flush()
                noise = 0
                while True:
                    line = self.process.stdout.readline(LIMIT + 1)
                    require(bool(line) and len(line) <= LIMIT and line.endswith(b"\n"),
                            "Native response truncated or exceeds bound")
                    if line.startswith(b"NET_SIM "):
                        result.put(line[len(b"NET_SIM "):])
                        break
                    noise += len(line)
                    require(noise <= 16384, "Native startup/output noise exceeds bound")
            except BaseException as exc:
                result.put(exc)

    def rpc(self, action: str, arguments: dict) -> dict:
        if not self._lock.acquire(blocking=False):
            raise ValueError("Native provider already has an in-flight request")
        try:
            require(not self._closed and self.process.poll() is None, "Native process is closed")
            require(self.count < 4096, "Native RPC budget exhausted")
            nonce = uuid.uuid4().hex
            request = {"schema": "ciw.godot-rpc.v1", "request_id": nonce,
                       "action": action, "arguments": detached(arguments)}
            raw = json.dumps(request, ensure_ascii=True, allow_nan=False).encode()
            require(len(raw) <= LIMIT, "Native request exceeds frame limit")
            response_queue = queue.Queue(maxsize=1)
            self._requests.put_nowait((raw, response_queue))
            self.count += 1
            try:
                response = response_queue.get(timeout=self.timeout)
            except queue.Empty as exc:
                raise ValueError("Native RPC deadline exceeded") from exc
            if isinstance(response, BaseException):
                raise ValueError(str(response)) from response
            from .session import loads_json
            value = loads_json(response.decode("utf-8"))
            keys(value, {"schema", "request_id", "action", "pid", "data"})
            require(value["schema"] == "ciw.godot-rpc-result.v1" and value["request_id"] == nonce
                    and value["action"] == action and type(value["pid"]) is int
                    and value["pid"] == self.process.pid, "Native response identity mismatch")
            data = detached(value["data"])
            require(type(data) is dict, "Native response must be data")
            if "error" in data:
                raise ValueError("Native provider refused: " + str(data["error"]))
            return data
        except BaseException:
            self.abort()
            raise
        finally:
            self._lock.release()

    def abort(self):
        if self._closed:
            return
        self._closed = True
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=5)
        self._requests.put_nowait(None)
        self._io_thread.join(timeout=5)
        self._err_thread.join(timeout=5)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            stream.close()

    def close(self):
        if self._closed:
            return
        if self.process.poll() is not None:
            self.abort()
            return
        try:
            self.rpc("shutdown", {})
            self.process.wait(timeout=5)
        finally:
            self.abort()

    def diagnostics(self) -> dict:
        return {"pid": self.process.pid, "returncode": self.process.poll(), "rpc_count": self.count,
                "stderr_tail": bytes(self._stderr).decode("utf-8", errors="replace")}


class GodotProjectile:
    """Opt-in native provider; construct only from an operator-selected binary.

    Use as a context manager. A retained lifecycle stop halts simulation; close()
    separately shuts down the process. The context also cleans up on failure.
    """
    def __init__(self, executable: Path, *, expected_sha256: str, configuration: dict | None = None,
                 simulation_id: str = "point-projectile", timeout: float = 10):
        self._configuration = detached(DEFAULT if configuration is None else configuration)
        validate_configuration(self._configuration)
        self._simulation_id = text(simulation_id)
        self._owner_id = "owner-" + uuid.uuid4().hex
        executable = Path(executable).resolve(strict=True)
        require(executable.is_file() and executable.stat().st_size <= 512 * 1024 * 1024,
                "Select a bounded regular Godot executable")
        expected_sha256 = content_ref(expected_sha256)
        require(bytes_ref(executable.read_bytes()) == expected_sha256, "Godot executable digest mismatch")
        worker = Path(__file__).with_name("godot_runtime") / "point_worker.gd"
        script = worker.read_bytes()
        self._temp = tempfile.TemporaryDirectory(prefix="net-godot-point-")
        self._pipe = None
        try:
            root = Path(self._temp.name)
            (root / "worker.gd").write_bytes(script)
            self._pipe = _Pipe([str(executable), "--headless", "--path", str(root),
                                "--script", str(root / "worker.gd")], cwd=root, timeout=timeout)
            reply = self._pipe.rpc("configure", {"configuration": self._configuration,
                "configuration_ref": digest(self._configuration), "owner_id": self._owner_id,
                "simulation_id": self._simulation_id})
            keys(reply, {"meta", "engine_version", "version"})
            require(reply["version"] == [4, 5, 2, "stable"], "Native pilot requires Godot 4.5.2 stable")
            self._runtime = {"provider": PROVIDER_ID, "engine_version": text(reply["engine_version"]),
                "executable_sha256": expected_sha256, "worker_sha256": bytes_ref(script),
                "adapter_sha256": bytes_ref(Path(__file__).read_bytes()), "protocol": "ciw.godot-rpc.v1"}
            self._meta(reply["meta"])
        except BaseException as exc:
            self.close()
            if isinstance(exc, Exception) and self._pipe is not None:
                raise ValueError(str(exc) + "; native stderr: " + self._pipe.diagnostics()["stderr_tail"]) from exc
            raise

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        try:
            if self._pipe is not None:
                self._pipe.close()
        finally:
            self._temp.cleanup()

    def diagnostics(self) -> dict:
        return self._pipe.diagnostics()

    def _meta(self, value: dict) -> dict:
        keys(value, {"owner_id", "simulation_id", "tick", "state_revision", "phase"})
        require(value["owner_id"] == self._owner_id and value["simulation_id"] == self._simulation_id,
                "Native owner/lineage mismatch")
        require(type(value["tick"]) is int and 0 <= value["tick"] <= 128
                and type(value["state_revision"]) is int and value["tick"] <= value["state_revision"] <= 1024,
                "Native clock/revision outside bound")
        require(value["phase"] in {"created", "running", "paused", "stopped"}, "Native lifecycle invalid")
        return value

    def identity(self) -> dict:
        meta = self._meta(self._pipe.rpc("identity", {}))
        return {"runtime": deepcopy(self._runtime), "model_id": MODEL_ID,
                "simulation_id": self._simulation_id, "owner_id": self._owner_id,
                "state_revision": meta["state_revision"],
                "clock": {"id": "godot-point-ticks-64hz", "time_s": meta["tick"] * STEP}}

    def configuration(self) -> dict:
        return deepcopy(self._configuration)

    def snapshot(self) -> bytes:
        value = self._pipe.rpc("snapshot", {})
        keys(value, {"snapshot_b64"})
        return decode_snapshot(value["snapshot_b64"])

    def restore(self, payload: bytes):
        self._meta(self._pipe.rpc("restore", {"snapshot_b64": encode_snapshot(payload)}))

    def lifecycle(self, action: str):
        require(action in {"start", "pause", "resume", "stop"}, "Unknown native lifecycle")
        self._meta(self._pipe.rpc("lifecycle", {"action": action}))

    def step(self, dt: float):
        require(number(dt) == STEP, "Native pilot supports one 1/64-second tick per step")
        self._meta(self._pipe.rpc("step", {"dt": dt}))

    def intervene(self, intervention: dict):
        keys(intervention, {"actor_id", "operation", "target", "parameters"})
        require(intervention["operation"] == "projectile.queue-impulse.v1"
                and intervention["target"] == "projectile", "Unsupported native point intervention")
        text(intervention["actor_id"])
        args = intervention["parameters"]
        keys(args, {"at_tick", "delta_v_m_s"})
        require(type(args["at_tick"]) is int and 1 <= args["at_tick"] <= 128, "Invalid impulse tick")
        vector(args["delta_v_m_s"])
        self._meta(self._pipe.rpc("intervene", detached(intervention)))

    def observe_for(self, selected: dict) -> dict:
        validate_observer(selected)
        require(selected["policy"] == {} and selected["player_knowledge_transfer"] is False,
                "Native point provider has no policy override or knowledge-transfer action")
        require(set(selected["channels"]) <= CHANNELS, "Unsupported point observation channel")
        require(selected["kind"] == "debugger" or all(c.startswith("position_") for c in selected["channels"]),
                "Embodied/narrator observation cannot expose velocity")
        source = bytes_ref(self.snapshot())
        value = self._pipe.rpc("observe", {"observer": detached(selected)})
        keys(value, {"meta", "samples"})
        meta = self._meta(value["meta"])
        require(type(value["samples"]) is list and len(value["samples"]) <= 192, "Native sample budget exceeded")
        samples = []
        for item in value["samples"]:
            keys(item, {"tick", "quantity", "value"})
            require(type(item["tick"]) is int and 0 <= item["tick"] <= meta["tick"]
                    and item["quantity"] in selected["channels"], "Native sample outside selected channel/time")
            number(item["value"])
            samples.append(observation(identity={"model_id": MODEL_ID, "entity_id": "projectile", "execution_id": None},
                clock={"id": "godot-point-ticks-64hz", "time_s": item["tick"] * STEP}, frame="godot/y-up/metres",
                quantity=item["quantity"], value=item["value"], unit="m" if item["quantity"].startswith("position_") else "m/s",
                provenance={"provider": PROVIDER_ID, "sources": [source], "semantics": "simulated"}))
        return {"observer": detached(selected), "available_at": {"id": "godot-point-ticks-64hz", "time_s": meta["tick"] * STEP},
                "samples": samples}

    def observe(self) -> dict:
        from .simulation_records import observer
        return self.observe_for(observer("debugger", kind="debugger", channels=["position_x"]))
