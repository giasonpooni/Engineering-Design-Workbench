"""Host contracts around a retained synthetic specimen; not per-test GDAL runs.

Actual GSC subprocess/COG execution is exercised by check_rs_pipeline.py.
"""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ciw.adapters.protocol import AdapterRefusal
from ciw.control_contracts import load
from ciw.control_plane import builtin_registry, run_graph
from ciw.control_checks import compare
from ciw.instruments import make_demo_run
from ciw.operations.runner import seal,digest
from ciw.session import Session
from ciw.rs_operations import (RasterBinding,OPERATIONS,add_rs_routes,make_plan,mean_observations,
                               open_workspace,validate_request,validate_result)


@pytest.fixture
def specimen():
    return load(Path(__file__).with_name('fixtures')/'rs/contract-result.json')


def parameters(r):
    return {'bundle_ref':r['bundle_sha256'],'request':{'investigation_id':'synthetic-yard-cover','room':'LANDSHARK',
        'entity':{'kind':'site','id':'synthetic-site'},'aoi_ref':r['selection']['aoi_ref'],'window':[0,0,4,4],'quality':'declared_mask'}}


class AdapterDouble:
    def __init__(self,r):self.r=r;self.calls=[]
    def runtime_identity(self):return {'test_double':True}
    def invoke(self,op,inputs):
        self.calls.append((op,deepcopy(inputs)))
        r=deepcopy(self.r);r['request_ref']=digest(inputs['request']);r['operation_id']=op
        if op=='rs.scene.inspect.v1':r['index']=None
        return r


def lab(tmp_path,r):
    b=RasterBinding.__new__(RasterBinding);b._bundle='/operator/scene.json';b.bundle_ref=r['bundle_sha256']
    b.adapter=AdapterDouble(r);b._specialist=r['runtime']
    reg=builtin_registry();add_rs_routes(reg,binding=b)
    return Session(make_demo_run(),tmp_path/'session',operations=reg.operations),reg,b


def execute(session,reg,r,op='rs.index.ndvi.v1'):
    outcome=run_graph(session,make_plan(op,parameters(r)),reg)
    assert outcome['status']=='completed',session.executions
    return list(session.results.values())[-1]


def test_unbound_routes_are_optional_and_keep_prior_catalog():
    reg=builtin_registry();before=reg.catalog();add_rs_routes(reg)
    after=reg.catalog();assert all(after['operations'][k]==v for k,v in before['operations'].items())
    assert all(not after['operations'][k]['bound'] for k in OPERATIONS)
    assert 'rs.scene.admit.v1' not in after['operations']


def test_unbound_execution_is_retained_refusal(tmp_path,specimen):
    reg=builtin_registry();add_rs_routes(reg);s=Session(make_demo_run(),tmp_path,operations=reg.operations)
    response=s.handle({'protocol_version':1,'request_id':'unbound','type':'operation.execute',
        'payload':{'operation_id':'rs.index.ndvi.v1','parameters':parameters(specimen)}})
    assert response['payload']['status']=='refused' and not s.results and len(s.executions)==1


def test_actual_registry_session_contract_and_host_recording_not_forwarded(tmp_path,specimen):
    s,reg,b=lab(tmp_path,specimen);old=deepcopy(s.run);r=execute(s,reg,specimen)
    assert s.run==old and len(b.adapter.calls)==1
    sent=b.adapter.calls[0][1];assert set(sent)=={'bundle_path','bundle_sha256','request'}
    assert 'channels' not in sent and r['data']['specialist_result']['index']['valid_count']==13
    assert r['execution_id']!=r['data']['specialist_result']['provider_execution_id']
    assert r['data']['state_admission_by_net'] is False


def test_inspect_contract_no_ndvi(tmp_path,specimen):
    s,reg,_=lab(tmp_path,specimen);r=execute(s,reg,specimen,'rs.scene.inspect.v1')
    assert r['data']['specialist_result']['index'] is None
    with pytest.raises(ValueError):mean_observations(r)


def test_mean_projection_uses_original_execution_and_acquisition_not_known_at(tmp_path,specimen):
    s,reg,_=lab(tmp_path,specimen);r=execute(s,reg,specimen);sample=mean_observations(r)['observations'][0]
    assert sample['identity']['execution_id']==r['execution_id'] and sample['value']==pytest.approx(6/13)
    assert sample['provenance']['semantics']=='simulated' and sample['unit']=='1'
    from datetime import datetime
    assert sample['clock']['time_s']==datetime.fromisoformat('2026-09-26T12:00:00+00:00').timestamp()


def test_no_data_mean_remains_missing(tmp_path,specimen):
    ix=specimen['index'];ix.update(values=[None]*16,valid_count=0,status='insufficient_data',mean=None,minimum=None,maximum=None)
    ix['excluded_counts'].update(nodata=16,quality_mask=0,zero_denominator=0)
    s,reg,_=lab(tmp_path,specimen);r=execute(s,reg,specimen);samples=mean_observations(r)['observations']
    assert samples[0]['value'] is None and compare(samples,samples,atol=0,rtol=0)['outcome']['status']=='INDETERMINATE'


def test_existing_comparator_reproduction_and_changed_support(tmp_path,specimen):
    s,reg,b=lab(tmp_path,specimen);a=execute(s,reg,specimen);c=execute(s,reg,specimen)
    assert a['execution_id']!=c['execution_id']
    left=mean_observations(a)['observations'];right=mean_observations(c)['observations']
    assert compare(left,right,atol=0,rtol=0)['outcome']['status']=='PASS'
    ix=b.adapter.r['index'];ix['values'][0]=None;ix['valid_count']-=1;ix['excluded_counts']['nodata']+=1
    d=execute(s,reg,specimen)
    assert compare(left,mean_observations(d)['observations'],atol=0,rtol=0)['outcome']['status']=='INDETERMINATE'


@pytest.mark.parametrize('change',[lambda p:p.update(executable='/bin/sh'),lambda p:p['request'].update(pixels=[1]),
    lambda p:p['request']['entity'].update(kind='person'),lambda p:p['request'].update(window=[0,0,100,100]),
    lambda p:p['request'].update(window=[0,False,4,4]),lambda p:p['request'].update(quality='automatic-cloud'),
    lambda p:p['request'].update(room='Satellite'),lambda p:p.update(bundle_ref='file:///x')])
def test_bad_request_metadata(change,specimen):
    p=parameters(specimen);change(p)
    with pytest.raises(ValueError):validate_request('rs.index.ndvi.v1',p)


@pytest.mark.parametrize('change',[lambda r:r['data'].update(state_admission_by_net=True),
    lambda r:r['data']['specialist_result'].update(state_admission='admitted'),
    lambda r:r['data']['specialist_result'].update(bundle_sha256='sha256:'+'0'*64),
    lambda r:r['data']['specialist_result'].update(request_ref='sha256:'+'0'*64),
    lambda r:r['data']['specialist_result']['index'].update(clamped=True),
    lambda r:r['data']['specialist_result']['index'].update(valid_count=0),
    lambda r:r['data']['specialist_result']['index'].update(unit='m'),
    lambda r:r['data']['specialist_result']['index']['values'].__setitem__(0,True),
    lambda r:r['data']['specialist_result']['selection'].update(window=[0,0,2,2]),
    lambda r:r['runtime']['specialist'].update(gdal='different'),
    lambda r:r['data']['specialist_result']['source'].update(yield_class='person'),
    lambda r:r['data']['specialist_result']['scene'].update(cloud_cover_scope='local-cloud-fraction'),
    lambda r:r.update(verification_status='verified')])
def test_resealed_misbound_result_refuses(tmp_path,specimen,change):
    s,reg,_=lab(tmp_path,specimen);r=execute(s,reg,specimen);change(r);seal(r)
    with pytest.raises(ValueError):validate_result(r)


def test_reopen_without_provider_or_raster_library(tmp_path,specimen):
    s,reg,_=lab(tmp_path,specimen);r=execute(s,reg,specimen);path=tmp_path/'workspace.json';s.save_workspace(path)
    with patch('subprocess.Popen',side_effect=AssertionError('no process')),patch.object(RasterBinding,'__init__',side_effect=AssertionError('no binding')):
        loaded=open_workspace(path,output_dir=tmp_path/'reader')
    assert loaded.results[r['result_id']]==r


def test_binding_source_cannot_be_changed_by_parameters(tmp_path,specimen):
    s,reg,b=lab(tmp_path,specimen);p=parameters(specimen);p['bundle_ref']='sha256:'+'0'*64
    with pytest.raises(ValueError):b.execute('rs.index.ndvi.v1',s.run,p)
    assert b.adapter.calls==[]


def test_interval_scene_does_not_invent_acquisition_instant(tmp_path,specimen):
    specimen['scene']['valid_time']['end']='2026-09-27T12:00:00Z'
    s,reg,_=lab(tmp_path,specimen);r=execute(s,reg,specimen)
    with pytest.raises(ValueError,match='interval'):mean_observations(r)


def test_cli_catalog_and_offline_inspect(tmp_path,specimen,capsys):
    from ciw.net import main
    assert main(['spatial','catalog'])==0
    assert 'rs.index.ndvi.v1' in capsys.readouterr().out
    s,reg,_=lab(tmp_path,specimen);r=execute(s,reg,specimen);path=tmp_path/'workspace.json';s.save_workspace(path)
    with patch('subprocess.Popen',side_effect=AssertionError('no process')):
        assert main(['spatial','raster','inspect',str(path)])==0
        assert main(['spatial','raster','observations',str(path),'--result-id',r['result_id'],'--output',str(tmp_path/'obs.json')])==0
    assert load(tmp_path/'obs.json')['observations'][0]['value']==pytest.approx(6/13)


def test_duplicate_registration_preserves_registry():
    reg=builtin_registry();add_rs_routes(reg);before=reg.catalog()
    with pytest.raises(ValueError):add_rs_routes(reg)
    assert reg.catalog()==before
