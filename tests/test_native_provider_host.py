"""Real compiled host conformance; simulated children are marked protocol-only."""
from copy import deepcopy
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import time

import pytest

from execution.commitments import (commit_hex, PROGRAM_TAG, INPUT_TAG, OUTPUT_TAG,
                                   SPECIFICATION_TAG, COMPUTATION_TAG, canonical_u32)


@pytest.fixture(scope="module")
def host():
    supplied = os.environ.get("SCR_PROVIDER_HOST")
    if not supplied or not Path(supplied).is_file():
        if os.environ.get("SCR_NATIVE_REQUIRED") == "1":
            pytest.fail("Required compiled SCR_PROVIDER_HOST is unavailable")
        pytest.skip("set SCR_PROVIDER_HOST to the compiled native provider host")
    return Path(supplied).resolve()


def frame(value):
    raw = value if isinstance(value, bytes) else json.dumps(value, separators=(",", ":")).encode()
    return struct.pack(">I", len(raw)) + raw


def decode(raw):
    out = []
    while raw:
        assert len(raw) >= 4
        length = struct.unpack(">I", raw[:4])[0]
        assert 0 < length <= 4_194_304 and len(raw) >= 4 + length
        out.append(json.loads(raw[4:4 + length]))
        raw = raw[4 + length:]
    return out


def affine(request_id="req-1", exact=False):
    return {"schema": "ciw.native-interop-request.v1", "request_id": request_id,
            "parent_execution_id": "parent-1", "profile": "affine-d256.v1" if exact else "affine-binary64.v1",
            "arithmetic": "exact-d256" if exact else "binary64",
            "semantics": {"layout": "row-major", "input_units": "dimensionless", "output_units": "dimensionless",
                          "frame": "declared-cartesian", "clock": "not-applicable"},
            "payload": {"rows": 2, "columns": 3,
                        "a_row_major": [512, 256, -256, -256, 768, 512] if exact else [2, 1, -1, -1, 3, 2],
                        "b": [1280, -512] if exact else [5, -2],
                        "x0": [768, 1024, 512] if exact else [3, 4, 2],
                        "delta_x": [64, -128, 32] if exact else [0.25, -0.5, 0.125]}}


def invoke(host, messages, args=()):
    raw = b"".join(frame(m) for m in messages)
    run = subprocess.run([str(host), *args], input=raw, capture_output=True, timeout=20)
    return run, decode(run.stdout)


def assert_identities(result):
    h = result["host"]
    program, config, source, output = (bytes.fromhex(h[k]) for k in
                                      ("program_bytes_hex", "configuration_bytes_hex", "input_bytes_hex", "output_bytes_hex"))
    assert h["program_id"] == commit_hex(PROGRAM_TAG, [program])
    assert h["input_id"] == commit_hex(INPUT_TAG, [source])
    assert h["output_id"] == commit_hex(OUTPUT_TAG, [output])
    assert h["specification_id"] == commit_hex(SPECIFICATION_TAG, [program, config, source])
    assert h["computation_id"] == commit_hex(COMPUTATION_TAG, [bytes.fromhex(h["program_id"]),
             bytes.fromhex(h["input_id"]), bytes.fromhex(h["output_id"]), canonical_u32(0)])
    assert json.loads(output) == result["data"]
    assert json.loads(program) == {"profile": result["profile"], "runtime": h["provider_runtime"]}
    assert h["proof"] is None


def test_real_cpp_a_b_a_restart_and_identity_separation(host):
    a, b, again = affine(), affine("req-2"), affine("req-3")
    b["payload"]["b"] = [0, 0]
    run, results = invoke(host, [a, b, again], ["--provider", "cpp"])
    assert run.returncode == 0, run.stderr.decode()
    assert [r["host"]["occurrence"] for r in results] == [0, 1, 2]
    assert results[0]["data"] == results[2]["data"]
    assert results[0]["data"]["model_output"] == [12.875, 9.5]
    assert results[1]["data"]["model_output"] == [7.875, 11.5]
    for result in results:
        assert_identities(result)
    assert results[0]["host"]["specification_id"] == results[2]["host"]["specification_id"]
    assert results[0]["host"]["specification_id"] != results[1]["host"]["specification_id"]
    restarted, other = invoke(host, [affine("restart")], ["--provider", "cpp"])
    assert restarted.returncode == 0
    assert other[0]["data"] == results[0]["data"]
    assert other[0]["host"]["process_id"] != results[0]["host"]["process_id"]
    assert other[0]["host"]["computation_id"] == results[0]["host"]["computation_id"]


def test_real_cpp_exact_values_and_domain_refusal_have_no_false_output(host):
    bad = affine("bad", exact=True)
    bad["payload"]["x0"][0] = 4097
    run, results = invoke(host, [affine(exact=True), bad], ["--provider", "cpp"])
    assert run.returncode == 0
    assert results[0]["data"]["model_output"] == [843776, 622592]
    assert results[0]["data"]["denominator"] == 65536
    assert_identities(results[0])
    assert results[1]["status"] == "refused"
    assert results[1]["host"]["status"] == "halted"
    assert results[1]["host"]["output_id"] is None
    assert results[1]["host"]["computation_id"] is None


def test_real_cpp_force_energy_nonunit_mass(host):
    request = affine()
    request.update(profile="oscillator-force-energy.v1", semantics={"layout": "row-major", "input_units": "SI",
                   "output_units": "SI", "frame": "one-dimensional-inertial", "clock": "declared-simulation-time"},
                   payload={"model": {"mass_kg": 2, "omega_0_rad_s": 2, "gamma_s_inv": 0.1},
                            "time_s": [0], "q_m": [1], "v_m_s": [-0.25]})
    run, results = invoke(host, [request], ["--provider", "cpp"])
    assert run.returncode == 0
    assert results[0]["data"]["energy_j"] == [4.0625]
    assert results[0]["data"]["acceleration_m_s2"] == [-3.95]
    assert_identities(results[0])


@pytest.mark.parametrize("raw", [b"\0", b"\0\0\0\x03a", b"\0\0\0\0", b"\xff\xff\xff\xff",
                                 frame(b'{"schema":"a","schema":"b"}'), frame(b'{"x":NaN}')])
def test_compiled_host_refuses_bad_frames_and_json(host, raw):
    run = subprocess.run([str(host), "--provider", "cpp"], input=raw, capture_output=True, timeout=10)
    assert run.returncode == 2 and not run.stdout
    assert b"refused" in run.stderr


def test_duplicate_transport_id_stops_stream_before_second_execution(host):
    run, results = invoke(host, [affine(), affine()], ["--provider", "cpp"])
    assert run.returncode == 2
    assert len(results) == 1
    assert b"repeated request ID" in run.stderr


@pytest.fixture(scope="module")
def protocol_child(tmp_path_factory):
    rustc = shutil.which("rustc")
    if not rustc:
        pytest.fail("Rust compiler required for protocol-only child fixture")
    root = tmp_path_factory.mktemp("fixture")
    executable = root / ("fixture.exe" if os.name == "nt" else "fixture")
    subprocess.run([rustc, str(Path(__file__).with_name("native_host_fixture.rs")), "-o", str(executable)], check=True,
                   capture_output=True, timeout=60)
    return executable


def fixture_args(tmp_path, executable, mode, timeout=2000):
    project = tmp_path / "native-interop"
    project.mkdir()
    (project / "Project.toml").write_text("[deps]\n")
    (project / "Manifest.toml").write_text("# protocol-only fixture\n")
    (project / "worker.jl").write_text(mode)
    old = tmp_path / "julia-oscillator"
    old.mkdir()
    (old / "oscillator_worker.jl").write_text("# fixture, never interpreted as Julia\n")
    return ["--provider", "julia", "--julia", str(executable), "--project", str(project),
            "--worker", str(project / "worker.jl"), "--timeout-ms", str(timeout)]


@pytest.mark.parametrize("mode", ["stale", "timeout", "stderr", "truncated", "crash"])
def test_child_protocol_failure_is_bounded_reaped_and_cannot_be_reused(host, protocol_child, tmp_path, mode):
    args = fixture_args(tmp_path, protocol_child, mode, timeout=500)
    started = time.monotonic()
    run, results = invoke(host, [affine(), affine("late-request")], args)
    assert time.monotonic() - started < 10
    assert run.returncode == 2
    assert len(results) == 1
    assert results[0]["status"] == "refused"
    assert results[0]["host"]["output_id"] is None
    assert results[0]["host"]["computation_id"] is None
    assert len(bytes.fromhex(results[0]["host"]["child_stderr_hex"])) <= 65536


@pytest.mark.skipif(os.name != "nt", reason="Windows JobObject lifetime conformance")
def test_windows_child_dies_when_outer_host_is_killed(host, protocol_child, tmp_path):
    args = fixture_args(tmp_path, protocol_child, "linger")
    parent = subprocess.Popen([str(host), *args], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        parent.stdin.write(frame(affine()))
        parent.stdin.flush()
        header = parent.stdout.read(4)
        assert len(header) == 4, parent.stderr.read().decode()
        result = json.loads(parent.stdout.read(struct.unpack(">I", header)[0]))
        pid = result["host"]["child_process_id"]
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x00100000, 0, pid)
        assert handle
        try:
            parent.kill()
            parent.wait(timeout=5)
            assert kernel.WaitForSingleObject(handle, 5000) == 0
        finally:
            kernel.CloseHandle(handle)
    finally:
        if parent.poll() is None:
            parent.kill()
        parent.wait(timeout=5)


def test_genuine_julia_affine_control_tsit5_qp_and_cpp_trajectory_link(host):
    """No substitute worker: requires an explicitly provisioned Julia environment."""
    executable, project = os.environ.get("SCR_JULIA_EXE"), os.environ.get("SCR_JULIA_PROJECT")
    if not executable or not project:
        if os.environ.get("SCR_NATIVE_REQUIRE_JULIA") == "1":
            pytest.fail("required genuine Julia paths are not configured")
        pytest.skip("set SCR_JULIA_EXE and SCR_JULIA_PROJECT for genuine Julia integration")
    import math
    a, b, again, exact = affine("a"), affine("b"), affine("again"), affine("exact", exact=True)
    b["payload"]["b"] = [0, 0]
    physical = {"layout": "row-major", "input_units": "SI", "output_units": "SI",
                "frame": "one-dimensional-inertial", "clock": "declared-simulation-time"}
    model = {"mass_kg": 2.0, "omega_0_rad_s": 2.0, "gamma_s_inv": 0.1}
    times = [i / 10 for i in range(11)]
    osc = affine("tsit5")
    osc.update(profile="oscillator-tsit5.v1", semantics=physical,
               payload={"model": model, "initial_state": {"q0_m": 1.0, "v0_m_s": -0.25}, "time_s": times,
                        "solver": {"abstol": 1e-10, "reltol": 1e-10, "maxiters": 100000}})
    control = deepcopy(osc)
    control.update(request_id="control", profile="control-oscillator.v1")
    control["payload"].pop("solver")
    qp = affine("qp-interior")
    qp.update(profile="design-qp.v1", payload={"rows": 2, "columns": 2, "j_row_major": [2, 1, -1, 3],
              "y0": [1, -2], "target": [0, 0], "regularization": 1, "lower": [-1, -1],
              "upper": [1, 1], "max_iterations": 10000})
    active = deepcopy(qp)
    active["request_id"] = "qp-active"
    active["payload"].update(j_row_major=[1, 0, 0, 1], y0=[2, -2], lower=[-0.5, -0.5], upper=[0.5, 0.5])
    rectangular = deepcopy(qp)
    rectangular["request_id"] = "qp-rectangular"
    rectangular["payload"].update(rows=1, j_row_major=[1, 1], y0=[2], target=[0])
    requests = [a, b, again, exact, osc, control, qp, active, rectangular]
    arguments = [str(host), "--provider", "julia", "--julia", executable, "--project", project,
                 "--worker", str(Path(project) / "worker.jl"), "--timeout-ms", "300000"]
    raw_input = b"".join(frame(r) for r in requests)
    run = subprocess.run(arguments, input=raw_input, capture_output=True, timeout=360)
    assert run.returncode == 0, run.stderr.decode()
    results = decode(run.stdout)
    assert len(results) == len(requests)
    for index, result in enumerate(results):
        assert result["status"] == "ok", result
        assert result["host"]["child_occurrence"] == index
        assert bytes.fromhex(result["host"]["child_request_bytes_hex"]) == frame(requests[index])[4:]
        child = json.loads(bytes.fromhex(result["host"]["child_response_bytes_hex"]))
        outer = {k: v for k, v in result.items() if k != "host"}
        # Type/value exact transport preservation, not a numerical tolerance.
        assert json.dumps(child, sort_keys=True) == json.dumps(outer, sort_keys=True)
        assert_identities(result)
    assert len({r["host"]["child_process_id"] for r in results}) == 1
    assert results[0]["data"] == results[2]["data"]
    assert results[0]["data"]["model_output"] == [12.875, 9.5]
    assert results[3]["data"]["model_output"] == [843776, 622592]
    omega = math.sqrt(4.0 - 0.01)
    expected_q, expected_v = [], []
    for t in times:
        c, s, scale = math.cos(omega * t), math.sin(omega * t), math.exp(-0.1 * t)
        q = scale * (c - 0.15 / omega * s)
        v = scale * (-0.1 * (c - 0.15 / omega * s) - omega * s - 0.15 * c)
        expected_q.append(q)
        expected_v.append(v)
    for index in [4, 5]:
        assert results[index]["data"]["q_m"] == pytest.approx(expected_q, abs=2e-8)
        assert results[index]["data"]["v_m_s"] == pytest.approx(expected_v, abs=2e-8)
    assert results[6]["data"]["delta"] == pytest.approx([-0.6, 0.4], abs=2e-8)
    assert results[6]["data"]["objective_value"] == pytest.approx(0.3, abs=2e-8)
    assert results[7]["data"]["delta"] == pytest.approx([-0.5, 0.5], abs=2e-8)
    assert results[7]["data"]["objective_value"] == pytest.approx(2.5, abs=2e-8)
    assert results[8]["data"]["delta"] == pytest.approx([-2 / 3, -2 / 3], abs=1e-7)
    assert results[8]["data"]["objective_value"] == pytest.approx(2 / 3, abs=2e-8)
    trajectory = results[4]["data"]
    force = affine("force-from-tsit5")
    force.update(profile="oscillator-force-energy.v1", semantics=physical,
                 parent_execution_id="tsit5-linked-parent",
                 payload={"model": model, "time_s": times, "q_m": trajectory["q_m"], "v_m_s": trajectory["v_m_s"]})
    cpp, evaluated = invoke(host, [force], ["--provider", "cpp"])
    assert cpp.returncode == 0
    assert evaluated[0]["data"]["energy_j"] == pytest.approx(trajectory["energy_j"], abs=1e-12)
    for q, v, actual in zip(trajectory["q_m"], trajectory["v_m_s"], evaluated[0]["data"]["acceleration_m_s2"]):
        assert actual == pytest.approx(-4 * q - 0.2 * v, abs=1e-12)
    # A fresh process has a distinct child occurrence while preserving computation identity.
    restarted = subprocess.run(arguments, input=frame(affine("restart")), capture_output=True, timeout=120)
    assert restarted.returncode == 0
    repeated = decode(restarted.stdout)[0]
    assert repeated["data"] == results[0]["data"]
    assert repeated["host"]["child_process_id"] != results[0]["host"]["child_process_id"]
    assert repeated["host"]["computation_id"] == results[0]["host"]["computation_id"]
    destination = os.environ.get("SCR_NATIVE_EVIDENCE_DIR")
    if destination:
        out = Path(destination)
        out.mkdir(parents=True, exist_ok=True)
        (out / "genuine-julia-requests.bin").write_bytes(raw_input)
        (out / "genuine-julia-responses.bin").write_bytes(run.stdout)
        (out / "genuine-julia-stderr.txt").write_bytes(run.stderr)
        (out / "genuine-linked-checks.json").write_text(json.dumps({"julia": results, "cpp_trajectory": evaluated,
                "restart": repeated, "scope": "numerical and process conformance; no proof or physical validation"}, indent=2))
