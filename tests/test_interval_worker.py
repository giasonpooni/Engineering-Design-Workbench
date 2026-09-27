"""Opt-in genuine JuliaIntervals frames, checked by independent exact Fractions."""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import tomllib

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "runtimes/interval-requirement"
SEMANTICS = {"layout": "scalar", "input_unit": "1", "output_unit": "1",
             "frame": "dimensionless-cartesian", "clock": "not_applicable"}
CONFIGURATION = {"input_encoding": "reduced-rational", "endpoint_encoding": "ieee754-binary64-hex",
    "rounding": "correct", "power": "slow", "decoration": "com", "guaranteed": True,
    "covariance_status": "not_applicable", "calibration_status": "not_applicable"}
pytestmark = pytest.mark.integration


def rat(n, d=1):
    value = Fraction(n, d)
    return {"numerator": value.numerator, "denominator": value.denominator}


def request(name="first", *, x=rat(3), lower=rat(-1, 2), upper=rat(1, 2), limit=rat(1, 4)):
    return {"schema": "ciw.native-interop-request.v1", "request_id": name,
        "parent_execution_id": "execution/" + name, "profile": "scalar-square-interval.v1",
        "arithmetic": "outward-binary64", "semantics": deepcopy(SEMANTICS),
        "payload": {"model": "scalar-square.v1", "x": deepcopy(x),
                    "variation_lower": deepcopy(lower), "variation_upper": deepcopy(upper),
                    "error_limit": deepcopy(limit)}}


def hello():
    return {"schema": "ciw.native-interop-handshake-request.v1", "request_id": "hello"}


def frame(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return len(raw).to_bytes(4, "big") + raw


def frames(raw):
    values = []
    while raw:
        assert len(raw) >= 4, "stdout contains an incomplete header or diagnostics"
        size = int.from_bytes(raw[:4], "big")
        assert 1 <= size <= 1024 * 1024 and len(raw) >= size + 4
        values.append(json.loads(raw[4:4+size]))
        raw = raw[4+size:]
    return values


@pytest.fixture(scope="module")
def julia():
    exe, depot = os.environ.get("CIW_TEST_INTERVAL_JULIA"), os.environ.get("CIW_TEST_INTERVAL_DEPOT")
    if not exe or not depot:
        if os.environ.get("CIW_INTERVAL_REQUIRE_JULIA") == "1":
            pytest.fail("Required interval gate needs CIW_TEST_INTERVAL_JULIA and CIW_TEST_INTERVAL_DEPOT")
        pytest.skip("set CIW_TEST_INTERVAL_JULIA and CIW_TEST_INTERVAL_DEPOT for genuine interval tests")
    assert Path(exe).is_file()
    assert all(Path(path).is_dir() for path in depot.split(os.pathsep))
    return exe, dict(os.environ, JULIA_DEPOT_PATH=depot, JULIA_LOAD_PATH=os.pathsep.join(("@", "@stdlib")),
        JULIA_PKG_OFFLINE="true", JULIA_NUM_THREADS="1")


def invoke(julia, raw):
    exe, env = julia
    return subprocess.run([exe, "--startup-file=no", "--history-file=no", f"--project={PROJECT}",
        str(PROJECT / "worker.jl")], input=raw, capture_output=True, env=env, timeout=180)


@pytest.fixture(scope="module")
def solved(julia):
    maximum = request("max/" + "a" * 156)
    maximum["parent_execution_id"] = "p/" + "b" * 158
    rows = [request("dyadic-boundary"), request("positive", lower=rat(1), upper=rat(2), limit=rat(1, 2)),
        request("mixed", lower=rat(-1), upper=rat(1), limit=rat(1, 2)),
        request("rational-boundary", lower=rat(1, 10), upper=rat(1, 10), limit=rat(1, 100)),
        request("zero", lower=rat(0), upper=rat(0), limit=rat(0)),
        request("negative", lower=rat(-2), upper=rat(-1), limit=rat(5)),
        request("again"), request("changed-x", x=rat(-10)),
        request("extreme", x=rat(-100), lower=rat(0), upper=rat(200), limit=rat(40000)),
        request("small", lower=rat(1, 1000000), upper=rat(2, 999983), limit=rat(0)), maximum]
    proc = invoke(julia, b"".join(frame(v) for v in [hello(), *rows]))
    assert proc.returncode == 0, proc.stderr.decode(errors="replace")
    replies = frames(proc.stdout)
    assert len(replies) == len(rows) + 1
    assert all(r["status"] == "ok" for r in replies), replies
    return rows, replies


def test_identity_and_environment_hashes_are_actual(solved):
    _, rows = solved
    identity = rows[0]["identity"]
    assert rows[0]["profiles"] == ["scalar-square-interval.v1"]
    assert identity["schema"] == "ciw.interval-julia-identity.v1"
    assert identity["julia_version"] == "1.10.12"
    assert type(identity["threads"]) is int and identity["threads"] == 1
    assert set(identity["packages"]) == {"IntervalArithmetic", "JSON3"}
    for key, name in (("worker_sha256", "worker.jl"), ("project_sha256", "Project.toml"), ("manifest_sha256", "Manifest.toml")):
        assert identity[key] == "sha256:" + hashlib.sha256((PROJECT / name).read_bytes()).hexdigest()
    project = tomllib.loads((PROJECT / "Project.toml").read_text())
    manifest = tomllib.loads((PROJECT / "Manifest.toml").read_text())
    for name, version in identity["packages"].items():
        assert project["compat"][name] == "=" + version
        assert manifest["deps"][name][0]["version"] == version


def test_actual_outward_enclosures_contain_exact_extrema_without_tolerance(solved):
    requests, responses = solved
    for sent, response in zip(requests, responses[1:]):
        assert response["request_id"] == sent["request_id"]
        assert response["parent_execution_id"] == sent["parent_execution_id"]
        data, source = response["data"], sent["payload"]
        assert set(data) == {"model", "expression", "enclosure", "requirement", "configuration"}
        assert data["model"] == "scalar-square.v1" and data["expression"] == "u^2-error_limit"
        assert data["configuration"] == CONFIGURATION
        enclosure = data["enclosure"]
        assert enclosure["guaranteed"] is True and enclosure["decoration"] == "com"
        assert all(len(enclosure[k]) == 16 and set(enclosure[k]) <= set("0123456789abcdef") for k in ("lower_hex", "upper_hex"))
        lo, hi = (struct.unpack(">d", bytes.fromhex(enclosure[k]))[0] for k in ("lower_hex", "upper_hex"))
        assert math.isfinite(lo) and math.isfinite(hi) and lo <= hi
        a, b, e = (Fraction(source[k]["numerator"], source[k]["denominator"]) for k in ("variation_lower", "variation_upper", "error_limit"))
        exact_lo = (Fraction(0) if a <= 0 <= b else min(a*a, b*b)) - e
        exact_hi = max(a*a, b*b) - e
        assert Fraction.from_float(lo) <= exact_lo <= exact_hi <= Fraction.from_float(hi)
        expected = "holds_throughout" if hi <= 0 else "fails_throughout" if lo > 0 else "inconclusive"
        assert data["requirement"] == expected
    assert [r["data"]["requirement"] for r in responses[1:7]] == [
        "holds_throughout", "fails_throughout", "inconclusive", "inconclusive", "holds_throughout", "holds_throughout"]


def test_persistent_a_b_a_and_restart_keep_same_numerics(solved, julia):
    _, rows = solved
    assert rows[1]["data"] == rows[7]["data"] == rows[8]["data"]
    fresh = invoke(julia, frame(hello()) + frame(request("new-occurrence")))
    assert fresh.returncode == 0
    assert frames(fresh.stdout)[1]["data"] == rows[1]["data"]


def test_invalid_data_refused_and_next_occurrence_recovers(julia):
    rows = []
    mutations = [("x", {"numerator": True, "denominator": 1}), ("x", {"numerator": 1, "denominator": True}),
        ("x", {"numerator": 1.0, "denominator": 1}), ("x", {"numerator": 2, "denominator": 2}),
        ("x", {"numerator": 0, "denominator": 2}), ("x", {"numerator": 1, "denominator": 0}),
        ("x", {"numerator": 1, "denominator": -1}), ("x", {"numerator": 1000001, "denominator": 1}),
        ("x", {"numerator": 1, "denominator": 1000001}), ("x", rat(101)),
        ("variation_lower", rat(1)), ("variation_upper", rat(201)), ("error_limit", rat(-1)),
        ("error_limit", rat(40001)), ("model", "custom-expression"), ("code", "run(`cmd.exe`)")]
    for i, (key, value) in enumerate(mutations):
        item = request("invalid/" + str(i)); item["payload"][key] = value; rows.append(item)
    outside = request("outside", x=rat(100)); rows.append(outside)
    units = request("units"); units["semantics"]["input_unit"] = "m"; rows.append(units)
    arithmetic = request("arithmetic"); arithmetic["arithmetic"] = "binary64"; rows.append(arithmetic)
    proc = invoke(julia, b"".join(frame(v) for v in [hello(), *rows, request("recovery")]))
    assert proc.returncode == 0, proc.stderr.decode(errors="replace")
    responses = frames(proc.stdout)[1:]
    assert len(responses) == len(rows) + 1
    assert all(r["status"] == "refused" and "data" not in r for r in responses[:-1])
    assert all(r["refusal"]["code"] == "INVALID_REQUEST" for r in responses[:-1])
    assert responses[-1]["status"] == "ok" and proc.stderr


def test_integer_token_spelling_is_checked_before_json3_normalization(julia):
    # JSON3 also parses 1.0, 1e0, +1 and 01 as Int64. Build raw frames to retain
    # each spelling; json.dumps would normalize some of these invalid tokens.
    invalid = (b"1.0", b"1e0", b"1E+0", b"-1.0", b"0e1", b"+1", b"01", b"-01")
    raw_frames = [frame(hello())]
    for component in ("numerator", "denominator"):
        for index, token in enumerate(invalid):
            sent = request(f"lexical/{component}/{index}", x=rat(1))
            raw = frame(sent)[4:]
            marker = b'"' + component.encode() + b'":1'
            # Change the x component only, leaving all other rational sources
            # untouched even when their numeral begins with the same digit.
            start = raw.index(b'"x":')
            raw = raw[:start] + raw[start:].replace(marker, b'"' + component.encode() + b'":' + token, 1)
            raw_frames.append(len(raw).to_bytes(4, "big") + raw)
    # Signed zero is a JSON integer token; numeric-looking identifier strings
    # remain strings and must not be rejected by the spelling check.
    accepted = request("valid-1.0e2", x=rat(0))
    raw = frame(accepted)[4:].replace(b'"numerator":0', b'"numerator":-0')
    raw_frames.append(len(raw).to_bytes(4, "big") + raw)
    raw_frames.append(frame(request("lexical-recovery")))
    proc = invoke(julia, b"".join(raw_frames))
    assert proc.returncode == 0, proc.stderr.decode(errors="replace")
    responses = frames(proc.stdout)[1:]
    assert len(responses) == 2 * len(invalid) + 2
    assert all(r["status"] == "refused" and "data" not in r and
               r["refusal"]["code"] == "INVALID_REQUEST" for r in responses[:-2]), responses
    assert all(r["status"] == "ok" for r in responses[-2:])


@pytest.mark.parametrize("raw", [b"\0\0", b"\0\0\0\0", (1024*1024+1).to_bytes(4, "big"),
    b"{unframed}", b"\0\0\0\1\xff", b'"worker.jl"',
    b'{"schema":"x","schema":"y"}', b'{"x":' + b"["*17 + b"]"*17 + b"}", b'{}{}'])
def test_malformed_transport_and_duplicate_json_refused(julia, raw):
    if raw.startswith((b"{", b'"')):
        raw = len(raw).to_bytes(4, "big") + raw
    proc = invoke(julia, raw)
    assert proc.returncode == 2 and proc.stdout == b"" and proc.stderr


def test_duplicate_occurrence_and_identifier_bounds_refused(julia):
    duplicate = invoke(julia, frame(hello()) + frame(request()) + frame(request()))
    assert duplicate.returncode == 2 and len(frames(duplicate.stdout)) == 2
    for key, value in [("request_id", "a"*161), ("request_id", "bad\n"), ("parent_execution_id", "bad\n")]:
        bad = request(); bad[key] = value
        proc = invoke(julia, frame(hello()) + frame(bad))
        assert proc.returncode == 2 and len(frames(proc.stdout)) == 1


def test_nested_duplicate_and_boolean_semantics_never_execute(julia):
    raw = frame(request())[4:].replace(b'"numerator":3', b'"numerator":3,"numerator":4')
    proc = invoke(julia, frame(hello()) + len(raw).to_bytes(4, "big") + raw)
    assert proc.returncode == 2 and len(frames(proc.stdout)) == 1
    bad = request(); bad["semantics"]["input_unit"] = True
    proc = invoke(julia, frame(hello()) + frame(bad))
    assert proc.returncode == 0 and frames(proc.stdout)[1]["status"] == "refused"
