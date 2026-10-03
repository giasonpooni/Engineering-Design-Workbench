"""Project controller tests. Fake engine fixtures are not native qualification."""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ciw import game_project as p
from ciw import game_project_workflow as w
from ciw.control_contracts import bytes_ref, load
from ciw.control_plane import Choice, ParameterSpace
from ciw.core.identities import content_identity
from ciw.operations.runner import seal


def profile():
    return {'schema':p.PROFILE, 'project_id':'fixture-title', 'source_revision':'0'*40,
        'source_scope':'explicit unit test double, not game execution', 'engine_version_prefix':'4.5.1',
        'entrypoint':'tests/capture.gd', 'files':{'tests/capture.gd': bytes_ref(b'extends SceneTree\n')},
        'parameter_space':ParameterSpace({'amount':Choice((0,1,2))}).to_dict(),
        'scenario':{'schema':'ciw.game-scenario.v1','project_id':'fixture-title','scenario_id':'count',
            'model_id':'fixture.v1','source_class':'authored_game','clock':{'id':'fixture','tick_seconds':1,'duration_ticks':1},
            'entities':['player'], 'channels':{'count':{'entity_id':'player','quantity':'count','unit':'1','frame':'test','perspective':'world'}},
            'parameters':{'amount':1,'fixture':True},
            'checks':[{'id':'count-one','kind':'final_equals','channel':'count','value':1}]}}


def capture(spec, parameters):
    scenario=p.candidate_scenario(spec,parameters)
    samples=[{'tick':i,'channel':'count','value':parameters['assignment']['amount']} for i in range(2)]
    dropped=parameters['diagnostic_fault']=='drop-sample'
    if dropped:samples.pop()
    record={'schema':'ciw.game-trace.v1','request_nonce':parameters['nonce'],'scenario_digest':content_identity(scenario),
            'engine':'godot','engine_version':'4.5.1.stable.unit-test-double','samples':samples,'events':[],
            'complete':not dropped,'dropped_samples':int(dropped),'dropped_events':0}
    raw=json.dumps(record)
    return {'schema':'ciw.game-capture.v1','request':{'scenario':scenario,'scenario_digest':content_identity(scenario),
            'nonce':parameters['nonce'],'diagnostic_fault':parameters['diagnostic_fault']},'trace_utf8':raw,'trace_sha256':bytes_ref(raw.encode())}


class FixtureBinding:
    def __init__(self,spec,fail=False):self.profile=deepcopy(spec);self.calls=0;self.fail=fail
    def runtime_identity(self):return {'provider':'project.unit-test-double','execution_mode':'unit_test_double'}
    def invoke(self,spec,parameters):
        from ciw.adapters.protocol import AdapterRefusal
        self.calls+=1
        if self.fail:raise AdapterRefusal('fixture_failure','explicit unit double')
        assert spec==self.profile
        return capture(spec,parameters)


def orders():
    return [{'job_id':'candidate','attempts':[{'amount':0},{'amount':1}],'depends_on':[]},
            {'job_id':'regression','attempts':[{'amount':1}],'depends_on':['candidate']}]


def run(tmp_path, spec=None, cases=None, binding=None):
    spec=profile() if spec is None else spec
    source,plan=w.declare(spec,orders() if cases is None else cases)
    binding=FixtureBinding(spec) if binding is None else binding
    return w.execute(spec,source,plan,binding,tmp_path),binding


def test_title_source_is_an_existing_run_and_not_live_game_state():
    from ciw.instruments import validate_run
    from ciw.core.identities import validate_evidence_identity
    source=p.make_run(profile());validate_run(source);validate_evidence_identity(source)
    assert source['metadata']['game_project']['scenario']==source['metadata']['game_scenario']
    assert source['metadata']['provenance']['origin']=='scenario_declaration_not_gameplay_observation'


def test_real_session_failure_correction_dependency_and_feedback(tmp_path):
    report,binding=run(tmp_path/'campaign')
    assert report['status']=='completed' and binding.calls==3
    data=w.feedback(tmp_path/'campaign')
    assert data['counts']['accepted']==2 and data['execution_count']==3
    first,second=data['jobs']['candidate']['attempts']
    assert first['status']=='rejected' and first['failed_rules'][0]['id']=='count-one'
    assert second['status']=='accepted' and second['failed_rules']==[]
    assert first['candidates'][0]['execution_id']!=second['candidates'][0]['execution_id']


def test_grid_uses_original_finite_parameter_space(tmp_path):
    spec=profile();grid=w.grid_orders(spec)
    assert len(grid)==3
    report,binding=run(tmp_path/'grid',spec,grid)
    assert report['status']=='incomplete' and binding.calls==3
    assert w.feedback(tmp_path/'grid')['counts']=={'accepted':1,'rejected':2,'held':0,'refused':0,'blocked':0}


def test_missing_sample_holds_and_never_consumes_repair(tmp_path):
    spec=profile();source,plan=w.declare(spec,orders())
    graph=plan['jobs'][0]['attempts'][0];graph['nodes'][0]['parameters']['diagnostic_fault']='drop-sample'
    seal(graph);seal(plan)
    binding=FixtureBinding(spec)
    report=w.execute(spec,source,plan,binding,tmp_path/'campaign')
    assert report['jobs']['candidate']['status']=='held' and binding.calls==1
    assert w.feedback(tmp_path/'campaign')['counts']['blocked']==1


def test_runtime_refusal_no_result_and_no_retry(tmp_path):
    report,binding=run(tmp_path/'campaign',binding=FixtureBinding(profile(),fail=True))
    assert report['result_count']==0 and binding.calls==1
    result=w.feedback(tmp_path/'campaign')
    assert result['counts']['refused']==1 and result['counts']['blocked']==1


def test_provider_free_feedback_unchanged_bytes(tmp_path):
    root=tmp_path/'campaign';run(root)
    before={str(f):f.read_bytes() for f in root.rglob('*.json')}
    with patch('subprocess.Popen',side_effect=AssertionError('process')),patch.object(FixtureBinding,'invoke',side_effect=AssertionError('provider')):
        assert w.feedback(root)['fresh_execution'] is False
    assert before=={str(f):f.read_bytes() for f in root.rglob('*.json')}


@pytest.mark.parametrize('value',[True,False,3,-1,None,{},[],1.0,'1'])
def test_out_of_domain_values_refuse_before_write(tmp_path,value):
    with pytest.raises(ValueError):w.declare(profile(),[{'job_id':'bad','attempts':[{'amount':value}],'depends_on':[]}])


@pytest.mark.parametrize('change',['policy','model','route','parameters','later_assignment','source','job_source','project_identity'])
def test_resealed_bad_order_refuses_before_write_or_execute(tmp_path,change):
    spec=profile();source,plan=w.declare(spec,orders());graph=plan['jobs'][0]['attempts'][1]
    if change=='policy':graph['nodes'][0]['parameters']['checks']=[]
    elif change=='model':
        for g in plan['jobs'][0]['attempts']:g['model_id']='other';seal(g)
    elif change=='route':
        for g in plan['jobs'][0]['attempts']:g['nodes'][0]['operation_id']='shell.execute.v1';seal(g)
    elif change=='parameters':graph['parameters']={'amount':1}
    elif change=='later_assignment':graph['nodes'][0]['parameters']['assignment']['amount']=99
    elif change=='source':source['metadata']['game_project']['scenario']['checks'][0]['value']=0
    elif change=='project_identity':plan['project_id']='different-title'
    else:plan['source_evidence_id']='sha256:'+'0'*64
    seal(graph);seal(plan);binding=FixtureBinding(spec)
    with pytest.raises((ValueError,KeyError)):w.execute(spec,source,plan,binding,tmp_path/'no')
    assert binding.calls==0 and not (tmp_path/'no').exists()


@pytest.mark.parametrize('path',['../bad.gd','/bad.gd','C:/bad.gd','a\\bad.gd','a//bad.gd','./bad.gd','a/../bad.gd','.hidden/test.gd','CON.gd','aux/test.gd','a./test.gd','test.py','https://x.gd','a:b.gd'])
def test_source_paths_have_identical_bounded_platform_semantics(path):
    with pytest.raises(ValueError):p.relative_script(path)


@pytest.mark.parametrize('kind',['empty','case_collision','missing_entry','digest','unbounded_files','unknown_field','engine','scenario_source','domain','fixed_checks'])
def test_profile_validation(kind):
    spec=profile()
    if kind=='empty':spec['files']={}
    elif kind=='case_collision':spec['files']['tests/Capture.gd']=next(iter(spec['files'].values()))
    elif kind=='missing_entry':spec['entrypoint']='missing.gd'
    elif kind=='digest':spec['files']['tests/capture.gd']='not-a-digest'
    elif kind=='unbounded_files':spec['files'].update({f'{i}.gd':'sha256:'+'0'*64 for i in range(33)})
    elif kind=='unknown_field':spec['shell']='bash'
    elif kind=='engine':spec['engine_version_prefix']='4.5'
    elif kind=='scenario_source':spec['scenario']['source_class']='synthetic_fixture'
    elif kind=='domain':spec['parameter_space']=ParameterSpace({'missing':Choice((1,))}).to_dict()
    else:spec['scenario']['checks']=[]
    with pytest.raises(ValueError):p.validate_profile(spec)


def snapshot(tmp_path):
    spec=profile();root=tmp_path/'source';(root/'tests').mkdir(parents=True)
    (root/'tests/capture.gd').write_bytes(b'extends SceneTree\n')
    engine=tmp_path/'godot';engine.write_bytes(b'not an executable: unit double')
    return spec,root,engine


def test_pin_rejects_wrong_binary_and_changed_source(tmp_path):
    spec,root,engine=snapshot(tmp_path)
    with pytest.raises(ValueError):p.GodotProjectBinding(engine,root,spec,expected_sha256='sha256:'+'0'*64)
    (root/'tests/capture.gd').write_text('changed')
    with pytest.raises(ValueError):p.GodotProjectBinding(engine,root,spec,expected_sha256=p.file_sha(engine))


def test_source_file_and_parent_symlinks_refused(tmp_path):
    spec,root,engine=snapshot(tmp_path)
    original=root/'tests/capture.gd';original.rename(root/'other.gd')
    try:original.symlink_to(root/'other.gd')
    except OSError:pytest.skip('Platform cannot create symlinks')
    with pytest.raises(ValueError):p.GodotProjectBinding(engine,root,spec,expected_sha256=p.file_sha(engine))


def test_binary_drift_is_refusal(tmp_path):
    spec,root,engine=snapshot(tmp_path);binding=p.GodotProjectBinding(engine,root,spec,expected_sha256=p.file_sha(engine))
    engine.write_bytes(b'changed')
    from ciw.adapters.protocol import AdapterRefusal
    with pytest.raises(AdapterRefusal):binding.runtime_identity()


def test_frozen_snapshot_not_live_checkout_and_no_mutable_profile_alias(tmp_path):
    spec,root,engine=snapshot(tmp_path);binding=p.GodotProjectBinding(engine,root,spec,expected_sha256=p.file_sha(engine))
    (root/'tests/capture.gd').write_bytes(b'new unpublished code')
    spec['scenario']['checks'][0]['value']=0
    view=binding.profile;view['scenario']['checks'][0]['value']=0
    def process(command,cwd,watched,timeout):
        assert (cwd/'tests/capture.gd').read_bytes()==b'extends SceneTree\n'
        request=load(cwd/'request.json')
        params={'assignment':{'amount':1},'nonce':request['nonce'],'diagnostic_fault':'none'}
        data=capture(binding.profile,params)
        (cwd/'trace.json').write_text(data['trace_utf8']);(cwd/'stdout.log').write_bytes(b'');(cwd/'stderr.log').write_bytes(b'')
    with patch('ciw.game_project.run_process',side_effect=process):
        result=binding.invoke(binding.profile,{'assignment':{'amount':1},'nonce':'fixture','diagnostic_fault':'none'})
    assert result['request']['scenario']['checks'][0]['value']==1
    assert (root/'tests/capture.gd').read_bytes()==b'new unpublished code'


@pytest.mark.parametrize('fault',['error_log','oversized','wrong_version','wrong_engine','wrong_nonce','timeout','missing_file'])
def test_native_boundary_negative_doubles(tmp_path,fault):
    spec,root,engine=snapshot(tmp_path);binding=p.GodotProjectBinding(engine,root,spec,expected_sha256=p.file_sha(engine))
    params={'assignment':{'amount':1},'nonce':'fixture','diagnostic_fault':'none'}
    def process(command,cwd,watched,timeout):
        if fault=='timeout':raise RuntimeError('runtime timeout')
        result=capture(spec,params);data=json.loads(result['trace_utf8'])
        if fault=='wrong_version':data['engine_version']='4.5.10.stable'
        if fault=='wrong_engine':data['engine']='not godot'
        if fault=='wrong_nonce':data['request_nonce']='different'
        if fault!='missing_file':(cwd/'trace.json').write_text('x'*65537 if fault=='oversized' else json.dumps(data))
        (cwd/'stdout.log').write_bytes(b'');(cwd/'stderr.log').write_bytes(b'SCRIPT ERROR: no' if fault=='error_log' else b'')
    from ciw.adapters.protocol import AdapterRefusal
    with patch('ciw.game_project.run_process',side_effect=process),pytest.raises(AdapterRefusal):binding.invoke(spec,params)


def test_read_profile_exact_bytes_not_silently_reserialized(tmp_path):
    target=tmp_path/'profile.json';raw=json.dumps(profile()).encode();target.write_bytes(raw)
    assert p.read_profile(target,bytes_ref(raw))==profile()
    target.write_bytes(raw+b' ')
    with pytest.raises(ValueError):p.read_profile(target,bytes_ref(raw))


def test_feedback_rejects_changed_checks_even_with_resealed_report(tmp_path):
    root=tmp_path/'campaign';run(root)
    report=load(root/'production.json');report['jobs']['candidate']['status']='held';seal(report)
    (root/'production.json').write_text(json.dumps(report))
    with pytest.raises(ValueError):w.feedback(root)


def test_feedback_reads_only_frozen_validated_bytes(tmp_path):
    root=tmp_path/'campaign';run(root)
    with w.frozen_campaign(root) as frozen:
        (root/'production.json').write_text('{}')
        assert w.feedback(frozen)['counts']['accepted']==2


def test_cli_declaration_and_feedback_never_spawn(tmp_path):
    from ciw.net import main
    target=tmp_path/'profile.json';target.write_text(json.dumps(profile()))
    with patch('subprocess.Popen',side_effect=AssertionError('process')):
        assert main(['production','project','grid','--profile',str(target),'--profile-sha256',p.file_sha(target),'--output-dir',str(tmp_path/'orders')])==0
    assert len(load(tmp_path/'orders/plan.json')['jobs'])==3
    run(tmp_path/'campaign')
    assert main(['production','project','feedback',str(tmp_path/'campaign'),'--output',str(tmp_path/'feedback.json')])==0
    assert main(['production','project','feedback',str(tmp_path/'campaign'),'--output',str(tmp_path/'feedback.json')])==1


def test_full_grid_budget_refuses_before_execution(tmp_path):
    spec=profile();source,plan=w.declare(spec,w.grid_orders(spec));binding=FixtureBinding(spec)
    with pytest.raises(ValueError):w.execute(spec,source,plan,binding,tmp_path/'no',max_operations=2)
    assert binding.calls==0 and not (tmp_path/'no').exists()
