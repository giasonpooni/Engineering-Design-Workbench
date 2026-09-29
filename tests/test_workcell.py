"""Workcell contracts/orchestration with EXPLICITLY SIMULATED container responses.

Native Docker/Godot qualification is scripts/check_workcell.py, not this fixture.
"""
from copy import deepcopy
import base64
import json
import os
from pathlib import Path
import shutil
from unittest.mock import patch

import pytest
from ciw import workcell as wc
from ciw import workcell_contracts as c
from ciw.workcell_container import POLICY as ISOLATION, create_args, verify_config
from ciw.control_contracts import bytes_ref,load
from ciw.core.identities import content_identity
from ciw.foundry_packets import inventory
from ciw.agent_mcp import Server

ROOT=Path(os.environ.get('NET_WORKCELL_TEST_ROOT',Path(__file__).resolve().parents[1]))


def asset(raw):
    return {'sha256':bytes_ref(raw),'bytes':len(raw),'base64_chunks':[base64.b64encode(raw).decode()]}


def mesh():
    vs=[[-1.,-.125,-.5],[1.,-.125,-.5],[1.,.125,-.5],[-1.,.125,-.5],[-1.,-.125,.5],[1.,-.125,.5],[1.,.125,.5],[-1.,.125,.5]]
    ts=[[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],[3,7,6],[3,6,2],[0,4,7],[0,7,3],[1,2,6],[1,6,5]]
    return {'vertices':vs,'triangles':ts}


class FixtureBackend:
    """No container or compiler is invoked by this explicitly labelled test double."""
    def __init__(self, fault=None):self.calls=[];self.fault=fault
    def runtime_identity(self):return {'provider':'unit-test-fixture','execution_mode':'unit_test_double'}
    def invoke(self,stage,files,candidate):
        self.calls.append(stage)
        p={'schema':'ciw.workcell-process.v1','stage':stage,'nonce':'fixture','outcome':'completed','diagnostic':'','files':{},'observations':None,'logs':'unit_test_double'}
        m=mesh()
        if stage=='build':
            if b'bad_mesh' in files['compiler.py']:m['vertices'][0][0]=-3.
            p['files']={'mesh.json':asset(json.dumps(m).encode()),'motion.gd':asset(files['motion.gd']),
                        'prop.res':asset(b'fixture-not-real-native-mesh'),'main.scn':asset(b'fixture-not-real-native-scene')}
        elif stage=='test':
            p['observations']={'engine':'unit_test_double','bounds':[2.,.25,1.],
                'vertices':[m['vertices'][i] for t in m['triangles'] for i in t],
                'challenges':[[0.,2.,.25],[1.9,2.,.25],[2.,0.,.4],[-1.,1.,.1],[1.,1.,.5]],
                'values':[.5,2.,1.2,-.8,1.],'trajectory':[min(i/30.,2.) for i in range(121)],
                'scene_has_platform':True,'platform_matches':True}
            if b'bad_motion' in files['motion.gd']:p['observations']['values'][0]=-.5
        else:
            p['files']={'slice.pck':asset(b'GDPC-unit-test-package-not-real')}
            p['observations']={'pack_scene_loaded':True,'height':2.,'platform_y':2.3}
        if self.fault=='timeout':p.update(outcome='timeout',files={},observations=None,diagnostic='fixture timeout')
        if self.fault=='missing' and stage=='test':p['observations']=None
        return {'schema':'ciw.workcell-capture.v1','stage':stage,'candidate_id':candidate,'process':p,'elapsed_wall_s':.01,
            'isolation':{'mode':'docker_container','image_id':'sha256:'+'1'*64,'container_id':'2'*64,
                'policy_sha256':content_identity(ISOLATION),'checked_before_start':True,'cleanup_complete':True}}


@pytest.fixture
def setup(tmp_path):
    source=tmp_path/'source';shutil.copytree(ROOT/'examples/workcells/godot-prop',source)
    backend=FixtureBackend()
    host=wc.WorkcellHost(source,tmp_path/'cell',backend,expected_source_id=inventory(source)['inventory_id'])
    return host,backend,source


def test_complete_fixed_threshold_and_original_occurrences(setup):
    h,b,source=setup;before=inventory(source)
    candidate=h.call('net_cell_submit',{'attempt':'one','changes':{}})
    report=h.call('net_cell_build',{'attempt':'one','candidate':candidate['candidate']})
    assert report['status']=='completed' and report['execution_count']==3 and report['package_created']
    assert b.calls==['build','test','package'] and inventory(source)==before
    workspace=load(h.root/'runs/one/session/workspace.json')
    assert len({r['execution_id'] for r in workspace['results']})==3
    assert all(r['verification_id'] is None for r in workspace['results'])
    assert report['release_authorized'] is False


def test_compiler_output_rejected_blocks_all_descendants(setup):
    h,b,_=setup;cand=h.submit('bad',{'compiler.py':'bad_mesh'})
    report=h.build('bad',cand['candidate'])
    assert b.calls==['build'] and report['jobs']['build']['status']=='rejected'
    assert report['jobs']['test']['status']==report['jobs']['package']['status']=='blocked'
    assert not report['package_created']


def test_mechanic_failure_does_not_earn_packaging(setup):
    h,b,_=setup;cand=h.submit('bad',{'motion.gd':'bad_motion'})
    report=h.build('bad',cand['candidate'])
    assert b.calls==['build','test'] and report['jobs']['test']['status']=='rejected'
    assert report['jobs']['package']['status']=='blocked'


def test_same_agent_can_correct_without_changing_threshold(setup):
    h,b,_=setup
    wrong=h.submit('first',{'motion.gd':'bad_motion'});bad=h.build('first',wrong['candidate'])
    fixed=h.submit('second',{});good=h.build('second',fixed['candidate'])
    assert bad['status']=='incomplete' and good['status']=='completed'
    assert h.inspect('first')['status']=='incomplete'


@pytest.mark.parametrize('name',['spec.json','tests/test.py','.github/workflows/x.yml','../escape','/tmp/escape','project.godot','runner.py'])
def test_no_expanded_source_or_acceptance_grants(setup,name):
    h,b,_=setup
    with pytest.raises(ValueError):h.call('net_cell_submit',{'attempt':'x','changes':{name:'anything'}})
    assert not b.calls


@pytest.mark.parametrize('name',['net_cell_approve','net_cell_spawn','net_cell_change_policy','shell','net_cell_image'])
def test_no_self_upgrade_tools(setup,name):
    with pytest.raises(ValueError):setup[0].call(name,{})


def test_duplicate_submission_and_execution_are_not_extra_compute(setup):
    h,b,_=setup
    one=h.submit('same',{});two=h.submit('same',{});assert two['reused_response']
    first=h.build('same',one['candidate']);second=h.build('same',one['candidate'])
    assert second['reused_response'] and first['production_id']==second['production_id'] and len(b.calls)==3
    with pytest.raises(ValueError):h.submit('same',{'motion.gd':'different'})
    other=h.submit('new',{'motion.gd':'bad_motion'})
    with pytest.raises(ValueError):h.build('same',other['candidate'])


def test_budget_bounds_and_package_grant(tmp_path):
    source=ROOT/'examples/workcells/godot-prop';b=FixtureBackend()
    h=wc.WorkcellHost(source,tmp_path/'cell',b,expected_source_id=inventory(source)['inventory_id'],max_candidates=1,max_runs=1,allow_package=False)
    cand=h.submit('one',{});assert h.submit('same-content',{})['candidate']==cand['candidate']
    report=h.build('one',cand['candidate'])
    assert set(report['jobs'])=={'build','test'} and not report['package_created']
    with pytest.raises(ValueError):h.build('two',cand['candidate'])
    with pytest.raises(ValueError):h.submit('different',{'motion.gd':'bad_motion'})


def test_reasoning_only_scope_cannot_submit_code(tmp_path):
    source=ROOT/'examples/workcells/godot-prop'
    h=wc.WorkcellHost(source,tmp_path/'cell',FixtureBackend(),expected_source_id=inventory(source)['inventory_id'],writable=())
    with pytest.raises(ValueError):h.submit('x',{'compiler.py':'code'})
    assert h.describe()['packet']['writable']==[]


@pytest.mark.parametrize('fault,expected',[('timeout','held'),('missing','held')])
def test_unavailable_capture_holds_and_blocks(setup,fault,expected):
    h,b,_=setup;b.fault=fault;cand=h.submit('one',{});report=h.build('one',cand['candidate'])
    assert report['status']=='incomplete' and report['jobs']['package']['status']=='blocked'
    assert report['jobs']['build' if fault=='timeout' else 'test']['status']==expected


def test_inspection_cannot_start_or_modify_provider(setup):
    h,b,_=setup;cand=h.submit('one',{});h.build('one',cand['candidate'])
    before={p:p.read_bytes() for p in h.root.rglob('*') if p.is_file()}
    with patch('subprocess.Popen',side_effect=AssertionError('process')):
        assert h.inspect('one')['status']=='completed'
    assert all(p.read_bytes()==raw for p,raw in before.items())


def test_post_submission_disk_mutation_does_not_replace_frozen_candidate(setup):
    h,b,_=setup;cand=h.submit('one',{});(h.root/'candidates'/cand['candidate']/'compiler.py').write_text('bad_mesh')
    assert h.build('one',cand['candidate'])['status']=='completed'


def test_mcp_reuses_existing_server_and_only_lists_slot_tools(setup):
    h,_,_=setup;s=Server(h)
    def call(i,method,params):return s.handle(json.dumps({'jsonrpc':'2.0','id':i,'method':method,'params':params}).encode())
    init=call(1,'initialize',{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'fixture','version':'1'}})
    assert 'workcell' in init['result']['instructions']
    s.handle(b'{"jsonrpc":"2.0","method":"notifications/initialized"}')
    listed=call(2,'tools/list',{});assert len(listed['result']['tools'])==4
    out=call(3,'tools/call',{'name':'net_cell_describe','arguments':{}})
    assert out['result']['structuredContent']['package_grant'] is True


def config(source):
    return {'Image':'sha256:'+'1'*64,'Config':{'User':'65534:65534','Entrypoint':['/usr/bin/python3']},
       'HostConfig':{'NetworkMode':'none','ReadonlyRootfs':True,'Privileged':False,'Memory':536870912,'MemorySwap':536870912,
       'NanoCpus':1000000000,'PidsLimit':64,'CapDrop':['ALL'],'SecurityOpt':['no-new-privileges'],'IpcMode':'private',
       'Tmpfs':{'/work':'size=67108864','/tmp':'size=8388608'},'LogConfig':{'Type':'none'}},
       'Mounts':[{'Destination':'/input','Source':str(source),'RW':False,'Type':'bind'}]}


@pytest.mark.parametrize('field,value',[('NetworkMode','host'),('ReadonlyRootfs',False),('Privileged',True),('PidsLimit',0),
    ('Memory',0),('MemorySwap',-1),('NanoCpus',0),('CapAdd',['SYS_ADMIN']),('SecurityOpt',['unconfined']),('PidMode','host')])
def test_daemon_cannot_silently_relax_isolation(tmp_path,field,value):
    conf=config(tmp_path);conf['HostConfig'][field]=value
    with pytest.raises(ValueError):verify_config(conf,'sha256:'+'1'*64,tmp_path)


def test_fixed_create_command_no_shell_or_host_write(tmp_path):
    args=create_args('sha256:'+'1'*64,'net-cell-'+'a'*32,tmp_path,'build')
    assert '--read-only' in args and '--network=none' in args and '--pull=never' in args
    assert '-v' not in args and 'sh' not in args and '/var/run/docker.sock' not in ' '.join(args)
    assert 'readonly' in args[args.index('--mount')+1]
    verify_config(config(tmp_path),'sha256:'+'1'*64,tmp_path)


@pytest.mark.parametrize('field,value',[('bytes',True),('sha256','sha256:'+'0'*64),('base64_chunks',['!!!!']),('bytes',9999999)])
def test_artifact_substitution_or_resource_abuse_refuses(field,value):
    item=asset(b'bytes');item[field]=value
    with pytest.raises((ValueError,TypeError)):c.artifact_bytes(item)


def test_tampered_retained_capture_is_not_trusted(setup):
    h,_,_=setup;cand=h.submit('one',{});h.build('one',cand['candidate'])
    path=h.root/'runs/one/attempt-0002-checks.json';path.write_text('{}')
    with pytest.raises(ValueError):h.inspect('one')


def test_threshold_types_are_immutable():
    policy=deepcopy(c.POLICY);policy['release_authorized']=0
    with pytest.raises(ValueError):c.gates()['workcell.quality.v1'].validate_policy(policy)
