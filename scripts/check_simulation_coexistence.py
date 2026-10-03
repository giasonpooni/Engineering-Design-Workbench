"""Require real engine and SCR workloads on one existing Session, without shared state.

This gate does not substitute providers or provision credentials. All executables
and adapter source roots are explicit operator inputs. Inspect copies stay read-only.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
import uuid

from ciw import interactive_contract as contract
from ciw import interactive_simulation as flow
from ciw import simulation
from ciw.session import Session
from ciw.simulation_session import SimulationSession


def live_command(sim, **values):
    state=sim.inspect()
    return dict(command_id='command-'+uuid.uuid4().hex, owner_id=state['owner_id'],
                expected_revision=state['revision'], at_tick=state['state']['tick'], **values)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('binding','blender','godot','bevy','output-dir'):
        parser.add_argument('--'+name, type=Path, required=True)
    root=Path(__file__).resolve().parents[1]
    parser.add_argument('--adapter-root',type=Path,default=root/'tools/interactive-simulation')
    args=parser.parse_args()
    args.output_dir.mkdir(parents=True,exist_ok=False)
    sources={'adapter_root':args.adapter_root}
    scenario=contract.read(root/'examples/interactive-simulation/projectile.json')
    path,godot=flow.run_case(scenario,args.blender,'godot',args.godot,args.output_dir/'projectile',**sources)
    session=SimulationSession.from_workspace(path,args.output_dir/'shared-session')
    flow.validate_session(session)
    source=deepcopy(session.run)
    original_results=deepcopy(session.results)
    sim=simulation.Simulation({'omega_0_rad_s':2.,'gamma_s_inv':.1,'mass_kg':1.},
        {'tick':0,'q_m':1.,'v_m_s':0.},args.binding,args.output_dir/'oscillator')
    try:
        session.attach_simulation(sim)
        initial=sim.inspect()
        sim.mutate('advance',live_command(sim,ticks=12))
        advanced=sim.inspect()
        contract.require(session.run==source and session.results==original_results,'live operation rewrote retained projectile evidence')
        flow.bind(session,{'bevy':flow.Binding('bevy',args.bevy,**sources)})
        params=deepcopy(godot['parameters']);params.update(engine='bevy',nonce=uuid.uuid4().hex)
        workspace=args.output_dir/'shared-session/workspace.json'
        bevy=flow._request(session,flow.RUN_OP,params,workspace)
        comparison=flow.compare_results(session,godot,bevy,workspace)
        contract.require(sim.inspect()==advanced,'engine execution changed the attached oscillator')
        contract.require(all(comparison['data'][side]['status']=='PASS' for side in ('left','right')),'native trajectory comparison failed')
        sim.mutate('advance',live_command(sim,ticks=12))
        final=sim.inspect()
        contract.require(final['state']['tick']==24 and final['owner_id']==initial['owner_id'],'persistent state owner or tick changed unexpectedly')
        contract.require(session.run==source,'evidence source was replaced by simulation state')
        receipt=sim.checkpoint()
        before=deepcopy(session.results)
        with tempfile.TemporaryDirectory(prefix='ciw-coexistence-inspect-') as tmp, \
             patch.object(flow,'Binding',side_effect=AssertionError('offline inspection launched engine')), \
             patch.object(simulation,'ProviderPair',side_effect=AssertionError('offline inspection launched SCR')), \
             patch.object(contract,'reference',side_effect=AssertionError('offline inspection recomputed reference')):
            reopened=SimulationSession.from_workspace(workspace,Path(tmp))
            flow.validate_session(reopened)
            contract.require(reopened.results==before and 'simulation' not in reopened.snapshot(),'workspace reopening changed records or restored a live owner')
        report={'schema':'notation.simulation-coexistence-gate.v1','status':'PASS',
                'scope':'actual provider-owned oscillator beside engine-owned projectile operations on the existing Session',
                'model_id':final['model_id'],'simulation_id':final['simulation_id'],'owner_id':final['owner_id'],
                'state':final['state'],'source_evidence_id':source['evidence_id'],
                'engine_execution_ids':[godot['execution_id'],bevy['execution_id']],
                'comparison_result_id':comparison['result_id'],'checkpoint':receipt,
                'checks':['same-session','separate-models','single-persistent-writer','engine-run-does-not-advance-oscillator',
                          'live-command-does-not-rewrite-evidence','provider-free-reopen','no-implicit-reattach'],
                'physical_validation':'not_established','equipment_authority':'none'}
        flow.write_new(args.output_dir/'qualification.json',report)
        print(json.dumps(report,indent=2))
    finally:
        sim.close()


if __name__=='__main__':
    main()
