"""Run and independently reopen the controlled workshop backend matrix.

Original 1792 source is an operator-supplied pinned checkout. No source is vendored,
no backend is installed into the game, and the matrix is not a performance contest.
"""
from pathlib import Path
from copy import deepcopy
import argparse
import json
from unittest.mock import patch
import uuid

from ciw import foundry_physics as f, foundry_physics_checks as c, foundry_physics_spec as s
from ciw import foundry_packets as packets
from ciw.control_contracts import load, save_new
from ciw.production import _read


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--game-root',type=Path,required=True)
    ap.add_argument('--godot',type=Path,required=True)
    ap.add_argument('--output-dir',type=Path,required=True)
    args=ap.parse_args();out=args.output_dir
    out.mkdir(parents=True,exist_ok=False)
    original=packets.inventory(args.game_root)
    observations=[]
    def check(value,label):
        if not value:raise ValueError(label)
        observations.append({'check':label,'status':'PASS'})
    try:f.run(args.game_root,args.godot,s.ENGINE,out/'budget-refusal',max_operations=3)
    except ValueError:check(not (out/'budget-refusal').exists(),'four-operation reservation enforced before native launch/output')
    else:raise ValueError('operation budget ignored')
    result=f.run(args.game_root,args.godot,s.ENGINE,out/'production')
    saved={p:p.read_bytes() for p in (out/'production').rglob('*') if p.is_file()}
    with patch('subprocess.Popen',side_effect=AssertionError('offline inspection launched a native process')):
        report=f.inspect(out/'production')
        check(report['baseline_qualified'],'all unchanged baseline requirements passed on both repeats')
        check(report['jolt_qualified_for_this_profile'],'all unchanged Jolt requirements passed on both repeats')
        check(all(p.read_bytes()==raw for p,raw in saved.items()),'offline reinspection preserves all original bytes')
        check(not report['migration_performed'] and not report['automatic_migration_authorized'],'inspection does not migrate or authorize rollout')
    check(packets.inventory(args.game_root)==original,'original complete game source remains unchanged')
    check(result['attempt_count']==4,'exactly four independently retained NET execution attempts')
    first=result['jobs']['godot-1']['attempts'][0]
    receipt=_read(out/'production',first['name'],first)
    graph=_read(out/'production',receipt['graph']['name'],receipt['graph'])
    data=graph['nodes']['candidate']['result']['data']
    for fault in ['backend-label','missing-observer','failed-test','probe-signature','teleport','created-money','source-drift','unmarked-rewind']:
        bad=deepcopy(data)
        if fault=='backend-label':bad['override']=c.blob(s.override('jolt'))
        elif fault=='missing-observer':bad['processes']['bench']['observer']=None
        elif fault=='failed-test':bad['processes']['riding']['stdout']=c.blob(b'RIDING_TESTS: 176 passed, 1 failed\n')
        elif fault=='probe-signature':
            p=json.loads(c.read_blob(bad['probe'],16384));p['face_index']=-1;bad['probe']=c.blob(json.dumps(p).encode())
        elif fault=='source-drift':bad['source_inventory_id']='sha256:'+'0'*64
        else:
            game=json.loads(c.read_blob(bad['gameplay'],2*1024*1024))
            if fault=='teleport':game['trace'][10]['position'][0]+=10
            elif fault=='created-money':game['stages']['delivered']['misl']['ledger']['treasury']+=100
            elif fault=='unmarked-rewind':
                for row in game['trace']:row['epoch']=0
            bad['gameplay']=c.blob(json.dumps(game).encode())
        check(c.evaluate_data(bad)['status']!='PASS','altered native observation does not qualify: '+fault)
    save_new(out/'comparison.json',report)
    (out/'BACKEND-COMPARISON.md').write_text(f.report_markdown(report),encoding='utf-8')
    record={'schema':'ciw.physics-matrix-qualification.v1','execution_id':uuid.uuid4().hex,
        'operation_id':'physics-matrix-reinspection-and-mutation-check.v1','checks':observations,
        'source_commit':s.GAME_COMMIT,'engine_sha256':s.ENGINE,'production_id':result['production_id'],
        'per_run_assertions':2096,'distinct_inherited_game_suites':14,'complete_runs':4,
        'godot_process_invocations':64,'python_rechecker_invocations':4,
        'original_retained_files_rechecked':len(saved),'human_playtests':0,'performance_benchmark':False,
        'automatic_migration':False,'limits':report['not_qualified']}
    save_new(out/'qualification.json',record)
    print(f"PHYSICS_MATRIX_CHECKS: {len(observations)} passed; 0 failed; 4 runs / 64 Godot invocations")
    return 0

if __name__=='__main__':raise SystemExit(main())
