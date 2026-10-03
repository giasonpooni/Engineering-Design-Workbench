"""Actual retained Python thermal workflow -> NET observation/comparison checks.

Inputs are declared synthetic data; no native Julia or hardware is claimed.
"""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from ciw import scientific
from ciw.control_contracts import bytes_ref, load, save_new
from ciw.control_checks import compare, inspect_record
from ciw.core.identities import content_identity
from ciw.instruments import make_demo_run
from ciw.net import main
from ciw.operations.runner import seal
from ciw.scientific_observations import export_observations, select_observations, validate_view, match_workspace
from ciw.session import Session
from ciw.thermal_workflow import ThermalWorkflow
from test_thermal_workflow import _source


def make_case(root, mask=3):
    source = _source()
    for row in source['request']['observations']:
        for axis in range(2):
            if not mask & (1 << axis):
                row[axis] = None
    session = Session(make_demo_run(), root)
    result = scientific.execute(session, 'thermal-observer', json.dumps(source).encode(), label='synthetic test case')
    path = session.save_workspace(root / 'workspace.json')
    return session, result, path, bytes_ref(path.read_bytes())


@pytest.fixture(scope='module')
def cases(tmp_path_factory):
    return {mask: make_case(tmp_path_factory.mktemp('native-thermal-' + str(mask)), mask) for mask in range(4)}


def view(case, stage='posterior'):
    session, result, path, digest = case
    return export_observations(path, expected_sha256=digest, bundle_id=result['bundle_id'], stage=stage, entity_id='test/core-shell')


@pytest.mark.parametrize('stage', ['predicted', 'posterior', 'measurement'])
@pytest.mark.parametrize('mask', range(4))
def test_original_values_matrices_missingness_and_occurrences(cases, mask, stage):
    session, summary, path, sha = cases[mask]
    before = session.workbench.serialize()
    value = view(cases[mask], stage)
    step = session.workbench.get_bundle(summary['bundle_id'])['steps'][0]
    obs = value['stream']['observations']
    assert len(obs) == 3
    assert [row['clock']['time_s'] for row in obs] == [1., 2., 3.]
    assert value['coordinate_order'] == ['core_temperature', 'shell_temperature']
    for i, row in enumerate(obs):
        measured = stage == 'measurement'
        values = step['request']['observations'][i] if measured else step['result']['data']['observer']['trace'][i][stage + '_mean']
        matrix = step['request']['observation_noise_covariance'] if measured else step['result']['data']['observer']['trace'][i][stage + '_covariance']
        assert row['value'] == values
        assert row['unit'] == 'K'
        assert row['identity']['execution_id'] == (None if measured else step['execution_id'])
        assert row['provenance']['semantics'] == ('simulated' if measured else 'estimated')
        if measured and mask != 3:
            assert row['uncertainty'] is None
            assert value['row_context'][i]['covariance_attachment'] == 'unattached_due_to_missing_values'
            assert value['native_step']['request']['observation_noise_covariance'] == matrix
        else:
            assert row['uncertainty']['matrix'] == matrix
            assert row['uncertainty']['reference_values'] == values
            assert row['uncertainty']['quantity_ids'] == ['temperature[0]', 'temperature[1]']
    validate_view(value)
    match_workspace(value, path)
    assert session.workbench.serialize() == before
    assert bytes_ref(path.read_bytes()) == sha


def test_no_synthetic_reference_truth_is_exported(cases):
    data = view(cases[3])
    def walk(value):
        if isinstance(value, dict):
            assert not {'evaluation', 'held_out', 'generator_model', 'states'} & value.keys()
            for child in value.values(): walk(child)
        elif isinstance(value, list):
            for child in value: walk(child)
    walk(data)
    assert data['authority']['reference_truth'] == 'not_included'
    assert data['authority']['new_execution'] == 'not_performed'
    assert data['authority']['cross_tick_covariance'] == 'not_supplied'


@pytest.mark.parametrize('mutation', ['values', 'matrix', 'time', 'frame', 'unit', 'axis_order', 'mask', 'authority', 'native', 'source', 'execution'])
def test_resealed_view_cannot_contradict_native_evidence(cases, mutation):
    value = view(cases[3]); row = value['stream']['observations'][0]
    if mutation == 'values': row['value'][0] += 1
    elif mutation == 'matrix': row['uncertainty']['matrix'][0][1] = 0
    elif mutation == 'time': row['clock']['time_s'] = 0
    elif mutation == 'frame': row['frame'] = 'world'
    elif mutation == 'unit': row['unit'] = 'C'
    elif mutation == 'axis_order': value['coordinate_order'].reverse()
    elif mutation == 'mask': value['row_context'][0]['available_mask'] = 0
    elif mutation == 'authority': value['authority']['physical_validation'] = 'passed'
    elif mutation == 'native': value['native_step']['result']['data']['observer']['trace'][0]['posterior_mean'][0] += 5
    elif mutation == 'source': value['binding']['source_evidence_id'] = 'sha256:' + '0' * 64
    else: row['identity']['execution_id'] = 'execution-' + '1' * 32
    seal(row); seal(value['stream']); seal(value)
    with pytest.raises(ValueError): validate_view(value)


@pytest.mark.parametrize('stage', ['truth', 'reconciled', '', 'posterior_mean'])
def test_unsupported_stage_never_becomes_observation(cases, stage):
    with pytest.raises(ValueError): view(cases[3], stage)


def test_digest_binds_exact_bytes_not_reserialized_json(cases, tmp_path):
    value = view(cases[3]); path = cases[3][2]
    alternate = tmp_path / 'same-json.json'; alternate.write_bytes(path.read_bytes() + b'\n')
    assert json.loads(alternate.read_bytes()) == json.loads(path.read_bytes())
    with pytest.raises(ValueError, match='SHA256'): match_workspace(value, alternate)
    assert bytes_ref(path.read_bytes()) == cases[3][3]


def test_mutating_return_does_not_rewrite_source(cases):
    session, summary, _, digest = cases[3]
    data = select_observations(session, bundle_id=summary['bundle_id'], stage='posterior', entity_id='entity', workspace_sha256=digest)
    original = session.workbench.get_bundle(summary['bundle_id'])
    data['native_step']['request']['observations'][0][0] = 999
    assert session.workbench.get_bundle(summary['bundle_id']) == original


def test_projection_and_view_reader_do_not_execute_provider(cases, monkeypatch):
    def forbidden(*a, **kw): raise AssertionError('Provider execution is not inspection')
    for name in ('create_session', 'replay_session', '_adapters', '_step'):
        monkeypatch.setattr(ThermalWorkflow, name, forbidden)
    data = view(cases[3]); validate_view(data); inspect_record(data)
    match_workspace(data, cases[3][2])


def test_actual_fresh_replay_compares_without_overwriting_occurrence(cases, tmp_path):
    _, original, path, _ = cases[3]
    left = view(cases[3])
    with scientific.open_workspace(path, tmp_path / 'replay') as session:
        replay = scientific.replay(session, original['bundle_id'], repositories={})
    replay_path = tmp_path / 'replay/workspace.json'
    right = export_observations(replay_path, expected_sha256=bytes_ref(replay_path.read_bytes()),
        bundle_id=replay['bundle']['bundle_id'], stage='posterior', entity_id=left['entity_id'])
    assert left['native_step']['execution_id'] != right['native_step']['execution_id']
    assert left['native_step']['result_id'] != right['native_step']['result_id']
    assert compare(left['stream']['observations'], right['stream']['observations'], atol=0)['outcome']['status'] == 'PASS'


def test_missing_observation_comparison_is_indeterminate(cases):
    a,b = view(cases[0]), view(cases[0], 'measurement')
    result = compare(a['stream']['observations'], b['stream']['observations'], atol=1)
    assert result['outcome']['status'] == 'INDETERMINATE'
    assert result['outcome']['reason'] == 'missing_sample'


def test_different_evidence_clocks_cannot_be_silently_aligned(cases):
    a,b = view(cases[1]),view(cases[3])
    result = compare(a['stream']['observations'], b['stream']['observations'], atol=100)
    assert result['outcome']['status'] == 'INDETERMINATE'


def test_cli_export_inspect_compare_and_non_overwrite(cases, tmp_path, capsys):
    _, summary, path, digest = cases[3]
    output = tmp_path / 'posterior.json'
    args=['science','observations','--workspace',str(path),'--workspace-sha256',digest,'--bundle',summary['bundle_id'],
          '--stage','posterior','--entity','entity','--output',str(output)]
    assert main(args)==0; capsys.readouterr(); before=output.read_bytes()
    assert main(args)==1; capsys.readouterr(); assert output.read_bytes()==before
    assert main(['inspect',str(output),'--json'])==0
    assert json.loads(capsys.readouterr().out)['record']['stream']['observations']
    assert main(['compare',str(output),str(output),'--atol','0','--json'])==0
    assert json.loads(capsys.readouterr().out)['outcome']['status']=='PASS'
    bad=tmp_path/'bad.json'
    args[args.index('--workspace-sha256')+1]='sha256:'+'0'*64
    args[args.index('--output')+1]=str(bad)
    assert main(args)==1; capsys.readouterr(); assert not bad.exists()


def test_fresh_process_reader_uses_no_execution_hooks(cases, tmp_path):
    path=tmp_path/'view.json'; save_new(path,view(cases[3]))
    code='''
from pathlib import Path
import sys
from ciw.thermal_workflow import ThermalWorkflow
from ciw.net import inspect_path

def forbidden(*a, **kw): raise AssertionError("provider hook called")
ThermalWorkflow.create_session = forbidden
ThermalWorkflow.replay_session = forbidden
ThermalWorkflow._adapters = forbidden
assert inspect_path(Path(sys.argv[1]))['integrity'] == 'checked'
'''
    result=subprocess.run([sys.executable,'-c',code,str(path)],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr


def test_wrong_bundle_type_and_unknown_identity_refuse(cases):
    session, summary, _, digest = cases[3]
    with pytest.raises(ValueError):
        select_observations(session,bundle_id='absent',stage='posterior',entity_id='entity',workspace_sha256=digest)


def test_load_optional_digest_preserves_existing_loader_behavior(tmp_path):
    path=tmp_path/'data.json'; path.write_text('{"number": 1}',encoding='utf-8')
    assert load(path)==load(path,expected_sha256=bytes_ref(path.read_bytes()))
    with pytest.raises(ValueError): load(path,expected_sha256='not-a-hash')


@pytest.mark.parametrize("field", ["request", "result", "input_refs"])
def test_missing_native_fields_refuse_cleanly(cases, field):
    value=view(cases[3]); value["native_step"].pop(field); seal(value)
    with pytest.raises(ValueError): validate_view(value)
