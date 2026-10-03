"""Regression checks for retained output bounds and provenance commitments."""

import json
from types import SimpleNamespace

import pytest

from ciw import geomatics_workflow as workflow
from ciw.operations.runner import check_seal, digest
from net_geomatics.catalog import EXAMPLES, OPERATIONS, _build_catalog
from net_geomatics.common import example_raster, metric


@pytest.mark.parametrize('crs', ['LOCAL_METRE:', 'LOCAL_METRE:   ', 'LOCAL_METRE:\t',
                                'EPSG:4326', True])
def test_metric_requires_named_local_frame(crs):
    with pytest.raises(ValueError):
        metric({'crs': crs})


def test_metric_accepts_explicit_frame_name():
    metric({'crs': 'LOCAL_METRE:synthetic-campus'})


def test_catalog_operation_example_keys_match():
    assert set(OPERATIONS) == set(EXAMPLES)


def test_catalog_rejects_duplicate_operation_ids():
    provider = SimpleNamespace(OPERATIONS={'geomatics.reference.v1': lambda p: p},
                               EXAMPLES={'geomatics.reference.v1': {}})
    with pytest.raises(ValueError, match='Duplicate geomatics operation IDs'):
        _build_catalog([provider, provider])


@pytest.mark.parametrize('example_ids', [[], ['geomatics.unknown.v1'],
                                       ['geomatics.reference.v1', 'geomatics.unknown.v1']])
def test_catalog_refuses_missing_or_extra_examples(example_ids):
    provider = SimpleNamespace(OPERATIONS={'geomatics.reference.v1': lambda p: p},
                               EXAMPLES={name: {} for name in example_ids})
    with pytest.raises(ValueError, match='exactly one example'):
        _build_catalog([provider])


def test_replay_receipt_commits_both_compared_records(tmp_path):
    request = workflow.example('geomatics.coordinates.enu.v1')
    original = workflow.run(request, tmp_path / 'original')
    receipt = workflow.replay(tmp_path / 'original', tmp_path / 'reproduced')
    reproduced = workflow.inspect(tmp_path / 'reproduced')
    assert receipt['subject_record_digest'] == original['result']['record_digest']
    assert receipt['reproduced_record_digest'] == reproduced['result']['record_digest']
    assert receipt['subject_record_digest'] != receipt['reproduced_record_digest']
    assert receipt['numerical_match'] is True
    check_seal(receipt)


def test_expanded_request_is_bounded_before_writes(tmp_path):
    request = workflow.example('geomatics.coordinates.enu.v1')
    # Legal bounded JSON, compactly small but deeply indented scalar rows.
    nested = [0] * 60000
    for _ in range(18):
        nested = [nested]
    request['parameters'] = {'nested': nested}
    assert len(json.dumps(request, separators=(',', ':')).encode()) < 512 * 1024
    assert len(json.dumps(request, indent=2).encode()) > 2 * 1024 * 1024
    with pytest.raises(ValueError, match='Indented geomatics request exceeds 2 MiB'):
        workflow.run(request, tmp_path / 'run')
    assert not (tmp_path / 'run').exists()


def test_oversized_zonal_output_is_retained_as_readable_refusal(tmp_path):
    request = workflow.example('geomatics.raster.zonal.v1')
    request['parameters'] = {
        'values': example_raster([[0] * 100 for _ in range(100)]),
        'zones': example_raster([[row * 100 + col for col in range(100)] for row in range(100)]),
    }
    workflow.validate_request(request)
    result = workflow.run(request, tmp_path / 'run')
    assert result['status'] == 'refused'
    assert result['result'] is None
    assert result['refusal']['message'] == 'Indented geomatics output exceeds 1 MiB'
    assert workflow.inspect(tmp_path / 'run') == result
    assert not list((tmp_path / 'run').glob('result-*.json'))
    assert (tmp_path / 'run' / 'workspace.json').stat().st_size < 1024 * 1024
    with pytest.raises(ValueError, match='refused execution'):
        workflow.replay(tmp_path / 'run', tmp_path / 'reproduced')
    assert not (tmp_path / 'reproduced').exists()


def test_saved_payload_output_bound_does_not_call_provider(monkeypatch):
    import net_geomatics.catalog
    request = workflow.example('geomatics.coordinates.enu.v1')
    source = workflow.make_source(request)
    # Each string obeys the JSON tree limit, but their combined output does not.
    output = {'text': ['x' * 65536] * 17}
    data = {'schema': workflow.RESULT_SCHEMA, 'operation_id': request['operation_id'],
            'request_digest': digest(request), 'output': output,
            'authority': dict(workflow.AUTHORITY)}
    monkeypatch.setattr(net_geomatics.catalog, 'execute',
                        lambda *args: pytest.fail('retained validation executed a provider'))
    with pytest.raises(ValueError, match='Indented geomatics output exceeds 1 MiB'):
        workflow.validate_payload(request['operation_id'], data, source, {},
                                  {'channel': 'configuration_index', 'interval_s': [0.0, 1.0]})
