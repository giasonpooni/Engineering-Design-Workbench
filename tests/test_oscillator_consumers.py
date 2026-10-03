"""Consumer boundary tests. The local native fixture is explicitly hand-lowered.

Only the real CI qualification gate establishes Julia-generated C/Godot execution.
"""
from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def gate():
    spec = importlib.util.spec_from_file_location("consumer_gate_test", ROOT / "scripts/check_oscillator_consumers.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def native(tmp_path_factory):
    if sys.platform != "linux" or not shutil.which("gcc") or not shutil.which("g++"):
        pytest.skip("Linux GCC/G++ required for the explicitly hand-lowered ABI fixture")
    directory = tmp_path_factory.mktemp("cpp-consumer-fixture")
    source = ROOT / "runtimes/julia-oscillator-kernel"
    digest = sha256((source / "oscillator.jl").read_bytes()).hexdigest()
    # A test fixture, NOT output attributed to a Julia exporter execution.
    c = (source / "abi.c.in").read_text().replace("@SOURCE_SHA256@", digest).replace("@RHS_Q@", "v")
    c = c.replace("@RHS_V@", "(((-2.0 * gamma) * v) - ((omega * omega) * q))")
    (directory / "fixture.c").write_text(c)
    subprocess.run([shutil.which("gcc"), "-std=c11", "-O2", "-fno-fast-math", "-ffp-contract=off",
        "-shared", "-fPIC", str(directory / "fixture.c"), "-o", str(directory / "libciw_oscillator_kernel.so"), "-lm"],
        capture_output=True, check=True, timeout=30)
    binary = directory / "cpp-probe"
    subprocess.run([shutil.which("g++"), "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
        str(source / "cpp_probe.cpp"), "-L" + str(directory), "-lciw_oscillator_kernel", "-Wl,-rpath,$ORIGIN", "-o", str(binary)],
        capture_output=True, check=True, timeout=30)
    return directory, binary, digest


def test_cpp_selftest(native):
    _, binary, digest = native
    result = subprocess.run([binary, digest, "--selftest"], capture_output=True, timeout=10)
    assert result.returncode == 0 and b"11 passed" in result.stdout


@pytest.mark.parametrize("raw", [b"", b"1\t2\t0.1\n", b"1\t2\t0.1\t1\textra\n",
    b"nan\t0\t0\t1\n", b"0\t0\t1\t1\n", b"true\t0\t0\t1\n", b"1\t2\t0.1\t1\n\n"])
def test_cpp_bad_input_no_partial_output(native, raw):
    _, binary, digest = native
    result = subprocess.run([binary, digest], input=raw, capture_output=True, timeout=10)
    assert result.returncode == 2 and result.stdout == b""


def test_cpp_wrong_pin(native):
    _, binary, _ = native
    result = subprocess.run([binary, "0" * 64], input=b"1\t2\t0\t1\n", capture_output=True, timeout=10)
    assert result.returncode == 2 and result.stdout == b""


def test_cpp_256_cases(native):
    _, binary, digest = native
    rng = random.Random(131)
    rows = []
    for _ in range(256):
        omega = rng.uniform(0.01, 20.0)
        rows.append([rng.uniform(-100, 100), rng.uniform(-100, 100), rng.uniform(0, 0.5 * omega), omega])
    raw = ("\n".join("\t".join(map(repr, row)) for row in rows) + "\n").encode()
    result = subprocess.run([binary, digest], input=raw, capture_output=True, timeout=10, check=True)
    actual = [list(map(float, line.split())) for line in result.stdout.splitlines()]
    assert len(actual) == len(rows)
    for output, (q, v, gamma, omega) in zip(actual, rows):
        assert output == pytest.approx([v, -2.0 * gamma * v - omega * omega * q], abs=2e-12, rel=2e-13)


def test_probe_validator():
    data = {"schema": "oscillator-godot-probe.v1", "mode": "probe", "source_sha256": "a" * 64,
            "refusal_checks": "passed", "rows": [[1.0, -2.0]]}
    assert gate().probe_rows(data, "a" * 64, 1) == [[1.0, -2.0]]
    for field, value in (("source_sha256", "b" * 64), ("mode", "trajectory"), ("refusal_checks", "not_run"),
                         ("rows", [[True, 0.0]]), ("rows", [[float("nan"), 0.0]]), ("rows", [[1.0]])):
        bad = deepcopy(data)
        bad[field] = value
        with pytest.raises(ValueError):
            gate().probe_rows(bad, "a" * 64, 1)


def test_trajectory_validator():
    times = [0.0, 0.5]
    data = {"schema": "oscillator-godot-probe.v1", "mode": "trajectory", "source_sha256": "a" * 64,
        "trajectory": {"time_s": times, "q_m": [1.0, 0.5], "v_m_s": [0.0, -1.0], "energy_j": [2.0, 1.0],
                       "owner": "godot-host-rk4", "rk4_steps": 512}}
    assert gate().trajectory_output(data, "a" * 64, times)["rk4_steps"] == 512
    for field, value in (("owner", "net"), ("rk4_steps", True), ("q_m", [1.0]), ("v_m_s", [0.0, float("inf")]),
                         ("time_s", [0.0, 0.25])):
        bad = deepcopy(data)
        bad["trajectory"][field] = value
        with pytest.raises(ValueError):
            gate().trajectory_output(bad, "a" * 64, times)


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}'])
def test_json_rejects_noncanonical_fields(tmp_path, raw):
    path = tmp_path / "bad.json"
    path.write_bytes(raw)
    with pytest.raises(ValueError):
        gate().read_json(path)


def test_parent_must_be_complete(tmp_path):
    (tmp_path / "gate-report.json").write_text(json.dumps({"status": "incomplete", "gates": {}}))
    with pytest.raises(ValueError, match="not complete"):
        gate().check_parent(tmp_path)


def test_parent_bad_digest(tmp_path):
    module = gate()
    report = {"status": "passed", "gates": {key: {"outcome": "passed"} for key in module.REQUIRED_PARENT_GATES},
              "report_digest": "sha256:" + "0" * 64}
    (tmp_path / "gate-report.json").write_text(json.dumps(report))
    with pytest.raises(ValueError, match="integrity"):
        module.check_parent(tmp_path)


def test_expected_failure_is_not_silently_accepted(tmp_path):
    module = gate()
    report = {"commands": []}
    with pytest.raises(RuntimeError):
        module.run([sys.executable, "-c", "pass"], tmp_path, report, expected=2)
    assert report["commands"][0]["status"] == "failed"
