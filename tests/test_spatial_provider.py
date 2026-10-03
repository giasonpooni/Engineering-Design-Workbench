"""NET contracts plus opt-in, actual external GSC/PROJ integration."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
import pytest
from ciw.core.identities import evidence_id
from ciw.operations.registry import Operation, default_registry
from ciw.operations.runner import seal
from ciw.session import Session, envelope
from ciw import spatial_records as records
from ciw import spatial_scene as scene
from ciw import spatial_workflow as workflow


def fixture_data(run, parameters):
    """Shape fixture only. Values are not a PROJ execution or accuracy evidence."""
    inputs, indices=records.request(run,parameters)
    points=[None if p is None else [float(i),float(i),0.] for i,p in zip(indices,inputs['samples'])]
    return {"schema":records.SCHEMA,"origin":inputs["origin"],"positions_enu_m":points,
        "axes":["east","north","up"],"unit":"m","height_reference":"WGS84_ellipsoidal",
        "runtime":{"worker_version":"1","pyproj":"3.7.2","proj":"9.5.1","pipeline":records.pipeline(inputs['origin']),"network_enabled":False},
        "uncertainty":{"status":"unavailable","reason":"not_propagated"},"authority":"representation_only",
        "source_evidence_id":run["evidence_id"],"sample_indices":indices,"time_s":[run["time_s"][i] for i in indices],
        "entity_id":run["metadata"]["spatial"]["entity_id"],"frame_id":"local-enu:"+records.content_identity(inputs["origin"])}


def fixture_session(tmp_path):
    run,origin=records.demo_run();registry=default_registry()
    registry.register(Operation(records.OPERATION,"backend",fixture_data,lambda:{"provider":"test_shape_fixture_not_native"}))
    s=Session(run,tmp_path/"session",operations=registry)
    params={"origin":origin,"channel":s.selection['channel'],"interval_s":s.selection['interval_s']}
    value=s.handle(envelope("operation.execute",{"operation_id":records.OPERATION,"parameters":params},uuid.uuid4().hex))['payload']
    assert value['status']=='completed'
    p=tmp_path/"session/workspace.json";s.save_workspace(p)
    return s,p,value['result']


def test_source_reads_without_geospatial_runtime(tmp_path,monkeypatch):
    run,_=records.demo_run();monkeypatch.setitem(sys.modules,"pyproj",None)
    s=Session(run,tmp_path/"source");p=tmp_path/"workspace.json";s.save_workspace(p)
    restored=Session.from_workspace(p,tmp_path/"restored")
    assert restored.run==run


def test_real_session_operation_identity_and_offline_restore(tmp_path,monkeypatch):
    s,p,result=fixture_session(tmp_path)
    monkeypatch.setattr('ciw.operations.registry.OperationRegistry.get',lambda *a:pytest.fail('reader executed'))
    monkeypatch.setitem(sys.modules,'pyproj',None)
    restored=Session.from_workspace(p,tmp_path/"read")
    assert restored.results[result['result_id']]==result
    assert result['execution_id']!=result['result_id']!=result['evidence_id']
    assert result['verification_id'] is None and result['verification_status']=='not_verified'
    assert restored.executions[result['execution_id']]['status']=='completed'
    assert workflow.inspect(p)['provider_execution']=='not_performed'


@pytest.mark.parametrize('field,value',[('authority','admitted'),('unit','cm'),('axes',['east','up','north']),
 ('source_evidence_id','sha256:wrong'),('sample_indices',[0,1,2,4,3,5]),('time_s',[0,1,2,3,4,8]),
 ('uncertainty',{'status':'available'}),('entity_id','other'),('frame_id','other')])
def test_resealed_semantic_tampering_is_rejected(tmp_path,field,value):
    _,p,_=fixture_session(tmp_path);raw=json.loads(p.read_bytes())
    raw['results'][0]['data'][field]=value;seal(raw['results'][0]);p.write_text(json.dumps(raw))
    with pytest.raises(ValueError):workflow.inspect(p)


@pytest.mark.parametrize('point',[[0,0,0],[float('inf'),0,0],[True,0,0]])
def test_missing_sample_cannot_be_filled(tmp_path,point):
    _,p,_=fixture_session(tmp_path);raw=json.loads(p.read_bytes())
    raw['results'][0]['data']['positions_enu_m'][3]=point
    if all(not isinstance(v,float) or v!=float('inf') for v in point):seal(raw['results'][0])
    p.write_text(json.dumps(raw))
    with pytest.raises(ValueError):workflow.inspect(p)


@pytest.mark.parametrize('value',[[181,0,0],[0,91,0],[0,0,-1001],[True,0,0],[0,0],[float('nan'),0,0]])
def test_invalid_origin_refuses_before_worker(value):
    run,origin=records.demo_run()
    with pytest.raises(ValueError):records.request(run,{'origin':value,'channel':'longitude','interval_s':[0.,6.]})


def test_selection_stays_half_open_and_missingness_preserved():
    run,origin=records.demo_run()
    inputs,indices=records.request(run,{'origin':origin,'channel':'longitude','interval_s':[1.,4.]})
    assert indices==[1,2,3] and inputs['samples'][-1] is None


def test_catalog_is_detached_and_provider_free(monkeypatch):
    monkeypatch.setitem(sys.modules,'pyproj',None);monkeypatch.setitem(sys.modules,'pxr',None)
    from ciw.provider_catalog import catalog
    a=catalog();ids=[p['provider_id'] for p in a['providers']]
    assert len(ids)==len(set(ids))
    assert all(not p['authorizes_execution'] for p in a['providers'])
    a['providers'][0]['provider_id']='mutated'
    assert catalog()['providers'][0]['provider_id']=='gsc.local-frame'


def test_scene_source_binding_static_html_and_no_source_mutation(tmp_path,monkeypatch):
    _,p,result=fixture_session(tmp_path);before=p.read_bytes()
    monkeypatch.setitem(sys.modules,'pxr',None)
    out=tmp_path/'export';report=scene.export(p,result['result_id'],out)
    assert report['usd']=={'status':'not_requested'}
    v=json.loads((out/'scene-binding.json').read_bytes())
    assert v['entity_id']=='demo:survey-probe' and v['runtime_entity_id'] is None
    assert v['prim_path']!=v['entity_id'] and v['up_axis']=='Z'
    assert v['positions_enu_m'][3] is None and v['interpolation']=='none'
    text=(out/'inspector.html').read_text()
    assert '<script' not in text and 'unavailable' in text and text.count('<circle')==5
    assert 'http://' not in text and 'https://' not in text
    assert p.read_bytes()==before
    checked=scene.verify_export(out);assert checked['usd_sdk']=='not_invoked'


def test_export_is_create_only(tmp_path):
    _,p,r=fixture_session(tmp_path);out=tmp_path/'export';scene.export(p,r['result_id'],out)
    before={f.name:f.read_bytes() for f in out.iterdir()}
    with pytest.raises(FileExistsError):scene.export(p,r['result_id'],out)
    assert {f.name:f.read_bytes() for f in out.iterdir()}==before


def test_missing_usd_sdk_no_fake_fallback_or_publication(tmp_path,monkeypatch):
    _,p,r=fixture_session(tmp_path);out=tmp_path/'export';monkeypatch.setitem(sys.modules,'pxr',None)
    with pytest.raises(RuntimeError,match='OpenUSD is unavailable'):scene.export(p,r['result_id'],out,with_usd=True)
    assert not out.exists()


def test_unknown_result_rejected_before_sdk(tmp_path,monkeypatch):
    _,p,_=fixture_session(tmp_path);monkeypatch.setattr(scene,'_sdk',lambda:pytest.fail('loaded SDK'))
    with pytest.raises(ValueError):scene.export(p,'unknown',tmp_path/'export',with_usd=True)


@pytest.mark.parametrize('name',['scene-binding.json','inspector.html','workspace.json'])
def test_export_tampering_rejected(tmp_path,name):
    _,p,r=fixture_session(tmp_path);out=tmp_path/'export';scene.export(p,r['result_id'],out)
    f=out/name;f.write_bytes(f.read_bytes()+b' ')
    with pytest.raises(ValueError):scene.verify_export(out)


def test_resealed_export_authority_cannot_promote(tmp_path):
    _,p,r=fixture_session(tmp_path);out=tmp_path/'export';scene.export(p,r['result_id'],out)
    f=out/'export.json';v=json.loads(f.read_bytes());v['authority']['state_admission']='passed';seal(v);f.write_text(json.dumps(v))
    with pytest.raises(ValueError):scene.verify_export(out)


def test_resealed_binding_semantics_still_checked(tmp_path):
    _,p,r=fixture_session(tmp_path);out=tmp_path/'export';scene.export(p,r['result_id'],out)
    f=out/'scene-binding.json';v=json.loads(f.read_bytes());v['positions_enu_m'][0][0]+=5;f.write_text(json.dumps(v))
    m=out/'export.json';report=json.loads(m.read_bytes());report['artifacts'][f.name]='sha256:'+sha256(f.read_bytes()).hexdigest();seal(report);m.write_text(json.dumps(report))
    with pytest.raises(ValueError):scene.verify_export(out)


def test_duplicate_json_and_byte_limits(tmp_path,monkeypatch):
    p=tmp_path/'bad.json';p.write_text('{"workspace_version":1,"workspace_version":2}')
    with pytest.raises(ValueError):workflow.inspect(p)
    monkeypatch.setattr(scene,'MAX_BYTES',8)
    with pytest.raises(ValueError,match='byte limit'):scene.read_bounded(p)


def test_symlink_refused(tmp_path):
    p=tmp_path/'file';p.write_text('{}');s=tmp_path/'link'
    try:s.symlink_to(p)
    except OSError:pytest.skip('symlink unavailable')
    with pytest.raises(ValueError):scene.read_bounded(s)


@pytest.fixture
def actual_gsc():
    root=os.environ.get('GSC_LOCAL_FRAME_ROOT')
    if not root:pytest.skip('Provide GSC_LOCAL_FRAME_ROOT for native provider tests')
    root=Path(root);revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    return root,revision


def test_actual_native_workflow_and_replay(tmp_path,actual_gsc):
    root,rev=actual_gsc;run,origin=records.demo_run()
    a=workflow.create(run,origin,tmp_path/'a',gsc_root=root,revision=rev)
    b=workflow.create(run,origin,tmp_path/'b',gsc_root=root,revision=rev)
    assert a['status']==b['status']=='completed'
    assert a['result']['data']==b['result']['data']
    assert a['result']['execution_id']!=b['result']['execution_id']
    assert a['result']['evidence_id']==b['result']['evidence_id']
    assert a['result']['data']['positions_enu_m'][0]==[0.,0.,0.]
    assert a['result']['data']['positions_enu_m'][1][0]==pytest.approx(8.020934436998065,abs=1e-6)
    assert workflow.inspect(tmp_path/'a/workspace.json')['results'][0]==a['result']


def test_native_refusal_is_retained(tmp_path,actual_gsc):
    root,rev=actual_gsc;run,_=records.demo_run()
    result=workflow.create(run,[0.,0.,0.],tmp_path/'refusal',gsc_root=root,revision=rev)
    assert result['status']=='refused' and result['result'] is None
    v=workflow.inspect(tmp_path/'refusal/workspace.json')
    assert len(v['executions'])==1 and v['executions'][0]['status']=='refused'


def test_native_source_pin_mismatch_keeps_provisioning_refusal(tmp_path,actual_gsc):
    root,_=actual_gsc;run,origin=records.demo_run()
    with pytest.raises(ValueError):workflow.create(run,origin,tmp_path/'pin',gsc_root=root,revision='0'*40)
    assert (tmp_path/'pin/provisioning-refusal.json').exists()
    assert workflow.inspect(tmp_path/'pin/workspace.json')['executions']==[]


def test_actual_usd_sdk_roundtrip(tmp_path):
    pytest.importorskip('pxr.Usd',reason='Actual OpenUSD SDK required')
    _,p,r=fixture_session(tmp_path);out=tmp_path/'native-usd'
    report=scene.export(p,r['result_id'],out,with_usd=True)
    assert report['usd']['status']=='sdk_roundtrip_matched' and report['usd']['points_checked']==5
    assert (out/'scene.usda').read_text().startswith('#usda 1.0')
    assert scene.verify_export(out)['artifacts_checked']==4


def test_module_cli_catalog_without_provider(capsys, monkeypatch):
    monkeypatch.setitem(sys.modules, "pyproj", None)
    assert workflow.main(["catalog"]) == 0
    report=json.loads(capsys.readouterr().out)
    assert report["authorizes_execution"] is False


def test_module_cli_refusal_is_json(tmp_path,capsys):
    assert workflow.main(["inspect",str(tmp_path/"missing.json")]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "refused"
