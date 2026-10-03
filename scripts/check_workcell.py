"""Actual official MCP client -> NET -> Docker -> Godot -> fixed gates -> PCK.

This is a deterministic tool client, NOT an LLM or an autonomous quality study.
"""
import argparse
import asyncio
from datetime import timedelta
import json
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import patch

from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from ciw.control_contracts import bytes_ref,save_new
from ciw.foundry_packets import inventory
from ciw.workcell import inspect_attempt

PROBE = '''import os, socket
from pathlib import Path
assert os.geteuid() == 65534
status = Path('/proc/self/status').read_text()
assert 'NoNewPrivs:\\t1' in status
assert 'CapEff:\\t0000000000000000' in status
assert not Path('/var/run/docker.sock').exists()
assert 'WORKCELL_SECRET_SENTINEL' not in os.environ
for path in ('/input/spec.json', '/recipe/runner.py', '/forbidden-write'):
    try:
        with open(path,'wb') as f: f.write(b'forbidden')
    except OSError: pass
    else: raise AssertionError('Unexpected write access '+path)
s = socket.socket(); s.settimeout(1)
try: s.connect(('1.1.1.1',443))
except OSError: pass
else: raise AssertionError('Unexpected external network access')
finally: s.close()
'''


async def campaign(args,root):
    source=Path(args.source_root).absolute(); before=inventory(source)
    docker=Path(args.docker).absolute()
    profile={'schema':'ciw.workcell-profile.v1','source_root':str(source),'source_id':before['inventory_id'],
             'output_dir':str(root/'cell'),'docker':str(docker),'docker_sha256':bytes_ref(docker.read_bytes()),
             'image_id':args.image_id,'socket':'unix:///var/run/docker.sock','writable':['compiler.py','motion.gd'],
             'max_candidates':8,'max_runs':8,'allow_package':True}
    save_new(root/'profile.json',profile)
    server=StdioServerParameters(command=sys.executable,args=['-I','-m','ciw.workcell_cli','serve','--profile',str(root/'profile.json')],
                                env={'WORKCELL_SECRET_SENTINEL':'must-not-reach-build'})
    transcript=[]; checks=[];reports={}
    async with stdio_client(server) as (reader,writer):
        async with ClientSession(reader,writer,read_timeout_seconds=timedelta(seconds=180)) as client:
            initialized=await client.initialize(); assert initialized.protocolVersion=='2025-11-25'
            assert len((await client.list_tools()).tools)==4;checks.append('existing-MCP-server-four-workcell-tools')
            async def call(name,args):
                value=await client.call_tool(name,args)
                result=value.structuredContent
                assert result is not None and json.loads(value.content[0].text)==result
                transcript.append({'tool':name,'arguments':args,'result':result,'isError':value.isError})
                return value,result
            response,access=await call('net_cell_describe',{})
            assert not response.isError and access['package_grant']; checks.append('operator-profile-fixed-before-agent')
            _,denied=await call('net_cell_submit',{'attempt':'forbidden','changes':{'spec.json':'{}'}})
            assert denied['status']=='refused';checks.append('no-agent-threshold-edit')
            async def run(name,changes):
                response,candidate=await call('net_cell_submit',{'attempt':name,'changes':changes})
                assert not response.isError
                response,report=await call('net_cell_build',{'attempt':name,'candidate':candidate['candidate']})
                reports[name]=report
                save_new(root/(name+'-feedback.json'),report)
                return candidate,report
            good,baseline=await run('baseline',{})
            assert baseline['status']=='completed' and baseline['package_created']; checks.append('compiled-scene-and-packaged-smoke')
            response,retry=await call('net_cell_build',{'attempt':'baseline','candidate':good['candidate']})
            assert retry['reused_response'] and retry['production_id']==baseline['production_id'];checks.append('no-duplicate-build-for-transport-retry')
            motion=(source/'motion.gd').read_text()
            _,bad=await run('wrong-mechanic',{'motion.gd':motion.replace('2.0 * delta','-2.0 * delta')})
            assert bad['jobs']['test']['status']=='rejected' and bad['jobs']['package']['status']=='blocked';checks.append('failed-mechanic-blocks-assembly')
            _,fixed=await run('corrected-mechanic',{'motion.gd':motion})
            assert fixed['status']=='completed' and fixed['production_id']!=baseline['production_id'];checks.append('same-client-repairs-and-crosses-fixed-threshold')
            compiler=(source/'compiler.py').read_text()
            _,badmesh=await run('wrong-compiler',{'compiler.py':compiler.replace('2.0 for v','1.0 for v')})
            assert badmesh['jobs']['build']['status']=='rejected' and badmesh['jobs']['test']['status']=='blocked';checks.append('generated-asset-must-meet-independent-dimension-contract')
            _,isolation=await run('isolation-probe',{'compiler.py':PROBE+'\n'+compiler})
            assert isolation['status']=='completed';checks.append('actual-readonly-nonroot-no-network-no-secret-no-socket-probes')
            _,timeout=await run('bounded-timeout',{'compiler.py':'while True: pass\n'})
            assert timeout['status']=='incomplete' and not timeout['package_created'];checks.append('candidate-timeout-retained-and-blocked')
            _,denied=await call('net_cell_change_image',{'image':'anything'})
            assert denied['status']=='refused';checks.append('no-self-provision-or-permission-escalation-tool')
    assert inventory(source)==before;checks.append('original-source-unchanged')
    for name,report in reports.items():
        directory=root/'cell/runs'/name
        frozen={p:p.read_bytes() for p in directory.rglob('*') if p.is_file()}
        with patch('subprocess.Popen',side_effect=AssertionError('offline provider dispatch')):
            rechecked=inspect_attempt(directory)
        assert rechecked['status']==report['status'] and all(p.read_bytes()==raw for p,raw in frozen.items())
    checks.append('all-six-campaigns-recheck-without-execution-or-mutation')
    remaining=subprocess.check_output([str(docker),'--host','unix:///var/run/docker.sock','ps','-aq','--filter','name=net-cell-'],text=True).strip()
    assert not remaining;checks.append('no-leftover-workcell-containers-after-timeout')
    summary={'schema':'ciw.workcell-qualification.v1','status':'passed','checks':checks,'check_count':len(checks),
             'native_container_attempts':sum(r['execution_count'] for r in reports.values()),
             'image_id':args.image_id,'protocol_version':initialized.protocolVersion,
             'campaigns':{name:{'status':r['status'],'executions':r['execution_count'],'package_created':r['package_created']} for name,r in reports.items()},
             'scope':'actual Docker and headless Godot through official MCP SDK; deterministic client, no LLM; original test slice not 1792 game/visual/physics qualification',
             'human_hours':None,'model_tokens':None,'release_authorized':False}
    save_new(root/'transcript.json',{'calls':transcript});save_new(root/'qualification.json',summary)
    print(json.dumps(summary,indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--docker',required=True);p.add_argument('--image-id',required=True)
    p.add_argument('--source-root',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    args=p.parse_args();root=args.output_dir.absolute();root.mkdir(parents=True,exist_ok=False)
    asyncio.run(campaign(args,root))

if __name__=='__main__':main()
