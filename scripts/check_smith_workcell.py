"""Official MCP client -> original workcell -> actual 1792 code -> native images/PCK.

The client is deterministic, not an LLM. No automatic merge or art approval.
"""
from __future__ import annotations
import argparse
import asyncio
import base64
from datetime import timedelta
import json
from pathlib import Path
import sys
from unittest.mock import patch

from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from ciw.control_contracts import bytes_ref,save_new,load
from ciw.foundry_packets import inventory
from ciw.workcell import inspect_attempt
from ciw.workcell_title import configure


async def campaign(args,root):
    before=inventory(args.title_root)
    profile=configure(title_root=args.title_root,profile=args.source_profile,profile_sha256=args.profile_sha256,
                      docker=args.docker,image_id=args.image_id,output_dir=root/'host',allow_package=True)
    config=StdioServerParameters(command=sys.executable,args=['-I','-m','ciw.workcell_cli','serve','--profile',str(profile)])
    transcript=[];reports={};checks=[]
    async with stdio_client(config) as (reader,writer):
        async with ClientSession(reader,writer,read_timeout_seconds=timedelta(seconds=180)) as client:
            initialized=await client.initialize();assert initialized.protocolVersion=='2025-11-25'
            names={t.name for t in (await client.list_tools()).tools}
            assert names=={'net_cell_describe','net_cell_submit','net_cell_build','net_cell_inspect','net_cell_preview'}
            checks.append('five-tools-over-original-MCP-transport')
            async def call(name,arguments):
                response=await client.call_tool(name,arguments)
                value=response.structuredContent
                assert value is not None and json.loads(response.content[0].text)==value
                transcript.append({'tool':name,'arguments':arguments,'result':value,'isError':response.isError})
                save_new(root/f'call-{len(transcript):03d}.json',transcript[-1])
                return response,value
            _,access=await call('net_cell_describe',{})
            assert access['packet']['writable']==['workshops/workshop_world.gd','workshops/workshop_rules.gd']
            checks.append('fixed-title-source-write-grants')
            async def run(name,changes):
                response,c=await call('net_cell_submit',{'attempt':name,'changes':changes});assert not response.isError
                response,report=await call('net_cell_build',{'attempt':name,'candidate':c['candidate']})
                save_new(root/(name+'.json'),report);reports[name]=report
                return c,report
            async def preview(name,view):
                response,value=await call('net_cell_preview',{'attempt':name,'view':view})
                assert not response.isError and response.content[1].type=='image' and response.content[1].mimeType=='image/png'
                raw=base64.b64decode(response.content[1].data,validate=True)
                assert bytes_ref(raw)==value['image']['sha256'] and len(raw)==value['image']['bytes']
                (root/f'{name}-{view}.png').write_bytes(raw)
                return value,raw
            baseline,r=await run('baseline',{})
            assert r['status']=='completed' and r['package_created'];checks.append('actual-title-baked-scene-test-and-package')
            day,day_raw=await preview('baseline','daylight');evening,evening_raw=await preview('baseline','evening')
            assert day_raw!=evening_raw and day['execution_id']==evening['execution_id'];checks.append('MCP-image-content-same-occurrence-two-lighting-views')
            _,retry=await call('net_cell_build',{'attempt':'baseline','candidate':baseline['candidate']})
            assert retry['reused_response'] and retry['production_id']==r['production_id'];checks.append('transport-retry-no-extra-container')
            rule=(args.title_root/'workshops/workshop_rules.gd').read_text()
            assert 'const OUTPUT := 2' in rule
            _,bad=await run('wrong-output',{'workshops/workshop_rules.gd':rule.replace('const OUTPUT := 2','const OUTPUT := 3')})
            assert bad['jobs']['test']['status']=='rejected' and bad['jobs']['package']['status']=='blocked';checks.append('real-title-rule-defect-blocks-package')
            observed,_=await preview('wrong-output','daylight')
            assert observed['job_status']=='rejected' and observed['release_authorized'] is False;checks.append('rejected-native-image-observable-not-promoted')
            art=(args.title_root/'workshops/workshop_world.gd').read_text();assert '"715640"' in art
            _,fixed=await run('corrected-with-art-variant',{'workshops/workshop_rules.gd':rule,'workshops/workshop_world.gd':art.replace('"715640"','"885d3f"')})
            assert fixed['status']=='completed';_,changed=await preview('corrected-with-art-variant','daylight')
            assert changed!=day_raw;checks.append('candidate-art-variant-produces-different-native-pixels-under-fixed-gates')
            _,oversize=await run('oversized-workplace',{'workshops/workshop_world.gd':art.replace('Vector3(6,0.02,4.8)','Vector3(60,0.02,4.8)')})
            assert oversize['jobs']['build']['status']=='rejected' and oversize['jobs']['test']['status']=='blocked';checks.append('oversized-asset-rejected-before-rendering')
            response,denied=await call('net_cell_submit',{'attempt':'protected','changes':{'workcells/smith_probe.gd':'pass'}})
            assert response.isError and denied['status']=='refused';checks.append('no-agent-test-authority')
            response,denied=await call('net_cell_preview',{'attempt':'baseline','view':'../../etc/passwd'})
            assert response.isError;checks.append('image-tool-cannot-browse-arbitrary-files')
    assert inventory(args.title_root)==before;checks.append('live-title-checkout-unchanged')
    files_checked=0;execution_ids=set();container_ids=set();stage_data={}
    for name,report in reports.items():
        directory=root/'host/cell/runs'/name;frozen={p:p.read_bytes() for p in directory.rglob('*') if p.is_file()}
        with patch('subprocess.Popen',side_effect=AssertionError('native dispatch during inspection')):
            assert inspect_attempt(directory)['status']==report['status']
        assert all(p.read_bytes()==raw for p,raw in frozen.items());files_checked+=len(frozen)
        workspace=load(directory/'session/workspace.json')
        for result in workspace['results']:
            execution_ids.add(result['execution_id']);container_ids.add(result['data']['isolation']['container_id'])
        stage_data[name]=[{'stage':r['data']['stage'],'wall_s':r['data']['elapsed_wall_s'],
                          'observations':r['data']['process']['observations']} for r in workspace['results']]
    checks.append('retained-scenes-images-rules-rechecked-without-native-execution')
    # A separate operator slot permits testing but deliberately withholds packaging.
    limited=configure(title_root=args.title_root,profile=args.source_profile,profile_sha256=args.profile_sha256,
                      docker=args.docker,image_id=args.image_id,output_dir=root/'test-only',allow_package=False)
    from ciw.workcell_cli import from_profile
    host=from_profile(limited);candidate=host.submit('one',{});report=host.build('one',candidate['candidate'])
    assert report['status']=='completed' and not report['package_created'] and set(report['jobs'])=={'build','test'}
    checks.append('passing-all-tests-does-not-invent-package-authority')
    save_new(root/'test-only.json',report)
    summary={'schema':'ciw.smith-workcell-qualification.v1','status':'passed','checks':checks,'check_count':len(checks),
             'native_container_attempts':sum(r['execution_count'] for r in reports.values())+report['execution_count'],
             'MCP_campaigns':{n:{'status':r['status'],'executions':r['execution_count'],'package_created':r['package_created']} for n,r in reports.items()},
             'native_MCP_execution_ids':sorted(execution_ids),'native_MCP_container_ids':sorted(container_ids),
             'source_profile_sha256':args.profile_sha256,'image_id':args.image_id,'retained_files_rechecked':files_checked,
             'scope':'actual containerized title-owned art/reducer and software-rendered images; deterministic SDK client not LLM; not full Home journey/art approval/GPU-FPS qualification',
             'model_tokens':None,'model_cost':None,'human_hours':None,'release_authorized':False}
    save_new(root/'stage-data.json',{'campaigns':stage_data});save_new(root/'qualification.json',summary)
    print(json.dumps(summary,indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--title-root',type=Path,required=True);p.add_argument('--source-profile',type=Path,required=True)
    p.add_argument('--profile-sha256',required=True);p.add_argument('--docker',type=Path,required=True)
    p.add_argument('--image-id',required=True);p.add_argument('--output-dir',type=Path,required=True)
    args=p.parse_args();root=args.output_dir.absolute();root.mkdir(parents=True,exist_ok=False)
    asyncio.run(campaign(args,root))


if __name__=='__main__':main()
