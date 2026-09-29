"""Official MCP client -> existing server -> explicitly granted branch campaign.

--wire reuses the original, separately labelled stdlib diagnostic client. No LLM,
API account, renderer, live hardware or alternate campaign implementation.
"""
from __future__ import annotations
import argparse
import asyncio
from importlib.metadata import version
import json
from pathlib import Path
import runpy
from unittest.mock import patch

from ciw.agent_api import encode, parse
from ciw.simulation_agent import demo_profiles
from ciw.simulation_campaign import validate_campaign
from ciw.simulation_control import open_workspace
from ciw.simulation_records import observer
from ciw.simulation_timeline import build, inspect_bundle


async def run(root: Path, *, wire=False, godot: Path | None = None, pin: str | None = None):
    clients = runpy.run_path(str(Path(__file__).with_name('check_simulation_agent.py')))
    manager = clients['wire_client' if wire else 'sdk_client']
    base, profile_path = demo_profiles(root/'profiles', replay=True, campaign=True)
    profile = parse(profile_path.read_bytes())
    profile['campaigns']['max_executions'] = 44
    quantity, expected_error = 'position', 2.0
    if godot is not None:
        model = profile['models']['motion']
        model['provider'] = 'godot-point'
        model['configuration'] = {'executable': str(godot.resolve()), 'sha256': pin}
        model['policy']['steps'] = {'tick': {'dt': 1/64}}
        quantity, expected_error = 'position_x', 2/64
        model['policy']['observers'] = {
            'position': observer('position', kind='debugger', channels=[quantity]),
            'delayed': observer('delayed', kind='embodied_agent', channels=[quantity])}
        model['policy']['interventions'] = {'push': {'actor_id': 'operator-granted-agent',
            'operation': 'projectile.queue-impulse.v1', 'target': 'projectile',
            'parameters': {'at_tick': 3, 'delta_v_m_s': [2, 0, 0]}}}
        profile['campaigns']['templates']['impulses']['quantity'] = quantity
    profile_path.write_bytes(encode(profile))
    checks, transcript = [], []
    def check(condition, name):
        if not condition: raise AssertionError(name)
        checks.append(name)
    async with manager(['serve','--profile',str(base),'--simulation-profile',str(profile_path)],root/'server-stderr.log') as client:
        protocol = await client.initialize()
        check(protocol == '2025-11-25', 'original_mcp_protocol_negotiated')
        tools = await client.list()
        check(len(tools) == 17 and {'net_sim_campaign','net_sim_replay','net_replay'} <= {t['name'] for t in tools},
              'seventeen_tools_without_replacing_original_replays')
        async def call(name, **args):
            result, error = await client.call(name, args)
            transcript.append({'tool':name,'arguments':args,'result':result,'isError':error})
            (root/'transcript.json').write_bytes(encode({'calls':transcript}))
            return result,error
        async def command(instance, action, attempt, preset=None):
            view,error = await call('net_sim_inspect',instance=instance)
            assert not error,view
            result,error = await call('net_sim_command',instance=instance,expected=view['expected'],
                action=action,attempt=attempt,preset=preset)
            assert not error,result
            return result
        cap,error = await call('net_capabilities')
        check(not error and not cap['stateful']['instances'] and cap['stateful']['campaigns']['reserved_executions']==0,
              'capability_inspection_does_not_start_owners')
        created,error = await call('net_sim_create',model='motion',attempt='create')
        check(not error and created['execution_id'] is None,'attachment_is_not_numerical_execution')
        source = created['instance']
        for action,attempt,preset in [('start','start',None),('step','tick-one','tick'),
            ('intervene','queued','push'),('pause','pause',None),('checkpoint','cp',None)]:
            result = await command(source,action,attempt,preset)
        checkpoint = result['checkpoint']
        before,_ = await call('net_sim_inspect',instance=source)
        args = {'checkpoint':checkpoint,'instance':source,'expected':before['expected'],'campaign':'impulses','attempt':'campaign-one'}
        stale,error = await call('net_sim_campaign',**{**args,'attempt':'stale','expected':{**before['expected'],'revision':0}})
        check(error and stale['dispatch_performed'] is False,'stale_source_refuses_before_factory')
        first,error = await call('net_sim_campaign',**args)
        check(not error and first['status']=='completed' and first['summary']['comparison_counts']=={'PASS':1,'FAIL':1,'INDETERMINATE':0},
              'complete_campaign_preserves_pass_and_expected_fail')
        check(first['reserved_executions']==22 and first['summary']['execution_count']==22,'reservation_counts_restore_intervention_and_stop')
        after,_ = await call('net_sim_inspect',instance=source)
        check(after==before,'parent_boundary_unchanged')
        check(len({c['view']['expected']['owner_id'] for c in first['cases']})==3
              and all(c['view']['status']=='stopped' for c in first['cases']),'three_independent_stopped_variants')
        baseline,replica,changed = first['cases']
        compared,error = await call('net_compare',left=changed['observations'][quantity]['artifact_id'],
            right=baseline['observations'][quantity]['artifact_id'],policy='strict')
        check(not error and compared['outcome']==first['comparisons'][1]['outcome']
              and compared['outcome']['metrics']['max_abs_error']==expected_error,'existing_comparator_confirms_intervention_difference')
        seen,error = await call('net_observe',artifact=replica['observations'][quantity]['artifact_id'])
        check(not error and seen['data'] and all(s['identity']['execution_id']==replica['observation_execution_id'] for s in seen['data']),
              'observation_streams_retain_actual_variant_occurrences')
        repeated,error = await call('net_sim_campaign',**args)
        check(not error and repeated==first,'same_attempt_returns_original_receipt')
        second,error = await call('net_sim_campaign',**{**args,'attempt':'campaign-two'})
        ids = lambda r: {eid for c in r['cases'] for eid in c['execution_ids']}
        check(not error and len(ids(second))==22 and not ids(first)&ids(second),'new_attempt_reexecutes_fresh_variants')
        denied,error = await call('net_sim_campaign',**{**args,'attempt':'too-many'})
        cap,_ = await call('net_capabilities')
        check(error and not denied['dispatch_performed'] and cap['stateful']['campaigns']['reserved_executions']==44
              and len(cap['stateful']['instances'])==7,'entire_campaign_budget_checked_before_excess_launch')
        check(cap['stateful']['replay']['reserved_executions']==0,'existing_replay_reservation_unchanged')
        await command(source,'stop','stop-source')
        cached,error = await call('net_sim_campaign',**args)
        check(not error and cached==first,'retry_survives_source_stop')
        check('snapshot_b64' not in json.dumps(transcript),'no_checkpoint_bytes_in_agent_transcript')
        injection,error = await call('net_sim_campaign',**{**args,'attempt':'injection','steps':300})
        check(error and injection['status']=='refused','agent_cannot_replace_operator_template')
    workspace = root/'profiles/agent-output/stateful/workspace.json'
    reports = [workspace.parent/('attempt-'+name)/'campaign.json' for name in ('campaign-one','campaign-two')]
    with patch('subprocess.Popen',side_effect=AssertionError('no provider during evidence inspection')):
        session = open_workspace(workspace,output_dir=root/'readback')
        for path in reports:validate_campaign(parse(path.read_bytes()))
        timeline = build(root/'timeline',workspaces=[workspace],reports=reports)
        checked = inspect_bundle(root/'timeline')
    check(len(session.executions)==len(session.results)==50,'fifty_original_occurrences_after_shutdown')
    check(timeline['instance_count']==7 and checked['summary']==timeline,'unchanged_timeline_indexes_two_original_reports')
    check(parse((workspace.parent/'shutdown.json').read_bytes())['status']=='closed','cleanup_receipt_retained')
    report = {'status':'passed','check_count':len(checks),'checks':checks,'protocol_version':protocol,
        'client':'stdlib wire diagnostic' if wire else 'official MCP Python SDK','client_version':None if wire else version('mcp'),
        'provider':'godot-point' if godot else 'reference','executions_per_campaign':22,'campaign_reservation':44,
        'comparison_max_abs_error':expected_error,'stateful_execution_count':50,'timeline':timeline,'no_llm_invoked':True}
    (root/'report.json').write_bytes(encode(report))
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--wire',action='store_true')
    parser.add_argument('--godot',type=Path)
    parser.add_argument('--godot-sha256')
    args=parser.parse_args()
    root=args.output_dir.absolute();root.mkdir(exist_ok=False)
    try:report=asyncio.run(run(root,wire=args.wire,godot=args.godot,pin=args.godot_sha256))
    except Exception as exc:
        (root/'report.json').write_text(json.dumps({'status':'failed','reason':str(exc)}),encoding='utf-8')
        raise
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
