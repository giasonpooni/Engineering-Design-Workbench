"""Request/dispatch tests only. No actual GSC, GSV, PPDA or ESM adapter runs here."""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ciw.adapters.protocol import AdapterRefusal
from ciw.control_contracts import bytes_ref, load
from ciw.control_plane import builtin_registry, plan_graph, run_graph
from ciw.instruments import make_demo_run
from ciw.net import main
from ciw.operations.runner import seal
from ciw.session import Session
from ciw.spatial_requests import (
    AUTHORITY, ROUTES, ProviderBinding, add_spatial_routes, make_plan,
    open_spatial_workspace, validate_request,
)

REF = bytes_ref(b'synthetic-contract-output-not-an-admission')
OTHER = bytes_ref(b'other-synthetic-basis')
EXAMPLE = Path(__file__).parents[1] / 'examples/spatial/scene-request.json'


def fields(alias='rs.scene.admit'):
    value = load(EXAMPLE)['spatial']
    source = value['sources'][0]
    if alias == 'spatial.map':
        source['kind'] = 'admitted_state'
        value['governance'].update(esm_admission_ref=REF, admitted_state_ref=source['ref'])
    elif alias == 'spatial.inspect':
        source['kind'] = 'released_snapshot'
        value['governance'].update(esm_release_ref=REF, released_snapshot_ref=source['ref'])
    return value


class Probe:
    """Explicit contract double. A reference it returns grants no real authority."""
    def __init__(self, target):
        self.target = target
        self.calls = []
        self.identity = {'provider': target, 'implementation_ref': REF, 'qualification': 'synthetic_contract_only'}

    def invoke(self, operation, request):
        self.calls.append((operation, deepcopy(request)))
        # Exercise detachment; changing this copy must not change the saved request.
        request['scene'] = None
        return {'output_ref': REF, 'provider_execution_ref': OTHER}

    def runtime(self):
        return deepcopy(self.identity)

    def binding(self):
        return ProviderBinding(self.invoke, self.runtime)


def session_for(tmp_path, alias):
    registry = builtin_registry(bind=True)
    probe = Probe(ROUTES[alias][0])
    add_spatial_routes(registry, bindings={alias: probe.binding()})
    session = Session(make_demo_run(), tmp_path / 'session', operations=registry.operations)
    return session, registry, probe


def dispatch(session, alias, value):
    return session.handle({'protocol_version': 1, 'request_id': 'spatial-request',
        'type': 'operation.execute', 'payload': {'operation_id': alias + '.v1', 'parameters': {'spatial': value}}})


def test_catalog_is_existing_registry_with_unbound_targets_only():
    registry = builtin_registry(bind=True)
    before = registry.catalog()
    add_spatial_routes(registry)
    catalog = registry.catalog('gis_rs')
    assert set(catalog['providers']) == {'GSC', 'GSV', 'PPDA+ESM'}
    assert set(catalog['operations']) == {name + '.v1' for name in ROUTES}
    assert all(not r['bound'] and r['runtime']['status'] == 'unbound_interface_target' for r in catalog['operations'].values())
    assert not catalog['authorizes_execution']
    for name, old in before['operations'].items():
        assert registry.catalog()['operations'][name] == old
    assert registry.catalog()['providers']['GSV']['role'] == 'view'
    assert 'rs.index.ndvi.v1' not in registry.catalog()['operations']


def test_default_catalog_stays_unchanged():
    assert set(builtin_registry().catalog()['operations']) == {'statistics.v1', 'spectrum.periodogram.v1'}


@pytest.mark.parametrize('alias', list(ROUTES))
def test_declared_target_is_not_a_live_adapter(tmp_path, alias):
    registry = builtin_registry(bind=True)
    with patch('subprocess.Popen', side_effect=AssertionError('no provider discovery')):
        add_spatial_routes(registry)
        session = Session(make_demo_run(), tmp_path / 'session', operations=registry.operations)
        response = dispatch(session, alias, fields(alias))
    assert response['payload']['status'] == 'refused'
    assert response['payload']['execution']['refusal']['code'] == 'operation_unavailable'
    assert response['payload']['result'] is None and len(session.executions) == 1


@pytest.mark.parametrize('alias', list(ROUTES))
def test_real_session_dispatches_only_request_metadata_to_contract_double(tmp_path, alias):
    session, registry, probe = session_for(tmp_path, alias)
    request = fields(alias)
    original = deepcopy(request)
    original_run = deepcopy(session.run)
    response = dispatch(session, alias, request)
    assert response['payload']['status'] == 'completed', response
    result = response['payload']['result']
    assert probe.calls == [(alias, original)]
    assert request == original and session.run == original_run
    assert result['parameters'] == {'spatial': original}
    assert result['data']['provider'] == ROUTES[alias][0]
    assert result['data']['output_ref'] == REF and result['role'] == 'backend'
    assert result['verification_id'] is None and result['verification_status'] == 'not_verified'
    assert all(result['data'][k] == v for k, v in AUTHORITY.items())
    # No copied raster, canonical state, new admission or substituted observation time.
    assert set(result['data']) == {'provider', 'output_kind', 'request_ref', 'output_ref', 'provider_execution_ref', *AUTHORITY}
    assert result['parameters']['spatial']['sources'][0]['knownAt'] == '2026-09-03T12:00:00Z'
    path = tmp_path / 'workspace.json'; session.save_workspace(path)
    with patch.object(probe, 'invoke', side_effect=AssertionError('reader cannot execute')):
        reopened = open_spatial_workspace(path, output_dir=tmp_path / 'read')
    assert reopened.results[result['result_id']] == result
    assert len(reopened.executions) == 1
    assert dispatch(reopened, alias, fields(alias))['payload']['status'] == 'refused'


CASES = [
    ('crs-absent', 'unresolved_crs'), ('source-crs-absent', 'unresolved_crs'),
    ('crs-null', 'unresolved_crs'), ('crs-axis', 'unresolved_crs'),
    ('source-crs', 'mixed_crs_basis'), ('axis-order', 'mixed_crs_basis'),
    ('datum', 'implicit_datum_shift'), ('epoch', 'implicit_datum_shift'),
    ('basis', 'mixed_geometry_basis'), ('mixed-pixels', 'mixed_pixel_basis'),
    ('mixed-grid', 'mixed_grid_basis'), ('unclassified-pixels', 'mixed_pixel_basis'),
    ('missing-source', 'missing_provenance_source'), ('empty-source', 'missing_provenance_source'),
    ('person-source', 'person_yield'), ('unknown-source-yield', 'person_yield'),
    ('person-entity', 'person_yield'), ('person-product', 'person_yield'),
    ('geofence', 'geofence_product'), ('satellite-room', 'unknown_room'),
    ('license', 'license_posture_unresolved'), ('license-ref', 'license_posture_unresolved'),
    ('scene', 'scene_required'), ('candidate-admitted', 'candidate_not_canonical'),
    ('duplicate', 'duplicate_source'), ('time-window', 'invalid_time_window'),
    ('naive-time', 'unresolved_time'),
]


def corrupt(value, mode):
    source = value['sources'][0]
    if mode == 'crs-absent': del value['crs']
    elif mode == 'source-crs-absent': del source['crs']
    elif mode == 'crs-null': value['crs'] = None
    elif mode == 'crs-axis': value['crs']['axis_order'] = []
    elif mode == 'source-crs': source['crs']['definition_ref'] = OTHER
    elif mode == 'axis-order': source['crs']['axis_order'].reverse()
    elif mode == 'datum': source['crs']['datum_ref'] = OTHER
    elif mode == 'epoch': source['crs']['coordinate_epoch'] = 2020.0
    elif mode == 'basis': source['geometry_basis_ref'] = OTHER
    elif mode in ('mixed-pixels', 'mixed-grid'):
        second = deepcopy(source); second['ref'] = OTHER
        second['pixel_basis' if mode == 'mixed-pixels' else 'grid_ref'] = 'point' if mode == 'mixed-pixels' else OTHER
        value['sources'].append(second)
    elif mode == 'unclassified-pixels': source['pixel_basis'] = 'not_applicable'
    elif mode == 'missing-source': del source['provenance']['source']
    elif mode == 'empty-source': source['provenance']['source'] = '  '
    elif mode == 'person-source': source['yield_class'] = 'natural_person'
    elif mode == 'unknown-source-yield': source['yield_class'] = 'unknown'
    elif mode == 'person-entity': value['entity']['kind'] = 'resident'
    elif mode == 'person-product': value['collection']['subject'] = 'residents_as_pixels'
    elif mode == 'geofence': value['collection']['product'] = 'geofence'
    elif mode == 'satellite-room': value['room'] = 'Satellite'
    elif mode == 'license': value['license_posture'] = 'unknown'
    elif mode == 'license-ref': value['license_ref'] = None
    elif mode == 'scene': value['scene'] = None
    elif mode == 'candidate-admitted': value['governance']['esm_admission_ref'] = REF
    elif mode == 'duplicate': value['sources'].append(deepcopy(source))
    elif mode == 'time-window': value['time_window']['start'] = '2026-09-05T00:00:00Z'
    elif mode == 'naive-time': source['knownAt'] = '2026-09-03T12:00:00'


@pytest.mark.parametrize('mode,code', CASES)
def test_typed_refusal_is_retained_without_provider_call(tmp_path, mode, code):
    session, _, probe = session_for(tmp_path, 'rs.scene.admit')
    value = fields(); corrupt(value, mode)
    response = dispatch(session, 'rs.scene.admit', value)
    assert response['payload']['status'] == 'refused', response
    assert response['payload']['execution']['refusal']['code'] == code, response
    assert response['payload']['result'] is None and probe.calls == []


def test_building_address_identifier_is_not_a_person_yield_heuristic():
    value = fields(); value['entity']['id'] = 'building-address-reference'
    validate_request('rs.scene.admit', value)


@pytest.mark.parametrize('alias,change,code', [
    ('spatial.map','admission','esm_admission_required'),
    ('spatial.map','state','admission_source_mismatch'),
    ('spatial.map','layer','admission_source_mismatch'),
    ('spatial.inspect','release','released_snapshot_required'),
    ('spatial.inspect','snapshot','release_source_mismatch'),
    ('spatial.inspect','layer','release_source_mismatch'),
])
def test_admission_and_release_are_required_not_inferred(tmp_path, alias, change, code):
    session, _, probe = session_for(tmp_path, alias)
    value = fields(alias)
    if change == 'admission': value['governance']['esm_admission_ref'] = None
    elif change == 'state': value['sources'][0]['kind'] = 'raster'
    elif change == 'release': value['governance']['esm_release_ref'] = None
    elif change == 'snapshot': value['governance']['released_snapshot_ref'] = OTHER
    else:
        extra = deepcopy(value['sources'][0]); extra.update(ref=OTHER, kind='raster'); value['sources'].append(extra)
    r = dispatch(session, alias, value)
    assert r['payload']['execution']['refusal']['code'] == code
    assert probe.calls == []


@pytest.mark.parametrize('injection', ['command', 'pixels', 'write', 'raw_geotiff'])
def test_no_arbitrary_commands_or_raster_payload_fields(tmp_path, injection):
    session, _, probe = session_for(tmp_path, 'rs.scene.admit')
    value = fields(); value[injection] = 'untrusted input'
    assert dispatch(session, 'rs.scene.admit', value)['payload']['status'] == 'refused'
    assert probe.calls == []


def test_provider_denial_remains_original_refusal(tmp_path):
    session, _, probe = session_for(tmp_path, 'rs.scene.admit')
    def deny(*args): raise AdapterRefusal('esm_admission_denied', 'External admission rejected')
    # Bind the callable itself, not a mutable string or import selector.
    registry = builtin_registry(bind=True)
    add_spatial_routes(registry, bindings={'rs.scene.admit': ProviderBinding(deny, probe.runtime)})
    session = Session(make_demo_run(), tmp_path/'denied', operations=registry.operations)
    r = dispatch(session, 'rs.scene.admit', fields())
    assert r['payload']['execution']['refusal']['code'] == 'esm_admission_denied'
    assert not session.results


def test_runtime_drift_refuses_before_dispatch(tmp_path):
    session, _, probe = session_for(tmp_path, 'spatial.map')
    probe.identity['implementation_ref'] = OTHER
    r = dispatch(session, 'spatial.map', fields('spatial.map'))
    assert r['payload']['execution']['refusal']['code'] == 'runtime_mismatch'
    assert probe.calls == []


@pytest.mark.parametrize('mode', ['no-pin','wrong-provider','saved-path'])
def test_invalid_binding_does_not_mutate_original_catalog(mode):
    registry = builtin_registry()
    before = registry.catalog()
    probe = Probe('GSC')
    if mode == 'no-pin': probe.identity.pop('implementation_ref')
    elif mode == 'wrong-provider': probe.identity['provider'] = 'NET'
    binding = '/bin/provider' if mode == 'saved-path' else probe.binding()
    with pytest.raises(AdapterRefusal): add_spatial_routes(registry, bindings={'spatial.map': binding})
    assert registry.catalog() == before


def test_existing_registration_is_not_replaced():
    registry = builtin_registry(); add_spatial_routes(registry); before=registry.catalog()
    with pytest.raises(AdapterRefusal, match='never replaced'): add_spatial_routes(registry)
    assert registry.catalog() == before


def test_existing_graph_and_session_run_without_new_executor(tmp_path):
    session, registry, probe = session_for(tmp_path, 'rs.scene.admit')
    graph = make_plan('rs.scene.admit', fields(), model_id='synthetic-entity-observation.v1')
    assert graph['schema'] == 'ciw.experiment.v1'
    assert graph['parameters']['spatial']['room'] == 'PAYLOAD'
    plan_graph(graph, registry)
    result = run_graph(session, graph, registry)
    assert result['status'] == 'completed' and len(probe.calls) == 1
    assert len(session.executions) == len(session.results) == 1


def test_provider_cannot_return_local_canonical_state(tmp_path):
    probe = Probe('PPDA+ESM'); registry=builtin_registry()
    add_spatial_routes(registry, bindings={'rs.scene.admit':ProviderBinding(lambda *args: {'output_ref':REF,'provider_execution_ref':OTHER,'canonical_state':{}},probe.runtime)})
    session=Session(make_demo_run(), tmp_path/'session',operations=registry.operations)
    assert dispatch(session,'rs.scene.admit',fields())['payload']['status']=='refused'
    assert not session.results


@pytest.mark.parametrize('key,value', [('state_admission_by_net',True),('state_release_by_net',True),('verification_id','invented'),('request_ref',OTHER)])
def test_resealed_payload_cannot_grant_authority(tmp_path,key,value):
    session,_,_=session_for(tmp_path,'rs.scene.admit')
    result=dispatch(session,'rs.scene.admit',fields())['payload']['result']
    path=tmp_path/'original.json';session.save_workspace(path)
    saved=json.loads(path.read_text());r=next(r for r in saved['results'] if r['result_id']==result['result_id'])
    r['data'][key]=value;seal(r)
    path.write_text(json.dumps(saved))
    with pytest.raises(ValueError): open_spatial_workspace(path,output_dir=tmp_path/'reader')


def test_cli_writes_existing_plan_and_no_provider_claim(tmp_path,capsys):
    with patch('subprocess.Popen',side_effect=AssertionError('no discovery')):
        assert main(['spatial','catalog'])==0
        assert main(['spatial','check',str(EXAMPLE)])==0
        path=tmp_path/'plan.json'
        assert main(['spatial','plan',str(EXAMPLE),'--model-id','synthetic-site.v1','--output',str(path)])==0
        assert main(['spatial','plan',str(EXAMPLE),'--model-id','synthetic-site.v1','--output',str(path)])==1
    assert load(path)['nodes'][0]['operation_id']=='rs.scene.admit.v1'
    assert '"reference_authenticity_checked": false' in capsys.readouterr().out


def test_cli_does_not_publish_invalid_plan(tmp_path,capsys):
    value=load(EXAMPLE);value['spatial']['crs']=None
    request=tmp_path/'bad.json';request.write_text(json.dumps(value))
    output=tmp_path/'plan.json'
    assert main(['spatial','plan',str(request),'--model-id','synthetic-site.v1','--output',str(output)])==1
    assert not output.exists() and 'unresolved_crs' in capsys.readouterr().err


def test_future_numeric_operations_do_not_exist_yet():
    for alias in ('spatial.warp','spatial.sample','spatial.reproject','rs.index.ndvi','rs.scene.ingest'):
        with pytest.raises(AdapterRefusal): validate_request(alias, fields())


def test_reopened_request_result_cannot_change_its_role(tmp_path):
    session,_,_=session_for(tmp_path,'spatial.map')
    result=dispatch(session,'spatial.map',fields('spatial.map'))['payload']['result']
    path=tmp_path/'source.json';session.save_workspace(path)
    value=json.loads(path.read_text())
    r=next(r for r in value['results'] if r['result_id']==result['result_id'])
    r['role']='verification';seal(r);path.write_text(json.dumps(value))
    with pytest.raises(ValueError): open_spatial_workspace(path,output_dir=tmp_path/'reader')
