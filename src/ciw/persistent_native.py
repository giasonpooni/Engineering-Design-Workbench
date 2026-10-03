"""Bounded persistent transport for the *existing* SCR native host.

No new numerical profile or process protocol is introduced. One request is in
flight per channel. A failed stream is killed/reaped and cannot be reused.
"""
from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import queue
import re
import signal
import struct
import subprocess
import tempfile
import threading
import time
import uuid

from . import native_interop as native
from . import native_interop_contract as contract
from .adapters.protocol import AdapterRefusal
from .adapters.subprocess import _json
from .telemetry import canonical, digest, byte_digest

MAX_REQUESTS = 240  # Below the existing host's 256-frame stream budget.


def validate_runtime(runtime):
    """Offline form of the existing approved-runtime/closure constraints."""
    contract.keys(runtime, {"schema", "revision", "source_tree", "host_sha256",
        "host_byte_count", "source_to_binary_attestation", "julia"})
    if (runtime["schema"] != "ciw.native-interop-runtime.v1"
            or runtime["revision"] not in native._pins()["scr_revisions"]
            or runtime["source_to_binary_attestation"] != "not_established"
            or type(runtime["source_tree"]) is not str
            or not re.fullmatch(r"[a-f0-9]{40}", runtime["source_tree"])
            or type(runtime["host_sha256"]) is not str
            or not re.fullmatch(r"sha256:[a-f0-9]{64}", runtime["host_sha256"])
            or type(runtime["host_byte_count"]) is not int
            or not 1 <= runtime["host_byte_count"] <= 64*1024*1024):
        raise ValueError("Unapproved retained native runtime")
    j = runtime["julia"]
    if j is not None:
        contract.keys(j, {"executable_sha256", "files", "threads", "startup_file",
                          "package_resolution", "depot_attestation"})
        if (j["files"] not in native._julia_closures(native._pins())
                or type(j["threads"]) is not int or j["threads"] != 1
                or j["startup_file"] != "disabled" or j["package_resolution"] != "offline"
                or j["depot_attestation"] != "not_established"
                or type(j["executable_sha256"]) is not str
                or not re.fullmatch(r"sha256:[a-f0-9]{64}", j["executable_sha256"])):
            raise ValueError("Unapproved retained Julia closure")


def validate_step(step, runtime):
    """Use the existing native record reader; never launch a provider here."""
    validate_runtime(runtime)
    source = contract.source(canonical(step["request"]))
    native.NativeInteropWorkflow()._validate_step(
        step, source, byte_digest(canonical(source)), runtime)
    return deepcopy(step["result"]["data"]["output"])


def checked_step(source, execution_id, transport, runtime):
    """Construct the unchanged native step/result records, with a fresh check.

    This is one checked execution, NOT the two-execution one-shot bundle.
    Its enclosing simulation record declares reproduction not performed.
    """
    source = contract.source(canonical(source))
    evidence = byte_digest(canonical(source))
    response = _json(native._unblob(transport["response"]))
    native._host_check(source, _json(native._unblob(transport["request"])), response)
    contract.validate_output(source, response["data"])
    started = time.perf_counter()
    check = contract.check_output(source, response["data"])
    seconds = time.perf_counter() - started
    result = {"schema": "ciw.native-interop-result.v1", "operation_id": native.OPERATION,
              "execution_ref": execution_id, "input_refs": [evidence],
              "data": {"output": deepcopy(response["data"]), "reference_check": check,
                       "authority": deepcopy(contract.AUTHORITY)},
              "authority": deepcopy(contract.AUTHORITY)}
    result["result_id"] = digest(result)
    numerical = native._numeric(source, response["data"])
    step = {"runtime_ref": native.ROLE, "operation_id": native.OPERATION,
            "execution_id": execution_id, "input_refs": [evidence],
            "request": source, "request_sha256": digest(source), "transport": transport,
            "check_seconds": seconds, "result": result, "result_sha256": digest(result),
            "result_id": result["result_id"], "numerical_result": numerical,
            "numerical_result_id": digest(numerical)}
    validate_step(step, runtime)
    return step


class FramedProcess:
    """Internal pipe owner. Deadlines include blocked writes; queues are bounded."""
    def __init__(self, command, *, cwd, env, timeout=210.0):
        self.timeout = timeout
        self.closed = False
        self.error = None
        self.stderr = bytearray()
        self._lock = threading.Lock()
        self._messages = queue.Queue(maxsize=2)
        self.process = subprocess.Popen(
            command, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, start_new_session=os.name != "nt")
        self._readers = [threading.Thread(target=self._read, daemon=True),
                         threading.Thread(target=self._diagnostics, daemon=True)]
        for reader in self._readers:
            reader.start()

    def _stop(self):
        try:
            if self.process.poll() is None:
                if os.name == "nt":
                    self.process.kill()
                else:
                    os.killpg(self.process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def _fail(self, message):
        self.error = message
        self._stop()
        try:
            self._messages.put_nowait(None)
        except queue.Full:
            pass

    def _exact(self, count):
        data = bytearray()
        while len(data) < count:
            chunk = self.process.stdout.read(count - len(data))
            if not chunk:
                raise EOFError("Native stream ended inside or before a response")
            data.extend(chunk)
        return bytes(data)

    def _read(self):
        try:
            while not self.closed:
                size = struct.unpack(">I", self._exact(4))[0]
                if not 1 <= size <= native.FRAME_LIMIT:
                    raise ValueError("Native frame exceeds its existing bound")
                self._messages.put_nowait(self._exact(size))
        except (EOFError, OSError, ValueError, queue.Full) as exc:
            if not self.closed:
                self._fail(str(exc) or "Unsolicited native response queue overflow")

    def _diagnostics(self):
        try:
            while chunk := self.process.stderr.read(4096):
                if len(self.stderr) + len(chunk) > 65536:
                    self._fail("Native diagnostic lifetime budget exceeded")
                    return
                self.stderr.extend(chunk)
        except (ValueError, OSError):
            if not self.closed:
                self._fail("Native diagnostic pipe failed")

    def exchange(self, raw):
        if not self._lock.acquire(blocking=False):
            raise AdapterRefusal("STREAM_BUSY", "One request may be in flight")
        writer = None
        try:
            if self.closed or self.error or not self._messages.empty():
                raise ValueError(self.error or "Native stream closed or contaminated")
            if not 1 <= len(raw) <= 1048576:
                raise ValueError("Request exceeds the existing native limit")
            started = time.monotonic()
            def write():
                try:
                    self.process.stdin.write(native.frame(raw))
                    self.process.stdin.flush()
                except (ValueError, OSError):
                    self._fail("Native input pipe failed")
            writer = threading.Thread(target=write, daemon=True)
            writer.start()
            response = self._messages.get(timeout=self.timeout)
            writer.join(max(0.0, self.timeout - (time.monotonic() - started)))
            if response is None or self.error or writer.is_alive() or not self._messages.empty():
                raise ValueError(self.error or "Native stream violated request bounds")
            return response
        except (ValueError, queue.Empty) as exc:
            self.close()
            if writer is not None:
                writer.join(timeout=1)
            raise AdapterRefusal("STREAM_FAILED", str(exc) or "Native request timed out") from exc
        finally:
            self._lock.release()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self._stop()
        self.process.wait(timeout=10)
        for reader in self._readers:
            reader.join(timeout=2)
        for pipe in (self.process.stdin, self.process.stdout, self.process.stderr):
            pipe.close()


class PersistentChannel:
    """One approved provider process, fixed runtime, and retained handshake."""
    def __init__(self, provider, bindings, runtime):
        if provider not in {"cpp", "julia"}:
            raise ValueError("This stream supports only the existing cpp/julia families")
        current, host_bytes, artifacts = native._runtime(bindings)
        if current != runtime:
            raise ValueError("Runtime changed before persistent initialization")
        if provider == "julia" and runtime["julia"] is None:
            raise ValueError("Julia is required; no fallback provider")
        self.provider, self.runtime = provider, deepcopy(runtime)
        self.stream_id = "native-stream-" + uuid.uuid4().hex
        self.count, self.closed = 0, False
        self._host_identity = None
        self._last_occurrence = -1
        self.pipe = None
        scratch = Path(bindings["host"]).resolve().parent / ".ciw-provider-runs"
        scratch.mkdir(exist_ok=True)
        self._temp = tempfile.TemporaryDirectory(prefix="ciw-persistent-", dir=scratch)
        root = Path(self._temp.name)
        exe = root / ("scr-provider-host.exe" if os.name == "nt" else "scr-provider-host")
        exe.write_bytes(host_bytes)
        exe.chmod(0o700)
        self._snapshots = {exe: host_bytes}
        env = os.environ.copy()
        env.update(JULIA_NUM_THREADS="1", JULIA_LOAD_PATH=os.pathsep.join(("@", "@stdlib")),
                   JULIA_PKG_OFFLINE="true")
        command = [str(exe), "--provider", provider, "--timeout-ms", "180000"]
        if provider == "julia":
            for name, raw in artifacts.items():
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(raw)
                self._snapshots[p] = raw
            project = root / "runtimes/native-interop"
            command += ["--julia", str(Path(bindings["julia"]).resolve()),
                        "--project", str(project), "--worker", str(project / "worker.jl")]
            env["JULIA_DEPOT_PATH"] = native._depot(bindings["julia_depot"])
        try:
            self.pipe = FramedProcess(command, cwd=root, env=env)
            self.hello = canonical({"schema": "ciw.native-interop-handshake-request.v1",
                                    "request_id": "handshake-" + uuid.uuid4().hex})
            self.reply = self.pipe.exchange(self.hello)
            reply = _json(self.reply)
            if reply.get("status") != "ok" or reply.get("request_id") != _json(self.hello)["request_id"]:
                raise ValueError("Persistent host handshake mismatch")
        except Exception:
            self.close()
            raise

    def execute(self, source):
        source = contract.source(canonical(source))
        if source["provider"] != self.provider or self.closed or self.count >= MAX_REQUESTS:
            raise ValueError("Wrong provider, closed channel, or exhausted stream budget")
        execution_id = "execution-" + uuid.uuid4().hex
        request = canonical({"schema": native.REQUEST_SCHEMA,
                             "request_id": "request-" + uuid.uuid4().hex,
                             "parent_execution_id": execution_id,
                             **{k: source[k] for k in ("profile", "arithmetic", "semantics", "payload")}})
        try:
            for path, raw in self._snapshots.items():
                if path.read_bytes() != raw:
                    raise ValueError("Pinned runtime snapshot changed")
            started = time.perf_counter()
            response = self.pipe.exchange(request)
            transport = {"handshake_request": native._blob(self.hello),
                         "handshake_response": native._blob(self.reply),
                         "request": native._blob(request), "response": native._blob(response),
                         "stderr": native._blob(bytes(self.pipe.stderr)),
                         "process_seconds": time.perf_counter() - started}
            for path, raw in self._snapshots.items():
                if path.read_bytes() != raw:
                    raise ValueError("Pinned runtime snapshot changed during execution")
            step = checked_step(source, execution_id, transport, self.runtime)
            host = _json(response)["host"]
            identity = (host["process_id"], host["child_process_id"])
            if ((self._host_identity is not None and identity != self._host_identity)
                    or host["occurrence"] <= self._last_occurrence):
                raise ValueError("Native stream changed process or reused an occurrence")
            self._host_identity, self._last_occurrence = identity, host["occurrence"]
            self.count += 1
            return step
        except Exception:
            self.close()
            raise

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.pipe is not None:
            self.pipe.close()
        self._temp.cleanup()


class ProviderPair:
    """Julia integrates; C++ evaluates observables. Neither owns NET state."""
    def __init__(self, binding, expected_runtime=None):
        bindings, self.runtime = native.NativeInteropWorkflow()._adapters({"runtime": str(binding)})
        if expected_runtime is not None and self.runtime != expected_runtime:
            raise ValueError("Checkpoint restart requires the original runtime")
        self.channels = {}
        try:
            for provider in ("julia", "cpp"):
                self.channels[provider] = PersistentChannel(provider, bindings, self.runtime)
        except Exception:
            self.close()
            raise

    def execute(self, source):
        return self.channels[source["provider"]].execute(source)

    def close(self):
        for channel in self.channels.values():
            channel.close()
