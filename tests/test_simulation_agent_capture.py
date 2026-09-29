"""Capture grants, original Session/PNG evidence and MCP delivery; doubles only.

Native renderer acceptance belongs to the independent SDK integration driver.
"""
import base64
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ciw.agent_api import encode, parse
from ciw.agent_mcp import Server, from_profile as base_profile
from ciw.godot_capture import inspect_capture
from ciw.simulation_agent import Binding, SimulationAgentHost, demo_profiles, from_profile
from ciw.simulation_agent_capture import CaptureBinding, MAX_INLINE, compile_binding, observation_handle
from ciw.simulation_agent_tools import descriptions
from ciw.simulation_capture import CHANNELS, PROVIDER, OPERATION, validate_result
from ciw.simulation_records import observer
from ciw.simulation_timeline import build, inspect_bundle
from test_simulation_capture import PointContractDouble, RendererContractDouble, PNG, RUNTIME

POLICY = {'models': ['point'], 'cameras': ['oblique', 'front'], 'max_captures': 4, 'max_inline_bytes': MAX_INLINE}


@pytest.fixture
def lab(tmp_path):
    base, _ = demo_profiles(tmp_path / 'profiles')
    renderer = RendererContractDouble()
    renderer.runtime = deepcopy(RUNTIME)
    actions = {'actions': ['start', 'pause', 'resume', 'stop', 'step', 'observe', 'checkpoint'],
        'steps': {'tick': {'dt': 1}}, 'interventions': {},
        'observers': {'xyz': observer('xyz', kind='debugger', channels=CHANNELS),
                      'scalar': observer('scalar', kind='debugger', channels=['position_x'])}}
    host = SimulationAgentHost(base_profile(base), source='source',
        bindings={'point': Binding(PROVIDER, PointContractDouble, actions)},
        capture_binding=CaptureBinding(renderer, POLICY))
    instance = host.call('net_sim_create', {'model': 'point', 'attempt': 'create'})['instance']
    yield host, renderer, instance
    host.close()


def command(host, instance, action, attempt, preset=None):
    result = host.call('net_sim_command', {'instance': instance, 'expected': host.inspect(instance)['expected'],
        'action': action, 'attempt': attempt, 'preset': preset})
    assert result['status'] == 'completed', result
    return result


def observed(lab, *, preset='xyz', attempt='observe'):
    host, _, instance = lab
    return command(host, instance, 'observe', attempt, preset)


def capture_args(record, attempt='image', index=0, camera='oblique'):
    return {'observation': record['observation'], 'attempt': attempt, 'sample_index': index, 'camera': camera}


def test_actual_existing_capture_operation_source_isolation_and_bundle(lab, tmp_path):
    host, renderer, instance = lab
    record = observed(lab)
    before = deepcopy(host.session.results)
    view = host.inspect(instance)
    provider = host._providers[0]
    with patch.object(provider, 'snapshot', side_effect=AssertionError('source state cannot be read')), \
         patch.object(provider, 'step', side_effect=AssertionError('source must not step')):
        result = host.call('net_sim_capture', capture_args(record))
    assert result['status'] == 'completed' and renderer.calls == 1
    assert result['source_execution_id'] == record['execution_id']
    assert result['execution_id'] != record['execution_id']
    assert result['position_xyz_m'] == [1.25, 2.5, -3.75]
    assert host.inspect(instance) == view and len(host.session.executions) == 2
    assert all(host.session.results[k] == v for k, v in before.items())
    full = host.session.results[result['result_id']]
    assert full['operation_id'] == OPERATION
    validate_result(full, PNG)
    with patch('subprocess.Popen', side_effect=AssertionError('provider-free inspection')):
        assert inspect_capture(host._root / 'attempt-image')['status'] == 'retained_capture_checked'
        summary = build(tmp_path / 'timeline', captures=[host._root / 'attempt-image'])
        assert inspect_bundle(tmp_path / 'timeline')['summary'] == summary
    assert summary['unique_executions'] == 2 and summary['checked_images'] == 1


def test_renderer_only_receives_original_observation_projection(lab):
    host, renderer, _ = lab
    result = host.call('net_sim_capture', capture_args(observed(lab)))
    assert result['status'] == 'completed'
    request = encode(renderer.request)
    for forbidden in (b'snapshot_b64', b'configuration', b'velocity', b'queued'):
        assert forbidden not in request
    for raw in host.host._artifacts.values():
        assert b'snapshot_b64' not in raw and b'ciw.simulation-observation-capture.v1' not in raw
    inspected = host.call('net_inspect', {'artifact': result['image']['artifact_id']})
    assert inspected['data']['media_type'] == 'image/png'
    assert inspected['data']['metadata']['semantics'] == 'derived_visualization'


def test_capture_old_observation_after_source_stops_and_retry_after_close(lab):
    host, renderer, instance = lab
    source = observed(lab)
    command(host, instance, 'stop', 'stop')
    args = capture_args(source)
    first = host.call('net_sim_capture', args)
    n = len(host.session.executions)
    assert host.call('net_sim_capture', args) == first
    host.close()
    assert host.call('net_sim_capture', args) == first
    assert host.image_content('net_sim_capture', first)[0]['data'] == base64.b64encode(PNG).decode()
    assert len(host.session.executions) == n and renderer.calls == 1 and host._capture_reserved == 1


def test_changed_retry_and_new_intent_have_different_semantics(lab):
    host, renderer, _ = lab
    args = capture_args(observed(lab))
    first = host.call('net_sim_capture', args)
    with pytest.raises(ValueError, match='different request'):
        host.call('net_sim_capture', {**args, 'camera': 'front'})
    second = host.call('net_sim_capture', {**args, 'camera': 'front', 'attempt': 'front'})
    assert second['status'] == 'completed' and first['execution_id'] != second['execution_id']
    assert first['source_result_ref'] == second['source_result_ref']
    assert renderer.calls == 2 and host._capture_reserved == 2


@pytest.mark.parametrize('mode', ['index', 'null', 'scalar', 'camera', 'budget', 'runtime', 'changed-source'])
def test_preflight_rejections_never_render_or_create_simulation_occurrences(lab, mode):
    host, renderer, instance = lab
    source = observed(lab, preset='scalar' if mode == 'scalar' else 'xyz')
    args = capture_args(source)
    if mode == 'index': args['sample_index'] = 15
    elif mode == 'null': args['sample_index'] = None
    elif mode == 'camera': args['camera'] = 'ungranted'
    elif mode == 'budget': host._capture_reserved = POLICY['max_captures']
    elif mode == 'runtime': renderer.runtime['worker_sha256'] = 'sha256:' + 'e' * 64
    elif mode == 'changed-source':
        handle = host._capture_observations[source['observation']]
        handle['result_ref'] = 'sha256:' + 'e' * 64
    before = len(host.session.executions)
    with patch.object(renderer, 'render', side_effect=AssertionError('no render')):
        response = host.call('net_sim_capture', args)
    assert response['status'] == 'refused' and response['dispatch_performed'] is False
    assert len(host.session.executions) == before and not host._blocked
    assert host.call('net_sim_capture', args) == response
    assert not (host._root / 'attempt-image/capture.json').exists()
    command(host, instance, 'stop', 'healthy-stop')


@pytest.mark.parametrize('mode', ['empty', 'partial'])
def test_unavailable_and_partial_xyz_never_impute_coordinates(lab, mode):
    host, renderer, _ = lab
    setattr(host._providers[0], 'empty' if mode == 'empty' else 'missing', True)
    result = host.call('net_sim_capture', capture_args(observed(lab), index=None if mode == 'empty' else 0))
    assert result['status'] == 'completed' and result['position_xyz_m'] is None
    assert result['availability'] == ('no_samples' if mode == 'empty' else 'missing_components')
    assert renderer.request['view']['position_xyz_m'] is None
    assert parse((host._root / 'attempt-image/native.json').read_bytes())['marker_count'] == 0


def test_native_render_refusal_is_original_capture_occurrence_and_source_stays_healthy(lab):
    host, renderer, instance = lab
    args = capture_args(observed(lab))
    with patch.object(renderer, 'render', side_effect=ValueError('no display')):
        response = host.call('net_sim_capture', args)
    assert response['status'] == 'refused' and response['dispatch_performed'] is True
    assert host.session.executions[response['execution_id']]['status'] == 'refused'
    assert response['result_id'] is None and host._capture_reserved == 1 and not host._blocked
    assert not (host._root / 'attempt-image/capture.json').exists()
    assert host.image_content('net_sim_capture', response) == []
    command(host, instance, 'start', 'can-still-start')


@pytest.mark.parametrize('phase', ['source-workspace', 'workspace', 'capture-selection.json', 'capture.json', 'response.json'])
def test_storage_failure_does_not_repeat_render_on_retry(lab, phase):
    host, renderer, _ = lab
    args = capture_args(observed(lab))
    if phase in ('source-workspace', 'workspace'):
        original = host.session.save_workspace
        def fail(path):
            if path.name == phase + '.json': raise OSError('disk unavailable')
            return original(path)
        context = patch.object(host.session, 'save_workspace', fail)
    else:
        module = 'ciw.simulation_agent' if phase == 'response.json' else 'ciw.simulation_agent_capture'
        from ciw.control_contracts import save_new
        def fail(path, value):
            if path.name == phase: raise OSError('disk unavailable')
            return save_new(path, value)
        context = patch(module + '.save_new', fail)
    with context:
        result = host.call('net_sim_capture', args)
    assert result['status'] in ('failed', 'incomplete') and host._blocked
    n = renderer.calls
    assert host.call('net_sim_capture', args) == result and renderer.calls == n
    assert host.image_content('net_sim_capture', result) == []
    if phase == 'workspace': assert not (host._root / 'attempt-image/capture.json').exists()
    if phase == 'response.json': assert (host._root / 'attempt-image/capture.json').exists()


def test_exact_source_selection_and_reservation_written_before_renderer(lab):
    host, renderer, _ = lab
    args = capture_args(observed(lab))
    original = renderer.render
    def checked(view, camera):
        root = host._root / 'attempt-image'
        assert (root / 'request.json').is_file() and (root / 'source-workspace.json').is_file()
        assert parse((root / 'capture-selection.json').read_bytes())['reserved_captures'] == 1
        assert not (root / 'capture.json').exists()
        return original(view, camera)
    with patch.object(renderer, 'render', checked):
        assert host.call('net_sim_capture', args)['status'] == 'completed'


def test_large_valid_png_uses_explicit_operator_only_delivery_not_silent_resize(lab):
    host, renderer, _ = lab
    host._capture_policy['max_inline_bytes'] = 1
    result = host.call('net_sim_capture', capture_args(observed(lab)))
    assert result['status'] == 'completed' and result['image_delivery'] == 'operator_bundle_only'
    assert result['image_size_bytes'] == len(PNG) and host._capture_images == {}
    assert host.image_content('net_sim_capture', result) == []
    assert inspect_capture(host._root / 'attempt-image')['image_sha256'] == result['image_sha256']


def test_changed_inline_bytes_or_receipt_never_delivers_unbound_image(lab):
    host, _, _ = lab
    result = host.call('net_sim_capture', capture_args(observed(lab)))
    altered = {**result, 'image_sha256': 'sha256:' + '0' * 64}
    with pytest.raises(ValueError, match='receipt'): host.image_content('net_sim_capture', altered)
    host._capture_images[result['result_id']] = b'changed'
    with pytest.raises(ValueError, match='image changed'): host.image_content('net_sim_capture', result)


@pytest.mark.parametrize('key,value', [('observation','/tmp/source'), ('camera','../../camera'),
    ('sample_index',True), ('sample_index',-1), ('sample_index',256), ('attempt','/bin/sh'),
    ('coordinates',[1,2,3]), ('executable','/bin/sh'), ('image_uri','https://example.invalid')])
def test_argument_injection_rejected_before_execution(lab, key, value):
    host, renderer, _ = lab
    args = capture_args(observed(lab)); args[key] = value
    before = len(host.session.executions)
    with pytest.raises(ValueError): host.call('net_sim_capture', args)
    assert renderer.calls == 0 and host._capture_reserved == 0 and len(host.session.executions) == before


@pytest.mark.parametrize('key,value', [('models',[]), ('models',['missing']), ('models',['point','point']),
    ('cameras',['unknown']), ('cameras',[]), ('max_captures',True), ('max_captures',0),
    ('max_captures',9), ('max_inline_bytes',-1), ('max_inline_bytes',MAX_INLINE+1),
    ('max_inline_bytes',True), ('code','arbitrary')])
def test_invalid_capture_grants_refuse(key, value):
    policy = {**deepcopy(POLICY), key: value}
    with pytest.raises(ValueError):
        compile_binding(CaptureBinding(RendererContractDouble(), policy), {'point': object()})


def test_grants_are_frozen_and_catalog_extensions_are_independent(lab):
    host, _, _ = lab
    cap = host.capabilities()
    cap['stateful']['capture']['grants']['cameras'].clear()
    assert host.capabilities()['stateful']['capture']['grants']['cameras'] == ['oblique', 'front']
    assert len(descriptions()) == 4
    assert len(descriptions(include_capture=True)) == 5
    assert len(descriptions(include_capture=True, include_replay=True, include_campaign=True)) == 7
    assert host.capabilities()['stateful']['capture']['reserved_captures'] == 0


def test_original_profile_has_no_new_handles_grant_or_tool(tmp_path):
    base, profile = demo_profiles(tmp_path / 'old')
    with from_profile(base_profile(base), profile) as host:
        assert not host.capture_enabled and 'capture' not in host.capabilities()['stateful']
        i = host.call('net_sim_create', {'model':'motion','attempt':'new'})['instance']
        source = command(host, i, 'observe', 'o', 'position')
        assert 'observation' not in source
        with pytest.raises(ValueError, match='not granted'):
            host.call('net_sim_capture', {'observation':'o-x','camera':'front','sample_index':0,'attempt':'x'})


def test_same_observation_is_named_once_and_handles_do_not_retain_full_state(lab):
    host, _, _ = lab
    result = observed(lab)
    full = host.session.results[result['result_id']]
    assert observation_handle(host, full) == {'observation':result['observation']}
    assert len(host._capture_handles) == 1
    assert set(host._capture_observations[result['observation']]) == {'model','result_id','result_ref'}


def test_mcp_delivers_actual_image_content_plus_unchanged_structured_metadata(lab):
    host, renderer, _ = lab
    args = capture_args(observed(lab))
    server = Server(host, extra_tools=descriptions(include_capture=True), image_content=host.image_content)
    def rpc(i, method, params):
        return server.handle(encode({'jsonrpc':'2.0','id':i,'method':method,'params':params}))['result']
    rpc(1,'initialize',{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'test','version':'1'}})
    server.handle(encode({'jsonrpc':'2.0','method':'notifications/initialized'}))
    assert len(rpc(2,'tools/list',{})['tools']) == 16
    result = rpc(3,'tools/call',{'name':'net_sim_capture','arguments':args})
    assert not result['isError'] and len(result['content']) == 2
    assert parse(result['content'][0]['text'].encode()) == result['structuredContent']
    image = result['content'][1]
    assert image['type'] == 'image' and image['mimeType'] == 'image/png'
    assert base64.b64decode(image['data'],validate=True) == PNG
    assert len(encode(result)) < 1024 * 1024
    assert rpc(4,'tools/call',{'name':'net_sim_capture','arguments':args}) == result
    assert renderer.calls == 1


def test_profile_binding_and_native_example_do_not_launch_process(tmp_path):
    from ciw.simulation_agent_capture import native_demo_profile
    executable = tmp_path / 'godot'; executable.write_bytes(b'pinned-test-double')
    from ciw.control_contracts import bytes_ref
    pin = bytes_ref(executable.read_bytes())
    base, profile = demo_profiles(tmp_path / 'capture', campaign=True, replay=True)
    with patch('subprocess.Popen',side_effect=AssertionError('no startup process')):
        native = native_demo_profile(parse(profile.read_bytes()),executable,pin)
        profile.write_bytes(encode(native))
        with from_profile(base_profile(base),profile) as host:
            assert host.capture_enabled and host.campaign_enabled and host.replay_enabled
            assert host.session.executions == {} and host._providers == []
            assert host._bindings['motion'].policy['observers']['xyz']['channels'] == CHANNELS
            assert host._campaign_policy['templates']['impulses']['arguments']['quantity'] == 'position_x'


def test_capture_cli_requires_explicit_pinned_native_and_no_output_on_bad_pin(tmp_path):
    from ciw.net import main
    dest = tmp_path / 'bad'
    with pytest.raises(SystemExit): main(['agent','demo-config','--stateful-capture','--output-dir',str(dest)])
    assert not dest.exists()
    binary = tmp_path / 'godot'; binary.write_bytes(b'x')
    assert main(['agent','demo-config','--stateful','--stateful-capture','--godot',str(binary),
        '--godot-sha256','sha256:'+'0'*64,'--output-dir',str(dest)]) == 1
    assert not dest.exists()


def test_large_inline_image_uses_transport_not_scientific_string_budget(lab):
    from hashlib import shake_256
    from test_simulation_capture import native_for, test_png
    from ciw.simulation_capture import render_request
    host, renderer, _ = lab
    args = capture_args(observed(lab))
    rows = b''.join(b'\0' + (shake_256(str(i).encode()).digest(3840) if i < 18 else b'\0' * 3840) for i in range(800))
    png = test_png(pixels=rows)
    assert 65536 < len(base64.b64encode(png)) < 200000
    def large(view, camera):
        request = render_request(view, camera, 'a' * 32)
        native = native_for(request, png=png)
        renderer.last_native, renderer.last_png = encode(native), png
        return native, png
    server = Server(host, extra_tools=descriptions(include_capture=True), image_content=host.image_content)
    server.initialized = True
    with patch.object(renderer, 'render', large):
        result = server.handle(encode({'jsonrpc':'2.0','id':1,'method':'tools/call',
            'params':{'name':'net_sim_capture','arguments':args}}))['result']
    assert result['isError'] is False, result
    assert base64.b64decode(result['content'][1]['data'],validate=True) == png
    # Scientific records keep their original per-string bound.
    with pytest.raises(ValueError, match='text exceeds bound'):
        encode({'not_an_image': 'x' * 65537})
