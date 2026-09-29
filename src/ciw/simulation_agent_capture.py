"""Agent-selected retained images through the existing capture operation.

Only an operator binds a renderer. Observation handles resolve original Session
results, not snapshots or agent-supplied coordinates. PNG delivery is optional
MCP content; the original artifact/result remain the retained evidence.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
import uuid

from .agent_api import identifier
from .control_contracts import bytes_ref, detached, keys, save_new
from .godot_capture import bind_renderer, read_bounded
from .simulation_capture import (
    MAX_IMAGE, OPERATION, VIEW_SCOPE, project, selection, validate_dependencies,
    validate_result, validate_runtime,
)
from .simulation_records import require

MAX_INLINE = 196608  # <=256 KiB base64, independent of 4 MiB artifact limit.
MAX_OBSERVATIONS = 256


@dataclass(frozen=True)
class CaptureBinding:
    """Trusted installed renderer object; no executable selected by a tool call."""
    renderer: object
    policy: dict


def compile_binding(binding: CaptureBinding | None, models: dict) -> tuple[object | None, dict | None]:
    if binding is None:
        return None, None
    require(isinstance(binding, CaptureBinding) and callable(getattr(binding.renderer, 'render', None)),
            'An explicit trusted capture renderer is required')
    value = detached(binding.policy)
    keys(value, {'models', 'cameras', 'max_captures', 'max_inline_bytes'})
    for key in ('models', 'cameras'):
        require(type(value[key]) is list and 1 <= len(value[key]) <= 8,
                'Capture models/cameras must be bounded nonempty lists')
        for item in value[key]:
            identifier(item)
        require(len(set(value[key])) == len(value[key]), 'Duplicate capture model or camera')
    require(set(value['models']) <= set(models), 'Capture model is not operator-bound')
    require(set(value['cameras']) <= {'oblique', 'front'}, 'Unsupported capture camera')
    require(type(value['max_captures']) is int and 1 <= value['max_captures'] <= 8,
            'Capture budget must be 1..8')
    require(type(value['max_inline_bytes']) is int and 0 <= value['max_inline_bytes'] <= MAX_INLINE,
            'Inline image budget must be 0..196608 bytes')
    validate_runtime(binding.renderer.runtime)
    return binding.renderer, {**value, 'runtime': detached(binding.renderer.runtime)}


def observation_handle(host, result: dict) -> dict:
    """Name an original observation already disclosed through this agent host."""
    if not host.capture_enabled:
        return {}
    instance_id = result['data']['after']['instance_id']
    model = next((m for m, w in host._instances.values() if w.instance_id == instance_id), None)
    if model not in host._capture_policy['models']:
        return {}
    require(host.session.results.get(result['result_id']) == result,
            'Observation is not an original retained Session result')
    key = result['result_id']
    if key not in host._capture_handles:
        require(len(host._capture_handles) < MAX_OBSERVATIONS, 'Capture observation handle budget exhausted')
        handle = 'o-' + uuid.uuid4().hex
        host._capture_handles[key] = handle
        host._capture_observations[handle] = {'model': model, 'result_id': key,
                                             'result_ref': result['record_digest']}
    return {'observation': host._capture_handles[key]}


def request_capture(host, observation: str, camera: str, sample_index: int | None, attempt: str) -> dict:
    """Render one immutable selected observation; never call its source provider."""
    require(host.capture_enabled, 'Image capture was not granted by the operator')
    for value in (observation, camera, attempt):
        identifier(value)
    require(observation in host._capture_observations, 'Unknown host-disclosed observation handle')
    require(sample_index is None or (type(sample_index) is int and 0 <= sample_index < 256),
            'Select a bounded sample index or null for unavailable')
    arguments = detached({'observation': observation, 'camera': camera,
                          'sample_index': sample_index, 'attempt': attempt})
    directory = host._root / ('attempt-' + attempt)
    pending = {}

    def execute():
        try:
            ref = host._capture_observations[observation]
            require(ref['model'] in host._capture_policy['models'], 'Observation model is not capture-granted')
            require(camera in host._capture_policy['cameras'], 'Camera was not granted by the operator')
            require(host._capture_reserved < host._capture_policy['max_captures'], 'Capture reservation budget exhausted')
            require(host._capture_renderer.runtime == host._capture_policy['runtime'], 'Capture runtime changed after binding')
            source = host.session.results.get(ref['result_id'])
            require(source is not None and source['record_digest'] == ref['result_ref'], 'Retained observation binding changed')
            selected = selection(source, entity_id='projectile', sample_index=sample_index, camera=camera)
            project(source, selected)  # Original XYZ/missingness checks, no renderer.
        except ValueError as exc:
            return {'status': 'refused', 'dispatch_performed': False,
                    'refusal': {'code': 'simulation_capture_preflight', 'message': str(exc)}}
        host._capture_reserved += 1
        host.session.save_workspace(directory / 'source-workspace.json')
        raw = read_bounded(directory / 'source-workspace.json')
        selected = selection(source, entity_id='projectile', sample_index=sample_index,
                             camera=camera, source_workspace_sha256=bytes_ref(raw))
        save_new(directory / 'capture-selection.json', {'schema': 'ciw.simulation-agent-capture-selection.v1',
            'observation': observation, 'selection': selected, 'policy_ref': host._policy_ref,
            'reserved_captures': host._capture_reserved})
        renderer = host._capture_renderer
        if not host._capture_bound:
            bind_renderer(host.session, renderer, host._root / 'images')
            host._capture_bound = True
        renderer.last_log, renderer.last_native, renderer.last_png = b'', None, None
        try:
            receipt = host.session.handle({'protocol_version': 1, 'request_id': 'agent-' + attempt,
                'type': 'operation.execute', 'payload': {'operation_id': OPERATION, 'parameters': selected}})
            save_new(directory / 'dispatch.json', receipt)
            require(receipt.get('type') == 'response', 'Capture Session publication failed')
            payload = receipt['payload']
            execution = payload['execution']
            if payload['status'] != 'completed':
                return {'status': payload['status'], 'dispatch_performed': True,
                        'execution_id': execution['execution_id'], 'result_id': None,
                        'refusal': detached(execution['refusal'])}
            result = payload['result']
            image = result['data']['image']
            filename = image['sha256'].split(':', 1)[1] + '.png'
            png = read_bounded(host._root / 'images' / filename, MAX_IMAGE)
            validate_result(result, png)
            validate_dependencies(host.session)
            (directory / 'images').mkdir(exist_ok=False)
            with (directory / 'images' / filename).open('xb') as output:
                output.write(png)
            pending['result'] = detached(result)
            view = result['data']['view']
            inline = len(png) <= host._capture_policy['max_inline_bytes']
            # Never put the full capture/result or checkpoint into AgentHost's
            # inspectable artifacts. The original image descriptor contains no bytes.
            artifact = host.host._retain(image)
            if inline:
                host._capture_images[result['result_id']] = png
            return {'status': 'completed', 'dispatch_performed': True,
                'observation': observation, 'source_execution_id': source['execution_id'],
                'source_result_ref': source['record_digest'], 'execution_id': result['execution_id'],
                'result_id': result['result_id'], 'result_ref': result['record_digest'],
                'image': artifact, 'image_sha256': image['sha256'], 'image_size_bytes': len(png),
                'image_delivery': 'inline_mcp' if inline else 'operator_bundle_only',
                'camera': camera, 'sample_time_s': view['sample_time_s'],
                'available_at': deepcopy(view['available_at']), 'availability': view['availability'],
                'position_xyz_m': deepcopy(view['position_xyz_m']), 'claim_scope': VIEW_SCOPE}
        finally:
            (directory / 'render.log').write_bytes(renderer.last_log)
            if renderer.last_native is not None:
                (directory / 'native.json').write_bytes(renderer.last_native)
            if renderer.last_png is not None:
                (directory / 'native-image.png').write_bytes(renderer.last_png)

    def finalize():
        # Reuse the original inspect_capture bundle layout. This completion comes
        # after workspace publication, before the agent response is published.
        save_new(directory / 'capture.json', pending['result'])

    return host._attempt('net_sim_capture', arguments, execute, after_workspace=finalize)


def image_content(host, name: str, response: dict) -> list[dict]:
    """Additional MCP content from an exact completed receipt, never raw paths."""
    if name != 'net_sim_capture' or response.get('status') != 'completed' or response.get('image_delivery') != 'inline_mcp':
        return []
    require(host._attempts[response['attempt']]['response'] == response, 'Image delivery differs from retained receipt')
    png = host._capture_images[response['result_id']]
    require(bytes_ref(png) == response['image_sha256'], 'Retained inline image changed')
    require(len(png) <= host._capture_policy['max_inline_bytes'], 'Inline image exceeds fixed transport budget')
    return [{'type': 'image', 'mimeType': 'image/png', 'data': base64.b64encode(png).decode('ascii')}]


def from_profile(value: dict, root: Path) -> CaptureBinding:
    """Only the operator startup profile supplies paths and pinned native code."""
    from .godot_capture import GodotObservationRenderer
    keys(value, {'executable', 'sha256', 'timeout_s', 'models', 'cameras', 'max_captures', 'max_inline_bytes'})
    require(type(value['executable']) is str and value['executable'], 'Capture executable must be operator-selected')
    renderer = GodotObservationRenderer(root / value['executable'], value['sha256'], timeout=value['timeout_s'])
    return CaptureBinding(renderer, {k: value[k] for k in ('models', 'cameras', 'max_captures', 'max_inline_bytes')})


def native_demo_profile(value: dict, executable: Path, pin: str) -> dict:
    """Extend the example with native presets; old scalar presets remain explicit."""
    from .simulation_records import observer
    from .simulation_capture import CHANNELS
    native = {'executable': str(Path(executable).resolve(strict=True)), 'sha256': pin}
    binding = from_profile({**native, 'timeout_s': 60, 'models': ['motion'],
        'cameras': ['oblique', 'front'], 'max_captures': 8, 'max_inline_bytes': MAX_INLINE}, Path('.'))
    model = value['models']['motion']
    model.update(provider='godot-point', configuration=native)
    policy = model['policy']
    policy['steps'] = {'tick': {'dt': 1 / 64}}
    policy['observers'] = {
        'position': observer('position', kind='debugger', channels=['position_x']),
        'delayed': observer('delayed', kind='embodied_agent', channels=['position_x']),
        'xyz': observer('xyz', kind='debugger', channels=CHANNELS),
        'xyz-delayed': observer('xyz-delayed', kind='embodied_agent', channels=CHANNELS)}
    policy['interventions'] = {'push': {'actor_id': 'operator-granted-agent',
        'operation': 'projectile.queue-impulse.v1', 'target': 'projectile',
        'parameters': {'at_tick': 3, 'delta_v_m_s': [2, 0, 0]}}}
    for template in value.get('campaigns', {}).get('templates', {}).values():
        template['quantity'] = 'position_x'
    value['capture'] = {**native, 'timeout_s': 60, **detached(binding.policy)}
    return value
