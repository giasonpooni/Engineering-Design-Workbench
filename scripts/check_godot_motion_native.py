"""Native engine acceptance; no fallback. Compare to a separate Python reference.

Real Godot owns all native snapshots. Tests of malformed retained data do not
execute saved code, and an intentional engine death must quarantine the handle.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
from pathlib import Path
import sys
from unittest.mock import patch


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--godot',type=Path,required=True)
    parser.add_argument('--godot-sha256',required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    import ciw
    from ciw.godot_motion import GodotMotion,PROVIDER_ID,validate_snapshot
    from ciw import godot_motion_study as study
    from ciw.simulation_control import SimulationControl,completed
    from ciw.simulation_records import observer,decode_snapshot
    from ciw.simulation_reference import ReferenceMotion
    from ciw.control_contracts import save_new,load
    from ciw.session import Session,loads_json
    from ciw.instruments import make_demo_run
    from ciw.telemetry import canonical
    from ciw.operations.runner import seal
    checkout=Path(__file__).resolve().parents[1]
    assert not Path(ciw.__file__).resolve().is_relative_to(checkout),'Use installed wheel outside checkout'
    out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    checks=[]
    def check(condition,label):
        if not condition:raise AssertionError(label)
        checks.append(label)
    processes=[]
    def native(**kw):
        return GodotMotion(args.godot,args.godot_sha256,**kw)
    try:
        report=study.demo(args.godot,args.godot_sha256,out/'study')
        check(report['derived']['replay']['status']=='PASS','Fresh native replay')
        check(report['derived']['replay']['checked_commands']==9,'All nine accepted suffix commands replayed')
        check(report['derived']['branch_comparison']['metrics']['max_abs_error']==8,'Counterfactual differs by eight metres')
        check(report['derived']['player_latest_sample_s']==4,'Embodied observation delay')
        check(report['derived']['debugger_latest_sample_s']==6 and report['derived']['narrator_latest_sample_s']==6,'Privileged view and retrospective view are separate')
        replay=load(out/'study/replay.json')
        checkpoint=loads_json(decode_snapshot(replay['checkpoint']['data']['snapshot_b64']).decode())
        check(checkpoint['state']['tick']==2 and checkpoint['state']['queued']==[{'at_tick':4,'delta_v':3}], 'Checkpoint contains pending event before firing')
        for result in replay['source']:
            batch=result['data']['observations']
            if batch and batch['observer']['kind']!='debugger':
                raw=canonical(batch)
                check(b'"velocity"' not in raw and b'"rng"' not in raw and b'"queued"' not in raw,'Restricted observer payload excludes hidden state')
        with patch.object(GodotMotion,'__init__',side_effect=AssertionError('offline launch')):
            checked=study.inspect(out/'study')
        check(checked['provider_execution']=='not_performed','Offline inspection did not start engine')
        # Independent reference executions, not a fallback for Godot.
        for seed in [0,7,2147483647]:
            engine=native(seed=seed);reference=ReferenceMotion(seed=seed)
            try:
                engine.lifecycle('start');reference.lifecycle('start')
                pid=engine.process_id
                for tick in range(1,13):
                    if tick==3:
                        event={'actor_id':'test','operation':'motion.queue-impulse.v1','target':'body-1',
                               'parameters':{'at_tick':4,'delta_v':3}}
                        engine.intervene(event);reference.intervene(event)
                    engine.step(1);reference.step(1)
                    expected=loads_json(reference.snapshot())
                    actual=validate_snapshot(engine.snapshot(),engine.configuration())
                    check(actual==expected,f'Independent state/RNG/queue/history oracle seed={seed} tick={tick}')
                    check(engine.process_id==pid,f'Persistent native process seed={seed} tick={tick}')
                engine.lifecycle('pause');reference.lifecycle('pause')
                before=engine.snapshot()
                # No autonomous state ticks while the host observes or waits.
                import time
                time.sleep(.05)
                check(engine.snapshot()==before,'Wall time did not advance world')
                restored=native(seed=seed)
                try:
                    restored.restore(before)
                    check(restored.snapshot()==before,'Exact engine snapshot restoration')
                    engine.lifecycle('resume');restored.lifecycle('resume')
                    engine.step(1);restored.step(1)
                    check(engine.snapshot()==restored.snapshot(),'Restored continuation equals uninterrupted engine')
                finally:
                    restored.close();processes.append(restored.diagnostics())
            finally:
                engine.close();processes.append(engine.diagnostics())
        session=Session(make_demo_run(),out/'failure-session')
        control=SimulationControl(session)
        for mode in ['hidden-channel','death']:
            engine=native();instance=control.attach(engine,provider_id=PROVIDER_ID,experiment_id=mode)
            try:
                completed(instance.command('start'))
                before=instance.inspect()
                if mode=='death':
                    engine.close()
                    response=instance.command('step',dt=1)
                else:
                    response=instance.command('observe',observer=observer('player',kind='embodied_agent',channels=['velocity']))
                check(response['payload']['status']=='refused',mode+' retained refusal')
                check(instance.inspect()['status']=='refused' and instance.inspect()['state_status']=='unknown_after_failure',mode+' quarantines owner')
                check(instance.inspect()['state_ref']==before['state_ref'],mode+' does not invent a new state reference')
            finally:
                engine.close();processes.append(engine.diagnostics())
        session.save_workspace(out/'failure-session/workspace.json')
        check(sum(e['status']=='refused' for e in session.executions.values())==2,'Two distinct refused executions retained')
        engine=native()
        try:
            checkpoint=loads_json(engine.snapshot());checkpoint['state'].pop('rng')
            requests=engine._mailbox.sequence
            try:engine.restore(canonical(checkpoint))
            except ValueError:pass
            else:raise AssertionError('Incomplete checkpoint accepted')
            check(engine._mailbox.sequence==requests,'Missing RNG refused before native restore request')
        finally:
            engine.close();processes.append(engine.diagnostics())
        check(all(p['closed'] and p['returncode'] is not None for p in processes),'All extra engine processes reaped')
        qualification=seal({'schema':'ciw.godot-motion-qualification.v1','status':'passed',
            'checks':checks,'checks_passed':len(checks),'study':report,'installed_module':str(Path(ciw.__file__).resolve()),
            'python':sys.version,'scope':'Headless synthetic integer motion only; no rendering, general game save, or physical validation.'})
        save_new(out/'qualification.json',qualification)
        print(canonical(qualification).decode())
    finally:
        save_new(out/'process-diagnostics.json',{'processes':processes})


if __name__=='__main__':main()
