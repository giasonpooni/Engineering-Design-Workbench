"""Real all-three qualification. No runtime doubles, network provisioning or skips.

The caller supplies Blender, Godot and the compiled Bevy adapter. All executions
use the existing CIW Session and are retained in create-only output directories.
"""
import argparse
import copy
import json
from pathlib import Path
from unittest.mock import patch

from ciw import interactive_contract as c
from ciw import interactive_simulation as flow


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("blender","godot","bevy","output-dir"):
        parser.add_argument("--"+name,required=True)
    parser.add_argument("--adapter-root", type=Path, default=Path(__file__).resolve().parents[1]/"tools/interactive-simulation")
    args=parser.parse_args()
    sources={"adapter_root": args.adapter_root}
    root=Path(args.output_dir); root.mkdir(parents=True,exist_ok=False)
    s=c.read(Path(__file__).resolve().parents[1]/"examples/interactive-simulation/projectile.json")
    path,godot=flow.run_case(s,args.blender,"godot",args.godot,root/"01-godot", **sources)
    path,bevy=flow.extend_case(path,"bevy",args.bevy,root/"02-bevy", **sources)
    baseline={"godot":godot,"bevy":bevy}
    checks={}
    for engine,original in baseline.items():
        c.require(original["data"]["trace"]["engine_version"]!="TEST_DOUBLE_NOT_NATIVE","fake runtime is not qualification")
        c.require(c.metrics(original["data"])["status"]=="PASS",engine+" reference failed")
        path,replayed=flow.extend_case(path,engine,getattr(args,engine),root/("03-replay-"+engine),execution_id=original["execution_id"], **sources)
        c.require(replayed["execution_id"]!=original["execution_id"] and replayed["result_id"]!=original["result_id"],"replay reused occurrence")
        c.require(replayed["data"]["trace"]["observations"]==original["data"]["trace"]["observations"],"same-build observation reproduction failed")
        checks[engine]={"engine_version":original["data"]["trace"]["engine_version"],
                        "baseline":c.metrics(original["data"]),"original_execution_id":original["execution_id"],
                        "replay_execution_id":replayed["execution_id"]}
    path,bad=flow.extend_case(path,"bevy",args.bevy,root/"04-injected-regression",fault="double-gravity", **sources)
    c.require(c.metrics(bad["data"])["status"]=="FAIL","intentional regression was not detected")
    path,fixed=flow.extend_case(path,"bevy",args.bevy,root/"05-corrected", **sources)
    c.require(c.metrics(fixed["data"])["status"]=="PASS","corrected implementation failed")
    checks["diagnostic_regression"]={"fault_execution_id":bad["execution_id"],"failure":c.metrics(bad["data"]),
                                     "corrected_execution_id":fixed["execution_id"]}
    for engine in ("godot","bevy"):
        refined=copy.deepcopy(s); refined["step_hz"]*=2; refined["ticks"]*=2
        path,fine=flow.extend_case(path,engine,getattr(args,engine),root/("06-refined-"+engine),scenario=refined, **sources)
        ratio=c.metrics(fine["data"])["max_position_error_m"]/checks[engine]["baseline"]["max_position_error_m"]
        c.require(.45 < ratio < .55,"first-order timestep refinement failed")
        checks[engine]["refinement_ratio"]=ratio
        inputs=copy.deepcopy(s); inputs["inputs"]=[{"id":"kick-013","tick":13,"delta_v_m_s":[.3,.2,0]}]
        path,kicked=flow.extend_case(path,engine,getattr(args,engine),root/("07-input-"+engine),scenario=inputs, **sources)
        c.require(c.metrics(kicked["data"])["status"]=="PASS","input-phase reference failed")
        checks[engine]["input_execution_id"]=kicked["execution_id"]
    with patch.object(flow,"Binding",side_effect=AssertionError("offline reader launched runtime")), patch.object(c,"reference",side_effect=AssertionError("offline reader recomputed reference")):
        retained=flow.inspect(path)
    report={"status":"PASS","scope":"Blender-authored GLB; Godot SceneTree and Bevy ECS point-projectile; same-build Linux qualification",
            "checks":checks,"last_workspace":str(path),"retained_execution_count":len(retained["executions"]),
            "not_claimed":["contact physics","Bevy renderer/GltfPlugin","live player controls","checkpoint continuation",
                           "cross-platform determinism","physical validation","industrial qualification"]}
    flow.write_new(root/"qualification.json",report)
    print(json.dumps(report,indent=2))


if __name__=="__main__": main()
