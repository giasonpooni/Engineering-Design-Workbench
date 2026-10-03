"""Actual installed NET -> unchanged SCR Rust/C++/Julia study qualification.

Provision runtimes explicitly. Native evidence is retained in the provider's
owner repository; this script contains no provider implementation or fallback.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
from unittest.mock import patch


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binding',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    import ciw
    from ciw import simulation as sim
    from ciw import simulation_study as study
    from ciw import native_interop_contract as contract
    from ciw.control_contracts import load,save_new
    from ciw.operations.runner import seal
    from ciw.simulation_study_view import write
    from ciw.session import envelope
    from ciw.telemetry import canonical
    import uuid
    root=Path(__file__).resolve().parents[1]
    if Path(ciw.__file__).resolve().is_relative_to(root):
        raise RuntimeError('Qualification requires an installed wheel outside source imports')
    output=args.output_dir.resolve();output.mkdir(parents=True,exist_ok=False)
    plan=study.default_plan()
    original=study.run(plan,args.binding.resolve(),output/'original')
    reproduced=study.reproduce(output/'original',args.binding.resolve(),output/'fresh',expected_report_digest=original['record_digest'])
    assert all(c['outcome']['status']=='PASS' for p in reproduced['checks'] for c in p['checks'].values())
    assert all(c['outcome']['status']=='FAIL' for c in original['comparisons'][0]['checks'].values())
    # Old checkpoints contain full original native execution identity. Collect
    # unique IDs: inherited parent events are not additional executions.
    def native_ids(directory):
        ids=set()
        for name in ['parent','branch-00','branch-01']:
            cp=sim.read_checkpoint(directory/name/'payload.json')
            ids.add(cp['initial_force']['execution_id'])
            for event in cp['events']:
                for step in event.get('native_steps',[]):ids.add(step['execution_id'])
        return ids
    old_ids,new_ids=native_ids(output/'original'),native_ids(output/'fresh')
    assert old_ids and old_ids.isdisjoint(new_ids)
    # These are real native source files. Blocking launch/reference calls here
    # tests the offline reader; it does not replace providers during execution.
    with patch.object(sim,'ProviderPair',side_effect=AssertionError('offline launch')), patch.object(contract,'oscillator_reference',side_effect=AssertionError('offline oracle')):
        checked=study.inspect_reproduction(output/'original',output/'fresh')
        assert checked['numerical_outcomes']==['PASS']*6
        views=[write(output/'original',observer,output/(name+'.html')) for observer,name in [('observer:position','position-inspector'),('observer:diagnostic','diagnostic-inspector')]]
    owner=sim.Simulation(plan['model'],plan['initial'],args.binding.resolve(),output/'control/native')
    try:
        session=study._session(owner,output/'control/session')
        def ask(kind,payload):return session.handle(envelope(kind,payload,uuid.uuid4().hex))
        def command(**extra):
            v=owner.inspect()
            return dict(command_id='command-'+uuid.uuid4().hex,owner_id=v['owner_id'],expected_revision=v['revision'],at_tick=v['state']['tick'],**extra)
        control=dict(owner_id=owner.inspect()['owner_id'],expected_control_revision=0)
        pause=ask('simulation.pause',control);assert pause['payload']['paused'] is True
        blocked=ask('simulation.advance',command(ticks=12));assert blocked['type']=='error'
        stepped=ask('simulation.step',command(ticks=12));assert stepped['payload']['state']['tick']==12
        stale=ask('simulation.resume',control);assert stale['type']=='error'
        resumed=ask('simulation.resume',{**control,'expected_control_revision':1});assert resumed['payload']['paused'] is False
        assert owner.inspect()['state']['tick']==12
        observed=ask('simulation.observe',{'observer':plan['observers'][0]})
        assert observed['payload']['streams']['q_m']==[] # 24 tick delay
        wrapper,_=study._capture(owner,output/'control',original['study_id'])
        save_new(output/'control/commands.json',{'pause':pause,'blocked':blocked,'stepped':stepped,'stale':stale,'resumed':resumed,'observed':observed})
    finally:owner.close()
    final={}
    for name in ['branch-00','branch-01']:
        cp=sim.read_checkpoint(output/'original'/name/'payload.json');final[name]=sim.inspect_checkpoint(cp)['state']
    assert abs(final['branch-01']['q_m']-final['branch-00']['q_m'])>.01
    report=seal({'status':'passed','schema':'ciw.simulation-study-qualification.v1','ciw_module':str(Path(ciw.__file__).resolve()),'python':sys.version,
                 'original_report':original['record_digest'],'reproduction':reproduced,'offline_recheck':checked,
                 'native_execution_counts':{'original':len(old_ids),'fresh':len(new_ids)},'disjoint_native_occurrences':True,
                 'final_states':final,'observer_views':views,'control_checkpoint':wrapper['record_digest'],
                 'scope':'Actual bounded oscillator; no general game state restore, bitwise guarantee, physical validation or proof.'})
    save_new(output/'qualification.json',report)
    print(canonical(report).decode())


if __name__=='__main__':main()
