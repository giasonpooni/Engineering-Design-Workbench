"""Independent, bounded checks of a retained procedural triangle mesh.

The verifier reads grid-edge lineage and checks geometry; it never calls the
extractor. Field agreement is sampled at vertices and winding is checked with
finite differences. Neither check establishes continuous fidelity, absence of
self-intersections, physical properties or manufacturing suitability. Static
report validation does not evaluate the expression or repeat mesh verification.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import math

import numpy as np

from .control_contracts import json_tree, keys, number
from .operations.runner import check_seal, digest, seal
from .procedural_contract import CLAIMS, evaluate_field, validate_request, validate_result

REPORT_SCHEMA = "ciw.procedural-verification.v1"
MAX_METRIC = 1e150
COUNT_METRICS = {
    "vertex_count", "triangle_count", "boundary_edge_count", "component_count",
    "orientation_conflict_count", "nonmanifold_edge_count", "nonmanifold_vertex_count",
    "duplicate_triangle_count", "degenerate_triangle_count",
}
METRIC_NAMES = COUNT_METRICS | {
    "minimum_triangle_quality", "surface_area", "max_field_residual", "bounding_box",
}
ZERO_CHECKS = {
    "lineage_grid_edges", "lineage_root_interpolation", "lineage_coordinates",
    "vertices_in_domain", "coincident_vertices", "unused_vertices",
    "degenerate_triangles", "duplicate_triangles", "nonmanifold_edges",
    "nonmanifold_vertices", "orientation_conflicts", "increasing_field_winding",
}
CHECK_NAMES = ZERO_CHECKS | {"sampled_field_residual", "required_closed_surface"}


def _count(value):
    if type(value) is not int or not 0 <= value <= 1_000_000:
        raise ValueError("Mesh counts require bounded nonnegative integers")
    return value


def _bounded(value):
    return min(abs(float(value)), MAX_METRIC) if math.isfinite(value) else MAX_METRIC


def _check_spec(request):
    return {name: request["verification"]["field_tolerance"] if name == "sampled_field_residual" else 0.0
            for name in CHECK_NAMES}


def _grid_point(request, node):
    """Decode the fixed i-major Cartesian lattice, without importing extraction."""
    n = request["domain"]["resolution"]
    side = n + 1
    i, remaining = divmod(node, side * side)
    j, k = divmod(remaining, side)
    index = (i, j, k)
    # The declaration uses linspace: form its binary64 step before multiplying
    # the integer index. Reordering (hi-lo)*index/n can move exact-zero samples
    # and noticeably change roots of almost-zero grid edges.
    point = tuple(hi if component == n else lo + ((hi - lo) / n) * component
                  for component, (lo, hi) in zip(index, request["domain"]["bounds"]))
    return index, point


def _lineage(request, mesh):
    vertices, sources = mesh["vertices"], mesh["edge_sources"]
    n = request["domain"]["resolution"]
    last = (n + 1) ** 3
    cache = {}
    for a, b, _alpha in sources:
        for node in (a, b):
            if node not in cache and type(node) is int and 0 <= node < last:
                cache[node] = _grid_point(request, node)
    ordered = list(cache)
    values = evaluate_field(request, np.asarray([cache[node][1] for node in ordered], dtype=float))
    field = {node: float(value) - request["surface"]["isovalue"] for node, value in zip(ordered, values)}
    edge_failures = root_failures = coordinate_failures = 0
    scale = max(1.0, *(abs(value) for bounds in request["domain"]["bounds"] for value in bounds))
    coordinate_allowance = 256 * math.ulp(scale)
    for vertex, (a, b, alpha) in zip(vertices, sources):
        valid = (type(a) is int and type(b) is int and 0 <= a <= b < last)
        if valid and a != b:
            delta = [right - left for left, right in zip(cache[a][0], cache[b][0])]
            # Six tetrahedra meet the 0--7 cube diagonal. Their edges join
            # comparable corners (only positive, at most one-step changes).
            valid = all(value in (0, 1) for value in delta) and any(delta)
        if not valid:
            edge_failures += 1
            continue
        fa, fb = field[a], field[b]
        if a == b:
            root_valid = fa == 0.0 and alpha == 0.0
        else:
            crossing = (fa < 0 < fb) or (fb < 0 < fa)
            expected_alpha = fa / (fa - fb) if crossing else -1.0
            root_valid = crossing and abs(alpha - expected_alpha) <= 256 * math.ulp(1.0)
        root_failures += not root_valid
        expected = [(1.0 - alpha) * left + alpha * right
                    for left, right in zip(cache[a][1], cache[b][1])]
        coordinate_failures += any(abs(float(actual) - wanted) > coordinate_allowance
                                   for actual, wanted in zip(vertex, expected))
    return {"lineage_grid_edges": float(edge_failures),
            "lineage_root_interpolation": float(root_failures),
            "lineage_coordinates": float(coordinate_failures)}


def _topology(mesh):
    vertices = [tuple(map(float, point)) for point in mesh["vertices"]]
    faces = mesh["triangles"]
    adjacency = [set() for _ in vertices]
    links = [defaultdict(set) for _ in vertices]
    edges, seen = defaultdict(list), set()
    duplicates = degenerates = 0
    qualities, areas, normals, centers = [], [], [], []
    for face in faces:
        a, b, c = (vertices[index] for index in face)
        face_key = tuple(sorted(face))
        duplicates += face_key in seen
        seen.add(face_key)
        u, v = tuple(b[i] - a[i] for i in range(3)), tuple(c[i] - a[i] for i in range(3))
        cross = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        magnitude = math.hypot(*cross)
        longest = max(math.dist(a, b), math.dist(b, c), math.dist(c, a))
        quality = magnitude / longest ** 2 if longest else 0.0
        degenerates += magnitude == 0.0
        qualities.append(quality)
        areas.append(0.5 * magnitude)
        normals.append(tuple(value / magnitude for value in cross) if magnitude else (0.0, 0.0, 0.0))
        centers.append(tuple(math.fsum(point[axis] for point in (a, b, c)) / 3.0 for axis in range(3)))
        for position, i in enumerate(face):
            j = face[(position + 1) % 3]
            edges[tuple(sorted((i, j)))].append((i, j))
            adjacency[i].add(j)
            adjacency[j].add(i)
            x, y = face[(position + 1) % 3], face[(position + 2) % 3]
            links[i][x].add(y)
            links[i][y].add(x)
    nonmanifold_vertices = 0
    for link in links:
        if not link:
            nonmanifold_vertices += 1
            continue
        reached, pending = set(), [next(iter(link))]
        while pending:
            vertex = pending.pop()
            if vertex not in reached:
                reached.add(vertex)
                pending.extend(link[vertex] - reached)
        degrees = [len(neighbors) for neighbors in link.values()]
        nonmanifold_vertices += (len(reached) != len(link)
                                 or any(degree not in (1, 2) for degree in degrees)
                                 or degrees.count(1) not in (0, 2))
    components, reached = 0, set()
    for vertex in range(len(vertices)):
        if vertex in reached:
            continue
        components += 1
        pending = [vertex]
        while pending:
            current = pending.pop()
            if current not in reached:
                reached.add(current)
                pending.extend(adjacency[current] - reached)
    metrics = {"vertex_count": len(vertices), "triangle_count": len(faces),
               "boundary_edge_count": sum(len(incident) == 1 for incident in edges.values()),
               "component_count": components,
               "orientation_conflict_count": sum(len(incident) == 2 and incident[0] == incident[1]
                                                  for incident in edges.values()),
               "nonmanifold_edge_count": sum(len(incident) > 2 for incident in edges.values()),
               "nonmanifold_vertex_count": int(nonmanifold_vertices),
               "duplicate_triangle_count": int(duplicates), "degenerate_triangle_count": int(degenerates),
               "minimum_triangle_quality": min(qualities), "surface_area": math.fsum(areas),
               "bounding_box": [[min(point[axis] for point in vertices), max(point[axis] for point in vertices)]
                                for axis in range(3)]}
    errors = {"coincident_vertices": float(len(vertices) - len(set(vertices))),
              "unused_vertices": float(sum(not neighbors for neighbors in adjacency)),
              "degenerate_triangles": float(degenerates), "duplicate_triangles": float(duplicates),
              "nonmanifold_edges": float(metrics["nonmanifold_edge_count"]),
              "nonmanifold_vertices": float(metrics["nonmanifold_vertex_count"]),
              "orientation_conflicts": float(metrics["orientation_conflict_count"])}
    return metrics, errors, np.asarray(centers), np.asarray(normals)


def _winding(request, centers, normals):
    """Sample bounded one-sided/central differences inside the declared box."""
    gradients = np.empty_like(centers)
    for axis, (lo, hi) in enumerate(request["domain"]["bounds"]):
        step = (hi - lo) / request["domain"]["resolution"] * 1e-4
        lower, upper = centers.copy(), centers.copy()
        lower[:, axis] = np.maximum(lo, centers[:, axis] - step)
        upper[:, axis] = np.minimum(hi, centers[:, axis] + step)
        width = upper[:, axis] - lower[:, axis]
        values_lower, values_upper = evaluate_field(request, lower), evaluate_field(request, upper)
        gradients[:, axis] = (values_upper - values_lower) / width
    products = np.sum(gradients * normals, axis=1)
    scale = np.sum(np.abs(gradients), axis=1)
    # A positive rescaling of a scalar field must not weaken its orientation
    # check. Normalize the allowance by gradient size, without an absolute
    # floor that would accept an entirely reversed, small-amplitude field.
    # A zero or numerically tangential gradient cannot establish winding.
    allowance = 1e-8 * scale
    return float(np.count_nonzero(products <= allowance))


def verify(request: dict, result: dict) -> dict:
    """Freshly check a bounded mesh without invoking extraction or simulation."""
    request = validate_request(request)
    result = validate_result(request, result)
    mesh = result["mesh"]
    metrics, errors, centers, normals = _topology(mesh)
    errors.update(_lineage(request, mesh))
    errors["vertices_in_domain"] = float(sum(any(value < lo or value > hi for value, (lo, hi)
                                           in zip(point, request["domain"]["bounds"]))
                                        for point in mesh["vertices"]))
    errors["increasing_field_winding"] = _winding(request, centers, normals)
    field = evaluate_field(request, np.asarray(mesh["vertices"], dtype=float))
    metrics["max_field_residual"] = _bounded(float(np.max(np.abs(field - request["surface"]["isovalue"]))))
    errors["sampled_field_residual"] = metrics["max_field_residual"]
    errors["required_closed_surface"] = (float(metrics["boundary_edge_count"])
                                         if request["verification"]["require_closed"] else 0.0)
    spec = _check_spec(request)
    checks = [{"name": name, "status": "PASS" if errors[name] <= spec[name] else "FAIL",
               "value": errors[name], "tolerance": spec[name]} for name in sorted(spec)]
    return seal({"schema": REPORT_SCHEMA, "request_digest": digest(request),
                 "candidate_digest": result["record_digest"],
                 "status": "PASS" if all(row["status"] == "PASS" for row in checks) else "FAIL",
                 "checks": checks, "metrics": metrics, "claims": deepcopy(CLAIMS)})


def validate_report(request: dict, result: dict, report: dict) -> dict:
    """Validate retained declarations; coherent numerical forgeries need a fresh check."""
    request = validate_request(request)
    result = validate_result(request, result)
    json_tree(report)
    keys(report, {"schema", "request_digest", "candidate_digest", "status", "checks", "metrics", "claims", "record_digest"})
    if (report["schema"] != REPORT_SCHEMA or report["request_digest"] != digest(request)
            or report["candidate_digest"] != result["record_digest"] or report["claims"] != CLAIMS
            or report["status"] not in {"PASS", "FAIL"}):
        raise ValueError("Retained procedural report identity or authority differs")
    metrics = report["metrics"]
    keys(metrics, METRIC_NAMES)
    for name in COUNT_METRICS:
        _count(metrics[name])
    for name in ("minimum_triangle_quality", "surface_area", "max_field_residual"):
        if not 0 <= number(metrics[name]) <= (1.0 if name == "minimum_triangle_quality" else MAX_METRIC):
            raise ValueError("Retained mesh metrics require bounded nonnegative finite values")
    if (metrics["vertex_count"] != len(result["mesh"]["vertices"])
            or metrics["triangle_count"] != len(result["mesh"]["triangles"])
            or not 1 <= metrics["component_count"] <= metrics["vertex_count"]):
        raise ValueError("Retained mesh count declarations contradict candidate arrays")
    limits = {"boundary_edge_count": 3 * metrics["triangle_count"],
              "orientation_conflict_count": 3 * metrics["triangle_count"],
              "nonmanifold_edge_count": 3 * metrics["triangle_count"],
              "nonmanifold_vertex_count": metrics["vertex_count"],
              "duplicate_triangle_count": metrics["triangle_count"],
              "degenerate_triangle_count": metrics["triangle_count"]}
    if any(metrics[name] > upper for name, upper in limits.items()):
        raise ValueError("Retained topology counts exceed their candidate array bounds")
    box = metrics["bounding_box"]
    if type(box) is not list or len(box) != 3:
        raise ValueError("Retained mesh bounding box requires three ordered coordinate pairs")
    for axis, bounds in enumerate(box):
        if type(bounds) is not list or len(bounds) != 2:
            raise ValueError("Retained mesh bounding box requires coordinate pairs")
        if (number(bounds[0]) > number(bounds[1]) or
                bounds != [min(point[axis] for point in result["mesh"]["vertices"]),
                           max(point[axis] for point in result["mesh"]["vertices"])]):
            raise ValueError("Retained mesh bounding box contradicts candidate coordinates")
    spec = _check_spec(request)
    checks = report["checks"]
    if type(checks) is not list or len(checks) != len(spec):
        raise ValueError("Retained procedural report is missing or duplicates checks")
    values = {}
    for row in checks:
        keys(row, {"name", "status", "value", "tolerance"})
        name = row["name"]
        if type(name) is not str or name not in spec or name in values:
            raise ValueError("Retained procedural report has an unknown or duplicate check")
        value, tolerance = number(row["value"]), number(row["tolerance"])
        if value < 0 or tolerance != spec[name] or row["status"] != ("PASS" if value <= tolerance else "FAIL"):
            raise ValueError("Retained procedural check contradicts its threshold or status")
        if name != "sampled_field_residual" and (not value.is_integer() or value > 3 * metrics["triangle_count"] + metrics["vertex_count"]):
            raise ValueError("Retained topology and lineage errors require bounded integer counts")
        values[name] = value
    bindings = {"degenerate_triangles": "degenerate_triangle_count", "duplicate_triangles": "duplicate_triangle_count",
                "nonmanifold_edges": "nonmanifold_edge_count", "nonmanifold_vertices": "nonmanifold_vertex_count",
                "orientation_conflicts": "orientation_conflict_count", "sampled_field_residual": "max_field_residual"}
    if any(values[name] != metrics[metric] for name, metric in bindings.items()):
        raise ValueError("Retained procedural checks contradict their metric declarations")
    expected_closed = float(metrics["boundary_edge_count"]) if request["verification"]["require_closed"] else 0.0
    if values["required_closed_surface"] != expected_closed:
        raise ValueError("Retained closure check contradicts the declared boundary count or requirement")
    expected = "PASS" if all(row["status"] == "PASS" for row in checks) else "FAIL"
    if report["status"] != expected:
        raise ValueError("Retained procedural report status contradicts its checks")
    check_seal(report)
    return deepcopy(report)
