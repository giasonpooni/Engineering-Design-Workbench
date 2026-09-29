"""Official MCP SDK -> existing stdio server -> native observation PNG.

Requires the explicitly pinned Godot runtime and a real graphical display.
No LLM is invoked; small images arrive as actual MCP ImageContent, not URLs.
"""
from __future__ import annotations
import argparse
import asyncio
import base64
from importlib.metadata import version
import json
from pathlib import Path
import sys
from unittest.mock import patch

from ciw.agent_api import encode, parse
from ciw.control_contracts import bytes_ref
from ciw.godot_capture import inspect_capture
from ciw.simulation_agent import demo_profiles
from ciw.simulation_agent_capture import native_demo_profile
from ciw.simulation_capture import png_info
from ciw.simulation_control import open_workspace
from ciw.simulation_timeline import build, inspect_bundle


async def run(root: Path, godot: Path, pin: str) -> dict:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    base, simulation = demo_profiles(root / 'profiles', replay=True, campaign=True)
    profile = native_demo_profile(parse(simulation.read_bytes()), godot, pin)
    profile['capture']['max_captures'] = 4
    simulation.write_bytes(encode(profile))
    checks, transcript, received = [], [], {}
    (root / 'received').mkdir()
    def check(condition, name):
        if not condition:
            raise AssertionError(name)
        checks.append(name)
    params = StdioServerParameters(command=sys.executable, args=['-I', '-m', 'ciw.agent_mcp',
        'serve', '--profile', str(base), '--simulation-profile', str(simulation)])
    with (root / 'server-stderr.log').open('w', encoding='utf-8') as error_log:
        async with stdio_client(params, errlog=error_log) as (reader, writer):
            async with ClientSession(reader, writer) as client:
                init = await client.initialize()
                check(init.protocolVersion == '2025-11-25', 'original_protocol_negotiated')
                tools = await client.list_tools()
                check(len(tools.tools) == 18 and 'net_sim_capture' in {t.name for t in tools.tools}, 'independent_opt_in_eighteen_tool_catalog')
                async def call(name, **args):
                    response = await client.call_tool(name, args)
                    result = response.structuredContent
                    assert json.loads(response.content[0].text) == result
                    images = []
                    for item in response.content[1:]:
                        assert item.type == 'image' and item.mimeType == 'image/png'
                        png = base64.b64decode(item.data, validate=True)
                        assert png_info(png)['width'] == 1280
                        sha = bytes_ref(png)
                        assert result['image_sha256'] == sha
                        path = root / 'received' / (sha.split(':')[1] + '.png')
                        if path.exists():
                            assert path.read_bytes() == png
                        else:
                            path.write_bytes(png)
                        received[result['result_id']] = png
                        images.append({'sha256': sha, 'size_bytes': len(png), 'mimeType': item.mimeType})
                    transcript.append({'tool': name, 'arguments': args, 'result': result,
                                       'isError': response.isError, 'images': images})
                    (root / 'transcript.json').write_bytes(encode({'calls': transcript}))
                    return result, response.isError, images
                async def command(instance, action, attempt, preset=None):
                    view, error, _ = await call('net_sim_inspect', instance=instance)
                    assert not error
                    result, error, _ = await call('net_sim_command', instance=instance,
                        expected=view['expected'], action=action, attempt=attempt, preset=preset)
                    assert not error, result
                    return result
                cap, _, _ = await call('net_capabilities')
                check(cap['stateful']['capture']['reserved_captures'] == 0 and cap['stateful']['instances'] == {}, 'discovery_does_not_launch_or_render')
                created, error, _ = await call('net_sim_create', model='motion', attempt='create')
                check(not error and created['attachment_only'] and created['execution_id'] is None, 'original_native_attachment')
                instance = created['instance']
                empty = await command(instance, 'observe', 'empty', 'xyz-delayed')
                await command(instance, 'start', 'start')
                for index in range(10):
                    await command(instance, 'step', 'step-' + str(index), 'tick')
                await command(instance, 'pause', 'pause')
                current = await command(instance, 'observe', 'current', 'xyz')
                delayed = await command(instance, 'observe', 'delayed', 'xyz-delayed')
                scalar = await command(instance, 'observe', 'scalar', 'position')
                cp = await command(instance, 'checkpoint', 'checkpoint')
                await command(instance, 'stop', 'stop-source')
                before, _, _ = await call('net_sim_inspect', instance=instance)
                check(before['status'] == 'stopped', 'source_stopped_before_capture')
                check(all(x['observation'].startswith('o-') for x in (current, delayed, empty)), 'original_observations_have_opaque_handles')
                bad, error, images = await call('net_sim_capture', observation=cp['checkpoint'], sample_index=0, camera='front', attempt='not-observation')
                check(error and not images, 'checkpoint_cannot_be_used_as_observation_handle')
                for record, sample, attempt in ((scalar, 0, 'scalar-refusal'), (current, 200, 'index-refusal')):
                    bad, error, images = await call('net_sim_capture', observation=record['observation'], sample_index=sample, camera='oblique', attempt=attempt)
                    check(error and bad['dispatch_performed'] is False and not images, attempt + '_before_render')
                captures = []
                for name, record, sample, camera in (('current', current, 10, 'oblique'),
                        ('delayed', delayed, 8, 'oblique'), ('unavailable', empty, None, 'oblique'),
                        ('front', current, 10, 'front')):
                    args = {'observation': record['observation'], 'sample_index': sample, 'camera': camera, 'attempt': 'image-' + name}
                    result, error, images = await call('net_sim_capture', **args)
                    check(not error and result['status'] == 'completed' and len(images) == 1
                          and result['image_delivery'] == 'inline_mcp', name + '_actual_mcp_png')
                    check(result['source_execution_id'] == record['execution_id']
                          and result['execution_id'] != record['execution_id'], name + '_distinct_capture_occurrence')
                    captures.append((name, args, result, images))
                current_image, delayed_image, empty_image, front_image = [item[2] for item in captures]
                check(current_image['sample_time_s'] == 10/64 and delayed_image['sample_time_s'] == 8/64
                    and delayed_image['available_at']['time_s'] == 10/64, 'sample_and_delivery_times_preserved')
                check(empty_image['availability'] == 'no_samples' and empty_image['position_xyz_m'] is None
                      and empty_image['sample_time_s'] is None, 'unavailable_is_not_a_zero_position')
                check(front_image['source_result_ref'] == current_image['source_result_ref']
                      and front_image['position_xyz_m'] == current_image['position_xyz_m'], 'camera_change_preserves_original_coordinates')
                again, error, images = await call('net_sim_capture', **captures[0][1])
                check(not error and again == current_image and images == captures[0][3], 'identical_retry_delivers_same_receipt_and_png')
                over, error, images = await call('net_sim_capture', **{**captures[0][1], 'attempt': 'over-budget'})
                cap, _, _ = await call('net_capabilities')
                check(error and over['dispatch_performed'] is False and not images
                      and cap['stateful']['capture']['reserved_captures'] == 4, 'exhausted_budget_does_not_render')
                after, _, _ = await call('net_sim_inspect', instance=instance)
                check(after == before and len(cap['stateful']['instances']) == 1, 'capture_does_not_change_source_or_attach_simulation')
                image_record, error, _ = await call('net_inspect', artifact=current_image['image']['artifact_id'])
                check(not error and image_record['data']['metadata']['semantics'] == 'derived_visualization', 'original_image_artifact_inspection')
                check('snapshot_b64' not in json.dumps(transcript), 'no_checkpoint_bytes_in_agent_transcript')
    stateful = root / 'profiles/agent-output/stateful'
    with patch('subprocess.Popen', side_effect=AssertionError('retained checks cannot execute')):
        loaded = open_workspace(stateful / 'workspace.json', output_dir=root / 'reader')
        directories = [stateful / ('attempt-image-' + name) for name, *_ in captures]
        for directory, (_, _, result, _) in zip(directories, captures):
            checked = inspect_capture(directory)
            assert checked['image_sha256'] == result['image_sha256']
            filename = result['image_sha256'].split(':')[1] + '.png'
            assert (directory / 'images' / filename).read_bytes() == received[result['result_id']]
        summary = build(root / 'timeline', workspaces=[stateful / 'workspace.json'], captures=directories)
        assert inspect_bundle(root / 'timeline')['summary'] == summary
    check(len(loaded.executions) == len(loaded.results) == 22, 'eighteen_source_plus_four_capture_occurrences')
    check(summary['instance_count'] == 1 and summary['checked_images'] == 4, 'original_timeline_links_all_four_images')
    check(parse((stateful / 'shutdown.json').read_bytes())['status'] == 'closed', 'native_owner_cleanup_retained')
    report = {'status': 'passed', 'check_count': len(checks), 'checks': checks,
        'client': 'official MCP Python SDK', 'client_version': version('mcp'),
        'provider': 'godot-point', 'renderer': 'godot-4.5.2-gl-compatibility',
        'protocol_version': init.protocolVersion, 'image_count': 4,
        'stateful_execution_count': len(loaded.executions), 'timeline': summary, 'no_llm_invoked': True}
    (root / 'report.json').write_bytes(encode(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--godot', type=Path, required=True)
    parser.add_argument('--godot-sha256', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    root = args.output_dir.absolute()
    root.mkdir(exist_ok=False)
    try:
        result = asyncio.run(run(root, args.godot, args.godot_sha256))
    except Exception as exc:
        (root / 'report.json').write_text(json.dumps({'status': 'failed', 'reason': str(exc)}), encoding='utf-8')
        raise
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
