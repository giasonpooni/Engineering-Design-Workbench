"""Data-only workcell checks. Passing declared tests is not art/release approval."""
from __future__ import annotations
import base64
from collections import Counter
from pathlib import Path

from .control_contracts import bytes_ref, content_ref, detached, keys, number
from .production import Gate
from .core.identities import content_identity
from .session import loads_json

RECIPE = 'godot-prop.v1'
STAGES = ('build', 'test', 'package')
OPS = {stage: 'workcell.' + stage + '.v1' for stage in STAGES}
MAX_FILE = 512 * 1024
MAX_ARTIFACTS = 2 * 1024 * 1024
POLICY = {'recipe': RECIPE, 'size': [2.0, 0.25, 1.0], 'vertices': 8, 'triangles': 12,
          'speed': 2.0, 'ticks': 120, 'dt': 1.0/60.0, 'atol': 1e-6,
          'threshold': 'all_required_checks_pass', 'release_authorized': False}
REGISTERED = False


def artifact_bytes(item: dict) -> bytes:
    keys(item, {'sha256', 'bytes', 'base64_chunks'})
    content_ref(item['sha256'])
    if type(item['bytes']) is not int or not 0 < item['bytes'] <= MAX_FILE:
        raise ValueError('Workcell artifact size is invalid')
    if type(item['base64_chunks']) is not list or not 1 <= len(item['base64_chunks']) <= 22:
        raise ValueError('Workcell artifact chunks are invalid')
    chunks = []
    for chunk in item['base64_chunks']:
        if type(chunk) is not str or not 1 <= len(chunk) <= 32000:
            raise ValueError('Workcell base64 chunk exceeds budget')
        chunks.append(base64.b64decode(chunk, validate=True))
    raw = b''.join(chunks)
    if len(raw) != item['bytes'] or bytes_ref(raw) != item['sha256']:
        raise ValueError('Workcell artifact digest/length mismatch')
    return raw


def validate_capture(capture: dict, stage: str, candidate: str):
    keys(capture, {'schema','stage','candidate_id','process','isolation','elapsed_wall_s'})
    if capture['schema'] != 'ciw.workcell-capture.v1' or capture['stage'] != stage or capture['candidate_id'] != candidate:
        raise ValueError('Workcell occurrence/source binding mismatch')
    content_ref(candidate)
    if number(capture['elapsed_wall_s']) < 0:
        raise ValueError('Invalid workcell elapsed time')
    iso = capture['isolation']
    keys(iso, {'mode','image_id','container_id','policy_sha256','checked_before_start','cleanup_complete'})
    if iso['mode'] != 'docker_container' or iso['checked_before_start'] is not True or iso['cleanup_complete'] is not True:
        raise ValueError('Workcell isolation was not established or cleanup failed')
    content_ref(iso['image_id']); content_ref(iso['policy_sha256'])
    if type(iso['container_id']) is not str or len(iso['container_id']) != 64 or any(c not in '0123456789abcdef' for c in iso['container_id']):
        raise ValueError('Invalid container occurrence')
    p = capture['process']
    keys(p, {'schema','stage','nonce','outcome','diagnostic','files','observations','logs'})
    if p['schema'] != 'ciw.workcell-process.v1' or p['stage'] != stage or p['outcome'] not in {'completed','failed','timeout'}:
        raise ValueError('Invalid contained process result')
    if type(p['nonce']) is not str or not 1 <= len(p['nonce']) <= 80:
        raise ValueError('Missing process request nonce')
    if type(p['logs']) is not str or len(p['logs'].encode()) > 64000 or type(p['diagnostic']) is not str or len(p['diagnostic'].encode()) > 40000:
        raise ValueError('Contained diagnostics exceed budget')
    if type(p['files']) is not dict or len(p['files']) > 4:
        raise ValueError('Contained artifact set exceeds budget')
    allowed = {'build': {'mesh.json','motion.gd','prop.res','main.scn'}, 'test':set(), 'package':{'slice.pck'}}[stage]
    if set(p['files']) != (allowed if p['outcome'] == 'completed' else set()):
        raise ValueError('Missing or undeclared contained artifact')
    if sum(len(artifact_bytes(v)) for v in p['files'].values()) > MAX_ARTIFACTS:
        raise ValueError('Contained output exceeds total byte budget')
    detached(capture)


def mesh_checks(raw: bytes):
    mesh = loads_json(raw.decode())
    keys(mesh, {'vertices','triangles'})
    vs, ts = mesh['vertices'], mesh['triangles']
    if type(vs) is not list or len(vs) != 8 or type(ts) is not list or len(ts) != 12:
        return {'mesh_counts':False}
    for v in vs:
        if type(v) is not list or len(v) != 3: raise ValueError('Malformed vertex')
        for q in v: number(q)
    for face in ts:
        if type(face) is not list or len(face) != 3 or any(type(i) is not int or not 0 <= i < 8 for i in face):
            raise ValueError('Malformed triangle')
    extents = [max(v[a] for v in vs)-min(v[a] for v in vs) for a in range(3)]
    edges = Counter((a,b) for t in ts for a,b in zip(t,t[1:]+t[:1]))
    return {'mesh_counts':True, 'mesh_size': all(abs(a-b)<=POLICY['atol'] for a,b in zip(extents,POLICY['size'])),
            'mesh_closed_oriented':len(edges)==36 and all(edges[(b,a)]==1 and n==1 for (a,b),n in edges.items()),
            'mesh_non_degenerate':all(len(set(t))==3 for t in ts)}


def checks_for(capture: dict):
    stage, p = capture['stage'], capture['process']
    validate_capture(capture, stage, capture['candidate_id'])
    if p['outcome'] != 'completed':
        return {'status': 'INDETERMINATE' if p['outcome']=='timeout' else 'FAIL',
                'detail': {'contained_outcome':p['outcome'],'diagnostic':p['diagnostic']}}
    checks = {}
    if stage == 'build':
        checks = mesh_checks(artifact_bytes(p['files']['mesh.json']))
        checks['compiled_resource_bytes'] = all(p['files'][n]['bytes']>16 for n in ('prop.res','main.scn'))
    elif stage == 'test':
        o = p['observations']
        if o is None: return {'status':'INDETERMINATE','detail':'missing_observations'}
        keys(o, {'engine','bounds','vertices','challenges','values','trajectory','scene_has_platform','platform_matches'})
        challenges = [[0.,2.,.25],[1.9,2.,.25],[2.,0.,.4],[-1.,1.,.1],[1.,1.,.5]]
        expected = [.5,2.,1.2,-.8,1.]
        # These are fixed reference-test conditions, not a replacement game runtime.
        checks['challenge_identity'] = (type(o['challenges']) is list and len(o['challenges'])==5 and
            all(type(row) is list and len(row)==3 and [number(v) for v in row]==expected_row
                for row,expected_row in zip(o['challenges'],challenges)))
        checks['mechanic_response'] = (type(o['values']) is list and len(o['values'])==5 and
            all(abs(number(a)-b)<=POLICY['atol'] for a,b in zip(o['values'],expected)))
        trajectory = o['trajectory']
        checks['bounded_tick_trajectory'] = (type(trajectory) is list and len(trajectory)==121 and
            all(abs(number(q)-min(i/30.,2.))<=POLICY['atol'] for i,q in enumerate(trajectory)))
        checks['compiled_mesh_bounds'] = (type(o['bounds']) is list and len(o['bounds'])==3 and
            all(abs(number(a)-b)<=POLICY['atol'] for a,b in zip(o['bounds'],POLICY['size'])))
        checks['compiled_mesh_vertices'] = (type(o['vertices']) is list and len(o['vertices'])==36 and
            all(type(v) is list and len(v)==3 and all(abs(abs(number(q))-d/2)<=POLICY['atol'] for q,d in zip(v,POLICY['size'])) for v in o['vertices']))
        checks['scene_integration'] = o['scene_has_platform'] is True and o['platform_matches'] is True
    else:
        o=p['observations']
        if o is None: return {'status':'INDETERMINATE','detail':'missing_package_observations'}
        keys(o,{'pack_scene_loaded','height','platform_y'})
        checks['package_header'] = artifact_bytes(p['files']['slice.pck'])[:4] == b'GDPC'
        checks['packaged_scene_smoke'] = o['pack_scene_loaded'] is True and abs(number(o['height'])-2.)<=POLICY['atol'] and abs(number(o['platform_y'])-2.3)<=POLICY['atol']
    return {'status':'PASS' if all(checks.values()) else 'FAIL', 'detail':{'checks':checks,'release_authorized':False}}


def gates():
    def policy(value):
        if content_identity(value) != content_identity(POLICY): raise ValueError('Workcell thresholds are fixed by the installed recipe')
    def evaluate(result, value):
        policy(value)
        return {'status':'INDETERMINATE','detail':'missing_capture'} if result is None else checks_for(result['data'])
    name = 'workcell.quality.v1'
    return {name: Gate(name, {'provider':'net.workcell-checks','source_sha256':bytes_ref(Path(__file__).read_bytes())},policy,evaluate)}


def register_schemas():
    global REGISTERED
    if REGISTERED:return
    from .operations.schemas import register_payload_validator
    def validate(op, data, run, params, selection):
        keys(params, {'candidate_id'})
        source = run['metadata']['workcell']
        supplied=source['source_utf8']
        if type(supplied) is not dict or set(supplied)!={'compiler.py','motion.gd','spec.json'} or any(type(v) is not str for v in supplied.values()):
            raise ValueError('Missing exact candidate source')
        if content_identity({n:bytes_ref(v.encode()) for n,v in supplied.items()})!=source['candidate_id']:
            raise ValueError('Candidate source identity mismatch')
        if params['candidate_id'] != source['candidate_id']:
            raise ValueError('Workcell candidate differs from retained source')
        stage = next(k for k,v in OPS.items() if v==op)
        validate_capture(data,stage,params['candidate_id'])
        if stage=='build' and data['process']['outcome']=='completed' and artifact_bytes(data['process']['files']['motion.gd'])!=supplied['motion.gd'].encode():
            raise ValueError('Compiler changed the candidate mechanic')
    for op in OPS.values():register_payload_validator(op,validate)
    REGISTERED=True
