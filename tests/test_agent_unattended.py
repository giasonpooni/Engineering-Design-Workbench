"""Unattended supervisor tests. All model/cell fixtures here are explicitly simulated."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch
import uuid

import pytest
from ciw.agent_local_model import LocalModel
from ciw.agent_unattended import apply_decision, validate_task, decision_schema, drive, inspect, McpWorkcell
from ciw.workcell import WorkcellHost
from ciw.workcell_smith import SMITH, SOURCES
from ciw.foundry_packets import inventory
from test_workcell_smith import Fixture
from test_agent_local_model import profile, identity, reply


PATH = 'workshops/workshop_world.gd'
RULE = 'workshops/workshop_rules.gd'


def task():
    return {'schema':'ciw.unattended-task.v1','goal':'Fixture task, not actual creative model work.',
            'editable_paths':[PATH], 'context_paths':[PATH], 'max_revisions':2, 'stop_after_accept':False}


def edit(old='synthetic source fixture', new='improved fixture', path=PATH):
    return {'action':'edit','summary':'Fixture change','edits':[{'path':path,'old':old,'new':new}]}


def test_exact_replacement_only_and_stop():
    source={PATH:'synthetic source fixture\n'}
    assert apply_decision(edit(), source, [PATH])[PATH]=='improved fixture\n'
    assert source[PATH]=='synthetic source fixture\n'
    assert apply_decision({'action':'stop','summary':'Done','edits':[]},source,[PATH]) is None


@pytest.mark.parametrize('fault', ['path','ambiguous','stale','noop','count','boolean','stop_edit','shell','long','empty'])
def test_bad_candidate_never_becomes_executable(fault):
    d=edit(); source={PATH:'synthetic source fixture\n'}
    if fault=='path':d['edits'][0]['path']='workcells/smith_probe.gd'
    elif fault=='ambiguous':source[PATH]*=2
    elif fault=='stale':d['edits'][0]['old']='not present'
    elif fault=='noop':d['edits'][0]['new']=d['edits'][0]['old']
    elif fault=='count':d['edits']*=5
    elif fault=='boolean':d['edits'][0]['new']=True
    elif fault=='stop_edit':d['action']='stop'
    elif fault=='shell':d['shell']='anything'
    elif fault=='long':d['edits'][0]['new']='x'*8193
    else:d['edits']=[]
    with pytest.raises((ValueError, TypeError)): apply_decision(d,source,[PATH])


@pytest.mark.parametrize('field,value',[('max_revisions',True),('context_paths',[]),('editable_paths',['../escape']),
    ('stop_after_accept',1),('goal',''),('image','something')])
def test_invalid_task(field,value):
    t=task();t[field]=value
    with pytest.raises((ValueError,TypeError)):validate_task(t)


class ModelFixture(LocalModel):
    def __init__(self, decisions, fault=None):
        p=profile();p.update(max_calls=3,max_total_tokens=20000)
        super().__init__(p);self.decisions=decisions;self.requests=[];self.fault=fault
    def probe(self):return identity()
    def request(self,path,payload=None):
        assert path=='/api/chat';self.requests.append(deepcopy(payload))
        if self.fault=='timeout':raise TimeoutError('fixture timeout, not real inference')
        if self.fault=='malformed':return b'{'
        result=reply(self.decisions[len(self.requests)-1])
        if self.fault=='usage':result.pop('eval_count')
        if self.fault=='length':result['done_reason']='length'
        return json.dumps(result).encode()


class SdkReply:
    def __init__(self,obj):
        self.obj=obj;self.structuredContent=obj['structuredContent']
        self.content=[type('Part',(),part)() for part in obj['content']]
    def model_dump(self,**_):return deepcopy(self.obj)


class SdkFixture:
    def __init__(self,host):self.host=host
    async def call_tool(self,name,args):
        try:
            value=self.host.call(name,args)
            obj=self.host.mcp_result(name,value)
            if obj is None:obj={'structuredContent':value,'content':[{'type':'text','text':json.dumps(value)}], 'isError':False}
        except ValueError as e:
            value={'status':'refused','reason':str(e)}
            obj={'structuredContent':value,'content':[{'type':'text','text':json.dumps(value)}],'isError':True}
        return SdkReply(obj)


@pytest.fixture
def setup(tmp_path):
    root=tmp_path/'experiment';root.mkdir()
    source=tmp_path/'source';source.mkdir()
    for name in SOURCES:
        p=source/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('synthetic source fixture\n')
    class UniqueFixture(Fixture):
        def invoke(self,stage,files,cid):
            response=super().invoke(stage,files,cid)
            response['isolation']['container_id']=uuid.uuid4().hex*2
            return response
    backend=UniqueFixture()
    host=WorkcellHost(source,root/'host/cell',backend,expected_source_id=inventory(source)['inventory_id'],recipe=SMITH)
    return root,McpWorkcell(SdkFixture(host),root,host.root),backend


def test_unattended_edit_build_images_next_call_and_stop(setup):
    root,cell,backend=setup
    model=ModelFixture([edit(),{'action':'stop','summary':'Observed the fixture outcome','edits':[]}])
    report=asyncio.run(drive(cell,model,task(),root))
    assert report['status']=='model_stopped', report
    assert report['original_workcell_yield']['unique_technically_accepted_revisions']==1
    assert report['model_usage']['total_tokens']==240
    assert len(model.requests)==2 and backend.calls==['build','test','package']*2
    assert model.requests[1]['messages'][1]['images']
    assert 'improved fixture' in model.requests[1]['messages'][1]['content']
    assert report['model_usage']['billed_usd'] is None
    with patch('subprocess.Popen',side_effect=AssertionError('provider')),patch('http.client.HTTPConnection',side_effect=AssertionError('model')):
        audited=inspect(root)
    assert audited['fresh_execution'] is False and audited['model_usage']==report['model_usage']


def test_rejection_then_real_feedback_driven_fixture_correction(setup):
    root,cell,backend=setup;t=task();t['editable_paths']=[RULE];t['context_paths']=[RULE]
    model=ModelFixture([edit(new='WRONG fixture',path=RULE),edit(old='WRONG fixture',new='corrected fixture',path=RULE),
                        {'action':'stop','summary':'stop','edits':[]}])
    r=asyncio.run(drive(cell,model,t,root))
    assert r['status']=='model_stopped',r
    assert r['original_workcell_yield']['unique_changed_candidates']==2
    assert r['original_workcell_yield']['unique_technically_accepted_revisions']==1
    assert 'rejected' in model.requests[1]['messages'][1]['content']
    assert backend.calls==['build','test','package','build','test','build','test','package']
    assert inspect(root)['original_workcell_yield']['unique_changed_candidates']==2


@pytest.mark.parametrize('fault', ['usage','timeout','malformed','length'])
def test_ambiguous_protocol_or_usage_halts_no_auto_retry(setup,fault):
    root,cell,backend=setup;model=ModelFixture([edit()],fault=fault)
    r=asyncio.run(drive(cell,model,task(),root))
    assert r['status']=='held_model_or_protocol_error',r
    assert len(model.requests)==1 and backend.calls==['build','test','package']
    if fault!='length':assert r['model_usage']['total_tokens'] is None
    assert inspect(root)['model_usage']==r['model_usage']


def test_out_of_scope_model_edit_cannot_change_gates(setup):
    root,cell,backend=setup
    r=asyncio.run(drive(cell,ModelFixture([edit(path='workcells/smith_probe.gd')]),task(),root))
    assert r['status']=='held_model_or_protocol_error'
    assert backend.calls==['build','test','package']


def test_stops_at_preexisting_revision_and_model_budget(setup):
    root,cell,backend=setup;t=task();t['max_revisions']=1
    model=ModelFixture([edit(),edit(old='improved fixture',new='another fixture')])
    r=asyncio.run(drive(cell,model,t,root))
    assert r['status']=='revision_budget_exhausted' and len(backend.calls)==6


def test_noop_return_to_baseline_does_not_inflate_yield(setup):
    root,cell,backend=setup
    model=ModelFixture([edit(),edit(old='improved fixture',new='synthetic source fixture')])
    r=asyncio.run(drive(cell,model,task(),root))
    assert r['status']=='duplicate_candidate' and len(backend.calls)==6
    assert r['original_workcell_yield']['unique_changed_candidates']==1


def test_operator_can_stop_after_first_technical_pass(setup):
    root,cell,_=setup;t=task();t['stop_after_accept']=True
    model=ModelFixture([edit()]);r=asyncio.run(drive(cell,model,t,root))
    assert r['status']=='technical_acceptance_stop' and len(model.requests)==1


def test_independent_model_reply_cannot_supply_billing_or_human_time(setup):
    root,cell,backend=setup;d=edit();d['cost_usd']=0
    r=asyncio.run(drive(cell,ModelFixture([d]),task(),root))
    assert len(backend.calls)==3 and r['model_usage']['billed_usd'] is None


def test_tamper_model_usage_or_native_checks_is_rejected(setup):
    root,cell,_=setup
    asyncio.run(drive(cell,ModelFixture([{'action':'stop','summary':'stop','edits':[]}]),task(),root))
    path=root/'model-001-turn.json';record=json.loads(path.read_text());record['usage']['generated_tokens']=999;path.write_text(json.dumps(record))
    with pytest.raises(ValueError):inspect(root)
