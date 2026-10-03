"""Installed 1792 smith-workshop recipe; game mathematics/assets remain title-owned.

These independent host checks describe a bounded inspection fixture. They do not
claim full-world journey, historical or artistic acceptance, or hardware FPS.
"""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import re

from .control_contracts import bytes_ref, content_ref, detached, keys, number
from .core.identities import content_identity
from .production import Gate
from .workcell_contracts import artifact_bytes
from .workcell_recipe import Recipe
from . import workcell_pixels

ID='1792.smith.v1'
SOURCES=(
    'characters/character_names.gd','childhood/childhood_state.gd','mounts/riding_rules.gd',
    'presentation/canopy.gdshader','presentation/handmade_surface.gdshader','presentation/workshop_kit.gd',
    'territory/misl_rules.gd','workshops/workshop_rules.gd','workshops/workshop_world.gd',
    'workcells/baked_smith.gd','workcells/smith_scene.gd','workcells/smith_probe.gd','workcells/NOTICE.txt',
)
WRITABLE=('workshops/workshop_world.gd','workshops/workshop_rules.gd')
OUTPUTS={'build':('smith.scn',),'test':('daylight.png','evening.png'),'package':('smith.pck',)}
OPS={stage:'workcell.smith.'+stage+'.v1' for stage in OUTPUTS}
POLICY={'recipe':ID,'max_nodes':256,'max_meshes':96,'max_triangles':50000,'max_materials':24,
        'required_colliders':4,'max_draw_calls':160,'max_stage_wall_s':55.0,'preview_size':[640,360],
        'atol':1e-5,'threshold':'all_required_checks_pass','art_review':'not_performed',
        'hardware_performance_qualified':False,'release_authorized':False}
_REGISTERED=False


def validate_capture(value,stage,candidate):
    keys(value,{'schema','stage','candidate_id','process','isolation','elapsed_wall_s'})
    if value['schema']!='ciw.workcell-capture.v1' or value['stage']!=stage or value['candidate_id']!=candidate:
        raise ValueError('Smith capture/source mismatch')
    content_ref(candidate)
    if number(value['elapsed_wall_s'])<0:raise ValueError('Invalid observed wall time')
    iso=value['isolation'];keys(iso,{'mode','image_id','container_id','policy_sha256','checked_before_start','cleanup_complete'})
    if iso['mode']!='docker_container' or iso['checked_before_start'] is not True or iso['cleanup_complete'] is not True:
        raise ValueError('Smith isolation/cleanup not established')
    content_ref(iso['image_id']);content_ref(iso['policy_sha256'])
    if type(iso['container_id']) is not str or re.fullmatch('[a-f0-9]{64}',iso['container_id']) is None:
        raise ValueError('Invalid container occurrence')
    p=value['process'];keys(p,{'schema','stage','nonce','outcome','diagnostic','files','observations','logs'})
    if p['schema']!='ciw.workcell-process.v1' or p['stage']!=stage or p['outcome'] not in ('completed','failed','timeout'):
        raise ValueError('Invalid smith process capture')
    for name,limit in [('nonce',80),('diagnostic',40000),('logs',64000)]:
        if type(p[name]) is not str or len(p[name].encode())>limit:raise ValueError('Oversized/invalid smith diagnostic')
    if not p['nonce']:raise ValueError('Missing request nonce')
    expected=set(OUTPUTS[stage]) if p['outcome']=='completed' else set()
    if type(p['files']) is not dict or set(p['files'])!=expected:raise ValueError('Unexpected smith artifact set')
    if sum(len(artifact_bytes(item)) for item in p['files'].values())>2*1024*1024:
        raise ValueError('Smith artifact budget exceeded')
    detached(value)


def _whole(v):
    v=number(v)
    if v<0 or v!=int(v):raise ValueError('Expected nonnegative integral measurement')
    return int(v)


def _close(a,b):return abs(number(a)-b)<=POLICY['atol']


def _summary(phase,treasury=116,timber=6,tools=2,favor=50):
    return {'phase':phase,'treasury':treasury,'purse':18,'timber':timber,'tools':tools,'favor':favor}


def _summary_matches(value,expected):
    keys(value,set(expected))
    return value['phase']==expected['phase'] and all(_whole(value[k])==expected[k] for k in expected if k!='phase')


def rule_checks(r):
    keys(r,{'stages','errors','early_refused','early_atomic','roundtrip_equal','duplicate_refused','duplicate_atomic','refund_errors','refund'})
    expected=[_summary(phase) for phase in ('fuel','working','ready','tools')]+[_summary('complete',tools=4,favor=53)]
    return {'commission_transitions':type(r['stages']) is list and len(r['stages'])==5 and all(_summary_matches(a,b) for a,b in zip(r['stages'],expected)),
            'accepted_action_results':r['errors']==['']*5,'refund_action_results':r['refund_errors']==['',''],
            'refund_custody':_summary_matches(r['refund'],_summary('cancelled',treasury=120,timber=8)),
            **{name:r[name] is True for name in ('early_refused','early_atomic','roundtrip_equal','duplicate_refused','duplicate_atomic')}}


def pose_checks(pose):
    keys(pose,{'tick','phase','arm_x','coal','finished','carried'})
    return _whole(pose['tick'])==36 and pose['phase']=='working' and _close(pose['arm_x'],1.36) and pose['coal'] is True and pose['finished'] is False and pose['carried'] is False


def checks(value):
    stage=value['stage'];validate_capture(value,stage,value['candidate_id']);p=value['process']
    if p['outcome']!='completed':
        return {'status':'INDETERMINATE' if p['outcome']=='timeout' else 'FAIL','detail':{'outcome':p['outcome'],'diagnostic':p['diagnostic']}}
    o=p['observations']
    if o is None:return {'status':'INDETERMINATE','detail':'missing_native_observations'}
    base={'schema','mode','engine','inventory','loaded_baked_scene'}
    keys(o,base|({'compiled_scene_sha256'} if stage=='build' else {'rules','scene_actions','pose', 'captures' if stage=='test' else 'completion_phase'}))
    if o['schema']!='1792.smith-workcell-observations.v1' or o['mode']!={'build':'build','test':'test','package':'smoke'}[stage]:
        raise ValueError('Wrong native smith observation profile')
    inv=o['inventory'];keys(inv,{'nodes','meshes','triangles','collision_shapes','materials','colliders','workshop_extent'})
    checks={'observed_stage_budget':number(value['elapsed_wall_s'])<=POLICY['max_stage_wall_s'],
            'loaded_baked_scene':o['loaded_baked_scene'] is True,
            'node_budget':1<=_whole(inv['nodes'])<=POLICY['max_nodes'],
            'mesh_budget':30<=_whole(inv['meshes'])<=POLICY['max_meshes'],
            'triangle_budget':1<=_whole(inv['triangles'])<=POLICY['max_triangles'],
            'material_budget':1<=_whole(inv['materials'])<=POLICY['max_materials'],
            'preserved_collision_count':_whole(inv['collision_shapes'])==POLICY['required_colliders']}
    colliders=inv['colliders'];extent=inv['workshop_extent']
    expected_colliders=[[-15.,.45,7.2,.68,.62,.64],[-15.,.88,7.2,1.05,.24,.44],[-17.25,.52,6.6,1.15,.76,1.1],[-14.9,1.08,9.3,2.,.14,.75]]
    checks['preserved_collision_geometry']=(type(colliders) is list and len(colliders)==4 and
        all(type(row) is list and len(row)==6 and any(all(_close(a,b) for a,b in zip(row,expected)) for expected in expected_colliders) for row in colliders) and
        all(any(all(_close(a,b) for a,b in zip(row,expected)) for row in colliders) for expected in expected_colliders))
    checks['workplace_extent']=(type(extent) is list and len(extent)==3 and all(lo<=number(v)<=hi for v,lo,hi in zip(extent,[5.9,2.6,4.7],[6.1,3.3,4.9])))
    if stage=='build':
        checks['compiled_scene_identity']=o['compiled_scene_sha256']==p['files']['smith.scn']['sha256']
        checks['compiled_scene_nonempty']=p['files']['smith.scn']['bytes']>=1024
    else:
        checks.update(rule_checks(o['rules']))
        checks['scene_uses_title_actions']=o['scene_actions']==['','']
        checks['baked_pose_binds_original_animation']=pose_checks(o['pose'])
        if stage=='test':
            captures=o['captures']
            if type(captures) is not list or len(captures)!=2:raise ValueError('Missing same-state lighting views')
            for i,name in enumerate(('daylight','evening')):
                row=captures[i]
                keys(row,{'id','pose','width','height','image_sha256','draw_calls','render_primitives','video_adapter','renderer','camera_transform','camera_kind'})
                item=p['files'][name+'.png'];stats=workcell_pixels.inspect(artifact_bytes(item))
                checks[name+'.capture_identity']=row['id']==name and row['image_sha256']==item['sha256'] and [_whole(row['width']),_whole(row['height'])]==POLICY['preview_size']
                checks[name+'.nonblank_scene_pixels']=stats['nonblank']
                checks[name+'.draw_budget']=1<=_whole(row['draw_calls'])<=POLICY['max_draw_calls']
                checks[name+'.render_primitives']=1<=_whole(row['render_primitives'])<=POLICY['max_triangles']
                checks[name+'.fixed_pose']=pose_checks(row['pose'])
                checks[name+'.renderer']=row['renderer']=='gl_compatibility' and type(row['video_adapter']) is str and bool(row['video_adapter'])
                checks[name+'.inspection_camera']=row['camera_kind']=='fixed_asset_inspection_not_player_camera'
                if type(row['camera_transform']) is not list or len(row['camera_transform'])!=6:raise ValueError('Missing camera transform')
                for v in row['camera_transform']:number(v)
            checks['same_camera']=captures[0]['camera_transform']==captures[1]['camera_transform']
            checks['lighting_changes_pixels']=p['files']['daylight.png']['sha256']!=p['files']['evening.png']['sha256']
        else:
            checks['pack_header']=artifact_bytes(p['files']['smith.pck'])[:4]==b'GDPC'
            checks['packaged_work_ready_on_600th_tick']=o['completion_phase']=='ready'
    return {'status':'PASS' if all(checks.values()) else 'FAIL','detail':{'checks':checks,'art_review':'not_performed','release_authorized':False}}


def gates():
    def policy(value):
        if content_identity(value)!=content_identity(POLICY):raise ValueError('Smith acceptance policy is operator-fixed')
    def evaluate(result,value):
        policy(value)
        return {'status':'INDETERMINATE','detail':'missing_capture'} if result is None else checks(result['data'])
    name='workcell.smith.quality.v1'
    runtime={'provider':name,'source_sha256':bytes_ref(Path(__file__).read_bytes()),
             'pixel_reader_sha256':bytes_ref(Path(workcell_pixels.__file__).read_bytes())}
    return {name:Gate(name,runtime,policy,evaluate)}


def register():
    global _REGISTERED
    if _REGISTERED:return
    from .operations.schemas import register_payload_validator
    def validate(op,data,run,params,selection):
        keys(params,{'candidate_id'})
        source=run['metadata']['workcell'];files=source['source_utf8']
        if type(files) is not dict or set(files)!=set(SOURCES) or any(type(v) is not str for v in files.values()):
            raise ValueError('Missing exact title-owned source capsule')
        cid=content_identity({n:bytes_ref(v.encode()) for n,v in files.items()})
        if source['candidate_id']!=cid or params['candidate_id']!=cid:raise ValueError('Title candidate identity mismatch')
        validate_capture(data,next(s for s,v in OPS.items() if v==op),cid)
    for op in OPS.values():register_payload_validator(op,validate)
    _REGISTERED=True


SMITH=Recipe(ID,SOURCES,WRITABLE,OUTPUTS,{'test':('daylight.png','evening.png'),'package':('smith.pck',)},OPS,POLICY,checks,gates,register,validate_capture,True)
