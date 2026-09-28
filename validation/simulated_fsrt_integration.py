"""Required real Godot -> NET -> approved FSRT tests, not mocked qualification."""
from copy import deepcopy
from fractions import Fraction as F
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

import pytest

from ciw.adapters.subprocess import _bounded_process, PinnedSubprocessAdapter
from ciw.core.identities import content_identity
from ciw.operations.runner import seal
from ciw.session import Session
from ciw.simulated_fsrt import create, inspect, replay, sha256, OPERATION

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def generated(tmp_path_factory):
    godot=Path(os.environ['GODOT_BIN']).resolve()
    fsrt=Path(os.environ['CIW_FSRT_REPO']).resolve()
    assert godot.is_file() and fsrt.is_dir(), 'Real runtimes are required'
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    version=subprocess.check_output([str(godot),'--version'],text=True,timeout=15).strip()
    assert version.startswith('4.5.2.stable'), version
    out=Path(os.environ.get('CIW_SIMULATED_FSRT_OUT',str(tmp_path_factory.mktemp('simulated-fsrt')))).resolve()
    out.mkdir(parents=True,exist_ok=True)
    template=json.loads((ROOT/'examples/simulation-observation/source.json').read_text())
    params=json.loads((ROOT/'examples/simulation-observation/parameters.json').read_text())
    snapshots={}
    for mode in ('ordinary','held','missing','both_missing','singular'):
        source=deepcopy(template)
        source['producer'].update(engine='godot',version=version,source_revision=revision,
            executable_sha256=sha256(godot.read_bytes()),execution_id='execution-'+uuid.uuid4().hex,
            simulation_id='simulation-'+uuid.uuid4().hex,state_owner='godot',clock_owner='godot')
        source['sensor_model_id']=content_identity({'fixture':'additive_test_error','mode':mode,
            'covariance':[[1.0,1.0],[1.0,1.0]] if mode=='singular' else [[0.4,0.1],[0.1,0.9]]})
        src=out/(mode+'.json'); context=out/(mode+'.context.json');context.write_text(json.dumps(source))
        code,log=_bounded_process([str(godot),'--headless','--path',str(ROOT/'validation/simulation-observation'),
            '--script','mass_snapshot.gd','--',str(context),str(src),mode],cwd=out,timeout=20,limit=1024*1024)
        (out/(mode+'.godot.log')).write_bytes(log)
        assert code==0 and src.is_file(), log.decode(errors='replace')
        assert b'SCRIPT ERROR' not in log and b'Parse Error' not in log
        actual=json.loads(src.read_text());assert actual['producer']==source['producer']
        snapshots[mode]=(src,sha256(src.read_bytes()))
    return out,fsrt,params,snapshots


@pytest.fixture(scope='module')
def cases(generated):
    out,fsrt,params,snapshots=generated
    items={}
    for mode,(source,digest) in snapshots.items():
        path=create(source,digest,params,fsrt,out/(mode+'-run'),sys.executable)
        raw=path.read_bytes(); report=inspect(path,sha256(raw))
        items[mode]=(path,report)
    manifest={k:{'workspace':str(p.relative_to(out)),'workspace_sha256':sha256(p.read_bytes()),
        'source':snapshots[k][0].name,'source_sha256':snapshots[k][1],
        'reference':snapshots[k][0].name+'.reference.json','reference_sha256':sha256(Path(str(snapshots[k][0])+'.reference.json').read_bytes()),
        'status':r['executions'][-1]['status'],'scope':'real Godot/FSRT execution; synthetic qualification scene'}
        for k,(p,r) in items.items()}
    (out/'index.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return items


@pytest.mark.parametrize('name',['ordinary','held','missing','both_missing','singular'])
def test_real_engine_occurrence_kept_separate_from_estimator(cases,name):
    path,report=cases[name]; source=report['source'];execution=report['executions'][-1]
    assert source['producer']['engine']=='godot' and source['producer']['state_owner']=='godot'
    assert execution['execution_id']!=source['producer']['execution_id']
    assert execution['runtime']['revision']=='09a756dd9cdd3a9bb6cb14b5cd498f6259937ac2'
    assert execution['operation_id']==OPERATION
    if name in ('both_missing','singular'):
        assert execution['status']=='refused' and report['results']==[]
        assert execution['refusal']['code']==('insufficient_observations' if name=='both_missing' else 'numerical_refusal')
    else:
        result=report['results'][-1]
        assert result['verification_id'] is None and result['verification_status']=='not_verified'
        assert result['data']['source_class']=='simulated_observation'
        assert result['data']['reference_truth_supplied'] is False
        assert len(result['data']['data']['covariance_artifacts'])==6


def test_held_and_missing_are_not_repaired(cases):
    data=cases['held'][1]['results'][-1]['data']['data']
    assert data['diagnostics']['physical_model_status']=='physical_model_disagreement'
    assert data['residuals']['correction'] is None and data['residuals']['balance_after'] is None
    a=data['covariance_artifacts']; assert a['posterior']['matrix']==a['reconciled']['matrix']
    assert a['posterior']['covariance_id']!=a['reconciled']['covariance_id']
    m=cases['missing'][1]['results'][-1]['data']['data']
    assert m['calibrated_observation']['values'][1] is None
    assert m['residuals']['innovation'][1] is None
    assert len(m['covariance_artifacts']['innovation']['matrix'])==1
    assert m['diagnostics']['fault_attribution']=='confounded_or_unidentifiable'


def test_independent_rational_posterior_reference(cases):
    # Independent 2x2 closed-form inverse: test oracle only, not another solver.
    data=cases['ordinary'][1]['results'][-1]['data']['data']
    R=[[F(2,5),F(1,10)],[F(1,10),F(9,10)]];p=F(25)
    S=[[p+R[0][0],R[0][1]],[R[1][0],p+R[1][1]]]
    det=S[0][0]*S[1][1]-S[0][1]*S[1][0]
    inv=[[S[1][1]/det,-S[0][1]/det],[-S[1][0]/det,S[0][0]/det]]
    residual=[F(1),F(-3)]
    mean=[F(50)+p*sum(inv[i][j]*residual[j] for j in range(2)) for i in range(2)]
    cov=[[p*(i==j)-p*p*inv[i][j] for j in range(2)] for i in range(2)]
    assert data['unprojected_estimate']['values']==pytest.approx([float(x) for x in mean],rel=0.0,abs=1e-12)
    for i in range(2):assert data['unprojected_estimate']['covariance'][i]==pytest.approx([float(x) for x in cov[i]],rel=0.0,abs=1e-12)
    assert data['covariance_artifacts']['observation']['matrix'][0][1]==0.1


def test_reference_truth_is_not_forwarded(generated,monkeypatch):
    out,fsrt,params,sources=generated;path,digest=sources['ordinary']
    original=PinnedSubprocessAdapter.invoke;seen=[]
    def capture(self,operation,inputs):
        seen.append(deepcopy(inputs));return original(self,operation,inputs)
    monkeypatch.setattr(PinnedSubprocessAdapter,'invoke',capture)
    before=create(path,digest,params,fsrt,out/'truth-isolation-before',sys.executable)
    truth=Path(str(path)+'.reference.json');saved=truth.read_bytes();truth.write_text('{"hidden_state":"changed deliberately"}')
    try:after=create(path,digest,params,fsrt,out/'truth-isolation-after',sys.executable)
    finally:truth.write_bytes(saved)
    assert seen[0]==seen[1] and len(seen)==2
    assert 'mass_kg' not in seen[0] and 'truth' not in seen[0]
    first=inspect(before,sha256(before.read_bytes()));second=inspect(after,sha256(after.read_bytes()))
    assert first['results'][0]['data']==second['results'][0]['data']
    assert first['executions'][0]['execution_id']!=second['executions'][0]['execution_id']


def test_provider_free_reopen_and_fresh_estimator_replay(generated,cases,monkeypatch):
    out,fsrt,_,_=generated;path,old=cases['ordinary'];before=path.read_bytes()
    with monkeypatch.context() as m:
        m.setattr(subprocess,'Popen',lambda *a,**k:pytest.fail('Inspection attempted execution'))
        report=inspect(path,sha256(before))
    assert report==old and path.read_bytes()==before
    new_path=replay(path,sha256(before),fsrt,out/'replay',sys.executable)
    new=inspect(new_path,sha256(new_path.read_bytes()))
    assert new['results'][0]==old['results'][0]
    assert new['results'][-1]['execution_id']!=old['results'][0]['execution_id']
    assert new['results'][-1]['data']==old['results'][0]['data']
    assert new['source']['producer']['execution_id']==old['source']['producer']['execution_id']
    assert path.read_bytes()==before


@pytest.mark.parametrize('name',['status','source','covariance','verification'])
def test_rehashed_corruption_is_rejected(cases,tmp_path,name):
    path,_=cases['held'];data=json.loads(path.read_text());result=data['results'][0]
    if name=='status':result['data']['data']['diagnostics']['reconciliation_status']='ok'
    if name=='source':result['data']['source_class']='physical_measurement'
    if name=='covariance':result['data']['data']['covariance_artifacts']['posterior']['matrix'][0][1]+=1.0
    if name=='verification':result['verification_status']='verified'
    seal(result); altered=tmp_path/'altered.json';altered.write_text(json.dumps(data))
    with pytest.raises(ValueError):inspect(altered,sha256(altered.read_bytes()))


def test_cli_no_overwrite(generated,cases,tmp_path):
    out,fsrt,params,sources=generated;source,digest=sources['ordinary']
    p=tmp_path/'params.json';p.write_text(json.dumps(params));dest=tmp_path/'cli'
    command=[sys.executable,'-m','ciw.simulated_fsrt','create',str(source),'--expect-sha256',digest,
             '--parameters',str(p),'--fsrt-repo',str(fsrt),'--output-dir',str(dest)]
    done=subprocess.run(command,capture_output=True,text=True,timeout=60)
    assert done.returncode==0,done.stderr
    summary=json.loads(done.stdout);before=Path(summary['workspace']).read_bytes()
    assert subprocess.run(command,capture_output=True,timeout=60).returncode==2
    assert Path(summary['workspace']).read_bytes()==before
