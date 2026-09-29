"""Actual local vision-model -> fixed MCP -> original Docker/Godot trial.

Provisioning is an operator action outside the agent loop. Model rejection is a
valid measured outcome, not a reason to rewrite its answer or relax a gate.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys
import urllib.request

from ciw.agent_local_model import endpoint
from ciw.agent_unattended import inspect
from ciw.control_contracts import bytes_ref, save_new
from ciw.workcell_title import configure


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--endpoint', required=True)
    p.add_argument('--model', required=True)
    p.add_argument('--server-version', required=True)
    p.add_argument('--title-root', type=Path, required=True)
    p.add_argument('--source-profile', type=Path, required=True)
    p.add_argument('--profile-sha256', required=True)
    p.add_argument('--docker', type=Path, required=True)
    p.add_argument('--image-id', required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    args = p.parse_args()
    endpoint(args.endpoint)
    root = args.output_dir.absolute(); root.mkdir(parents=True, exist_ok=False)
    # Explicit operator selection from already provisioned local inventory; no pull or fallback.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(args.endpoint + '/api/tags', timeout=10) as response:
        tags = json.loads(response.read(1024*1024))
    selected = [row for row in tags['models'] if row['name'] == args.model]
    if len(selected) != 1:
        raise ValueError('Requested local model has not been provisioned')
    save_new(root/'operator-model-inventory.json', tags)
    model = {'schema': 'ciw.local-model-profile.v1', 'endpoint': args.endpoint,
             'model': args.model, 'model_digest': 'sha256:' + selected[0]['digest'].removeprefix('sha256:'),
             'server_version': args.server_version, 'num_ctx': 16384, 'num_predict': 768,
             'max_calls': 2, 'max_total_tokens': 36000, 'timeout_s': 600, 'vision': True, 'pricing': None}
    task = {'schema': 'ciw.unattended-task.v1',
            'goal': 'Inspect the actual daylight and evening images. Make ONE minimal material/color edit to improve the separation of bench timber and iron in workshop_world.gd. Do not add geometry, nodes or new materials; reuse the existing material constructors. Keep mechanics, colliders, camera, lighting and all other behavior unchanged. After that revision is built, inspect its returned evidence and STOP. This is an experiment; a justified stop without an edit is allowed. Return the action JSON only.',
            'editable_paths': ['workshops/workshop_world.gd'],
            'context_paths': ['workshops/workshop_world.gd', 'presentation/workshop_kit.gd'],
            'max_revisions': 1, 'stop_after_accept': False}
    save_new(root/'model.json', model); save_new(root/'task.json', task)
    host = configure(title_root=args.title_root, profile=args.source_profile,
                     profile_sha256=args.profile_sha256, docker=args.docker, image_id=args.image_id,
                     output_dir=root/'operator-workcell', allow_package=True)
    command = [sys.executable, '-I', '-m', 'ciw.agent_unattended', 'run',
               '--workcell-profile', str(host), '--workcell-profile-sha256', bytes_ref(host.read_bytes()),
               '--model-profile', str(root/'model.json'), '--model-profile-sha256', bytes_ref((root/'model.json').read_bytes()),
               '--task', str(root/'task.json'), '--task-sha256', bytes_ref((root/'task.json').read_bytes()),
               '--output-dir', str(root/'run')]
    save_new(root/'command.json', {'argv': command, 'candidate_answer_preselected': False})
    completed = subprocess.run(command, check=False, timeout=1500)
    report_path = root/'run/report.json'
    if not report_path.is_file():
        raise RuntimeError('Unattended runner produced no inspectable final outcome')
    report = json.loads(report_path.read_text())
    # Require actual identity-bound inference and accounting, NOT a successful art candidate.
    assert report['model_calls_with_responses'] >= 1
    assert report['model_usage']['usage_coverage'] == 'complete'
    assert report['model_usage']['known_prompt_tokens'] > 0
    assert report['model_usage']['known_generated_tokens'] > 0
    assert report['model_usage']['billed_usd'] is None
    assert report['original_workcell_yield']['baseline_technically_accepted']
    before = {f: bytes_ref(f.read_bytes()) for f in (root/'run').rglob('*') if f.is_file()}
    from unittest.mock import patch
    with patch('subprocess.Popen', side_effect=AssertionError('No workcell execution during audit')), \
            patch('http.client.HTTPConnection', side_effect=AssertionError('No model request during audit')):
        rechecked = inspect(root/'run')
    assert rechecked['model_usage'] == report['model_usage']
    assert all(bytes_ref(path.read_bytes()) == digest for path, digest in before.items())
    save_new(root/'qualification.json', {'schema':'ciw.unattended-qualification.v1', 'status':'passed',
        'runner_exit_code':completed.returncode, 'model':args.model, 'model_digest':model['model_digest'],
        'actual_model_responses':report['model_calls_with_responses'], 'usage':report['model_usage'],
        'agent_outcome':report['status'], 'yield':report['original_workcell_yield'],
        'retained_files_unchanged':len(before), 'independent_art_review':'not_performed', 'release_authorized':False})


if __name__ == '__main__':
    main()
