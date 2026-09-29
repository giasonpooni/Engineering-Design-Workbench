"""Actual reference campaigns on the original agent/Session boundary, not native tests."""
from copy import deepcopy
import json
from unittest.mock import patch

import pytest

from ciw.agent_api import encode, parse
from ciw.agent_mcp import Server, from_profile as base_profile
from ciw.simulation_agent import Binding, demo_profiles, from_profile
from ciw.simulation_agent_campaign import compile_grant
from ciw.simulation_agent_tools import descriptions
from ciw.simulation_campaign import validate_campaign
from ciw.simulation_control import open_workspace
from ciw.simulation_reference import ReferenceMotion
from ciw.simulation_timeline import build


@pytest.fixture
def host(tmp_path):
    base, profile = demo_profiles(tmp_path / 'profiles', campaign=True, replay=True)
    h = from_profile(base_profile(base), profile)
    yield h
    h.close()


def command(h, instance, action, attempt, preset=None):
    r = h.call('net_sim_command', {'instance': instance, 'expected': h.inspect(instance)['expected'],
        'action': action, 'attempt': attempt, 'preset': preset})
    assert r['status'] == 'completed', r
    return r


def source(h, prefix='source'):
    instance = h.call('net_sim_create', {'model': 'motion', 'attempt': prefix+'-create'})['instance']
    command(h, instance, 'start', prefix+'-start')
    command(h, instance, 'step', prefix+'-step', 'tick')
    command(h, instance, 'intervene', prefix+'-queued', 'push')
    command(h, instance, 'pause', prefix+'-pause')
    cp = command(h, instance, 'checkpoint', prefix+'-cp')['checkpoint']
    return {'checkpoint': cp, 'instance': instance, 'expected': h.inspect(instance)['expected'],
            'campaign': 'impulses', 'attempt': 'campaign-one'}


def test_actual_runner_comparison_and_original_source_unchanged(host):
    args = source(host)
    before = deepcopy(host.session.results)
    parent = host.inspect(args['instance'])
    from ciw.simulation_agent_campaign import run_campaign as original
    with patch('ciw.simulation_agent_campaign.run_campaign', wraps=original) as reused, \
         patch.object(host._providers[0], 'snapshot', side_effect=AssertionError('source must not run')):
        r = host.call('net_sim_campaign', args)
    assert reused.call_count == 1 and r['status'] == 'completed'
    assert r['summary']['comparison_counts'] == {'PASS': 1, 'FAIL': 1, 'INDETERMINATE': 0}
    assert r['reserved_executions'] == r['summary']['execution_count'] == 22
    assert r['comparisons'][1]['outcome']['metrics']['max_abs_error'] == 2
    assert host.inspect(args['instance']) == parent
    assert all(host.session.results[k] == v for k,v in before.items())
    assert len(host.session.executions) == 27 and host._campaign_reserved == 22
    assert len({c['view']['expected']['owner_id'] for c in r['cases']}) == 3
    assert all(c['view']['status'] == 'stopped' for c in r['cases'])
    baseline, replica, changed = r['cases']
    compared = host.call('net_compare', {'left': changed['observations']['position']['artifact_id'],
        'right': baseline['observations']['position']['artifact_id'], 'policy': 'strict'})
    assert compared['outcome'] == r['comparisons'][1]['outcome']
    samples = host.call('net_observe', {'artifact': replica['observations']['position']['artifact_id']})['data']
    assert all(s['identity']['execution_id'] == replica['observation_execution_id'] for s in samples)
    report = parse((host._root/'attempt-campaign-one/campaign.json').read_bytes())
    validate_campaign(report)
    assert report['record_digest'] == r['report_ref'] and report['verification_status'] == 'not_verified'
    assert r['summary']['ranking'] == 'not_performed'


def test_no_snapshots_or_full_plans_are_agent_artifacts(host):
    r = host.call('net_sim_campaign', source(host))
    for token in ('snapshot_b64', 'configuration_ref', 'delta_v', 'parameters'):
        assert token not in json.dumps(r)
    assert all(b'snapshot_b64' not in raw for raw in host.host._artifacts.values())
    with pytest.raises(ValueError): host.call('net_inspect', {'artifact': r['report_ref']})


def test_same_request_retry_after_source_change_and_close_never_runs(host):
    args = source(host); first = host.call('net_sim_campaign', args)
    command(host, args['instance'], 'stop', 'stop-source')
    before = len(host.session.executions)
    with patch.object(ReferenceMotion, '__init__', side_effect=AssertionError('no factory')):
        assert host.call('net_sim_campaign', deepcopy(args)) == first
    assert len(host.session.executions) == before and host._campaign_reserved == 22
    host.close()
    assert host.call('net_sim_campaign', args) == first


def test_new_attempt_makes_new_owners_and_occurrences(host):
    args = source(host)
    a = host.call('net_sim_campaign', args)
    b = host.call('net_sim_campaign', {**args, 'attempt': 'campaign-two'})
    assert b['status'] == 'completed' and host._campaign_reserved == 44
    ids = lambda r: {eid for c in r['cases'] for eid in c['execution_ids']}
    assert len(ids(a)) == len(ids(b)) == 22 and not ids(a) & ids(b)
    assert not {c['instance'] for c in a['cases']} & {c['instance'] for c in b['cases']}


def test_attempt_reuse_with_different_template_or_fence_refuses(host):
    args = source(host); host.call('net_sim_campaign', args)
    changed = deepcopy(args); changed['expected']['revision'] += 1
    with pytest.raises(ValueError, match='different request'): host.call('net_sim_campaign', changed)
    assert host._campaign_reserved == 22


@pytest.mark.parametrize('reason', ['stale','running','instances','executions','wrong-source','missing-boundary','grant-drift'])
def test_preflight_leaves_source_healthy_without_dispatch(host, reason):
    args = source(host)
    if reason == 'stale': args['expected']['revision'] += 1
    elif reason == 'running':
        command(host,args['instance'],'resume','resume');args['expected']=host.inspect(args['instance'])['expected']
    elif reason == 'instances': host._max_instances = 3  # Parent plus 3 exceeds total capacity.
    elif reason == 'executions': host._campaign_policy['max_executions'] = 21
    elif reason == 'wrong-source': args['checkpoint'] = source(host,'other')['checkpoint']
    elif reason == 'missing-boundary':
        _, cp = host._checkpoints[args['checkpoint']]
        # Keep the checkpoint entry itself; alter the captured view to an unbacked revision.
        world = host._instances[args['instance']][1]
        from ciw.operations.runner import seal
        world._view['revision'] += 1; seal(world._view)
        args['expected'] = host.inspect(args['instance'])['expected']
    else: host.host._policies['strict']['atol'] = 9
    before = len(host.session.executions)
    with patch.object(ReferenceMotion,'__init__',side_effect=AssertionError('no provider')):
        r = host.call('net_sim_campaign',args)
    assert r['status']=='refused' and not r['dispatch_performed']
    assert not host._blocked and host._campaign_reserved==0 and len(host.session.executions)==before
    assert not (host._root/'attempt-campaign-one/plan.json').exists()
    assert host.call('net_sim_campaign',args)==r


def test_stopped_source_is_usable_and_not_resumed(host):
    args=source(host); command(host,args['instance'],'stop','stop')
    args['expected']=host.inspect(args['instance'])['expected']
    assert host.call('net_sim_campaign',args)['status']=='completed'
    assert host.inspect(args['instance'])['status']=='stopped'


def test_refused_variant_preserves_prefix_and_tracks_failed_owner(host):
    args=source(host); count=0; b=host._bindings['motion']
    class Broken(ReferenceMotion):
        def step(self,dt):
            super().step(dt)
            raise RuntimeError('injected mutation failure')
    def factory():
        nonlocal count
        count+=1
        return (Broken if count==2 else ReferenceMotion)(simulation_id='agent-motion')
    host._bindings['motion']=Binding(b.provider_id,factory,b.policy)
    before=host.inspect(args['instance'])
    r=host.call('net_sim_campaign',args)
    assert r['status']=='failed' and host._blocked and host._campaign_reserved==22
    assert count==2 and len(host._instances)==3 and host.inspect(args['instance'])==before
    assert sum(e['status']=='refused' for e in host.session.executions.values())==1
    assert not (host._root/'attempt-campaign-one/campaign.json').exists()
    assert host.call('net_sim_campaign',args)==r
    host.close();assert all(p.status=='stopped' for p in host._providers)


def test_restore_failure_owner_is_tracked(host):
    args=source(host);b=host._bindings['motion']
    class BadRestore(ReferenceMotion):
        def restore(self,raw): raise ValueError('bad native restore')
    host._bindings['motion']=Binding(b.provider_id,lambda:BadRestore(simulation_id='agent-motion'),b.policy)
    r=host.call('net_sim_campaign',args)
    assert r['status']=='failed' and len(host._instances)==2 and host._campaign_reserved==22
    host.close();assert all(p.status=='stopped' for p in host._providers)


@pytest.mark.parametrize('filename',['campaign-selection.json','plan.json','campaign.json','workspace','observation'])
def test_failed_publication_is_not_implicitly_reexecuted(host,filename):
    args=source(host)
    if filename=='workspace': context=patch.object(host.session,'save_workspace',side_effect=OSError('disk full'))
    elif filename=='observation': context=patch.object(host.host,'_retain',side_effect=OSError('artifact store full'))
    else:
        from ciw.simulation_agent_campaign import save_new as original
        def failed(path,value):
            if path.name==filename: raise OSError('disk full')
            return original(path,value)
        context=patch('ciw.simulation_agent_campaign.save_new',failed)
    with context:r=host.call('net_sim_campaign',args)
    assert r['status'] in {'failed','incomplete'} and host._blocked and host._campaign_reserved==22
    before=len(host.session.executions)
    assert host.call('net_sim_campaign',args)==r and len(host.session.executions)==before
    if filename in {'campaign-selection.json','plan.json'}:assert len(host._providers)==1
    with pytest.raises(ValueError,match='publication is uncertain'):
        host.call('net_sim_campaign',{**args,'attempt':'cannot-repeat'})


def test_factory_failure_reservation_and_intent_retained_once(host):
    args=source(host);b=host._bindings['motion']
    def factory():
        root=host._root/'attempt-campaign-one'
        assert (root/'request.json').exists() and (root/'plan.json').exists()
        assert parse((root/'campaign-selection.json').read_bytes())['reserved_executions']==22
        raise RuntimeError('no allocation')
    host._bindings['motion']=Binding(b.provider_id,factory,b.policy)
    r=host.call('net_sim_campaign',args)
    assert r['status']=='failed' and host._campaign_reserved==22
    assert host.call('net_sim_campaign',args)==r


def test_empty_delayed_observations_remain_indeterminate(tmp_path):
    base,p=demo_profiles(tmp_path/'empty',campaign=True)
    v=parse(p.read_bytes());t=v['campaigns']['templates']['impulses'];t['steps']=1;t['observer']='delayed'
    t['variants']=t['variants'][:2];p.write_bytes(encode(v))
    with from_profile(base_profile(base),p) as h:
        i=h.call('net_sim_create',{'model':'motion','attempt':'create'})['instance']
        command(h,i,'start','s');command(h,i,'pause','p')
        cp=command(h,i,'checkpoint','cp')['checkpoint']
        r=h.call('net_sim_campaign',{'checkpoint':cp,'instance':i,'expected':h.inspect(i)['expected'],
            'campaign':'impulses','attempt':'empty'})
        assert r['status']=='completed' and r['summary']['comparison_counts']['INDETERMINATE']==1
        assert h.call('net_observe',{'artifact':r['cases'][0]['observations']['position']['artifact_id']})['data']==[]


@pytest.mark.parametrize('change',['bool-budget','too-much-budget','no-templates','unknown-model','bool-steps',
    'too-many-steps','unknown-step','unknown-observer','wrong-quantity','unknown-comparison','one-variant',
    'nine-variants','duplicate-variant','changed-baseline','unknown-intervention','extra-policy','missing-action'])
def test_invalid_operator_grants_refuse_before_host_allocation(tmp_path,change):
    base,p=demo_profiles(tmp_path/'profiles',campaign=True)
    v=parse(p.read_bytes());g=v['campaigns'];t=g['templates']['impulses']
    if change=='bool-budget':g['max_executions']=True
    elif change=='too-much-budget':g['max_executions']=513
    elif change=='no-templates':g['templates']={}
    elif change=='unknown-model':t['model']='other'
    elif change=='bool-steps':t['steps']=False
    elif change=='too-many-steps':t['steps']=33
    elif change=='unknown-step':t['step']='other'
    elif change=='unknown-observer':t['observer']='other'
    elif change=='wrong-quantity':t['quantity']='velocity'
    elif change=='unknown-comparison':t['comparison']='other'
    elif change=='one-variant':t['variants']=t['variants'][:1]
    elif change=='nine-variants':t['variants']*=3
    elif change=='duplicate-variant':t['variants'][1]['variant_id']='baseline'
    elif change=='changed-baseline':t['variants'][0]['interventions']=['push']
    elif change=='unknown-intervention':t['variants'][2]['interventions']=['not-granted']
    elif change=='extra-policy':t['atol']=100
    else:v['models']['motion']['policy']['actions'].remove('pause')
    p.write_bytes(encode(v));b=base_profile(base)
    with patch.object(ReferenceMotion,'__init__',side_effect=AssertionError('no execution')):
        with pytest.raises(ValueError):from_profile(b,p)
    assert not (base.parent/'agent-output/stateful').exists()


@pytest.mark.parametrize('key,value',[('parameters',{}),('variants',[]),('policy','relaxed'),('steps',10),
    ('campaign','../path'),('checkpoint','/tmp/checkpoint'),('attempt','bad/path'),
    ('expected',{'owner_id':'o','revision':True,'state_revision':0})])
def test_agent_cannot_supply_parameters_or_paths(host,key,value):
    args=source(host);args[key]=value
    before=len(host.session.executions)
    with pytest.raises(ValueError):host.call('net_sim_campaign',args)
    assert len(host.session.executions)==before and host._campaign_reserved==0


def test_profiles_are_optional_and_frozen(tmp_path):
    assert len(descriptions())==4
    assert len(descriptions(include_replay=True))==5
    assert len(descriptions(include_campaign=True))==5
    assert len(descriptions(include_replay=True,include_campaign=True))==6
    b,p=demo_profiles(tmp_path/'old')
    with from_profile(base_profile(b),p) as h:
        assert not h.campaign_enabled and 'campaigns' not in h.capabilities()['stateful']
        with pytest.raises(ValueError,match='not granted'):
            h.call('net_sim_campaign',{'checkpoint':'c','instance':'s','expected':{'owner_id':'o','revision':0,'state_revision':0},'campaign':'c','attempt':'a'})
    b,p=demo_profiles(tmp_path/'new',campaign=True)
    with from_profile(base_profile(b),p) as h:
        copy=h.capabilities();copy['stateful']['campaigns']['grants']['templates']['impulses']['arguments']['dt']=300
        assert h.capabilities()['stateful']['campaigns']['grants']['templates']['impulses']['arguments']['dt']==1
        p.write_text('{}')
        assert h.call('net_sim_campaign',source(h))['status']=='completed'


def test_mcp_catalog_completed_fail_is_not_transport_error(host):
    s=Server(host,extra_tools=descriptions(include_replay=True,include_campaign=True))
    def rpc(i,method,params):return s.handle(encode({'jsonrpc':'2.0','id':i,'method':method,'params':params}))['result']
    rpc(1,'initialize',{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'test','version':'1'}})
    s.handle(encode({'jsonrpc':'2.0','method':'notifications/initialized'}))
    assert len(rpc(2,'tools/list',{})['tools'])==17
    args=source(host);r=rpc(3,'tools/call',{'name':'net_sim_campaign','arguments':args})
    assert not r['isError'] and r['structuredContent']['comparisons'][1]['outcome']['status']=='FAIL'
    args['attempt']='stale';args['expected']['revision']+=1
    bad=rpc(4,'tools/call',{'name':'net_sim_campaign','arguments':args})
    assert bad['isError'] and not bad['structuredContent']['dispatch_performed']


def test_replay_budget_stays_independent_and_timeline_reads_campaign(host,tmp_path):
    args=source(host);r=host.call('net_sim_campaign',args)
    assert host._replay_reserved==0
    host.close()
    with patch('subprocess.Popen',side_effect=AssertionError('no provider')):
        s=open_workspace(host._root/'workspace.json',output_dir=tmp_path/'readback')
        summary=build(tmp_path/'timeline',workspaces=[host._root/'workspace.json'],
            reports=[host._root/'attempt-campaign-one/campaign.json'])
    assert len(s.executions)==28 and summary['instance_count']==4
    assert summary['unique_executions']==28
    t=parse((tmp_path/'timeline/timeline.json').read_bytes())
    assert t['analyses'][0]['summary']==r['summary']


def test_cli_requires_explicit_stateful(tmp_path):
    from ciw.net import main
    with pytest.raises(SystemExit):main(['agent','demo-config','--stateful-campaign','--output-dir',str(tmp_path/'bad')])
    assert not (tmp_path/'bad').exists()
    assert main(['agent','demo-config','--stateful','--stateful-campaign','--output-dir',str(tmp_path/'ok')])==0
    assert 'campaigns' in parse((tmp_path/'ok/simulation-profile.json').read_bytes())


def test_quantity_uses_existing_observation_grammar_not_handle_grammar(host):
    from ciw.simulation_records import observer
    binding = host._bindings['motion']
    policy = deepcopy(binding.policy)
    policy['observers']['position'] = observer('position',kind='debugger',channels=['position.x'])
    template = deepcopy(host._campaign_policy['templates']['impulses']['definition'])
    template['quantity'] = 'position.x'
    grant = compile_grant({'max_executions':128,'templates':{'named':template}},
        {'motion':Binding(binding.provider_id,binding.factory,policy)},host.host._policies)
    assert grant['templates']['named']['arguments']['quantity']=='position.x'
