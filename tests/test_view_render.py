"""Presentation render descriptors copy retained values and refuse invention."""
from copy import deepcopy

import pytest

from ciw.view_render import (
    AUTHORITY,
    SCHEMA,
    attach_plane,
    attach_strip,
    attach_system,
    declared_circle_overlay,
    declared_mesh,
    plane_from_interleaved,
    strip_from_parameter,
)


def test_plane_pairs_retained_coordinates_without_connecting_them():
    values = [1.0, 0.0, 0.0, 1.0]
    labels = ["p0.x", "p0.y", "p1.x", "p1.y"]
    units = ["m"] * 4
    render = plane_from_interleaved(values, labels, units, frame="bench-plane")
    assert render["schema"] == SCHEMA
    assert render["kind"] == "plane2d"
    assert render["connect"] is False
    assert render["authority"] == AUTHORITY
    assert render["points"] == [{"label": "p0", "x": 1.0, "y": 0.0}, {"label": "p1", "x": 0.0, "y": 1.0}]
    render["points"][0]["x"] = 99
    assert values[0] == 1.0


def test_attach_plane_is_additive_and_detached_from_panel_values():
    panel = {"panel_id": "observed_points_m", "labels": ["a.x", "a.y"], "values": [0.5, -0.25],
             "units": ["m", "m"]}
    attach_plane(panel, frame={"id": "bench-plane"})
    assert panel["values"] == [0.5, -0.25]
    assert panel["render"]["points"][0] == {"label": "a", "x": 0.5, "y": -0.25}
    panel["render"]["points"][0]["y"] = 8
    assert panel["values"][1] == -0.25


@pytest.mark.parametrize("values,labels,units", [
    ([1.0], ["a.x"], ["m"]),
    ([1.0, 2.0, 3.0], ["a.x", "a.y", "b.x"], ["m", "m", "m"]),
    ([1.0, 2.0], ["a.x", "a.y"], ["m", "s"]),
    ([1.0, float("nan")], ["a.x", "a.y"], ["m", "m"]),
    ([1.0, float("inf")], ["a.x", "a.y"], ["m", "m"]),
])
def test_plane_render_refuses_ambiguous_or_nonfinite_values(values, labels, units):
    with pytest.raises(ValueError):
        plane_from_interleaved(values, labels, units, frame="bench-plane")


def test_declared_circle_overlay_copies_constraint_and_does_not_fit():
    constraint = {"kind": "circle", "center_m": [0.0, 0.0], "radius_m": 1.0, "constraint_id": "reference-circle"}
    overlay = declared_circle_overlay(constraint)
    assert overlay["center"] == [0.0, 0.0]
    assert overlay["radius"] == 1.0
    assert overlay["source"] == "declared_constraint"
    overlay["radius"] = 4
    assert constraint["radius_m"] == 1.0
    with pytest.raises(ValueError):
        declared_circle_overlay({"kind": "ellipse", "center_m": [0, 0], "radius_m": 1})
    with pytest.raises(ValueError):
        declared_circle_overlay({"kind": "circle", "center_m": [0, 0], "radius_m": float("nan")})


def test_declared_mesh_copies_faces_and_retained_path_indices():
    mesh = {"vertices": [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]],
            "triangles": [[0, 1, 2], [0, 2, 3]], "units": "normalized_length",
            "coordinate_frame": "synthetic-planar-square"}
    render = declared_mesh(mesh, path=[1, 0, 3], source_vertex=1, target_vertex=3)
    assert render["kind"] == "mesh"
    assert render["path"] == [1, 0, 3]
    assert render["projection"] == "first_two_declared_axes"
    render["vertices"][0][0] = 9
    assert mesh["vertices"][0][0] == 0
    with pytest.raises(ValueError):
        declared_mesh(mesh, path=[8])
    with pytest.raises(ValueError):
        declared_mesh({"vertices": [[0, 0]], "triangles": []})


def test_interleaved_native_points_keep_declared_circle_as_overlay_only():
    constraint = {"kind": "circle", "center_m": [0.0, 0.0], "radius_m": 1.0, "constraint_id": "reference-circle"}
    panel = {"labels": ["o0.x", "o0.y", "o1.x", "o1.y"], "values": [1.0, 0.0, 0.0, 1.0], "units": ["m"] * 4}
    attach_plane(panel, frame="bench-plane", overlays=[declared_circle_overlay(constraint)])
    assert [point["x"] for point in panel["render"]["points"]] == [1.0, 0.0]
    assert panel["render"]["overlays"][0]["source"] == "declared_constraint"
    assert panel["values"] == [1.0, 0.0, 0.0, 1.0]


def test_strip_uses_declared_parameter_and_refuses_a_decreasing_axis():
    parameter = [0.0, 0.5, 1.0]
    values = [0.1, 0.2, 0.15]
    render = strip_from_parameter(parameter, values, parameter_name="arclength",
                                  parameter_unit="m", value_unit="m", frame="path")
    assert render["kind"] == "strip"
    assert render["connect"] is False
    assert render["samples"][1] == {"parameter": 0.5, "value": 0.2}
    render["samples"][0]["value"] = 9
    assert values[0] == 0.1
    panel = {"values": [0.1, 0.2, 0.15], "units": ["m", "m", "m"]}
    attach_strip(panel, parameter, parameter_name="arclength", parameter_unit="m", frame="path")
    assert panel["render"]["parameter_name"] == "arclength"
    with pytest.raises(ValueError):
        strip_from_parameter([1.0, 0.0], [1.0, 2.0], parameter_name="s",
                             parameter_unit="m", value_unit="m", frame="path")
    with pytest.raises(ValueError):
        strip_from_parameter([0.0, float("nan")], [1.0, 2.0], parameter_name="s",
                             parameter_unit="m", value_unit="m", frame="path")
    with pytest.raises(ValueError):
        attach_strip({"values": [1.0, 2.0], "units": ["m", "radian"]},
                     [0.0, 1.0], parameter_name="s", parameter_unit="m", frame="path")


def test_attach_system_copies_the_mesh_and_survives_panel_mutation():
    mesh = {"vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
            "triangles": [[0, 1, 2]], "units": "normalized_length",
            "coordinate_frame": "synthetic-triangle"}
    render = declared_mesh(mesh, path=[0, 1], source_vertex=0, target_vertex=1)
    view = {"kind": "mesh-path", "panels": [{"render": render}]}
    attach_system(view, render)
    assert view["system_render"]["kind"] == "mesh"
    assert view["system_render"]["path"] == [0, 1]
    render["path"].append(2)
    view["panels"][0]["render"]["vertices"][0][0] = 9
    assert view["system_render"]["path"] == [0, 1]
    assert view["system_render"]["vertices"][0][0] == 0
    with pytest.raises(ValueError):
        attach_system(view, {"kind": "mesh"})
