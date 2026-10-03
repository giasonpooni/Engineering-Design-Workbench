"""Check-plan contracts plus actual retained thermal inference and fresh replay.

Synthetic data and ordinary numerical checks; not physical/native-engine qualification.
"""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from ciw.check_suite import (
    MAX_INPUT_BYTES, evaluate, plan, run_files, validate_plan, validate_report,
)
from ciw.control_checks import compare, inspect_record
from ciw.control_contracts import bytes_ref, observation, record, save_new
from ciw.core.covariance import create_covariance_artifact
from ciw.core.identities import content_identity
from ciw.net import main
from ciw.operations.runner import seal

REF = content_identity({"fixture": "check-suite-contract"})


def encoded(value):
    return (json.dumps(value, indent=2) + '\n').encode()


def stream(values=(300., 302., 303.), covariance=False):
    items = []
    for i, value in enumerate(values):
        cov = None
        if covariance and value is not None:
            cov = create_covariance_artifact(matrix=[[1.]], quantity_ids=['temperature'], units=['K'],
                frame='declared-thermal-axis', reference_values=[value], method='contract fixture',
                basis={'kind':'estimated_state','id':f'fixture-{i}'},
                provenance={'provider':'fixture','source_evidence_ids':[REF],'source_covariance_ids':[]},
                assumptions=['Synthetic declared covariance, not calibrated'])
        items.append(observation(identity={'model_id':'fixture.v1','entity_id':'core','execution_id':'fixture-execution'},
            clock={'id':'fixture-clock','time_s':float(i)},frame='declared-thermal-axis',quantity='temperature',value=value,
            unit='K', uncertainty=cov,
            provenance={'provider':'fixture','sources':[REF],'semantics':'simulated'}))
    return record('observation-stream',observations=items)


def check(name='temperature limits', kind='bounded', alias='observations', policy=None):
    return {'name':name,'kind':kind,'input':alias,
            'policy': {'minimum':250.,'maximum':350.,'unit':'K'} if policy is None else policy}


def specification(inputs, checks=None):
    return plan('declared-synthetic-conditions',inputs={alias:{'schema':value['schema'],'sha256':bytes_ref(encoded(value))}
        for alias,value in inputs.items()},checks=[check()] if checks is None else checks)


def pd_policy():
    return {'quantity_ids':['temperature'],'units':['K'],'frame':'declared-thermal-axis','margin':1e-12}


def test_bounds_and_self_contained_offline_recheck():
    value = stream(); spec=specification({'observations':value}); raw=encoded(value)
    result=evaluate(spec,{'observations':raw})
    assert result['summary']['status']=='PASS'
    assert result['summary']['check_count']==result['summary']['assertion_count']==1
    assert result['inputs']['observations']['utf8'].encode()==raw
    assert result['plan_id']==content_identity(spec)
    assert result['authority']['verification_id'] is None
    assert result['checks'][0]['cases'][0]['assertion']['verification_id'] is None
    validate_report(result)
    assert inspect_record(result)['integrity']=='checked'
    result['plan']['checks'][0]['policy']['maximum']=999
    assert spec['checks'][0]['policy']['maximum']==350


@pytest.mark.parametrize('provided', [{}, {'observations':None}], ids=['omitted','explicit-null'])
def test_missing_inputs_retain_every_declared_check(provided):
    spec=specification({'observations':stream()},[check(),check('threshold','less_than',policy={'limit':360,'unit':'K'})])
    result=evaluate(spec,provided)
    assert result['summary']['status']=='INDETERMINATE'
    assert result['summary']['missing_inputs']==['observations']
    assert result['summary']['counts']=={'PASS':0,'FAIL':0,'INDETERMINATE':2}
    assert len(result['checks'])==2
    validate_report(result)


@pytest.mark.parametrize('values,status', [((300,None),'INDETERMINATE'),((),'INDETERMINATE'),((300,500),'FAIL')],
    ids=['missing-sample','empty-series','outside-bound'])
def test_statuses_do_not_discard_incomplete_or_failed_evidence(values,status):
    value=stream(values); result=evaluate(specification({'observations':value}),{'observations':encoded(value)})
    assert result['summary']['status']==status
    validate_report(result)


def test_all_covariance_samples_are_checked_and_missing_one_is_indeterminate():
    value=stream(covariance=True); value['observations'][1]['uncertainty']=None
    seal(value['observations'][1]); seal(value)
    spec=specification({'observations':value},[check('PD at every tick','covariance_positive_definite',policy=pd_policy())])
    report=evaluate(spec,{'observations':encoded(value)})
    assert report['summary']['status']=='INDETERMINATE'
    assert report['summary']['assertion_count']==3
    assert [r['sample_index'] for r in report['checks'][0]['cases']]==[0,1,2]
    assert [r['assertion']['outcome']['status'] for r in report['checks'][0]['cases']]==['PASS','INDETERMINATE','PASS']
    validate_report(report)


def test_covariance_axis_binding_and_zero_variance():
    from ciw.core.covariance import covariance_identity
    value=stream(covariance=True); cov=value['observations'][-1]['uncertainty']
    cov['matrix']=[[0.]]; cov['covariance_id']=covariance_identity(cov)
    seal(value['observations'][-1]); seal(value)
    spec=specification({'observations':value},[check('PD','covariance_positive_definite',policy=pd_policy())])
    assert evaluate(spec,{'observations':encoded(value)})['summary']['status']=='FAIL'
    spec['checks'][0]['policy']['frame']='different-axis'
    with pytest.raises(ValueError): evaluate(spec,{'observations':encoded(value)})


def test_covariance_artifact_and_typed_state_use_existing_validator():
    from ciw.control_contracts import state
    value=stream(covariance=True); row=value['observations'][0]; cov=row['uncertainty']
    data=state(identity=row['identity'],clock=row['clock'],frame=row['frame'],
               variables={'temperature':{'value':300.,'unit':'K'}},provenance=row['provenance'],uncertainty=cov)
    inputs={'artifact':cov,'state':data}
    spec=specification(inputs,[check('artifact PD','covariance_positive_definite','artifact',pd_policy()),
                              check('state PD','covariance_positive_definite','state',pd_policy())])
    result=evaluate(spec,{alias:encoded(item) for alias,item in inputs.items()})
    assert result['summary']['status']=='PASS'
    validate_report(result)


def test_failure_dominates_missing_input_without_hiding_it():
    value=stream((500,)); missing=stream(); inputs={'observations':value,'missing':missing}
    spec=specification(inputs,[check(),check('missing measurement',alias='missing')])
    result=evaluate(spec,{'observations':encoded(value)})
    assert result['summary']['status']=='FAIL'
    assert result['summary']['counts']=={'PASS':0,'FAIL':1,'INDETERMINATE':1}
    assert result['summary']['missing_inputs']==['missing']


@pytest.mark.parametrize('case', ['empty','unknown-kind','duplicate-name','unused-input','unknown-input','unknown-field',
 'unknown-schema','unversioned','invalid-policy','schema-kind-mismatch','oversized-checks','executable-name'])
def test_bad_plans_fail_before_reading_inputs(case,tmp_path,monkeypatch):
    value=stream(); spec=specification({'observations':value})
    if case=='empty': spec['checks']=[]
    elif case=='unknown-kind': spec['checks'][0]['kind']='my_custom_code'
    elif case=='duplicate-name': spec['checks'].append(deepcopy(spec['checks'][0]))
    elif case=='unused-input': spec['inputs']['unused']=deepcopy(spec['inputs']['observations'])
    elif case=='unknown-input': spec['checks'][0]['input']='undeclared'
    elif case=='unknown-field': spec['checks'][0]['skip_missing']=True
    elif case=='unknown-schema': spec['inputs']['observations']['schema']='ciw.dynamic-code.v1'
    elif case=='unversioned': spec['schema']='ciw.check-plan'
    elif case=='invalid-policy': spec['checks'][0]['policy']['maximum']=True
    elif case=='schema-kind-mismatch': spec['checks'][0]['kind']='close_to';spec['checks'][0]['policy']={}
    elif case=='oversized-checks': spec['checks']=[check(str(i)) for i in range(33)]
    else: spec['checks'][0]['policy']['expression']='__import__("os").system("whoami")'
    with pytest.raises(ValueError): validate_plan(spec)


@pytest.mark.parametrize('mode', ['whitespace','wrong-schema','nan','duplicate','oversized','invalid-utf8'],
                         ids=['exact-bytes','schema','nonfinite','duplicate-key','byte-budget','encoding'])
def test_supplied_bad_inputs_are_not_treated_as_missing(mode):
    value=stream(); spec=specification({'observations':value}); raw=encoded(value)
    if mode=='whitespace': raw+=b'\n'
    elif mode=='wrong-schema': value['schema']='ciw.not-supported.v1';raw=encoded(value);spec['inputs']['observations']['sha256']=bytes_ref(raw)
    elif mode=='nan': raw=b'{"number":NaN}'
    elif mode=='duplicate': raw=b'{"a":1,"a":2}'
    elif mode=='oversized': raw=b' '*(MAX_INPUT_BYTES+1)
    else: raw=b'\xff'
    with pytest.raises(ValueError): evaluate(spec,{'observations':raw})


@pytest.mark.parametrize('change',['summary','case-status','delete-check','delete-input','edit-input','alter-policy',
 'identity','physical-claim','verification-id','case-index','rename','boolean-count'])
def test_resealed_report_cannot_contradict_retained_evidence(change):
    value=stream((300,500)); report=evaluate(specification({'observations':value}),{'observations':encoded(value)})
    if change=='summary': report['summary']['status']='PASS'
    elif change=='case-status': report['checks'][0]['status']='PASS'
    elif change=='delete-check': report['checks']=[]
    elif change=='delete-input': report['inputs']={}
    elif change=='edit-input': report['inputs']['observations']['utf8']+='\n'
    elif change=='alter-policy': report['plan']['checks'][0]['policy']['maximum']=600
    elif change=='identity': report['plan_id']=REF
    elif change=='physical-claim': report['authority']['physical_validation']='established'
    elif change=='verification-id': report['authority']['verification_id']='verification-'+'0'*32
    elif change=='case-index': report['checks'][0]['cases'][0]['sample_index']=0
    elif change=='rename': report['checks'][0]['name']='different check'
    else: report['summary']['check_count']=True
    seal(report)
    with pytest.raises(ValueError): validate_report(report)


def test_budget_refusal_precedes_assertion_evaluation(monkeypatch):
    import ciw.check_suite as suite
    value=stream(covariance=True)
    # 32 checks x 3 covariance marginals = 96 assertions, then lower test-only budget.
    spec=specification({'observations':value},[check(str(i),'covariance_positive_definite',policy=pd_policy()) for i in range(32)])
    monkeypatch.setattr(suite,'MAX_ASSERTIONS',95)
    def forbidden(*a,**kw): raise AssertionError('Assertions must not execute before budget preflight')
    monkeypatch.setattr(suite,'verify',forbidden)
    with pytest.raises(ValueError,match='budget'): suite.evaluate(spec,{'observations':encoded(value)})


def test_file_api_single_reads_and_source_bytes_unchanged(tmp_path,monkeypatch):
    value=stream(); spec=specification({'observations':value})
    src=tmp_path/'source.json';src.write_bytes(encoded(value))
    config=tmp_path/'plan.json';config.write_bytes(encoded(spec))
    original=Path.open;counts={}
    def counted(self,*a,**kw):
        counts[self]=counts.get(self,0)+1
        return original(self,*a,**kw)
    monkeypatch.setattr(Path,'open',counted)
    report=run_files(config,{'observations':src})
    assert counts=={config:1,src:1}
    assert report['inputs']['observations']['utf8'].encode()==encoded(value)


def test_cli_status_codes_plan_inspection_and_create_only(tmp_path,capsys):
    value=stream((300,500));spec=specification({'observations':value})
    cfg=tmp_path/'plan.json';cfg.write_bytes(encoded(spec));src=tmp_path/'source.json';src.write_bytes(encoded(value))
    out=tmp_path/'report.json'
    args=['check','--plan',str(cfg),'--input','observations='+str(src),'--output',str(out),'--json']
    assert main(args)==2
    report=json.loads(capsys.readouterr().out); assert report['summary']['status']=='FAIL'
    before=out.read_bytes(); assert main(args)==1; capsys.readouterr(); assert out.read_bytes()==before
    assert main(['inspect',str(out),'--json'])==0
    assert json.loads(capsys.readouterr().out)['record']['summary']['status']=='FAIL'
    assert main(['inspect',str(cfg),'--json'])==0
    assert json.loads(capsys.readouterr().out)['outcome']['status']=='not_evaluated'
    assert main(['check','--plan',str(cfg),'--output',str(tmp_path/'missing.json'),'--json'])==3
    assert json.loads(capsys.readouterr().out)['summary']['status']=='INDETERMINATE'
    args[args.index('--input')+1]='unknown='+str(src); args[args.index('--output')+1]=str(tmp_path/'bad.json')
    assert main(args)==1;capsys.readouterr();assert not (tmp_path/'bad.json').exists()


@pytest.mark.parametrize('bindings',[['x'],['=x'],['x='],['x=a','x=b']],ids=['no-equals','empty-alias','empty-path','duplicate-alias'])
def test_cli_binding_syntax_rejected(tmp_path,bindings,capsys):
    args=['check','--plan',str(tmp_path/'not-needed.json'),'--output',str(tmp_path/'report.json')]
    for binding in bindings:args.extend(['--input',binding])
    assert main(args)==1
    assert not (tmp_path/'report.json').exists()
    assert json.loads(capsys.readouterr().err)['status']=='refused'


@pytest.fixture(scope='module')
def actual_thermal(tmp_path_factory):
    from ciw import scientific
    from ciw.instruments import make_demo_run
    from ciw.scientific_observations import export_observations
    from ciw.session import Session
    root=tmp_path_factory.mktemp('check-actual-thermal')
    source=Path(__file__).resolve().parents[1]/'examples/thermal-observations/source.json'
    session=Session(make_demo_run(),root/'original')
    result=scientific.execute(session,'thermal-observer',source.read_bytes(),label='declared synthetic thermal check test')
    path=session.save_workspace(root/'original/workspace.json'); sha=bytes_ref(path.read_bytes())
    left=export_observations(path,expected_sha256=sha,bundle_id=result['bundle_id'],stage='posterior',entity_id='core-shell')
    measured=export_observations(path,expected_sha256=sha,bundle_id=result['bundle_id'],stage='measurement',entity_id='core-shell')
    replay=scientific.replay(session,result['bundle_id'],repositories={})
    fresh=session.save_workspace(root/'replayed.json')
    right=export_observations(fresh,expected_sha256=bytes_ref(fresh.read_bytes()),bundle_id=replay['bundle']['bundle_id'],
                              stage='posterior',entity_id='core-shell')
    comparison=compare(left['stream']['observations'],right['stream']['observations'],atol=0)
    return left,measured,right,comparison


def test_actual_thermal_bounds_full_covariance_and_fresh_replay(actual_thermal):
    left,measured,right,comparison=actual_thermal
    assert left['native_step']['execution_id']!=right['native_step']['execution_id']
    cov=left['stream']['observations'][0]['uncertainty']
    pd={'quantity_ids':cov['quantity_ids'],'units':cov['units'],'frame':cov['frame'],'margin':1e-12}
    inputs={'posterior':left,'replay':comparison}
    spec=specification(inputs,[check(alias='posterior'),check('all marginals PD','covariance_positive_definite','posterior',pd),
                              check('fresh replay matches','close_to','replay',{})])
    report=evaluate(spec,{alias:encoded(value) for alias,value in inputs.items()})
    assert report['summary']['status']=='PASS'
    assert report['summary']['check_count']==3 and report['summary']['assertion_count']==5
    for i,case in enumerate(report['checks'][1]['cases']):
        assert case['assertion']['evidence']['matrix']==left['stream']['observations'][i]['uncertainty']['matrix']
    validate_report(report)
    broken=specification({'observations':measured})
    assert evaluate(broken,{'observations':encoded(measured)})['summary']['status']=='INDETERMINATE'


def test_actual_report_reopens_without_provider_or_source_files(actual_thermal,tmp_path):
    left=actual_thermal[0];spec=specification({'observations':left});report=evaluate(spec,{'observations':encoded(left)})
    path=tmp_path/'report.json';save_new(path,report)
    code='''
import sys
from pathlib import Path
from ciw.thermal_workflow import ThermalWorkflow
from ciw.net import inspect_path

def forbidden(*a, **kw): raise AssertionError("provider launch attempted")
ThermalWorkflow.create_session=forbidden
ThermalWorkflow.replay_session=forbidden
ThermalWorkflow._adapters=forbidden
assert inspect_path(Path(sys.argv[1]))['record']['summary']['status']=='PASS'
'''
    completed=subprocess.run([sys.executable,'-c',code,str(path)],capture_output=True,text=True,timeout=30)
    assert completed.returncode==0,completed.stderr
