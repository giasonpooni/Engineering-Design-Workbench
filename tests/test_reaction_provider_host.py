"""Real SCR host tests; synthetic Python children are protocol-only evidence."""
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tests.test_native_provider_host import host, frame, decode, assert_identities


def reaction(request_id="req-1"):
    return {"schema": "ciw.native-interop-request.v1", "request_id": request_id,
            "parent_execution_id": "parent-1", "profile": "reaction-a-to-b.v1", "arithmetic": "binary64",
            "semantics": {"layout": "time-major", "concentration_unit": "mol/m^3", "production_rate_unit": "mol/m^3/s",
                          "time_unit": "s", "temperature_unit": "K", "volume_unit": "m^3",
                          "frame": "homogeneous-control-volume", "clock": "declared-simulation-time"},
            "payload": {"model": "closed-isothermal-a-to-b.v1", "species_order": ["A", "B"],
                        "initial_concentration_mol_m3": [1, 0], "rate_constant_s_inv": 1,
                        "temperature_k": 300, "volume_m3": 0.1, "time_s": [0, 1],
                        "solver": {"reltol": 1e-9, "abstol_mol_m3": 1e-11, "max_steps": 10000}}}


def fixture_args(tmp_path, mode="ok"):
    project = tmp_path / "project"
    project.mkdir()
    raw = Path(__file__).with_name("reaction_protocol_fixture.py").read_text(encoding="utf-8")
    (project / "worker.py").write_text(raw.replace('MODE = "ok"', f'MODE = "{mode}"'), encoding="utf-8", newline="\n")
    (project / "requirements.txt").write_text("# protocol-only fixture\n", encoding="utf-8")
    return ["--provider", "cantera", "--python", sys.executable, "--project", str(project),
            "--worker", str(project / "worker.py"), "--timeout-ms", "3000"]


def invoke(host, messages, args):
    run = subprocess.run([str(host), *args], input=b"".join(frame(m) for m in messages), capture_output=True, timeout=20)
    return run, decode(run.stdout)


def test_python_family_snapshot_isolation_a_b_a_and_exact_bindings(host, tmp_path):
    args = fixture_args(tmp_path)
    a, b, again = reaction(), reaction("req-2"), reaction("req-3")
    b["payload"]["initial_concentration_mol_m3"] = [0.5, 0.5]
    hello = {"schema": "ciw.native-interop-handshake-request.v1", "request_id": "hello"}
    run, responses = invoke(host, [hello, a, b, again], args)
    assert run.returncode == 0, run.stderr.decode()
    assert responses[0]["profiles"] == ["reaction-a-to-b.v1"]
    runtime = responses[0]["identity"]
    assert runtime["provider"] == "cantera"
    assert "oscillator_worker_sha256" not in runtime and "manifest_sha256" not in runtime
    assert runtime["python_executable_sha256"] == "sha256:" + hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()
    assert runtime["worker_sha256"] == runtime["worker_identity"]["worker_sha256"]
    results = responses[1:]
    assert [r["host"]["child_occurrence"] for r in results] == [0, 1, 2]
    assert len({r["host"]["child_process_id"] for r in results}) == 1
    assert results[0]["data"] == results[2]["data"] != results[1]["data"]
    assert results[0]["host"]["computation_id"] == results[2]["host"]["computation_id"]
    for request, result in zip([a, b, again], results):
        assert_identities(result)
        assert bytes.fromhex(result["host"]["child_request_bytes_hex"]) == frame(request)[4:]
        assert json.loads(bytes.fromhex(result["host"]["child_response_bytes_hex"]))["data"] == result["data"]
    run, restarted = invoke(host, [a], args)
    assert run.returncode == 0
    assert restarted[0]["host"]["computation_id"] == results[0]["host"]["computation_id"]


@pytest.mark.parametrize("mode", ["grid", "solver", "digest", "nonfinite", "stale", "refused", "timeout", "stderr", "crash", "truncated"])
def test_python_family_refusals_halt_without_result_and_close_stream(host, tmp_path, mode):
    run, responses = invoke(host, [reaction(), reaction("req-2")], fixture_args(tmp_path, mode))
    assert run.returncode == 2
    assert len(responses) == 1, run.stderr.decode(errors="replace")
    assert responses[0]["status"] == "refused"
    record = responses[0]["host"]
    assert record["status"] == "halted"
    assert record["output_id"] is None and record["computation_id"] is None
    assert record["output_bytes_hex"] is None
    assert len(bytes.fromhex(record["child_stderr_hex"])) <= 65536


def test_python_family_snapshot_identity_mismatch_refuses_before_execution(host, tmp_path):
    run, responses = invoke(host, [reaction()], fixture_args(tmp_path, "identity"))
    assert run.returncode == 2 and not responses
    assert b"snapshot" in run.stderr


def test_python_family_duplicate_ids_rejected(host, tmp_path):
    run, responses = invoke(host, [reaction(), reaction()], fixture_args(tmp_path))
    assert run.returncode == 2 and len(responses) == 1
    assert responses[0]["status"] == "ok" and b"repeated request ID" in run.stderr


@pytest.mark.parametrize("field,value", [("profile", "affine-binary64.v1"), ("arithmetic", "exact-d256"),
                                        ("semantics", {"clock": "wall-time"})])
def test_reaction_family_rejects_other_profile_arithmetic_and_semantics(host, tmp_path, field, value):
    request = reaction()
    request[field] = value
    run, responses = invoke(host, [request], fixture_args(tmp_path))
    assert run.returncode == 2 and not responses


@pytest.mark.parametrize("args", [["--provider", "cantera"], ["--provider", "catalyst"],
                                 ["--provider", "julia", "--python", "unused"],
                                 ["--provider", "cpp", "--python", "unused"]])
def test_reaction_trusted_launcher_configuration_refuses_incomplete_or_unused(host, args):
    run, responses = invoke(host, [], args)
    assert run.returncode == 2 and not responses


def test_cpp_does_not_silently_acquire_reaction_profile(host):
    run, responses = invoke(host, [reaction()], ["--provider", "cpp"])
    assert run.returncode == 2 and not responses


@pytest.mark.parametrize("provider", ["catalyst", "cantera"])
def test_genuine_reaction_engine_persistent_references_and_refusal(host, provider):
    """Requires independently provisioned real engines; never installs packages."""
    prefix = "SCR_" + provider.upper()
    executable, project = os.environ.get(prefix + "_EXE"), os.environ.get(prefix + "_PROJECT")
    if not executable or not project:
        if os.environ.get("SCR_REACTION_REQUIRED") == "1":
            pytest.fail(f"{prefix}_EXE and {prefix}_PROJECT required")
        pytest.skip(f"set {prefix}_EXE and {prefix}_PROJECT for genuine engine conformance")
    project = Path(project).resolve()
    worker = project / ("worker.py" if provider == "cantera" else "worker.jl")
    args = ["--provider", provider, "--python" if provider == "cantera" else "--julia", executable,
            "--project", str(project), "--worker", str(worker), "--timeout-ms", "300000"]
    requests = [reaction(f"reaction-{i}") for i in range(7)]
    for request in requests:
        request["payload"]["time_s"] = [0, 0.1, 0.5, 1]
    requests[1]["payload"]["initial_concentration_mol_m3"] = [0.2, 0.8]
    requests[3]["payload"]["species_order"] = ["B", "A"]
    requests[3]["payload"]["initial_concentration_mol_m3"] = [0.3, 0.7]
    requests[4]["payload"]["initial_concentration_mol_m3"] = [0, 1]
    requests[5]["payload"]["rate_constant_s_inv"] = 0
    requests[6]["payload"]["initial_concentration_mol_m3"] = [1e-6, 0]
    hello = {"schema": "ciw.native-interop-handshake-request.v1", "request_id": "hello"}
    raw = b"".join(frame(r) for r in [hello, *requests])
    run = subprocess.run([str(host), *args], input=raw, capture_output=True, timeout=600)
    responses = decode(run.stdout)
    evidence_root = os.environ.get("SCR_REACTION_EVIDENCE_DIR")
    evidence = None
    if evidence_root:
        evidence = Path(evidence_root).resolve() / provider
        evidence.mkdir(parents=True, exist_ok=False)
        (evidence / "requests.frames").write_bytes(raw)
        (evidence / "responses.frames").write_bytes(run.stdout)
        (evidence / "stderr.bin").write_bytes(run.stderr)
        (evidence / "responses.json").write_text(json.dumps(responses, indent=2), encoding="utf-8")
    assert run.returncode == 0, run.stderr.decode(errors="replace")
    assert len(responses) == 8 and responses[0]["profiles"] == ["reaction-a-to-b.v1"]
    if evidence:
        (evidence / "handshake.json").write_text(json.dumps(responses[0], indent=2), encoding="utf-8")
    results = responses[1:]
    assert len({r["host"]["child_process_id"] for r in results}) == 1
    assert results[0]["data"] == results[2]["data"]
    assert results[0]["host"]["computation_id"] == results[2]["host"]["computation_id"]
    for request, result in zip(requests, results):
        assert result["status"] == "ok", result
        assert_identities(result)
        data, source = result["data"], request["payload"]
        order = source["species_order"]
        a_index, b_index = order.index("A"), order.index("B")
        a0, b0 = source["initial_concentration_mol_m3"][a_index], source["initial_concentration_mol_m3"][b_index]
        rate = source["rate_constant_s_inv"]
        for t, row, production in zip(source["time_s"], data["concentration_mol_m3"], data["production_rate_mol_m3_s"]):
            a = a0 * math.exp(-rate * t)
            assert row[a_index] == pytest.approx(a, rel=2e-7, abs=2e-10)
            assert row[b_index] == pytest.approx(b0 + a0 - a, rel=2e-7, abs=2e-10)
            assert sum(row) == pytest.approx(a0 + b0, rel=2e-9, abs=2e-10)
            assert production[a_index] == pytest.approx(-rate * row[a_index], rel=1e-10, abs=1e-13)
            assert production[b_index] == pytest.approx(rate * row[a_index], rel=1e-10, abs=1e-13)
        assert bytes.fromhex(result["host"]["child_request_bytes_hex"]) == frame(request)[4:]
        assert json.loads(bytes.fromhex(result["host"]["child_response_bytes_hex"]))["data"] == data
    limited = reaction("limited")
    limited["payload"]["solver"]["max_steps"] = 1
    limited_raw = frame(limited)
    limited_run = subprocess.run([str(host), *args], input=limited_raw, capture_output=True, timeout=600)
    limited_results = decode(limited_run.stdout)
    if evidence:
        (evidence / "limited-request.frames").write_bytes(limited_raw)
        (evidence / "limited-response.frames").write_bytes(limited_run.stdout)
        (evidence / "limited-stderr.bin").write_bytes(limited_run.stderr)
    assert limited_run.returncode == 2 and len(limited_results) == 1
    assert limited_results[0]["status"] == "refused"
    assert limited_results[0]["host"]["output_id"] is None
    assert limited_results[0]["host"]["computation_id"] is None
