"""Contract/reference tests use labelled synthetic traces, never engine evidence."""
import copy
from pathlib import Path
import struct
import sys
import uuid

import pytest

from ciw import interactive_contract as c
from ciw.interactive_simulation import run_process, write_new


def scenario():
    return {"schema": c.SCENARIO, "name": "unit-fixture", "model": "point-projectile-no-contact.v1",
            "entity": "projectile", "frame": "local-y-up-m", "p0_m": [0,5,0], "v0_m_s": [2,0,0],
            "gravity_m_s2": [0,-9.81,0], "mass_kg": 1, "step_hz": 120, "ticks": 60, "inputs": []}


def synthetic_trace(s=None, engine="bevy", factor=1):
    """Explicit test double; native qualification never imports this function."""
    s = copy.deepcopy(s or scenario())
    request = {"schema": "ciw.projectile-request.v1", "scenario": s, "asset_sha256": "sha256:"+"a"*64,
               "nonce": uuid.uuid4().hex, "fault": "none" if factor == 1 else "double-gravity"}
    p, v, rows, events = s["p0_m"][:], s["v0_m_s"][:], [], []
    for n in range(s["ticks"]+1):
        if n:
            for event in s["inputs"]:
                if event["tick"] == n:
                    v = [x+y for x,y in zip(v,event["delta_v_m_s"])]
                    events.append({"id": event["id"], "requested_tick": n, "applied_tick": n, "delta_v_m_s": event["delta_v_m_s"]})
            v = [x+factor*g/s["step_hz"] for x,g in zip(v,s["gravity_m_s2"])]
            p = [x+y/s["step_hz"] for x,y in zip(p,v)]
        rows.append({"tick": n, "time_s": n/s["step_hz"], "entity": "projectile", "p_m": p[:], "v_m_s": v[:]})
    trace = {"engine": engine, "engine_version": "TEST_DOUBLE_NOT_NATIVE", "state_owner": engine,
             "clock": "integer-ticks", "phase": "initial_then_post_step", "request_sha256": c.sha(c.canonical(request)),
             "asset_sha256": request["asset_sha256"], "precision": {"bevy": "f64", "godot": "Vector3-float32"}[engine],
             "import_report": {"landmarks_m": copy.deepcopy(c.LANDMARKS), "vertex_count": 72,
                               "bounds_min_m": [-.25]*3, "bounds_max_m": [.25]*3},
             "observations": rows, "events": events, "complete": True}
    return {"schema": c.TRACE, "request": request, "trace": trace}


def glb_fixture():
    """Parser fixture only, not authored by Blender."""
    binary = struct.pack("<18f", *[-.25,0,0, .25,0,0, 0,-.25,0, 0,.25,0, 0,0,-.25, 0,0,.25])
    doc = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": len(binary)}],
           "nodes": [{"name": name, "translation": pos} for name,pos in c.LANDMARKS.items()] + [{"name": "projectile", "mesh": 0}],
           "scenes": [{"nodes": list(range(5))}], "scene": 0,
           "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "mode": 0}]}],
           "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(binary)}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": 6, "type": "VEC3", "min": [-.25]*3, "max": [.25]*3}]}
    raw = c.canonical(doc)
    raw += b" "*((-len(raw))%4)
    return struct.pack("<4sII", b"glTF", 2, 28+len(raw)+len(binary)) + struct.pack("<II",len(raw),0x4E4F534A)+raw+struct.pack("<II",len(binary),0x004E4942)+binary


def test_analytic_endpoint_and_discretization():
    s = scenario()
    assert c.reference(s,60)[0] == pytest.approx([1,3.77375,0])
    result = c.metrics(synthetic_trace(s))
    assert result["status"] == "PASS"
    assert result["max_position_error_m"] == pytest.approx(.0204375)
    assert result["max_velocity_error_m_s"] < 1e-12


def test_refinement_reduces_first_order_error():
    s = scenario(); s["step_hz"] *= 2; s["ticks"] *= 2
    assert c.metrics(synthetic_trace(s))["max_position_error_m"] == pytest.approx(c.metrics(synthetic_trace())["max_position_error_m"]/2)


def test_detects_intentional_regression():
    result = c.comparison(synthetic_trace(), synthetic_trace(factor=2))
    assert result["left"]["status"] == "PASS"
    assert result["right"]["status"] == "FAIL"
    assert result["right"]["first_out_of_policy_tick"] == 1


def test_input_phase_and_order():
    s = scenario(); s["inputs"] = [{"id": "kick", "tick": 2, "delta_v_m_s": [1,0,0]}]
    trace = synthetic_trace(s)
    c.validate_trace(trace)
    assert c.reference(s,0)[1][0] == 2
    assert c.reference(s,1)[1][0] == 2
    assert c.reference(s,2)[1][0] == 3
    assert c.metrics(trace)["status"] == "PASS"


@pytest.mark.parametrize("field,value", [("step_hz", True), ("step_hz",0), ("ticks",2001), ("mass_kg",0),
    ("frame","other"), ("p0_m",[float("nan"),0,0]), ("v0_m_s",[0,0]), ("model","unknown")])
def test_invalid_scenarios(field,value):
    s = scenario(); s[field]=value
    with pytest.raises(ValueError): c.validate_scenario(s)


def test_duplicate_input_ids_refused():
    s = scenario(); s["inputs"]=[{"id":"x","tick":1,"delta_v_m_s":[0,0,0]}]*2
    with pytest.raises(ValueError,match="duplicate"): c.validate_scenario(s)


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e999}', b'not json'])
def test_strict_json(raw):
    with pytest.raises(ValueError): c.parse(raw)


@pytest.mark.parametrize("mutation", [
    lambda t: t["trace"].update(state_owner="python"),
    lambda t: t["trace"].update(asset_sha256="sha256:"+"b"*64),
    lambda t: t["trace"].update(request_sha256="sha256:"+"b"*64),
    lambda t: t["trace"].update(phase="render_frame"),
    lambda t: t["trace"]["observations"][2].update(tick=3),
    lambda t: t["trace"]["observations"][2].update(time_s=9),
    lambda t: t["trace"]["observations"][2].update(entity="other"),
    lambda t: t["trace"]["import_report"]["landmarks_m"].update(axis_y=[0,0,2]),
    lambda t: t["trace"]["import_report"].update(bounds_max_m=[1,1,1]),
    lambda t: t["trace"]["observations"][0].update(p_m=[4,5,6]),
])
def test_changed_bindings_refused(mutation):
    trace=synthetic_trace(); mutation(trace)
    with pytest.raises(ValueError): c.validate_trace(trace)


def test_missing_observation_is_not_pass_or_zero():
    trace=synthetic_trace()
    trace["trace"]["observations"][3].update(p_m=None,v_m_s=None)
    with pytest.raises(ValueError,match="completeness"): c.validate_trace(trace)
    trace["trace"]["complete"]=False
    report=c.comparison(synthetic_trace(),trace)
    assert report["right"]["status"] == "INCOMPLETE"
    assert report["cross_runtime_max_position_m"] is None


def test_partial_trace_remains_incomplete():
    trace=synthetic_trace(); trace["trace"]["observations"]=trace["trace"]["observations"][:3]
    trace["trace"]["complete"]=False
    assert c.metrics(trace)["status"] == "INCOMPLETE"


def test_mismatched_grid_is_not_compared_by_index():
    s=scenario(); s["step_hz"]=60; s["ticks"]=30
    with pytest.raises(ValueError,match="incomparable"): c.comparison(synthetic_trace(),synthetic_trace(s))


def test_glb_embedded_profile_and_corruption():
    raw=glb_fixture(); c.validate_glb(raw)
    with pytest.raises(ValueError): c.validate_glb(raw[:-1])
    with pytest.raises(ValueError): c.validate_glb(b"BAD!"+raw[4:])


def test_create_only_artifact(tmp_path):
    path=tmp_path/"record.json"; write_new(path,{"old":1})
    with pytest.raises(FileExistsError): write_new(path,{"new":2})
    assert c.read(path)=={"old":1}


def test_actual_child_success(tmp_path):
    assert run_process([sys.executable,"-c","print('process test, not an engine')"],tmp_path)["returncode"] == 0


def test_actual_child_failure(tmp_path):
    with pytest.raises(RuntimeError,match="runtime exit 7"):
        run_process([sys.executable,"-c","raise SystemExit(7)"],tmp_path)


def test_actual_child_timeout(tmp_path):
    with pytest.raises(RuntimeError,match="timeout"):
        run_process([sys.executable,"-c","import time; time.sleep(60)"],tmp_path,timeout=.05)
