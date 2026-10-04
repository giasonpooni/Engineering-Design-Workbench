"""Temperature processing uses existing MCP permissions, identities and replay."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from ciw.agent_api import encode, parse
from ciw.agent_mcp import VERSIONS, demo_config, from_profile, main, temperature_config
from ciw.operations.runner import seal
from ciw.session import Session
from ciw.temperature_contract import AUTHORITY
from ciw.temperature_workflow import PROCESS, source_request


def test_temperature_mcp_execution_retry_and_replay_retain_separate_authority(tmp_path):
    profile = temperature_config(tmp_path / 'profile')
    before = {p.name: p.read_bytes() for p in profile.parent.iterdir()}
    host = from_profile(profile, instrument='temperature')
    catalog = host.capabilities()['catalog']
    assert set(catalog['operations']) == {PROCESS}
    assert catalog['authorizes_execution'] is False
    first = host.call('net_execute', {'source': 'source', 'graph': 'baseline', 'attempt': 'first'})
    assert first['status'] == 'completed', first
    workspace = parse((profile.parent / 'agent-output/first/workspace.json').read_bytes())
    result = workspace['results'][0]
    assert result['operation_id'] == PROCESS
    assert result['data']['authority'] == AUTHORITY
    assert result['verification_status'] == 'not_verified'
    assert result['verification_id'] is None
    retry = host.call('net_execute', {'source': 'source', 'graph': 'baseline', 'attempt': 'first'})
    assert retry['reused_response'] is True
    assert retry['execution_ids'] == first['execution_ids']
    replay = host.call('net_replay', {'original_attempt': 'first', 'new_attempt': 'second'})
    assert replay['status'] == 'completed', replay
    assert set(first['execution_ids']).isdisjoint(replay['execution_ids'])
    assert set(first['result_ids']).isdisjoint(replay['result_ids'])
    second = parse((profile.parent / 'agent-output/second/workspace.json').read_bytes())
    assert second['results'][0]['data'] == result['data']
    assert second['run']['evidence_id'] == workspace['run']['evidence_id']
    assert before == {name: (profile.parent / name).read_bytes() for name in before}


def test_temperature_requires_explicit_instrument_and_execution_grant(tmp_path):
    profile = temperature_config(tmp_path / 'profile')
    with pytest.raises(ValueError, match='not advertised'):
        from_profile(profile)
    value = parse(profile.read_bytes())
    value['allow_operations'] = []
    profile.write_bytes(encode(value))
    host = from_profile(profile, instrument='temperature')
    op = host.capabilities()['catalog']['operations'][PROCESS]
    assert not op['bound'] and not op['agent_execution_enabled']
    with pytest.raises(ValueError, match='not enabled'):
        host.call('net_execute', {'source': 'source', 'graph': 'baseline', 'attempt': 'denied'})
    builtin = from_profile(demo_config(tmp_path / 'builtin'))
    assert PROCESS not in builtin.capabilities()['catalog']['operations']


def test_temperature_profile_cannot_grant_candidate_calibration_or_policy_edits(tmp_path):
    profile = temperature_config(tmp_path / 'profile')
    value = parse(profile.read_bytes())
    value['candidate_domains'] = {'baseline': {}}
    profile.write_bytes(encode(value))
    with pytest.raises(ValueError, match='no agent-editable'):
        from_profile(profile, instrument='temperature')


def test_temperature_profile_creation_is_inert_and_create_only(tmp_path, monkeypatch):
    from ciw import temperature_processing, temperature_workflow

    def forbidden(*args, **kwargs):
        pytest.fail('Creating a profile dispatched measurement processing')

    monkeypatch.setattr(temperature_processing, 'process_request', forbidden)
    monkeypatch.setattr(temperature_workflow, 'runtime_identity', forbidden)
    profile = temperature_config(tmp_path / 'profile')
    assert not (profile.parent / 'agent-output').exists()
    before = {p.name: p.read_bytes() for p in profile.parent.iterdir()}
    with pytest.raises(FileExistsError):
        temperature_config(profile.parent)
    assert before == {p.name: p.read_bytes() for p in profile.parent.iterdir()}


def test_temperature_restore_never_executes_the_processing_provider(tmp_path, monkeypatch):
    from ciw import temperature_processing, temperature_workflow
    profile = temperature_config(tmp_path / 'profile')
    host = from_profile(profile, instrument='temperature')
    result = host.call('net_execute', {'source': 'source', 'graph': 'baseline', 'attempt': 'first'})
    assert result['status'] == 'completed', result

    def forbidden(*args, **kwargs):
        pytest.fail('Restoring a workspace dispatched a processing provider')

    monkeypatch.setattr(temperature_processing, 'process_request', forbidden)
    monkeypatch.setattr(temperature_workflow, '_process', forbidden)
    monkeypatch.setattr(temperature_workflow, 'runtime_identity', forbidden)
    saved = profile.parent / 'agent-output/first/workspace.json'
    restored = Session.from_workspace(saved, tmp_path / 'restored')
    assert len(restored.results) == 1
    assert next(iter(restored.results.values()))['data']['authority'] == AUTHORITY


def test_source_envelope_cannot_relabel_declared_sensor_data(tmp_path):
    profile = temperature_config(tmp_path / 'profile')
    source = parse((profile.parent / 'source.json').read_bytes())
    source['channels']['measurement_declaration']['values'] = [2.0]
    from ciw.core.identities import evidence_id
    source['evidence_id'] = evidence_id(source)
    with pytest.raises(ValueError, match='exact retained'):
        source_request(source)


def test_temperature_pipeline_refuses_unspecified_operation_parameters(tmp_path):
    profile = temperature_config(tmp_path / 'profile')
    path = profile.parent / 'experiment.json'
    graph = parse(path.read_bytes())
    graph['nodes'][0]['parameters'] = {'coverage_factor': 1}
    seal(graph)
    path.write_bytes(encode(graph))
    host = from_profile(profile, instrument='temperature')
    result = host.call('net_execute', {'source': 'source', 'graph': 'baseline', 'attempt': 'bad-parameters'})
    assert result['status'] != 'completed'
    workspace = parse((profile.parent / 'agent-output/bad-parameters/workspace.json').read_bytes())
    assert workspace['results'] == []
    assert workspace['executions'][0]['status'] == 'refused'


def test_temperature_mcp_stdio_launch_processes_without_protocol_noise(tmp_path):
    profile = temperature_config(tmp_path / 'profile')
    messages = [
        {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
            'protocolVersion': VERSIONS[0], 'capabilities': {},
            'clientInfo': {'name': 'temperature-contract-test', 'version': '1'}}},
        {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
        {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {
            'name': 'net_execute', 'arguments': {'source': 'source', 'graph': 'baseline', 'attempt': 'first'}}},
    ]
    environment = os.environ.copy()
    from ciw import temperature_workflow
    environment['PYTHONPATH'] = str(Path(temperature_workflow.__file__).resolve().parents[1])
    result = subprocess.run([sys.executable, '-m', 'ciw.agent_mcp', 'serve', '--instrument', 'temperature',
                             '--profile', str(profile)], input=b'\n'.join(encode(v) for v in messages) + b'\n',
                            capture_output=True, timeout=30, env=environment)
    assert result.returncode == 0, result.stderr.decode()
    responses = {m['id']: m for m in map(json.loads, result.stdout.splitlines())}
    assert set(responses) == {1, 2}
    assert responses[2]['result']['isError'] is False
    assert responses[2]['result']['structuredContent']['status'] == 'completed'


def test_temperature_config_cli(tmp_path, capsys):
    assert main(['temperature-config', '--output-dir', str(tmp_path / 'profile')]) == 0
    assert Path(capsys.readouterr().out.strip()).is_file()


def test_temperature_config_accepts_operator_request_and_freezes_source(tmp_path, capsys):
    from ciw.temperature_contract import example_request
    request = example_request()
    request['identity']['cycle_id'] = 'operator-selected-cycle'
    input_path = tmp_path / 'input.json'
    input_path.write_bytes(encode(request))
    destination = tmp_path / 'profile'
    assert main(['temperature-config', '--output-dir', str(destination), '--request', str(input_path)]) == 0
    capsys.readouterr()
    source = parse((destination / 'source.json').read_bytes())
    assert source_request(source) == request
    request['identity']['cycle_id'] = 'changed-after-binding'
    input_path.write_bytes(encode(request))
    (destination / 'request.json').write_bytes(encode(request))
    host = from_profile(destination / 'profile.json', instrument='temperature')
    result = host.call('net_execute', {'source': 'source', 'graph': 'baseline', 'attempt': 'frozen'})
    assert result['status'] == 'completed', result
    workspace = parse((destination / 'agent-output/frozen/workspace.json').read_bytes())
    assert workspace['results'][0]['data']['measurement_identity']['cycle_id'] == 'operator-selected-cycle'
