"""Closed asset profile and packet boundaries. Synthetic meshes here are TEST DOUBLES.

Actual Blender/Godot qualification is in scripts/check_foundry_asset.py. These
helpers do not establish that a native tool ran or that a human reviewed artwork.
"""
from copy import deepcopy
import base64
import json
from pathlib import Path
import struct
from unittest.mock import patch

import pytest
from ciw import foundry_asset_contract as c, foundry_asset_worker as w
from ciw import foundry_packets as packets, foundry_pipeline as pipeline
from ciw.control_contracts import bytes_ref, save_new, load
from ciw.operations.runner import seal
from ciw.production import preflight, run_production, inspect_production
from ciw.foundry_asset_cli import main
from ciw.foundry_workflow import main as foundry_main


def pack(d, binary):
    j=json.dumps(d,separators=(',',':'),allow_nan=False).encode();j+=b' '*((-len(j))%4)
    binary+=b'\0'*((-len(binary))%4)
    return struct.pack('<4sII',b'glTF',2,28+len(j)+len(binary))+struct.pack('<II',len(j),0x4e4f534a)+j+struct.pack('<II',len(binary),0x004e4942)+binary


def unpack(raw):
    n=struct.unpack_from('<I',raw,12)[0];d=json.loads(raw[20:20+n]);return d,raw[28+n:]


def mesh_fixture(legs=4):
    """Independent TEST fixture encoding six quad faces, not executing Blender."""
    d={'asset':{'version':'2.0','generator':'explicit unit-test fixture'},'scene':0,
       'scenes':[{'nodes':[]}],'nodes':[],'meshes':[],'accessors':[],'bufferViews':[],
       'buffers':[],'materials':[{'pbrMetallicRoughness':{'metallicFactor':0,'roughnessFactor':.82}}]}
    data=bytearray()
    def accessor(values,typ,fmt):
        data.extend(b'\0'*((-len(data))%4));start=len(data)
        for row in values:data.extend(struct.pack('<'+fmt*len(row),*row))
        v={'buffer':0,'byteOffset':start,'byteLength':len(data)-start,'target':34962 if typ=='VEC3' else 34963}
        d['bufferViews'].append(v)
        a={'bufferView':len(d['bufferViews'])-1,'componentType':5126 if fmt=='f' else 5123,'count':len(values),'type':typ}
        a['min']=[min(x[i] for x in values) for i in range(len(values[0]))];a['max']=[max(x[i] for x in values) for i in range(len(values[0]))]
        d['accessors'].append(a);return len(d['accessors'])-1
    for name,(lo,hi) in c.expected_bounds().items():
        if name=='leg_3' and legs==3:continue
        positions=[];normals=[];indices=[]
        for axis in range(3):
            other=[j for j in range(3) if j!=axis]
            for side in (0,1):
                face=[]
                for i,j in [(0,0),(1,0),(1,1),(0,1)]:
                    point=[0,0,0];point[axis]=(lo,hi)[side][axis]
                    point[other[0]]=(lo,hi)[i][other[0]];point[other[1]]=(lo,hi)[j][other[1]];face.append(point)
                u=[face[1][i]-face[0][i] for i in range(3)];v=[face[2][i]-face[0][i] for i in range(3)]
                cross=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
                if cross[axis]*(1 if side else -1)<0:face.reverse()
                start=len(positions);positions.extend(face)
                normal=[0,0,0];normal[axis]=1 if side else -1;normals.extend([normal]*4)
                indices.extend((start+i,) for i in [0,1,2,0,2,3])
        p=accessor(positions,'VEC3','f');n=accessor(normals,'VEC3','f');idx=accessor(indices,'SCALAR','H')
        d['meshes'].append({'primitives':[{'attributes':{'POSITION':p,'NORMAL':n},'indices':idx,'material':0}]})
        d['nodes'].append({'name':name,'mesh':len(d['meshes'])-1});d['scenes'][0]['nodes'].append(len(d['nodes'])-1)
    d['buffers']=[{'byteLength':len(data)}];return pack(d,bytes(data))


def import_fixture(raw,request):
    p=c.observe_glb(raw)['parts']
    probes=[([0,1.5,0],[0,.5,0],'top',[0,.9,0]),
            ([-.76,.1,-1],[-.76,.1,0],'leg_0',[-.76,.1,-.29]),
            ([.76,.1,-1],[.76,.1,0],'leg_1',[.76,.1,-.29]),
            ([-.76,.1,1],[-.76,.1,0],'leg_2',[-.76,.1,.29]),
            ([.76,.1,1],[.76,.1,0],'leg_3',[.76,.1,.29]),([2,1.5,0],[2,-.2,0],None,None)]
    return {'schema':'ciw.workbench-import.v1','engine_version':'4.5.1-stable (official)','asset_sha256':bytes_ref(raw),
        'request':request,'parts':p,'rays':[{'from':a,'to':b,'name':n if n in p else None,
            'hit':n in p,'position':v if n in p else None} for a,b,n,v in probes]}


@pytest.fixture
def case(tmp_path):
    root=tmp_path/'source';root.mkdir();(root/'brief.md').write_text('TEST FIXTURE original workbench brief, not historical evidence.')
    project=pipeline.create_project('asset-fixture',root,tmp_path/'project')
    artifact=tmp_path/'artifacts';artifact.mkdir();(artifact/'decision.md').write_text('TEST FIXTURE ONLY: no human review occurred.')
    evidence={}
    for task in ['vision','historical-scope']:
        out=tmp_path/task
        pipeline.review_task(project,task,root,artifact,out,producer='TEST PRODUCER',reviewer='TEST REVIEWER',decision='approved',evidence=evidence)
        evidence[task]=out
    packet=packets.make_packet(project,pipeline.task_for(project,'art-target'),root,writable=[c.OUTPUT],context=['brief.md'],assignee='test-asset-host')
    return root,project,packet,evidence


def capture_fixture(case,legs=4):
    root,project,packet,_=case
    declared=w.assignment(project,packet,packet['record_digest']);params={'nonce':'1'*32,'legs':legs}
    request={'schema':'ciw.workbench-request.v1','packet_id':packet['record_digest'],**params}
    raw=mesh_fixture(legs);candidate=w.candidate_inventory(packet['baseline'],raw)
    scope=seal({'schema':'ciw.foundry-candidate-scope.v1','packet_digest':packet['record_digest'],
        'candidate_inventory_id':candidate['inventory_id'],'changes':[{'path':c.OUTPUT,'change':'added'}],
        'out_of_scope':[],'changed_bytes':len(raw),'status':'scope_passed','quality_acceptance':'not_performed','executed':False,'publication':'not_performed'})
    data={'schema':'ciw.workbench-capture.v1','request':request,'asset_b64':base64.b64encode(raw).decode(),'asset_sha256':bytes_ref(raw),
        'candidate_inventory':candidate,'scope_check':scope,'author_utf8':json.dumps({'schema':'ciw.workbench-author.v1','request':request,'blender_version':'4.5.3'}),
        'import_utf8':json.dumps(import_fixture(raw,request)),
        'logs':{k:{'utf8':'TEST DOUBLE','sha256':bytes_ref(b'TEST DOUBLE')} for k in ['blender.stdout','blender.stderr','godot.stdout','godot.stderr']},
        'elapsed_wall_s':0,'captured_native_calls':2}
    return data,declared,params


def test_fixture_geometry_is_not_native_evidence():
    raw=mesh_fixture();d=c.observe_glb(raw)
    assert len(d['parts'])==9 and d['triangles']==108
    assert c.semantic_checks(d,import_fixture(raw,{}),{})['status']=='PASS'
    assert c.semantic_checks(d,None,{})['status']=='INDETERMINATE'


def test_absent_leg_is_geometry_failure_not_weakened_contract():
    raw=mesh_fixture(3);d=c.observe_glb(raw)
    outcome=c.semantic_checks(d,import_fixture(raw,{}),{})
    assert outcome['status']=='FAIL'
    assert outcome['detail']['checks']['bounds:leg_3'] is False
    assert outcome['detail']['checks']['ray:4'] is False


@pytest.mark.parametrize('fault',['header','version','length','chunk','extra_chunk','truncate','external_buffer','image','animation','extension','matrix','rotation','scale','duplicate_name','extra_mesh','hidden_root','index_offset','index_count','index_bool','view_length','view_stride','index_stride','metadata','unused_accessor','nonfinite','bad_index','normal','degenerate','inward','double_sided','texture','duplicate_json'])
def test_profile_refuses_malformed_or_unsupported_data(fault):
    raw=mesh_fixture();d,binary=unpack(raw)
    if fault=='header':raw=b'WRNG'+raw[4:]
    elif fault=='version':raw=raw[:4]+struct.pack('<I',1)+raw[8:]
    elif fault=='length':raw=raw[:8]+struct.pack('<I',len(raw)+4)+raw[12:]
    elif fault=='chunk':raw=raw[:12]+struct.pack('<I',3)+raw[16:]
    elif fault=='extra_chunk':raw=raw[:8]+struct.pack('<I',len(raw)+8)+raw[12:]+b'\0'*8
    elif fault=='truncate':raw=raw[:-1]
    elif fault=='external_buffer':d['buffers'][0]['uri']='https://untrusted.invalid/data.bin'
    elif fault=='image':d['images']=[{'uri':'../../elsewhere.png'}]
    elif fault=='animation':d['animations']=[]
    elif fault=='extension':d['extensionsUsed']=['untrusted']
    elif fault=='matrix':d['nodes'][0]['matrix']=[1]*16
    elif fault=='rotation':d['nodes'][0]['rotation']=[0,.2,0,1]
    elif fault=='scale':d['nodes'][0]['scale']=[2,2,2]
    elif fault=='duplicate_name':d['nodes'][1]['name']='top'
    elif fault=='extra_mesh':d['meshes'].append(deepcopy(d['meshes'][0]))
    elif fault=='hidden_root':d['scenes'][0]['nodes'].pop()
    elif fault=='index_offset':d['accessors'][2]['byteOffset']=99999
    elif fault=='index_count':d['accessors'][2]['count']=999999
    elif fault=='index_bool':d['nodes'][0]['mesh']=True
    elif fault=='view_length':d['bufferViews'][0]['byteLength']=len(binary)+10
    elif fault=='view_stride':d['bufferViews'][0]['byteStride']=11
    elif fault=='index_stride':d['bufferViews'][2]['byteStride']=4
    elif fault=='metadata':d['accessors'][0]['max']=[99,99,99]
    elif fault=='unused_accessor':d['accessors'].append(deepcopy(d['accessors'][0]))
    elif fault=='nonfinite':binary=struct.pack('<f',float('nan'))+binary[4:]
    elif fault=='bad_index':
        start=d['bufferViews'][2]['byteOffset'];binary=binary[:start]+struct.pack('<H',9999)+binary[start+2:]
    elif fault=='normal':
        start=d['bufferViews'][1]['byteOffset'];binary=binary[:start]+struct.pack('<3f',0,0,0)+binary[start+12:]
    elif fault=='degenerate':
        start=d['bufferViews'][2]['byteOffset'];binary=binary[:start]+struct.pack('<3H',0,0,0)+binary[start+6:]
    elif fault=='inward':
        start=d['bufferViews'][2]['byteOffset'];binary=binary[:start]+struct.pack('<3H',0,2,1)+binary[start+6:]
    elif fault=='double_sided':d['materials'][0]['doubleSided']=True
    elif fault=='texture':d['materials'][0]['pbrMetallicRoughness']['baseColorTexture']={'index':0}
    elif fault=='duplicate_json':
        n=struct.unpack_from('<I',raw,12)[0];j=raw[20:20+n].rstrip(b' ');j=j[:-1]+b',"scene":0}';j+=b' '*((-len(j))%4)
        raw=struct.pack('<4sII',b'glTF',2,28+len(j)+len(binary))+struct.pack('<II',len(j),0x4e4f534a)+j+struct.pack('<II',len(binary),0x004e4942)+binary
    if fault not in {'header','version','length','chunk','extra_chunk','truncate','duplicate_json'}:raw=pack(d,binary)
    with pytest.raises((ValueError,KeyError,struct.error)):c.observe_glb(raw)


@pytest.mark.parametrize('fault',['import_hash','request','version','wrong_bound','missing_mesh','wrong_ray','ray_origin'])
def test_second_engine_observations_must_match_actual_geometry(fault):
    raw=mesh_fixture();report=import_fixture(raw,{})
    if fault=='import_hash':report['asset_sha256']='sha256:'+'0'*64
    if fault=='request':report['request']={'other':True}
    if fault=='version':report['engine_version']='4.6.0.unknown'
    if fault=='wrong_bound':report['parts']['top']['min'][0]=-9
    if fault=='missing_mesh':del report['parts']['leg_0']
    if fault=='wrong_ray':report['rays'][0]['name']='rail_back'
    if fault=='ray_origin':report['rays'][0]['from'][0]=100
    try:outcome=c.semantic_checks(c.observe_glb(raw),report,{})
    except ValueError:return
    assert outcome['status']=='FAIL'


def test_capture_is_custody_not_worker_pass(case):
    data,declared,params=capture_fixture(case)
    w.capture(data,declared,params)
    assert w.evaluate({'operation_id':w.OP,'data':data},c.POLICY)['status']=='PASS'
    data['PASS']=True
    with pytest.raises(ValueError):w.capture(data,declared,params)


@pytest.mark.parametrize('fault',['packet','scope','asset','inventory','log','producer','call_count','missing_field','unauthorized_key'])
def test_capture_rejects_identity_permission_and_artifact_substitution(case,fault):
    d,declared,params=capture_fixture(case)
    if fault=='packet':d['request']['packet_id']='sha256:'+'0'*64
    if fault=='scope':d['scope_check']['quality_acceptance']='approved'
    if fault=='asset':d['asset_sha256']='sha256:'+'0'*64
    if fault=='inventory':d['candidate_inventory']['files']['brief.md']['bytes']+=1
    if fault=='log':d['logs']['blender.stdout']['utf8']='altered'
    if fault=='producer':
        a=json.loads(d['author_utf8']);a['request']['legs']=3;d['author_utf8']=json.dumps(a)
    if fault=='call_count':d['captured_native_calls']=True
    if fault=='missing_field':del d['author_utf8']
    if fault=='unauthorized_key':d['executable']='somewhere'
    with pytest.raises(ValueError):w.capture(d,declared,params)


def test_packet_and_policy_cannot_be_replaced(case):
    _,p,packet,_=case
    with pytest.raises(ValueError):w.assignment(p,packet,'sha256:'+'0'*64)
    bad=deepcopy(packet);bad['rights']['execute']=True;bad.pop('record_digest');bad=seal(bad)
    with pytest.raises(ValueError):w.assignment(p,bad,bad['record_digest'])
    policy=deepcopy(c.POLICY);policy['expected_parts']=8
    with pytest.raises(ValueError):w.policy(policy)
    with pytest.raises(ValueError):w.parameters({'nonce':'1'*32,'legs':True})
    with pytest.raises(ValueError):w.parameters({'nonce':'1'*32,'legs':4,'script':'anything'})


def test_actual_run_rechecks_prerequisites_before_runtime(case,tmp_path):
    root,project,packet,evidence=case
    with patch.object(w,'AssetBinding',side_effect=AssertionError('must not bind')):
        with pytest.raises(ValueError,match='prerequisites'):
            w.run_asset(project,packet,root,Path('none'),Path('none'),tmp_path/'blocked',packet_id=packet['record_digest'],blender_sha256='sha256:'+'0'*64,godot_sha256='sha256:'+'0'*64)
    assert not (tmp_path/'blocked').exists()
    assert pipeline.assess(project,root,evidence)['tasks']['art-target']['status']=='awaiting_review'


def test_compilation_uses_original_controller_fixed_gates_and_bounded_repairs(case):
    _,project,packet,_=case
    source=w.source(project,packet)
    plan=w.compile_plan(source,legs=3,repair=True)
    assert len(plan['jobs'][0]['attempts'])==2
    assert plan['jobs'][1]['depends_on']==['workbench']
    assert plan['jobs'][0]['checks']==plan['jobs'][1]['checks']
    assert w.objective(source)['packet']['rights']['execute'] is False
    with pytest.raises(ValueError):w.compile_plan(source,repair=1)


def test_inspect_and_export_missing_results_do_not_launch_engines(tmp_path):
    directory=tmp_path/'empty';directory.mkdir()
    with patch('subprocess.Popen',side_effect=AssertionError('offline engine launch')):
        with pytest.raises(ValueError):w.inspect_asset(directory)


def test_cli_errors_are_refusals_not_tracebacks(case,tmp_path,capsys):
    _,project,packet,_=case
    assert foundry_main(['asset','inspect',str(tmp_path/'not-a-run')])==1
    assert json.loads(capsys.readouterr().err)['status']=='refused'
    project_path=tmp_path/'project/project.json';packet_path=tmp_path/'packet.json';save_new(packet_path,packet)
    assert main(['run',str(project_path),'--packet',str(packet_path),'--packet-id',packet['record_digest'],
        '--source-root',str(case[0]),'--blender','missing','--blender-sha256','sha256:'+'0'*64,
        '--godot','missing','--godot-sha256','sha256:'+'0'*64,'--output-dir',str(tmp_path/'run')])==1
    assert 'prerequisites' in json.loads(capsys.readouterr().err)['reason']


def test_unchanged_template_and_offline_parent_still_needs_review(case):
    root,project,packet,evidence=case
    with patch('subprocess.Popen',side_effect=AssertionError('provider launched')):
        report=pipeline.assess(project,root,evidence)
    assert len(project['tasks'])==60
    assert sum(t['installed_recipe'] is not None for t in project['tasks'])==1
    assert report['tasks']['art-target']['status']=='awaiting_review'
    assert report['release_authorized'] is False


def test_missing_observations_hold_without_issuing_pass(case):
    data,declared,params=capture_fixture(case);data['import_utf8']=None
    w.capture(data,declared,params)
    assert w.evaluate({'operation_id':w.OP,'data':data},c.POLICY)['status']=='INDETERMINATE'


def test_explicit_source_snapshot_drift_is_not_rebased(case):
    root,p,packet,_=case
    before=deepcopy(packet)
    (root/'brief.md').write_text('changed after operator issue')
    with pytest.raises(ValueError,match='Source drift'):w.read_snapshot(root,packet['baseline'])
    assert packet==before


def test_real_production_session_integration_with_explicit_test_double(case,tmp_path):
    class SyntheticBinding:
        def runtime_identity(self):return {'provider':'explicit-unit-test-double-NOT-Blender'}
        def invoke(self,declared,params):
            data,expected,_=capture_fixture(case,params['legs'])
            assert declared==expected
            data['request']['nonce']=params['nonce']
            for key in ('author_utf8','import_utf8'):
                report=json.loads(data[key]);report['request']=data['request'];data[key]=json.dumps(report)
            return data
    reg=w.registry(SyntheticBinding());source=w.source(case[1],case[2]);plan=w.compile_plan(source,legs=3,repair=True)
    out=tmp_path/'production'
    with pytest.raises(ValueError):preflight(plan,reg,w.WORKERS,w.gates(),max_operations=1)
    report=run_production(source,plan,reg,w.WORKERS,w.gates(),out,max_operations=3)
    assert report['attempt_count']==3 and report['status']=='completed'
    original={p:p.read_bytes() for p in out.rglob('*') if p.is_file()}
    with patch('subprocess.Popen',side_effect=AssertionError('offline call')):
        assert inspect_production(out,w.gates())['status']=='completed'
        with pytest.raises(ValueError,match='explicitly bound'):w.inspect_asset(out)
    assert all(p.read_bytes()==raw for p,raw in original.items())


def test_only_prescribed_asset_path_and_tasks_can_select_worker(case):
    root,p,packet,_=case
    for task,path in [('vision',c.OUTPUT),('art-target','assets/another.glb')]:
        value=packets.make_packet(p,pipeline.task_for(p,task),root,writable=[path],context=[],assignee='fixture')
        with pytest.raises(ValueError):w.assignment(p,value,value['record_digest'])
