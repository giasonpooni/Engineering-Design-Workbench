"""Shared Session boundaries with labelled doubles, not native qualification."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import uuid

import pytest
from ciw import interactive_simulation as flow
from ciw import interactive_contract as c
from ciw import simulation as sim_module
from ciw.session import Session
from ciw.simulation_session import SimulationSession
from test_interactive_contract import scenario
from test_interactive_session import FakeBinding
from test_persistent_simulation import ReferenceDouble, command


@pytest.fixture
def mixed(tmp_path, monkeypatch):
    monkeypatch.setattr(flow, 'Binding', FakeBinding)
    monkeypatch.setattr(sim_module, 'ProviderPair', ReferenceDouble)
    monkeypatch.setattr(sim_module, 'validate_step', lambda step, runtime: deepcopy(step['output']))
    ReferenceDouble.failure = ReferenceDouble.blocker = None
    path, result = flow.run_case(scenario(), 'unused', 'godot', 'unused', tmp_path/'initial')
    session = SimulationSession.from_workspace(path, tmp_path/'mixed')
    flow.validate_session(session)
    simulation = sim_module.Simulation({'omega_0_rad_s':2.,'gamma_s_inv':.1,'mass_kg':1.},
        {'tick':0,'q_m':1.,'v_m_s':0.}, 'unused', tmp_path/'oscillator')
    session.attach_simulation(simulation)
    try:
        yield session, simulation, result, tmp_path
    finally:
        simulation.close()
        ReferenceDouble.failure = ReferenceDouble.blocker = None


def test_persistent_commands_do_not_rewrite_projectile_evidence(mixed):
    session, sim, _, _ = mixed
    source, results, executions = deepcopy(session.run), deepcopy(session.results), deepcopy(session.executions)
    sim.mutate('advance', command(sim, ticks=12))
    assert sim.inspect()['state']['tick'] == 12
    assert session.run == source and session.results == results and session.executions == executions
    assert session.snapshot()['simulation']['model_id'] == sim.inspect()['model_id']
    assert session.run['instrument'] == 'org.notationsystems.projectile-scenario'


def test_engine_execution_does_not_advance_attached_oscillator(mixed):
    session, sim, original, root = mixed
    sim.mutate('advance', command(sim, ticks=12))
    before = sim.inspect()
    flow.bind(session, {'bevy': FakeBinding('bevy','unused')})
    params=deepcopy(original['parameters']);params.update(engine='bevy',nonce=uuid.uuid4().hex)
    result=flow._request(session,flow.RUN_OP,params,root/'mixed/workspace.json')
    flow.compare_results(session,original,result,root/'mixed/workspace.json')
    assert result['runtime']['provider'].endswith('bevy')
    assert sim.inspect() == before
    assert result['execution_id'] != original['execution_id']


def test_saved_workspace_does_not_reattach_or_restart_simulation(mixed):
    session, sim, _, root = mixed
    path=root/'mixed/workspace.json';session.save_workspace(path)
    checkpoint=sim.checkpoint();before=sim.inspect()
    with patch.object(sim_module,'ProviderPair',side_effect=AssertionError('reader launched native code')), \
         patch.object(flow,'Binding',side_effect=AssertionError('reader launched engine')), \
         patch.object(c,'reference',side_effect=AssertionError('reader ran reference')):
        restored=SimulationSession.from_workspace(path,root/'offline')
        flow.validate_session(restored)
        assert 'simulation' not in restored.snapshot()
        assert restored.run == session.run
    assert sim.inspect() == before
    assert checkpoint['checkpoint_id']


def test_second_owner_is_refused(mixed):
    session, sim, _, _ = mixed
    with pytest.raises(ValueError,match='already owns'):
        session.attach_simulation(sim)


def test_namespaces_and_unknown_live_commands_remain_separate(mixed):
    session, sim, _, _=mixed
    before=sim.inspect()
    request={'protocol_version':1,'request_id':'scope-check','type':'simulation.launch',
             'payload':{'executable':'untrusted'}}
    response=session.handle(request)
    assert response['type']=='error'
    assert sim.inspect()==before


def test_stale_command_stays_stale_after_projectile_comparison(mixed):
    session, sim, original, root=mixed
    stale=command(sim,ticks=12)
    sim.mutate('advance',command(sim,ticks=12))
    flow.bind(session,{})
    flow.compare_results(session,original,original,root/'mixed/workspace.json')
    with pytest.raises(ValueError):
        sim.mutate('advance',stale)
    assert sim.inspect()['state']['tick']==12
