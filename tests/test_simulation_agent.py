"""Actual reference providers through the reused MCP/CIW boundary, not native doubles."""
from copy import deepcopy
import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ciw.agent_mcp import Server, from_profile as base_profile, serve
from ciw.agent_api import encode, parse
from ciw.simulation_agent import (Binding, SimulationAgentHost, demo_profiles, from_profile,
                                  validate_policy)
from ciw.simulation_agent_tools import descriptions
from ciw.simulation_control import open_workspace
from ciw.simulation_reference import ReferenceMotion, PROVIDER_ID


@pytest.fixture
def host(tmp_path):
    base, profile = demo_profiles(tmp_path / 'profiles')
    value = from_profile(base_profile(base), profile)
    yield value
    value.close()


def call(host, name, **args):
    return host.call(name, args)


def create(host, attempt='new'):
    result = call(host, 'net_sim_create', model='motion', attempt=attempt)
    assert result['status'] == 'completed', result
    return result['instance']


def command(host, instance, action, attempt, preset=None, expected=None):
    if expected is None:
        expected = call(host, 'net_sim_inspect', instance=instance)['expected']
    return call(host, 'net_sim_command', instance=instance, attempt=attempt, expected=expected,
                action=action, preset=preset)


def good(host, instance, action, attempt, preset=None):
    result = command(host, instance, action, attempt, preset)
    assert result['status'] == 'completed', result
    return result


def test_full_loop_uses_original_compare_and_recording(host):
    original = deepcopy(host.session.run)
    parent = create(host)
    good(host, parent, 'start', 'start')
    good(host, parent, 'step', 'one', 'tick')
    good(host, parent, 'pause', 'pause')
    cp = good(host, parent, 'checkpoint', 'checkpoint')['checkpoint']
    before = call(host, 'net_sim_inspect', instance=parent)
    child = call(host, 'net_sim_branch', checkpoint=cp, attempt='branch')['instance']
    good(host, child, 'intervene', 'push', 'push')
    for handle, prefix in ((parent,'a'),(child,'b')):
        good(host, handle, 'resume', prefix+'resume')
        good(host, handle, 'step', prefix+'two', 'tick')
        good(host, handle, 'step', prefix+'three', 'tick')
    a = good(host, parent, 'observe', 'observea', 'position')['observations']['position']['artifact_id']
    b = good(host, child, 'observe', 'observeb', 'position')['observations']['position']['artifact_id']
    compared = call(host, 'net_compare', left=b, right=a, policy='strict')
    assert compared['outcome']['status'] == 'FAIL'
    assert compared['outcome']['metrics']['max_abs_error'] == 2
    observed = call(host, 'net_observe', artifact=b)
    assert observed['data'][-1]['identity']['execution_id'] != observed['data'][0]['record_digest']
    assert host.session.run == original
    assert before['expected']['owner_id'] != call(host,'net_sim_inspect',instance=child)['expected']['owner_id']


def test_create_is_attachment_not_an_invented_execution(host):
    result=call(host,'net_sim_create',model='motion',attempt='create')
    assert result['attachment_only'] and result['execution_id'] is None
    assert not host.session.executions
    assert call(host,'net_sim_create',model='motion',attempt='create') == result
    assert len(host._instances)==1


def test_command_retry_and_changed_attempt_data(host):
    instance=create(host)
    fence=host.inspect(instance)['expected']
    first=command(host,instance,'start','start',expected=fence)
    assert command(host,instance,'start','start',expected=fence)==first
    assert len(host.session.executions)==1
    with pytest.raises(ValueError,match='different request'):
        command(host,instance,'pause','start')
    assert len(host.session.executions)==1


def test_stale_fence_refusal_is_retained_and_does_not_touch_provider(host):
    instance=create(host)
    fence=host.inspect(instance)['expected']
    good(host,instance,'start','start')
    provider=host._providers[0]
    with patch.object(provider,'step',side_effect=AssertionError('no native dispatch')):
        refused=command(host,instance,'step','stale','tick',expected=fence)
    assert refused['status']=='refused' and refused['refusal']['code']=='stale_simulation_command'
    assert refused['result_id'] is None and host.inspect(instance)['status']=='running'
    assert command(host,instance,'step','stale','tick',expected=fence)==refused
    good(host,instance,'step','fresh','tick')


def test_branch_retry_preserves_parent_and_does_not_launch_twice(host):
    instance=create(host);good(host,instance,'start','start');good(host,instance,'pause','pause')
    checkpoint=good(host,instance,'checkpoint','cp')['checkpoint']
    before=host.inspect(instance)
    first=call(host,'net_sim_branch',checkpoint=checkpoint,attempt='branch')
    with patch.object(ReferenceMotion,'__init__',side_effect=AssertionError('no new process')):
        again=call(host,'net_sim_branch',checkpoint=checkpoint,attempt='branch')
    assert first==again and host.inspect(instance)==before and len(host._providers)==2


@pytest.mark.parametrize('injection',['../path','/tmp/a','x/y','https://example','x\\y','', 'x'*81])
def test_handles_and_attempts_are_not_paths(host,injection):
    with pytest.raises(ValueError):call(host,'net_sim_create',model='motion',attempt=injection)
    assert not host._providers


@pytest.mark.parametrize('which',['action','preset','extra','expected','checkpoint','model'])
def test_scope_injection_is_rejected_before_execution(host,which):
    i=create(host)
    if which=='checkpoint':
        with pytest.raises(ValueError):call(host,'net_sim_branch',checkpoint='unknown',attempt='x')
    elif which=='model':
        with pytest.raises(ValueError):call(host,'net_sim_create',model='unknown',attempt='x')
    else:
        args={'instance':i,'attempt':'x','action':'step','preset':'tick','expected':host.inspect(i)['expected']}
        if which=='action':args['action']='shell'
        elif which=='preset':args['preset']='ungranted'
        elif which=='extra':args['arguments']={'dt':999,'executable':'evil'}
        else:args['expected']['revision']=True
        with pytest.raises(ValueError):host.call('net_sim_command',args)
    assert not host.session.executions


def test_checkpoint_bytes_are_not_an_agent_artifact(host):
    i=create(host);good(host,i,'start','a');good(host,i,'pause','b')
    cp=good(host,i,'checkpoint','c')
    assert 'snapshot_b64' not in json.dumps(cp)
    with pytest.raises(ValueError):call(host,'net_inspect',artifact=cp['checkpoint'])
    assert not host.host._generated


def test_empty_delayed_observations_remain_indeterminate(host):
    i=create(host)
    result=good(host,i,'observe','early','delayed')
    artifact=result['observations']['position']['artifact_id']
    assert call(host,'net_observe',artifact=artifact)['data']==[]
    compared=call(host,'net_compare',left=artifact,right=artifact,policy='strict')
    assert compared['outcome']['status']=='INDETERMINATE'


def test_provider_failure_quarantines_without_success(host):
    i=create(host);good(host,i,'start','a');provider=host._providers[0]
    def mutate(dt):
        provider._state['tick']+=1
        raise RuntimeError('injected after mutation')
    with patch.object(provider,'step',mutate):
        result=command(host,i,'step','broken','tick')
    assert result['status']=='refused' and result['result_id'] is None
    assert result['view']['state_status']=='unknown_after_failure'
    assert host.session.executions[result['execution_id']]['status']=='refused'


def test_publication_failure_blocks_new_commands_but_retry_is_not_reexecuted(host):
    i=create(host);fence=host.inspect(i)['expected']
    with patch.object(host.session,'save_workspace',side_effect=OSError('disk-full')):
        value=command(host,i,'start','a',expected=fence)
    assert value['status']=='incomplete' and host._blocked
    assert command(host,i,'start','a',expected=fence)==value
    assert len(host.session.executions)==1
    with pytest.raises(ValueError,match='publication is uncertain'):command(host,i,'pause','b')


def test_request_retention_failure_never_launches_provider(host):
    with patch('ciw.simulation_agent.save_new',side_effect=OSError('disk-full')):
        result=call(host,'net_sim_create',model='motion',attempt='first')
    assert result['status']=='incomplete' and not host._providers
    assert call(host,'net_sim_create',model='motion',attempt='first')==result


def test_inspection_is_captured_metadata_not_a_provider_call(host):
    i=create(host)
    with patch.object(host._providers[0],'identity',side_effect=AssertionError('no provider')):
        view=call(host,'net_sim_inspect',instance=i)
        assert view['clock']['time_s']==0
        assert call(host,'net_capabilities')['stateful']['instances'][i]==view
    view['expected']['owner_id']='mutated'
    assert host.inspect(i)['expected']['owner_id']!='mutated'


def test_budgets_and_stop_cleanup(host):
    host._maximum=1
    i=create(host)
    with pytest.raises(ValueError,match='budget'):command(host,i,'start','x')
    report=host.close()
    assert report['status']=='closed' and host._providers[0].status=='stopped'
    assert len(host.session.executions)==1  # cleanup stop remains an original execution
    assert host.close()==report
    reopened=open_workspace(host._root/'workspace.json',output_dir=host._root/'readback')
    assert reopened.executions==host.session.executions


def test_caller_policy_mutation_cannot_expand_presets(tmp_path):
    base,profile=demo_profiles(tmp_path/'p');core=base_profile(base)
    original=parse(profile.read_bytes())['models']['motion']['policy']
    h=SimulationAgentHost(core,source='source',bindings={'motion':Binding(PROVIDER_ID,ReferenceMotion,original)})
    try:
        original['steps']['bad']={'dt':999}
        i=create(h)
        with pytest.raises(ValueError):command(h,i,'step','no','bad')
    finally:h.close()


def test_server_extension_preserves_original_tools_and_protocol(host):
    s=Server(host,extra_tools=descriptions())
    result=s.handle(encode({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'test','version':'1'}}}))
    assert result['result']['protocolVersion']=='2025-11-25'
    s.handle(encode({'jsonrpc':'2.0','method':'notifications/initialized'}))
    listed=s.handle(encode({'jsonrpc':'2.0','id':2,'method':'tools/list'}))['result']['tools']
    assert len(listed)==15 and {'net_execute','net_compare','net_sim_command'}<={x['name'] for x in listed}
    listed.clear()
    assert len(s.handle(encode({'jsonrpc':'2.0','id':5,'method':'tools/list'}))['result']['tools'])==15
    response=s.handle(encode({'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'net_sim_create','arguments':{'model':'motion','attempt':'create'}}}))
    assert not response['result']['isError']
    i=response['result']['structuredContent']['instance']
    response=s.handle(encode({'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':'net_sim_command','arguments':{'instance':i,'attempt':'bad','expected':host.inspect(i)['expected'],'action':'step','preset':'tick'}}}))
    assert response['result']['isError'] and response['result']['structuredContent']['status']=='refused'


def test_duplicate_catalog_names_are_rejected(host):
    with pytest.raises(ValueError,match='duplicate'):
        Server(host,extra_tools=descriptions()+descriptions())


def test_notifications_cannot_execute(host):
    s=Server(host,extra_tools=descriptions())
    assert s.handle(encode({'jsonrpc':'2.0','method':'tools/call','params':{'name':'net_sim_create','arguments':{'model':'motion','attempt':'one'}}})) is None
    assert not host._providers


def test_factory_failure_is_consumed_once_and_retained(host):
    b=host._bindings['motion']
    with patch('ciw.simulation_reference.ReferenceMotion.__init__',side_effect=RuntimeError('broken startup')):
        result=call(host,'net_sim_create',model='motion',attempt='failed')
    assert result['status']=='failed'
    assert call(host,'net_sim_create',model='motion',attempt='failed')==result
    assert not host._providers


def test_unknown_provider_profile_refuses_before_simulation_output(tmp_path):
    base,profile=demo_profiles(tmp_path/'p');core=base_profile(base)
    value=parse(profile.read_bytes());value['models']['motion']['provider']='evil.module'
    profile.write_bytes(encode(value))
    with pytest.raises(ValueError,match='Only installed'):from_profile(core,profile)
    assert not (core._output/'stateful').exists()


def test_frozen_profile_no_provider_start_during_bind(tmp_path):
    base,profile=demo_profiles(tmp_path/'p');core=base_profile(base)
    with patch.object(ReferenceMotion,'__init__',side_effect=AssertionError('no launch')):
        extended=from_profile(core,profile)
    try:
        profile.write_text('{}')
        assert create(extended)
    finally:extended.close()


def test_stateful_tool_does_not_grant_acceptance(host):
    with pytest.raises(ValueError):call(host,'net_accept',instance='anything')
    assert call(host,'net_capabilities')['authority']['verification_id'] is None


def test_net_facade_generates_both_optional_profiles(tmp_path,capsys):
    from ciw.net import main
    assert main(['agent','demo-config','--stateful','--output-dir',str(tmp_path/'p')])==0
    value=json.loads(capsys.readouterr().out)
    assert Path(value['profile']).is_file() and Path(value['simulation_profile']).is_file()
    assert not (tmp_path/'p/agent-output').exists()


def test_instance_budget_stops_factory_before_launch(host):
    host._max_instances=1
    create(host)
    with patch.object(ReferenceMotion,'__init__',side_effect=AssertionError('no launch')):
        result=call(host,'net_sim_create',model='motion',attempt='over')
    assert result['status']=='failed' and 'instance budget' in result['reason']
    assert len(host._providers)==1


def test_inflight_create_cannot_be_raced(host):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    entered,release=threading.Event(),threading.Event()
    original=ReferenceMotion.__init__
    def blocked(provider,**kwargs):
        entered.set();assert release.wait(timeout=10);original(provider,**kwargs)
    with patch.object(ReferenceMotion,'__init__',blocked), ThreadPoolExecutor(1) as pool:
        pending=pool.submit(call,host,'net_sim_create',model='motion',attempt='create')
        assert entered.wait(timeout=10)
        try:
            with pytest.raises(ValueError,match='in flight'):
                call(host,'net_sim_create',model='motion',attempt='create')
        finally:release.set()
        assert pending.result(timeout=15)['status']=='completed'
    assert len(host._providers)==1
