"""One operator-approved Blender asset worker behind existing NET packets/production.

Produces a scoped candidate, not source promotion. Native inspector and pure gates
are separately bound; the author never receives the gate or approval authority.
"""
from __future__ import annotations
import base64
from copy import deepcopy
from pathlib import Path
import platform
import re
import struct
import tempfile
import uuid

from . import foundry_packets as packets, foundry_pipeline as pipeline
from . import foundry_asset_contract as contract
from . import foundry_asset_inspector as inspector
from .control_contracts import _base, bytes_ref, content_ref, keys, load, number, save_new
from .core.identities import content_identity
from .game_workflow import make_run
from .interactive_simulation import file_sha, run_process
from .operations.runner import seal
from .production import Gate, Worker, plan, preflight, run_production, inspect_production
from .production_workflow import _graph, _job

OP = 'asset.workbench-production.v1'
GATE = 'asset.workbench-acceptance.v1'
MODEL = 'workbench-candidate.v1'
WORKERS = (Worker('blender-workbench-worker', (OP,)),)
TASKS = frozenset({'art-target', 'props-materials', 'blender-export', 'collision-lod'})
_REGISTERED = False


def parameters(value):
    keys(value, {'nonce', 'legs'})
    if type(value['nonce']) is not str or re.fullmatch('[0-9a-f]{32}', value['nonce']) is None:
        raise ValueError('Invalid request nonce')
    if type(value['legs']) is not int or value['legs'] not in (3, 4):
        raise ValueError('Declare a bounded three/four-leg candidate')


def assignment(project, packet, expected_id):
    content_ref(expected_id)
    if packet.get('record_digest') != expected_id:
        raise ValueError('Packet differs from the independently operator-retained identity')
    task = pipeline.task_for(project, packet['task_id'])
    packets.validate_packet(packet, project, task)
    if task['task_id'] not in TASKS or packet['writable'] != [contract.OUTPUT]:
        raise ValueError('Worker requires an asset-related task and exactly assets/props/workbench.glb')
    if len(packet['baseline']['files']) >= packets.MAX_FILES and contract.OUTPUT not in packet['baseline']['files']:
        raise ValueError('Candidate needs one available inventory entry')
    return {'schema': 'ciw.workbench-assignment.v1', 'project': deepcopy(project),
            'packet': deepcopy(packet), 'packet_id': expected_id,
            'scope': 'operator-selected candidate subjob; not parent-task approval'}


def objective(run):
    value = run['metadata']['game_scenario']['parameters']
    keys(value, {'schema', 'project', 'packet', 'packet_id', 'scope'})
    if assignment(value['project'], value['packet'], value['packet_id']) != value:
        raise ValueError('Work assignment changed')
    if run['metadata']['game_scenario']['model_id'] != MODEL:
        raise ValueError('Wrong asset model')
    return value


def source(project, packet):
    value = assignment(project, packet, packet['record_digest'])
    return make_run({'schema': 'ciw.game-scenario.v1', 'project_id': project['project_id'],
        'scenario_id': contract.PROFILE, 'model_id': MODEL, 'source_class': 'authored_game',
        'clock': {'id': 'asset-declaration-not-game-clock', 'tick_seconds': 1, 'duration_ticks': 1},
        'entities': ['workbench'], 'channels': {'declaration': {'entity_id': 'workbench',
            'quantity': 'declared_asset_order', 'unit': '1', 'frame': 'gltf-Y-up', 'perspective': 'world'}},
        'parameters': value, 'checks': []})


def compile_plan(run, *, legs=4, repair=False):
    value = objective(run)
    parameters({'nonce': '0'*32, 'legs': legs})
    if type(repair) is not bool:
        raise ValueError('Repair must be boolean')
    def graph(name, n):
        return _graph(name, OP, {'nonce': uuid.uuid4().hex, 'legs': n}, model=MODEL)
    checks = [{'check_id': 'actual-geometry-scope-and-import', 'node_id': 'candidate',
               'gate_id': GATE, 'policy': deepcopy(contract.POLICY)}]
    attempts = [graph('workbench-candidate', legs)]
    if repair and legs == 3:
        attempts.append(graph('declared-four-leg-correction', 4))
    return plan('workbench-production', project_id=value['project']['project_id'],
        source_evidence_id=run['evidence_id'], jobs=[
            _job('workbench', WORKERS[0].worker_id, ['asset.workbench'], attempts, checks),
            _job('workbench-regression', WORKERS[0].worker_id, ['asset.workbench'],
                 [graph('fresh-author-and-import-regression', 4)], checks, ['workbench'])])


def write_snapshot(root, manifest, raws):
    for path, raw in raws.items():
        destination = root / packets.relative(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('xb') as stream:
            stream.write(raw)
        # Only executable/nonexecutable state is in the existing inventory contract.
        destination.chmod(0o755 if manifest['files'][path]['executable'] else 0o644)


def read_snapshot(root, baseline):
    if packets.inventory(root) != baseline:
        raise ValueError('Source drift from operator-locked packet')
    raws = {p: packets.read_file(packets.root_dir(root), p) for p in baseline['files']}
    if packets.inventory(root) != baseline or any(bytes_ref(raw) != baseline['files'][p]['sha256'] for p, raw in raws.items()):
        raise ValueError('Source changed during snapshot')
    return raws


def candidate_inventory(baseline, raw):
    result = deepcopy(baseline)
    result['files'][contract.OUTPUT] = {'sha256': bytes_ref(raw), 'bytes': len(raw), 'executable': False}
    result['files'] = dict(sorted(result['files'].items()))
    result.pop('inventory_id')
    result['inventory_id'] = content_identity(result)
    packets.validate_inventory(result)
    return result


def capture(value, declared, params):
    """Validate envelope/custody; independent geometric acceptance remains a gate."""
    parameters(params)
    keys(value, {'schema', 'request', 'asset_b64', 'asset_sha256', 'candidate_inventory', 'scope_check',
                 'author_utf8', 'import_utf8', 'logs', 'elapsed_wall_s', 'captured_native_calls'})
    if value['schema'] != 'ciw.workbench-capture.v1':
        raise ValueError('Unknown asset capture')
    request = {'schema': 'ciw.workbench-request.v1', 'packet_id': declared['packet_id'], **params}
    if value['request'] != request:
        raise ValueError('Asset request changed')
    if type(value['asset_b64']) is not str or len(value['asset_b64']) > 65536:
        raise ValueError('Asset encoding outside bound')
    raw = base64.b64decode(value['asset_b64'], validate=True)
    if not 0 < len(raw) <= contract.MAX_ASSET or bytes_ref(raw) != value['asset_sha256']:
        raise ValueError('Asset byte identity mismatch')
    expected = candidate_inventory(declared['packet']['baseline'], raw)
    if value['candidate_inventory'] != expected:
        raise ValueError('Candidate wrote something besides the granted asset')
    scope = value['scope_check']
    _base(scope, 'foundry-candidate-scope', {'packet_digest', 'candidate_inventory_id', 'changes', 'out_of_scope',
        'changed_bytes', 'status', 'quality_acceptance', 'executed', 'publication'})
    diff = packets.changes(declared['packet']['baseline'], expected)
    count = sum(expected['files'].get(d['path'], {}).get('bytes', 0) for d in diff)
    allowed = count <= declared['packet']['max_changed_bytes']
    required = {'schema': scope['schema'], 'packet_digest': declared['packet_id'],
        'candidate_inventory_id': expected['inventory_id'], 'changes': diff, 'out_of_scope': [],
        'changed_bytes': count, 'status': 'scope_passed' if allowed else 'scope_refused',
        'quality_acceptance': 'not_performed', 'executed': False, 'publication': 'not_performed'}
    if scope != seal(required):
        raise ValueError('Scope summary contradicts actual returned asset')
    from .session import loads_json
    if type(value['author_utf8']) is not str or len(value['author_utf8'].encode()) > 4096:
        raise ValueError('Author report byte budget')
    author = loads_json(value['author_utf8'])
    keys(author, {'schema', 'request', 'blender_version'})
    if author['schema'] != 'ciw.workbench-author.v1' or author['request'] != request or author['blender_version'] != '4.5.3':
        raise ValueError('Unqualified Blender author/request')
    imported = None
    if value['import_utf8'] is not None:
        if type(value['import_utf8']) is not str or len(value['import_utf8'].encode()) > 16384:
            raise ValueError('Import observation budget')
        imported = loads_json(value['import_utf8'])
    keys(value['logs'], {'blender.stdout', 'blender.stderr', 'godot.stdout', 'godot.stderr'})
    for record in value['logs'].values():
        keys(record, {'utf8','sha256'})
        if type(record['utf8']) is not str or len(record['utf8'].encode()) > 16384 or bytes_ref(record['utf8'].encode()) != record['sha256']:
            raise ValueError('Native log identity mismatch')
    if number(value['elapsed_wall_s']) < 0 or type(value['captured_native_calls']) is not int or value['captured_native_calls'] != 2:
        raise ValueError('Native capture accounting')
    return raw, imported


class AssetBinding:
    """Trusted local native cell. Disposable directories are not an OS/network sandbox."""
    def __init__(self, project, packet, source_root, blender, godot, *, packet_id, blender_sha256, godot_sha256):
        self.declared = assignment(project, packet, packet_id)
        self.raws = read_snapshot(source_root, packet['baseline'])
        self.paths = {'blender': Path(blender).expanduser().resolve(strict=True), 'godot': Path(godot).expanduser().resolve(strict=True)}
        for key, digest in [('blender', blender_sha256), ('godot', godot_sha256)]:
            content_ref(digest)
            if not self.paths[key].is_file() or file_sha(self.paths[key]) != digest:
                raise ValueError(key + ' executable digest mismatch')
        self.scripts = {'author.py': Path(__file__).with_name('foundry_asset_blender.py').read_bytes(),
                        'inspect.gd': inspector.GODOT_SCRIPT.encode(), 'project.godot': inspector.PROJECT}
        self.identity = {'provider': 'ciw.foundry.blender-workbench', 'execution_mode': 'native_author_and_separate_importer',
            'author_sha256': blender_sha256, 'inspector_sha256': godot_sha256,
            'scripts': {k:bytes_ref(v) for k,v in self.scripts.items()},
            'host_adapter_sha256': bytes_ref(Path(__file__).read_bytes()), 'packet_id': packet_id,
            'platform': platform.platform(), 'scope': 'trusted executables/scripts only; shared libraries and external reads not attested'}

    def runtime_identity(self):
        if any(file_sha(self.paths[k]) != self.identity[field] for k,field in [('blender','author_sha256'),('godot','inspector_sha256')]):
            raise ValueError('Bound runtime changed')
        if {k:bytes_ref(v) for k,v in self.scripts.items()} != self.identity['scripts']:
            raise ValueError('Bound scripts changed')
        if any(bytes_ref(v) != self.declared['packet']['baseline']['files'][k]['sha256'] for k,v in self.raws.items()):
            raise ValueError('Bound source changed')
        return deepcopy(self.identity)

    def invoke(self, declared, params):
        from .adapters.protocol import AdapterRefusal
        parameters(params);self.runtime_identity()
        if declared != self.declared:
            raise ValueError('Execution assignment differs from operator grant')
        request={'schema':'ciw.workbench-request.v1','packet_id':declared['packet_id'],**params}
        try:
            with tempfile.TemporaryDirectory(prefix='net-asset-worker-') as temporary:
                root=Path(temporary); author=root/'author'; native=root/'importer'; candidate=root/'candidate'
                author.mkdir();native.mkdir();candidate.mkdir()
                write_snapshot(candidate, declared['packet']['baseline'], self.raws)
                (author/'author.py').write_bytes(self.scripts['author.py'])
                save_new(author/'request.json',request)
                a=run_process([str(self.paths['blender']), '--background', '--factory-startup', '--disable-autoexec',
                    '--threads','1','--python-exit-code','2','--python',str(author/'author.py'),'--',
                    str(author/'request.json'),str(author/'candidate.glb'),str(author/'author.json')],author,
                    [author/'candidate.glb',author/'author.json'],timeout=60)
                with (author/'candidate.glb').open('rb') as stream: raw=stream.read(contract.MAX_ASSET+1)
                # Safety/profile check before admitting embedded data to the second engine.
                # Semantic acceptance remains independent; a missing leg still reaches the gate.
                contract.observe_glb(raw)
                output=candidate/contract.OUTPUT;output.parent.mkdir(parents=True,exist_ok=True)
                output.write_bytes(raw);output.chmod(0o644)
                (native/'candidate.glb').write_bytes(raw)
                (native/'inspect.gd').write_bytes(self.scripts['inspect.gd'])
                (native/'project.godot').write_bytes(self.scripts['project.godot'])
                save_new(native/'request.json',request)
                b=run_process([str(self.paths['godot']),'--headless','--path',str(native),'--script','res://inspect.gd',
                    '--',str(native/'candidate.glb'),str(native/'request.json'),str(native/'observations.json')],native,
                    [native/'observations.json'],timeout=30)
                logs={}
                for engine, directory in [('blender',author),('godot',native)]:
                    for stream in ('stdout','stderr'):
                        data=(directory/(stream+'.log')).read_bytes()
                        if len(data)>16384 or b'ERROR:' in data or b'Traceback' in data:
                            raise ValueError('Native error or oversized log')
                        logs[engine+'.'+stream]={'utf8':data.decode(),'sha256':bytes_ref(data)}
                if ((author/'author.py').read_bytes()!=self.scripts['author.py'] or
                    (native/'inspect.gd').read_bytes()!=self.scripts['inspect.gd'] or
                    (native/'project.godot').read_bytes()!=self.scripts['project.godot'] or
                    (native/'candidate.glb').read_bytes()!=raw or load(author/'request.json')!=request or load(native/'request.json')!=request):
                    raise ValueError('Runtime modified fixed execution inputs')
                result={'schema':'ciw.workbench-capture.v1','request':request,
                    'asset_b64':base64.b64encode(raw).decode(),'asset_sha256':bytes_ref(raw),
                    'candidate_inventory':packets.inventory(candidate),
                    'scope_check':packets.check_candidate(declared['packet'],declared['project'],
                        pipeline.task_for(declared['project'],declared['packet']['task_id']),candidate,expected_packet_id=declared['packet_id']),
                    'author_utf8':(author/'author.json').read_text(encoding='utf-8'),
                    'import_utf8':(native/'observations.json').read_text(encoding='utf-8') if (native/'observations.json').exists() else None,
                    'logs':logs,'elapsed_wall_s':a['elapsed_wall_s']+b['elapsed_wall_s'],'captured_native_calls':2}
                capture(result,declared,params);self.runtime_identity()
                return result
        except (OSError,ValueError,RuntimeError) as exc:
            raise AdapterRefusal('asset_worker_runtime_failed',str(exc)[:4096]) from exc


def register_schema():
    global _REGISTERED
    if not _REGISTERED:
        from .operations.schemas import register_payload_validator
        register_payload_validator(OP, lambda op,data,run,params,selection: capture(data,objective(run),params))
        _REGISTERED=True


def registry(binding):
    from .adapters.protocol import InstrumentManifest
    from .control_plane import CapabilityRegistry
    from .operations.registry import Operation
    register_schema();result=CapabilityRegistry()
    manifest=InstrumentManifest(instrument_id='org.notationsystems.asset-workbench',version='1',role='operation_provider',
        inputs=('run.v1',),outputs=('ciw.operation-result.v1',),units={},frames=('gltf-Y-up',),
        sampling={'mode':'bounded_asset_candidate'},normalization={'state':'original_asset_bytes'},
        supported_operations=(OP,),determinism={'claim':'not_assumed'},
        tolerance_policy={'policy':'fixed_workbench_asset_contract'},calibration_requirements={'status':'authored_not_measured'})
    result.advertise(manifest,runtime=binding.runtime_identity(),capabilities={OP:['asset.workbench']})
    result.bind(Operation(OP,'backend',lambda run,p:binding.invoke(objective(run),p),binding.runtime_identity))
    return result


def policy(value):
    if content_identity(value)!=content_identity(contract.POLICY):
        raise ValueError('Worker cannot weaken installed asset acceptance')


def evaluate(result, value):
    policy(value)
    if result is None:
        return {'status':'INDETERMINATE','detail':{'reason':'missing_result'}}
    if result['operation_id']!=OP:
        raise ValueError('Wrong asset operation')
    data=result['data']
    try:
        observed=contract.observe_glb(base64.b64decode(data['asset_b64'],validate=True))
        from .session import loads_json
        outcome=contract.semantic_checks(observed,None if data['import_utf8'] is None else loads_json(data['import_utf8']),data['request'])
        if data['scope_check']['status']!='scope_passed':
            return {'status':'FAIL','detail':{'reason':'candidate_exceeded_packet_scope_or_budget'}}
        return outcome
    except (ValueError,TypeError,KeyError,IndexError,OverflowError,struct.error) as exc:
        return {'status':'FAIL','detail':{'reason':'invalid_asset_or_import','message':str(exc)[:1024]}}



def gates():
    register_schema()
    return {GATE:Gate(GATE,{'provider':'ciw.foundry.independent-workbench-checks',
        'validator_sha256':bytes_ref(Path(contract.__file__).read_bytes()),
        'inspector_sha256':bytes_ref(inspector.GODOT_SCRIPT.encode()),
        'gate_host_sha256':bytes_ref(Path(__file__).read_bytes()),
        'scope':'technical asset acceptance; no human art approval or release'},policy,evaluate)}


def run_asset(project, packet, source_root, blender, godot, destination, *, packet_id,
              blender_sha256, godot_sha256, evidence=None, legs=4, repair=False, max_operations=3):
    assignment(project,packet,packet_id)
    disposition=pipeline.assess(project,source_root,evidence)['tasks'][packet['task_id']]
    if disposition['blocked_by'] or disposition['status']=='stale':
        raise ValueError('Parent task prerequisites unresolved or stale; no asset dispatch')
    from .foundry_pipeline_cli import outside_source
    outside_source(Path(source_root),Path(destination))
    run=source(project,packet);specification=compile_plan(run,legs=legs,repair=repair)
    binding=AssetBinding(project,packet,source_root,blender,godot,packet_id=packet_id,
        blender_sha256=blender_sha256,godot_sha256=godot_sha256)
    reg=registry(binding)
    preflight(specification,reg,WORKERS,gates(),max_operations=max_operations)
    report=run_production(run,specification,reg,WORKERS,gates(),destination,max_operations=max_operations)
    return {'status':report['status'],'production_id':report['production_id'],'session_id':report['session_id'],
        'attempt_count':report['attempt_count'],'parent_task':packet['task_id'],
        'parent_task_acceptance':'not_performed','publication':'not_performed'}


def inspect_asset(destination):
    root=packets.root_dir(destination)
    result=inspect_production(root,gates())
    workspace=load(root/'session/workspace.json'); declared=objective(workspace['run'])
    spec=load(root/'plan.json'); bindings=load(root/'bindings.json')
    if [j['job_id'] for j in spec['jobs']]!=['workbench','workbench-regression'] or spec['jobs'][1]['depends_on']!=['workbench']:
        raise ValueError('Required asset candidate/regression sequence changed')
    if bindings['workers']!={WORKERS[0].worker_id:[OP]}:
        raise ValueError('Worker identity/allowlist changed')
    runtime=bindings['contracts'][OP]['runtime']
    if runtime.get('provider')!='ciw.foundry.blender-workbench' or runtime.get('packet_id')!=declared['packet_id'] or runtime.get('execution_mode')!='native_author_and_separate_importer':
        raise ValueError('Not the explicitly bound asset producer/importer')
    expected_scripts={'author.py':bytes_ref(Path(__file__).with_name('foundry_asset_blender.py').read_bytes()),
        'inspect.gd':bytes_ref(inspector.GODOT_SCRIPT.encode()),'project.godot':bytes_ref(inspector.PROJECT)}
    if runtime.get('scripts')!=expected_scripts or runtime.get('host_adapter_sha256')!=bytes_ref(Path(__file__).read_bytes()):
        raise ValueError('Retained worker differs from this installed approved recipe')
    expected_checks=[{'check_id':'actual-geometry-scope-and-import','node_id':'candidate','gate_id':GATE,'policy':deepcopy(contract.POLICY)}]
    for job in spec['jobs']:
        if job['checks']!=expected_checks or job['worker_id']!=WORKERS[0].worker_id or job['requires']!=['asset.workbench']:
            raise ValueError('Asset acceptance changed')
        for attempt in job['attempts']:
            if len(attempt['nodes'])!=1 or attempt['nodes'][0]['operation_id']!=OP:
                raise ValueError('Unexpected asset operation')
    return {**result,'parent_task':declared['packet']['task_id'],'parent_task_acceptance':'not_performed',
        'model_calls':0,'human_playtests':0,'human_art_approval':'not_performed',
        'scope':'candidate artifact qualification only; pipeline and game state unchanged'}


def export_asset(destination, source_root, output_dir):
    root=packets.root_dir(destination);inspection=inspect_asset(root)
    if inspection['status']!='completed':
        raise ValueError('Both primary candidate and dependent regression must be accepted')
    from .foundry_workflow import _accepted_result
    from .foundry_pipeline_cli import outside_source
    receipt,result=_accepted_result(root,inspection,'workbench')
    declared=objective(load(root/'session/workspace.json')['run'])
    raws=read_snapshot(source_root,declared['packet']['baseline'])
    raw=base64.b64decode(result['data']['asset_b64'],validate=True)
    raws[contract.OUTPUT]=raw
    manifest=result['data']['candidate_inventory']
    output=Path(output_dir)
    outside_source(Path(source_root),output);outside_source(root,output)
    output.mkdir(parents=True,exist_ok=False)
    write_snapshot(output/'candidate',manifest,raws)
    checked=packets.check_candidate(declared['packet'],declared['project'],
        pipeline.task_for(declared['project'],declared['packet']['task_id']),output/'candidate',expected_packet_id=declared['packet_id'])
    if checked!=result['data']['scope_check']:
        raise ValueError('Export candidate does not match accepted bytes/scope; no manifest written')
    export=seal({'schema':'ciw.foundry-asset-export.v1','packet_id':declared['packet_id'],
        'asset_path':contract.OUTPUT,'asset_sha256':bytes_ref(raw),'candidate_inventory_id':manifest['inventory_id'],
        'source_execution_id':result['execution_id'],'source_result_id':result['result_id'],
        'source_record_digest':result['record_digest'],'acceptance_receipt_digest':receipt['record_digest'],
        'production_id':load(root/'production.json')['production_id'],'parent_task':declared['packet']['task_id'],
        'parent_task_acceptance':'not_performed','publication':'not_performed','verification_id':None,
        'scope':'accepted technical candidate for separate review and integration; not a game build or release'})
    save_new(output/'manifest.json',export)
    return export
