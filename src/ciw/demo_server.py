"""Bounded, synthetic-only browser interface to existing pinned NET instruments.

Run an installed package with operator-provisioned provider Git checkouts:
python -m ciw.demo_server --gsie-repo DIR --jspt-repo DIR --port 4173
The worker executes fixed declarations; visitors cannot supply code or paths.
"""
from __future__ import annotations

import argparse
from collections import OrderedDict, deque
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit

from .adapters.subprocess import _json
from .telemetry import canonical


@dataclass(frozen=True)
class Limits:
    wall_seconds: float = 45
    cpu_seconds: int = 30
    memory_mib: int = 2048
    output_bytes: int = 8 * 1024 * 1024
    body_bytes: int = 32 * 1024
    max_running: int = 2
    per_session_running: int = 1
    max_queued: int = 8
    max_jobs: int = 64
    max_sessions: int = 128
    max_http_connections: int = 32
    retained_bytes: int = 32 * 1024 * 1024
    retention_seconds: float = 3600

    def __post_init__(self):
        if any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0
               for value in asdict(self).values()):
            raise ValueError("All demo execution limits must be finite and positive")
        for key, value in asdict(self).items():
            if key not in {"wall_seconds", "retention_seconds"} and type(value) is not int:
                raise ValueError("Demo count and byte limits must be integers")
        if self.max_running > 2 or self.per_session_running != 1:
            raise ValueError("Public demo allows at most two workers and one per session")


class DemoError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status

    def value(self):
        return {"code": self.code, "message": self.message}


@dataclass
class Job:
    id: str
    owner: str
    example: str
    source: dict
    mode: str = "execute"
    original: dict | None = None
    original_id: str | None = None
    status: str = "queued"
    created: float = field(default_factory=time.time)
    started: float | None = None
    completed: float | None = None
    result: dict | None = None
    bundle: dict | None = None
    receipt: dict | None = None
    error: dict | None = None
    size: int = 0
    cancel: threading.Event = field(default_factory=threading.Event)

    def public(self):
        value = {"id": self.id, "example": self.example, "status": self.status,
                 "mode": self.mode, "created_at": self.created,
                 "started_at": self.started, "completed_at": self.completed}
        if self.original_id:
            value["original_id"] = self.original_id
        if self.result is not None:
            value["result"] = deepcopy(self.result)
        if self.receipt is not None:
            value["replay_receipt"] = deepcopy(self.receipt)
        if self.error:
            value["error"] = dict(self.error)
        return value


def stop_group(process):
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except ProcessLookupError:
        pass


def sanitized_environment(directory):
    # Do not inherit credentials, Git overrides, Python paths or loader hooks.
    value = {"PATH": os.defpath, "HOME": str(directory), "TMPDIR": str(directory),
             "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1",
             "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1",
             "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1"}
    if os.name == "nt" and "SYSTEMROOT" in os.environ:
        value["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    return value


class DemoService:
    """Private ephemeral jobs, bounded queue and actual isolated execution.

    ``worker_command`` is a trusted constructor-only fault-test seam. It is never
    exposed by HTTP or loaded from a downloaded configuration.
    """
    def __init__(self, repositories, *, limits=None, worker_command=None):
        self.repositories = {role: str(Path(path).resolve()) for role, path in repositories.items()}
        if set(self.repositories) != {"gsie", "jspt"}:
            raise ValueError("Require exactly operator-bound GSIE and JSPT providers")
        self.limits = limits or Limits()
        self.command = worker_command or [sys.executable, "-I", "-m", "ciw.demo_worker",
            "--gsie-repo", self.repositories["gsie"], "--jspt-repo", self.repositories["jspt"],
            "--cpu-seconds", str(self.limits.cpu_seconds), "--memory-mib", str(self.limits.memory_mib),
            "--output-bytes", str(self.limits.output_bytes)]
        self.jobs = OrderedDict()
        self.sessions = OrderedDict()
        self.queue = deque()
        self.running = set()
        self.lock = threading.Condition()
        self.closing = False
        self.qualified = []
        self.qualification = []
        self.scheduler = threading.Thread(target=self._schedule, name="net-demo-scheduler", daemon=True)
        self.scheduler.start()

    def _prune(self):
        cutoff = time.time() - self.limits.retention_seconds
        for identity, job in list(self.jobs.items()):
            if job.completed is not None and job.completed < cutoff:
                del self.jobs[identity]
        for owner, value in list(self.sessions.items()):
            if value["seen"] < cutoff and not any(j.owner == owner and j.completed is None for j in self.jobs.values()):
                del self.sessions[owner]
                for identity, job in list(self.jobs.items()):
                    if job.owner == owner and job.completed is not None:
                        del self.jobs[identity]

    def session(self, supplied=None):
        with self.lock:
            self._prune()
            if supplied in self.sessions:
                self.sessions[supplied]["seen"] = time.time()
                return supplied, self.sessions[supplied]["csrf"], False
            if len(self.sessions) >= self.limits.max_sessions:
                raise DemoError("SESSION_CAPACITY", "The demo is busy. Try again after an existing session expires.", 503)
            owner, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            self.sessions[owner] = {"csrf": csrf, "seen": time.time()}
            return owner, csrf, True

    def require_session(self, owner):
        with self.lock:
            self._prune()
            if owner not in self.sessions:
                raise DemoError("SESSION_EXPIRED", "Your private demo session expired. Reload the page to begin again.", 401)
            self.sessions[owner]["seen"] = time.time()

    def qualify(self):
        from .demo_catalog import catalog, source_for
        for example in catalog():
            identity = example["id"]
            try:
                source = source_for(identity, {})
                first = self._invoke({"mode": "execute", "source": source}, threading.Event())
                self._validate_response(first, source)
                replay = self._invoke({"mode": "replay", "bundle": first["bundle"]}, threading.Event())
                self._validate_response(replay, source)
                receipt = replay["replay_receipt"]
                if (not isinstance(receipt, dict) or receipt.get("numerical_match") is not True or
                        receipt.get("source_bundle_digest") != first["bundle"]["bundle_digest"]):
                    raise DemoError("QUALIFICATION_REPLAY", "Native replay did not reproduce and bind the original execution.", 503)
                self.qualified.append(deepcopy(example))
                self.qualification.append({"example": identity, "outcome": "passed",
                    "bundle_digest": first["bundle"]["bundle_digest"],
                    "replay_id": replay["replay_receipt"]["replay_id"]})
            except (DemoError, ValueError, OSError) as exc:
                self.qualification.append({"example": identity, "outcome": "failed",
                    "error": exc.value() if isinstance(exc, DemoError) else
                    {"code": "QUALIFICATION_FAILED", "message": "Check installed package and pinned provider histories."}})
        return deepcopy(self.qualification)

    @staticmethod
    def _validate_response(response, source):
        from .sensor_fusion_ekf_workflow import SensorFusionEKFWorkflow
        if not isinstance(response, dict) or set(response) != {"ok", "bundle", "replay_receipt"} or response["ok"] is not True:
            raise DemoError("WORKER_RESPONSE", "The worker returned an incomplete result. Retry the example.", 503)
        raw = SensorFusionEKFWorkflow()._validate(response["bundle"])
        if canonical(_json(raw)) != canonical(source):
            raise DemoError("SOURCE_INTEGRITY", "The retained result does not match its declared configuration.", 503)
        receipt = response["replay_receipt"]
        if receipt is not None and response["bundle"].get("replay_receipts") != [receipt]:
            raise DemoError("REPLAY_INTEGRITY", "The replay receipt is not bound to the fresh evidence bundle.", 503)

    def submit(self, owner, example, parameters=None, *, replay_id=None):
        from .demo_catalog import source_for
        self.require_session(owner)
        if example not in {entry["id"] for entry in self.qualified}:
            raise DemoError("EXAMPLE_UNAVAILABLE", "This example has not passed installation, execution and replay qualification.", 503)
        if parameters is not None and not isinstance(parameters, dict):
            raise DemoError("INVALID_CONFIGURATION", "Parameters must be a JSON object. Reset the example controls.")
        try:
            source = source_for(example, parameters or {})
        except (ValueError, TypeError, KeyError) as exc:
            raise DemoError("INVALID_CONFIGURATION", str(exc)) from exc
        with self.lock:
            self._prune()
            if self.closing:
                raise DemoError("SHUTTING_DOWN", "The demo is restarting. Reload shortly.", 503)
            if sum(j.owner == owner and j.completed is None for j in self.jobs.values()) >= 2:
                raise DemoError("SESSION_BUSY", "Your session already has two pending runs. Wait or cancel one.", 429)
            if len(self.queue) >= self.limits.max_queued:
                raise DemoError("QUEUE_FULL", "The demo execution queue is full. Wait for a run to complete, then retry.", 429)
            if len(self.jobs) >= self.limits.max_jobs:
                raise DemoError("RESULT_CAPACITY", "The demo has reached its retained run limit. Try again after retention expires.", 503)
            original = None
            if replay_id:
                old = self._owned(owner, replay_id)
                if old.status != "succeeded":
                    raise DemoError("REPLAY_UNAVAILABLE", "Replay requires a successfully retained execution.", 409)
                source, original = deepcopy(old.source), deepcopy(old.bundle)
            job = Job(secrets.token_hex(16), owner, example, source, mode="replay" if replay_id else "execute",
                      original=original, original_id=replay_id)
            self.jobs[job.id] = job
            self.queue.append(job.id)
            self.lock.notify_all()
            return job.public()

    def _owned(self, owner, identity):
        job = self.jobs.get(identity)
        if job is None or job.owner != owner:
            raise DemoError("RUN_NOT_FOUND", "This run is unavailable in your private session. Run the example again.", 404)
        return job

    def get(self, owner, identity):
        self.require_session(owner)
        with self.lock:
            return self._owned(owner, identity).public()

    def replay(self, owner, identity):
        self.require_session(owner)
        with self.lock:
            example = self._owned(owner, identity).example
        return self.submit(owner, example, {}, replay_id=identity)

    def download(self, owner, identity, kind):
        self.require_session(owner)
        with self.lock:
            job = self._owned(owner, identity)
            if kind == "configuration":
                return canonical(job.source), f"net-{job.example}-configuration.json"
            if job.status != "succeeded":
                raise DemoError("EVIDENCE_UNAVAILABLE", "Evidence is available after a successful run. Inspect its status first.", 409)
            return canonical(job.bundle), f"net-{job.example}-{job.id}-evidence.json"

    def cancel(self, owner, identity):
        self.require_session(owner)
        with self.lock:
            job = self._owned(owner, identity)
            if job.status in {"queued", "running"}:
                job.cancel.set()
                if job.status == "queued":
                    self.queue.remove(identity)
                    job.status, job.completed = "cancelled", time.time()
                    job.error = {"code": "CANCELLED", "message": "Execution was cancelled. You can adjust the controls and run again."}
                self.lock.notify_all()
            return job.public()

    def _schedule(self):
        while True:
            with self.lock:
                if self.closing and not self.running:
                    return
                selected = None
                if len(self.running) < self.limits.max_running:
                    active_owners = {self.jobs[key].owner for key in self.running}
                    selected = next((key for key in self.queue if self.jobs[key].owner not in active_owners), None)
                if selected is None:
                    self.lock.wait(timeout=.1)
                    continue
                self.queue.remove(selected)
                self.running.add(selected)
                job = self.jobs[selected]
                job.status, job.started = "running", time.time()
                threading.Thread(target=self._execute, args=(job,), name="net-demo-job", daemon=True).start()

    def _execute(self, job):
        try:
            request = {"mode": "replay", "bundle": job.original} if job.mode == "replay" else {"mode": "execute", "source": job.source}
            response = self._invoke(request, job.cancel)
            self._validate_response(response, job.source)
            if job.mode == "replay" and (response["replay_receipt"] is None or
                    response["replay_receipt"]["source_bundle_digest"] != job.original["bundle_digest"]):
                raise DemoError("REPLAY_INTEGRITY", "Replay did not bind the retained original execution.", 503)
            from .demo_catalog import project
            result = project(response["bundle"], job.example)
            size = len(canonical(response)) + len(canonical(result))
            with self.lock:
                if job.cancel.is_set():
                    raise DemoError("CANCELLED", "Execution was cancelled. Run again when ready.", 409)
                if sum(value.size for value in self.jobs.values()) + size > self.limits.retained_bytes:
                    raise DemoError("RESULT_CAPACITY", "The evidence retention budget is full. Try again after retained runs expire.", 503)
                job.bundle, job.receipt, job.result, job.size = response["bundle"], response["replay_receipt"], result, size
                job.status = "succeeded"
        except DemoError as exc:
            with self.lock:
                job.error = exc.value()
                job.status = "cancelled" if exc.code == "CANCELLED" else "timed_out" if exc.code == "TIMEOUT" else "failed"
        except Exception as exc:
            with self.lock:
                job.status = "failed"
                job.error = {"code": "RESULT_REFUSED", "message": "Result integrity or scientific validation failed. Reset the example and retry."}
            print(f"NET demo result refusal: {type(exc).__name__}", file=sys.stderr)
        finally:
            with self.lock:
                job.original = None
                job.completed = time.time()
                self.running.discard(job.id)
                self.lock.notify_all()

    def _invoke(self, request, cancel):
        limit = self.limits.output_bytes
        raw = canonical(request)
        if len(raw) > limit:
            raise DemoError("INPUT_LIMIT", "The retained execution exceeds the worker input budget.")
        with tempfile.TemporaryDirectory(prefix="net-demo-worker-") as directory:
            with tempfile.TemporaryFile() as stdin:
                stdin.write(raw)
                stdin.seek(0)
                try:
                    process = subprocess.Popen(self.command, cwd=directory, env=sanitized_environment(directory),
                        stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        start_new_session=os.name == "posix")
                except (OSError, ValueError) as exc:
                    raise DemoError("WORKER_UNAVAILABLE", "The installed worker cannot start. Contact the demo operator.", 503) from exc
                chunks, count, count_lock, exceeded = [], [0], threading.Lock(), threading.Event()

                def drain(pipe, retain):
                    try:
                        while chunk := pipe.read1(8192):
                            with count_lock:
                                remaining = max(0, limit - count[0])
                                count[0] += len(chunk)
                                if retain and remaining:
                                    chunks.append(chunk[:remaining])
                                if count[0] > limit:
                                    exceeded.set()
                                    stop_group(process)
                                    break
                    finally:
                        pipe.close()

                readers = [threading.Thread(target=drain, args=(process.stdout, True), daemon=True),
                           threading.Thread(target=drain, args=(process.stderr, False), daemon=True)]
                for reader in readers:
                    reader.start()
                deadline, failure = time.monotonic() + self.limits.wall_seconds, None
                try:
                    while process.poll() is None:
                        if cancel.is_set():
                            failure = DemoError("CANCELLED", "Execution was cancelled. Adjust the controls and run again.", 409)
                            break
                        if time.monotonic() >= deadline:
                            failure = DemoError("TIMEOUT", "The run exceeded its time limit. Reset and retry; if it persists, ask the operator to review execution limits.", 408)
                            break
                        cancel.wait(.03)
                finally:
                    # Also stop descendants if operator shutdown interrupts
                    # qualification, and after a worker exits on its own.
                    stop_group(process)
                    process.wait(timeout=5)
                    for reader in readers:
                        reader.join(timeout=1)
                if failure:
                    raise failure
                if exceeded.is_set():
                    raise DemoError("OUTPUT_LIMIT", "The scientific worker exceeded its output budget. Reset the example and retry.", 503)
                if any(reader.is_alive() for reader in readers):
                    raise DemoError("WORKER_IO", "A worker left an output stream open. Contact the operator.", 503)
                try:
                    response = _json(b"".join(chunks))
                except ValueError as exc:
                    if process.returncode != 0:
                        raise DemoError("WORKER_FAILED", "The scientific worker failed or reached a resource limit. Reset and retry.", 503) from exc
                    raise DemoError("WORKER_RESPONSE", "The worker did not return valid scientific JSON. Contact the operator.", 503) from exc
                if isinstance(response, dict) and response.get("ok") is False:
                    error = response.get("error")
                    if (set(response) != {"ok", "error"} or not isinstance(error, dict) or
                            not isinstance(error.get("code"), str) or
                            re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", error["code"]) is None):
                        raise DemoError("WORKER_RESPONSE", "The worker returned a malformed refusal. Contact the operator.", 503)
                    raise DemoError(error["code"],
                        "The pinned provider refused this run. Reset the example; if it persists, contact the operator.", 503)
                if process.returncode != 0:
                    raise DemoError("WORKER_FAILED", "The scientific worker failed or reached a resource limit. Reset and retry.", 503)
                return response

    def close(self):
        with self.lock:
            self.closing = True
            for job in self.jobs.values():
                if job.completed is None:
                    job.cancel.set()
            for identity in self.queue:
                job = self.jobs[identity]
                job.status, job.completed = "cancelled", time.time()
            self.queue.clear()
            self.lock.notify_all()
        self.scheduler.join(timeout=8)


class DemoHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16

    def __init__(self, address, service, public_origin=None):
        self.service, self.public_origin = service, public_origin
        self.connection_slots = threading.BoundedSemaphore(service.limits.max_http_connections)
        if public_origin:
            parsed = urlsplit(public_origin)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:
                raise ValueError("Public origin must be an exact http(s) origin")
        super().__init__(address, DemoHandler)

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(5)
        return connection, address

    def process_request(self, request, client_address):
        if not self.connection_slots.acquire(blocking=False):
            raw = canonical({"error": {"code": "HTTP_CAPACITY", "message": "The demo is busy. Wait briefly and retry."}})
            try:
                request.sendall(b"HTTP/1.1 503 Service Unavailable\r\nContent-Type: application/json\r\n"
                    b"Cache-Control: no-store\r\nConnection: close\r\nContent-Length: " +
                    str(len(raw)).encode() + b"\r\n\r\n" + raw)
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.connection_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.connection_slots.release()


class DemoHandler(BaseHTTPRequestHandler):
    server_version = "NETDemo/1"

    def log_message(self, format, *args):
        pass

    def _send(self, status, raw, content_type="application/json", *, cookie=None, filename=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        if cookie:
            secure = "; Secure" if (self.server.public_origin or "").startswith("https:") else ""
            self.send_header("Set-Cookie", f"net_demo_session={cookie}; Path=/; HttpOnly; SameSite=Strict{secure}")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _owner(self):
        try:
            cookies = SimpleCookie(self.headers.get("Cookie", ""))
            return cookies["net_demo_session"].value if "net_demo_session" in cookies else None
        except Exception:
            return None

    def _body(self):
        if self.headers.get("Transfer-Encoding"):
            raise DemoError("INVALID_REQUEST", "Chunked request bodies are not supported.")
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise DemoError("INVALID_REQUEST", "Require an explicit JSON content length.") from exc
        if not 0 <= size <= self.server.service.limits.body_bytes:
            raise DemoError("BODY_LIMIT", "The configuration is too large. Use the example controls.", 413)
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            raise DemoError("INVALID_REQUEST", "Send configuration as application/json.", 415)
        raw = self.rfile.read(size)
        if len(raw) != size:
            raise DemoError("INVALID_REQUEST", "The JSON request body was incomplete.")
        try:
            value = _json(raw or b"{}")
        except ValueError as exc:
            raise DemoError("INVALID_JSON", "Require finite JSON with no duplicate keys.") from exc
        if not isinstance(value, dict):
            raise DemoError("INVALID_REQUEST", "Require a JSON object.")
        return value

    def _authorize(self, owner):
        service = self.server.service
        service.require_session(owner)
        expected_origin = self.server.public_origin
        if expected_origin is None:
            host = self.headers.get("Host", "")
            if not re.fullmatch(r"[A-Za-z0-9.\-\[\]:]+", host):
                raise DemoError("ORIGIN_REFUSED", "Reload the demo from its public address.", 403)
            expected_origin = "http://" + host
        if self.headers.get("Origin") != expected_origin:
            raise DemoError("ORIGIN_REFUSED", "Run requests must originate from this demo page.", 403)
        with service.lock:
            expected = service.sessions[owner]["csrf"]
        if not secrets.compare_digest(self.headers.get("X-CSRF-Token", ""), expected):
            raise DemoError("CSRF_REFUSED", "Your request token expired. Reload the demo page.", 403)

    def _handle(self, method):
        service = self.server.service
        path = urlsplit(self.path).path
        try:
            if method == "GET" and path == "/api/health":
                self._send(200 if service.qualified else 503, canonical({"status": "ready" if service.qualified else "unavailable",
                    "qualified_examples": [entry["id"] for entry in service.qualified], "synthetic": True}))
                return
            if method == "GET" and path == "/api/catalog":
                owner, csrf, fresh = service.session(self._owner())
                value = {"examples": deepcopy(service.qualified), "csrf_token": csrf,
                         "limits": asdict(service.limits), "qualification": deepcopy(service.qualification),
                         "synthetic": True, "retention": f"Private ephemeral evidence; expires after {service.limits.retention_seconds:g} seconds or server restart."}
                self._send(200, canonical(value), cookie=owner if fresh else None)
                return
            if path.startswith("/api/"):
                owner = self._owner()
                service.require_session(owner)
                if method == "POST":
                    self._authorize(owner)
                    body = self._body()
                match = re.fullmatch(r"/api/runs/([a-f0-9]{32})(?:/(cancel|replay|evidence|configuration))?", path)
                if method == "POST" and path == "/api/runs":
                    if set(body) != {"example", "parameters"} or not isinstance(body["example"], str) or not isinstance(body["parameters"], dict):
                        raise DemoError("INVALID_REQUEST", "Choose an example and provide its supported parameter object.")
                    value = service.submit(owner, body["example"], body["parameters"])
                    status = 202
                elif match:
                    identity, action = match.groups()
                    if method == "GET" and action in {"evidence", "configuration"}:
                        raw, name = service.download(owner, identity, action)
                        self._send(200, raw, filename=name)
                        return
                    if method == "GET" and action is None:
                        value, status = service.get(owner, identity), 200
                    elif method == "POST" and action in {"cancel", "replay"}:
                        if body:
                            raise DemoError("INVALID_REQUEST", "Cancel and replay require an empty JSON object.")
                        value = service.cancel(owner, identity) if action == "cancel" else service.replay(owner, identity)
                        status = 200 if action == "cancel" else 202
                    else:
                        raise DemoError("NOT_FOUND", "This API operation is unavailable.", 404)
                else:
                    raise DemoError("NOT_FOUND", "This API operation is unavailable.", 404)
                self._send(status, canonical(value))
                return
            assets = {"/": ("demo.html", "text/html; charset=utf-8"),
                      "/demo.js": ("demo.js", "text/javascript; charset=utf-8"),
                      "/demo.css": ("demo.css", "text/css; charset=utf-8")}
            if method == "GET" and path in assets:
                filename, content_type = assets[path]
                self._send(200, (Path(__file__).parent / "web" / filename).read_bytes(), content_type)
                return
            raise DemoError("NOT_FOUND", "This demo page or operation is unavailable.", 404)
        except DemoError as exc:
            self._send(exc.status, canonical({"error": exc.value()}))
        except (TimeoutError, OSError):
            self._send(408, canonical({"error": {"code": "REQUEST_TIMEOUT", "message": "The request was interrupted. Reload and retry."}}))
        except Exception as exc:
            print(f"NET demo HTTP refusal: {type(exc).__name__}", file=sys.stderr)
            self._send(500, canonical({"error": {"code": "SERVER_ERROR", "message": "The demo could not process this request. Contact the operator."}}))

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gsie-repo", required=True)
    parser.add_argument("--jspt-repo", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4173)
    parser.add_argument("--timeout", type=float, default=45)
    parser.add_argument("--public-origin")
    args = parser.parse_args(argv)
    service = DemoService({"gsie": args.gsie_repo, "jspt": args.jspt_repo}, limits=Limits(wall_seconds=args.timeout))
    def terminate(signum, frame):
        raise KeyboardInterrupt
    previous_terminate = signal.signal(signal.SIGTERM, terminate)
    try:
        report = service.qualify()
        print(json.dumps({"qualification": report}, allow_nan=False), flush=True)
        if not service.qualified:
            print("No examples qualified. Install the package and verify pinned provider histories.", file=sys.stderr)
            return 1
        server = DemoHTTPServer((args.host, args.port), service, args.public_origin)
        print(f"NET synthetic demo listening at http://{args.host}:{server.server_port}", flush=True)
        try:
            server.serve_forever(poll_interval=.2)
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    except KeyboardInterrupt:
        return 130
    finally:
        service.close()
        signal.signal(signal.SIGTERM, previous_terminate)


if __name__ == "__main__":
    raise SystemExit(main())
