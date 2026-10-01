"""Execute native asset production, refusal/correction, export and offline inspection.

The workcell and prerequisite reviews are conspicuously TEST FIXTURES, not evidence
that a human approved 1792's art or history. No game checkout or model API is used.
"""
from __future__ import annotations
import argparse
import base64
import contextlib
import io
import json
from pathlib import Path
import shutil
import uuid
from unittest.mock import patch

from ciw import foundry_asset_worker as worker, foundry_asset_contract as contract
from ciw import foundry_pipeline as pipeline, foundry_packets as packets
from ciw.control_contracts import load, save_new, bytes_ref
from ciw.foundry_pipeline_cli import main as pipeline_cli
from ciw.foundry_workflow import _accepted_result
from ciw.interactive_simulation import file_sha


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--blender',type=Path,required=True)
    ap.add_argument('--godot',type=Path,required=True)
    ap.add_argument('--output-dir',type=Path,required=True)
    args=ap.parse_args();out=args.output_dir
    out.mkdir(parents=True,exist_ok=False)
    checks=[]
    def check(ok,label):
        if not ok:raise AssertionError(label)
        checks.append({'check':label,'status':'PASS'})
    source=out/'workcell';source.mkdir()
    (source/'brief.md').write_text('# Original workbench reference prop\n\nTEST WORKCELL. Not the 1792 checkout.\n'
        'Requested geometry: 1.8 m long, 0.7 m deep, 0.9 m high, four legs and lower rails.\n'
        'Y-up metre-scale technical blockout only; no claim of historical form, wood strength or final art.\n')
    project=pipeline.create_project('1792-workbench-qualification-fixture',source,out/'project')
    original=packets.inventory(source)
    artifact=out/'fixture-review-artifacts';artifact.mkdir()
    (artifact/'READ_THIS.md').write_text('TEST FIXTURE ONLY. The following review records test dependency handling.\n'
        'No human artistic, historical or production approval occurred. They do not approve the 1792 project.\n')
    evidence={}
    for task in ('vision','historical-scope'):
        path=out/('fixture-review-'+task)
        pipeline.review_task(project,task,source,artifact,path,producer='TEST-FIXTURE-PRODUCER',
            reviewer='TEST-FIXTURE-REVIEWER-NOT-A-PERSON',decision='approved',evidence=evidence)
        evidence[task]=path
    with contextlib.redirect_stdout(io.StringIO()):
        code=pipeline_cli(['packet',str(out/'project/project.json'),'--source-root',str(source),
            '--task','art-target','--assignee','operator-bound-blender-recipe','--allow-write',contract.OUTPUT,
            '--context','brief.md','--evidence','vision='+str(evidence['vision']),
            '--evidence','historical-scope='+str(evidence['historical-scope']),'--output-dir',str(out/'packet')])
    check(code==0,'existing packet CLI issues scoped asset contract only after declared prerequisite fixtures')
    packet=load(out/'packet/packet.json')
    bsha,gsha=file_sha(args.blender),file_sha(args.godot)
    options={'packet_id':packet['record_digest'],'blender_sha256':bsha,'godot_sha256':gsha,'evidence':evidence}
    # All refusals here must precede native dispatch.
    for name,overrides in [('wrong-packet',{'packet_id':'sha256:'+'0'*64}),
                          ('wrong-executable',{'blender_sha256':'sha256:'+'0'*64}),
                          ('unresolved-prerequisites',{'evidence':{}}),
                          ('insufficient-budget',{'max_operations':1})]:
        try:worker.run_asset(project,packet,source,args.blender,args.godot,out/name,**(options|overrides))
        except ValueError:check(not (out/name).exists(),name+' refuses before destination creation')
        else:raise AssertionError(name+' unexpectedly dispatched')
    campaigns={}
    for name,legs,repair,status in [('baseline',4,False,'completed'),('corrected',3,True,'completed'),('exhausted',3,False,'incomplete')]:
        run=worker.run_asset(project,packet,source,args.blender,args.godot,out/name,legs=legs,repair=repair,**options)
        check(run['status']==status,name+' original production disposition')
        campaigns[name]=run
    # Reinspect all original retained records with process creation explicitly forbidden.
    kept={p:p.read_bytes() for n in campaigns for p in (out/n).rglob('*') if p.is_file()}
    inspections={}
    with patch('subprocess.Popen',side_effect=AssertionError('offline operation launched a process')):
        for name in campaigns:inspections[name]=worker.inspect_asset(out/name)
        check(inspections['corrected']['attempt_count']==3,'rejected authoring plus correction and dependent fresh-process regression retained')
        check(inspections['exhausted']['jobs']['workbench']['status']=='rejected' and
            inspections['exhausted']['jobs']['workbench-regression']['status']=='blocked','no acceptance or regression after exhausted repair')
        check(all(p.read_bytes()==v for p,v in kept.items()),'all original native evidence bytes unchanged during offline reinspection')
        exported=worker.export_asset(out/'corrected',source,out/'accepted')
        check(exported['parent_task_acceptance']=='not_performed' and exported['publication']=='not_performed','candidate export does not approve the parent task or publish a game')
        try:worker.export_asset(out/'exhausted',source,out/'bad-export')
        except ValueError:check(not (out/'bad-export').exists(),'rejected export creates no candidate destination')
        else:raise AssertionError('rejected export permitted')
    receipt,result=_accepted_result(out/'corrected',inspections['corrected'],'workbench')
    raw=(out/'accepted/candidate'/contract.OUTPUT).read_bytes()
    check(raw==base64.b64decode(result['data']['asset_b64'],validate=True),'export resolves exact accepted PRIMARY asset bytes')
    check(packets.inventory(out/'accepted/candidate')==result['data']['candidate_inventory'],'complete candidate matches retained scoped inventory')
    scoped=packets.check_candidate(packet,project,pipeline.task_for(project,'art-target'),out/'accepted/candidate',expected_packet_id=packet['record_digest'])
    check(scoped['status']=='scope_passed' and scoped['changes']==[{'path':contract.OUTPUT,'change':'added'}],'external candidate contains only the allowed new asset')
    _,base_result=_accepted_result(out/'baseline',inspections['baseline'],'workbench')
    _,reg_result=_accepted_result(out/'corrected',inspections['corrected'],'workbench-regression')
    check(len({base_result['execution_id'],result['execution_id'],reg_result['execution_id']})==3,'reproduction uses distinct original execution identities')
    observed=contract.observe_glb(raw)
    check(observed['parts']==contract.observe_glb(base64.b64decode(base_result['data']['asset_b64']))['parts'] and
        observed['parts']==contract.observe_glb(base64.b64decode(reg_result['data']['asset_b64']))['parts'],
        'independent baseline/corrected/regression actual decoded geometry agrees')
    first=load(out/'corrected/attempt-0001-graph.json')['nodes']['candidate']['result']
    rejected=base64.b64decode(first['data']['asset_b64'])
    check(len(contract.observe_glb(rejected)['parts'])==8,'rejected asset physically has eight parts, not a fake error flag')
    (out/'rejected-three-leg.glb').write_bytes(rejected)
    check(pipeline.assess(project,source,evidence)['tasks']['art-target']['status']=='awaiting_review','accepted technical subjob does not self-approve human art task')
    check(packets.inventory(source)==original,'operator source remains byte-identical')
    # Observe source drift before export. The original accepted bytes are retained but
    # cannot be grafted onto a different baseline by this API.
    changed=out/'drift-source';shutil.copytree(source,changed)
    (changed/'brief.md').write_text('Changed baseline')
    try:worker.export_asset(out/'corrected',changed,out/'drift-export')
    except ValueError:check(not (out/'drift-export').exists(),'changed source refuses export before writing')
    else:raise AssertionError('changed baseline exported')
    save_new(out/'candidate-scope.json',scoped)
    report={'schema':'ciw.foundry-asset-qualification.v1','operation_id':'workbench-native-qualification.v1',
        'execution_id':uuid.uuid4().hex,'checks':checks,'campaigns':campaigns,'inspection':inspections,
        'producer_binary_sha256':bsha,'inspector_binary_sha256':gsha,'asset_sha256':bytes_ref(raw),
        'asset_bytes':len(raw),'geometry':observed,'accepted_export':exported,
        'native_production_attempts':sum(x['attempt_count'] for x in campaigns.values()),
        'captured_native_invocations':sum(load(out/n/'production.json')['result_count']*2 for n in campaigns),
        'original_retained_files_checked':len(kept),'byte_identical_same_build_assets':
            base_result['data']['asset_sha256']==result['data']['asset_sha256']==reg_result['data']['asset_sha256'],
        'model_calls':0,'human_playtests':0,'real_human_reviews':0,'review_records':'explicit_test_fixtures',
        'history':'original fictional workbench; not measured historical reconstruction',
        'scope':'one technical asset-production worker, not autonomous art direction, game integration or a release'}
    save_new(out/'qualification.json',report)
    print(f"FOUNDRY_ASSET_CHECKS: {len(checks)} passed; 0 failed; {report['native_production_attempts']} production attempts / {report['captured_native_invocations']} native tool calls")
    return 0


if __name__=='__main__':
    raise SystemExit(main())
