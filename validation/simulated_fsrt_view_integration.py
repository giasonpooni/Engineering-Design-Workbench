"""Exporter regression against real retained Godot/FSRT observations; no provider rerun.

CI generates the source bundle immediately before this module. For local read-only
reruns use a checksum-verified bundle; that does not qualify fresh engine execution.
"""
import base64
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from ciw.fsrt_view import export_view as export_rci_view, sha256, write_view
from ciw.session import loads_json
from ciw.simulated_fsrt_view import export_view, ENVELOPE
from ciw.operations.runner import seal


@pytest.fixture(scope='module')
def bundle():
    root = Path(os.environ['CIW_SYNTHETIC_VIEW_FIXTURES']).resolve()
    index = loads_json((root/'index.json').read_text())
    assert set(index) == {'ordinary','held','missing','both_missing','singular'}
    for entry in index.values():
        for kind in ('workspace','source','reference'):
            assert sha256((root/entry[kind]).read_bytes()) == entry[kind+'_sha256']
    return root, index


def case(bundle, name='ordinary'):
    root,index=bundle;item=index[name];path=root/item['workspace']
    workspace=loads_json(path.read_text());ex=workspace['executions'][-1]['execution_id']
    return path,item,workspace,ex


@pytest.mark.parametrize('name',['ordinary','held','missing','both_missing','singular'])
def test_exact_original_records_and_source_bytes(bundle,name,tmp_path):
    path,item,workspace,ex=case(bundle,name)
    before={p:p.read_bytes() for p in path.parent.iterdir() if p.is_file()}
    view=export_view(path,ex,expected_workspace_sha256=item['workspace_sha256'])
    payload=loads_json(view['payload'])
    assert view['schema']==ENVELOPE and sha256(view['payload'].encode())==view['sha256']
    assert payload['execution']==workspace['executions'][-1]
    assert payload['result']==(workspace['results'][-1] if workspace['results'] else None)
    raw=base64.b64decode(workspace['run']['metadata']['simulation_source']['raw_b64'])
    assert payload['source']['payload'].encode()==raw
    assert payload['source']['source_sha256']==sha256(raw)
    source=loads_json(payload['source']['payload'])
    assert source['clock']=={'tick':1,'ticks_per_second':10,'phase':'post_step'}
    assert source['producer']['execution_id']!=ex
    assert payload['authority']['reference_truth_included'] is False
    assert 'reference_class' not in view['payload']
    for p,data in before.items():assert p.read_bytes()==data
    output=tmp_path/'view.json';write_view(view,output)
    with pytest.raises(FileExistsError):write_view(view,output)


def test_export_does_not_execute_or_register_provider(bundle,monkeypatch):
    path,item,_,ex=case(bundle)
    monkeypatch.setattr(subprocess,'Popen',lambda *a,**k:pytest.fail('Inspection attempted a process'))
    export_view(path,ex,expected_workspace_sha256=item['workspace_sha256'])
    assert not any(n=='set_lcm' or n.startswith('set_lcm.') for n in sys.modules)


def test_estimator_input_truth_is_not_exposed(bundle):
    path,item,workspace,ex=case(bundle)
    result=loads_json(export_view(path,ex,expected_workspace_sha256=item['workspace_sha256'])['payload'])
    assert result['result']['data']['reference_truth_supplied'] is False
    assert 'mass_kg' not in result['source'] and 'true_mass' not in result['source']
    assert result['result']['data']==workspace['results'][-1]['data']


def test_old_exporter_does_not_accept_synthetic_source(bundle):
    path,item,_,ex=case(bundle)
    with pytest.raises(ValueError):export_rci_view(path,ex,expected_workspace_sha256=item['workspace_sha256'])


@pytest.mark.parametrize('kind',['wrong_digest','unknown_execution','engine_execution','bad_id','oversize'])
def test_explicit_occurrence_and_budget_refusals(bundle,tmp_path,kind):
    path,item,workspace,ex=case(bundle);expected=item['workspace_sha256']
    if kind=='wrong_digest':expected='sha256:'+'f'*64
    if kind=='unknown_execution':ex='execution-'+'f'*32
    if kind=='engine_execution':ex=loads_json(base64.b64decode(workspace['run']['metadata']['simulation_source']['raw_b64']).decode())['producer']['execution_id']
    if kind=='bad_id':ex='latest'
    if kind=='oversize':
        path=tmp_path/'big.json';path.write_bytes(b' '*(8*1024*1024+1));expected=sha256(path.read_bytes())
    with pytest.raises(ValueError):export_view(path,ex,expected_workspace_sha256=expected)


@pytest.mark.parametrize('field',['source_class','clock','covariance','truth','verification','held'])
def test_resealed_payload_inconsistency_refused(bundle,tmp_path,field):
    _,_,workspace,ex=case(bundle,'held');r=workspace['results'][-1]
    if field=='source_class':r['data']['source_class']='physical_measurement'
    if field=='clock':r['data']['data']['calibrated_observation']['t']=0.0
    if field=='covariance':r['data']['data']['estimate']['covariance'][0][1]+=1
    if field=='truth':r['data']['reference_truth_supplied']=True
    if field=='verification':r['verification_status']='verified'
    if field=='held':r['data']['data']['residuals']['correction']=[0,0]
    seal(r);path=tmp_path/'bad.json';path.write_text(json.dumps(workspace))
    with pytest.raises(ValueError):export_view(path,ex,expected_workspace_sha256=sha256(path.read_bytes()))


def test_cli_matches_api_and_is_create_only(bundle,tmp_path):
    path,item,_,ex=case(bundle);dest=tmp_path/'view.json'
    cmd=[sys.executable,'-m','ciw.simulated_fsrt_view',str(path),'--execution',ex,
         '--expect-workspace-sha256',item['workspace_sha256'],'--output',str(dest)]
    done=subprocess.run(cmd,capture_output=True,text=True,timeout=30)
    assert done.returncode==0,done.stderr
    result=json.loads(done.stdout)
    assert result['source_class']=='simulated_observation'
    assert result['view_sha256']==export_view(path,ex,expected_workspace_sha256=item['workspace_sha256'])['sha256']
    before=dest.read_bytes()
    assert subprocess.run(cmd,capture_output=True,timeout=30).returncode==2
    assert dest.read_bytes()==before


def test_emit_exact_views_for_gsc(bundle):
    out=Path(os.environ['CIW_SYNTHETIC_VIEW_OUT']);out.mkdir(parents=True,exist_ok=False)
    manifest={}
    for name in bundle[1]:
        path,item,_,ex=case(bundle,name)
        view=export_view(path,ex,expected_workspace_sha256=item['workspace_sha256'])
        file=out/(name+'.view.json');write_view(view,file)
        manifest[name]={'view':file.name,'file_sha256':sha256(file.read_bytes()),
                        'view_sha256':view['sha256'],'workspace_sha256':item['workspace_sha256'],
                        'source_sha256':item['source_sha256'],'execution_id':ex}
    (out/'index.json').write_text(json.dumps(manifest,indent=2)+'\n')
