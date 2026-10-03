"""Recompute gameplay qualification from retained observations, not backend preference.

No engine startup or source mutation occurs here. Exact source/engine/policy pins
remain mandatory; this does not authenticate an untrusted reporting machine.
"""
import math
import re
from . import foundry_physics_spec as s
from .control_contracts import bytes_ref, keys, number
from .session import loads_json

ERROR = re.compile(r'(?m)^(SCRIPT ERROR|ERROR):')

def blob(raw):
    # Respect the existing 64 KiB scalar-string bound without changing Session.
    # Unicode-safe chunks retain the exact original UTF-8 bytes on concatenation.
    text=raw.decode('utf-8')
    return {'chunks':[text[i:i+16384] for i in range(0,len(text),16384)],
            'sha256':bytes_ref(raw),'bytes':len(raw)}

def read_blob(value, limit):
    keys(value, {'chunks', 'sha256','bytes'})
    chunks=value['chunks']
    if type(chunks) is not list or len(chunks)>256 or any(type(t) is not str or len(t)>16384 for t in chunks):
        raise ValueError('Invalid retained text chunks')
    text=''.join(chunks);raw=text.encode()
    if type(value['bytes']) is not int or len(raw)!=value['bytes'] or len(raw)>limit or bytes_ref(raw)!=value['sha256']:
        raise ValueError('retained byte identity')
    return text

def vector(v):
    if type(v)!=list or len(v)!=3: raise ValueError('three finite coordinates required')
    return [number(x) for x in v]

def request(parameters, suite):
    return {'schema':'ciw.physics-backend-request.v1','profile':s.PROFILE,
            'backend':parameters['backend'],'replicate':parameters['replicate'],
            'nonce':parameters['nonce'],'suite':suite}

def process_checks(record):
    keys(record, {'stdout','stderr','returncode','elapsed_wall_s','failure','observer'})
    stdout=read_blob(record['stdout'],s.MAX_LOG);stderr=read_blob(record['stderr'],s.MAX_LOG)
    if type(record['returncode']) not in (int,type(None)) or number(record['elapsed_wall_s'])<0:
        raise ValueError('invalid process observation')
    if record['failure'] is not None and type(record['failure']) is not str: raise ValueError('bad failure')
    return stdout, stderr

def observer_checks(raw, params, suite):
    o=loads_json(read_blob(raw,65536))
    keys(o,{'schema','request','engine','backend','registered_backends','physics_hz','settings','user_data_dir','completed'})
    expected=s.BACKENDS[params['backend']]
    return (o['schema']=='ciw.physics-backend-observer.v1' and o['request']==request(params,suite)
        and o['engine'].get('hash')==s.ENGINE_BUILD and o['engine'].get('string')=='4.5.1-stable (official)'
        and o['backend']==expected and expected in o['registered_backends'].split(',')
        and o['physics_hz']==60 and o['completed'] is True
        and o['settings'].get('physics/3d/physics_engine')==expected
        and o['settings'].get('physics/common/physics_ticks_per_second')==60)

def gameplay_checks(d):
    """Independent bounded custody/movement checks over the game's existing trace."""
    checks={}
    checks['format']=(d.get('schema')=='1792.accepted-bench-gameplay.v1' and d.get('physics_hz')==60
        and d.get('engine')=='4.5.1-stable (official)' and d.get('passed')==106 and d.get('failed')==0 and d.get('dropped')==0)
    g=d['metrics']['geometry']
    checks['unchanged_bench']=(g['asset_sha256']=='60ea4b4657f9c73d12c956e20498e99afa0f892a7b3167ecb033c53d3ec50736'
        and g['parts']==9 and g['triangles']==108
        and math.dist(vector(g['position']),[-46,.132,-5.4])<1e-5
        and math.dist(vector(g['size']),[1.8,.9,.7])<1e-5)
    sides=d['metrics']['collisions'];checks['four_sides']=len(sides)==4
    for i,row in enumerate(sides):
        end,start=vector(row['end_local']),vector(row['start_offset']);axis=0 if start[0] else 2
        checks['side:'+str(i)]=(row['bench_contact'] is True and abs(end[1])<.04
            and end[axis]*math.copysign(1,start[axis])>(1.24 if axis==0 else .69))
    a=d['metrics']['access'];checks['blocked_pickup_atomic']=a['stale_collect_before']==a['stale_collect_after']
    stages=d['stages'];checks['stages']=set(stages)=={'initial','ready','carried','delivered'}
    start=stages['initial']['misl']['ledger'];last=stages['delivered']['misl']['ledger']
    target=dict(start['stock']);target['timber']-=2;target['tools']+=2
    checks['cash']=(last['treasury']==start['treasury']-4 and last['purse']==start['purse'])
    checks['stock']=last['stock']==target and start['watch']==last['watch']==0
    for name,phase in [('ready','ready'),('carried','tools'),('delivered','complete')]:
        value=stages[name]['misl']['ledger']
        checks['custody:'+name]=(value['workshop']['phase']==phase and
            value['stock']['tools']==start['stock']['tools']+(2 if name=='delivered' else 0))
    events=[e for e in stages['delivered']['misl']['events'] if e['kind'].startswith('smith.')]
    checks['events']=[e['kind'] for e in events]==['smith.reserve','smith.start','smith.ready','smith.collect','smith.deliver']
    checks['duration']=len(events)==5 and events[2]['tick']-events[1]['tick']==600
    trace=d['trace'];checks['trace_complete']=500<len(trace)<20000
    prior=None;epochs=set();minimum=math.inf;max_step=0.;valid=True
    for index,row in enumerate(trace):
        p=vector(row['position']);vector(row['velocity'])
        valid &= row['sample']==index and type(row['tick']) is int and type(row['epoch']) is int
        epochs.add(row['epoch'])
        clearance=math.hypot(max(0,abs(p[0]+46)-.9),max(0,abs(p[2]+5.4)-.35))
        minimum=min(minimum,clearance);valid &= clearance>=.345
        if prior is not None and prior['epoch']==row['epoch']:
            ticks=row['tick']-prior['tick'];step=math.hypot(p[0]-prior['position'][0],p[2]-prior['position'][2])
            valid &= ticks>0 and step<=7.5*ticks/60+.06
            if ticks>0:max_step=max(max_step,step/ticks)
        prior=row
    checks['trajectory']=bool(valid and epochs=={0,1,2})
    checks['phases']={'fuel','working','ready','tools'}<=set(row['phase'] for row in trace)
    return checks, {'samples':len(trace),'minimum_capsule_clearance_m':minimum,'maximum_step_per_tick_m':max_step,
                    'delivered_coins':last['treasury'],'delivered_tools':last['stock']['tools'],'rewinds':len(epochs)-1}

def evaluate_data(data):
    keys(data,{'schema','parameters','source_inventory_id','engine_sha256','override','scripts','processes',
               'probe','gameplay','game_recheck','source_preserved','process_calls','elapsed_wall_s'})
    if data['schema']!='ciw.physics-backend-capture.v1':raise ValueError('capture schema')
    p=data['parameters'];checks={};unknown=[];summary={}
    checks['bound_source']=data['source_inventory_id']==s.INVENTORY
    checks['bound_engine']=data['engine_sha256']==s.ENGINE
    checks['source_preserved']=data['source_preserved'] is True
    checks['override']=read_blob(data['override'],4096).encode()==s.override(p['backend'])
    expected=['import','probe']+[row[0] for row in s.SUITES]+['recheck']
    keys(data['processes'],set(expected))
    checks['count']=type(data['process_calls']) is int and data['process_calls']==len(expected)
    observed_settings=[]
    assertions=0;failed_assertions=0
    for name in expected:
        record=data['processes'][name]
        if record is None:
            unknown.append(name);continue
        out,err=process_checks(record)
        checks['process:'+name]=(record['returncode']==0 and record['failure'] is None and ERROR.search(out+'\n'+err) is None)
        if name not in ('import','recheck'):
            if record['observer'] is None: unknown.append('observer:'+name)
            else:
                checks['backend:'+name]=observer_checks(record['observer'],p,name)
                observed_settings.append(loads_json(read_blob(record['observer'],65536))['settings'])
        if name in [row[0] for row in s.SUITES]:
            spec=next(row for row in s.SUITES if row[0]==name)
            markers=re.findall(r'(?m)^'+re.escape(spec[2])+r': (\d+) passed, (\d+) failed\s*$',out)
            checks['suite:'+name]=len(markers)==1 and tuple(map(int,markers[0]))==(spec[3],0)
            if len(markers)==1:assertions+=int(markers[0][0]);failed_assertions+=int(markers[0][1])
    checks['settings_unchanged_between_suites']=bool(observed_settings) and all(x==observed_settings[0] for x in observed_settings)
    if data['probe'] is None:unknown.append('probe-output')
    else:
        probe=loads_json(read_blob(data['probe'],16384))
        checks['backend_signature']=(probe['schema']=='ciw.physics-backend-probe.v1' and probe['request']==request(p,'probe')
            and probe['backend']==s.BACKENDS[p['backend']] and probe['hit'] is True
            and probe['face_index']==(8 if p['backend']=='godot' else -1)
            and math.dist(vector(probe['position']),[0,.1,0])<1e-5)
    if data['gameplay'] is None:unknown.append('gameplay')
    else:
        observed=loads_json(read_blob(data['gameplay'],2*1024*1024))
        game,summary=gameplay_checks(observed);checks.update({'game:'+k:v for k,v in game.items()})
    if data['game_recheck'] is None:unknown.append('original-game-recheck')
    else:
        g=loads_json(read_blob(data['game_recheck'],16384))
        checks['original_game_recheck']=(g['status']=='passed' and g['native_assertions']==106 and g['independent_gameplay_recheck'] is True)
    if type(data['process_calls']) is not int or number(data['elapsed_wall_s'])<0:raise ValueError('capture metrics')
    failed=[k for k,v in checks.items() if not v]
    return {'status':'FAIL' if failed else 'INDETERMINATE' if unknown else 'PASS',
            'detail':{'checks':checks,'failed_checks':failed,'unavailable':unknown,'assertions_passed':assertions,
                      'assertions_failed':failed_assertions,'gameplay':summary,
                      'scope':'pinned workshop branch; no automatic backend migration, performance ranking or full-game qualification'}}
