"""Backend qualification on the original Foundry controller, never game migration."""
from copy import deepcopy
from pathlib import Path
import argparse
import json
import math
import sys
import uuid

from . import foundry_physics_spec as s, foundry_physics_checks as c, foundry_physics_native as native
from .control_contracts import bytes_ref, load, save_new
from .core.identities import content_identity
from .production import Gate, Worker, plan, preflight, run_production, inspect_production, _read
from .production_workflow import _graph, _job
from .game_workflow import make_run

OP='game.physics-backend-qualification.v1'
GATE='game.physics-backend-acceptance.v1'
WORKERS=(Worker('godot-backend-worker',(OP,)),)
REGISTERED=False
JOBS=(('godot-1','godot',1),('jolt-1','jolt',1),('godot-2','godot',2),('jolt-2','jolt',2))


def objective():
    return {'schema':'ciw.physics-backend-objective.v1','profile':s.PROFILE,'source_inventory_id':s.INVENTORY}

def source():
    return make_run({'schema':'ciw.game-scenario.v1','project_id':'1792-physics-qualification',
        'scenario_id':s.PROFILE,'model_id':s.PROFILE,'source_class':'authored_game',
        'clock':{'id':'comparison-declaration-not-game-clock','tick_seconds':1,'duration_ticks':1},
        'entities':['backend'],'channels':{'declaration':{'entity_id':'backend','quantity':'requested_comparison',
            'unit':'1','frame':'game-local','perspective':'world'}},'parameters':objective(),'checks':[]})

def make_plan(run):
    check=[{'check_id':'preserved-gameplay-contracts','node_id':'candidate','gate_id':GATE,'policy':deepcopy(s.POLICY)}]
    # Independent jobs: a failed baseline or Jolt run must not hide the other
    # backend or a repeated failure. No automated repair alters the comparison.
    jobs=[_job(name,WORKERS[0].worker_id,['game.physics.compare'],[_graph(name,OP,
          {'backend':backend,'replicate':replicate,'nonce':uuid.uuid4().hex},model=s.PROFILE)],check)
          for name,backend,replicate in JOBS]
    return plan('physics-backend-matrix',project_id='1792-physics-qualification',source_evidence_id=run['evidence_id'],jobs=jobs)

def register():
    global REGISTERED
    if not REGISTERED:
        from .operations.schemas import register_payload_validator
        register_payload_validator(OP,lambda op,data,run,params,selection:
            native.validate_capture(data,run['metadata']['game_scenario']['parameters'],params))
        REGISTERED=True

def registry(binding):
    from .adapters.protocol import InstrumentManifest
    from .control_plane import CapabilityRegistry
    from .operations.registry import Operation
    register();result=CapabilityRegistry()
    m=InstrumentManifest(instrument_id='org.notationsystems.physics-backend-comparison',version='1',role='operation_provider',
        inputs=('run.v1',),outputs=('ciw.operation-result.v1',),units={},frames=('game-local',),
        sampling={'mode':'fixed_60Hz_original_game_tests'},normalization={'state':'game_owned'},supported_operations=(OP,),
        determinism={'claim':'measured_not_assumed'},tolerance_policy={'policy':'unchanged_game_and_fixed_observation_contract'},
        calibration_requirements={'status':'version_specific_backend_probe'})
    result.advertise(m,runtime=binding.runtime_identity(),capabilities={OP:['game.physics.compare']})
    result.bind(Operation(OP,'backend',lambda run,p:binding.invoke(run['metadata']['game_scenario']['parameters'],p),binding.runtime_identity))
    return result

def policy(value):
    if content_identity(value)!=content_identity(s.POLICY):raise ValueError('Physics acceptance policy changed')

def evaluate(result,value):
    policy(value)
    if result is None:return {'status':'INDETERMINATE','detail':{'reason':'missing_backend_result'}}
    if result['operation_id']!=OP:raise ValueError('wrong backend operation')
    try:return c.evaluate_data(result['data'])
    except (ValueError,KeyError,TypeError,IndexError,OverflowError) as exc:
        return {'status':'FAIL','detail':{'reason':'malformed_backend_observations','message':str(exc)[:1024]}}

def gates():
    register()
    return {GATE:Gate(GATE,{'provider':'ciw.fixed-backend-gameplay-checks',
        'contract_sha256':bytes_ref(Path(c.__file__).read_bytes()),'profile_sha256':bytes_ref(Path(s.__file__).read_bytes()),
        'gate_sha256':bytes_ref(Path(__file__).read_bytes())},policy,evaluate)}

def run(game_root,godot,expected_sha256,destination,max_operations=4):
    from .foundry_pipeline_cli import outside_source
    outside_source(Path(game_root),Path(destination))
    binding=native.PhysicsBinding(game_root,godot,expected_sha256)
    declaration=source();spec=make_plan(declaration);reg=registry(binding)
    preflight(spec,reg,WORKERS,gates(),max_operations=max_operations)
    return run_production(declaration,spec,reg,WORKERS,gates(),destination,max_operations=max_operations)

def _projection(data):
    g=json.loads(c.read_blob(data['gameplay'],2*1024*1024))
    return {'trace':g['trace'],'stages':g['stages'],'metrics':g['metrics'],'passed':g['passed'],'failed':g['failed']}

def difference(left,right):
    a,b=_projection(left),_projection(right)
    ta,tb=a['trace'],b['trace'];first=None;max_delta=0.;aligned=len(ta)==len(tb)
    for i,(x,y) in enumerate(zip(ta,tb)):
        if first is None and x!=y:first={'sample':i,'left_tick':x['tick'],'right_tick':y['tick'],
            'left_position':x['position'],'right_position':y['position']}
        if (x['tick'],x['epoch'],x['phase'])!=(y['tick'],y['epoch'],y['phase']):aligned=False
        if aligned:max_delta=max(max_delta,math.dist(c.vector(x['position']),c.vector(y['position'])))
    if first is None and len(ta)!=len(tb):first={'sample':min(len(ta),len(tb)),'reason':'trace_lengths_differ'}
    la=a['stages']['delivered']['misl']['ledger'];lb=b['stages']['delivered']['misl']['ledger']
    sa=json.loads(c.read_blob(left['processes']['bench']['observer'],65536))['settings']
    sb=json.loads(c.read_blob(right['processes']['bench']['observer'],65536))['settings']
    sa.pop('physics/3d/physics_engine',None);sb.pop('physics/3d/physics_engine',None)
    return {'resolved_settings_equal_except_backend':sa==sb,'trace_lengths':[len(ta),len(tb)],'trajectory_exact':ta==tb,
        'full_observation_projection_exact':a==b,'first_trace_difference':first,
        'aligned_max_position_delta_m':max_delta if aligned else None,
        'final_resources_equal':all(la[k]==lb[k] for k in ('treasury','purse','stock')),
        'comparison':'observed consistency; exact cross-backend trajectory is not an acceptance requirement'}

def inspect(root):
    from .foundry_packets import root_dir
    root=root_dir(root);checked=inspect_production(root,gates())
    plan_record=load(root/'plan.json');binding=load(root/'bindings.json')
    if binding['workers']!={WORKERS[0].worker_id:[OP]}:raise ValueError('Changed worker allowlist')
    runtime=binding['contracts'][OP]['runtime']
    if runtime.get('provider')!='ciw.foundry.godot-backend-comparison' or runtime.get('executable_sha256')!=s.ENGINE or runtime.get('source_inventory_id')!=s.INVENTORY:
        raise ValueError('Not the bound native comparison provider')
    if runtime.get('scripts')!={k:bytes_ref(v) for k,v in native.scripts().items()} or runtime.get('host_sha256')!=bytes_ref(Path(native.__file__).read_bytes()):
        raise ValueError('Retained instrumentation differs from installed trusted code')
    if [j['job_id'] for j in plan_record['jobs']]!=[j[0] for j in JOBS]:raise ValueError('Incomplete backend matrix')
    rows={};payloads={}
    for job,(name,backend,replicate) in zip(plan_record['jobs'],JOBS):
        expected_checks=[{'check_id':'preserved-gameplay-contracts','node_id':'candidate','gate_id':GATE,'policy':deepcopy(s.POLICY)}]
        if job['depends_on'] or job['checks']!=expected_checks or job['worker_id']!=WORKERS[0].worker_id or job['requires']!=['game.physics.compare'] or len(job['attempts'])!=1:
            raise ValueError('Changed matrix sequence, workers or acceptance')
        nodes=job['attempts'][0]['nodes']
        if len(nodes)!=1 or nodes[0]['operation_id']!=OP:raise ValueError('Changed matrix operation')
        p=nodes[0]['parameters'];native.parameters(p)
        if p['backend']!=backend or p['replicate']!=replicate:raise ValueError('Backend relabelled')
        state=checked['jobs'][name];row={'status':state['status']}
        ref=state['attempts'][0];receipt=_read(root,ref['name'],ref)
        graph=_read(root,receipt['graph']['name'],receipt['graph']);result=graph['nodes']['candidate'].get('result')
        if result:
            data=result['data'];outcome=c.evaluate_data(data)
            row.update(acceptance=outcome,execution_id=result['execution_id'],elapsed_native_process_wall_s=data['elapsed_wall_s'],
                       process_calls=data['process_calls'])
            payloads[name]=data
        rows[name]=row
    comparisons={}
    for label,a,b in [('godot-repeat','godot-1','godot-2'),('jolt-repeat','jolt-1','jolt-2'),('cross-backend','godot-1','jolt-1')]:
        if a in payloads and b in payloads and payloads[a]['gameplay'] and payloads[b]['gameplay']:
            comparisons[label]=difference(payloads[a],payloads[b])
        else:comparisons[label]={'status':'unavailable','reason':'missing retained gameplay observations'}
    return {'schema':'ciw.physics-backend-comparison.v1','production':checked,'source_commit':s.GAME_COMMIT,
        'source_inventory_id':s.INVENTORY,'engine_sha256':s.ENGINE,'runs':rows,'comparisons':comparisons,
        'baseline_qualified':all(rows[k]['status']=='accepted' for k in ('godot-1','godot-2')),
        'jolt_qualified_for_this_profile':all(rows[k]['status']=='accepted' for k in ('jolt-1','jolt-2')),
        'migration_performed':False,'automatic_migration_authorized':False,'fresh_execution':False,
        'performance_ranking':'not_measured; process wall times include startup, scripts, IO and host noise',
        'not_qualified':['parallel movement-foundation branch','funded-service branch','crowd scaling','cloth/destruction',
                         'physical-GPU/CPU benchmark','cross-backend save migration','human playtesting','Windows native execution'],
        'scope':'four source-pinned native runs; repeated complete journeys, not cross-process campaign save-resume proof'}

def report_markdown(report):
    lines=['# 1792 · Physics backend qualification','',f"Game source: `{s.GAME_COMMIT}`. Engine: Godot 4.5.1 Standard.",'',
        '| Run | Status | Native assertions passed / failed | Process calls |', '|---|---|---:|---:|']
    for name,row in report['runs'].items():
        d=row.get('acceptance',{}).get('detail',{})
        lines.append(f"| {name} | {row['status']} | {d.get('assertions_passed','—')} / {d.get('assertions_failed','—')} | {row.get('process_calls','—')} |")
    lines += ['', '## Comparison', '', '```json',json.dumps(report['comparisons'],indent=2),'```','',
        'No backend migration or game repository modification. The original tests, capsule, geometry, costs and saves were not retuned.',
        'These are headless regression runs, not CPU/GPU performance rankings or a claim of crowd scalability.',
        'Each suite has its own process and the entire matrix has isolated save directories. Repetition is not a new distinct gameplay scenario.',
        'The separately developed traversal and funded-service branches are not included or silently merged.']
    return '\n'.join(lines)+'\n'

def main(argv=None):
    ap=argparse.ArgumentParser(prog='net foundry physics',description=__doc__);sub=ap.add_subparsers(dest='command',required=True)
    r=sub.add_parser('run');r.add_argument('--game-root',required=True,type=Path);r.add_argument('--godot',required=True,type=Path)
    r.add_argument('--godot-sha256',required=True);r.add_argument('--output-dir',required=True,type=Path);r.add_argument('--max-operations',type=int,default=4)
    for name in ('inspect','report'):
        p=sub.add_parser(name);p.add_argument('production',type=Path)
        if name=='report':p.add_argument('--output',type=Path)
    args=ap.parse_args(argv)
    try:
        if args.command=='run':
            run(args.game_root,args.godot,args.godot_sha256,args.output_dir,args.max_operations)
            result=inspect(args.output_dir)
        else:result=inspect(args.production)
        if args.command=='report':
            text=report_markdown(result)
            if args.output:
                from .foundry_pipeline_cli import outside_source
                outside_source(args.production,args.output)
                with args.output.open('x',encoding='utf-8') as f:f.write(text)
            else:print(text,end='')
        else:print(json.dumps(result,indent=2,allow_nan=False))
        return 0 if result['production']['status']=='completed' else 2
    except (ValueError,OSError,TypeError,KeyError,IndexError,OverflowError) as exc:
        print(json.dumps({'status':'refused','reason':str(exc)}),file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
