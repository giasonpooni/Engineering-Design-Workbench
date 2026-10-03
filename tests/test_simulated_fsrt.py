"""Contract fixtures only; real Godot/FSRT qualification lives in validation/."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import uuid

import pytest

from ciw.core.identities import evidence_id
from ciw.session import Session
from ciw.simulated_fsrt import (
    INSTRUMENT, OPERATION, STATE, MAX_SOURCE_BYTES, _scientific_content,
    native_inputs, validate_observation, validate_source, sha256, create, inspect,
)
ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def source():
    return json.loads((ROOT/'examples/simulation-observation/source.json').read_text())


@pytest.fixture
def parameters():
    return json.loads((ROOT/'examples/simulation-observation/parameters.json').read_text())


def make_run(source):
    _,channels,metadata=_scientific_content(json.dumps(source).encode())
    run={'run_schema':'run.v1','run_id':'run-'+uuid.uuid4().hex,'instrument':INSTRUMENT,
         'metadata':metadata,'time_s':[0.0],'channels':channels,'render':{}}
    run['evidence_id']=evidence_id(run)
    return run


def test_source_and_request_keep_synthetic_meaning(source,parameters):
    run=make_run(source); inputs=native_inputs(run,parameters)
    assert 'rci_source' not in run['metadata']
    assert all(c['kind']=='simulated_observation' for c in run['channels'].values())
    obs=inputs['observations'][0]
    assert obs['values']==source['values'] and obs['covariance']==source['covariance']
    assert obs['t']==0.1 and inputs['state_order']==STATE
    assert set(inputs)=={'model','observations','state_order','observation_covariance'}
    assert 'producer' not in json.dumps(inputs) or 'producer_execution_id' in json.dumps(inputs)
    metadata=inputs['observation_covariance']['provenance']['metadata']
    assert metadata['source_class']=='simulated_observation'
    assert metadata['calibration_status']=='not_applicable_simulated_reading'
    assert 'physically measured or calibrated' in metadata['native_label_notice']
    assert obs['covariance'][0][1]==0.1


def test_missing_is_not_imputed(source,parameters):
    source['values'][1]=None;source['mask'][1]=False;source['reference_values'][1]=0.0
    request=native_inputs(make_run(source),parameters)
    assert request['observations'][0]['values'][1] is None
    assert request['observation_covariance']['reference_values'][1]==0.0


BAD_SOURCE=[
    lambda s:s.__setitem__('truth',[49,51]),
    lambda s:s['producer'].__setitem__('truth',[49,51]),
    lambda s:s['clock'].__setitem__('tick',True),
    lambda s:s['clock'].__setitem__('tick',1.5),
    lambda s:s['clock'].__setitem__('ticks_per_second',0),
    lambda s:s['clock'].__setitem__('phase','render_interpolated'),
    lambda s:s['clock'].__setitem__('tick',2**53+1),
    lambda s:s.__setitem__('source_class','physical_measurement'),
    lambda s:s['producer'].__setitem__('clock_owner','NET'),
    lambda s:s['producer'].__setitem__('source_revision','latest'),
    lambda s:s['producer'].__setitem__('execution_id','same-instance'),
    lambda s:s['producer'].__setitem__('executable_sha256','hash'),
    lambda s:s.__setitem__('unit','g'),
    lambda s:s.__setitem__('frame','world'),
    lambda s:s['source_ids'].__setitem__(1,s['source_ids'][0]),
    lambda s:s['entity_ids'].__setitem__(1,s['entity_ids'][0]),
    lambda s:s['values'].__setitem__(0,True),
    lambda s:s['values'].__setitem__(0,float('nan')),
    lambda s:s['values'].__setitem__(0,-1),
    lambda s:s['values'].__setitem__(1,None),
    lambda s:s['reference_values'].__setitem__(0,0.0),
    lambda s:s['mask'].__setitem__(0,1),
    lambda s:s['covariance'][0].__setitem__(1,9),
    lambda s:s['covariance'][0].__setitem__(0,-1),
    lambda s:s.__setitem__('values',[[1,2],[3,4]]),
    lambda s:s.__setitem__('observations',[{},{}]),
]
@pytest.mark.parametrize('mutate',BAD_SOURCE)
def test_invalid_source_is_refused(source,mutate):
    mutate(source)
    with pytest.raises((ValueError,TypeError)):
        validate_observation(source)


@pytest.mark.parametrize('flag',['prior_independent_of_observations','declared_total_independent_of_observations','prior_independent_of_declared_total'])
@pytest.mark.parametrize('value',[False,None,1,'true'])
def test_no_manufactured_independence(source,parameters,flag,value):
    parameters['independence'][flag]=value
    with pytest.raises(ValueError,match='dependence'):
        native_inputs(make_run(source),parameters)


def test_explicit_entity_mapping_required(source,parameters):
    parameters['state_bindings'].reverse()
    with pytest.raises(ValueError,match='binding'):
        native_inputs(make_run(source),parameters)


def test_native_receives_only_selected_observation_not_reference(source,parameters):
    run=make_run(source); first=native_inputs(run,parameters)
    # Reference truth is deliberately not part of the source or API.
    external_reference={'true_mass':[49.0,51.0]};external_reference['true_mass']=[1e6,0]
    assert native_inputs(run,parameters)==first
    assert 'true_mass' not in json.dumps(first)


def test_legacy_rci_operation_does_not_accept_new_source(source):
    from ciw.investigation import _fsrt_inputs
    with pytest.raises((ValueError,KeyError)):
        _fsrt_inputs(make_run(source),{})


def test_reopen_runs_no_engine_or_estimator(source,tmp_path,monkeypatch):
    run=make_run(source); session=Session(run,tmp_path/'original'); path=session.save_workspace(tmp_path/'original/workspace.json')
    before=path.read_bytes()
    def forbidden(*a,**k):raise AssertionError('Inspection launched a provider')
    monkeypatch.setattr(subprocess,'Popen',forbidden)
    report=inspect(path,sha256(before))
    assert report['source']==source and report['inspection_only'] is True
    assert path.read_bytes()==before
    assert not any(n=='set_lcm' or n.startswith('set_lcm.') for n in sys.modules)


@pytest.mark.parametrize('change',['channels','clock','kind'])
def test_rehashed_run_cannot_detach_from_source_bytes(source,tmp_path,change):
    run=make_run(source)
    if change=='channels':run['channels'][source['source_ids'][0]]['values']=[0.0]
    if change=='clock':run['metadata']['provenance']['time_reference']='wall clock'
    if change=='kind':run['channels'][source['source_ids'][0]]['kind']='physical_observation'
    run['evidence_id']=evidence_id(run)
    with pytest.raises(ValueError):Session(run,tmp_path/change)
    assert not (tmp_path/change).exists()


@pytest.mark.parametrize('bad',['digest','duplicate','oversize'])
def test_bad_import_writes_nothing(source,parameters,tmp_path,bad):
    raw=json.dumps(source).encode()
    if bad=='duplicate':raw=raw.replace(b'{',b'{"schema":"duplicate",',1)
    if bad=='oversize':raw=b' '*(MAX_SOURCE_BYTES+1)
    path=tmp_path/'source.json';path.write_bytes(raw)
    expected='sha256:'+'f'*64 if bad=='digest' else sha256(raw)
    with pytest.raises(ValueError):create(path,expected,parameters,tmp_path/'no-provider',tmp_path/'must-not-write')
    assert not (tmp_path/'must-not-write').exists()


def test_declared_runtime_cannot_register_code(source,tmp_path):
    run=make_run(source);session=Session(run,tmp_path/'s')
    assert OPERATION not in [x['operation_id'] for x in session.operations.describe()]
