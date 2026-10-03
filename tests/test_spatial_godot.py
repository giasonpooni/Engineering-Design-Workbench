"""Consumer contracts; native Godot execution is a separate explicit campaign."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import pytest

from ciw import spatial_godot as consumer
from ciw import spatial_workflow
from ciw.operations.runner import seal
from test_spatial_provider import fixture_session


@pytest.fixture
def prepared(tmp_path):
    _, workspace, result = fixture_session(tmp_path)
    out = tmp_path / "consumer"
    consumer.prepare(workspace, result["result_id"], out)
    return workspace, result, out


@pytest.mark.parametrize("point,expected", [([1, 2, 3], [1, 3, -2]), ([-2, -5, -3], [-2, -3, 5]), (None, None)])
def test_basis(point, expected):
    assert consumer.enu_to_godot(point) == expected


def test_basis_is_proper_rotation():
    import numpy as np
    basis = np.array(consumer.BASIS)
    assert np.array_equal(basis @ basis.T, np.eye(3))
    assert np.linalg.det(basis) == 1
    rng = np.random.default_rng(42)
    for p in rng.normal(size=(100, 3)):
        xyz = consumer.enu_to_godot(p.tolist())
        assert xyz == pytest.approx(basis @ p)
        assert np.linalg.norm(xyz) == pytest.approx(np.linalg.norm(p))


@pytest.mark.parametrize("bad", [[True, 1, 2], [float('nan'), 0, 0], [float('inf'), 1, 2], [1, 2], "1,2,3"])
def test_bad_coordinates(bad):
    with pytest.raises(ValueError):
        consumer.enu_to_godot(bad)


def test_provider_free_prepare_and_check(prepared, monkeypatch):
    workspace, result, out = prepared
    original = workspace.read_bytes()
    monkeypatch.setitem(sys.modules, "pyproj", None)
    monkeypatch.setitem(sys.modules, "pxr", None)
    monkeypatch.setattr(consumer.subprocess, "run", lambda *a, **kw: pytest.fail("execution during inspection"))
    checked = consumer.verify(out)
    display = json.loads((out / "display.json").read_bytes())
    assert checked["available_count"] == 5 and checked["sample_count"] == 6
    assert display["positions_xyz_m"][3] is None
    assert display["source"]["result_id"] == result["result_id"]
    assert display["source"]["runtime_entity_id"] is None
    assert checked["godot_execution"] == checked["provider_execution"] == "not_performed"
    assert workspace.read_bytes() == original


@pytest.mark.parametrize("radius", [True, 0, -1, 100.01, float('nan')])
def test_bad_radius_has_no_output(tmp_path, radius):
    _, workspace, result = fixture_session(tmp_path)
    out = tmp_path / "bad"
    with pytest.raises(ValueError):
        consumer.prepare(workspace, result['result_id'], out, marker_radius_m=radius)
    assert not out.exists()


def test_prepare_create_only(prepared):
    workspace, result, out = prepared
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    with pytest.raises(FileExistsError):
        consumer.prepare(workspace, result['result_id'], out)
    assert before == {p.name: p.read_bytes() for p in out.iterdir()}


@pytest.mark.parametrize("name", sorted(consumer.ARTIFACTS))
def test_every_changed_artifact_refused(prepared, name):
    _, _, out = prepared
    p = out / name
    p.write_bytes(p.read_bytes() + b" ")
    with pytest.raises(ValueError):
        consumer.verify(out)


def reseal(out, artifact):
    p = out / 'manifest.json'
    value = json.loads(p.read_bytes())
    value['artifacts'][artifact] = consumer.digest((out / artifact).read_bytes())
    seal(value)
    p.write_bytes(consumer.encode(value))


@pytest.mark.parametrize("name", ['view.gd', 'self_test.gd', 'project.godot', 'main.tscn', 'display.json'])
def test_resealed_untrusted_code_or_projection_refused(prepared, name):
    _, _, out = prepared
    p = out / name
    p.write_bytes(p.read_bytes() + b" ")
    reseal(out, name)
    with pytest.raises(ValueError, match="trusted templates"):
        consumer.verify(out)


def test_promoted_authority_refused(prepared):
    _, _, out = prepared
    p = out / 'manifest.json'; value = json.loads(p.read_bytes())
    value['authority']['state_admission'] = 'passed'; seal(value); p.write_bytes(consumer.encode(value))
    with pytest.raises(ValueError):
        consumer.verify(out)


def test_bad_expected_digest_no_output(prepared, tmp_path):
    workspace, result, _ = prepared
    out = tmp_path / 'bad'
    with pytest.raises(ValueError, match="operator's digest"):
        consumer.prepare(workspace, result['result_id'], out, expected_workspace_sha256='sha256:'+'0'*64)
    assert not out.exists()


def test_binary_pin_refused_before_execution(prepared, tmp_path, monkeypatch):
    _, _, out = prepared
    monkeypatch.setattr(consumer.subprocess, 'run', lambda *a, **kw: pytest.fail('unbound executable ran'))
    output = tmp_path / 'evidence'
    with pytest.raises(ValueError, match="executable digest"):
        consumer.check(out, Path(sys.executable), 'sha256:'+'0'*64, output)
    assert not output.exists()


def test_failed_execution_keeps_receipt(prepared, tmp_path, monkeypatch):
    _, _, out = prepared
    def fail(*a, **kw):
        raise OSError('injected spawn failure')
    monkeypatch.setattr(consumer.subprocess, 'run', fail)
    binary = Path(sys.executable).resolve()
    output = tmp_path / 'evidence'
    with pytest.raises(OSError):
        consumer.check(out, binary, consumer.digest(binary.read_bytes()), output)
    receipt = json.loads((output / 'check.json').read_bytes())
    assert receipt['status'] == 'failed'
    assert receipt['provider_execution'] == 'not_performed'


def test_module_and_existing_spatial_cli(prepared, capsys):
    _, _, out = prepared
    assert consumer.main(['verify', str(out)]) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'retained_godot_bundle_checked'
    assert spatial_workflow.main(['godot', 'verify', str(out)]) == 0
    assert json.loads(capsys.readouterr().out)['godot_execution'] == 'not_performed'


def test_templates_have_no_service_or_dynamic_import():
    for name in consumer.TEMPLATES:
        value = consumer.files('ciw').joinpath('viewer_assets', 'spatial', name).read_text()
        for forbidden in ['HTTPRequest', 'WebSocket', 'OS.execute', 'OS.create_process', '@tool', '[autoload]']:
            assert forbidden not in value
