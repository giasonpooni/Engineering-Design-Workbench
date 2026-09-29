"""Exercise the installed existing MCP server with optional stateful grants.

Default: independent official SDK client. --wire uses a small stdlib test client
for offline local diagnosis, explicitly distinguished in its evidence report.
No LLM, paid model API or hardware is invoked. --godot selects real point dynamics.
"""
from __future__ import annotations
import argparse
import asyncio
from contextlib import asynccontextmanager
from importlib.metadata import version
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading

from ciw.agent_api import encode, parse
from ciw.simulation_agent import demo_profiles
from ciw.simulation_records import observer
from ciw.simulation_control import open_workspace
from ciw.simulation_timeline import build


@asynccontextmanager
async def wire_client(args, errors):
    with errors.open('wb') as log:
        process=subprocess.Popen([sys.executable,'-I','-m','ciw.agent_mcp',*args],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log)
        responses=queue.Queue()
        def pump():
            try:
                for line in process.stdout:
                    responses.put(json.loads(line))
            except Exception as exc: responses.put(exc)
        reader=threading.Thread(target=pump,daemon=True);reader.start()
        class Client:
            sequence=0
            async def send(self,method,params=None,notification=False):
                self.sequence+=1
                packet={'jsonrpc':'2.0','method':method,'params':params or {}}
                if not notification:packet['id']=self.sequence
                process.stdin.write(encode(packet)+b'\n');process.stdin.flush()
                if notification:return None
                reply=responses.get(timeout=30)
                assert not isinstance(reply,Exception),reply
                assert reply.get('id')==self.sequence and 'error' not in reply,reply
                return reply['result']
            async def initialize(self):
                result=await self.send('initialize',{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'NET wire diagnosis','version':'1'}})
                await self.send('notifications/initialized',notification=True)
                return result['protocolVersion']
            async def list(self):return (await self.send('tools/list'))['tools']
            async def call(self,name,arguments):
                result=await self.send('tools/call',{'name':name,'arguments':arguments})
                assert json.loads(result['content'][0]['text'])==result['structuredContent']
                return result['structuredContent'],result['isError']
        try:yield Client()
        finally:
            process.stdin.close()
            try:assert process.wait(timeout=15)==0
            finally:
                if process.poll() is None:process.kill();process.wait()
                process.stdout.close();reader.join(timeout=2)


@asynccontextmanager
async def sdk_client(args, errors):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    server=StdioServerParameters(command=sys.executable,args=['-I','-m','ciw.agent_mcp',*args])
    with errors.open('w',encoding='utf-8') as log:
        async with stdio_client(server,errlog=log) as (reader,writer):
            async with ClientSession(reader,writer) as session:
                class Client:
                    async def initialize(self):return (await session.initialize()).protocolVersion
                    async def list(self):return [t.model_dump() for t in (await session.list_tools()).tools]
                    async def call(self,name,arguments):
                        result=await session.call_tool(name,arguments)
                        assert json.loads(result.content[0].text)==result.structuredContent
                        return result.structuredContent,result.isError
                yield Client()


async def run(root: Path, *, wire=False, godot: Path | None=None, pin: str | None=None):
    base,sim=demo_profiles(root/'profiles')
    field='position';expected_error=2.0
    if godot is not None:
        profile=parse(sim.read_bytes()); model=profile['models']['motion']
        model['provider']='godot-point';model['configuration']={'executable':str(godot.resolve()),'sha256':pin}
        model['policy']['steps']={'tick':{'dt':1/64}}
        field='position_x';expected_error=2/64
        model['policy']['observers']={
            'position':observer('position',kind='debugger',channels=[field]),
            'delayed':observer('delayed',kind='embodied_agent',channels=[field])}
        model['policy']['interventions']={'push':{'actor_id':'operator-granted-agent','operation':'projectile.queue-impulse.v1','target':'projectile','parameters':{'at_tick':3,'delta_v_m_s':[2,0,0]}}}
        sim.write_bytes(encode(profile))
    checks=[]; transcript=[]
    def check(condition,name):
        assert condition,name
        checks.append(name)
    manager=wire_client if wire else sdk_client
    async with manager(['serve','--profile',str(base),'--simulation-profile',str(sim)],root/'server-stderr.log') as client:
        protocol=await client.initialize();check(protocol=='2025-11-25','protocol_negotiated')
        listed=await client.list();check(len(listed)==15,'original_eleven_plus_four_stateful_tools')
        async def call(name,**args):
            value,error=await client.call(name,args)
            transcript.append({'tool':name,'arguments':args,'result':value,'isError':error})
            (root/'transcript.json').write_bytes(encode({'calls':transcript}))
            return value,error
        created,error=await call('net_sim_create',model='motion',attempt='create')
        check(not error and created['execution_id'] is None and created['attachment_only'],'attachment_not_fabricated_execution')
        parent=created['instance']
        again,_=await call('net_sim_create',model='motion',attempt='create')
        check(again==created,'creation_retry_no_second_owner')
        async def command(instance,action,attempt,preset=None,fence=None):
            if fence is None:
                meta,error=await call('net_sim_inspect',instance=instance)
                assert not error
                fence=meta['expected']
            return await call('net_sim_command',instance=instance,action=action,attempt=attempt,expected=fence,preset=preset)
        early,error=await command(parent,'observe','early','delayed')
        check(not error,'initial_delayed_observation_executed')
        empty=early['observations'][field]['artifact_id']
        missing,error=await call('net_compare',left=empty,right=empty,policy='strict')
        check(not error and missing['outcome']['status']=='INDETERMINATE','missing_samples_not_zero_or_pass')
        fence=early['view']['expected']
        start,error=await command(parent,'start','start',fence=fence);assert not error
        duplicate,_=await command(parent,'start','start',fence=fence)
        check(duplicate==start,'command_retry_preserves_original_occurrence')
        stale,error=await command(parent,'step','stale','tick',fence=fence)
        check(error and stale['refusal']['code']=='stale_simulation_command' and stale['result_id'] is None,'stale_fence_refuses_without_success')
        for action,attempt,preset in [('step','one','tick'),('pause','pause',None),('checkpoint','checkpoint',None)]:
            outcome,error=await command(parent,action,attempt,preset);assert not error,outcome
        cp=outcome['checkpoint']
        check('snapshot_b64' not in json.dumps(outcome),'checkpoint_is_opaque_handle')
        before,_=await call('net_sim_inspect',instance=parent)
        branched,error=await call('net_sim_branch',checkpoint=cp,attempt='branch');assert not error,branched
        child=branched['instance']
        again,_=await call('net_sim_branch',checkpoint=cp,attempt='branch')
        after,_=await call('net_sim_inspect',instance=parent)
        check(again==branched and before==after and child!=parent,'branch_retry_and_parent_isolation')
        value,error=await command(child,'intervene','push','push');assert not error,value
        streams={}
        for instance,prefix in ((parent,'baseline'),(child,'candidate')):
            for action,suffix,preset in [('resume','resume',None),('step','two','tick'),('step','three','tick'),('observe','observe','position')]:
                value,error=await command(instance,action,prefix+suffix,preset);assert not error,value
            streams[prefix]=value['observations'][field]['artifact_id']
        result,error=await call('net_compare',left=streams['candidate'],right=streams['baseline'],policy='strict')
        check(not error and result['outcome']['status']=='FAIL' and result['outcome']['metrics']['max_abs_error']==expected_error,'real_observations_use_existing_comparator')
        evidence,error=await call('net_observe',artifact=streams['candidate'],limit=2)
        check(not error and len(evidence['data'])==2 and evidence['next_offset']==2,'existing_observation_pagination')
        refused,error=await command(parent,'intervene','ungranted','evil')
        check(error and refused['status']=='refused','ungranted_preset_refused')
        accepted,error=await call('net_accept')
        check(error,'no_acceptance_or_shell_tool')
        analysis,error=await call('net_execute',source='source',graph='baseline',attempt='analysis')
        check(not error and analysis['status']=='completed','original_agent_analysis_still_executes')
        for instance,prefix in ((parent,'parent'),(child,'child')):
            value,error=await command(instance,'stop',prefix+'stop');assert not error,value
    workspace=root/'profiles/agent-output/stateful/workspace.json'
    from unittest.mock import patch
    with patch('subprocess.Popen',side_effect=AssertionError('provider-free audit')):
        session=open_workspace(workspace,output_dir=root/'readback')
        summary=build(root/'timeline',workspaces=[workspace])
    check(len(session.executions)==18 and len(session.results)==17,'eighteen_original_occurrences_one_stale_refusal')
    check(summary['instance_count']==2 and summary['unique_executions']==18,'existing_timeline_accepts_agent_driven_history')
    shutdown=parse((workspace.parent/'shutdown.json').read_bytes())
    check(shutdown['status']=='closed','host_shutdown_retention')
    (root/'transcript.json').write_bytes(encode({'calls':transcript}))
    return {'status':'passed','check_count':len(checks),'checks':checks,'protocol_version':protocol,
        'client':'stdlib wire diagnostic' if wire else 'official MCP Python SDK',
        'client_version':None if wire else version('mcp'),'provider':'godot-point' if godot else 'reference',
        'comparison_max_abs_error':expected_error,'summary':summary,'no_llm_invoked':True}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',required=True,type=Path)
    parser.add_argument('--wire',action='store_true')
    parser.add_argument('--godot',type=Path);parser.add_argument('--godot-sha256')
    args=parser.parse_args();root=args.output_dir.absolute();root.mkdir(exist_ok=False)
    try:report=asyncio.run(run(root,wire=args.wire,godot=args.godot,pin=args.godot_sha256))
    except Exception as exc:
        (root/'report.json').write_text(json.dumps({'status':'failed','reason':str(exc)}),encoding='utf-8')
        raise
    (root/'report.json').write_bytes(encode(report));print(json.dumps(report,indent=2))


if __name__=='__main__':main()
