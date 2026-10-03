"""Real CIW Session/record lifecycle with explicit fake runtime bindings.

These tests do not count as Blender, Godot or Bevy qualification. The separate
check_interactive_simulation.py command requires all actual engine binaries.
"""
import base64
import copy
from pathlib import Path
from unittest.mock import patch

import pytest

from ciw import interactive_contract as c
from ciw import interactive_simulation as flow
from test_interactive_contract import scenario, synthetic_trace, glb_fixture


class FakeBinding:
    def __init__(self, engine, executable, expected=None):
        self.engine=engine
        self.identity={"provider":"ciw.interactive."+engine, "adapter_sha256":"sha256:"+"7"*64,
                       "test_double":True}
        c.require(expected is None or expected==self.identity,"wrong fake binding")
    def runtime_identity(self): return copy.deepcopy(self.identity)
    def invoke(self, request=None, asset=None):
        if self.engine=="blender":
            raw=glb_fixture()
            return {"schema":c.AUTHOR,"format":"glb","asset_sha256":c.sha(raw),
                    "asset_b64":base64.b64encode(raw).decode(),"generator_sha256":self.identity["adapter_sha256"],
                    "report":{"blender_version":"TEST_DOUBLE_NOT_BLENDER","export_y_up":True,"radius_m":.25}}
        result=synthetic_trace(request["scenario"],self.engine,2 if request["fault"]=="double-gravity" else 1)
        result["request"]=copy.deepcopy(request)
        result["trace"].update(request_sha256=c.sha(c.canonical(request)),asset_sha256=c.sha(asset))
        return result


@pytest.mark.parametrize("engine",["godot","bevy"])
def test_session_retains_and_reopens_without_runtime(tmp_path,engine):
    with patch.object(flow,"Binding",FakeBinding):
        path,result=flow.run_case(scenario(),"unused",engine,"unused",tmp_path/"first")
    with patch.object(flow,"Binding",side_effect=AssertionError("reader launched runtime")), patch.object(c,"reference",side_effect=AssertionError("reader recomputed reference")):
        report=flow.inspect(path)
    assert len(report["executions"])==3
    assert report["comparisons"][0]["left"]["status"]=="PASS"
    assert result["verification_id"] is None
    assert result["verification_status"]=="not_verified"


def test_replay_new_id_and_retained_history(tmp_path):
    with patch.object(flow,"Binding",FakeBinding):
        first,old=flow.run_case(scenario(),"unused","godot","unused",tmp_path/"first")
        second,new=flow.extend_case(first,"godot","unused",tmp_path/"second",execution_id=old["execution_id"])
    assert old["execution_id"] != new["execution_id"] and old["result_id"] != new["result_id"]
    assert old["data"]["request"]["nonce"] != new["data"]["request"]["nonce"]
    assert old["data"]["trace"]["observations"] == new["data"]["trace"]["observations"]
    assert old["execution_id"] in [x["execution_id"] for x in flow.inspect(second)["executions"]]


def test_cross_runtime_candidate_and_fault_are_distinct(tmp_path):
    with patch.object(flow,"Binding",FakeBinding):
        first,_=flow.run_case(scenario(),"unused","godot","unused",tmp_path/"first")
        second,bevy=flow.extend_case(first,"bevy","unused",tmp_path/"second")
        third,bad=flow.extend_case(second,"bevy","unused",tmp_path/"bad",fault="double-gravity")
    assert bevy["runtime"]["provider"].endswith("bevy")
    assert bad["data"]["request"]["fault"]=="double-gravity"
    assert flow.inspect(third)["comparisons"][-1]["right"]["status"]=="FAIL"


def test_refused_runtime_is_saved_not_a_success(tmp_path):
    class Broken(FakeBinding):
        def invoke(self,*args):
            if self.engine!="blender": raise RuntimeError("intentional process test failure")
            return super().invoke(*args)
    with patch.object(flow,"Binding",Broken), pytest.raises(ValueError,match="retained refusal"):
        flow.run_case(scenario(),"unused","godot","unused",tmp_path/"failed")
    report=flow.inspect(tmp_path/"failed/workspace.json")
    assert report["executions"][-1]["status"]=="refused"
    assert report["executions"][-1]["result_id"] is None


def test_existing_destination_is_not_overwritten(tmp_path):
    target=tmp_path/"occupied"; target.mkdir(); (target/"keep").write_text("original")
    with pytest.raises(FileExistsError): flow.run_case(scenario(),"unused","godot","unused",target)
    assert (target/"keep").read_text()=="original"


def test_custom_dependency_corruption_is_detected(tmp_path):
    with patch.object(flow,"Binding",FakeBinding):
        path,result=flow.run_case(scenario(),"unused","godot","unused",tmp_path/"first")
    session=flow.open_saved(path,tmp_path/"read")
    session.results[result["result_id"]]["parameters"]["asset_record_digest"]="sha256:"+"f"*64
    with pytest.raises(ValueError,match="asset dependency"):
        flow.validate_session(session)
