"""Real native executions plus bounded worker, session and HTTP fault paths."""
from copy import deepcopy
import http.client
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time

import pytest

from ciw.demo_server import DemoError, DemoHTTPServer, DemoService, Limits
from ciw.sensor_fusion_ekf_workflow import SensorFusionEKFWorkflow
from ciw.telemetry import canonical
from scripts.prepare_web_demo import prepare_providers

ROOT = Path(__file__).resolve().parents[1]


def proc_directory(pid):
    """Resolve namespace PIDs when the runner mounts the host's /proc tree."""
    if Path("/proc/self/stat").read_text().split()[0] == str(os.getpid()):
        path = Path(f"/proc/{pid}")
        return path if path.exists() else None
    namespace = os.readlink("/proc/self/ns/pid")
    for status in Path("/proc").glob("[0-9]*/status"):
        try:
            if os.readlink(status.parent / "ns/pid") != namespace:
                continue
            lines = status.read_text().splitlines()
            identity = next((line.split()[1:] for line in lines if line.startswith("NSpid:")), [])
            if identity and int(identity[-1]) == pid:
                return status.parent
        except (OSError, ValueError):
            continue
    return None


def wait_job(service, owner, identity, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = service.get(owner, identity)
        if value["status"] not in {"queued", "running"}:
            return value
        time.sleep(.025)
    raise AssertionError("Worker did not reach a terminal status")


@pytest.fixture(scope="module")
def providers(tmp_path_factory):
    # Export and audit original pinned provider objects without claiming that
    # uncommitted demo authoring bytes are an already qualified Git revision.
    bindings = prepare_providers(tmp_path_factory.mktemp("demo-providers"))
    return {role: item["repository_root"] for role, item in bindings.items()}


@pytest.fixture(scope="module")
def qualified(providers):
    service = DemoService(providers)
    report = service.qualify()
    assert {item["example"] for item in report if item["outcome"] == "passed"} == {"metrology", "thermal", "range"}, report
    yield service
    service.close()


@pytest.mark.parametrize("example", ["metrology", "thermal", "range"])
def test_native_run_export_replay_preserves_distinct_occurrences(qualified, example):
    owner, _, _ = qualified.session()
    submitted = qualified.submit(owner, example, {"measurement_scale": 1.25})
    completed = wait_job(qualified, owner, submitted["id"])
    assert completed["status"] == "succeeded", completed
    raw, filename = qualified.download(owner, submitted["id"], "evidence")
    original = json.loads(raw)
    assert filename.endswith("-evidence.json")
    SensorFusionEKFWorkflow()._validate(original)
    configuration, _ = qualified.download(owner, submitted["id"], "configuration")
    assert json.loads(configuration) == original["steps"][0]["request"]
    replay = qualified.replay(owner, submitted["id"])
    fresh = wait_job(qualified, owner, replay["id"])
    assert fresh["status"] == "succeeded", fresh
    receipt = fresh["replay_receipt"]
    assert receipt["numerical_match"] is True
    assert receipt["source_bundle_digest"] == original["bundle_digest"]
    assert receipt["admission"] == "not_performed"
    new_raw, _ = qualified.download(owner, replay["id"], "evidence")
    new = json.loads(new_raw)
    assert original["steps"][0]["execution_id"] != new["steps"][0]["execution_id"]
    assert original["verification"]["verification_id"] != new["verification"]["verification_id"]
    assert qualified.download(owner, submitted["id"], "evidence")[0] == raw
    assert original["steps"][0]["numerical_result"] == new["steps"][0]["numerical_result"]
    assert original["steps"][0]["operation_id"] == "ciw.sensor-fusion-ekf.v1"


def test_invalid_configuration_never_reaches_worker_and_owner_isolation(qualified):
    first, _, _ = qualified.session()
    second, _, _ = qualified.session()
    with pytest.raises(DemoError) as error:
        qualified.submit(first, "metrology", {"measurement_scale": 0})
    assert error.value.code == "INVALID_CONFIGURATION"
    with pytest.raises(DemoError):
        qualified.submit(first, "metrology", {"provider_path": "/tmp/untrusted"})
    with pytest.raises(DemoError):
        qualified.submit(first, "unknown", {})
    job = qualified.submit(first, "metrology", {})
    for call in (lambda: qualified.get(second, job["id"]),
                 lambda: qualified.cancel(second, job["id"]),
                 lambda: qualified.replay(second, job["id"]),
                 lambda: qualified.download(second, job["id"], "configuration")):
        with pytest.raises(DemoError) as error:
            call()
        assert error.value.status == 404
    qualified.cancel(first, job["id"])
    wait_job(qualified, first, job["id"])


def test_native_bundle_tamper_refused_before_retained_replay(qualified):
    owner, _, _ = qualified.session()
    job = qualified.submit(owner, "range", {})
    assert wait_job(qualified, owner, job["id"])["status"] == "succeeded"
    native = qualified.jobs[job["id"]].bundle
    damaged = deepcopy(native)
    damaged["steps"][0]["result"]["data"]["estimates"][0]["mean"][0] += 1
    with pytest.raises(ValueError):
        SensorFusionEKFWorkflow()._validate(damaged)


def fake_service(code, **limits):
    service = DemoService({"gsie": ROOT, "jspt": ROOT}, limits=Limits(**limits),
                          worker_command=[sys.executable, "-I", "-c", code])
    service.qualified = [{"id": "metrology"}]
    return service


@pytest.mark.parametrize(("code", "expected"), [
    ("import sys;sys.stdout.write('not-json')", "WORKER_RESPONSE"),
    ("import sys;sys.exit(3)", "WORKER_FAILED"),
    ("import json;print(json.dumps({'ok':False,'error':{'code':'SOURCE_PIN_MISMATCH'}}))", "SOURCE_PIN_MISMATCH"),
    ("print('{\"ok\":false,\"error\":null}')", "WORKER_RESPONSE"),
    ("print('{\"ok\":false,\"error\":[]}')", "WORKER_RESPONSE"),
    ("print('{\"ok\":false,\"error\":{\"code\":[]}}')", "WORKER_RESPONSE"),
    ("print('{\"ok\":false,\"error\":{\"code\":123}}')", "WORKER_RESPONSE"),
    ("print('{\"ok\":false,\"error\":{}}')", "WORKER_RESPONSE"),
    ("import sys;sys.stdout.write('x'*10000)", "OUTPUT_LIMIT"),
    ("import time;time.sleep(10)", "TIMEOUT"),
])
def test_bounded_worker_provider_failure_bad_output_and_deadline(code, expected):
    service = fake_service(code, wall_seconds=.2, output_bytes=1024)
    try:
        with pytest.raises(DemoError) as error:
            service._invoke({"mode": "execute", "source": {}}, threading.Event())
        assert error.value.code == expected
    finally:
        service.close()


def test_worker_environment_does_not_inherit_credentials_or_python_paths(monkeypatch):
    monkeypatch.setenv("NET_DEMO_TEST_SECRET", "private")
    monkeypatch.setenv("PYTHONPATH", "/tmp/untrusted")
    monkeypatch.setenv("GIT_DIR", "/tmp/untrusted")
    service = fake_service("import os,json;print(json.dumps({k:os.getenv(k) for k in ['NET_DEMO_TEST_SECRET','PYTHONPATH','GIT_DIR','OPENBLAS_NUM_THREADS']}))")
    try:
        value = service._invoke({}, threading.Event())
        assert value == {"NET_DEMO_TEST_SECRET": None, "PYTHONPATH": None, "GIT_DIR": None, "OPENBLAS_NUM_THREADS": "1"}
    finally:
        service.close()


def test_running_cancel_queued_cancel_and_concurrent_session_limits():
    service = fake_service("import time;time.sleep(10)", max_queued=2, wall_seconds=5)
    try:
        owner, _, _ = service.session()
        other, _, _ = service.session()
        first = service.submit(owner, "metrology", {})
        deadline = time.monotonic() + 2
        while service.get(owner, first["id"])["status"] != "running" and time.monotonic() < deadline:
            time.sleep(.01)
        queued = service.submit(owner, "metrology", {})
        separate = service.submit(other, "metrology", {})
        while service.get(other, separate["id"])["status"] != "running" and time.monotonic() < deadline:
            time.sleep(.01)
        assert service.get(owner, queued["id"])["status"] == "queued"
        assert len(service.running) == 2
        with pytest.raises(DemoError) as error:
            service.submit(owner, "metrology", {})
        assert error.value.code == "SESSION_BUSY"
        assert service.cancel(owner, queued["id"])["status"] == "cancelled"
        service.cancel(owner, first["id"])
        assert wait_job(service, owner, first["id"], 3)["status"] == "cancelled"
        service.cancel(other, separate["id"])
        assert wait_job(service, other, separate["id"], 3)["status"] == "cancelled"
    finally:
        service.close()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux /proc and resource-limit containment")
@pytest.mark.parametrize("cancelled", [False, True])
def test_timeout_and_cancel_stop_provider_descendants_even_if_they_request_own_session(tmp_path, cancelled):
    pid_path = tmp_path / "provider.pid"
    # Same trusted worker containment used by the real providers. Their normal
    # request for a new session is overridden so the outer group owns them.
    script = f"""from ciw.demo_worker import install_limits
install_limits(3,512,1024*1024)
import os,subprocess,sys,time
p=subprocess.Popen([sys.executable,'-I','-c','import time;time.sleep(20)'], start_new_session=True)
open({str(pid_path)!r},'w').write(str(p.pid)+':'+str(os.getpgid(p.pid))+':'+str(os.getpgrp()))
time.sleep(20)
"""
    service = fake_service(script, wall_seconds=.5)
    event = threading.Event()
    error = []
    def invoke():
        try:
            service._invoke({}, event)
        except DemoError as exc:
            error.append(exc.code)
    thread = threading.Thread(target=invoke)
    thread.start()
    try:
        deadline = time.monotonic() + 2
        while not pid_path.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        assert pid_path.exists()
        pid, child_group, worker_group = map(int, pid_path.read_text().split(":"))
        assert child_group == worker_group
        child_proc = proc_directory(pid)
        assert child_proc is not None and (child_proc / "stat").read_text().split()[2] != "Z"
        if cancelled:
            event.set()
        thread.join(timeout=3)
        assert error == ["CANCELLED" if cancelled else "TIMEOUT"]
        stat = child_proc / "stat"
        # Adopted zombies are no longer executing and cannot retain resources;
        # container PID 1 owns final reaping when the parent group is killed.
        assert not stat.exists() or stat.read_text().split()[2] == "Z"
    finally:
        event.set()
        thread.join(timeout=3)
        service.close()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux /proc and SIGTERM lifecycle")
def test_sigterm_during_real_startup_qualification_cleans_worker(providers):
    process = subprocess.Popen([sys.executable, "-I", "-m", "ciw.demo_server",
        "--gsie-repo", providers["gsie"], "--jspt-repo", providers["jspt"], "--port", "0"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    children = []
    try:
        deadline = time.monotonic() + 5
        parent_proc = proc_directory(process.pid)
        assert parent_proc is not None
        while time.monotonic() < deadline and not children:
            # Some managed kernels omit /proc/PID/task/TID/children. PPid in
            # status is available and uses the same namespace as the mount.
            for status in Path("/proc").glob("[0-9]*/status"):
                try:
                    parent = next((line.split()[1] for line in status.read_text().splitlines()
                                   if line.startswith("PPid:")), None)
                    if parent == parent_proc.name:
                        children.append(status.parent)
                except OSError:
                    continue
            time.sleep(.01)
        if not children:
            process.send_signal(signal.SIGTERM)
            stdout, stderr = process.communicate(timeout=8)
            pytest.fail(f"Real startup worker was not observed: exit={process.returncode}; stdout={stdout!r}; stderr={stderr!r}")
        process.send_signal(signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=8)
        assert process.returncode == 130, (stdout, stderr)
        for child in children:
            stat = child / "stat"
            assert not stat.exists() or stat.read_text().split()[2] == "Z"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux process resource limits")
def test_worker_cpu_and_file_resource_limits(tmp_path):
    cpu = fake_service("from ciw.demo_worker import install_limits;install_limits(1,512,1024);exec('while True: pass')", wall_seconds=4)
    try:
        with pytest.raises(DemoError) as error:
            cpu._invoke({}, threading.Event())
        assert error.value.code == "WORKER_FAILED"
    finally:
        cpu.close()
    files = fake_service("from ciw.demo_worker import install_limits;install_limits(2,512,1024);f=open('oversize','wb');f.write(b'x'*2048);f.flush()")
    try:
        with pytest.raises(DemoError) as error:
            files._invoke({}, threading.Event())
        assert error.value.code == "WORKER_FAILED"
    finally:
        files.close()
    memory = fake_service("from ciw.demo_worker import install_limits;install_limits(2,256,1024);x=bytearray(512*1024*1024)")
    try:
        with pytest.raises(DemoError) as error:
            memory._invoke({}, threading.Event())
        assert error.value.code == "WORKER_FAILED"
    finally:
        memory.close()


def test_failed_qualification_never_exposes_example():
    service = fake_service("import json;print(json.dumps({'ok':False,'error':{'code':'SOURCE_PIN_MISMATCH'}}))")
    service.qualified = []
    try:
        report = service.qualify()
        assert len(report) == 3 and all(item["outcome"] == "failed" for item in report)
        assert service.qualified == []
        owner, _, _ = service.session()
        with pytest.raises(DemoError) as error:
            service.submit(owner, "metrology", {})
        assert error.value.code == "EXAMPLE_UNAVAILABLE"
    finally:
        service.close()


@pytest.mark.parametrize("refusal", ["not-json", '{"ok":false,"error":null}', '{"ok":false,"error":[]}'])
def test_malformed_worker_refusal_marks_qualification_unavailable(refusal):
    service = fake_service(f"print({refusal!r})")
    service.qualified = []
    try:
        report = service.qualify()
        assert len(report) == 3
        assert all(item["outcome"] == "failed" and item["error"]["code"] == "WORKER_RESPONSE" for item in report)
        assert service.qualified == []
    finally:
        service.close()


def test_qualification_requires_receipt_binding_to_the_execution_it_qualified(monkeypatch):
    service = fake_service("import sys;sys.exit(1)")
    service.qualified = []
    # The native verifier checks each complete bundle independently. This fault
    # isolates the orchestration boundary: a coherent receipt for another
    # retained execution must not qualify the first execution.
    responses = iter([{"bundle": {"bundle_digest": "original"}},
                      {"replay_receipt": {"numerical_match": True, "source_bundle_digest": "unrelated"}}] * 3)
    monkeypatch.setattr(service, "_invoke", lambda request, cancel: next(responses))
    monkeypatch.setattr(service, "_validate_response", lambda response, source: None)
    try:
        report = service.qualify()
        assert len(report) == 3
        assert all(item["outcome"] == "failed" and item["error"]["code"] == "QUALIFICATION_REPLAY" for item in report)
        assert service.qualified == []
    finally:
        service.close()


def test_retained_job_count_capacity_does_not_evict_other_evidence():
    service = fake_service("import json;print(json.dumps({'ok':False,'error':{'code':'SOURCE_PIN_MISMATCH'}}))", max_jobs=1)
    try:
        owner, _, _ = service.session()
        job = service.submit(owner, "metrology", {})
        assert wait_job(service, owner, job["id"])["status"] == "failed"
        with pytest.raises(DemoError) as error:
            service.submit(owner, "metrology", {})
        assert error.value.code == "RESULT_CAPACITY"
        assert service.get(owner, job["id"])["status"] == "failed"
    finally:
        service.close()


def test_http_connection_capacity_is_bounded():
    service = fake_service("import sys;sys.exit(1)", max_http_connections=1)
    server = DemoHTTPServer(("127.0.0.1", 0), service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    slow = socket.create_connection(("127.0.0.1", server.server_port), timeout=2)
    try:
        slow.sendall(b"GET /api/health HTTP/1.1\r\n")
        time.sleep(.05)
        other = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
        other.request("GET", "/api/health")
        response = other.getresponse()
        assert response.status == 503
        assert json.loads(response.read())["error"]["code"] == "HTTP_CAPACITY"
        other.close()
    finally:
        slow.close()
        server.shutdown()
        server.server_close()
        service.close()
        thread.join(timeout=2)


def test_queue_retention_session_and_result_capacity_are_bounded():
    service = fake_service("import time;time.sleep(10)", max_queued=1, max_jobs=3, max_sessions=3, retention_seconds=.08)
    try:
        owners = [service.session()[0] for _ in range(3)]
        with pytest.raises(DemoError) as error:
            service.session()
        assert error.value.code == "SESSION_CAPACITY"
        first = service.submit(owners[0], "metrology", {})
        deadline = time.monotonic() + 1
        while len(service.running) < 1 and time.monotonic() < deadline:
            time.sleep(.005)
        second = service.submit(owners[1], "metrology", {})
        while len(service.running) < 2 and time.monotonic() < deadline:
            time.sleep(.005)
        queued = service.submit(owners[2], "metrology", {})
        with pytest.raises(DemoError) as error:
            service.submit(owners[0], "metrology", {})
        assert error.value.code == "QUEUE_FULL"
        for owner, job in zip(owners, [first, second, queued]):
            service.cancel(owner, job["id"])
            wait_job(service, owner, job["id"], 3)
        time.sleep(.12)
        with pytest.raises(DemoError) as error:
            service.get(owners[0], first["id"])
        assert error.value.code == "SESSION_EXPIRED"
        assert len(service.jobs) == 0
    finally:
        service.close()


def test_http_origin_csrf_body_limits_and_cross_session_access(qualified):
    server = DemoHTTPServer(("127.0.0.1", 0), qualified)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    origin = f"http://127.0.0.1:{server.server_port}"
    try:
        connection.request("GET", "/api/catalog")
        response = connection.getresponse()
        cookie = response.getheader("Set-Cookie")
        assert "HttpOnly" in cookie and "SameSite=Strict" in cookie
        catalog = json.loads(response.read())
        headers = {"Cookie": cookie.split(";")[0], "Origin": origin,
                   "X-CSRF-Token": catalog["csrf_token"], "Content-Type": "application/json"}
        payload = json.dumps({"example": "thermal", "parameters": {}})
        for change, expected in [({"Origin": "https://untrusted.example"}, "ORIGIN_REFUSED"),
                                 ({"X-CSRF-Token": "invalid"}, "CSRF_REFUSED")]:
            connection.request("POST", "/api/runs", payload, {**headers, **change})
            response = connection.getresponse()
            assert response.status == 403
            assert json.loads(response.read())["error"]["code"] == expected
        connection.request("POST", "/api/runs", "x" * (qualified.limits.body_bytes + 1), headers)
        response = connection.getresponse()
        assert response.status == 413
        response.read()
        connection.request("POST", "/api/runs", payload, headers)
        response = connection.getresponse()
        assert response.status == 202
        job = json.loads(response.read())
        other = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        other.request("GET", "/api/catalog")
        response = other.getresponse()
        other_cookie = response.getheader("Set-Cookie").split(";")[0]
        response.read()
        other.request("GET", f'/api/runs/{job["id"]}', headers={"Cookie": other_cookie})
        response = other.getresponse()
        assert response.status == 404
        response.read()
        other.close()
        owner = headers["Cookie"].split("=", 1)[1]
        qualified.cancel(owner, job["id"])
        wait_job(qualified, owner, job["id"])
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
