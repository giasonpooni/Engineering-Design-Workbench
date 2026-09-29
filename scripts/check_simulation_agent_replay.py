"""Independent client -> installed original MCP server -> opt-in stateful replay.

Reuse the existing qualification client's stdio framing. Default is the official
MCP SDK; --wire is an explicitly labelled stdlib diagnosis. No language model API.
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
from ciw.simulation_control import open_workspace
from ciw.simulation_records import observer
from ciw.simulation_replay import validate_replay
from ciw.simulation_timeline import build, inspect_bundle


async def run(root: Path, *, wire=False, godot: Path | None = None, pin: str | None = None):
    clients = runpy.run_path(str(Path(__file__).with_name('check_simulation_agent.py')))
    manager = clients['wire_client' if wire else 'sdk_client']
    base, simulation = demo_profiles(root / 'profiles', replay=True)
    profile = parse(simulation.read_bytes())
    profile['replay'] = {'max_commands': 8, 'max_executions': 12}
    quantity = 'position'
    if godot is not None:
        model = profile['models']['motion']
        model['provider'] = 'godot-point'
        model['configuration'] = {'executable': str(godot.resolve()), 'sha256': pin}
        model['policy']['steps'] = {'tick': {'dt': 1/64}}
        quantity = 'position_x'
        model['policy']['observers'] = {
            'position': observer('position', kind='debugger', channels=[quantity]),
            'delayed': observer('delayed', kind='embodied_agent', channels=[quantity])}
        model['policy']['interventions'] = {'push': {'actor_id':'operator-granted-agent',
            'operation':'projectile.queue-impulse.v1', 'target':'projectile',
            'parameters':{'at_tick':3,'delta_v_m_s':[2,0,0]}}}
    simulation.write_bytes(encode(profile))
    checks, transcript = [], []
    def check(condition, name):
        if not condition: raise AssertionError(name)
        checks.append(name)
    async with manager(['serve','--profile',str(base),'--simulation-profile',str(simulation)], root / 'server-stderr.log') as client:
        protocol = await client.initialize()
        check(protocol == '2025-11-25', 'negotiated_existing_protocol')
        tools = await client.list()
        check(len(tools) == 16 and {'net_replay','net_sim_replay','net_compare','net_sim_branch'} <= {t['name'] for t in tools},
              'sixteen_tools_original_analysis_replay_preserved')
        async def call(name, **args):
            result, error = await client.call(name, args)
            transcript.append({'tool':name, 'arguments':args, 'result':result, 'isError':error})
            (root / 'transcript.json').write_bytes(encode({'calls':transcript}))
            return result, error
        async def command(instance, action, attempt, preset=None):
            view, error = await call('net_sim_inspect', instance=instance)
            assert not error, view
            result, error = await call('net_sim_command', instance=instance, expected=view['expected'],
                action=action, attempt=attempt, preset=preset)
            assert not error, result
            return result
        cap, _ = await call('net_capabilities')
        check(cap['stateful']['replay']['reserved_executions'] == 0, 'grant_visible_without_execution')
        created, error = await call('net_sim_create', model='motion', attempt='create')
        check(not error and created['attachment_only'] and created['execution_id'] is None, 'attachment_not_replay_execution')
        source = created['instance']
        for action, attempt, preset in [('start','start',None), ('step','one','tick'),
            ('intervene','queued','push'), ('pause','pause',None), ('checkpoint','cp',None)]:
            result = await command(source, action, attempt, preset)
        cp = result['checkpoint']
        check('snapshot_b64' not in json.dumps(result), 'opaque_checkpoint_handle')
        for action, attempt, preset in [('resume','resume',None),('step','two','tick'),('step','three','tick')]:
            await command(source, action, attempt, preset)
        original = await command(source, 'observe', 'observed', 'position')
        await command(source, 'pause', 'boundary')
        before, _ = await call('net_sim_inspect', instance=source)
        args = {'checkpoint':cp, 'instance':source, 'expected':before['expected'], 'attempt':'replay-one'}
        stale = {**args, 'attempt':'stale', 'expected':{**before['expected'], 'revision':before['expected']['revision']+1}}
        refused, error = await call('net_sim_replay', **stale)
        check(error and refused['status'] == 'refused' and refused['dispatch_performed'] is False, 'stale_replay_fence_refuses_before_factory')
        first, error = await call('net_sim_replay', **args)
        check(not error and first['outcome']['status']=='PASS' and first['outcome']['checked_commands']==5, 'actual_five_command_replay_passes')
        after, _ = await call('net_sim_inspect', instance=source)
        check(before == after and first['instance'] != source and first['view']['expected']['owner_id'] != before['expected']['owner_id'],
              'fresh_owner_parent_unchanged')
        check(len(first['execution_ids']) == 6 and not set(first['execution_ids']) & set(first['source_execution_ids']), 'restore_and_suffix_have_fresh_occurrences')
        compared, error = await call('net_compare', left=first['observations'][quantity]['artifact_id'],
                                     right=original['observations'][quantity]['artifact_id'], policy='strict')
        check(not error and compared['outcome']['status']=='PASS', 'replayed_observations_use_original_comparator')
        viewed, error = await call('net_observe', artifact=first['observations'][quantity]['artifact_id'])
        check(not error and viewed['data'] and all(s['identity']['execution_id']==first['observation_execution_id'] for s in viewed['data']),
              'observation_execution_identity_is_replay_not_analysis')
        again, error = await call('net_sim_replay', **args)
        check(not error and again == first, 'same_attempt_no_new_execution')
        second, error = await call('net_sim_replay', **{**args, 'attempt':'replay-two'})
        check(not error and second['outcome']['status']=='PASS' and second['instance']!=first['instance']
              and not set(first['execution_ids']) & set(second['execution_ids']), 'new_attempt_intentionally_reexecutes')
        budget, error = await call('net_sim_replay', **{**args,'attempt':'over-budget'})
        cap, _ = await call('net_capabilities')
        check(error and budget['dispatch_performed'] is False and cap['stateful']['replay']['reserved_executions']==12
              and len(cap['stateful']['instances'])==3, 'reservation_budget_includes_restore_and_does_not_launch_excess_owner')
        await command(source, 'stop', 'source-stop')
        cached, error = await call('net_sim_replay', **args)
        check(not error and cached == first, 'retry_receipt_survives_source_boundary_change')
        check('snapshot_b64' not in json.dumps(transcript), 'no_raw_checkpoint_bytes_cross_agent_boundary')
    workspace = root / 'profiles/agent-output/stateful/workspace.json'
    reports = [workspace.parent / ('attempt-'+name) / 'replay.json' for name in ('replay-one','replay-two')]
    with patch('subprocess.Popen', side_effect=AssertionError('inspection must not execute')):
        session = open_workspace(workspace, output_dir=root/'readback')
        for report in reports: validate_replay(parse(report.read_bytes()))
        timeline = build(root/'timeline', workspaces=[workspace], reports=reports)
        checked = inspect_bundle(root/'timeline')
    check(len(session.executions)==25 and len(session.results)==25, 'twenty_five_original_executions_after_cleanup')
    check(timeline['instance_count']==3 and checked['summary']==timeline, 'unchanged_timeline_reads_both_replays_without_provider')
    check(parse((workspace.parent/'shutdown.json').read_bytes())['status']=='closed', 'all_owners_cleanup_retained')
    report = {'status':'passed', 'check_count':len(checks), 'checks':checks, 'protocol_version':protocol,
              'client':'stdlib wire diagnostic' if wire else 'official MCP Python SDK',
              'client_version':None if wire else version('mcp'), 'provider':'godot-point' if godot else 'reference',
              'source_commands':5, 'executions_per_replay':6, 'replay_reservation':12,
              'stateful_execution_count':len(session.executions), 'timeline':timeline, 'no_llm_invoked':True}
    (root/'report.json').write_bytes(encode(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--wire', action='store_true')
    parser.add_argument('--godot', type=Path)
    parser.add_argument('--godot-sha256')
    args = parser.parse_args()
    root = args.output_dir.absolute(); root.mkdir(exist_ok=False)
    try:
        report = asyncio.run(run(root, wire=args.wire, godot=args.godot, pin=args.godot_sha256))
    except Exception as exc:
        (root/'report.json').write_text(json.dumps({'status':'failed','reason':str(exc)}), encoding='utf-8')
        raise
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
