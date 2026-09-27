"""Read-only USDA copies stay unconnected and off the OpenUSD runtime."""
from pathlib import Path

import pytest

from ciw.instruments import make_demo_run
from ciw.usda_export import SCHEMA, export_payload, export_recording, export_render
from ciw.view_render import attach_plane, attach_strip, declared_mesh


def test_oscillator_recording_exports_unconnected_points():
    run = make_demo_run()
    text = export_recording(run)
    assert text.startswith("#usda 1.0")
    assert SCHEMA in text
    assert "def Points" in text
    assert "BasisCurves" not in text
    assert "inspection_copy_not_observation" in text
    assert run["run_id"] in text
    assert "oscillator-state" in text
    assert str(run["render"]["trajectory"][0][0]) in text


def test_plane_and_strip_exports_refuse_a_connected_copy():
    panel = {"labels": ["a.x", "a.y"], "values": [1.0, 0.0], "units": ["m", "m"]}
    attach_plane(panel, frame="bench-plane", canvas_id="observed_points_m",
                 canvas_title="Observed coordinates")
    text = export_render(panel["render"])
    assert "def Points" in text
    assert "observed_points_m" in text
    assert "bench-plane" in text
    panel["render"]["connect"] = True
    with pytest.raises(ValueError, match="Plane and strip copies stay unconnected"):
        export_render(panel["render"])
    strip = {"values": [0.1, 0.2], "units": ["m", "m"]}
    attach_strip(strip, [0.0, 1.0], parameter_name="arclength", parameter_unit="m",
                 frame="geodesic-reference", canvas_id="separation",
                 canvas_title="Native transverse separation")
    text = export_render(strip["render"])
    assert "arclength" in text
    assert "separation" in text


def test_mesh_export_copies_declared_faces():
    mesh = {"vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
            "triangles": [[0, 1, 2]], "units": "normalized_length",
            "coordinate_frame": "synthetic-triangle"}
    render = declared_mesh(mesh, path=[0, 1], source_vertex=0, target_vertex=1,
                           canvas_id="vertex-distances",
                           canvas_title="Shortest distances along mesh edges")
    text = export_render(render)
    assert "def Mesh" in text
    assert "vertex-distances" in text
    assert "synthetic-triangle" in text
    assert "faceVertexIndices = [0, 1, 2]" in text


def test_inspect_view_export_uses_system_render(tmp_path: Path):
    panel = {"labels": ["a.x", "a.y"], "values": [0.5, -0.25], "units": ["m", "m"]}
    attach_plane(panel, frame="area-one-flat-quotient", canvas_id="cover_points",
                 canvas_title="Lifted path coordinates")
    view = {"schema": "ciw.experiment-view.v1", "system_canvas_id": "cover_points",
            "system_render": panel["render"]}
    text = export_payload(view)
    assert "cover_points" in text
    assert "area-one-flat-quotient" in text
    target = tmp_path / "cover.usda"
    target.write_text(text, encoding="utf-8")
    assert target.read_text(encoding="utf-8").startswith("#usda 1.0")
