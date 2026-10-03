"""Title recipe boundary tests. Captures are labelled fixtures, NOT native evidence."""
from copy import deepcopy
import json
from pathlib import Path
import struct
from unittest.mock import patch
import zlib

import pytest
from ciw.control_contracts import bytes_ref
from ciw.core.identities import content_identity
from ciw.foundry_packets import inventory
from ciw.workcell import WorkcellHost, inspect_attempt
from ciw.workcell_container import create_args, POLICY as CONTAINER_POLICY
from ciw.workcell_smith import SMITH, SOURCES, POLICY, checks, rule_checks, _summary
from ciw.workcell_recipe import installed
from ciw.workcell_title import configure, freeze
from ciw.workcell_pixels import decode,inspect as pixels_inspect
import base64

def asset(raw):
    return {'sha256':bytes_ref(raw),'bytes':len(raw),'base64_chunks':[base64.b64encode(raw[i:i+24000]).decode() for i in range(0,len(raw),24000)]}


def png(color=1,filter_type=0,rgba=False):
    def chunk(name,data):return struct.pack('>I',len(data))+name+data+struct.pack('>I',zlib.crc32(name+data)&0xffffffff)
    channels=4 if rgba else 3;previous=bytes(640*channels);data=[]
    for y in range(360):
        row=bytes(v for x in range(640) for v in (((x+color*32)%256,(y+color*16)%256,(x+y)%256)+((255,) if rgba else ())))
        filtered=[]
        for i,v in enumerate(row):
            a=row[i-channels] if i>=channels else 0;b=previous[i];c=previous[i-channels] if i>=channels else 0
            if filter_type==1:p=a
            elif filter_type==2:p=b
            elif filter_type==3:p=(a+b)//2
            elif filter_type==4:
                estimate=a+b-c;pa=abs(estimate-a);pb=abs(estimate-b);pc=abs(estimate-c)
                p=a if pa<=pb and pa<=pc else b if pb<=pc else c
            else:p=0
            filtered.append((v-p)&255)
        data.append(bytes([filter_type])+bytes(filtered));previous=row
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',640,360,8,6 if rgba else 2,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(data)))+chunk(b'IEND',b'')


DAY=png(1);EVENING=png(2)


def rules():
    return {'stages':[_summary(p) for p in ('fuel','working','ready','tools')]+[_summary('complete',tools=4,favor=53)],
            'errors':['']*5,'early_refused':True,'early_atomic':True,'roundtrip_equal':True,
            'duplicate_refused':True,'duplicate_atomic':True,'refund_errors':['',''],
            'refund':_summary('cancelled',treasury=120,timber=8)}


def pose():return {'tick':36,'phase':'working','arm_x':1.36,'coal':True,'finished':False,'carried':False}


class Fixture:
    def __init__(self):self.calls=[];self.fault=None
    def runtime_identity(self):return {'provider':'smith-test-fixture','execution_mode':'unit_test_double'}
    def invoke(self,stage,files,cid):
        self.calls.append(stage)
        inv={'nodes':100,'meshes':55,'triangles':12000,'collision_shapes':4,'materials':15,'workshop_extent':[6.,2.8,4.8],
             'colliders':[[-15.,.45,7.2,.68,.62,.64],[-15.,.88,7.2,1.05,.24,.44],[-17.25,.52,6.6,1.15,.76,1.1],[-14.9,1.08,9.3,2.,.14,.75]]}
        o={'schema':'1792.smith-workcell-observations.v1','mode':{'build':'build','test':'test','package':'smoke'}[stage],
           'engine':'unit-test-double','inventory':inv,'loaded_baked_scene':True}
        artifacts={}
        if stage=='build':
            artifacts={'smith.scn':asset(b'fixture-scene-not-native'*70)};o['compiled_scene_sha256']=artifacts['smith.scn']['sha256']
            if self.fault=='geometry':inv['workshop_extent'][0]=60.
            if self.fault=='budget':inv['triangles']=50001
        else:
            o.update(rules=rules(),scene_actions=['',''],pose=pose())
            if b'WRONG' in files['workshops/workshop_rules.gd']:o['rules']['stages'][-1]['tools']=5
            if stage=='test':
                artifacts={'daylight.png':asset(DAY),'evening.png':asset(EVENING)}
                o['captures']=[{'id':name,'pose':pose(),'width':640,'height':360,'image_sha256':artifacts[name+'.png']['sha256'],
                    'draw_calls':55,'render_primitives':12000,'video_adapter':'unit_test_double','renderer':'gl_compatibility',
                    'camera_transform':[1.,2.,3.,0.,.5,0.],'camera_kind':'fixed_asset_inspection_not_player_camera'} for name in ('daylight','evening')]
            else:artifacts={'smith.pck':asset(b'GDPC-fixture-not-native')};o['completion_phase']='ready'
        if self.fault=='missing' and stage=='test':o=None
        return {'schema':'ciw.workcell-capture.v1','stage':stage,'candidate_id':cid,'elapsed_wall_s':.1,
                'process':{'schema':'ciw.workcell-process.v1','stage':stage,'nonce':'fixture','outcome':'completed','diagnostic':'','logs':'unit_test_double','files':artifacts,'observations':o},
                'isolation':{'mode':'docker_container','image_id':'sha256:'+'a'*64,'container_id':'b'*64,'policy_sha256':content_identity(CONTAINER_POLICY),'checked_before_start':True,'cleanup_complete':True}}


@pytest.fixture
def cell(tmp_path):
    root=tmp_path/'source';root.mkdir()
    for name in SOURCES:
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('synthetic source fixture\n')
    backend=Fixture();host=WorkcellHost(root,tmp_path/'cell',backend,recipe=SMITH,expected_source_id=inventory(root)['inventory_id'])
    return host,backend,root


def test_existing_host_runs_title_recipe_and_exports_only_checked_artifacts(cell):
    host,backend,_=cell;c=host.submit('baseline',{});r=host.build('baseline',c['candidate'])
    assert r['status']=='completed' and r['execution_count']==3 and backend.calls==['build','test','package']
    assert set(r['exports'])=={'smith.pck','daylight.png','evening.png'} and r['art_review']=='not_performed'
    before={p:p.read_bytes() for p in host.root.rglob('*') if p.is_file()}
    with patch('subprocess.Popen',side_effect=AssertionError('provider')):assert host.inspect('baseline')['status']=='completed'
    assert all(p.read_bytes()==raw for p,raw in before.items())


def test_title_candidate_correction_fixed_rules_and_retry(cell):
    h,b,_=cell;bad=h.submit('bad',{'workshops/workshop_rules.gd':'WRONG'})
    r=h.build('bad',bad['candidate']);assert r['jobs']['test']['status']=='rejected' and not r['package_created']
    good=h.submit('fixed',{});r=h.build('fixed',good['candidate']);assert r['status']=='completed'
    before=len(b.calls);assert h.build('fixed',good['candidate'])['reused_response'] and len(b.calls)==before


@pytest.mark.parametrize('name',[n for n in SOURCES if n not in SMITH.writable_paths]+['../anything','project.godot','policy.json'])
def test_title_original_dependencies_harness_and_notices_not_writable(cell,name):
    with pytest.raises(ValueError):cell[0].submit('bad',{name:'changed'})


@pytest.mark.parametrize('fault,job,status',[('budget','build','rejected'),('geometry','build','rejected'),('missing','test','held')])
def test_failed_resource_or_missing_visual_evidence_blocks_assembly(cell,fault,job,status):
    h,b,_=cell;b.fault=fault;c=h.submit('one',{});r=h.build('one',c['candidate'])
    assert r['jobs'][job]['status']==status and r['jobs']['package']['status']=='blocked'


@pytest.mark.parametrize('key',['treasury','purse','timber','tools','favor'])
def test_boolean_or_changed_economic_values_cannot_pass(key):
    r=rules();r['stages'][0][key]=False
    with pytest.raises(ValueError):rule_checks(r)
    r=rules();r['stages'][0][key]+=1;assert rule_checks(r)['commission_transitions'] is False


@pytest.mark.parametrize('key',['nodes','meshes','triangles','collision_shapes','materials'])
def test_numeric_budget_boolean_cannot_pass(key):
    c=Fixture().invoke('build',{},'sha256:'+'c'*64);c['process']['observations']['inventory'][key]=True
    with pytest.raises(ValueError):checks(c)


def test_fixed_pose_cameras_and_capture_hashes():
    c=Fixture().invoke('test',{'workshops/workshop_rules.gd':b''},'sha256:'+'c'*64)
    c['process']['observations']['captures'][1]['camera_transform'][0]+=1
    assert checks(c)['detail']['checks']['same_camera'] is False
    c['process']['observations']['captures'][0]['image_sha256']='sha256:'+'0'*64
    assert checks(c)['detail']['checks']['daylight.capture_identity'] is False


def test_changed_colliders_and_unbaked_scene_fail():
    c=Fixture().invoke('build',{},'sha256:'+'c'*64);o=c['process']['observations']
    o['inventory']['colliders'][0][3]*=2;o['loaded_baked_scene']=False
    r=checks(c);assert not r['detail']['checks']['preserved_collision_geometry'] and not r['detail']['checks']['loaded_baked_scene']


@pytest.mark.parametrize('filter_type',range(5))
def test_all_png_filters_agree_and_have_nonblank_scene(filter_type):
    raw=png(filter_type=filter_type,rgba=True)
    assert decode(raw)==decode(DAY)
    assert pixels_inspect(raw)['nonblank'] and not pixels_inspect(raw)['aesthetic_acceptance']


@pytest.mark.parametrize('fault',['crc','truncated','trailing','wrong_size','bomb'])
def test_untrusted_image_bytes_refuse(fault):
    raw=bytearray(DAY)
    if fault=='crc':raw[35]^=1
    elif fault=='truncated':raw=raw[:-1]
    elif fault=='trailing':raw+=b'extra'
    elif fault=='wrong_size':raw[16:20]=struct.pack('>I',1000000)
    else:
        def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
        raw=DAY[:33]+chunk(b'IDAT',zlib.compress(b'\0'*2000000))+chunk(b'IEND',b'')
    with pytest.raises(ValueError):decode(bytes(raw))


def test_nonblank_gate_rejects_flat_image():
    def chunk(k,d):return struct.pack('>I',len(d))+k+d+struct.pack('>I',zlib.crc32(k+d)&0xffffffff)
    raw=DAY[:33]+chunk(b'IDAT',zlib.compress(b'\0'*(360*(640*3+1))))+chunk(b'IEND',b'')
    assert pixels_inspect(raw)['nonblank'] is False


def test_recipe_cannot_import_arbitrary_code_or_change_runtime_mounts(tmp_path):
    with pytest.raises(ValueError):installed('user.python.module')
    args=create_args('sha256:'+'a'*64,'net-cell-'+'b'*32,tmp_path,'test',recipe_id=SMITH.recipe_id)
    assert args[-1]==SMITH.recipe_id and '--network=none' in args and '--memory=512m' in args


def test_operator_capsule_pins_exact_title_files_before_output(cell,tmp_path):
    _,_,source=cell
    p={'schema':'ciw.workcell-title-profile.v1','recipe':SMITH.recipe_id,
       'sources':{n:{'sha256':bytes_ref((source/n).read_bytes()),'bytes':len((source/n).read_bytes())} for n in SOURCES},
       'writable':list(SMITH.writable_paths),'scope':'unit fixture'}
    path=tmp_path/'title.json';path.write_text(json.dumps(p));digest=bytes_ref(path.read_bytes())
    recipe,files,manifest=freeze(source,path,digest);assert recipe is SMITH and len(files)==13
    docker=tmp_path/'docker';docker.write_text('not-executed')
    out=configure(title_root=source,profile=path,profile_sha256=digest,docker=docker,image_id='sha256:'+'a'*64,output_dir=tmp_path/'configured')
    assert out.is_file() and (out.parent/'source-profile.json').read_bytes()==path.read_bytes()
    (source/SOURCES[0]).write_text('changed')
    with pytest.raises(ValueError):configure(title_root=source,profile=path,profile_sha256=digest,docker=docker,image_id='sha256:'+'a'*64,output_dir=tmp_path/'refused')
    assert not (tmp_path/'refused').exists()


def test_inspection_rejects_tampered_export(cell):
    h,_,_=cell;c=h.submit('one',{});h.build('one',c['candidate'])
    (h.root/'runs/one/daylight.png').write_bytes(EVENING)
    with pytest.raises(ValueError,match='Exported artifact'):h.inspect('one')


def test_duplicate_scene_compiler_resources_are_not_execution_approval(cell):
    h,_,_=cell
    with pytest.raises(ValueError):h.call('net_cell_change_image',{})
    assert h.describe()['threshold']['hardware_performance_qualified'] is False


def test_mcp_returns_actual_image_content_and_metadata_without_reexecution(cell):
    from ciw.agent_mcp import Server
    h,b,_=cell;c=h.submit('one',{});h.build('one',c['candidate']);calls=len(b.calls)
    server=Server(h)
    server.handle(json.dumps({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'unit','version':'1'}}}).encode())
    server.handle(b'{"jsonrpc":"2.0","method":"notifications/initialized"}')
    result=server.handle(json.dumps({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'net_cell_preview','arguments':{'attempt':'one','view':'daylight'}}}).encode())['result']
    assert result['content'][1]['type']=='image' and base64.b64decode(result['content'][1]['data'])==DAY
    assert json.loads(result['content'][0]['text'])==result['structuredContent']
    assert 'base64_chunks' not in result['structuredContent']['image']
    assert len(b.calls)==calls and result['structuredContent']['job_status']=='accepted'


def test_preview_can_show_rejected_work_without_changing_its_status(cell):
    h,_,_=cell;c=h.submit('wrong',{'workshops/workshop_rules.gd':'WRONG'});h.build('wrong',c['candidate'])
    result=h.call('net_cell_preview',{'attempt':'wrong','view':'daylight'})
    assert result['job_status']=='rejected' and result['release_authorized'] is False
    assert h.inspect('wrong')['status']=='incomplete'


@pytest.mark.parametrize('view',['/etc/passwd','../daylight','image.png'])
def test_preview_does_not_accept_filesystem_paths(cell,view):
    with pytest.raises(ValueError):cell[0].call('net_cell_preview',{'attempt':'anything','view':view})
