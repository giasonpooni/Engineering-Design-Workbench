"""Relay one real externally authored LLM revision through the existing MCP cell.

No canned defect/correction, generated candidate or model API lives in this
runner. Decisions are supplied by a separately declared interactive model session.
Candidate failures are data, not a reason to discard an experimental result.
"""
from __future__ import annotations
import argparse
import asyncio
import base64
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from ciw.agent_experiment import read_revision, audit_attempt, summarize
from ciw.control_contracts import bytes_ref, save_new, load
from ciw.core.identities import content_identity
from ciw.foundry_packets import inventory, read_file
from ciw.workcell_title import configure
from ciw.workcell_smith import SMITH


def now(): return datetime.now(timezone.utc).isoformat()


async def run(args, root):
    decision, changes = read_revision(args.response, args.response_sha256,
        agent_id=args.agent_id, writable=SMITH.writable_paths)
    if all(read_file(args.title_root, n).decode('utf-8') == value for n, value in changes.items()):
        raise ValueError('An unchanged baseline is not an agent revision')
    before = inventory(args.title_root)
    started = time.perf_counter()
    save_new(root/'decision.json', decision)
    save_new(root/'experiment.json', {'schema':'ciw.single-agent-experiment.v1',
        'started_utc':now(), 'agent_id':args.agent_id, 'response_sha256':args.response_sha256,
        'title_source_profile_sha256':args.profile_sha256, 'image_id':args.image_id,
        'revision_budget':1, 'baseline_control':True,
        'decision_transport':'retained interactive assistant response -> deterministic MCP relay',
        'prior_evidence_authenticity':'agent-declared references; not proof that a provider viewed an image',
        'native_recipe_policy_sha256':content_identity(SMITH.policy),
        'criteria_owner':'unchanged pre-existing workcell implementation',
        'model_tokens':None,'model_cost_usd':None,'human_active_seconds':None,'release_authorized':False})
    profile = configure(title_root=args.title_root, profile=args.source_profile,
        profile_sha256=args.profile_sha256, docker=args.docker, image_id=args.image_id,
        output_dir=root/'host', allow_package=True)
    # A single owner-controlled slot, bounded to the baseline plus one revision.
    p = load(profile); p['max_candidates']=2; p['max_runs']=2
    config = profile.with_name('bounded-profile.json')
    # Keep the capsule manifest adjacent to the operator profile as its loader requires.
    save_new(config,p)
    server = StdioServerParameters(command=sys.executable,
        args=['-I','-m','ciw.workcell_cli','serve','--profile',str(config)])
    counts = {'calls':0}; measurements={}; reports={}
    async with stdio_client(server) as (reader,writer):
        async with ClientSession(reader,writer,read_timeout_seconds=timedelta(seconds=180)) as client:
            initialized = await client.initialize()
            save_new(root/'mcp-initialize.json',initialized.model_dump(mode='json'))
            if initialized.protocolVersion != '2025-11-25':raise ValueError('Unqualified MCP protocol')
            async def call(name,arguments):
                counts['calls']+=1; prefix=f"call-{counts['calls']:03d}"
                save_new(root/(prefix+'-request.json'),{'tool':name,'arguments':arguments,'started_utc':now()})
                t=time.perf_counter()
                response=await client.call_tool(name,arguments)
                save_new(root/(prefix+'-response.json'),{'response':response.model_dump(mode='json'),
                    'elapsed_rpc_wall_s':time.perf_counter()-t,'completed_utc':now()})
                value=response.structuredContent
                if value is None or not response.content or json.loads(response.content[0].text)!=value:
                    raise ValueError('MCP structured/text response disagreement')
                return response,value
            _, access = await call('net_cell_describe',{})
            if set(changes)-set(access['packet']['writable']):raise ValueError('Response exceeds independent slot grant')
            save_new(root/'access.json',access)
            for label,replacements in [('baseline',{}),('revision',changes)]:
                response,candidate = await call('net_cell_submit',{'attempt':label,'changes':replacements})
                if response.isError:raise ValueError('Source submission refused: '+json.dumps(candidate))
                response,report = await call('net_cell_build',{'attempt':label,'candidate':candidate['candidate']})
                # Deliberately no assertion that the LLM proposal passes.
                if 'production_id' not in report:raise ValueError('No retained production outcome: '+json.dumps(report))
                save_new(root/(label+'-feedback.json'),report);reports[label]=report
                measurements[label]=audit_attempt(root/'host/cell/runs'/label)
                save_new(root/(label+'-measurement.json'),measurements[label])
                for view in ('daylight','evening'):
                    response,value = await call('net_cell_preview',{'attempt':label,'view':view})
                    if response.isError:continue  # Keep original refused call; never manufacture pixels.
                    if len(response.content)!=2 or response.content[1].type!='image' or response.content[1].mimeType!='image/png':
                        raise ValueError('Expected actual native image content')
                    raw=base64.b64decode(response.content[1].data,validate=True)
                    if bytes_ref(raw)!=value['image']['sha256'] or len(raw)!=value['image']['bytes']:
                        raise ValueError('MCP image identity mismatch')
                    (root/f'{label}-{view}.png').write_bytes(raw)
                if label=='baseline' and not measurements[label]['package_accepted']:
                    break  # Broken control is not evidence about the agent.
    if inventory(args.title_root)!=before:raise ValueError('Live title source mutated')
    summary=summarize(measurements['baseline'],[measurements['revision']] if 'revision' in measurements else [])
    summary.update({'experiment_status':'measured' if 'revision' in measurements else 'baseline_unqualified',
        'agent_id':args.agent_id,'revision_id':decision['revision_id'],
        'decision_sha256':args.response_sha256,'response_authorship':decision['author_attestation'],
        'native_policy_sha256':content_identity(SMITH.policy),
        'experiment_wall_s':time.perf_counter()-started,
        'experiment_wall_scope':'profile creation and MCP baseline/revision/test/package/previews/audit only; excludes model generation, provisioning and queue/setup',
        'measured_rpc_calls':counts['calls'],'completed_utc':now()})
    save_new(root/'summary.json',summary)
    print(json.dumps(summary,indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--title-root',type=Path,required=True);p.add_argument('--source-profile',type=Path,required=True)
    p.add_argument('--profile-sha256',required=True);p.add_argument('--docker',type=Path,required=True)
    p.add_argument('--image-id',required=True);p.add_argument('--response',type=Path,required=True)
    p.add_argument('--response-sha256',required=True);p.add_argument('--agent-id',required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    args=p.parse_args();root=args.output_dir.absolute()
    if any(q.is_symlink() for q in (root,*root.parents)):raise ValueError('Linked experiment destination')
    # Full response preflight before output creation/provider startup.
    read_revision(args.response,args.response_sha256,agent_id=args.agent_id,writable=SMITH.writable_paths)
    root.mkdir(parents=True,exist_ok=False)
    try:asyncio.run(run(args,root))
    except BaseException as exc:
        save_new(root/'interrupted.json',{'schema':'ciw.agent-experiment-interruption.v1',
            'error_type':type(exc).__name__,'reason':str(exc)[-2000:],'completed_utc':now(),
            'automatic_resume':False,'release_authorized':False})
        raise


if __name__=='__main__':main()
