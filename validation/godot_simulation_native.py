"""Execute actual pinned Godot, not a protocol double or Python dynamics fallback."""
from __future__ import annotations
import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
import time

from ciw.control_contracts import bytes_ref, save_new
from ciw.godot_simulation import DEFAULT, PROVIDER_ID, STEP, GodotProjectile
from ciw.godot_simulation_cli import demo, campaign
from ciw.instruments import make_demo_run
from ciw.session import Session
from ciw.simulation_control import SimulationControl, completed, open_workspace
from ciw.simulation_campaign import read_campaign
from ciw.simulation_campaign_view import save_view
from ciw.simulation_records import observer
from ciw.simulation_replay import validate_replay


def run(executable: Path, binary_hash: str, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    checks=[]
    def check(condition, label):
        if not condition: raise AssertionError(label)
        checks.append(label)
    summary=demo(executable,binary_hash,output/'demo')
    check(summary['max_differences_m']==[.25,.25,.5], 'actual_four_branch_native_campaign')
    check(summary['replay']['status']=='PASS','fresh_native_checkpoint_replay')
    check(summary['parent_unchanged_during_campaign'], 'parent_isolation')
    check(summary['world_time_s']==10*STEP and summary['player_latest_time_s']==8*STEP,'native_observation_delay')
    check(len(summary['processes'])==6 and all(x['returncode']==0 for x in summary['processes']),'six_native_owners_closed')
    check(len({p['pid'] for p in summary['processes']})==6,'independent_concurrently_alive_processes')
    report=read_campaign(output/'demo/campaign.json')
    # Independent discrete recurrence solution, not a second runtime implementation.
    maximum=0.0
    for index,case in enumerate(report['cases']):
        result=next(r for r in case['results'] if r['parameters']['action']=='observe')
        delta=[0,-2,2,4][index]
        for item in result['data']['observations']['samples']:
            tick=round(item['clock']['time_s']/STEP)
            expected=2*tick*STEP+max(0,tick-5)*STEP+delta*max(0,tick-2)*STEP
            maximum=max(maximum,abs(item['value']-expected))
    check(maximum==0, 'independent_dyadic_impulse_reference')
    save_view(report,output/'demo/inspector.html')
    fresh=campaign(executable,binary_hash,output/'demo/workspace.json',output/'demo/plan.json',output/'repeat')
    check(fresh==report['summary'],'fresh_native_saved_plan')
    repeated=read_campaign(output/'repeat/campaign.json')
    old_ids={r['execution_id'] for c in report['cases'] for r in c['results']}
    new_ids={r['execution_id'] for c in repeated['cases'] for r in c['results']}
    check(not old_ids & new_ids,'fresh_occurrence_ids')
    # Separate actual engine tests for gravity, missingness, fencing and failure.
    session=Session(make_demo_run(),output/'diagnostics')
    control=SimulationControl(session)
    providers=[]
    gravity_error={"position_y":0.0,"velocity_y":0.0}
    try:
        config=deepcopy(DEFAULT);config['gravity_m_s2']=[0,-9.81,0]
        with GodotProjectile(executable,expected_sha256=binary_hash,configuration=config) as native:
            providers.append(native)
            instance=control.attach(native,provider_id=PROVIDER_ID,experiment_id='native-numerics')
            def call(action,**args):return completed(instance.command(action,**args))
            blank=call('observe',observer=observer('player',kind='embodied_agent',channels=['position_y']))
            check(blank['data']['observations']['samples']==[],'unavailable_native_observation_is_empty')
            req=instance.request('start',command_id='native-start-once')
            first=control.submit(req);before=native.diagnostics()['rpc_count']
            check(control.submit(req)==first and native.diagnostics()['rpc_count']==before,'native_retry_does_not_execute')
            identity=native.identity();time.sleep(.05)
            check(native.identity()==identity,'wall_clock_does_not_advance_native_time')
            stale=instance.request('step',dt=STEP);stale['expected']['owner_id']='old-owner'
            before=native.diagnostics()['rpc_count']
            refusal=control.submit(stale)
            check(refusal['payload']['status']=='refused' and native.diagnostics()['rpc_count']==before,'stale_owner_fenced_before_native_dispatch')
            pid=native.diagnostics()['pid']
            for _ in range(32):call('step',dt=STEP)
            measured=call('observe',observer=observer('debugger',kind='debugger',channels=['position_y','velocity_y']))
            for sample in measured['data']['observations']['samples']:
                n=round(sample['clock']['time_s']/STEP)
                expected=3*n*STEP-9.81*STEP**2*n*(n+1)/2 if sample['quantity']=='position_y' else 3-9.81*n*STEP
                gravity_error[sample['quantity']]=max(gravity_error[sample['quantity']],abs(sample['value']-expected))
            check(all(v<1e-5 for v in gravity_error.values()),'non_dyadic_gravity_independent_discrete_reference')
            check(pid==native.diagnostics()['pid'],'one_native_process_persists_across_commands')
            call('pause');cp=call('checkpoint')
            before_state=instance.inspect()
            with GodotProjectile(executable,expected_sha256=binary_hash,configuration=config) as fresh_native:
                providers.append(fresh_native)
                child,receipt=control.branch(cp,fresh_native,experiment_id='restore-numerics')
                completed(receipt)
                check(child.inspect()['state_ref']==before_state['state_ref'],'opaque_native_snapshot_restores_exact_bytes')
                completed(child.command('stop'))
            check(instance.inspect()==before_state,'numerical_restore_preserves_parent')
            call('stop')
        with GodotProjectile(executable,expected_sha256=binary_hash) as dead:
            providers.append(dead)
            instance=control.attach(dead,provider_id=PROVIDER_ID,experiment_id='native-process-death')
            completed(instance.command('start'))
            dead._pipe.process.kill();dead._pipe.process.wait(timeout=5)
            response=instance.command('step',dt=STEP)
            check(response['payload']['status']=='refused' and response['payload']['result'] is None,
                  'actual_native_process_death_has_no_success_result')
            check(instance.inspect()['state_status']=='unknown_after_failure','native_death_quarantines_owner')
        with GodotProjectile(executable,expected_sha256=binary_hash) as malformed:
            providers.append(malformed)
            try:malformed.restore(b'not-a-native-snapshot')
            except ValueError:pass
            else:raise AssertionError('invalid native snapshot accepted')
            check(malformed.diagnostics()['returncode'] is not None,'invalid_snapshot_refuses_and_closes_native_process')
    finally:
        session.save_workspace(output/'diagnostics/workspace.json')
        save_new(output/'diagnostics/processes.json',{'processes':[p.diagnostics() for p in providers]})
    # Reopen without any process creation. Rechecking evidence is not a new engine run.
    from unittest.mock import patch
    from ciw.control_contracts import load
    with patch('subprocess.Popen',side_effect=AssertionError('offline reader launched process')):
        for name in ('demo','repeat','diagnostics'):
            restored=open_workspace(output/name/'workspace.json',output_dir=output/'readers'/name)
            check(bool(restored.results),f'provider_free_{name}_workspace')
        read_campaign(output/'demo/campaign.json')
        read_campaign(output/'repeat/campaign.json')
        validate_replay(load(output/'demo/replay.json'))
    result={'status':'passed','checks':checks,'check_count':len(checks),
            'binary_sha256':binary_hash,'engine_runtime':summary['runtime'],
            'max_campaign_reference_error_m':maximum,'max_gravity_reference_error':gravity_error,
            'scope':'actual headless Godot point provider; no contact/rendering or physical validation',
            'verification_status':'not_verified'}
    save_new(output/'qualification.json',result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--godot',type=Path,required=True)
    parser.add_argument('--godot-sha256',required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(run(args.godot,args.godot_sha256,args.output_dir),indent=2))
