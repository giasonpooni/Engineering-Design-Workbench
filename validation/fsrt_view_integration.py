"""Real retained RCI -> FSRT -> provider-free view checks. Missing pins FAIL.

Only public synthetic examples are generated; no observations are field evidence.
CIW_FSRT_VIEW_FIXTURES can select a previously produced, digest-checked CI bundle
for provider-free local regression; it does not constitute fresh execution.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from ciw.fsrt_view import export_view, sha256, write_view
from ciw.operations.runner import seal
from ciw.session import loads_json

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def cases(tmp_path_factory):
    cached = os.getenv('CIW_FSRT_VIEW_FIXTURES')
    if cached:
        root = Path(cached)
        index = loads_json((root / 'index.json').read_text())
        for item in index.values():
            assert sha256((root / item['workspace']).read_bytes()) == item['workspace_sha256']
            assert sha256((root / item['view']).read_bytes()) == item['file_sha256']
        return root, index
    from ciw.investigation import create_investigation
    providers = [Path(os.environ['CIW_' + name + '_REPO']) for name in ('RCI', 'FSRT')]
    output = Path(os.environ.get('CIW_FSRT_VIEW_OUT', str(tmp_path_factory.mktemp('fsrt-views'))))
    output.mkdir(parents=True, exist_ok=True)
    index = {}
    for name in ('ordinary', 'held', 'refused', 'legacy'):
        filename = 'two-reservoir.json' if name == 'legacy' else 'two-reservoir-covariance.json'
        inputs = loads_json((ROOT / 'examples/adapters' / filename).read_text())
        if name == 'held':
            inputs['model']['total_mass_kg'] = 0.0
        if name == 'refused':
            inputs['model']['prior_std'] = 0.0
        created = create_investigation(inputs, *providers, output / name, sys.executable)
        path = Path(created['workspace_file'])
        raw = path.read_bytes()
        workspace = loads_json(raw.decode())
        execution = workspace['executions'][-1]
        expected_status = 'refused' if name == 'refused' else 'completed'
        assert execution['status'] == expected_status, execution
        envelope = export_view(path, execution['execution_id'], expected_workspace_sha256=sha256(raw))
        view_file = output / (name + '.view.json')
        write_view(envelope, view_file)
        index[name] = {'workspace': str(path.relative_to(output)), 'workspace_sha256': sha256(raw),
                       'execution_id': execution['execution_id'], 'view': view_file.name,
                       'view_sha256': envelope['sha256'], 'file_sha256': sha256(view_file.read_bytes()),
                       'scope': 'actual pinned RCI/FSRT execution on synthetic inputs'}
    (output / 'index.json').write_text(json.dumps(index, indent=2) + '\n')
    return output, index


def load(cases, name='ordinary'):
    root, index = cases
    item = index[name]
    path = root / item['workspace']
    return path, item, loads_json(path.read_text())


@pytest.mark.parametrize('name', ['ordinary', 'held', 'refused', 'legacy'])
def test_exact_records_and_exclusive_output(cases, name, tmp_path):
    path, item, workspace = load(cases, name)
    before = {p: p.read_bytes() for p in path.parent.iterdir() if p.is_file()}
    view = export_view(path, item['execution_id'], expected_workspace_sha256=item['workspace_sha256'])
    payload = loads_json(view['payload'])
    assert payload['execution'] == workspace['executions'][-1]
    result = workspace['results'][-1] if name != 'refused' else None
    assert payload['result'] == result
    assert sha256(view['payload'].encode()) == item['view_sha256'] == view['sha256']
    assert payload['authority']['read_only'] is True
    assert payload['authority']['state_admission'] == 'not_performed'
    for file, raw in before.items():
        assert file.read_bytes() == raw
    destination = tmp_path / 'view.json'
    write_view(view, destination)
    with pytest.raises(FileExistsError):
        write_view(view, destination)
    assert json.loads(destination.read_text()) == view


def test_held_correction_keeps_two_stage_identities(cases):
    path, item, _ = load(cases, 'held')
    data = loads_json(export_view(path, item['execution_id'], expected_workspace_sha256=item['workspace_sha256'])['payload'])['result']['data']
    assert data['diagnostics']['physical_model_status'] == 'physical_model_disagreement'
    assert data['diagnostics']['reconciliation_status'] == 'model_inconsistent'
    assert data['residuals']['correction'] is None and data['residuals']['balance_after'] is None
    assert data['estimate']['values'] == data['unprojected_estimate']['values']
    a = data['covariance_artifacts']
    assert a['posterior']['matrix'] == a['reconciled']['matrix']
    assert a['posterior']['covariance_id'] != a['reconciled']['covariance_id']
    assert data['diagnostics']['fault_attribution'] == 'confounded_or_unidentifiable'


def test_full_covariance_and_no_new_verification(cases):
    path, item, _ = load(cases)
    result = loads_json(export_view(path, item['execution_id'], expected_workspace_sha256=item['workspace_sha256'])['payload'])['result']
    assert result['verification_id'] is None and result['verification_status'] == 'not_verified'
    a = result['data']['covariance_artifacts']
    assert set(a) == {'observation', 'prior', 'declared_total', 'innovation', 'posterior', 'reconciled'}
    assert a['reconciled']['matrix'][0][1] != 0
    assert a['reconciled']['matrix'] == result['data']['estimate']['covariance']
    assert a['observation']['provenance']['metadata']['prior_independent_of_observations'] is True


def test_export_never_launches_a_provider(cases, monkeypatch):
    path, item, _ = load(cases)
    def forbidden(*args, **kwargs):
        pytest.fail('Inspection attempted process execution')
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    export_view(path, item['execution_id'], expected_workspace_sha256=item['workspace_sha256'])
    assert not any(name == prefix or name.startswith(prefix + '.') for name in sys.modules
                   for prefix in ('set_lcm', 'instrument_chain'))


@pytest.mark.parametrize('mutation', ['result_id', 'execution_id', 'units', 'covariance', 'held', 'authority'])
def test_resealed_inconsistent_records_refused(cases, tmp_path, mutation):
    _, item, workspace = load(cases, 'held' if mutation == 'held' else 'ordinary')
    result = workspace['results'][-1]
    if mutation == 'result_id':
        result['result_id'] = 'result-' + 'f' * 32
    elif mutation == 'execution_id':
        result['execution_id'] = 'execution-' + 'f' * 32
    elif mutation == 'units':
        result['data']['estimate']['unit'] = 'g'
    elif mutation == 'covariance':
        result['data']['covariance_artifacts']['posterior']['matrix'][0][1] += 1.0
    elif mutation == 'held':
        result['data']['residuals']['correction'] = [0., 0.]
    else:
        result['verification_status'] = 'verified'
    seal(result)
    path = tmp_path / 'tampered.json'
    path.write_text(json.dumps(workspace))
    with pytest.raises(ValueError):
        export_view(path, item['execution_id'], expected_workspace_sha256=sha256(path.read_bytes()))


@pytest.mark.parametrize('mutation', ['wrong_digest', 'unknown_execution', 'duplicate_key', 'oversize', 'nan'])
def test_selection_and_json_refusal(cases, tmp_path, mutation):
    source, item, _ = load(cases)
    raw = source.read_bytes()
    identity = item['execution_id']
    if mutation == 'duplicate_key':
        raw = raw.replace(b'{', b'{"workspace_version":2,', 1)
    elif mutation == 'oversize':
        raw = b' ' * (8 * 1024 * 1024 + 1)
    elif mutation == 'nan':
        raw = b'{"workspace_version":NaN}'
    elif mutation == 'unknown_execution':
        identity = 'execution-' + 'f' * 32
    path = tmp_path / 'bad.json'
    path.write_bytes(raw)
    expected = 'sha256:' + 'f' * 64 if mutation == 'wrong_digest' else sha256(raw)
    with pytest.raises(ValueError):
        export_view(path, identity, expected_workspace_sha256=expected)


def test_cli_and_no_overwrite(cases, tmp_path):
    path, item, _ = load(cases)
    destination = tmp_path / 'cli.json'
    command = [sys.executable, '-m', 'ciw.fsrt_view', str(path), '--execution', item['execution_id'],
               '--expect-workspace-sha256', item['workspace_sha256'], '--output', str(destination)]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)['view_sha256'] == item['view_sha256']
    before = destination.read_bytes()
    assert subprocess.run(command, capture_output=True, timeout=30).returncode == 2
    assert destination.read_bytes() == before
