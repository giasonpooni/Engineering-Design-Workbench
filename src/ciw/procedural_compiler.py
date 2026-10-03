"""Deterministic bounded marching-tetrahedra extraction for visual geometry.

Every cube uses six tetrahedra around the same body diagonal. Vertices retain
their grid-edge interpolation lineage. The only cleanup is exact zero-area and
duplicate-triangle removal; there is no hole filling, smoothing or solid repair.
"""
from __future__ import annotations

from copy import deepcopy
from itertools import combinations
from time import monotonic

import numpy as np

from .operations.runner import digest, seal
from .procedural_contract import (CLAIMS, FRAME, MAX_TRIANGLES, MAX_VERTICES,
                                  RESULT_SCHEMA, UNITS, evaluate, validate_request,
                                  validate_result)

TETRAHEDRA = ((0, 1, 3, 7), (0, 3, 2, 7), (0, 2, 6, 7),
             (0, 6, 4, 7), (0, 4, 5, 7), (0, 5, 1, 7))
TETRA_EDGES = tuple(combinations(range(4), 2))
MAX_GENERATION_SECONDS = 15.0


def generate(request: dict) -> dict:
    """Compile a strict declared field into an inspectable sealed triangle mesh."""
    started = monotonic()
    request = validate_request(request)
    domain, definition = request["domain"], request["definition"]
    resolution = domain["resolution"]
    side = resolution + 1
    axes = [np.linspace(lower, upper, side, dtype=np.float64) for lower, upper in domain["bounds"]]
    grid = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 3)
    values = evaluate(definition["expression"], definition["parameters"], grid[:, 0], grid[:, 1], grid[:, 2])
    vertices, sources, triangles = [], [], []
    edge_cache, triangle_cache = {}, set()

    def point_for_edge(left, right):
        left, right = sorted((left, right))
        if values[left] == 0:
            left = right = left
        elif values[right] == 0:
            left = right = right
        edge = (left, right)
        if edge in edge_cache:
            return edge_cache[edge]
        alpha = 0.0 if left == right else float(values[left] / (values[left] - values[right]))
        if not 0 <= alpha <= 1:
            raise ValueError("Grid-edge interpolation escaped its edge")
        coordinate = (1.0 - alpha) * grid[left] + alpha * grid[right]
        index = len(vertices)
        if index >= MAX_VERTICES:
            raise ValueError("Mesh exceeds the 40000-vertex extraction budget")
        vertices.append(coordinate.tolist())
        sources.append([left, right, alpha])
        edge_cache[edge] = index
        return index

    def add_triangle(indices, direction):
        if len(set(indices)) != 3:
            return
        canonical = tuple(sorted(indices))
        if canonical in triangle_cache:
            return
        p0, p1, p2 = (np.asarray(vertices[index]) for index in indices)
        normal = np.cross(p1 - p0, p2 - p0)
        if np.dot(normal, normal) == 0.0:
            return
        if np.dot(normal, direction) < 0:
            indices = [indices[0], indices[2], indices[1]]
        if len(triangles) >= MAX_TRIANGLES:
            raise ValueError("Mesh exceeds the 65536-triangle extraction budget")
        triangles.append(indices)
        triangle_cache.add(canonical)

    for i in range(resolution):
        if monotonic() - started > MAX_GENERATION_SECONDS:
            raise ValueError("Procedural extraction exceeded its cooperative 15-second deadline")
        for j in range(resolution):
            for k in range(resolution):
                corners = [((i + ((corner >> 2) & 1)) * side + j + ((corner >> 1) & 1)) * side
                           + k + (corner & 1) for corner in range(8)]
                for tetra in TETRAHEDRA:
                    ids = [corners[corner] for corner in tetra]
                    inside = [index for index in range(4) if values[ids[index]] < 0]
                    outside = [index for index in range(4) if values[ids[index]] >= 0]
                    if not inside or not outside:
                        continue
                    # The centroid-to-centroid direction has positive product
                    # with this tetrahedron's affine field gradient, and avoids
                    # computing/inverting a gradient on every tetrahedron.
                    direction = grid[[ids[index] for index in outside]].mean(axis=0) - grid[[ids[index] for index in inside]].mean(axis=0)
                    if len(inside) == 1 or len(outside) == 1:
                        singleton, others = (inside[0], outside) if len(inside) == 1 else (outside[0], inside)
                        face = [point_for_edge(ids[singleton], ids[other]) for other in others]
                        add_triangle(face, direction)
                    else:
                        a, b = inside
                        c, d = outside
                        ac, ad = point_for_edge(ids[a], ids[c]), point_for_edge(ids[a], ids[d])
                        bc, bd = point_for_edge(ids[b], ids[c]), point_for_edge(ids[b], ids[d])
                        add_triangle([ac, ad, bd], direction)
                        add_triangle([ac, bd, bc], direction)
    if not triangles:
        raise ValueError("Declared field produced an empty surface on the bounded grid")
    # Exact-zero cleanup can leave unused intersection vertices. Drop these
    # without changing retained coordinate/lineage values or triangle order.
    used = sorted({index for face in triangles for index in face})
    remap = {index: position for position, index in enumerate(used)}
    result = seal({"schema": RESULT_SCHEMA, "request_digest": digest(request),
                   "mesh": {"vertices": [vertices[index] for index in used],
                            "triangles": [[remap[index] for index in face] for face in triangles],
                            "edge_sources": [sources[index] for index in used], "units": UNITS, "frame": FRAME},
                   "appearance": deepcopy(request["appearance"]), "claims": deepcopy(CLAIMS)})
    validated = validate_result(request, result)
    if monotonic() - started > MAX_GENERATION_SECONDS:
        raise ValueError("Procedural generation exceeded its cooperative 15-second deadline")
    return validated
