"""Qualify the actual 1792 attachment; never import game code into the NET package.

Operator-provisioned checkout; native tests execute only in a fresh staging copy.
No paid model call is made. Candidate proposals here are declared test inputs.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

from ciw import production_reconstruction as r


def snapshot(root: Path) -> dict:
    files = {}
    for path in root.rglob('*'):
        relative = path.relative_to(root)
        if any(part in {'.git', '.godot', '__pycache__', 'test-results'} for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError('Qualification checkout contains a symlink')
        if path.is_file():
            files[relative.as_posix()] = r.sha(path.read_bytes())
    return files


def run_logged(argv: list[str], cwd: Path, path: Path, *, env: dict, timeout: int = 900) -> str:
    with path.open('wb') as log:
        completed = subprocess.run(argv, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=timeout, check=False)
    text = r.read_regular(path, 2 * 1024 * 1024).decode('utf-8', errors='replace')
    print(text)
    if completed.returncode or re.search(r'(?m)^(SCRIPT ERROR|ERROR):', text):
        raise RuntimeError(f'Native qualification failed: {path.name}')
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-root', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--godot', type=Path)
    parser.add_argument('--godot-sha256')
    parser.add_argument('--render', action='store_true')
    args = parser.parse_args()
    game = args.game_root.absolute()
    before = snapshot(game)
    packet = r.prepare(game, '1792-reconstruction-qualification', {'household_well': ['position'], 'market_awning': ['size']})
    target = r.new_directory(args.output_dir)
    r.save_new(target / 'packet.json', packet)
    def proposal(x):
        return r.proposal(packet, 'declared-qualification-input-not-an-LLM', [
            {'feature_id': 'household_well', 'field': 'position', 'value': [-24, .1, -12] if x < 0 else [24, .1, 15]},
            {'feature_id': 'market_awning', 'field': 'size', 'value': [x if x > 0 else 4.5, 2.8, 3]}])
    rejected, repaired, other = proposal(-1), proposal(4.5), proposal(5)
    def batch(repair):
        return {'schema': r.BATCH, 'jobs': [
            {'job_id': 'primary', 'proposals': [rejected, repaired] if repair else [rejected], 'depends_on': []},
            {'job_id': 'dependent', 'proposals': [other], 'depends_on': ['primary']},
            {'job_id': 'independent', 'proposals': [other], 'depends_on': []}]}
    successful = r.run_batch(packet, batch(True), game, target / 'repaired')
    failed = r.run_batch(packet, batch(False), game, target / 'exhausted')
    assert successful['status'] == 'completed' and successful['attempt_count'] == 4
    assert failed['status'] == 'incomplete' and failed['attempt_count'] == 2
    assert failed['jobs']['primary']['status'] == 'rejected'
    assert failed['jobs']['dependent']['status'] == 'blocked'
    assert failed['jobs']['independent']['status'] == 'accepted'
    retained = snapshot(target)
    with patch.object(subprocess, 'Popen', side_effect=AssertionError('Inspection must not start a process')):
        a, b = r.inspect(target / 'repaired', game), r.inspect(target / 'exhausted', game)
        assert not a['fresh_execution'] and not b['fresh_execution']
    assert retained == snapshot(target)
    export = r.export_candidate(target / 'repaired', game, 'primary', target / 'accepted')
    candidate = (target / 'accepted' / export['file']).read_bytes()
    assert r.sha(candidate) == export['candidate_sha256']
    data = r.parse(candidate)
    assert next(f for f in data['features'] if f['id'] == 'market_awning')['size'][0] == 4.5
    baseline = r.parse(packet['baseline_utf8'].encode())
    for key in baseline:
        if key != 'features':
            assert data[key] == baseline[key]
    native = {'status': 'not_run', 'render': 'not_run'}
    if args.godot:
        executable = args.godot.resolve(strict=True)
        digest = r.sha(executable.read_bytes())
        assert digest == args.godot_sha256, 'Native executable digest mismatch'
        with tempfile.TemporaryDirectory(prefix='net-1792-candidate-') as directory:
            stage = Path(directory) / '1792'
            shutil.copytree(game, stage, ignore=shutil.ignore_patterns('.git', '.godot', '__pycache__', 'test-results'))
            assert snapshot(stage) == before
            (stage / r.SOURCE_PATH).write_bytes(candidate)
            difference = {name for name, digest_ in snapshot(stage).items() if before.get(name) != digest_}
            assert difference == {r.SOURCE_PATH}, difference
            env = dict(os.environ, XDG_DATA_HOME=str(target / 'userdata'), LIBGL_ALWAYS_SOFTWARE='1')
            run_logged([sys.executable, 'tools/run_checks.py', '--godot', str(executable)], stage, target / 'native-game-tests.log', env=env)
            shutil.copytree(stage / 'test-results', target / 'native-test-results')
            native = {'status': 'passed', 'executable_sha256': digest, 'changed_paths': sorted(difference), 'render': 'not_run'}
            if args.render:
                xvfb = shutil.which('xvfb-run')
                assert xvfb, 'xvfb-run must be explicitly provisioned for rendering'
                text = run_logged([xvfb, '-a', str(executable), '--path', 'game', '--rendering-method', 'gl_compatibility',
                    '--audio-driver', 'Dummy', '--script', 'res://tests/render_reconstruction.gd'], stage,
                    target / 'native-render.log', env=env, timeout=120)
                assert 'RECONSTRUCTION_RENDER: 4 captures; 0 failures' in text
                captures = list((target / 'userdata').rglob('reconstruction-*.png'))
                assert len(captures) == 4, captures
                native['render'] = 'four_captures_passed'
            assert r.sha(executable.read_bytes()) == digest
    assert snapshot(game) == before, 'Operator game checkout was modified'
    summary = {'schema': 'ciw.reconstruction-qualification.v1', 'game_reference_revision': r.GAME_REVISION,
        'validator_sha256': r.VALIDATOR_SHA256, 'source_tree_files': before,
        'source_sha256': packet['source_sha256'], 'candidate_sha256': export['candidate_sha256'],
        'production_attempts': 6, 'production_executions': successful['execution_count'] + failed['execution_count'],
        'repair_and_dependency_checks': 'passed', 'offline_inspection': 'passed_without_processes',
        'game_checkout_unchanged': True, 'native': native, 'model_api_calls': 0,
        'scope': 'bounded real-game attachment; not historical truth, art approval or autonomous studio qualification'}
    # This qualification record may exceed the CLI's 64 KiB work-packet budget.
    (target / 'qualification.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k != 'source_tree_files'}, indent=2))


if __name__ == '__main__':
    main()
