"""Original stateful replay through the opt-in agent grant; no native-test claim."""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ciw.agent_api import encode, parse
from ciw.agent_mcp import Server, from_profile as base_profile
from ciw.simulation_agent import Binding, demo_profiles, from_profile
from ciw.simulation_agent_replay import validate_grant
from ciw.simulation_agent_tools import descriptions
from ciw.simulation_reference import ReferenceMotion
from ciw.simulation_replay import validate_replay
from ciw.simulation_control import completed, open_workspace
from ciw.simulation_timeline import build


@pytest.fixture
def host(tmp_path):
    base, profile = demo_profiles(tmp_path / 'profiles', replay=True)
    value = from_profile(base_profile(base), profile)
    yield value
    value.close()


def command(host, instance, action, attempt, preset=None):
    response = host.call('net_sim_command', {'instance': instance, 'expected': host.inspect(instance)['expected'],
        'action': action, 'attempt': attempt, 'preset': preset})
    assert response['status'] == 'completed', response
    return response


def source_case(host, *, prefix='source', suffix=True):
    created = host.call('net_sim_create', {'model': 'motion', 'attempt': prefix + 'create'})
    instance = created['instance']
    command(host, instance, 'start', prefix + 'start')
    command(host, instance, 'step', prefix + 'one', 'tick')
    command(host, instance, 'intervene', prefix + 'push', 'push')  # queued event lives in checkpoint
    command(host, instance, 'pause', prefix + 'pause')
    cp = command(host, instance, 'checkpoint', prefix + 'cp')['checkpoint']
    observation = None
    if suffix:
        command(host, instance, 'resume', prefix + 'resume')
        command(host, instance, 'step', prefix + 'two', 'tick')
        command(host, instance, 'step', prefix + 'three', 'tick')
        observation = command(host, instance, 'observe', prefix + 'observe', 'position')
        command(host, instance, 'pause', prefix + 'end')
    return {'checkpoint': cp, 'instance': instance, 'expected': host.inspect(instance)['expected'],
            'attempt': 'reproduction'}, observation


def test_real_replay_reuses_engine_and_keeps_parent_and_occurrences(host):
    args, observation = source_case(host)
    before = deepcopy(host.session.results)
    parent_view = host.inspect(args['instance'])
    parent = host._providers[0]
    from ciw.simulation_agent_replay import replay as original_replay
    with patch.object(parent, 'snapshot', side_effect=AssertionError('must not call source provider')), \
         patch('ciw.simulation_agent_replay.replay', wraps=original_replay) as reused:
        result = host.call('net_sim_replay', args)
    assert reused.call_count == 1
    assert result['status'] == 'completed' and result['outcome']['status'] == 'PASS'
    assert result['outcome']['checked_commands'] == 5 and result['reserved_executions'] == 6
    assert len(result['execution_ids']) == len(result['result_ids']) == 6
    assert not set(result['source_execution_ids']) & set(result['execution_ids'])
    assert all(host.session.results[key] == value for key, value in before.items())
    assert host.inspect(args['instance']) == parent_view
    assert result['view']['expected']['owner_id'] != parent_view['expected']['owner_id']
    assert result['view']['clock']['time_s'] == 3 and result['view']['status'] == 'paused'
    artifact = result['observations']['position']['artifact_id']
    comparison = host.call('net_compare', {'left': artifact,
        'right': observation['observations']['position']['artifact_id'], 'policy': 'strict'})
    assert comparison['outcome']['status'] == 'PASS'
    samples = host.call('net_observe', {'artifact': artifact})['data']
    assert all(x['identity']['execution_id'] == result['observation_execution_id'] for x in samples)
    assert result['observation_source_execution_id'] == observation['execution_id']
    report = parse((host._root / 'attempt-reproduction/replay.json').read_bytes())
    validate_replay(report)
    assert report['record_digest'] == result['report_ref']
    assert report['verification_id'] is None and report['state_admission'] == 'not_performed'
    assert host._replay_reserved == 6


def test_replay_never_exposes_snapshot_or_full_report_to_agent(host):
    args, _ = source_case(host)
    result = host.call('net_sim_replay', args)
    assert 'snapshot_b64' not in json.dumps(result) and 'configuration_ref' not in json.dumps(result)
    for raw in host.host._artifacts.values():
        assert b'snapshot_b64' not in raw
    with pytest.raises(ValueError): host.call('net_inspect', {'artifact': result['report_ref']})


def test_retry_before_source_fence_check_and_after_shutdown(host):
    args, _ = source_case(host)
    first = host.call('net_sim_replay', args)
    command(host, args['instance'], 'stop', 'stop-source')
    before = len(host.session.executions)
    with patch.object(ReferenceMotion, '__init__', side_effect=AssertionError('no second factory')):
        assert host.call('net_sim_replay', deepcopy(args)) == first
    assert len(host.session.executions) == before and host._replay_reserved == 6
    host.close()
    assert host.call('net_sim_replay', args) == first


def test_new_attempt_explicitly_reexecutes_and_allocates_fresh_owner(host):
    args, _ = source_case(host)
    a = host.call('net_sim_replay', args)
    b = host.call('net_sim_replay', {**args, 'attempt': 'again'})
    assert a['instance'] != b['instance'] and not set(a['execution_ids']) & set(b['execution_ids'])
    assert b['outcome']['status'] == 'PASS' and host._replay_reserved == 12


def test_reused_attempt_with_changed_request_refuses_without_execution(host):
    args, _ = source_case(host)
    host.call('net_sim_replay', args)
    changed = deepcopy(args); changed['expected']['revision'] += 1
    before = len(host.session.executions)
    with pytest.raises(ValueError, match='different request'): host.call('net_sim_replay', changed)
    assert len(host.session.executions) == before


@pytest.mark.parametrize('reason', ['stale', 'running', 'empty', 'command-limit', 'reservation-limit', 'instance-limit'])
def test_preflight_refuses_without_provider_or_blocking_healthy_parent(host, reason):
    args, _ = source_case(host, suffix=reason != 'empty')
    if reason == 'stale': args['expected']['state_revision'] += 1
    elif reason == 'running':
        command(host, args['instance'], 'resume', 'running'); args['expected'] = host.inspect(args['instance'])['expected']
    elif reason == 'command-limit': host._replay_policy['max_commands'] = 4
    elif reason == 'reservation-limit': host._replay_policy['max_executions'] = 5
    elif reason == 'instance-limit': host._max_instances = 1
    before = len(host.session.executions)
    with patch.object(ReferenceMotion, '__init__', side_effect=AssertionError('no provider launch')):
        refused = host.call('net_sim_replay', args)
        assert host.call('net_sim_replay', args) == refused
    assert refused['status'] == 'refused' and refused['dispatch_performed'] is False
    assert not host._blocked and host._replay_reserved == 0 and len(host.session.executions) == before
    assert (host._root / 'attempt-reproduction/response.json').exists()
    assert not (host._root / 'attempt-reproduction/replay.json').exists()
    command(host, args['instance'], 'stop', 'healthy-stop')


def test_checkpoint_cannot_select_another_instance(host):
    args, _ = source_case(host)
    other, _ = source_case(host, prefix='other')
    args['checkpoint'] = other['checkpoint']
    refused = host.call('net_sim_replay', args)
    assert refused['status'] == 'refused' and 'does not belong' in refused['refusal']['message']
    assert not host._blocked and len(host._providers) == 2


def test_original_stale_refusals_are_not_replayed_as_accepted_commands(host):
    args, _ = source_case(host, suffix=False)
    old = host.inspect(args['instance'])['expected']
    command(host, args['instance'], 'resume', 'r')
    refused = host.call('net_sim_command', {'instance': args['instance'], 'expected': old,
        'action': 'step', 'attempt': 'stale-step', 'preset': 'tick'})
    assert refused['status'] == 'refused'
    command(host, args['instance'], 'step', 'valid-step', 'tick')
    command(host, args['instance'], 'pause', 'p')
    args['expected'] = host.inspect(args['instance'])['expected']
    result = host.call('net_sim_replay', args)
    assert result['outcome']['status'] == 'PASS' and result['outcome']['checked_commands'] == 3
    assert refused['execution_id'] not in result['source_execution_ids']
    assert host.session.executions[refused['execution_id']]['status'] == 'refused'


def test_commands_from_outside_agent_presets_cannot_be_replayed(host):
    args, _ = source_case(host, suffix=False)
    from ciw.simulation_records import observer
    _, world = host._instances[args['instance']]
    completed(world.command('observe', observer=observer('ungranted', kind='debugger', channels=['velocity'])))
    args['expected'] = host.inspect(args['instance'])['expected']
    result = host.call('net_sim_replay', args)
    assert result['status'] == 'refused' and 'outside current fixed presets' in result['refusal']['message']
    assert len(host._providers) == 1


def test_empty_observation_replay_agreement_does_not_make_numeric_evidence(host):
    i = host.call('net_sim_create', {'model': 'motion', 'attempt': 'new'})['instance']
    command(host, i, 'start', 's'); command(host, i, 'pause', 'p')
    cp = command(host, i, 'checkpoint', 'cp')['checkpoint']
    command(host, i, 'resume', 'r'); command(host, i, 'step', 'one', 'tick')
    original = command(host, i, 'observe', 'delayed', 'delayed')
    command(host, i, 'pause', 'end')
    result = host.call('net_sim_replay', {'instance': i, 'checkpoint': cp,
        'expected': host.inspect(i)['expected'], 'attempt': 'replay'})
    assert result['outcome']['status'] == 'PASS'
    stream = result['observations']['position']['artifact_id']
    assert host.call('net_observe', {'artifact': stream})['data'] == []
    comparison = host.call('net_compare', {'left': stream, 'right': original['observations']['position']['artifact_id'], 'policy': 'strict'})
    assert comparison['outcome']['status'] == 'INDETERMINATE'


def test_completed_divergence_is_fail_not_transport_failure(host):
    args, _ = source_case(host)
    class Divergent(ReferenceMotion):
        def step(self, dt):
            super().step(dt)
            self._state['position'] += 10
            self._state['history'][-1][1] += 10
    b = host._bindings['motion']
    host._bindings['motion'] = Binding(b.provider_id, lambda: Divergent(simulation_id="agent-motion"), b.policy)
    result = host.call('net_sim_replay', args)
    assert result['status'] == 'completed' and result['outcome']['status'] == 'FAIL'
    assert result['outcome']['first_divergence'] == 1 and not host._blocked
    validate_replay(parse((host._root / 'attempt-reproduction/replay.json').read_bytes()))


def test_provider_failure_retains_child_and_prefix_but_no_replay_completion(host):
    args, _ = source_case(host)
    before = host.inspect(args['instance'])
    class Broken(ReferenceMotion):
        def step(self, dt):
            super().step(dt)
            raise RuntimeError('injected after mutation')
    b = host._bindings['motion']; host._bindings['motion'] = Binding(b.provider_id, lambda: Broken(simulation_id="agent-motion"), b.policy)
    result = host.call('net_sim_replay', args)
    assert result['status'] == 'failed' and host._blocked and host._replay_reserved == 6
    assert len(host._instances) == 2 and host.inspect(args['instance']) == before
    child = next(w for h, (_, w) in host._instances.items() if h != args['instance'])
    assert child.inspect()['state_status'] == 'unknown_after_failure'
    assert not (host._root / 'attempt-reproduction/replay.json').exists()
    assert sum(e['status'] == 'refused' for e in host.session.executions.values()) == 1
    assert host.call('net_sim_replay', args) == result
    host.close(); assert all(p.status == 'stopped' for p in host._providers)


def test_failed_restore_child_is_retained_for_cleanup(host):
    args, _ = source_case(host)
    class BadRestore(ReferenceMotion):
        def restore(self, payload): raise ValueError('cannot restore')
    b = host._bindings['motion']; host._bindings['motion'] = Binding(b.provider_id, lambda: BadRestore(simulation_id="agent-motion"), b.policy)
    result = host.call('net_sim_replay', args)
    assert result['status'] == 'failed' and len(host._instances) == 2
    assert len(host.session.executions) == 11
    host.close(); assert all(p.status == 'stopped' for p in host._providers)


@pytest.mark.parametrize('path', ['replay-selection.json', 'replay.json', 'workspace'])
def test_storage_failure_blocks_new_work_and_never_reexecutes_retry(host, path):
    args, _ = source_case(host)
    if path == 'workspace':
        context = patch.object(host.session, 'save_workspace', side_effect=OSError('disk full'))
    else:
        from ciw.simulation_agent_replay import save_new as original
        def failing(target, value):
            if target.name == path: raise OSError('disk full')
            return original(target, value)
        context = patch('ciw.simulation_agent_replay.save_new', failing)
    with context: result = host.call('net_sim_replay', args)
    assert result['status'] in {'failed', 'incomplete'} and host._blocked
    assert host._replay_reserved == 6
    before = len(host.session.executions)
    assert host.call('net_sim_replay', args) == result and len(host.session.executions) == before
    if path == 'replay-selection.json': assert len(host._providers) == 1
    with pytest.raises(ValueError, match='publication is uncertain'):
        host.call('net_sim_replay', {**args, 'attempt': 'not-a-retry'})


def test_factory_failure_reserves_once(host):
    args, _ = source_case(host)
    with patch.object(ReferenceMotion, '__init__', side_effect=RuntimeError('startup failed')):
        result = host.call('net_sim_replay', args)
    assert result['status'] == 'failed' and host._replay_reserved == 6
    assert host.call('net_sim_replay', args) == result and host._replay_reserved == 6
    assert len(host._providers) == 1


def test_intent_and_source_selection_precede_factory(host):
    args, _ = source_case(host)
    b = host._bindings['motion']
    def factory():
        path = host._root / 'attempt-reproduction'
        selection = parse((path / 'replay-selection.json').read_bytes())
        assert (path / 'request.json').exists() and selection['reserved_executions'] == 6
        assert len(selection['source_execution_ids']) == 5
        return ReferenceMotion(simulation_id='agent-motion')
    host._bindings['motion'] = Binding(b.provider_id, factory, b.policy)
    assert host.call('net_sim_replay', args)['status'] == 'completed'


@pytest.mark.parametrize('grant', [False, {}, {'max_commands': True, 'max_executions': 8},
    {'max_commands': 0, 'max_executions': 8}, {'max_commands': 33, 'max_executions': 8},
    {'max_commands': 4, 'max_executions': True}, {'max_commands': 4, 'max_executions': 1},
    {'max_commands': 4, 'max_executions': 129}, {'max_commands': 4, 'max_executions': 8, 'tolerance': 1}])
def test_invalid_grants_are_rejected(grant):
    with pytest.raises(ValueError): validate_grant(grant)


def test_grant_copy_and_default_catalogs(tmp_path):
    original = {'max_commands': 8, 'max_executions': 24}
    value = validate_grant(original); original['max_commands'] = 100
    assert value['max_commands'] == 8
    assert len(descriptions()) == 4 and len(descriptions(include_replay=True)) == 5
    base, profile = demo_profiles(tmp_path / 'old')
    with from_profile(base_profile(base), profile) as old:
        assert not old.replay_enabled and 'replay' not in old.capabilities()['stateful']
        with pytest.raises(ValueError, match='not granted'):
            old.call('net_sim_replay', {'checkpoint': 'c-any', 'instance': 's-any', 'attempt': 'x',
                'expected': {'owner_id': 'owner', 'revision': 0, 'state_revision': 0}})


@pytest.mark.parametrize('key,value', [('commands', []), ('tolerance', 9), ('executable', '/bin/sh'),
    ('checkpoint', '../source'), ('attempt', '/tmp/file'), ('expected', {'owner_id': 'x','revision': True,'state_revision': 0})])
def test_agent_cannot_inject_paths_commands_or_policy(host, key, value):
    args, _ = source_case(host); args[key] = value
    before = len(host.session.executions)
    with pytest.raises(ValueError): host.call('net_sim_replay', args)
    assert len(host.session.executions) == before and host._replay_reserved == 0


def test_final_operator_report_reopens_in_existing_timeline_without_providers(host, tmp_path):
    args, _ = source_case(host)
    outcome = host.call('net_sim_replay', args)
    host.close()
    with patch('subprocess.Popen', side_effect=AssertionError('no execution')):
        loaded = open_workspace(host._root / 'workspace.json', output_dir=tmp_path / 'reader')
        summary = build(tmp_path / 'timeline', workspaces=[host._root / 'workspace.json'],
                        reports=[host._root / 'attempt-reproduction/replay.json'])
    assert loaded.executions == host.session.executions
    assert summary['instance_count'] == 2 and summary['unique_executions'] == 18
    t = parse((tmp_path / 'timeline/timeline.json').read_bytes())
    assert t['analyses'][0]['summary'] == outcome['outcome']


def test_stopped_source_and_no_observation_suffix(host):
    args, _ = source_case(host, suffix=False)
    command(host, args['instance'], 'stop', 'end')
    args['expected'] = host.inspect(args['instance'])['expected']
    response = host.call('net_sim_replay', args)
    assert response['outcome']['status'] == 'PASS' and response['view']['status'] == 'stopped'
    assert 'observations' not in response and response['reserved_executions'] == 2


def test_replay_profile_cli_requires_explicit_stateful_and_leaves_no_output(tmp_path):
    from ciw.net import main
    with pytest.raises(SystemExit):
        main(['agent', 'demo-config', '--stateful-replay', '--output-dir', str(tmp_path / 'bad')])
    assert not (tmp_path / 'bad').exists()
    assert main(['agent', 'demo-config', '--stateful', '--stateful-replay', '--output-dir', str(tmp_path / 'ok')]) == 0
    assert parse((tmp_path / 'ok/simulation-profile.json').read_bytes())['replay'] == {'max_commands': 32, 'max_executions': 128}


def test_mcp_opt_in_catalog_and_response_error_semantics(host):
    server = Server(host, extra_tools=descriptions(include_replay=True))
    def rpc(index, method, params):
        return server.handle(encode({'jsonrpc':'2.0','id':index,'method':method,'params':params}))['result']
    rpc(1, 'initialize', {'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'test','version':'1'}})
    server.handle(encode({'jsonrpc':'2.0','method':'notifications/initialized'}))
    listed = rpc(2, 'tools/list', {})['tools']
    assert len(listed) == 16 and 'net_replay' in {t['name'] for t in listed}
    args, _ = source_case(host)
    good = rpc(3, 'tools/call', {'name':'net_sim_replay','arguments':args})
    assert not good['isError'] and good['structuredContent']['outcome']['status'] == 'PASS'
    args['attempt'] = 'stale'; args['expected']['revision'] += 1
    bad = rpc(4, 'tools/call', {'name':'net_sim_replay','arguments':args})
    assert bad['isError'] and bad['structuredContent']['dispatch_performed'] is False
