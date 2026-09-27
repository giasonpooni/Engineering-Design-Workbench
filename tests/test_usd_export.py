"""Real OpenUSD roundtrip; absence skips locally and fails the installed gate."""
from copy import deepcopy
from pathlib import Path
import json
import sys

import pytest
from ciw import usd_export as usd
from ciw.learning import work
from ciw.telemetry import canonical, digest


def fixture(tmp_path):
    result = work(tmp_path / "source")
    return Path(result["workspace_file"]), result["result"]["result_id"]


def native():
    pytest.importorskip("pxr.Usd", reason="Actual OpenUSD SDK is required for this test")
    from pxr import Sdf
    return Sdf


def reseal(directory, scene):
    (directory / "scene.usda").write_bytes(scene)
    report = json.loads((directory / "export.json").read_bytes())
    report["scene_sha256"] = usd._hash(scene)
    report["export_id"] = digest({k: v for k, v in report.items() if k != "export_id"})
    (directory / "export.json").write_bytes(canonical(report))


def test_projection_uses_source_metres_not_mixed_unit_render_axes(tmp_path):
    path, rid = fixture(tmp_path)
    value = json.loads(path.read_bytes())
    assert value["run"]["render"]["transform"]["scale"] != [1., 1., 1.]
    raw = canonical(value)
    projection = usd._project(raw, rid)
    assert projection["q"] == value["run"]["channels"]["q"]["values"]
    assert projection["unit"] == "m"
    assert projection["mapping"] == "q_metres_to_local_x.v1"
    assert projection["times"][-1] == 767 / 64


def test_unknown_result_refuses_before_sdk_loading(tmp_path, monkeypatch):
    path, _ = fixture(tmp_path)
    monkeypatch.setattr(usd, "_sdk", lambda: pytest.fail("Invalid result reached SDK"))
    with pytest.raises(ValueError):
        usd.export_workspace(path, "unknown", tmp_path / "export")
    assert not (tmp_path / "export").exists()


def test_sdk_absence_has_no_handwritten_usda_fallback(tmp_path, monkeypatch):
    path, rid = fixture(tmp_path)
    monkeypatch.setitem(sys.modules, "pxr", None)
    with pytest.raises(RuntimeError, match="OpenUSD is unavailable"):
        usd.export_workspace(path, rid, tmp_path / "export")
    assert not (tmp_path / "export").exists()


def test_native_sdk_roundtrip_and_provider_free_reopen(tmp_path, monkeypatch):
    native()
    path, rid = fixture(tmp_path)
    before = path.read_bytes()
    output = tmp_path / "export"
    report = usd.export_workspace(path, rid, output)
    monkeypatch.setattr("ciw.operations.registry.OperationRegistry.get", lambda *_: pytest.fail("Export verification computed"))
    result = usd.verify_export(output)
    assert result["validation"] == "sdk_roundtrip_matched" and result["samples_checked"] == 768
    assert result["export_id"] == report["export_id"]
    assert set(result["authority"].values()) == {"not_performed"}
    assert path.read_bytes() == before
    assert (output / "workspace.json").read_bytes() == before
    assert report["projection"]["result_id"] == rid
    assert (output / "scene.usda").read_text().startswith("#usda 1.0")


@pytest.mark.parametrize("change", ["units", "axis", "time_scale", "sample_value", "sample_time", "binding", "external", "transform", "prim_type", "glyph"])
def test_resealed_scene_tampering_fails_semantics_not_just_hashes(tmp_path, change):
    Sdf = native()
    from pxr import Gf
    path, rid = fixture(tmp_path)
    output = tmp_path / "export"
    usd.export_workspace(path, rid, output)
    layer = Sdf.Layer.CreateAnonymous(".usda")
    assert layer.ImportFromString((output / "scene.usda").read_text())
    if change == "units": layer.pseudoRoot.SetInfo("metersPerUnit", 0.001)
    if change == "axis": layer.pseudoRoot.SetInfo("upAxis", "Y")
    if change == "time_scale": layer.timeCodesPerSecond = 24
    if change == "sample_value": layer.SetTimeSample("/Notations/Displacement.xformOp:translate", 0., Gf.Vec3d(123., 0., 0.))
    if change == "sample_time": layer.SetTimeSample("/Notations/Displacement.xformOp:translate", 12., Gf.Vec3d(0., 0., 0.))
    if change == "binding": layer.GetAttributeAtPath("/Notations.notations:binding").default = "{}"
    if change == "external": layer.subLayerPaths = ["/does-not-exist/remote.usda"]
    if change == "transform": layer.GetAttributeAtPath("/Notations/Displacement.xformOpOrder").default = ["!resetXformStack!", "xformOp:translate"]
    if change == "prim_type": layer.GetPrimAtPath("/Notations/Displacement").typeName = "UnregisteredCustomType"
    if change == "glyph": layer.GetAttributeAtPath("/Notations/Displacement/Marker.radius").default = 30.
    reseal(output, layer.ExportToString().encode())
    with pytest.raises(ValueError):
        usd.verify_export(output)


def test_reused_export_directory_preserves_prior_files(tmp_path):
    native()
    path, rid = fixture(tmp_path)
    output = tmp_path / "export"
    usd.export_workspace(path, rid, output)
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    with pytest.raises(FileExistsError):
        usd.export_workspace(path, rid, output)
    assert {p.name: p.read_bytes() for p in output.iterdir()} == before


def test_explicit_usd_pilot_requires_real_sdk_and_retains_report(tmp_path):
    native()
    from ciw.pilot import run
    report = run(tmp_path / "pilot", with_usd=True)
    assert report["scene"]["status"] == "passed"
    assert report["scene"]["samples_checked"] == 384
    assert report["scene"]["authority"]["cryptographic_verification"] == "not_performed"


def test_resealed_manifest_cannot_promote_authority(tmp_path):
    native()
    path, rid = fixture(tmp_path)
    output = tmp_path / "export"
    usd.export_workspace(path, rid, output)
    report = json.loads((output / "export.json").read_bytes())
    report["authority"]["cryptographic_verification"] = "passed"
    report["export_id"] = digest({k: v for k, v in report.items() if k != "export_id"})
    (output / "export.json").write_bytes(canonical(report))
    with pytest.raises(ValueError):
        usd.verify_export(output)


def test_byte_limit_is_enforced_before_parsing(tmp_path):
    path = tmp_path / "oversize.json"
    path.write_bytes(b"x" * 65)
    with pytest.raises(ValueError, match="byte limit"):
        usd._read(path, 64)
