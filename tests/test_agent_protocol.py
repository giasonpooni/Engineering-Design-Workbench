"""Real CIW agent operations, fixed policy, scope refusals and MCP transport tests."""
from copy import deepcopy
import io
import json
from pathlib import Path
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from ciw.agent_api import AgentHost, AUTHORITY, bytes_ref, encode, parse
from ciw.agent_mcp import Server, demo_config, from_profile, serve, VERSIONS
from ciw.agent_tools import descriptions, validate_arguments
from ciw.control_plane import builtin_registry, experiment, ParameterSpace, Choice
from ciw.control_contracts import record, save_new, observation
from ciw.control_checks import compare, validate_comparison
from ciw.check_suite import validate_report
from ciw.instruments import make_demo_run
from ciw.computational_source import _snapshot, bind_source


@pytest.fixture
def configured(tmp_path):
    profile = demo_config(tmp_path / 'demo')
    return profile, from_profile(profile)


def call(host, name, **kwargs):
    return host.call(name, kwargs)


def stream(values, *, unit='m', missing=False, execution='execution-fixture'):
    return record('observation-stream', observations=[observation(
        identity={'model_id':'fixture-model', 'entity_id':'fixture-entity', 'execution_id':execution},
        clock={'id':'fixture-clock', 'time_s':i*0.1}, frame='fixture-frame', quantity='position',
        value=None if missing and i == 0 else value, unit=unit,
        provenance={'provider':'agent-test-fixture', 'sources':['sha256:'+'1'*64], 'semantics':'simulated'})
        for i,value in enumerate(values)])


def observation_host(tmp_path):
    comparison_policies = {'strict': {'atol':1e-8,'rtol':1e-8}, 'loose':{'atol':100.,'rtol':0.}}
    suites={'regression':{'inputs':{'difference':{'schema':'ciw.comparison.v1','comparison_policy':'strict'}},
        'checks':[{'name':'position', 'kind':'close_to', 'input':'difference', 'policy':{}}]}}
    return AgentHost(registry=builtin_registry(), inputs={
        'left':encode(stream([1.,2.,3.])), 'right':encode(stream([1.,2.,3.],execution='execution-other')),
        'faulty':encode(stream([1.,20.,3.])), 'missing':encode(stream([1.,2.,3.],missing=True)),
        'wrong_units':encode(stream([1.,2.,3.],unit='cm'))},
        output_dir=tmp_path/'out', comparisons=comparison_policies, check_suites=suites)


def test_real_execute_candidate_replay_and_baseline_preservation(configured):
    path, host = configured
    original=(path.parent/'source.json').read_bytes()
    base=(path.parent/'experiment.json').read_bytes()
    first=call(host,'net_execute',source='source',graph='baseline',attempt='original')
    assert first['status']=='completed' and len(first['execution_ids'])==1
    repeated=call(host,'net_execute',source='source',graph='baseline',attempt='original')
    assert repeated['reused_response'] is True and repeated['execution_ids']==first['execution_ids']
    replay=call(host,'net_replay',original_attempt='original',new_attempt='reproduced')
    assert replay['status']=='completed' and replay['execution_ids']!=first['execution_ids']
    proposed=call(host,'net_candidate',baseline='baseline',changes={'statistics':{'channel':'v'}})
    assert proposed['executed'] is False
    candidate=call(host,'net_execute',source='source',graph=proposed['candidate']['artifact_id'],attempt='candidate')
    assert candidate['status']=='completed' and candidate['execution_ids']!=first['execution_ids']
    run=call(host,'net_inspect',artifact=first['artifacts']['graph-run']['artifact_id'])['data']
    assert run['nodes']['statistics']['result']['data']['unit']=='m'
    run2=call(host,'net_inspect',artifact=candidate['artifacts']['graph-run']['artifact_id'])['data']
    assert run2['nodes']['statistics']['result']['data']['unit']=='m/s'
    assert (path.parent/'source.json').read_bytes()==original
    assert (path.parent/'experiment.json').read_bytes()==base
    assert first['authority']==AUTHORITY
    assert host.capabilities()['execution_budget']['used']==3


def test_retention_hashes_match_exact_file_bytes(configured):
    profile,host=configured
    candidate=call(host,'net_candidate',baseline='baseline',changes={'statistics':{'channel':'v'}})['candidate']
    raw=(profile.parent/'agent-output'/(candidate['artifact_id']+'.json')).read_bytes()
    assert bytes_ref(raw)==candidate['sha256']
    # An identical proposal is reused without replacing the file.
    assert call(host,'net_candidate',baseline='baseline',changes={'statistics':{'channel':'v'}})['candidate']==candidate


def test_frozen_inputs_and_detached_responses(configured):
    path,host=configured
    (path.parent/'source.json').write_text('malformed')
    assert call(host,'net_execute',source='source',graph='baseline',attempt='frozen')['status']=='completed'
    first=host.capabilities();first['catalog']['operations'].clear();first['inputs'].clear()
    assert host.capabilities()['catalog']['operations'] and host.capabilities()['inputs']
    data=call(host,'net_inspect',artifact='baseline')['data'];data['nodes'].clear()
    assert call(host,'net_inspect',artifact='baseline')['data']['nodes']


@pytest.mark.parametrize('changes',[{}, {'unknown':{'channel':'v'}}, {'statistics':{}},
    {'statistics':{'channel':'missing'}},{'statistics':{'channel':True}},
    {'statistics':{'operation_id':'accept.v1'}},{'statistics':{'atol':1e10}},
    {'statistics':{'library':'/tmp/evil.so'}},{'statistics':{'channel':['q']}}])
def test_candidates_cannot_broaden_scope(configured, changes):
    _,host=configured
    with pytest.raises(ValueError): call(host,'net_candidate',baseline='baseline',changes=changes)
    assert host.capabilities()['execution_budget']['used']==0


@pytest.mark.parametrize('attempt',['../escape','/tmp/file','a/b','a\\b','https://host/x','', '.', 'a'*81])
def test_attempt_not_a_filesystem_path(configured,attempt):
    _,host=configured
    with pytest.raises(ValueError): call(host,'net_execute',source='source',graph='baseline',attempt=attempt)


@pytest.mark.parametrize('name',['net_accept','accept','net_merge','net_shell','net_publish','net_register_provider'])
def test_no_escalation_tools(configured,name):
    _,host=configured
    with pytest.raises(ValueError): host.call(name,{})


def test_attempt_collision_and_explicit_replay(configured):
    _,host=configured
    call(host,'net_execute',source='source',graph='baseline',attempt='one')
    candidate=call(host,'net_candidate',baseline='baseline',changes={'statistics':{'channel':'v'}})
    with pytest.raises(ValueError,match='different request'):
        call(host,'net_execute',source='source',graph=candidate['candidate']['artifact_id'],attempt='one')
    with pytest.raises(ValueError,match='new attempt'):
        call(host,'net_replay',original_attempt='one',new_attempt='one')
    with pytest.raises(ValueError,match='Unknown attempt'):
        call(host,'net_replay',original_attempt='nonexistent',new_attempt='two')


def test_simultaneous_retry_executes_once(configured):
    _,host=configured
    def run(_): return call(host,'net_execute',source='source',graph='baseline',attempt='same')
    with ThreadPoolExecutor(max_workers=4) as pool: results=list(pool.map(run,range(4)))
    assert len({x['execution_ids'][0] for x in results})==1
    assert sum(x['reused_response'] for x in results)==3


def test_readonly_and_unbound_capabilities(tmp_path):
    source=encode(make_demo_run())
    host=AgentHost(registry=builtin_registry(),inputs={'source':source})
    assert not host.capabilities()['output_enabled']
    assert all(not x['bound'] for x in host.capabilities()['catalog']['operations'].values())
    with pytest.raises(ValueError): call(host,'net_execute',source='source',graph='source',attempt='one')
    with pytest.raises(ValueError): AgentHost(registry=builtin_registry(),inputs={},allow_operations=('statistics.v1',))


def test_allowlist_checks_every_node_before_any_dispatch(tmp_path):
    registry=builtin_registry(bind=True)
    graph=experiment('two',model_id='oscillator',nodes=[
        {'node_id':'stats','operation_id':'statistics.v1','parameters':{},'inputs':{},'depends_on':[]},
        {'node_id':'spectrum','operation_id':'spectrum.periodogram.v1','parameters':{},'inputs':{},'depends_on':[]}])
    host=AgentHost(registry=registry, inputs={'source':encode(make_demo_run()),'graph':encode(graph)},
        allow_operations=('statistics.v1',),output_dir=tmp_path/'out')
    with pytest.raises(ValueError,match='not enabled'):call(host,'net_execute',source='source',graph='graph',attempt='one')
    assert host.capabilities()['execution_budget']['used']==0 and not list((tmp_path/'out').iterdir())


def test_node_and_attempt_budgets(tmp_path):
    path=demo_config(tmp_path/'case');profile=parse(path.read_bytes());profile['max_executions']=1
    path.write_bytes(encode(profile));host=from_profile(path)
    call(host,'net_execute',source='source',graph='baseline',attempt='one')
    with pytest.raises(ValueError,match='budget'):call(host,'net_replay',original_attempt='one',new_attempt='two')
    assert call(host,'net_execute',source='source',graph='baseline',attempt='one')['reused_response']


def test_registry_drift_refuses_before_execution(configured):
    _,host=configured
    host._registry._contracts['statistics.v1']['runtime']['version']='modified'
    with pytest.raises(ValueError,match='Registry changed'):
        call(host,'net_execute',source='source',graph='baseline',attempt='drift')


def test_provider_failure_consumes_attempt_and_retains_original_records(tmp_path):
    from ciw.operations.registry import Operation
    from ciw.adapters.oscillator import OscillatorAdapter
    from ciw.control_plane import CapabilityRegistry
    registry=CapabilityRegistry()
    registry.advertise(OscillatorAdapter.manifest, runtime={'name':'failure-fixture'},
        capabilities={'statistics.v1':['statistics'],'spectrum.periodogram.v1':['spectrum']})
    calls=[]
    def failure(run,p):calls.append(p);raise ValueError('deliberate-provider-failure')
    registry.bind(Operation('statistics.v1','analysis',failure,lambda:{'name':'failure-fixture'}))
    graph=experiment('failure',model_id='oscillator',nodes=[{'node_id':'stats','operation_id':'statistics.v1',
        'parameters':{},'inputs':{},'depends_on':[]}])
    host=AgentHost(registry=registry, inputs={'source':encode(make_demo_run()),'graph':encode(graph)},
        allow_operations=('statistics.v1',),output_dir=tmp_path/'out')
    first=call(host,'net_execute',source='source',graph='graph',attempt='failure')
    assert first['status']=='incomplete' and first['execution_ids'] and not first['result_ids']
    assert call(host,'net_execute',source='source',graph='graph',attempt='failure')['reused_response']
    assert len(calls)==1
    ws=call(host,'net_inspect',artifact=first['artifacts']['workspace']['artifact_id'],selector=['executions'])['data']
    assert next(iter(ws.values()))['status']=='refused'


def test_offline_inspection_does_not_dispatch(configured,monkeypatch):
    _,host=configured
    outcome=call(host,'net_execute',source='source',graph='baseline',attempt='one')
    monkeypatch.setattr('ciw.control_plane.run_graph',lambda *a:pytest.fail('executed during inspect'))
    monkeypatch.setattr('ctypes.CDLL',lambda *a:pytest.fail('native library load'))
    result=call(host,'net_inspect',artifact=outcome['artifacts']['workspace']['artifact_id'],selector=['session'])
    assert 'session_id' not in result['data']
    retained=call(host,'net_inspect',artifact=outcome['artifacts']['workspace']['artifact_id'],selector=['executions'])
    assert list(retained['data'])==outcome['execution_ids']


@pytest.mark.parametrize('other,expected',[('right','PASS'),('faulty','FAIL'),('missing','INDETERMINATE'),('wrong_units','INDETERMINATE')])
def test_existing_typed_comparison_and_fixed_check_suite(tmp_path,other,expected):
    host=observation_host(tmp_path)
    c=call(host,'net_compare',left='left',right=other,policy='strict')
    assert c['outcome']['status']==expected
    value=host._get(c['comparison']['artifact_id']);validate_comparison(value)
    report=call(host,'net_qualify',suite='regression',inputs={'difference':c['comparison']['artifact_id']})
    assert report['summary']['status']==expected
    validate_report(host._get(report['report']['artifact_id']))
    assert report['authority']==AUTHORITY


def test_permissive_comparison_cannot_satisfy_strict_qualification(tmp_path):
    host=observation_host(tmp_path)
    c=call(host,'net_compare',left='left',right='faulty',policy='loose')
    assert c['outcome']['status']=='PASS'
    with pytest.raises(ValueError,match='fixed qualification policy'):
        call(host,'net_qualify',suite='regression',inputs={'difference':c['comparison']['artifact_id']})
    with pytest.raises(ValueError):call(host,'net_compare',left='left',right='faulty',policy='unregistered')
    with pytest.raises(ValueError):host.call('net_compare',{'left':'left','right':'right','policy':'strict','atol':100})


def test_missing_input_never_passes(tmp_path):
    host=observation_host(tmp_path)
    r=call(host,'net_qualify',suite='regression',inputs={})
    assert r['summary']['status']=='INDETERMINATE' and r['summary']['missing_inputs']==['difference']
    with pytest.raises(ValueError):call(host,'net_qualify',suite='invented',inputs={})
    with pytest.raises(ValueError):call(host,'net_qualify',suite='regression',inputs={'extra':'left'})


def test_observation_pagination_and_selector_limits(tmp_path):
    host=observation_host(tmp_path)
    page=call(host,'net_observe',artifact='left',limit=2)
    assert len(page['data'])==2 and page['next_offset']==2
    assert len(call(host,'net_observe',artifact='left',offset=2,limit=2)['data'])==1
    for kwargs in ({'limit':True},{'offset':-1},{'limit':0},{'limit':129}):
        with pytest.raises(ValueError):call(host,'net_observe',artifact='left',**kwargs)
    with pytest.raises(ValueError):call(host,'net_inspect',artifact='left',selector=['observations',True])
    assert call(host,'net_inspect',artifact='left',selector=['observations',0,'unit'])['data']=='m'


def test_existing_source_context_and_edit_guard(tmp_path,monkeypatch):
    raw=b'def rhs(x):\n    return x * 2\n\nother = 3\n'
    selection=bind_source(_snapshot(raw,'test/repository','a'*40,'model.py','python'),
        {'symbol':'rhs','line':None,'span':None},editable=True)
    host=AgentHost(registry=builtin_registry(),inputs={'selection':encode(selection)})
    monkeypatch.setattr('subprocess.run',lambda *a,**k:pytest.fail('subprocess from retained source'))
    context=call(host,'net_source_context',artifact='selection')
    assert 'return x * 2' in context['excerpt'] and context['limits']['source_text_is_untrusted_data']
    valid=call(host,'net_check_edit',artifact='selection',candidate_utf8=raw.replace(b'x * 2',b'x * 3').decode())
    assert valid['status']=='PASS' and valid['applied'] is False
    invalid=call(host,'net_check_edit',artifact='selection',candidate_utf8=raw.replace(b'other = 3',b'other = 4').decode())
    assert invalid['status']=='FAIL'


@pytest.mark.parametrize('payload',[b'{}',b'{"a":1,"a":2}',b'{"a":NaN}',b'[]',b'null',b'{"schema":"python.import","module":"os"}'])
def test_untrusted_initial_documents_refused(payload):
    with pytest.raises((ValueError,KeyError)):
        AgentHost(registry=builtin_registry(),inputs={'input':payload})


def test_output_dir_is_create_only_and_no_symlinks(configured,tmp_path):
    path,_=configured
    with pytest.raises(FileExistsError):from_profile(path)
    target=tmp_path/'target';target.mkdir()
    link=tmp_path/'link'
    try:link.symlink_to(target,target_is_directory=True)
    except OSError as exc: pytest.skip(f'Symlink creation unavailable: {exc}')
    with pytest.raises(ValueError,match='symbolic'):
        AgentHost(registry=builtin_registry(),inputs={},output_dir=link/'out')


def rpc(server, method, params=None, id=1):
    message={'jsonrpc':'2.0','method':method,'params':params or {}}
    if id is not None:message['id']=id
    return server.handle(encode(message))


def ready(host):
    s=Server(host)
    response=rpc(s,'initialize',{'protocolVersion':VERSIONS[0],'capabilities':{},'clientInfo':{'name':'test','version':'1'}},0)
    assert response['result']['protocolVersion']==VERSIONS[0]
    assert rpc(s,'notifications/initialized',id=None) is None
    return s


def test_mcp_discovery_and_tool_call(configured):
    _,host=configured;s=ready(host)
    tools=rpc(s,'tools/list',id=1)['result']['tools']
    assert len(tools)==11 and {t['name'] for t in tools}=={t['name'] for t in descriptions()}
    response=rpc(s,'tools/call',{'name':'net_execute','arguments':{'source':'source','graph':'baseline','attempt':'real'}},2)
    assert not response['result']['isError']
    assert response['result']['structuredContent']['status']=='completed'
    assert json.loads(response['result']['content'][0]['text'])==response['result']['structuredContent']


def test_notification_cannot_execute_and_duplicate_rpc_cannot_execute(configured):
    _,host=configured;s=ready(host)
    p={'name':'net_execute','arguments':{'source':'source','graph':'baseline','attempt':'real'}}
    assert rpc(s,'tools/call',p,id=None) is None
    assert host.capabilities()['execution_budget']['used']==0
    rpc(s,'tools/call',p,id=2)
    p['arguments']['attempt']='unwanted'
    assert rpc(s,'tools/call',p,id=2)['error']['code']==-32600
    assert host.capabilities()['execution_budget']['used']==1


def test_mcp_initialization_and_unknown_methods(configured):
    _,host=configured;s=Server(host)
    assert rpc(s,'tools/list')['error']['code']==-32002
    assert rpc(s,'initialize',{},2)['error']['code']==-32602
    assert rpc(s,'initialize',{'protocolVersion':'2099-01-01','capabilities':{},'clientInfo':{'name':'test','version':'1'}},3)['result']['protocolVersion']==VERSIONS[0]
    assert rpc(s,'tools/list',id=4)['error']['code']==-32002
    rpc(s,'notifications/initialized',id=None)
    assert rpc(s,'initialize',{},5)['error']['code']==-32600
    assert rpc(s,'resources/list',id=6)['error']['code']==-32601


@pytest.mark.parametrize('raw', [b'{"jsonrpc":"2.0","id":1,"id":2,"method":"ping"}',b'{',b'\xff',b'{"a":Infinity}'])
def test_mcp_malformed_json_refused(configured,raw):
    _,host=configured
    assert ready(host).handle(raw)['error']['code']==-32700


@pytest.mark.parametrize('value',[[],None,{'jsonrpc':'2.0','id':True,'method':'ping'},
    {'jsonrpc':'2.0','id':None,'method':'ping'}, {'jsonrpc':'2.0','id':2**54,'method':'ping'}])
def test_invalid_rpc_request(configured,value):
    _,host=configured
    assert ready(host).handle(encode(value))['error']['code']==-32600


def test_mcp_tool_refusal_keeps_connection_alive(configured):
    _,host=configured;s=ready(host)
    bad=rpc(s,'tools/call',{'name':'net_shell','arguments':{'command':'rm -rf /'}},2)
    assert bad['result']['isError']
    assert rpc(s,'tools/call',{'name':'net_capabilities'},3)['result']['isError'] is False


def test_stdio_roundtrip_and_frame_bounds(configured):
    _,host=configured
    messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':VERSIONS[0],'capabilities':{},'clientInfo':{'name':'t','version':'1'}}},
        {'jsonrpc':'2.0','method':'notifications/initialized'},
        {'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'net_capabilities'}}]
    output=io.BytesIO();assert serve(host,io.BytesIO(b'\n'.join(encode(m) for m in messages)+b'\n'),output)==0
    assert len(output.getvalue().splitlines())==2
    output=io.BytesIO();assert serve(host,io.BytesIO(b'x'*(1024*1024+1)),output)==2
    assert json.loads(output.getvalue())['error']['code']==-32700


def test_real_cli_process_uses_machine_readable_stdout(tmp_path):
    profile=demo_config(tmp_path/'cli')
    messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':VERSIONS[0],'capabilities':{},'clientInfo':{'name':'subprocess','version':'1'}}},
        {'jsonrpc':'2.0','method':'notifications/initialized'},
        {'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'net_execute','arguments':{'source':'source','graph':'baseline','attempt':'actual'}}}]
    result=subprocess.run([sys.executable,'-m','ciw.agent_mcp','serve','--profile',str(profile)],
        input=b'\n'.join(encode(m) for m in messages)+b'\n',capture_output=True,timeout=30)
    assert result.returncode==0,result.stderr.decode()
    rows=[json.loads(line) for line in result.stdout.splitlines()]
    assert len(rows)==2 and rows[1]['result']['structuredContent']['status']=='completed'


def test_extract_existing_record_from_real_execution(configured):
    _,host=configured
    result=call(host,'net_execute',source='source',graph='baseline',attempt='original')
    projected=call(host,'net_extract',artifact=result['artifacts']['graph-run']['artifact_id'],selector=['experiment'])
    assert host._get(projected['artifact']['artifact_id'])==host._get('baseline')
    assert projected['authority']==AUTHORITY
    with pytest.raises(ValueError):call(host,'net_extract',artifact='baseline',selector=['nodes',0,'operation_id'])


def test_capability_policy_digest_is_stable_and_checkable(configured):
    _,host=configured
    before=host.capabilities()
    call(host,'net_candidate',baseline='baseline',changes={'statistics':{'channel':'v'}})
    after=host.capabilities()
    assert before['host_policy_sha256']==after['host_policy_sha256']==bytes_ref(encode(after['host_policy']))


def test_reserved_alias_refused():
    with pytest.raises(ValueError,match='reserved'):
        AgentHost(registry=builtin_registry(),inputs={'a-shadow':encode(make_demo_run())})


def test_large_valid_mcp_response_is_not_rejected_as_source_text(configured):
    _,host=configured
    result=call(host,'net_execute',source='source',graph='baseline',attempt='one')
    messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':VERSIONS[0],'capabilities':{},'clientInfo':{'name':'test','version':'1'}}},
        {'jsonrpc':'2.0','method':'notifications/initialized'},
        {'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'net_inspect','arguments':{
            'artifact':'source','selector':[]}}}]
    out=io.BytesIO();assert serve(host,io.BytesIO(b'\n'.join(encode(m) for m in messages)+b'\n'),out)==0
    assert not json.loads(out.getvalue().splitlines()[-1])['result']['isError']
    assert len(out.getvalue().splitlines()[-1])>65536
