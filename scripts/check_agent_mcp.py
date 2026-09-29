#!/usr/bin/env python3
"""Independent official MCP SDK client gate, using an installed NET package.

Requires test-only mcp==1.26.0. Makes no LLM request and needs no API key.
"""
from __future__ import annotations
import argparse
import asyncio
from hashlib import sha256
import json
from pathlib import Path
import platform
import sys
from importlib.metadata import version

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from ciw.agent_mcp import demo_config
from ciw.agent_api import encode, parse
from ciw.control_checks import validate_comparison
from ciw.check_suite import validate_report


async def campaign(root: Path):
    profile=demo_config(root/'demo')
    checks=[]
    transcript=[]
    server=StdioServerParameters(command=sys.executable, args=['-I','-m','ciw.agent_mcp','serve','--profile',str(profile)])
    async with stdio_client(server) as (reader,writer):
        async with ClientSession(reader,writer) as client:
            initialization=await client.initialize()
            checks.append('official-sdk-initialize')
            listed=await client.list_tools()
            assert len(listed.tools)==11
            checks.append('discover-11-schema-described-tools')
            async def call(name, arguments):
                response=await client.call_tool(name,arguments)
                value=response.structuredContent
                assert value is not None
                transcript.append({'tool':name,'arguments':arguments,'result':value,'isError':response.isError})
                assert json.loads(response.content[0].text)==value
                return response,value
            response,caps=await call('net_capabilities',{})
            assert not response.isError and caps['catalog']['operations']['statistics.v1']['agent_execution_enabled']
            assert not caps['catalog']['operations']['spectrum.periodogram.v1']['agent_execution_enabled']
            checks.append('execution-is-explicit-not-all-advertised')
            response,first=await call('net_execute',{'source':'source','graph':'baseline','attempt':'baseline'})
            assert not response.isError and first['status']=='completed'
            response,again=await call('net_execute',{'source':'source','graph':'baseline','attempt':'baseline'})
            assert again['reused_response'] and first['execution_ids']==again['execution_ids']
            checks.append('real-ciw-dispatch-and-retry-without-reexecution')
            response,replay=await call('net_replay',{'original_attempt':'baseline','new_attempt':'replayed'})
            assert not response.isError and replay['execution_ids']!=first['execution_ids']
            checks.append('explicit-replay-fresh-execution-identity')
            response,proposal=await call('net_candidate',{'baseline':'baseline','changes':{'statistics':{'channel':'v'}}})
            assert not response.isError and proposal['executed'] is False
            response,candidate=await call('net_execute',{'source':'source','graph':proposal['candidate']['artifact_id'],'attempt':'candidate'})
            assert not response.isError and candidate['status']=='completed'
            checks.append('bounded-candidate-then-explicit-run')
            response,details=await call('net_inspect',{'artifact':candidate['artifacts']['graph-run']['artifact_id'],
                'selector':['nodes','statistics','result','data']})
            assert not response.isError and details['data']['unit']=='m/s'
            checks.append('inspect-actual-candidate-result')
            response,observation=await call('net_observe',{'artifact':'reference','offset':0,'limit':4})
            assert not response.isError and observation['next_offset']==4
            checks.append('bounded-observation-page')
            response,difference=await call('net_compare',{'left':'reference','right':'reference','policy':'strict'})
            assert not response.isError and difference['outcome']['status']=='PASS'
            response,qualified=await call('net_qualify',{'suite':'regression','inputs':{'difference':difference['comparison']['artifact_id']}})
            assert not response.isError and qualified['summary']['status']=='PASS'
            assert qualified['authority']['verification_id'] is None
            checks.append('fixed-ordinary-check-plan-no-verification-promotion')
            response,missing=await call('net_qualify',{'suite':'regression','inputs':{}})
            assert not response.isError and missing['summary']['status']=='INDETERMINATE'
            checks.append('missing-evidence-indeterminate')
            response,refused=await call('net_candidate',{'baseline':'baseline','changes':{'statistics':{'atol':1000}}})
            assert response.isError and refused['status']=='refused'
            checks.append('policy-change-refused')
            response,refused=await call('net_execute',{'source':'source','graph':'baseline','attempt':'../escape'})
            assert response.isError
            checks.append('path-injection-refused')
            response,refused=await call('net_accept',{})
            assert response.isError
            checks.append('no-baseline-acceptance-tool')
    for file in (root/'demo'/'agent-output').glob('a-*.json'):
        raw=file.read_bytes();value=parse(raw)
        assert file.stem=='a-'+sha256(raw).hexdigest()
        if value['schema']=='ciw.comparison.v1':validate_comparison(value)
        if value['schema']=='ciw.check-report.v1':validate_report(value)
    checks.append('retained-file-digests-and-existing-offline-validators')
    (root/'transcript.json').write_bytes(encode({'calls':transcript}))
    return {'status':'passed','checks':checks,'check_count':len(checks),
        'protocol_version':initialization.protocolVersion,'client':'official mcp Python SDK',
        'client_version':version('mcp'),'python':platform.python_version(),'platform':platform.platform(),
        'scope':'builtin analytical data, real CIW operations and MCP transport; no LLM or native engine invocation',
        'comparison_scope':'same retained reference transport, not independent numerical validation',
        'execution_ids':first['execution_ids']+replay['execution_ids']+candidate['execution_ids']}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
    root=a.output_dir.absolute();root.mkdir(parents=False,exist_ok=False)
    try:report=asyncio.run(campaign(root))
    except Exception as exc:
        (root/'report.json').write_text(json.dumps({'status':'failed','type':type(exc).__name__,'reason':str(exc)}))
        raise
    report['artifact_sha256']={x.relative_to(root).as_posix():sha256(x.read_bytes()).hexdigest() for x in root.rglob('*') if x.is_file()}
    (root/'report.json').write_bytes(encode(report));print(json.dumps(report,indent=2))

if __name__=='__main__':main()
