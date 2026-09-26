"""Opt-in tests that exchange actual frames with Julia, never an imitation."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil

import pytest

from ciw import julia_oscillator as jo

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.integration
DIMENSIONLESS = {"layout": "row-major", "input_units": "dimensionless", "output_units": "dimensionless",
                 "frame": "declared-cartesian", "clock": "not-applicable"}
PHYSICAL = {"layout": "row-major", "input_units": "SI", "output_units": "SI",
            "frame": "one-dimensional-inertial", "clock": "declared-simulation-time"}


def _frame(value):
    raw = json.dumps(value, separators=(",", ":"), allow_nan=False).encode()
    return len(raw).to_bytes(4, "big") + raw


def _frames(raw):
    values = []
    while raw:
        assert len(raw) >= 4, "stdout contains an incomplete header or unframed diagnostics"
        count = int.from_bytes(raw[:4], "big")
        assert 0 < count <= 4*1024*1024
        assert len(raw) >= count+4, "stdout contains an incomplete payload"
        values.append(json.loads(raw[4:4+count]))
        raw = raw[4+count:]
    return values


@pytest.fixture(scope="module")
def julia():
    executable = os.environ.get("CIW_TEST_JULIA")
    if not executable:
        pytest.skip("set CIW_TEST_JULIA and CIW_TEST_JULIA_DEPOT for genuine Julia gates")
    assert Path(executable).is_file(), "configured Julia executable is missing"
    env = dict(os.environ, JULIA_PKG_OFFLINE="true", JULIA_NUM_THREADS="1")
    if depot := os.environ.get("CIW_TEST_JULIA_DEPOT"):
        env["JULIA_DEPOT_PATH"] = depot
    return executable, env


def invoke(julia, payload, *, native=False):
    executable, env = julia
    project = ROOT/"runtimes"/("native-interop" if native else "julia-oscillator")
    worker = project/("worker.jl" if native else "oscillator_worker.jl")
    return subprocess.run([executable, "--startup-file=no", "--history-file=no", f"--project={project}", str(worker)],
                          input=payload, capture_output=True, env=env, timeout=300)


def model():
    return {"model": {"omega_0_rad_s": 2.0, "gamma_s_inv": 0.1, "mass_kg": 2.0},
            "initial_state": {"q0_m": 1.0, "v0_m_s": -0.25}, "time_s": [0.0, 0.1, 0.2, 0.3],
            "solver": {"abstol": 1e-10, "reltol": 1e-10, "maxiters": 100000}}


def old_hello():
    return {"schema": "ciw.julia-worker-handshake-request.v1", "request_id": "handshake", "operation_id": jo.OPERATION}


def old_request(rid="solve", **changes):
    return {"schema": "ciw.julia-oscillator-request.v1", "request_id": rid, "operation_id": jo.OPERATION,
            **model(), **changes}


def test_old_worker_genuine_handshake_solve_and_analytic_reference(julia):
    proc = invoke(julia, _frame(old_hello()) + _frame(old_request()))
    assert proc.returncode == 0, proc.stderr.decode(errors="replace")
    hello, solved = _frames(proc.stdout)
    assert hello["request_id"] == "handshake"
    assert hello["identity"]["julia_version"].startswith("1.10.")
    assert solved["status"] == "ok", solved
    assert solved["request_id"] == solved["data"]["request_id"] == "solve"
    expected = jo.analytic_oracle(model())
    for name in ("q_m", "v_m_s", "energy_j"):
        assert solved["data"][name] == pytest.approx(expected[name], abs=2e-8, rel=2e-8)


def test_old_worker_persistent_a_b_a_and_restart(julia):
    a = old_request("a")
    b = old_request("b", initial_state={"q0_m": -0.5, "v0_m_s": 0.0})
    again = old_request("a-again")
    proc = invoke(julia, b"".join(_frame(x) for x in (old_hello(), a, b, again)))
    assert proc.returncode == 0, proc.stderr.decode(errors="replace")
    responses = _frames(proc.stdout)[1:]
    assert [x["request_id"] for x in responses] == ["a", "b", "a-again"]
    assert all(x["status"] == "ok" for x in responses)
    assert responses[0]["data"]["q_m"] == responses[2]["data"]["q_m"]
    assert responses[0]["data"]["q_m"] != responses[1]["data"]["q_m"]
    fresh = invoke(julia, _frame(old_hello()) + _frame(old_request("fresh")))
    assert fresh.returncode == 0, fresh.stderr.decode(errors="replace")
    assert _frames(fresh.stdout)[1]["data"]["q_m"] == responses[0]["data"]["q_m"]


@pytest.mark.parametrize("bad", [b"\0", b"\0\0\0\0", (4*1024*1024+1).to_bytes(4,"big"),
                                   b"\0\0\0\5{}", b"\0\0\0\1{", b"\0\0\0\1\xff"])
def test_old_worker_rejects_bad_frames_and_json(julia, bad):
    proc = invoke(julia, bad)
    assert proc.returncode != 0
    assert proc.stdout == b""
    assert proc.stderr


def test_old_worker_refuses_extra_fields_and_nonfinite_math(julia):
    extra = old_request("extra", executable="arbitrary")
    invalid = old_request("invalid", initial_state={"q0_m": True, "v0_m_s": 0.0})
    proc = invoke(julia, b"".join(_frame(x) for x in (old_hello(), extra, invalid, old_request("recovered"))))
    assert proc.returncode == 0, proc.stderr.decode(errors="replace")
    values = _frames(proc.stdout)
    assert [x["status"] for x in values[1:]] == ["refused", "refused", "ok"]


def hello():
    return {"schema": "ciw.native-interop-handshake-request.v1", "request_id": "native-handshake"}


def request(profile, payload, rid="native-a"):
    return {"schema": "ciw.native-interop-request.v1", "request_id": rid, "parent_execution_id": "execution:test",
            "profile": profile, "arithmetic": "exact-d256" if profile == "affine-d256.v1" else "binary64",
            "semantics": PHYSICAL if "oscillator" in profile else DIMENSIONLESS, "payload": payload}


def affine():
    return {"rows": 2, "columns": 3, "a_row_major": [2,1,-1,-1,3,2], "b": [5,-2],
            "x0": [3,4,2], "delta_x": [0.25,-0.5,0.125]}


def qp():
    return {"rows": 2, "columns": 2, "j_row_major": [2,1,-1,3], "y0": [1,-2], "target": [0,0],
            "regularization": 1.0, "lower": [-1,-1], "upper": [1,1], "max_iterations": 1000}


def native_run(julia, requests):
    proc = invoke(julia, _frame(hello()) + b"".join(_frame(x) for x in requests), native=True)
    assert proc.returncode == 0, proc.stderr.decode(errors="replace")
    outputs = _frames(proc.stdout)
    assert outputs[0]["request_id"] == "native-handshake"
    for source, response in zip(requests, outputs[1:], strict=True):
        assert response["request_id"] == source["request_id"]
        assert response["parent_execution_id"] == source["parent_execution_id"]
    return outputs[1:]


def test_native_affine_binary64_exact_layout_persistent(julia):
    base = affine()
    exact = {key: [int(v*256) for v in value] if isinstance(value,list) else value for key,value in base.items()}
    inputs = [request("affine-binary64.v1",base,"a"), request("affine-d256.v1",exact,"b"),
              request("affine-binary64.v1",base,"a-again")]
    outputs = native_run(julia,inputs)
    assert all(x["status"] == "ok" for x in outputs), outputs
    assert outputs[0]["data"] == outputs[2]["data"]
    expected = {"baseline_output": [13,11], "contributions": [0.5,-0.5,-0.125,-0.25,-1.5,0.25],
                "predicted_delta": [-0.125,-1.5], "predicted_output": [12.875,9.5],
                "model_output": [12.875,9.5], "residual": [0,0]}
    for field, values in expected.items():
        assert outputs[0]["data"][field] == values
        assert outputs[1]["data"][field] == [int(v*65536) for v in values]


def test_native_control_tsit5_and_independent_analytic_reference(julia):
    source = model()
    control = {key:value for key,value in source.items() if key != "solver"}
    outputs = native_run(julia,[request("oscillator-tsit5.v1",source,"tsit5"), request("control-oscillator.v1",control,"control")])
    expected = jo.analytic_oracle(source)
    for output in outputs:
        assert output["status"] == "ok", output
        for name in ("q_m","v_m_s","energy_j"):
            assert output["data"][name] == pytest.approx(expected[name],abs=2e-8,rel=2e-8)
    assert outputs[1]["data"]["solver"]["algorithm"] == "ControlSystemsBase.lsim"
    assert outputs[1]["data"]["solver"]["method"] == "zoh"


def test_native_jump_coupled_active_and_changed_target(julia):
    interior = qp()
    active = {**qp(),"j_row_major":[1,0,0,1],"y0":[2,-2],"lower":[-0.5,-0.5],"upper":[0.5,0.5]}
    changed = {**qp(),"target":[1,-2]}
    outputs = native_run(julia,[request("design-qp.v1",p,f"qp-{i}") for i,p in enumerate((interior,active,changed))])
    for result,delta,objective in zip(outputs,([-0.6,0.4],[-0.5,0.5],[0,0]),(0.3,2.5,0),strict=True):
        assert result["status"] == "ok",result
        data=result["data"]
        assert data["delta"] == pytest.approx(delta,abs=2e-7)
        assert data["objective_value"] == pytest.approx(objective,abs=2e-7)
        assert max(data["lower_residual"]+data["upper_residual"]) <= 1e-8
        assert data["solver"]["termination_status"] == "OPTIMAL"


def test_native_jump_rectangular_independent_stationarity(julia):
    problem = {"rows":1,"columns":3,"j_row_major":[1,2,0],"y0":[1],"target":[0],
               "regularization":1,"lower":[-1,-1,-1],"upper":[1,1,1],"max_iterations":1000}
    result, = native_run(julia,[request("design-qp.v1",problem)])
    assert result["status"] == "ok",result
    data=result["data"]
    assert data["delta"] == pytest.approx([-1/6,-1/3,0],abs=2e-7)
    d=data["delta"]
    residual=1+d[0]+2*d[1]
    objective=0.5*residual**2+0.5*sum(value**2 for value in d)
    assert objective == pytest.approx(1/12,abs=1e-12)
    assert data["objective_value"] == pytest.approx(objective,abs=1e-12)
    assert [residual+d[0],2*residual+d[1],d[2]] == pytest.approx([0,0,0],abs=2e-7)


def test_native_refusal_iteration_limit_irregular_grid_and_malformed_shapes(julia):
    irregular={key:value for key,value in model().items() if key != "solver"}
    irregular["time_s"]=[0.0,0.1,0.3]
    # HiGHS can finish the 2D unconstrained fixture during initialization, even
    # with a zero iteration limit. This active-bound fixture needs an iteration.
    limited={"rows":8,"columns":8,"j_row_major":[int(i==j) for i in range(8) for j in range(8)],
             "y0":[10,-10]*4,"target":[0]*8,"regularization":1,
             "lower":[-0.1]*8,"upper":[0.1]*8,"max_iterations":0}
    cases=[request("design-qp.v1",limited,"limit"),
           request("design-qp.v1",{**qp(),"lower":[2,2]},"bounds"),
           request("control-oscillator.v1",irregular,"grid"),
           request("affine-binary64.v1",{**affine(),"a_row_major":[1]},"shape"),
           request("affine-d256.v1",{**affine(),"delta_x":[True,0,0]},"exact-type")]
    outputs=native_run(julia,cases)
    assert all(x["status"]=="refused" and "data" not in x for x in outputs),outputs
    assert "ITERATION_LIMIT" in outputs[0]["refusal"]["message"]


def test_native_duplicate_occurrence_terminates_worker(julia):
    item=request("affine-binary64.v1",affine())
    proc=invoke(julia,_frame(hello())+_frame(item)+_frame(item),native=True)
    assert proc.returncode != 0
    assert len(_frames(proc.stdout))==2
    assert b"duplicate or stale" in proc.stderr


@pytest.mark.parametrize("bad",[b"\0",b"\0\0\0\0",(1024*1024+1).to_bytes(4,"big"),
                                  b"\0\0\0\5{}",b"\0\0\0\1{",b"\0\0\0\1\xff"])
def test_native_rejects_truncated_empty_oversized_and_malformed_frames(julia,bad):
    proc=invoke(julia,bad,native=True)
    assert proc.returncode != 0
    assert proc.stdout == b""
    assert proc.stderr


def test_native_missing_packages_are_unavailable_without_installation(julia,tmp_path):
    executable,env=julia
    empty=tmp_path/"empty-depot"
    empty.mkdir()
    env=dict(env,JULIA_DEPOT_PATH=str(empty),JULIA_PKG_OFFLINE="true")
    proc=invoke((executable,env),_frame(hello()),native=True)
    assert proc.returncode != 0
    assert proc.stdout == b""
    assert not (empty/"packages").exists()


def test_native_nested_snapshot_normalizes_identity_paths(julia, tmp_path):
    # The imported sibling is a valid <=256-character path, but the textual
    # native-interop/../ spelling exceeds Win32 MAX_PATH before normalization.
    suffix = "/julia-oscillator/oscillator_worker.jl"
    wanted = 256 - len(suffix)
    padding = wanted - len(str(tmp_path)) - 1
    assert 1 <= padding <= 255, "Use a shorter pytest --basetemp for this path regression"
    root = tmp_path / ("s" * padding)
    project = root / "native-interop"
    project.mkdir(parents=True)
    old = root / "julia-oscillator"
    old.mkdir()
    for name in ("Project.toml", "Manifest.toml", "worker.jl"):
        shutil.copyfile(ROOT/"runtimes/native-interop"/name, project/name)
    old_worker = old/"oscillator_worker.jl"
    shutil.copyfile(ROOT/"runtimes/julia-oscillator/oscillator_worker.jl", old_worker)
    unresolved = project/".."/"julia-oscillator"/"oscillator_worker.jl"
    assert len(str(unresolved)) > 260 and len(str(old_worker)) <= 256
    executable, env = julia
    proc = subprocess.run([executable, "--startup-file=no", "--history-file=no", f"--project={project}", str(project/"worker.jl")],
                          input=_frame(hello()), capture_output=True, env=env, timeout=300)
    assert proc.returncode == 0, proc.stderr.decode(errors="replace")
    response, = _frames(proc.stdout)
    expected = "sha256:" + hashlib.sha256(old_worker.read_bytes()).hexdigest()
    assert response["identity"]["oscillator_worker_sha256"] == expected
