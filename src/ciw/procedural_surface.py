"""Declared UV-parametric visual surfaces with retained notation and sampling."""
from __future__ import annotations

from copy import deepcopy
import json
import math
from time import monotonic

import numpy as np

from .control_contracts import MAX_BYTES, keys, number
from .graphics_notation import compile_uv, evaluate_uv, validate_parameters
from .operations.runner import check_seal, digest, seal
from .procedural_contract import CLAIMS, FIELD_LIMIT, FRAME, UNITS

REQUEST_SCHEMA = "ciw.procedural-surface-request.v1"
RESULT_SCHEMA = "ciw.procedural-surface-mesh.v1"
MAX_GENERATION_SECONDS = 15.0


def _bounds(bounds):
    if type(bounds) is not list or len(bounds) != 2:
        raise ValueError("Require two UV axis bounds")
    for pair in bounds:
        if type(pair) is not list or len(pair) != 2:
            raise ValueError("UV bounds must contain lower and upper values")
        lo, hi = map(number, pair)
        if not -10 <= lo < hi <= 10 or hi - lo < 0.1:
            raise ValueError("UV bounds must lie within -10..10 with span at least 0.1")


def _appearance(appearance):
    keys(appearance, {"base_color", "roughness", "metallic"})
    if type(appearance["base_color"]) is not list or len(appearance["base_color"]) != 3:
        raise ValueError("Require three visual color channels")
    if any(not 0 <= number(channel) <= 1 for channel in appearance["base_color"]):
        raise ValueError("Visual color channels must lie inside 0..1")
    if not 0.05 <= number(appearance["roughness"]) <= 1 or not 0 <= number(appearance["metallic"]) <= 1:
        raise ValueError("Visual roughness/metallic parameters exceed their bounds")


def validate_surface_request(request: dict) -> dict:
    keys(request, {"schema", "definition", "domain", "appearance", "verification"})
    if request["schema"] != REQUEST_SCHEMA:
        raise ValueError("Unsupported parametric surface schema")
    definition = request["definition"]
    keys(definition, {"expressions", "parameters"})
    validate_parameters(definition["parameters"])
    if type(definition["expressions"]) is not list or len(definition["expressions"]) != 3:
        raise ValueError("Require three Cartesian position expressions in UV coordinates")
    for expression in definition["expressions"]:
        compile_uv(expression, definition["parameters"])
    domain = request["domain"]
    keys(domain, {"bounds", "resolution", "periodic", "units", "frame"})
    _bounds(domain["bounds"])
    if (type(domain["resolution"]) is not list or len(domain["resolution"]) != 2
            or any(type(value) is not int or not 8 <= value <= 48 for value in domain["resolution"])):
        raise ValueError("UV resolution must contain two integers inside 8..48")
    if type(domain["periodic"]) is not list or len(domain["periodic"]) != 2 or any(type(value) is not bool for value in domain["periodic"]):
        raise ValueError("Declare periodicity independently for each UV axis")
    if domain["units"] != UNITS or domain["frame"] != FRAME:
        raise ValueError("Require normalized visual Cartesian units/frame")
    _appearance(request["appearance"])
    keys(request["verification"], {"field_tolerance", "require_closed"})
    if not 0.001 <= number(request["verification"]["field_tolerance"]) <= 2 or type(request["verification"]["require_closed"]) is not bool:
        raise ValueError("Declare a bounded surface tolerance and boolean closure requirement")
    if len((json.dumps(request, indent=2, allow_nan=False) + "\n").encode()) > 65536:
        raise ValueError("Surface declaration exceeds 64KiB")
    return deepcopy(request)


def validate_surface_result(request: dict, result: dict) -> dict:
    """Static data/identity validation; never evaluates parametric expressions."""
    request = validate_surface_request(request)
    keys(result, {"schema", "request_digest", "mesh", "appearance", "claims", "ir", "record_digest"})
    if result["schema"] != RESULT_SCHEMA or result["request_digest"] != digest(request):
        raise ValueError("Surface result schema or request binding differs")
    _appearance(result["appearance"])
    if result["appearance"] != request["appearance"] or result["claims"] != CLAIMS:
        raise ValueError("Retained visual appearance or claim scope differs")
    expected_ir = [compile_uv(expression, request["definition"]["parameters"]) for expression in request["definition"]["expressions"]]
    if digest(result["ir"]) != digest(expected_ir):
        raise ValueError("Retained typed surface IR differs from declared notation")
    mesh = result["mesh"]
    keys(mesh, {"vertices", "triangles", "parameter_coordinates", "units", "frame"})
    if mesh["units"] != UNITS or mesh["frame"] != FRAME:
        raise ValueError("Surface mesh units/frame differs")
    vertices, triangles, parameters = mesh["vertices"], mesh["triangles"], mesh["parameter_coordinates"]
    if type(vertices) is not list or not 3 <= len(vertices) <= 40000 or type(triangles) is not list or not 1 <= len(triangles) <= 65536:
        raise ValueError("Surface mesh array counts exceed the profile")
    if type(parameters) is not list or len(parameters) != len(vertices):
        raise ValueError("Every vertex requires its UV sampling coordinate")
    for vertex in vertices:
        if type(vertex) is not list or len(vertex) != 3 or any(abs(number(value)) > FIELD_LIMIT for value in vertex):
            raise ValueError("Require finite bounded Cartesian surface vertices")
    for coordinate in parameters:
        if (type(coordinate) is not list or len(coordinate) != 2
                or any(not lo <= number(value) <= hi for value, (lo, hi) in zip(coordinate, request["domain"]["bounds"]))):
            raise ValueError("Surface UV samples exceed the declared bounds")
    for face in triangles:
        if type(face) is not list or len(face) != 3 or any(type(index) is not int or not 0 <= index < len(vertices) for index in face):
            raise ValueError("Surface triangle indices exceed the vertex array")
    check_seal(result)
    if len((json.dumps(result, indent=2, allow_nan=False) + "\n").encode()) > MAX_BYTES:
        raise ValueError("Surface artifact exceeds 8MiB")
    return deepcopy(result)


def generate_surface(request: dict) -> dict:
    started = monotonic()
    request = validate_surface_request(request)
    domain, definition = request["domain"], request["definition"]
    axes = [np.linspace(lo, hi, resolution + (not periodic), endpoint=not periodic, dtype=np.float64)
            for (lo, hi), resolution, periodic in zip(domain["bounds"], domain["resolution"], domain["periodic"])]
    coordinates = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 2)
    channels = []
    for expression in definition["expressions"]:
        channels.append(evaluate_uv(expression, definition["parameters"], coordinates[:, 0], coordinates[:, 1]))
        if monotonic() - started > MAX_GENERATION_SECONDS:
            raise ValueError("Surface evaluation exceeded its cooperative 15-second deadline")
    vertices = np.stack(channels, axis=-1)
    nu, nv = domain["resolution"]
    u_count, v_count = map(len, axes)
    triangles = []
    for i in range(nu):
        if monotonic() - started > MAX_GENERATION_SECONDS:
            raise ValueError("Surface tessellation exceeded its cooperative 15-second deadline")
        for j in range(nv):
            a, b, c, d = i * v_count + j, ((i + 1) % u_count) * v_count + j, ((i + 1) % u_count) * v_count + (j + 1) % v_count, i * v_count + (j + 1) % v_count
            triangles.extend([[a, b, c], [a, c, d]])
    result = seal({"schema": RESULT_SCHEMA, "request_digest": digest(request),
                   "mesh": {"vertices": vertices.tolist(), "triangles": triangles,
                            "parameter_coordinates": coordinates.tolist(), "units": UNITS, "frame": FRAME},
                   "appearance": deepcopy(request["appearance"]), "claims": deepcopy(CLAIMS),
                   "ir": [compile_uv(expression, definition["parameters"]) for expression in definition["expressions"]]})
    validated = validate_surface_result(request, result)
    if monotonic() - started > MAX_GENERATION_SECONDS:
        raise ValueError("Surface generation exceeded its cooperative 15-second deadline")
    return validated


def example_surface() -> dict:
    radial = "(R+r*cos(v))"
    return validate_surface_request({"schema": REQUEST_SCHEMA,
        "definition": {"expressions": [f"cos(a)*{radial}*cos(u)+sin(a)*r*sin(v)",
                         f"{radial}*sin(u)", f"-sin(a)*{radial}*cos(u)+cos(a)*r*sin(v)"],
                       "parameters": {"R": {"value": 0.65, "minimum": 0.4, "maximum": 0.85},
                                      "r": {"value": 0.22, "minimum": 0.08, "maximum": 0.3},
                                      "a": {"value": 0.35, "minimum": -1.5, "maximum": 1.5}}},
        "domain": {"bounds": [[0.0, 2 * math.pi], [0.0, 2 * math.pi]], "resolution": [24, 16],
                   "periodic": [True, True], "units": UNITS, "frame": FRAME},
        "appearance": {"base_color": [0.64, 0.38, 0.82], "roughness": 0.35, "metallic": 0.35},
        "verification": {"field_tolerance": 0.001, "require_closed": True}})
