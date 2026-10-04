from copy import deepcopy
import json
from pathlib import Path
import re
import subprocess
import pytest
from ciw.control_contracts import bytes_ref
from ciw.foundry_childhood import ChildhoodBinding,evaluate_data,policy,bounded_state_equal,source

@pytest.fixture
def captured():
    # Retained native observation is data for verifier tests, not a new execution.
    return json.loads((Path(__file__).parent/'fixtures/childhood_native_capture.json').read_text())

def test_retained_native_capture(captured):
    assert evaluate_data(captured)['status']=='PASS'
    assert captured['capture_class']=='actual_input_driven_journey'

@pytest.mark.parametrize('fault',['future','cause','covariance','identity','reload','hidden','delivery','order','travel','clock','historical','probability'])
def test_verifier_rejects_retained_counterexamples(captured,fault):
    d=deepcopy(captured)
    if fault=='future': d['samples'][2]['memories'][1]['received_tick']=100000
    if fault=='cause': d['samples'][3]['perspective']['cause_identity']='invented-enemy'
    if fault=='covariance': d['samples'][3]['perspective']['weights']=[0,1]
    if fault=='identity': d['samples'][4]['state']['player']['character_id']='another'
    if fault=='reload': d['samples'][12]['state']['childhood']['tracks']=2
    if fault=='hidden': d['samples'][0]['memories']=[{'id':'secret'}]
    if fault=='delivery': d['samples'][2]['state']['childhood']['heard']=[]
    if fault=='order': d['samples'].reverse()
    if fault=='travel': d['samples'][4]['state']['childhood']['ride_gate']=0
    if fault=='clock': d['samples'][4]['state']['childhood']['tick']=True
    if fault=='historical': d['historical_authentication']=True
    if fault=='probability': d['samples'][3]['perspective']['calibrated_probability']=True
    d['failures']=0;d['assertions']=999999
    assert evaluate_data(d)['status']=='FAIL'

def test_policy_cannot_weaken():
    with pytest.raises(ValueError):policy({'ignore_knowledge':True})

def test_numeric_json_bound_does_not_erase_identity():
    assert bounded_state_equal({'x':0.1},{'x':0.1+1e-15})
    assert not bounded_state_equal({'tick':1},{'tick':True})
    assert not bounded_state_equal({'id':'a'},{'id':'b'})
    assert not bounded_state_equal({'x':0.1},{'x':0.1+1e-6})


@pytest.mark.parametrize('newline', [b'\n', b'\r\n'], ids=['LF', 'CRLF'])
@pytest.mark.parametrize('mutation', [None, 'project.godot', 'foundry/childhood_slice.gd'],
                         ids=['unchanged', 'project-mutated', 'script-mutated'])
def test_native_binding_preserves_project_bytes_and_detects_mutation(tmp_path, monkeypatch, newline, mutation):
    game_root = tmp_path / 'source'
    game = game_root / 'game'
    (game / 'foundry').mkdir(parents=True)
    original_project = newline.join([
        '; UTF-8 comment: \u00e9'.encode('utf-8'), b'[application]', b'config/name="1792"', b'',
    ])
    (game / 'project.godot').write_bytes(original_project)
    (game / 'foundry/childhood_slice.gd').write_bytes(b'extends SceneTree\n')
    executable = tmp_path / 'godot'
    executable.write_bytes(b'fake engine for adapter test')
    binding = ChildhoodBinding(executable, game_root, bytes_ref(executable.read_bytes()))
    calls = []

    def fake_engine(command, **kwargs):
        calls.append(command)
        isolated_game = Path(command[command.index('--path') + 1])
        isolated_project = (isolated_game / 'project.godot').read_bytes()
        assert re.sub(rb'config/name="1792-foundry-[0-9a-f]{32}"',
                      b'config/name="1792"', isolated_project) == original_project
        assert b'config/name="1792"' not in isolated_project
        if '--script' in command:
            request = json.loads(Path(command[-2]).read_bytes())
            Path(command[-1]).write_bytes(json.dumps(request).encode('utf-8'))
            if mutation:
                target = isolated_game / mutation
                target.write_bytes(target.read_bytes() + b'; engine changed source\n')
        return subprocess.CompletedProcess(command, 0, 'native test log\n', '')

    monkeypatch.setattr('ciw.foundry_childhood.subprocess.run', fake_engine)
    if mutation:
        with pytest.raises(ValueError, match='^ENGINE_MUTATED_SOURCE$'):
            binding.invoke(source(binding.lock), {'nonce': 'test-native-byte-preservation'})
    else:
        capture = binding.invoke(source(binding.lock), {'nonce': 'test-native-byte-preservation'})
        assert capture['observations'] == capture['request']
    assert len(calls) == 2
    assert (game / 'project.godot').read_bytes() == original_project
