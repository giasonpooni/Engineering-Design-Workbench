"""Presentation-only geometry copied from already-projected inspection values.

Clients may draw these descriptors. They are not measurements, interpolations,
admitted state, or inputs to any calculation. Overlay geometry is copied from a
declared constraint or mesh; this module does not solve, project, or resample.
"""
from __future__ import annotations

from copy import deepcopy

SCHEMA = "ciw.panel-render.v1"
AUTHORITY = {
    "read_only": True,
    "computation": "not_performed",
    "interpolation": "not_performed",
    "state_admission": "not_performed",
    "physical_geometry": "not_established",
    "surveyed_frame": "not_established",
}


def _finite_pair(value, name):
    if (not isinstance(value, (list, tuple)) or len(value) < 2 or
            any(type(item) not in (int, float) or item != item or abs(item) == float("inf")
                for item in value[:2])):
        raise ValueError(name + " is not a finite coordinate pair")
    return [float(value[0]), float(value[1])]


def plane_from_interleaved(values, labels, units, *, frame, overlays=()):
    """Pair already-projected sample-major x,y values for a 2D inspection canvas."""
    if not isinstance(values, list) or len(values) < 2 or len(values) % 2:
        raise ValueError("Plane render requires an even nonempty interleaved x,y sequence")
    if not isinstance(labels, list) or not isinstance(units, list):
        raise ValueError("Plane render requires retained labels and units")
    if len(labels) != len(values) or len(units) != len(values):
        raise ValueError("Plane render labels and units must match values")
    if any(unit != units[0] for unit in units):
        raise ValueError("Plane render refuses mixed units")
    if any(type(item) not in (int, float) or item != item or abs(item) == float("inf") for item in values):
        raise ValueError("Plane render requires finite coordinates")
    points = []
    for index in range(0, len(values), 2):
        label = labels[index]
        if isinstance(label, str) and label.endswith(".x"):
            label = label[:-2]
        points.append({"label": label, "x": float(values[index]), "y": float(values[index + 1])})
    return deepcopy({
        "schema": SCHEMA,
        "kind": "plane2d",
        "authority": dict(AUTHORITY),
        "frame": frame,
        "unit": units[0],
        "points": points,
        "overlays": deepcopy(list(overlays)),
        "connect": False,
        "note": "Declared-order points in the retained frame; not a trajectory or interpolation",
    })


def declared_circle_overlay(constraint):
    """Copy a fixed declared circle. No fit or residual geometry is computed."""
    if not isinstance(constraint, dict) or constraint.get("kind") != "circle":
        raise ValueError("Circle overlay requires a declared circle constraint")
    return deepcopy({
        "kind": "declared_circle",
        "center": _finite_pair(constraint["center_m"], "circle center"),
        "radius": float(constraint["radius_m"]),
        "source": "declared_constraint",
        "authority": "declared_not_surveyed",
        "constraint_id": constraint.get("constraint_id"),
    })


def declared_mesh(mesh, *, path=(), source_vertex=None, target_vertex=None):
    """Copy a declared triangle mesh for wireframe inspection."""
    if not isinstance(mesh, dict):
        raise ValueError("Mesh render requires the retained mesh declaration")
    vertices = mesh.get("vertices")
    triangles = mesh.get("triangles")
    if not isinstance(vertices, list) or not isinstance(triangles, list) or not vertices or not triangles:
        raise ValueError("Mesh render requires declared vertices and triangles")
    copied = []
    for vertex in vertices:
        if not isinstance(vertex, (list, tuple)) or len(vertex) < 2:
            raise ValueError("Mesh vertices must be coordinate tuples")
        copied.append([float(component) for component in vertex])
        if any(item != item or abs(item) == float("inf") for item in copied[-1]):
            raise ValueError("Mesh vertices must be finite")
    faces = []
    count = len(copied)
    for face in triangles:
        if not isinstance(face, (list, tuple)) or len(face) != 3:
            raise ValueError("Mesh triangles must be three vertex indices")
        indices = [int(index) for index in face]
        if any(index < 0 or index >= count for index in indices):
            raise ValueError("Mesh triangle index is outside the declared vertices")
        faces.append(indices)
    route = [int(index) for index in path] if path else []
    if any(index < 0 or index >= count for index in route):
        raise ValueError("Mesh path index is outside the declared vertices")
    return deepcopy({
        "schema": SCHEMA,
        "kind": "mesh",
        "authority": dict(AUTHORITY),
        "frame": mesh.get("coordinate_frame"),
        "unit": mesh.get("units"),
        "vertices": copied,
        "triangles": faces,
        "path": route,
        "source_vertex": source_vertex,
        "target_vertex": target_vertex,
        "projection": "first_two_declared_axes",
        "note": "Wireframe of declared vertices; 2D clients use the first two axes only",
    })


def attach_plane(panel, *, frame, overlays=()):
    panel["render"] = plane_from_interleaved(
        panel["values"], panel["labels"], panel["units"], frame=frame, overlays=overlays)
    return panel
