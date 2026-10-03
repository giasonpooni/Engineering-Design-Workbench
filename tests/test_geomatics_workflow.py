"""Numerical tools must keep NET evidence and event identities distinct."""
import json

import pytest

from ciw import geomatics_workflow as workflow
from ciw.geomatics_cli import main
from net_geomatics.catalog import OPERATIONS


@pytest.mark.parametrize('operation_id', sorted(OPERATIONS))
def test_every_operation_retains_inspects_and_reproduces(tmp_path, operation_id):
    request = workflow.example(operation_id)
    original = workflow.run(request, tmp_path/'original')
    assert original['status'] == 'completed', original
    assert original['result']['data']['authority']['state_admission'] == 'not_performed'
    assert original['source_evidence_id'].startswith('sha256:')
    assert original['execution_id'].startswith('execution-')
    assert original['result']['result_id'].startswith('result-')
    receipt = workflow.replay(tmp_path/'original', tmp_path/'replay')
    assert receipt['numerical_match'] is True
    assert receipt['independent'] is False
    assert receipt['verification_id'].startswith('verification-')
    assert receipt['reproduced_execution_id'] != original['execution_id']
    assert receipt['reproduced_result_id'] != original['result']['result_id']
    assert receipt['source_evidence_id'] == original['source_evidence_id']
    assert (tmp_path/'replay/reproduction.json').is_file()


def _request():
    return workflow.example('geomatics.atmosphere.transmission.v1')


def test_inspection_does_not_execute_provider(tmp_path, monkeypatch):
    original = workflow.run(_request(), tmp_path/'run')
    import net_geomatics.catalog
    monkeypatch.setattr(net_geomatics.catalog, 'execute', lambda *args: pytest.fail('inspection executed provider'))
    assert workflow.inspect(tmp_path/'run') == original


def test_changed_runtime_refuses_before_new_execution(tmp_path, monkeypatch):
    workflow.run(_request(), tmp_path/'run')
    old = workflow.runtime_identity()
    monkeypatch.setattr(workflow, 'runtime_identity', lambda: {**old, 'code_sha256':'0'*64})
    with pytest.raises(ValueError, match='runtime differs'):
        workflow.replay(tmp_path/'run', tmp_path/'replay')
    assert not (tmp_path/'replay').exists()


def test_invalid_domain_retains_refusal(tmp_path):
    request = _request()
    request['parameters']['optical_depth'] = -1
    result = workflow.run(request, tmp_path/'run')
    assert result['status'] == 'refused'
    assert result['result'] is None
    assert result['refusal']
    with pytest.raises(ValueError, match='refused execution'):
        workflow.replay(tmp_path/'run', tmp_path/'replay')


def test_unknown_operation_refuses_before_directory_creation(tmp_path):
    request = _request()
    request['operation_id'] = 'geomatics.untrusted-plugin.v1'
    with pytest.raises(ValueError, match='Unknown'):
        workflow.run(request, tmp_path/'run')
    assert not (tmp_path/'run').exists()


def test_workspace_byte_tampering_is_detected(tmp_path):
    workflow.run(_request(), tmp_path/'run')
    path = tmp_path/'run/workspace.json'
    data = json.loads(path.read_text())
    data['run']['metadata']['geomatics_request']['parameters']['optical_depth'] = 7
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='[Ee]vidence|integrity'):
        workflow.inspect(tmp_path/'run')


def test_resealed_structurally_invalid_result_is_rejected(tmp_path):
    from ciw.operations.runner import seal
    workflow.run(_request(), tmp_path/'run')
    path = tmp_path/'run/workspace.json'
    data = json.loads(path.read_text())
    result = data['results'][0]
    result['data']['output'] = {}
    seal(result)
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        workflow.inspect(tmp_path/'run')


def test_no_overwrite_and_no_symlink_read(tmp_path):
    workflow.run(_request(), tmp_path/'run')
    with pytest.raises(FileExistsError):
        workflow.run(_request(), tmp_path/'run')
    (tmp_path/'link').mkdir()
    try:
        (tmp_path/'link/workspace.json').symlink_to(tmp_path/'run/workspace.json')
    except OSError:
        pytest.skip('Platform does not permit creating test symlinks')
    with pytest.raises(ValueError, match='regular bounded'):
        workflow.inspect(tmp_path/'link')


def test_cli_complete_journey(tmp_path, capsys):
    assert main(['catalog']) == 0
    assert json.loads(capsys.readouterr().out)['operations']
    source = tmp_path/'request.json'
    assert main(['example',_request()['operation_id'],'--output',str(source)]) == 0
    assert main(['run',str(source),'--output-dir',str(tmp_path/'run')]) == 0
    assert main(['inspect',str(tmp_path/'run')]) == 0
    assert main(['replay',str(tmp_path/'run'),'--output-dir',str(tmp_path/'replay')]) == 0
    assert main(['run',str(source),'--output-dir',str(tmp_path/'run')]) == 2


def test_operation_role_cannot_claim_verification():
    from ciw.operations.schemas import validate_role
    with pytest.raises(ValueError, match='backend'):
        validate_role(_request()['operation_id'], 'verification')


def test_registry_never_binds_from_saved_data(tmp_path):
    from ciw.session import Session
    workflow.run(_request(), tmp_path/'run')
    reopened = Session.from_workspace(tmp_path/'run/workspace.json', tmp_path/'reopened')
    assert not any(op['operation_id'].startswith('geomatics.') for op in reopened.operations.describe())
