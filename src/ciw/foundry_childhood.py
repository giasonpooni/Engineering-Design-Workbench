"""Input-driven 1792 childhood recipe on the existing NET production substrate."""
from __future__ import annotations
from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path
import json
import re
import shutil
import subprocess
import tempfile
import time
import uuid

from .adapters.protocol import AdapterRefusal, InstrumentManifest
from .control_contracts import bytes_ref, keys, save_new
from .core.identities import content_identity
from .control_plane import CapabilityRegistry
from .operations.registry import Operation
from .operations.schemas import register_payload_validator
from .production import Gate, Worker, plan, run_production
from .production_workflow import _graph, _job
from .game_workflow import make_run

OP='game.childhood-slice-1792.v1'
GATE='game.childhood-preservation-1792.v1'
MODEL='1792.childhood.production-slice.v1'
MILESTONES=(
 'walk and view practice precede reading','E acquires letter physically',
 'courier account attributed','two oral accounts open riding','all three physical gates',
 'actual guard input checks telegraphed practice strikes','counter opens hunting lesson',
 'physical sight and inspection of track 1','physical sight and inspection of track 2',
 'physical sight and inspection of track 3','quiet quarry observation precedes ambush',
 'actual movement escapes to the courtyard','save resumes before ambush without losing lessons')
LIKELIHOODS={'steward':(F(3,4),F(1,4)),'courier':(F(3,10),F(7,10)),'assault':(F(1,20),F(19,20))}
_REGISTERED=False


def source_snapshot(root):
    root=Path(root).resolve(strict=True);sources={}
    for base in ('game','data'):
        for path in sorted((root/base).rglob('*')):
            if path.is_dir(): continue
            if '.godot' in path.parts or path.suffix=='.import': continue
            if path.is_symlink(): raise ValueError('SOURCE_SYMLINK')
            raw=path.read_bytes()
            if len(raw)>16*1024*1024: raise ValueError('SOURCE_FILE_BUDGET')
            sources[path.relative_to(root).as_posix()]=raw
    if len(sources)>512 or sum(map(len,sources.values()))>64*1024*1024: raise ValueError('SOURCE_BUDGET')
    if 'game/foundry/childhood_slice.gd' not in sources: raise ValueError('ENTRYPOINT_MISSING')
    manifest={'schema':'ciw.childhood-source-lock.v1','files':{p:bytes_ref(b) for p,b in sources.items()}}
    manifest['source_lock_id']=content_identity(manifest)
    return manifest,sources


def source(lock):
    scenario={'schema':'ciw.game-scenario.v1','project_id':'1792','scenario_id':MODEL,
      'model_id':MODEL,'source_class':'authored_game','clock':{'id':'foundry-declaration','tick_seconds':1,'duration_ticks':1},
      'entities':['ranjit_singh'],'channels':{'declaration':{'entity_id':'ranjit_singh','quantity':'objective',
        'unit':'1','frame':'foundry-declaration','perspective':'world'}},
      'parameters':{'source_lock':deepcopy(lock)},'checks':[]}
    return make_run(scenario)


def policy(value):
    if value!={}: raise ValueError('INSTALLED_POLICY_CANNOT_BE_WEAKENED')


def perspective(memories,tick):
    weights=[F(1,2),F(1,2)];seen=set();prior=-1;used=[]
    for m in memories:
        keys(m,{'id','source_id','channel','received_tick','text'})
        t=m['received_tick']
        if type(t) not in (int,float) or int(t)!=t or t<prior or t>tick or m['id'] in seen:
            raise ValueError('FUTURE_DUPLICATE_OR_UNORDERED_MEMORY')
        seen.add(m['id']);prior=t
        if m['id'] in LIKELIHOODS:
            weights=[a*b for a,b in zip(weights,LIKELIHOODS[m['id']])];total=sum(weights)
            weights=[v/total for v in weights]
            used.append({'memory_id':m['id'],'source_id':m['source_id'],'received_tick':t,'age_ticks':tick-t})
    return weights,used


def bounded_state_equal(a,b):
    if isinstance(a,dict) and isinstance(b,dict):
        return set(a)==set(b) and all(bounded_state_equal(a[k],b[k]) for k in a)
    if isinstance(a,list) and isinstance(b,list):
        return len(a)==len(b) and all(bounded_state_equal(x,y) for x,y in zip(a,b))
    if type(a) in (int,float) and type(b) in (int,float):
        import math
        return math.isfinite(a) and math.isfinite(b) and (a==b if type(a) is int and type(b) is int else abs(a-b)<=1e-12)
    return type(a) is type(b) and a==b


def evaluate_data(data):
    """Installed predicates, independent from the game's assertion count/PASS flags."""
    checks={}
    try:
        samples=data['samples']
        checks['ordered_milestones']=[s['milestone'] for s in samples]==list(MILESTONES)
        if len(samples)!=13: return {'status':'FAIL','detail':{'checks':checks}}
        ticks=[s['state']['childhood']['tick'] for s in samples]
        checks['clock_before_reload']=all(type(t) in (int,float) and int(t)==t and t>=0 for t in ticks) and ticks[:12]==sorted(ticks[:12])
        checks['player_identity']=all(s['state']['player']['character_id']=='ranjit_singh' for s in samples)
        checks['native_journal_binding']=all(s['memories']==s['state']['childhood']['memories'] for s in samples)
        checks['initial_knowledge_empty']=samples[0]['memories']==[]
        checks['letter_not_read']=samples[1]['state']['childhood']['heard']==[] and len(samples[1]['memories'])==1
        checks['oral_information_delivery']=samples[2]['state']['childhood']['heard']==['courier'] and set(samples[3]['state']['childhood']['heard'])=={'courier','steward'}
        checks['physical_travel_observed']=samples[0]['state']['childhood']['walked']>=5 and samples[4]['state']['childhood']['ride_gate']==3
        checks['physical_conflict_observed']=samples[5]['state']['childhood']['parries']==2 and samples[6]['state']['childhood']['counters']>=1
        checks['tracking_observed']=[samples[i]['state']['childhood']['tracks'] for i in (7,8,9)]==[1,2,3]
        checks['escaped']=samples[11]['state']['childhood']['ambush']['status']=='escaped'
        # Compare the restored checkpoint with the actual pre-ambush snapshot.
        checks['whole_state_save_reload_bound']=bounded_state_equal(samples[10]['state'],samples[12]['state'])
        checks['perspective_recomputed']=True
        for s,t in zip(samples,ticks):
            weights,used=perspective(s['memories'],t);view=s['perspective']
            checks['perspective_recomputed'] &= (view['received_evidence']==used and
                len(view['weights'])==2 and all(abs(float(a)-b)<1e-12 for a,b in zip(weights,view['weights'])) and
                view['cause_identity'] is None and view['clock_id']=='1792.childhood.tick' and view['tick']==t and
                view['status']=='PROJECTED' and view['likelihood_class']=='authored_gameplay_tuning' and
                view['calibrated_probability'] is False and view['canonical_state_mutated'] is False and
                view['conditional_independence_assumed'] is True and view['report_age_behavior']=='retained_without_decay')
        checks['historical_scope_retained']=data['historical_authentication'] is False and data['source_class']=='authored_source_informed_prototype'
        checks['human_review_not_fabricated']=data['human_playability_review'] is False
        checks['capture_kind']=data['capture_class']=='actual_input_driven_journey'
    except (KeyError,TypeError,ValueError,IndexError,OverflowError):
        return {'status':'FAIL','detail':{'reason':'MALFORMED_OR_UNSUPPORTED_OBSERVATIONS','checks':checks}}
    return {'status':'PASS' if all(checks.values()) else 'FAIL','detail':{'checks':checks,
      'save_numeric_absolute_tolerance':1e-12,'scope':'input journey and declared epistemic predicates; no historical/human art acceptance'}}


def validate_capture(capture,run,params):
    keys(params,{'nonce'})
    if type(params['nonce']) is not str or not 1<=len(params['nonce'])<=128: raise ValueError('NONCE')
    keys(capture,{'schema','request','observations','elapsed_wall_s','stdout','stdout_ref'})
    lock=run['metadata']['game_scenario']['parameters']['source_lock']
    expected={'nonce':params['nonce'],'source_lock_id':lock['source_lock_id']}
    if capture['request']!=expected or capture['observations']['nonce']!=params['nonce'] or capture['observations']['source_lock_id']!=lock['source_lock_id']:
        raise ValueError('OCCURRENCE_OR_SOURCE_BINDING')
    if bytes_ref(capture['stdout'].encode())!=capture['stdout_ref']: raise ValueError('LOG_CHANGED')
    if type(capture['elapsed_wall_s']) not in (int,float) or not 0<=capture['elapsed_wall_s']<=240: raise ValueError('ELAPSED_TIME')
    if capture['schema']!='ciw.childhood-capture.v1': raise ValueError('CAPTURE_SCHEMA')


def register():
    global _REGISTERED
    if not _REGISTERED:
        register_payload_validator(OP,lambda op,data,run,params,selection:validate_capture(data,run,params))
        _REGISTERED=True


def evaluate(result,value):
    policy(value)
    if result is None: return {'status':'INDETERMINATE','detail':{'reason':'MISSING_RESULT'}}
    return evaluate_data(result['data']['observations'])


def gates():
    return {GATE:Gate(GATE,{'provider':'ciw.foundry.childhood-independent-verifier',
       'source_sha256':bytes_ref(Path(__file__).read_bytes())},policy,evaluate)}


def compile_plan(run):
    checks=[{'check_id':'playable-childhood-preservation','node_id':'candidate','gate_id':GATE,'policy':{}}]
    return plan('1792-childhood-slice',project_id='1792',source_evidence_id=run['evidence_id'],jobs=[
        _job('childhood-input-journey','1792-native', ['game.1792.childhood'],
             [_graph('native-childhood',OP,{'nonce':uuid.uuid4().hex},model=MODEL)],checks)])


class ChildhoodBinding:
    def __init__(self,executable,game_root,expected_sha256):
        self.executable=Path(executable).resolve(strict=True);self.root=Path(game_root).resolve(strict=True)
        if bytes_ref(self.executable.read_bytes())!=expected_sha256: raise ValueError('ENGINE_PIN_MISMATCH')
        self.lock,self.sources=source_snapshot(self.root)
        self.identity={'provider':'1792.native-childhood','executable_sha256':expected_sha256,
                       'source_lock':self.lock,'host_adapter_sha256':bytes_ref(Path(__file__).read_bytes()),
                       'scope':'pinned source and executable; no OS/dependency sandbox attestation'}
    def runtime_identity(self):
        if bytes_ref(self.executable.read_bytes())!=self.identity['executable_sha256'] or source_snapshot(self.root)[0]!=self.lock:
            raise ValueError('RUNTIME_OR_SOURCE_DRIFT')
        return deepcopy(self.identity)
    def invoke(self,run,params):
        self.runtime_identity()
        if run['metadata']['game_scenario']['parameters']['source_lock']!=self.lock: raise ValueError('SOURCE_BINDING')
        keys(params,{'nonce'});request={'nonce':params['nonce'],'source_lock_id':self.lock['source_lock_id']}
        started=time.monotonic()
        with tempfile.TemporaryDirectory(prefix='1792-childhood-foundry-') as directory:
            root=Path(directory)
            for name,raw in self.sources.items():
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
            project=root/'game/project.godot'
            # Keep the exact isolated bytes for the post-run source integrity check.
            isolated=project.read_bytes().replace(b'config/name="1792"',
                ('config/name="1792-foundry-'+uuid.uuid4().hex+'"').encode('utf-8'))
            project.write_bytes(isolated)
            save_new(root/'request.json',request)
            logs=''
            commands=[['--headless','--path',str(root/'game'),'--editor','--import'],
              ['--headless','--fixed-fps','60','--path',str(root/'game'),'--script','res://foundry/childhood_slice.gd','--',
               str(root/'request.json'),str(root/'observations.json')]]
            for args in commands:
                result=subprocess.run([str(self.executable),*args],capture_output=True,text=True,timeout=90)
                log=result.stdout+result.stderr
                if result.returncode or re.search(r'(?m)^(?:SCRIPT ERROR|ERROR):',log):
                    raise AdapterRefusal('CHILDHOOD_RUNTIME_REFUSED',log[-3000:])
                logs+=log
            if len(logs.encode())>65536: raise ValueError('LOG_BUDGET')
            raw=(root/'observations.json').read_bytes()
            if len(raw)>512*1024: raise ValueError('CAPTURE_BUDGET')
            for name,original in self.sources.items():
                expected=isolated if name=='game/project.godot' else original
                if (root/name).read_bytes()!=expected: raise ValueError('ENGINE_MUTATED_SOURCE')
            data=json.loads(raw)
        self.runtime_identity()
        capture={'schema':'ciw.childhood-capture.v1','request':request,'observations':data,
                 'elapsed_wall_s':time.monotonic()-started,'stdout':logs,'stdout_ref':bytes_ref(logs.encode())}
        validate_capture(capture,run,params)
        return capture


def registry(binding):
    register();reg=CapabilityRegistry()
    manifest=InstrumentManifest(instrument_id='org.cartesiangraphics.1792-childhood',version='1',role='operation_provider',
      inputs=('run.v1',),outputs=('ciw.operation-result.v1',),units={},frames=(),
      sampling={'mode':'native_input_journey'},normalization={'state':'game_owned'},supported_operations=(OP,),
      determinism={'claim':'not_established'},tolerance_policy={'policy':'installed_childhood_predicates'},
      calibration_requirements={'status':'authored_gameplay'})
    reg.advertise(manifest,runtime=binding.runtime_identity(),capabilities={OP:['game.1792.childhood']})
    reg.bind(Operation(OP,'backend',lambda run,params:binding.invoke(run,params),binding.runtime_identity))
    return reg


def execute(executable,game_root,output_dir):
    b=ChildhoodBinding(executable,game_root,bytes_ref(Path(executable).read_bytes()))
    run=source(b.lock);work=compile_plan(run)
    return run_production(run,work,registry(b),workers=(Worker('1792-native',(OP,)),),gates=gates(),output_dir=Path(output_dir))


def main(argv=None):
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--godot',type=Path,required=True)
    p.add_argument('--game-root',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    args=p.parse_args(argv)
    result=execute(args.godot,args.game_root,args.output_dir)
    print(json.dumps({'status':result['status'],'execution_count':result['execution_count'],
                      'human_hours':None,'accepted_output_per_human_hour':None,
                      'human_playability_review':'not_performed'}))
    return 0 if result['status']=='completed' else 2
