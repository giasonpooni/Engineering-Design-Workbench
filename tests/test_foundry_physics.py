"""Explicit synthetic records for boundary tests; NOT physical gameplay evidence."""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from ciw import foundry_physics as f, foundry_physics_checks as c
from ciw import foundry_physics_native as n, foundry_physics_spec as s
from ciw.control_contracts import bytes_ref, save_new
from ciw.production import preflight, run_production, inspect_production
from ciw.foundry_workflow import main as foundry_main


def raw(value):return c.blob(json.dumps(value).encode())


def game_fixture():
    """Hand-authored data example, no engine, game source, or historical claim."""
    first={'treasury':120,'purse':18,'stock':{'timber':8,'tools':2},'watch':0}
    stages={'initial':{'misl':{'ledger':first}}}
    events=[{'kind':'smith.'+name,'tick':tick} for name,tick in [('reserve',0),('start',1),('ready',601),('collect',602),('deliver',603)]]
    for name,phase in [('ready','ready'),('carried','tools'),('delivered','complete')]:
        ledger={'treasury':116,'purse':18,'stock':{'timber':6,'tools':4 if name=='delivered' else 2},'watch':0,'workshop':{'phase':phase}}
        stages[name]={'misl':{'ledger':ledger,'events':events}}
    trace=[{'sample':i,'tick':i%201,'epoch':i//201,'position':[0,0,0],'velocity':[0,0,0],
            'phase':['fuel','working','ready','tools'][min(i//150,3)]} for i in range(603)]
    sides=[{'start_offset':p,'end_local':e,'bench_contact':True} for p,e in [([-2,0,0],[-1.25,0,0]),([2,0,0],[1.25,0,0]),([0,0,-2],[0,0,-.7]),([0,0,2],[0,0,.7])]]
    return {'schema':'1792.accepted-bench-gameplay.v1','engine':'4.5.1-stable (official)','physics_hz':60,'passed':106,'failed':0,'dropped':0,
        'metrics':{'geometry':{'asset_sha256':'60ea4b4657f9c73d12c956e20498e99afa0f892a7b3167ecb033c53d3ec50736',
            'parts':9,'triangles':108,'position':[-46,.132,-5.4],'size':[1.8,.9,.7]},'collisions':sides,
            'access':{'stale_collect_before':{},'stale_collect_after':{}}},'stages':stages,'trace':trace}


def capture_fixture(backend='godot',replicate=1,nonce='1'*32):
    p={'backend':backend,'replicate':replicate,'nonce':nonce};processes={}
    for name in ['import','probe']+[x[0] for x in s.SUITES]+['recheck']:
        out=''
        if name in [x[0] for x in s.SUITES]:
            r=next(x for x in s.SUITES if x[0]==name);out=f'{r[2]}: {r[3]} passed, 0 failed\n'
        record={'stdout':c.blob(out.encode()),'stderr':c.blob(b''),'returncode':0,'failure':None,'elapsed_wall_s':.1,'observer':None}
        if name not in ('import','recheck'):
            o={'schema':'ciw.physics-backend-observer.v1','request':c.request(p,name),
               'engine':{'hash':s.ENGINE_BUILD,'string':'4.5.1-stable (official)'},'backend':s.BACKENDS[backend],
               'registered_backends':'DEFAULT,GodotPhysics3D,Jolt Physics,Dummy','physics_hz':60,
               'settings':{'physics/3d/physics_engine':s.BACKENDS[backend],'physics/common/physics_ticks_per_second':60},
               'user_data_dir':'EXPLICIT TEST FIXTURE - NOT AN ENGINE OBSERVATION','completed':True}
            record['observer']=raw(o)
        processes[name]=record
    return {'schema':'ciw.physics-backend-capture.v1','parameters':p,'source_inventory_id':s.INVENTORY,'engine_sha256':s.ENGINE,
        'override':c.blob(s.override(backend)),'scripts':{k:bytes_ref(v) for k,v in n.scripts().items()},'processes':processes,
        'probe':raw({'schema':'ciw.physics-backend-probe.v1','request':c.request(p,'probe'),'backend':s.BACKENDS[backend],
            'hit':True,'face_index':8 if backend=='godot' else -1,'position':[0,.1,0]}),
        'gameplay':raw(game_fixture()),'game_recheck':raw({'status':'passed','native_assertions':106,'independent_gameplay_recheck':True}),
        'source_preserved':True,'process_calls':17,'elapsed_wall_s':1.7}


@pytest.mark.parametrize('backend',['godot','jolt'])
def test_well_formed_synthetic_capture_passes_contract_not_physical_proof(backend):
    d=capture_fixture(backend);n.validate_capture(d,f.objective(),d['parameters'])
    out=c.evaluate_data(d)
    assert out['status']=='PASS' and out['detail']['assertions_passed']==2096


@pytest.mark.parametrize('fault',['source','engine','settings','probe','missing_suite','failed_suite','missing_marker','duplicate_marker','runtime_error','exit','source_mutation','wrong_floor','obstructed','geometry','early_stock','money','duplicate_event','duration','teleport','rewind','dropped','nonce','no_observer','false_completion','changed_rate','settings_drift'])
def test_altered_observations_never_qualify(fault):
    d=capture_fixture();g=json.loads(c.read_blob(d['gameplay'],2*1024*1024))
    if fault=='source':d['source_inventory_id']='sha256:'+'0'*64
    if fault=='engine':d['engine_sha256']='sha256:'+'0'*64
    if fault=='settings':d['override']=c.blob(s.override('jolt'))
    if fault=='probe':
        p=json.loads(c.read_blob(d['probe'],16384));p['face_index']=-1;d['probe']=raw(p)
    if fault=='missing_suite':d['processes']['riding']=None
    if fault=='failed_suite':d['processes']['riding']['stdout']=c.blob(b'RIDING_TESTS: 176 passed, 1 failed\n')
    if fault=='missing_marker':d['processes']['riding']['stdout']=c.blob(b'finished')
    if fault=='duplicate_marker':d['processes']['riding']['stdout']=c.blob(b'RIDING_TESTS: 177 passed, 0 failed\n'*2)
    if fault=='runtime_error':d['processes']['riding']['stderr']=c.blob(b'ERROR: game broke\n')
    if fault=='exit':d['processes']['riding']['returncode']=1
    if fault=='source_mutation':d['source_preserved']=False
    if fault=='wrong_floor':g['metrics']['collisions'][0]['end_local'][1]=1
    if fault=='obstructed':g['metrics']['access']['stale_collect_after']={'extra_tools':2}
    if fault=='geometry':g['metrics']['geometry']['parts']=8
    if fault=='early_stock':g['stages']['carried']['misl']['ledger']['stock']['tools']=4
    if fault=='money':g['stages']['delivered']['misl']['ledger']['treasury']=999
    if fault=='duplicate_event':g['stages']['delivered']['misl']['events'].append(g['stages']['delivered']['misl']['events'][-1])
    if fault=='duration':g['stages']['delivered']['misl']['events'][2]['tick']=2
    if fault=='teleport':g['trace'][10]['position'][0]=10
    if fault=='rewind':g['trace'][201]['epoch']=0
    if fault=='dropped':g['dropped']=1
    if fault=='nonce':
        o=json.loads(c.read_blob(d['processes']['bench']['observer'],65536));o['request']['nonce']='2'*32;d['processes']['bench']['observer']=raw(o)
    if fault=='no_observer':d['processes']['bench']['observer']=None
    if fault in ('false_completion','changed_rate','settings_drift'):
        o=json.loads(c.read_blob(d['processes']['bench']['observer'],65536))
        if fault=='false_completion':o['completed']=False
        if fault=='changed_rate':o['physics_hz']=30
        if fault=='settings_drift':o['settings']['physics/3d/default_gravity']=0
        d['processes']['bench']['observer']=raw(o)
    d['gameplay']=raw(g)
    assert c.evaluate_data(d)['status']!='PASS'


@pytest.mark.parametrize('backend',['DEFAULT','Dummy','jolt; execute','unknown',None])
def test_only_known_explicit_profiles(backend):
    with pytest.raises(ValueError):s.override(backend)


@pytest.mark.parametrize('values',[{'backend':'godot','replicate':True,'nonce':'1'*32},
    {'backend':'godot','replicate':3,'nonce':'1'*32},{'backend':'godot','replicate':1,'nonce':'x'},
    {'backend':'godot','replicate':1,'nonce':'1'*32,'gravity':0}])
def test_no_arbitrary_tuning_from_saved_task(values):
    with pytest.raises(ValueError):n.parameters(values)


def test_plan_keeps_failed_candidates_visible_and_has_no_repair():
    p=f.make_plan(f.source())
    assert [j['job_id'] for j in p['jobs']]==[j[0] for j in f.JOBS]
    assert all(not j['depends_on'] and len(j['attempts'])==1 for j in p['jobs'])
    bad=deepcopy(s.POLICY);bad['assertions_per_pass']=1
    with pytest.raises(ValueError):f.policy(bad)


def test_repeated_and_cross_backend_comparison_does_not_require_same_floats():
    a,b=capture_fixture(),capture_fixture('jolt')
    g=json.loads(c.read_blob(b['gameplay'],2*1024*1024));g['trace'][10]['position'][0]=.001;b['gameplay']=raw(g)
    assert c.evaluate_data(b)['status']=='PASS'
    diff=f.difference(a,b)
    assert diff['trajectory_exact'] is False and diff['final_resources_equal'] is True
    assert diff['first_trace_difference']['sample']==10
    assert diff['resolved_settings_equal_except_backend'] is True


def test_trustworthy_byte_binding():
    d=capture_fixture();d['gameplay']['chunks'][0]+=' '
    with pytest.raises(ValueError):c.evaluate_data(d)
    d=capture_fixture();d['scripts']['backend-probe.gd']='sha256:'+'0'*64
    with pytest.raises(ValueError):n.validate_capture(d,f.objective(),d['parameters'])


def test_incomplete_backend_matrix_does_not_launch_during_inspect(tmp_path,capsys):
    with patch('subprocess.Popen',side_effect=AssertionError('offline engine launch')):
        assert foundry_main(['physics','inspect',str(tmp_path)])==1
    assert json.loads(capsys.readouterr().err)['status']=='refused'


def test_original_production_controller_with_explicit_mock(tmp_path):
    class Mock:
        def runtime_identity(self):return {'provider':'UNIT TEST DOUBLE, NOT GODOT'}
        def invoke(self,objective,p):return capture_fixture(p['backend'],p['replicate'],p['nonce'])
    r=f.registry(Mock());declaration=f.source();p=f.make_plan(declaration)
    with pytest.raises(ValueError):preflight(p,r,f.WORKERS,f.gates(),max_operations=3)
    out=tmp_path/'matrix';report=run_production(declaration,p,r,f.WORKERS,f.gates(),out,max_operations=4)
    assert report['status']=='completed' and report['attempt_count']==4
    files={p:p.read_bytes() for p in out.rglob('*') if p.is_file()}
    with patch('subprocess.Popen',side_effect=AssertionError('offline engine launch')):
        assert inspect_production(out,f.gates())['status']=='completed'
        with pytest.raises(ValueError,match='bound native'):f.inspect(out)
    assert all(p.read_bytes()==raw for p,raw in files.items())


def test_unknown_engine_is_refused_without_subprocess(tmp_path):
    with patch('subprocess.Popen',side_effect=AssertionError('preflight launched a process')):
        with pytest.raises(ValueError):n.PhysicsBinding(tmp_path,Path('unknown'),'sha256:'+'0'*64)


def test_source_snapshot_digest_is_not_a_game_relabel():
    assert s.GAME_COMMIT=='4869eac467288b99c32268df99d4a06e573fb28d'
    assert len(s.SUITES)==14 and sum(x[3] for x in s.SUITES)==2096
    assert s.override('godot').replace(b'GodotPhysics3D',b'Jolt Physics')==s.override('jolt')
