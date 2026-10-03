"""Independent audits of UV meshes and CPU-baked RGBA8 texture artifacts.

These checks do not call generation, establish continuous surface error, or
compile a shader on a GPU. Static report validation only checks retained data
and dependencies; an explicit fresh audit recomputes geometry or pixels.
"""
from __future__ import annotations

import base64
from copy import deepcopy
import math
import struct
import zlib

import numpy as np

from .control_contracts import json_tree, keys, number
from .operations.runner import check_seal, digest, seal
from .procedural_contract import CLAIMS
from .procedural_verification import COUNT_METRICS, METRIC_NAMES, _count, _topology

REPORT_SCHEMA = "ciw.procedural-representation-verification.v1"
SURFACE_SCHEMA = "ciw.procedural-surface-request.v1"
TEXTURE_SCHEMA = "ciw.procedural-texture-request.v1"
TOPOLOGY_BINDINGS = {"degenerate_triangles": "degenerate_triangle_count",
                     "duplicate_triangles": "duplicate_triangle_count",
                     "nonmanifold_edges": "nonmanifold_edge_count",
                     "nonmanifold_vertices": "nonmanifold_vertex_count",
                     "orientation_conflicts": "orientation_conflict_count"}
SURFACE_CHECKS = set(TOPOLOGY_BINDINGS) | {
    "coincident_vertices", "unused_vertices", "parameter_coordinates",
    "tessellation_connectivity", "sampled_position_residual", "periodic_seam_residual",
    "parameter_winding", "required_closed_surface",
}
TEXTURE_CHECKS = {"png_structure", "png_rgba_binding", "sampled_channel_bytes"}
TEXTURE_METRICS = {"width", "height", "pixel_count", "max_channel_byte_error", "png_bytes"}


def _decode_png(data: bytes, width: int, height: int) -> bytes:
    """Decode only the declared one-IDAT, RGBA8, filter-zero PNG profile."""
    if type(data) is not bytes or not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) > 8 * 1024 * 1024:
        raise ValueError("Invalid or oversized PNG signature")
    offset, chunks = 8, []
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError("Truncated PNG chunk")
        length, = struct.unpack(">I", data[offset:offset + 4])
        end = offset + 12 + length
        if end > len(data):
            raise ValueError("PNG chunk exceeds retained bytes")
        kind, payload = data[offset + 4:offset + 8], data[offset + 8:offset + 8 + length]
        actual_crc, = struct.unpack(">I", data[offset + 8 + length:end])
        if zlib.crc32(kind + payload) & 0xffffffff != actual_crc:
            raise ValueError("PNG chunk CRC differs")
        chunks.append((kind, payload))
        offset = end
    if [kind for kind, _ in chunks] != [b"IHDR", b"IDAT", b"IEND"]:
        raise ValueError("PNG chunk order differs from the bounded profile")
    ihdr, compressed, end = (payload for _kind, payload in chunks)
    if len(ihdr) != 13 or struct.unpack(">IIBBBBB", ihdr) != (width, height, 8, 6, 0, 0, 0) or end:
        raise ValueError("PNG dimensions or RGBA8 encoding differ")
    expected = height * (1 + 4 * width)
    inflater = zlib.decompressobj()
    try:
        raw = inflater.decompress(compressed, expected + 1)
    except zlib.error as exc:
        raise ValueError("Invalid PNG deflate stream") from exc
    if (len(raw) != expected or inflater.unconsumed_tail or inflater.unused_data or not inflater.eof):
        raise ValueError("PNG deflate length or termination differs")
    stride = 1 + 4 * width
    if any(raw[row * stride] != 0 for row in range(height)):
        raise ValueError("Only declared zero-filter PNG rows are supported")
    return b"".join(raw[row * stride + 1:(row + 1) * stride] for row in range(height))


def decode_texture_png(data: bytes, width: int, height: int) -> bytes:
    """Independently reopen the bounded exported PNG and return decoded RGBA8."""
    if (type(width) is not int or type(height) is not int
            or not 16 <= width <= 256 or not 16 <= height <= 256):
        raise ValueError("Exported texture dimensions exceed the bounded profile")
    return _decode_png(data, width, height)


def _contracts(request, result):
    schema = request.get("schema") if type(request) is dict else None
    if schema == SURFACE_SCHEMA:
        from .procedural_surface import validate_surface_request, validate_surface_result
        request = validate_surface_request(request)
        return request, validate_surface_result(request, result)
    if schema == TEXTURE_SCHEMA:
        from .procedural_texture import validate_texture_request, validate_texture_result
        request = validate_texture_request(request)
        return request, validate_texture_result(request, result)
    raise ValueError("Unsupported procedural representation request")


def _surface_values(request, coordinates):
    from .graphics_notation import evaluate_uv
    definition = request["definition"]
    coordinates = np.asarray(coordinates, dtype=float)
    return np.stack([evaluate_uv(expression, definition["parameters"], coordinates[:, 0], coordinates[:, 1])
                     for expression in definition["expressions"]], axis=1)


def _surface_lattice(request):
    domain = request["domain"]
    nu, nv = domain["resolution"]
    periodic_u, periodic_v = domain["periodic"]
    axes = [np.linspace(lo, hi, count if periodic else count + 1, endpoint=not periodic)
            for (lo, hi), count, periodic in zip(domain["bounds"], (nu, nv), domain["periodic"])]
    u_count, v_count = len(axes[0]), len(axes[1])
    coordinates = [[float(u), float(v)] for u in axes[0] for v in axes[1]]
    triangles = []
    for i in range(nu):
        for j in range(nv):
            next_i, next_j = (i + 1) % u_count, (j + 1) % v_count
            a, b = i * v_count + j, next_i * v_count + j
            c, d = next_i * v_count + next_j, i * v_count + next_j
            triangles.extend([[a, b, c], [a, c, d]])
    return coordinates, triangles


def _parameter_winding(request, mesh, actual_normals):
    coordinates = np.asarray(mesh["parameter_coordinates"], dtype=float)
    centers = []
    for face in mesh["triangles"]:
        uv = coordinates[face].copy()
        for axis, ((lo, hi), periodic) in enumerate(zip(request["domain"]["bounds"], request["domain"]["periodic"])):
            if periodic:
                span = hi - lo
                delta = uv[:, axis] - uv[0, axis]
                uv[:, axis] -= span * np.floor(delta / span + 0.5)
        center = np.mean(uv, axis=0)
        for axis, ((lo, hi), periodic) in enumerate(zip(request["domain"]["bounds"], request["domain"]["periodic"])):
            if periodic:
                center[axis] = lo + (center[axis] - lo) % (hi - lo)
        centers.append(center)
    centers = np.asarray(centers)
    derivatives = []
    for axis, (lo, hi) in enumerate(request["domain"]["bounds"]):
        step = (hi - lo) / request["domain"]["resolution"][axis] * 1e-4
        lower, upper = centers.copy(), centers.copy()
        lower[:, axis] = np.maximum(lo, centers[:, axis] - step)
        upper[:, axis] = np.minimum(hi, centers[:, axis] + step)
        derivatives.append((_surface_values(request, upper) - _surface_values(request, lower)) /
                           (upper[:, axis] - lower[:, axis])[:, None])
    expected_normals = np.cross(*derivatives)
    products = np.sum(expected_normals * actual_normals, axis=1)
    scale = np.sum(np.abs(expected_normals), axis=1)
    return float(np.count_nonzero(products <= 1e-8 * scale))


def _verify_surface(request, result):
    mesh = result["mesh"]
    metrics, values, _centers, normals = _topology(mesh)
    expected_coordinates, expected_triangles = _surface_lattice(request)
    values["parameter_coordinates"] = float(mesh["parameter_coordinates"] != expected_coordinates)
    values["tessellation_connectivity"] = float(mesh["triangles"] != expected_triangles)
    expected = _surface_values(request, mesh["parameter_coordinates"])
    metrics["max_field_residual"] = float(np.max(np.abs(expected - np.asarray(mesh["vertices"]))))
    values["sampled_position_residual"] = metrics["max_field_residual"]
    seam_residual = 0.0
    for axis, periodic in enumerate(request["domain"]["periodic"]):
        if periodic:
            other = 1 - axis
            lo, hi = request["domain"]["bounds"][axis]
            other_lo, other_hi = request["domain"]["bounds"][other]
            points = np.zeros((request["domain"]["resolution"][other] + 1, 2))
            points[:, other] = np.linspace(other_lo, other_hi, len(points))
            points[:, axis] = lo
            opposite = points.copy()
            opposite[:, axis] = hi
            seam_residual = max(seam_residual, float(np.max(np.abs(_surface_values(request, points) - _surface_values(request, opposite)))))
    values["periodic_seam_residual"] = seam_residual
    values["parameter_winding"] = _parameter_winding(request, mesh, normals)
    values["required_closed_surface"] = float(metrics["boundary_edge_count"]) if request["verification"]["require_closed"] else 0.0
    return metrics, values


def _verify_texture(request, result):
    from .graphics_notation import evaluate_uv
    image = result["image"]
    width, height = image["width"], image["height"]
    rgba = base64.b64decode(image["rgba_base64"], validate=True)
    png = base64.b64decode(image["png_base64"], validate=True)
    (u0, u1), (v0, v1) = request["domain"]["bounds"]
    u = u0 + (np.arange(width) + 0.5) * ((u1 - u0) / width)
    v = v0 + (np.arange(height) + 0.5) * ((v1 - v0) / height)
    uu, vv = np.meshgrid(u, v, indexing="xy")
    definition = request["definition"]
    channels = [evaluate_uv(expression, definition["parameters"], uu, vv) for expression in definition["expressions"]]
    channels.append(np.ones_like(uu))  # Alpha is fixed opaque in this profile.
    # Explicit positive half-up quantization; neither bankers' round nor the
    # texture generator is used to audit the declared clipped channels.
    expected = np.floor(np.clip(np.stack(channels, axis=-1), 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8).tobytes()
    observed = np.frombuffer(rgba, dtype=np.uint8).astype(np.int16)
    wanted = np.frombuffer(expected, dtype=np.uint8).astype(np.int16)
    max_error = int(np.max(np.abs(observed - wanted)))
    values = {"sampled_channel_bytes": float(max_error), "png_structure": 0.0, "png_rgba_binding": 0.0}
    try:
        decoded = _decode_png(png, width, height)
        values["png_rgba_binding"] = float(sum(left != right for left, right in zip(decoded, rgba)))
    except ValueError:
        values["png_structure"] = 1.0
    metrics = {"width": width, "height": height, "pixel_count": width * height,
               "max_channel_byte_error": max_error, "png_bytes": len(png)}
    return metrics, values


def _spec(request):
    names = SURFACE_CHECKS if request["schema"] == SURFACE_SCHEMA else TEXTURE_CHECKS
    return {name: request["verification"]["field_tolerance"]
            if name in {"sampled_position_residual", "periodic_seam_residual"} else 0.0 for name in names}


def verify(request: dict, result: dict) -> dict:
    """Fresh independent mesh/pixel audit; no generator, GPU or external provider."""
    request, result = _contracts(request, result)
    metrics, values = (_verify_surface if request["schema"] == SURFACE_SCHEMA else _verify_texture)(request, result)
    checks = [{"name": name, "value": values[name], "tolerance": tolerance,
               "status": "PASS" if values[name] <= tolerance else "FAIL"}
              for name, tolerance in sorted(_spec(request).items())]
    return seal({"schema": REPORT_SCHEMA, "request_digest": digest(request), "candidate_digest": result["record_digest"],
                 "status": "PASS" if all(row["status"] == "PASS" for row in checks) else "FAIL",
                 "checks": checks, "metrics": metrics, "claims": deepcopy(CLAIMS)})


def validate_report(request: dict, result: dict, report: dict) -> dict:
    """Retained structure, seals and bindings only; no expression/PNG audit."""
    request, result = _contracts(request, result)
    json_tree(report)
    keys(report, {"schema", "request_digest", "candidate_digest", "status", "checks", "metrics", "claims", "record_digest"})
    if (report["schema"] != REPORT_SCHEMA or report["request_digest"] != digest(request)
            or report["candidate_digest"] != result["record_digest"] or report["claims"] != CLAIMS
            or report["status"] not in {"PASS", "FAIL"}):
        raise ValueError("Retained representation report identity or authority differs")
    metrics = report["metrics"]
    if request["schema"] == SURFACE_SCHEMA:
        keys(metrics, METRIC_NAMES)
        for name in COUNT_METRICS:
            _count(metrics[name])
        for name in ("minimum_triangle_quality", "surface_area", "max_field_residual"):
            if not 0 <= number(metrics[name]) <= (1.0 if name == "minimum_triangle_quality" else 1e150):
                raise ValueError("Invalid retained surface metric")
        if (metrics["vertex_count"] != len(result["mesh"]["vertices"])
                or metrics["triangle_count"] != len(result["mesh"]["triangles"])
                or not 1 <= metrics["component_count"] <= metrics["vertex_count"]):
            raise ValueError("Retained surface counts contradict mesh arrays")
        limits = {"boundary_edge_count": 3 * metrics["triangle_count"],
                  "orientation_conflict_count": 3 * metrics["triangle_count"],
                  "nonmanifold_edge_count": 3 * metrics["triangle_count"],
                  "nonmanifold_vertex_count": metrics["vertex_count"],
                  "duplicate_triangle_count": metrics["triangle_count"],
                  "degenerate_triangle_count": metrics["triangle_count"]}
        if any(metrics[name] > upper for name, upper in limits.items()):
            raise ValueError("Retained surface topology counts exceed candidate array bounds")
        expected_box = [[min(point[axis] for point in result["mesh"]["vertices"]),
                         max(point[axis] for point in result["mesh"]["vertices"])] for axis in range(3)]
        box = metrics["bounding_box"]
        if type(box) is not list or len(box) != 3:
            raise ValueError("Retained surface bounds require three coordinate pairs")
        for pair in box:
            if type(pair) is not list or len(pair) != 2:
                raise ValueError("Retained surface bounds require coordinate pairs")
            for value in pair:
                number(value)
        if box != expected_box:
            raise ValueError("Retained surface bounds contradict mesh coordinates")
    else:
        keys(metrics, TEXTURE_METRICS)
        for name, value in metrics.items():
            if name == "png_bytes":
                if type(value) is not int or not 1 <= value <= 1024 * 1024:
                    raise ValueError("Retained PNG byte count exceeds the artifact budget")
            else:
                _count(value)
        image = result["image"]
        if (metrics["width"] != image["width"] or metrics["height"] != image["height"]
                or metrics["pixel_count"] != image["width"] * image["height"]
                or metrics["png_bytes"] != len(base64.b64decode(image["png_base64"], validate=True))
                or metrics["max_channel_byte_error"] > 255):
            raise ValueError("Retained texture metrics contradict image declarations")
    spec, values = _spec(request), {}
    if type(report["checks"]) is not list or len(report["checks"]) != len(spec):
        raise ValueError("Retained representation checks are missing or duplicated")
    for row in report["checks"]:
        keys(row, {"name", "value", "tolerance", "status"})
        name = row["name"]
        if type(name) is not str or name not in spec or name in values:
            raise ValueError("Unknown or duplicate representation check")
        value, tolerance = number(row["value"]), number(row["tolerance"])
        if value < 0 or tolerance != spec[name] or row["status"] != ("PASS" if value <= tolerance else "FAIL"):
            raise ValueError("Retained representation check contradicts its threshold or status")
        if name not in {"sampled_position_residual", "periodic_seam_residual"} and not value.is_integer():
            raise ValueError("Retained representation errors require integer counts or byte errors")
        values[name] = value
    if request["schema"] == SURFACE_SCHEMA:
        bindings = TOPOLOGY_BINDINGS | {"sampled_position_residual": "max_field_residual"}
        if any(values[name] != metrics[metric] for name, metric in bindings.items()):
            raise ValueError("Retained surface checks contradict metrics")
        expected_closed = float(metrics["boundary_edge_count"]) if request["verification"]["require_closed"] else 0.0
        if values["required_closed_surface"] != expected_closed:
            raise ValueError("Retained surface closure contradicts boundary declaration")
    elif values["sampled_channel_bytes"] != metrics["max_channel_byte_error"]:
        raise ValueError("Retained texture pixel error contradicts metric")
    elif values["png_structure"] not in (0.0, 1.0) or values["png_rgba_binding"] > metrics["pixel_count"] * 4:
        raise ValueError("Retained PNG errors exceed the declared image/check bounds")
    if report["status"] != ("PASS" if all(row["status"] == "PASS" for row in report["checks"]) else "FAIL"):
        raise ValueError("Retained representation status contradicts its checks")
    check_seal(report)
    return deepcopy(report)
