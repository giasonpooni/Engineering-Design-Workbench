"""Data-only bounded notation and visual mesh declarations.

The safe interpreter accepts dimensionless scalar algebra. It does not execute
Python code, load providers, generate meshes, or establish physical properties.
"""
from __future__ import annotations

import ast
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import json
import math
import re

import numpy as np

from .control_contracts import MAX_BYTES, keys, number
from .operations.runner import check_seal, digest

REQUEST_SCHEMA = "ciw.procedural-request.v1"
RESULT_SCHEMA = "ciw.procedural-mesh.v1"
UNITS = "normalized_length"
FRAME = "procedural.local_xyz.v1"
MAX_VERTICES = 40000
MAX_TRIANGLES = 65536
MAX_FIELD_SAMPLES = 200000
FIELD_LIMIT = 1e6
FUNCTIONS = {"sin": 1, "cos": 1, "abs": 1, "sqrt": 1, "min": 2, "max": 2}
CLAIMS = {"scope": "visual_only", "physical_validation": "not_established",
          "manufacturing": "not_established", "continuous_fidelity": "not_established",
          "self_intersections": "not_checked"}


def _parameter_names(parameters) -> set[str]:
    if parameters is None:
        return set()
    if type(parameters) is not dict or len(parameters) > 8:
        raise ValueError("Require at most eight declared parameters")
    for name in parameters:
        if (type(name) is not str or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,31}", name) is None
                or name in {"x", "y", "z"} | set(FUNCTIONS)):
            raise ValueError("Parameter names must be bounded unreserved ASCII identifiers")
    return set(parameters)


def parse_expression(expression: str, parameters: dict | None = None) -> ast.Expression:
    """Validate a small algebra grammar; returned AST contains no executable code."""
    if type(expression) is not str or not expression.strip() or len(expression) > 1024:
        raise ValueError("Notation must be nonempty and at most 1024 characters")
    names = {"x", "y", "z"} | _parameter_names(parameters)
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, RecursionError, ValueError) as exc:
        raise ValueError("Invalid algebraic notation") from exc
    if sum(1 for _ in ast.walk(tree)) > 128:
        raise ValueError("Notation exceeds the 128-node budget")

    def visit(node, depth):
        if depth > 16:
            raise ValueError("Notation exceeds the 16-level depth budget")
        if type(node) is ast.Expression:
            visit(node.body, depth + 1)
        elif type(node) is ast.Constant:
            if type(node.value) not in (int, float) or abs(node.value) > FIELD_LIMIT or not math.isfinite(node.value):
                raise ValueError("Require finite bounded real literals")
            if type(node.value) is float and node.value == 0.0:
                try:
                    exact = Decimal(ast.get_source_segment(expression, node))
                except (InvalidOperation, ValueError, TypeError) as exc:
                    raise ValueError("Invalid decimal literal") from exc
                if exact != 0:
                    raise ValueError("Nonzero literals must not silently underflow binary64 to zero")
        elif type(node) is ast.Name:
            if node.id not in names or type(node.ctx) is not ast.Load:
                raise ValueError("Unknown notation identifier")
        elif type(node) is ast.UnaryOp and type(node.op) in (ast.UAdd, ast.USub):
            visit(node.operand, depth + 1)
        elif type(node) is ast.BinOp and type(node.op) in (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow):
            if type(node.op) is ast.Pow and (type(node.right) is not ast.Constant
                    or type(node.right.value) is not int or not 0 <= node.right.value <= 6):
                raise ValueError("Powers require a literal integer exponent inside 0..6")
            visit(node.left, depth + 1)
            visit(node.right, depth + 1)
        elif type(node) is ast.Call:
            if (type(node.func) is not ast.Name or node.func.id not in FUNCTIONS
                    or node.keywords or len(node.args) != FUNCTIONS[node.func.id]):
                raise ValueError("Only declared functions with exact arity are allowed")
            for argument in node.args:
                visit(argument, depth + 1)
        else:
            raise ValueError("Unsupported algebraic syntax")

    visit(tree, 0)
    return tree


def _real_array(value):
    try:
        value = np.asarray(value)
        if value.dtype.kind not in "iuf":
            raise ValueError("Require real numeric coordinates without implicit text/complex conversion")
        value = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Require finite bounded scalar or array coordinates") from exc
    return value


def _finite_field(value):
    value = _real_array(value)
    if value.size > MAX_FIELD_SAMPLES:
        raise ValueError("Field samples exceed the bounded interpreter profile")
    if np.any(~np.isfinite(value)) or np.any(np.abs(value) > FIELD_LIMIT):
        raise ValueError("Field arithmetic exceeds the finite 1e6 value budget")
    return value


def evaluate(expression: str, parameters: dict, x, y, z):
    """Interpret allowlisted algebra over scalar or broadcast-compatible arrays."""
    tree = parse_expression(expression, parameters)
    environment = {"x": _finite_field(x), "y": _finite_field(y), "z": _finite_field(z)}
    try:
        shape = np.broadcast_shapes(environment["x"].shape, environment["y"].shape, environment["z"].shape)
    except ValueError as exc:
        raise ValueError("Coordinate arrays must have compatible shapes") from exc
    if math.prod(shape) > MAX_FIELD_SAMPLES:
        raise ValueError("Broadcast field samples exceed the bounded interpreter profile")
    for name, declaration in parameters.items():
        value = declaration.get("value") if type(declaration) is dict else declaration
        environment[name] = _finite_field(number(value))
    functions = {"sin": np.sin, "cos": np.cos, "abs": np.abs, "sqrt": np.sqrt,
                 "min": np.minimum, "max": np.maximum}

    def interpret(node):
        if type(node) is ast.Constant:
            return _finite_field(node.value)
        if type(node) is ast.Name:
            return environment[node.id]
        if type(node) is ast.UnaryOp:
            value = interpret(node.operand)
            return _finite_field(-value if type(node.op) is ast.USub else value)
        if type(node) is ast.BinOp:
            left, right = interpret(node.left), interpret(node.right)
            if type(node.op) is ast.Add:
                value = left + right
            elif type(node.op) is ast.Sub:
                value = left - right
            elif type(node.op) is ast.Mult:
                value = left * right
            elif type(node.op) is ast.Div:
                value = left / right
            else:
                value = left ** right
            return _finite_field(value)
        return _finite_field(functions[node.func.id](*(interpret(argument) for argument in node.args)))

    try:
        with np.errstate(all="raise"):
            value = interpret(tree.body)
            result = np.broadcast_to(value, shape)
    except (FloatingPointError, OverflowError, ValueError, TypeError) as exc:
        raise ValueError("Undefined or out-of-budget field arithmetic") from exc
    return float(result) if result.ndim == 0 else result


def _bounded(value, lower, upper, label):
    value = number(value)
    if not lower <= value <= upper:
        raise ValueError(f"{label} must be inside {lower}..{upper}")
    return value


def validate_request(request: dict) -> dict:
    """Return detached strict data; checking notation never evaluates its field."""
    keys(request, {"schema", "definition", "domain", "surface", "appearance", "verification"})
    if request["schema"] != REQUEST_SCHEMA:
        raise ValueError("Unsupported procedural request schema")
    definition = request["definition"]
    keys(definition, {"expression", "parameters"})
    _parameter_names(definition["parameters"])
    for name, parameter in definition["parameters"].items():
        keys(parameter, {"value", "minimum", "maximum"})
        lower = _bounded(parameter["minimum"], -FIELD_LIMIT, FIELD_LIMIT, name + ".minimum")
        upper = _bounded(parameter["maximum"], -FIELD_LIMIT, FIELD_LIMIT, name + ".maximum")
        _bounded(parameter["value"], lower, upper, name + ".value")
    parse_expression(definition["expression"], definition["parameters"])
    domain = request["domain"]
    keys(domain, {"bounds", "resolution", "units", "frame"})
    if domain["units"] != UNITS or domain["frame"] != FRAME:
        raise ValueError("Require the declared normalized Cartesian frame")
    if type(domain["bounds"]) is not list or len(domain["bounds"]) != 3:
        raise ValueError("Require three Cartesian axis bounds")
    for bounds in domain["bounds"]:
        if type(bounds) is not list or len(bounds) != 2:
            raise ValueError("Each Cartesian bound must contain lower and upper values")
        lower, upper = (_bounded(value, -10, 10, "domain bound") for value in bounds)
        if upper - lower < 0.1:
            raise ValueError("Each axis span must be at least 0.1")
    if type(domain["resolution"]) is not int or not 8 <= domain["resolution"] <= 24:
        raise ValueError("Resolution must be an integer inside 8..24")
    keys(request["surface"], {"isovalue", "convention"})
    if number(request["surface"]["isovalue"]) != 0 or request["surface"]["convention"] != "negative_inside":
        raise ValueError("Require zero isovalue and negative-inside convention")
    appearance = request["appearance"]
    keys(appearance, {"base_color", "roughness", "metallic"})
    if type(appearance["base_color"]) is not list or len(appearance["base_color"]) != 3:
        raise ValueError("Require three visual base-color channels")
    for value in appearance["base_color"]:
        _bounded(value, 0, 1, "base color")
    _bounded(appearance["roughness"], 0.05, 1, "roughness")
    _bounded(appearance["metallic"], 0, 1, "metallic")
    keys(request["verification"], {"field_tolerance", "require_closed"})
    _bounded(request["verification"]["field_tolerance"], 0.001, 2, "field tolerance")
    if type(request["verification"]["require_closed"]) is not bool:
        raise ValueError("require_closed must be a boolean")
    return deepcopy(request)


def request_digest(request: dict) -> str:
    return digest(validate_request(request))


def evaluate_field(request: dict, points):
    """Evaluate the declared scalar field at an explicit finite Nx3 array."""
    request = validate_request(request)
    points = _real_array(points)
    if points.ndim != 2 or points.shape[1] != 3 or len(points) > MAX_FIELD_SAMPLES:
        raise ValueError("Require a bounded Nx3 coordinate array")
    definition = request["definition"]
    return evaluate(definition["expression"], definition["parameters"], points[:, 0], points[:, 1], points[:, 2])


def validate_result(request: dict, result: dict) -> dict:
    """Static bounded structure/bindings only; no field or geometry evaluation."""
    request = validate_request(request)
    keys(result, {"schema", "request_digest", "mesh", "appearance", "claims", "record_digest"})
    if result["schema"] != RESULT_SCHEMA or result["request_digest"] != digest(request):
        raise ValueError("Procedural result schema or request binding differs")
    appearance = result["appearance"]
    keys(appearance, {"base_color", "roughness", "metallic"})
    if type(appearance["base_color"]) is not list or len(appearance["base_color"]) != 3:
        raise ValueError("Require three retained visual base-color channels")
    for value in appearance["base_color"]:
        _bounded(value, 0, 1, "retained base color")
    _bounded(appearance["roughness"], 0.05, 1, "retained roughness")
    _bounded(appearance["metallic"], 0, 1, "retained metallic")
    if result["appearance"] != request["appearance"] or result["claims"] != CLAIMS:
        raise ValueError("Appearance or visual-only claim binding differs")
    mesh = result["mesh"]
    keys(mesh, {"vertices", "triangles", "edge_sources", "units", "frame"})
    if mesh["units"] != UNITS or mesh["frame"] != FRAME:
        raise ValueError("Mesh units or frame differs")
    vertices, triangles, sources = mesh["vertices"], mesh["triangles"], mesh["edge_sources"]
    if type(vertices) is not list or not 3 <= len(vertices) <= MAX_VERTICES:
        raise ValueError("Mesh vertex count exceeds the profile")
    if type(triangles) is not list or not 1 <= len(triangles) <= MAX_TRIANGLES:
        raise ValueError("Mesh triangle count exceeds the profile")
    if type(sources) is not list or len(sources) != len(vertices):
        raise ValueError("Every mesh vertex must retain one grid-edge source")
    for vertex in vertices:
        if type(vertex) is not list or len(vertex) != 3:
            raise ValueError("Require Cartesian mesh vertices")
        for coordinate in vertex:
            _bounded(coordinate, -10, 10, "mesh coordinate")
    for triangle in triangles:
        if (type(triangle) is not list or len(triangle) != 3
                or any(type(index) is not int or not 0 <= index < len(vertices) for index in triangle)):
            raise ValueError("Triangle indices exceed the mesh vertex array")
    grid_count = (request["domain"]["resolution"] + 1) ** 3
    for source in sources:
        if (type(source) is not list or len(source) != 3
                or any(type(index) is not int or not 0 <= index < grid_count for index in source[:2])
                or source[0] > source[1]):
            raise ValueError("Grid-edge source indices exceed the declared ordered grid")
        _bounded(source[2], 0, 1, "edge interpolation")
    check_seal(result)
    # The retained substrate writes indented JSON plus a final newline. Use
    # that actual serialization budget, rather than compact JSON which can
    # understate the size of the artifact that users will inspect/replay.
    if len((json.dumps(result, indent=2, allow_nan=False) + "\n").encode()) > MAX_BYTES:
        raise ValueError("Mesh output exceeds the 8MiB artifact budget")
    return deepcopy(result)


def example_request(profile: str = "gyroid") -> dict:
    """Dimensionless visual examples; none asserts material/manufacturing validity."""
    definitions = {
        "gyroid": ("abs(sin(k*x)*cos(k*y)+sin(k*y)*cos(k*z)+sin(k*z)*cos(k*x))-tau",
                   {"k": {"value": 2.0, "minimum": 1.0, "maximum": 6.0},
                    "tau": {"value": 0.5, "minimum": 0.1, "maximum": 0.6}}, False, 0.2),
        "sphere": ("x*x+y*y+z*z-r*r", {"r": {"value": 0.7, "minimum": 0.2, "maximum": 0.85}}, True, 0.05),
        "wave": ("z-a*sin(k*x)*cos(k*y)",
                 {"a": {"value": 0.3, "minimum": 0.05, "maximum": 0.6},
                  "k": {"value": 2.5, "minimum": 1.0, "maximum": 6.0}}, False, 0.15),
    }
    if profile not in definitions:
        raise ValueError("Unknown procedural example")
    expression, parameters, closed, tolerance = definitions[profile]
    return validate_request({"schema": REQUEST_SCHEMA,
        "definition": {"expression": expression, "parameters": parameters},
        "domain": {"bounds": [[-1.0, 1.0], [-1.0, 1.0], [-1.0, 1.0]], "resolution": 16,
                   "units": UNITS, "frame": FRAME},
        "surface": {"isovalue": 0.0, "convention": "negative_inside"},
        "appearance": {"base_color": [0.22, 0.68, 0.76], "roughness": 0.45, "metallic": 0.2},
        "verification": {"field_tolerance": tolerance, "require_closed": closed}})
