"""Compiled interval host transport checks; scripted children are not Julia evidence."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess

import pytest

from tests.test_native_provider_host import host, frame, decode, assert_identities

CONFIGURATION = {"input_encoding": "reduced-rational", "endpoint_encoding": "ieee754-binary64-hex",
                 "rounding": "correct", "power": "slow", "decoration": "com", "guaranteed": True,
                 "covariance_status": "not_applicable", "calibration_status": "not_applicable"}


def rational(n, d=1):
    return {"numerator": n, "denominator": d}


def request(request_id="req-1"):
    return {"schema": "ciw.native-interop-request.v1", "request_id": request_id,
            "parent_execution_id": "parent-1", "profile": "scalar-square-interval.v1", "arithmetic": "outward-binary64",
            "semantics": {"layout": "scalar", "input_unit": "1", "output_unit": "1",
                          "frame": "dimensionless-cartesian", "clock": "not_applicable"},
            "payload": {"model": "scalar-square.v1", "x": rational(0), "variation_lower": rational(-1, 2),
                        "variation_upper": rational(1, 2), "error_limit": rational(1, 4)}}


def result(source, lo=-0.25, hi=0.0, requirement="holds_throughout"):
    return {"schema": "ciw.native-interop-response.v1", "request_id": source["request_id"],
            "parent_execution_id": source["parent_execution_id"], "profile": source["profile"], "status": "ok",
            "data": {"model": "scalar-square.v1", "expression": "u^2-error_limit",
                     "enclosure": {"lower_hex": struct.pack(">d", lo).hex(), "upper_hex": struct.pack(">d", hi).hex(),
                                   "decoration": "com", "guaranteed": True},
                     "requirement": requirement, "configuration": deepcopy(CONFIGURATION)}}


@pytest.fixture(scope="module")
def interval_protocol_child(tmp_path_factory):
    rustc = shutil.which("rustc")
    assert rustc, "Rust compiler required for protocol-only fixture"
    folder = tmp_path_factory.mktemp("interval-fixture")
    executable = folder / ("interval-fixture.exe" if os.name == "nt" else "interval-fixture")
    subprocess.run([rustc, str(Path(__file__).with_name("interval_host_fixture.rs")), "-o", str(executable)],
                   check=True, capture_output=True, timeout=60)
    return executable


def invoke(host, executable, tmp_path, requests, outputs, mode="ok", bad_identity=None):
    project = tmp_path / "interval-project"
    project.mkdir(exist_ok=True)
    (project / "worker.jl").write_text(mode, encoding="utf-8", newline="\n")
    (project / "Project.toml").write_text("[deps]\n", encoding="utf-8", newline="\n")
    (project / "Manifest.toml").write_text("# protocol-only fixture\n", encoding="utf-8", newline="\n")
    (project / "not-in-the-snapshot.txt").write_text("must not cross the boundary", encoding="utf-8")
    identity = {"schema": "ciw.interval-julia-identity.v1", "julia_version": "1.10.12",
                "platform": "PROTOCOL-ONLY-NOT-JULIA", "threads": 1,
                "packages": {"IntervalArithmetic": "protocol-only", "JSON3": "protocol-only"}}
    for key, name in [("worker_sha256", "worker.jl"), ("project_sha256", "Project.toml"), ("manifest_sha256", "Manifest.toml")]:
        identity[key] = "sha256:" + hashlib.sha256((project / name).read_bytes()).hexdigest()
    if bad_identity:
        identity.update(bad_identity)
    hello = {"schema": "ciw.native-interop-handshake-response.v1", "request_id": "scr-host-handshake",
             "status": "ok", "identity": identity, "profiles": ["scalar-square-interval.v1"]}
    scripted = tmp_path / "scripted.frames"
    scripted.write_bytes(b"".join(frame(value) for value in [hello, *outputs]))
    environment = dict(os.environ, SCR_INTERVAL_FIXTURE_FRAMES=str(scripted))
    args = ["--provider", "intervals", "--julia", str(executable), "--project", str(project),
            "--worker", str(project / "worker.jl"), "--timeout-ms", "2000"]
    run = subprocess.run([str(host), *args], input=b"".join(frame(value) for value in requests),
                         capture_output=True, timeout=15, env=environment)
    return run, decode(run.stdout)


def test_interval_snapshot_persistent_occurrences_restart_and_exact_commitments(host, interval_protocol_child, tmp_path):
    a, b, again = request(), request("req-2"), request("req-3")
    b["payload"]["error_limit"] = rational(0)
    scripted = [result(a), result(b, 0, 0.25, "inconclusive"), result(again)]
    hello = {"schema": "ciw.native-interop-handshake-request.v1", "request_id": "hello"}
    run, responses = invoke(host, interval_protocol_child, tmp_path, [hello, a, b, again], scripted)
    assert run.returncode == 0, run.stderr.decode(errors="replace")
    assert responses[0]["profiles"] == ["scalar-square-interval.v1"]
    runtime = responses[0]["identity"]
    assert runtime["provider"] == "intervals"
    assert runtime["worker_identity"]["schema"] == "ciw.interval-julia-identity.v1"
    assert "oscillator_worker_sha256" not in runtime and "python_executable_sha256" not in runtime
    assert runtime["julia_executable_sha256"] == "sha256:" + hashlib.sha256(interval_protocol_child.read_bytes()).hexdigest()
    results = responses[1:]
    assert [r["host"]["child_occurrence"] for r in results] == [0, 1, 2]
    assert len({r["host"]["child_process_id"] for r in results}) == 1
    assert results[0]["data"] == results[2]["data"] != results[1]["data"]
    assert results[0]["host"]["computation_id"] == results[2]["host"]["computation_id"]
    for original, expected, actual in zip([a, b, again], scripted, results):
        assert_identities(actual)
        assert bytes.fromhex(actual["host"]["child_request_bytes_hex"]) == frame(original)[4:]
        assert bytes.fromhex(actual["host"]["child_response_bytes_hex"]) == frame(expected)[4:]
    run, restarted = invoke(host, interval_protocol_child, tmp_path, [a], [result(a)])
    assert run.returncode == 0
    assert restarted[0]["host"]["child_process_id"] != results[0]["host"]["child_process_id"]
    assert restarted[0]["host"]["computation_id"] == results[0]["host"]["computation_id"]


@pytest.mark.parametrize("mode", ["stale", "refused", "timeout", "stderr", "crash", "truncated",
                                  "guarantee", "decoration", "configuration", "classification", "nonfinite", "order", "uppercase"])
def test_interval_failures_halt_without_output_and_close_stream(host, interval_protocol_child, tmp_path, mode):
    source = request()
    response = result(source)
    if mode == "stale":
        response["parent_execution_id"] = "another-parent"
    elif mode == "refused":
        response.pop("data")
        response.update(status="refused", refusal={"code": "test-only", "detail": "deliberate protocol refusal"})
    elif mode == "guarantee":
        response["data"]["enclosure"]["guaranteed"] = False
    elif mode == "decoration":
        response["data"]["enclosure"]["decoration"] = "trv"
    elif mode == "configuration":
        response["data"]["configuration"]["rounding"] = "none"
    elif mode == "classification":
        response["data"]["requirement"] = "fails_throughout"
    elif mode == "nonfinite":
        response["data"]["enclosure"]["lower_hex"] = "fff0000000000000"
    elif mode == "order":
        response["data"]["enclosure"]["upper_hex"] = "bff0000000000000"
    elif mode == "uppercase":
        response["data"]["enclosure"]["lower_hex"] = "BFD0000000000000"
    run, responses = invoke(host, interval_protocol_child, tmp_path, [source, request("late")], [response], mode=mode)
    assert run.returncode == 2 and len(responses) == 1, run.stderr.decode(errors="replace")
    assert responses[0]["status"] == "refused"
    record = responses[0]["host"]
    assert record["status"] == "halted"
    assert record["output_id"] is None and record["computation_id"] is None and record["output_bytes_hex"] is None
    assert len(bytes.fromhex(record["child_stderr_hex"])) <= 65536


@pytest.mark.parametrize("key,value", [("worker_sha256", "sha256:" + "0" * 64), ("schema", "ciw.reaction-catalyst-identity.v1"),
                                      ("packages", {"JSON3": "1"}), ("threads", True)])
def test_interval_bad_identity_refuses_before_execution(host, interval_protocol_child, tmp_path, key, value):
    run, responses = invoke(host, interval_protocol_child, tmp_path, [request()], [], bad_identity={key: value})
    assert run.returncode == 2 and not responses


@pytest.mark.parametrize("field,value", [("variation_lower", rational(2, 4)), ("variation_lower", rational(0, 2)),
                                        ("variation_lower", rational(True)), ("variation_lower", rational(1.0)),
                                        ("variation_lower", rational(1)), ("x", rational(100)),
                                        ("error_limit", rational(-1))])
def test_interval_bad_domain_refuses_with_halted_occurrence_before_child_dispatch(host, interval_protocol_child, tmp_path, field, value):
    source = request()
    source["payload"][field] = value
    run, responses = invoke(host, interval_protocol_child, tmp_path, [source], [result(source)])
    assert run.returncode == 2 and len(responses) == 1
    record = responses[0]["host"]
    assert record["status"] == "halted" and record["output_id"] is None
    assert record["child_request_bytes_hex"] is None and record["child_response_bytes_hex"] is None


@pytest.mark.parametrize("provider", ["cpp", "julia", "catalyst", "cantera"])
def test_interval_profile_is_not_added_to_existing_families(host, provider):
    options = {"cpp": [], "julia": ["--julia", "absent"], "catalyst": ["--julia", "absent"], "cantera": ["--python", "absent"]}
    args = options[provider] + ([] if provider == "cpp" else ["--project", "absent", "--worker", "absent"])
    run = subprocess.run([str(host), "--provider", provider, *args], input=frame(request()), capture_output=True, timeout=10)
    assert run.returncode == 2 and not run.stdout
    assert b"unsupported profile" in run.stderr


@pytest.mark.parametrize("field,value", [("profile", "reaction-a-to-b.v1"), ("arithmetic", "binary64"),
                                        ("semantics", {"clock": "not-applicable"})])
def test_interval_refuses_other_profiles_arithmetic_and_semantics_without_launch(host, field, value):
    source = request()
    source[field] = value
    run = subprocess.run([str(host), "--provider", "intervals", "--julia", "absent", "--project", "absent", "--worker", "absent"],
                         input=frame(source), capture_output=True, timeout=10)
    assert run.returncode == 2 and not run.stdout
    assert b"unsupported profile" in run.stderr or b"arithmetic profile" in run.stderr or b"declaration differs" in run.stderr


def test_genuine_interval_worker_exact_enclosures_persistence_and_restart(host):
    """Opt-in real Julia/IntervalArithmetic gate; never resolves or installs packages."""
    from fractions import Fraction
    import math

    executable = os.environ.get("SCR_INTERVAL_EXE")
    project = os.environ.get("SCR_INTERVAL_PROJECT")
    depot = os.environ.get("SCR_INTERVAL_DEPOT")
    if not all([executable, project, depot]):
        if os.environ.get("SCR_INTERVAL_REQUIRED") == "1":
            pytest.fail("SCR_INTERVAL_EXE, SCR_INTERVAL_PROJECT and SCR_INTERVAL_DEPOT are required")
        pytest.skip("set explicit SCR_INTERVAL_EXE, SCR_INTERVAL_PROJECT and SCR_INTERVAL_DEPOT for genuine interval qualification")
    executable, project, depot = (Path(value).resolve() for value in [executable, project, depot])
    assert executable.is_file() and project.is_dir() and depot.is_dir()
    args = [str(host), "--provider", "intervals", "--julia", str(executable), "--project", str(project),
            "--worker", str(project / "worker.jl"), "--timeout-ms", "300000"]
    environment = dict(os.environ, JULIA_DEPOT_PATH=str(depot))
    hello = {"schema": "ciw.native-interop-handshake-request.v1", "request_id": "interval-hello"}
    cases = [request(name) for name in ["dyadic-a", "mixed-b", "dyadic-again", "rational-boundary", "zero", "negative"]]
    cases[1]["payload"].update(variation_lower=rational(-1), variation_upper=rational(1))
    cases[3]["payload"].update(variation_lower=rational(1, 10), variation_upper=rational(1, 10), error_limit=rational(1, 100))
    cases[4]["payload"].update(variation_lower=rational(0), variation_upper=rational(0), error_limit=rational(0))
    cases[5]["payload"].update(variation_lower=rational(-2), variation_upper=rational(-1))
    raw = b"".join(frame(value) for value in [hello, *cases])
    evidence_root = os.environ.get("SCR_INTERVAL_EVIDENCE_DIR")
    evidence = Path(evidence_root).resolve() if evidence_root else None
    if evidence:
        evidence.mkdir(parents=True, exist_ok=False)
        (evidence / "requests.frames").write_bytes(raw)
    run = subprocess.run(args, input=raw, capture_output=True, timeout=600, env=environment)
    if evidence:
        (evidence / "responses.frames").write_bytes(run.stdout)
        (evidence / "stderr.bin").write_bytes(run.stderr)
    responses = decode(run.stdout)
    if evidence:
        (evidence / "responses.json").write_text(json.dumps(responses, indent=2), encoding="utf-8")
        if responses:
            (evidence / "handshake.json").write_text(json.dumps(responses[0], indent=2), encoding="utf-8")
    assert run.returncode == 0, run.stderr.decode(errors="replace")
    assert len(responses) == len(cases) + 1
    assert responses[0]["profiles"] == ["scalar-square-interval.v1"]
    runtime = responses[0]["identity"]
    assert runtime["provider"] == "intervals"
    assert runtime["worker_identity"]["schema"] == "ciw.interval-julia-identity.v1"
    assert set(runtime["worker_identity"]["packages"]) == {"IntervalArithmetic", "JSON3"}
    assert runtime["worker_identity"]["julia_version"] == "1.10.12"
    assert runtime["worker_identity"]["threads"] == 1
    assert runtime["julia_executable_sha256"] == "sha256:" + hashlib.sha256(executable.read_bytes()).hexdigest()
    for field, filename in [("worker_sha256", "worker.jl"), ("project_sha256", "Project.toml"), ("manifest_sha256", "Manifest.toml")]:
        expected = "sha256:" + hashlib.sha256((project / filename).read_bytes()).hexdigest()
        assert runtime[field] == runtime["worker_identity"][field] == expected

    def check_exact_enclosure(source, actual):
        assert actual["status"] == "ok", actual
        assert_identities(actual)
        data = actual["data"]
        assert data["model"] == "scalar-square.v1" and data["expression"] == "u^2-error_limit"
        assert data["configuration"] == CONFIGURATION
        enclosure = data["enclosure"]
        assert enclosure["guaranteed"] is True and enclosure["decoration"] == "com"
        lower, upper = (struct.unpack(">d", bytes.fromhex(enclosure[key]))[0] for key in ["lower_hex", "upper_hex"])
        assert math.isfinite(lower) and math.isfinite(upper) and lower <= upper
        payload = source["payload"]
        lo, hi, epsilon = (Fraction(payload[key]["numerator"], payload[key]["denominator"])
                           for key in ["variation_lower", "variation_upper", "error_limit"])
        exact_minimum = (Fraction(0) if lo <= 0 <= hi else min(lo * lo, hi * hi)) - epsilon
        exact_maximum = max(lo * lo, hi * hi) - epsilon
        # Fraction.from_float interprets each actual binary64 endpoint exactly.
        # No epsilon or statistical tolerance is permitted in this gate.
        assert Fraction.from_float(lower) <= exact_minimum
        assert exact_maximum <= Fraction.from_float(upper)
        expected_classification = "holds_throughout" if upper <= 0 else "fails_throughout" if lower > 0 else "inconclusive"
        assert data["requirement"] == expected_classification
        record = actual["host"]
        assert bytes.fromhex(record["child_request_bytes_hex"]) == frame(source)[4:]
        child_raw = bytes.fromhex(record["child_response_bytes_hex"])
        child = json.loads(child_raw)
        assert child == {key: value for key, value in actual.items() if key != "host"}
        assert record["provider_runtime"] == runtime
        return {"request_id": source["request_id"], "exact_minimum": str(exact_minimum),
                "exact_maximum": str(exact_maximum), "returned_lower_exact": str(Fraction.from_float(lower)),
                "returned_upper_exact": str(Fraction.from_float(upper)), "requirement": data["requirement"]}

    results = responses[1:]
    checks = [check_exact_enclosure(source, actual) for source, actual in zip(cases, results)]
    assert [actual["host"]["child_occurrence"] for actual in results] == list(range(len(cases)))
    assert len({actual["host"]["child_process_id"] for actual in results}) == 1
    assert results[0]["data"] == results[2]["data"] != results[1]["data"]
    assert results[0]["host"]["computation_id"] == results[2]["host"]["computation_id"]
    assert results[0]["data"]["requirement"] == "holds_throughout"
    assert results[1]["data"]["requirement"] == "inconclusive"
    assert results[4]["data"]["requirement"] == "holds_throughout"
    assert results[5]["data"]["requirement"] == "fails_throughout"
    repeated_request = request("fresh-process-a")
    restarted_raw = frame(hello) + frame(repeated_request)
    if evidence:
        (evidence / "restart-requests.frames").write_bytes(restarted_raw)
    restarted_run = subprocess.run(args, input=restarted_raw, capture_output=True, timeout=600, env=environment)
    if evidence:
        (evidence / "restart-responses.frames").write_bytes(restarted_run.stdout)
        (evidence / "restart-stderr.bin").write_bytes(restarted_run.stderr)
    assert restarted_run.returncode == 0, restarted_run.stderr.decode(errors="replace")
    restarted = decode(restarted_run.stdout)
    assert len(restarted) == 2 and restarted[0]["identity"] == runtime
    repeated = restarted[1]
    checks.append(check_exact_enclosure(repeated_request, repeated))
    assert repeated["data"] == results[0]["data"]
    assert repeated["host"]["process_id"] != results[0]["host"]["process_id"]
    assert repeated["host"]["child_process_id"] != results[0]["host"]["child_process_id"]
    assert repeated["host"]["child_occurrence"] == 0
    assert repeated["host"]["computation_id"] == results[0]["host"]["computation_id"]
    if evidence:
        (evidence / "exact-enclosure-checks.json").write_text(json.dumps({"checks": checks,
            "scope": "exact rational enclosure comparison and process conformance; no physical validation, proof or authorization"}, indent=2), encoding="utf-8")
