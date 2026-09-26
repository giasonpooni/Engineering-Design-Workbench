"""Opt-in genuine Catalyst frames; analytical checks use no Catalyst routines."""
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tomllib

import pytest


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "runtimes/reaction-kinetics"
SEMANTICS = {"layout": "time-major", "concentration_unit": "mol/m^3",
    "production_rate_unit": "mol/m^3/s", "time_unit": "s", "temperature_unit": "K",
    "volume_unit": "m^3", "frame": "homogeneous-control-volume", "clock": "declared-simulation-time"}
pytestmark = pytest.mark.integration


def frame(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return len(raw).to_bytes(4, "big") + raw


def frames(raw):
    values = []
    while raw:
        assert len(raw) >= 4, "stdout has an incomplete frame or unframed diagnostics"
        count = int.from_bytes(raw[:4], "big")
        assert 0 < count <= 1024 * 1024
        assert len(raw) >= count + 4
        values.append(json.loads(raw[4:count + 4]))
        raw = raw[count + 4:]
    return values


def hello():
    return {"schema": "ciw.native-interop-handshake-request.v1", "request_id": "reaction-handshake"}


def request(name="a", **changes):
    payload = {"model": "closed-isothermal-a-to-b.v1", "species_order": ["A", "B"],
        "initial_concentration_mol_m3": [1.2, .3], "rate_constant_s_inv": .7,
        "temperature_k": 300., "volume_m3": .01, "time_s": [0., .1, .3, 1., 3.],
        "solver": {"reltol": 1e-9, "abstol_mol_m3": 1e-11, "max_steps": 100000}}
    payload.update(changes)
    return {"schema": "ciw.native-interop-request.v1", "request_id": name,
        "parent_execution_id": "execution-" + name, "profile": "reaction-a-to-b.v1",
        "arithmetic": "binary64", "semantics": deepcopy(SEMANTICS), "payload": payload}


@pytest.fixture(scope="module")
def julia():
    executable = os.environ.get("CIW_TEST_REACTION_JULIA")
    depot = os.environ.get("CIW_TEST_REACTION_JULIA_DEPOT")
    if not executable or not depot:
        if os.environ.get("CIW_REACTION_REQUIRE_JULIA") == "1":
            pytest.fail("Required Catalyst gate needs CIW_TEST_REACTION_JULIA and CIW_TEST_REACTION_JULIA_DEPOT")
        pytest.skip("Set CIW_TEST_REACTION_JULIA and CIW_TEST_REACTION_JULIA_DEPOT for genuine Catalyst tests")
    assert Path(executable).is_file(), "configured Julia executable is missing"
    assert all(Path(path).is_dir() for path in depot.split(os.pathsep)), "configured Julia depot is missing"
    return executable, dict(os.environ, JULIA_DEPOT_PATH=depot, JULIA_LOAD_PATH=os.pathsep.join(("@", "@stdlib")),
                           JULIA_PKG_OFFLINE="true", JULIA_NUM_THREADS="1")


def invoke(julia, payload):
    executable, env = julia
    return subprocess.run([executable, "--startup-file=no", "--history-file=no", f"--project={PROJECT}",
                           str(PROJECT / "worker.jl")], input=payload, capture_output=True, env=env, timeout=300)


@pytest.fixture(scope="module")
def solved(julia):
    max_id = request("id/domain/" + "a"*150)
    max_id["parent_execution_id"] = "parent/" + "b"*153
    requests = [request("a"),
        request("b", species_order=["B", "A"], initial_concentration_mol_m3=[.3, 1.2]),
        request("a-again"), request("zero-rate", rate_constant_s_inv=0.),
        request("zero-a", initial_concentration_mol_m3=[0., .3]),
        request("small-total", initial_concentration_mol_m3=[1e-6, 0.]),
        request("large-total", initial_concentration_mol_m3=[1000., 0.]),
        request("long-grid", rate_constant_s_inv=.3, temperature_k=250., volume_m3=1.,
                time_s=[100.*i/127 for i in range(128)]),
        request("fast", rate_constant_s_inv=10., time_s=[0., .001, .3, 1., 3.]),
        max_id, request("inert-closure", temperature_k=500., volume_m3=1e-6)]
    proc = invoke(julia, b"".join(frame(value) for value in [hello(), *requests]))
    assert proc.returncode == 0, proc.stderr.decode(errors="replace")
    replies = frames(proc.stdout)
    assert len(replies) == len(requests) + 1
    assert all(response["status"] == "ok" for response in replies), replies
    return requests, replies


def test_genuine_worker_identity_and_mechanism_are_exact_retained_bytes(solved):
    _, replies = solved
    handshake = replies[0]
    assert handshake["profiles"] == ["reaction-a-to-b.v1"]
    assert handshake["request_id"] == hello()["request_id"]
    identity = handshake["identity"]
    assert identity["schema"] == "ciw.reaction-catalyst-identity.v1"
    assert identity["julia_version"] == "1.10.12"
    assert identity["threads"] == 1 and type(identity["threads"]) is int
    for field, name in (("worker_sha256", "worker.jl"), ("project_sha256", "Project.toml"),
                        ("manifest_sha256", "Manifest.toml")):
        assert identity[field] == "sha256:" + hashlib.sha256((PROJECT / name).read_bytes()).hexdigest()
    manifest = tomllib.loads((PROJECT / "Manifest.toml").read_text())
    project = tomllib.loads((PROJECT / "Project.toml").read_text())
    assert set(identity["packages"]) == set(project["deps"])
    for package, version in identity["packages"].items():
        assert version == manifest["deps"][package][0]["version"]
        assert project["compat"][package] == "=" + version
    for response in replies[1:]:
        mechanism = response["data"]["mechanism"]
        assert mechanism["format"] == "catalyst-code-v1"
        assert bytes.fromhex(mechanism["bytes_hex"]) == (PROJECT / "worker.jl").read_bytes()
        assert mechanism["sha256"] == identity["worker_sha256"]


def test_actual_catalyst_trajectories_rates_and_balance_match_independent_reference(solved):
    requests, replies = solved
    for sent, response in zip(requests, replies[1:]):
        assert response["request_id"] == sent["request_id"]
        assert response["parent_execution_id"] == sent["parent_execution_id"]
        assert "refusal" not in response
        payload, output = sent["payload"], response["data"]
        order = payload["species_order"]
        initial = dict(zip(order, payload["initial_concentration_mol_m3"]))
        rate = payload["rate_constant_s_inv"]
        assert output["model"] == payload["model"]
        assert output["species_order"] == order
        assert output["time_s"] == payload["time_s"]
        assert len(output["concentration_mol_m3"]) == len(payload["time_s"])
        assert len(output["production_rate_mol_m3_s"]) == len(payload["time_s"])
        for time, values, rates in zip(output["time_s"], output["concentration_mol_m3"],
                                       output["production_rate_mol_m3_s"]):
            reference = {"A": initial["A"] * math.exp(-rate*time),
                         "B": initial["B"] - initial["A"] * math.expm1(-rate*time)}
            assert values == pytest.approx([reference[name] for name in order], rel=2e-8, abs=2e-8)
            observed = dict(zip(order, values))
            expected_rates = {"A": -rate*observed["A"], "B": rate*observed["A"]}
            assert rates == pytest.approx([expected_rates[name] for name in order], rel=2e-14, abs=2e-14)
            assert sum(values) == pytest.approx(sum(initial.values()), rel=2e-9, abs=2e-10)
            assert min(values) >= -2e-10
        assert output["concentration_mol_m3"][0] == payload["initial_concentration_mol_m3"]
        assert output["solver"] == {"algorithm": "Catalyst.Tsit5", "retcode": "Success", **payload["solver"]}


def test_state_reset_species_permutation_and_prescribed_closure(solved, julia):
    _, replies = solved
    outputs = [row["data"] for row in replies[1:]]
    assert outputs[0] == outputs[2]
    assert outputs[1]["concentration_mol_m3"] == [list(reversed(row)) for row in outputs[0]["concentration_mol_m3"]]
    assert outputs[1]["production_rate_mol_m3_s"] == [list(reversed(row)) for row in outputs[0]["production_rate_mol_m3_s"]]
    assert outputs[0]["concentration_mol_m3"] == outputs[-1]["concentration_mol_m3"]
    fresh = invoke(julia, frame(hello()) + frame(request("fresh")))
    assert fresh.returncode == 0, fresh.stderr.decode(errors="replace")
    assert frames(fresh.stdout)[1]["data"] == outputs[0]


def test_worker_refuses_invalid_data_and_actual_solver_exhaustion_then_recovers(julia):
    mutations = [
        {"model": "arbitrary-network"}, {"species_order": ["A", "A"]},
        {"species_order": ["C", "B"]}, {"initial_concentration_mol_m3": [True, .3]},
        {"initial_concentration_mol_m3": [-.1, .3]}, {"initial_concentration_mol_m3": [0., 0.]},
        {"initial_concentration_mol_m3": [1e-7, 0.]},
        {"initial_concentration_mol_m3": [1000., .1]},
        {"rate_constant_s_inv": True}, {"rate_constant_s_inv": -1},
        {"rate_constant_s_inv": 10.0001},
        {"temperature_k": 200.}, {"volume_m3": 0.}, {"time_s": [0., True]},
        {"temperature_k": 500.01}, {"volume_m3": 1.0001},
        {"time_s": [0., .1, .1]}, {"time_s": [1., 2.]}, {"time_s": [0., 100.]},
        {"time_s": [i/128 for i in range(129)]}, {"time_s": [0., 100.01]},
        {"time_s": [0.]}, {"expression": "run(`cmd.exe`)"},
        {"solver": {"reltol": 1e-6, "abstol_mol_m3": 1e-11, "max_steps": 100000}},
        {"solver": {"reltol": 1e-9, "abstol_mol_m3": 1e-11, "max_steps": True}},
    ]
    requests = [request("bad-" + str(i), **value) for i, value in enumerate(mutations)]
    wrong_units = request("wrong-units")
    wrong_units["semantics"]["concentration_unit"] = "kmol/m^3"
    requests.append(wrong_units)
    exhausted = request("exhausted", rate_constant_s_inv=10.,
                        solver={"reltol": 1e-9, "abstol_mol_m3": 1e-11, "max_steps": 1})
    proc = invoke(julia, b"".join(frame(value) for value in [hello(), *requests, exhausted, request("recovered")]))
    assert proc.returncode == 0, proc.stderr.decode(errors="replace")
    responses = frames(proc.stdout)[1:]
    assert len(responses) == len(requests) + 2
    for response in responses[:-1]:
        assert response["status"] == "refused", response
        assert "data" not in response
    assert responses[-2]["refusal"]["code"] == "NUMERICAL_FAILURE"
    assert "MaxIters" in responses[-2]["refusal"]["message"]
    assert responses[-1]["status"] == "ok"
    assert proc.stderr, "refusal diagnostics should remain on stderr"


@pytest.mark.parametrize("raw", [b"\0\0", (1024*1024+1).to_bytes(4, "big"),
    frame(hello()) + b" {}", b"\0\0\0\1\xff",
    b"\0\0\0\1" + b'{"x":' + b"["*17 + b"]"*17 + b"}",
    frame(hello()).replace(b'"request_id":"reaction-handshake"',
                          b'"request_id":"one","request_id":"two"')])
def test_worker_rejects_malformed_or_duplicate_handshake(julia, raw):
    # Recompute the length for the deliberately duplicated JSON object.
    if len(raw) > 4:
        raw = (len(raw)-4).to_bytes(4, "big") + raw[4:]
    proc = invoke(julia, raw)
    assert proc.returncode != 0
    assert proc.stdout == b""
    assert proc.stderr


def test_duplicate_nested_payload_key_is_refused_before_numerical_execution(julia):
    raw = frame(request())[4:]
    raw = raw.replace(b'"rate_constant_s_inv":0.7',
                      b'"rate_constant_s_inv":0.7,"rate_constant_s_inv":0.8')
    assert raw.count(b'"rate_constant_s_inv"') == 2
    proc = invoke(julia, frame(hello()) + len(raw).to_bytes(4, "big") + raw)
    assert proc.returncode != 0
    assert len(frames(proc.stdout)) == 1, "only the handshake may be returned"
    assert b"duplicate JSON key" in proc.stderr


@pytest.mark.parametrize("number", [b"NaN", b"1e9999"])
def test_nonfinite_json_number_cannot_reach_the_solver(julia, number):
    raw = frame(request())[4:].replace(b'"rate_constant_s_inv":0.7',
                                       b'"rate_constant_s_inv":' + number)
    proc = invoke(julia, frame(hello()) + len(raw).to_bytes(4, "big") + raw)
    assert proc.returncode != 0
    assert len(frames(proc.stdout)) == 1
    assert proc.stderr


@pytest.mark.parametrize("field", ["request_id", "parent_execution_id"])
@pytest.mark.parametrize("invalid", ["x"*161, "request\n"])
def test_identifier_outside_host_domain_is_refused_without_execution(julia, field, invalid):
    value = request()
    value[field] = invalid
    proc = invoke(julia, frame(hello()) + frame(value))
    assert proc.returncode != 0
    assert len(frames(proc.stdout)) == 1
    assert b"invalid request or execution identifier" in proc.stderr


def test_stale_transport_id_terminates_after_first_completed_occurrence(julia):
    value = request("duplicate")
    proc = invoke(julia, frame(hello()) + frame(value) + frame(value))
    assert proc.returncode != 0
    replies = frames(proc.stdout)
    assert len(replies) == 2 and replies[1]["status"] == "ok"
    assert b"duplicate or stale" in proc.stderr
