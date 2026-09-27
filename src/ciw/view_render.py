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

UNCONNECTED_KINDS = ("plane2d", "strip")
DECLARED_CIRCLE = "declared_circle"
DECLARED_CONSTRAINT = "declared_constraint"


def detach_overlay(overlay):
    """Copy a declared overlay. Fitted or estimated geometry is refused."""
    if not isinstance(overlay, dict):
        raise ValueError("Overlay must be a declared object")
    if overlay.get("kind") != DECLARED_CIRCLE:
        raise ValueError("Plane overlay must be a declared circle")
    if overlay.get("source") != DECLARED_CONSTRAINT:
        raise ValueError("Circle overlay refuses fitted or estimated geometry")
    if overlay.get("authority") not in (None, "declared_not_surveyed"):
        raise ValueError("Circle overlay refuses a surveyed or fitted authority")
    radius = overlay.get("radius")
    if type(radius) not in (int, float) or radius != radius or abs(radius) == float("inf"):
        raise ValueError("Circle overlay requires a finite declared radius")
    identity = overlay.get("constraint_id")
    if identity is not None and (not isinstance(identity, str) or not identity):
        raise ValueError("Circle overlay constraint_id must be a retained identity")
    title = identity
    if overlay.get("overlay_title") not in (None, title):
        raise ValueError("Circle overlay title must match the retained constraint_id")
    return deepcopy({
        "kind": DECLARED_CIRCLE,
        "center": _finite_pair(overlay.get("center"), "circle center"),
        "radius": float(radius),
        "source": DECLARED_CONSTRAINT,
        "authority": "declared_not_surveyed",
        "constraint_id": identity,
        "overlay_title": title,
    })


def detach_overlays(overlays):
    if overlays in (None, ()):
        return []
    if not isinstance(overlays, (list, tuple)):
        raise ValueError("Plane overlays must be a declared list")
    return [detach_overlay(overlay) for overlay in overlays]


def detach_render(render):
    """Copy a presentation descriptor. Plane and strip samples stay unconnected."""
    if not isinstance(render, dict) or render.get("schema") != SCHEMA:
        raise ValueError("System render requires a detached panel-render descriptor")
    payload = deepcopy(render)
    if payload.get("kind") in UNCONNECTED_KINDS:
        payload["connect"] = False
    if payload.get("kind") == "plane2d":
        payload["overlays"] = detach_overlays(payload.get("overlays"))
        payload["points"] = detach_plane_points(payload.get("points"))
        payload.update(plane_endpoint_labels(payload["points"], payload))
    if payload.get("kind") == "mesh":
        payload.update(detach_mesh_geometry(payload))
    if payload.get("kind") == "strip":
        payload["samples"] = detach_strip_samples(payload.get("samples"))
        payload.update(strip_endpoint_labels(
            payload["samples"], payload.get("parameter_name"), payload))
    return payload


def _finite_pair(value, name):
    if (not isinstance(value, (list, tuple)) or len(value) < 2 or
            any(type(item) not in (int, float) or item != item or abs(item) == float("inf")
                for item in value[:2])):
        raise ValueError(name + " is not a finite coordinate pair")
    return [float(value[0]), float(value[1])]


def detach_plane_points(points):
    """Copy declared plane points. Nonfinite coordinates are refused."""
    if not isinstance(points, list) or not points:
        raise ValueError("Plane render requires an even nonempty interleaved x,y sequence")
    copied = []
    for item in points:
        if not isinstance(item, dict):
            raise ValueError("Plane render requires finite coordinates")
        copied.append({
            "label": item.get("label"),
            "x": _finite_number(item.get("x"), "Plane render requires finite coordinates"),
            "y": _finite_number(item.get("y"), "Plane render requires finite coordinates"),
        })
    return copied


def plane_endpoint_labels(points, claimed=None):
    """Name the first and last declared plane points. Not a trajectory."""
    if not points:
        return {}
    start = points[0].get("label") or "first"
    end = points[-1].get("label") or "last"
    labels = {"start_label": start, "end_label": end}
    if len(points) == 1 or start == end:
        labels["end_label"] = None
    if isinstance(claimed, dict):
        for key, value in labels.items():
            if claimed.get(key, value) != value:
                raise ValueError("Plane endpoint label must match the declared points")
    return labels


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
    points = detach_plane_points(points)
    payload = {
        "schema": SCHEMA,
        "kind": "plane2d",
        "authority": dict(AUTHORITY),
        "frame": frame,
        "unit": units[0],
        "points": points,
        "overlays": detach_overlays(overlays),
        "connect": False,
        "note": "Declared-order points in the retained frame; not a trajectory or interpolation",
    }
    payload.update(plane_endpoint_labels(points))
    return deepcopy(payload)


def declared_circle_overlay(constraint):
    """Copy a fixed declared circle. No fit or residual geometry is computed."""
    if not isinstance(constraint, dict) or constraint.get("kind") != "circle":
        raise ValueError("Circle overlay requires a declared circle constraint")
    radius = constraint["radius_m"]
    if type(radius) not in (int, float) or radius != radius or abs(radius) == float("inf"):
        raise ValueError("Circle overlay requires a finite declared radius")
    identity = constraint.get("constraint_id")
    if identity is not None and (not isinstance(identity, str) or not identity):
        raise ValueError("Circle overlay constraint_id must be a retained identity")
    return deepcopy({
        "kind": "declared_circle",
        "center": _finite_pair(constraint["center_m"], "circle center"),
        "radius": float(radius),
        "source": "declared_constraint",
        "authority": "declared_not_surveyed",
        "constraint_id": identity,
        "overlay_title": identity,
    })


def _declared_vertices(vertices):
    if not isinstance(vertices, list) or not vertices:
        raise ValueError("Mesh render requires declared vertices and triangles")
    copied = []
    for vertex in vertices:
        if not isinstance(vertex, (list, tuple)) or len(vertex) < 2:
            raise ValueError("Mesh vertices must be coordinate tuples")
        copied.append([float(component) for component in vertex])
        if any(item != item or abs(item) == float("inf") for item in copied[-1]):
            raise ValueError("Mesh vertices must be finite")
    return copied


def _declared_faces(triangles, count):
    if not isinstance(triangles, list) or not triangles:
        raise ValueError("Mesh render requires declared vertices and triangles")
    faces = []
    for face in triangles:
        if not isinstance(face, (list, tuple)) or len(face) != 3:
            raise ValueError("Mesh triangles must be three vertex indices")
        indices = [int(index) for index in face]
        if any(index < 0 or index >= count for index in indices):
            raise ValueError("Mesh triangle index is outside the declared vertices")
        faces.append(indices)
    return faces


def _declared_indices(values, count, name):
    if values in (None, ()):
        return []
    if not isinstance(values, (list, tuple)):
        raise ValueError(name + " must be a declared index list")
    route = [int(index) for index in values]
    if any(index < 0 or index >= count for index in route):
        raise ValueError(name + " is outside the declared vertices")
    return route


def _declared_index(value, count, name):
    if value is None:
        return None
    index = int(value)
    if index < 0 or index >= count:
        raise ValueError(name + " is outside the declared vertices")
    return index


def detach_mesh_geometry(render):
    """Copy declared mesh faces and path indices. Out-of-range paths are refused."""
    vertices = _declared_vertices(render.get("vertices"))
    count = len(vertices)
    source = _declared_index(render.get("source_vertex"), count, "Mesh source vertex")
    target = _declared_index(render.get("target_vertex"), count, "Mesh target vertex")
    planar = all(len(vertex) < 3 or vertex[2] == 0 for vertex in vertices)
    if render.get("declared_planar") is True and not planar:
        raise ValueError("Mesh declared_planar refuses a lifted vertex")
    source_label = None if source is None else "source %s" % source
    target_label = None if target is None else "target %s" % target
    if render.get("source_label", source_label) != source_label:
        raise ValueError("Mesh source label must match the declared vertex")
    if render.get("target_label", target_label) != target_label:
        raise ValueError("Mesh target label must match the declared vertex")
    return {
        "vertices": vertices,
        "triangles": _declared_faces(render.get("triangles"), count),
        "path": _declared_indices(render.get("path"), count, "Mesh path index"),
        "source_vertex": source,
        "target_vertex": target,
        "source_label": source_label,
        "target_label": target_label,
        "declared_planar": planar,
    }


def declared_mesh(mesh, *, path=(), source_vertex=None, target_vertex=None,
                  canvas_id=None, canvas_title=None):
    """Copy a declared triangle mesh for wireframe inspection."""
    if not isinstance(mesh, dict):
        raise ValueError("Mesh render requires the retained mesh declaration")
    geometry = detach_mesh_geometry({
        "vertices": mesh.get("vertices"),
        "triangles": mesh.get("triangles"),
        "path": path,
        "source_vertex": source_vertex,
        "target_vertex": target_vertex,
    })
    identity = canvas_id or mesh.get("coordinate_frame")
    title = canvas_title or mesh.get("coordinate_frame")
    payload = {
        "schema": SCHEMA,
        "kind": "mesh",
        "authority": dict(AUTHORITY),
        "frame": mesh.get("coordinate_frame"),
        "unit": mesh.get("units"),
        "vertices": geometry["vertices"],
        "triangles": geometry["triangles"],
        "path": geometry["path"],
        "source_vertex": geometry["source_vertex"],
        "target_vertex": geometry["target_vertex"],
        "source_label": geometry["source_label"],
        "target_label": geometry["target_label"],
        "declared_planar": geometry["declared_planar"],
        "projection": "first_two_declared_axes",
        "note": ("Wireframe of declared planar vertices"
                 if geometry["declared_planar"]
                 else "Wireframe of declared vertices; 2D clients use the first two axes only"),
    }
    if identity:
        payload["canvas_id"] = identity
    if title:
        payload["canvas_title"] = title
    return deepcopy(payload)


def attach_plane(panel, *, frame, overlays=(), canvas_id=None, canvas_title=None):
    render = plane_from_interleaved(
        panel["values"], panel["labels"], panel["units"], frame=frame, overlays=overlays)
    if canvas_id:
        render["canvas_id"] = canvas_id
        render["canvas_title"] = canvas_title or canvas_id
    panel["render"] = render
    return panel


def _finite_number(value, name):
    if type(value) not in (int, float) or value != value or abs(value) == float("inf"):
        raise ValueError(name)
    return float(value)


def detach_strip_samples(samples):
    """Copy declared parameter samples. Nonfinite or decreasing axes are refused."""
    if not isinstance(samples, list) or not samples:
        raise ValueError("Strip render requires matching nonempty parameter and value lists")
    copied = []
    previous = None
    for item in samples:
        if not isinstance(item, dict):
            raise ValueError("Strip render requires finite numeric samples")
        abscissa = _finite_number(item.get("parameter"), "Strip render requires finite numeric samples")
        ordinate = _finite_number(item.get("value"), "Strip render requires finite numeric samples")
        if previous is not None and abscissa < previous:
            raise ValueError("Strip render requires a nondecreasing parameter")
        previous = abscissa
        copied.append({"parameter": abscissa, "value": ordinate})
    return copied


def strip_endpoint_labels(samples, parameter_name, claimed=None):
    """Name the first and last declared parameter samples. Not interpolation."""
    if not samples:
        return {}
    name = parameter_name or "parameter"
    first = samples[0]["parameter"]
    last = samples[-1]["parameter"]
    labels = {
        "start_parameter": first,
        "end_parameter": last,
        "start_label": "%s=%s" % (name, first),
        "end_label": "%s=%s" % (name, last),
    }
    if first == last:
        labels["end_label"] = None
    if isinstance(claimed, dict):
        for key, value in labels.items():
            offered = claimed.get(key, value)
            if offered != value:
                raise ValueError("Strip endpoint label must match the declared samples")
    return labels


def strip_from_parameter(parameter, values, *, parameter_name, parameter_unit, value_unit, frame,
                         canvas_id=None, canvas_title=None):
    """Place already-projected samples on a declared parameter axis.

    The parameter is copied from the retained record (arclength, sample index
    identity, etc.). This is not event time and not interpolation.
    """
    if not isinstance(parameter, list) or not isinstance(values, list):
        raise ValueError("Strip render requires declared parameter and value lists")
    if len(parameter) != len(values) or not values:
        raise ValueError("Strip render requires matching nonempty parameter and value lists")
    samples = detach_strip_samples([
        {"parameter": abscissa, "value": ordinate}
        for abscissa, ordinate in zip(parameter, values)
    ])
    payload = {
        "schema": SCHEMA,
        "kind": "strip",
        "authority": dict(AUTHORITY),
        "frame": frame,
        "parameter_name": parameter_name,
        "parameter_unit": parameter_unit,
        "value_unit": value_unit,
        "samples": samples,
        "connect": False,
        "note": "Declared parameter axis; points only; not a time trajectory",
    }
    payload.update(strip_endpoint_labels(samples, parameter_name))
    if canvas_id:
        payload["canvas_id"] = canvas_id
        payload["canvas_title"] = canvas_title or canvas_id
    return deepcopy(payload)


def attach_strip(panel, parameter, *, parameter_name, parameter_unit, frame,
                 canvas_id=None, canvas_title=None):
    units = panel.get("units")
    if not isinstance(units, list) or not units:
        raise ValueError("Strip render requires a retained value unit")
    if any(unit != units[0] for unit in units):
        raise ValueError("Strip render refuses mixed units")
    panel["render"] = strip_from_parameter(
        parameter, panel["values"], parameter_name=parameter_name,
        parameter_unit=parameter_unit, value_unit=units[0], frame=frame,
        canvas_id=canvas_id, canvas_title=canvas_title)
    return panel


def attach_system(view, render):
    """Copy a presentation descriptor onto the view so sibling panels keep the canvas."""
    if not isinstance(view, dict):
        raise ValueError("System render requires the inspection view")
    if not isinstance(render, dict) or render.get("schema") != SCHEMA:
        raise ValueError("System render requires a detached panel-render descriptor")
    view["system_render"] = detach_render(render)
    return view


def attach_system_canvases(view, canvases, *, default_id=None):
    """Copy declared alternative canvases. Selection is presentation-only."""
    if not isinstance(view, dict):
        raise ValueError("System canvases require the inspection view")
    if not isinstance(canvases, (list, tuple)) or not canvases:
        raise ValueError("System canvases require a nonempty declared list")
    copied = []
    seen = set()
    for item in canvases:
        if not isinstance(item, dict):
            raise ValueError("System canvas entries must be objects")
        identity = item.get("id")
        render = item.get("render")
        if not isinstance(identity, str) or not identity or identity in seen:
            raise ValueError("System canvas ids must be unique retained identities")
        if not isinstance(render, dict) or render.get("schema") != SCHEMA:
            raise ValueError("System canvas requires a detached panel-render descriptor")
        seen.add(identity)
        payload = detach_render(render)
        payload["canvas_id"] = identity
        payload["canvas_title"] = item.get("title") or identity
        copied.append({
            "id": identity,
            "title": payload["canvas_title"],
            "render": payload,
        })
    chosen = default_id or copied[-1]["id"]
    match = next((item for item in copied if item["id"] == chosen), None)
    if match is None:
        raise ValueError("System canvas default is not one of the declared canvases")
    view["system_canvases"] = copied
    view["system_canvas_id"] = match["id"]
    view["system_render"] = detach_render(match["render"])
    return view
